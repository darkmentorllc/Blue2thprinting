"""Where the LMP tool lives.

DarkFirmware_VSC_LMP finds <repo>/Logs from the path of its own binary, so the
launcher, the setup helper and the C source have to agree on where that is. It
moved out of the bluez-5.66 tree when that tree and its sdptool were removed.
"""
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "Scripts"))
import central_app_launcher as cal

SOURCE = REPO / "Scripts/DarkFirmware_VSC_LMP_src/DarkFirmware_VSC_LMP.c"
SETUP = (REPO / "setup_capture_helper_debian-based.sh").read_text()


def test_launcher_setup_and_source_agree_on_where_the_binary_is():
    binary = Path(cal.darkfirmware_lmp_path)
    assert binary == REPO / "Scripts/DarkFirmware_VSC_LMP"
    assert SOURCE.is_file()
    # The setup helper builds that file from that source, from inside Scripts/.
    build = SETUP[SETUP.rindex('cd "$BASE_PATH/Scripts"'):]
    assert ("gcc -O2 -Wall -o DarkFirmware_VSC_LMP \\\n"
            "            DarkFirmware_VSC_LMP_src/DarkFirmware_VSC_LMP.c") in build
    # The tool strips as many path components from /proc/self/exe as the binary
    # is deep below the repository root.
    stripped = re.search(r"// Strip (\d+) path components.*\n\s*for \(int i = 0; i < (\d+); i\+\+\)",
                         SOURCE.read_text())
    assert stripped, "the repo-root lookup in the C source was not found"
    assert int(stripped.group(1)) == int(stripped.group(2)) == len(binary.relative_to(REPO).parts)


def test_nothing_runs_or_builds_the_removed_sdptool():
    assert not hasattr(cal, "sdptool_enabled") and not hasattr(cal, "sdptool_exec_path")
    assert cal.btc_sdp_gatt_enabled is True
    assert "./configure" not in SETUP and "tools/sdptool" not in SETUP
    assert not [line for line in SETUP.splitlines() if re.match(r"\s*make\b", line)]
    assert not list(REPO.glob("bluez-5.66/tools/*.c"))
