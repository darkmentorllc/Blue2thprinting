# Written by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026

"""Opt-in, one-shot access check for the Nordic Secure DFU Control Point.

The only DFU value transmitted here is GET_CRC (0x03). It reports transfer
state; it does not create, execute, abort, or write an object. If notifications
are required, the probe can enable the exact Control Point CCCD and repeat
GET_CRC once. It never writes the Packet characteristic. This is an access
check, not a test of the firmware-validation race.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import globals
from BG_Helper_All import write_outbound_pkt
from BG_Helper_ATT import opcode_ATT_ERROR_RSP, opcode_ATT_WRITE_REQ, opcode_ATT_WRITE_RSP, send_ATT_WRITE_REQ
from BG_Helper_Output import print_and_exit


DFU_SERVICE_UUID = "0000fe59-0000-1000-8000-00805f9b34fb"
CONTROL_POINT_UUID = "8ec90001-f315-4f60-9fb8-838830daea50"
PACKET_UUID = "8ec90002-f315-4f60-9fb8-838830daea50"
CONTROL_POINT_UUID_LE = bytes.fromhex(CONTROL_POINT_UUID.replace("-", ""))[::-1]
PACKET_UUID_LE = bytes.fromhex(PACKET_UUID.replace("-", ""))[::-1]
SERVICE_UUID_LE = bytes.fromhex(DFU_SERVICE_UUID.replace("-", ""))[::-1]
GET_CRC = b"\x03"
ENABLE_NOTIFICATIONS = b"\x01\x00"
LINK_SECURITY_ERRORS = {0x05, 0x0F}
ENCRYPTION_LL_OPCODES = {0x03, 0x04, 0x05, 0x06, 0x0A, 0x0B}
ATT_HANDLE_VALUE_NOTIFICATION = 0x1B


class NordicDfuAccessProbe:
    """Run only after complete structural GATT discovery on a fresh link."""

    def __init__(self, result_path, pcap_path, timeout_seconds=2.0,
                 initial_notification_grace_seconds=0.4):
        self.result_path = Path(result_path)
        self.timeout_seconds = timeout_seconds
        self.initial_notification_grace_seconds = initial_notification_grace_seconds
        self.sent_at = None
        self.stage = "discovery"
        self.pending_handle = None
        self.control_handle = None
        self.cccd_handle = None
        self.initial_control_admitted = False
        self.matching_notification_seen = False
        self.finished = False
        self.security_transition_observed = False
        self.result = {
            "schema_version": 1,
            "probe": "nordic_secure_dfu_control_point_get_crc_access",
            "status": "pending_discovery",
            "interpretation": "No Control Point access conclusion yet.",
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "bdaddr": globals.target_bdaddr,
            "bdaddr_type": "public" if globals.target_bdaddr_type_public else "random",
            "pcap_path": str(Path(pcap_path).resolve()),
            "service_uuid": DFU_SERVICE_UUID,
            "control_point_uuid": CONTROL_POINT_UUID,
            "packet_uuid": PACKET_UUID,
            "att_request_opcode": opcode_ATT_WRITE_REQ,
            "dfu_request_hex": GET_CRC.hex(),
            "attempts": 0,
            "control_point_att_admitted": False,
            "get_crc_notification_confirmed": False,
            "packet_write_access": "unknown",
            "toctou_implementation": "unknown",
            "observations": [],
            "link_context": {
                "fresh_connection": True,
                "pairing_attempted_by_probe": False,
                "encryption_procedure_observed": False,
                "peer_smp_signaling_observed": False,
                "ll_encryption_control_opcodes": [],
                "smp_opcodes_observed": [],
            },
        }
        self._persist()

    def _persist(self):
        """Atomically replace the sidecar so interrupted scans leave evidence."""
        self.result["observed_at_utc"] = datetime.now(timezone.utc).isoformat()
        self.result_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.result_path.with_name(f"{self.result_path.name}.tmp.{os.getpid()}")
        with temporary.open("w", encoding="utf-8") as output:
            json.dump(self.result, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, self.result_path)

    def _observe(self, direction, stage, att_opcode, handle=None, value_hex=None,
                 error_code=None):
        entry = {
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "direction": direction,
            "stage": stage,
            "att_opcode": att_opcode,
        }
        if handle is not None:
            entry["handle"] = handle
        if value_hex is not None:
            entry["value_hex"] = value_hex
        if error_code is not None:
            entry["error_code"] = error_code
        self.result["observations"].append(entry)
        self._persist()

    def observe_ll_control(self, opcode):
        if self.finished or opcode not in ENCRYPTION_LL_OPCODES:
            return
        self.security_transition_observed = True
        context = self.result["link_context"]
        context["encryption_procedure_observed"] = True
        context["ll_encryption_control_opcodes"].append(opcode)
        self._persist()
        self._finish_security_signal()

    def observe_smp(self, opcode):
        if self.finished:
            return
        self.security_transition_observed = True
        context = self.result["link_context"]
        context["peer_smp_signaling_observed"] = True
        context["smp_opcodes_observed"].append(opcode)
        self._persist()
        self._finish_security_signal()

    def _finish_security_signal(self):
        if self.stage == "discovery":
            self._finish("not_tested_security_transition",
                         "Encryption or SMP security signaling was observed before the plaintext access check.")
        else:
            self._finish("inconclusive_security_transition",
                         "Encryption or SMP security signaling was observed during the probe.")

    def _finish(self, status, interpretation, **details):
        self.finished = True
        self.result.update(details)
        self.result["status"] = status
        self.result["interpretation"] = interpretation
        self.result["connection_teardown_requested"] = True
        self._persist()
        print(f"Nordic DFU access probe: {status}; {interpretation}")
        if globals.received_handles:
            print_and_exit()
        else:
            # An early security signal can arrive before any GATT handles.
            # Still terminate the link without calling print_all_info(),
            # whose output requires at least one discovered handle.
            write_outbound_pkt(3, b"\x02\x13")
            time.sleep(0.1)
            raise SystemExit(0)

    def finish_interrupted(self):
        if self.finished:
            return
        self.finished = True
        self.result["status"] = "inconclusive_interrupted"
        self.result["interpretation"] = "The scan ended before a correlated ATT result."
        self._persist()

    def finish_link_lost(self):
        """The controller reported no active link; no ATT operation can remain pending."""
        if self.finished:
            return
        self.finished = True
        self.result["status"] = "inconclusive_link_lost"
        self.result["interpretation"] = "The BLE link ended before the probe completed."
        self.result["connection_teardown_requested"] = False
        self._persist()
        print("Nordic DFU access probe: link lost before a conclusive result")
        raise SystemExit(0)

    @staticmethod
    def _service_is_fe59(service_uuid, uuid_size):
        if uuid_size == 2:
            return service_uuid == 0xFE59 or service_uuid == b"\x59\xfe"
        return uuid_size == 16 and service_uuid == SERVICE_UUID_LE

    def _find_target(self):
        matches = []
        for begin, (end, service_uuid, uuid_size) in globals.primary_service_handle_ranges_dict.items():
            if not self._service_is_fe59(service_uuid, uuid_size):
                continue
            controls = [handle for handle, uuid_bytes in globals.received_handles.items()
                        if begin < handle <= end and uuid_bytes == CONTROL_POINT_UUID_LE]
            packets = [handle for handle, uuid_bytes in globals.received_handles.items()
                       if begin < handle <= end and uuid_bytes == PACKET_UUID_LE]
            matches.append((begin, end, controls, packets))
        return matches

    @staticmethod
    def _find_control_cccd(begin, end, control_handle, packet_handle):
        declarations = sorted(handle for handle, uuid_bytes in globals.received_handles.items()
                              if begin < handle <= end and uuid_bytes == b"\x03\x28")
        preceding = [handle for handle in declarations if handle < control_handle]
        # Characteristic Value immediately follows its declaration. Without
        # that structural evidence, a 0x2902 elsewhere could be misattributed.
        if not preceding or preceding[-1] + 1 != control_handle:
            return None, []
        following = [handle for handle in declarations if handle > control_handle]
        if packet_handle > control_handle:
            following.append(packet_handle)
        next_declaration_or_value = min(following) if following else end + 1
        candidates = sorted(handle for handle, uuid_bytes in globals.received_handles.items()
                            if control_handle < handle < next_declaration_or_value and
                            uuid_bytes == b"\x02\x29")
        return (candidates[0] if len(candidates) == 1 else None), candidates

    def _send_write(self, handle, value, stage):
        self.stage = stage
        self.pending_handle = handle
        self.sent_at = time.monotonic()
        send_ATT_WRITE_REQ(handle, value)
        self.result["attempts"] += 1
        self.result["status"] = f"awaiting_{stage}_att_response"
        self._observe("central_to_peripheral", stage, opcode_ATT_WRITE_REQ,
                      handle=handle, value_hex=value.hex())

    def _confirm_protocol_response(self):
        self.result["get_crc_notification_confirmed"] = True
        self._finish("get_crc_confirmed_unencrypted",
                     "Plaintext Control Point GET_CRC was ATT-admitted and returned a matching DFU success notification; the TOCTOU defect itself remains unproven.")

    def _start_cccd_confirmation(self):
        if self.cccd_handle is None:
            if self.initial_control_admitted:
                self._finish("write_admitted_unencrypted",
                             "ATT admitted GET_CRC on the plaintext Control Point, but no exact CCCD was found to confirm DFU processing.")
            else:
                self._finish("inconclusive_cccd_unavailable",
                             "The Control Point requested CCCD configuration, but its exact CCCD was not discovered.")
            return
        self._send_write(self.cccd_handle, ENABLE_NOTIFICATIONS, "cccd_enable")

    def _handle_write_response(self):
        stage = self.stage
        self._observe("peripheral_to_central", stage, opcode_ATT_WRITE_RSP,
                      handle=self.pending_handle)
        if stage == "control_initial":
            self.initial_control_admitted = True
            self.result["control_point_att_admitted"] = True
            if self.matching_notification_seen:
                self._confirm_protocol_response()
            else:
                self.stage = "await_initial_notification"
                self.sent_at = time.monotonic()
                self.result["status"] = "awaiting_initial_get_crc_notification"
                self._persist()
        elif stage == "cccd_enable":
            self.result["cccd_att_admitted"] = True
            if self.matching_notification_seen and self.initial_control_admitted:
                self._confirm_protocol_response()
            else:
                # A notification after a 0xFD initial rejection cannot be
                # attributed to an admitted GET_CRC request.
                self.matching_notification_seen = False
                self._send_write(self.control_handle, GET_CRC, "control_repeat")
        elif stage == "control_repeat":
            self.result["control_point_att_admitted"] = True
            if self.matching_notification_seen:
                self._confirm_protocol_response()
            else:
                self.stage = "await_final_notification"
                self.sent_at = time.monotonic()
                self.result["status"] = "awaiting_final_get_crc_notification"
                self._persist()

    def _handle_write_error(self, request_opcode, handle, error_code):
        stage = self.stage
        self._observe("peripheral_to_central", stage, opcode_ATT_ERROR_RSP,
                      handle=handle, error_code=error_code)
        details = {
            "att_response_opcode": opcode_ATT_ERROR_RSP,
            "att_request_opcode_in_error": request_opcode,
            "att_handle_in_error": handle,
            "att_error_code": error_code,
            "att_error_name": globals.att_errorcode_to_str.get(error_code, "Unknown"),
        }
        if handle != self.pending_handle:
            self._finish("inconclusive_error_on_other_handle",
                         "The ATT error named a handle other than the pending write handle.", **details)
            return
        if stage == "cccd_enable":
            self._finish("inconclusive_cccd_write_rejected",
                         "Enabling the exact Control Point CCCD was rejected; this does not establish Control Point write security.", **details)
            return
        if error_code == 0xFD and stage == "control_initial":
            self.result["initial_control_error_code"] = error_code
            self._start_cccd_confirmation()
            return
        if stage == "control_repeat" and self.initial_control_admitted:
            self._finish("inconclusive_inconsistent_control_result",
                         "The repeated Control Point write was rejected after an earlier ATT admission.", **details)
            return
        if error_code in LINK_SECURITY_ERRORS:
            self._finish("write_security_gated",
                         "The Control Point GET_CRC write was rejected for link security on this unpaired plaintext connection.", **details)
        elif error_code == 0x08:
            self._finish("write_authorization_gated",
                         "The Control Point GET_CRC write was rejected for authorization; the required policy is unknown.", **details)
        elif error_code == 0x0C:
            self._finish("inconclusive_key_size_error",
                         "The key-size error conflicts with the expected unencrypted link state; inspect the PCAP before classifying access.", **details)
        else:
            self._finish("inconclusive_other_att_error",
                         "The Control Point write was rejected for a reason other than a conclusive link-security error.", **details)

    def _handle_response(self, dpkt):
        body = dpkt.body
        if len(body) < 7 or (body[0] & 0x03) != 0x02 or body[4:6] != globals.ATT_CID_bytes:
            return
        l2cap_length = int.from_bytes(body[2:4], "little")
        if len(body) < 6 + l2cap_length:
            return
        opcode = body[6]
        if opcode == ATT_HANDLE_VALUE_NOTIFICATION and l2cap_length >= 3:
            handle = int.from_bytes(body[7:9], "little")
            value = body[9:6 + l2cap_length]
            if handle == self.control_handle:
                self._observe("peripheral_to_central", self.stage, opcode,
                              handle=handle, value_hex=value.hex())
                if len(value) == 11 and value[:3] == b"\x60\x03\x01":
                    self.matching_notification_seen = True
                    if self.stage in ("await_initial_notification", "await_final_notification"):
                        self._confirm_protocol_response()
                elif len(value) >= 3 and value[:2] == b"\x60\x03" and self.result["control_point_att_admitted"]:
                    self._finish("inconclusive_get_crc_negative_notification",
                                 "GET_CRC reached the DFU protocol but returned a non-success result; inspect the notification and PCAP.")
            return
        if opcode == opcode_ATT_WRITE_RSP and l2cap_length == 1:
            if self.stage in ("control_initial", "cccd_enable", "control_repeat"):
                self._handle_write_response()
            return
        if opcode != opcode_ATT_ERROR_RSP or l2cap_length != 5:
            return
        request_opcode = body[7]
        handle = int.from_bytes(body[8:10], "little")
        error_code = body[10]
        if request_opcode != opcode_ATT_WRITE_REQ:
            return
        if self.stage in ("control_initial", "cccd_enable", "control_repeat"):
            self._handle_write_error(request_opcode, handle, error_code)

    def process(self, dpkt):
        """Return True once the normal read/SMP flow must remain suppressed."""
        if self.finished:
            return True
        if not (globals.primary_services_all_recv and globals.secondary_services_all_recv and
                globals.all_info_handles_recv and globals.characteristic_read_by_type_req_all_received):
            return False
        if self.security_transition_observed:
            self._finish_security_signal()
            return True
        if self.stage == "discovery":
            matches = self._find_target()
            if not matches:
                self._finish("not_tested_fe59_absent", "No FE59 primary service was discovered.")
                return True
            if len(matches) != 1:
                self._finish("not_tested_ambiguous_fe59", "More than one FE59 primary service was discovered.")
                return True
            begin, end, controls, packets = matches[0]
            self.result["service_begin_handle"] = begin
            self.result["service_end_handle"] = end
            self.result["control_point_handles_found"] = controls
            self.result["packet_handles_found"] = packets
            if len(controls) != 1 or len(packets) != 1:
                self._finish("not_tested_incomplete_fe59",
                             "The FE59 service did not contain exactly one core Control Point and Packet characteristic.")
                return True
            self.control_handle = controls[0]
            self.cccd_handle, cccd_candidates = self._find_control_cccd(
                begin, end, self.control_handle, packets[0])
            self.result["control_point_value_handle"] = self.control_handle
            self.result["packet_value_handle"] = packets[0]
            self.result["control_point_cccd_handle"] = self.cccd_handle
            self.result["control_point_cccd_candidates"] = cccd_candidates
            self.result["status"] = "request_prepared"
            self._persist()
            self._send_write(self.control_handle, GET_CRC, "control_initial")
            return True
        self._handle_response(dpkt)
        self.tick()
        return True

    def tick(self):
        """Advance bounded waits even when only debug/state messages arrive."""
        if self.finished:
            return
        if self.sent_at is None:
            return
        elapsed = time.monotonic() - self.sent_at
        if self.stage == "await_initial_notification" and elapsed >= self.initial_notification_grace_seconds:
            self._start_cccd_confirmation()
        elif self.stage == "await_final_notification" and elapsed >= self.timeout_seconds:
            self._finish("inconclusive_notification_timeout",
                         "ATT admitted GET_CRC after CCCD enablement, but no matching DFU success notification arrived.")
        elif self.stage in ("control_initial", "cccd_enable", "control_repeat") and elapsed >= self.timeout_seconds:
            self._finish("inconclusive_timeout",
                         "No correlated ATT response arrived before the probe deadline.", timed_out_stage=self.stage)
