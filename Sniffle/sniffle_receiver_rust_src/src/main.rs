//! sniffle_receiver_rust — full Rust port of sniff_receiver.py + sniffle_hw.py for
//! the Sniffle v1.11 firmware over CP210x serial. No external crates;
//! pure std + a small hand-rolled libc FFI block. Intended to be a
//! drop-in replacement for sniff_receiver.py in central_app_launcher.py,
//! including all of:
//!   * passive / active / connection-follow / extended-adv modes
//!   * MAC, IRK, RSSI, ad-string filtering
//!   * coded-PHY long range
//!   * Interval-preload and PHY-preload for encrypted-conn tracking
//!   * AuxPtr-chain + scan-rsp + connect-rsp tracking (cur_aa / crc_init_rev
//!     state transitions identical to the Python `update_state()`)
//!   * Pcap output (DLT_BLUETOOTH_LE_LL_WITH_PHDR=256) with proper
//!     pdu_type / aux_type / CRC / channel mapping for every packet class
//!   * Optional packet pretty-printing on stdout (Python parity)
//!
//! Deliberately *not* ported:
//!   * SDR back-ends (sniffle_sdr.py)  — out of scope for Sonoff/UART
//!   * decode_adv_data (-d flag)       — that's its own ~200-line module
//!   * relay_master / relay_protocol   — out of scope
//!
//! Build:  cargo build --release --offline    (no external deps)
//! Usage:  same as sniff_receiver.py, e.g.
//!     sniffle_receiver_rust -s=/dev/ttyUSB0 -o=cap.pcap -A
//!     sniffle_receiver_rust -s=/dev/ttyUSB0 -o=cap.pcap -m CA:FE:13:37:00:01
//!     sniffle_receiver_rust -s=/dev/ttyUSB0 -o=cap.pcap -m CA:FE:13:37:00:01 -e

use std::env;
use std::fs::File;
use std::io::{BufWriter, Read, Write};
use std::os::unix::io::{AsRawFd, RawFd};
use std::process::ExitCode;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

mod advdata;
mod advdata_constants;

// =====================================================================
// Constants — kept identical to constants.py / firmware
// =====================================================================

const BLE_ADV_AA: u32 = 0x8E89_BED6;
const BLE_ADV_CRCI: u32 = 0x0055_5555;
const PCAP_LINKTYPE_BLE_PHDR: u32 = 256;
const TS_WRAP_US: u64 = 1u64 << 32; // 4294967296 µs ≈ 71.58 min

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
#[repr(u8)]
#[allow(dead_code)]
enum PhyMode {
    Phy1m = 0,
    Phy2m = 1,
    PhyCodedS8 = 2,
    PhyCodedS2 = 3,
}

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
#[repr(u8)]
#[allow(dead_code)]
enum SnifferMode {
    ConnFollow = 0,
    PassiveScan = 1,
    ActiveScan = 2,
}

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
#[allow(dead_code)]
enum SnifferState {
    Static = 0,
    AdvertSeek = 1,
    AdvertHop = 2,
    Data = 3,
    Paused = 4,
    Initiating = 5,
    Central = 6,
    Peripheral = 7,
    Advertising = 8,
    Scanning = 9,
    AdvertisingExt = 10,
}

impl SnifferState {
    fn from_u8(v: u8) -> Self {
        match v {
            0 => Self::Static,
            1 => Self::AdvertSeek,
            2 => Self::AdvertHop,
            3 => Self::Data,
            4 => Self::Paused,
            5 => Self::Initiating,
            6 => Self::Central,
            7 => Self::Peripheral,
            8 => Self::Advertising,
            9 => Self::Scanning,
            10 => Self::AdvertisingExt,
            _ => Self::Static,
        }
    }
    fn name(self) -> &'static str {
        match self {
            Self::Static => "STATIC",
            Self::AdvertSeek => "ADVERT_SEEK",
            Self::AdvertHop => "ADVERT_HOP",
            Self::Data => "DATA",
            Self::Paused => "PAUSED",
            Self::Initiating => "INITIATING",
            Self::Central => "CENTRAL",
            Self::Peripheral => "PERIPHERAL",
            Self::Advertising => "ADVERTISING",
            Self::Scanning => "SCANNING",
            Self::AdvertisingExt => "ADVERTISING_EXT",
        }
    }
}

// =====================================================================
// Base64
// =====================================================================

const B64_DECODE: [i8; 256] = {
    let mut t = [-1i8; 256];
    let alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut i = 0;
    while i < 64 {
        t[alphabet[i] as usize] = i as i8;
        i += 1;
    }
    t[b'=' as usize] = -2;
    t
};

/// Strict-on-content base64 decoder. Returns the actual output length
/// (handles the firmware's "=" padding on short messages — the firmware
/// pads its 4-byte word boundary, Python's b64decode strips the
/// equivalent automatically). Returns None for any non-alphabet byte
/// (other than '=' at the very end).
#[inline]
fn b64_decode(in_buf: &[u8], out_buf: &mut [u8]) -> Option<usize> {
    if in_buf.is_empty() || in_buf.len() % 4 != 0 {
        return Some(0);
    }
    let n_chunks = in_buf.len() / 4;
    let mut n_in = 0;
    let mut n_out = 0;
    for _ in 0..n_chunks - 1 {
        let a = B64_DECODE[in_buf[n_in] as usize];
        let b = B64_DECODE[in_buf[n_in + 1] as usize];
        let c = B64_DECODE[in_buf[n_in + 2] as usize];
        let d = B64_DECODE[in_buf[n_in + 3] as usize];
        if a < 0 || b < 0 || c < 0 || d < 0 {
            return None;
        }
        out_buf[n_out] = ((a as u8) << 2) | ((b as u8) >> 4);
        out_buf[n_out + 1] = ((b as u8) << 4) | ((c as u8) >> 2);
        out_buf[n_out + 2] = ((c as u8) << 6) | (d as u8);
        n_in += 4;
        n_out += 3;
    }
    let l0 = in_buf[n_in];
    let l1 = in_buf[n_in + 1];
    let l2 = in_buf[n_in + 2];
    let l3 = in_buf[n_in + 3];
    let a = B64_DECODE[l0 as usize];
    let b = B64_DECODE[l1 as usize];
    if a < 0 || b < 0 {
        return None;
    }
    out_buf[n_out] = ((a as u8) << 2) | ((b as u8) >> 4);
    n_out += 1;
    if l2 == b'=' {
        return Some(n_out);
    }
    let c = B64_DECODE[l2 as usize];
    if c < 0 {
        return None;
    }
    out_buf[n_out] = ((b as u8) << 4) | ((c as u8) >> 2);
    n_out += 1;
    if l3 == b'=' {
        return Some(n_out);
    }
    let d = B64_DECODE[l3 as usize];
    if d < 0 {
        return None;
    }
    out_buf[n_out] = ((c as u8) << 6) | (d as u8);
    n_out += 1;
    Some(n_out)
}

const B64_ENCODE: &[u8; 64] =
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

fn b64_encode(in_buf: &[u8], out_buf: &mut [u8]) -> usize {
    let mut o = 0;
    let mut i = 0;
    while i + 3 <= in_buf.len() {
        let v = ((in_buf[i] as u32) << 16) | ((in_buf[i + 1] as u32) << 8) | (in_buf[i + 2] as u32);
        out_buf[o] = B64_ENCODE[((v >> 18) & 0x3F) as usize];
        out_buf[o + 1] = B64_ENCODE[((v >> 12) & 0x3F) as usize];
        out_buf[o + 2] = B64_ENCODE[((v >> 6) & 0x3F) as usize];
        out_buf[o + 3] = B64_ENCODE[(v & 0x3F) as usize];
        i += 3;
        o += 4;
    }
    let rem = in_buf.len() - i;
    if rem == 1 {
        let v = (in_buf[i] as u32) << 16;
        out_buf[o] = B64_ENCODE[((v >> 18) & 0x3F) as usize];
        out_buf[o + 1] = B64_ENCODE[((v >> 12) & 0x3F) as usize];
        out_buf[o + 2] = b'=';
        out_buf[o + 3] = b'=';
        o += 4;
    } else if rem == 2 {
        let v = ((in_buf[i] as u32) << 16) | ((in_buf[i + 1] as u32) << 8);
        out_buf[o] = B64_ENCODE[((v >> 18) & 0x3F) as usize];
        out_buf[o + 1] = B64_ENCODE[((v >> 12) & 0x3F) as usize];
        out_buf[o + 2] = B64_ENCODE[((v >> 6) & 0x3F) as usize];
        out_buf[o + 3] = b'=';
        o += 4;
    }
    o
}

// =====================================================================
// BLE CRC LUT (crc_ble.py — same 256 entries)
// =====================================================================

const BLE_CRC_LUT: [u32; 256] = [
    0x000000, 0x01b4c0, 0x036980, 0x02dd40, 0x06d300, 0x0767c0, 0x05ba80, 0x040e40, 0x0da600,
    0x0c12c0, 0x0ecf80, 0x0f7b40, 0x0b7500, 0x0ac1c0, 0x081c80, 0x09a840, 0x1b4c00, 0x1af8c0,
    0x182580, 0x199140, 0x1d9f00, 0x1c2bc0, 0x1ef680, 0x1f4240, 0x16ea00, 0x175ec0, 0x158380,
    0x143740, 0x103900, 0x118dc0, 0x135080, 0x12e440, 0x369800, 0x372cc0, 0x35f180, 0x344540,
    0x304b00, 0x31ffc0, 0x332280, 0x329640, 0x3b3e00, 0x3a8ac0, 0x385780, 0x39e340, 0x3ded00,
    0x3c59c0, 0x3e8480, 0x3f3040, 0x2dd400, 0x2c60c0, 0x2ebd80, 0x2f0940, 0x2b0700, 0x2ab3c0,
    0x286e80, 0x29da40, 0x207200, 0x21c6c0, 0x231b80, 0x22af40, 0x26a100, 0x2715c0, 0x25c880,
    0x247c40, 0x6d3000, 0x6c84c0, 0x6e5980, 0x6fed40, 0x6be300, 0x6a57c0, 0x688a80, 0x693e40,
    0x609600, 0x6122c0, 0x63ff80, 0x624b40, 0x664500, 0x67f1c0, 0x652c80, 0x649840, 0x767c00,
    0x77c8c0, 0x751580, 0x74a140, 0x70af00, 0x711bc0, 0x73c680, 0x727240, 0x7bda00, 0x7a6ec0,
    0x78b380, 0x790740, 0x7d0900, 0x7cbdc0, 0x7e6080, 0x7fd440, 0x5ba800, 0x5a1cc0, 0x58c180,
    0x597540, 0x5d7b00, 0x5ccfc0, 0x5e1280, 0x5fa640, 0x560e00, 0x57bac0, 0x556780, 0x54d340,
    0x50dd00, 0x5169c0, 0x53b480, 0x520040, 0x40e400, 0x4150c0, 0x438d80, 0x423940, 0x463700,
    0x4783c0, 0x455e80, 0x44ea40, 0x4d4200, 0x4cf6c0, 0x4e2b80, 0x4f9f40, 0x4b9100, 0x4a25c0,
    0x48f880, 0x494c40, 0xda6000, 0xdbd4c0, 0xd90980, 0xd8bd40, 0xdcb300, 0xdd07c0, 0xdfda80,
    0xde6e40, 0xd7c600, 0xd672c0, 0xd4af80, 0xd51b40, 0xd11500, 0xd0a1c0, 0xd27c80, 0xd3c840,
    0xc12c00, 0xc098c0, 0xc24580, 0xc3f140, 0xc7ff00, 0xc64bc0, 0xc49680, 0xc52240, 0xcc8a00,
    0xcd3ec0, 0xcfe380, 0xce5740, 0xca5900, 0xcbedc0, 0xc93080, 0xc88440, 0xecf800, 0xed4cc0,
    0xef9180, 0xee2540, 0xea2b00, 0xeb9fc0, 0xe94280, 0xe8f640, 0xe15e00, 0xe0eac0, 0xe23780,
    0xe38340, 0xe78d00, 0xe639c0, 0xe4e480, 0xe55040, 0xf7b400, 0xf600c0, 0xf4dd80, 0xf56940,
    0xf16700, 0xf0d3c0, 0xf20e80, 0xf3ba40, 0xfa1200, 0xfba6c0, 0xf97b80, 0xf8cf40, 0xfcc100,
    0xfd75c0, 0xffa880, 0xfe1c40, 0xb75000, 0xb6e4c0, 0xb43980, 0xb58d40, 0xb18300, 0xb037c0,
    0xb2ea80, 0xb35e40, 0xbaf600, 0xbb42c0, 0xb99f80, 0xb82b40, 0xbc2500, 0xbd91c0, 0xbf4c80,
    0xbef840, 0xac1c00, 0xada8c0, 0xaf7580, 0xaec140, 0xaacf00, 0xab7bc0, 0xa9a680, 0xa81240,
    0xa1ba00, 0xa00ec0, 0xa2d380, 0xa36740, 0xa76900, 0xa6ddc0, 0xa40080, 0xa5b440, 0x81c800,
    0x807cc0, 0x82a180, 0x831540, 0x871b00, 0x86afc0, 0x847280, 0x85c640, 0x8c6e00, 0x8ddac0,
    0x8f0780, 0x8eb340, 0x8abd00, 0x8b09c0, 0x89d480, 0x886040, 0x9a8400, 0x9b30c0, 0x99ed80,
    0x985940, 0x9c5700, 0x9de3c0, 0x9f3e80, 0x9e8a40, 0x972200, 0x9696c0, 0x944b80, 0x95ff40,
    0x91f100, 0x9045c0, 0x929880, 0x932c40,
];

#[inline]
fn rbit24(c: u32) -> u32 {
    let mut out = 0u32;
    for i in 0..24 {
        if (c >> i) & 1 != 0 {
            out |= 1 << (23 - i);
        }
    }
    out
}

#[inline]
fn crc_ble_reverse(crc_init_rev: u32, data: &[u8]) -> u32 {
    let mut state = crc_init_rev & 0x00FF_FFFF;
    for &b in data {
        let key = (b as u32) ^ (state & 0xFF);
        state = (state >> 8) ^ BLE_CRC_LUT[key as usize];
    }
    state
}

// =====================================================================
// Linux serial port (termios) — minimal hand-rolled FFI, no `libc` crate.
// =====================================================================

#[cfg(target_os = "linux")]
mod sys {
    use std::os::raw::*;

    pub const O_RDWR: c_int = 0o000_0002;
    pub const O_NOCTTY: c_int = 0o000_0400;
    pub const O_NONBLOCK: c_int = 0o000_4000;
    pub const F_GETFL: c_int = 3;
    pub const F_SETFL: c_int = 4;
    pub const IGNBRK: c_uint = 0o000_0001;
    pub const BRKINT: c_uint = 0o000_0002;
    pub const PARMRK: c_uint = 0o000_0010;
    pub const ISTRIP: c_uint = 0o000_0040;
    pub const INLCR: c_uint = 0o000_0100;
    pub const IGNCR: c_uint = 0o000_0200;
    pub const ICRNL: c_uint = 0o000_0400;
    pub const IXON: c_uint = 0o002_0000;
    pub const OPOST: c_uint = 0o000_0001;
    pub const ISIG: c_uint = 0o000_0001;
    pub const ICANON: c_uint = 0o000_0002;
    pub const ECHO: c_uint = 0o000_0010;
    pub const ECHONL: c_uint = 0o000_0100;
    pub const IEXTEN: c_uint = 0o010_0000;
    pub const CSIZE: c_uint = 0o000_0060;
    pub const CS8: c_uint = 0o000_0060;
    pub const PARENB: c_uint = 0o000_0400;
    pub const CLOCAL: c_uint = 0o000_4000;
    pub const CREAD: c_uint = 0o000_0200;
    pub const VTIME: usize = 5;
    pub const VMIN: usize = 6;
    pub const NCCS: usize = 32;
    pub const TCSANOW: c_int = 0;
    pub const TCIOFLUSH: c_int = 2;
    pub const FIONREAD: c_ulong = 0x541B;
    pub const B2000000: c_uint = 0o010013;
    pub type SpeedT = c_uint;
    pub type TcflagT = c_uint;
    pub type CcT = c_uchar;

    #[repr(C)]
    pub struct Termios {
        pub c_iflag: TcflagT,
        pub c_oflag: TcflagT,
        pub c_cflag: TcflagT,
        pub c_lflag: TcflagT,
        pub c_line: CcT,
        pub c_cc: [CcT; NCCS],
        pub c_ispeed: SpeedT,
        pub c_ospeed: SpeedT,
    }

    extern "C" {
        pub fn open(pathname: *const c_char, flags: c_int) -> c_int;
        pub fn close(fd: c_int) -> c_int;
        pub fn fcntl(fd: c_int, cmd: c_int, arg: c_int) -> c_int;        pub fn ioctl(fd: c_int, request: c_ulong, ...) -> c_int;
        pub fn tcgetattr(fd: c_int, termios_p: *mut Termios) -> c_int;
        pub fn tcsetattr(fd: c_int, optional_actions: c_int, termios_p: *const Termios) -> c_int;
        pub fn cfsetispeed(termios_p: *mut Termios, speed: SpeedT) -> c_int;
        pub fn cfsetospeed(termios_p: *mut Termios, speed: SpeedT) -> c_int;
        pub fn tcflush(fd: c_int, queue_selector: c_int) -> c_int;
    }
}

#[cfg(target_os = "linux")]
fn open_serial(path: &str, baud: u32) -> std::io::Result<File> {
    use sys::*;
    let cpath = std::ffi::CString::new(path).unwrap();
    let fd = unsafe { open(cpath.as_ptr(), O_RDWR | O_NOCTTY | O_NONBLOCK) };
    if fd < 0 {
        return Err(std::io::Error::last_os_error());
    }
    unsafe {
        let flags = fcntl(fd, F_GETFL, 0);
        fcntl(fd, F_SETFL, flags & !O_NONBLOCK);
    }
    let mut tio: Termios = unsafe { std::mem::zeroed() };
    if unsafe { tcgetattr(fd, &mut tio) } != 0 {
        let e = std::io::Error::last_os_error();
        unsafe { close(fd); }
        return Err(e);
    }
    tio.c_iflag &= !(IGNBRK | BRKINT | PARMRK | ISTRIP | INLCR | IGNCR | ICRNL | IXON);
    tio.c_oflag &= !OPOST;
    tio.c_lflag &= !(ECHO | ECHONL | ICANON | ISIG | IEXTEN);
    tio.c_cflag &= !(CSIZE | PARENB);
    tio.c_cflag |= CS8 | CLOCAL | CREAD;
    tio.c_cc[VMIN] = 1;
    tio.c_cc[VTIME] = 0;
    let speed: SpeedT = match baud {
        2_000_000 => B2000000,
        921_600 => 0o010007, // B921600
        1_500_000 => 0o010012, // B1500000
        _ => B2000000,
    };
    if unsafe { cfsetispeed(&mut tio, speed) } != 0 || unsafe { cfsetospeed(&mut tio, speed) } != 0 {
        let e = std::io::Error::last_os_error();
        unsafe { close(fd); }
        return Err(e);
    }
    if unsafe { tcsetattr(fd, TCSANOW, &tio) } != 0 {
        let e = std::io::Error::last_os_error();
        unsafe { close(fd); }
        return Err(e);
    }
    unsafe { tcflush(fd, TCIOFLUSH); }
    use std::os::unix::io::FromRawFd;
    Ok(unsafe { File::from_raw_fd(fd) })
}

// =====================================================================
// macOS serial port (XNU/BSD termios) — same minimal hand-rolled FFI.
//
// Differences from the Linux block:
//   - tcflag_t and speed_t are 64-bit on macOS (the kernel uses u_long).
//   - NCCS is 20, no c_line field, c_ispeed/c_ospeed live in the struct.
//   - Constants are POSIX-named but use the BSD numeric values.
//   - There is no B2000000 baud constant — to set arbitrary baud
//     (incl. 2 Mbaud) you do tcsetattr() then issue the macOS-specific
//     IOSSIOSPEED ioctl with a speed_t value.
//
// Tested against /dev/cu.usbserial-1320 (CP2102N Sonoff at 2 Mbaud).
// =====================================================================

#[cfg(target_os = "macos")]
mod sys {
    use std::os::raw::*;

    pub const O_RDWR: c_int = 0x0002;
    pub const O_NOCTTY: c_int = 0x20000;
    pub const O_NONBLOCK: c_int = 0x0004;
    pub const F_GETFL: c_int = 3;
    pub const F_SETFL: c_int = 4;

    // c_iflag
    pub const IGNBRK: c_ulong = 0x0001;
    pub const BRKINT: c_ulong = 0x0002;
    pub const PARMRK: c_ulong = 0x0008;
    pub const ISTRIP: c_ulong = 0x0020;
    pub const INLCR: c_ulong = 0x0040;
    pub const IGNCR: c_ulong = 0x0080;
    pub const ICRNL: c_ulong = 0x0100;
    pub const IXON: c_ulong = 0x0200;
    // c_oflag
    pub const OPOST: c_ulong = 0x0001;
    // c_lflag
    pub const ECHO: c_ulong = 0x0008;
    pub const ECHONL: c_ulong = 0x0010;
    pub const ISIG: c_ulong = 0x0080;
    pub const ICANON: c_ulong = 0x0100;
    pub const IEXTEN: c_ulong = 0x0400;
    // c_cflag
    pub const CSIZE: c_ulong = 0x0300;
    pub const CS8: c_ulong = 0x0300;
    pub const PARENB: c_ulong = 0x1000;
    pub const CREAD: c_ulong = 0x0800;
    pub const CLOCAL: c_ulong = 0x8000;

    pub const NCCS: usize = 20;
    pub const VTIME: usize = 17;
    pub const VMIN: usize = 16;

    pub const TCSANOW: c_int = 0;
    pub const TCIOFLUSH: c_int = 3;
    pub const FIONREAD: c_ulong = 0x4004_667F;

    // ioctl<termios_set_speed>(fd, IOSSIOSPEED, &speed_t)
    // Numeric value verified against <IOKit/serial/ioss.h>:
    //   _IOW('T', 2, speed_t) => 0x80085402 (speed_t is 8 bytes)
    pub const IOSSIOSPEED: c_ulong = 0x8008_5402;

    pub type SpeedT = u64;
    pub type TcflagT = u64;
    pub type CcT = c_uchar;

    #[repr(C)]
    pub struct Termios {
        pub c_iflag: TcflagT,
        pub c_oflag: TcflagT,
        pub c_cflag: TcflagT,
        pub c_lflag: TcflagT,
        pub c_cc: [CcT; NCCS],
        pub _padding: [u8; 4],   // align c_ispeed to 8 bytes (struct is 72 bytes)
        pub c_ispeed: SpeedT,
        pub c_ospeed: SpeedT,
    }

    extern "C" {
        pub fn open(pathname: *const c_char, flags: c_int) -> c_int;
        pub fn close(fd: c_int) -> c_int;
        pub fn fcntl(fd: c_int, cmd: c_int, arg: c_int) -> c_int;        pub fn ioctl(fd: c_int, request: c_ulong, ...) -> c_int;
        pub fn tcgetattr(fd: c_int, termios_p: *mut Termios) -> c_int;
        pub fn tcsetattr(fd: c_int, optional_actions: c_int, termios_p: *const Termios) -> c_int;
        pub fn tcflush(fd: c_int, queue_selector: c_int) -> c_int;
    }
}

#[cfg(target_os = "macos")]
fn open_serial(path: &str, baud: u32) -> std::io::Result<File> {
    use sys::*;
    let cpath = std::ffi::CString::new(path).unwrap();
    let fd = unsafe { open(cpath.as_ptr(), O_RDWR | O_NOCTTY | O_NONBLOCK) };
    if fd < 0 {
        return Err(std::io::Error::last_os_error());
    }
    unsafe {
        let flags = fcntl(fd, F_GETFL, 0);
        fcntl(fd, F_SETFL, flags & !O_NONBLOCK);
    }
    let mut tio: Termios = unsafe { std::mem::zeroed() };
    if unsafe { tcgetattr(fd, &mut tio) } != 0 {
        let e = std::io::Error::last_os_error();
        unsafe { close(fd); }
        return Err(e);
    }
    tio.c_iflag &= !(IGNBRK | BRKINT | PARMRK | ISTRIP | INLCR | IGNCR | ICRNL | IXON);
    tio.c_oflag &= !OPOST;
    tio.c_lflag &= !(ECHO | ECHONL | ICANON | ISIG | IEXTEN);
    tio.c_cflag &= !(CSIZE | PARENB);
    tio.c_cflag |= CS8 | CLOCAL | CREAD;
    tio.c_cc[VMIN] = 1;
    tio.c_cc[VTIME] = 0;
    if unsafe { tcsetattr(fd, TCSANOW, &tio) } != 0 {
        let e = std::io::Error::last_os_error();
        unsafe { close(fd); }
        return Err(e);
    }
    // macOS-specific: set non-standard baud via IOSSIOSPEED ioctl.
    // Required because there is no B2000000 constant on macOS.
    let speed: sys::SpeedT = baud as sys::SpeedT;
    if unsafe { ioctl(fd, IOSSIOSPEED, &speed as *const sys::SpeedT) } != 0 {
        let e = std::io::Error::last_os_error();
        unsafe { close(fd); }
        return Err(e);
    }
    unsafe { tcflush(fd, TCIOFLUSH); }
    use std::os::unix::io::FromRawFd;
    Ok(unsafe { File::from_raw_fd(fd) })
}

#[cfg(target_os = "macos")]
fn tty_inq(fd: RawFd) -> i32 {
    let mut n: i32 = 0;
    unsafe { sys::ioctl(fd, sys::FIONREAD, &mut n as *mut i32) };
    n
}

// Fallback for OSes that aren't Linux or macOS — refuse to open.
#[cfg(not(any(target_os = "linux", target_os = "macos")))]
fn open_serial(_path: &str, _baud: u32) -> std::io::Result<File> {
    Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "sniffle_receiver_rust supports only Linux and macOS",
    ))
}

#[cfg(target_os = "linux")]
fn tty_inq(fd: RawFd) -> i32 {
    let mut n: i32 = 0;
    unsafe { sys::ioctl(fd, sys::FIONREAD, &mut n as *mut i32) };
    n
}
#[cfg(not(any(target_os = "linux", target_os = "macos")))]
fn tty_inq(_fd: RawFd) -> i32 { -1 }

// =====================================================================
// pcap writer
// =====================================================================

struct PcapWriter {
    out: BufWriter<File>,
}

impl PcapWriter {
    fn new(path: &str) -> std::io::Result<Self> {
        let file = File::create(path)?;
        let mut out = BufWriter::with_capacity(64 * 1024, file);
        out.write_all(&0xa1b2_c3d4u32.to_le_bytes())?;
        out.write_all(&2u16.to_le_bytes())?;
        out.write_all(&4u16.to_le_bytes())?;
        out.write_all(&0u32.to_le_bytes())?;
        out.write_all(&0u32.to_le_bytes())?;
        out.write_all(&65535u32.to_le_bytes())?;
        out.write_all(&PCAP_LINKTYPE_BLE_PHDR.to_le_bytes())?;
        Ok(Self { out })
    }

    #[allow(clippy::too_many_arguments)]
    fn write_packet(
        &mut self,
        ts_epoch_us: u64,
        aa: u32,
        rf_chan: u8,
        rssi: i8,
        phy: u8,
        pdu_type: u8,
        aux_type: u8,
        crc_rev: u32,
        crc_err: bool,
        body: &[u8],
    ) -> std::io::Result<()> {
        let ts_s = (ts_epoch_us / 1_000_000) as u32;
        let ts_u = (ts_epoch_us % 1_000_000) as u32;

        // Flags from sniffle/pcap.py:PcapBleWriter.payload
        let mut flags: u16 = 0x0413;
        if !crc_err { flags |= 0x0800; }
        if phy != 3 {
            flags |= ((phy as u16) & 0x3) << 14;
        } else {
            flags |= 2 << 14;
        }
        flags |= ((pdu_type as u16) & 0x7) << 7;
        if pdu_type == 1 {
            flags |= ((aux_type as u16) & 0x3) << 12;
        }

        let ci_b: &[u8] = match phy {
            2 => &[0],
            3 => &[1],
            _ => &[],
        };

        let payload_len = 10u32 + 4 + ci_b.len() as u32 + body.len() as u32 + 3;

        let mut scratch = [0u8; 512];
        let mut p = 0;
        scratch[p..p + 4].copy_from_slice(&ts_s.to_le_bytes()); p += 4;
        scratch[p..p + 4].copy_from_slice(&ts_u.to_le_bytes()); p += 4;
        scratch[p..p + 4].copy_from_slice(&payload_len.to_le_bytes()); p += 4;
        scratch[p..p + 4].copy_from_slice(&payload_len.to_le_bytes()); p += 4;
        scratch[p] = rf_chan; p += 1;
        scratch[p] = rssi as u8; p += 1;
        scratch[p] = (-128i8) as u8; p += 1;
        scratch[p] = 0; p += 1;
        scratch[p..p + 4].copy_from_slice(&aa.to_le_bytes()); p += 4;
        scratch[p..p + 2].copy_from_slice(&flags.to_le_bytes()); p += 2;
        scratch[p..p + 4].copy_from_slice(&aa.to_le_bytes()); p += 4;
        if !ci_b.is_empty() {
            scratch[p] = ci_b[0]; p += 1;
        }
        if p + body.len() + 3 > scratch.len() {
            self.out.write_all(&scratch[..p])?;
            self.out.write_all(body)?;
            self.out.write_all(&[(crc_rev & 0xFF) as u8, ((crc_rev >> 8) & 0xFF) as u8, ((crc_rev >> 16) & 0xFF) as u8])?;
            return Ok(());
        }
        scratch[p..p + body.len()].copy_from_slice(body); p += body.len();
        scratch[p] = (crc_rev & 0xFF) as u8; p += 1;
        scratch[p] = ((crc_rev >> 8) & 0xFF) as u8; p += 1;
        scratch[p] = ((crc_rev >> 16) & 0xFF) as u8; p += 1;
        self.out.write_all(&scratch[..p])
    }

    fn flush(&mut self) -> std::io::Result<()> {
        self.out.flush()
    }
}

#[inline]
fn ble_to_rf_chan(chan: u8) -> u8 {
    if chan == 37 { 0 }
    else if chan == 38 { 12 }
    else if chan == 39 { 39 }
    else if chan < 11 { chan + 1 }
    else { chan + 2 }
}

// =====================================================================
// Decoder state + packet classification
// =====================================================================

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
struct AdvDataInfo { did: u16, sid: u8 }

impl AdvDataInfo {
    fn parse(b: &[u8]) -> Self {
        Self { did: (b[0] as u16) | (((b[1] & 0x0F) as u16) << 8), sid: b[1] >> 4 }
    }
}

struct AuxPtr { chan: u8, offset_us: u32 }
impl AuxPtr {
    fn parse(b: &[u8]) -> Self {
        let chan = b[0] & 0x3F;
        let offset_mult: u32 = if b[0] & 0x80 != 0 { 300 } else { 30 };
        let aux_offset: u32 = (b[1] as u32) | (((b[2] & 0x1F) as u32) << 8);
        Self { chan, offset_us: aux_offset * offset_mult }
    }
}

struct DecoderState {
    cur_aa: u32,
    crc_init_rev: u32,
    last_state: SnifferState,
    aux_pending_aa: Option<u32>,
    aux_pending_crci: Option<u32>,
    /// (adi, channel, deadline_secs_since_first_pkt)
    aux_pending_scan_rsp: Option<(AdvDataInfo, u8, f64)>,
    aux_pending_chain: Option<(AdvDataInfo, u8, f64)>,
    /// Time anchoring (mirrors python: time_offset/first_epoch_time/ts_wraps/last_ts)
    time_anchor_us: Option<i64>,
    first_epoch_us: u64,
    last_raw_ts: u32,
    ts_wraps: u64,
    last_raw_ts_seen: bool,
}

impl DecoderState {
    fn new() -> Self {
        Self {
            cur_aa: BLE_ADV_AA,
            crc_init_rev: rbit24(BLE_ADV_CRCI),
            last_state: SnifferState::Static,
            aux_pending_aa: None,
            aux_pending_crci: None,
            aux_pending_scan_rsp: None,
            aux_pending_chain: None,
            time_anchor_us: None,
            first_epoch_us: 0,
            last_raw_ts: 0,
            ts_wraps: 0,
            last_raw_ts_seen: false,
        }
    }
    fn reset_adv(&mut self) {
        self.cur_aa = BLE_ADV_AA;
        self.crc_init_rev = rbit24(BLE_ADV_CRCI);
    }
}

/// Compute monotonic seconds-since-first-packet (the same `pkt.ts` Python
/// uses for aux-timeout comparisons in update_state()).
fn relative_ts_sec(ts_raw: u32, dstate: &DecoderState) -> f64 {
    let anchor = dstate.time_anchor_us.unwrap_or(0);
    let rel_us =
        anchor + (ts_raw as i64) + (dstate.ts_wraps as i64) * (TS_WRAP_US as i64);
    (rel_us as f64) / 1_000_000.0
}

/// Classification result for one PacketMessage. Carries enough info to
/// (a) write the correct pcap pdu_type/aux_type and (b) advance the decoder
/// state machine (cur_aa / crc_init_rev / aux_pending_*).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum PduClass {
    // Primary advertising channel PDUs (chan 37/38/39)
    AdvInd,            // 0
    AdvDirectInd,      // 1
    AdvNonconnInd,     // 2
    ScanReq,           // 3
    ScanRsp,           // 4
    ConnectInd,        // 5
    AdvScanInd,        // 6
    AdvExtInd,         // 7
    AdvOther,
    // Secondary advertising channel PDUs (chan < 37)
    AuxScanReq,        // 3
    AuxConnectReq,     // 5
    AuxAdvInd,         // 7 (no match)
    AuxScanRsp,        // 7 (matched scan_rsp pending)
    AuxChainInd,       // 7 (matched chain pending)
    AuxConnectRsp,     // 8
    // Data channel
    LlData,            // LLID=2
    LlDataCont,        // LLID=1
    LlControl,         // LLID=3
    LlDataRfu,         // LLID=0
}

impl PduClass {
    /// pcap pdu_type field (lower 3 bits of the LL_WITH_PHDR flags byte)
    fn pdu_type(self, data_dir: u8) -> u8 {
        match self {
            // Data packets — pdu_type 3 if data_dir set (P->C), else 2 (C->P)
            Self::LlData | Self::LlDataCont | Self::LlControl | Self::LlDataRfu => {
                if data_dir != 0 { 3 } else { 2 }
            }
            // Anything on a secondary/aux channel → pdu_type 1
            Self::AuxScanReq
            | Self::AuxConnectReq
            | Self::AuxAdvInd
            | Self::AuxScanRsp
            | Self::AuxChainInd
            | Self::AuxConnectRsp => 1,
            // Everything else (primary adv channels) → pdu_type 0
            _ => 0,
        }
    }
    /// pcap aux_type field
    fn aux_type(self) -> u8 {
        match self {
            Self::AuxChainInd => 1,
            Self::AuxScanRsp => 3,
            _ => 0,
        }
    }
}

/// Parsed view of a PacketMessage body — owns no buffers, just slice indices.
struct ParsedPacket<'a> {
    rssi: i8,
    chan: u8,           // BLE channel (0..39)
    phy: u8,
    data_dir: u8,       // 0 = C->P, 1 = P->C
    crc_err: bool,
    body: &'a [u8],     // pkt header (no, this is the BLE PDU body — without firmware's 10-byte header)
    /// real wall-clock timestamp in microseconds
    ts_epoch_us: u64,
    /// relative seconds since first packet (for aux-timeout comparisons)
    ts_rel_s: f64,
}

/// Parse a `MESSAGE_BLEFRAME` (mtype=0x10) body. Returns None for malformed.
/// Also updates the dstate time anchor / wrap counter exactly like
/// PacketMessage.__init__ in packet_decoder.py.
fn parse_packet_message<'a>(
    mbody: &'a [u8],
    dstate: &mut DecoderState,
) -> Option<ParsedPacket<'a>> {
    if mbody.len() < 10 {
        return None;
    }
    let ts_raw = u32::from_le_bytes([mbody[0], mbody[1], mbody[2], mbody[3]]);
    let l_raw = u16::from_le_bytes([mbody[4], mbody[5]]);
    // event = mbody[6..8]; we don't track it
    let rssi = mbody[8] as i8;
    let chan_b = mbody[9];

    let data_dir = ((l_raw >> 15) & 1) as u8;
    let crc_err = (l_raw & 0x4000) != 0;
    let length = (l_raw & 0x3FFF) as usize;
    let body = &mbody[10..];
    if body.len() != length {
        return None;
    }
    let phy = chan_b >> 6;
    let chan = chan_b & 0x3F;

    // Python: "if chan >= 37 and dstate.cur_aa != BLE_ADV_AA: dstate.reset_adv()"
    if chan >= 37 && dstate.cur_aa != BLE_ADV_AA {
        dstate.reset_adv();
    }

    // Time anchoring + wrap detection (with the corrected gap heuristic).
    if dstate.time_anchor_us.is_none() {
        dstate.time_anchor_us = Some(-(ts_raw as i64));
        dstate.first_epoch_us = now_us();
        dstate.last_raw_ts = ts_raw;
        dstate.last_raw_ts_seen = true;
    } else if dstate.last_raw_ts_seen && ts_raw < dstate.last_raw_ts {
        let gap = dstate.last_raw_ts - ts_raw;
        if gap > (1u32 << 31) {
            dstate.ts_wraps += 1;
        }
        dstate.last_raw_ts = ts_raw;
    } else {
        dstate.last_raw_ts = ts_raw;
    }
    let ts_rel_s = relative_ts_sec(ts_raw, dstate);
    let ts_epoch_us = (dstate.first_epoch_us as i64 + (ts_rel_s * 1_000_000.0) as i64) as u64;

    Some(ParsedPacket {
        rssi,
        chan,
        phy,
        data_dir,
        crc_err,
        body,
        ts_epoch_us,
        ts_rel_s,
    })
}

/// Classify the packet (mirrors AdvertMessage.decode + DataMessage.decode
/// in packet_decoder.py).
fn classify(pkt: &ParsedPacket, dstate: &DecoderState) -> PduClass {
    if pkt.body.is_empty() {
        return PduClass::AdvOther;
    }
    if dstate.cur_aa != BLE_ADV_AA {
        // Data channel packet.
        let llid = pkt.body[0] & 0x3;
        return match llid {
            0 => PduClass::LlDataRfu,
            1 => PduClass::LlDataCont,
            2 => PduClass::LlData,
            3 => PduClass::LlControl,
            _ => unreachable!(),
        };
    }
    // Advertising AA.
    let pdu_type = pkt.body[0] & 0xF;
    if pkt.chan >= 37 {
        match pdu_type {
            0 => PduClass::AdvInd,
            1 => PduClass::AdvDirectInd,
            2 => PduClass::AdvNonconnInd,
            3 => PduClass::ScanReq,
            4 => PduClass::ScanRsp,
            5 => PduClass::ConnectInd,
            6 => PduClass::AdvScanInd,
            7 => PduClass::AdvExtInd,
            _ => PduClass::AdvOther,
        }
    } else {
        match pdu_type {
            3 => PduClass::AuxScanReq,
            5 => PduClass::AuxConnectReq,
            7 => classify_aux_ext(pkt, dstate),
            8 => PduClass::AuxConnectRsp,
            _ => PduClass::AdvOther,
        }
    }
}

fn classify_aux_ext(pkt: &ParsedPacket, dstate: &DecoderState) -> PduClass {
    // AdvDataInfo is needed to disambiguate AUX_SCAN_RSP / AUX_CHAIN_IND / AUX_ADV_IND.
    let adi = match parse_adi_from_ext(pkt.body) {
        Some(adi) => adi,
        None => return PduClass::AuxAdvInd,
    };
    if let Some(p) = dstate.aux_pending_scan_rsp {
        if pkt.chan == p.1 && pkt.ts_rel_s < p.2 && adi == p.0 {
            return PduClass::AuxScanRsp;
        }
    }
    if let Some(p) = dstate.aux_pending_chain {
        if pkt.chan == p.1 && pkt.ts_rel_s < p.2 && adi == p.0 {
            return PduClass::AuxChainInd;
        }
    }
    PduClass::AuxAdvInd
}

/// Walk an ADV_EXT_IND / AUX_ADV_IND header to fetch its ADI field, if
/// present. Returns None if the extended header doesn't contain ADI.
fn parse_adi_from_ext(body: &[u8]) -> Option<AdvDataInfo> {
    if body.len() < 4 {
        return None;
    }
    let hdr_body_len = (body[2] & 0x3F) as usize;
    if body.len() < hdr_body_len + 3 {
        return None;
    }
    let hdr_flags = body[3];
    let mut pos = 4;
    if hdr_flags & 0x01 != 0 { pos += 6; } // AdvA
    if hdr_flags & 0x02 != 0 { pos += 6; } // TargetA
    if hdr_flags & 0x04 != 0 { pos += 1; } // CTEInfo
    if hdr_flags & 0x08 != 0 {
        if pos + 2 > body.len() {
            return None;
        }
        return Some(AdvDataInfo::parse(&body[pos..pos + 2]));
    }
    None
}

/// Walk the same ext header to fetch the AuxPtr, if present.
fn parse_auxptr_from_ext(body: &[u8]) -> Option<AuxPtr> {
    if body.len() < 4 {
        return None;
    }
    let hdr_body_len = (body[2] & 0x3F) as usize;
    if body.len() < hdr_body_len + 3 {
        return None;
    }
    let hdr_flags = body[3];
    let mut pos = 4;
    if hdr_flags & 0x01 != 0 { pos += 6; }
    if hdr_flags & 0x02 != 0 { pos += 6; }
    if hdr_flags & 0x04 != 0 { pos += 1; }
    if hdr_flags & 0x08 != 0 { pos += 2; }
    if hdr_flags & 0x10 != 0 {
        if pos + 3 > body.len() {
            return None;
        }
        return Some(AuxPtr::parse(&body[pos..pos + 3]));
    }
    None
}

/// Extended-adv "AdvMode" field (00=non-conn/non-scan, 01=conn, 10=scan, 11=RFU).
fn adv_mode_from_ext(body: &[u8]) -> u8 {
    if body.len() < 3 { 0 } else { body[2] >> 6 }
}

/// Walk the ADV_EXT_IND / AUX_ADV_IND extended header and return the
/// byte offset where adv_data begins (i.e. just past all fields the
/// header-flags byte advertised + any ACAD). Returns None if the
/// header is malformed/truncated. Mirrors AdvExtIndMessage.__init__
/// in packet_decoder.py.
fn ext_adv_data_offset(body: &[u8]) -> Option<usize> {
    if body.len() < 4 { return None; }
    let hdr_body_len = (body[2] & 0x3F) as usize;
    if body.len() < hdr_body_len + 1 { return None; }
    let hdr_flags = body[3];
    let mut pos = 4;
    if hdr_flags & 0x01 != 0 { pos += 6; }   // AdvA
    if hdr_flags & 0x02 != 0 { pos += 6; }   // TargetA
    if hdr_flags & 0x04 != 0 { pos += 1; }   // CTEInfo
    if hdr_flags & 0x08 != 0 { pos += 2; }   // AdvDataInfo
    if hdr_flags & 0x10 != 0 { pos += 3; }   // AuxPtr
    if hdr_flags & 0x20 != 0 { pos += 18; }  // SyncInfo
    if hdr_flags & 0x40 != 0 { pos += 1; }   // TxPower
    // ACAD fills any remaining bytes in the extended header (anything
    // between the structured fields and the header_body_len boundary).
    let extended_header_end = 3 + hdr_body_len;
    if pos < extended_header_end { pos = extended_header_end; }
    if pos > body.len() { return None; }
    Some(pos)
}

/// Locate the advertising data bytes within a PDU body, given the
/// classified PDU type. Returns None for PDU types that don't carry
/// AD data (e.g. ScanReq, ConnectInd, data-channel PDUs).
fn adv_data_slice<'a>(klass: PduClass, body: &'a [u8]) -> Option<&'a [u8]> {
    match klass {
        // AdvaMessage family: 2-byte header + 6-byte AdvA, then adv_data
        PduClass::AdvInd | PduClass::AdvNonconnInd | PduClass::ScanRsp | PduClass::AdvScanInd => {
            if body.len() >= 8 { Some(&body[8..]) } else { None }
        }
        // AdvDirectInd: 2-byte header + 6-byte AdvA + 6-byte TargetA, then (usually empty) adv_data
        PduClass::AdvDirectInd => {
            if body.len() >= 14 { Some(&body[14..]) } else { None }
        }
        // Extended advertising: walk the variable-length header
        PduClass::AdvExtInd | PduClass::AuxAdvInd | PduClass::AuxScanRsp | PduClass::AuxChainInd => {
            let off = ext_adv_data_offset(body)?;
            if off <= body.len() { Some(&body[off..]) } else { None }
        }
        _ => None,
    }
}

/// Parse a ConnectInd/AuxConnectReq body (need aa + CRCInit for state update).
/// Returns (aa, crc_init).
fn parse_connect_ind(body: &[u8]) -> Option<(u32, u32)> {
    if body.len() < 21 {
        return None;
    }
    let aa = u32::from_le_bytes([body[14], body[15], body[16], body[17]]);
    let crc_init = (body[18] as u32) | ((body[19] as u32) << 8) | ((body[20] as u32) << 16);
    Some((aa, crc_init))
}

/// State machine — mirror of packet_decoder.py update_state(), called
/// after every classified packet (during ConnFollow / ext-adv work).
fn update_state(klass: PduClass, pkt: &ParsedPacket, dstate: &mut DecoderState) {
    match klass {
        PduClass::ConnectInd | PduClass::AuxConnectReq => {
            if let Some((aa, crci)) = parse_connect_ind(pkt.body) {
                if pkt.chan < 37 && dstate.last_state != SnifferState::AdvertisingExt {
                    dstate.aux_pending_aa = Some(aa);
                    dstate.aux_pending_crci = Some(crci);
                } else {
                    dstate.cur_aa = aa;
                    dstate.crc_init_rev = rbit24(crci);
                }
            }
        }
        PduClass::AuxConnectRsp => {
            if let Some(aa) = dstate.aux_pending_aa.take() {
                dstate.cur_aa = aa;
            }
            if let Some(crci) = dstate.aux_pending_crci.take() {
                dstate.crc_init_rev = rbit24(crci);
            }
        }
        PduClass::AuxAdvInd => {
            // AuxPtr triggers a chain timeout, scannable triggers a scan_rsp timeout.
            if let Some(ap) = parse_auxptr_from_ext(pkt.body) {
                if let Some(adi) = parse_adi_from_ext(pkt.body) {
                    let deadline = pkt.ts_rel_s + (ap.offset_us as f64) * 1e-6 + 0.0005;
                    dstate.aux_pending_chain = Some((adi, ap.chan, deadline));
                }
            }
            let adv_mode = adv_mode_from_ext(pkt.body);
            if adv_mode == 2 {
                // scannable
                let (overhead, time_per_byte) = match pkt.phy {
                    1 => (8, 4e-6),       // 2M
                    2 => (10, 64e-6),     // Coded S=8
                    3 => (27, 16e-6),     // Coded S=2
                    _ => (8, 8e-6),       // 1M
                };
                let ad_duration = (overhead as f64 + pkt.body.len() as f64) * time_per_byte;
                let scan_req_duration = (overhead as f64 + 14.0) * time_per_byte;
                let timeout = ad_duration + 150e-6 + scan_req_duration + 150e-6 + 50e-6;
                if let Some(adi) = parse_adi_from_ext(pkt.body) {
                    dstate.aux_pending_scan_rsp =
                        Some((adi, pkt.chan, pkt.ts_rel_s + timeout));
                }
            }
        }
        _ => {}
    }

    // Clear pending flags as in update_state's tail block.
    if let Some(p) = dstate.aux_pending_scan_rsp {
        if pkt.ts_rel_s > p.2 || matches!(klass, PduClass::AuxScanRsp) {
            dstate.aux_pending_scan_rsp = None;
        }
    }
    if let Some(p) = dstate.aux_pending_chain {
        if pkt.ts_rel_s > p.2 {
            dstate.aux_pending_chain = None;
        } else if matches!(klass, PduClass::AuxChainInd) && pkt.chan == p.1 {
            if let Some(adi) = parse_adi_from_ext(pkt.body) {
                if adi == p.0 {
                    dstate.aux_pending_chain = None;
                }
            }
        }
    }
}

// =====================================================================
// Sniffle command-sending API (mirrors sniffle_hw.py SniffleHW.cmd_*)
// =====================================================================

fn send_cmd(file: &mut File, cmd: &[u8]) -> std::io::Result<()> {
    // Mirror Python's _send_cmd exactly:
    //   b0 = (len(cmd) + 3) // 3
    //   payload = bytes([b0, *cmd])
    //   wire = b64encode(payload) + b'\r\n'
    //
    // CRITICAL: we encode exactly len(payload) bytes (b0 + cmd). Any zero-
    // padding to b0*3 will be visible to the firmware after b64decode and
    // breaks commands whose handler strictly checks `if (ret == N)` — e.g.
    // COMMAND_MACFILT in CommandTask.c requires ret==8 to *enable* the
    // filter; ret==9 falls through to *disable*. b64encode itself will
    // add the '=' padding the firmware's decoder expects on the wire.
    let payload_len = cmd.len() + 1;
    let b0 = ((cmd.len() + 3) / 3) as u8;
    let mut payload = [0u8; 384];
    payload[0] = b0;
    payload[1..1 + cmd.len()].copy_from_slice(cmd);
    let mut encoded = [0u8; 512];
    let n_enc = b64_encode(&payload[..payload_len], &mut encoded);
    if std::env::var_os("SNIFFLE_RECEIVER_RUST_TRACE_CMD").is_some() {
        let hex: String = cmd.iter().map(|b| format!("{:02X}", b)).collect::<Vec<_>>().join(" ");
        let b64s = std::str::from_utf8(&encoded[..n_enc]).unwrap_or("?");
        eprintln!("[CMD] {} -> b64 \"{}\"", hex, b64s);
    }
    file.write_all(&encoded[..n_enc])?;
    file.write_all(b"\r\n")
}

fn cmd_chan_aa_phy(chan: u8, aa: u32, phy: u8, crci: u32) -> [u8; 11] {
    let mut out = [0u8; 11];
    out[0] = 0x10;
    out[1] = chan;
    out[2..6].copy_from_slice(&aa.to_le_bytes());
    out[6] = phy;
    out[7..11].copy_from_slice(&crci.to_le_bytes());
    out
}

fn cmd_pause_done(p: &mut File, on: bool) -> std::io::Result<()> {
    send_cmd(p, &[0x11, if on { 1 } else { 0 }])
}
fn cmd_rssi(p: &mut File, min: i8) -> std::io::Result<()> {
    send_cmd(p, &[0x12, min as u8])
}
fn cmd_mac(p: &mut File, mac: Option<&[u8; 6]>, hop3: bool) -> std::io::Result<()> {
    match mac {
        None => send_cmd(p, &[0x13]),
        Some(m) => {
            let mut b = [0u8; 7];
            b[0] = 0x13;
            b[1..7].copy_from_slice(m);
            send_cmd(p, &b)?;
            if hop3 { send_cmd(p, &[0x14])?; }
            Ok(())
        }
    }
}
fn cmd_follow(p: &mut File, on: bool) -> std::io::Result<()> {
    send_cmd(p, &[0x15, if on { 1 } else { 0 }])
}
fn cmd_auxadv(p: &mut File, on: bool) -> std::io::Result<()> {
    send_cmd(p, &[0x16, if on { 1 } else { 0 }])
}
fn cmd_marker(p: &mut File, data: &[u8]) -> std::io::Result<()> {
    let mut b = Vec::with_capacity(1 + data.len());
    b.push(0x18);
    b.extend_from_slice(data);
    send_cmd(p, &b)
}
fn cmd_setaddr(p: &mut File, addr: &[u8; 6], is_random: bool) -> std::io::Result<()> {
    let mut b = [0u8; 8];
    b[0] = 0x1B;
    b[1] = if is_random { 1 } else { 0 };
    b[2..8].copy_from_slice(addr);
    send_cmd(p, &b)
}
fn cmd_irk(p: &mut File, irk: Option<&[u8; 16]>, hop3: bool) -> std::io::Result<()> {
    match irk {
        None => send_cmd(p, &[0x1E]),
        Some(k) => {
            let mut b = [0u8; 17];
            b[0] = 0x1E;
            b[1..17].copy_from_slice(k);
            send_cmd(p, &b)?;
            if hop3 { send_cmd(p, &[0x14])?; }
            Ok(())
        }
    }
}
fn cmd_interval_preload(p: &mut File, pairs: &[(u16, u16)]) -> std::io::Result<()> {
    let mut b = Vec::with_capacity(1 + pairs.len() * 4);
    b.push(0x21);
    for &(interval, dinst) in pairs {
        b.extend_from_slice(&interval.to_le_bytes());
        b.extend_from_slice(&dinst.to_le_bytes());
    }
    send_cmd(p, &b)
}
fn cmd_scan(p: &mut File) -> std::io::Result<()> {
    send_cmd(p, &[0x22])
}
fn cmd_phy_preload(p: &mut File, phy: Option<u8>) -> std::io::Result<()> {
    let v = phy.unwrap_or(0xFF);
    send_cmd(p, &[0x23, v])
}
fn cmd_crc_valid(p: &mut File, on: bool) -> std::io::Result<()> {
    send_cmd(p, &[0x26, if on { 1 } else { 0 }])
}
fn cmd_tx_power(p: &mut File, dbm: i8) -> std::io::Result<()> {
    send_cmd(p, &[0x27, dbm as u8])
}

/// Mirror of SniffleHW.setup_sniffer
#[allow(clippy::too_many_arguments)]
fn setup_sniffer(
    port: &mut File,
    mode: SnifferMode,
    chan: u8,
    targ_mac: Option<&[u8; 6]>,
    targ_irk: Option<&[u8; 16]>,
    hop3: bool,
    ext_adv: bool,
    coded_phy: bool,
    rssi_min: i8,
    interval_preload: &[(u16, u16)],
    phy_preload: Option<u8>,
    pause_done: bool,
    validate_crc: bool,
    tx_power: i8,
) -> std::io::Result<()> {
    let phy = if coded_phy { PhyMode::PhyCodedS8 as u8 } else { PhyMode::Phy1m as u8 };
    let cmd = cmd_chan_aa_phy(chan, BLE_ADV_AA, phy, BLE_ADV_CRCI);
    send_cmd(port, &cmd)?;
    cmd_rssi(port, rssi_min)?;
    cmd_pause_done(port, pause_done)?;
    cmd_follow(port, mode == SnifferMode::ConnFollow)?;
    cmd_auxadv(port, ext_adv)?;
    if let Some(mac) = targ_mac {
        cmd_mac(port, Some(mac), hop3)?;
    } else if let Some(irk) = targ_irk {
        cmd_irk(port, Some(irk), hop3)?;
    } else {
        cmd_mac(port, None, false)?;
    }
    cmd_crc_valid(port, validate_crc)?;
    cmd_tx_power(port, tx_power)?;
    cmd_interval_preload(port, interval_preload)?;
    cmd_phy_preload(port, phy_preload)?;
    if mode == SnifferMode::ActiveScan {
        // Sniffle wants its own random static address before active-scan TXs.
        let mut rnd = random_static_addr();
        rnd[5] |= 0xC0;
        cmd_setaddr(port, &rnd, true)?;
        cmd_scan(port)?;
    }
    Ok(())
}

fn random_static_addr() -> [u8; 6] {
    let mut rnd = [0u8; 6];
    let mut seed = (SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos() as u64)
        ^ (std::process::id() as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15);
    for r in rnd.iter_mut() {
        seed = seed
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        *r = (seed >> 33) as u8;
    }
    rnd
}

// =====================================================================
// Message recv (the inner read loop). Mirrors _recv_msg.
// =====================================================================

#[derive(Debug)]
enum RecvErr {
    Io(std::io::Error),
    /// CRLF terminator missing from message tail
    Crlf,
    /// header b64 decode failed
    DecodeHdr,
    /// full payload b64 decode failed
    Decode,
    /// firmware sent word_cnt that won't fit our buffer
    Overflow,
    Eof,
}

impl From<std::io::Error> for RecvErr {
    fn from(e: std::io::Error) -> Self { RecvErr::Io(e) }
}

fn read_exact_io(f: &mut File, buf: &mut [u8]) -> std::io::Result<()> {
    let mut filled = 0;
    while filled < buf.len() {
        match f.read(&mut buf[filled..]) {
            Ok(0) => return Err(std::io::Error::new(std::io::ErrorKind::UnexpectedEof, "EOF")),
            Ok(n) => filled += n,
            Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(e),
        }
    }
    Ok(())
}

fn read_until_lf(f: &mut File) {
    let mut b = [0u8; 1];
    for _ in 0..2048 {
        match f.read(&mut b) {
            Ok(0) | Err(_) => return,
            Ok(_) if b[0] == b'\n' => return,
            _ => {}
        }
    }
}

/// One Sniffle message: msg_type byte + body slice (decoded payload minus
/// the firmware's word_cnt byte and mtype byte).
struct RecvBuf {
    decoded: Vec<u8>,
    n_dec: usize,
}

impl RecvBuf {
    fn new() -> Self { Self { decoded: vec![0u8; 8192], n_dec: 0 } }
    fn mtype(&self) -> u8 { self.decoded[1] }
    fn body(&self) -> &[u8] { &self.decoded[2..self.n_dec] }
}

fn recv_msg(port: &mut File, rbuf: &mut RecvBuf, raw_buf: &mut Vec<u8>) -> Result<usize, RecvErr> {
    let mut header_buf = [0u8; 6];
    read_exact_io(port, &mut header_buf).map_err(|e| {
        if e.kind() == std::io::ErrorKind::UnexpectedEof { RecvErr::Eof } else { RecvErr::Io(e) }
    })?;
    let mut hdr3 = [0u8; 3];
    let dec = b64_decode(&header_buf[..4], &mut hdr3).ok_or(RecvErr::DecodeHdr)?;
    if dec < 2 {
        return Ok(0);
    }
    let word_cnt = hdr3[0] as usize;
    if word_cnt == 0 {
        return Ok(0);
    }
    let extra_bytes = (word_cnt - 1) * 4;
    let total_len = 6 + extra_bytes;
    if total_len > raw_buf.len() {
        if total_len > 16384 {
            read_until_lf(port);
            return Err(RecvErr::Overflow);
        }
        raw_buf.resize(total_len, 0);
    }
    raw_buf[..6].copy_from_slice(&header_buf);
    if extra_bytes > 0 {
        read_exact_io(port, &mut raw_buf[6..6 + extra_bytes])?;
    }
    if &raw_buf[total_len - 2..total_len] != b"\r\n" {
        read_until_lf(port);
        return Err(RecvErr::Crlf);
    }
    let b64_len = total_len - 2;
    let needed = (b64_len / 4) * 3;
    if needed > rbuf.decoded.len() {
        rbuf.decoded.resize(needed, 0);
    }
    let n_dec = b64_decode(&raw_buf[..b64_len], &mut rbuf.decoded).ok_or(RecvErr::Decode)?;
    rbuf.n_dec = n_dec;
    if n_dec < 2 {
        return Ok(0);
    }
    Ok(n_dec)
}

// =====================================================================
// Hexdump for pretty-printing
// =====================================================================

fn hexdump(out: &mut String, data: &[u8]) {
    use std::fmt::Write;
    for (i, chunk) in data.chunks(16).enumerate() {
        let _ = write!(out, "0x{:04x}:  ", i * 16);
        for (j, b) in chunk.iter().enumerate() {
            let _ = write!(out, "{:02x} ", b);
            if j == 7 { out.push(' '); }
        }
        let pad = 16 - chunk.len();
        for j in 0..pad {
            let _ = write!(out, "   ");
            if chunk.len() + j == 7 { out.push(' '); }
        }
        out.push(' ');
        for b in chunk {
            let c = if (0x20..0x7F).contains(b) { *b as char } else { '.' };
            out.push(c);
        }
        out.push('\n');
    }
}

fn str_mac(mac: &[u8]) -> String {
    let mut s = String::with_capacity(17);
    for (i, b) in mac.iter().rev().enumerate() {
        if i > 0 { s.push(':'); }
        let _ = std::fmt::Write::write_fmt(&mut s, format_args!("{:02X}", b));
    }
    s
}

fn _str_atype(addr: &[u8], is_random: bool) -> &'static str {
    if !is_random { return "Public"; }
    match addr[5] >> 6 {
        0 => "NRPA",
        1 => "RPA",
        2 => "RFU",
        _ => "Static",
    }
}

fn str_mac2(mac: &[u8], is_random: bool) -> String {
    format!("{} ({})", str_mac(mac), _str_atype(mac, is_random))
}

const PHY_NAMES: [&str; 4] = ["1M", "2M", "Coded (S=8)", "Coded (S=2)"];
const LL_CONTROL_NAMES: [&str; 26] = [
    "LL_CONNECTION_UPDATE_IND", "LL_CHANNEL_MAP_IND", "LL_TERMINATE_IND",
    "LL_ENC_REQ", "LL_ENC_RSP", "LL_START_ENC_REQ", "LL_START_ENC_RSP",
    "LL_UNKNOWN_RSP", "LL_FEATURE_REQ", "LL_FEATURE_RSP", "LL_PAUSE_ENC_REQ",
    "LL_PAUSE_ENC_RSP", "LL_VERSION_IND", "LL_REJECT_IND",
    "LL_PERIPHERAL_FEATURE_REQ", "LL_CONNECTION_PARAM_REQ",
    "LL_CONNECTION_PARAM_RSP", "LL_REJECT_EXT_IND", "LL_PING_REQ",
    "LL_PING_RSP", "LL_LENGTH_REQ", "LL_LENGTH_RSP", "LL_PHY_REQ",
    "LL_PHY_RSP", "LL_PHY_UPDATE_IND", "LL_MIN_USED_CHANNELS_IND",
];

fn pdu_name(klass: PduClass) -> &'static str {
    match klass {
        PduClass::AdvInd => "ADV_IND",
        PduClass::AdvDirectInd => "ADV_DIRECT_IND",
        PduClass::AdvNonconnInd => "ADV_NONCONN_IND",
        PduClass::ScanReq => "SCAN_REQ",
        PduClass::ScanRsp => "SCAN_RSP",
        PduClass::ConnectInd => "CONNECT_IND",
        PduClass::AdvScanInd => "ADV_SCAN_IND",
        PduClass::AdvExtInd => "ADV_EXT_IND",
        PduClass::AdvOther => "RFU",
        PduClass::AuxScanReq => "AUX_SCAN_REQ",
        PduClass::AuxConnectReq => "AUX_CONNECT_REQ",
        PduClass::AuxAdvInd => "AUX_ADV_IND",
        PduClass::AuxScanRsp => "AUX_SCAN_RSP",
        PduClass::AuxChainInd => "AUX_CHAIN_IND",
        PduClass::AuxConnectRsp => "AUX_CONNECT_RSP",
        PduClass::LlData => "LL DATA",
        PduClass::LlDataCont => "LL DATA CONT",
        PduClass::LlControl => "LL CONTROL",
        PduClass::LlDataRfu => "RFU",
    }
}

fn print_packet(
    klass: PduClass,
    pkt: &ParsedPacket,
    dstate: &DecoderState,
    quiet: bool,
    decode_ad: bool,
) -> String {
    let ts_print = pkt.ts_rel_s;
    let phy_name = PHY_NAMES.get(pkt.phy as usize).copied().unwrap_or("?");
    let crc_str = if pkt.crc_err {
        "Invalid".to_string()
    } else {
        let crc = pkt.body;
        let crc_val = rbit24(crc_ble_reverse(dstate.crc_init_rev, crc));
        format!("0x{:06X}", crc_val)
    };
    let mut out = String::new();
    use std::fmt::Write;

    let _ = writeln!(
        out,
        "Timestamp: {:8.6}  Length: {:2}  RSSI: {:3}  Channel: {:2}  PHY: {}  CRC: {}",
        ts_print, pkt.body.len(), pkt.rssi, pkt.chan, phy_name, crc_str
    );
    match klass {
        PduClass::LlData | PduClass::LlDataCont | PduClass::LlControl | PduClass::LlDataRfu => {
            if pkt.body.is_empty() { return out; }
            let nesn = (pkt.body[0] >> 2) & 1;
            let sn = (pkt.body[0] >> 3) & 1;
            let md = (pkt.body[0] >> 4) & 1;
            let dl = if pkt.body.len() > 1 { pkt.body[1] } else { 0 };
            // skip if quiet and empty
            if quiet && matches!(klass, PduClass::LlData | PduClass::LlDataCont | PduClass::LlDataRfu) && dl == 0 {
                return String::new();
            }
            let _ = writeln!(out, "LLID: {}", pdu_name(klass));
            let dir = if pkt.data_dir != 0 { "P->C" } else { "C->P" };
            let _ = writeln!(out, "Dir: {} NESN: {} SN: {} MD: {} Data Length: {}", dir, nesn, sn, md, dl);
            if let PduClass::LlControl = klass {
                if pkt.body.len() > 2 {
                    let opcode = pkt.body[2] as usize;
                    if opcode < LL_CONTROL_NAMES.len() {
                        let _ = writeln!(out, "Opcode: {}", LL_CONTROL_NAMES[opcode]);
                    } else {
                        let _ = writeln!(out, "Opcode: RFU (0x{:02X})", opcode);
                    }
                }
            }
        }
        _ => {
            if pkt.body.is_empty() { return out; }
            let ch_sel = (pkt.body[0] >> 5) & 1;
            let tx_add = (pkt.body[0] >> 6) & 1;
            let rx_add = (pkt.body[0] >> 7) & 1;
            let ad_length = if pkt.body.len() > 1 { pkt.body[1] } else { 0 };
            let _ = writeln!(out, "Ad Type: {}", pdu_name(klass));
            let _ = writeln!(out, "ChSel: {} TxAdd: {} RxAdd: {} Ad Length: {}",
                ch_sel, tx_add, rx_add, ad_length);
            // Type-specific extras (subset of Python: AdvA/TargetA/InitA/ScanA/ext-header)
            match klass {
                PduClass::AdvInd | PduClass::AdvNonconnInd | PduClass::ScanRsp
                | PduClass::AdvScanInd => {
                    if pkt.body.len() >= 8 {
                        let adva = &pkt.body[2..8];
                        let _ = writeln!(out, "AdvA: {}", str_mac2(adva, tx_add != 0));
                    }
                }
                PduClass::AdvDirectInd => {
                    if pkt.body.len() >= 14 {
                        let adva = &pkt.body[2..8];
                        let targa = &pkt.body[8..14];
                        let _ = writeln!(out, "AdvA: {} TargetA: {}",
                            str_mac2(adva, tx_add != 0), str_mac2(targa, rx_add != 0));
                    }
                }
                PduClass::ScanReq | PduClass::AuxScanReq => {
                    if pkt.body.len() >= 14 {
                        let scna = &pkt.body[2..8];
                        let adva = &pkt.body[8..14];
                        let _ = writeln!(out, "ScanA: {} AdvA: {}",
                            str_mac2(scna, tx_add != 0), str_mac2(adva, rx_add != 0));
                    }
                }
                PduClass::ConnectInd | PduClass::AuxConnectReq => {
                    if let Some((aa, crci)) = parse_connect_ind(pkt.body) {
                        let inita = &pkt.body[2..8];
                        let adva = &pkt.body[8..14];
                        let _ = writeln!(out,
                            "InitA: {} AdvA: {} AA: 0x{:08X} CRCInit: 0x{:06X}",
                            str_mac2(inita, tx_add != 0), str_mac2(adva, rx_add != 0), aa, crci);
                        if pkt.body.len() >= 36 {
                            let win_size = pkt.body[21];
                            let win_off = u16::from_le_bytes([pkt.body[22], pkt.body[23]]);
                            let interval = u16::from_le_bytes([pkt.body[24], pkt.body[25]]);
                            let latency = u16::from_le_bytes([pkt.body[26], pkt.body[27]]);
                            let timeout = u16::from_le_bytes([pkt.body[28], pkt.body[29]]);
                            let hop = pkt.body[35] & 0x1F;
                            let sca = pkt.body[35] >> 5;
                            let _ = writeln!(out,
                                "WinSize: {} WinOffset: {} Interval: {} Latency: {} Timeout: {} Hop: {} SCA: {}",
                                win_size, win_off, interval, latency, timeout, hop, sca);
                        }
                    }
                }
                _ => {}
            }
        }
    }
    // -d / --decode: walk the LTV adv_data of any AdvA-bearing PDU.
    // Mirrors sniff_receiver.py: only AdvaMessage / AdvDirectInd /
    // ScanRsp / AdvExtInd-family PDUs have adv_data to decode.
    if decode_ad {
        if let Some(ad_bytes) = adv_data_slice(klass, pkt.body) {
            for rec in advdata::decode(ad_bytes) {
                let _ = writeln!(out, "{}", rec);
            }
        }
    }
    hexdump(&mut out, pkt.body);
    out.push('\n');
    out
}

// =====================================================================
// Main loop
// =====================================================================

#[derive(Default)]
struct Counters {
    bytes_read: u64,
    msgs_total: u64,
    pkts_written: u64,
    markers: u64,
    states: u64,
    measurements: u64,
    debug: u64,
    other: u64,
    crlf_err: u64,
    decode_err: u64,
    bad_len: u64,
    overflow: u64,
    max_inq: i32,
}

#[derive(Debug)]
struct Args {
    serport: String,
    output: Option<String>,
    mode: SnifferMode,
    chan: u8,
    targ_mac: Option<[u8; 6]>,
    targ_irk: Option<[u8; 16]>,
    targ_string: Option<Vec<u8>>,
    ext_adv: bool,
    longrange: bool,
    hop3: bool,
    rssi_min: i8,
    preload: Vec<(u16, u16)>,
    phy_preload: Option<u8>,
    pause_done: bool,
    capture_crc_err: bool,
    quiet: bool,
    duration_s: Option<u64>,
    label: String,
    baud: u32,
    print_stdout: bool,
    decode_ad: bool,
}

fn parse_mac(s: &str) -> Result<[u8; 6], String> {
    let parts: Vec<&str> = s.split(':').collect();
    if parts.len() != 6 {
        return Err(format!("MAC must be 6 colon-separated hex bytes: {}", s));
    }
    let mut m = [0u8; 6];
    // Python parses as `reversed(args.mac.split(":"))` so we store LE
    for (i, p) in parts.iter().rev().enumerate() {
        m[i] = u8::from_str_radix(p.trim(), 16)
            .map_err(|_| format!("bad MAC byte: {}", p))?;
    }
    Ok(m)
}

fn parse_irk(s: &str) -> Result<[u8; 16], String> {
    let trimmed = s.trim();
    if trimmed.len() != 32 {
        return Err(format!("IRK must be 32 hex chars: {}", s));
    }
    let mut out = [0u8; 16];
    for i in 0..16 {
        out[i] = u8::from_str_radix(&trimmed[2 * i..2 * i + 2], 16)
            .map_err(|_| format!("bad IRK hex: {}", s))?;
    }
    Ok(out)
}

fn parse_preload(s: &str) -> Result<Vec<(u16, u16)>, String> {
    s.split(',')
        .filter(|t| !t.is_empty())
        .map(|t| {
            let mut it = t.split(':');
            let a = it.next().ok_or_else(|| format!("bad preload: {}", t))?;
            let b = it.next().ok_or_else(|| format!("bad preload: {}", t))?;
            let interval: u16 = a.parse().map_err(|_| format!("bad preload int: {}", a))?;
            let delta: u16 = b.parse().map_err(|_| format!("bad preload int: {}", b))?;
            Ok((interval, delta))
        })
        .collect()
}

fn parse_string_escape(s: &str) -> Vec<u8> {
    // Python: args.string.encode('latin-1').decode('unicode_escape').encode('latin-1')
    // Support the common \xHH, \r, \n, \t, \\ escapes.
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'\\' && i + 1 < bytes.len() {
            match bytes[i + 1] {
                b'x' if i + 3 < bytes.len() => {
                    if let Ok(v) = u8::from_str_radix(
                        std::str::from_utf8(&bytes[i + 2..i + 4]).unwrap_or("00"), 16) {
                        out.push(v);
                        i += 4;
                        continue;
                    }
                }
                b'r' => { out.push(b'\r'); i += 2; continue; }
                b'n' => { out.push(b'\n'); i += 2; continue; }
                b't' => { out.push(b'\t'); i += 2; continue; }
                b'\\' => { out.push(b'\\'); i += 2; continue; }
                b'0' => { out.push(0); i += 2; continue; }
                _ => {}
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    out
}

fn print_usage() {
    eprintln!(
        "usage: sniffle_receiver_rust -s=PATH -o=PCAP [-c=CHAN] [-A | -a]\n\
         \t[-m MAC] [-i IRK] [-S STRING] [-r RSSI] [-C] [-q] [-d]\n\
         \t[-e] [-H] [-l] [-Q PRELOAD] [-n] [-p] [-b BAUD]\n\
         \t[--duration=SEC] [--label=NAME] [--print]\n\
         Drop-in replacement for Sniffle's sniff_receiver.py."
    );
}

fn parse_args() -> Result<Args, String> {
    // Thin wrapper around parse_args_from so the actual parsing/validation can
    // be unit-tested with synthetic argv slices (env::args() isn't injectable).
    parse_args_from(env::args().skip(1))
}

fn parse_args_from<I: Iterator<Item = String>>(arg_iter: I) -> Result<Args, String> {
    let mut args = Args {
        serport: String::new(),
        output: None,
        mode: SnifferMode::ConnFollow,
        chan: 37,
        targ_mac: None,
        targ_irk: None,
        targ_string: None,
        ext_adv: false,
        longrange: false,
        hop3: false,
        rssi_min: -128,
        preload: Vec::new(),
        phy_preload: Some(PhyMode::Phy2m as u8),
        pause_done: false,
        capture_crc_err: false,
        quiet: false,
        duration_s: None,
        label: String::new(),
        baud: 2_000_000,
        print_stdout: false,
        decode_ad: false,
    };
    let mut adv_chan_was_default = true;
    let mut explicit_hop = false;
    let mut iter = arg_iter.peekable();
    while let Some(a) = iter.next() {
        let (k, val_inline) = if let Some(eq) = a.find('=') {
            (a[..eq].to_string(), Some(a[eq + 1..].to_string()))
        } else {
            (a.clone(), None)
        };
        // Helper to consume next arg if no inline value
        let mut take_val = || -> Result<String, String> {
            if let Some(v) = val_inline.clone() { return Ok(v); }
            iter.next().ok_or_else(|| format!("missing value for {}", k))
        };
        match k.as_str() {
            "-s" | "--serport" => args.serport = take_val()?,
            "-o" | "--output" => args.output = Some(take_val()?),
            "-c" | "--advchan" => {
                args.chan = take_val()?.parse().map_err(|_| "bad -c".to_string())?;
                adv_chan_was_default = false;
            }
            "-m" | "--mac" => args.targ_mac = Some(parse_mac(&take_val()?)?),
            "-i" | "--irk" => args.targ_irk = Some(parse_irk(&take_val()?)?),
            "-S" | "--string" => args.targ_string = Some(parse_string_escape(&take_val()?)),
            "-r" | "--rssi" => {
                let v: i32 = take_val()?.parse().map_err(|_| "bad -r".to_string())?;
                args.rssi_min = v.clamp(-128, 127) as i8;
            }
            "-Q" | "--preload" => args.preload = parse_preload(&take_val()?)?,
            "-b" | "--baudrate" => args.baud = take_val()?.parse().map_err(|_| "bad -b".to_string())?,
            "-A" | "--scan" => args.mode = SnifferMode::ActiveScan,
            "-a" | "--advonly" => args.mode = SnifferMode::PassiveScan,
            "-e" | "--extadv" => args.ext_adv = true,
            "-H" | "--hop" => { args.hop3 = true; explicit_hop = true; }
            "-l" | "--longrange" => args.longrange = true,
            "-q" | "--quiet" => args.quiet = true,
            "-n" | "--nophychange" => args.phy_preload = None,
            "-C" | "--crcerr" => args.capture_crc_err = true,
            "-p" | "--pause" => args.pause_done = true,
            "-d" | "--decode" => args.decode_ad = true,
            "--print" => args.print_stdout = true,
            "--duration" => args.duration_s = Some(take_val()?.parse().map_err(|_| "bad --duration".to_string())?),
            "--label" => args.label = take_val()?,
            "-h" | "--help" => { print_usage(); std::process::exit(0); }
            _ => return Err(format!("unknown arg: {}", k)),
        }
    }

    // Cross-flag sanity (matches sniff_receiver.py).
    let targ_specs = args.targ_mac.is_some() as u8
        + args.targ_irk.is_some() as u8
        + args.targ_string.is_some() as u8;
    if explicit_hop && targ_specs < 1 {
        return Err("hop requires a target MAC/IRK/string".into());
    }
    if args.longrange && explicit_hop {
        return Err("hop unsupported on long range PHY".into());
    }
    if targ_specs > 1 {
        return Err("MAC, IRK, and string filters are mutually exclusive".into());
    }
    if !adv_chan_was_default && explicit_hop {
        return Err("don't specify -c with -H".into());
    }
    if args.serport.is_empty() {
        return Err("missing -s".into());
    }
    if args.label.is_empty() {
        args.label = args.serport.rsplit('/').next().unwrap_or("?").to_string();
    }

    // Final hop3 — must mirror sniff_receiver.py exactly:
    //   hop3 = True if targ_specs else False
    //   if args.advchan != 40: hop3 = False   # explicit -c kills hop3
    // (the firmware's COMMAND_ADVHOP / advHopSeekMode is "hop 37/38/39
    // while seeking the target's next advertisement"; setting it when
    // the user pinned a specific channel makes us miss CONNECT_IND
    // packets because we're on the wrong channel at the wrong time.)
    args.hop3 = (targ_specs > 0) && adv_chan_was_default;
    // -e ext_adv on legacy PHY also turns hop3 off (per Python's
    // "disable 37/38/39 hop in extended mode unless overridden").
    if args.ext_adv && !explicit_hop {
        args.hop3 = false;
    }
    Ok(args)
}

fn now_us() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_micros() as u64)
        .unwrap_or(0)
}

/// Get a MAC by scanning for an advertisement whose body contains the
/// target string (mirrors get_mac_from_string in sniff_receiver.py).
fn get_mac_from_string(
    port: &mut File,
    needle: &[u8],
    coded_phy: bool,
    label: &str,
) -> std::io::Result<([u8; 6], bool)> {
    eprintln!("[{}] waiting for advertisement containing {:?} (extended-adv scan)…", label, needle);
    let mut dstate = DecoderState::new();
    let phy_preload = Some(PhyMode::Phy2m as u8);
    setup_sniffer(
        port,
        SnifferMode::ActiveScan,
        37,
        None,
        None,
        false,
        true,            // extadv
        coded_phy,
        -128,
        &[],
        phy_preload,
        false,
        true,
        5,
    )?;
    let mut rbuf = RecvBuf::new();
    let mut raw_buf = vec![0u8; 8192];
    loop {
        let n_dec = match recv_msg(port, &mut rbuf, &mut raw_buf) {
            Ok(n) => n,
            Err(RecvErr::Crlf | RecvErr::Decode | RecvErr::DecodeHdr | RecvErr::Overflow) => continue,
            Err(RecvErr::Io(e)) => return Err(e),
            Err(RecvErr::Eof) => return Err(std::io::Error::new(std::io::ErrorKind::UnexpectedEof, "EOF on -S scan")),
        };
        if n_dec < 2 { continue; }
        if rbuf.mtype() != 0x10 { continue; }
        let pkt = match parse_packet_message(rbuf.body(), &mut dstate) {
            Some(p) => p,
            None => continue,
        };
        // Need an AdvaMessage subclass with an AdvA. Look at the body.
        let klass = classify(&pkt, &dstate);
        let (adva, tx_add) = match klass {
            PduClass::AdvInd | PduClass::AdvNonconnInd | PduClass::ScanRsp
            | PduClass::AdvScanInd if pkt.body.len() >= 8 =>
                (&pkt.body[2..8], (pkt.body[0] >> 6) & 1),
            PduClass::AdvDirectInd if pkt.body.len() >= 8 =>
                (&pkt.body[2..8], (pkt.body[0] >> 6) & 1),
            PduClass::AdvExtInd | PduClass::AuxAdvInd => {
                // Need to walk the extended header to find AdvA.
                if let Some((adva, tx_add)) = ext_get_adva(pkt.body) {
                    if pkt.body.windows(needle.len()).any(|w| w == needle) {
                        let mut mac = [0u8; 6];
                        mac.copy_from_slice(adva);
                        return Ok((mac, tx_add != 0));
                    }
                }
                continue;
            }
            _ => continue,
        };
        if pkt.body.windows(needle.len()).any(|w| w == needle) {
            let mut mac = [0u8; 6];
            mac.copy_from_slice(adva);
            return Ok((mac, tx_add != 0));
        }
    }
}

fn ext_get_adva(body: &[u8]) -> Option<(&[u8], u8)> {
    if body.len() < 4 { return None; }
    let hdr_flags = body[3];
    let tx_add = (body[0] >> 6) & 1;
    if hdr_flags & 0x01 == 0 { return None; }
    if body.len() < 10 { return None; }
    Some((&body[4..10], tx_add))
}

fn run(args: &Args) -> std::io::Result<Counters> {
    eprintln!("[{}] sniffle_receiver_rust v0.2 opening {}{}",
        args.label, args.serport,
        if let Some(o) = &args.output { format!(" -> {}", o) } else { String::new() });
    let mut port = open_serial(&args.serport, args.baud)?;
    let port_fd = port.as_raw_fd();
    let mut pcap = match &args.output {
        Some(p) => Some(PcapWriter::new(p)?),
        None => None,
    };

    // Initial sync marker (firmware echoes it back so we know it's listening)
    cmd_marker(&mut port, b"@")?;

    // Resolve targeted MAC if -S was given
    let mut targ_mac = args.targ_mac;
    if let Some(needle) = &args.targ_string {
        let (mac, _) = get_mac_from_string(&mut port, needle, args.longrange, &args.label)?;
        eprintln!("[{}] found target MAC: {}", args.label, str_mac(&mac));
        targ_mac = Some(mac);
    }

    // hop3 was decided in parse_args() to match Python's logic exactly.
    // ext_adv is upgraded if longrange (coded PHY needs ext_adv).
    let hop3 = args.hop3;
    let chan = args.chan;
    let ext_adv = args.ext_adv || args.longrange;

    setup_sniffer(
        &mut port,
        args.mode,
        chan,
        targ_mac.as_ref(),
        args.targ_irk.as_ref(),
        hop3,
        ext_adv,
        args.longrange,
        args.rssi_min,
        &args.preload,
        args.phy_preload,
        args.pause_done,
        !args.capture_crc_err,  // -C means we DO want CRC-errored packets, so disable validate
        5,
    )?;

    // mark_and_flush: send a marker with a random tag. We *prefer* to gate
    // pcap recording on receiving that marker echo back (matches Python
    // semantics — drops any pre-session UART residue), but fall back to
    // arming anyway after MARKER_FALLBACK_S so a wedged-firmware dongle
    // (e.g. one whose state machine isn't echoing markers but is still
    // streaming packets) still produces a usable capture.
    let marker_tag = (now_us() as u32).to_le_bytes();
    cmd_marker(&mut port, &marker_tag)?;

    let mut dstate = DecoderState::new();
    let mut rbuf = RecvBuf::new();
    let mut raw_buf = vec![0u8; 8192];
    let mut counters = Counters::default();
    let start = Instant::now();
    let mut last_report = start;
    let mut last_flush = start;
    let deadline = args.duration_s.map(|s| start + Duration::from_secs(s));
    let mut got_marker_echo = false;
    const MARKER_FALLBACK_S: u64 = 3;
    eprintln!("[{}] entering read loop", args.label);

    loop {
        if let Some(d) = deadline {
            if Instant::now() >= d { break; }
        }
        let n_dec = match recv_msg(&mut port, &mut rbuf, &mut raw_buf) {
            Ok(n) => n,
            Err(RecvErr::Crlf) => {
                counters.crlf_err += 1;
                let inq = tty_inq(port_fd);
                if inq > counters.max_inq { counters.max_inq = inq; }
                continue;
            }
            Err(RecvErr::Decode) | Err(RecvErr::DecodeHdr) => { counters.decode_err += 1; continue; }
            Err(RecvErr::Overflow) => { counters.overflow += 1; continue; }
            Err(RecvErr::Eof) => { eprintln!("[{}] EOF", args.label); break; }
            Err(RecvErr::Io(e)) => { eprintln!("[{}] I/O error: {}", args.label, e); break; }
        };
        if n_dec < 2 { continue; }
        counters.bytes_read += rbuf.n_dec as u64;
        counters.msgs_total += 1;

        let mtype = rbuf.mtype();
        let body = rbuf.body();
        // Fallback: arm pcap recording even without a marker echo after a
        // short grace period.
        if !got_marker_echo && start.elapsed().as_secs() >= MARKER_FALLBACK_S {
            got_marker_echo = true;
            eprintln!("[{}] no marker echo after {}s — arming pcap fallback",
                args.label, MARKER_FALLBACK_S);
        }
        match mtype {
            0x10 => {
                if !got_marker_echo {
                    // Drop pre-marker packets (mark_and_flush parity).
                    continue;
                }
                let pkt = match parse_packet_message(body, &mut dstate) {
                    Some(p) => p,
                    None => { counters.bad_len += 1; continue; }
                };
                let klass = classify(&pkt, &dstate);
                // pcap write
                if let Some(pcw) = pcap.as_mut() {
                    let crc_rev = if pkt.crc_err {
                        0
                    } else {
                        crc_ble_reverse(dstate.crc_init_rev, pkt.body)
                    };
                    let pdu_type = klass.pdu_type(pkt.data_dir);
                    let aux_type = klass.aux_type();
                    pcw.write_packet(
                        pkt.ts_epoch_us,
                        dstate.cur_aa,
                        ble_to_rf_chan(pkt.chan),
                        pkt.rssi,
                        pkt.phy,
                        pdu_type,
                        aux_type,
                        crc_rev,
                        pkt.crc_err,
                        pkt.body,
                    )?;
                    counters.pkts_written += 1;
                }
                // optional pretty-print
                if args.print_stdout {
                    let s = print_packet(klass, &pkt, &dstate, args.quiet, args.decode_ad);
                    if !s.is_empty() {
                        print!("{}", s);
                    }
                }
                // state transitions for following / aux
                update_state(klass, &pkt, &mut dstate);
            }
            0x11 => {
                counters.debug += 1;
                if args.print_stdout {
                    eprintln!("[{}] DEBUG: {}",
                        args.label, String::from_utf8_lossy(body));
                }
            }
            0x12 => {
                counters.markers += 1;
                // First marker echo => begin pcap recording
                if !got_marker_echo {
                    got_marker_echo = true;
                    eprintln!("[{}] marker echo received; pcap recording armed", args.label);
                }
            }
            0x13 => {
                counters.states += 1;
                if !body.is_empty() {
                    let new_state = SnifferState::from_u8(body[0]);
                    if args.print_stdout {
                        eprintln!("[{}] TRANSITION: {} from {}",
                            args.label, new_state.name(), dstate.last_state.name());
                    }
                    dstate.last_state = new_state;
                    // Python triggers reset_adv() on entering ADVERT_HOP from ADVERT_SEEK?
                    // No — reset_adv is only triggered in parse_packet_message when chan>=37.
                }
            }
            0x14 => counters.measurements += 1,
            _ => counters.other += 1,
        }

        let now = Instant::now();
        if now - last_flush >= Duration::from_millis(1000) {
            if let Some(pcw) = pcap.as_mut() { let _ = pcw.flush(); }
            last_flush = now;
        }
        if now - last_report >= Duration::from_secs(10) {
            let inq = tty_inq(port_fd);
            eprintln!(
                "[{}] +10s: msgs={} pkts={} states={} meas={} crlf_err={} dec_err={} bad_len={} inq_now={} inq_max={}",
                args.label, counters.msgs_total, counters.pkts_written,
                counters.states, counters.measurements,
                counters.crlf_err, counters.decode_err, counters.bad_len,
                inq, counters.max_inq,
            );
            last_report = now;
        }
    }
    if let Some(pcw) = pcap.as_mut() { let _ = pcw.flush(); }
    let elapsed = start.elapsed().as_secs_f64();
    eprintln!(
        "[{}] DONE: elapsed={:.1}s bytes={} msgs={} pkts_written={} markers={} states={} meas={} debug={} other={} bad_len={} crlf_err={} dec_err={} overflow={} max_inq={} ts_wraps={} cur_aa=0x{:08X} last_state={}",
        args.label, elapsed, counters.bytes_read, counters.msgs_total,
        counters.pkts_written, counters.markers, counters.states,
        counters.measurements, counters.debug, counters.other,
        counters.bad_len, counters.crlf_err, counters.decode_err,
        counters.overflow, counters.max_inq, dstate.ts_wraps,
        dstate.cur_aa, dstate.last_state.name(),
    );
    Ok(counters)
}

fn main() -> ExitCode {
    // Diagnostic short-circuit: --decode-hex HEX runs advdata::decode on
    // the given hex string and prints the same one-record-per-line output
    // that `-d --print` produces, then exits. Used for offline parity
    // comparisons against Python's `decode_adv_data`. Bypasses everything
    // else — no serial port, no pcap.
    let argv: Vec<String> = env::args().collect();
    if let Some(idx) = argv.iter().position(|a|
        a == "--decode-hex" || a.starts_with("--decode-hex="))
    {
        let hex = if argv[idx].starts_with("--decode-hex=") {
            argv[idx]["--decode-hex=".len()..].to_string()
        } else if idx + 1 < argv.len() {
            argv[idx + 1].clone()
        } else {
            String::new()
        };
        match hex_to_bytes(&hex) {
            Some(bytes) => {
                for rec in advdata::decode(&bytes) {
                    println!("{}", rec);
                }
                return ExitCode::SUCCESS;
            }
            None => {
                eprintln!("error: --decode-hex value must be valid hex");
                return ExitCode::from(2);
            }
        }
    }

    let args = match parse_args() {
        Ok(a) => a,
        Err(e) => { eprintln!("error: {}", e); print_usage(); return ExitCode::from(2); }
    };
    match run(&args) {
        Ok(_) => ExitCode::SUCCESS,
        Err(e) => { eprintln!("error: {}", e); ExitCode::from(1) }
    }
}

fn hex_to_bytes(s: &str) -> Option<Vec<u8>> {
    let trimmed: String = s.chars().filter(|c| !c.is_whitespace() && *c != ':').collect();
    if trimmed.len() % 2 != 0 { return None; }
    let mut out = Vec::with_capacity(trimmed.len() / 2);
    for i in (0..trimmed.len()).step_by(2) {
        let byte = u8::from_str_radix(&trimmed[i..i + 2], 16).ok()?;
        out.push(byte);
    }
    Some(out)
}

// ============================================================================
// CLI argument-parsing + helper tests
// ============================================================================
// sniffle_receiver_rust hand-rolls its arg parsing (no clap, to keep the build
// dependency-free for the Pi Zero W). parse_args_from() takes an arbitrary
// String iterator so the parsing + cross-flag validation + Python-mirroring
// hop3 derivation can be unit-tested without env::args(). The --help branch
// calls process::exit, so it's intentionally never passed here.
#[cfg(test)]
mod cli_tests {
    use super::*;

    fn parse(args: &[&str]) -> Result<Args, String> {
        parse_args_from(args.iter().map(|s| s.to_string()))
    }

    // -------------------------- value helpers -------------------------------

    #[test]
    fn parse_mac_reverses_to_little_endian() {
        // sniff_receiver.py parses reversed(mac.split(':')) → LE byte order.
        assert_eq!(
            parse_mac("CA:FE:13:37:00:01").unwrap(),
            [0x01, 0x00, 0x37, 0x13, 0xFE, 0xCA]
        );
    }

    #[test]
    fn parse_mac_rejects_bad_shapes() {
        assert!(parse_mac("CA:FE:13:37:00").is_err());       // 5 bytes
        assert!(parse_mac("CA:FE:13:37:00:01:02").is_err()); // 7 bytes
        assert!(parse_mac("ZZ:FE:13:37:00:01").is_err());    // non-hex
    }

    #[test]
    fn parse_irk_requires_32_hex_chars() {
        let irk = parse_irk("000102030405060708090a0b0c0d0e0f").unwrap();
        assert_eq!(irk[0], 0x00);
        assert_eq!(irk[15], 0x0f);
        assert!(parse_irk("00112233").is_err());     // too short
        assert!(parse_irk(&"z".repeat(32)).is_err()); // right len, bad hex
    }

    #[test]
    fn parse_preload_parses_interval_delta_pairs() {
        assert_eq!(parse_preload("6:0,10:5").unwrap(), vec![(6u16, 0u16), (10, 5)]);
        assert_eq!(parse_preload("").unwrap(), Vec::<(u16, u16)>::new());
        assert!(parse_preload("6").is_err());     // missing delta
        assert!(parse_preload("x:0").is_err());   // non-numeric
    }

    #[test]
    fn parse_string_escape_handles_common_escapes() {
        assert_eq!(parse_string_escape(r"AB\x43"), vec![0x41, 0x42, 0x43]); // \x43 = 'C'
        assert_eq!(parse_string_escape(r"\r\n\t"), vec![0x0d, 0x0a, 0x09]);
        assert_eq!(parse_string_escape("plain"), b"plain".to_vec());
        assert_eq!(parse_string_escape(r"a\\b"), vec![b'a', b'\\', b'b']);
    }

    // ------------------------- defaults & required --------------------------

    #[test]
    fn defaults_match_sniff_receiver_py() {
        let a = parse(&["-s", "/dev/ttyUSB0"]).unwrap();
        assert_eq!(a.serport, "/dev/ttyUSB0");
        assert_eq!(a.output, None);
        assert_eq!(a.mode, SnifferMode::ConnFollow);
        assert_eq!(a.chan, 37);
        assert_eq!(a.targ_mac, None);
        assert_eq!(a.targ_irk, None);
        assert_eq!(a.targ_string, None);
        assert!(!a.ext_adv);
        assert!(!a.longrange);
        assert!(!a.hop3);
        assert_eq!(a.rssi_min, -128);
        assert!(a.preload.is_empty());
        assert_eq!(a.phy_preload, Some(PhyMode::Phy2m as u8));
        assert!(!a.pause_done);
        assert!(!a.capture_crc_err);
        assert!(!a.quiet);
        assert_eq!(a.duration_s, None);
        assert_eq!(a.baud, 2_000_000);
        assert!(!a.print_stdout);
        assert!(!a.decode_ad);
        // label defaults to the serport basename.
        assert_eq!(a.label, "ttyUSB0");
    }

    #[test]
    fn serport_is_required() {
        assert_eq!(parse(&[]).unwrap_err(), "missing -s");
    }

    #[test]
    fn inline_equals_and_space_forms_are_equivalent() {
        let space = parse(&["-s", "/dev/ttyUSB0", "-o", "cap.pcap"]).unwrap();
        let inline = parse(&["-s=/dev/ttyUSB0", "-o=cap.pcap"]).unwrap();
        assert_eq!(space.serport, inline.serport);
        assert_eq!(space.output, inline.output);
        assert_eq!(inline.output.as_deref(), Some("cap.pcap"));
        // long-form aliases too
        let long = parse(&["--serport", "/dev/ttyUSB0", "--output", "cap.pcap"]).unwrap();
        assert_eq!(long.serport, "/dev/ttyUSB0");
        assert_eq!(long.output.as_deref(), Some("cap.pcap"));
    }

    // ----------------------------- options ----------------------------------

    #[test]
    fn advchan_parses_and_rejects_garbage() {
        assert_eq!(parse(&["-s", "x", "-c", "39"]).unwrap().chan, 39);
        assert!(parse(&["-s", "x", "-c", "notanum"]).is_err());
    }

    #[test]
    fn scan_modes_parse() {
        assert_eq!(parse(&["-s", "x", "-A"]).unwrap().mode, SnifferMode::ActiveScan);
        assert_eq!(parse(&["-s", "x", "--scan"]).unwrap().mode, SnifferMode::ActiveScan);
        assert_eq!(parse(&["-s", "x", "-a"]).unwrap().mode, SnifferMode::PassiveScan);
        assert_eq!(parse(&["-s", "x", "--advonly"]).unwrap().mode, SnifferMode::PassiveScan);
    }

    #[test]
    fn boolean_flags_set() {
        let a = parse(&["-s", "x", "-e", "-l", "-q", "-C", "-p", "-d", "--print"]).unwrap();
        assert!(a.ext_adv);
        assert!(a.longrange);
        assert!(a.quiet);
        assert!(a.capture_crc_err);
        assert!(a.pause_done);
        assert!(a.decode_ad);
        assert!(a.print_stdout);
    }

    #[test]
    fn nophychange_clears_phy_preload() {
        assert_eq!(parse(&["-s", "x", "-n"]).unwrap().phy_preload, None);
        assert_eq!(parse(&["-s", "x", "--nophychange"]).unwrap().phy_preload, None);
    }

    #[test]
    fn mac_filter_parses_reversed() {
        let a = parse(&["-s", "x", "-m", "CA:FE:13:37:00:01"]).unwrap();
        assert_eq!(a.targ_mac, Some([0x01, 0x00, 0x37, 0x13, 0xFE, 0xCA]));
    }

    #[test]
    fn rssi_is_clamped_to_i8_range() {
        // take_val() grabs the next token unconditionally, so a leading-dash
        // value works here (unlike clap).
        assert_eq!(parse(&["-s", "x", "-r", "-200"]).unwrap().rssi_min, -128);
        assert_eq!(parse(&["-s", "x", "-r", "200"]).unwrap().rssi_min, 127);
        assert_eq!(parse(&["-s", "x", "-r", "-60"]).unwrap().rssi_min, -60);
    }

    #[test]
    fn preload_baud_duration_label_parse() {
        let a = parse(&[
            "-s", "x",
            "-Q", "6:0,10:5",
            "-b", "921600",
            "--duration", "30",
            "--label", "ch37",
        ])
        .unwrap();
        assert_eq!(a.preload, vec![(6, 0), (10, 5)]);
        assert_eq!(a.baud, 921_600);
        assert_eq!(a.duration_s, Some(30));
        assert_eq!(a.label, "ch37"); // explicit label overrides serport basename
    }

    #[test]
    fn unknown_flag_is_rejected() {
        let err = parse(&["-s", "x", "--bogus"]).unwrap_err();
        assert!(err.contains("unknown arg"), "got: {err}");
    }

    // ------------------- cross-flag validation + hop3 -----------------------

    #[test]
    fn mac_irk_string_filters_are_mutually_exclusive() {
        let err = parse(&[
            "-s", "x",
            "-m", "CA:FE:13:37:00:01",
            "-i", "000102030405060708090a0b0c0d0e0f",
        ])
        .unwrap_err();
        assert!(err.contains("mutually exclusive"), "got: {err}");
    }

    #[test]
    fn hop_requires_a_target_filter() {
        let err = parse(&["-s", "x", "-H"]).unwrap_err();
        assert!(err.contains("hop requires a target"), "got: {err}");
    }

    #[test]
    fn hop_conflicts_with_longrange_and_explicit_channel() {
        // -m supplies a target so we get past the "hop requires target" check.
        assert!(parse(&["-s", "x", "-m", "CA:FE:13:37:00:01", "-l", "-H"])
            .unwrap_err()
            .contains("long range"));
        assert!(parse(&["-s", "x", "-m", "CA:FE:13:37:00:01", "-c", "38", "-H"])
            .unwrap_err()
            .contains("don't specify -c with -H"));
    }

    #[test]
    fn hop3_derivation_mirrors_python() {
        // Target + default channel + legacy adv → hop3 on.
        assert!(parse(&["-s", "x", "-m", "CA:FE:13:37:00:01"]).unwrap().hop3);
        // Explicit -c kills hop3.
        assert!(!parse(&["-s", "x", "-m", "CA:FE:13:37:00:01", "-c", "38"]).unwrap().hop3);
        // -e (extended adv) without explicit -H kills hop3.
        assert!(!parse(&["-s", "x", "-m", "CA:FE:13:37:00:01", "-e"]).unwrap().hop3);
        // No target → hop3 stays off.
        assert!(!parse(&["-s", "x"]).unwrap().hop3);
    }
}
