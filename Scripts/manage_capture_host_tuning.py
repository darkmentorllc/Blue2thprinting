#!/usr/bin/env python3
"""Give a small capture host the two settings a Raspberry Pi Zero needs.

* A single-core host cannot keep up with LE discovery scanning all the time, so
  BlueZ is told to scan 90 ms in every 300 ms (/etc/bluetooth/main.conf, [LE]).
* A host with less than 1 GB of RAM whose swap file is managed by
  dphys-swapfile gets a 2 GB swap file.

Each is skipped where it does not apply and left alone where it is already in
place. docs/Capture.md has the reasons. --check reports without changing anything.
"""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


MAIN_CONF = Path("/etc/bluetooth/main.conf")
SWAP_CONF = Path("/etc/dphys-swapfile")
BACKUP_DIR = Path("/var/backups/blue2thprinting")

# Units of 0.625 ms: scan for 90 ms in every 300 ms.
LE_DISCOVERY_SCAN = {"ScanIntervalDiscovery": 480, "ScanWindowDiscovery": 144}
SWAP_MB = 2048
SMALL_RAM_BYTES = 1 << 30
MIB = 1 << 20


def set_section_keys(text: str, section: str, values: dict) -> str:
    """Return key-file `text` with every key of `values` set under [section].

    A key already assigned there has its value replaced. A new key goes after
    its commented-out example if the section has one, else straight after the
    section header. The section is added at the end if the file has none.
    """
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    header = re.compile(r"^\s*\[(.+?)\]\s*$")
    start = None
    for index, line in enumerate(lines):
        match = header.match(line)
        if match and match.group(1) == section:
            start = index
            break
    if start is None:
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.append(f"[{section}]\n")
        start = len(lines) - 1
    end = next((i for i in range(start + 1, len(lines)) if header.match(lines[i])), len(lines))

    after_header = start + 1
    for key, value in values.items():
        setting = f"{key}={value}\n"
        assigned = re.compile(rf"^\s*{re.escape(key)}\s*=")
        example = re.compile(rf"^\s*#\s*{re.escape(key)}\s*=")
        live = [i for i in range(start + 1, end) if assigned.match(lines[i])]
        if live:
            for index in live:
                lines[index] = setting
            continue
        hint = next((i + 1 for i in range(start + 1, end) if example.match(lines[i])), None)
        if hint is None:
            hint = after_header
            after_header += 1
        lines.insert(hint, setting)
        end += 1
    return "".join(lines)


def shell_value(text: str, key: str):
    """The last uncommented KEY=value of a shell-style settings file, or None."""
    found = None
    for line in text.splitlines():
        match = re.match(rf"^\s*{re.escape(key)}\s*=\s*(\S*)", line)
        if match:
            found = match.group(1).strip("'\"")
    return found


def set_shell_value(text: str, key: str, value) -> str:
    """Return shell-style settings `text` with one uncommented KEY=value."""
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    setting = f"{key}={value}\n"
    assigned = re.compile(rf"^\s*{re.escape(key)}\s*=")
    live = [i for i, line in enumerate(lines) if assigned.match(line)]
    if live:
        for index in live:
            lines[index] = setting
        return "".join(lines)
    example = re.compile(rf"^\s*#\s*{re.escape(key)}\s*=")
    hint = next((i + 1 for i, line in enumerate(lines) if example.match(line)), len(lines))
    lines.insert(hint, setting)
    return "".join(lines)


def swap_plan(text: str):
    """(new /etc/dphys-swapfile text, or None to leave it alone; the reason)."""
    limit = shell_value(text, "CONF_MAXSWAP")
    if limit and limit.isdigit() and int(limit) < SWAP_MB:
        return None, f"CONF_MAXSWAP={limit} keeps swap below {SWAP_MB} MB; left as configured"
    size = shell_value(text, "CONF_SWAPSIZE")
    if size and size.isdigit() and int(size) >= SWAP_MB:
        return None, f"swap file is already set to {size} MB (dphys-swapfile caps it at {limit or 2048} MB)"
    return set_shell_value(text, "CONF_SWAPSIZE", SWAP_MB), f"CONF_SWAPSIZE={size or '(unset)'} -> {SWAP_MB}"


def dphys_swapfile():
    """Path of the dphys-swapfile tool, or None; a plain user's PATH has no sbin."""
    return shutil.which("dphys-swapfile", path=os.environ.get("PATH", "") + os.pathsep + "/usr/sbin:/sbin")


def ram_bytes() -> int:
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")


def save_backup(path: Path, original: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_DIR / f"{path.name}-{stamp}-{os.getpid()}.txt"
    backup.write_text(original)
    backup.chmod(0o600)
    return backup


def replace_file(path: Path, text: str) -> None:
    """Swap in the new contents in one step, keeping the file's mode and owner."""
    candidate = path.with_name(path.name + ".blue2thprinting-new")
    try:
        candidate.write_text(text)
        shutil.copymode(path, candidate)
        status = path.stat()
        os.chown(candidate, status.st_uid, status.st_gid)
        os.replace(candidate, path)
    finally:
        candidate.unlink(missing_ok=True)


def restart_bluetoothd() -> str:
    """Restart bluetoothd unless capture is running; say what happened."""
    if subprocess.run(["pgrep", "-f", "central_app_launcher.py"], capture_output=True).returncode == 0:
        return "capture is running, so bluetoothd was not restarted; it applies after the next reboot"
    if shutil.which("systemctl") and subprocess.run(["systemctl", "try-restart", "bluetooth"]).returncode == 0:
        return "bluetoothd restarted"
    return "restart bluetoothd or reboot for it to apply"


def tune_le_discovery_scan(check: bool) -> str:
    cores = os.cpu_count() or 1
    if cores > 1:
        return f"{cores} CPU cores; BlueZ's own scan timing left alone"
    if not MAIN_CONF.is_file():
        return f"{MAIN_CONF} not found (is the bluez package installed?); nothing changed"
    original = MAIN_CONF.read_text()
    desired = set_section_keys(original, "LE", LE_DISCOVERY_SCAN)
    wanted = ", ".join(f"{key}={value}" for key, value in LE_DISCOVERY_SCAN.items())
    if desired == original:
        return f"already set ({wanted})"
    if check:
        return f"would set {wanted} under [LE] in {MAIN_CONF}"
    backup = save_backup(MAIN_CONF, original)
    replace_file(MAIN_CONF, desired)
    return f"set {wanted} under [LE] in {MAIN_CONF} (previous file saved to {backup}); {restart_bluetoothd()}"


def tune_swap(check: bool) -> str:
    ram = ram_bytes()
    if ram >= SMALL_RAM_BYTES:
        return f"{ram // MIB} MB of RAM; swap left alone"
    tool = dphys_swapfile()
    if not SWAP_CONF.is_file() or not tool:
        return "swap is not managed by dphys-swapfile here; left alone"
    original = SWAP_CONF.read_text()
    desired, reason = swap_plan(original)
    if desired is None:
        return reason
    swapfile = Path(shell_value(original, "CONF_SWAPFILE") or "/var/swap")
    existing = swapfile.stat().st_size if swapfile.is_file() else 0
    needed = SWAP_MB * MIB - existing + 1024 * MIB
    free = shutil.disk_usage(swapfile.parent).free
    if free < needed:
        return (f"{free // MIB} MB free on the disk holding {swapfile}; a {SWAP_MB} MB swap file "
                f"wants {needed // MIB} MB free, so swap was left alone")
    if check:
        return f"would set {reason} in {SWAP_CONF} and rebuild {swapfile}"
    backup = save_backup(SWAP_CONF, original)
    replace_file(SWAP_CONF, desired)
    try:
        for step in ("swapoff", "setup", "swapon"):
            subprocess.run([tool, step], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        subprocess.run([tool, "swapon"], capture_output=True)
        raise RuntimeError(f"{SWAP_CONF} now says {SWAP_MB} MB (previous file saved to {backup}) but the swap "
                           f"file could not be rebuilt now ({exc}); it is rebuilt at the next boot") from exc
    return f"set {reason} in {SWAP_CONF} (previous file saved to {backup}) and rebuilt {swapfile}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report what would change and change nothing")
    args = parser.parse_args()
    if not args.check and os.geteuid() != 0:
        raise SystemExit("Run this script as root (or with --check)")
    failed = False
    for label, tune in (("LE discovery scanning", tune_le_discovery_scan), ("Swap", tune_swap)):
        try:
            print(f"  {label}: {tune(args.check)}")
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"  {label}: FAILED: {exc}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
