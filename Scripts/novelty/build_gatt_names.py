#!/usr/bin/env python3
"""Build novelty_names_GATT.json: advertised names of devices already fully
GATT-enumerated in the local bt2 database.

Novelty mode skips a device whose advertised name is in this file, because its
GATT database has been collected before. The output is private (it is made of
device names from the local database), so it is written to
Analysis/metadata/private/ and copied to a capture node with scp, like
novelty_names.json. Nothing here is committed to this repository.

Nothing but the database is required. Analysis/metadata/private is ignored by
Git and is created if it is missing. The two optional inputs are read from the
output's directory when they are there, and their content is never copied into
the output: novelty_names.json (private category rules; without it only the
public rules decide which names are left to the other rules) and
novelty_names_GATT_families.json (hand-written families). The script refuses
to write to a place inside this repository that Git does not ignore.

    venv/bin/python Scripts/novelty/build_gatt_names.py

"Fully enumerated" means, for one (address, address type):
  * services and characteristics were discovered,
  * every service that spans more than its own declaration has characteristics,
  * every characteristic with the Read property was answered, by a value
    (ATT_READ_RSP) or by an ATT error, and
  * at least one value was actually read.

Only *advertised* names count: Complete or Shortened Local Name from LE
advertising/scan responses and from BR/EDR EIR. A name read over GATT is no use
here, because novelty mode decides before connecting.

Where many devices share a naming scheme with a per-device identifier, one
NamePrint-style regex replaces the individual names, and so also covers family
members that have not been enumerated yet. Families are inferred from every
advertised name in the database, not just the enumerated ones:

  1. id:      the rightmost run of 3+ hex characters holding a digit is the
              identifier ("Lamp_0A1B2C3D", "Door-0AF").
  2. serial:  the same with a run of 5+ letters and digits ("Cam 3S 4GK7QZ").
  3. aligned: names of one length that share five characters at the same
              offset ("31000000.0A0B0C0D", "Unit 0A:1B:2C").
  4. initial: names of one length that start with the same character, for
              families whose only fixed text is one letter.

A family becomes a regex only when all of these hold; otherwise its enumerated
names stay as exact names:
  * at least MIN_FAMILY_NAMES distinct names in the database fit it,
  * at least MIN_UNIQUE of them were each seen on one or two devices (a name
    shared by many devices is a model name, not an identifier),
  * at least three characters vary, and what stays fixed is a usable anchor
    (a single fixed letter is enough only when five or more enumerated members
    share one GATT database and vary in the same places as the whole family,
    which shows the family is real: "N4GK7", "NQZ2M", ... but not every name
    starting with "I" because "IDX13" and "IDX19" were enumerated),
  * the varying part is an identifier, not free text: no spaces, and digits
    or symbols in it rather than words ("Anna's Room", "Brand Watch4 (AB12)"),
  * the enumerated members do not all have different GATT databases. A family
    that fails this is never retried in a wider or narrower form.

A family already covered by a wider accepted one is dropped.

Two things take precedence over the inference:

  * Names the other novelty rules already skip (the category rules, or the
    retained-vehicle veto that would stop this file's entry from ever
    applying) are left out, so this list and those rules never overlap on an
    enumerated name. At run time this list is consulted last.
  * Hand-written families in novelty_names_GATT_families.json, next to the
    output, are taken as given: {"families": [{"pattern": "^...$", "note": "..."}]}.
    They are for families the checks above refuse, or that have too few
    examples to be inferred. One is used only while it matches an enumerated
    name that the other rules do not already skip; the rest are listed under
    "unused_families".
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from novelty.rules import GATT_NAMES_FILE, NoveltyRules, RETAINED, normalize_name

REPO_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_DIR = REPO_ROOT / 'Analysis/metadata/private'
FAMILIES_FILE = 'novelty_names_GATT_families.json'

MIN_FAMILY_NAMES = 8     # distinct database names that must fit a family
MIN_UNIQUE = 0.8         # share of those names seen on at most two devices
MIN_VARIABLE = 3         # characters that must vary
MIN_MACHINE_MADE = 0.6   # share of varying parts holding a digit or a symbol
MIN_SYMBOLS = 0.25       # share of symbols that makes a run "printable junk"
MAX_LETTER_RUN = 3       # longest run of letters only that is still a code
MIN_NAME_LENGTH = 3      # shorter names cannot identify anything
GRAM = 5                 # shared characters that start an aligned family
ATT_READ_RSP, ATT_ERROR_RSP, CHAR_PROPERTY_READ = 0x0b, 0x01, 0x02

MIN_PROVEN_DEVICES = 5   # enumerated members that can vouch for a weak anchor
HEX_RUN = re.compile(r'[0-9A-Fa-f]{3,}')
ALNUM_RUN = re.compile(r'[0-9A-Za-z]{5,}')


def decode_hex_name(value):
    try:
        return bytes.fromhex(str(value)).decode('utf-8', errors='replace')
    except ValueError:
        return ''


# --------------------------------------------------------------------------
# Which devices are fully enumerated
# --------------------------------------------------------------------------

def fully_enumerated(services, characteristics, values):
    """Devices whose GATT enumeration ran to the end.

    services:        iterable of (device, begin_handle, end_handle)
    characteristics: iterable of (device, declaration_handle, properties, value_handle)
    values:          iterable of (device, value_handle, operation)
    """
    spans, declared, answered, read = defaultdict(set), defaultdict(set), defaultdict(set), set()
    for device, begin, end in services:
        spans[device].add((begin, end))
    for device, declaration, properties, value_handle in characteristics:
        declared[device].add((declaration, properties, value_handle))
    for device, value_handle, operation in values:
        if operation in (ATT_READ_RSP, ATT_ERROR_RSP):
            answered[device].add(value_handle)
        if operation == ATT_READ_RSP:
            read.add(device)
    complete = set()
    for device, rows in declared.items():
        if device not in spans or device not in read:
            continue
        readable = [value_handle for _, properties, value_handle in rows if properties & CHAR_PROPERTY_READ]
        if not readable or any(handle not in answered[device] for handle in readable):
            continue
        declarations = sorted(declaration for declaration, _, _ in rows)
        if all(any(begin < declaration <= end for declaration in declarations)
               for begin, end in spans[device] if end > begin):
            complete.add(device)
    return complete


# --------------------------------------------------------------------------
# Family inference
# --------------------------------------------------------------------------

def _run_class(chars):
    """The tightest character class holding every character seen in a run."""
    digits = any(c.isdigit() for c in chars)
    upper = {c for c in chars if 'A' <= c <= 'Z'}
    lower = {c for c in chars if 'a' <= c <= 'z'}
    if any(not ('0' <= c <= '9' or 'A' <= c <= 'Z' or 'a' <= c <= 'z') for c in chars):
        return '[!-~]' if all('!' <= c <= '~' for c in chars) else '.'
    hex_only = upper <= set('ABCDEF') and lower <= set('abcdef')
    if not upper and not lower:
        return '[0-9]'
    if hex_only and digits:
        return '[0-9A-Fa-f]' if upper and lower else '[0-9A-F]' if upper else '[0-9a-f]'
    head = '0-9' if digits else ''
    return f"[{head}{'A-Z' if upper else ''}{'a-z' if lower else ''}]"


def _template(names):
    """Per-position view of same-length names: (regex, fixed text, varying spans).

    A position is fixed when every name agrees on it. Fixed positions between
    the first and last varying one of a span are treated as varying too: a
    serial number's middle digit that has not rolled over yet is not a rule.
    """
    length = len(names[0])
    columns = [{name[i] for name in names} for i in range(length)]
    fixed = [len(column) == 1 for column in columns]
    spans, i = [], 0
    while i < length:
        if fixed[i]:
            i += 1
            continue
        j = i
        while j < length and not fixed[j]:
            j += 1
        spans.append([i, j])
        i = j
    # Join spans separated only by fixed letters/digits (not by a separator).
    merged = []
    for span in spans:
        gap = names[0][merged[-1][1]:span[0]] if merged else ''
        if merged and gap and gap.isalnum() and len(gap) <= 2:
            merged[-1][1] = span[1]
        else:
            merged.append(span)
    regex, literal, position = '', '', 0
    for start, end in merged:
        regex += re.escape(names[0][position:start])
        literal += names[0][position:start]
        chars = set().union(*columns[start:end])
        regex += _run_class(chars) + (f'{{{end - start}}}' if end - start > 1 else '')
        position = end
    regex += re.escape(names[0][position:])
    literal += names[0][position:]
    return '^' + regex + '$', literal, [tuple(span) for span in merged]


def _anchored(literal, variable):
    """Is the fixed text enough to tell this family from unrelated names?"""
    letters = sum(c.isalpha() for c in literal)
    alnum = sum(c.isalnum() for c in literal)
    return ((letters >= 2 and len(literal) >= 3) or
            (letters >= 1 and alnum >= 3 and len(literal) >= 4) or
            (letters >= 1 and alnum >= 2 and variable >= 12))


def _free_text(names, spans):
    """Why the varying parts are text rather than identifiers, or None."""
    for start, end in spans:
        chars = [c for name in names for c in name[start:end]]
        if any(c.isspace() for c in chars):
            return 'varying part holds spaces'
        if any(not '!' <= c <= '~' for c in chars):
            return 'varying part is not ASCII'
        symbols = sum(not c.isalnum() for c in chars)
        if symbols:
            if symbols < MIN_SYMBOLS * len(chars):
                return 'varying part mixes text and punctuation'
        elif not any(c.isdigit() for c in chars):
            cases = {c.isupper() for c in chars}
            if end - start > MAX_LETTER_RUN or len(cases) > 1:
                return 'varying part is letters only'
    return None


def _gatt_agreement(signatures):
    """Share of enumerated members whose GATT database is (nearly) the commonest one."""
    if not signatures:
        return 0.0
    mode = Counter(signatures).most_common(1)[0][0]
    return sum(len(s & mode) >= 0.8 * len(s | mode) for s in signatures) / len(signatures)


def _judge(names, known, corpus, signatures):
    """Return (record, reason). reason is None when the family is accepted."""
    names = sorted(names)
    regex, literal, spans = _template(names)
    variable = sum(end - start for start, end in spans)
    members = [name for name in names if name in known]
    devices = sorted({device for name in members for device in known[name]})
    record = {'pattern': regex, 'database_names': len(names), 'enumerated_devices': len(devices),
              'example': members[0] if members else names[0], '_names': names}
    if len(names) < MIN_FAMILY_NAMES:
        return record, 'few names'
    if sum(corpus[name] <= 2 for name in names) < MIN_UNIQUE * len(names):
        return record, 'names shared by many devices'
    if variable < MIN_VARIABLE:
        return record, 'identifier too short'
    gatt = [signatures[d] for d in devices if d in signatures]
    agreement = _gatt_agreement(gatt)
    proven = (len(gatt) >= MIN_PROVEN_DEVICES and agreement >= 0.75 and any(c.isalpha() for c in literal)
              and len(members) >= MIN_PROVEN_DEVICES and _template(sorted(members))[1] == literal)
    if not (_anchored(literal, variable) or proven):
        return record, 'no usable anchor'
    text = _free_text(names, spans)
    if text:
        return record, text
    machine = sum(any(not c.isalpha() and not c.isspace() for start, end in spans for c in name[start:end])
                  for name in names)
    if machine < MIN_MACHINE_MADE * len(names):
        return record, 'varying part is not machine-made'
    # With three or more enumerated members, one database must account for half.
    if len(gatt) >= 3 and agreement < 0.5:
        return record, 'GATT databases differ'
    return record, None


def _rightmost(pattern, name, need_digit=True, reject=None):
    span = None
    for match in pattern.finditer(name):
        text = match.group()
        if need_digit and not any(c.isdigit() for c in text):
            continue
        if reject is not None and reject(text):
            continue
        span = match.span()
    return span


def _region_families(corpus, region):
    families = defaultdict(list)
    for name in corpus:
        span = region(name)
        if span:
            families[(name[:span[0]], span[1] - span[0], name[span[1]:])].append(name)
    return families


def infer(known, corpus, signatures=None):
    """Split the enumerated names into family regexes and leftover exact names.

    known:      {name: [enumerated devices advertising it]}
    corpus:     {name: number of devices advertising it}, every database name
    signatures: {device: frozenset of characteristic UUIDs}, for the GATT check
    Returns (accepted records, leftover names, rejected records).
    """
    signatures = signatures or {}
    accepted, rejected, covered, blocked, seen = [], [], set(), set(), set()

    def consider(names, how):
        """Judge one candidate family. Returns the verdict, or None if not judged."""
        key = frozenset(names)
        if key in seen or not any(name in known and name not in covered and name not in blocked
                                  for name in names):
            return None
        seen.add(key)
        record, reason = _judge(names, known, corpus, signatures)
        record['inferred_by'] = how
        if reason:
            record['rejected'] = reason
            rejected.append(record)
            if reason == 'GATT databases differ':
                blocked.update(name for name in names if name in known)
        else:
            accepted.append(record)
            matcher = re.compile(record['pattern'])
            covered.update(name for name in known if matcher.fullmatch(name))
        return reason or 'accepted'

    is_hex = re.compile(r'[0-9A-Fa-f]+').fullmatch
    for how, region in (
            ('id', lambda name: _rightmost(HEX_RUN, name)),
            ('serial', lambda name: _rightmost(ALNUM_RUN, name, reject=is_hex))):
        families = _region_families((name for name in corpus if name not in covered), region)
        for key in sorted(families, key=lambda key: (-len(families[key]), key)):
            consider(families[key], how)

    # Aligned: same length, the same GRAM characters at the same offset.
    index = defaultdict(set)
    for name in corpus:
        if name in covered:
            continue
        for offset in range(len(name) - GRAM + 1):
            index[(len(name), offset, name[offset:offset + GRAM])].add(name)
    for name in sorted(known):
        if name in covered or name in blocked or len(name) < GRAM + MIN_VARIABLE:
            continue
        clusters = {frozenset(index.get((len(name), offset, name[offset:offset + GRAM]), ()))
                    for offset in range(len(name) - GRAM + 1)} - {frozenset()}
        # Largest family first: one regex for the whole family, not one per batch.
        for cluster in sorted(clusters, key=lambda c: (-len(c), sorted(c)[0])):
            if name in covered or name in blocked or len(cluster) < MIN_FAMILY_NAMES:
                break
            consider(sorted(cluster), 'aligned')

    # Initial: one token of letters and digits in one case, same length and
    # first character ("N4GK7", "NQZ2M"). Only a proven family passes here.
    upper, lower = re.compile(r'[0-9A-Z]+').fullmatch, re.compile(r'[0-9a-z]+').fullmatch
    initial = defaultdict(list)
    for name in corpus:
        if name not in covered and (upper(name) or lower(name)):
            initial[(len(name), name[:1], bool(upper(name)))].append(name)
    for key in sorted(initial, key=lambda key: (-len(initial[key]), key)):
        consider(initial[key], 'initial')

    # Drop a family that a wider accepted one already covers completely.
    accepted.sort(key=lambda record: (-record['database_names'], record['pattern']))
    matchers = [re.compile(record['pattern']) for record in accepted]
    kept = [record for i, record in enumerate(accepted)
            if not any(j != i and (other['database_names'], -j) > (record['database_names'], -i) and
                       all(matchers[j].fullmatch(name) for name in record['_names'])
                       for j, other in enumerate(accepted))]
    kept_matchers = [re.compile(record['pattern']) for record in kept]
    leftover = sorted(name for name in known if not any(m.fullmatch(name) for m in kept_matchers))
    return kept, leftover, rejected


def curated_families(entries, known, corpus):
    """Hand-written families: (records for those in use, patterns not in use)."""
    records, unused = [], []
    for entry in entries:
        pattern = entry['pattern']
        if not (pattern.startswith('^') and pattern.endswith('$')):
            raise ValueError(f'A family pattern must be anchored with ^ and $: {pattern}')
        matcher = re.compile(pattern)
        members = sorted(name for name in known if matcher.fullmatch(name))
        if not members:
            unused.append(pattern)
            continue
        record = {'pattern': pattern,
                  'database_names': sum(1 for name in corpus if matcher.fullmatch(name)),
                  'enumerated_devices': len({device for name in members for device in known[name]}),
                  'example': members[0], 'inferred_by': 'curated', '_names': members}
        if entry.get('note'):
            record['note'] = entry['note']
        records.append(record)
    return records, unused


def already_skipped_by(rules):
    """A test for names the other novelty rules deal with, given NoveltyRules(dir, gatt=False)."""
    def already_skipped(name):
        return bool(RETAINED.search(name) or
                    rules.classify(((9, name.encode('utf-8')),), '00:00:00:00:00:00', 'random'))
    return already_skipped


def build(known, corpus, signatures=None, counts=None, curated=(), already_skipped=None):
    """The JSON document for novelty_names_GATT.json, and the rejected families."""
    usable = {name: devices for name, devices in known.items() if len(name) >= MIN_NAME_LENGTH}
    too_short = sorted(name for name in known if name not in usable)
    held = {}

    def elsewhere(name):
        """Is this name already dealt with by the other novelty rules?"""
        if already_skipped is None:
            return False
        if name not in held:
            held[name] = bool(already_skipped(name))
        return held[name]

    redundant = {name for name in usable if elsewhere(name)}
    usable = {name: devices for name, devices in usable.items() if name not in redundant}

    chosen, unused = curated_families(curated, usable, corpus)
    chosen_matchers = [re.compile(record['pattern']) for record in chosen]
    remaining = {name: devices for name, devices in usable.items()
                 if not any(m.fullmatch(name) for m in chosen_matchers)}
    inferred, leftover, rejected = infer(remaining, corpus, signatures)
    # An inferred family adds nothing when a hand-written one covers all of its
    # names that the other rules do not already hold. (That is how a hand-written
    # family with an exception for those names replaces a wider inferred one.)
    inferred = [record for record in inferred
                if not any(all(m.fullmatch(name) for name in record['_names'] if not elsewhere(name))
                           for m in chosen_matchers)]
    patterns = sorted(chosen + inferred, key=lambda record: (-record['database_names'], record['pattern']))
    for record in patterns + rejected:
        record.pop('_names', None)
    matchers = [re.compile(record['pattern']) for record in patterns]
    covered = sum(any(m.fullmatch(name) for m in matchers) for name in usable)
    document = {
        'generated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'source': 'local bt2 database: advertised names (LE advertising/scan response, BR/EDR EIR) '
                  'of devices whose GATT enumeration ran to the end',
        'matching': 'patterns are full-match regexes, names are exact; both are case-sensitive and '
                    'apply to the NFKC-normalized, trimmed advertised name. Consulted only for a '
                    'device that no other novelty rule skips.',
        'counts': dict(counts or {}, enumerated_names=len(known), patterns=len(patterns),
                       hand_written_patterns=len(chosen), names_covered_by_patterns=covered,
                       exact_names=len(leftover), names_too_short_to_use=len(too_short),
                       names_left_to_the_other_rules=len(redundant)),
        'patterns': patterns,
        'names': leftover,
        'too_short': too_short,
    }
    if unused:
        document['unused_families'] = unused
    return document, rejected


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

def would_be_committed(path, repo_root=REPO_ROOT):
    """Is path inside the repository at a place Git does not ignore?"""
    path = Path(path).resolve()
    try:
        path.relative_to(Path(repo_root).resolve())
    except ValueError:
        return False                       # outside the repository
    try:
        result = subprocess.run(['git', '-C', str(repo_root), 'check-ignore', '-q', str(path)],
                                capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False                       # no Git here, nothing to commit to
    return result.returncode == 1          # 0 ignored, 1 not ignored, 128 not a repository


def prepare_output(path, repo_root=REPO_ROOT):
    """Create the output's directory, unless the file could end up in a commit."""
    path = Path(path)
    if would_be_committed(path, repo_root):
        raise SystemExit(f'{path} is inside this repository and is not ignored by Git. This file holds '
                         'device names from the local database: write it to Analysis/metadata/private '
                         '(the default) or somewhere outside the repository.')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_database(cursor):
    """Return (known, corpus, signatures, counts) from an open bt2 cursor."""
    def device(bdaddr, random):
        return (str(bdaddr).strip().lower(), int(random))

    cursor.execute('SELECT bdaddr, bdaddr_random, begin_handle, end_handle FROM GATT_services')
    services = [(device(b, r), begin, end) for b, r, begin, end in cursor]
    cursor.execute('SELECT bdaddr, bdaddr_random, declaration_handle, char_properties, char_value_handle, UUID '
                   'FROM GATT_characteristics')
    rows = [(device(b, r), declaration, properties, value_handle, uuid)
            for b, r, declaration, properties, value_handle, uuid in cursor]
    cursor.execute('SELECT bdaddr, bdaddr_random, char_value_handle, operation FROM GATT_characteristics_values')
    values = [(device(b, r), value_handle, operation) for b, r, value_handle, operation in cursor]
    complete = fully_enumerated(services, [row[:4] for row in rows], values)

    signatures = defaultdict(set)
    for dev, _, _, _, uuid in rows:
        if dev in complete:
            signatures[dev].add(str(uuid).strip().lower().replace('-', ''))
    signatures = {dev: frozenset(uuids) for dev, uuids in signatures.items()}

    advertised, name_devices = defaultdict(set), defaultdict(set)
    cursor.execute('SELECT bdaddr, bdaddr_random, name_hex_str FROM LE_bdaddr_to_name '
                   'WHERE device_name_type IN (8, 9)')
    for b, r, encoded in cursor:
        name = normalize_name(decode_hex_name(encoded))
        if name:
            advertised[device(b, r)].add(name)
            name_devices[name].add(('le',) + device(b, r))
    cursor.execute('SELECT bdaddr, name_hex_str FROM EIR_bdaddr_to_name WHERE device_name_type IN (8, 9)')
    for b, encoded in cursor:
        name = normalize_name(decode_hex_name(encoded))
        if name:
            advertised[device(b, 0)].add(name)      # BR/EDR addresses are public
            name_devices[name].add(('btc',) + device(b, 0))

    known = defaultdict(list)
    named = 0
    for dev in sorted(complete):
        named += bool(advertised.get(dev))
        for name in advertised.get(dev, ()):
            known[name].append(dev)
    counts = {'fully_enumerated_devices': len(complete), 'of_which_advertise_a_name': named,
              'advertised_names_in_database': len(name_devices)}
    return dict(known), {name: len(devices) for name, devices in name_devices.items()}, signatures, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', default=str(PRIVATE_DIR / GATT_NAMES_FILE))
    parser.add_argument('--show-rejected', action='store_true', help='list families that were not generalized')
    parser.add_argument('--db-host', default='localhost')
    parser.add_argument('--db-user', default='user')
    parser.add_argument('--db-password', default='a')
    parser.add_argument('--db-name', default='bt2')
    args = parser.parse_args()
    output = prepare_output(args.output)

    sys.path.insert(0, str(REPO_ROOT / 'Analysis'))
    from handle_venv import activate_venv
    activate_venv()
    import mysql.connector
    connection = mysql.connector.connect(
        host=args.db_host, user=args.db_user, password=args.db_password, database=args.db_name,
        charset='utf8mb4', collation='utf8mb4_unicode_ci', auth_plugin='mysql_native_password')
    cursor = connection.cursor()
    try:
        known, corpus, signatures, counts = load_database(cursor)
    finally:
        cursor.close()
        connection.close()

    families_file = output.parent / FAMILIES_FILE
    curated = json.loads(families_file.read_text())['families'] if families_file.exists() else ()
    rules = NoveltyRules(output.parent, gatt=False)
    document, rejected = build(known, corpus, signatures, counts, curated, already_skipped_by(rules))
    output.write_text(json.dumps(document, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps(document['counts'], indent=1))
    print(f'wrote {output}')
    for pattern in document.get('unused_families', ()):
        print(f'hand-written family not in use: {pattern}')
    if args.show_rejected:
        for record in sorted(rejected, key=lambda r: -r['database_names']):
            if record['rejected'] != 'few names':
                print(f"{record['database_names']:6d} names  {record['rejected']:38s} {record['pattern']}")


if __name__ == '__main__':
    main()
