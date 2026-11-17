"""Portable no-radio regressions; also runnable on a capture Pi with unittest."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from novelty.rules import (AdvertisementEvidence, NoveltyRules, ad_frames, fast_pair_audio, PRODUCTS, IDS,
                           PRIVATE_NAMES_FILE, EVIDENCE_TYPES)

ADDRESS = 'ce:00:00:00:00:01'
REPO_ROOT = Path(__file__).resolve().parents[2]
METADATA = REPO_ROOT / 'Analysis/metadata'
# Rules reviewed from the private NamePrints are not part of this repository.
# They are present on the analysis machine and on a capture node they were
# copied to; anywhere else the tests that need them are skipped.
PRIVATE_DIR = METADATA / 'private'
HAVE_PRIVATE_RULES = (PRIVATE_DIR / PRIVATE_NAMES_FILE).exists()
HAVE_PRIVATE_NAMEPRINTS = bool(list(PRIVATE_DIR.glob('NAMEPRINT_*.csv')))


def ad(kind, data):
    if isinstance(data, str):
        data = data.encode()
    return bytes([len(data)+1, kind]) + data


def sd(number, data=b''):
    return ad(0x16, number.to_bytes(2, 'little')+data)


class RuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = NoveltyRules()

    def classify(self, raw=b'', address=ADDRESS, atype='random'):
        return self.rules.classify(ad_frames(raw), address, atype)

    def test_reviewed_names_and_localizations(self):
        groups = {
            'APPLE': ['Joao’s iPhone', 'AirPods Pro', 'HomePod'],
            'SAMSUNG': ['[TV] Samsung Q60', 'Galaxy Watch', "Asmi's S21 FE"],
            'ANDROID': ['Android-1234', 'Galaxy S21 5G'],
            'AUDIO': ['LE-WH-CH720N', 'LE_WH-1000XM4', 'Bose SL Flex SE 2', "Alex’s Pixel Buds Pro 2", 'tcl_B14S45H0_AB12'],
            'VEHICLES': ['GM_PEPS_VKM3', 'VM-207-BLE', 'TELLURIDE Digital Key', 'Carnival Digital Key', 'K5 Digital Key', 'Palisade Digital Key', 'Sonata Digital Key', 'IONIQ 5 Digital Key'],
        }
        for category, names in groups.items():
            for name in names:
                with self.subTest(category=category, name=name):
                    self.assertIn(category, self.classify(ad(9, name)))
                    self.assertIn(category, self.classify(ad(8, name.lower())))

    @unittest.skipUnless(HAVE_PRIVATE_RULES, f'{PRIVATE_NAMES_FILE} is not installed in Analysis/metadata/private')
    def test_private_nameprint_rules_are_loaded_from_private_metadata(self):
        """These names are covered only by rules reviewed from the private NamePrints."""
        private = NoveltyRules(PRIVATE_DIR)
        self.assertGreater(private.private_name_rules, 0)
        self.assertIn(str(PRIVATE_DIR), private.describe())
        groups = {
            'SAMSUNG': ['태연의 S21'],
            'ANDROID': ['S21 FE de Silva', 'S21 FE de Joao', "Shalonda's S21 FE", '태연의 S21'],
            'AUDIO': ['TOZO-T10'],
        }
        for category, names in groups.items():
            for name in names:
                for raw in (ad(9, name), ad(8, name.lower())):
                    with self.subTest(category=category, name=name):
                        self.assertIn(category, private.classify(ad_frames(raw), ADDRESS, 'random'))
                        # The committed public snapshot alone must not know them.
                        self.assertNotIn(category, self.rules.classify(ad_frames(raw), ADDRESS, 'random'))

    def test_public_snapshot_describes_missing_private_rules(self):
        with tempfile.TemporaryDirectory() as d:
            rules = NoveltyRules(d)
            self.assertEqual(rules.private_name_rules, 0)
            self.assertIn('no private name rules', rules.describe())
            self.assertEqual(rules.public_name_rules, NoveltyRules().public_name_rules)

    def test_empty_name_is_not_a_name(self):
        self.assertFalse(self.classify(ad(9, b'')))
        self.assertFalse(self.classify(ad(9, b'\x00\x00 ')))

    def test_negative_names_and_shared_service_ids(self):
        for name in ('Novel Sensor', 'NKEY eLatch', 'Digital Key', 'Key', 'Keyboard', 'TOZO-S3', 'Sony BRAVIA', 'QCY Watch'):
            with self.subTest(name=name):
                self.assertFalse(self.classify(ad(9, name)))
        for n in (0xfff5, 0xfeaa, 0xfe2c, 0x1853, 0xfe03):
            self.assertFalse(self.classify(sd(n)))

    def test_chinese_vehicles_retained_even_with_shared_vendor_services(self):
        for name in ('BYD Key', 'NIO Key', 'AVATR Key', 'XPeng', 'Volvo XC90', 'Polestar 2'):
            with self.subTest(name=name):
                self.assertFalse(self.classify(ad(9, name)+sd(0xfe48)+sd(0xfd6f)+ad(255,b'\x4c\0\x10\x01')))

    def test_android_service_data_not_just_uuid_list(self):
        for n in (0xfcf1, 0xfe50):
            self.assertIn('ANDROID', self.classify(sd(n)))
            self.assertNotIn('ANDROID', self.classify(ad(3,n.to_bytes(2,'little'))))

    def test_phone_appearance_requires_company_or_public_phone_oui(self):
        appearance=ad(0x19,b'\x40\x00')
        self.assertNotIn('ANDROID', self.classify(appearance))
        self.assertIn('ANDROID', self.classify(appearance+ad(255,b'\xc4\x00')))
        self.assertIn('ANDROID', self.classify(appearance,'94:8b:c1:00:00:01','public'))
        self.assertNotIn('ANDROID', self.classify(appearance,'94:8b:c1:00:00:01','random'))

    def test_public_oui_never_matches_random_unknown_or_malformed_address(self):
        for category, group in (('APPLE','APPLE_OUIS'),('SAMSUNG','SAMSUNG_OUIS'),('AUDIO','AUDIO_OUIS')):
            for oui in IDS[group]:
                addr=':'.join(f'{oui:06x}'[p:p+2] for p in (0,2,4))+':00:00:01'
                with self.subTest(category=category,addr=addr):
                    self.assertIn(category,self.classify(b'',addr,'public'))
                    self.assertNotIn(category,self.classify(b'',addr,'random'))
                    self.assertNotIn(category,self.classify(b'',addr,None))
        self.assertFalse(self.classify(b'','not-an-address','public'))

    def test_ibeacon_is_not_apple(self):
        self.assertNotIn('APPLE',self.classify(ad(255,bytes.fromhex('4c000215')+bytes(21))))
        self.assertIn('APPLE',self.classify(ad(255,bytes.fromhex('4c001005'))))
        self.assertIn('APPLE',self.classify(ad(255,bytes.fromhex('4c000215'))+ad(255,bytes.fromhex('4c001005'))))

    def test_vehicle_identifiers_and_appearance_constraints(self):
        for cid in IDS['VEHICLE_COMPANIES']:
            self.assertIn('VEHICLES',self.classify(ad(255,cid.to_bytes(2,'little'))))
        for n in (0xfe48,0x1122):
            self.assertIn('VEHICLES',self.classify(ad(3,n.to_bytes(2,'little'))))
        self.assertNotIn('VEHICLES',self.classify(ad(0x19,b'\xc0\x08')))
        self.assertIn('VEHICLES',self.classify(ad(0x19,b'\xc0\x08'),'0c:29:8f:00:00:01','public'))
        self.assertNotIn('VEHICLES',self.classify(ad(0x19,b'\xc0\x08'),'0c:29:8f:00:00:01','random'))
        self.assertNotIn('VEHICLES',self.classify(ad(9,'Tesla Powerwall')+sd(0xfe48)))

    def test_exact_audio_msd_lengths_and_prefixes(self):
        for length,prefix in PRODUCTS:
            data=prefix+bytes(length-len(prefix))
            with self.subTest(prefix=prefix.hex()):
                self.assertIn('AUDIO',self.classify(ad(255,data)))
                for end in range(len(data)):
                    self.assertNotIn('AUDIO',self.classify(ad(255,data[:end])))
                self.assertNotIn('AUDIO',self.classify(ad(255,data+b'\0')))
                damaged=bytearray(data);damaged[len(prefix)-1]^=1
                self.assertNotIn('AUDIO',self.classify(ad(255,damaged)))
                self.assertNotIn('AUDIO',self.classify(ad(9,'Sony BRAVIA')+ad(255,data)))

    def test_fast_pair_complete_boundaries(self):
        battery=bytes.fromhex('003001020311013364e4ff')
        switch=bytes.fromhex('1030010203210102260102')
        for raw in (battery,switch):
            self.assertTrue(fast_pair_audio(raw))
            self.assertIn('AUDIO',self.classify(sd(0xfe2c,raw)))
            for end in range(len(raw)):
                self.assertFalse(fast_pair_audio(raw[:end]))
            self.assertFalse(fast_pair_audio(raw+b'\x00'))
        for raw in ('00300102031101', '00330102031101', '0030010203110133656464', '2030010203110133646464'):
            self.assertFalse(fast_pair_audio(bytes.fromhex(raw)))
        self.assertIn('AUDIO',self.classify(sd(0x1853)+sd(0xfe2c,b'\x01\x02\x03')))
        self.assertNotIn('AUDIO',self.classify(sd(0xfe2c,b'\x01\x02\x03')))
        self.assertNotIn('AUDIO',self.classify(ad(0x14,b'\x53\x18')+sd(0xfe2c,b'\x01\x02\x03')))

    def test_service_uuid_width_and_byte_order(self):
        import uuid
        value='00000211-b2d1-43f0-9b88-960cebf8b91e'
        raw=uuid.UUID(value).bytes[::-1]
        self.assertIn('VEHICLES',self.classify(ad(7,raw)))
        self.assertIn('VEHICLES',self.classify(ad(0x21,raw)))
        self.assertIn('VEHICLES',self.classify(ad(5,(0xfe48).to_bytes(4,'little'))))
        self.assertIn('VEHICLES',self.classify(ad(0x20,(0xfe48).to_bytes(4,'little'))))
        self.assertNotIn('VEHICLES',self.classify(ad(0x15,raw)))

    def test_malformed_ad_never_reads_beyond_boundary(self):
        raw=ad(9,'LE-WH-CH720N')
        self.assertFalse(self.classify(raw[:-1]))
        self.assertFalse(self.classify(b'\0'+raw))
        self.assertEqual(self.classify(raw),self.classify(raw+b'\x20\xff\x4c'))
        self.assertEqual(ad_frames(b'\x01\x09'),((9,b''),))

    def test_private_reviewed_additions_are_optional_and_validated(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(NoveltyRules(d).classify(((9,b'Private QA audio'),),ADDRESS,'random'))
            p=Path(d)/'novelty_names.json'
            p.write_text(json.dumps({'categories':{'AUDIO':[{'pattern':'^Private QA audio$'}]}}))
            self.assertIn('AUDIO',NoveltyRules(d).classify(((9,b'Private QA audio'),),ADDRESS,'random'))
            p.write_text(json.dumps({'categories':{'unreviewed':[{'pattern':'.*'}]}}))
            with self.assertRaises(ValueError): NoveltyRules(d)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.now=0
        self.cache=AdvertisementEvidence(NoveltyRules(),clock=lambda:self.now,capacity=2,lifetime=10)

    def test_scan_response_and_nameless_update_merge_then_expire(self):
        self.cache.observe(ADDRESS,'random','BLE',ad_frames(ad(9,'LE-WH-CH720N')))
        self.now=9
        self.assertIn('AUDIO',self.cache.observe(ADDRESS,'random','BLE',ad_frames(ad(1,b'\x06'))))
        self.now=10
        self.assertFalse(self.cache.reasons(ADDRESS,'random','BLE'))

    def test_new_name_replaces_identity_and_type_transport_are_isolated(self):
        self.cache.observe(ADDRESS,'random','BLE',ad_frames(ad(9,'LE-WH-CH720N')))
        self.assertFalse(self.cache.reasons(ADDRESS,'public','BLE'))
        self.assertFalse(self.cache.reasons(ADDRESS,'random','BTC'))
        self.assertFalse(self.cache.observe(ADDRESS,'random','BLE',ad_frames(ad(9,'Novel Sensor'))))

    def test_shortened_and_complete_name_halves_merge_instead_of_erasing_each_other(self):
        """ADV_IND and SCAN_RSP arrive as separate reports. A Shortened Local Name
        in one and the Complete Local Name in the other are the same device."""
        advert=ad_frames(ad(8,'Novel Sen')+ad(255,bytes.fromhex('2d0104000202b03108')+bytes(13)))
        response=ad_frames(ad(9,'Novel Sensor'))
        for _ in range(3):  # several scan cycles: the verdict must not flip-flop
            self.assertIn('AUDIO',self.cache.observe(ADDRESS,'random','BLE',advert))
            self.assertIn('AUDIO',self.cache.observe(ADDRESS,'random','BLE',response))
            self.assertIn('AUDIO',self.cache.reasons(ADDRESS,'random','BLE'))

    def test_changed_name_of_the_same_type_still_replaces_identity(self):
        for kind in (8,9):
            self.cache.observe(ADDRESS,'random','BLE',ad_frames(ad(kind,'LE-WH-CH720N')))
            self.assertFalse(self.cache.observe(ADDRESS,'random','BLE',ad_frames(ad(kind,'Novel Sensor'))))
            self.cache.entries.clear()

    def test_repeated_reports_and_scheduler_questions_do_not_reclassify(self):
        """Classifying costs milliseconds on a Pi Zero. A report that repeats
        fields already held, or the launcher asking for the verdict again, must
        reuse the stored one."""
        advert=ad_frames(ad(1,b'\x06')+ad(255,bytes.fromhex('4c001005'))+ad(9,'Kitchen'))
        self.assertIn('APPLE',self.cache.observe(ADDRESS,'random','BLE',advert))
        ran=self.cache.classifications
        for tx_power in range(20):   # same evidence; only non-evidence fields differ
            self.now+=0.1
            noise=ad_frames(ad(1,b'\x06')+ad(0x0a,bytes([tx_power]))+ad(255,bytes.fromhex('4c001005'))+ad(9,'Kitchen'))
            self.assertIn('APPLE',self.cache.observe(ADDRESS,'random','BLE',noise))
            self.assertIn('APPLE',self.cache.reasons(ADDRESS,'random','BLE'))
        self.assertEqual(self.cache.classifications,ran)
        # New evidence is judged once, then reused again.
        self.assertIn('APPLE',self.cache.observe(ADDRESS,'random','BLE',ad_frames(ad(255,bytes.fromhex('4c001006')))))
        self.assertEqual(self.cache.classifications,ran+1)
        self.cache.reasons(ADDRESS,'random','BLE')
        self.assertEqual(self.cache.classifications,ran+1)

    def test_stored_verdict_always_equals_a_fresh_classification(self):
        """Replay a long pseudo-random stream against a cache that reclassifies
        from scratch at every step. Expiry, renames, the 64-field bound and
        eviction must leave both with the same answer at every step."""
        import random
        rules=NoveltyRules()
        class Fresh:
            """The evidence rules with no stored verdict."""
            def __init__(self,clock,capacity,lifetime):
                self.clock,self.capacity,self.lifetime,self.entries=clock,capacity,lifetime,{}
            def live(self,key):
                now=self.clock()
                return {f:t for f,t in self.entries.get(key,{}).items() if now-t<self.lifetime}
            def observe(self,address,atype,transport,frames):
                key=(address.lower(),atype,transport)
                fields=self.live(key);self.entries.pop(key,None)
                frames=[f for f in frames if f[0] in EVIDENCE_TYPES]
                for kind in (8,9):
                    new={f for f in frames if f[0]==kind};old={f for f in fields if f[0]==kind}
                    if new and old and new!=old:
                        fields={};break
                for f in frames: fields[f]=self.clock()
                fields=dict(sorted(fields.items(),key=lambda item:item[1])[-64:])
                self.entries[key]=fields
                while len(self.entries)>self.capacity: del self.entries[next(iter(self.entries))]
                return rules.classify(tuple(fields),address,atype)
            def reasons(self,address,atype,transport):
                key=(address.lower(),atype,transport)
                return rules.classify(tuple(self.live(key)) if key in self.entries else (),address,atype)
        fields=[ad(9,'LE-WH-CH720N'),ad(8,'LE-WH'),ad(9,'Novel Sensor'),ad(9,'BYD Key'),ad(9,'Tesla Powerwall'),
                ad(9,'Sony BRAVIA'),ad(255,bytes.fromhex('4c001005')),ad(255,bytes.fromhex('4c000215')+bytes(21)),
                ad(255,b'\x75\x00\x01'),ad(255,bytes.fromhex('2d0104000202b03108')+bytes(13)),
                ad(255,bytes.fromhex('2d011300')+bytes(15)),ad(3,b'\x82\xfd'),ad(3,b'\x48\xfe'),sd(0xfcf1),
                sd(0xfe2c,bytes.fromhex('003001020311013364e4ff')),sd(0x1853),ad(0x19,b'\x40\x00'),
                ad(255,b'\xc4\x00'),ad(1,b'\x06'),ad(0x0a,b'\x04'),b'']
        identities=[(f'ce:00:00:00:00:0{n}',atype,kind) for n in range(3) for atype in ('random','public')
                    for kind in ('BLE','BTC')]+[('94:8b:c1:00:00:01','public','BLE'),('0c:29:8f:00:00:01','public','BTC')]
        for seed in range(4):
            rng=random.Random(seed)
            self.now=0
            cached=AdvertisementEvidence(rules,clock=lambda:self.now,capacity=6,lifetime=10)
            fresh=Fresh(lambda:self.now,6,10)
            for step in range(1500):
                self.now+=rng.choice((0,0.1,0.5,2,5,11))
                identity=rng.choice(identities)
                if rng.random()<0.35:
                    self.assertEqual(cached.reasons(*identity),fresh.reasons(*identity),(seed,step))
                    continue
                raw=b''.join(rng.sample(fields,rng.randint(0,4)))
                if rng.random()<0.05:   # payload churn: exceed the per-identity field bound
                    raw=b''.join(ad(255,b'\x4c\x00'+rng.randbytes(3)) for _ in range(70))
                frames=ad_frames(raw)
                self.assertEqual(cached.observe(*identity,frames),fresh.observe(*identity,frames),(seed,step))
            self.assertLess(cached.classifications,1500)

    def test_evidence_types_are_exactly_the_ad_types_the_rules_read(self):
        """Fields of other AD types are not cached. If a rule starts reading a new
        AD type without adding it to EVIDENCE_TYPES, the cache would silently
        drop that evidence; this fails instead."""
        import uuid
        rules=NoveltyRules()
        wide=uuid.UUID('00000211-b2d1-43f0-9b88-960cebf8b91e').bytes[::-1]
        apple16=sorted(IDS['APPLE_SIG_UUID16S'])[0]
        apple128=uuid.UUID(next(v for v in sorted(IDS['APPLE_CLUES_UUIDS']) if len(v)==36 and 'x' not in v)).bytes[::-1]
        # Every shape of payload some rule accepts, offered under every AD type.
        payloads=[b'AirPods Pro',b'LE-WH-CH720N',bytes.fromhex('4c001005'),b'\x75\x00\x01',
                  bytes.fromhex('2d0104000202b03108')+bytes(13),
                  b'\x48\xfe',(0xfe48).to_bytes(4,'little'),wide,b'\xf1\xfc',b'\xf1\xfc\x00',
                  apple16.to_bytes(2,'little'),apple16.to_bytes(4,'little'),apple128,b'\x40\x00']
        company=(255,b'\xc4\x00')   # phone Appearance needs a phone company beside it
        self.assertFalse(rules.classify((company,),ADDRESS,'random'))
        read=set()
        for kind in range(256):
            for payload in payloads:
                frames=((kind,payload),company)
                if rules.classify(frames,ADDRESS,'random'):
                    read.add(kind)
                    # ...and the cache must carry that same field through.
                    self.assertTrue(self.cache.observe(ADDRESS,'random','BLE',frames),hex(kind))
                    self.cache.entries.clear()
        self.assertEqual(read,set(EVIDENCE_TYPES))

    def test_bounded_cache(self):
        for n in range(3):
            self.cache.observe(f'ce:00:00:00:00:0{n}','random','BLE',ad_frames(ad(9,'Bose SL Flex SE 2')))
        self.assertEqual(len(self.cache.entries),2)
        self.assertFalse(self.cache.reasons('ce:00:00:00:00:00','random','BLE'))



class RegistryTests(unittest.TestCase):
    def test_import_does_not_confuse_uuid_placeholder_with_integer_literal(self):
        from novelty.import_dm_bt_rules import parse_sets
        self.assertEqual(parse_sets('val TEST: Set<String> = setOf("4f86000x-943b-49ef-bed4-2f730304427a", "fd44")'),
                         {'TEST':['4f86000x-943b-49ef-bed4-2f730304427a','fd44']})
        self.assertEqual(parse_sets('val TEST = setOf(0x004c, 0x0075)'),{'TEST':[76,117]})

    def test_clues_wildcard_uuids_match_any_hex_digit_in_the_placeholder(self):
        """CLUES writes a wildcard hex digit as a lowercase x ("4f86000x-...")."""
        import uuid
        rules=NoveltyRules()
        wildcards=[(vendor,value) for vendor in ('APPLE','SAMSUNG')
                   for value in IDS[vendor+'_CLUES_UUIDS'] if 'x' in value]
        self.assertTrue(wildcards)
        for vendor,value in wildcards:
            for digit in '059af':
                concrete=value.replace('x',digit)
                with self.subTest(vendor=vendor,uuid=concrete):
                    raw=ad(7,uuid.UUID(concrete).bytes[::-1])
                    self.assertIn(vendor,rules.classify(ad_frames(raw),ADDRESS,'random'))
            # The placeholder widens one digit only, not the rest of the UUID.
            position=value.index('x')
            other=position+1 if value[position+1]!='-' else position+2
            changed=value[:other]+('0' if value[other]!='0' else '1')+value[other+1:]
            raw=ad(7,uuid.UUID(changed.replace('x','0')).bytes[::-1])
            self.assertNotIn(vendor,rules.classify(ad_frames(raw),ADDRESS,'random'))

    def test_every_exact_reviewed_vendor_uuid_identifies_vendor(self):
        import uuid
        rules=NoveltyRules()
        for vendor in ('APPLE','SAMSUNG'):
            self.assertTrue(IDS[vendor+'_CLUES_UUIDS'])
            for value in IDS[vendor+'_CLUES_UUIDS']:
                if 'x' in value: continue  # Preserve source entries; placeholders are not wildcard rules.
                if len(value)==4: raw=ad(3,int(value,16).to_bytes(2,'little'))
                else: raw=ad(7,uuid.UUID(value).bytes[::-1])
                with self.subTest(vendor=vendor,uuid=value):
                    self.assertIn(vendor,rules.classify(ad_frames(raw),ADDRESS,'random'))


class PrivateMetadataSeparationTests(unittest.TestCase):
    """Analysis/metadata/private is a separate private repository. Nothing derived
    from it may be committed to this (public) one; a capture node gets it by scp."""

    def test_importer_splits_private_nameprint_rules_out_of_the_public_snapshot(self):
        from novelty.import_dm_bt_rules import nameprint_rows, split_names
        with tempfile.TemporaryDirectory() as d:
            public_csv=Path(d)/'NAMEPRINT_UNIQUE_DB.csv'
            private_csv=Path(d)/'NAMEPRINT_UNIQUE_DB_private.csv'
            public_csv.write_text('"Public speaker","^PubSpk-[0-9]{4}$"\n"Shared phone","^Shared Phone$"\n')
            private_csv.write_text('"Private speaker","^PrivSpk-[0-9]{4}$"\n"Shared phone","^Shared Phone$"\n'
                                   '"Private earbuds, legacy escaping","^Priv\\\\+Buds$"\n')
            manifest={'research_date':'x','held':{'private':'detail'},'categories':{
                'AUDIO':[{'pattern':'^PubSpk-[0-9]{4}$','source':'Public speaker'},
                         {'pattern':'^PrivSpk-[0-9]{4}$','source':'Private speaker'},
                         {'pattern':'^Priv\\+Buds$','source':'reworded description'},
                         {'pattern':'^Generic (?:Family)$','source':'Bounded advertising-name family'}],
                'ANDROID':[{'pattern':'^Shared Phone$','source':'Shared phone'}]}}
            public,private=split_names(manifest,nameprint_rows([public_csv]),nameprint_rows([private_csv]))
        self.assertEqual([r['pattern'] for r in public['categories']['AUDIO']],
                         ['^PubSpk-[0-9]{4}$','^Generic (?:Family)$'])
        self.assertEqual([r['pattern'] for r in private['categories']['AUDIO']],
                         ['^PrivSpk-[0-9]{4}$','^Priv\\+Buds$'])
        # A rule that is also a public NamePrint stays public.
        self.assertEqual(len(public['categories']['ANDROID']),1)
        self.assertEqual(private['categories']['ANDROID'],[])
        # DM BT's "held" notes quote private NamePrint rows; neither output carries them.
        self.assertNotIn('held',public)
        self.assertNotIn('held',private)

    def test_importer_refuses_to_run_without_the_private_nameprints(self):
        from novelty.import_dm_bt_rules import export
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                export(d,Path(d)/'out',metadata=d,private_dir=Path(d)/'missing')
            self.assertFalse((Path(d)/'out').exists())

    @unittest.skipUnless(HAVE_PRIVATE_NAMEPRINTS, 'private NamePrints are not installed in Analysis/metadata/private')
    def test_committed_public_snapshot_contains_no_private_nameprint_rule(self):
        from novelty.import_dm_bt_rules import nameprint_rows, split_names
        snapshot=json.loads((Path(__file__).resolve().parents[1]/'novelty/data/names.json').read_text())
        self.assertNotIn('held',snapshot)
        _,private=split_names(snapshot,nameprint_rows(sorted(METADATA.glob('NAMEPRINT_*.csv'))),
                              nameprint_rows(sorted(PRIVATE_DIR.glob('NAMEPRINT_*.csv'))))
        leaked=[row['pattern'] for rows in private['categories'].values() for row in rows]
        self.assertEqual(leaked,[],'private NamePrint rules are committed in Scripts/novelty/data/names.json')

    def test_public_snapshot_text_never_points_into_private_metadata(self):
        data=Path(__file__).resolve().parents[1]/'novelty/data'
        for name in ('names.json','identifiers.json','provenance.json'):
            with self.subTest(file=name):
                self.assertNotIn('metadata/private',(data/name).read_text())


if __name__=='__main__': unittest.main()
