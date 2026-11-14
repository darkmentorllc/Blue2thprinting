import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "manage_capture_cron.py"
SPEC = importlib.util.spec_from_file_location("manage_capture_cron", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_preserves_other_jobs_and_comments():
    runall = "/home/user/Blue2thprinting/Scripts/runall.sh"
    original = (
        "SHELL=/bin/bash\n"
        "# user note\n"
        "@daily /usr/local/bin/backup\n"
        "@reboot /opt/another-project/Scripts/runall.sh\n"
        f"@reboot {runall} && echo custom\n"
    )
    result = MODULE.reconcile_crontab(original, runall)
    assert result.startswith(original)
    assert result.endswith(MODULE.MARKER + "\n" + f"@reboot {runall}\n")


def test_replaces_only_own_duplicate_entries_and_is_idempotent():
    runall = "/home/user/Blue2thprinting/Scripts/runall.sh"
    original = (
        f"@reboot {runall}\n"
        "@hourly /usr/local/bin/check\n"
        f"@reboot    {runall}   \n"
        f"{MODULE.MARKER}\n"
    )
    result = MODULE.reconcile_crontab(original, runall)
    assert result.count(f"@reboot {runall}\n") == 1
    assert "@hourly /usr/local/bin/check\n" in result
    assert MODULE.reconcile_crontab(result, runall) == result


def test_first_install():
    runall = "/home/user/Blue2thprinting/Scripts/runall.sh"
    assert MODULE.reconcile_crontab("", runall) == (
        MODULE.MARKER + "\n" + f"@reboot {runall}\n"
    )
