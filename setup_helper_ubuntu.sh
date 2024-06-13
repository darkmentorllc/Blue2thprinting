#!/bin/bash

if [ "$EUID" -ne 0 ]; then
    echo "This script needs to be run with sudo"
    exit 1
fi

echo "============================================================================"
echo "This script assumes you're running a Debian-derivative system that uses apt!"
echo "============================================================================"
echo ""
echo "===================================="
echo "Installing all prerequisite software"
echo "===================================="
#sudo apt-get install -y python3-pip python3-mysql.connector python3-docutils tshark mariadb-server gpsd gpsd-clients expect git net-tools openssh-server libusb-dev libdbus-1-dev libglib2.0-dev libudev-dev libical-dev libreadline-dev autoconf python2.7 
#sudo pip3 install gmplot inotify_simple

echo ""
echo "====================================================================================================================================="
echo "Fixing this repository if you didn't clone it with a recursive pull of the submodules (which gets the latest Bluetooth assigned IDs)."
echo "====================================================================================================================================="
#git submodule update --init --recursive

# Next commands assume they run from the Analysis folder
cd ./Analysis

echo ""
echo "==================================="
echo "Creating all MySQL database tables."
echo "==================================="
./create_all_db_tables.sh

echo ""
echo "===================================="
echo "Importing IEEE OUI list to database."
echo "===================================="
./process_OUI_lists.sh ./oui.txt
echo "==========================================================="
echo "You should see 10 (XEROX) IEEE OUIs after the next command:"
echo "==========================================================="
mysql -u user -pa --database='bt' --execute="SELECT * from IEEE_bdaddr_to_company limit 10;"

echo ""
echo "==================================================="
echo "Filling database with Bluetooth 16-bit company IDs."
echo "==================================================="
./translator_fill_UUID16_to_company.sh
echo "======================================================================"
echo "You should see 10 16-bit Bluetooth company IDs after the next command:"
echo "======================================================================"
mysql -u user -pa --database='bt' --execute="SELECT * from UUID16_to_company limit 10;"
