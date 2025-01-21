#!/bin/bash


# Start from the file (like oui.txt from IEEE from https://standards-oui.ieee.org/oui/oui.txt)
# Only keep the lines that have "(hex)" on them, since that contains the hex string like XX-XX-XX which is easiest to convert to XX:XX:XX to match db
grep "(hex)" $1 > /tmp/f1.txt
# Do the conversion of XX-XX-XX -> XX:XX:XX, drop the "(hex)", and keep the company name. Also add quotes so it's csv output like "AA:BB:CC","Company Name"
sed -E 's/^([0-9A-Fa-f]+)-([0-9A-Fa-f]+)-([0-9A-Fa-f]+)[[:space:]]+\(hex\)[[:space:]]+(.*)$/"\1:\2:\3","\4\"/g' /tmp/f1.txt > /tmp/fixme.txt
# Somehow sed is inserting meta-characters into the file, at the end before the ". Remove them (^M is typed with ctrl-v, ctrl-m)
sed 's/m//g' /tmp/fixme.txt > /tmp/d1.txt
echo "Importing IEEE OUIs into IEEE_bdaddr_to_company"bdaddr
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/d1.txt'  IGNORE INTO TABLE IEEE_bdaddr_to_company FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, company_name);"
mysql -u user -pa --database='bttest' --execute="LOAD DATA INFILE '/tmp/d1.txt'  IGNORE INTO TABLE IEEE_bdaddr_to_company FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, company_name);"
