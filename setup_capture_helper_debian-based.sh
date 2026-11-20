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
    sudo apt-get install -y python3-pip python3-venv mariadb-server gpsd gpsd-clients expect git net-tools openssh-server gcc libc6-dev pkg-config libbluetooth-dev libjson-c-dev zstd usbutils rfkill uhubctl bluez rustc cargo
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
    #### Keep these submodules in sync on future `git pull`s so a pull never leaves you with
    #### code referencing newer submodule content than your checkout has. Scoped to this repo
    #### (--local), not --global, so it doesn't change behavior for the user's other repos.
    git config --local submodule.recurse true
    echo "  Done"
}

enter_venv(){
    if ! python3 -m venv ./venv; then
        echo "Blue2thprinting: failed to create the capture virtual environment."
        exit 1
    fi
    if ! source ./venv/bin/activate; then
        echo "Blue2thprinting: failed to activate the capture virtual environment."
        exit 1
    fi
    # A dbus-fast source compile takes ~90 min on a Pi Zero W (armv6l), so it must
    # come as a wheel there. If a platform has none on its package indexes, add one
    # by running
    # `pip wheel dbus-fast==<pin> -w wheels/$(python3 -c 'import platform;print(platform.machine())')/`
    # on that platform once and committing the result: --find-links below makes
    # pip prefer a wheel under wheels/<machine>/ when that folder exists.
    # dbus-fast and pyyaml are version-pinned: pip resolves to the newest version
    # available across ALL sources, so an unpinned dbus-fast resolves to whatever
    # PyPI currently lists, which may have no armv6l wheel yet. dbus-fast 5.2.0 is
    # on piwheels for armv6l with both Python 3.11 (Bookworm) and 3.13 (Trixie);
    # the 4.0.4 that was pinned before has no armv6l wheel for Python 3.13, so a
    # Trixie Pi Zero would have compiled it. pyyaml 6.0.2 is on piwheels for both
    # too. Bump these pins only when you've confirmed a matching armv6l wheel
    # exists for every Python in use (or ship one under wheels/armv6l/).
    # jsonschema + colorama are required by Scripts/btc_sdp_gatt.py via the
    # shared TME.* package under Analysis/. jsonschema is pinned to 4.23 because
    # TME_BTIDES_base uses a constructor that older distro-packaged versions
    # (e.g. Ubuntu 24.04's) don't have — same pin as setup_analysis_helper.
    # pyyaml lets Tell_Me_Everything.py run --input-BTIDES on a capture node
    # (TME.TME_import loads YAML metadata at import time). google-auth* /
    # googleapiclient are intentionally NOT installed here — they're only
    # needed for BTIDALPOOL features and add ~10 MB; install them via
    # setup_analysis_helper_debian-based.sh if you need that path.
    local WHEEL_DIR="$BASE_PATH/wheels/$(python3 -c 'import platform;print(platform.machine())')"
    local FIND_LINKS=()
    [ -d "$WHEEL_DIR" ] && FIND_LINKS=(--find-links "$WHEEL_DIR")
    if ! pip install "${FIND_LINKS[@]}" \
        gmplot intelhex inotify inotify_simple pyserial mysql-connector dbus-fast==5.2.0 \
        jsonschema==4.23 colorama pyyaml==6.0.2; then
        echo "Blue2thprinting: failed to install capture Python dependencies."
        exit 1
    fi
}

ensure_sniffle_venv(){
    # Fast path for --flash-sniffle: if the venv already exists and the modules
    # cc2538-bsl.py imports are present, skip the slow `python3 -m venv` plus
    # full `pip install` cycle. On a Pi Zero W (armv6l) that cycle is ~3-5 min
    # for repeat runs even when nothing needs reinstallation, because pip still
    # hits PyPI/piwheels for resolution on every package. Falls back to the
    # full enter_venv on the first install (no venv yet) or if cc2538-bsl's
    # deps got removed.
    if [ -d "$BASE_PATH/venv" ]; then
        # shellcheck source=/dev/null
        source "$BASE_PATH/venv/bin/activate"
        if python3 -c "import serial, intelhex" 2>/dev/null; then
            echo "  Reusing existing venv (pyserial + intelhex already importable)."
            return 0
        fi
        deactivate 2>/dev/null || true
    fi
    enter_venv
}

configure_scripts() {
    #### Scripts and binaries now resolve their own repo root via BASH_SOURCE / __file__
    #### / /proc/self/exe, so there's no longer anything to sed-rewrite post-clone.

    print_banner "Adding execute permissions to the shell scripts."
    cd "$BASE_PATH/Scripts"
    chmod +x *.sh
    echo "  Done"

    print_banner "Creating Logs/ directory tree."
    #### Logs/ is .gitignored, so a fresh `git clone` produces a checkout
    #### without it. Pre-create Logs/ and the per-tool subdirs
    #### central_app_launcher.py expects so the install-from-scratch path
    #### doesn't depend on any tool having been run previously.
    mkdir -p "$BASE_PATH/Logs" \
             "$BASE_PATH/Logs/BetterGetter" \
             "$BASE_PATH/Logs/btc_sdp_gatt" \
             "$BASE_PATH/Logs/DarkFirmwareLMPLog"
    echo "  Created $BASE_PATH/Logs/ + per-tool subdirs."

    print_banner "Ensuring root crontab has one capture entry."
    # This script keeps every unrelated cron line, replaces only this
    # checkout's runall.sh entry, and saves a durable backup before changes.
    sudo python3 "$BASE_PATH/Scripts/manage_capture_cron.py" || exit 1

    # Keep the sentinel for backward compat with any external tooling
    # that checks it; it's no longer used as a dedup gate.
    touch "$BASE_PATH/Scripts/.cron_added"
}

compile_toolz() {
    #### The capture path compiles one C tool. What is not built here:
    #### sdptool:  gone. Scripts/btc_sdp_gatt.py collects SDP (and GATT over
    ####           BR/EDR) through the kernel's L2CAP sockets, so the customized
    ####           bluez-5.66 source tree this repository used to carry, and the
    ####           development packages only its build needed, were removed.
    #### btmon:    Scripts/start_btmon.sh uses /usr/bin/btmon from the bluez
    ####           apt package.
    #### gatttool: deprecated in favor of BetterGetter.py.
    #### bluetoothctl: discovery is in-process via BlueZ D-Bus inside
    ####           central_app_launcher.py (issue #47). Scripts/start_bluetoothctl.sh
    ####           is kept for ad-hoc diagnostics and runs the system bluetoothctl.
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
    # in libbluetooth.so from the libbluetooth-dev package. The binary goes in
    # Scripts/, where central_app_launcher.py runs it from and from where it
    # finds Logs/.
    cd "$BASE_PATH/Scripts"
    if [ ! -f DarkFirmware_VSC_LMP ] || \
       [ DarkFirmware_VSC_LMP_src/DarkFirmware_VSC_LMP.c -nt DarkFirmware_VSC_LMP ]; then
        gcc -O2 -Wall -o DarkFirmware_VSC_LMP \
            DarkFirmware_VSC_LMP_src/DarkFirmware_VSC_LMP.c \
            $(pkg-config --cflags --libs json-c) \
            -lbluetooth -lpthread
        if [ $? != 0 ]; then
            echo "  Compilation of DarkFirmware_VSC_LMP failed. Resolve the error above and try again."
            exit 1
        fi
        echo "  Built Scripts/DarkFirmware_VSC_LMP."
    else
        echo "  DarkFirmware_VSC_LMP is up to date."
    fi
    cd "$BASE_PATH"
}

tune_capture_host() {
    print_banner "Tuning this host for capture if it is a small one (single CPU core, under 1 GB of RAM)."
    # On a Raspberry Pi Zero this lowers the duty cycle of BlueZ LE discovery
    # scanning and enlarges the swap file; on a larger host it changes nothing.
    # It runs before the compile stages so they have the swap available.
    # The files it changes are first saved under /var/backups/blue2thprinting,
    # and a repeat run is a no-op. docs/Capture.md has the reasons.
    sudo python3 "$BASE_PATH/Scripts/manage_capture_host_tuning.py" || \
        echo "  Host tuning did not complete (see above). Setup continues without it."
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

build_sniffle_receiver_rust() {
    print_banner "Building the Rust Sniffle host-side receiver."
    # Replacement for sniff_receiver.py — central_app_launcher.py invokes
    # this binary at Sniffle/sniffle_receiver_rust. Without it, central_app
    # would fail to spawn sniffers because the file path it points at
    # wouldn't exist.
    #
    # Source lives at Sniffle/sniffle_receiver_rust_src/ (a cargo project).
    # The `_src` suffix avoids a path collision with the deployed binary
    # at Sniffle/sniffle_receiver_rust (a regular file) — cp file dir/
    # would otherwise copy *into* the cargo project dir, hiding the
    # binary from central_app_launcher.
    #
    # On a Pi Zero W the first build takes ~6–12 min single-threaded.
    # Subsequent rebuilds are seconds.
    #
    # aarch64 (e.g. Pi Zero 2 W) CANNOT build this crate natively: the 64-bit
    # rustc segfaults compiling it regardless of toolchain, flags, memory or
    # swap — even `cargo check` crashes. This is a defect in the aarch64 rustc,
    # not the source: the same source cross-compiles fine on x86_64. Skip the
    # doomed native build here; the operator supplies a cross-built binary.
    # The 32-bit Pi Zero W (armv6l) is unaffected and still builds below.
    # See PI_ZERO_2W_RUST_BUILD.md for the failure analysis and the cross-build.
    local arch
    arch="$(uname -m)"
    if [ "$arch" = "aarch64" ] || [ "$arch" = "arm64" ]; then
        local dest="$BASE_PATH/Sniffle/sniffle_receiver_rust"
        if [ -x "$dest" ]; then
            echo "  aarch64 host detected; a prebuilt sniffle_receiver_rust is already"
            echo "  present at Sniffle/sniffle_receiver_rust — keeping it, skipping the build."
            return 0
        fi
        echo ""
        echo "Blue2thprinting: aarch64 host ($arch) detected — SKIPPING the native cargo"
        echo "build of sniffle_receiver_rust; the aarch64 rustc segfaults on this crate."
        echo ""
        echo "ACTION REQUIRED: cross-compile a static aarch64-musl binary on an x86_64"
        echo "host and install it at Sniffle/sniffle_receiver_rust, or central_app_launcher.py"
        echo "will not be able to spawn Sniffle sniffers."
        echo "Instructions: $BASE_PATH/PI_ZERO_2W_RUST_BUILD.md"
        echo ""
        return 0
    fi
    cd "$BASE_PATH/Sniffle/sniffle_receiver_rust_src"
    # Cargo.lock written by a newer cargo would be rejected by Debian's
    # apt-installed cargo (1.65 on Bookworm); start fresh and let it
    # regenerate. --offline avoids a 5-minute crates.io sync on the
    # Pi Zero W's slow link (project has zero external deps anyway).
    rm -f Cargo.lock
    if ! cargo build --release --offline; then
        echo ""
        echo "Blue2thprinting: cargo build of sniffle_receiver_rust FAILED."
        echo "central_app_launcher.py will not be able to spawn Sniffle sniffers without it."
        exit -1
    fi
    # Use install(1) (not cp) for atomic, mode-aware deployment.
    # Explicitly name the destination FILE to avoid any future ambiguity
    # if a directory ever sneaks in next to the binary.
    install -m 755 target/release/sniffle_receiver_rust "$BASE_PATH/Sniffle/sniffle_receiver_rust"
    echo "  Installed $(ls -l "$BASE_PATH/Sniffle/sniffle_receiver_rust" | awk '{print $5}') bytes at Sniffle/sniffle_receiver_rust"
    cd "$BASE_PATH"
}

flash_sniffle(){
    print_banner "Attempting to flash Sniffle firmware to any attached Sonoff dongles."
    cd $BASE_PATH/Sniffle/cc2538-bsl/
    if [ -f "$BASE_PATH/Sniffle/cc2538-bsl/Sniffle_fw_v1.11.0_20dBm_Sonoff_2M.hex" ]; then
        dongles=$(find /dev/serial/by-id/ -name "usb-ITead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_*")
        if [ -z "$dongles" ]; then
            echo "  No Sonoff 2Mbps dongles found. No flashing attempted."
        else
            # -I {} already implies one execution per input line, so the -n 1
            # we used to pass was redundant; xargs warns about the combination
            # ("--max-args and --replace are mutually exclusive") and ignores
            # the -n 1. Drop it to silence the warning.
            echo "$dongles" | xargs -I {} python3 ./cc2538-bsl.py -p {} --bootloader-sonoff-usb -ewv ./Sniffle_fw_v1.11.0_20dBm_Sonoff_2M.hex
            echo "  Sonoff firmware flashing complete."
        fi
    else
        echo "  No Sonoff 2Mbps firmware file found, not attempting firmware flashing."
    fi

    if [ -f "$BASE_PATH/Sniffle/cc2538-bsl/Sniffle_fw_v1.11.0_20dBm_Sonoff_1M.hex" ]; then
        dongles=$(find /dev/serial/by-id/ -name "usb-Silicon_Labs_Sonoff_Zigbee_3.0_USB_Dongle_Plus_*")
        if [ -z "$dongles" ]; then
            echo "  No Sonoff 921600 baud dongles found. No flashing attempted."
        else
            echo "$dongles" | xargs -I {} python3 ./cc2538-bsl.py -p {} --bootloader-sonoff-usb -ewv ./Sniffle_fw_v1.11.0_20dBm_Sonoff_1M.hex
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
            ensure_sniffle_venv
            flash_sniffle
            cd $BASE_PATH
            exit 0
            ;;
        --build-rust)
            check_env
            build_sniffle_receiver_rust
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
        --tune-host)
            check_env
            tune_capture_host
            cd $BASE_PATH
            exit 0
            ;;
        --help)
            echo "Usage: $0 [--flash-sniffle | --build-rust | --install-rtl-firmware | --force-reinstall-rtl-firmware | --tune-host]"
            echo "       $0 (no args) runs the full setup."
            exit 0
            ;;
    esac
done

do_all(){
    check_env
    install_prerequs
    tune_capture_host
    enter_venv
    configure_scripts
    compile_toolz
    build_sniffle_receiver_rust
    flash_sniffle
    install_realtek_firmware
    unblock_bluetooth_rfkill
    create_aliases
    cd $BASE_PATH
    print_banner "Everything seems to have completed successfully! \o/"
}

#Execute all the default steps
do_all
