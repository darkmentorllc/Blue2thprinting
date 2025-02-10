#!/bin/bash

echo "Initial setup"
mysql -u root -e "CREATE USER 'user'@'localhost' IDENTIFIED BY 'a'"
mysql -u root -e "GRANT ALL PRIVILEGES ON *.* TO 'user'@'localhost';"
mysql -u user -pa -e "create database bt2;"

echo "Creating BT Classic tables"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE EIR_bdaddr_to_PSRM (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, page_scan_rep_mode TINYINT NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, page_scan_rep_mode)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE EIR_bdaddr_to_name (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, device_name_type TINYINT NOT NULL, name_hex_str VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, device_name_type, name_hex_str)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE EIR_bdaddr_to_DevID (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, vendor_id_source INT NOT NULL, vendor_id INT NOT NULL, product_id INT NOT NULL, product_version INT NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, vendor_id_source, vendor_id, product_id, product_version)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE EIR_bdaddr_to_tx_power (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, device_tx_power TINYINT NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, device_tx_power)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE EIR_bdaddr_to_CoD (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, class_of_device INT NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, class_of_device)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE EIR_bdaddr_to_UUID16s (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, list_type TINYINT NOT NULL, str_UUID16s VARCHAR(480), PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, list_type, str_UUID16s)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE EIR_bdaddr_to_UUID32s (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, list_type TINYINT NOT NULL, str_UUID32s VARCHAR(100), PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, list_type, str_UUID32s)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE EIR_bdaddr_to_UUID128s (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, list_type TINYINT NOT NULL, str_UUID128s VARCHAR(480), PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, list_type, str_UUID128s)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE EIR_bdaddr_to_flags (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, le_limited_discoverable_mode BOOLEAN NOT NULL, le_general_discoverable_mode BOOLEAN NOT NULL, bredr_not_supported BOOLEAN NOT NULL, le_bredr_support_controller BOOLEAN NOT NULL, le_bredr_support_host BOOLEAN NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE EIR_bdaddr_to_URI (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, uri_hex_str VARCHAR(512) NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, uri_hex_str)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE EIR_bdaddr_to_3d_info (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, byte1 TINYINT UNSIGNED NOT NULL, path_loss TINYINT UNSIGNED NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, byte1, path_loss)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE EIR_bdaddr_to_MSD (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, device_BT_CID INT NOT NULL, manufacturer_specific_data VARCHAR(480) NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, device_BT_CID, manufacturer_specific_data)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE HCI_bdaddr_to_name (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, status TINYINT NOT NULL, name_hex_str VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, status, name_hex_str)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

echo "Creating BT Low Energy tables"
mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_name (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, device_name_type TINYINT NOT NULL, name_hex_str VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, device_name_type, name_hex_str)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_UUID16s_list (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, list_type TINYINT NOT NULL, str_UUID16s VARCHAR(480), PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID16s)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_UUID32s_list (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, list_type TINYINT NOT NULL, str_UUID32s VARCHAR(100), PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID32s)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_UUID128s_list (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, list_type TINYINT NOT NULL, str_UUID128s VARCHAR(480), PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID128s)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_flags (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, le_limited_discoverable_mode BOOLEAN NOT NULL, le_general_discoverable_mode BOOLEAN NOT NULL, bredr_not_supported BOOLEAN NOT NULL, le_bredr_support_controller BOOLEAN NOT NULL, le_bredr_support_host BOOLEAN NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_tx_power (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, device_tx_power TINYINT NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, device_tx_power)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_CoD (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, class_of_device INT NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, class_of_device)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_appearance (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, appearance SMALLINT UNSIGNED NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, appearance)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_connect_interval (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, interval_min SMALLINT UNSIGNED NOT NULL, interval_max SMALLINT UNSIGNED NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, interval_min, interval_max)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_UUID16_service_solicit (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, str_UUID16s VARCHAR(480), PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, str_UUID16s)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_UUID16_service_data (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, ACID_length TINYINT NOT NULL, UUID16_hex_str VARCHAR(4), service_data_hex_str VARCHAR(480), PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, ACID_length, UUID16_hex_str, service_data_hex_str)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_UUID32_service_solicit (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, str_UUID32s VARCHAR(480), PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, str_UUID32s)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_UUID32_service_data (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, ACID_length TINYINT NOT NULL, UUID32_hex_str VARCHAR(8), service_data_hex_str VARCHAR(480), PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, ACID_length, UUID32_hex_str, service_data_hex_str)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_UUID128_service_solicit (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, str_UUID128s VARCHAR(480), PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, str_UUID128s)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_UUID128_service_data (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, ACID_length TINYINT NOT NULL, UUID128_hex_str VARCHAR(32), service_data_hex_str VARCHAR(480), PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, ACID_length, UUID128_hex_str, service_data_hex_str)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_public_target_bdaddr (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, public_bdaddr VARCHAR(20) NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, public_bdaddr)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_random_target_bdaddr (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, random_bdaddr VARCHAR(20) NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, random_bdaddr)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_other_le_bdaddr (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, other_bdaddr VARCHAR(20), other_bdaddr_random BOOLEAN NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, other_bdaddr, other_bdaddr_random)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_role (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, role TINYINT UNSIGNED NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, role)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_URI (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, uri_hex_str VARCHAR(512) NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, uri_hex_str)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_3d_info (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, byte1 TINYINT UNSIGNED NOT NULL, path_loss TINYINT UNSIGNED NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, byte1, path_loss)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LE_bdaddr_to_MSD (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) NOT NULL, bdaddr_random BOOLEAN NOT NULL, le_evt_type TINYINT UNSIGNED NOT NULL, device_BT_CID INT NOT NULL, manufacturer_specific_data VARCHAR(480) NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, le_evt_type, device_BT_CID, manufacturer_specific_data)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

echo "Creating GATT tables"
mysql -u user -pa --database='bt2' --execute="CREATE TABLE GATT_services (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, bdaddr_random BOOLEAN NOT NULL, service_type SMALLINT UNSIGNED NOT NULL, begin_handle SMALLINT UNSIGNED NOT NULL, end_handle SMALLINT UNSIGNED NOT NULL, UUID CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, service_type, begin_handle, end_handle, UUID)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE GATT_attribute_handles (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, bdaddr_random BOOLEAN NOT NULL, attribute_handle SMALLINT UNSIGNED NOT NULL, UUID CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, attribute_handle, UUID)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE GATT_characteristics (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, bdaddr_random BOOLEAN NOT NULL, declaration_handle SMALLINT UNSIGNED NOT NULL, char_properties TINYINT UNSIGNED NOT NULL, char_value_handle SMALLINT UNSIGNED NOT NULL, UUID CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, declaration_handle, char_properties, char_value_handle, UUID)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE GATT_characteristics_values (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, bdaddr_random BOOLEAN NOT NULL, char_value_handle SMALLINT UNSIGNED NOT NULL, operation TINYINT UNSIGNED NOT NULL, byte_values BLOB NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, char_value_handle, operation, byte_values(1024))) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

echo "Creating SMP tables"
mysql -u user -pa --database='bt2' --execute="CREATE TABLE SMP_Pairing_Req_Res (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, bdaddr_random BOOLEAN NOT NULL, opcode TINYINT UNSIGNED NOT NULL, io_cap TINYINT UNSIGNED NOT NULL, oob_data TINYINT UNSIGNED NOT NULL, auth_req TINYINT UNSIGNED NOT NULL, max_key_size TINYINT UNSIGNED NOT NULL, initiator_key_dist TINYINT UNSIGNED NOT NULL, responder_key_dist TINYINT UNSIGNED NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

echo "Creating SDP tables"
mysql -u user -pa --database='bt2' --execute="CREATE TABLE SDP_SERVICE_SEARCH_ATTR_REQ_RSP (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, direction TINYINT UNSIGNED NOT NULL, l2cap_len SMALLINT UNSIGNED NOT NULL, l2cap_cid SMALLINT UNSIGNED NOT NULL, pdu_id TINYINT UNSIGNED NOT NULL, transaction_id SMALLINT UNSIGNED NOT NULL, param_len SMALLINT UNSIGNED NOT NULL, byte_values BLOB NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values(1024))) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

echo "Creating BLE LL CTRL tables"
mysql -u user -pa --database='bt2' --execute="CREATE TABLE LL_VERSION_IND (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, bdaddr_random BOOLEAN NOT NULL, ll_version TINYINT UNSIGNED NOT NULL, device_BT_CID SMALLINT UNSIGNED NOT NULL, ll_sub_version SMALLINT UNSIGNED NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, ll_version, device_BT_CID, ll_sub_version)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LL_UNKNOWN_RSP (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, bdaddr_random BOOLEAN NOT NULL, unknown_opcode TINYINT UNSIGNED NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, unknown_opcode)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LL_FEATUREs (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, bdaddr_random BOOLEAN NOT NULL, opcode TINYINT UNSIGNED NOT NULL, features BIGINT UNSIGNED NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, opcode, features)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LL_PHYs (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, bdaddr_random BOOLEAN NOT NULL, opcode TINYINT UNSIGNED NOT NULL, direction BOOLEAN NOT NULL, tx_phys SMALLINT UNSIGNED NOT NULL, rx_phys SMALLINT UNSIGNED NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, opcode, direction, tx_phys, rx_phys)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LL_PINGs (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, bdaddr_random BOOLEAN NOT NULL, opcode TINYINT UNSIGNED NOT NULL, direction BOOLEAN NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, opcode, direction)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LL_LENGTHs (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, bdaddr_random BOOLEAN NOT NULL, opcode TINYINT UNSIGNED NOT NULL, max_rx_octets SMALLINT UNSIGNED NOT NULL, max_rx_time SMALLINT UNSIGNED NOT NULL, max_tx_octets SMALLINT UNSIGNED NOT NULL, max_tx_time SMALLINT UNSIGNED NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, bdaddr_random, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time) ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

echo "Creating BTC LMP tables"
mysql -u user -pa --database='bt2' --execute="CREATE TABLE LMP_VERSION_RES (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, lmp_version TINYINT UNSIGNED NOT NULL, device_BT_CID SMALLINT UNSIGNED NOT NULL, lmp_sub_version SMALLINT UNSIGNED NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, lmp_version, device_BT_CID, lmp_sub_version)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LMP_FEATURES_RES (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, page TINYINT UNSIGNED NOT NULL, features BIGINT UNSIGNED NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, page, features)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LMP_FEATURES_RES_EXT (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, page TINYINT UNSIGNED NOT NULL, max_page TINYINT UNSIGNED NOT NULL, features BIGINT UNSIGNED NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, page, features)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE LMP_NAME_RES (id INT NOT NULL AUTO_INCREMENT, bdaddr CHAR(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, device_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, device_name)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

echo "Creating other helper tables"
mysql -u user -pa --database='bt2' --execute="CREATE TABLE IEEE_bdaddr_to_company (id INT NOT NULL AUTO_INCREMENT, bdaddr VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, company_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (bdaddr, company_name)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

mysql -u user -pa --database='bt2' --execute="CREATE TABLE UUID16_to_company (id INT NOT NULL AUTO_INCREMENT, str_UUID16_CID VARCHAR(6) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, company_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (str_UUID16_CID, company_name)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# uuid_type 1 is a service, uuid_type 2 is a characteristic. Note that this is using "str_UUID128" not "str_UUID128s", because each entry will be a single UUID128
mysql -u user -pa --database='bt2' --execute="CREATE TABLE BLEScope_UUID128s (id INT NOT NULL AUTO_INCREMENT, android_pkg_name VARCHAR(100) NOT NULL, uuid_type TINYINT NOT NULL, str_UUID128 VARCHAR(37) NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (android_pkg_name, uuid_type, str_UUID128)) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
