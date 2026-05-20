# Better_Getter Test Suite

A pytest-based regression suite for `Scripts/BG/Better_Getter.py` and the
`BG_Helper_*` modules that drive the LL Control / L2CAP / ATT / GATT / SMP
state machines.

## What's covered

| File | Coverage |
|---|---|
| `test_apple_filter.py` | `Better_Getter.apple_advertisement()` — Apple Company ID detection across both byte orders, non-Apple devices, ADV_IND-only filtering |
| `test_skip_apple.py` | The `-A` / skip-apple feature end-to-end across all three detection vectors: (1) Advertisement Company ID via `print_packet()` → `exit(0x0A)`, driven by **real captured Apple advertisements** (`fixtures/apple_advertisements.pcap`); (2) LL_VERSION_IND Company ID exit-code contract; (3) the GATT Manufacturer-Name probe (`detect_Apple_by_GATT_Manufacturer_Name` + `send_ATT_FIND_BY_TYPE_VALUE_REQ_0x2A29_Apple`) and the `stateful_GATT_getter` exit |
| `test_output.py` | `BG_Helper_Output.convert_bytes_to_UUID128_str()`, `append_common()`, `write_to_csv()`, `print_all_info()` formatting |
| `test_l2cap.py` | `BG_Helper_L2CAP` — packet type classification, CONNECTION_PARAMETER_UPDATE_REQ rejection, signaling-channel detection |
| `test_ll_ctrl.py` | `BG_Helper_LL` — LL_VERSION_IND, LL_FEATURE_REQ/RSP, LL_PERIPHERAL_FEATURE_REQ, LL_LENGTH_REQ/RSP, LL_PHY_REQ/RSP/UPDATE_IND, LL_REJECT_EXT_IND, LL_UNKNOWN_RSP, LL_TERMINATE_IND, the `stateful_LL_CTRL_outgoing_handler` ordering, the 2M PHY toggle |
| `test_smp.py` | `BG_Helper_SMP` — Pairing Request payload bytes, gating on `all_handles_read`, legacy Pairing Response handling, Pairing Failed (Not Supported) early-exit, Pairing Failed → SC fallback |
| `test_gatt.py` | `BG_Helper_GATT`/`BG_Helper_ATT` — ATT packet-type matching, MTU exchange (REQ/RSP both directions), Read by Group Type for Primary/Secondary services (UUID16 + UUID128 entries), Find Information for handle enumeration, ATT_READ_REQ value reads, error-response handling (Attribute Not Found, Read Not Permitted, Insufficient Authentication), `get_next_handle_to_att_read` service-handle skipping |
| `test_pcap_replay.py` | End-to-end replay of `fixtures/cafe_capture.pcap` (354 frames captured from CA:FE:13:37:00:01) through the BG state machines; asserts the full pipeline reaches each terminal state in order |
| `test_cli.py` | argparse — `--help` smoke, `--advchan` value validation, `-2`/`-A`/`-q`/`-l`/`-P` flag toggles, BDADDR validation (missing / malformed / valid hex pairs), output-PCAP wiring, all binary flag combinations against a mocked `SniffleHW` |

## Test data

### `fixtures/cafe_capture.pcap`

The real Sniffle capture from a Better_Getter run against `CA:FE:13:37:00:01`
(a developer test peripheral advertising the name `UVP01`). 354 frames over
~2.6 s, covering every functional area BG touches:

- LL Control: `LL_FEATURE_REQ`, `LL_FEATURE_RSP`, `LL_PERIPHERAL_FEATURE_REQ`,
  `LL_VERSION_IND` (both directions), `LL_PHY_REQ`, `LL_REJECT_EXT_IND`,
  `LL_LENGTH_REQ`, `LL_LENGTH_RSP`, `LL_PHY_RSP`, `LL_PHY_UPDATE_IND`,
  `LL_TERMINATE_IND`
- ATT: `EXCHANGE_MTU_REQ`/`RSP`, `READ_BY_GROUP_TYPE_REQ`/`RSP` for both
  Primary (0x2800) and Secondary (0x2801) services, `FIND_INFORMATION_REQ`/
  `RSP` for handle enumeration, `READ_REQ`/`RSP` for every readable handle
- ATT errors: `Attribute Not Found`, `Read Not Permitted`,
  `Insufficient Authentication`
- SMP: legacy `Pairing Request` → `Pairing Response`

### `fixtures/apple_advertisements.pcap`

6 real Apple (Company ID `0x004C`) `ADV_IND` frames sliced from a **NYC
field capture**
(`NYC_Day1/sniffle/2026-05-06-11-25-07_ttyUSB1_follow_ch38_pi4-2.pcap`).
Used by `test_skip_apple.py` to drive the advertisement-based `-A` exit
with authentic off-air data rather than synthetic bytes.

**Provenance, not address type, is the privacy rule here.** Test fixtures
must not contain anything live-sniffed at the maintainer's current home,
since persistent identifiers there could reveal a home location. Captures
from away-from-home field trips (the NYC sniffs) are fine to commit
regardless of whether the addresses are public, random-static, or
rotating-private. Re-slice only from those approved away-from-home
sources.

### `fixtures/public_bdaddr_capture.pcap`

A second real capture from a Better_Getter run with `-P -2` flags against a
**public** BDADDR (`7c:0a:3f:58:72:7b`, Samsung Electronics OUI), sliced
from the NYC_Day1 sniff. 387 frames over ~6 s. Exercises:

- the `args.public=True` codepath (CONNECT_IND with `RxAdd: Public`)
- the `-2` (`attempt_2M_PHY_update`) handler — `LL_PHY_REQ` →
  `LL_PHY_RSP` → `LL_PHY_UPDATE_IND` all visible in the prelude
- `manage_peripheral_info_requests` rejecting a Peripheral-initiated
  `ATT_READ_BY_GROUP_TYPE_REQ` with `Unlikely Error`
- the SMP retry-cap path — this peripheral ignored every Pairing Request,
  so BG re-sent at ~1 s intervals and gave up after the 6th attempt
- clean `LL_TERMINATE_IND` teardown

## Running

From the repo root:

```sh
# Full BG suite
python3 -m pytest Scripts/BG/tests/ -v

# Single test
python3 -m pytest Scripts/BG/tests/test_ll_ctrl.py::test_incoming_LL_VERSION_IND_sets_state -v
```

The suite is pure-Python: no MySQL, no hardware. `SniffleHW` is replaced by
a recording stub in `conftest.py`, and `Scripts/BG/` is added to `sys.path`
so the bare `import globals` / `from BG_Helper_* import *` style used by
`Better_Getter.py` works unchanged.

## How `globals` resets between tests

`Scripts/BG/globals.py` holds the state machine variables as module-level
attributes. The `clean_globals` fixture in `conftest.py` reloads the module
between tests so attributes return to their declared defaults (and the
`ll_ctrl_state` instance is re-created), preventing cross-test bleed.
