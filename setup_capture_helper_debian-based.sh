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
    sudo apt-get install -y python3-pip python3-venv python3-docutils mariadb-server gpsd gpsd-clients expect git net-tools openssh-server libusb-dev libdbus-1-dev libglib2.0-dev libudev-dev libical-dev libreadline-dev autoconf libbluetooth-dev libjson-c-dev zstd usbutils rfkill uhubctl bluez
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
    # --find-links lets pip prefer prebuilt wheels under wheels/ over source builds.
    # This is what saves Pi Zero W (armv6l) installs from a ~90-min dbus-fast source
    # compile — PyPI/piwheels don't publish armv6l wheels for dbus-fast, so we ship
    # one ourselves. Add a wheel for any new architecture/Python combo by running
    # `pip wheel dbus-fast -w wheels/$(python3 -c 'import platform;print(platform.machine())')/`
    # on that platform once and committing the result.
    # jsonschema + colorama are required by Scripts/btc_sdp_gatt.py via the
    # shared TME.* package under Analysis/. jsonschema is pinned to 4.23 because
    # TME_BTIDES_base uses a constructor that older distro-packaged versions
    # (e.g. Ubuntu 24.04's) don't have — same pin as setup_analysis_helper.
    pip install --find-links "$BASE_PATH/wheels/$(python3 -c 'import platform;print(platform.machine())')" \
        gmplot intelhex inotify inotify_simple pyserial mysql-connector dbus-fast \
        jsonschema==4.23 colorama
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
    #### which invokes the sub-scripts to run btmon (primary HCI logging) and
    #### central_app_launcher.py (which performs in-process BlueZ D-Bus
    #### discovery and orchestrates GATT/SDP/LL/LMP measurements). See issue #47.
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
    print_banner "Compiling the customized BlueZ sdptool."
    #### sdptool: logs every invocation so we can compare how many SDP browses
    ####          succeeded vs. failed. The system sdptool from the bluez apt
    ####          package can't be substituted because it lacks our logging.
    #### btmon:   not built — Scripts/start_btmon.sh uses /usr/bin/btmon from
    ####          the bluez apt package. The Btsnoop format it writes is
    ####          identical to what bluez-5.66/monitor/btmon would produce.
    #### gatttool: not built — deprecated in favor of BetterGetter.py.
    #### bluetoothctl: not built — discovery is now in-process via BlueZ
    ####          D-Bus inside central_app_launcher.py (issue #47), so the
    ####          custom bluetoothctl scan tail is no longer on the runtime
    ####          path. The Scripts/start_bluetoothctl.sh wrapper is kept
    ####          around for ad-hoc diagnostics; if you need it, run it
    ####          against the system-installed bluetoothctl.
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
        ./configure --prefix=/usr --mandir=/usr/share/man --sysconfdir=/etc --localstatedir=/var --enable-experimental --enable-deprecated --disable-systemd --with-udevdir="$UDEV_DIR"
    else
        echo "  config.status present. Configuration already succeeded."
    fi
    if [ $? != 0 ]; then
        echo "  Something went wrong with the ./configure. Look for an error message, correct it, and try again."
        exit
    fi
    ### Compilation ###
    if [ ! -f "$BASE_PATH/bluez-5.66/tools/sdptool" ]; then
    print_tool_working "  Beginning compilation (only the targets we need)."
    # Memory-aware -j. BlueZ's larger source files (client/player.c,
    # client/adv_monitor.c, mesh/...) can each push cc1 to ~500 MB peak. On a
    # 1 GB Pi, an unbounded "make -j" runs as many cc1s as there are cores
    # and the kernel OOM-killer terminates them mid-build. Budget ~600 MB per
    # job, capped at nproc, with a floor of 1.
    mem_kb=$(awk '/MemTotal:/ {print $2; exit}' /proc/meminfo 2>/dev/null || echo 1048576)
    mem_mb=$(( mem_kb / 1024 ))
    cores=$(nproc 2>/dev/null || echo 2)
    jobs=$(( mem_mb / 600 ))
    if [ "$jobs" -lt 1 ]; then jobs=1; fi
    if [ "$jobs" -gt "$cores" ]; then jobs=$cores; fi
    print_tool_working "  Detected ${mem_mb} MB RAM, ${cores} cores; building with make -j${jobs}."
    # Targeted build: only the dependency closure of tools/sdptool. Skips the
    # bulk of BlueZ targets (client/bluetoothctl, monitor/btmon, profiles,
    # mesh, the dozens of tools we don't use, the test suite).
    make -j"${jobs}" tools/sdptool
    print_tool_working "  Testing sdptool runs successfully. If you see the help output, it's working."
    $BASE_PATH/bluez-5.66/tools/sdptool --help
    if [ $? != 0 ]; then
        echo "  Something went wrong with the compilation. Look for an error message, correct it, and try again."
        exit
    fi
    else
        echo "  sdptool already exists, skipping recompilation."
    fi
    # System btmon (provided by the 'bluez' apt package) is what start_btmon.sh
    # invokes. Surface a clear error here if it didn't get installed.
    if [ ! -x /usr/bin/btmon ]; then
        echo "  ERROR: /usr/bin/btmon not found. Install the 'bluez' package: sudo apt-get install -y bluez"
        exit 1
    fi
    print_tool_working "  Confirming /usr/bin/btmon (system btmon used by Scripts/start_btmon.sh)."
    /usr/bin/btmon --version

    print_banner "Compiling DarkFirmware_VSC_LMP (BlueZ Realtek-VSC LMP fingerprinter)."
    # Standalone compile against the system libbluetooth + json-c. The tool
    # uses only public BlueZ HCI APIs (hci_open_dev / hci_send_cmd /
    # hci_create_connection / hci_read_remote_version / etc) which all live
    # in libbluetooth.so from the libbluetooth-dev package, so it does not
    # need the BlueZ source tree. Compile is ~1s on a Pi.
    cd "$BASE_PATH/bluez-5.66"
    if [ ! -f "$BASE_PATH/bluez-5.66/tools/DarkFirmware_VSC_LMP" ] || \
       [ "$BASE_PATH/bluez-5.66/tools/DarkFirmware_VSC_LMP.c" -nt \
         "$BASE_PATH/bluez-5.66/tools/DarkFirmware_VSC_LMP" ]; then
        gcc -O2 -Wall -o tools/DarkFirmware_VSC_LMP \
            tools/DarkFirmware_VSC_LMP.c \
            $(pkg-config --cflags --libs json-c) \
            -lbluetooth -lpthread
        if [ $? != 0 ]; then
            echo "  Compilation of DarkFirmware_VSC_LMP failed. Resolve the error above and try again."
            exit
        fi
        echo "  Built tools/DarkFirmware_VSC_LMP."
    else
        echo "  DarkFirmware_VSC_LMP is up to date."
    fi
}

unblock_bluetooth_rfkill() {
    print_banner "Ensuring Bluetooth is not soft-blocked by rfkill."
    # Raspbian (and some Ubuntu images) ship with bluetooth soft-blocked at
    # boot via systemd-rfkill. With it blocked, "hciconfig hciN up" fails
    # with "Operation not possible due to RF-kill (132)" even when the
    # firmware loaded fine. We unblock once now, and Scripts/runall.sh
    # also runs the same unblock at every boot so the state persists.
    if [ ! -x /usr/sbin/rfkill ] && [ ! -x /sbin/rfkill ]; then
        echo "  rfkill binary not found; skipping (apt should have installed it)."
        return 0
    fi
    sudo rfkill unblock bluetooth
    if [ $? != 0 ]; then
        echo "  rfkill unblock failed; check rfkill list output."
        return 1
    fi
    echo "  Bluetooth is now soft-unblocked."
}

install_realtek_firmware() {
    print_banner "Installing custom Realtek (DarkFirmware_real_i) firmware if a supported dongle is attached."
    local SENTINEL="/lib/firmware/rtl_bt/.darkfirmware_real_i_installed"
    if [ -f "$SENTINEL" ] && [ "$1" != "force" ]; then
        echo "  Sentinel $SENTINEL present; skipping. Pass --force-reinstall-rtl-firmware to bypass."
        return 0
    fi

    # First-pass exact VID:PID match — list ported from
    # RTL8761B_usbbluetooth_Patch_Writer.py:59-71, plus 0bda:b771 (a common
    # RTL8761BU variant that the Patch_Writer doesn't enumerate but which
    # uses the same rtl8761bu_fw.bin file the kernel loads).
    local RTL_VIDPIDS="0bda:a728 0bda:a729 0bda:8771 0bda:877b 0bda:b771 2550:8761 2357:0604 2c0a:8761"
    local found=""
    for vp in $RTL_VIDPIDS; do
        if lsusb 2>/dev/null | grep -qi "$vp"; then
            found="$vp"
            break
        fi
    done
    # Permissive fallback: any Realtek (VID 0bda) Bluetooth device.
    # install_DarkFirmware_real.sh writes to /lib/firmware/rtl_bt/rtl8761bu_fw.bin
    # which the kernel will only load for compatible chipsets, so this is safe.
    if [ -z "$found" ]; then
        found=$(lsusb 2>/dev/null | grep -i "0bda:" | grep -i -E "(bluetooth|radio)" | \
                head -n 1 | awk '{print $6}')
    fi
    if [ -z "$found" ]; then
        echo "  No supported Realtek Bluetooth dongle detected via lsusb. Skipping firmware install."
        echo "  Known supported VID:PIDs: $RTL_VIDPIDS"
        return 0
    fi
    echo "  Realtek dongle detected: $found"

    local FW_INSTALLER="$BASE_PATH/DarkFirmware_real_i/03_custom_patch_standalone_file_for_linux/install_DarkFirmware_real.sh"
    if [ ! -x "$FW_INSTALLER" ]; then
        echo "  Installer not found or not executable: $FW_INSTALLER"
        echo "  Did 'git submodule update --init --recursive' run in install_prerequs?"
        return 1
    fi

    pushd "$BASE_PATH/DarkFirmware_real_i/03_custom_patch_standalone_file_for_linux" >/dev/null
    sudo ./install_DarkFirmware_real.sh
    local rc=$?
    popd >/dev/null
    if [ "$rc" != 0 ]; then
        echo "  install_DarkFirmware_real.sh exited with $rc; aborting Realtek install."
        return $rc
    fi

    if command -v usbreset >/dev/null 2>&1; then
        sudo usbreset "$found" || true
    else
        echo "  'usbreset' not available; please unplug and replug the Realtek dongle to load the new firmware."
    fi

    sudo touch "$SENTINEL"
    echo "  Wrote sentinel $SENTINEL."

    # Soft sanity check: the upstream installer always backs up the stock
    # firmware as <name>.orig. Warn (don't fail) if no .orig is present.
    if ! ls /lib/firmware/rtl_bt/rtl8761bu_fw.bin*.orig >/dev/null 2>&1; then
        echo "  Warning: no rtl8761bu_fw.bin*.orig backup found in /lib/firmware/rtl_bt/."
        echo "  This may indicate the installer ran a second time after manual edits."
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
        --install-rtl-firmware)
            check_env
            install_realtek_firmware
            cd $BASE_PATH
            exit 0
            ;;
        --force-reinstall-rtl-firmware)
            check_env
            install_realtek_firmware force
            cd $BASE_PATH
            exit 0
            ;;
        --help)
            echo "Usage: $0 [--flash-sniffle | --install-rtl-firmware | --force-reinstall-rtl-firmware]"
            echo "       $0 (no args) runs the full setup."
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
    install_realtek_firmware
    unblock_bluetooth_rfkill
    create_aliases
    cd $BASE_PATH
    print_banner "Everything seems to have completed successfully! \o/"
}

#Execute all the default steps
do_all
