#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################
# Tested on Ubuntu 24.04, Raspbian Buster & Bookworm

check_env() {
    if [ "$EUID" -ne 0 ]; then
        echo "This script needs to be run with sudo"
        exit -1
    fi
    USERNAME="$SUDO_USER"
    echo "Username detected as '$USERNAME'."
    if [[ ! -d "/home/$USERNAME/Blue2thprinting" && ! -d "/home/$USERNAME/blue2thprinting" ]]; then
        echo "All Blue2thprinting code assumes that Blue2thprinting has been checked out to your home directory (/home/$USERNAME/Blue2thprinting)"
        echo "Please move the folder to /home/$USERNAME/Blue2thprinting and re-run this script from there."
        exit -1
    fi
    apt -v
    if [ $? != 0 ]; then
        print_banner "This script assumes you're running a Debian-derivative system that uses apt (like Ubuntu)."
        print_banner "If you want to run it on a non-debian-derivative, you will need to read this script and adjust commands & prerequisite software to your platform."
        exit -1
    fi
}

print_banner() {
    local message="$1"
    echo ""
    echo "========================================================================================"
    echo "  $message"
    echo "========================================================================================"
}

print_tool_working() {
    local message="$1"
    echo "  >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
    echo "  $message"
    echo "  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
}

install_prerequs(){
    print_banner "Installing all prerequisite software"
    sudo apt-get update
    # Suppress the faux-GUI prompt
    echo "wireshark-common wireshark-common/install-setuid boolean true" | sudo debconf-set-selections
    sudo DEBIAN_FRONTEND=noninteractive apt-get -y install tshark
    sudo apt-get install -y python3-pip python3-venv python3-docutils mariadb-server gpsd gpsd-clients expect git net-tools openssh-server libusb-dev libdbus-1-dev libglib2.0-dev libudev-dev libical-dev libreadline-dev autoconf
    if [ $? != 0 ]; then
        echo ""
        echo "Blue2thprinting: AN ERROR OCCURRED with prerequisite software installation. Resolve error messages above."
        exit -1
    fi
    echo "  Done"
    #### This git repository includes the Bluetooth SIG's assigned numbers git repo under the ./public subfolder
    #### Most people would check it out before seeing that they need to pass the parameter to recurse submodules
    #### So I'm just not bothering with telling folks to do that, and just doing it here
    cd /home/$USERNAME/Blue2thprinting
    git submodule update --init --recursive
    echo "  Done"
}

enter_venv(){
    python3 -m venv ./venv
    source ./venv/bin/activate
    pip install gmplot intelhex inotify inotify_simple pyserial mysql-connector
}

configure_scripts() {
    print_banner "Correcting locations which include hardcoded username in a /home/username/... path."
    #### There's a few places where paths are assumed to be in the user's home dir. This fixes those up.
    if [ $USERNAME != "user" ]; then
        echo "Replacing username 'user' with '$USERNAME'."
        cd /home/$USERNAME/Blue2thprinting
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
        sed -i "s|username = \"user\"|username = \"$USERNAME\"|" central_app_launcher.py
        echo "Correcting central_app_launcher.py"
    fi
    echo "  Done"

    print_banner "Adding execute permissions to the shell scripts."
    chmod +x *.sh
    echo "  Done"

    print_banner "Appending entry to root crontab to run ~/Scripts/runall.sh at reboot."
    #### This tries to make sure it preserves whatever is already in the crontab
    #### and it just appends an entry to run the runall.sh script at reboot
    #### which invokes the sub-scripts to run btmon (primary HCI logging),
    #### bluetoothctl (primary discovery), and central_app_launcher.py
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
}

compile_toolz() {
    print_banner "Compiling the customized BlueZ gatttool & sdptool & bluetoothctl."
    #### I use custom BlueZ utilities to output information in a more machine-parsable format (bluetoothctl & gatttool)
    #### Or to log invocations so I can compare how many succeeded vs. failed (gatttool & sdptool)
    #### Or to do the equivalent of multiple CLI invocations all in one shot (gatttool)
    cd /home/$USERNAME/Blue2thprinting/bluez-5.66
    ### BlueZ Configuration ###
    if [ ! -f "/home/$USERNAME/Blue2thprinting/bluez-5.66/Makefile" ]; then
        print_compilation_step "  Beginning configuration."
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
    print_tool_working "  Beginning compilation (this will take a while!)"
    make -j4
    print_tool_working "  Testing gatttool runs successfully. If you see the help output, it's working."
    /home/$USERNAME/Blue2thprinting/bluez-5.66/attrib/gatttool --help
    if [ $? != 0 ]; then
        echo "  Something went wrong with the compilation. Look for an error message, correct it, and try again."
        exit
    fi
    print_tool_working "  Testing sdptool runs successfully. If you see the help output, it's working."
    /home/$USERNAME/Blue2thprinting/bluez-5.66/tools/sdptool --help
    if [ $? != 0 ]; then
        echo "  Something went wrong with the compilation. Look for an error message, correct it, and try again."
        exit
    fi
    print_tool_working "  Testing custom bluetoothctl runs successfully. If you see the version output = 5.66, it's working."
    /home/$USERNAME/Blue2thprinting/bluez-5.66/client/bluetoothctl --version
    if [ $? != 0 ]; then
        echo "  Something went wrong with the compilation. Look for an error message, correct it, and try again."
        exit
    fi
    else
        echo "  gatttool and sdptool and bluetoothctl already exist, skipping recompilation."
    fi
}

flash_sniffle(){
    print_banner "Attempting to flash Sniffle firmware to any attached Sonoff dongles."
    cd /home/$USERNAME/Blue2thprinting/Sniffle/cc2538-bsl/
    if [ -f "/home/$USERNAME/Blue2thprinting/Sniffle/cc2538-bsl/Sniffle_fw_v1.10.0_Sonoff_2M.hex" ]; then
        dongles=$(find /dev/serial/by-id/ -name "usb-ITead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_*")
        if [ -z "$dongles" ]; then
            echo "  No Sonoff 2Mbps dongles found. No flashing attempted."
        else
            echo "$dongles" | xargs -n 1 -I {} python3 ./cc2538-bsl.py -p {} --bootloader-sonoff-usb -ewv ./Sniffle_fw_v1.10.0_Sonoff_2M.hex
            echo "  Sonoff firmware flashing complete."
        fi
    else
        echo "  No Sonoff 2Mbps firmware file found, not attempting firmware flashing."
    fi

    if [ -f "/home/$USERNAME/Blue2thprinting/Sniffle/cc2538-bsl/Sniffle_fw_v1.10.0_Sonoff_1M.hex" ]; then
        dongles=$(find /dev/serial/by-id/ -name "usb-Silicon_Labs_Sonoff_Zigbee_3.0_USB_Dongle_Plus_*")
        if [ -z "$dongles" ]; then
            echo "  No Sonoff 921600 baud dongles found. No flashing attempted."
        else
            echo "$dongles" | xargs -n 1 -I {} python3 ./cc2538-bsl.py -p {} --bootloader-sonoff-usb -ewv ./Sniffle_fw_v1.10.0_Sonoff_1M.hex
            echo "  Sonoff firmware flashing complete."
        fi
    else
        echo "  No Sonoff 921600 baud firmware file found, not attempting firmware flashing."
    fi
}

create_aliases() {
    print_banner "Adding helpful command aliases (c, k, TME) to ~/.bashrc"
    echo "alias c=\"~/Blue2thprinting/Scripts/check.sh\"" >> /home/$USERNAME/.bashrc
    echo "alias k=\"sudo ~/Blue2thprinting/Scripts/killall.sh\"" >> /home/$USERNAME/.bashrc
    echo "alias d=\"ls -la /dev/serial/by-id/\"" >> /home/$USERNAME/.bashrc
    echo "alias pj=\"python -m json.tool\"" >> /home/$USERNAME/.bashrc
    echo "alias TME=\"python3 ./Tell_Me_Everything.py\"" >> /home/$USERNAME/.bashrc
    echo "alias TB=\"python3 /.Tell_Me_Everything.py --token-file ./tf --query-BTIDALPOOL\"" >> /home/$USERNAME/.bashrc
    echo "alias TBB=\"python3 /.Tell_Me_Everything.py --token-file ./tf --query-BTIDALPOOL --bdaddr\"" >> /home/$USERNAME/.bashrc
    echo "alias BG=\"python3 ./Better_Getter.py\"" >> /home/$USERNAME/.bashrc
    source /home/$USERNAME/.bashrc
    print_banner "Correcting permissions on the Blue2thprinting folder."
    sudo chown -R "$USERNAME" /home/"$USERNAME"/Blue2thprinting
}



# Argument parsing
for arg in "$@"; do
    case "$arg" in
        --flash-sniffle)
            check_env
            enter_venv
            flash_sniffle
            exit 0
            ;;
        --help)
            echo "Usage: $0 [--flash-sniffle] or $0 to execute everything by default"
            exit 0
            ;;
    esac
done

do_all(){
    check_env
    install_prerequs
    enter_venv
    configure_scripts
    compile_toolz
    flash_sniffle
    create_aliases
    print_banner "Everything seems to have completed successfully! \o/"
}
