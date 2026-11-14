#!/usr/bin/env python3
"""Install one Blue2thprinting capture boot entry without touching other cron lines."""

from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import tempfile


MARKER = "# Blue2thprinting capture (managed by setup_capture_helper_debian-based.sh)"


def reconcile_crontab(existing: str, runall_path: str) -> str:
    """Remove only this checkout's simple runall entries, then add one managed entry."""
    kept = []
    for line in existing.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        fields = content.split()
        if content == MARKER:
            continue
        if len(fields) == 2 and fields == ["@reboot", runall_path]:
            continue
        kept.append(line)
    if kept and not kept[-1].endswith("\n"):
        kept[-1] += "\n"
    return "".join(kept) + MARKER + "\n" + f"@reboot {runall_path}\n"


def read_root_crontab() -> str:
    result = subprocess.run(
        ["crontab", "-u", "root", "-l"],
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": "C"},
    )
    if result.returncode == 0:
        return result.stdout
    if result.returncode == 1 and "no crontab for root" in result.stderr.lower():
        return ""
    raise RuntimeError(f"Could not read root crontab: {result.stderr.strip()}")


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Run this script as root")
    runall = Path(__file__).resolve().parent / "runall.sh"
    if not runall.is_file():
        raise SystemExit(f"Missing capture launcher: {runall}")

    original = read_root_crontab()
    desired = reconcile_crontab(original, str(runall))
    if desired == original:
        print("Root crontab already has one managed capture entry; no change")
        return

    backup_dir = Path("/var/backups/blue2thprinting")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_dir / f"root-crontab-{stamp}-{os.getpid()}.txt"
    backup.write_text(original)
    backup.chmod(0o600)

    if read_root_crontab() != original:
        raise RuntimeError("Root crontab changed during setup; kept backup and made no change")

    with tempfile.NamedTemporaryFile("w", prefix="blue2-cron-", delete=False) as temp:
        temp.write(desired)
        candidate = Path(temp.name)
    try:
        subprocess.run(["crontab", "-u", "root", str(candidate)], check=True)
    finally:
        candidate.unlink(missing_ok=True)

    if read_root_crontab() != desired:
        raise RuntimeError(f"Root crontab verification failed; backup is {backup}")
    print(f"Installed one capture boot entry; previous crontab saved to {backup}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"capture crontab setup failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
