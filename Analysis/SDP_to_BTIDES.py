########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

# Activate venv before any other imports
from handle_venv import activate_venv
activate_venv()

import argparse, os, re, struct
import xml.etree.ElementTree as ET

import TME.TME_glob
from TME.TME_helpers import qprint, vprint
from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
from TME.TME_BTIDES_base import write_BTIDES
from TME.TME_BTIDES_SDP import ff_SDP_Common, BTIDES_export_SDP_packet
from BTIDES_to_SQL import btides_to_sql_args, btides_to_sql


############################
# SDP binary re-encoding
############################

def _sdp_var_len(type_id, payload):
    """Encode a variable-length SDP data element (type_id is the 5-bit type value)."""
    n = len(payload)
    if n <= 0xFF:
        return struct.pack('>BB', (type_id << 3) | 5, n) + payload
    elif n <= 0xFFFF:
        return struct.pack('>BH', (type_id << 3) | 6, n) + payload
    else:
        return struct.pack('>BI', (type_id << 3) | 7, n) + payload


def encode_sdp_element(elem):
    """Recursively encode an XML element as an SDP binary data element."""
    tag = elem.tag

    if tag == 'nil':
        return struct.pack('>B', 0x00)

    elif tag == 'uint8':
        return struct.pack('>BB', 0x08, int(elem.get('value'), 16))

    elif tag == 'uint16':
        return struct.pack('>BH', 0x09, int(elem.get('value'), 16))

    elif tag == 'uint32':
        return struct.pack('>BI', 0x0A, int(elem.get('value'), 16))

    elif tag == 'uint64':
        return struct.pack('>BQ', 0x0B, int(elem.get('value'), 16))

    elif tag == 'int8':
        return struct.pack('>Bb', 0x10, int(elem.get('value'), 16))

    elif tag == 'int16':
        return struct.pack('>Bh', 0x11, int(elem.get('value'), 16))

    elif tag == 'int32':
        return struct.pack('>Bi', 0x12, int(elem.get('value'), 16))

    elif tag == 'int64':
        return struct.pack('>Bq', 0x13, int(elem.get('value'), 16))

    elif tag == 'uuid':
        val = elem.get('value', '')
        if val.startswith('0x') or val.startswith('0X'):
            n = int(val, 16)
            if n <= 0xFFFF:
                return struct.pack('>BH', 0x19, n)
            else:
                return struct.pack('>BI', 0x1A, n)
        else:
            # UUID128 with dashes, e.g. "00000000-deca-fade-deca-deafdecacaff"
            uuid_bytes = bytes.fromhex(val.replace('-', ''))
            return struct.pack('>B', 0x1C) + uuid_bytes

    elif tag == 'text':
        s = elem.get('value', '').encode('utf-8')
        return _sdp_var_len(4, s)

    elif tag == 'boolean':
        v = 1 if elem.get('value', 'false').lower() in ('true', '1') else 0
        return struct.pack('>BB', 0x28, v)

    elif tag == 'sequence':
        inner = b''.join(encode_sdp_element(child) for child in elem)
        return _sdp_var_len(6, inner)

    elif tag == 'alternate':
        inner = b''.join(encode_sdp_element(child) for child in elem)
        return _sdp_var_len(7, inner)

    elif tag == 'url':
        s = elem.get('value', '').encode('utf-8')
        return _sdp_var_len(8, s)

    else:
        qprint(f"Warning: unknown sdptool XML element type '{tag}', skipping")
        return b''


def encode_record(record_elem):
    """Encode a single <record> element as an SDP attribute list sequence."""
    pairs = b''
    for attr in record_elem.findall('attribute'):
        attr_id = int(attr.get('id'), 16)
        pairs += struct.pack('>BH', 0x09, attr_id)
        for child in attr:
            pairs += encode_sdp_element(child)
    return _sdp_var_len(6, pairs)


############################
# XML file parsing
############################

def parse_sdp_xml_file(xml_path):
    """Parse an sdptool XML file and return a list of <record> Element objects."""
    try:
        with open(xml_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except OSError as e:
        qprint(f"Warning: could not read {xml_path}: {e}")
        return []

    # Split on XML declarations; the first chunk is the non-XML preamble
    chunks = re.split(r'<\?xml[^?]*\?>', content)
    records = []
    for chunk in chunks:
        # Extract only the <record>...</record> portion; chunks may contain
        # trailing non-XML text like "Browsing ... Service Search failed: ..."
        m = re.search(r'<record\b.*?</record>', chunk, re.DOTALL)
        if not m:
            continue
        try:
            root = ET.fromstring(m.group(0))
            if root.tag == 'record':
                records.append(root)
        except ET.ParseError as e:
            qprint(f"Warning: XML parse error in {xml_path}: {e}")
    return records


############################
# Per-file BTIDES export
############################

def process_sdp_file(xml_path, bdaddr):
    """Parse one sdptool XML file and emit a BTIDES SDP_SERVICE_SEARCH_ATTR_RSP entry."""
    records = parse_sdp_xml_file(xml_path)
    if not records:
        vprint(f"  No SDP records found in {xml_path}, skipping.")
        return False

    # Build AttributeLists: outer sequence wrapping one inner sequence per record
    inner_seqs = b''.join(encode_record(r) for r in records)
    outer_seq = _sdp_var_len(6, inner_seqs)

    # SDP_SERVICE_SEARCH_ATTR_RSP parameter bytes:
    # [AttributeListsByteCount (2)] + [AttributeLists] + [ContinuationState (1)]
    attr_lists_byte_count = len(outer_seq)
    payload = struct.pack('>H', attr_lists_byte_count) + outer_seq + b'\x00'

    data = ff_SDP_Common(
        pdu_id=type_SDP_SERVICE_SEARCH_ATTR_RSP,
        direction=type_BTIDES_direction_P2C,
        l2cap_len=len(payload) + 5,   # 5-byte SDP PDU header
        l2cap_cid=0x0040,             # first dynamic L2CAP CID
        transaction_id=0x0001,
        param_len=len(payload),
        raw_data_hex_str=payload.hex()
    )

    BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
    vprint(f"  Exported {len(records)} SDP record(s) for {bdaddr}")
    return True


def extract_bdaddr_from_filename(path):
    """Return the BDADDR embedded in a '{bdaddr}_sdp.xml' filename (lowercased)."""
    name = os.path.basename(path)
    return name.replace('_sdp.xml', '').lower()


############################
# Main
############################

def main():
    parser = argparse.ArgumentParser(description='sdptool XML input arguments')
    parser.add_argument('--input', type=str, required=True,
                        help='Input: a single {BDADDR}_sdp.xml file, or a directory containing them.')

    btides_group = parser.add_argument_group('BTIDES file output arguments')
    btides_group.add_argument('--output', type=str, required=False,
                              help='Output file name for BTIDES JSON file.')
    btides_group.add_argument('--verbose-BTIDES', action='store_true', required=False,
                              help='Include optional fields in BTIDES output for human readability.')

    sql_group = parser.add_argument_group('Local SQL database storage arguments')
    sql_group.add_argument('--to-SQL', action='store_true', required=False,
                           help='Store output BTIDES file to your local SQL database.')
    sql_group.add_argument('--use-test-db', action='store_true', required=False,
                           help='Use the bttest database instead of bt2.')

    print_group = parser.add_argument_group('Print verbosity arguments')
    print_group.add_argument('--verbose-print', action='store_true', required=False,
                             help='Show per-file progress output.')
    print_group.add_argument('--quiet-print', action='store_true', required=False,
                             help='Suppress all print output.')

    args = parser.parse_args()

    if not args.output and not args.to_SQL:
        parser.error("At least one of --output or --to-SQL must be specified.")

    TME.TME_glob.verbose_print = args.verbose_print
    TME.TME_glob.quiet_print = args.quiet_print
    TME.TME_glob.verbose_BTIDES = args.verbose_BTIDES
    TME.TME_glob.use_test_db = args.use_test_db

    # Collect input files
    if os.path.isdir(args.input):
        input_files = sorted(
            os.path.join(args.input, f)
            for f in os.listdir(args.input)
            if f.endswith('_sdp.xml')
        )
        if not input_files:
            print(f"No *_sdp.xml files found in directory: {args.input}")
            return
    elif os.path.isfile(args.input):
        input_files = [args.input]
    else:
        print(f"Error: {args.input} is not a file or directory.")
        return

    qprint(f"Processing {len(input_files)} sdptool XML file(s)...")

    processed = 0
    for xml_path in input_files:
        bdaddr = extract_bdaddr_from_filename(xml_path)
        if process_sdp_file(xml_path, bdaddr):
            processed += 1

    qprint(f"Exported SDP data for {processed} device(s).")

    if args.output:
        write_BTIDES(args.output)
        qprint(f"BTIDES output written to {args.output}")

    if args.to_SQL:
        b2s_args = btides_to_sql_args(
            input=[args.output] if args.output else [],
            use_test_db=args.use_test_db,
            quiet_print=args.quiet_print,
            verbose_print=args.verbose_print,
            skip_schema_validation=True
        )
        btides_to_sql(b2s_args)


if __name__ == "__main__":
    main()
