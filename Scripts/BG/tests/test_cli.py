########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Unit tests for the Better_Getter.py command-line interface.

Covers argparse behavior (subprocess) plus the post-argparse main() flow
behavior (in-process with mocked SniffleHW). Exercising main() in-process
needs the same MockHW the helper-tests use so the script doesn't try to
open /dev/cu.usbserial-* or talk to a non-existent sniffer dongle.

CLI surface under test:

    -s --serport      sniffer serial port (default None → auto-detect)
    -c --advchan      37 | 38 | 39
    -b --bdaddr       target BDADDR (required for any connection attempt)
    -l --longrange    use coded PHY for primary advertising
    -P --public       BDADDR is public (else random)
    -o --output       PCAP output file
    -q --quiet        suppress empty-packet prints
    -2 --attempt-2M-PHY-update   try negotiating 2M PHY
    -A --skip-apple   bail on Apple Company ID
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

BG_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Subprocess-based — argparse failures + --help
# ---------------------------------------------------------------------------
def _run_bg(*args, expect_success=False, timeout=10):
    """Run Better_Getter.py as a subprocess from Scripts/BG/ (mimicking how
    the launcher invokes it). Returns CompletedProcess."""
    result = subprocess.run(
        [sys.executable, "Better_Getter.py", *args],
        cwd=str(BG_DIR), capture_output=True, text=True, timeout=timeout,
    )
    if expect_success and result.returncode != 0:
        raise AssertionError(
            f"Better_Getter.py failed (exit {result.returncode}):\n"
            f"args: {args}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


class TestHelpOutput:
    def test_help_succeeds_and_lists_every_flag(self):
        result = _run_bg("--help", expect_success=True)
        # argparse prints the program description + each flag.
        assert "Code to enumerate public GATT information" in result.stdout
        # Pin every documented flag — defends against accidental removal.
        for flag in ["-s", "--serport", "-c", "--advchan", "-b", "--bdaddr",
                      "-l", "--longrange", "-P", "--public",
                      "-o", "--output", "-q", "--quiet",
                      "-2", "--attempt-2M-PHY-update", "-A", "--skip-apple"]:
            assert flag in result.stdout, f"flag {flag!r} missing from --help"

    def test_short_h_is_alias_for_help(self):
        result = _run_bg("-h", expect_success=True)
        assert "Code to enumerate public GATT information" in result.stdout


class TestArgparseRejection:
    @pytest.mark.parametrize("advchan", ["40", "0", "36", "abc"])
    def test_invalid_advchan_rejected(self, advchan):
        # argparse `choices=[37, 38, 39]` should reject these before
        # SniffleHW is ever called — exit code 2 from argparse.
        result = _run_bg("-c", advchan, "-b", "ca:fe:13:37:00:01")
        assert result.returncode == 2
        assert "invalid choice" in result.stderr or "argument -c" in result.stderr

    @pytest.mark.parametrize("advchan", ["37", "38", "39"])
    def test_valid_advchan_passes_argparse(self, advchan):
        # Argparse-OK; subsequently exits because there's no sniffer
        # attached on this test host. We don't care HOW it fails — only
        # that it gets past argparse (exit code != 2 from argparse,
        # though it may exit nonzero for IOError).
        result = _run_bg("-c", advchan, "-b", "ca:fe:13:37:00:01",
                          "-s", "/dev/nonexistent-test-port")
        assert result.returncode != 2

    def test_unknown_flag_rejected(self):
        result = _run_bg("--nonexistent-flag", "-b", "ca:fe:13:37:00:01")
        assert result.returncode == 2
        assert "unrecognized arguments" in result.stderr or "--nonexistent" in result.stderr


# ---------------------------------------------------------------------------
# In-process — parse args + drive main() with a mocked SniffleHW
# ---------------------------------------------------------------------------
@pytest.fixture
def patched_main(monkeypatch, clean_globals, mock_hw):
    """Patch sniffle.sniffle_hw.SniffleHW (and the BG_Helper_All
    re-exported alias) plus PcapBleWriter so that running Better_Getter's
    main() in-process never tries to open a serial port or write a real
    pcap. Returns the imported Better_Getter module with the patches in
    place; tests then set `sys.argv` and call `bg.main()`."""
    import importlib
    import Better_Getter as bg
    importlib.reload(bg)

    class _StubPcwriter:
        def __init__(self, path):
            self.path = path
            self.packets = []
        def write_packet_message(self, pkt):
            self.packets.append(pkt)

    # SniffleHW shows up in both the BG_Helper_All star-import surface and
    # the bg module directly. Replace both.
    sniffle_hw_factory = lambda *a, **kw: mock_hw  # noqa: E731
    monkeypatch.setattr(bg, "SniffleHW", sniffle_hw_factory, raising=False)
    monkeypatch.setattr(bg, "PcapBleWriter", _StubPcwriter, raising=False)

    # Make hw.recv_and_decode() raise KeyboardInterrupt on its first call
    # so main()'s `while True` loop exits cleanly after we've completed
    # all the setup work. send_LL_TERMINATE_IND then runs in the except
    # branch — record that the call happened.
    def _kbint():
        raise KeyboardInterrupt
    mock_hw.recv_and_decode = _kbint

    return bg


def _set_argv(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["Better_Getter.py", *args])


class TestMainBDADDRValidation:
    def test_missing_bdaddr_prints_error_and_returns(
            self, patched_main, monkeypatch, capsys):
        # No -b flag → main() prints "Must specify target BDADDR address"
        # and returns without entering the recv loop.
        _set_argv(monkeypatch)
        patched_main.main()       # should NOT raise
        captured = capsys.readouterr()
        assert "Must specify target BDADDR address" in captured.err

    @pytest.mark.parametrize("bad_bdaddr", [
        "not-a-bdaddr",
        "ca:fe:13:37:00",          # 5 bytes
        "ca:fe:13:37:00:01:02",    # 7 bytes
        "GG:HH:II:JJ:KK:LL",       # non-hex
        "",
    ])
    def test_invalid_bdaddr_prints_error(
            self, patched_main, monkeypatch, capsys, bad_bdaddr):
        _set_argv(monkeypatch, "-b", bad_bdaddr)
        # The function should print the error and return without raising
        # (except for the empty string case where bool(args.bdaddr) is
        # False → "Must specify target BDADDR address" instead).
        patched_main.main()
        captured = capsys.readouterr()
        if bad_bdaddr == "":
            assert "Must specify target BDADDR address" in captured.err
        else:
            assert "BDADDR must be 6 colon-separated hex bytes" in captured.err

    def test_valid_bdaddr_lowercase_accepted(
            self, patched_main, monkeypatch, mock_hw):
        _set_argv(monkeypatch, "-b", "ca:fe:13:37:00:01")
        with pytest.raises(SystemExit) as exc:
            patched_main.main()
        # main()'s KeyboardInterrupt branch calls exit(-1) after sending
        # LL_TERMINATE_IND.
        assert exc.value.code == -1
        # The MAC command should have fired with the BDADDR reversed.
        assert mock_hw.mac_calls
        bdaddr_bytes, is_random = mock_hw.mac_calls[0]
        assert bdaddr_bytes == (0x01, 0x00, 0x37, 0x13, 0xfe, 0xca)
        assert is_random is False  # cmd_mac always gets False per BG code

    def test_valid_bdaddr_uppercase_accepted(
            self, patched_main, monkeypatch, mock_hw):
        _set_argv(monkeypatch, "-b", "CA:FE:13:37:00:01")
        with pytest.raises(SystemExit):
            patched_main.main()
        # Uppercase should parse the same way.
        bdaddr_bytes, _ = mock_hw.mac_calls[0]
        assert bdaddr_bytes == (0x01, 0x00, 0x37, 0x13, 0xfe, 0xca)


class TestMainFlagToggles:
    """Verify that each CLI flag actually flips its corresponding entry
    in the `globals` module after main() finishes."""

    def test_quiet_flag_sets_verbose_false(
            self, patched_main, monkeypatch, clean_globals):
        _set_argv(monkeypatch, "-b", "ca:fe:13:37:00:01", "-q")
        with pytest.raises(SystemExit):
            patched_main.main()
        assert clean_globals.verbose is False

    def test_no_quiet_leaves_verbose_true(
            self, patched_main, monkeypatch, clean_globals):
        _set_argv(monkeypatch, "-b", "ca:fe:13:37:00:01")
        with pytest.raises(SystemExit):
            patched_main.main()
        assert clean_globals.verbose is True

    def test_attempt_2M_PHY_update_flag_sets_global_and_supported_PHYs(
            self, patched_main, monkeypatch, clean_globals):
        _set_argv(monkeypatch, "-b", "ca:fe:13:37:00:01", "-2")
        with pytest.raises(SystemExit):
            patched_main.main()
        assert clean_globals.attempt_2M_PHY_update is True
        # When -2 is passed, supported_PHYs gets set to 0x2 (LE 2M).
        assert clean_globals.current_ll_ctrl_state.supported_PHYs == 0x2

    def test_no_2M_flag_leaves_supported_PHYs_at_1M(
            self, patched_main, monkeypatch, clean_globals):
        _set_argv(monkeypatch, "-b", "ca:fe:13:37:00:01")
        with pytest.raises(SystemExit):
            patched_main.main()
        assert clean_globals.attempt_2M_PHY_update is False
        assert clean_globals.current_ll_ctrl_state.supported_PHYs == 0x1

    def test_skip_apple_flag_sets_global(
            self, patched_main, monkeypatch, clean_globals):
        _set_argv(monkeypatch, "-b", "ca:fe:13:37:00:01", "-A")
        with pytest.raises(SystemExit):
            patched_main.main()
        assert clean_globals.skip_apple is True

    def test_public_flag_records_target_as_public(
            self, patched_main, monkeypatch, clean_globals):
        _set_argv(monkeypatch, "-b", "ca:fe:13:37:00:01", "-P")
        with pytest.raises(SystemExit):
            patched_main.main()
        assert clean_globals.target_bdaddr_type_public is True

    def test_no_public_records_target_as_random(
            self, patched_main, monkeypatch, clean_globals):
        _set_argv(monkeypatch, "-b", "ca:fe:13:37:00:01")
        with pytest.raises(SystemExit):
            patched_main.main()
        assert clean_globals.target_bdaddr_type_public is False

    def test_target_bdaddr_stored_in_globals(
            self, patched_main, monkeypatch, clean_globals):
        _set_argv(monkeypatch, "-b", "ca:fe:13:37:00:01")
        with pytest.raises(SystemExit):
            patched_main.main()
        assert clean_globals.target_bdaddr == "ca:fe:13:37:00:01"


class TestOutputFlag:
    def test_output_flag_creates_pcap_writer(
            self, patched_main, monkeypatch, clean_globals, tmp_path):
        out_path = str(tmp_path / "test.pcap")
        _set_argv(monkeypatch, "-b", "ca:fe:13:37:00:01", "-o", out_path)
        with pytest.raises(SystemExit):
            patched_main.main()
        # globals.pcwriter is our _StubPcwriter; verify the path was set.
        assert clean_globals.pcwriter is not None
        assert clean_globals.pcwriter.path == out_path
        # At least one packet (the synthetic CONNECT_IND) was written.
        assert len(clean_globals.pcwriter.packets) >= 1

    def test_no_output_flag_leaves_pcwriter_none(
            self, patched_main, monkeypatch, clean_globals):
        _set_argv(monkeypatch, "-b", "ca:fe:13:37:00:01")
        with pytest.raises(SystemExit):
            patched_main.main()
        assert clean_globals.pcwriter is None


class TestAdvchanWiring:
    """Verify -c gets routed to cmd_chan_aa_phy on the sniffer hardware."""

    @pytest.mark.parametrize("chan", [37, 38, 39])
    def test_advchan_passed_to_hw(
            self, patched_main, monkeypatch, clean_globals, mock_hw, chan):
        recorded = []
        mock_hw.cmd_chan_aa_phy = lambda c, aa, phy: recorded.append((c, aa, phy))

        _set_argv(monkeypatch, "-b", "ca:fe:13:37:00:01", "-c", str(chan))
        with pytest.raises(SystemExit):
            patched_main.main()
        assert recorded[0][0] == chan


class TestLongRangeFlag:
    def test_longrange_flag_sets_coded_phy_in_chan_aa_phy(
            self, patched_main, monkeypatch, mock_hw):
        recorded = []
        mock_hw.cmd_chan_aa_phy = lambda c, aa, phy: recorded.append((c, aa, phy))

        _set_argv(monkeypatch, "-b", "ca:fe:13:37:00:01", "-l")
        with pytest.raises(SystemExit):
            patched_main.main()
        # cmd_chan_aa_phy(args.advchan, BLE_ADV_AA, 2 if args.longrange else 0)
        assert recorded[0][2] == 2

    def test_no_longrange_uses_phy_0(
            self, patched_main, monkeypatch, mock_hw):
        recorded = []
        mock_hw.cmd_chan_aa_phy = lambda c, aa, phy: recorded.append((c, aa, phy))

        _set_argv(monkeypatch, "-b", "ca:fe:13:37:00:01")
        with pytest.raises(SystemExit):
            patched_main.main()
        assert recorded[0][2] == 0


# ---------------------------------------------------------------------------
# Combination smoke tests
# ---------------------------------------------------------------------------
class TestCombinations:
    """The launcher invokes BG with combinations like `-q -s=… -o=… -b=… -P -2`.
    Confirm a few representative combinations all parse + execute cleanly."""

    def test_launcher_style_public_2M_combo(
            self, patched_main, monkeypatch, clean_globals, tmp_path):
        # This is exactly the shape CAL.log shows for a public BLE target.
        out_path = str(tmp_path / "out.pcap")
        _set_argv(monkeypatch,
                  "-q",
                  "-s", "/dev/ignored-by-mock",
                  "-o", out_path,
                  "-b", "6c:4a:85:2c:c3:a9",
                  "-P", "-2")
        with pytest.raises(SystemExit):
            patched_main.main()
        assert clean_globals.verbose is False
        assert clean_globals.target_bdaddr == "6c:4a:85:2c:c3:a9"
        assert clean_globals.target_bdaddr_type_public is True
        assert clean_globals.attempt_2M_PHY_update is True
        assert clean_globals.current_ll_ctrl_state.supported_PHYs == 0x2
        assert clean_globals.pcwriter is not None

    def test_launcher_style_random_combo(
            self, patched_main, monkeypatch, clean_globals, tmp_path):
        out_path = str(tmp_path / "out.pcap")
        _set_argv(monkeypatch,
                  "-q",
                  "-s", "/dev/ignored",
                  "-o", out_path,
                  "-b", "ca:fe:13:37:00:01",
                  "-2")
        with pytest.raises(SystemExit):
            patched_main.main()
        assert clean_globals.target_bdaddr_type_public is False
        assert clean_globals.attempt_2M_PHY_update is True

    def test_all_boolean_flags_enabled_simultaneously(
            self, patched_main, monkeypatch, clean_globals):
        _set_argv(monkeypatch,
                  "-b", "ca:fe:13:37:00:01",
                  "-l", "-P", "-q", "-2", "-A")
        with pytest.raises(SystemExit):
            patched_main.main()
        assert clean_globals.verbose is False
        assert clean_globals.attempt_2M_PHY_update is True
        assert clean_globals.skip_apple is True
        assert clean_globals.target_bdaddr_type_public is True

    def test_no_flags_at_all_uses_defaults(
            self, patched_main, monkeypatch, clean_globals):
        _set_argv(monkeypatch, "-b", "ca:fe:13:37:00:01")
        with pytest.raises(SystemExit):
            patched_main.main()
        assert clean_globals.verbose is True
        assert clean_globals.attempt_2M_PHY_update is False
        assert clean_globals.skip_apple is False
        assert clean_globals.target_bdaddr_type_public is False
        assert clean_globals.pcwriter is None
