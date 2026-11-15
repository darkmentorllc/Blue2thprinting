#!/usr/bin/env python3
"""Corroborate DM BT Nordic Secure DFU probe JSONL with an H4 BTSnoop log.

This is an offline, read-only verifier. It never connects to a Bluetooth device.
It checks the exact Get CRC ATT exchange and whether HCI shows pairing or link
encryption before the successful response. An Android GATT callback alone cannot
establish the link security state.

Non-rooted phone workflow:
    1. Enable *full* Bluetooth HCI snoop logging in Android Developer options.
    2. Run the DM BT probe, then collect a phone bugreport with ``adb bugreport``.
    3. Extract ``FS/data/misc/bluetooth/logs/btsnoop_hci.log`` from the bugreport.
    4. Export ``nordic_secure_dfu_probe_results.jsonl`` from DM BT.
    5. Run this tool on those two files. Keep the full bugreport and all-device
       HCI log private; share only target-specific extracts or verdict rows.

Usage:
    python3 Analysis/verify_dm_bt_dfu_hci.py \
      --btsnoop /path/to/btsnoop_hci.log \
      --probe-jsonl /path/to/nordic_secure_dfu_probe_results.jsonl \
      --output-jsonl /path/to/verdicts.jsonl \
      --output-csv /path/to/verdicts.csv

The output uses the same ``hci*`` field names as the DM BT on-device verifier.
An ``INCONCLUSIVE`` verdict is appropriate when the capture misses required
packets. Only ``VERIFIED_UNENCRYPTED`` demonstrates the safe probe's successful
response before any observed pairing/encryption transition on that connection.
Newer DM BT records include ``connection_time_ms`` and ``probe_started_at_ms``;
these bound connection selection and ATT matching. Older JSONL remains supported
with the configurable completion-time window.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import json
import struct
import sys
from pathlib import Path
from typing import Any

from hci_log_parser import HCILogRecord, parse as parse_hci_log


DFU_CP_UUID = "8ec90001f3154f609fb8838830daea50"
SECURITY_ERROR_CODES = {0x05, 0x0C, 0x0F}
START_TIME_TOLERANCE_MS = 25  # Same phone clock; allow only timestamp rounding/scheduling jitter.
CONNECTION_TIME_TOLERANCE_MS = 1000


def _u16(data: bytes) -> int:
    return int.from_bytes(data[:2], "little")


def _millis(timestamp: dt.datetime) -> int:
    # hci_log_parser returns UTC wall time without tzinfo for BTSnoop.
    return int(timestamp.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def _iso(millis: int | None) -> str | None:
    if millis is None:
        return None
    return dt.datetime.fromtimestamp(millis / 1000, dt.timezone.utc).isoformat(timespec="milliseconds")


def _address(raw_le: bytes) -> str:
    return ":".join(f"{byte:02X}" for byte in reversed(raw_le))


def _normalize_address(value: Any) -> str:
    raw = str(value or "").replace(":", "").replace("-", "").upper()
    if len(raw) != 12 or any(char not in "0123456789ABCDEF" for char in raw):
        raise ValueError(f"Invalid Bluetooth address: {value!r}")
    return ":".join(raw[pos:pos + 2] for pos in range(0, 12, 2))


def _handle(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    return int(str(value), 0)


@dataclasses.dataclass
class Session:
    peer: str
    address_type: int
    handle: int
    connection_frame: int
    connection_ms: int
    disconnect_frame: int | None = None
    disconnect_ms: int | None = None
    att: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    security: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    service_frames: list[int] = dataclasses.field(default_factory=list)
    characteristic_declarations: dict[int, tuple[str, int]] = dataclasses.field(default_factory=dict)
    descriptors: dict[int, tuple[int, int]] = dataclasses.field(default_factory=dict)
    fragments: dict[int, tuple[int, int, bytes]] = dataclasses.field(default_factory=dict)
    missing_fragments: bool = False
    capture_issue_frames: list[int] = dataclasses.field(default_factory=list)
    first_drops: int | None = None

    def add_security(self, record: HCILogRecord, kind: str, **detail: Any) -> None:
        self.security.append({"frame": record.seq, "timeMs": _millis(record.ts), "kind": kind, **detail})


def _parse_att(session: Session, record: HCILogRecord, direction: int, pdu: bytes) -> None:
    if not pdu:
        return
    opcode = pdu[0]
    event: dict[str, Any] = {
        "frame": record.seq, "timeMs": _millis(record.ts),
        "direction": "host_to_device" if direction == 0 else "device_to_host",
        "opcode": opcode,
    }
    if opcode in (0x12, 0x52, 0x1B, 0x1D) and len(pdu) >= 3:
        event["handle"] = _u16(pdu[1:3])
        event["value"] = pdu[3:].hex()
    elif opcode == 0x01 and len(pdu) >= 5:
        event.update({"requestOpcode": pdu[1], "handle": _u16(pdu[2:4]), "errorCode": pdu[4]})
    elif opcode == 0x11 and len(pdu) >= 2:
        item_length = pdu[1]
        if item_length >= 6:
            for offset in range(2, len(pdu) - item_length + 1, item_length):
                item = pdu[offset:offset + item_length]
                if item_length == 6 and _u16(item[4:6]) == 0xFE59:
                    session.service_frames.append(record.seq)
    elif opcode == 0x09 and len(pdu) >= 2:
        item_length = pdu[1]
        if item_length in (7, 21):
            for offset in range(2, len(pdu) - item_length + 1, item_length):
                item = pdu[offset:offset + item_length]
                value_handle = _u16(item[3:5])
                raw_uuid = item[5:]
                uuid = raw_uuid[::-1].hex() if len(raw_uuid) == 16 else f"{_u16(raw_uuid):04x}"
                session.characteristic_declarations[value_handle] = (uuid, record.seq)
    elif opcode == 0x05 and len(pdu) >= 2:
        item_length = {1: 4, 2: 18}.get(pdu[1])
        if item_length:
            for offset in range(2, len(pdu) - item_length + 1, item_length):
                item = pdu[offset:offset + item_length]
                if item_length == 4:
                    session.descriptors[_u16(item[:2])] = (_u16(item[2:4]), record.seq)
    session.att.append(event)


def _parse_acl(session: Session, record: HCILogRecord) -> None:
    data = record.data
    if len(data) < 5:
        return
    word = _u16(data[1:3])
    pb = (word >> 12) & 0x3
    direction = record.flags & 1
    length = _u16(data[3:5])
    fragment = data[5:5 + length]
    if len(fragment) != length:
        session.missing_fragments = True
        return
    if pb in (0, 2, 3):
        if direction in session.fragments:
            # A new L2CAP start abandoned an earlier partial PDU. The missing
            # bytes could have contained SMP or ATT security evidence.
            session.missing_fragments = True
            session.fragments.pop(direction, None)
        if len(fragment) < 4:
            session.missing_fragments = True
            return
        expected = _u16(fragment[:2])
        cid = _u16(fragment[2:4])
        payload = fragment[4:]
        if len(payload) > expected:
            session.missing_fragments = True
            return
        if len(payload) < expected:
            session.fragments[direction] = (expected, cid, payload)
            return
    elif pb == 1:
        pending = session.fragments.get(direction)
        if pending is None:
            session.missing_fragments = True
            return
        expected, cid, previous = pending
        payload = previous + fragment
        if len(payload) > expected:
            session.missing_fragments = True
            session.fragments.pop(direction, None)
            return
        if len(payload) < expected:
            session.fragments[direction] = (expected, cid, payload)
            return
    else:
        return
    session.fragments.pop(direction, None)
    payload = payload[:expected]
    if cid == 0x0004:
        _parse_att(session, record, direction, payload)
    elif cid == 0x0006 and payload:
        session.add_security(record, "SMP", direction="host_to_device" if direction == 0 else "device_to_host", smpOpcode=payload[0])


def _inspect_h4_btsnoop(path: Path) -> tuple[set[int], bool]:
    """Find truncated records that the shared HCI parser otherwise tolerates.

    The main parser deliberately skips an incomplete tail for bulk ingestion;
    a security verdict must instead know when capture integrity is uncertain.
    """
    truncated_records: set[int] = set()
    with path.open("rb") as stream:
        if stream.read(8) != b"btsnoop\x00":
            raise ValueError("Expected a BTSnoop H4 file")
        header = stream.read(8)
        if len(header) != 8:
            raise ValueError("Truncated BTSnoop header")
        version, data_link_type = struct.unpack(">II", header)
        if version != 1 or data_link_type != 1002:
            raise ValueError(f"Expected BTSnoop version 1, H4/UART datalink 1002; got {version}/{data_link_type}")
        sequence = 0
        tail_truncated = False
        while True:
            record_header = stream.read(24)
            if not record_header:
                break
            sequence += 1
            if len(record_header) != 24:
                tail_truncated = True
                truncated_records.add(sequence)
                break
            original_length, included_length, _, _, timestamp = struct.unpack(">IIIIq", record_header)
            if included_length == 0 or timestamp == 0:
                raise ValueError(f"Invalid BTSnoop record {sequence}: empty packet or zero timestamp")
            if original_length != included_length:
                truncated_records.add(sequence)
            if len(stream.read(included_length)) != included_length:
                tail_truncated = True
                truncated_records.add(sequence)
                break
    return truncated_records, tail_truncated


def parse_sessions(records: list[HCILogRecord], truncated_records: set[int] | None = None) -> list[Session]:
    """Build LE connection sessions, distinguishing recycled controller handles."""
    sessions: list[Session] = []
    active: dict[int, Session] = {}
    truncated_records = truncated_records or set()
    for record in records:
        for session in active.values():
            if record.seq in truncated_records:
                session.capture_issue_frames.append(record.seq)
            if record.drops is not None:
                if session.first_drops is None:
                    session.first_drops = record.drops
                elif record.drops > session.first_drops:
                    session.capture_issue_frames.append(record.seq)
                    session.first_drops = record.drops
        data = record.data
        if not data:
            for session in active.values():
                session.capture_issue_frames.append(record.seq)
            continue
        if data[0] == 4:
            if len(data) < 3 or len(data[3:]) < data[2]:
                for session in active.values():
                    session.capture_issue_frames.append(record.seq)
                continue
            code = data[1]
            params = data[3:3 + data[2]]
            if code == 0x3E and len(params) >= 12 and params[0] in (0x01, 0x0A) and params[1] == 0:
                handle = _u16(params[2:4]) & 0x0FFF
                prior = active.pop(handle, None)
                if prior is not None:
                    prior.missing_fragments = True
                session = Session(
                    peer=_address(params[6:12]), address_type=params[5],
                    handle=handle, connection_frame=record.seq, connection_ms=_millis(record.ts),
                )
                session.first_drops = record.drops
                if record.seq in truncated_records:
                    session.capture_issue_frames.append(record.seq)
                sessions.append(session)
                active[handle] = session
            elif code == 0x05 and len(params) >= 4:
                handle = _u16(params[1:3]) & 0x0FFF
                session = active.pop(handle, None)
                if session is not None:
                    if session.fragments:
                        session.missing_fragments = True
                        session.fragments.clear()
                    session.disconnect_frame = record.seq
                    session.disconnect_ms = _millis(record.ts)
            elif code in (0x08, 0x59) and len(params) >= 4:
                handle = _u16(params[1:3]) & 0x0FFF
                if handle in active:
                    active[handle].add_security(record, "ENCRYPTION_CHANGE", status=params[0], enabled=bool(params[3]))
            elif code == 0x30 and len(params) >= 3:
                handle = _u16(params[1:3]) & 0x0FFF
                if handle in active:
                    active[handle].add_security(record, "ENCRYPTION_KEY_REFRESH", status=params[0])
            elif code == 0x3E and len(params) >= 3 and params[0] == 0x05:
                handle = _u16(params[1:3]) & 0x0FFF
                if handle in active:
                    active[handle].add_security(record, "LE_LONG_TERM_KEY_REQUEST")
        elif data[0] == 1:
            if len(data) < 4 or len(data[4:]) < data[3]:
                for session in active.values():
                    session.capture_issue_frames.append(record.seq)
                continue
            opcode = _u16(data[1:3])
            params = data[4:4 + data[3]]
            if opcode in (0x2019, 0x201A, 0x201B, 0x0413) and len(params) >= 2:
                handle = _u16(params[:2]) & 0x0FFF
                if handle in active:
                    active[handle].add_security(record, {
                        0x2019: "LE_START_ENCRYPTION_COMMAND",
                        0x201A: "LE_LONG_TERM_KEY_REPLY",
                        0x201B: "LE_LONG_TERM_KEY_NEGATIVE_REPLY",
                        0x0413: "SET_CONNECTION_ENCRYPTION_COMMAND",
                    }[opcode])
        elif data[0] == 2:
            if len(data) < 5:
                for session in active.values():
                    session.capture_issue_frames.append(record.seq)
                continue
            handle = _u16(data[1:3]) & 0x0FFF
            if handle in active:
                _parse_acl(active[handle], record)
    for session in active.values():
        if session.fragments:
            session.missing_fragments = True
    return sessions


def _resolve_cccd(session: Session, cp_handle: int, app_handle: int | None) -> tuple[int | None, str]:
    if app_handle is not None:
        return app_handle, "app_jsonl"
    candidates = sorted(handle for handle, (uuid, _) in session.descriptors.items()
                        if uuid == 0x2902 and handle > cp_handle)
    if candidates:
        return candidates[0], "hci_descriptor_discovery"
    return None, "unresolved"


def _pair_write_responses(events: list[dict[str, Any]]) -> None:
    pending: list[dict[str, Any]] = []
    for event in events:
        opcode = event["opcode"]
        if opcode == 0x12 and event["direction"] == "host_to_device":
            pending.append(event)
        elif opcode == 0x13 and event["direction"] == "device_to_host" and pending:
            pending.pop(0)["responseFrame"] = event["frame"]
        elif opcode == 0x01 and event.get("requestOpcode") == 0x12:
            for index, request in enumerate(pending):
                if request.get("handle") == event.get("handle"):
                    request["errorFrame"] = event["frame"]
                    request["errorCode"] = event["errorCode"]
                    pending.pop(index)
                    break


def _base_result(probe: dict[str, Any], line: int, source: str) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "probeLine": line,
        "address": probe.get("address"),
        "probeTimeMs": probe.get("time_ms"),
        "probeStartedAtMs": probe.get("probe_started_at_ms"),
        "appConnectionTimeMs": probe.get("connection_time_ms"),
        "appOutcome": probe.get("outcome"),
        "hciVerdict": "INCONCLUSIVE",
        "hciConnectionHandle": None,
        "hciConnectionAddressType": None,
        "hciConnectionFrame": None,
        "hciConnectionTime": None,
        "hciCorrelationWindowStartMs": None,
        "hciDisconnectFrame": None,
        "hciDisconnectTime": None,
        "hciServiceFrames": [],
        "hciControlPointDeclarationFrame": None,
        "hciCpWriteFrames": [],
        "hciCpWriteResponseFrames": [],
        "hciCccdHandle": None,
        "hciCccdHandleSource": None,
        "hciCccdWriteFrames": [],
        "hciCccdWriteResponseFrames": [],
        "hciCrcNotificationFrame": None,
        "hciCrcResponseHex": None,
        "hciAttErrorFrames": [],
        "hciAttErrors": [],
        "hciCaptureIssueFrames": [],
        "hciSecurityEventFrames": [],
        "hciSecurityEvents": [],
        "hciSource": source,
        "hciDetail": "",
    }


def verify_probe(probe: dict[str, Any], line: int, sessions: list[Session], source: str,
                 window_ms: int = 30_000) -> dict[str, Any]:
    result = _base_result(probe, line, source)
    try:
        address = _normalize_address(probe.get("address"))
        time_ms = int(probe["time_ms"])
        cp_handle = _handle(probe.get("control_point_value_handle"))
        app_cccd_handle = _handle(probe.get("cccd_handle"))
        app_address_type = _handle(probe.get("address_type"))
        probe_start_ms = _handle(probe.get("probe_started_at_ms"))
        app_connection_ms = _handle(probe.get("connection_time_ms"))
        if cp_handle is None:
            raise ValueError("Missing control_point_value_handle")
        if probe_start_ms is not None and probe_start_ms > time_ms:
            raise ValueError("probe_started_at_ms occurs after time_ms")
        if probe.get("service_uuid") and str(probe["service_uuid"]).lower() != "0000fe59-0000-1000-8000-00805f9b34fb":
            raise ValueError("Probe service UUID is not FE59")
        if probe.get("control_point_uuid") and str(probe["control_point_uuid"]).replace("-", "").lower() != DFU_CP_UUID:
            raise ValueError("Probe Control Point UUID differs from Nordic Secure DFU")
    except (ValueError, KeyError, TypeError) as exc:
        result["hciDetail"] = f"Invalid probe record: {exc}"
        return result

    lower_bound_ms = max(time_ms - window_ms, probe_start_ms - START_TIME_TOLERANCE_MS) \
        if probe_start_ms is not None else time_ms - window_ms
    result["hciCorrelationWindowStartMs"] = lower_bound_ms
    candidates = [session for session in sessions if session.peer == address
                  and (app_address_type is None or session.address_type == app_address_type)
                  and (app_connection_ms is None or
                       abs(session.connection_ms - app_connection_ms) <= CONNECTION_TIME_TOLERANCE_MS)
                  and session.connection_ms <= time_ms
                  and (session.disconnect_ms is None or session.disconnect_ms >= time_ms - window_ms)]
    if not candidates:
        result.update(hciVerdict="NO_MATCHING_CONNECTION",
                      hciDetail="No complete LE connection event for this address/address type and "
                                "optional connection timestamp within the time window")
        return result
    active_probe_candidates = [session for session in candidates if any(
        event["opcode"] == 0x12 and event.get("handle") == cp_handle and event.get("value") == "03"
        and lower_bound_ms <= event["timeMs"] <= time_ms for event in session.att)]
    matching = active_probe_candidates or candidates
    if len(matching) != 1:
        result.update(hciVerdict="AMBIGUOUS_SESSION",
                      hciDetail="Multiple same-address LE sessions match the probe time and Control Point handle; "
                                f"connection frames: {[session.connection_frame for session in matching]}")
        return result
    session = matching[0]
    result.update(
        address=address,
        hciConnectionHandle=f"0x{session.handle:04x}",
        hciConnectionAddressType=session.address_type,
        hciConnectionFrame=session.connection_frame,
        hciConnectionTime=_iso(session.connection_ms),
        hciDisconnectFrame=session.disconnect_frame,
        hciDisconnectTime=_iso(session.disconnect_ms),
        hciServiceFrames=session.service_frames,
        hciCaptureIssueFrames=sorted(set(session.capture_issue_frames)),
    )
    declaration = session.characteristic_declarations.get(cp_handle)
    if declaration:
        result["hciControlPointDeclarationFrame"] = declaration[1]
        if declaration[0] != DFU_CP_UUID:
            result["hciDetail"] = (f"HCI declaration at handle 0x{cp_handle:04x} is UUID "
                                   f"{declaration[0]}, not the Nordic DFU Control Point")
            return result

    cccd_handle, cccd_source = _resolve_cccd(session, cp_handle, app_cccd_handle)
    result.update(hciCccdHandle=f"0x{cccd_handle:04x}" if cccd_handle is not None else None,
                  hciCccdHandleSource=cccd_source)
    if app_cccd_handle is not None and cccd_handle in session.descriptors and session.descriptors[cccd_handle][0] != 0x2902:
        result["hciDetail"] = f"Configured CCCD handle 0x{cccd_handle:04x} has non-CCCD descriptor UUID in HCI"
        return result

    # Match the app record to nearby ATT activity on this exact connection.
    events = [dict(event) for event in session.att if lower_bound_ms <= event["timeMs"] <= time_ms]
    _pair_write_responses(events)
    cp_writes = [event for event in events if event["opcode"] == 0x12 and
                 event["direction"] == "host_to_device" and event.get("handle") == cp_handle and
                 event.get("value") == "03"]
    cccd_writes = [event for event in events if cccd_handle is not None and event["opcode"] == 0x12 and
                   event["direction"] == "host_to_device" and event.get("handle") == cccd_handle and
                   event.get("value") == "0100"]
    notifications = [event for event in events if event["opcode"] == 0x1B and
                     event["direction"] == "device_to_host" and event.get("handle") == cp_handle and
                     len(event.get("value", "")) == 22 and event.get("value", "").startswith("600301") and
                     event["timeMs"] <= time_ms]
    notification = min(notifications, key=lambda event: time_ms - event["timeMs"]) if notifications else None
    if notification:
        prior_response_frame = max((event["frame"] for event in notifications
                                    if event["frame"] < notification["frame"]), default=0)
        cp_writes = [event for event in cp_writes
                     if prior_response_frame < event["frame"] < notification["frame"]]
        cccd_writes = [event for event in cccd_writes
                       if prior_response_frame < event["frame"] < notification["frame"]]
    errors = [event for event in events if event["opcode"] == 0x01 and event.get("requestOpcode") == 0x12 and
              event.get("handle") in (cp_handle, cccd_handle)]
    result.update(
        hciCpWriteFrames=[event["frame"] for event in cp_writes],
        hciCpWriteResponseFrames=[event["responseFrame"] for event in cp_writes if "responseFrame" in event],
        hciCccdWriteFrames=[event["frame"] for event in cccd_writes],
        hciCccdWriteResponseFrames=[event["responseFrame"] for event in cccd_writes if "responseFrame" in event],
        hciAttErrorFrames=[event["frame"] for event in errors],
        hciAttErrors=[{"frame": event["frame"], "handle": f"0x{event['handle']:04x}",
                       "requestOpcode": f"0x{event['requestOpcode']:02x}",
                       "errorCode": f"0x{event['errorCode']:02x}"} for event in errors],
        hciSecurityEventFrames=[event["frame"] for event in session.security],
        hciSecurityEvents=session.security,
    )
    if notification:
        result.update(hciCrcNotificationFrame=notification["frame"],
                      hciCrcResponseHex=notification["value"])

    security_cutoff_ms = notification["timeMs"] if notification else time_ms
    security_before_response = [event for event in session.security if event["timeMs"] <= security_cutoff_ms]
    if security_before_response:
        if cp_writes:
            result.update(hciVerdict="ENCRYPTED_OR_PAIRED",
                          hciDetail="Pairing or encryption activity was observed on this connection before the "
                                    f"CRC response or probe end: {[event['kind'] for event in security_before_response]}")
        else:
            result["hciDetail"] = ("Pairing/encryption activity occurred on the connection, but no "
                                   "Control Point Get CRC write matches this app probe window")
        return result
    if session.capture_issue_frames or session.missing_fragments:
        issues = [f"BTSnoop packet loss/truncation at frames {sorted(set(session.capture_issue_frames))}"] if session.capture_issue_frames else []
        if session.missing_fragments:
            issues.append("missing or incomplete ACL/L2CAP fragments")
        result["hciDetail"] = "Capture integrity is insufficient to rule out a security transition: " + "; ".join(issues)
        return result

    # DM BT's automatic probe sends one Get CRC, subscribes, then confirms with
    # a second Get CRC. Require matching Write Responses and the final notification.
    confirmed_sequence = False
    for first in cp_writes:
        if "responseFrame" not in first:
            continue
        for cccd in cccd_writes:
            if cccd["frame"] <= first["responseFrame"] or "responseFrame" not in cccd:
                continue
            for second in cp_writes:
                if second["frame"] <= cccd["responseFrame"] or "responseFrame" not in second:
                    continue
                if notification and notification["frame"] > second["frame"]:
                    confirmed_sequence = True
                    break
            if confirmed_sequence:
                break
        if confirmed_sequence:
            break
    app_response = str(probe.get("crc_response_hex") or "").lower()
    app_claims_success = probe.get("outcome") == "CRC_RESPONSE_RECEIVED" and \
        len(app_response) == 22 and app_response.startswith("600301")
    if confirmed_sequence and notification and app_claims_success and app_response == notification["value"]:
        result.update(hciVerdict="VERIFIED_UNENCRYPTED",
                      hciDetail="Get CRC writes, CCCD notification enablement, three ATT Write Responses, "
                                "and success notification preceded any pairing/encryption activity")
    else:
        if (cp_writes or cccd_writes) and any(event.get("errorCode") in SECURITY_ERROR_CODES for event in errors):
            result.update(hciVerdict="AUTHENTICATION_REQUIRED",
                          hciDetail="Control Point or CCCD returned ATT insufficient authentication/encryption")
            return result
        if (cp_writes or cccd_writes) and any(event.get("errorCode") == 0x08 for event in errors):
            result.update(hciVerdict="ACCESS_RESTRICTED",
                          hciDetail="Control Point or CCCD returned ATT insufficient authorization")
            return result
        missing = []
        if len(cp_writes) < 2:
            missing.append("two Control Point Get CRC Write Requests")
        if not cccd_writes:
            missing.append("CCCD notification-enable Write Request at a discovered or app-recorded descriptor handle")
        if len(result["hciCpWriteResponseFrames"]) < 2 or not result["hciCccdWriteResponseFrames"]:
            missing.append("ATT Write Responses")
        if not notification:
            missing.append("successful Get CRC notification")
        if not app_claims_success:
            missing.append("app CRC_RESPONSE_RECEIVED outcome and its exact 11-byte CRC response")
        elif notification and notification["value"] != app_response:
            missing.append("matching app/HCI notification values")
        if not missing:
            missing.append("expected ATT event order")
        result["hciDetail"] = "Incomplete or inconsistent HCI evidence: " + ", ".join(missing)
        if session.missing_fragments:
            result["hciDetail"] += "; capture has missing ACL fragments"
    return result


def verify_file(btsnoop: Path, probe_jsonl: Path, window_seconds: float = 30.0) -> list[dict[str, Any]]:
    truncated_records, tail_truncated = _inspect_h4_btsnoop(btsnoop)
    records = parse_hci_log(str(btsnoop))
    sessions = parse_sessions(records, truncated_records)
    if tail_truncated:
        for session in sessions:
            if session.disconnect_frame is None:
                session.capture_issue_frames.append(max(truncated_records))
    output: list[dict[str, Any]] = []
    for line_number, line in enumerate(probe_jsonl.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            probe = json.loads(line)
            if not isinstance(probe, dict):
                raise ValueError("JSONL line must be an object")
        except (json.JSONDecodeError, ValueError) as exc:
            output.append({**_base_result({}, line_number, str(btsnoop)),
                           "hciDetail": f"Invalid JSONL line: {exc}"})
            continue
        output.append(verify_probe(probe, line_number, sessions, str(btsnoop), int(window_seconds * 1000)))
    return output


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(_base_result({}, 0, ""))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value) if isinstance(value, (list, dict)) else value
                             for key, value in row.items()})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--btsnoop", type=Path, required=True, help="H4 BTSnoop log exported from Android")
    parser.add_argument("--probe-jsonl", type=Path, required=True, help="DM BT Nordic probe results JSONL")
    parser.add_argument("--output-jsonl", "--output-json", dest="output_jsonl", type=Path,
                        help="Write one verdict JSON object per line (alias: --output-json)")
    parser.add_argument("--output-csv", type=Path, help="Also write verdict CSV")
    parser.add_argument("--window-seconds", type=float, default=30.0,
                        help="Maximum time gap between app result and HCI probe activity (default: 30)")
    args = parser.parse_args(argv)
    if args.window_seconds <= 0:
        parser.error("--window-seconds must be positive")
    try:
        rows = verify_file(args.btsnoop, args.probe_jsonl, args.window_seconds)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.output_jsonl:
        _write_jsonl(args.output_jsonl, rows)
    if args.output_csv:
        _write_csv(args.output_csv, rows)
    if not args.output_jsonl:
        for row in rows:
            print(json.dumps(row, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
