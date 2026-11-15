"""GATT value rules must keep chip and module evidence separate."""

import sys
from pathlib import Path

import pytest

ANALYSIS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ANALYSIS_DIR))

import TME.TME_glob as glob  # noqa: E402
import TME.TME_metadata as metadata  # noqa: E402
from TME.TME_import import import_GATT_value_fingerprints  # noqa: E402


def test_rule_matching_respects_uuid_and_address_type(monkeypatch):
    import_GATT_value_fingerprints()

    def fake_query(query, values):
        assert 'v.operation = 11' in query
        assert values == ('aa:bb:cc:00:00:01', 1)
        return [
            ('00002A24-0000-1000-8000-00805F9B34FB', 10, b'CC2640'),
            ('2a28', 12, b'nRF52-SDK17.02'),
            ('2a24', 14, b'BM71'),
            ('2a24', 16, b'FSC-BT836'),
            ('2a29', 18, b'CC2640'),  # same text, wrong UUID
            (None, 20, b'QCC3040'),  # explicitly allowed unmapped value
            (None, 22, b'BM71'),  # module rule requires its UUID
            ('2a24', 24, b'RN4020-junk'),
        ]

    monkeypatch.setattr(metadata, 'execute_query', fake_query)
    matches = metadata.lookup_GATT_value_fingerprints('aa:bb:cc:00:00:01', 1)
    assert [rule['id'] for rule, _, _ in matches] == [
        'ti_cc2640', 'nordic_nrf52_sdk_17_0_2', 'microchip_bm71',
        'feasycom_fsc_bt836', 'qualcomm_qcc3040',
    ]
    assert matches[2][0]['chip'] == 'Microchip IS1871'
    assert matches[2][0]['module'] == 'Microchip BM71'
    assert matches[3][0]['chip'] == 'Realtek RTL8761 family'
    assert matches[3][0]['chip_maker'] == 'Realtek'
    assert matches[3][0]['module_maker'] == 'Feasycom'


def test_module_sections_use_module_fields(monkeypatch):
    import_GATT_value_fingerprints()
    rules = {rule['id']: rule for rule in glob.gatt_value_fingerprint_rules}
    matches = [
        (rules['microchip_bm71'], '2a24', 'BM71'),
        (rules['feasycom_fsc_bt946'], '2a24', 'FSC-BT946'),
    ]
    output = []
    monkeypatch.setattr(metadata, 'qprint', output.append)
    monkeypatch.setattr(metadata, 'vprint', lambda _value: None)
    monkeypatch.setattr(metadata, 'string_yellow_bright', lambda value: value)
    monkeypatch.setattr(glob, 'g_printed_ModulePrint_header', False)
    monkeypatch.setattr(glob, 'g_printed_ModuleMakerPrint_header', False)

    metadata.print_ModulePrint('aa:bb:cc:00:00:01', 0, matches)
    metadata.print_ModuleMakerPrint('aa:bb:cc:00:00:01', 0, matches)
    rendered = '\n'.join(output)
    assert 'ModulePrint:' in rendered
    assert 'Microchip BM71' in rendered
    assert 'Feasycom FSC-BT946' in rendered
    assert 'ModuleMakerPrint:' in rendered
    assert 'Microchip Technology' in rendered
    assert 'Feasycom' in rendered


def test_default_module_name_uses_module_sections(monkeypatch):
    output = []
    monkeypatch.setattr(metadata, 'qprint', output.append)
    monkeypatch.setattr(metadata, 'vprint', lambda _value: None)
    monkeypatch.setattr(metadata, 'string_yellow_bright', lambda value: value)
    monkeypatch.setattr(glob, 'g_printed_ModulePrint_header', False)
    monkeypatch.setattr(glob, 'g_printed_ModuleMakerPrint_header', False)
    monkeypatch.setattr(glob, 'g_printed_ChipPrint_header', False)
    def fake_nameprint(_address, _random, field):
        return {
            '2thprint_Module': 'JDY-23 serial module',
            '2thprint_Module_Maker': 'Shenzhen Jindouyun',
        }.get(field, '')
    monkeypatch.setattr(metadata, 'lookup_metadata_by_nameprint', fake_nameprint)

    metadata.print_ModulePrint('aa:bb:cc:00:00:01', 0, [])
    metadata.print_ModuleMakerPrint('aa:bb:cc:00:00:01', 0, [])
    rendered = '\n'.join(output)
    assert 'JDY-23 serial module' in rendered
    assert 'Shenzhen Jindouyun' in rendered
    assert not glob.g_printed_ChipPrint_header


def test_sdk_rules_capture_build_strings_without_chip_attribution():
    import_GATT_value_fingerprints()
    rules = {rule['id']: rule for rule in glob.gatt_value_fingerprint_rules}
    examples = [
        ('nordic_nrf52_sdk_13', '2a28', 'nRF52-SDK13.0'),
        ('nordic_nrf52_sdk_17_0_2', '2a28', 'nRF52-SDK17.02'),
        ('nordic_nrf5_sdk_build', '2a28', 'nRF5_SDK_11.0.0_89a8197'),
        ('beats_mt28_sdk_build', '2a26', 'MT2831_SDK_V1.1.0.ER44'),
        ('soundcore_release_sdk_build', '2a26', 'FW VERSION-0.0.0.0-Release-SDK_6.5.5.59'),
        ('enzytek_sdk_label', '2a26', 'SDK 2.0'),
    ]
    for rule_id, uuid, value in examples:
        assert metadata._gatt_value_matches_rule(rules[rule_id], uuid, value)
    assert 'chip' not in rules['beats_mt28_sdk_build']
    assert 'chip_maker' not in rules['beats_mt28_sdk_build']
    assert not metadata._gatt_value_matches_rule(
        rules['beats_mt28_sdk_build'], '2a24', 'MT2831_SDK_V1.1.0.ER44'
    )
    assert metadata._gatt_value_matches_rule(rules['enzytek_sdk_label'], None, 'SDK 2.0')


def test_sdkprint_combines_gatt_observation_and_ll_compatibility(monkeypatch):
    import_GATT_value_fingerprints()
    rules = {rule['id']: rule for rule in glob.gatt_value_fingerprint_rules}
    matches = [(rules['nordic_nrf52_sdk_17_0_2'], '2a28', 'nRF52-SDK17.02')]
    monkeypatch.setattr(
        metadata, 'execute_query',
        lambda query, values: [(0x0A, 0x0059, 0x0102), (0x0A, 0x0059, 0x0102)],
    )
    monkeypatch.setattr(
        metadata, 'lookup_LL_VERSION_IND_metadata',
        lambda *args: {
            'sdk_versions': ['nRF5 SDK 17.0.2', 'nRF5 SDK 17.1.0'],
            'match_quality': 'exact LL_VERSION_IND metadata match',
        },
    )
    output = []
    monkeypatch.setattr(metadata, 'qprint', output.append)
    monkeypatch.setattr(metadata, 'vprint', lambda _value: None)
    monkeypatch.setattr(metadata, 'string_yellow_bright', lambda value: value)
    monkeypatch.setattr(glob, 'g_printed_SDKPrint_header', False)

    metadata.print_SDKPrint('aa:bb:cc:00:00:01', 1, matches)
    rendered = '\n'.join(output)
    assert 'SDKPrint:' in rendered
    assert "Observed build string 'nRF52-SDK17.02' (GATT 0x2a28)" in rendered
    assert rendered.count('Compatible SDK release(s): nRF5 SDK 17.0.2') == 1
    assert 'LL_VERSION_IND 0A:0059:0102' in rendered


def test_numeric_sdk_candidate_requires_separate_chipmaker_print(monkeypatch):
    import_GATT_value_fingerprints()
    rules = {rule['id']: rule for rule in glob.gatt_value_fingerprint_rules}
    candidate = (rules['silabs_gecko_sdk_version_candidate'], '2a26', '4.5.0')
    assert metadata._gatt_value_matches_rule(*candidate)
    output = []
    monkeypatch.setattr(metadata, 'qprint', output.append)
    monkeypatch.setattr(metadata, 'vprint', lambda _value: None)
    monkeypatch.setattr(metadata, 'string_yellow_bright', lambda value: value)
    monkeypatch.setattr(glob, 'g_printed_SDKPrint_header', False)

    # A Qualcomm LL company ID is a real observed collision for this value.
    monkeypatch.setattr(metadata, 'execute_query', lambda query, values: [(10, 0x000A, 1)])
    metadata.print_SDKPrint('7e:24:11:bc:06:1b', 1, [candidate])
    assert output == []

    monkeypatch.setattr(metadata, 'execute_query', lambda query, values: [(10, 0x02FF, 1)])
    metadata.print_SDKPrint('7e:24:11:bc:06:1b', 1, [candidate])
    assert 'possible only' in '\n'.join(output)
    assert 'Firmware may use an unrelated version scheme' in '\n'.join(output)


def test_observed_bose_qualcomm_450_collision_stays_suppressed(monkeypatch):
    """Use the actual observed GATT/LL values through lookup and SDKPrint."""
    import_GATT_value_fingerprints()
    address = '7e:24:11:bc:06:1b'

    def observed_rows(query, values):
        assert values == (address, 1)
        if 'FROM GATT_characteristics_values' in query:
            return [
                ('2a29', 24, b'Bose Corporation'),
                ('2a24', 26, b'4.0.1'),
                ('2a26', 32, b'4.5.0'),
            ]
        assert 'FROM LL_VERSION_IND' in query
        return [(8, 0x000A, 11835)]  # Qualcomm controller in the observed record

    output = []
    monkeypatch.setattr(metadata, 'execute_query', observed_rows)
    monkeypatch.setattr(metadata, 'lookup_LL_VERSION_IND_metadata', lambda *args: None)
    monkeypatch.setattr(metadata, 'qprint', output.append)
    monkeypatch.setattr(metadata, 'vprint', lambda line: None)
    monkeypatch.setattr(glob, 'g_printed_SDKPrint_header', False)

    matches = metadata.lookup_GATT_value_fingerprints(address, 1)
    assert [rule['id'] for rule, _, _ in matches] == [
        'silabs_gecko_sdk_version_candidate'
    ]
    metadata.print_SDKPrint(address, 1, matches)
    assert output == []
    assert not glob.g_printed_SDKPrint_header


@pytest.mark.parametrize(
    ('other_rule_id', 'address_type', 'oui_name', 'expected'),
    [
        ('silabs_blue_gecko', 1, None, True),
        ('ti_cc2640', 1, None, False),
        ('feasycom_fsc_bt946', 1, None, False),
        (None, 0, 'Silicon Laboratories, Inc.', True),
        (None, 1, 'Silicon Laboratories, Inc.', False),
    ],
)
def test_numeric_sdk_maker_evidence_paths(
    monkeypatch, other_rule_id, address_type, oui_name, expected
):
    """A same-maker GATT print or public OUI qualifies; unrelated evidence does not."""
    import_GATT_value_fingerprints()
    rules = {rule['id']: rule for rule in glob.gatt_value_fingerprint_rules}
    matches = [(rules['silabs_gecko_sdk_version_candidate'], '2a26', '4.5.0')]
    if other_rule_id:
        matches.append((rules[other_rule_id], '2a24', rules[other_rule_id]['pattern']))
    output = []
    monkeypatch.setattr(metadata, 'ChipMaker_OUI_hash', {
        'aa:bb:cc': oui_name
    } if oui_name else {})
    monkeypatch.setattr(metadata, 'execute_query', lambda query, values: [])
    monkeypatch.setattr(metadata, 'qprint', output.append)
    monkeypatch.setattr(metadata, 'vprint', lambda line: None)
    monkeypatch.setattr(metadata, 'string_yellow_bright', lambda value: value)
    monkeypatch.setattr(glob, 'g_printed_SDKPrint_header', False)

    metadata.print_SDKPrint('aa:bb:cc:00:00:01', address_type, matches)
    rendered = '\n'.join(output)
    assert ('Silicon Labs Gecko SDK' in rendered) is expected
    assert ('Firmware may use an unrelated version scheme.' in rendered) is expected


def test_numeric_sdk_rule_rejects_wrong_uuid_and_pre_component_tags():
    import_GATT_value_fingerprints()
    rules = {rule['id']: rule for rule in glob.gatt_value_fingerprint_rules}
    candidate = rules['silabs_gecko_sdk_version_candidate']
    assert metadata._gatt_value_matches_rule(candidate, '2a26', '4.5.0')
    assert not metadata._gatt_value_matches_rule(candidate, '2a28', '4.5.0')
    assert not metadata._gatt_value_matches_rule(candidate, '2a26', '4.1.3')
    assert not metadata._gatt_value_matches_rule(candidate, '2a26', '4.5.2')


def test_suppressed_numeric_candidate_preserves_independent_ll_sdkprint(monkeypatch):
    import_GATT_value_fingerprints()
    rules = {rule['id']: rule for rule in glob.gatt_value_fingerprint_rules}
    candidate = (rules['silabs_gecko_sdk_version_candidate'], '2a26', '4.5.0')
    monkeypatch.setattr(metadata, 'execute_query', lambda query, values: [(8, 0x0059, 0x0098)])
    monkeypatch.setattr(metadata, 'lookup_LL_VERSION_IND_metadata', lambda *args: {
        'sdk_versions': ['nRF5 SDK 13.0.0', 'nRF5 SDK 13.1.0'],
        'match_quality': 'exact LL_VERSION_IND metadata match',
    })
    output = []
    monkeypatch.setattr(metadata, 'qprint', output.append)
    monkeypatch.setattr(metadata, 'string_yellow_bright', lambda value: value)
    monkeypatch.setattr(glob, 'g_printed_SDKPrint_header', False)

    metadata.print_SDKPrint('aa:bb:cc:00:00:01', 1, [candidate])
    rendered = '\n'.join(output)
    assert 'Compatible SDK release(s): nRF5 SDK 13.0.0, nRF5 SDK 13.1.0' in rendered
    assert 'Silicon Labs Gecko SDK' not in rendered


def test_explicit_sdk_archive_name_does_not_need_chipmaker_print(monkeypatch):
    import_GATT_value_fingerprints()
    rules = {rule['id']: rule for rule in glob.gatt_value_fingerprint_rules}
    match = (rules['nordic_nrf5_sdk_build'], '2a28', 'nRF5_SDK_11.0.0_89a8197')
    output = []
    monkeypatch.setattr(metadata, 'execute_query', lambda query, values: [])
    monkeypatch.setattr(metadata, 'qprint', output.append)
    monkeypatch.setattr(metadata, 'string_yellow_bright', lambda value: value)
    monkeypatch.setattr(glob, 'g_printed_SDKPrint_header', False)

    metadata.print_SDKPrint('c6:12:ac:5d:cd:d4', 1, [match])
    assert 'Nordic nRF5 SDK 11.0.0 (archive 89a8197)' in '\n'.join(output)


def test_sdkprint_omits_unknown_ll_release(monkeypatch):
    import_GATT_value_fingerprints()
    monkeypatch.setattr(
        metadata, 'execute_query',
        lambda query, values: [(0x0A, 0x0059, 0xDEAD)],
    )
    monkeypatch.setattr(
        metadata, 'lookup_LL_VERSION_IND_metadata',
        lambda *args: {
            'sdk_versions': ['Exact SDK release unknown'],
            'match_quality': 'vendor/version inference; exact FWID unknown',
        },
    )
    output = []
    monkeypatch.setattr(metadata, 'qprint', output.append)
    monkeypatch.setattr(metadata, 'vprint', lambda _value: None)
    monkeypatch.setattr(glob, 'g_printed_SDKPrint_header', False)
    metadata.print_SDKPrint('aa:bb:cc:00:00:01', 0, [])
    assert output == []
