#!/bin/bash

# input: ./usb.ids.txt (from http://www.linux-usb.org/usb.ids)
# output: /tmp/USB_CID_to_company.csv
python3 ./process_Linux_USB_company_names.py

mysql -u user -pa --database='bt2' --execute="CREATE TABLE USB_CID_to_company (id INT NOT NULL AUTO_INCREMENT, device_USB_CID INT NOT NULL, company_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (device_USB_CID, company_name));"
mysql -u user -pa --database='bttest' --execute="CREATE TABLE USB_CID_to_company (id INT NOT NULL AUTO_INCREMENT, device_USB_CID INT NOT NULL, company_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (device_USB_CID, company_name));"

mysql -u user -pa --database='bt2' --execute="LOAD DATA INFILE '/tmp/USB_CID_to_company.csv' IGNORE INTO TABLE USB_CID_to_company FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (@device_USB_CID, company_name) SET device_USB_CID = CAST(CONV(REPLACE(@device_USB_CID, '0x', ''), 16, 10) AS UNSIGNED);"
mysql -u user -pa --database='bttest' --execute="LOAD DATA INFILE '/tmp/USB_CID_to_company.csv' IGNORE INTO TABLE USB_CID_to_company FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (@device_USB_CID, company_name) SET device_USB_CID = CAST(CONV(REPLACE(@device_USB_CID, '0x', ''), 16, 10) AS UNSIGNED);"
