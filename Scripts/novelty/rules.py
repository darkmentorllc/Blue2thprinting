"""Reviewed DM BT rules, applied only to on-air AD/EIR structures.

No device display-name, GATT, SDP or SQL API belongs in this module. Public
address OUIs are deliberately unavailable for random or unknown address types.
"""
from collections import OrderedDict
from functools import lru_cache
import json
from pathlib import Path
import re
import threading
import time
import unicodedata
import uuid

DATA = Path(__file__).parent / 'data'
IDS = json.loads((DATA / 'identifiers.json').read_text())
for _key, _value in list(IDS.items()):
    if isinstance(_value, list):
        IDS[_key] = frozenset(_value)
RETAINED = re.compile(IDS['RETAINED_VEHICLE'], re.I)
NON_AUDIO = re.compile(IDS['NON_AUDIO'], re.I)
ADDRESS = re.compile(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}')
APPLE_NAMES = ('iphone', 'ipad', 'ipod', 'macbook', 'imac', 'airpods', 'apple watch', 'airtag', 'homepod')
SAMSUNG_MODEL = re.compile(r'\b(S\d{2} ?Ultra|S\d{2} ?FE|Z ?Fold\d*|Z ?Flip\d*)\b', re.I)
PRODUCTS = [(n, bytes.fromhex(p)) for n, p in (
    (21, '2d010400013105'), (22, '2d0104000202b03108'),
    (26, 'cb0e2e2101'), (29, 'd6050a00040022'), (29, 'd6050b00040022'))]


def ad_frames(raw):
    """Parse complete AD structures. Never infer anything from a truncated tail."""
    out, offset = [], 0
    while offset < len(raw):
        length = raw[offset]
        if length == 0 or offset + length >= len(raw):
            break
        out.append((raw[offset + 1], bytes(raw[offset + 2:offset + length + 1])))
        offset += length + 1
    return tuple(out)


def service_uuid(data):
    if len(data) in (2, 4):
        return f'{int.from_bytes(data, "little"):08x}-0000-1000-8000-00805f9b34fb'
    return str(uuid.UUID(bytes=data[::-1]))


def uuid16(value):
    return f'{value:08x}-0000-1000-8000-00805f9b34fb'


def fast_pair_audio(data):
    if len(data) < 3 or data[0] not in (0, 0x10):
        return False
    length = data[1] >> 4
    if length < 3 or data[1] & 15 not in (0, 2):
        return False
    offset = 2 + length
    if offset >= len(data):
        return False
    salt = data[offset]
    length = salt >> 4
    if salt & 15 != 1 or length not in (1, 2) or (data[0] == 0x10 and length != 2):
        return False
    offset += 1 + length
    if offset > len(data):
        return False
    battery = audio_switch = False
    while offset < len(data):
        header = data[offset]
        length, kind = header >> 4, header & 15
        offset += 1
        if not length or offset + length > len(data) or kind in (0, 1, 2):
            return False
        if kind in (3, 4):
            if battery or length != 3 or any((v & 127) > 100 and (v & 127) != 127 for v in data[offset:offset+length]):
                return False
            battery = True
        elif kind == 6 and data[0] == 0x10 and length >= 2:
            audio_switch = True
        offset += length
    return battery or audio_switch


def _full_uuid(value):
    """CLUES writes 16-bit UUIDs as four hex digits; everything else is 128-bit."""
    return uuid16(0)[:4] + value + uuid16(0)[8:] if len(value) == 4 else value


# CLUES uses a lowercase "x" for one wildcard hex digit ("4f86000x-..."). DM BT
# resolves those through its CLUES lookup; here they become bounded patterns.
VENDOR_SERVICES = {
    vendor: frozenset(uuid16(v) for v in IDS[vendor + '_SIG_UUID16S']) |
            frozenset(_full_uuid(v) for v in IDS[vendor + '_CLUES_UUIDS'] if 'x' not in v)
    for vendor in ('APPLE', 'SAMSUNG')
}
VENDOR_SERVICE_WILDCARDS = {
    vendor: tuple(re.compile(_full_uuid(v).replace('x', '[0-9a-f]'))
                  for v in sorted(IDS[vendor + '_CLUES_UUIDS']) if 'x' in v)
    for vendor in ('APPLE', 'SAMSUNG')
}
AUDIO_SERVICES = frozenset(uuid16(v) for v in IDS['AUDIO_SERVICES'])
NAME_CATEGORIES = ('ANDROID', 'SAMSUNG_PHONES', 'VEHICLES', 'AUDIO')
PRIVATE_NAMES_FILE = 'novelty_names.json'
# Advertised names of devices whose GATT database is already fully enumerated in
# the local database (Scripts/novelty/build_gatt_names.py). Private, like the above.
GATT_NAMES_FILE = 'novelty_names_GATT.json'
GATT_KNOWN = 'GATT_KNOWN'


def normalize_name(name):
    """The form GATT-known names are compared in, at build time and at run time."""
    if not isinstance(name, str):
        return ''
    return unicodedata.normalize('NFKC', name).strip('\x00 \t\r\n\x0b\x0c').strip()


def _compile(rows):
    return tuple(re.compile(row['pattern'], re.I) for row in rows)


@lru_cache(maxsize=1)
def _bundled_patterns():
    rows = json.loads((DATA / 'names.json').read_text())['categories']
    unknown = set(rows) - set(NAME_CATEGORIES)
    if unknown:
        raise ValueError(f'Unknown novelty category: {sorted(unknown)}')
    return {key: _compile(rows.get(key, ())) for key in NAME_CATEGORIES}


class NoveltyRules:
    """Name rules come from two places.

    Scripts/novelty/data/names.json is committed here and holds only rules that
    are public: the public NamePrints plus the generic name families. Rules
    reviewed from the *private* NamePrints live outside this repository, in
    <private_dir>/novelty_names.json, and are copied to a capture node with scp.
    Without that file novelty mode still runs, with fewer name rules.

    <private_dir>/novelty_names_GATT.json, when present, adds the GATT_KNOWN
    category: the device advertises a name (or a name of a family) whose GATT
    database has been fully enumerated before. Its patterns and names are
    case-sensitive, unlike the category rules above.

    That list is the last resort. It is consulted only for a device that nothing
    else has skipped, and its builder leaves out every name the other rules
    already skip, so the two never do the same work twice. gatt=False ignores the
    file; the builder uses that to ask what the other rules skip on their own.
    """
    def __init__(self, private_dir=None, gatt=True):
        self.patterns = dict(_bundled_patterns())
        self.public_name_rules = sum(len(v) for v in self.patterns.values())
        self.private_name_rules = 0
        self.private_file = None
        # Private additions must be explicitly categorized and reviewed. Do not
        # guess categories from arbitrary NamePrint descriptions or CLUES prose.
        if private_dir is not None:
            private_file = Path(private_dir) / PRIVATE_NAMES_FILE
            if private_file.exists():
                additions = json.loads(private_file.read_text())['categories']
                for category, entries in additions.items():
                    if category not in self.patterns:
                        raise ValueError(f'Unknown novelty category: {category}')
                    compiled = _compile(entries)
                    self.patterns[category] += compiled
                    self.private_name_rules += len(compiled)
                self.private_file = private_file
        self.gatt_patterns, self.gatt_names, self.gatt_file = (), frozenset(), None
        if private_dir is not None and gatt:
            gatt_file = Path(private_dir) / GATT_NAMES_FILE
            if gatt_file.exists():
                known = json.loads(gatt_file.read_text())
                self.gatt_patterns = tuple(re.compile(row['pattern']) for row in known.get('patterns', ()))
                self.gatt_names = frozenset(known.get('names', ()))
                self.gatt_file = gatt_file
        self.name_categories = lru_cache(maxsize=1024)(self._name_categories)
        self.gatt_known = lru_cache(maxsize=1024)(self._gatt_known)

    def describe(self):
        private = (f'{self.private_name_rules} private name rules from {self.private_file}'
                   if self.private_file else
                   f'no private name rules ({PRIVATE_NAMES_FILE} not found)')
        gatt = (f'{len(self.gatt_patterns)} name families and {len(self.gatt_names)} names already '
                f'GATT-enumerated from {self.gatt_file}' if self.gatt_file else
                f'no GATT-enumerated names ({GATT_NAMES_FILE} not found)')
        return f'{self.public_name_rules} public name rules, {private}, {gatt}'

    def _gatt_known(self, name):
        """Has a device advertising this name been fully GATT-enumerated before?"""
        if not self.gatt_file:
            return False
        name = normalize_name(name)
        return name in self.gatt_names or any(pattern.fullmatch(name) for pattern in self.gatt_patterns)

    def _name_categories(self, name):
        return frozenset(key for key, patterns in self.patterns.items()
                         if any(pattern.fullmatch(name) for pattern in patterns))

    def classify(self, frames, address, address_type):
        names = [name for name in (data.decode('utf-8', errors='replace').strip('\x00 \t\r\n')
                                   for kind, data in frames if kind in (8, 9)) if name]
        # Retain Chinese vehicle brands even if they advertise a shared Apple
        # integration service. Otherwise enabling all categories defeats the veto.
        if any(RETAINED.search(name) for name in names):
            return frozenset()
        msds = [data for kind, data in frames if kind == 255 and len(data) >= 2]
        companies = {int.from_bytes(data[:2], 'little') for data in msds}
        services, vendor_services, appearances = set(), set(), set()
        sd16 = {}
        for kind, data in frames:
            width = {2: 2, 3: 2, 4: 4, 5: 4, 6: 16, 7: 16, 0x14: 2, 0x1f: 4, 0x15: 16}.get(kind)
            if width:
                parsed = {service_uuid(data[p:p+width]) for p in range(0, len(data)-width+1, width)}
                vendor_services.update(parsed)
                if kind not in (0x14, 0x1f, 0x15):
                    services.update(parsed)
            width = {0x16: 2, 0x20: 4, 0x21: 16}.get(kind)
            if width and len(data) >= width:
                services.add(service_uuid(data[:width]))
                if kind == 0x16:
                    sd16.setdefault(int.from_bytes(data[:2], 'little'), []).append(data[2:])
            if kind == 0x19 and len(data) == 2:
                appearances.add(int.from_bytes(data, 'little'))
        vendor_services.update(services)
        oui = int(address[:8].replace(':', ''), 16) if address_type == 'public' and ADDRESS.fullmatch(address) else None
        bits = set().union(*(self.name_categories(name) for name in names))
        result = set()
        for vendor, cid in (('APPLE', 0x4c), ('SAMSUNG', 0x75)):
            cid_match = any(int.from_bytes(data[:2], 'little') == cid and
                            not (cid == 0x4c and data[2:4] == b'\x02\x15') for data in msds)
            if (cid_match or oui in IDS[vendor + '_OUIS'] or vendor_services & VENDOR_SERVICES[vendor] or
                    any(pattern.fullmatch(value) for pattern in VENDOR_SERVICE_WILDCARDS[vendor]
                        for value in vendor_services)):
                result.add(vendor)
        if any(any(marker in n.lower() for marker in APPLE_NAMES) for n in names):
            result.add('APPLE')
        if 'SAMSUNG_PHONES' in bits or any('samsung' in n.lower() or 'galaxy' in n.lower() or SAMSUNG_MODEL.search(n) for n in names):
            result.add('SAMSUNG')
        if (0xfcf1 in sd16 or 0xfe50 in sd16 or 'ANDROID' in bits or
                (0x40 in appearances and (companies & IDS['PHONE_COMPANIES'] or oui in IDS['PHONE_OUIS']))):
            result.add('ANDROID')
        if not any('powerwall' in n.lower() for n in names) and (
                'VEHICLES' in bits or companies & IDS['VEHICLE_COMPANIES'] or
                services & {uuid16(0xfe48), uuid16(0x1122), '00000211-b2d1-43f0-9b88-960cebf8b91e'} or
                (any(0x8c0 <= v <= 0x8cf for v in appearances) and oui in IDS['VEHICLE_OUIS'])):
            result.add('VEHICLES')
        audio_appearance = any(0x840 <= v <= 0x845 or 0x940 <= v <= 0x946 or v == 0x881 for v in appearances)
        sony = bool(services & {uuid16(0xfd82), uuid16(0xfd2a)}) and any(
            len(d) == 19 and d[:4] == bytes.fromhex('2d011300') for d in msds)
        fp = any(d.hex() in IDS['AUDIO_FAST_PAIR_IDS'] for d in sd16.get(0xfe2c, ())) and (
            companies & (IDS['AUDIO_COMPANIES'] | {0x12d}) or audio_appearance)
        reviewed = any(len(d) == length and d.startswith(prefix) for d in msds for length, prefix in PRODUCTS)
        reviewed |= any(fast_pair_audio(d) for d in sd16.get(0xfe2c, ()))
        reviewed |= uuid16(0x1853) in services and any(len(d) >= 3 for d in sd16.get(0xfe2c, ()))
        if not any(NON_AUDIO.search(n) for n in names) and (
                'AUDIO' in bits or audio_appearance or sony or fp or reviewed or
                companies & IDS['AUDIO_COMPANIES'] or oui in IDS['AUDIO_OUIS'] or
                services & AUDIO_SERVICES):
            result.add('AUDIO')
        # Last resort: only a device nothing else skips is looked up among the
        # names already GATT-enumerated.
        if not result and self.gatt_file and any(self.gatt_known(name) for name in names):
            result.add(GATT_KNOWN)
        return frozenset(result)


# The only AD types classify() reads. Flags, TX power and the like are never
# evidence, so they are not cached: a packet that differs only in those fields
# must not look like new evidence. A rule that starts reading another AD type
# has to add it here (Scripts/tests checks the two stay in step).
EVIDENCE_TYPES = frozenset({8, 9, 255, 2, 3, 4, 5, 6, 7, 0x14, 0x15, 0x1f, 0x16, 0x20, 0x21, 0x19})
_NEVER = float('inf')


class AdvertisementEvidence:
    """Bounded ten-minute AD/scan-response evidence; typed addresses never mix.

    A changed name replaces previous identity evidence. Each individual AD
    field expires independently, so flags-only packets cannot keep a stale
    name/MSD alive. Only complete on-air fields may be passed to observe().

    HCI delivers an advertisement and its scan response as separate reports, so
    a Shortened Local Name in one and the Complete Local Name in the other are
    one identity, not a rename. Only a different value for the *same* name type
    counts as a change; otherwise the two halves would erase each other's
    evidence on every scan cycle.

    The verdict for an identity is kept with its evidence and recomputed only
    when the evidence changes: a field appears, expires or is replaced. Most
    reports repeat fields already held, and the launcher asks for the verdict
    again at every scheduling step, so classifying each time cost several
    milliseconds per report on a Pi Zero and could take its whole core.
    """
    def __init__(self, rules, clock=time.monotonic, capacity=4096, lifetime=600):
        self.rules, self.clock, self.capacity, self.lifetime = rules, clock, capacity, lifetime
        self.entries = OrderedDict()   # key -> (fields {frame: last seen}, verdict, first expiry)
        self.lock = threading.RLock()
        self.classifications = 0       # how often the rules actually ran (tests, QA)

    def _judge(self, key, fields, address, address_type):
        self.classifications += 1
        verdict = self.rules.classify(tuple(fields), address, address_type)
        self.entries[key] = (fields, verdict, min(fields.values()) + self.lifetime if fields else _NEVER)
        return verdict

    def _live(self, fields, now):
        return {frame: stamp for frame, stamp in fields.items() if now - stamp < self.lifetime}

    def observe(self, address, address_type, transport, frames):
        key = (address.lower(), address_type, transport)
        with self.lock:
            now = self.clock()
            fields, verdict, expiry = self.entries.pop(key, ({}, None, _NEVER))
            changed = verdict is None
            if now >= expiry:
                fields, before = self._live(fields, now), len(fields)
                changed = changed or len(fields) != before
            frames = [frame for frame in frames if frame[0] in EVIDENCE_TYPES]
            for kind in (8, 9):
                names = {frame for frame in frames if frame[0] == kind}
                old_names = {frame for frame in fields if frame[0] == kind}
                if names and old_names and names != old_names:
                    fields, changed = {}, True
                    break
            for frame in frames:
                changed = changed or frame not in fields
                fields[frame] = now
            if len(fields) > 64:
                # Bound pathological payload churn per identity, as well as identities.
                fields, changed = dict(sorted(fields.items(), key=lambda item: item[1])[-64:]), True
            if changed:
                verdict = self._judge(key, fields, address, address_type)
            else:
                self.entries[key] = (fields, verdict, min(fields.values()) + self.lifetime if fields else _NEVER)
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)
            return verdict

    def reasons(self, address, address_type, transport):
        with self.lock:
            key = (address.lower(), address_type, transport)
            entry = self.entries.get(key)
            if entry is None:
                # Nothing heard on air: only a public-address OUI can still decide.
                return self.rules.classify((), address, address_type)
            fields, verdict, expiry = entry
            now = self.clock()
            if now < expiry:
                return verdict
            return self._judge(key, self._live(fields, now), address, address_type)
