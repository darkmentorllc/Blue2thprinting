#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

FILES="$@"

echo "passed in " ${args[0]}

BTMONLOGS="/home/user/Scripts/Blue2thprinting/logs/btmon/"
GPSPIPELOGS="/home/user/Scripts/Blue2thprinting/logs/gpspipe/"

# Reset the files and db tables
rm /tmp/advspecific.csv
rm /tmp/gpsspecific.csv
rm /tmp/specific.csv
mysql --database='bt' --execute='ALTER DATABASE bt CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci'
mysql --database='bt' --execute='DROP TABLE adv_specific'
mysql --database='bt' --execute='DROP TABLE gps_specific'
mysql --database='bt' --execute="CREATE TABLE adv_specific (id INT NOT NULL AUTO_INCREMENT, capture_date_unix INT(11) NOT NULL, rssi TINYINT NOT NULL, bdaddr_random VARCHAR(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL, bdaddr VARCHAR(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL, device_name VARCHAR(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL, PRIMARY KEY (id)) CHARACTER SET utf8mb3;"
#mysql --database='bt' --execute='ALTER TABLE adv_specific CONVERT TO CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci'
mysql --database='bt' --execute='CREATE TABLE gps_specific (unix_host_time INT(11) NOT NULL, unix_gps_time INT(11) NOT NULL, lat DECIMAL(10, 8) NOT NULL, lon DECIMAL(11, 8) NOT NULL, PRIMARY KEY (unix_host_time));'


for file in $FILES
do
	echo "Processing " ${file}
	# Process the specific file for advertisements. Output goes into /tmp/advspecific.csv
	echo ${file} | xargs -n 1 -I {} tshark -r $BTMONLOGS{}.bin -Y 'btcommon.eir_ad.entry.type >= 0x08 && btcommon.eir_ad.entry.type <= 0x09 && bthci_evt.le_meta_subevent == 0x02 && btcommon.eir_ad.entry.device_name != S80744e222b66cb48C' -T fields -e frame.time_epoch -e bthci_evt.rssi -e bthci_evt.le_peer_address_type -e bthci_evt.bd_addr -e btcommon.eir_ad.entry.device_name -E separator=, -E quote=d >> /tmp/advspecific.csv
        #bbe -e 's/\xFF/XcleanedX/g' /tmp/advspecific.csv > /tmp/cleaned.csv
	#bbe -e 's/\xED\x84/XcleanedX/g' /tmp/cleaned.csv > /tmp/advspecific.csv
        #mv /tmp/cleaned.csv /tmp/advspecific.csv

	# Insert data into database
	mysql --database='bt' --execute="LOAD DATA INFILE '/tmp/advspecific.csv' INTO TABLE adv_specific FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (capture_date_unix,rssi,bdaddr_random,bdaddr,device_name);"

	# Process the specific gps coordinates, Output goes into /tmp/gpsspecific.csv
	echo ${file} | xargs -n 1 -I {} python /home/user/Blue2thprinting/Scripts/gpspipe2mysql.py $GPSPIPELOGS{}.txt >> /tmp/gpsspecific.csv

	# Insert data into database
	mysql --database='bt' --execute="LOAD DATA INFILE '/tmp/gpsspecific.csv' REPLACE INTO TABLE gps_specific FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (@host_time,@gps_time,lat,lon) SET unix_host_time = UNIX_TIMESTAMP(@host_time), unix_gps_time = UNIX_TIMESTAMP(@gps_time);"
done

#Join the device detection to the GPS coordinates and export it
mysql --database='bt' --execute="SELECT device_name, bdaddr, rssi, lat, lon FROM adv_specific INNER JOIN gps_specific ON adv_specific.capture_date_unix = gps_specific.unix_host_time INTO OUTFILE '/tmp/specific.csv' FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n';"

python3 plot_specific.py

#remove common meta-character polution which stops mapping from working
sed -e "s/
//" bt_map.html > /tmp/a.html
sed -e "s///" /tmp/a.html > /tmp/b.html
mv /tmp/b.html bt_map.html
