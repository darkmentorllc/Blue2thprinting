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
# The Rust workspaces need jsonschema 0.30 (rustc >= 1.79) and can only read
# v4 Cargo.lock files (cargo >= 1.78). Debian/Ubuntu's apt-shipped cargo is
# frequently older — e.g. Ubuntu 24.04 ships 1.75, which can't even parse the
# lock files ("lock file version 4 requires -Znext-lockfile-bump"). So we
# require cargo >= 1.79 and install the current stable toolchain via rustup
# when the system cargo is missing OR too old (not merely missing).
# build-essential / curl / pkg-config are needed for native crate compiles.
sudo apt-get install -y build-essential curl ca-certificates pkg-config

# Returns 0 only if a cargo >= 1.79 is already available to $USERNAME.
cargo_is_recent_enough() {
    local ver major minor
    ver="$(sudo -u "$USERNAME" bash -lc 'command -v cargo >/dev/null 2>&1 && cargo --version' 2>/dev/null | awk '{print $2}')"
    [[ -z "$ver" ]] && return 1
    major="${ver%%.*}"
    minor="${ver#*.}"; minor="${minor%%.*}"
    [[ "${major:-0}" -gt 1 ]] && return 0
    [[ "${major:-0}" -eq 1 && "${minor:-0}" -ge 79 ]] && return 0
    return 1
}

if ! cargo_is_recent_enough; then
    echo "No cargo >= 1.79 found for $USERNAME (the apt-shipped cargo is often too old); installing the current stable toolchain via rustup."
    sudo -u "$USERNAME" sh -c "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --profile minimal"
fi

# Prefer the rustup cargo (~/.cargo/bin) over any older /usr/bin/cargo, and use
# this explicit path for the builds below so they can't silently fall back to
# a too-old system cargo regardless of PATH ordering.
USER_HOME="$(eval echo ~"$USERNAME")"
if [[ -x "$USER_HOME/.cargo/bin/cargo" ]]; then
    CARGO_BIN="$USER_HOME/.cargo/bin/cargo"
else
    CARGO_BIN="$(sudo -u "$USERNAME" bash -lc 'command -v cargo' 2>/dev/null)"
fi
if [[ -z "$CARGO_BIN" ]]; then
    echo "Rust toolchain install failed — no usable cargo found for $USERNAME."
    exit -1
fi
echo "Using cargo: $CARGO_BIN ($(sudo -u "$USERNAME" "$CARGO_BIN" --version 2>/dev/null))"

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
echo "Building the Rust BTIDES tools. Three Cargo workspaces:"
echo "  * Analysis/BTIDES_Schema/rust/ — schema-agnostic converters"
echo "      (pcap-to-BTIDES, hci-to-BTIDES, sdp-to-BTIDES, library crates)"
echo "  * Analysis/rust/ — Blue2thprinting-specific tools"
echo "      (wigle-to-BTIDES, import-all-BTIDES)"
echo "  * BTIDALPOOL/ — Rust BTIDALPOOL server + client"
echo "      (btidalpool-server [with sql-ingest], btidalpool-client)"
echo "Release builds, may take a minute or two."
echo "================================================================================="
sudo -u "$USERNAME" bash -lc "cd '$BASE_PATH/Analysis/BTIDES_Schema/rust' && \"$CARGO_BIN\" build --release"
if [ $? -ne 0 ]; then
    echo "cargo build failed in Analysis/BTIDES_Schema/rust. Check the output above."
    exit -1
fi
sudo -u "$USERNAME" bash -lc "cd '$BASE_PATH/Analysis/rust' && \"$CARGO_BIN\" build --release"
if [ $? -ne 0 ]; then
    echo "cargo build failed in Analysis/rust. Check the output above."
    exit -1
fi
# BTIDALPOOL server + client. The server is built with the sql-ingest feature
# so it can ingest uploads into the local bt2/bttest MySQL the way the Python
# server does (the underlying BTIDES-to-SQL crate is pure-Rust MySQL, so no
# system MySQL dev libraries are needed). The client is the merged
# upload/query CLI that the Python shims under BTIDALPOOL/python/ exec.
sudo -u "$USERNAME" bash -lc "cd '$BASE_PATH/BTIDALPOOL' && \"$CARGO_BIN\" build --release -p btidalpool-server --features sql-ingest"
if [ $? -ne 0 ]; then
    echo "cargo build failed in BTIDALPOOL (btidalpool-server). Check the output above."
    exit -1
fi
sudo -u "$USERNAME" bash -lc "cd '$BASE_PATH/BTIDALPOOL' && \"$CARGO_BIN\" build --release -p btidalpool-client"
if [ $? -ne 0 ]; then
    echo "cargo build failed in BTIDALPOOL (btidalpool-client). Check the output above."
    exit -1
fi
echo "Built binaries are at:"
echo "  $BASE_PATH/Analysis/BTIDES_Schema/rust/target/release/"
echo "  $BASE_PATH/Analysis/rust/target/release/"
echo "  $BASE_PATH/BTIDALPOOL/target/release/"

echo "======================================================="
echo "Correcting permissions on the Blue2thprinting folder."
echo "======================================================="
sudo chown -R "$USERNAME" "$BASE_PATH"

echo ""
echo "[--------------------------------------------------]"
echo "Everything seems to have completed successfully! \o/"
echo "[--------------------------------------------------]"
