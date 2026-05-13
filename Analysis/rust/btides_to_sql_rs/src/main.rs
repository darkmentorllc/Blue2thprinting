// Rust port of Analysis/BTIDES_to_SQL.py.
//
// Goal: produce a byte-identical bttest database to the Python importer
// for the same BTIDES input, with as little overhead as possible.
//
// Strategy: parse the JSON once with serde_json, accumulate rows per
// destination table into Vec<...> buffers, then emit one multi-row
// INSERT IGNORE per table at the end (chunked). GPS and LMP_NAME_RES
// preserve the special semantics from the Python (rssi=0 promotion,
// per-bdaddr fragment defragmentation).

use clap::Parser;
use mysql::prelude::*;
use mysql::{Opts, OptsBuilder, Pool, Row, Value};
use once_cell::sync::Lazy;
use regex::Regex;
use serde_json::Value as J;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs::File;
use std::io::BufReader;
use std::time::Instant;

// ------------------------------- constants ----------------------------------
// Mirrors the dispatch table values in Analysis/TME/BT_Data_Types.py and
// Analysis/TME/BTIDES_Data_Types.py — we only redeclare the values we
// actually branch on.

const TYPE_BTIDES_DIR_C2P: i64 = 0;
#[allow(dead_code)]
const TYPE_BTIDES_DIR_P2C: i64 = 1;

// AdvData TLV type bytes
const T_FLAGS: i64 = 0x01;
const T_UUID16_INC: i64 = 0x02;
const T_UUID16_CMP: i64 = 0x03;
const T_UUID32_INC: i64 = 0x04;
const T_UUID32_CMP: i64 = 0x05;
const T_UUID128_INC: i64 = 0x06;
const T_UUID128_CMP: i64 = 0x07;
const T_NAME_SHORT: i64 = 0x08;
const T_NAME_FULL: i64 = 0x09;
const T_TX_POWER: i64 = 0x0a;
const T_COD: i64 = 0x0d;
const T_DEV_ID: i64 = 0x10;
const T_CONN_INT_RANGE: i64 = 0x12;
const T_UUID16_SS: i64 = 0x14;
const T_UUID128_SS: i64 = 0x15;
const T_UUID16_SD: i64 = 0x16;
const T_PUB_TARGET: i64 = 0x17;
const T_RAND_TARGET: i64 = 0x18;
const T_APPEARANCE: i64 = 0x19;
const T_LE_BDADDR: i64 = 0x1b;
const T_LE_ROLE: i64 = 0x1c;
const T_UUID32_SD: i64 = 0x20;
const T_UUID128_SD: i64 = 0x21;
const T_URI: i64 = 0x24;
const T_NAME_BROADCAST: i64 = 0x30;
const T_3D_INFO: i64 = 0x3d;
const T_MSD: i64 = 0xff;

// AdvChan PDU types (after BTIDES_types_to_le_evt_type mapping)
const ADV_IND: i64 = 0;
const ADV_DIRECT_IND: i64 = 1;
const ADV_NONCONN_IND: i64 = 2;
const SCAN_RSP: i64 = 4;
const ADV_SCAN_IND: i64 = 6;
const AUX_ADV_IND: i64 = 7;
// AUX_SCAN_RSP shares value 7 in BT_Data_Types.py (the AUX comment notes the
// collision). We never look up by AUX_SCAN_RSP independently below.

// BTIDES AdvChan top-level types (different namespace than the LE-event-type)
const B_ADV_IND: i64 = 0;
const B_ADV_DIRECT_IND: i64 = 1;
const B_ADV_NONCONN_IND: i64 = 2;
const B_ADV_SCAN_IND: i64 = 3;
const B_AUX_ADV_IND: i64 = 10;
const B_SCAN_RSP: i64 = 20;
const B_AUX_SCAN_RSP: i64 = 21;
const B_EIR: i64 = 50;

fn btides_to_le_evt_type(t: i64) -> i64 {
    // Mirrors BTIDES_types_to_le_evt_type in BTIDES_to_SQL.py.
    match t {
        B_ADV_IND => ADV_IND,
        B_ADV_DIRECT_IND => ADV_DIRECT_IND,
        B_ADV_NONCONN_IND => ADV_NONCONN_IND,
        B_ADV_SCAN_IND => ADV_SCAN_IND,
        B_AUX_ADV_IND => AUX_ADV_IND,
        B_SCAN_RSP => SCAN_RSP,
        B_AUX_SCAN_RSP => SCAN_RSP, // Python returns the SCAN_RSP value here; mirror it
        B_EIR => B_EIR,             // EIR sentinel == 50
        other => other,
    }
}

// LL opcodes we route on
const LL_UNKNOWN_RSP: i64 = 7;
const LL_FEATURE_REQ: i64 = 8;
const LL_FEATURE_RSP: i64 = 9;
const LL_VERSION_IND: i64 = 12;
const LL_PERIPHERAL_FEATURE_REQ: i64 = 14;
const LL_PING_REQ: i64 = 18;
const LL_PING_RSP: i64 = 19;
const LL_LENGTH_REQ: i64 = 20;
const LL_LENGTH_RSP: i64 = 21;
const LL_PHY_REQ: i64 = 22;
const LL_PHY_RSP: i64 = 23;

// LMP base opcodes
const LMP_NAME_RES: i64 = 2;
const LMP_ACCEPTED: i64 = 3;
const LMP_NOT_ACCEPTED: i64 = 4;
const LMP_DETACH: i64 = 7;
const LMP_AUTO_RATE: i64 = 35;
const LMP_PREFERRED_RATE: i64 = 36;
const LMP_VERSION_REQ: i64 = 37;
const LMP_VERSION_RES: i64 = 38;
const LMP_FEATURES_REQ: i64 = 39;
const LMP_FEATURES_RES: i64 = 40;
const LMP_TIMING_ACCURACY_REQ: i64 = 47;
const LMP_SETUP_COMPLETE: i64 = 49;

// LMP extended opcodes (escape 127 + ext opcode)
const EXT_LMP_ACCEPTED_EXT: i64 = 1;
const EXT_LMP_NOT_ACCEPTED_EXT: i64 = 2;
const EXT_LMP_FEATURES_REQ_EXT: i64 = 3;
const EXT_LMP_FEATURES_RES_EXT: i64 = 4;
const EXT_LMP_CHANNEL_CLASSIFICATION: i64 = 17;
const EXT_LMP_POWER_CONTROL_REQ: i64 = 31;
const EXT_LMP_POWER_CONTROL_RES: i64 = 32;

// ATT opcodes
const ATT_FIND_INFORMATION_RSP: i64 = 0x05;
const ATT_READ_REQ: i64 = 0x0a;
const ATT_READ_RSP: i64 = 0x0b;

// L2CAP codes
const L2CAP_CONN_PARAM_UPDATE_REQ: i64 = 0x12;
const L2CAP_CONN_PARAM_UPDATE_RSP: i64 = 0x13;

// SMP opcodes
const SMP_PAIRING_REQUEST: i64 = 1;
const SMP_PAIRING_RESPONSE: i64 = 2;

// SDP PDU id
const SDP_ERROR_RSP_ID: i64 = 0x01;

// EIR sub-types
const EIR_PSRM: i64 = 1;
const EIR_COD: i64 = 2;

// HCI event codes
const HCI_REMOTE_NAME_REQUEST_COMPLETE: i64 = 7;

// ----------------------------- helpers --------------------------------------

#[inline]
fn as_i64(v: &J) -> Option<i64> {
    v.as_i64().or_else(|| v.as_u64().map(|x| x as i64))
}

#[inline]
fn obj_i64(o: &serde_json::Map<String, J>, k: &str) -> Option<i64> {
    o.get(k).and_then(as_i64)
}

#[inline]
fn obj_str<'a>(o: &'a serde_json::Map<String, J>, k: &str) -> Option<&'a str> {
    o.get(k).and_then(|v| v.as_str())
}

fn hex_str_to_bytes(s: &str) -> Vec<u8> {
    // The Python uses bytes.fromhex which tolerates whitespace and ignores
    // case. hex::decode is stricter but the BTIDES inputs we care about are
    // already plain even-length hex.
    hex::decode(s).unwrap_or_default()
}

fn parse_hex_int_u64(s: &str) -> u64 {
    // int(s, 16) but truncating to u64 if it ever grows larger (the schema's
    // largest hex-derived column is BIGINT UNSIGNED).
    u64::from_str_radix(s.trim_start_matches("0x"), 16).unwrap_or(0)
}

// Mirrors convert_UUID128_to_UUID16_if_possible from TME_BTIDES_base.py.
//   * shorter than 32 → returned as-is
//   * 32 hex chars and matches the BT base UUID → returns the embedded UUID16
//   * else → strips dashes, lowercases
static BT_BASE_UUID_RE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"^0000[a-f0-9]{4}00001000800000805f9b34fb$").unwrap());

fn normalize_uuid(uuid: &str) -> String {
    if uuid.len() < 32 {
        return uuid.to_string();
    }
    let lower: String = uuid.trim().to_lowercase().replace('-', "");
    if BT_BASE_UUID_RE.is_match(&lower) {
        lower[4..8].to_string()
    } else {
        lower
    }
}

// Strip dashes only, no lowercasing or UUID16 promotion. Used in places where
// the Python only does `.replace('-','')`.
fn strip_uuid_dashes(uuid: &str) -> String {
    uuid.replace('-', "")
}

// `direction == 0` (C2P) routes to CONNECT_IND.central_bdaddr; everything else
// (including missing direction) routes to peripheral. CONNECT_IND-less
// entries fall back to entry["bdaddr"]/entry["bdaddr_rand"]. The two helpers
// share that scaffolding and only diverge on which side they pull.
fn get_bdaddr_peripheral(entry: &serde_json::Map<String, J>) -> (String, i64) {
    if let Some(c) = entry.get("CONNECT_IND").and_then(|v| v.as_object()) {
        let bdaddr = obj_str(c, "peripheral_bdaddr").unwrap_or("").to_lowercase();
        let r = obj_i64(c, "peripheral_bdaddr_rand").unwrap_or(0);
        return (bdaddr, r);
    }
    (
        entry
            .get("bdaddr")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_lowercase(),
        obj_i64(entry, "bdaddr_rand").unwrap_or(0),
    )
}

fn get_bdaddr_central(entry: &serde_json::Map<String, J>) -> (String, i64) {
    if let Some(c) = entry.get("CONNECT_IND").and_then(|v| v.as_object()) {
        let bdaddr = obj_str(c, "central_bdaddr").unwrap_or("").to_lowercase();
        let r = obj_i64(c, "central_bdaddr_rand").unwrap_or(0);
        return (bdaddr, r);
    }
    (
        entry
            .get("bdaddr")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_lowercase(),
        obj_i64(entry, "bdaddr_rand").unwrap_or(0),
    )
}

// ------------------------- row buffers --------------------------------------
//
// Each table is collected into a Vec<Vec<Value>> where the inner Vec is one
// row's bind values in column order. We flush each at the end of the import
// with a multi-row INSERT IGNORE, chunked so the placeholder list stays
// under MySQL's parameter limit (65535 placeholders / row width).

#[derive(Default)]
struct Buffers {
    // EIR_*
    eir_flags: Vec<Vec<Value>>,        // (bdaddr, lim, gen, bredr_not, c, h)
    eir_uuid16s: Vec<Vec<Value>>,      // (bdaddr, list_type, str)
    eir_uuid32s: Vec<Vec<Value>>,      // (bdaddr, list_type, str)
    eir_uuid128s: Vec<Vec<Value>>,     // (bdaddr, list_type, str)
    eir_name: Vec<Vec<Value>>,         // (bdaddr, dev_name_type, hex)
    eir_tx_power: Vec<Vec<Value>>,     // (bdaddr, tx)
    eir_dev_id: Vec<Vec<Value>>,       // (bdaddr, src, vid, pid, ver)
    eir_uri: Vec<Vec<Value>>,          // (bdaddr, uri_hex)
    eir_3d: Vec<Vec<Value>>,           // (bdaddr, byte1, path_loss)
    eir_msd: Vec<Vec<Value>>,          // (bdaddr, cid, msd_hex)
    eir_psrm: Vec<Vec<Value>>,         // (bdaddr, mode)
    eir_cod: Vec<Vec<Value>>,          // (bdaddr, cod)

    // LE_*
    le_flags: Vec<Vec<Value>>,
    le_uuid16s_list: Vec<Vec<Value>>,
    le_uuid32s_list: Vec<Vec<Value>>,
    le_uuid128s_list: Vec<Vec<Value>>,
    le_name: Vec<Vec<Value>>,
    le_tx_power: Vec<Vec<Value>>,
    le_cod: Vec<Vec<Value>>,
    le_appearance: Vec<Vec<Value>>,
    le_conn_interval: Vec<Vec<Value>>,
    le_uuid16_ss: Vec<Vec<Value>>,
    le_uuid128_ss: Vec<Vec<Value>>,
    le_uuid16_sd: Vec<Vec<Value>>,
    le_uuid32_sd: Vec<Vec<Value>>,
    le_uuid128_sd: Vec<Vec<Value>>,
    le_public_target: Vec<Vec<Value>>,
    le_random_target: Vec<Vec<Value>>,
    le_other_le: Vec<Vec<Value>>,
    le_role: Vec<Vec<Value>>,
    le_uri: Vec<Vec<Value>>,
    le_3d: Vec<Vec<Value>>,
    le_msd: Vec<Vec<Value>>,

    // HCI
    hci_name: Vec<Vec<Value>>,

    // L2CAP
    l2cap_conn_update_req: Vec<Vec<Value>>,
    l2cap_conn_update_rsp: Vec<Vec<Value>>,

    // SMP
    smp_pairing: Vec<Vec<Value>>,

    // SDP
    sdp_error_rsp: Vec<Vec<Value>>,
    sdp_common: Vec<Vec<Value>>,

    // LL
    ll_unknown_rsp: Vec<Vec<Value>>,
    ll_version_ind: Vec<Vec<Value>>,
    ll_features: Vec<Vec<Value>>,
    ll_pings: Vec<Vec<Value>>,
    ll_lengths: Vec<Vec<Value>>,
    ll_phys: Vec<Vec<Value>>,

    // LMP
    lmp_name_res_fragmented: Vec<Vec<Value>>,
    lmp_name_res_defragmented: Vec<Vec<Value>>,
    lmp_accepted: Vec<Vec<Value>>,
    lmp_not_accepted: Vec<Vec<Value>>,
    lmp_accepted_ext: Vec<Vec<Value>>,
    lmp_not_accepted_ext: Vec<Vec<Value>>,
    lmp_detach: Vec<Vec<Value>>,
    lmp_preferred_rate: Vec<Vec<Value>>,
    lmp_version_req: Vec<Vec<Value>>,
    lmp_version_res: Vec<Vec<Value>>,
    lmp_features_req: Vec<Vec<Value>>,
    lmp_features_res: Vec<Vec<Value>>,
    lmp_features_req_ext: Vec<Vec<Value>>,
    lmp_features_res_ext: Vec<Vec<Value>>,
    lmp_channel_classification: Vec<Vec<Value>>,
    lmp_power_control_req: Vec<Vec<Value>>,
    lmp_power_control_res: Vec<Vec<Value>>,
    lmp_empty_opcodes: Vec<Vec<Value>>,

    // GATT
    gatt_attribute_handles: Vec<Vec<Value>>,
    gatt_services: Vec<Vec<Value>>,
    gatt_characteristics: Vec<Vec<Value>>,
    gatt_characteristics_values: Vec<Vec<Value>>,
    gatt_characteristic_descriptor_values: Vec<Vec<Value>>,

    // Accumulators that need cross-entry state for parity with Python.
    // bdaddr (lowercased) -> Vec<full_pkt_hex_str>. Python keeps this per-call
    // (per parse_LMPArray call) but the dedupe properties of INSERT IGNORE
    // make a single global dict equivalent: any duplicate (bdaddr, offset,
    // total_length, fragment) is collapsed by the unique key anyway, and
    // defragmentation per-bdaddr produces one row regardless of how many
    // calls contributed to the fragment list.
    name_frag_dict: HashMap<String, Vec<String>>,

    // Raw GPS ops, mirroring parse_all_GPSArrays_batched in Python.
    // (bdaddr, bdaddr_random, time, time_type, rssi, lat, lon)
    gps_ops: Vec<(String, i64, u64, i64, i64, f64, f64)>,
}

// --------------------------- AdvData routing --------------------------------

fn process_adv_data_array(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    adv_data_array: &[J],
    b: &mut Buffers,
) {
    for ad in adv_data_array {
        let obj = match ad.as_object() {
            Some(o) => o,
            None => continue,
        };
        let t = match obj_i64(obj, "type") {
            Some(t) => t,
            None => continue,
        };
        match t {
            T_FLAGS => import_adv_flags(bdaddr, bdaddr_rand, db_type, obj, b),
            T_MSD => import_adv_msd(bdaddr, bdaddr_rand, db_type, obj, b),
            T_UUID16_INC | T_UUID16_CMP => {
                import_adv_uuid16s(bdaddr, bdaddr_rand, db_type, obj, b)
            }
            T_UUID32_INC | T_UUID32_CMP => {
                import_adv_uuid32s(bdaddr, bdaddr_rand, db_type, obj, b)
            }
            T_UUID128_INC | T_UUID128_CMP => {
                import_adv_uuid128s(bdaddr, bdaddr_rand, db_type, obj, b)
            }
            T_NAME_SHORT | T_NAME_FULL | T_NAME_BROADCAST => {
                import_adv_name(bdaddr, bdaddr_rand, db_type, obj, b)
            }
            T_TX_POWER => import_adv_tx_power(bdaddr, bdaddr_rand, db_type, obj, b),
            T_COD => import_adv_cod(bdaddr, bdaddr_rand, db_type, obj, b),
            T_DEV_ID => import_adv_dev_id(bdaddr, db_type, obj, b),
            T_CONN_INT_RANGE => {
                import_adv_conn_interval(bdaddr, bdaddr_rand, db_type, obj, b)
            }
            T_UUID16_SS => import_adv_uuid16_ss(bdaddr, bdaddr_rand, db_type, obj, b),
            T_UUID128_SS => import_adv_uuid128_ss(bdaddr, bdaddr_rand, db_type, obj, b),
            T_PUB_TARGET => import_adv_pub_target(bdaddr, bdaddr_rand, db_type, obj, b),
            T_RAND_TARGET => import_adv_rand_target(bdaddr, bdaddr_rand, db_type, obj, b),
            T_APPEARANCE => import_adv_appearance(bdaddr, bdaddr_rand, db_type, obj, b),
            T_LE_BDADDR => import_adv_le_bdaddr(bdaddr, bdaddr_rand, db_type, obj, b),
            T_LE_ROLE => import_adv_le_role(bdaddr, bdaddr_rand, db_type, obj, b),
            T_UUID16_SD => import_adv_uuid16_sd(bdaddr, bdaddr_rand, db_type, obj, b),
            T_UUID32_SD => import_adv_uuid32_sd(bdaddr, bdaddr_rand, db_type, obj, b),
            T_UUID128_SD => import_adv_uuid128_sd(bdaddr, bdaddr_rand, db_type, obj, b),
            T_URI => import_adv_uri(bdaddr, bdaddr_rand, db_type, obj, b),
            T_3D_INFO => import_adv_3d_info(bdaddr, bdaddr_rand, db_type, obj, b),
            _ => {}
        }
    }
}

fn import_adv_flags(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    let flags_hex = match obj_str(o, "flags_hex_str") {
        Some(s) => s,
        None => return,
    };
    let flags_int = parse_hex_int_u64(flags_hex);
    let bit = |i: u32| if (flags_int & (1u64 << i)) != 0 { 1i64 } else { 0i64 };
    let lim = bit(0);
    let gen = bit(1);
    let bredr_not = bit(2);
    let c = bit(3);
    let h = bit(4);
    if db_type == B_EIR {
        b.eir_flags.push(vec![
            bdaddr.into(),
            lim.into(),
            gen.into(),
            bredr_not.into(),
            c.into(),
            h.into(),
        ]);
    } else {
        b.le_flags.push(vec![
            bdaddr.into(),
            bdaddr_rand.into(),
            db_type.into(),
            lim.into(),
            gen.into(),
            bredr_not.into(),
            c.into(),
            h.into(),
        ]);
    }
}

fn import_adv_uuid16s(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    let list = match o.get("UUID16List").and_then(|v| v.as_array()) {
        Some(l) => l,
        None => return,
    };
    let joined = list
        .iter()
        .filter_map(|v| v.as_str())
        .collect::<Vec<_>>()
        .join(",");
    let lt = obj_i64(o, "type").unwrap_or(0);
    if db_type == B_EIR {
        b.eir_uuid16s
            .push(vec![bdaddr.into(), lt.into(), joined.into()]);
    } else {
        b.le_uuid16s_list.push(vec![
            bdaddr.into(),
            bdaddr_rand.into(),
            db_type.into(),
            lt.into(),
            joined.into(),
        ]);
    }
}

fn import_adv_uuid32s(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    let list = match o.get("UUID32List").and_then(|v| v.as_array()) {
        Some(l) => l,
        None => return,
    };
    let joined = list
        .iter()
        .filter_map(|v| v.as_str())
        .collect::<Vec<_>>()
        .join(",");
    let lt = obj_i64(o, "type").unwrap_or(0);
    if db_type == B_EIR {
        b.eir_uuid32s
            .push(vec![bdaddr.into(), lt.into(), joined.into()]);
    } else {
        b.le_uuid32s_list.push(vec![
            bdaddr.into(),
            bdaddr_rand.into(),
            db_type.into(),
            lt.into(),
            joined.into(),
        ]);
    }
}

fn import_adv_uuid128s(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    let list = match o.get("UUID128List").and_then(|v| v.as_array()) {
        Some(l) => l,
        None => return,
    };
    let joined = list
        .iter()
        .filter_map(|v| v.as_str())
        .map(strip_uuid_dashes)
        .collect::<Vec<_>>()
        .join(",");
    let lt = obj_i64(o, "type").unwrap_or(0);
    if db_type == B_EIR {
        b.eir_uuid128s
            .push(vec![bdaddr.into(), lt.into(), joined.into()]);
    } else {
        b.le_uuid128s_list.push(vec![
            bdaddr.into(),
            bdaddr_rand.into(),
            db_type.into(),
            lt.into(),
            joined.into(),
        ]);
    }
}

fn import_adv_name(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    let dnt = obj_i64(o, "type").unwrap_or(0);
    let name = obj_str(o, "name_hex_str").unwrap_or("").to_string();
    if db_type == B_EIR {
        b.eir_name
            .push(vec![bdaddr.into(), dnt.into(), name.into()]);
    } else {
        b.le_name.push(vec![
            bdaddr.into(),
            bdaddr_rand.into(),
            db_type.into(),
            dnt.into(),
            name.into(),
        ]);
    }
}

fn import_adv_tx_power(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    let tx = obj_i64(o, "tx_power").unwrap_or(0);
    if db_type == B_EIR {
        b.eir_tx_power.push(vec![bdaddr.into(), tx.into()]);
    } else {
        b.le_tx_power.push(vec![
            bdaddr.into(),
            bdaddr_rand.into(),
            db_type.into(),
            tx.into(),
        ]);
    }
}

fn import_adv_cod(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    let cod_hex = match obj_str(o, "CoD_hex_str") {
        Some(s) => s,
        None => return,
    };
    let cod = parse_hex_int_u64(cod_hex) as i64;
    if db_type == B_EIR {
        b.eir_cod.push(vec![bdaddr.into(), cod.into()]);
    } else {
        b.le_cod.push(vec![
            bdaddr.into(),
            bdaddr_rand.into(),
            db_type.into(),
            cod.into(),
        ]);
    }
}

fn import_adv_dev_id(
    bdaddr: &str,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    // AFAIK this can't exist in LE AdvData, only EIR.
    if db_type != B_EIR {
        return;
    }
    let src = obj_i64(o, "vendor_id_source").unwrap_or(0);
    let vid = obj_i64(o, "vendor_id").unwrap_or(0);
    let pid = obj_i64(o, "product_id").unwrap_or(0);
    let ver = obj_i64(o, "version").unwrap_or(0);
    b.eir_dev_id.push(vec![
        bdaddr.into(),
        src.into(),
        vid.into(),
        pid.into(),
        ver.into(),
    ]);
}

fn import_adv_conn_interval(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    if db_type == B_EIR {
        return;
    }
    let cmin = obj_i64(o, "conn_interval_min").unwrap_or(0);
    let cmax = obj_i64(o, "conn_interval_max").unwrap_or(0);
    b.le_conn_interval.push(vec![
        bdaddr.into(),
        bdaddr_rand.into(),
        db_type.into(),
        cmin.into(),
        cmax.into(),
    ]);
}

fn import_adv_uuid16_ss(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    if db_type == B_EIR {
        return;
    }
    let list = match o.get("UUID16List").and_then(|v| v.as_array()) {
        Some(l) => l,
        None => return,
    };
    let joined = list
        .iter()
        .filter_map(|v| v.as_str())
        .collect::<Vec<_>>()
        .join(",");
    b.le_uuid16_ss.push(vec![
        bdaddr.into(),
        bdaddr_rand.into(),
        db_type.into(),
        joined.into(),
    ]);
}

fn import_adv_uuid128_ss(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    if db_type == B_EIR {
        return;
    }
    let list = match o.get("UUID128List").and_then(|v| v.as_array()) {
        Some(l) => l,
        None => return,
    };
    let joined = list
        .iter()
        .filter_map(|v| v.as_str())
        .map(strip_uuid_dashes)
        .collect::<Vec<_>>()
        .join(",");
    b.le_uuid128_ss.push(vec![
        bdaddr.into(),
        bdaddr_rand.into(),
        db_type.into(),
        joined.into(),
    ]);
}

fn import_adv_uuid16_sd(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    if db_type == B_EIR {
        return;
    }
    let len = obj_i64(o, "length").unwrap_or(0);
    let uuid = obj_str(o, "UUID16").unwrap_or("").to_string();
    let sd = obj_str(o, "service_data_hex_str")
        .unwrap_or("")
        .to_string();
    b.le_uuid16_sd.push(vec![
        bdaddr.into(),
        bdaddr_rand.into(),
        db_type.into(),
        len.into(),
        uuid.into(),
        sd.into(),
    ]);
}

fn import_adv_uuid32_sd(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    if db_type == B_EIR {
        return;
    }
    let len = obj_i64(o, "length").unwrap_or(0);
    let uuid = obj_str(o, "UUID32").unwrap_or("").to_string();
    let sd = obj_str(o, "service_data_hex_str")
        .unwrap_or("")
        .to_string();
    b.le_uuid32_sd.push(vec![
        bdaddr.into(),
        bdaddr_rand.into(),
        db_type.into(),
        len.into(),
        uuid.into(),
        sd.into(),
    ]);
}

fn import_adv_uuid128_sd(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    if db_type == B_EIR {
        return;
    }
    let len = obj_i64(o, "length").unwrap_or(0);
    let uuid = strip_uuid_dashes(obj_str(o, "UUID128").unwrap_or(""));
    let sd = obj_str(o, "service_data_hex_str")
        .unwrap_or("")
        .to_string();
    b.le_uuid128_sd.push(vec![
        bdaddr.into(),
        bdaddr_rand.into(),
        db_type.into(),
        len.into(),
        uuid.into(),
        sd.into(),
    ]);
}

fn import_adv_pub_target(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    if db_type == B_EIR {
        return;
    }
    let pb = obj_str(o, "public_bdaddr").unwrap_or("").to_string();
    b.le_public_target.push(vec![
        bdaddr.into(),
        bdaddr_rand.into(),
        db_type.into(),
        pb.into(),
    ]);
}

fn import_adv_rand_target(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    if db_type == B_EIR {
        return;
    }
    let rb = obj_str(o, "random_bdaddr").unwrap_or("").to_string();
    b.le_random_target.push(vec![
        bdaddr.into(),
        bdaddr_rand.into(),
        db_type.into(),
        rb.into(),
    ]);
}

fn import_adv_appearance(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    if db_type == B_EIR {
        return;
    }
    let apphex = match obj_str(o, "appearance_hex_str") {
        Some(s) => s,
        None => return,
    };
    let app = parse_hex_int_u64(apphex) as i64;
    b.le_appearance.push(vec![
        bdaddr.into(),
        bdaddr_rand.into(),
        db_type.into(),
        app.into(),
    ]);
}

fn import_adv_le_bdaddr(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    if db_type == B_EIR {
        return;
    }
    let bt = obj_i64(o, "bdaddr_type").unwrap_or(0);
    let le_bd = obj_str(o, "le_bdaddr").unwrap_or("").to_string();
    b.le_other_le.push(vec![
        bdaddr.into(),
        bdaddr_rand.into(),
        db_type.into(),
        le_bd.into(),
        bt.into(),
    ]);
}

fn import_adv_le_role(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    if db_type == B_EIR {
        return;
    }
    let r = obj_i64(o, "role").unwrap_or(0);
    b.le_role.push(vec![
        bdaddr.into(),
        bdaddr_rand.into(),
        db_type.into(),
        r.into(),
    ]);
}

fn import_adv_uri(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    let uri = obj_str(o, "uri_hex_str").unwrap_or("").to_string();
    if db_type == B_EIR {
        b.eir_uri.push(vec![bdaddr.into(), uri.into()]);
    } else {
        b.le_uri.push(vec![
            bdaddr.into(),
            bdaddr_rand.into(),
            db_type.into(),
            uri.into(),
        ]);
    }
}

fn import_adv_3d_info(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    let byte1 = obj_i64(o, "byte1").unwrap_or(0);
    let path_loss = obj_i64(o, "path_loss").unwrap_or(0);
    if db_type == B_EIR {
        b.eir_3d
            .push(vec![bdaddr.into(), byte1.into(), path_loss.into()]);
    } else {
        b.le_3d.push(vec![
            bdaddr.into(),
            bdaddr_rand.into(),
            db_type.into(),
            byte1.into(),
            path_loss.into(),
        ]);
    }
}

fn import_adv_msd(
    bdaddr: &str,
    bdaddr_rand: i64,
    db_type: i64,
    o: &serde_json::Map<String, J>,
    b: &mut Buffers,
) {
    let cid_hex = match obj_str(o, "company_id_hex_str") {
        Some(s) => s,
        None => return,
    };
    let cid = parse_hex_int_u64(cid_hex) as i64;
    let msd = obj_str(o, "msd_hex_str").unwrap_or("").to_string();
    if db_type == B_EIR {
        b.eir_msd
            .push(vec![bdaddr.into(), cid.into(), msd.into()]);
    } else {
        b.le_msd.push(vec![
            bdaddr.into(),
            bdaddr_rand.into(),
            db_type.into(),
            cid.into(),
            msd.into(),
        ]);
    }
}

// --------------------------- AdvChanArray -----------------------------------

fn parse_adv_chan_array(entry: &serde_json::Map<String, J>, b: &mut Buffers) {
    let arr = match entry.get("AdvChanArray").and_then(|v| v.as_array()) {
        Some(a) => a,
        None => return,
    };
    let (bdaddr, bdaddr_rand) = get_bdaddr_peripheral(entry);
    if bdaddr.is_empty() {
        return;
    }
    for chan in arr {
        let chan_obj = match chan.as_object() {
            Some(o) => o,
            None => continue,
        };
        let chan_type = obj_i64(chan_obj, "type").unwrap_or(0);
        let db_type = btides_to_le_evt_type(chan_type);
        let ad_arr = match chan_obj.get("AdvDataArray").and_then(|v| v.as_array()) {
            Some(a) => a,
            None => continue,
        };
        process_adv_data_array(&bdaddr, bdaddr_rand, db_type, ad_arr, b);
    }
}

// --------------------------- LLArray ----------------------------------------

fn parse_ll_array(entry: &serde_json::Map<String, J>, b: &mut Buffers) {
    let arr = match entry.get("LLArray").and_then(|v| v.as_array()) {
        Some(a) => a,
        None => return,
    };
    for ll in arr {
        let o = match ll.as_object() {
            Some(o) => o,
            None => continue,
        };
        let (bdaddr, bdaddr_rand) = if obj_i64(o, "direction") == Some(TYPE_BTIDES_DIR_C2P) {
            get_bdaddr_central(entry)
        } else {
            get_bdaddr_peripheral(entry)
        };
        let opcode = match obj_i64(o, "opcode") {
            Some(x) => x,
            None => continue,
        };
        match opcode {
            LL_UNKNOWN_RSP => {
                let unk = obj_i64(o, "unknown_type").unwrap_or(0);
                b.ll_unknown_rsp.push(vec![
                    bdaddr.clone().into(),
                    bdaddr_rand.into(),
                    unk.into(),
                ]);
            }
            LL_VERSION_IND => {
                let v = obj_i64(o, "version").unwrap_or(0);
                let cid = obj_i64(o, "company_id").unwrap_or(0);
                let sv = obj_i64(o, "subversion").unwrap_or(0);
                b.ll_version_ind.push(vec![
                    bdaddr.clone().into(),
                    bdaddr_rand.into(),
                    v.into(),
                    cid.into(),
                    sv.into(),
                ]);
            }
            LL_FEATURE_REQ | LL_FEATURE_RSP | LL_PERIPHERAL_FEATURE_REQ => {
                let feat_hex = obj_str(o, "le_features_hex_str").unwrap_or("0");
                let feat = parse_hex_int_u64(feat_hex);
                b.ll_features.push(vec![
                    bdaddr.clone().into(),
                    bdaddr_rand.into(),
                    opcode.into(),
                    feat.into(),
                ]);
            }
            LL_PING_REQ | LL_PING_RSP => {
                let direction = obj_i64(o, "direction").unwrap_or(0);
                // Reproduce parse_LLArray's C2P PING_RSP -> infer P2C PING_REQ rule.
                let (final_bdaddr, final_rand, final_opcode, final_dir) =
                    if direction == TYPE_BTIDES_DIR_C2P {
                        if opcode == LL_PING_RSP {
                            let (pb, pr) = get_bdaddr_peripheral(entry);
                            (pb, pr, LL_PING_REQ, TYPE_BTIDES_DIR_P2C)
                        } else {
                            continue; // Skip C2P PING_REQ
                        }
                    } else {
                        (bdaddr.clone(), bdaddr_rand, opcode, direction)
                    };
                b.ll_pings.push(vec![
                    final_bdaddr.into(),
                    final_rand.into(),
                    final_opcode.into(),
                    final_dir.into(),
                ]);
            }
            LL_LENGTH_REQ | LL_LENGTH_RSP => {
                let mr_o = obj_i64(o, "max_rx_octets").unwrap_or(0);
                let mr_t = obj_i64(o, "max_rx_time").unwrap_or(0);
                let mt_o = obj_i64(o, "max_tx_octets").unwrap_or(0);
                let mt_t = obj_i64(o, "max_tx_time").unwrap_or(0);
                b.ll_lengths.push(vec![
                    bdaddr.clone().into(),
                    bdaddr_rand.into(),
                    opcode.into(),
                    mr_o.into(),
                    mr_t.into(),
                    mt_o.into(),
                    mt_t.into(),
                ]);
            }
            LL_PHY_REQ | LL_PHY_RSP => {
                let direction = obj_i64(o, "direction").unwrap_or(0);
                if direction == TYPE_BTIDES_DIR_C2P {
                    continue;
                }
                let tx_phys = obj_i64(o, "TX_PHYS").unwrap_or(0);
                let rx_phys = obj_i64(o, "RX_PHYS").unwrap_or(0);
                b.ll_phys.push(vec![
                    bdaddr.clone().into(),
                    bdaddr_rand.into(),
                    opcode.into(),
                    direction.into(),
                    tx_phys.into(),
                    rx_phys.into(),
                ]);
            }
            _ => {}
        }
    }
}

// --------------------------- LMPArray ---------------------------------------

fn parse_lmp_array(entry: &serde_json::Map<String, J>, b: &mut Buffers) {
    let arr = match entry.get("LMPArray").and_then(|v| v.as_array()) {
        Some(a) => a,
        None => return,
    };
    // parse_LMPArray bails entirely if bdaddr_rand != 0 — LMP is BR/EDR only.
    let bdr = obj_i64(entry, "bdaddr_rand").unwrap_or(0);
    if bdr != 0 {
        return;
    }
    let (bdaddr, _) = get_bdaddr_peripheral(entry);
    if bdaddr.is_empty() {
        return;
    }
    for lmp in arr {
        let o = match lmp.as_object() {
            Some(o) => o,
            None => continue,
        };
        let opcode = obj_i64(o, "opcode").unwrap_or(-1);
        let escape_127 = obj_i64(o, "escape_127").unwrap_or(-1);
        let ext_op = obj_i64(o, "extended_opcode").unwrap_or(-1);

        // -------- ext opcodes first (escape_127 path) --------
        if escape_127 == 127 {
            match ext_op {
                EXT_LMP_ACCEPTED_EXT => {
                    let (eo, xo) = if let Some(full) = obj_str(o, "full_pkt_hex_str") {
                        if full.len() == 4 {
                            let bytes = hex_str_to_bytes(full);
                            if bytes.len() >= 2 {
                                (bytes[0] as i64, bytes[1] as i64)
                            } else {
                                (0, 0)
                            }
                        } else {
                            (
                                obj_i64(o, "rcvd_escape_opcode").unwrap_or(0),
                                obj_i64(o, "rcvd_extended_opcode").unwrap_or(0),
                            )
                        }
                    } else {
                        (
                            obj_i64(o, "rcvd_escape_opcode").unwrap_or(0),
                            obj_i64(o, "rcvd_extended_opcode").unwrap_or(0),
                        )
                    };
                    b.lmp_accepted_ext
                        .push(vec![bdaddr.clone().into(), eo.into(), xo.into()]);
                    continue;
                }
                EXT_LMP_NOT_ACCEPTED_EXT => {
                    let (eo, xo, ec) = if let Some(full) = obj_str(o, "full_pkt_hex_str") {
                        if full.len() == 6 {
                            let bytes = hex_str_to_bytes(full);
                            if bytes.len() >= 3 {
                                (bytes[0] as i64, bytes[1] as i64, bytes[2] as i64)
                            } else {
                                (0, 0, 0)
                            }
                        } else {
                            (
                                obj_i64(o, "rcvd_escape_opcode").unwrap_or(0),
                                obj_i64(o, "rcvd_extended_opcode").unwrap_or(0),
                                obj_i64(o, "error_code").unwrap_or(0),
                            )
                        }
                    } else {
                        (
                            obj_i64(o, "rcvd_escape_opcode").unwrap_or(0),
                            obj_i64(o, "rcvd_extended_opcode").unwrap_or(0),
                            obj_i64(o, "error_code").unwrap_or(0),
                        )
                    };
                    b.lmp_not_accepted_ext.push(vec![
                        bdaddr.clone().into(),
                        eo.into(),
                        xo.into(),
                        ec.into(),
                    ]);
                    continue;
                }
                EXT_LMP_FEATURES_REQ_EXT | EXT_LMP_FEATURES_RES_EXT => {
                    let (page, max_page, features) = if let Some(full) =
                        obj_str(o, "full_pkt_hex_str")
                    {
                        if full.len() == 20 {
                            let bytes = hex_str_to_bytes(full);
                            if bytes.len() >= 10 {
                                let mut feat = [0u8; 8];
                                feat.copy_from_slice(&bytes[2..10]);
                                (
                                    bytes[0] as i64,
                                    bytes[1] as i64,
                                    u64::from_le_bytes(feat),
                                )
                            } else {
                                (0, 0, 0)
                            }
                        } else {
                            (
                                obj_i64(o, "page").unwrap_or(0),
                                obj_i64(o, "max_page").unwrap_or(0),
                                parse_hex_int_u64(obj_str(o, "lmp_features_hex_str").unwrap_or("0")),
                            )
                        }
                    } else {
                        (
                            obj_i64(o, "page").unwrap_or(0),
                            obj_i64(o, "max_page").unwrap_or(0),
                            parse_hex_int_u64(obj_str(o, "lmp_features_hex_str").unwrap_or("0")),
                        )
                    };
                    let row = vec![
                        bdaddr.clone().into(),
                        page.into(),
                        max_page.into(),
                        features.into(),
                    ];
                    if ext_op == EXT_LMP_FEATURES_RES_EXT {
                        b.lmp_features_res_ext.push(row);
                    } else {
                        b.lmp_features_req_ext.push(row);
                    }
                    continue;
                }
                EXT_LMP_CHANNEL_CLASSIFICATION => {
                    let bytes = if let Some(full) = obj_str(o, "full_pkt_hex_str") {
                        if full.len() == 20 {
                            hex_str_to_bytes(full)
                        } else if let Some(ac) = obj_str(o, "afh_channel_classification") {
                            hex_str_to_bytes(ac)
                        } else {
                            Vec::new()
                        }
                    } else if let Some(ac) = obj_str(o, "afh_channel_classification") {
                        hex_str_to_bytes(ac)
                    } else {
                        Vec::new()
                    };
                    b.lmp_channel_classification
                        .push(vec![bdaddr.clone().into(), bytes.into()]);
                    continue;
                }
                EXT_LMP_POWER_CONTROL_REQ => {
                    let v = if let Some(full) = obj_str(o, "full_pkt_hex_str") {
                        if full.len() == 2 {
                            hex_str_to_bytes(full).get(0).copied().unwrap_or(0) as i64
                        } else {
                            obj_i64(o, "power_adj_req").unwrap_or(0)
                        }
                    } else {
                        obj_i64(o, "power_adj_req").unwrap_or(0)
                    };
                    b.lmp_power_control_req
                        .push(vec![bdaddr.clone().into(), v.into()]);
                    continue;
                }
                EXT_LMP_POWER_CONTROL_RES => {
                    let v = if let Some(full) = obj_str(o, "full_pkt_hex_str") {
                        if full.len() == 2 {
                            hex_str_to_bytes(full).get(0).copied().unwrap_or(0) as i64
                        } else {
                            obj_i64(o, "power_adj_res").unwrap_or(0)
                        }
                    } else {
                        obj_i64(o, "power_adj_res").unwrap_or(0)
                    };
                    b.lmp_power_control_res
                        .push(vec![bdaddr.clone().into(), v.into()]);
                    continue;
                }
                _ => {}
            }
        }

        // -------- regular opcodes --------
        match opcode {
            LMP_NAME_RES => {
                let full = obj_str(o, "full_pkt_hex_str").unwrap_or("");
                if full.len() < 4 {
                    continue;
                }
                let head = hex_str_to_bytes(&full[0..4]);
                if head.len() < 2 {
                    continue;
                }
                let name_offset = head[0] as i64;
                let name_total_length = head[1] as i64;
                let name_fragment_bytes = hex_str_to_bytes(&full[4..]);
                b.lmp_name_res_fragmented.push(vec![
                    bdaddr.clone().into(),
                    name_offset.into(),
                    name_total_length.into(),
                    name_fragment_bytes.into(),
                ]);
                b.name_frag_dict
                    .entry(bdaddr.clone())
                    .or_default()
                    .push(full.to_string());
            }
            LMP_ACCEPTED => {
                let v = if let Some(full) = obj_str(o, "full_pkt_hex_str") {
                    if full.len() == 2 {
                        hex_str_to_bytes(full).get(0).copied().unwrap_or(0) as i64
                    } else {
                        obj_i64(o, "rcvd_opcode").unwrap_or(0)
                    }
                } else {
                    obj_i64(o, "rcvd_opcode").unwrap_or(0)
                };
                b.lmp_accepted.push(vec![bdaddr.clone().into(), v.into()]);
            }
            LMP_NOT_ACCEPTED => {
                let (op, ec) = if let Some(full) = obj_str(o, "full_pkt_hex_str") {
                    if full.len() == 4 {
                        let bytes = hex_str_to_bytes(full);
                        if bytes.len() >= 2 {
                            (bytes[0] as i64, bytes[1] as i64)
                        } else {
                            (0, 0)
                        }
                    } else {
                        (
                            obj_i64(o, "rcvd_opcode").unwrap_or(0),
                            obj_i64(o, "error_code").unwrap_or(0),
                        )
                    }
                } else {
                    (
                        obj_i64(o, "rcvd_opcode").unwrap_or(0),
                        obj_i64(o, "error_code").unwrap_or(0),
                    )
                };
                b.lmp_not_accepted
                    .push(vec![bdaddr.clone().into(), op.into(), ec.into()]);
            }
            LMP_DETACH => {
                let ec = if let Some(full) = obj_str(o, "full_pkt_hex_str") {
                    if full.len() == 2 {
                        hex_str_to_bytes(full).get(0).copied().unwrap_or(0) as i64
                    } else {
                        obj_i64(o, "error_code").unwrap_or(0)
                    }
                } else {
                    obj_i64(o, "error_code").unwrap_or(0)
                };
                b.lmp_detach.push(vec![bdaddr.clone().into(), ec.into()]);
            }
            LMP_PREFERRED_RATE => {
                let dr = if let Some(full) = obj_str(o, "full_pkt_hex_str") {
                    if full.len() == 2 {
                        hex_str_to_bytes(full).get(0).copied().unwrap_or(0) as i64
                    } else {
                        obj_i64(o, "data_rate").unwrap_or(0)
                    }
                } else {
                    obj_i64(o, "data_rate").unwrap_or(0)
                };
                b.lmp_preferred_rate
                    .push(vec![bdaddr.clone().into(), dr.into()]);
            }
            LMP_VERSION_REQ | LMP_VERSION_RES => {
                let (lv, cid, sv) = if let Some(full) = obj_str(o, "full_pkt_hex_str") {
                    if full.len() == 10 {
                        let bytes = hex_str_to_bytes(full);
                        if bytes.len() >= 5 {
                            let lv = bytes[0] as i64;
                            let cid = u16::from_le_bytes([bytes[1], bytes[2]]) as i64;
                            let sv = u16::from_le_bytes([bytes[3], bytes[4]]) as i64;
                            (lv, cid, sv)
                        } else {
                            (0, 0, 0)
                        }
                    } else {
                        (
                            obj_i64(o, "version").unwrap_or(0),
                            obj_i64(o, "company_id").unwrap_or(0),
                            obj_i64(o, "subversion").unwrap_or(0),
                        )
                    }
                } else {
                    (
                        obj_i64(o, "version").unwrap_or(0),
                        obj_i64(o, "company_id").unwrap_or(0),
                        obj_i64(o, "subversion").unwrap_or(0),
                    )
                };
                let row = vec![
                    bdaddr.clone().into(),
                    lv.into(),
                    cid.into(),
                    sv.into(),
                ];
                if opcode == LMP_VERSION_REQ {
                    b.lmp_version_req.push(row);
                } else {
                    b.lmp_version_res.push(row);
                }
            }
            LMP_FEATURES_REQ | LMP_FEATURES_RES => {
                let features = if let Some(full) = obj_str(o, "full_pkt_hex_str") {
                    if full.len() == 16 {
                        let bytes = hex_str_to_bytes(full);
                        if bytes.len() >= 8 {
                            let mut feat = [0u8; 8];
                            feat.copy_from_slice(&bytes[0..8]);
                            u64::from_le_bytes(feat)
                        } else {
                            0
                        }
                    } else {
                        parse_hex_int_u64(obj_str(o, "lmp_features_hex_str").unwrap_or("0"))
                    }
                } else {
                    parse_hex_int_u64(obj_str(o, "lmp_features_hex_str").unwrap_or("0"))
                };
                let row = vec![
                    bdaddr.clone().into(),
                    0i64.into(),
                    features.into(),
                ];
                if opcode == LMP_FEATURES_REQ {
                    b.lmp_features_req.push(row);
                } else {
                    b.lmp_features_res.push(row);
                }
            }
            LMP_AUTO_RATE | LMP_TIMING_ACCURACY_REQ | LMP_SETUP_COMPLETE => {
                b.lmp_empty_opcodes
                    .push(vec![bdaddr.clone().into(), opcode.into()]);
            }
            _ => {}
        }
    }
}

// Merge per-thread Buffers in-place. Per-table rows are appended; the
// LMP_NAME_RES fragment dictionary is merged per-bdaddr (fragments from the
// same bdaddr seen in two different files defragment together — matching
// what a serial run that processed both files into one Python invocation
// would have done); GPS ops are appended. Order across sources is the natural
// concat order; finalize_lmp_name_res_defrag and apply_gps_batch are both
// order-insensitive.
fn merge_buffers(dst: &mut Buffers, mut src: Buffers) {
    macro_rules! mv {
        ($field:ident) => {
            dst.$field.extend(std::mem::take(&mut src.$field).into_iter());
        };
    }
    mv!(eir_flags);
    mv!(eir_uuid16s);
    mv!(eir_uuid32s);
    mv!(eir_uuid128s);
    mv!(eir_name);
    mv!(eir_tx_power);
    mv!(eir_dev_id);
    mv!(eir_uri);
    mv!(eir_3d);
    mv!(eir_msd);
    mv!(eir_psrm);
    mv!(eir_cod);

    mv!(le_flags);
    mv!(le_uuid16s_list);
    mv!(le_uuid32s_list);
    mv!(le_uuid128s_list);
    mv!(le_name);
    mv!(le_tx_power);
    mv!(le_cod);
    mv!(le_appearance);
    mv!(le_conn_interval);
    mv!(le_uuid16_ss);
    mv!(le_uuid128_ss);
    mv!(le_uuid16_sd);
    mv!(le_uuid32_sd);
    mv!(le_uuid128_sd);
    mv!(le_public_target);
    mv!(le_random_target);
    mv!(le_other_le);
    mv!(le_role);
    mv!(le_uri);
    mv!(le_3d);
    mv!(le_msd);

    mv!(hci_name);
    mv!(l2cap_conn_update_req);
    mv!(l2cap_conn_update_rsp);
    mv!(smp_pairing);
    mv!(sdp_error_rsp);
    mv!(sdp_common);

    mv!(ll_unknown_rsp);
    mv!(ll_version_ind);
    mv!(ll_features);
    mv!(ll_pings);
    mv!(ll_lengths);
    mv!(ll_phys);

    mv!(lmp_name_res_fragmented);
    mv!(lmp_name_res_defragmented);
    mv!(lmp_accepted);
    mv!(lmp_not_accepted);
    mv!(lmp_accepted_ext);
    mv!(lmp_not_accepted_ext);
    mv!(lmp_detach);
    mv!(lmp_preferred_rate);
    mv!(lmp_version_req);
    mv!(lmp_version_res);
    mv!(lmp_features_req);
    mv!(lmp_features_res);
    mv!(lmp_features_req_ext);
    mv!(lmp_features_res_ext);
    mv!(lmp_channel_classification);
    mv!(lmp_power_control_req);
    mv!(lmp_power_control_res);
    mv!(lmp_empty_opcodes);

    mv!(gatt_attribute_handles);
    mv!(gatt_services);
    mv!(gatt_characteristics);
    mv!(gatt_characteristics_values);
    mv!(gatt_characteristic_descriptor_values);

    for (bdaddr, frags) in src.name_frag_dict {
        dst.name_frag_dict.entry(bdaddr).or_default().extend(frags);
    }
    dst.gps_ops.extend(src.gps_ops);
}

// Parse one BTIDES file from disk into a fresh Buffers. Defragmentation is
// not finalized here — that happens once after all parses merge.
fn parse_file(path: &str) -> Buffers {
    let mut buffers = Buffers::default();
    let f = match File::open(path) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("open {}: {}", path, e);
            return buffers;
        }
    };
    let reader = BufReader::new(f);
    let parsed: J = match serde_json::from_reader(reader) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("parse {}: {}", path, e);
            return buffers;
        }
    };
    let arr = match parsed.as_array() {
        Some(a) => a,
        None => {
            eprintln!("{}: top-level JSON is not an array", path);
            return buffers;
        }
    };
    for e in arr {
        let obj = match e.as_object() {
            Some(o) => o,
            None => continue,
        };
        parse_adv_chan_array(obj, &mut buffers);
        parse_ll_array(obj, &mut buffers);
        parse_lmp_array(obj, &mut buffers);
        parse_hci_array(obj, &mut buffers);
        parse_l2cap_array(obj, &mut buffers);
        parse_att_array(obj, &mut buffers);
        parse_gatt_array(obj, &mut buffers);
        parse_smp_array(obj, &mut buffers);
        parse_eir_array(obj, &mut buffers);
        parse_sdp_array(obj, &mut buffers);
        collect_gps_ops(obj, &mut buffers);
    }
    buffers
}

fn finalize_lmp_name_res_defrag(b: &mut Buffers) {
    // Mirrors the defrag loop at the end of parse_LMPArray.
    // For each bdaddr, sort fragments by name_offset, validate they agree on
    // name_total_length, drop trailing 0x00 padding if the fragment would
    // overflow, then concatenate.
    // Sort bdaddrs deterministically so insertion order matches across runs.
    let mut keys: Vec<String> = b.name_frag_dict.keys().cloned().collect();
    keys.sort();
    for bdaddr in keys {
        let frags = match b.name_frag_dict.get(&bdaddr) {
            Some(v) => v.clone(),
            None => continue,
        };
        let mut by_offset: BTreeMap<i64, (i64, String)> = BTreeMap::new();
        let mut total_len_seen: i64 = 0;
        for f in &frags {
            if f.len() < 4 {
                continue;
            }
            let head = hex_str_to_bytes(&f[0..4]);
            if head.len() < 2 {
                continue;
            }
            let offset = head[0] as i64;
            let total_len = head[1] as i64;
            let name_fragment = f[4..].to_string();
            by_offset.insert(offset, (total_len, name_fragment));
            total_len_seen = total_len;
        }
        let mut defrag = Vec::<u8>::new();
        let mut broke = false;
        for (offset, (tl, name_frag)) in &by_offset {
            if *tl != total_len_seen {
                broke = true;
                break;
            }
            let mut nf = name_frag.clone();
            if offset + (nf.len() as i64) / 2 - 1 > total_len_seen {
                // Replicate the rstrip("00") workaround
                while nf.ends_with("00") {
                    nf.pop();
                    nf.pop();
                }
                if offset + (nf.len() as i64) / 2 - 1 > total_len_seen {
                    broke = true;
                    break;
                }
            }
            defrag.extend(hex_str_to_bytes(&nf));
        }
        if broke {
            continue;
        }
        // Python decodes utf-8 with errors='ignore' then re-encodes implicitly
        // via the DB driver. We do the same: drop invalid bytes, store the
        // decoded UTF-8 string in the device_name column (utf8mb4).
        let s = String::from_utf8_lossy(&defrag).to_string();
        // Strip null bytes the way python's decode would have done (lossy on
        // 0xFF, but 0x00 stays). The Python prints it after decode, which
        // keeps 0x00. MySQL utf8mb4 columns *accept* embedded nulls. Leave as-is.
        b.lmp_name_res_defragmented
            .push(vec![bdaddr.clone().into(), s.into()]);
    }
}

// --------------------------- HCI / L2CAP / SMP / SDP / EIR ------------------

fn parse_hci_array(entry: &serde_json::Map<String, J>, b: &mut Buffers) {
    let arr = match entry.get("HCIArray").and_then(|v| v.as_array()) {
        Some(a) => a,
        None => return,
    };
    let (bdaddr, _) = get_bdaddr_peripheral(entry);
    if bdaddr.is_empty() {
        return;
    }
    for h in arr {
        let o = match h.as_object() {
            Some(o) => o,
            None => continue,
        };
        if obj_i64(o, "event_code") == Some(HCI_REMOTE_NAME_REQUEST_COMPLETE) {
            let name = obj_str(o, "remote_name_hex_str").unwrap_or("").to_string();
            // The Python writes status=0 as a literal in the INSERT. Match
            // that here by adding the constant in column order.
            b.hci_name
                .push(vec![bdaddr.clone().into(), 0i64.into(), name.into()]);
        }
    }
}

fn parse_l2cap_array(entry: &serde_json::Map<String, J>, b: &mut Buffers) {
    let arr = match entry.get("L2CAPArray").and_then(|v| v.as_array()) {
        Some(a) => a,
        None => return,
    };
    for l in arr {
        let o = match l.as_object() {
            Some(o) => o,
            None => continue,
        };
        let (bdaddr, bdaddr_rand) = if obj_i64(o, "direction") == Some(TYPE_BTIDES_DIR_C2P) {
            get_bdaddr_central(entry)
        } else {
            get_bdaddr_peripheral(entry)
        };
        if bdaddr == "00:00:00:00:00:00" {
            continue;
        }
        let code = match obj_i64(o, "code") {
            Some(x) => x,
            None => continue,
        };
        match code {
            L2CAP_CONN_PARAM_UPDATE_REQ => {
                let direction = obj_i64(o, "direction").unwrap_or(0);
                let pkt_id = obj_i64(o, "id").unwrap_or(0);
                let data_len = obj_i64(o, "data_len").unwrap_or(0);
                let imin = obj_i64(o, "interval_min").unwrap_or(0);
                let imax = obj_i64(o, "interval_max").unwrap_or(0);
                let lat = obj_i64(o, "latency").unwrap_or(0);
                let to = obj_i64(o, "timeout").unwrap_or(0);
                b.l2cap_conn_update_req.push(vec![
                    bdaddr.into(),
                    bdaddr_rand.into(),
                    direction.into(),
                    code.into(),
                    pkt_id.into(),
                    data_len.into(),
                    imin.into(),
                    imax.into(),
                    lat.into(),
                    to.into(),
                ]);
            }
            L2CAP_CONN_PARAM_UPDATE_RSP => {
                let direction = obj_i64(o, "direction").unwrap_or(0);
                let pkt_id = obj_i64(o, "id").unwrap_or(0);
                let data_len = obj_i64(o, "data_len").unwrap_or(0);
                let result = obj_i64(o, "result").unwrap_or(0);
                b.l2cap_conn_update_rsp.push(vec![
                    bdaddr.into(),
                    bdaddr_rand.into(),
                    direction.into(),
                    code.into(),
                    pkt_id.into(),
                    data_len.into(),
                    result.into(),
                ]);
            }
            _ => {}
        }
    }
}

fn parse_smp_array(entry: &serde_json::Map<String, J>, b: &mut Buffers) {
    let arr = match entry.get("SMPArray").and_then(|v| v.as_array()) {
        Some(a) => a,
        None => return,
    };
    for s in arr {
        let o = match s.as_object() {
            Some(o) => o,
            None => continue,
        };
        let (bdaddr, bdaddr_rand) = if obj_i64(o, "direction") == Some(TYPE_BTIDES_DIR_C2P) {
            get_bdaddr_central(entry)
        } else {
            get_bdaddr_peripheral(entry)
        };
        if bdaddr == "00:00:00:00:00:00" {
            continue;
        }
        let opcode = match obj_i64(o, "opcode") {
            Some(x) => x,
            None => continue,
        };
        if opcode != SMP_PAIRING_REQUEST && opcode != SMP_PAIRING_RESPONSE {
            continue;
        }
        let io_cap = obj_i64(o, "io_cap").unwrap_or(0);
        let oob = obj_i64(o, "oob_data").unwrap_or(0);
        let auth = obj_i64(o, "auth_req").unwrap_or(0);
        let mk = obj_i64(o, "max_key_size").unwrap_or(0);
        let ikd = obj_i64(o, "initiator_key_dist").unwrap_or(0);
        let rkd = obj_i64(o, "responder_key_dist").unwrap_or(0);
        b.smp_pairing.push(vec![
            bdaddr.into(),
            bdaddr_rand.into(),
            opcode.into(),
            io_cap.into(),
            oob.into(),
            auth.into(),
            mk.into(),
            ikd.into(),
            rkd.into(),
        ]);
    }
}

fn parse_sdp_array(entry: &serde_json::Map<String, J>, b: &mut Buffers) {
    let arr = match entry.get("SDPArray").and_then(|v| v.as_array()) {
        Some(a) => a,
        None => return,
    };
    for s in arr {
        let o = match s.as_object() {
            Some(o) => o,
            None => continue,
        };
        let (bdaddr, _) = if obj_i64(o, "direction") == Some(TYPE_BTIDES_DIR_C2P) {
            get_bdaddr_central(entry)
        } else {
            get_bdaddr_peripheral(entry)
        };
        if bdaddr == "00:00:00:00:00:00" {
            continue;
        }
        let pdu_id = match obj_i64(o, "pdu_id") {
            Some(x) => x,
            None => continue,
        };
        let l2cap_len = obj_i64(o, "l2cap_len").unwrap_or(0);
        let l2cap_cid = obj_i64(o, "l2cap_cid").unwrap_or(0);
        let direction = obj_i64(o, "direction").unwrap_or(0);
        let tx_id = obj_i64(o, "transaction_id").unwrap_or(0);
        let param_len = obj_i64(o, "param_len").unwrap_or(0);
        if pdu_id == SDP_ERROR_RSP_ID {
            let ec = obj_i64(o, "error_code").unwrap_or(0);
            b.sdp_error_rsp.push(vec![
                bdaddr.into(),
                direction.into(),
                l2cap_len.into(),
                l2cap_cid.into(),
                tx_id.into(),
                param_len.into(),
                ec.into(),
            ]);
        } else {
            let raw = hex_str_to_bytes(obj_str(o, "raw_data_hex_str").unwrap_or(""));
            b.sdp_common.push(vec![
                bdaddr.into(),
                direction.into(),
                l2cap_len.into(),
                l2cap_cid.into(),
                pdu_id.into(),
                tx_id.into(),
                param_len.into(),
                raw.into(),
            ]);
        }
    }
}

fn parse_eir_array(entry: &serde_json::Map<String, J>, b: &mut Buffers) {
    let arr = match entry.get("EIRArray").and_then(|v| v.as_array()) {
        Some(a) => a,
        None => return,
    };
    let (bdaddr, _) = get_bdaddr_peripheral(entry);
    if bdaddr.is_empty() {
        return;
    }
    for e in arr {
        let o = match e.as_object() {
            Some(o) => o,
            None => continue,
        };
        match obj_i64(o, "type") {
            Some(EIR_PSRM) => {
                let p = obj_i64(o, "page_scan_repetition_mode").unwrap_or(0);
                b.eir_psrm.push(vec![bdaddr.clone().into(), p.into()]);
            }
            Some(EIR_COD) => {
                let cod = parse_hex_int_u64(obj_str(o, "CoD_hex_str").unwrap_or("0")) as i64;
                b.eir_cod.push(vec![bdaddr.clone().into(), cod.into()]);
            }
            _ => {}
        }
    }
}

// --------------------------- ATTArray + GATTArray ---------------------------

fn parse_att_array(entry: &serde_json::Map<String, J>, b: &mut Buffers) {
    let arr = match entry.get("ATTArray").and_then(|v| v.as_array()) {
        Some(a) => a,
        None => return,
    };
    // Per-connection state used for ATT_READ_RSP correlation (the request
    // handle is implicit). g_last_read_req_handle and g_handle_to_UUID_map
    // are reset by btides_to_sql() before each top-level entry, so the same
    // happens here (function-local).
    let mut last_read_req_handle: i64 = 0;
    let mut handle_to_uuid_map: HashMap<i64, String> = HashMap::new();

    for a in arr {
        let o = match a.as_object() {
            Some(o) => o,
            None => continue,
        };
        let (bdaddr, bdaddr_rand) = if obj_i64(o, "direction") == Some(TYPE_BTIDES_DIR_C2P) {
            get_bdaddr_central(entry)
        } else {
            get_bdaddr_peripheral(entry)
        };

        // Even if the bdaddr is the placeholder, we still need to track
        // ATT_READ_REQ handles for later RSP correlation, exactly like Python.
        if bdaddr == "00:00:00:00:00:00" {
            if obj_i64(o, "opcode") == Some(ATT_READ_REQ) {
                last_read_req_handle = obj_i64(o, "handle").unwrap_or(0);
            }
            continue;
        }

        if let Some(en) = o.get("ATT_handle_enumeration").and_then(|v| v.as_array()) {
            for h in en {
                let ho = match h.as_object() {
                    Some(h) => h,
                    None => continue,
                };
                let handle = obj_i64(ho, "handle").unwrap_or(0);
                let uuid = normalize_uuid(obj_str(ho, "UUID").unwrap_or(""));
                b.gatt_attribute_handles.push(vec![
                    bdaddr.clone().into(),
                    bdaddr_rand.into(),
                    handle.into(),
                    uuid.into(),
                ]);
            }
        }

        let opcode = match obj_i64(o, "opcode") {
            Some(x) => x,
            None => continue,
        };
        match opcode {
            ATT_FIND_INFORMATION_RSP => {
                if let Some(info) = o.get("information_data").and_then(|v| v.as_array()) {
                    for ie in info {
                        let ieo = match ie.as_object() {
                            Some(x) => x,
                            None => continue,
                        };
                        let h = obj_i64(ieo, "handle").unwrap_or(0);
                        let u = obj_str(ieo, "UUID").unwrap_or("").to_string();
                        handle_to_uuid_map.insert(h, u);
                    }
                }
            }
            ATT_READ_REQ => {
                last_read_req_handle = obj_i64(o, "handle").unwrap_or(0);
            }
            ATT_READ_RSP => {
                let handle = last_read_req_handle;
                if handle == 0 {
                    continue;
                }
                let byte_values =
                    hex_str_to_bytes(obj_str(o, "value_hex_str").unwrap_or(""));
                // If the prior FIND_INFORMATION_RSP marked this handle as a
                // characteristic declaration (0x2803), decompose the value
                // into properties + char_value_handle + UUID and write to
                // GATT_characteristics rather than GATT_characteristics_values.
                let is_char_decl = handle_to_uuid_map
                    .get(&handle)
                    .map(|s| s == "2803")
                    .unwrap_or(false);
                if is_char_decl {
                    if byte_values.len() < 3 {
                        continue;
                    }
                    let char_properties = byte_values[0] as i64;
                    let char_value_handle = u16::from_le_bytes([byte_values[1], byte_values[2]]) as i64;
                    if char_value_handle == 0 {
                        continue;
                    }
                    let tail = &byte_values[3..];
                    let uuid_str = if tail.len() == 2 {
                        format!("{:04x}", u16::from_le_bytes([tail[0], tail[1]]))
                    } else {
                        // 16-byte UUID128 reversed (little-endian)
                        let mut le_bytes = tail.to_vec();
                        le_bytes.reverse();
                        hex::encode(&le_bytes)
                    };
                    let uuid = normalize_uuid(&uuid_str);
                    b.gatt_characteristics.push(vec![
                        bdaddr.clone().into(),
                        bdaddr_rand.into(),
                        handle.into(),
                        char_properties.into(),
                        char_value_handle.into(),
                        uuid.into(),
                    ]);
                } else {
                    b.gatt_characteristics_values.push(vec![
                        bdaddr.clone().into(),
                        bdaddr_rand.into(),
                        handle.into(),
                        opcode.into(),
                        byte_values.into(),
                    ]);
                }
            }
            _ => {}
        }
    }
}

fn parse_gatt_array(entry: &serde_json::Map<String, J>, b: &mut Buffers) {
    let arr = match entry.get("GATTArray").and_then(|v| v.as_array()) {
        Some(a) => a,
        None => return,
    };
    let (bdaddr, bdaddr_rand) = get_bdaddr_peripheral(entry);
    if bdaddr.is_empty() {
        return;
    }

    for svc in arr {
        let so = match svc.as_object() {
            Some(o) => o,
            None => continue,
        };
        // Service row (skip placeholder)
        if !so.contains_key("placeholder_entry") {
            let utype = obj_str(so, "utype").unwrap_or("");
            let service_type: i64 = match utype {
                "2800" => 0,
                "2801" => 1,
                _ => {
                    // Match Python which exits here. We just skip — a malformed
                    // gatt service shouldn't take down the whole import.
                    continue;
                }
            };
            let bh = obj_i64(so, "begin_handle").unwrap_or(0);
            let eh = obj_i64(so, "end_handle").unwrap_or(0);
            let uuid = normalize_uuid(obj_str(so, "UUID").unwrap_or(""));
            b.gatt_services.push(vec![
                bdaddr.clone().into(),
                bdaddr_rand.into(),
                service_type.into(),
                bh.into(),
                eh.into(),
                uuid.into(),
            ]);
        }

        let chars = match so.get("characteristics").and_then(|v| v.as_array()) {
            Some(c) => c,
            None => continue,
        };
        for ch in chars {
            let co = match ch.as_object() {
                Some(o) => o,
                None => continue,
            };
            if !co.contains_key("placeholder_entry") {
                let dh = obj_i64(co, "handle").unwrap_or(0);
                let props = obj_i64(co, "properties").unwrap_or(0);
                let vh = obj_i64(co, "value_handle").unwrap_or(0);
                if dh == 0 || vh == 0 {
                    continue;
                }
                let uuid = normalize_uuid(obj_str(co, "value_uuid").unwrap_or(""));
                b.gatt_characteristics.push(vec![
                    bdaddr.clone().into(),
                    bdaddr_rand.into(),
                    dh.into(),
                    props.into(),
                    vh.into(),
                    uuid.into(),
                ]);
            }

            if let Some(cv) = co.get("char_value").and_then(|v| v.as_object()) {
                let cv_handle_raw = cv.get("handle");
                let cvh: i64 = match cv_handle_raw {
                    Some(v) if v.is_string() => i64::from_str_radix(
                        v.as_str().unwrap().trim_start_matches("0x"),
                        16,
                    )
                    .unwrap_or(0),
                    Some(v) => as_i64(v).unwrap_or(0),
                    None => 0,
                };
                if cvh != 0 {
                    if let Some(io) = cv.get("io_array").and_then(|v| v.as_array()) {
                        for ie in io {
                            let ieo = match ie.as_object() {
                                Some(x) => x,
                                None => continue,
                            };
                            let op = obj_i64(ieo, "io_type").unwrap_or(0);
                            let bv =
                                hex_str_to_bytes(obj_str(ieo, "value_hex_str").unwrap_or(""));
                            b.gatt_characteristics_values.push(vec![
                                bdaddr.clone().into(),
                                bdaddr_rand.into(),
                                cvh.into(),
                                op.into(),
                                bv.into(),
                            ]);
                        }
                    }
                }
            }

            if let Some(descs) = co.get("descriptors").and_then(|v| v.as_array()) {
                for d in descs {
                    let do_ = match d.as_object() {
                        Some(x) => x,
                        None => continue,
                    };
                    let uuid = obj_str(do_, "UUID").unwrap_or("");
                    let handle = obj_i64(do_, "handle").unwrap_or(0);
                    let op = ATT_READ_RSP;
                    let bv: Vec<u8> = match uuid {
                        "2900" => {
                            let ep = obj_i64(do_, "extended_properties").unwrap_or(0) as u16;
                            ep.to_le_bytes().to_vec()
                        }
                        "2901" => {
                            hex_str_to_bytes(obj_str(do_, "user_description_hex_str").unwrap_or(""))
                        }
                        "2902" | "2903" => {
                            let cb = obj_i64(do_, "config_bits").unwrap_or(0) as u16;
                            cb.to_le_bytes().to_vec()
                        }
                        "2904" => {
                            let mut buf = Vec::with_capacity(7);
                            buf.push(obj_i64(do_, "format").unwrap_or(0) as u8);
                            buf.push(obj_i64(do_, "exponent").unwrap_or(0) as u8);
                            buf.extend_from_slice(
                                &(obj_i64(do_, "unit").unwrap_or(0) as u16).to_le_bytes(),
                            );
                            buf.push(obj_i64(do_, "name_space").unwrap_or(0) as u8);
                            buf.extend_from_slice(
                                &(obj_i64(do_, "description").unwrap_or(0) as u16).to_le_bytes(),
                            );
                            buf
                        }
                        "2905" => {
                            let mut buf = Vec::new();
                            if let Some(list) =
                                do_.get("attribute_handles_list").and_then(|v| v.as_array())
                            {
                                for h in list {
                                    let hv = as_i64(h).unwrap_or(0) as u16;
                                    buf.extend_from_slice(&hv.to_le_bytes());
                                }
                            }
                            buf
                        }
                        _ => continue,
                    };
                    b.gatt_characteristic_descriptor_values.push(vec![
                        bdaddr.clone().into(),
                        bdaddr_rand.into(),
                        uuid.to_string().into(),
                        handle.into(),
                        op.into(),
                        bv.into(),
                    ]);
                }
            }
        }
    }
}

// --------------------------- GPS --------------------------------------------

fn collect_gps_ops(entry: &serde_json::Map<String, J>, b: &mut Buffers) {
    let arr = match entry.get("GPSArray").and_then(|v| v.as_array()) {
        Some(a) => a,
        None => return,
    };
    let bdaddr = match entry.get("bdaddr").and_then(|v| v.as_str()) {
        Some(s) => s.to_string(),
        None => return,
    };
    let bdaddr_random = match obj_i64(entry, "bdaddr_rand") {
        Some(r) => r,
        None => return,
    };
    if bdaddr_random != 0 && bdaddr_random != 1 {
        return;
    }
    for g in arr {
        let go = match g.as_object() {
            Some(o) => o,
            None => continue,
        };
        let lat = go.get("lat").and_then(|v| v.as_f64());
        let lon = go.get("lon").and_then(|v| v.as_f64());
        let time = go.get("time").and_then(|v| v.as_object());
        let t = time.and_then(|t| t.get("unix_time_milli")).and_then(|v| v.as_u64());
        let (lat, lon, t) = match (lat, lon, t) {
            (Some(la), Some(lo), Some(ts)) => (la, lo, ts),
            _ => continue,
        };
        let rssi = obj_i64(go, "rssi").unwrap_or(0);
        b.gps_ops
            .push((bdaddr.clone(), bdaddr_random, t, 1 /* unix_time_milli */, rssi, lat, lon));
    }
}

fn apply_gps_batch(conn: &mut mysql::PooledConn, b: &Buffers) -> mysql::Result<(usize, usize)> {
    // Mirrors parse_all_GPSArrays_batched. Returns (updates, inserts).
    if b.gps_ops.is_empty() {
        return Ok((0, 0));
    }

    // Distinct bdaddrs that will be looked up.
    let bdaddrs: HashSet<&String> = b.gps_ops.iter().map(|op| &op.0).collect();
    let bdaddrs: Vec<&String> = bdaddrs.into_iter().collect();

    // key = (bdaddr, bdaddr_random, time, time_type, lat_bits, lon_bits) -> set of rssi.
    // Floats are keyed by their bit pattern to avoid hashing f64 nans.
    let mut existing: HashMap<(String, i64, u64, i64, u64, u64), HashSet<i64>> = HashMap::new();

    let chunk_size = 1000;
    for chunk in bdaddrs.chunks(chunk_size) {
        let placeholders = vec!["?"; chunk.len()].join(",");
        let q = format!(
            "SELECT bdaddr, bdaddr_random, time, time_type, rssi, lat, lon \
             FROM bdaddr_to_GPS WHERE bdaddr IN ({})",
            placeholders
        );
        let params: Vec<Value> = chunk.iter().map(|s| (*s).clone().into()).collect();
        let rows: Vec<Row> = conn.exec(&q, params)?;
        for mut row in rows {
            let bdaddr: String = row.take(0).unwrap();
            let bdaddr_random: i64 = row.take(1).unwrap();
            let time: u64 = row.take(2).unwrap();
            let time_type: i64 = row.take(3).unwrap();
            let rssi: i64 = row.take(4).unwrap();
            let lat: f64 = row.take(5).unwrap();
            let lon: f64 = row.take(6).unwrap();
            let key = (
                bdaddr,
                bdaddr_random,
                time,
                time_type,
                lat.to_bits(),
                lon.to_bits(),
            );
            existing.entry(key).or_default().insert(rssi);
        }
    }

    let mut updates: Vec<(i64, String, i64, u64, i64, f64, f64)> = Vec::new();
    let mut inserts: Vec<(String, i64, u64, i64, i64, f64, f64)> = Vec::new();
    let mut seen_batch_inserts: HashSet<(String, i64, u64, i64, i64, u64, u64)> =
        HashSet::new();

    for op in &b.gps_ops {
        let (bdaddr, br, t, tt, rssi, lat, lon) = op.clone();
        let key = (bdaddr.clone(), br, t, tt, lat.to_bits(), lon.to_bits());
        let entry = existing.entry(key.clone()).or_default();
        if entry.contains(&0) && rssi != 0 {
            updates.push((rssi, bdaddr.clone(), br, t, tt, lat, lon));
            entry.remove(&0);
            entry.insert(rssi);
        } else if rssi == 0 && entry.iter().any(|r| *r != 0) {
            continue;
        } else {
            let seen_key = (
                bdaddr.clone(),
                br,
                t,
                tt,
                rssi,
                lat.to_bits(),
                lon.to_bits(),
            );
            if entry.contains(&rssi) || seen_batch_inserts.contains(&seen_key) {
                continue;
            }
            inserts.push((bdaddr.clone(), br, t, tt, rssi, lat, lon));
            seen_batch_inserts.insert(seen_key);
            entry.insert(rssi);
        }
    }

    let update_count = updates.len();
    let insert_count = inserts.len();

    if !updates.is_empty() {
        let upd = "UPDATE bdaddr_to_GPS SET rssi = ? WHERE bdaddr = ? AND \
                   bdaddr_random = ? AND time = ? AND time_type = ? AND \
                   lat = ? AND lon = ?";
        for u in updates {
            conn.exec_drop(
                upd,
                (u.0, u.1, u.2, u.3, u.4, u.5, u.6),
            )?;
        }
    }

    if !inserts.is_empty() {
        let cols = "(bdaddr, bdaddr_random, time, time_type, rssi, lat, lon)";
        for chunk in inserts.chunks(chunk_size) {
            let row_ph = "(?, ?, ?, ?, ?, ?, ?)";
            let placeholders = vec![row_ph; chunk.len()].join(",");
            let q = format!(
                "INSERT IGNORE INTO bdaddr_to_GPS {} VALUES {}",
                cols, placeholders
            );
            let mut params: Vec<Value> = Vec::with_capacity(chunk.len() * 7);
            for r in chunk {
                params.push(r.0.clone().into());
                params.push(r.1.into());
                params.push(r.2.into());
                params.push(r.3.into());
                params.push(r.4.into());
                params.push(r.5.into());
                params.push(r.6.into());
            }
            conn.exec_drop(q, params)?;
        }
    }

    Ok((update_count, insert_count))
}

// --------------------------- bulk-insert helper -----------------------------

struct TableSpec {
    name: &'static str,
    columns: &'static str,
    width: usize,
}

fn bulk_insert(
    conn: &mut mysql::PooledConn,
    spec: &TableSpec,
    rows: &Vec<Vec<Value>>,
    chunk_rows: usize,
) -> mysql::Result<u64> {
    if rows.is_empty() {
        return Ok(0);
    }
    let mut affected: u64 = 0;
    let row_ph = format!("({})", vec!["?"; spec.width].join(","));
    for chunk in rows.chunks(chunk_rows) {
        let placeholders = vec![row_ph.clone(); chunk.len()].join(",");
        let q = format!(
            "INSERT IGNORE INTO {} {} VALUES {}",
            spec.name, spec.columns, placeholders
        );
        let mut params: Vec<Value> = Vec::with_capacity(chunk.len() * spec.width);
        for (i, row) in chunk.iter().enumerate() {
            if row.len() != spec.width {
                eprintln!(
                    "bulk_insert mismatch for {}: row[{}].len()={} but spec.width={}",
                    spec.name,
                    i,
                    row.len(),
                    spec.width
                );
            }
            for v in row {
                params.push(v.clone());
            }
        }
        conn.exec_drop(&q, params)?;
        affected = affected.saturating_add(conn.affected_rows());
    }
    Ok(affected)
}

// Owning version of TableSpec + rows used by the parallel writer; the
// borrowed-references shape used by flush_all() can't cross thread boundaries
// because Rust can't prove the Buffers stays alive long enough.
#[derive(Clone)]
struct OwnedTable {
    name: &'static str,
    columns: &'static str,
    width: usize,
    rows: Vec<Vec<Value>>,
}

fn build_table_list_owned(b: &Buffers) -> Vec<OwnedTable> {
    // Same set + column orderings as flush_all's static list, but owning the
    // rows so threads can take a partition without lifetime gymnastics.
    macro_rules! t {
        ($name:expr, $cols:expr, $w:expr, $rows:expr) => {
            OwnedTable {
                name: $name,
                columns: $cols,
                width: $w,
                rows: $rows.clone(),
            }
        };
    }
    vec![
        t!("EIR_bdaddr_to_flags", "(bdaddr, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)", 6, b.eir_flags),
        t!("EIR_bdaddr_to_UUID16s", "(bdaddr, list_type, str_UUID16s)", 3, b.eir_uuid16s),
        t!("EIR_bdaddr_to_UUID32s", "(bdaddr, list_type, str_UUID32s)", 3, b.eir_uuid32s),
        t!("EIR_bdaddr_to_UUID128s", "(bdaddr, list_type, str_UUID128s)", 3, b.eir_uuid128s),
        t!("EIR_bdaddr_to_name", "(bdaddr, device_name_type, name_hex_str)", 3, b.eir_name),
        t!("EIR_bdaddr_to_tx_power", "(bdaddr, device_tx_power)", 2, b.eir_tx_power),
        t!("EIR_bdaddr_to_DevID", "(bdaddr, vendor_id_source, vendor_id, product_id, product_version)", 5, b.eir_dev_id),
        t!("EIR_bdaddr_to_URI", "(bdaddr, uri_hex_str)", 2, b.eir_uri),
        t!("EIR_bdaddr_to_3d_info", "(bdaddr, byte1, path_loss)", 3, b.eir_3d),
        t!("EIR_bdaddr_to_MSD", "(bdaddr, device_BT_CID, manufacturer_specific_data)", 3, b.eir_msd),
        t!("EIR_bdaddr_to_PSRM", "(bdaddr, page_scan_rep_mode)", 2, b.eir_psrm),
        t!("EIR_bdaddr_to_CoD", "(bdaddr, class_of_device)", 2, b.eir_cod),
        t!("LE_bdaddr_to_flags", "(bdaddr, bdaddr_random, le_evt_type, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)", 8, b.le_flags),
        t!("LE_bdaddr_to_UUID16s_list", "(bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID16s)", 5, b.le_uuid16s_list),
        t!("LE_bdaddr_to_UUID32s_list", "(bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID32s)", 5, b.le_uuid32s_list),
        t!("LE_bdaddr_to_UUID128s_list", "(bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID128s)", 5, b.le_uuid128s_list),
        t!("LE_bdaddr_to_name", "(bdaddr, bdaddr_random, le_evt_type, device_name_type, name_hex_str)", 5, b.le_name),
        t!("LE_bdaddr_to_tx_power", "(bdaddr, bdaddr_random, le_evt_type, device_tx_power)", 4, b.le_tx_power),
        t!("LE_bdaddr_to_CoD", "(bdaddr, bdaddr_random, le_evt_type, class_of_device)", 4, b.le_cod),
        t!("LE_bdaddr_to_appearance", "(bdaddr, bdaddr_random, le_evt_type, appearance)", 4, b.le_appearance),
        t!("LE_bdaddr_to_connect_interval", "(bdaddr, bdaddr_random, le_evt_type, interval_min, interval_max)", 5, b.le_conn_interval),
        t!("LE_bdaddr_to_UUID16_service_solicit", "(bdaddr, bdaddr_random, le_evt_type, str_UUID16s)", 4, b.le_uuid16_ss),
        t!("LE_bdaddr_to_UUID128_service_solicit", "(bdaddr, bdaddr_random, le_evt_type, str_UUID128s)", 4, b.le_uuid128_ss),
        t!("LE_bdaddr_to_UUID16_service_data", "(bdaddr, bdaddr_random, le_evt_type, ACID_length, UUID16_hex_str, service_data_hex_str)", 6, b.le_uuid16_sd),
        t!("LE_bdaddr_to_UUID32_service_data", "(bdaddr, bdaddr_random, le_evt_type, ACID_length, UUID32_hex_str, service_data_hex_str)", 6, b.le_uuid32_sd),
        t!("LE_bdaddr_to_UUID128_service_data", "(bdaddr, bdaddr_random, le_evt_type, ACID_length, UUID128_hex_str, service_data_hex_str)", 6, b.le_uuid128_sd),
        t!("LE_bdaddr_to_public_target_bdaddr", "(bdaddr, bdaddr_random, le_evt_type, public_bdaddr)", 4, b.le_public_target),
        t!("LE_bdaddr_to_random_target_bdaddr", "(bdaddr, bdaddr_random, le_evt_type, random_bdaddr)", 4, b.le_random_target),
        t!("LE_bdaddr_to_other_le_bdaddr", "(bdaddr, bdaddr_random, le_evt_type, other_bdaddr, other_bdaddr_random)", 5, b.le_other_le),
        t!("LE_bdaddr_to_role", "(bdaddr, bdaddr_random, le_evt_type, role)", 4, b.le_role),
        t!("LE_bdaddr_to_URI", "(bdaddr, bdaddr_random, le_evt_type, uri_hex_str)", 4, b.le_uri),
        t!("LE_bdaddr_to_3d_info", "(bdaddr, bdaddr_random, le_evt_type, byte1, path_loss)", 5, b.le_3d),
        t!("LE_bdaddr_to_MSD", "(bdaddr, bdaddr_random, le_evt_type, device_BT_CID, manufacturer_specific_data)", 5, b.le_msd),
        t!("HCI_bdaddr_to_name", "(bdaddr, status, name_hex_str)", 3, b.hci_name),
        t!("L2CAP_CONNECTION_PARAMETER_UPDATE_REQ", "(bdaddr, bdaddr_random, direction, code, pkt_id, data_len, interval_min, interval_max, latency, timeout)", 10, b.l2cap_conn_update_req),
        t!("L2CAP_CONNECTION_PARAMETER_UPDATE_RSP", "(bdaddr, bdaddr_random, direction, code, pkt_id, data_len, result)", 7, b.l2cap_conn_update_rsp),
        t!("SMP_Pairing_Req_Res", "(bdaddr, bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist)", 9, b.smp_pairing),
        t!("SDP_ERROR_RSP", "(bdaddr, direction, l2cap_len, l2cap_cid, transaction_id, param_len, error_code)", 7, b.sdp_error_rsp),
        t!("SDP_Common", "(bdaddr, direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values)", 8, b.sdp_common),
        t!("LL_UNKNOWN_RSP", "(bdaddr, bdaddr_random, unknown_opcode)", 3, b.ll_unknown_rsp),
        t!("LL_VERSION_IND", "(bdaddr, bdaddr_random, ll_version, device_BT_CID, ll_sub_version)", 5, b.ll_version_ind),
        t!("LL_FEATUREs", "(bdaddr, bdaddr_random, opcode, features)", 4, b.ll_features),
        t!("LL_PINGs", "(bdaddr, bdaddr_random, opcode, direction)", 4, b.ll_pings),
        t!("LL_LENGTHs", "(bdaddr, bdaddr_random, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time)", 7, b.ll_lengths),
        t!("LL_PHYs", "(bdaddr, bdaddr_random, opcode, direction, tx_phys, rx_phys)", 6, b.ll_phys),
        t!("LMP_NAME_RES_fragmented", "(bdaddr, name_offset, name_total_length, name_fragment)", 4, b.lmp_name_res_fragmented),
        t!("LMP_NAME_RES_defragmented", "(bdaddr, device_name)", 2, b.lmp_name_res_defragmented),
        t!("LMP_ACCEPTED", "(bdaddr, rcvd_opcode)", 2, b.lmp_accepted),
        t!("LMP_NOT_ACCEPTED", "(bdaddr, rcvd_opcode, error_code)", 3, b.lmp_not_accepted),
        t!("LMP_ACCEPTED_EXT", "(bdaddr, rcvd_escape_opcode, rcvd_extended_opcode)", 3, b.lmp_accepted_ext),
        t!("LMP_NOT_ACCEPTED_EXT", "(bdaddr, rcvd_escape_opcode, rcvd_extended_opcode, error_code)", 4, b.lmp_not_accepted_ext),
        t!("LMP_DETACH", "(bdaddr, error_code)", 2, b.lmp_detach),
        t!("LMP_PREFERRED_RATE", "(bdaddr, data_rate)", 2, b.lmp_preferred_rate),
        t!("LMP_VERSION_REQ", "(bdaddr, lmp_version, device_BT_CID, lmp_sub_version)", 4, b.lmp_version_req),
        t!("LMP_VERSION_RES", "(bdaddr, lmp_version, device_BT_CID, lmp_sub_version)", 4, b.lmp_version_res),
        t!("LMP_FEATURES_REQ", "(bdaddr, page, features)", 3, b.lmp_features_req),
        t!("LMP_FEATURES_RES", "(bdaddr, page, features)", 3, b.lmp_features_res),
        t!("LMP_FEATURES_REQ_EXT", "(bdaddr, page, max_page, features)", 4, b.lmp_features_req_ext),
        t!("LMP_FEATURES_RES_EXT", "(bdaddr, page, max_page, features)", 4, b.lmp_features_res_ext),
        t!("LMP_CHANNEL_CLASSIFICATION", "(bdaddr, afh_channel_classification)", 2, b.lmp_channel_classification),
        t!("LMP_POWER_CONTROL_REQ", "(bdaddr, power_adj_req)", 2, b.lmp_power_control_req),
        t!("LMP_POWER_CONTROL_RES", "(bdaddr, power_adj_res)", 2, b.lmp_power_control_res),
        t!("LMP_empty_opcodes", "(bdaddr, opcode)", 2, b.lmp_empty_opcodes),
        t!("GATT_attribute_handles", "(bdaddr, bdaddr_random, attribute_handle, UUID)", 4, b.gatt_attribute_handles),
        t!("GATT_services", "(bdaddr, bdaddr_random, service_type, begin_handle, end_handle, UUID)", 6, b.gatt_services),
        t!("GATT_characteristics", "(bdaddr, bdaddr_random, declaration_handle, char_properties, char_value_handle, UUID)", 6, b.gatt_characteristics),
        t!("GATT_characteristics_values", "(bdaddr, bdaddr_random, char_value_handle, operation, byte_values)", 5, b.gatt_characteristics_values),
        t!("GATT_characteristic_descriptor_values", "(bdaddr, bdaddr_random, UUID, descriptor_handle, operation, byte_values)", 6, b.gatt_characteristic_descriptor_values),
    ]
}

// Returns true if the error is a MySQL deadlock-victim (ER_LOCK_DEADLOCK = 1213).
// Also matches ER_LOCK_WAIT_TIMEOUT (1205) since the same retry strategy applies
// — when the lock waiter times out, the safe response is to roll back & retry.
fn is_deadlock(err: &mysql::Error) -> bool {
    use mysql::Error::MySqlError;
    if let MySqlError(e) = err {
        return e.code == 1213 || e.code == 1205;
    }
    false
}

// Retry a closure on InnoDB deadlock/lock-wait-timeout, with exponential
// backoff (base 50ms, max 2s, simple linear jitter). Returns the final result
// or the last error if retries are exhausted. The closure is responsible for
// idempotency — INSERT IGNORE rolls back cleanly under a deadlock victim
// transaction, and re-running converges to the same state.
fn retry_on_deadlock<T, F>(
    label: &str,
    max_retries: usize,
    mut f: F,
) -> mysql::Result<T>
where
    F: FnMut() -> mysql::Result<T>,
{
    let mut attempt = 0usize;
    loop {
        match f() {
            Ok(v) => return Ok(v),
            Err(e) if is_deadlock(&e) && attempt < max_retries => {
                attempt += 1;
                let backoff_ms =
                    (50u64.saturating_mul(1 << attempt.min(6))).min(2000)
                        + (attempt as u64 * 17);
                eprintln!(
                    "[{}] deadlock victim (attempt {}/{}), sleeping {}ms and retrying",
                    label, attempt, max_retries, backoff_ms
                );
                std::thread::sleep(std::time::Duration::from_millis(backoff_ms));
            }
            Err(e) => return Err(e),
        }
    }
}

// Same intent as flush_parallel, but each lane's transaction is itself
// retried on deadlock. Errors from a lane that aren't deadlocks (or that
// exhaust retries) propagate as a stderr message; the lane drops its rows.
fn flush_parallel_with_retry(
    pool: &Pool,
    tables: Vec<OwnedTable>,
    threads: usize,
    verbose: bool,
    max_retries: usize,
) -> (u64, u64) {
    const CHUNK: usize = 200;
    let mut by_size = tables;
    by_size.sort_by(|a, b| b.rows.len().cmp(&a.rows.len()));
    let mut lanes: Vec<(u64, Vec<OwnedTable>)> =
        (0..threads).map(|_| (0u64, Vec::new())).collect();
    for t in by_size {
        lanes.sort_by(|a, b| a.0.cmp(&b.0));
        let row_count = t.rows.len() as u64;
        lanes[0].0 += row_count;
        lanes[0].1.push(t);
    }

    let handles: Vec<_> = lanes
        .into_iter()
        .map(|(_, lane_tables)| {
            let pool = pool.clone();
            std::thread::spawn(move || -> (u64, u64, Vec<String>) {
                let lane_label = format!(
                    "lane-{}",
                    lane_tables.first().map(|t| t.name).unwrap_or("empty")
                );
                let res = retry_on_deadlock(&lane_label, max_retries, || {
                    let mut conn = pool.get_conn()?;
                    conn.query_drop("START TRANSACTION")?;
                    let mut attempted = 0u64;
                    let mut inserted = 0u64;
                    let mut log = Vec::new();
                    for t in &lane_tables {
                        let attempted_t = t.rows.len() as u64;
                        let spec = TableSpec {
                            name: t.name,
                            columns: t.columns,
                            width: t.width,
                        };
                        // On deadlock partway through the lane's tables, the
                        // outer retry rolls back and replays. INSERT IGNORE
                        // makes that re-execution safe.
                        let inserted_t = bulk_insert(&mut conn, &spec, &t.rows, CHUNK)?;
                        attempted += attempted_t;
                        inserted += inserted_t;
                        if verbose && attempted_t > 0 {
                            log.push(format!(
                                "  {:50} attempted={:>7} inserted={:>7}",
                                t.name, attempted_t, inserted_t
                            ));
                        }
                    }
                    conn.query_drop("COMMIT")?;
                    Ok((attempted, inserted, log))
                });
                match res {
                    Ok(v) => v,
                    Err(e) => {
                        eprintln!("{} failed after retries: {}", lane_label, e);
                        (0, 0, Vec::new())
                    }
                }
            })
        })
        .collect();

    let mut total_a = 0u64;
    let mut total_i = 0u64;
    for h in handles {
        match h.join() {
            Ok((a, i, log)) => {
                total_a += a;
                total_i += i;
                if verbose {
                    for line in log {
                        eprintln!("{}", line);
                    }
                }
            }
            Err(e) => eprintln!("lane panic: {:?}", e),
        }
    }
    (total_a, total_i)
}

fn flush_all(conn: &mut mysql::PooledConn, b: &Buffers, verbose: bool) -> mysql::Result<(u64, u64)> {
    // Chunk rows so we stay clear of MySQL's 65535 placeholder cap and the
    // 1 MiB default max_allowed_packet headroom. 200 rows × ~10 cols = ~2000
    // placeholders / packet — well within both limits.
    const CHUNK: usize = 200;

    let tables: Vec<(&TableSpec, &Vec<Vec<Value>>)> = vec![
        // EIR / BTC
        (&TableSpec { name: "EIR_bdaddr_to_flags", columns: "(bdaddr, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)", width: 6 }, &b.eir_flags),
        (&TableSpec { name: "EIR_bdaddr_to_UUID16s", columns: "(bdaddr, list_type, str_UUID16s)", width: 3 }, &b.eir_uuid16s),
        (&TableSpec { name: "EIR_bdaddr_to_UUID32s", columns: "(bdaddr, list_type, str_UUID32s)", width: 3 }, &b.eir_uuid32s),
        (&TableSpec { name: "EIR_bdaddr_to_UUID128s", columns: "(bdaddr, list_type, str_UUID128s)", width: 3 }, &b.eir_uuid128s),
        (&TableSpec { name: "EIR_bdaddr_to_name", columns: "(bdaddr, device_name_type, name_hex_str)", width: 3 }, &b.eir_name),
        (&TableSpec { name: "EIR_bdaddr_to_tx_power", columns: "(bdaddr, device_tx_power)", width: 2 }, &b.eir_tx_power),
        (&TableSpec { name: "EIR_bdaddr_to_DevID", columns: "(bdaddr, vendor_id_source, vendor_id, product_id, product_version)", width: 5 }, &b.eir_dev_id),
        (&TableSpec { name: "EIR_bdaddr_to_URI", columns: "(bdaddr, uri_hex_str)", width: 2 }, &b.eir_uri),
        (&TableSpec { name: "EIR_bdaddr_to_3d_info", columns: "(bdaddr, byte1, path_loss)", width: 3 }, &b.eir_3d),
        (&TableSpec { name: "EIR_bdaddr_to_MSD", columns: "(bdaddr, device_BT_CID, manufacturer_specific_data)", width: 3 }, &b.eir_msd),
        (&TableSpec { name: "EIR_bdaddr_to_PSRM", columns: "(bdaddr, page_scan_rep_mode)", width: 2 }, &b.eir_psrm),
        (&TableSpec { name: "EIR_bdaddr_to_CoD", columns: "(bdaddr, class_of_device)", width: 2 }, &b.eir_cod),

        // LE
        (&TableSpec { name: "LE_bdaddr_to_flags", columns: "(bdaddr, bdaddr_random, le_evt_type, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)", width: 8 }, &b.le_flags),
        (&TableSpec { name: "LE_bdaddr_to_UUID16s_list", columns: "(bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID16s)", width: 5 }, &b.le_uuid16s_list),
        (&TableSpec { name: "LE_bdaddr_to_UUID32s_list", columns: "(bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID32s)", width: 5 }, &b.le_uuid32s_list),
        (&TableSpec { name: "LE_bdaddr_to_UUID128s_list", columns: "(bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID128s)", width: 5 }, &b.le_uuid128s_list),
        (&TableSpec { name: "LE_bdaddr_to_name", columns: "(bdaddr, bdaddr_random, le_evt_type, device_name_type, name_hex_str)", width: 5 }, &b.le_name),
        (&TableSpec { name: "LE_bdaddr_to_tx_power", columns: "(bdaddr, bdaddr_random, le_evt_type, device_tx_power)", width: 4 }, &b.le_tx_power),
        (&TableSpec { name: "LE_bdaddr_to_CoD", columns: "(bdaddr, bdaddr_random, le_evt_type, class_of_device)", width: 4 }, &b.le_cod),
        (&TableSpec { name: "LE_bdaddr_to_appearance", columns: "(bdaddr, bdaddr_random, le_evt_type, appearance)", width: 4 }, &b.le_appearance),
        (&TableSpec { name: "LE_bdaddr_to_connect_interval", columns: "(bdaddr, bdaddr_random, le_evt_type, interval_min, interval_max)", width: 5 }, &b.le_conn_interval),
        (&TableSpec { name: "LE_bdaddr_to_UUID16_service_solicit", columns: "(bdaddr, bdaddr_random, le_evt_type, str_UUID16s)", width: 4 }, &b.le_uuid16_ss),
        (&TableSpec { name: "LE_bdaddr_to_UUID128_service_solicit", columns: "(bdaddr, bdaddr_random, le_evt_type, str_UUID128s)", width: 4 }, &b.le_uuid128_ss),
        (&TableSpec { name: "LE_bdaddr_to_UUID16_service_data", columns: "(bdaddr, bdaddr_random, le_evt_type, ACID_length, UUID16_hex_str, service_data_hex_str)", width: 6 }, &b.le_uuid16_sd),
        (&TableSpec { name: "LE_bdaddr_to_UUID32_service_data", columns: "(bdaddr, bdaddr_random, le_evt_type, ACID_length, UUID32_hex_str, service_data_hex_str)", width: 6 }, &b.le_uuid32_sd),
        (&TableSpec { name: "LE_bdaddr_to_UUID128_service_data", columns: "(bdaddr, bdaddr_random, le_evt_type, ACID_length, UUID128_hex_str, service_data_hex_str)", width: 6 }, &b.le_uuid128_sd),
        (&TableSpec { name: "LE_bdaddr_to_public_target_bdaddr", columns: "(bdaddr, bdaddr_random, le_evt_type, public_bdaddr)", width: 4 }, &b.le_public_target),
        (&TableSpec { name: "LE_bdaddr_to_random_target_bdaddr", columns: "(bdaddr, bdaddr_random, le_evt_type, random_bdaddr)", width: 4 }, &b.le_random_target),
        (&TableSpec { name: "LE_bdaddr_to_other_le_bdaddr", columns: "(bdaddr, bdaddr_random, le_evt_type, other_bdaddr, other_bdaddr_random)", width: 5 }, &b.le_other_le),
        (&TableSpec { name: "LE_bdaddr_to_role", columns: "(bdaddr, bdaddr_random, le_evt_type, role)", width: 4 }, &b.le_role),
        (&TableSpec { name: "LE_bdaddr_to_URI", columns: "(bdaddr, bdaddr_random, le_evt_type, uri_hex_str)", width: 4 }, &b.le_uri),
        (&TableSpec { name: "LE_bdaddr_to_3d_info", columns: "(bdaddr, bdaddr_random, le_evt_type, byte1, path_loss)", width: 5 }, &b.le_3d),
        (&TableSpec { name: "LE_bdaddr_to_MSD", columns: "(bdaddr, bdaddr_random, le_evt_type, device_BT_CID, manufacturer_specific_data)", width: 5 }, &b.le_msd),

        // HCI
        (&TableSpec { name: "HCI_bdaddr_to_name", columns: "(bdaddr, status, name_hex_str)", width: 3 }, &b.hci_name),

        // L2CAP
        (&TableSpec { name: "L2CAP_CONNECTION_PARAMETER_UPDATE_REQ", columns: "(bdaddr, bdaddr_random, direction, code, pkt_id, data_len, interval_min, interval_max, latency, timeout)", width: 10 }, &b.l2cap_conn_update_req),
        (&TableSpec { name: "L2CAP_CONNECTION_PARAMETER_UPDATE_RSP", columns: "(bdaddr, bdaddr_random, direction, code, pkt_id, data_len, result)", width: 7 }, &b.l2cap_conn_update_rsp),

        // SMP
        (&TableSpec { name: "SMP_Pairing_Req_Res", columns: "(bdaddr, bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist)", width: 9 }, &b.smp_pairing),

        // SDP
        (&TableSpec { name: "SDP_ERROR_RSP", columns: "(bdaddr, direction, l2cap_len, l2cap_cid, transaction_id, param_len, error_code)", width: 7 }, &b.sdp_error_rsp),
        (&TableSpec { name: "SDP_Common", columns: "(bdaddr, direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values)", width: 8 }, &b.sdp_common),

        // LL
        (&TableSpec { name: "LL_UNKNOWN_RSP", columns: "(bdaddr, bdaddr_random, unknown_opcode)", width: 3 }, &b.ll_unknown_rsp),
        (&TableSpec { name: "LL_VERSION_IND", columns: "(bdaddr, bdaddr_random, ll_version, device_BT_CID, ll_sub_version)", width: 5 }, &b.ll_version_ind),
        (&TableSpec { name: "LL_FEATUREs", columns: "(bdaddr, bdaddr_random, opcode, features)", width: 4 }, &b.ll_features),
        (&TableSpec { name: "LL_PINGs", columns: "(bdaddr, bdaddr_random, opcode, direction)", width: 4 }, &b.ll_pings),
        (&TableSpec { name: "LL_LENGTHs", columns: "(bdaddr, bdaddr_random, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time)", width: 7 }, &b.ll_lengths),
        (&TableSpec { name: "LL_PHYs", columns: "(bdaddr, bdaddr_random, opcode, direction, tx_phys, rx_phys)", width: 6 }, &b.ll_phys),

        // LMP
        (&TableSpec { name: "LMP_NAME_RES_fragmented", columns: "(bdaddr, name_offset, name_total_length, name_fragment)", width: 4 }, &b.lmp_name_res_fragmented),
        (&TableSpec { name: "LMP_NAME_RES_defragmented", columns: "(bdaddr, device_name)", width: 2 }, &b.lmp_name_res_defragmented),
        (&TableSpec { name: "LMP_ACCEPTED", columns: "(bdaddr, rcvd_opcode)", width: 2 }, &b.lmp_accepted),
        (&TableSpec { name: "LMP_NOT_ACCEPTED", columns: "(bdaddr, rcvd_opcode, error_code)", width: 3 }, &b.lmp_not_accepted),
        (&TableSpec { name: "LMP_ACCEPTED_EXT", columns: "(bdaddr, rcvd_escape_opcode, rcvd_extended_opcode)", width: 3 }, &b.lmp_accepted_ext),
        (&TableSpec { name: "LMP_NOT_ACCEPTED_EXT", columns: "(bdaddr, rcvd_escape_opcode, rcvd_extended_opcode, error_code)", width: 4 }, &b.lmp_not_accepted_ext),
        (&TableSpec { name: "LMP_DETACH", columns: "(bdaddr, error_code)", width: 2 }, &b.lmp_detach),
        (&TableSpec { name: "LMP_PREFERRED_RATE", columns: "(bdaddr, data_rate)", width: 2 }, &b.lmp_preferred_rate),
        (&TableSpec { name: "LMP_VERSION_REQ", columns: "(bdaddr, lmp_version, device_BT_CID, lmp_sub_version)", width: 4 }, &b.lmp_version_req),
        (&TableSpec { name: "LMP_VERSION_RES", columns: "(bdaddr, lmp_version, device_BT_CID, lmp_sub_version)", width: 4 }, &b.lmp_version_res),
        (&TableSpec { name: "LMP_FEATURES_REQ", columns: "(bdaddr, page, features)", width: 3 }, &b.lmp_features_req),
        (&TableSpec { name: "LMP_FEATURES_RES", columns: "(bdaddr, page, features)", width: 3 }, &b.lmp_features_res),
        (&TableSpec { name: "LMP_FEATURES_REQ_EXT", columns: "(bdaddr, page, max_page, features)", width: 4 }, &b.lmp_features_req_ext),
        (&TableSpec { name: "LMP_FEATURES_RES_EXT", columns: "(bdaddr, page, max_page, features)", width: 4 }, &b.lmp_features_res_ext),
        (&TableSpec { name: "LMP_CHANNEL_CLASSIFICATION", columns: "(bdaddr, afh_channel_classification)", width: 2 }, &b.lmp_channel_classification),
        (&TableSpec { name: "LMP_POWER_CONTROL_REQ", columns: "(bdaddr, power_adj_req)", width: 2 }, &b.lmp_power_control_req),
        (&TableSpec { name: "LMP_POWER_CONTROL_RES", columns: "(bdaddr, power_adj_res)", width: 2 }, &b.lmp_power_control_res),
        (&TableSpec { name: "LMP_empty_opcodes", columns: "(bdaddr, opcode)", width: 2 }, &b.lmp_empty_opcodes),

        // GATT
        (&TableSpec { name: "GATT_attribute_handles", columns: "(bdaddr, bdaddr_random, attribute_handle, UUID)", width: 4 }, &b.gatt_attribute_handles),
        (&TableSpec { name: "GATT_services", columns: "(bdaddr, bdaddr_random, service_type, begin_handle, end_handle, UUID)", width: 6 }, &b.gatt_services),
        (&TableSpec { name: "GATT_characteristics", columns: "(bdaddr, bdaddr_random, declaration_handle, char_properties, char_value_handle, UUID)", width: 6 }, &b.gatt_characteristics),
        (&TableSpec { name: "GATT_characteristics_values", columns: "(bdaddr, bdaddr_random, char_value_handle, operation, byte_values)", width: 5 }, &b.gatt_characteristics_values),
        (&TableSpec { name: "GATT_characteristic_descriptor_values", columns: "(bdaddr, bdaddr_random, UUID, descriptor_handle, operation, byte_values)", width: 6 }, &b.gatt_characteristic_descriptor_values),
    ];

    let mut total_rows: u64 = 0;
    let mut total_affected: u64 = 0;
    for (spec, rows) in tables {
        let attempted = rows.len() as u64;
        let affected = bulk_insert(conn, spec, rows, CHUNK)?;
        total_rows += attempted;
        total_affected += affected;
        if verbose && attempted > 0 {
            eprintln!(
                "  {:50} attempted={:>7} inserted={:>7} duplicates={}",
                spec.name,
                attempted,
                affected,
                attempted.saturating_sub(affected)
            );
        }
    }
    Ok((total_rows, total_affected))
}

// --------------------------- main -------------------------------------------

#[derive(Parser, Debug)]
#[command(about = "BTIDES to MySQL importer (Rust port of BTIDES_to_SQL.py)")]
struct Args {
    /// Input file name for BTIDES JSON file. May be passed multiple times.
    #[arg(long, action = clap::ArgAction::Append, required = true)]
    input: Vec<String>,

    /// Use the alternate bttest database (matches --use-test-db in Python).
    #[arg(long)]
    use_test_db: bool,

    /// Print per-table statistics.
    #[arg(long, alias = "verbose-print")]
    verbose: bool,

    /// MySQL host (default localhost).
    #[arg(long, default_value = "localhost")]
    db_host: String,

    /// MySQL user (default 'user' — matches TME_helpers.py).
    #[arg(long, default_value = "user")]
    db_user: String,

    /// MySQL password (default 'a' — matches TME_helpers.py).
    #[arg(long, default_value = "a")]
    db_password: String,

    /// Disable per-statement autocommit and commit once at the end.
    #[arg(long, default_value_t = true)]
    one_transaction: bool,

    /// Use N parallel writer connections (each handles a disjoint set of
    /// destination tables). Default 1 = serial. GPS always runs serially at
    /// the end because of its read-modify-write semantics.
    #[arg(long, default_value_t = 1)]
    writer_threads: usize,

    /// Parse N input files concurrently into per-thread row buffers, then
    /// merge them before the write phase. Default 1 = serial parsing. Each
    /// reader operates on its own file(s), so there is no contention. Has no
    /// effect when only one --input file is provided.
    #[arg(long, default_value_t = 1)]
    reader_threads: usize,

    /// On MySQL error 1213 (deadlock victim), roll back and retry the
    /// transaction up to N times. Each retry sleeps an exponentially
    /// backed-off, jittered delay before re-running. Default 8 — sufficient
    /// for ~5 concurrent processes hammering the same table.
    #[arg(long, default_value_t = 8)]
    deadlock_retries: usize,
}

fn main() {
    let args = Args::parse();

    let opts: Opts = OptsBuilder::new()
        .ip_or_hostname(Some(&args.db_host))
        .user(Some(&args.db_user))
        .pass(Some(&args.db_password))
        .db_name(Some(if args.use_test_db { "bttest" } else { "bt2" }))
        .into();
    let pool = Pool::new(opts).expect("MySQL pool");
    let mut conn = pool.get_conn().expect("MySQL conn");

    // utf8mb4 to match what TME_helpers.py negotiates.
    let _ = conn.query_drop("SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci");

    // ---------------- Parse phase ----------------
    // With reader_threads > 1, split args.input across that many worker
    // threads, each parsing its assigned files into its own Buffers; then
    // merge.
    let t_parse = Instant::now();
    let mut buffers = if args.reader_threads <= 1 || args.input.len() <= 1 {
        // Serial parse: re-use the per-file path, accumulating into one Buffers.
        let mut acc = Buffers::default();
        for path in &args.input {
            let b = parse_file(path);
            merge_buffers(&mut acc, b);
        }
        acc
    } else {
        // Split files round-robin across reader_threads worker threads.
        let n = args.reader_threads.min(args.input.len());
        let mut groups: Vec<Vec<String>> = (0..n).map(|_| Vec::new()).collect();
        for (i, path) in args.input.iter().enumerate() {
            groups[i % n].push(path.clone());
        }
        let handles: Vec<_> = groups
            .into_iter()
            .map(|paths| {
                std::thread::spawn(move || {
                    let mut acc = Buffers::default();
                    for p in &paths {
                        let b = parse_file(p);
                        merge_buffers(&mut acc, b);
                    }
                    acc
                })
            })
            .collect();
        let mut acc = Buffers::default();
        for h in handles {
            match h.join() {
                Ok(b) => merge_buffers(&mut acc, b),
                Err(e) => eprintln!("reader thread panic: {:?}", e),
            }
        }
        acc
    };
    finalize_lmp_name_res_defrag(&mut buffers);
    let parse_elapsed = t_parse.elapsed();
    eprintln!(
        "Parsed {} file(s) with {} reader thread(s) in {:.2}s",
        args.input.len(),
        args.reader_threads,
        parse_elapsed.as_secs_f64()
    );

    // ---------------- Write phase ----------------
    // Wrap the per-mode write in retry-on-deadlock — InnoDB's gap locks on
    // INSERT IGNORE against a unique index will deadlock when two processes
    // try to insert overlapping key ranges in opposite orders. MySQL returns
    // 1213, and the only valid response is to roll back and replay.
    let t_write = Instant::now();
    let (attempted, inserted) =
        retry_on_deadlock("flush_all", args.deadlock_retries, || {
            if args.writer_threads <= 1 {
                let mut conn2 = pool.get_conn()?;
                conn2.query_drop("START TRANSACTION")?;
                let r = flush_all(&mut conn2, &buffers, args.verbose)?;
                conn2.query_drop("COMMIT")?;
                Ok(r)
            } else {
                let owned = build_table_list_owned(&buffers);
                Ok(flush_parallel_with_retry(
                    &pool,
                    owned,
                    args.writer_threads,
                    args.verbose,
                    args.deadlock_retries,
                ))
            }
        })
        .expect("flush retry exhausted");
    let (gps_updates, gps_inserts) =
        retry_on_deadlock("gps", args.deadlock_retries, || {
            let mut conn_gps = pool.get_conn()?;
            apply_gps_batch(&mut conn_gps, &buffers)
        })
        .expect("gps retry exhausted");
    let write_elapsed = t_write.elapsed();
    eprintln!(
        "Wrote {} rows ({} new) + GPS ({} updates / {} inserts) in {:.2}s ({} writer threads)",
        attempted,
        inserted,
        gps_updates,
        gps_inserts,
        write_elapsed.as_secs_f64(),
        args.writer_threads
    );
    let total_attempted = attempted + (gps_updates as u64) + (gps_inserts as u64);
    let total_inserted = inserted + (gps_updates as u64) + (gps_inserts as u64);

    eprintln!(
        "Done. Total rows attempted: {}, total new rows: {}, duplicates: {}",
        total_attempted,
        total_inserted,
        total_attempted.saturating_sub(total_inserted)
    );
}
