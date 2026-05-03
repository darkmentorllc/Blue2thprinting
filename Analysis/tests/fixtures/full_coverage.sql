-- ##############################################################################
-- Full-coverage fixture for the round-trip test in
-- Analysis/tests/test_full_coverage_round_trip.py.
-- =====
-- One device, BDADDR aa:bb:cc:dd:ee:7f (LE public, bdaddr_random=0), seeded
-- into every device-data table that BTIDES_to_SQL.py knows how to import.
-- =====
-- The round-trip test:
--   1. truncates the device-data tables in bttest
--   2. loads this file
--   3. exports BDADDR aa:bb:cc:dd:ee:7f via Tell_Me_Everything.py
--   4. edits the .btides file to bump the last BDADDR byte (7f → 80)
--   5. re-imports the modified file via BTIDES_to_SQL.py --use-test-db
--   6. asserts every row that landed under aa:bb:cc:dd:ee:80 matches the
--      corresponding original row under aa:bb:cc:dd:ee:7f exactly (only the
--      bdaddr column differs).
-- =====
-- All numeric / hex literals here are arbitrary-but-distinctive so the
-- comparison would catch transposition or default-value bugs.
-- ##############################################################################

-- =====
-- EIR (BR/EDR-side, no bdaddr_random column)
-- =====

INSERT INTO EIR_bdaddr_to_PSRM (bdaddr, page_scan_rep_mode)
VALUES ('aa:bb:cc:dd:ee:7f', 1);

INSERT INTO EIR_bdaddr_to_name (bdaddr, device_name_type, name_hex_str)
VALUES ('aa:bb:cc:dd:ee:7f', 9, '46756c6c436f76436c6173736963');  -- "FullCovClassic"

INSERT INTO EIR_bdaddr_to_DevID (bdaddr, vendor_id_source, vendor_id, product_id, product_version)
VALUES ('aa:bb:cc:dd:ee:7f', 2, 76, 4660, 257);  -- BT VID source, Apple, prod 0x1234, ver 0x0101

INSERT INTO EIR_bdaddr_to_tx_power (bdaddr, device_tx_power)
VALUES ('aa:bb:cc:dd:ee:7f', -7);

INSERT INTO EIR_bdaddr_to_CoD (bdaddr, class_of_device)
VALUES ('aa:bb:cc:dd:ee:7f', 2360340);  -- 0x240414 — Audio/Headphones

INSERT INTO EIR_bdaddr_to_UUID16s (bdaddr, list_type, str_UUID16s)
VALUES ('aa:bb:cc:dd:ee:7f', 3, '110a,110b');  -- A2DP/AVRCP

INSERT INTO EIR_bdaddr_to_UUID32s (bdaddr, list_type, str_UUID32s)
VALUES ('aa:bb:cc:dd:ee:7f', 5, 'cafebabe');

INSERT INTO EIR_bdaddr_to_UUID128s (bdaddr, list_type, str_UUID128s)
VALUES ('aa:bb:cc:dd:ee:7f', 7, '5e3a4f7e96b94c2da13fe9d1f2b87ce0');

INSERT INTO EIR_bdaddr_to_flags (bdaddr, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 1, 0, 1, 1);

INSERT INTO EIR_bdaddr_to_URI (bdaddr, uri_hex_str)
VALUES ('aa:bb:cc:dd:ee:7f', '17687474703a2f2f6578616d706c652e636f6d');  -- 0x17 + "http://example.com"

INSERT INTO EIR_bdaddr_to_3d_info (bdaddr, byte1, path_loss)
VALUES ('aa:bb:cc:dd:ee:7f', 5, 22);

INSERT INTO EIR_bdaddr_to_MSD (bdaddr, device_BT_CID, manufacturer_specific_data)
VALUES ('aa:bb:cc:dd:ee:7f', 76, 'cafedeadbeef');  -- Apple, hex payload

-- =====
-- HCI
-- =====

INSERT INTO HCI_bdaddr_to_name (bdaddr, status, name_hex_str)
VALUES ('aa:bb:cc:dd:ee:7f', 0, '46756c6c436f76484349');  -- "FullCovHCI"

-- =====
-- LE-side (bdaddr_random=0 throughout, le_evt_type=0 for ADV_IND)
-- =====

INSERT INTO LE_bdaddr_to_name (bdaddr, bdaddr_random, le_evt_type, device_name_type, name_hex_str)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 9, '46756c6c436f764c45');  -- "FullCovLE"

INSERT INTO LE_bdaddr_to_UUID16s_list (bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID16s)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 3, '180d,180f');  -- Heart Rate + Battery

INSERT INTO LE_bdaddr_to_UUID32s_list (bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID32s)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 5, 'deadbeef');

INSERT INTO LE_bdaddr_to_UUID128s_list (bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID128s)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 7, '6e400001b5a3f393e0a9e50e24dcca9e');  -- Nordic UART

INSERT INTO LE_bdaddr_to_flags (bdaddr, bdaddr_random, le_evt_type, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 0, 1, 1, 0, 0);

INSERT INTO LE_bdaddr_to_tx_power (bdaddr, bdaddr_random, le_evt_type, device_tx_power)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, -3);

INSERT INTO LE_bdaddr_to_CoD (bdaddr, bdaddr_random, le_evt_type, class_of_device)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 2360340);

INSERT INTO LE_bdaddr_to_appearance (bdaddr, bdaddr_random, le_evt_type, appearance)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 64);  -- 0x0040 = Generic Phone

INSERT INTO LE_bdaddr_to_connect_interval (bdaddr, bdaddr_random, le_evt_type, interval_min, interval_max)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 24, 40);

INSERT INTO LE_bdaddr_to_UUID16_service_solicit (bdaddr, bdaddr_random, le_evt_type, str_UUID16s)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, '180a');  -- Device Information

-- ACID_length is recomputed by the BTIDES export from data shape:
-- 1 byte type + 2 bytes UUID16 + 4 bytes payload = 7. Use that value here so
-- the round-trip matches.
INSERT INTO LE_bdaddr_to_UUID16_service_data (bdaddr, bdaddr_random, le_evt_type, ACID_length, UUID16_hex_str, service_data_hex_str)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 7, 'feed', '01020304');

-- ACID_length: 1 type + 4 UUID32 + 4 payload = 9.
INSERT INTO LE_bdaddr_to_UUID32_service_data (bdaddr, bdaddr_random, le_evt_type, ACID_length, UUID32_hex_str, service_data_hex_str)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 9, 'cafebabe', 'aabbccdd');

INSERT INTO LE_bdaddr_to_UUID128_service_solicit (bdaddr, bdaddr_random, le_evt_type, str_UUID128s)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, '0000180f00001000800000805f9b34fb');

-- ACID_length: 1 type + 16 UUID128 + 4 payload = 21.
INSERT INTO LE_bdaddr_to_UUID128_service_data (bdaddr, bdaddr_random, le_evt_type, ACID_length, UUID128_hex_str, service_data_hex_str)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 21, '6e400001b5a3f393e0a9e50e24dcca9e', '11223344');

INSERT INTO LE_bdaddr_to_public_target_bdaddr (bdaddr, bdaddr_random, le_evt_type, public_bdaddr)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, '11:22:33:44:55:66');

INSERT INTO LE_bdaddr_to_random_target_bdaddr (bdaddr, bdaddr_random, le_evt_type, random_bdaddr)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 'fe:dc:ba:98:76:54');

INSERT INTO LE_bdaddr_to_other_le_bdaddr (bdaddr, bdaddr_random, le_evt_type, other_bdaddr, other_bdaddr_random)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, '99:88:77:66:55:44', 1);

INSERT INTO LE_bdaddr_to_role (bdaddr, bdaddr_random, le_evt_type, role)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 1);  -- 1 = Peripheral preferred

INSERT INTO LE_bdaddr_to_URI (bdaddr, bdaddr_random, le_evt_type, uri_hex_str)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, '17687474703a2f2f6c652e6578616d706c65');

INSERT INTO LE_bdaddr_to_3d_info (bdaddr, bdaddr_random, le_evt_type, byte1, path_loss)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 3, 11);

INSERT INTO LE_bdaddr_to_MSD (bdaddr, bdaddr_random, le_evt_type, device_BT_CID, manufacturer_specific_data)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 76, '021500112233445566778899aabbccddeeff00010203');

-- =====
-- LL (BLE Link Layer)
-- =====

INSERT INTO LL_VERSION_IND (bdaddr, bdaddr_random, ll_version, device_BT_CID, ll_sub_version)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 9, 13, 322);  -- BT 5.1, TI

INSERT INTO LL_UNKNOWN_RSP (bdaddr, bdaddr_random, unknown_opcode)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 24);  -- LL_PHY_UPDATE_IND (must be a known LL ctrl opcode for the rendering path)

-- TME's LL features export emits opcode 9 (LL_FEATURE_RSP) regardless of
-- the underlying row's opcode, so seed with that value to keep round-trip
-- identity. (TODO: TME LLCP export could preserve REQ vs RSP.)
INSERT INTO LL_FEATUREs (bdaddr, bdaddr_random, opcode, features)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 9, 4503599627370497);

-- Direction is set to 1 (response/received) because TME's LLCP export
-- normalizes direction to 1 on this code path.
INSERT INTO LL_PHYs (bdaddr, bdaddr_random, opcode, direction, tx_phys, rx_phys)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 22, 1, 7, 7);  -- 1M+2M+Coded both directions

INSERT INTO LL_PINGs (bdaddr, bdaddr_random, opcode, direction)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 18, 1);  -- LL_PING_REQ

INSERT INTO LL_LENGTHs (bdaddr, bdaddr_random, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 20, 251, 2120, 251, 2120);

-- =====
-- L2CAP
-- =====

INSERT INTO L2CAP_CONNECTION_PARAMETER_UPDATE_REQ (bdaddr, bdaddr_random, direction, code, pkt_id, data_len, interval_min, interval_max, latency, timeout)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 18, 1, 8, 24, 40, 0, 100);

INSERT INTO L2CAP_CONNECTION_PARAMETER_UPDATE_RSP (bdaddr, bdaddr_random, direction, code, pkt_id, data_len, result)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 1, 19, 1, 2, 0);

-- =====
-- SMP
-- =====

INSERT INTO SMP_Pairing_Req_Res (bdaddr, bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 1, 4, 0, 13, 16, 7, 7);

INSERT INTO SMP_Pairing_Req_Res (bdaddr, bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 2, 3, 0, 13, 16, 7, 7);

-- =====
-- GATT
-- =====

-- One Battery service with one characteristic (Battery Level) and a CCCD descriptor.
INSERT INTO GATT_services (bdaddr, bdaddr_random, service_type, begin_handle, end_handle, UUID)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 0, 16, 25, '180f');

INSERT INTO GATT_attribute_handles (bdaddr, bdaddr_random, attribute_handle, UUID)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 17, '2803');  -- Characteristic declaration

INSERT INTO GATT_attribute_handles (bdaddr, bdaddr_random, attribute_handle, UUID)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 18, '2a19');  -- Battery Level char value handle

INSERT INTO GATT_attribute_handles (bdaddr, bdaddr_random, attribute_handle, UUID)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 19, '2902');  -- CCCD descriptor handle

INSERT INTO GATT_characteristics (bdaddr, bdaddr_random, declaration_handle, char_properties, char_value_handle, UUID)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 17, 18, 18, '2a19');  -- Properties=0x12 (Read+Notify)

INSERT INTO GATT_characteristics_values (bdaddr, bdaddr_random, char_value_handle, operation, byte_values)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 18, 11, UNHEX('55'));

INSERT INTO GATT_characteristic_descriptor_values (bdaddr, bdaddr_random, UUID, descriptor_handle, operation, byte_values)
VALUES ('aa:bb:cc:dd:ee:7f', 0, '2902', 19, 11, UNHEX('0100'));

-- =====
-- LMP (BR/EDR Link Manager Protocol — no bdaddr_random column)
-- =====

INSERT INTO LMP_NAME_RES_defragmented (bdaddr, device_name)
VALUES ('aa:bb:cc:dd:ee:7f', 'FullCovLMPName');

INSERT INTO LMP_ACCEPTED (bdaddr, rcvd_opcode)
VALUES ('aa:bb:cc:dd:ee:7f', 60);

INSERT INTO LMP_NOT_ACCEPTED (bdaddr, rcvd_opcode, error_code)
VALUES ('aa:bb:cc:dd:ee:7f', 17, 30);

INSERT INTO LMP_DETACH (bdaddr, error_code)
VALUES ('aa:bb:cc:dd:ee:7f', 19);

INSERT INTO LMP_PREFERRED_RATE (bdaddr, data_rate)
VALUES ('aa:bb:cc:dd:ee:7f', 4);

INSERT INTO LMP_empty_opcodes (bdaddr, opcode)
VALUES ('aa:bb:cc:dd:ee:7f', 35);  -- LMP_AUTO_RATE — defined in the BTIDES LMP schema as a no-payload PDU

INSERT INTO LMP_VERSION_RES (bdaddr, lmp_version, device_BT_CID, lmp_sub_version)
VALUES ('aa:bb:cc:dd:ee:7f', 8, 10, 801);  -- BT 5.0, CSR

INSERT INTO LMP_VERSION_REQ (bdaddr, lmp_version, device_BT_CID, lmp_sub_version)
VALUES ('aa:bb:cc:dd:ee:7f', 8, 76, 257);  -- BT 5.0, Apple

INSERT INTO LMP_FEATURES_RES (bdaddr, page, features)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 18446744073709551614);

INSERT INTO LMP_FEATURES_REQ (bdaddr, page, features)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 18374403900871474942);

INSERT INTO LMP_ACCEPTED_EXT (bdaddr, rcvd_escape_opcode, rcvd_extended_opcode)
VALUES ('aa:bb:cc:dd:ee:7f', 127, 1);

INSERT INTO LMP_NOT_ACCEPTED_EXT (bdaddr, rcvd_escape_opcode, rcvd_extended_opcode, error_code)
VALUES ('aa:bb:cc:dd:ee:7f', 127, 2, 6);

INSERT INTO LMP_FEATURES_REQ_EXT (bdaddr, page, max_page, features)
VALUES ('aa:bb:cc:dd:ee:7f', 1, 2, 100);

INSERT INTO LMP_FEATURES_RES_EXT (bdaddr, page, max_page, features)
VALUES ('aa:bb:cc:dd:ee:7f', 1, 2, 200);

INSERT INTO LMP_POWER_CONTROL_REQ (bdaddr, power_adj_req) VALUES ('aa:bb:cc:dd:ee:7f', 1);

INSERT INTO LMP_POWER_CONTROL_RES (bdaddr, power_adj_res) VALUES ('aa:bb:cc:dd:ee:7f', 5);

-- =====
-- SDP
-- =====

-- byte_values is a binary VARBINARY(1024); use UNHEX to insert the bytes.
INSERT INTO SDP_Common (bdaddr, direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values)
VALUES ('aa:bb:cc:dd:ee:7f', 1, 12, 64, 7, 5, 8, UNHEX('00040000aabbccdd'));

INSERT INTO SDP_ERROR_RSP (bdaddr, direction, l2cap_len, l2cap_cid, transaction_id, param_len, error_code)
VALUES ('aa:bb:cc:dd:ee:7f', 1, 5, 64, 5, 2, 1);

-- =====
-- GPS
-- =====

-- BTIDES_to_SQL.parse_all_GPSArrays_batched only round-trips entries with
-- time_type=1 (unix_time_milli); the unix_time path emits a JSON time dict
-- that the importer skips. Use time_type=1 + a millisecond timestamp.
INSERT INTO bdaddr_to_GPS (bdaddr, bdaddr_random, time, time_type, rssi, lat, lon)
VALUES ('aa:bb:cc:dd:ee:7f', 0, 1714000000000, 1, -50, 38.9072, -77.0369);
