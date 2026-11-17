# Novelty mode

Novelty mode was written on branch `novelty-mode`, which starts from `master` commit
`557d291d`, and was merged into `master` on 2026-11-17.
Set `novelty_mode = True` in `Scripts/central_app_launcher.py` (the default)
to skip Apple, Samsung, Android phones, reviewed vehicles/keys, and headphones /
speakers before active probing. Set it to `False` and restart the launcher to
disable all category skips. There are no separate category toggles.

The same decision applies to BLE Better Getter and BTC LMP, SDP and GATT-over-BR/EDR.
Novelty mode also passes Better Getter its own skip-Apple option (`-A`), which was
on by default before this branch: BG exits early (rc `0x0A`) when it confirms an
Apple device from the advertisement Company ID, LL_VERSION_IND or the GATT
Manufacturer Name. With novelty mode off, `-A` is not passed.

Turning it off does **not** disable personal-address exclusions, completed-target
suppression, the three-attempt limit or the ten-total-attempt ceiling. These
histories are still per launcher run, as before. The existing
covered-GATT-map/value-read staging and its intentional successful-staging retry
reset remain intact in both modes.

An attempt is a probe that was actually launched. A Better Getter run that is still
in flight when the BLE loop comes back to the same address is the same attempt, and
a pass that launched nothing (the candidate was withdrawn, or the last-moment
category check refused it) is not an attempt at all.

**Changed from `master`:** rediscovery and a rising RSSI no longer give a device its
failed attempts back. On `master` a device that BlueZ dropped and found again started
from zero, and each stronger RSSI reading took one attempt off, with only the
ten-attempt ceiling as a hard stop. Here three launched failures end it for the rest
of the launcher run.

**Removed from `master`:** the fallback queues that deprioritized devices by
`Analysis/adv_signature_priority.csv` (advertisement signatures already covered in
the database) and `Analysis/name_signature_priority.csv` (names already covered),
together with the Apple Company ID rule they shared a queue with. Those two files
and their `build_*_priority.py` scripts are still in the repository but nothing
reads them now.

## Evidence and rules

BlueZ continues to own `StartDiscovery(Transport=auto)`. A **passive Linux HCI
monitor** supplies legacy/complete extended LE advertising reports, scan responses,
and BR/EDR inquiry/EIR reports. Only the selected Realtek controller feeds the
launcher. Its index follows the existing USB-cycle resolver. Public OUIs work for
BTC and public LE addresses; random/unknown addresses never use OUI guesses.

Only an `ADV_IND` (or a connectable, undirected extended advertisement) puts an LE
device in the queue. Scan responses, `ADV_SCAN_IND`, `ADV_NONCONN_IND` and directed
advertisements are read for evidence but never admit a candidate: a scan response
also answers for devices that refuse connections, and a directed advertisement only
accepts its own peer.

An LE address is one candidate whatever address type a report gives it. Both
controllers on `pi0-2` occasionally report a random-address device as `public`
(the same iPhone, same payload, a few percent of its reports, empty scan responses
included). The launcher therefore counts the reports of each type per address,
probes with the type most of them carry, and lets evidence heard under either type
decide the skip. Without that, a skipped device came back as a second candidate
with no evidence and Better Getter was started with the wrong address type.

A packet that makes the report handler raise is logged and skipped; it does not end
discovery (which would end the launcher).

BlueZ `Device1.Name` and `UUIDs` can contain values learned through remote-name
requests, GATT or SDP. They no longer seed the queues or classification. Remote
Name Request Complete, connection events, ACL data and cached device snapshots
are ignored. Failure to open/read the monitor stops discovery rather than falling
back to those properties. The launcher must run with the existing capture-node
root privileges. The native `sockaddr_hci` binding supports the Pi's Python 3.11,
whose `socket.bind()` cannot select the monitor channel.

The reviewed DM BT snapshot is under `Scripts/novelty/data/`. `provenance.json`
records the source commit and SHA-256 of each source file. The initial source is
DM BT `6ec63335` (including the 2026-11-17 audio/key fixes). This is a portable
snapshot; the Pi does not need the Android repo, Kotlin, SQL or a network lookup.
Name rules reviewed from the **private** NamePrints are not in that snapshot; see
"Private metadata" below. The pattern counts in the table include them.

| Rule group | Included evidence |
| --- | --- |
| Apple | Public OUIs, non-iBeacon Apple MSD, reviewed SIG/CLUES UUIDs (a CLUES `x` is one wildcard hex digit) and product names. Apple-CID iBeacon alone is insufficient for the launcher; Better Getter's `-A` still exits on any Apple Company ID, iBeacon included, as it did before. |
| Samsung | Public OUIs, Samsung MSD and UUIDs, Samsung/Galaxy names and reviewed localized phone names. This preserves the broader Samsung-vendor skip as well as Android-phone rules. |
| Android | 142 reviewed name patterns; service **data** UUID FCF1 or FE50; phone Appearance plus a reviewed phone-company CID/public OUI. These two service-data policies deliberately may also skip tablets. |
| Vehicles | 216 name patterns including GM_PEPS, VM model names and confirmed Hyundai/Kia Digital Key models; bounded Tesla/Rivian CID/service rules; vehicle Appearance plus reviewed public OUIs. |
| Audio | 685 name patterns, reviewed audio companies/public OUIs/services/Appearances, exact Sony/JBL/JLab MSD prefix-and-length signatures, bounded Fast Pair model and account-data rules, and the CAS + Fast Pair service-data conjunction. |

Chinese vehicle brands remain eligible, including the previously retained Volvo,
Polestar and Lotus families. Their explicit advertising-name veto is applied
before **all** categories, so an Apple integration service cannot accidentally
undo that choice when every category is enabled. Powerwall retains the vehicle
exception; the audio non-product exclusions (TVs, watches, hearing aids, etc.)
remain in place. Such an exception does not cancel an independent Samsung-vendor
match: novelty mode enables that broad vendor rule too.

No blanket `Key`, generic Digital Key service, generic vehicle Appearance,
Sony-company-wide, Jieli-company-wide or random-address-prefix rule was added.
Solicitation UUIDs retain the existing Apple/Samsung policy but cannot qualify the
Android/vehicle/audio service-provider rules.

Advertising and scan-response fields are kept by address, address type and
transport in a bounded 4,096-entry, ten-minute cache, up to 64 fields per
identity. Only the AD types the rules read are kept. Each field expires
independently; nameless flags packets cannot keep an old name alive. A different
value for the same name type (Shortened or Complete) clears the previous identity
evidence; a Shortened Local Name in the advertisement and the Complete Local Name in
its scan response are one identity, not a rename.

The verdict is stored with the evidence and recomputed only when the evidence
changes. Classifying every report cost about 5 ms on the Pi Zero (over half its
core at 115 reports/s), and the launcher asks for the verdict again at every
scheduling step; with the stored verdict the same stream costs about 1.6 ms per
report including parsing. Compiling the name rules takes about 7 s at launcher
start, and the first sight of a new name costs about 20 ms.

There is a second category check immediately before each subprocess launch,
including after waiting for a dongle or LMP completion.

Passive capture continues normally. Novelty mode suppresses active probes, not
raw evidence logging. If a distinguishing scan response arrives after a probe
has already begun, it cannot undo that connection. Empty/non-identifying payloads
remain eligible. Fragmented/incomplete extended advertising reports are ignored
rather than guessed or combined across advertising sets. An identifying GATT
name alone never becomes a skip rule.

## Private metadata

`Analysis/metadata/private` is a separate private repository and is ignored by this
one. Nothing derived from it is committed here. The name rules are therefore split:

| File | Contents | How it reaches a capture node |
| --- | --- | --- |
| `Scripts/novelty/data/names.json` | 127 rules: the public NamePrints and the generic name families (`Android*`, `GM_PEPS_*`, Sony/Bose model families, ...) | Part of this repository |
| `Analysis/metadata/private/novelty_names.json` | 920 rules reviewed from the private NamePrints (102 Android, 4 Samsung phone, 169 vehicle, 645 audio) | **scp** from the analysis machine; never Git |
| `Analysis/metadata/private/novelty_names_GATT.json` | Advertised names, and name families, of devices already fully GATT-enumerated in the local database (see below) | **scp** from the analysis machine; never Git |

The launcher loads the private file when it is present and says so on its first
lines (`... 127 public name rules, 920 private name rules from ...`). Without it
novelty mode still runs with the public rules only. Allowed categories are
`ANDROID`, `SAMSUNG_PHONES`, `VEHICLES` and `AUDIO`; an unknown category or an
invalid pattern is a startup error. NamePrint descriptions and CLUES prose are never
classified by keyword.

To put the private rules on a capture node:

```bash
scp Analysis/metadata/private/novelty_names.json user@<pi>:Blue2thprinting/Analysis/metadata/private/
```

`import_dm_bt_rules.py` writes both files. A rule goes to the private file when its
pattern or description is a row of a private NamePrint file and is not also a row
of a public one. It refuses to run when the private NamePrints are not installed,
because it could not then tell which rules to keep out of the public file.

```bash
python3 Scripts/novelty/import_dm_bt_rules.py /path/to/XenoMetaRadar
venv/bin/python -m pytest -q Scripts/tests
```

Review the generated diff and the semantic Python port when DM BT's algorithms
change; the importer refreshes tables, not algorithm code.

`Scripts/novelty/data/identifiers.json` (OUI, Company ID, UUID and Fast Pair tables)
and the generic name families come from the DM BT repository, which is also
private, but not from `Analysis/metadata/private`. They are committed here because
novelty mode cannot run without them.

## Devices already fully GATT-enumerated

Novelty mode also skips a device that advertises a name whose GATT database has
been collected before. The names come from the local `bt2` database and are in a
second private file, `Analysis/metadata/private/novelty_names_GATT.json`, loaded at
launcher start like `novelty_names.json`. A match adds the reason `GATT_KNOWN`
(`Skipped BLE ...: novelty:GATT_KNOWN`) and applies to BLE and BR/EDR alike.

```bash
venv/bin/python Scripts/novelty/build_gatt_names.py
scp Analysis/metadata/private/novelty_names_GATT.json user@<pi>:Blue2thprinting/Analysis/metadata/private/
```

A device counts as fully enumerated when its services and characteristics were
discovered, every service that spans more than its own declaration has
characteristics, every characteristic with the Read property was answered (by a
value or by an ATT error), and at least one value was actually read. Only
advertised names are used (Complete or Shortened Local Name from LE advertising,
scan responses and BR/EDR EIR), because the decision is made before connecting. A
fully enumerated device that advertises no name cannot be skipped this way.

Where many devices share a naming scheme with a per-device identifier, one
NamePrint-style regex stands for the family instead of one entry per device, and so
also covers members that have not been enumerated. Families are inferred from every
advertised name in the database: an identifier is the rightmost run of hex digits
(`Lamp_0A1B2C3D`) or of letters and digits (`Cam 3S 4GK7QZ`), or whatever varies
between names of one length that share five characters at the same offset
(`Unit 0A:1B:2C`). A family becomes a regex only if at least 8 database names fit
it, at least 80% of them were each seen on one or two devices (a name shared by many
devices is a model name, not an identifier), at least three characters vary, the
fixed text is a usable anchor, the varying part is an identifier and not free text,
and its enumerated members do not all have different GATT databases. Everything else
stays an exact name. `--show-rejected` lists the families that were not generalized
and why.

The file's patterns and names are **case-sensitive** and are compared with the
advertised name after Unicode NFKC normalization and trimming. Names shorter than
three characters are left out (listed under `too_short`).

The builder needs nothing but the database. `Analysis/metadata/private` is ignored
by Git and is created if it is missing. `novelty_names.json` and the hand-written
families file are read from the output's directory when they are there; without
`novelty_names.json` only the public rules decide which names are left to the other
rules. Neither file's content is copied into the output. The builder refuses to
write to a place inside the repository that Git does not ignore.

**The list never does the other rules' work.** The builder leaves out every
enumerated name that the category rules already skip, or that the Chinese-vehicle
veto would stop from applying, and the launcher looks a name up in this list only
for a device that nothing else has skipped. So no device is checked against both.

**Hand-written families.** `Analysis/metadata/private/novelty_names_GATT_families.json`
(`{"families": [{"pattern": "^...$", "note": "..."}]}`) holds families to take as
given: ones with too few examples to infer, ones whose varying part is a number or a
model code, and ones whose enumerated members have different GATT databases. The
aim is to skip devices that are likely the same type as one already enumerated,
rather than to list individual names. A hand-written family is used only while it
matches an enumerated name the other rules do not already skip, and it replaces any
inferred family it covers. Where the category rules hold part of a naming scheme,
write the family with an exception for that part (a negative lookahead), so the two
lists stay disjoint.

The build of 2026-11-17 found 21,150 fully enumerated devices, 1,843 of which
advertise a name (1,460 distinct names). 323 of those names are left to the other
rules. The file holds 265 family regexes (123 hand-written, 142 inferred) covering
902 of the rest, plus 224 exact names. It matches about 38,700 of the 153,000
distinct advertised names in the database, none of which another rule also matches.

## Automated regression and QA

Run from the Blue2thprinting root:

```bash
venv/bin/python -m pytest -q Scripts/tests
venv/bin/python -m pytest -q Scripts/BG/tests
```

For a capture Pi without pytest, the new tests also run using the capture venv's
existing `dbus-fast` dependency and standard-library unittest:

```bash
venv/bin/python -m unittest discover -s Scripts/tests -p 'test_novelty*.py' -v
```

The launcher QA test replays the same raw records through the **real parser,
queues, worker loops and subprocess gate**, with process creation replaced by a
recorder. It explicitly asserts all four combinations: novelty **on/off × BLE/BTC**.
On: only ordinary sensors, retained Chinese vehicles and the non-vehicle key
control launch. Off: every category candidate launches. Every selected BTC
candidate invokes both LMP and SDP/GATT. Completed devices and exhausted retries
remain blocked in both modes; a partial BTC success remains eligible for its
unfinished work. Other regressions cover late scan responses, deferred GATT reads,
TTL, cache bounds, malformed AD/HCI lengths, Fast Pair boundaries, exact product
signatures, native socket binding, and discovery failure/cancellation cleanup.

Regressions added with the 2026-11-17 review: Better Getter gets `-A` exactly when
novelty mode is on; a run still in flight is one attempt and three launched
failures end a device; a probe refused at launch is not an attempt (BLE and BTC);
scan responses and directed advertisements never admit a candidate; one LE address
is one device across mislabelled address types; Shortened and Complete Local Name
halves merge; CLUES wildcard UUIDs match; one bad packet does not end discovery;
the stored verdict always equals a fresh classification (pseudo-random replay); the
cached AD types are exactly the ones the rules read; and the committed name snapshot
contains no private NamePrint rule. Tests that need the private rules are skipped
where `Analysis/metadata/private` is not installed.

For passive live QA, while the existing collector is scanning, resolve the
controller index with `hciconfig`, then run:

```bash
sudo venv/bin/python Scripts/novelty/passive_qa.py --index 2 --seconds 30 --show-names
```

The command makes **zero connections** and leaves discovery settings untouched.
It uses the launcher's rules, private ones included, counts both on/off eligibility
from the same on-air reports, and reports the CPU cost per report. `--show-names`
lists the advertised names it heard, split by verdict. A run with no reports is
inconclusive and exits nonzero. Identity counts mean “eligible at least once”; a
later identifying scan response can change subsequent decisions. It judges each
typed address on its own, so it does not apply the launcher's one-device-per-address
rule.

## Validation results

The first version of this branch was reviewed on 2026-11-17 and the errors found
were fixed before it was committed in its present form; the numbers below are for
the fixed code. The regression tests added with the fixes were also run against the
pre-review sources, where 28 of them fail, one or more for each defect.

| Check | Result |
| --- | --- |
| `venv/bin/python -m pytest -q Scripts/tests` (Mac) | **65 passed, 2,701 subtests passed.** 62 novelty tests plus the three capture-cron tests. |
| `venv/bin/python -m pytest -q Scripts/BG/tests` (Mac) | **228 passed.** |
| `unittest` on `pi0-2` (Pi Zero W, Python 3.11.2), private rules installed | **62 passed** in 39 s, none skipped. |
| Passive check, Broadcom `hci0`, 30 s, legacy reports, no duplicate filtering | 3,442 reports, 36 identities eligible with novelty off, 6 with it on. **1.6 ms CPU per report** (4.9 ms before the stored verdict). |
| Launcher `--discovery-only`, Realtek `hci2`, 85 s, extended reports | Admitted **exactly the 4 identities** an independent recorder on the same HCI stream judged eligible, out of 63. |
| Launcher, novelty **on**, real radios, first 3.5 min | 13 probes, all on the 4 eligible addresses. **None** on the 32 connectable Apple (23), Android (6) and audio (3) devices or the 33 non-connectable ones. Each BLE candidate got exactly three launched attempts, then `retry limit`. Every Better Getter launch carried `-A`. No exception. |
| Launcher, novelty **off**, real radios, 4.3 min | 37 candidates; probes on 36 addresses (25 Apple, 4 Android, 3 audio, 4 others); no `-A`; **7 GATT collections completed**, 13 more saved their handle/UUID map and deferred values; LMP completed on the one BR/EDR device. |
| Mislabelled address type | Three random addresses were also reported as `public` during these runs. Before the fix one was admitted as a second, evidence-free candidate; after it none was, and with novelty off all three were probed as `random`. |

Not covered by the live runs: a BR/EDR device that novelty mode should skip (only one
BR/EDR device was in range, and it is eligible; the on/off BTC decisions are covered
by the worker replay tests), a crowded environment, and a long soak.

The independent recorder is a second process reading the same HCI monitor stream
through its own evidence cache; each launch in the launcher log was checked against
what it had heard about that address by then.

## Field run of 2026-11-17 on `pi0-2`

The first run after the boot switch was pulled and checked against its own HCI
capture, replayed through the rules as an independent witness.

| | |
| --- | --- |
| Discovery | Ran from 13:04:36 to 13:30:48 UTC, then stopped for the rest of the run (first bug below). Nothing was collected after that, which includes the walk. |
| Seen while it ran | 239 identities: 80 connectable Apple, 11 Android, 5 audio, 1 vehicle, 25 eligible BLE, 3 eligible BR/EDR, 114 not connectable. |
| Probes | 76 (66 Better Getter, 3 LMP, 7 SDP/GATT). None on a device with a category verdict at that moment; all 25 eligible BLE devices were probed; none more than three times; every Better Getter launch had `-A` and the right address type. |
| Results | GATT collected from 7 of the 25 BLE devices; LMP from all 3 BR/EDR devices. 53 of 66 Better Getter attempts timed out, 36 of those on devices weaker than -85 dBm. |
| Timing | A new device was probed within a second or two once the start-up backlog had cleared; during the backlog (15 devices, two dongles) the median wait was 39 s. |

Two bugs were found and fixed, neither in the novelty rules:

* **The launcher changed Realtek after a power cycle.** This Pi has four
  DarkFirmware dongles, which all boot with the same BD address, and BlueZ
  registers an adapter for only one. After the second power cycle the first poll
  found one of the others (`hci4` -> `hci3`), `StartDiscovery` failed on it, and
  discovery never resumed. The launcher now takes the dongle BlueZ manages, remembers
  its USB port, and waits for that port to come back; it also tells the LMP tool
  which dongle to use. Checked on the Pi with three power cycles in a row.
* **`btc_sdp_gatt.py` wrote the L2CAP channel MTU as `l2cap_len`**, so the importer
  refused both SDP files from this tree. This is the fix already on `parallel-LMP`
  (`5c7f5735`), applied here as the same hunk. Corrected copies of the two files
  were imported; the originals in the archive are unchanged.

Seen but not changed: three failed attempts end a device for the run, so the
strongest devices in range (the DFU fixture at -40 dBm among them) were spent within
eight minutes and the two Better Getter dongles were idle for most of the remaining
eighteen. With two Sonoffs and `MAX_BG = 2` there is no dongle left for Sniffle, so
nothing was sniffed passively.

## Second run on `pi0-2` that day: candidates never left the queue

A 140-minute run on the move (17:59 to 20:19 UTC; 871 BLE and 82 BR/EDR
addresses heard) was audited from `Logs/CAL.log` and the Better Getter captures.

What held: discovery never stopped (every 10-minute window had new devices), all
201 Realtek power cycles completed (median 5.3 s, always the dongle on USB
`1-1.4.4`) and discovery was restarted after each, no device got more than three
attempts, no category-skipped device was connected to, and there was no traceback.

What did not: **none of 716 Better Getter attempts succeeded** (708 timeouts),
against 7 of 67 on the morning walk. 95 % of the captures hold nothing but our own
`CONNECT_IND`. The first attempt on a device came a median of 25 minutes after
it was first heard; 358 of 403 first attempts came more than five minutes after.
Two Sonoffs manage about five attempts a minute, more devices than that arrived,
and nothing took a device out of the queue for having gone out of range. Before
novelty mode the launcher did that on BlueZ's `InterfacesRemoved` (`[DEL]`),
which BlueZ sends 30 s after it last saw a device. Taking candidates from the HCI
monitor dropped it, and the review of the first version missed that.

The fix is `CANDIDATE_STALE_S` in `central_app_launcher.py`. A candidate not
heard for 30 s (BLE) or 60 s (BR/EDR) leaves its queue, with a
`[DEL] ... (not heard for Ns)` line, until it is heard again. It keeps its attempt
counts, and a device being probed is left alone. The check is made when a worker
picks a candidate and again after the wait for a Better Getter dongle. With it,
the first minutes of a stationary run on `pi0-2` gave 2 GATT successes in 9
attempts; it has not yet been on a walk.

Three log lines in that run looked like probes after a category skip. Two BLE
devices were heard again 45 minutes after a `GATT_KNOWN` skip, by then without
the name that had identified them (evidence is kept for ten minutes), and were
probed long after that; the aging stops such probes. The third was only a line in
`BTC_2THPRINT.log`: `launch_application()` had refused the launch. That line is no
longer written for a candidate withdrawn during the Realtek power cycle.

## A Realtek that loses its firmware

Found on `pi0-3` (Pi Zero W, Raspberry Pi OS Trixie, kernel 6.18) on its first
run. A minute in, after the first BR/EDR probe, the dongle stopped answering. The
kernel reset it (`command tx timeout`, `Resetting usb device`), the firmware
download then failed (`RTL: Read reg16 failed (-110)`), and it sat on its USB port
with address `00:00:00:00:00:00`. The launcher finds its dongle by the DarkFirmware
address, so `cycle_realtek_adapter()` reported "USB device not found", discovery
stayed dead, and the LMP tool, started without `--hci`, used the built-in adapter.
A power cycle of the port (`uhubctl`) brought the dongle back in two seconds.

Now the launcher keeps pointing at the USB port it pinned while a device is still
on it, so the power cycle before the next LMP probe recovers the dongle. A
watchdog on the discovery side power cycles the port itself after two looks, 15 s
apart, found the dongle there without its address, because without a BR/EDR device
left to probe nothing else would. Power cycles are serialized. With several
dongles, a BR/EDR device is not probed while ours is away, and no attempt is
counted. Tried on `pi0-2` by detaching the driver from the dongle: the watchdog
power cycled it 20 s later and discovery was running again after 28 s. It has not
yet been tried on `pi0-3`, and `pi0-2` (kernel 6.12) logged no such reset in
either run.

## State of `pi0-2` after this validation

`~/Blue2thprinting` on the Pi was not modified. It is still the `master` checkout
from 2026-11-14 with the uncommitted multi-Realtek (`BTC_do_it_all`,
split-discovery) changes.

The fixed novelty-mode tree is beside it in `~/Blue2thprinting-novelty`: `Scripts/`,
`docs/` and the Python parts of `Analysis/` from this branch, with `venv`,
`bluez-5.66`, `Sniffle`, `Logs` and `Analysis/metadata/private` linked to the
existing checkout, so logs land in the usual `~/Blue2thprinting/Logs`.

The private name files are both installed, and the launcher's first lines name them
(`... 920 private name rules ..., 189 name families and 698 names already
GATT-enumerated ...`).

**The Pi now boots into novelty mode.** Root's `@reboot` entry runs
`~/Blue2thprinting-novelty/Scripts/runall.sh` (the previous crontab is in
`/var/backups/blue2thprinting/`). This was checked with a reboot on 2026-11-17: the
launcher came up by itself about two minutes after power-on with novelty mode on and
the private rules loaded, started discovery, launched probes, and carried on through
a Realtek power-cycle with no error. To go back to the old launcher at boot, or
forward again:

```bash
bash ~/novelty_test/boot_switch.sh old
```

```bash
bash ~/novelty_test/boot_switch.sh novelty
```

Being `master`-based, this launcher uses one Realtek for discovery and LMP and two
Sonoffs for Better Getter. All four Realteks on this Pi boot with the same address
(`13:37:13:37:13:37`); only the old launcher gives the extra three their own. The
launcher uses the one BlueZ registered and keeps to its USB port (see the field run
above). So far that has been the TP-Link at USB `1-1.4.4`; in the runs that followed
the old launcher it was the weaker `0bda:a729` at `1-1.3`. Unplug the Realteks you
do not want it to use.

The side tree was only for testing the branch next to that checkout. A capture node
installed from `master` after the merge has novelty mode in its one checkout and
needs only the two private name files copied in (see "Private metadata" above).

`~/novelty_test` holds the helper scripts used here (`boot_switch.sh`,
`stop_novelty.sh`, `start_novelty_boot_style.sh`, `start_old.sh`, `recorder.py`)
and the run logs.
