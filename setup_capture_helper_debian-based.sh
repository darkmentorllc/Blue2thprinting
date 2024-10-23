#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################
# Tested on Ubuntu 24.04, Raspbian Buster & Bookworm

if [ "$EUID" -ne 0 ]; then
    echo "This script needs to be run with sudo"
    exit -1
fi

USERNAME="$SUDO_USER"
echo "Username detected as '$USERNAME'."

if [ ! -d "/home/$USERNAME/Blue2thprinting" && ! -d "/home/$USERNAME/blue2thprinting" ]; then
    echo "All Blue2thprinting code assumes that Blue2thprinting has been checked out to your home directory (/home/$USERNAME/Blue2thprinting)"
    echo "Please move the folder to /home/$USERNAME/Blue2thprinting and re-run this script from there."
    exit -1
fi

apt -v
if [ $? != 0 ]; then
    echo "================================================================================================================================================="
    echo "This script assumes you're running a Debian-derivative system that uses apt (like Ubuntu)."
    echo "If you want to run it on a non-debian-derivative, you will need to read this script and adjust commands & prerequisite software to your platform."
    echo "================================================================================================================================================="
    exit -1
fi

echo ""
echo "===================================="
echo "Installing all prerequisite software"
echo "===================================="
sudo apt-get update
# Suppress the faux-GUI prompt
echo "wireshark-common wireshark-common/install-setuid boolean true" | sudo debconf-set-selections
sudo DEBIAN_FRONTEND=noninteractive apt-get -y install tshark
sudo apt-get install -y python3-pip python3-docutils mariadb-server gpsd gpsd-clients expect git net-tools openssh-server libusb-dev libdbus-1-dev libglib2.0-dev libudev-dev libical-dev libreadline-dev autoconf python3-gmplot python3-intelhex
if [ $? != 0 ]; then
    echo ""
    echo "Blue2thprinting: AN ERROR OCCURRED with prerequisite software installation. Resolve error messages above."
    exit -1
fi
echo "  Done"

# Conditionally install the packages which differ from distro to distro
### inotify
dpkg -l | grep -q '^ii  python3-inotify'
if [ $? != 0 ]; then
    echo "  NOTE: This distribution is missing the python3-inotify package. This would prevent the code from working correctly, and is fatal. Attempting to install through pip instead."
    pip3 install inotify
    if [ $? != 0 ]; then
        echo "  Could not install inotify. Tool will not work without it."
        echo "  This is known to not be packaged by Ubuntu 24.04/Raspbian Bookworm and to require using the --break-system-packages option to install."
        while true; do
            read -p "Do you want to install with --break-system-packages (y/n): " user_input
            case "$user_input" in
                [Yy]* )
                    pip3 install inotify --break-system-packages
                    if [ $? != 0 ]; then
                        echo "  Could not install inotify. Tool will not work without it. Exiting."
                        exit -1
                    fi
                    break
                    ;;
                [Nn]* )
                    echo "  Could not install inotify. Tool will not work without it. Exiting."
                    exit -1
                    ;;
                * )
                    echo "Please answer y or n."
                    ;;
            esac
        done
    fi
else
    sudo apt-get install -y python3-inotify
fi

### mysql-connector
dpkg -l | grep -q '^ii  python3-mysql.connector'
if [ $? != 0 ]; then
    echo "  NOTE: This distribution is missing the python3-mysql.connector package. This may cause issues for data analysis. Attempting to install through pip instead."
    pip3 install mysql-connector
    if [ $? != 0 ]; then
        echo "  Could not install mysql-connector. Tool will not work without it."
        echo "  This is known to not be packaged by Ubuntu 24.04/Raspbian Bookworm and to require using the --break-system-packages option to install."
        while true; do
            read -p "Do you want to install with --break-system-packages (y/n): " user_input
            case "$user_input" in
                [Yy]* )
                    pip3 install mysql-connector --break-system-packages
                    if [ $? != 0 ]; then
                        echo "  Could not install mysql-connector. Data import to database & analysis will not work without it. Exiting."
                        exit -1
                    fi
                    break
                    ;;
                [Nn]* )
                    echo "  Could not install mysql-connector. Data import to database & analysis will not work without it. Exiting."
                    exit -1
                    ;;
                * )
                    echo "Please answer y or n."
                    ;;
            esac
        done
    fi
else
    sudo apt-get install -y python3-mysql.connector
fi

no_python2=1
### Python 2.7
dpkg -l | grep -q '^ii  python2.7'
if [ $? != 0 ]; then
    echo "  WARNING: This distribution is missing the python2.7 package. This is required for Sweyntooth. If you are not using Sweyntooth for 2thprinting, you can ignore this. If you are, this will prevent it from working."
else
    sudo apt-get install -y python2.7
    python2.7 --version
    if [ $? == 0 ]; then
        $no_python2=0
    fi
fi

echo ""
echo "====================================================================================================================================="
echo "Fixing this repository when it's not cloned with a recursive pull of the submodules (which gets the latest Bluetooth assigned IDs)."
echo "====================================================================================================================================="
#### This git repository includes the Bluetooth SIG's assigned numbers git repo under the ./public subfolder
#### Most people would check it out before seeing that they need to pass the parameter to recurse submodules
#### So I'm just not bothering with telling folks to do that, and just doing it here
cd /home/$USERNAME/Blue2thprinting
git submodule update --init --recursive
echo "  Done"

echo ""
echo "==================================================================================="
echo "Correcting locations which include hardcoded username in a /home/username/... path."
echo "==================================================================================="
#### There's a few places where paths are assumed to be in the user's home dir. This fixes those up.
if [ $USERNAME != "user" ]; then
    echo "Replacing username 'user' with '$USERNAME'."
    cd /home/$USERNAME/Blue2thprinting
    sed -i "s|/home/user/|/home/$USERNAME/|" sweyntooth_bluetooth_low_energy_attacks/LL2thprint.py
    echo "Correcting sweyntooth_bluetooth_low_energy_attacks/LL2thprint.py"
    echo "Correcting bluez-5.66/attrib/gatttool.c"
    sed -i "s|/home/user/|/home/$USERNAME/|" ./bluez-5.66/attrib/gatttool.c
    echo "Correcting bluez-5.66/tools/sdptool.c"
    sed -i "s|/home/user/|/home/$USERNAME/|" ./bluez-5.66/tools/sdptool.c
    echo "Correcting all the scripts in ./Scripts"
    cd /home/$USERNAME/Blue2thprinting/Scripts
    for i in *.sh; do
        echo "  Correcting $i"
        sed -i "s|/home/user/|/home/$USERNAME/|g" "$i";
    done
    for i in *.py; do
        echo "  Correcting $i"
        sed -i "s|/home/user/|/home/$USERNAME/|g" "$i";
    done
    sed -i "s|username = \"user\"|username = \"$USERNAME\"|" central_app_launcher2.py
    echo "Correcting central_app_launcher2.py"
fi
echo "  Done"

echo ""
echo "================================================"
echo "Adding execute permissions to the shell scripts."
echo "================================================"
chmod +x *.sh
echo "  Done"

echo ""
echo "====================================================================="
echo "Appending entry to root crontab to run ~/Scripts/runall.sh at reboot."
echo "====================================================================="
#### This tries to make sure it preserves whatever is already in the crontab
#### and it just appends an entry to run the runall.sh script at reboot
#### which invokes the sub-scripts to run btmon (primary HCI logging),
#### bluetoothctl (primary discovery), and central_app_launcher2.py
#### (orchestration of GATT/SDP/LL/LMP measurements)
if [ ! -f "/home/$USERNAME/Blue2thprinting/Scripts/.cron_added" ]; then
    cron_entry="@reboot /home/$USERNAME/Blue2thprinting/Scripts/runall.sh"
    echo "  Writing backup of existing root crontab to /tmp/crontab.root.bak"
    sudo crontab -u root -l > /tmp/crontab.root.bak
    sudo cp /tmp/crontab.root.bak /tmp/crontab.root.new
    echo "  Appending new entry: $cron_entry"
    echo "$cron_entry" >> /tmp/crontab.root.new
    echo "  Importing new crontab from /tmp/crontab.root.new"
    sudo cat /tmp/crontab.root.new | sudo crontab -u root -
    echo "  Setting flag in /home/$USERNAME/Blue2thprinting/Scripts/.cron_added to avoid re-settting."
    touch "/home/$USERNAME/Blue2thprinting/Scripts/.cron_added"
else
    echo "  Skipped, because already added."
fi

echo ""
echo "================================================================="
echo "Compiling the customized BlueZ gatttool & sdptool & bluetoothctl."
echo "================================================================="
#### I use custom BlueZ utilities to output information in a more machine-parsable format (bluetoothctl & gatttool)
#### Or to log invocations so I can compare how many succeeded vs. failed (gatttool & sdptool)
#### Or to do the equivalent of multiple CLI invocations all in one shot (gatttool)
cd /home/$USERNAME/Blue2thprinting/bluez-5.66
### BlueZ Configuration ###
if [ ! -f "/home/$USERNAME/Blue2thprinting/bluez-5.66/Makefile" ]; then
    echo "  >>>>>>>>>>>>>>>>>>>>>>>>"
    echo "  Beginning configuration."
    echo "  <<<<<<<<<<<<<<<<<<<<<<<<"
    ./configure --prefix=/usr --mandir=/usr/share/man --sysconfdir=/etc --localstatedir=/var --enable-experimental --enable-deprecated
else
    echo "  Makefile present. Configuration already succeeded."
fi
if [ $? != 0 ]; then
    echo "  Something went wrong with the ./configure. Look for an error message, correct it, and try again."
    exit
fi

### Compilation ###
if [ ! -f "/home/$USERNAME/Blue2thprinting/bluez-5.66/attrib/gatttool" ] || [ ! -f "/home/$USERNAME/Blue2thprinting/bluez-5.66/tools/sdptool" ] || [ ! -f "/home/$USERNAME/Blue2thprinting/bluez-5.66/client/bluetoothctl" ]; then
    echo "  >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
    echo "  Beginning compilation (this will take a while!)"
    echo "  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    make -j4
    echo "  >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
    echo "  Testing gatttool runs successfully. If you see the help output, it's working."
    echo "  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    /home/$USERNAME/Blue2thprinting/bluez-5.66/attrib/gatttool --help
    if [ $? != 0 ]; then
        echo "  Something went wrong with the compilation. Look for an error message, correct it, and try again."
        exit
    fi
    echo "  >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
    echo "  Testing sdptool runs successfully. If you see the help output, it's working."
    echo "  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    /home/$USERNAME/Blue2thprinting/bluez-5.66/tools/sdptool --help
    if [ $? != 0 ]; then
        echo "  Something went wrong with the compilation. Look for an error message, correct it, and try again."
        exit
    fi
    echo "  >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
    echo "  Testing custom bluetoothctl runs successfully. If you see the version output = 5.66, it's working."
    echo "  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    /home/$USERNAME/Blue2thprinting/bluez-5.66/client/bluetoothctl --version
    if [ $? != 0 ]; then
        echo "  Something went wrong with the compilation. Look for an error message, correct it, and try again."
        exit
    fi
else
    echo "  gatttool and sdptool and bluetoothctl already exist, skipping recompilation."
fi

echo ""
echo "================================================================="
echo "Compiling the customized BlueZ gatttool & sdptool & bluetoothctl."
echo "================================================================="
#### I use custom BlueZ utilities to output information in a more machine-parsable format (bluetoothctl & gatttool)
#### Or to log invocations so I can compare how many succeeded vs. failed (gatttool & sdptool)
#### Or to do the equivalent of multiple CLI invocations all in one shot (gatttool)
cd /home/$USERNAME/Blue2thprinting/Sniffle/cc2538-bsl/
### BlueZ Configuration ###
if [ -f "/home/$USERNAME/Blue2thprinting/Sniffle/cc2538-bsl/Sniffle_fw_v1.10.0_Sonoff_2M.hex" ]; then
    find /dev/serial/by-id/ -name "usb-ITead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_*" | xargs -n 1 -I {} python3 ./cc2538-bsl.py -p {} --bootloader-sonoff-usb -ewv ./Sniffle_fw_v1.10.0_Sonoff_2M.hex
    echo "  Sonoff firmware flashing complete."
else
    echo "  No Sonoff firmware, not attempting firmware flashing."
fi


echo ""
echo "[--------------------------------------------------]"
echo "Everything seems to have completed successfully! \o/"
echo "[--------------------------------------------------]"
if [ $no_python2 == 1 ]; then
    echo "WARNING: This system could not install the python2.7 package. This is required for Sweyntooth. If you are not using Sweyntooth for 2thprinting, you can ignore this. If you are, this will prevent full 2thprinting from working."
fi
