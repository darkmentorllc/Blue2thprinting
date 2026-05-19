#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
##########################################

if [ "$EUID" -ne 0 ]; then
    echo "This script needs to be run with sudo"
    exit 1
fi

USERNAME="$SUDO_USER"
BASE_PATH="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
echo "Username detected as '$USERNAME'."
echo "Repo detected at '$BASE_PATH'."

if [[ ! -f "$BASE_PATH/Analysis/handle_venv.py" ]]; then
    echo "Could not find Analysis/handle_venv.py relative to this script. Run setup from inside a Blue2thprinting checkout."
    exit -1
fi

apt -v
if [ ! $? ]; then
    echo "================================================================================================================================================="
    echo "This script assumes you're running a Debian-derivative system that uses apt (like Ubuntu)."
    echo "If you want to run it on a non-debian-derivative, you will need to read this script and adjust commands & prerequisite software to your platform."
    echo "================================================================================================================================================="
    exit -1
fi

echo ""
echo "====================================================================================================================================="
echo "Recursive pull of the submodules (which gets the latest Bluetooth assigned IDs, CLUES data, etc)."
echo "====================================================================================================================================="
git submodule update --init --recursive

sudo DEBIAN_FRONTEND=noninteractive apt-get -y install tshark
sudo apt-get install -y python3-pip python3-venv python3-docutils mariadb-server

echo ""
echo "====================================================================="
echo "Installing Rust toolchain (needed to build Analysis/BTIDES_Schema/rust/ workspace)."
echo "====================================================================="
# The Rust workspace uses jsonschema 0.30 which needs rustc >= 1.79;
# Debian/Ubuntu's apt-shipped rustc can be too old, so use rustup to
# install the current stable toolchain into the invoking user's home.
# build-essential / curl / pkg-config are needed for native crate compiles.
sudo apt-get install -y build-essential curl ca-certificates pkg-config
if ! sudo -u "$USERNAME" bash -lc 'command -v cargo' >/dev/null 2>&1; then
    sudo -u "$USERNAME" sh -c "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --profile minimal"
fi
CARGO_BIN="$(sudo -u "$USERNAME" bash -lc 'command -v cargo' 2>/dev/null)"
if [[ -z "$CARGO_BIN" ]]; then
    echo "Rust toolchain install failed — 'cargo' is not on \$PATH for $USERNAME."
    exit -1
fi
echo "Using cargo: $CARGO_BIN"

python3 -m venv ./venv
source ./venv/bin/activate
# Even for distributions like Ubuntu 24.04 which package jsonschema, it seems they're not at a new enough version to support a constructor we need. So I'm now requiring installation of this version.
pip install jsonschema==4.23 mysql-connector pyyaml requests google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client colorama

cd Analysis

# Using my branch because I've got changes that haven't been upstreamed
#git clone https://github.com/XenoKovah/scapy.git
cd scapy
pip install .
cd ..

# Next commands assume they run from the Analysis folder
cd ./one_time_initialization

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
mysql -u user -pa --database='bt2' --execute="SELECT * from IEEE_bdaddr_to_company limit 10;"

echo ""
echo "==================================================="
echo "Filling database with Bluetooth 16-bit company IDs."
echo "==================================================="
./translator_fill_UUID16_to_company.sh
echo "======================================================================"
echo "You should see 10 16-bit Bluetooth company IDs after the next command:"
echo "======================================================================"
mysql -u user -pa --database='bt2' --execute="SELECT * from UUID16_to_company limit 10;"

echo ""
echo "==================================================================================================="
echo "Filling database with BLEScope research paper's mappings between UUID128s and Android package names."
echo "==================================================================================================="
mysql -u user -pa --database='bt2' --execute="DROP table BLEScope_UUID128s" # This is just so I can re-run this file multiple times for testing
mysql -u user -pa --database='bt2' < BLEScope_UUID128s.sql
mysql -u user -pa --database='bttest' --execute="DROP table BLEScope_UUID128s" # This is just so I can re-run this file multiple times for testing
mysql -u user -pa --database='bttest' < BLEScope_UUID128s.sql

echo "============================================================================================"
echo "You should see 10 mappings between UUI128s and Android package names after the next command:"
echo "============================================================================================"
mysql -u user -pa --database='bt2' --execute="SELECT * from BLEScope_UUID128s limit 10;"

echo ""
echo "==================================================="
echo "Filling database with USB 16-bit company IDs."
echo "==================================================="
./translator_fill_USB_CID_to_company.sh
echo "============================================================================================"
echo "You should see 10 mappings between UUI128s and Android package names after the next command:"
echo "============================================================================================"
mysql -u user -pa --database='bt2' --execute="SELECT * from USB_CID_to_company order by id desc limit 10;"

echo ""
echo "================================================================================="
echo "Building the Rust BTIDES converters. Two Cargo workspaces:"
echo "  * Analysis/BTIDES_Schema/rust/ — schema-agnostic converters"
echo "      (pcap-to-BTIDES, hci-to-BTIDES, sdp-to-BTIDES, library crates)"
echo "  * Analysis/rust/ — Blue2thprinting-specific tools"
echo "      (wigle-to-BTIDES, import-all-BTIDES)"
echo "Release builds, may take a minute or two."
echo "================================================================================="
sudo -u "$USERNAME" bash -lc "cd '$BASE_PATH/Analysis/BTIDES_Schema/rust' && cargo build --release"
if [ $? -ne 0 ]; then
    echo "cargo build failed in Analysis/BTIDES_Schema/rust. Check the output above."
    exit -1
fi
sudo -u "$USERNAME" bash -lc "cd '$BASE_PATH/Analysis/rust' && cargo build --release"
if [ $? -ne 0 ]; then
    echo "cargo build failed in Analysis/rust. Check the output above."
    exit -1
fi
echo "Built binaries are at:"
echo "  $BASE_PATH/Analysis/BTIDES_Schema/rust/target/release/"
echo "  $BASE_PATH/Analysis/rust/target/release/"

echo "======================================================="
echo "Correcting permissions on the Blue2thprinting folder."
echo "======================================================="
sudo chown -R "$USERNAME" "$BASE_PATH"

echo ""
echo "[--------------------------------------------------]"
echo "Everything seems to have completed successfully! \o/"
echo "[--------------------------------------------------]"
