"""Host tuning for a small capture node: only where it applies, and only once."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "manage_capture_host_tuning.py"
SPEC = importlib.util.spec_from_file_location("manage_capture_host_tuning", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

# The shape of the main.conf that the bluez package installs.
MAIN_CONF = (
    "[General]\n"
    "#Name = BlueZ\n"
    "\n"
    "[BR]\n"
    "#PageScanInterval=\n"
    "\n"
    "[LE]\n"
    "# BlueZ default values are used when it's not set here.\n"
    "#ScanIntervalSuspend=\n"
    "#ScanWindowSuspend=\n"
    "\n"
    "#ScanIntervalDiscovery=\n"
    "#ScanWindowDiscovery=\n"
    "\n"
    "[Policy]\n"
    "AutoEnable=true\n"
)
SWAP_CONF = (
    "# /etc/dphys-swapfile - user settings for dphys-swapfile package\n"
    "#CONF_SWAPFILE=/var/swap\n"
    "CONF_SWAPSIZE=200\n"
    "#CONF_MAXSWAP=2048\n"
)
SCAN = MODULE.LE_DISCOVERY_SCAN


def test_scan_settings_go_after_their_commented_examples_and_nothing_else_moves():
    result = MODULE.set_section_keys(MAIN_CONF, "LE", SCAN)
    assert ("#ScanIntervalDiscovery=\nScanIntervalDiscovery=480\n"
            "#ScanWindowDiscovery=\nScanWindowDiscovery=144\n\n[Policy]\n") in result
    assert [line for line in result.splitlines() if "Discovery=4" not in line and "Discovery=1" not in line] \
        == MAIN_CONF.splitlines()
    assert MODULE.set_section_keys(result, "LE", SCAN) == result


def test_other_values_are_replaced_only_in_the_le_section():
    original = ("[BR]\nScanIntervalDiscovery=1\n[LE]\nScanIntervalDiscovery = 96\n"
                "ScanWindowDiscovery=96\n[GATT]\nScanWindowDiscovery=2\n")
    assert MODULE.set_section_keys(original, "LE", SCAN) == (
        "[BR]\nScanIntervalDiscovery=1\n[LE]\nScanIntervalDiscovery=480\n"
        "ScanWindowDiscovery=144\n[GATT]\nScanWindowDiscovery=2\n")


def test_a_bare_or_missing_le_section_gets_the_settings_in_order():
    assert MODULE.set_section_keys("[General]\n[LE]\n[GATT]\n", "LE", SCAN) == (
        "[General]\n[LE]\nScanIntervalDiscovery=480\nScanWindowDiscovery=144\n[GATT]\n")
    assert MODULE.set_section_keys("[General]\nName=x", "LE", SCAN) == (
        "[General]\nName=x\n\n[LE]\nScanIntervalDiscovery=480\nScanWindowDiscovery=144\n")
    assert MODULE.set_section_keys("", "LE", SCAN) == "[LE]\nScanIntervalDiscovery=480\nScanWindowDiscovery=144\n"


@pytest.mark.parametrize("text, expect", [
    (SWAP_CONF, SWAP_CONF.replace("CONF_SWAPSIZE=200", "CONF_SWAPSIZE=2048")),
    ("#CONF_SWAPSIZE=\n#CONF_MAXSWAP=2048\n", "#CONF_SWAPSIZE=\nCONF_SWAPSIZE=2048\n#CONF_MAXSWAP=2048\n"),
    ("", "CONF_SWAPSIZE=2048\n"),
    ("CONF_SWAPSIZE=2048\n", None),
    ("CONF_SWAPSIZE=4096\n", None),                       # pi0-2: capped at 2048 by dphys-swapfile
    ("CONF_SWAPSIZE=100\nCONF_MAXSWAP=1024\n", None),     # someone chose a lower ceiling
])
def test_swap_plan(text, expect):
    assert MODULE.swap_plan(text)[0] == expect


class Host:
    """A fake host under tmp_path; records the commands the script runs."""
    def __init__(self, tmp_path, monkeypatch, cores=1, ram_mb=427, free_mb=20000,
                 main_conf=MAIN_CONF, swap_conf=SWAP_CONF, capture_running=False):
        self.main, self.swap = tmp_path / "main.conf", tmp_path / "dphys-swapfile"
        self.rpi_conf, self.rpi_dropin = tmp_path / "rpi/swap.conf", tmp_path / "rpi/swap.conf.d/80-b2p.conf"
        self.backups, self.commands = tmp_path / "backups", []
        for path, text in ((self.main, main_conf), (self.swap, swap_conf)):
            if text is not None:
                path.write_text(text)

        def run(command, **kwargs):
            self.commands.append(" ".join(command))
            return SimpleNamespace(returncode=0 if command[0] != "pgrep" or capture_running else 1)

        monkeypatch.setattr(MODULE, "MAIN_CONF", self.main)
        monkeypatch.setattr(MODULE, "SWAP_CONF", self.swap)
        monkeypatch.setattr(MODULE, "BACKUP_DIR", self.backups)
        monkeypatch.setattr(MODULE, "RPI_SWAP_CONF", self.rpi_conf)
        monkeypatch.setattr(MODULE, "RPI_SWAP_DROPIN", self.rpi_dropin)
        monkeypatch.setattr(MODULE, "ram_bytes", lambda: ram_mb * MODULE.MIB)
        monkeypatch.setattr(MODULE.os, "cpu_count", lambda: cores)
        monkeypatch.setattr(MODULE.os, "geteuid", lambda: 0)
        monkeypatch.setattr(MODULE.os, "chown", lambda *args: None)
        monkeypatch.setattr(MODULE.shutil, "which", lambda name, path=None: name)
        monkeypatch.setattr(MODULE.shutil, "disk_usage", lambda path: SimpleNamespace(free=free_mb * MODULE.MIB))
        monkeypatch.setattr(MODULE.subprocess, "run", run)
        monkeypatch.setattr(MODULE.sys, "argv", ["manage_capture_host_tuning.py"])

    def changed(self):
        return [name for name, path, text in (("main.conf", self.main, MAIN_CONF), ("swap", self.swap, SWAP_CONF))
                if path.exists() and path.read_text() != text]


def test_a_pi_zero_is_tuned_once_and_then_left_alone(tmp_path, monkeypatch, capsys):
    host = Host(tmp_path, monkeypatch)
    assert MODULE.main() == 0
    assert host.changed() == ["main.conf", "swap"]
    assert "ScanIntervalDiscovery=480\n" in host.main.read_text() and "CONF_SWAPSIZE=2048\n" in host.swap.read_text()
    assert host.commands == ["pgrep -f central_app_launcher.py", "systemctl try-restart bluetooth",
                             "dphys-swapfile swapoff", "dphys-swapfile setup", "dphys-swapfile swapon"]
    assert sorted(path.read_text() for path in host.backups.iterdir()) == sorted([MAIN_CONF, SWAP_CONF])

    host.commands.clear()
    assert MODULE.main() == 0
    assert host.commands == [] and len(list(host.backups.iterdir())) == 2
    assert "already set" in capsys.readouterr().out


def test_a_larger_host_is_not_touched(tmp_path, monkeypatch):
    host = Host(tmp_path, monkeypatch, cores=4, ram_mb=8000)
    assert MODULE.main() == 0
    assert host.changed() == [] and host.commands == [] and not host.backups.exists()


def test_check_reports_and_changes_nothing(tmp_path, monkeypatch, capsys):
    host = Host(tmp_path, monkeypatch)
    monkeypatch.setattr(MODULE.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(MODULE.sys, "argv", ["manage_capture_host_tuning.py", "--check"])
    assert MODULE.main() == 0
    assert host.changed() == [] and host.commands == [] and not host.backups.exists()
    assert capsys.readouterr().out.count("would set") == 2


def test_bluetoothd_is_not_restarted_under_a_running_capture(tmp_path, monkeypatch, capsys):
    host = Host(tmp_path, monkeypatch, capture_running=True, swap_conf=None)
    assert MODULE.main() == 0
    assert host.changed() == ["main.conf"] and host.commands == ["pgrep -f central_app_launcher.py"]
    assert "not restarted" in capsys.readouterr().out


def test_swap_is_left_alone_without_dphys_swapfile_or_disk_space(tmp_path, monkeypatch, capsys):
    host = Host(tmp_path, monkeypatch, swap_conf=None)          # e.g. a zram-based image
    assert MODULE.main() == 0
    assert host.changed() == ["main.conf"] and not any("dphys" in command for command in host.commands)
    host = Host(tmp_path, monkeypatch, free_mb=1500)
    assert MODULE.main() == 0
    assert "swap" not in host.changed() and not any("dphys" in command for command in host.commands)
    assert "left alone" in capsys.readouterr().out


def test_a_failed_swap_rebuild_is_reported_and_swap_is_turned_back_on(tmp_path, monkeypatch, capsys):
    host = Host(tmp_path, monkeypatch)

    def run(command, **kwargs):
        host.commands.append(" ".join(command))
        if command == ["dphys-swapfile", "setup"]:
            raise MODULE.subprocess.CalledProcessError(1, command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    assert MODULE.main() == 1
    assert host.commands[-3:] == ["dphys-swapfile swapoff", "dphys-swapfile setup", "dphys-swapfile swapon"]
    assert "rebuilt at the next boot" in capsys.readouterr().err


# The swap.conf that the rpi-swap package installs: everything commented out.
RPI_SWAP_CONF = "[Main]\n#Mechanism=auto\n\n[File]\n#Path=/var/swap\n#FixedSizeMiB=\n\n[Zram]\n#FixedSizeMiB=\n"


def rpi_swap_host(tmp_path, monkeypatch, conf=RPI_SWAP_CONF, **kwargs):
    host = Host(tmp_path, monkeypatch, swap_conf=None, **kwargs)
    host.rpi_conf.parent.mkdir()
    host.rpi_conf.write_text(conf)
    return host


def test_rpi_swap_gets_a_swap_file_drop_in_once_and_says_to_reboot(tmp_path, monkeypatch, capsys):
    host = rpi_swap_host(tmp_path, monkeypatch)
    assert MODULE.main() == 0
    assert host.rpi_dropin.read_text() == MODULE.RPI_SWAP_TEXT
    assert "Mechanism=swapfile\n" in MODULE.RPI_SWAP_TEXT and "FixedSizeMiB=2048\n" in MODULE.RPI_SWAP_TEXT
    assert host.rpi_conf.read_text() == RPI_SWAP_CONF                      # the package's file is not edited
    assert not any("swap" in command for command in host.commands)        # nothing is rebuilt while running
    assert "REBOOT" in capsys.readouterr().out
    before = host.rpi_dropin.stat().st_mtime_ns
    assert MODULE.main() == 0
    assert host.rpi_dropin.stat().st_mtime_ns == before and "already set" in capsys.readouterr().out


def test_rpi_swap_chosen_by_hand_or_short_of_disk_is_left_alone(tmp_path, monkeypatch, capsys):
    host = rpi_swap_host(tmp_path, monkeypatch, conf=RPI_SWAP_CONF.replace("#Mechanism=auto", "Mechanism=zram"))
    assert MODULE.main() == 0
    assert not host.rpi_dropin.exists() and "left as configured" in capsys.readouterr().out

    host = Host(tmp_path, monkeypatch, swap_conf=None)
    host.rpi_conf.write_text(RPI_SWAP_CONF)
    host.rpi_dropin.parent.mkdir()
    (host.rpi_dropin.parent / "90-mine.conf").write_text("[Main]\nMechanism = none\n")
    assert MODULE.main() == 0
    assert not host.rpi_dropin.exists() and "90-mine.conf" in capsys.readouterr().out
    (host.rpi_dropin.parent / "90-mine.conf").unlink()

    host = Host(tmp_path, monkeypatch, swap_conf=None, free_mb=2500)
    assert MODULE.main() == 0
    assert not host.rpi_dropin.exists() and "left alone" in capsys.readouterr().out

    host = Host(tmp_path, monkeypatch, swap_conf=None, ram_mb=8000, cores=4)
    assert MODULE.main() == 0
    assert not host.rpi_dropin.exists()


def test_rpi_swap_check_only_reports(tmp_path, monkeypatch, capsys):
    host = rpi_swap_host(tmp_path, monkeypatch)
    monkeypatch.setattr(MODULE.sys, "argv", ["manage_capture_host_tuning.py", "--check"])
    assert MODULE.main() == 0
    assert not host.rpi_dropin.exists() and "would write" in capsys.readouterr().out
