#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

if [ "$EUID" -ne 0 ]; then
    echo "This script needs to be run with sudo"
    exit 1
fi

USERNAME="$SUDO_USER"
echo "Username detected as '$USERNAME'."

if [[ ! -d "/Users/$USERNAME/Blue2thprinting" && ! -d "/Users/$USERNAME/blue2thprinting" ]]; then
    echo "All Blue2thprinting code assumes that Blue2thprinting has been checked out to your home directory (/home/$USERNAME/Blue2thprinting)"
    echo "Please move the folder to /home/$USERNAME/Blue2thprinting and re-run this script from there."
    exit -1
fi

brew -v
if [ ! $? ]; then
    echo "================================================================================================================================================="
    echo "This script assumes you're running on macOS and that you have brew already installed from https://brew.sh/. Install brew to continue."
    echo "================================================================================================================================================="
    exit -1
fi

mysql --version
if [ ! $? ]; then
    echo "================================================================================================================================================="
    echo "This script assumes you've already run \"brew install mysql\" on macOS per the instructions in the git repository. Please run that first."
    echo "================================================================================================================================================="
    exit -1
fi

tshark --version
if [ ! $? ]; then
    echo "================================================================================================================================================="
    echo "This script assumes you've already run \"brew install wireshark\" on macOS per the instructions in the git repository. Please run that first."
    echo "================================================================================================================================================="
    exit -1
fi

python3 -m venv ./venv
source ./venv/bin/activate
pip install jsonschema==4.23 mysql-connector-python pyyaml requests google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client scapy

echo ""
echo "====================================================================================================================================="
echo "Fixing this repository if you didn't clone it with a recursive pull of the submodules (which gets the latest Bluetooth assigned IDs)."
echo "====================================================================================================================================="
git submodule update --init --recursive

# Next commands assume they run from the Analysis folder
cd ./Analysis/one_time_initialization

echo ""
echo "==================================="
echo "Creating all MySQL database tables."
echo "==================================="
#### This will create the less-privileged MySQL user "user", with a password of "a", under which subsequent commands will be run.
#### It will then create all the database tables where imported data will be stored
#### It will give an error message (that can be ignored) if the user or tables are already created
./initialize_database.sh
./initialize_test_database.sh

echo ""
echo "===================================="
echo "Importing IEEE OUI list to database."
echo "===================================="
#### This will just import a
#### The oui.txt came from "https://standards-oui.ieee.org/oui/oui.txt"
#### oui.txt will periodically be updated
./translator_fill_IEEE_bdaddr_to_company.sh ./oui.txt

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

echo ""
echo "==================================================================================================="
echo "Filling database with BLEScope research paper's mappings between UUI128s and Android package names."
echo "==================================================================================================="
/usr/bin/python3 ./translator_fill_BLEScope_UUID128s.py

echo "============================================================================================"
echo "You should see 10 mappings between UUI128s and Android package names after the next command:"
echo "============================================================================================"
mysql -u user -pa --database='bt' --execute="SELECT * from BLEScope_UUID128s limit 10;"

echo ""
echo "[--------------------------------------------------]"
echo "Everything seems to have completed successfully! \o/"
echo "[--------------------------------------------------]"
