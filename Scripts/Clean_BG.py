#!/usr/bin/env python3
########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Clean_BG.py — prune BetterGetter pcaps that captured no peripheral response.

A useful BetterGetter capture proves that the central reached the peripheral
and got at least one Link Layer reply *over the data channel*. Files that
contain only advertising-channel traffic (ADV_IND / SCAN_REQ / SCAN_RSP /
CONNECT_IND) but no post-connection peripheral->central data PDU are dead
weight: they can't contribute anything to the SQL database when imported
later, and they clutter the Logs/BetterGetter/ tree.

This tool walks a folder (recursively), and for each `.pcap` underneath:

  1. **Size fast-path** — if the file is small enough that it cannot
     possibly contain a peripheral data-channel packet, it is unconditionally
     deleted with no parse. The threshold is the byte-exact lower bound of
     "pcap global header + the BG-injected CONNECT_IND + one minimal
     peripheral->central data PDU"; see ``SIZE_FAST_DELETE_THRESHOLD`` below.

  2. **Streaming parse** — otherwise, the file is walked record-by-record,
     reading only the 16-byte pcap record header plus the 10-byte BLE-LL-PHDR
     of each record and seeking past the rest. The PHDR's flags field
     encodes a 3-bit `pdu_type` (bits 7..9):

         0 = primary advertising-channel PDU (channels 37/38/39)
         1 = AUX/secondary advertising-channel PDU
         2 = data-channel PDU, central -> peripheral
         3 = data-channel PDU, peripheral -> central     <-- what we want

     The instant any record has `pdu_type == 3`, the file is kept and the
     scan stops. If EOF is reached without seeing one, the file is deleted.

     This matches the encoding written by Sniffle's ``PcapBleWriter`` (which
     is what ``Scripts/BG/Better_Getter.py`` uses), at
     ``Sniffle/python_cli/sniffle/pcap.py`` ``payload()``:

         flags |= (pdu_type & 0x7) << 7

Files that fail to parse (truncated headers, corrupt records) are left in
place with a warning — we never delete a file we couldn't read; a human
should decide what to do with broken captures.

Non-`.pcap` files (e.g. ``Sniffle_stdout.log``) are ignored.
"""

import argparse
import os
import struct
import sys
from pathlib import Path

# --- pcap constants ---------------------------------------------------------

PCAP_MAGIC = 0xA1B2C3D4
EXPECTED_DLT = 256  # LINKTYPE_BLUETOOTH_LE_LL_WITH_PHDR

# Header sizes (bytes), for the size fast-path computation below.
PCAP_GLOBAL_HEADER_LEN = 24
PCAP_RECORD_HEADER_LEN = 16
PHDR_LEN = 10          # chan + sig_pwr + noise + AA_off + ref_AA + flags
AA_LEN = 4             # access address (repeated in payload after PHDR)
CRC_LEN = 3            # trailing BLE CRC

# Smallest possible *useful* BG pcap:
#   PCAP global header                            24
#   + BG-injected CONNECT_IND record:
#       rec_hdr  + PHDR + AA + LL(hdr 2 + body 34) + CRC
#       =  16   +  10  +  4 +        36           +  3   = 69
#   + one minimum-size data PDU peripheral->central:
#       rec_hdr  + PHDR + AA + LL(hdr 2 + body 0)  + CRC
#       =  16   +  10  +  4 +         2           +  3   = 35
#   -------------------------------------------------------
#   total minimum size of a file with one peripheral data PDU  =  128 bytes
#
# So any pcap whose total file size is < 128 bytes (i.e. <= 127) cannot
# contain a peripheral data PDU and is unconditionally junk. We use this as a
# hard fast-delete threshold. Files at or above this size still need the
# full parse since "many ADV_INDs + CONNECT_IND + no data" can be arbitrarily
# large.
SIZE_FAST_DELETE_THRESHOLD = (
    PCAP_GLOBAL_HEADER_LEN
    + (PCAP_RECORD_HEADER_LEN + PHDR_LEN + AA_LEN + 36 + CRC_LEN)   # CONNECT_IND
    + (PCAP_RECORD_HEADER_LEN + PHDR_LEN + AA_LEN + 2 + CRC_LEN)    # min P->C data
    - 1                                                              # strictly less than
)
assert SIZE_FAST_DELETE_THRESHOLD == 127, SIZE_FAST_DELETE_THRESHOLD

# --- PHDR flags layout ------------------------------------------------------
# Written by sniffle/pcap.py PcapBleWriter.payload():
#     flags = 0x0413
#     if not crc_err: flags |= 0x0800
#     flags |= (phy & 0x3) << 14
#     flags |= (pdu_type & 0x7) << 7
#     if pdu_type == 1: flags |= (aux_type & 0x3) << 12
# So pdu_type lives in flags[bits 7..9].
PHDR_FLAGS_OFFSET = 8    # offset within the 10-byte PHDR of the 16-bit flags field
PDU_TYPE_DATA_PERIPH_TO_CENTRAL = 3


# --- pcap parsing -----------------------------------------------------------

def _read_global_header(f) -> tuple[bool, str]:
    """Read and validate the pcap global header from an already-open file.

    Returns (is_bg_format, reason). When is_bg_format is False, the caller
    must NOT delete the file — it's either truncated, not a classic pcap,
    or a pcap with a different linktype, and we have no business touching
    files we don't understand.
    """
    global_hdr = f.read(PCAP_GLOBAL_HEADER_LEN)
    if len(global_hdr) < PCAP_GLOBAL_HEADER_LEN:
        return False, "parse error: pcap global header truncated"
    try:
        magic, _vmaj, _vmin, _tz, _sig, _snap, dlt = struct.unpack(
            "<IHHIIII", global_hdr
        )
    except struct.error as e:
        return False, f"parse error: global header: {e}"
    if magic != PCAP_MAGIC:
        return False, f"not a classic pcap (magic=0x{magic:08x}); leaving alone"
    if dlt != EXPECTED_DLT:
        return False, f"linktype {dlt} != BLE-LL-PHDR; leaving alone"
    return True, "BG-format pcap"


def _is_useful_pcap(path: Path) -> tuple[bool, str]:
    """Return (keep_file, reason).

    keep_file:
        True  → file should be kept (it has at least one peripheral->central
                data-channel PDU, OR it is not a Sniffle/BG-format pcap and
                we don't dare touch it).
        False → file should be deleted (no peripheral data-channel PDU was
                found before EOF).

    reason: short human-readable explanation, suitable for verbose logs.

    Raises OSError on filesystem failures.
    """
    with open(path, "rb") as f:
        ok, reason = _read_global_header(f)
        if not ok:
            return True, reason

        # Tolerate a truncated trailing record (common when BetterGetter is
        # killed mid-flush): if we've already classified some valid records,
        # treat any short read at the tail as effective EOF and apply the
        # normal "no P->C data PDU found" → delete decision. If the file is
        # truncated at the very first record we can't confidently classify
        # it, so we bail out as a parse error and leave it alone.
        record_count = 0
        while True:
            rec_hdr = f.read(PCAP_RECORD_HEADER_LEN)
            if len(rec_hdr) == 0:
                return False, f"no P->C data PDU in {record_count} records"
            if len(rec_hdr) < PCAP_RECORD_HEADER_LEN:
                if record_count > 0:
                    return False, (
                        f"no P->C data PDU in {record_count} records "
                        f"(file has {len(rec_hdr)} trailing bytes, ignored)"
                    )
                return True, "parse error: truncated record header at offset 24"
            try:
                _ts_s, _ts_u, incl_len, _orig_len = struct.unpack("<IIII", rec_hdr)
            except struct.error as e:
                return True, f"parse error: record header: {e}"

            if incl_len < PHDR_LEN:
                # Record can't even hold a PHDR; skip it and keep going.
                f.seek(incl_len, os.SEEK_CUR)
                record_count += 1
                continue

            phdr = f.read(PHDR_LEN)
            if len(phdr) < PHDR_LEN:
                if record_count > 0:
                    return False, (
                        f"no P->C data PDU in {record_count} records "
                        f"(final record's PHDR truncated, ignored)"
                    )
                return True, "parse error: truncated PHDR in first record"
            flags = struct.unpack_from("<H", phdr, PHDR_FLAGS_OFFSET)[0]
            pdu_type = (flags >> 7) & 0x7
            if pdu_type == PDU_TYPE_DATA_PERIPH_TO_CENTRAL:
                return True, f"peripheral data PDU found at record {record_count}"

            # Skip the remainder of this record (AA + LL + body + CRC).
            f.seek(incl_len - PHDR_LEN, os.SEEK_CUR)
            record_count += 1


# --- top-level driver -------------------------------------------------------

def clean_directory(root: Path, dry_run: bool, verbose: bool) -> int:
    """Walk `root` recursively. Returns process exit code (0 on success)."""
    if not root.exists():
        print(f"Path does not exist: {root}", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2

    stats = {
        "kept": 0,
        "deleted_after_parse": 0,
        "deleted_by_size": 0,
        "skipped_non_pcap": 0,
        "parse_errors": 0,
        "unlink_errors": 0,
    }

    # rglob walks subdirectories; the user explicitly wants recursion.
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() != ".pcap":
            stats["skipped_non_pcap"] += 1
            if verbose:
                print(f"  SKIP    {path}  (non-.pcap)")
            continue

        try:
            size = path.stat().st_size
        except OSError as e:
            print(f"  STAT-ERR {path}: {e}", file=sys.stderr)
            stats["parse_errors"] += 1
            continue

        # ----- Fast path: size below provable minimum -----
        # We still have to read the 24-byte pcap global header even on the
        # fast path so we don't accidentally delete a 100-byte pcap that's
        # actually some other linktype (e.g. Ethernet) the user happens to
        # have in the same tree.
        if size <= SIZE_FAST_DELETE_THRESHOLD:
            try:
                with open(path, "rb") as f:
                    is_bg, reason = _read_global_header(f)
            except OSError as e:
                print(f"  STAT-ERR {path}: {e}", file=sys.stderr)
                stats["parse_errors"] += 1
                continue
            if not is_bg:
                stats["parse_errors"] += 1
                print(f"  LEAVE    {path}  ({size} B, {reason})")
                continue
            stats["deleted_by_size"] += 1
            action = "WOULD-DELETE-SIZE" if dry_run else "DELETE-SIZE"
            print(f"  {action} {path}  ({size} B <= {SIZE_FAST_DELETE_THRESHOLD})")
            if not dry_run:
                try:
                    path.unlink()
                except OSError as e:
                    print(f"    unlink failed: {e}", file=sys.stderr)
                    stats["unlink_errors"] += 1
            continue

        # ----- Slow path: stream the records -----
        try:
            keep, reason = _is_useful_pcap(path)
        except OSError as e:
            print(f"  PARSE-ERR {path}: {e}", file=sys.stderr)
            stats["parse_errors"] += 1
            continue
        if reason.startswith("parse error") or reason.startswith("not a classic"):
            # We didn't actually classify the file (corrupt or unrelated
            # format) — be conservative and leave it.
            stats["parse_errors"] += 1
            print(f"  LEAVE    {path}  ({reason})")
            continue

        if keep:
            stats["kept"] += 1
            if verbose:
                print(f"  KEEP    {path}  ({size} B, {reason})")
        else:
            stats["deleted_after_parse"] += 1
            action = "WOULD-DELETE" if dry_run else "DELETE      "
            print(f"  {action} {path}  ({size} B, {reason})")
            if not dry_run:
                try:
                    path.unlink()
                except OSError as e:
                    print(f"    unlink failed: {e}", file=sys.stderr)
                    stats["unlink_errors"] += 1

    print()
    print("=== Summary ===")
    print(f"  kept                 : {stats['kept']}")
    print(f"  deleted (size shortcut): {stats['deleted_by_size']}")
    print(f"  deleted (after parse)  : {stats['deleted_after_parse']}")
    print(f"  parse errors / left    : {stats['parse_errors']}")
    print(f"  unlink errors          : {stats['unlink_errors']}")
    print(f"  non-.pcap skipped      : {stats['skipped_non_pcap']}")
    if dry_run:
        print("  (dry run — no files were actually removed)")
    return 0 if stats["unlink_errors"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Recursively delete BetterGetter pcaps that contain no "
            "peripheral->central data-channel PDU."
        ),
        epilog=(
            "Examples:\n"
            "  Clean_BG.py ~/Blue2thprinting/Logs/BetterGetter --dry-run -v\n"
            "  Clean_BG.py ~/Blue2thprinting/Logs/BetterGetter\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "path",
        help="Folder of BetterGetter .pcap files to clean (recurses into subdirs).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted; don't actually remove anything.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Also log files we are keeping or skipping.",
    )
    args = parser.parse_args()
    return clean_directory(Path(args.path).expanduser(), args.dry_run, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
