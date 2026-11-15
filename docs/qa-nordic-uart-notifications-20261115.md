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
This sample has a notify property; an indicate-only fixture is still needed for
radio validation of indication confirmation.

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
