"""The low-memory BTIDALPOOL export must keep the ordinary BTIDES result."""

import json

import pytest


@pytest.mark.parametrize("filters", [
    ("--bdaddr", "AA:BB:CC:11:22:01"),
    ("--bdaddr", "AA:BB:CC:11:22:03"),
    ("--company-regex", "Apple"),
])
def test_server_export_matches_regular_export(run_tme, tmp_path, filters):
    ordinary = tmp_path / "ordinary.btides"
    server = tmp_path / "server.btides"
    run_tme(*filters, "--quiet-print", "--output", str(ordinary))
    run_tme(*filters, "--quiet-print", "--server-export", "--output", str(server))
    regular_data = json.loads(ordinary.read_text())
    assert regular_data, "fixture must exercise a nonempty export"
    assert json.loads(server.read_text()) == regular_data


def test_server_export_requires_quiet_output(run_tme):
    result = run_tme("--server-export", "--bdaddr", "AA:BB:CC:11:22:01",
                     expect_success=False)
    assert result.returncode != 0
    assert "requires --quiet-print and --output" in result.stderr
