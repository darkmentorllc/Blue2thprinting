#!/bin/bash
echo "CSV insertion"
#NOTE: This assumes Service_UUID16_to_company.csv is in the same directory where this is run from
echo "mysql import"
# File needs to be in /tmp else we get "The MySQL server is running with the --secure-file-priv option so it cannot execute this statement"
cp Service_UUID16_to_company.csv /tmp/Service_UUID16_to_company.csv
mysql -u user -pa --database='bt' --execute="drop table UUID16_to_company;"
mysql -u user -pa --database='bt' --execute="CREATE TABLE UUID16_to_company (id INT NOT NULL AUTO_INCREMENT, str_UUID16_CID VARCHAR(6) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, company_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (str_UUID16_CID, company_name));"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/Service_UUID16_to_company.csv' IGNORE INTO TABLE UUID16_to_company FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' IGNORE 1 LINES (str_UUID16_CID, company_name);"
mysql -u user -pa --database='bttest' --execute="drop table UUID16_to_company;"
mysql -u user -pa --database='bttest' --execute="CREATE TABLE UUID16_to_company (id INT NOT NULL AUTO_INCREMENT, str_UUID16_CID VARCHAR(6) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, company_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, PRIMARY KEY (id), UNIQUE KEY uni_name (str_UUID16_CID, company_name));"
mysql -u user -pa --database='bttest' --execute="LOAD DATA INFILE '/tmp/Service_UUID16_to_company.csv' IGNORE INTO TABLE UUID16_to_company FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' IGNORE 1 LINES (str_UUID16_CID, company_name);"
