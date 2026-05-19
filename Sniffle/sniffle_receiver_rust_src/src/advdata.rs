//! BLE advertising-data decoder — Rust port of
//! `Sniffle/python_cli/sniffle/advdata/{decoder,ad_types,msd_apple,msd_microsoft}.py`.
//!
//! Surface API is intentionally tiny: `decode(data)` walks the LTV stream
//! and returns a `Vec<String>`, one entry per AD record, each already
//! formatted with the same `"    "` (4-space) continuation indent that
//! `sniff_receiver.py -d` produces. The caller (sniff_receiver-style
//! `print_packet`) just prints each string verbatim.
//!
//! Coverage matches the Python implementation:
//!   * 0x01 Flags
//!   * 0x02/0x03 Service-UUID16 list (with assigned-numbers lookup)
//!   * 0x04/0x05 Service-UUID32 list
//!   * 0x06/0x07 Service-UUID128 list
//!   * 0x08/0x09 Shortened/Complete Local Name
//!   * 0x0A TX Power Level
//!   * 0x16/0x20/0x21 Service Data (16/32/128-bit)
//!   * 0xFF Manufacturer-Specific Data
//!       - Microsoft (0x0006): BLE Beacon decode
//!       - Apple    (0x004C): Continuity message stream
//!         (iBeacon / AirDrop / AirPlay Target / Nearby Info typed; others raw)
//!   * Anything else → "Unknown Advertising Data Type: 0xNN" + hexdump
//!
//! Misparses on a record are isolated to that record (Python's
//! `record_from_type_data` semantics: a class constructor raising sets
//! `malformed=True` and produces the generic fallback).

use std::fmt::Write;

use crate::advdata_constants::{AD_TYPES, COMPANY_IDENTIFIERS, SERVICE_UUIDS16};

// =====================================================================
// Top-level walk
// =====================================================================

/// Decode one full advertising-data buffer. Returns one formatted string
/// per AD record.
///
/// Walk semantics match Python `decoder.decode_adv_data` exactly:
///   * We need at least `i+1 < data.len()` (i.e. a length byte AND a
///     type byte) to attempt a record. If type byte is past EOF, stop.
///   * A length byte of 0 means an empty value — Python still emits a
///     record for it (constructor sees empty data, raises, falls back to
///     malformed AdvDataRecord). We mirror that and advance by 1.
///   * A length byte that overruns the buffer is *silently truncated* by
///     Python's slice (`data[i+2 : i+1+l]`). We do the same so the
///     payload's tail still gets decoded.
pub fn decode(data: &[u8]) -> Vec<String> {
    let mut out = Vec::new();
    let mut i = 0;
    while i + 1 < data.len() {
        let l = data[i] as usize;
        let t = data[i + 1];
        // Python: d = data[i+2 : i+1+l]  — slice silently truncates.
        let v_start = i + 2;
        let v_end_unclamped = i + 1 + l;
        let v_end = v_end_unclamped.min(data.len()).max(v_start);
        let v = &data[v_start..v_end];
        out.push(format_record(t, v));
        i += 1 + l;
    }
    out
}

// =====================================================================
// Lookup helpers (binary search over sorted-by-key static slices)
// =====================================================================

fn lookup<K: Copy + Ord>(table: &[(K, &'static str)], key: K) -> Option<&'static str> {
    table.binary_search_by_key(&key, |&(k, _)| k).ok().map(|i| table[i].1)
}

fn company_name(id: u16) -> Option<&'static str> { lookup(COMPANY_IDENTIFIERS, id) }
fn ad_type_name(t: u8) -> Option<&'static str> { lookup(AD_TYPES, t) }
fn service16_name(u: u16) -> Option<&'static str> { lookup(SERVICE_UUIDS16, u) }

fn str_type(t: u8) -> String {
    match ad_type_name(t) {
        Some(s) => s.to_string(),
        None => format!("Unknown Advertising Data Type: 0x{:02X}", t),
    }
}

fn str_service16(u: u16) -> String {
    match service16_name(u) {
        Some(s) => format!("0x{:04X} ({})", u, s),
        None => format!("0x{:04X}", u),
    }
}

fn str_company(id: u16) -> String {
    match company_name(id) {
        Some(s) => format!("0x{:04X} ({})", id, s),
        None => format!("0x{:04X}", id),
    }
}

fn hexline(d: &[u8]) -> String {
    let mut s = String::with_capacity(d.len() * 3);
    for (i, b) in d.iter().enumerate() {
        if i > 0 { s.push(' '); }
        write!(s, "{:02X}", b).unwrap();
    }
    s
}

// Python's repr(bytes) — matches CPython byte-string repr exactly,
// including the delimiter-selection rule: use `"…"` iff the byte
// sequence contains b'\'' but not b'"'; otherwise use `'…'` and escape
// any embedded b'\'' as `\\'`. This matters for parity with Sniffle's
// "Value: %s" / "Data: %s" formatting which feeds `repr(bytes)`.
fn py_repr_bytes(d: &[u8]) -> String {
    let has_sq = d.contains(&b'\'');
    let has_dq = d.contains(&b'"');
    let quote: u8 = if has_sq && !has_dq { b'"' } else { b'\'' };

    let mut s = String::with_capacity(d.len() + 3);
    s.push('b');
    s.push(quote as char);
    for &b in d {
        match b {
            b'\\' => s.push_str("\\\\"),
            // Only escape the active delimiter quote.
            b'\'' if quote == b'\'' => s.push_str("\\'"),
            b'"'  if quote == b'"'  => s.push_str("\\\""),
            b'\n' => s.push_str("\\n"),
            b'\r' => s.push_str("\\r"),
            b'\t' => s.push_str("\\t"),
            0x20..=0x7E => s.push(b as char),
            _ => write!(s, "\\x{:02x}", b).unwrap(),
        }
    }
    s.push(quote as char);
    s
}

/// Format 16 bytes as a canonical UUID string, taking the bytes
/// **directly** (no endian swap). Sniffle's Python uses
/// `uuid.UUID(bytes=...)` everywhere it formats a 128-bit UUID — both
/// for BLE ServiceList128/ServiceData128 fields and for Apple iBeacon's
/// Proximity UUID. `UUID(bytes=...)` treats the input as big-endian /
/// network order, which means Sniffle effectively displays whatever
/// wire-order bytes it sees as the canonical hex string with no swap.
///
/// (This means for BLE service UUIDs — which the spec encodes
/// little-endian on the wire — Sniffle's display is the byte-reversed
/// canonical form. That's "wrong" by spec but matches Sniffle exactly,
/// which is the parity contract for this Rust port.)
fn uuid_canonical(bytes: &[u8]) -> String {
    debug_assert_eq!(bytes.len(), 16);
    format!(
        "{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
        bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7],
        bytes[8], bytes[9], bytes[10], bytes[11], bytes[12], bytes[13], bytes[14], bytes[15],
    )
}

// =====================================================================
// Per-record dispatch
// =====================================================================

/// Format one AD record. Returns "<header>\n    <line>\n    <line>…" (no
/// trailing newline). Mirrors the Python `AdvDataRecord.str_lines()`
/// chain — first line is the header, subsequent lines are indented 4 sp.
fn format_record(t: u8, v: &[u8]) -> String {
    // Try the typed decoder; on any panic-like condition fall back to
    // the generic "malformed" presentation.
    let lines: Vec<String> = match try_typed(t, v) {
        Some(lines) => lines,
        None => fallback_lines(t, v, true),
    };
    lines.join("\n    ")
}

fn try_typed(t: u8, v: &[u8]) -> Option<Vec<String>> {
    match t {
        0x01 => flags(v),
        0x02 | 0x03 => service_list16(t, v),
        0x04 | 0x05 => service_list32(t, v),
        0x06 | 0x07 => service_list128(t, v),
        0x08 | 0x09 => local_name(t, v),
        0x0A => tx_power(v),
        0x16 => service_data16(v),
        0x20 => service_data32(v),
        0x21 => service_data128(v),
        0xFF => msd_try(v),       // None falls back to malformed AdvDataRecord
        _ => Some(fallback_lines(t, v, false)),
    }
}

fn fallback_lines(t: u8, v: &[u8], malformed: bool) -> Vec<String> {
    let mut lines = vec![str_type(t)];
    if malformed {
        lines.push("Malformed".to_string());
    }
    lines.push(format!("Length: {}", v.len()));
    lines.push(format!("Value: {}", py_repr_bytes(v)));
    lines
}

// =====================================================================
// 0x01 Flags
// =====================================================================

fn flags(v: &[u8]) -> Option<Vec<String>> {
    if v.len() != 1 { return None; }
    Some(vec![format!("{}: 0x{:02X}", str_type(0x01), v[0])])
}

// =====================================================================
// 0x02/0x03 ServiceList16,  0x04/0x05 ServiceList32,  0x06/0x07 ServiceList128
// =====================================================================

fn service_list16(t: u8, v: &[u8]) -> Option<Vec<String>> {
    if v.len() % 2 != 0 { return None; }
    let mut lines = vec![str_type(t)];
    for chunk in v.chunks_exact(2) {
        let u = u16::from_le_bytes([chunk[0], chunk[1]]);
        lines.push(str_service16(u));
    }
    Some(lines)
}

fn service_list32(t: u8, v: &[u8]) -> Option<Vec<String>> {
    if v.len() % 4 != 0 { return None; }
    let mut lines = vec![str_type(t)];
    for chunk in v.chunks_exact(4) {
        let u = u32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]);
        lines.push(format!("0x{:08X}", u));
    }
    Some(lines)
}

fn service_list128(t: u8, v: &[u8]) -> Option<Vec<String>> {
    if v.len() % 16 != 0 { return None; }
    let mut lines = vec![str_type(t)];
    for chunk in v.chunks_exact(16) {
        lines.push(uuid_canonical(chunk));
    }
    Some(lines)
}

// =====================================================================
// 0x08/0x09 Local name
// =====================================================================

fn local_name(t: u8, v: &[u8]) -> Option<Vec<String>> {
    let name = std::str::from_utf8(v).ok()?;
    Some(vec![format!("{}: {}", str_type(t), name)])
}

// =====================================================================
// 0x0A TX Power Level
// =====================================================================

fn tx_power(v: &[u8]) -> Option<Vec<String>> {
    if v.len() != 1 { return None; }
    let p = v[0] as i8;
    Some(vec![format!("{}: {} dBm", str_type(0x0A), p)])
}

// =====================================================================
// 0x16/0x20/0x21 Service Data
// =====================================================================

fn service_data16(v: &[u8]) -> Option<Vec<String>> {
    if v.len() < 2 { return None; }
    let u = u16::from_le_bytes([v[0], v[1]]);
    let body = &v[2..];
    Some(vec![
        str_type(0x16),
        format!("Service: {}", str_service16(u)),
        format!("Data Length: {}", body.len()),
        format!("Data: {}", py_repr_bytes(body)),
    ])
}

fn service_data32(v: &[u8]) -> Option<Vec<String>> {
    if v.len() < 4 { return None; }
    let u = u32::from_le_bytes([v[0], v[1], v[2], v[3]]);
    let body = &v[4..];
    Some(vec![
        str_type(0x20),
        format!("Service: 0x{:08X}", u),
        format!("Data Length: {}", body.len()),
        format!("Data: {}", py_repr_bytes(body)),
    ])
}

fn service_data128(v: &[u8]) -> Option<Vec<String>> {
    if v.len() < 16 { return None; }
    let uuid = uuid_canonical(&v[..16]);
    let body = &v[16..];
    Some(vec![
        str_type(0x21),
        format!("Service: {}", uuid),
        format!("Data Length: {}", body.len()),
        format!("Data: {}", py_repr_bytes(body)),
    ])
}

// =====================================================================
// 0xFF Manufacturer-Specific Data, with Apple + Microsoft subdecoders
// =====================================================================

/// MSD dispatch. Returns `None` to signal "fall back to generic
/// AdvDataRecord with malformed=true" (Python's record_from_type_data
/// exception path).
fn msd_try(v: &[u8]) -> Option<Vec<String>> {
    if v.len() < 2 {
        // Length too short to even hold company id — Python's
        // ManufacturerSpecificDataRecord.__init__ raises on unpack.
        return None;
    }
    let company = u16::from_le_bytes([v[0], v[1]]);
    let body = &v[2..];

    match company {
        0x004C => Some(msd_apple(body)),
        // Microsoft strict-format check: any deviation → malformed fallback
        0x0006 => msd_microsoft_try(body),
        _ => Some(generic_msd(company, body)),
    }
}

fn generic_msd(company: u16, body: &[u8]) -> Vec<String> {
    vec![
        str_type(0xFF),
        format!("Company: {}", str_company(company)),
        format!("Data Length: {}", body.len()),
        format!("Data: {}", py_repr_bytes(body)),
    ]
}

// ---------------------------------------------------------------------
// Apple Continuity (BLE MSD 0x004C)
// ---------------------------------------------------------------------

fn apple_message_type_name(t: u8) -> &'static str {
    match t {
        0x02 => "iBeacon",
        0x03 => "AirPrint",
        0x05 => "AirDrop",
        0x06 => "HomeKit",
        0x07 => "Proximity Pairing",
        0x08 => "Hey Siri",
        0x09 => "AirPlay Target",
        0x0A => "AirPlay Source",
        0x0B => "MagicSwitch",
        0x0C => "Handoff",
        0x0D => "Tethering Target Presence",
        0x0E => "Tethering Source Presence",
        0x0F => "Nearby Action",
        0x10 => "Nearby Info",
        0x12 => "Find My",
        _ => "",
    }
}

fn apple_msg_type_str(t: u8) -> String {
    let name = apple_message_type_name(t);
    if name.is_empty() {
        format!("Unknown (0x{:02X})", t)
    } else {
        format!("{} (0x{:02X})", name, t)
    }
}

fn msd_apple(body: &[u8]) -> Vec<String> {
    let mut lines = vec![
        str_type(0xFF),
        format!("Company: {}", str_company(0x004C)),
    ];
    // body is a stream of (type, len, value) tuples — except for type 0x01
    // (Python comments "I don't know what these messages are"), which has no
    // length byte and consumes the rest of the buffer.
    let mut i = 0;
    while i < body.len() {
        let t = body[i];
        let l = if t != 0x01 {
            if i + 1 >= body.len() { break; }
            body[i + 1] as usize
        } else {
            // length implied by remaining bytes (Python idiom)
            if body.len() < i + 2 { break; }
            body.len() - i - 2
        };
        if i + 2 + l > body.len() { break; }
        let v = &body[i + 2..i + 2 + l];
        i += 2 + l;
        lines.extend(apple_message_lines(t, v));
    }
    lines
}

fn apple_message_lines(t: u8, data: &[u8]) -> Vec<String> {
    // Try a typed decoder; fall back to generic Apple-message presentation.
    if let Some(lines) = apple_message_typed(t, data) {
        return lines;
    }
    vec![
        apple_msg_type_str(t),
        format!("    Data: {}", py_repr_bytes(data)),
    ]
}

fn apple_message_typed(t: u8, data: &[u8]) -> Option<Vec<String>> {
    match t {
        0x02 => apple_ibeacon(data),
        0x09 => apple_airplay_target(data),
        0x10 => apple_nearby_info(data),
        // 0x05 AirDrop has no typed body in the Python port (just generic).
        _ => None,
    }
}

fn apple_ibeacon(data: &[u8]) -> Option<Vec<String>> {
    if data.len() != 21 { return None; }
    let prox = uuid_canonical(&data[..16]);
    let major = u16::from_le_bytes([data[16], data[17]]);
    let minor = u16::from_le_bytes([data[18], data[19]]);
    let meas = data[20] as i8;
    Some(vec![
        apple_msg_type_str(0x02),
        format!("    Proximity UUID: {}", prox),
        format!("    Major: 0x{:04X}", major),
        format!("    Minor: 0x{:04X}", minor),
        format!("    Measured Power: {}", meas),
    ])
}

fn apple_airplay_target(data: &[u8]) -> Option<Vec<String>> {
    if data.len() < 6 { return None; }
    let flags = data[0];
    let seed = data[1];
    let ip = &data[2..6];
    let mut out = vec![
        apple_msg_type_str(0x09),
        format!("    Flags: 0x{:02X}", flags),
        format!("    Seed: 0x{:02X}", seed),
        format!("    IP: {}.{}.{}.{}", ip[0], ip[1], ip[2], ip[3]),
    ];
    if data.len() > 6 {
        out.push(format!("    Extra: {}", hexline(&data[6..])));
    }
    Some(out)
}

fn apple_nearby_info(data: &[u8]) -> Option<Vec<String>> {
    if data.len() < 2 { return None; }
    let status = data[0] & 0x0F;
    let action = data[0] >> 4;
    let dflags = data[1];

    // Status flag descriptions
    let status_flags = [(0x01u8, "Primary iCloud device"), (0x04, "AirDrop receive enabled")];
    let mut s_desc = Vec::new();
    for (f, n) in status_flags { if f & status != 0 { s_desc.push(n); } }
    let s_str = if s_desc.is_empty() {
        format!("0x{:X}", status)
    } else {
        format!("0x{:X} ({})", status, s_desc.join(", "))
    };

    // Action codes
    let action_str = match action {
        0x00 => "0x0 (Activity level is not known)".to_string(),
        0x01 => "0x1 (Activity reporting is disabled)".to_string(),
        0x03 => "0x3 (User is idle)".to_string(),
        0x05 => "0x5 (Audio is playing with the screen off)".to_string(),
        0x07 => "0x7 (Screen is on)".to_string(),
        0x09 => "0x9 (Screen on and video playing)".to_string(),
        0x0A => "0xA (Watch is on wrist and unlocked)".to_string(),
        0x0B => "0xB (Recent user interaction)".to_string(),
        0x0D => "0xD (User is driving a vehicle)".to_string(),
        0x0E => "0xE (Phone call or Facetime)".to_string(),
        _ => format!("0x{:X}", action),
    };

    // Data flag descriptions
    let data_flags = [
        (0x02u8, "Four byte auth tag"),
        (0x04, "Wi-Fi on"),
        (0x10, "Auth tag present"),
        (0x20, "Apple Watch locked"),
        (0x40, "Apple Watch auto unlock"),
        (0x80, "Auto unlock"),
    ];
    let mut d_desc = Vec::new();
    for (f, n) in data_flags { if f & dflags != 0 { d_desc.push(n); } }
    let d_str = if d_desc.is_empty() {
        format!("0x{:02X}", dflags)
    } else {
        format!("0x{:02X} ({})", dflags, d_desc.join(", "))
    };

    let mut lines = vec![
        apple_msg_type_str(0x10),
        format!("    Status Flags: {}", s_str),
        format!("    Action Code: {}", action_str),
        format!("    Data Flags: {}", d_str),
    ];
    if data.len() > 2 {
        lines.push(format!("    Extra: {}", hexline(&data[2..])));
    }
    Some(lines)
}

// ---------------------------------------------------------------------
// Microsoft BLE Beacon (MSD 0x0006)
// ---------------------------------------------------------------------

fn msd_microsoft_try(body: &[u8]) -> Option<Vec<String>> {
    // Python asserts company_data length == 27 + scenario_type == 1.
    // On any deviation, Python raises (AssertionError) and
    // record_from_type_data falls back to the generic AdvDataRecord
    // with malformed=true on the FULL MSD value (including company id).
    // We signal that with `None` so the caller can produce the right fallback.
    if body.len() != 27 || body[0] != 1 {
        return None;
    }
    // device_type is low 5 bits of byte 1 (version check disabled in Python)
    let device_type = body[1] & 0x1F;
    let scenario_byte = body[2];
    // Python asserts scenario_byte >> 5 == 1 and (scenario_byte & 0x1E) == 0
    if scenario_byte >> 5 != 1 || (scenario_byte & 0x1E) != 0 {
        return None;
    }
    let flags = scenario_byte & 0x1F;
    let bt_addr_dev_id = (body[3] & 0x4) != 0;
    let device_status = body[3] >> 4;
    let salt = u32::from_le_bytes([body[4], body[5], body[6], body[7]]);
    let device_hash = &body[8..27];

    let device_type_str = match device_type {
         1 => "Xbox One",
         6 => "Apple iPhone",
         7 => "Apple iPad",
         8 => "Android device",
         9 => "Windows 10 Desktop",
        11 => "Windows 10 Phone",
        12 => "Linux device",
        13 => "Windows IoT",
        14 => "Surface Hub",
        15 => "Windows laptop",
        16 => "Windows tablet",
        _ => "",
    };
    let device_type_pretty = if device_type_str.is_empty() {
        format!("Unknown ({})", device_type)
    } else {
        device_type_str.to_string()
    };

    let status_flag_map = [
        (0x01u8, "Hosted by remote session"),
        (0x02, "Session hosting status unavailable"),
        (0x04, "NearShare supported for same user"),
        (0x08, "NearShare supported"),
    ];
    let mut status_descs = Vec::new();
    for (f, n) in status_flag_map { if f & device_status != 0 { status_descs.push(n); } }
    let status_str = if status_descs.is_empty() { "None".to_string() } else { status_descs.join(", ") };

    let mut flag_descs: Vec<&'static str> = Vec::new();
    if flags & 0x01 != 0 { flag_descs.push("NearBy share to everyone"); }
    if bt_addr_dev_id   { flag_descs.push("Bluetoth address as device ID"); }
    let flags_str = if flag_descs.is_empty() { "None".to_string() } else { flag_descs.join(", ") };

    let mut hash_hex = String::with_capacity(device_hash.len() * 2);
    for b in device_hash { write!(hash_hex, "{:02x}", b).unwrap(); }

    Some(vec![
        str_type(0xFF),
        format!("Company: {}", str_company(0x0006)),
        format!("Device Type: {}", device_type_pretty),
        format!("Device Status: {}", status_str),
        format!("Flags: {}", flags_str),
        format!("Salt: 0x{:08X}", salt),
        format!("Device Hash: {}", hash_hex),
    ])
}

// =====================================================================
// Tests — every assertion below is verified byte-for-byte against
// Python `sniffle.advdata.decoder.decode_adv_data` output on the same
// payload (see `tests/python_parity_oracle.py` in the repo for how the
// expected strings were captured). When you add a new decoder branch
// here, re-run the oracle and paste the new expected string in.
// =====================================================================

#[cfg(test)]
mod tests {
    use super::*;

    /// Render the full decoded output of one buffer as a single joined
    /// String (records separated by "\n", lines within a record by
    /// "\n    " — same as `for r in records: print(r)` in Python).
    fn render(data: &[u8]) -> String {
        decode(data).join("\n")
    }

    // ----- Single-record cases (each one verified against the Python
    // oracle output captured 2026-05-18). -----

    #[test]
    fn flags() {
        // payload (3 bytes): 020106
        assert_eq!(render(&[0x02, 0x01, 0x06]), "Flags: 0x06");
    }

    #[test]
    fn complete_local_name() {
        // payload (7 bytes): 06095556503031
        assert_eq!(
            render(&[0x06, 0x09, b'U', b'V', b'P', b'0', b'1']),
            "Complete Local Name: UVP01",
        );
    }

    #[test]
    fn shortened_local_name() {
        // payload (3 bytes): 020841
        assert_eq!(render(&[0x02, 0x08, b'A']), "Shortened Local Name: A");
    }

    #[test]
    fn tx_power_negative() {
        // -8 dBm — verifies signed-byte interpretation
        assert_eq!(render(&[0x02, 0x0A, 0xF8]), "Tx Power Level: -8 dBm");
    }

    #[test]
    fn tx_power_positive() {
        // +20 dBm — the UVP01 dev board's actual value
        assert_eq!(render(&[0x02, 0x0A, 0x14]), "Tx Power Level: 20 dBm");
    }

    #[test]
    fn service_list16_with_lookup() {
        // 0x180A=Device Information, 0x180F=Battery
        let expected = "Complete List of 16-bit Service or Service Class UUIDs\n    \
                        0x180A (Device Information)\n    \
                        0x180F (Battery)";
        assert_eq!(render(&[0x05, 0x03, 0x0A, 0x18, 0x0F, 0x18]), expected);
    }

    #[test]
    fn service_list16_unknown_uuid_omits_name() {
        let expected = "Complete List of 16-bit Service or Service Class UUIDs\n    \
                        0xABCD";
        assert_eq!(render(&[0x03, 0x03, 0xCD, 0xAB]), expected);
    }

    #[test]
    fn service_list32() {
        let expected = "Complete List of 32-bit Service or Service Class UUIDs\n    \
                        0x12345678";
        assert_eq!(render(&[0x05, 0x05, 0x78, 0x56, 0x34, 0x12]), expected);
    }

    #[test]
    fn service_list128() {
        // 16-byte UUID is read LE on the wire, displayed canonical form.
        let mut buf = vec![0x11, 0x07];
        buf.extend(0..16u8);
        let expected = "Complete List of 128-bit Service or Service Class UUIDs\n    \
                        00010203-0405-0607-0809-0a0b0c0d0e0f";
        assert_eq!(render(&buf), expected);
    }

    #[test]
    fn service_data16() {
        let expected = "Service Data - 16-bit UUID\n    \
                        Service: 0x180F (Battery)\n    \
                        Data Length: 3\n    \
                        Data: b'\\xaa\\xbb\\xcc'";
        assert_eq!(
            render(&[0x06, 0x16, 0x0F, 0x18, 0xAA, 0xBB, 0xCC]),
            expected,
        );
    }

    #[test]
    fn service_data32() {
        let expected = "Service Data - 32-bit UUID\n    \
                        Service: 0x12345678\n    \
                        Data Length: 3\n    \
                        Data: b'\\xaa\\xbb\\xcc'";
        assert_eq!(
            render(&[0x08, 0x20, 0x78, 0x56, 0x34, 0x12, 0xAA, 0xBB, 0xCC]),
            expected,
        );
    }

    #[test]
    fn service_data128() {
        // LTV length byte INCLUDES the type byte. Payload 0x12 0x21 + 18B
        // means length=18 → value is 17 bytes (one type byte + 16-UUID +
        // 1-data). Python service_data = data[16:17] = single trailing 0xDE.
        let mut buf = vec![0x12, 0x21];
        buf.extend(0..16u8);
        buf.extend([0xDE, 0xAD]);   // second byte falls *past* the record
        let expected = "Service Data - 128-bit UUID\n    \
                        Service: 00010203-0405-0607-0809-0a0b0c0d0e0f\n    \
                        Data Length: 1\n    \
                        Data: b'\\xde'";
        assert_eq!(render(&buf), expected);
    }

    // NOTE on indentation for Apple sub-fields below: every Apple message's
    // str_lines() emits its own field lines with a leading "    " (4 spaces).
    // The outer AppleMSDRecord then joins everything with "\n    " (another
    // 4 spaces). Total leading whitespace for an Apple sub-field = 8 spaces.
    // That's what `iBeacon …` etc. produce in Python and what we must match.

    #[test]
    fn ibeacon() {
        // 0xFF | 4C 00 | 02 15 | <16-byte UUID> <major LE 0x0001>
        //   <minor LE 0x0002> <measured power 0xC5 = -59>
        let mut buf = vec![0x1A, 0xFF, 0x4C, 0x00, 0x02, 0x15];
        buf.extend([0x11; 16]);
        buf.extend([0x01, 0x00, 0x02, 0x00, 0xC5]);
        let expected = "Manufacturer Specific Data\n    \
                        Company: 0x004C (Apple, Inc.)\n    \
                        iBeacon (0x02)\n        \
                            Proximity UUID: 11111111-1111-1111-1111-111111111111\n        \
                            Major: 0x0001\n        \
                            Minor: 0x0002\n        \
                            Measured Power: -59";
        assert_eq!(render(&buf), expected);
    }

    #[test]
    fn apple_airdrop_falls_to_generic_message() {
        // AirDrop (0x05), 0 data bytes — Python AirDropMessage subclass
        // has no extra fields, just generic AppleMessage formatting.
        let expected = "Manufacturer Specific Data\n    \
                        Company: 0x004C (Apple, Inc.)\n    \
                        AirDrop (0x05)\n        \
                            Data: b''";
        assert_eq!(render(&[0x05, 0xFF, 0x4C, 0x00, 0x05, 0x00]), expected);
    }

    #[test]
    fn apple_airplay_target() {
        // AirPlay Target (0x09), 6-byte body = flags + seed + 4-byte IP
        let expected = "Manufacturer Specific Data\n    \
                        Company: 0x004C (Apple, Inc.)\n    \
                        AirPlay Target (0x09)\n        \
                            Flags: 0x13\n        \
                            Seed: 0x98\n        \
                            IP: 192.168.1.165";
        assert_eq!(
            render(&[0x0B, 0xFF, 0x4C, 0x00, 0x09, 0x06, 0x13, 0x98, 192, 168, 1, 165]),
            expected,
        );
    }

    #[test]
    fn apple_nearby_info_with_flag_lookups() {
        let expected = "Manufacturer Specific Data\n    \
                        Company: 0x004C (Apple, Inc.)\n    \
                        Nearby Info (0x10)\n        \
                            Status Flags: 0x7 (Primary iCloud device, AirDrop receive enabled)\n        \
                            Action Code: 0x0 (Activity level is not known)\n        \
                            Data Flags: 0x04 (Wi-Fi on)";
        assert_eq!(
            render(&[0x07, 0xFF, 0x4C, 0x00, 0x10, 0x02, 0x07, 0x04]),
            expected,
        );
    }

    #[test]
    fn apple_type01_length_implied() {
        // Type 0x01 special case: Python skips the length byte and lets
        // the value consume "rest of buffer minus 2 bytes". For body
        // `01 02 03 04`, that means t=0x01, len=2, v=[0x03, 0x04].
        let expected = "Manufacturer Specific Data\n    \
                        Company: 0x004C (Apple, Inc.)\n    \
                        Unknown (0x01)\n        \
                            Data: b'\\x03\\x04'";
        assert_eq!(
            render(&[0x07, 0xFF, 0x4C, 0x00, 0x01, 0x02, 0x03, 0x04]),
            expected,
        );
    }

    #[test]
    fn microsoft_msd_valid() {
        // 27-byte Microsoft beacon body. Scenario=1, dev_type=1 (Xbox),
        // status nibble = 4 (NearShare supported for same user),
        // dev-id bit set, salt=0xDEADBEEF, 19-byte hash.
        let mut buf = vec![0x1E, 0xFF, 0x06, 0x00,
            0x01, 0x21, 0x20, 0x44, 0xEF, 0xBE, 0xAD, 0xDE];
        buf.extend((0xA0..0xA0 + 19u32).map(|n| n as u8));
        let expected = "Manufacturer Specific Data\n    \
                        Company: 0x0006 (Microsoft)\n    \
                        Device Type: Xbox One\n    \
                        Device Status: NearShare supported for same user\n    \
                        Flags: Bluetoth address as device ID\n    \
                        Salt: 0xDEADBEEF\n    \
                        Device Hash: a0a1a2a3a4a5a6a7a8a9aaabacadaeafb0b1b2";
        assert_eq!(render(&buf), expected);
    }

    #[test]
    fn microsoft_msd_invalid_falls_back_to_generic_advdata_record() {
        // 5-byte body (3 bytes after company id) — fails the len==27
        // assertion. Python returns the FULL 5-byte payload as a
        // malformed AdvDataRecord, not the company-stripped generic MSD.
        let expected = "Manufacturer Specific Data\n    \
                        Malformed\n    \
                        Length: 5\n    \
                        Value: b'\\x06\\x00\\xff\\xff\\xff'";
        assert_eq!(
            render(&[0x06, 0xFF, 0x06, 0x00, 0xFF, 0xFF, 0xFF]),
            expected,
        );
    }

    #[test]
    fn generic_msd_with_unknown_company() {
        let expected = "Manufacturer Specific Data\n    \
                        Company: 0xABCD\n    \
                        Data Length: 3\n    \
                        Data: b'\\xde\\xad\\xbe'";
        assert_eq!(
            render(&[0x06, 0xFF, 0xCD, 0xAB, 0xDE, 0xAD, 0xBE]),
            expected,
        );
    }

    #[test]
    fn msd_too_short_to_have_company_falls_back() {
        // Only 1 byte after the type → can't even hold the company id.
        // Python ManufacturerSpecificDataRecord.__init__ raises on unpack.
        let expected = "Manufacturer Specific Data\n    \
                        Malformed\n    \
                        Length: 1\n    \
                        Value: b'\\xcd'";
        assert_eq!(render(&[0x02, 0xFF, 0xCD]), expected);
    }

    #[test]
    fn unknown_type_falls_back_to_hex_dump() {
        let expected = "Unknown Advertising Data Type: 0x7E\n    \
                        Length: 3\n    \
                        Value: b'\\xaa\\xbb\\xcc'";
        assert_eq!(render(&[0x04, 0x7E, 0xAA, 0xBB, 0xCC]), expected);
    }

    // ----- py_repr_bytes parity (CPython delimiter-selection rule) -----

    #[test]
    fn py_repr_no_quotes_uses_single() {
        // Plain printable bytes — single quotes.
        // Python: repr(b'AB') -> b'AB'
        let v: &[u8] = b"AB";
        // Wrap as Service Data 16 so we go through py_repr_bytes
        // Service: 0x180F, service_data = b'AB'
        let expected = "Service Data - 16-bit UUID\n    \
                        Service: 0x180F (Battery)\n    \
                        Data Length: 2\n    \
                        Data: b'AB'";
        let _ = v;
        assert_eq!(render(&[0x05, 0x16, 0x0F, 0x18, b'A', b'B']), expected);
    }

    #[test]
    fn py_repr_single_quote_in_data_switches_to_double() {
        // Bytes contain b'\'' but no b'"' → Python uses double-quote
        // delimiter (and does NOT escape the single quote).
        // Python: repr(b"A'B") -> b"A'B"
        let expected = "Service Data - 16-bit UUID\n    \
                        Service: 0x180F (Battery)\n    \
                        Data Length: 3\n    \
                        Data: b\"A'B\"";
        assert_eq!(render(&[0x06, 0x16, 0x0F, 0x18, b'A', b'\'', b'B']), expected);
    }

    #[test]
    fn py_repr_double_quote_in_data_keeps_single_quotes() {
        // Bytes contain b'"' but no b'\'' → Python keeps single quotes.
        // Python: repr(b'A"B') -> b'A"B'
        let expected = "Service Data - 16-bit UUID\n    \
                        Service: 0x180F (Battery)\n    \
                        Data Length: 3\n    \
                        Data: b'A\"B'";
        assert_eq!(render(&[0x06, 0x16, 0x0F, 0x18, b'A', b'"', b'B']), expected);
    }

    #[test]
    fn py_repr_both_quote_types_in_data_uses_single_and_escapes() {
        // Bytes contain BOTH → Python uses single quotes and escapes b'\''
        // Python: repr(b'A\'B"C') -> b'A\'B"C'
        let expected = "Service Data - 16-bit UUID\n    \
                        Service: 0x180F (Battery)\n    \
                        Data Length: 5\n    \
                        Data: b'A\\'B\"C'";
        assert_eq!(
            render(&[0x08, 0x16, 0x0F, 0x18, b'A', b'\'', b'B', b'"', b'C']),
            expected,
        );
    }

    // ----- Walk semantics: multi-record, malformed, truncated. -----

    #[test]
    fn multiple_records_in_one_payload() {
        let mut buf = Vec::new();
        buf.extend([0x02, 0x01, 0x06]);                          // Flags
        buf.extend([0x06, 0x09, b'U', b'V', b'P', b'0', b'1']); // Local Name
        assert_eq!(
            render(&buf),
            "Flags: 0x06\nComplete Local Name: UVP01",
        );
    }

    #[test]
    fn zero_length_record_then_empty_servicelist128() {
        // Payload 00 01 06:
        //   first  record: l=0 t=0x01 → empty value → Flags malformed
        //   second record: l=1 t=0x06 → empty value → empty Incomplete List128
        // matches Python's exact behavior (slice/no-IndexError walk).
        let expected = "Flags\n    \
                        Malformed\n    \
                        Length: 0\n    \
                        Value: b''\n\
                        Incomplete List of 128-bit Service or Service Class UUIDs";
        assert_eq!(render(&[0x00, 0x01, 0x06]), expected);
    }

    #[test]
    fn truncated_value_silently_uses_available_bytes() {
        // Length claims 5 but only 2 bytes follow. Python slice silently
        // truncates → "Complete Local Name: AB".
        assert_eq!(
            render(&[0x05, 0x09, b'A', b'B']),
            "Complete Local Name: AB",
        );
    }
}
