# BG, BTIDES, SQL, and TME notification QA (2026-11-15)

This work is on branch `notification-checking` in the isolated linked worktree
`/Users/user/Blue2thprinting-notification-checking`. The original
`/Users/user/Blue2thprinting` checkout had unrelated uncommitted work and was
left untouched. The paired DM BT work and fixture setup are documented in
`/Users/user/Downloads/XenoMetaRadar/docs/qa-nordic-uart-notifications-20261115.md`.

## Fixture and captured packets

The nRF52832 DK (J-Link serial `682768135`) ran Zephyr 3.7.0
`peripheral_nus`, static random address `C6:09:6B:42:D1:92`. This sample uses
one-time advertising; reset the board before each connection with
`/Users/user/.nrfutil/bin/nrfutil device reset --serial-number 682768135`.
Sniffle port `/dev/cu.usbserial-1110` saw the board at RSSI about -49 dBm and
completed a connection. Port `21420` did not connect to this fixture. BG now
requests a 24-unit initial interval; Sniffle's random 5–15-unit WinOffset can
exceed BG's former 7-unit interval.

Run from `Scripts/BG`:

```sh
python3 -u Better_Getter.py -s /dev/cu.usbserial-1110 \
  -b C6:09:6B:42:D1:92 -c 37 \
  -o /Users/user/Downloads/XenoMetaRadar/artifacts/nrf52832-nus-qa/bg-nus-1110.pcap \
  --notification-window-seconds 6 --force-read-values -q
```

BG printed one CCCD subscription for NUS TX value handle `0x0012` via
CCCD `0x0013`, then two notifications with exact bytes
`48656c6c6f20576f726c64210a` (`Hello World!\n`). TShark found the CCCD
ATT Write Request in frame 120 and notifications in frames 178 and 278.
PCAP SHA-256: `38ec80a700aad86f663630eda373bd968677dc3af9a2a539f62dcc80b1e820b6`.
This sample has a notify property; the indicate-only characteristic and its
confirmation are checked in the follow-up QA below.

## Conversion and database checks

From `Analysis`, Python `HCI_to_BTIDES.py` converted the P1 BTSnoop and
`PCAP_to_BTIDES.py` converted the BG PCAP, each with `--input`, `--output`, and
`--quiet-print`. From `Analysis/BTIDES_Schema/rust`, `cargo build -p
hci-to-BTIDES -p pcap-to-BTIDES` built the Rust converters; both were run on
the same respective captures with `--schema-dir ..`. All four outputs validated
against the local BTIDES schema. Python and Rust agreed on the NUS RX write
`30313233343536373839`, NUS TX notification
`48656c6c6f20576f726c64210a`, and nested GATT characteristic handles.

The P1 HCI and BG Python PCAP JSON files were imported separately from
`Analysis` with:

```sh
python3 BTIDES_to_SQL.py --input <BTIDES JSON path> --use-test-db --quiet-print
```

The test database `bttest` contains NUS RX handle `0x0015`, operation 18,
value `30313233343536373839`, and NUS TX handle `0x0012`, operation 27,
value `48656c6c6f20576f726c64210a`. The existing table and import path
already store operation and binary bytes; no SQL or CLUES schema change was
needed. `INSERT IGNORE` collapses identical observations from P1 and BG, so
the table is a set of values, not a time-ordered event log.

From `Analysis`, this TME command printed the imported record:

```sh
python3 Tell_Me_Everything.py --use-test-db \
  --bdaddr c6:09:6b:42:d1:92 --bdaddr-type 1
```

Under NUS TX UUID `6e400003-b5a3-f393-e0a9-e50e24dcca9e`, TME printed
`Notification raw hex: 48656c6c6f20576f726c64210a`, followed one nesting
level deeper by `Speculative ASCII: Hello World!\\n`. The BTIDES ATT schema
did need a small correction: ATT_READ_RSP carries a value but no handle, so
its required field is `value_hex_str`.

Follow-up presentation check: TME colors only the raw hex bytes and speculative
ASCII interpretation bright magenta using the same helper as DeviceName values;
the `Notification raw hex:` and `Speculative ASCII:` labels stay uncolored. The focused
`python3 -m pytest -q Analysis/tests/test_tme_notification_values.py
Analysis/tests/test_att_value_updates.py` run passed 7 tests. A TME run on the
imported Nordic record through a terminal PTY exited 0 and contained the
bright-magenta ANSI sequences immediately after both labels.

## Automated checks

- `python3 -m pytest -q Scripts/BG/tests Analysis/tests/test_att_value_updates.py Analysis/tests/test_tme_notification_values.py Analysis/tests/test_hci_address_type.py`: **211 passed**.
- `python3 -m pytest -q Analysis/tests/test_standalone_converters.py`: **12 passed**.
- `CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test -p BTIDES-bt -p BTIDES-hci`: **5 passed** plus 0 doc tests.

The BG replay suite includes a subscription-stage pairing gate test. Other
replay fixtures predate CCCD capture and explicitly mark that phase complete.
Python tests cover binary notifications, indications, writes, schema-valid
read responses, and TME formatting. Rust tests cover exact binary update
bytes, truncated updates, nesting, and identity address types.

## Follow-up QA on `notification-checking`

The local branch at `d369ce54` passed the Blue2thprinting QA skill's local
streams on 2026-11-15: 227 Analysis pytest cases (3 BTIDALPOOL cases excluded),
203 BG pytest cases, and 121 Rust tests. The BTIDALPOOL and remote install
streams were skipped because they do not test this local notification path.
Logs are in `/tmp/qa-pass-2026-11-15/`.

The nRF52832 DK was reset and BG was run again with the same command above,
writing `bg-nus-qa-20261115-new.pcap`. BG enabled the NUS TX CCCD at handle
`0x0013` and received two notifications on value handle `0x0012`, each
`48656c6c6f20576f726c64210a`. Python and Rust PCAP converters each produced
schema-valid BTIDES with the notification at NUS TX. The Python BTIDES file
imported into `bttest`; TME printed the notification raw hex and speculative
ASCII beneath the TX characteristic.

The new `Analysis/tests/test_gatt_update_sql_roundtrip.py` regression uses a
synthetic BTIDES record with distinct binary notification and indication
values. It checks exact operation and bytes in `GATT_characteristics_values`,
then checks both values and speculative ASCII in nested TME output and BTIDES
re-export. It passed
with `python -m pytest -q Analysis/tests/test_gatt_update_sql_roundtrip.py`.

The same DK also passed a physical indication check. Build stock Zephyr 3.7.0
`zephyr/samples/bluetooth/peripheral_ht` for `nrf52dk/nrf52832` with the
`gnuarmemb` toolchain, flash only J-Link `682768135` with `VERIFY_READ`, and
reset it before running BG with the same port, address, channel, and options
above but output `bg-ht-indication.pcap`. This sample advertises as Zephyr
Health Thermometer at the same static random address. The test firmware SHA-256
was `222894119bd9127d86c2781b5d417fff5570a61b00b9a5597c7d0c6d113d83df`.
BG enabled notify CCCD `0x0013` and indicate CCCD `0x001d`; it captured six
notifications on value handle `0x0012` and six indications on `0x001c`.
TShark showed each ATT indication immediately followed by ATT confirmation
(frame pairs 164/165, 201/202, 237/238, 276/277, 312/313, 348/349).
The indication payload was `002e0900fe`. Both Python and Rust PCAP converters
validated BTIDES with six nested indications and six nested notifications.
The Python BTIDES file imported into `bttest`, and TME printed
`Indication raw hex: 002e0900fe` and speculative ASCII beneath Health
Thermometer Measurement UUID `2a1c`. The capture SHA-256 was
`261384e224bfe7894e7d46763f2ab40edaff698fa14e4a6f2246543bf5e22d7b`.
Finally, the original Nordic UART sample hex was restored to the DK with
`VERIFY_READ`; its SHA-256 was
`b7b6d4cfd3a87b48566007fd531ce07df30fec817db0f189d7898a23476ff8f2`.

Checklist: local suites passed; live NUS notification passed; live thermometer
indication and confirmation passed; Python/Rust conversions passed; SQL import,
TME nesting, and BTIDES re-export passed; Nordic UART firmware restored.

## Integration onto local `master`

The `notification-checking` branch was merged into local `master` alongside
newer master changes. The BTIDES schema submodule needed a merge commit that
keeps both the ATT update capture and master's HCI/SDP parsing changes.
On the combined tree, the local Blue2thprinting QA skill command
`bash /Users/user/.agents/skills/Blue2thprinting-run-unit-tests/scripts/run_qa.sh
--skip-btidalpool --skip-installs` passed 302 Analysis tests (3 BTIDALPOOL
tests deselected), 228 BG tests, and 132 Rust tests. Logs are under
`/tmp/qa-pass-2026-11-15/`.

The post-merge live BG connection could not be repeated: Sniffle port
`/dev/cu.usbserial-1110` did not initialize in the scanner, while port
`/dev/cu.usbserial-21420` saw the Nordic board but did not establish a BG
connection, as in the earlier fixture attempt. The board's UART continued
printing from the restored NUS sample. The live notification and indication
checks above were completed on the feature branch before integration.
