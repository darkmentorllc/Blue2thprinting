"""Names of devices already fully GATT-enumerated: builder and novelty rule.

Every name here is made up. The real file is built from the local database and
lives only in Analysis/metadata/private.
"""
import contextlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import central_app_launcher as cal
from novelty import build_gatt_names as builder
from novelty.discovery import Report
from novelty.rules import AdvertisementEvidence, GATT_KNOWN, GATT_NAMES_FILE, NoveltyRules, ad_frames
from test_novelty_rules import ad, ADDRESS, PRIVATE_DIR

READ, ERROR, NOTIFY = 0x0b, 0x01, 0x1b
HAVE_GATT_NAMES = (PRIVATE_DIR / GATT_NAMES_FILE).exists()


def dev(n):
    return (f'aa:00:00:00:00:{n:02x}', 1)


class FullyEnumeratedTests(unittest.TestCase):
    def enumerate(self, services, characteristics, values):
        d = dev(1)
        return bool(builder.fully_enumerated(
            [(d,) + s for s in services], [(d,) + c for c in characteristics], [(d,) + v for v in values]))

    def test_every_readable_characteristic_must_be_answered(self):
        services = [(1, 5), (6, 9)]
        characteristics = [(2, 0x02, 3), (4, 0x10, 5), (7, 0x0a, 8)]   # read, notify-only, read+write
        self.assertTrue(self.enumerate(services, characteristics, [(3, READ), (8, READ)]))
        self.assertFalse(self.enumerate(services, characteristics, [(3, READ)]))
        # An ATT error is an answer, a notification is not.
        self.assertTrue(self.enumerate(services, characteristics, [(3, READ), (8, ERROR)]))
        self.assertFalse(self.enumerate(services, characteristics, [(3, READ), (8, NOTIFY)]))

    def test_something_must_actually_have_been_read(self):
        self.assertFalse(self.enumerate([(1, 3)], [(2, 0x02, 3)], [(3, ERROR)]))
        self.assertFalse(self.enumerate([(1, 3)], [(2, 0x10, 3)], []))          # nothing readable

    def test_structure_must_be_complete(self):
        # The second service spans handles but none of its characteristics were found.
        self.assertFalse(self.enumerate([(1, 3), (4, 9)], [(2, 0x02, 3)], [(3, READ)]))
        self.assertTrue(self.enumerate([(1, 3), (4, 4)], [(2, 0x02, 3)], [(3, READ)]))   # empty service
        self.assertFalse(self.enumerate([], [(2, 0x02, 3)], [(3, READ)]))                # no services at all


def corpus_of(*families):
    """{name: device count} from (names, devices per name) groups."""
    return {name: count for names, count in families for name in names}


def lamps(n, prefix='Lamp_'):
    return [f'{prefix}{(i * 2749 + 4099) % 65536:04X}' for i in range(n)]


def code(i, length, alphabet='0123456789GHJKLMNPQRSTUVWXYZ'):
    """A made-up serial of digits and (non-hex) capitals."""
    value = (i * 7919 + 104729) * 2654435761 % len(alphabet) ** length
    return ''.join(alphabet[value // len(alphabet) ** k % len(alphabet)] for k in range(length))


class InferenceTests(unittest.TestCase):
    def infer(self, known, corpus, signatures=None):
        accepted, leftover, rejected = builder.infer(known, corpus, signatures)
        return [r['pattern'] for r in accepted], leftover, rejected

    def test_identifier_suffix_becomes_one_regex_covering_unenumerated_members(self):
        names = lamps(12)
        patterns, leftover, _ = self.infer({names[0]: [dev(1)], names[5]: [dev(2)]}, corpus_of((names, 1)))
        self.assertEqual(patterns, [r'^Lamp_[0-9A-F]{4}$'])
        self.assertEqual(leftover, [])
        self.assertTrue(all(re.fullmatch(patterns[0], name) for name in names))
        self.assertFalse(re.fullmatch(patterns[0], 'Lamp_12345'))
        self.assertFalse(re.fullmatch(patterns[0], 'Lamp_12G4'))

    def test_too_few_names_stay_exact(self):
        names = lamps(builder.MIN_FAMILY_NAMES - 1)
        patterns, leftover, _ = self.infer({names[0]: [dev(1)]}, corpus_of((names, 1)))
        self.assertEqual((patterns, leftover), ([], [names[0]]))

    def test_model_numbers_shared_by_many_devices_are_not_identifiers(self):
        models = [f'Speaker {n}B' for n in range(510, 600, 10)]
        patterns, leftover, rejected = self.infer({models[0]: [dev(1)]}, corpus_of((models, 25)))
        self.assertEqual((patterns, leftover), ([], [models[0]]))
        self.assertIn('names shared by many devices', {r['rejected'] for r in rejected})

    def test_free_text_is_not_an_identifier(self):
        people = ['Anna', 'Bert', 'Cleo', 'Dave', 'Edna', 'Finn', 'Gwen', 'Hugo', 'Iris', 'Jack']
        rooms = [f"{p}'s Room" for p in people]
        watches = [f'Brand{p} Watch (v{i})' for i, p in enumerate(people)]
        for names in (rooms, watches):
            patterns, leftover, _ = self.infer({names[0]: [dev(1)]}, corpus_of((names, 1)))
            self.assertEqual((patterns, leftover), ([], [names[0]]))

    def test_names_with_no_fixed_text_are_not_a_family(self):
        names = [f'{(i * 7919 + 104729) % 16 ** 8:08X}' for i in range(20)]
        patterns, leftover, rejected = self.infer({names[0]: [dev(1)]}, corpus_of((names, 1)))
        self.assertEqual((patterns, leftover), ([], [names[0]]))
        self.assertIn('no usable anchor', {r['rejected'] for r in rejected})

    def test_serial_and_aligned_families(self):
        serials = [f'Cam 3S {code(i, 6)}' for i in range(10)]
        suffixed = [f'{31000000 + i * 104729}.0A0B0C0D' for i in range(10)]
        patterns, leftover, _ = self.infer({serials[0]: [dev(1)], suffixed[0]: [dev(2)]},
                                           corpus_of((serials, 1), (suffixed, 1)))
        self.assertEqual(leftover, [])
        self.assertIn(r'^Cam\ 3S\ [0-9A-Z]{6}$', patterns)
        self.assertTrue(any(all(re.fullmatch(p, n) for n in suffixed) for p in patterns))

    def test_family_whose_members_have_different_gatt_databases_is_never_generalized(self):
        names = [f'Med {100000 + i * 7919}' for i in range(40)]
        known = {names[i]: [dev(i)] for i in range(4)}
        different = {dev(i): frozenset({f'uuid-{i}-{j}' for j in range(6)}) for i in range(4)}
        patterns, leftover, rejected = self.infer(known, corpus_of((names, 1)), different)
        self.assertEqual(patterns, [])                       # not as a whole, not split by first digit
        self.assertEqual(leftover, sorted(known))
        self.assertIn('GATT databases differ', {r['rejected'] for r in rejected})
        same = {device: frozenset({'a', 'b', 'c'}) for device in different}
        self.assertEqual(self.infer(known, corpus_of((names, 1)), same)[0], [r'^Med\ [0-9]{6}$'])

    def test_one_letter_anchor_needs_enumerated_members_that_vouch_for_it(self):
        family = [f'N{code(i, 4)}' for i in range(16)]
        corpus = corpus_of((family, 1))
        same = {dev(i): frozenset({'a', 'b'}) for i in range(8)}
        spread = {family[i]: [dev(i)] for i in range(6)}
        self.assertEqual(self.infer(spread, corpus, same)[0], [r'^N[0-9A-Z]{4}$'])
        self.assertEqual(self.infer(spread, corpus)[0], [])                 # no GATT evidence
        # Enumerated members that all share more than the family does prove nothing about it.
        narrow_names = ['NGH01', 'NGH02', 'NGH03', 'NGH04', 'NGH05']
        narrow = {name: [dev(i)] for i, name in enumerate(narrow_names)}
        self.assertEqual(self.infer(narrow, dict(corpus, **{n: 1 for n in narrow_names}), same)[0], [])

    def test_family_inside_a_wider_accepted_family_is_dropped(self):
        models = [f'Bulb_H10{m}_' for m in ('A1', 'B2', 'C3', 'D4')]
        names = [f'{model}{(i * 2749 + 4099 + k * 977) % 65536:04X}'
                 for k, model in enumerate(models) for i in range(10)]
        known = {names[0]: [dev(1)], names[25]: [dev(2)]}
        patterns, leftover, _ = self.infer(known, corpus_of((names, 1)))
        self.assertEqual(leftover, [])
        for pattern in patterns:      # no pattern is wholly inside another
            others = [p for p in patterns if p != pattern]
            covered = [n for n in names if re.fullmatch(pattern, n)]
            self.assertFalse(any(all(re.fullmatch(o, n) for n in covered) for o in others), patterns)

    def test_document_is_deterministic_and_leaves_out_unusable_names(self):
        names = lamps(12)
        known = {names[0]: [dev(1)], 'TY': [dev(2)], 'Kitchen Scale': [dev(3)], '??': [dev(4)]}
        corpus = corpus_of((names, 1), (['TY', 'Kitchen Scale', '??'], 3))
        first, _ = builder.build(known, corpus, counts={'fully_enumerated_devices': 4})
        second, _ = builder.build(dict(reversed(list(known.items()))), dict(reversed(list(corpus.items()))))
        self.assertEqual(first['patterns'], second['patterns'])
        self.assertEqual(first['names'], ['Kitchen Scale'])
        self.assertEqual(first['too_short'], ['??', 'TY'])
        self.assertEqual(first['counts']['patterns'], 1)
        self.assertEqual(first['counts']['fully_enumerated_devices'], 4)
        for record in first['patterns']:
            self.assertTrue(re.fullmatch(record['pattern'], record['example']))
            self.assertNotIn('_names', record)

    def test_builder_writes_only_into_an_existing_private_directory(self):
        with tempfile.TemporaryDirectory() as d, patch.object(sys, 'argv', ['build', '--output', f'{d}/missing/x.json']):
            with self.assertRaises(SystemExit):
                builder.main()


class GattKnownRuleTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        (Path(self.dir.name) / GATT_NAMES_FILE).write_text(json.dumps({
            'patterns': [{'pattern': r'^Lamp_[0-9A-F]{4}$'}], 'names': ['Kitchen Scale', 'Polestar 3']}))
        self.rules = NoveltyRules(self.dir.name)

    def classify(self, name, kind=9):
        return self.rules.classify(ad_frames(ad(kind, name)), ADDRESS, 'random')

    def test_exact_names_and_families_are_skipped(self):
        for name in ('Kitchen Scale', 'Lamp_0A1B', 'Lamp_FFFF'):
            for kind in (8, 9):
                self.assertEqual(self.classify(name, kind), {GATT_KNOWN}, name)
        for name in ('Kitchen Scales', 'Kitchen', 'Lamp_0A1', 'Lamp_0A1G', 'Novel Sensor'):
            self.assertFalse(self.classify(name), name)

    def test_matching_is_case_sensitive_and_ignores_padding(self):
        for name in ('kitchen scale', 'LAMP_0A1B', 'Lamp_0a1b'):
            self.assertFalse(self.classify(name), name)
        self.assertEqual(self.classify(b'Kitchen Scale\x00\x00'), {GATT_KNOWN})
        self.assertEqual(self.classify('  Lamp_0A1B '), {GATT_KNOWN})
        self.assertEqual(self.classify('Ｌａｍｐ_0A1B'), {GATT_KNOWN})     # NFKC, as the builder stores it

    def test_it_adds_to_the_other_categories(self):
        frames = ad_frames(ad(9, 'Kitchen Scale') + ad(255, bytes.fromhex('4c001005')))
        self.assertEqual(self.rules.classify(frames, ADDRESS, 'random'), {GATT_KNOWN, 'APPLE'})

    def test_retained_vehicle_brands_are_still_never_skipped(self):
        self.assertTrue(self.rules.gatt_known('Polestar 3'))
        self.assertFalse(self.classify('Polestar 3'))

    def test_without_the_file_nothing_is_gatt_known(self):
        with tempfile.TemporaryDirectory() as empty:
            rules = NoveltyRules(empty)
            self.assertFalse(rules.classify(ad_frames(ad(9, 'Kitchen Scale')), ADDRESS, 'random'))
            self.assertIn('no GATT-enumerated names', rules.describe())
        self.assertFalse(NoveltyRules().gatt_known('Kitchen Scale'))
        self.assertIn('1 name families and 2 names already GATT-enumerated', self.rules.describe())

    def test_launcher_skips_gatt_known_devices_on_both_transports_only_in_novelty_mode(self):
        stores = ('ble_bdaddrs', 'btc_bdaddrs', 'ble_gatt_value_deprioritized_bdaddrs', 'ble_address_types',
                  'device_connect_attempts', 'device_total_attempts', 'device_last_seen',
                  'gatt_success_bdaddrs', 'sdp_success_bdaddrs', 'lmp2thprint_success_bdaddrs')
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            for name in stores:
                stack.enter_context(patch.object(cal, name, {}))
            stack.enter_context(patch.object(cal, 'novelty_evidence', AdvertisementEvidence(self.rules)))
            stack.enter_context(patch.object(cal, 'skip_these_addresses', []))
            for enabled in (True, False):
                for kind, atype in (('BLE', 'random'), ('BTC', 'public')):
                    with self.subTest(novelty_mode=enabled, transport=kind):
                        stack.enter_context(patch.object(cal, 'novelty_mode', enabled))
                        queue = cal.ble_bdaddrs if kind == 'BLE' else cal.btc_bdaddrs
                        queue.clear()
                        cal._handle_discovery_report(Report(ADDRESS, atype, kind, -50, ((9, b'Lamp_0A1B'),)))
                        cal._handle_discovery_report(Report('ce:00:00:00:00:09', atype, kind, -50, ((9, b'Novel Sensor'),)))
                        self.assertEqual(ADDRESS in queue, not enabled)
                        self.assertIn('ce:00:00:00:00:09', queue)
                        self.assertEqual(cal._candidate_skip_reason(kind, ADDRESS, atype),
                                         f'novelty:{GATT_KNOWN}' if enabled else None)


class InstalledFileTests(unittest.TestCase):
    """The real file is private. These run only where it has been installed."""

    @unittest.skipUnless(HAVE_GATT_NAMES, f'{GATT_NAMES_FILE} is not installed in Analysis/metadata/private')
    def test_installed_file_is_usable(self):
        document = json.loads((PRIVATE_DIR / GATT_NAMES_FILE).read_text())
        rules = NoveltyRules(PRIVATE_DIR)
        self.assertEqual(len(rules.gatt_patterns), len(document['patterns']))
        self.assertTrue(document['patterns'] and document['names'])
        for record in document['patterns']:
            with self.subTest(pattern=record['pattern']):
                self.assertTrue(re.fullmatch(record['pattern'], record['example']))
                self.assertTrue(rules.gatt_known(record['example']))
                self.assertTrue(record['pattern'].startswith('^') and record['pattern'].endswith('$'))
        self.assertTrue(all(len(name) >= builder.MIN_NAME_LENGTH for name in document['names']))
        self.assertTrue(all(rules.gatt_known(name) for name in document['names']))
        self.assertEqual(sorted(document['names']), document['names'])

    def test_the_file_is_never_part_of_this_repository(self):
        scripts = Path(__file__).resolve().parents[1]
        self.assertEqual(list(scripts.rglob(GATT_NAMES_FILE)), [])
        self.assertEqual(builder.PRIVATE_DIR, PRIVATE_DIR)


if __name__ == '__main__':
    unittest.main()
