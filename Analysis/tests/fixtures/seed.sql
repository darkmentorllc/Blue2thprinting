-- ##############################################################################
-- Test fixture data for the Blue2thprinting unit test suite.
-- Loaded into the `bttest` database by tests/conftest.py.
-- Lookup tables (IEEE_bdaddr_to_company, UUID16_to_company, BLEScope_UUID128s)
-- are NOT touched here; they are populated separately by translator scripts.
-- ##############################################################################

-- Device 1: AA:BB:CC:11:22:01 — LE public, name + UUID16 list + flags + tx_power + MSD
-- Coverage: --bdaddr, --name-regex, --UUID-regex, --MSD-regex, --bdaddr-type 0
INSERT INTO LE_bdaddr_to_name (bdaddr, bdaddr_random, le_evt_type, device_name_type, name_hex_str)
VALUES ('aa:bb:cc:11:22:01', 0, 0, 9, '5465737444657669636531');

INSERT INTO LE_bdaddr_to_UUID16s_list (bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID16s)
VALUES ('aa:bb:cc:11:22:01', 0, 0, 2, '180d');  -- Complete list, Heart Rate Service

INSERT INTO LE_bdaddr_to_flags (bdaddr, bdaddr_random, le_evt_type, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)
VALUES ('aa:bb:cc:11:22:01', 0, 0, 0, 1, 1, 0, 0);

INSERT INTO LE_bdaddr_to_tx_power (bdaddr, bdaddr_random, le_evt_type, device_tx_power)
VALUES ('aa:bb:cc:11:22:01', 0, 0, -4);

-- MSD: company 0x004C (Apple), payload 02 15 (iBeacon prefix) + 16 random bytes
INSERT INTO LE_bdaddr_to_MSD (bdaddr, bdaddr_random, le_evt_type, device_BT_CID, manufacturer_specific_data)
VALUES ('aa:bb:cc:11:22:01', 0, 0, 76, '021500112233445566778899aabbccddeeff00010203');

-- Device 2: AA:BB:CC:11:22:02 — LE random, GATT services + characteristics + values + GPS
-- Coverage: --require-GATT-any, --require-GATT-values, --require-GPS, --bdaddr-type 1
INSERT INTO LE_bdaddr_to_name (bdaddr, bdaddr_random, le_evt_type, device_name_type, name_hex_str)
VALUES ('aa:bb:cc:11:22:02', 1, 4, 9, '546573744741545432');

INSERT INTO GATT_services (bdaddr, bdaddr_random, service_type, begin_handle, end_handle, UUID) VALUES
  ('aa:bb:cc:11:22:02', 1, 0,  1, 11, '1800'),    -- GAP service
  ('aa:bb:cc:11:22:02', 1, 0, 12, 15, '1801'),    -- GATT service
  ('aa:bb:cc:11:22:02', 1, 0, 16, 25, '180f');    -- Battery service

INSERT INTO GATT_characteristics (bdaddr, bdaddr_random, declaration_handle, char_properties, char_value_handle, UUID) VALUES
  ('aa:bb:cc:11:22:02', 1,  2,  2,  3, '2a00'),   -- Device Name (read)
  ('aa:bb:cc:11:22:02', 1,  4, 10,  5, '2a01'),   -- Appearance (read)
  ('aa:bb:cc:11:22:02', 1, 17, 18, 18, '2a19');   -- Battery Level (read)

-- Battery Level char value = 0x55 (85%); Device Name = "TestGATT2"; Appearance = 0x0040 (Generic Phone)
-- operation=11 corresponds to ATT_READ_RSP (a value of 0 is invalid per the
-- BTIDES io_type enum and trips schema validation on export).
INSERT INTO GATT_characteristics_values (bdaddr, bdaddr_random, char_value_handle, operation, byte_values) VALUES
  ('aa:bb:cc:11:22:02', 1,  3, 11, UNHEX('546573744741545432')),
  ('aa:bb:cc:11:22:02', 1,  5, 11, UNHEX('4000')),
  ('aa:bb:cc:11:22:02', 1, 18, 11, UNHEX('55'));

-- GPS coords: ~38.9072 N, -77.0369 W (Washington DC) — a non-NULL location.
-- time_type=0 (unix_time) was the path that triggered an UnboundLocalError
-- before commit 5726ec6 fixed it; keeping this row as the regression case.
INSERT INTO bdaddr_to_GPS (bdaddr, bdaddr_random, time, time_type, rssi, lat, lon)
VALUES ('aa:bb:cc:11:22:02', 1, 1714000000, 0, -55, 38.9072, -77.0369);

-- Device 3: AA:BB:CC:11:22:03 — BT Classic, EIR name + CoD + SDP records
-- Coverage: --require-SDP, EIR table queries
INSERT INTO EIR_bdaddr_to_name (bdaddr, device_name_type, name_hex_str)
VALUES ('aa:bb:cc:11:22:03', 9, '436c617373696354657374');

-- CoD: Audio/Video Major (0x04), Headphones Minor (0x04), Audio service (0x200000)
-- Encoded as: 0x240414 = 2360340 decimal
INSERT INTO EIR_bdaddr_to_CoD (bdaddr, class_of_device)
VALUES ('aa:bb:cc:11:22:03', 2360340);

-- Minimal SDP_Common row. byte_values is a SDP_ServiceSearchAttributeResponse
-- header followed by a 1-byte continuation. Real-world records can be hundreds
-- of bytes; this is enough to exercise "device has *some* SDP info" filters.
INSERT INTO SDP_Common (bdaddr, direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values)
VALUES ('aa:bb:cc:11:22:03', 1, 8, 64, 7, 1, 4, UNHEX('00040000'));

-- Device 4: AA:BB:CC:11:22:04 — LE public, with LL_VERSION_IND and LMP_VERSION_RES
-- Coverage: --require-LL_VERSION_IND, --require-LMP_VERSION_RES, --LL_VERSION_IND, --LMP_VERSION_RES
INSERT INTO LE_bdaddr_to_name (bdaddr, bdaddr_random, le_evt_type, device_name_type, name_hex_str)
VALUES ('aa:bb:cc:11:22:04', 0, 0, 9, '5465737456657273696f6e73');

-- BT 4.0 (version 6), Texas Instruments (CID 13), sub-version 0x0142 = 322
INSERT INTO LL_VERSION_IND (bdaddr, bdaddr_random, ll_version, device_BT_CID, ll_sub_version)
VALUES ('aa:bb:cc:11:22:04', 0, 6, 13, 322);

-- BT 5.0 (version 8), Cambridge Silicon Radio (CID 10), sub-version 0x0321 = 801
INSERT INTO LMP_VERSION_RES (bdaddr, lmp_version, device_BT_CID, lmp_sub_version)
VALUES ('aa:bb:cc:11:22:04', 8, 10, 801);

-- Device 5: AA:BB:CC:11:22:05 — LE public, with SMP Pairing Request/Response (legacy)
-- Coverage: --require-SMP, --require-SMP-legacy-pairing
INSERT INTO LE_bdaddr_to_name (bdaddr, bdaddr_random, le_evt_type, device_name_type, name_hex_str)
VALUES ('aa:bb:cc:11:22:05', 0, 0, 9, '54657374534d50');

-- Pairing Request (opcode 1): IO=NoInputNoOutput, no OOB, auth_req=0x01 (Bonding only,
-- no MITM, no Secure Connections → legacy pairing), max_key_size=16
INSERT INTO SMP_Pairing_Req_Res (bdaddr, bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist)
VALUES ('aa:bb:cc:11:22:05', 0, 1, 3, 0, 1, 16, 7, 7);

-- Pairing Response (opcode 2): same legacy fingerprint
INSERT INTO SMP_Pairing_Req_Res (bdaddr, bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist)
VALUES ('aa:bb:cc:11:22:05', 0, 2, 3, 0, 1, 16, 7, 7);
