# HCI-to-BTIDES reference slices

These small btsnoop captures provide real HCI packet references for the
protocol families missing from the existing `import.snoop` fixture. They are
exercised by `../../test_hci_btides_reference.py` alongside `import.snoop`.

| Capture | Source frames | BTIDES families |
| --- | --- | --- |
| `att_gatt_qa.snoop` | P1 QA capture frames 263, 304, 308 | ATT, GATT |
| `classic_sdp_qa.snoop` | P1 QA capture frames 7963, 7966, 7973, 7974, 7990, 7991, 7993, 7999, 8007, 8011 | L2CAP, SDP, LMP, HCI remote name |
| `classic_sdp_records_qa.snoop` | P1 HCI rotator probe frames 9377 and 9408–9459 (21 selected frames) | Three SDP channels, four complete ServiceSearchAttribute responses, five service records |
| `classic_sdp_continuation_qa.snoop` | P1 HCI rotator probe frames 15284 and 15336–15440 (46 selected frames) | L2CAP pending/success, ServiceSearchAttribute and ServiceAttribute response fragments, continuation requests with changing transaction IDs |
| `smp_pairing_sanitized.snoop` | Archived QA capture frames 12650, 12732, 12739 | SMP |

The first two peers are synthetic QA devices (`F0:F1:F2:F3:A0:EB` and
`DMBT-SDP-QA`). The SMP peer address was replaced with synthetic
`F0:F1:F2:F3:A0:EE`; only the connection event and pairing request/response
were retained. No pairing keys or complete private captures are checked in.
The archived source files remain local and outside Git.
For the two SDP record captures, the sole connection-complete peer address was
replaced with synthetic `F0:F1:F2:F3:A0:EF` and `F0:F1:F2:F3:A0:F0`,
respectively. Only connection signaling and SDP request/response frames were
retained. The SDP payload bytes are unchanged from the HCI logs; neither
capture includes pairing keys or unrelated traffic.
