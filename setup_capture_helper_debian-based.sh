#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
##########################################
# Tested on Ubuntu 24.04, Raspbian Buster & Bookworm

is_sourced() {
    # True if script is called with source script.sh
    [ "${BASH_SOURCE[0]}" != "$0" ]
}

check_env() {
    if [ "$EUID" -ne 0 ]; then
        echo "This script needs to be run with sudo"
        if is_sourced; then
            echo "Press any key to exit terminal or Ctlr + C to continue"
            read -n 1 -s
            exit -1
        fi
        exit -1
    fi
    USERNAME="$SUDO_USER"
    BASE_PATH="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
    echo "Username detected as '$USERNAME'."
    echo "Repo detected at '$BASE_PATH'."
    if [[ ! -f "$BASE_PATH/Scripts/runall.sh" ]]; then
        echo "Could not find Scripts/runall.sh relative to this script. Run setup from inside a Blue2thprinting checkout."
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
    echo "  ============================================================================="
    echo "  $message"
    echo "  ============================================================================="
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
    cd "$BASE_PATH"
    git submodule update --init --recursive
    echo "  Done"
}

enter_venv(){
    python3 -m venv ./venv
    source ./venv/bin/activate
    pip install gmplot intelhex inotify inotify_simple pyserial mysql-connector
}

configure_scripts() {
    #### Scripts and binaries now resolve their own repo root via BASH_SOURCE / __file__
    #### / /proc/self/exe, so there's no longer anything to sed-rewrite post-clone.

    print_banner "Adding execute permissions to the shell scripts."
    cd "$BASE_PATH/Scripts"
    chmod +x *.sh
    echo "  Done"

    print_banner "Appending entry to root crontab to run Scripts/runall.sh at reboot."
    #### This tries to make sure it preserves whatever is already in the crontab
    #### and it just appends an entry to run the runall.sh script at reboot
    #### which invokes the sub-scripts to run btmon (primary HCI logging),
    #### bluetoothctl (primary discovery), and central_app_launcher.py
    #### (orchestration of GATT/SDP/LL/LMP measurements)
    if [ ! -f "$BASE_PATH/Scripts/.cron_added" ]; then
        cron_entry="@reboot $BASE_PATH/Scripts/runall.sh"
        echo "  Writing backup of existing root crontab to /tmp/crontab.root.bak"
        sudo crontab -u root -l > /tmp/crontab.root.bak
        sudo cp /tmp/crontab.root.bak /tmp/crontab.root.new
        echo "  Appending new entry: $cron_entry"
        echo "$cron_entry" >> /tmp/crontab.root.new
        echo "  Importing new crontab from /tmp/crontab.root.new"
        sudo cat /tmp/crontab.root.new | sudo crontab -u root -
        echo "  Setting flag in $BASE_PATH/Scripts/.cron_added to avoid re-settting."
        touch "$BASE_PATH/Scripts/.cron_added"
    else
        echo "  Skipped, because already added."
    fi
}

compile_toolz() {
    print_banner "Compiling the customized BlueZ gatttool & sdptool & bluetoothctl."
    #### I use custom BlueZ utilities to output information in a more machine-parsable format (bluetoothctl & gatttool)
    #### Or to log invocations so I can compare how many succeeded vs. failed (gatttool & sdptool)
    #### Or to do the equivalent of multiple CLI invocations all in one shot (gatttool)
    cd $BASE_PATH/bluez-5.66
    ### BlueZ Configuration ###
    # config.status is the autotools completion sentinel, not Makefile. A Makefile
    # without config.status leaves autotools in a half-configured state where
    # 'make' tries to re-invoke ./config.status --recheck and fails with Error 127.
    if [ ! -f "$BASE_PATH/bluez-5.66/config.status" ]; then
        if [ -f "$BASE_PATH/bluez-5.66/Makefile" ]; then
            print_tool_working "  Stale Makefile without config.status detected; cleaning before reconfigure."
            make distclean >/dev/null 2>&1 || true
        fi
        # Discover udev directory. BlueZ 5.66's configure errors out with
        # "udev directory is required" when --with-udevdir is missing AND
        # `pkg-config --variable=udevdir udev` returns empty — which happens
        # on Debian Trixie / Raspbian Bookworm because the udev.pc that ships
        # there doesn't expose udevdir. Probe the live filesystem instead so
        # this works on usr-merged (/usr/lib/udev) and pre-merge (/lib/udev)
        # layouts alike.
        UDEV_DIR="$(pkg-config --variable=udevdir udev 2>/dev/null || true)"
        if [ -z "$UDEV_DIR" ] || [ ! -d "$UDEV_DIR" ]; then
            if [ -d "/usr/lib/udev" ]; then
                UDEV_DIR="/usr/lib/udev"
            elif [ -d "/lib/udev" ]; then
                UDEV_DIR="/lib/udev"
            else
                echo "  Could not locate a udev directory (tried pkg-config, /usr/lib/udev, /lib/udev)."
                echo "  Install systemd / udev or pass --with-udevdir manually, then re-run."
                exit 1
            fi
        fi
        print_tool_working "  Beginning configuration (udevdir=$UDEV_DIR)."
        # --disable-systemd: BlueZ's configure also wants a systemd system-unit
        # directory by default (`checking systemd system unit dir... error:
        # systemd system unit directory is required` on Trixie/Bookworm where
        # the systemd.pc doesn't expose systemdsystemunitdir). We don't ship
        # any systemd units (the launcher runs from a root @reboot crontab
        # entry), so disable that integration entirely.
        ./configure --prefix=/usr --mandir=/usr/share/man --sysconfdir=/etc --localstatedir=/var --enable-experimental --enable-deprecated --disable-systemd --with-udevdir="$UDEV_DIR"
    else
        echo "  config.status present. Configuration already succeeded."
    fi
    if [ $? != 0 ]; then
        echo "  Something went wrong with the ./configure. Look for an error message, correct it, and try again."
        exit
    fi
    ### Compilation ###
    if [ ! -f "$BASE_PATH/bluez-5.66/attrib/gatttool" ] || [ ! -f "$BASE_PATH/bluez-5.66/tools/sdptool" ] || [ ! -f "$BASE_PATH/bluez-5.66/client/bluetoothctl" ]; then
    print_tool_working "  Beginning compilation (this will take a while!)"
    make -j4
    print_tool_working "  Testing gatttool runs successfully. If you see the help output, it's working."
    $BASE_PATH/bluez-5.66/attrib/gatttool --help
    if [ $? != 0 ]; then
        echo "  Something went wrong with the compilation. Look for an error message, correct it, and try again."
        exit
    fi
    print_tool_working "  Testing sdptool runs successfully. If you see the help output, it's working."
    $BASE_PATH/bluez-5.66/tools/sdptool --help
    if [ $? != 0 ]; then
        echo "  Something went wrong with the compilation. Look for an error message, correct it, and try again."
        exit
    fi
    print_tool_working "  Testing custom bluetoothctl runs successfully. If you see the version output = 5.66, it's working."
    $BASE_PATH/bluez-5.66/client/bluetoothctl --version
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
    cd $BASE_PATH/Sniffle/cc2538-bsl/
    if [ -f "$BASE_PATH/Sniffle/cc2538-bsl/Sniffle_fw_v1.10.0_Sonoff_2M.hex" ]; then
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

    if [ -f "$BASE_PATH/Sniffle/cc2538-bsl/Sniffle_fw_v1.10.0_Sonoff_1M.hex" ]; then
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
    print_banner "Adding helpful command aliases (c, k, TME) to /home/$USERNAME/.bashrc"
    echo "alias c=\"$BASE_PATH/Scripts/check.sh\"" >> /home/$USERNAME/.bashrc
    echo "alias k=\"sudo $BASE_PATH/Scripts/killall.sh\"" >> /home/$USERNAME/.bashrc
    echo "alias d=\"ls -la /dev/serial/by-id/\"" >> /home/$USERNAME/.bashrc
    echo "alias pj=\"python -m json.tool\"" >> /home/$USERNAME/.bashrc
    echo "alias TME=\"python3 ./Tell_Me_Everything.py\"" >> /home/$USERNAME/.bashrc
    echo "alias TB=\"python3 ./Tell_Me_Everything.py --token-file ./tf --query-BTIDALPOOL\"" >> /home/$USERNAME/.bashrc
    echo "alias TBB=\"python3 ./Tell_Me_Everything.py --token-file ./tf --query-BTIDALPOOL --bdaddr\"" >> /home/$USERNAME/.bashrc
    echo "alias BG=\"python3 ./Better_Getter.py\"" >> /home/$USERNAME/.bashrc
    source /home/$USERNAME/.bashrc
    print_banner "Correcting permissions on the Blue2thprinting folder."
    sudo chown -R "$USERNAME" "$BASE_PATH"
}



# Argument parsing
for arg in "$@"; do
    case "$arg" in
        --flash-sniffle)
            check_env
            enter_venv
            flash_sniffle
            cd $BASE_PATH
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
    cd $BASE_PATH
    print_banner "Everything seems to have completed successfully! \o/"
}

#Execute all the default steps
do_all
