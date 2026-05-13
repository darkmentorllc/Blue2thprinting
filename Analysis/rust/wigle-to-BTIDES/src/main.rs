// wigle-to-BTIDES: CLI binary that converts a WiGLE Android backup SQLite
// database into a BTIDES JSON file. Ports Analysis/WIGLE_to_BTIDES.py,
// including the optional MySQL bdaddr_random lookup for BLE rows (see
// `BdaddrRandLookup` below) — disabled with --no-mysql-lookup if you don't
// have a local Blue2thprinting bt2/bttest MySQL database. When MySQL is
// disabled or returns no rows for a BDADDR, falls back to bdaddr_rand=1
// (same default as Python's `find_bdaddr_rand`).
//
// WiGLE schema (from `.schema network` / `.schema location`):
//   network(bssid TEXT PK, ssid TEXT, frequency INT, capabilities TEXT,
//           lasttime INT, lastlat DOUBLE, lastlon DOUBLE, type TEXT,
//           bestlevel INT, bestlat DOUBLE, bestlon DOUBLE,
//           rcois TEXT, mfgrid INT, service TEXT)
//   location(_id PK, bssid TEXT, level INT, lat DOUBLE, lon DOUBLE,
//            altitude DOUBLE, accuracy FLOAT, time INT, external INT, mfgrid INT)
// type 'B' = BR/EDR Classic (bdaddr_rand=0); type 'E' = BLE (looked up).

use std::collections::HashMap;
use std::path::PathBuf;

use BTIDES_model::Btides;
use clap::Parser;
use rusqlite::{params_from_iter, Connection};
use serde_json::{Map, Value};

// --------------------------------------------------------------------------
// MySQL bdaddr_random lookup (ports Python WIGLE_to_BTIDES.batch_find_bdaddr_rand)
//
// For each BLE BDADDR we want to fill in `bdaddr_rand` (public=0 / random=1)
// by majority-voting across every table in the bt2/bttest database that has
// a `bdaddr_random` column. The Python tool issues one UNION-ALL query per
// 1000-BDADDR chunk, with a shared IN-clause per table; we do the same.
// On any failure (cannot connect, table list empty, query error) we fall back
// to bdaddr_rand=1 — exactly Python's `if not tables: return 1` behavior.
// --------------------------------------------------------------------------

mod bdaddr_rand_lookup {
    use std::collections::HashMap;

    use mysql::prelude::*;
    use mysql::{Conn, OptsBuilder};

    pub struct MysqlConfig {
        pub host: String,
        pub port: u16,
        pub user: String,
        pub password: String,
        pub database: String,
    }

    /// Bulk-lookup `bdaddr_random` for every BDADDR in `bdaddrs`. Returns a map
    /// from BDADDR (input casing preserved) -> 0/1. Missing BDADDRs are absent
    /// from the map; the caller should default them to 1. Logs a single
    /// warning and returns an empty map on any connection/setup failure.
    pub fn fetch_map(bdaddrs: &[String], cfg: &MysqlConfig, chunk_size: usize) -> HashMap<String, i64> {
        if bdaddrs.is_empty() {
            return HashMap::new();
        }
        // Connect.
        let opts = OptsBuilder::new()
            .ip_or_hostname(Some(&cfg.host))
            .tcp_port(cfg.port)
            .user(Some(&cfg.user))
            .pass(Some(&cfg.password))
            .db_name(Some(&cfg.database));
        let mut conn = match Conn::new(opts) {
            Ok(c) => c,
            Err(e) => {
                eprintln!(
                    "warning: MySQL connect to {}@{}:{}/{} failed ({e}); falling back to bdaddr_rand=1 for all BLE rows.",
                    cfg.user, cfg.host, cfg.port, cfg.database
                );
                return HashMap::new();
            }
        };

        // Discover tables in the current database that have a bdaddr_random column.
        let tables: Vec<String> = match conn.query(
            "SELECT table_name FROM information_schema.columns \
             WHERE table_schema = DATABASE() AND column_name = 'bdaddr_random'",
        ) {
            Ok(v) => v,
            Err(e) => {
                eprintln!("warning: MySQL information_schema query failed: {e}; falling back to bdaddr_rand=1.");
                return HashMap::new();
            }
        };
        if tables.is_empty() {
            eprintln!("warning: no bdaddr_random-bearing tables in DB {}; falling back to bdaddr_rand=1.", cfg.database);
            return HashMap::new();
        }

        // counts: bdaddr -> [n_public, n_random]
        let mut counts: HashMap<String, [u32; 2]> = HashMap::with_capacity(bdaddrs.len());

        // De-dup input (Python does the same with `list({...})`).
        let unique: Vec<&String> = {
            let mut seen: std::collections::HashSet<&str> = std::collections::HashSet::new();
            bdaddrs.iter().filter(|b| seen.insert(b.as_str())).collect()
        };

        for chunk in unique.chunks(chunk_size) {
            // Each subquery: (SELECT bdaddr, bdaddr_random FROM <table> WHERE bdaddr IN (?,?,...))
            let placeholders = std::iter::repeat("?")
                .take(chunk.len())
                .collect::<Vec<_>>()
                .join(",");
            let subqueries: Vec<String> = tables
                .iter()
                .map(|t| {
                    format!(
                        "(SELECT bdaddr, bdaddr_random FROM `{}` WHERE bdaddr IN ({}))",
                        t, placeholders
                    )
                })
                .collect();
            let query = subqueries.join(" UNION ALL ");

            // Build params: chunk repeated once per table.
            let mut params: Vec<mysql::Value> = Vec::with_capacity(chunk.len() * tables.len());
            for _ in 0..tables.len() {
                for b in chunk {
                    params.push(mysql::Value::from(b.as_str()));
                }
            }

            // Run.
            let rows: Vec<(String, i64)> = match conn.exec(query, params) {
                Ok(v) => v,
                Err(e) => {
                    eprintln!("warning: MySQL UNION-ALL chunk failed: {e}; skipping {} BDADDRs.", chunk.len());
                    continue;
                }
            };

            for (bdaddr, bdaddr_random) in rows {
                let entry = counts.entry(bdaddr).or_insert([0, 0]);
                if (0..=1).contains(&bdaddr_random) {
                    entry[bdaddr_random as usize] = entry[bdaddr_random as usize].saturating_add(1);
                }
            }
        }

        // Majority vote, tie → 1 (matches Python).
        let mut out = HashMap::with_capacity(counts.len());
        for (bdaddr, c) in counts {
            let v = if c[0] > c[1] { 0 } else { 1 };
            out.insert(bdaddr, v);
        }
        out
    }
}

#[derive(Debug, Clone)]
struct GpsBoundingBox {
    lower_lat: f64,
    upper_lat: f64,
    lower_lon: f64,
    upper_lon: f64,
}

fn parse_latlon(s: &str) -> Result<(f64, f64), String> {
    let stripped = s.trim().trim_start_matches('(').trim_end_matches(')');
    let parts: Vec<&str> = stripped.split(',').map(|p| p.trim()).collect();
    if parts.len() != 2 {
        return Err(format!("expected (lat,lon), got {s:?}"));
    }
    let lat: f64 = parts[0].parse().map_err(|e| format!("lat: {e}"))?;
    let lon: f64 = parts[1].parse().map_err(|e| format!("lon: {e}"))?;
    Ok((lat, lon))
}

fn build_bbox(ul: &str, lr: &str) -> Result<GpsBoundingBox, String> {
    let (ul_lat, ul_lon) = parse_latlon(ul)?;
    let (lr_lat, lr_lon) = parse_latlon(lr)?;
    Ok(GpsBoundingBox {
        lower_lat: ul_lat.min(lr_lat),
        upper_lat: ul_lat.max(lr_lat),
        lower_lon: ul_lon.min(lr_lon),
        upper_lon: ul_lon.max(lr_lon),
    })
}

#[derive(Debug)]
struct NetworkRow {
    bssid: String,
    ssid: String,
    lasttime: i64,
    lastlat: f64,
    lastlon: f64,
    type_: String,
    bestlat: f64,
    bestlon: f64,
}

#[derive(Debug, Clone)]
struct LocationRow {
    level: i64,
    lat: f64,
    lon: f64,
    time: i64,
}

fn str_to_hex(s: &str) -> String {
    let mut out = String::with_capacity(s.len() * 2);
    for b in s.as_bytes() {
        out.push_str(&format!("{:02x}", b));
    }
    out
}

fn export_gps(bt: &mut Btides, bdaddr: &str, rand: i64, time_ms: i64, lat: f64, lon: f64, rssi: Option<i64>) {
    let mut time_obj = Map::new();
    time_obj.insert("unix_time_milli".into(), Value::from(time_ms));
    let mut record = Map::new();
    record.insert("time".into(), Value::Object(time_obj));
    record.insert(
        "lat".into(),
        Value::from(serde_json::Number::from_f64(lat).expect("lat finite")),
    );
    record.insert(
        "lon".into(),
        Value::from(serde_json::Number::from_f64(lon).expect("lon finite")),
    );
    if let Some(r) = rssi {
        record.insert("rssi".into(), Value::from(r));
    }
    bt.insert_single_t1(bdaddr, rand, Value::Object(record), "GPSArray");
}

fn export_remote_name(bt: &mut Btides, bdaddr: &str, rand: i64, name: &str) {
    let mut obj = Map::new();
    obj.insert("event_code".into(), Value::from(7));
    obj.insert("status".into(), Value::from(0));
    obj.insert("remote_name_hex_str".into(), Value::String(str_to_hex(name)));
    if bt.verbose_btides {
        obj.insert("utf8_name".into(), Value::String(printable_utf8(name)));
    }
    bt.insert_single_t1(bdaddr, rand, Value::Object(obj), "HCIArray");
}

fn printable_utf8(s: &str) -> String {
    s.chars().filter(|c| !c.is_control()).collect()
}

#[derive(Parser, Debug)]
#[command(version, about = "Convert a WiGLE backup SQLite into a BTIDES JSON file (GPS + name).")]
struct Cli {
    /// Path to the WiGLE backup SQLite database.
    #[arg(long)]
    input: PathBuf,
    #[arg(long)]
    output: PathBuf,
    #[arg(long)]
    schema_dir: PathBuf,
    #[arg(long = "verbose-BTIDES", default_value_t = false)]
    verbose_btides: bool,
    /// Emit a GPS record for every `location` row associated with each device,
    /// not just the trilaterated `best` lat/lon from `network`. Slower.
    #[arg(long = "get-all-GPS", default_value_t = false)]
    get_all_gps: bool,
    /// Optional bounding box to exclude. Both corners must be given. Format `(lat,lon)`.
    #[arg(long = "GPS-exclude-upper-left")]
    gps_exclude_upper_left: Option<String>,
    #[arg(long = "GPS-exclude-lower-right")]
    gps_exclude_lower_right: Option<String>,
    /// Skip the first N `network` rows. Mirrors the Python --offset.
    #[arg(long, default_value_t = 0)]
    offset: i64,
    /// Process at most N `network` rows.
    #[arg(long)]
    limit: Option<i64>,
    #[arg(long, default_value_t = false)]
    no_validate: bool,
    #[arg(long, default_value_t = false)]
    quiet: bool,

    // ---- MySQL bdaddr_random lookup ----
    /// Skip the MySQL bdaddr_random lookup; default all BLE rows to bdaddr_rand=1.
    /// Useful if you don't have the Blue2thprinting bt2/bttest MySQL DB available.
    #[arg(long, default_value_t = false)]
    no_mysql_lookup: bool,
    /// Use the `bttest` database instead of `bt2` for the bdaddr_random lookup.
    #[arg(long = "use-test-db", default_value_t = false)]
    use_test_db: bool,
    #[arg(long, default_value = "localhost")]
    mysql_host: String,
    #[arg(long, default_value_t = 3306)]
    mysql_port: u16,
    #[arg(long, default_value = "user")]
    mysql_user: String,
    #[arg(long, default_value = "a")]
    mysql_password: String,
    /// Chunk size for the bulk lookup (BDADDRs per UNION-ALL roundtrip).
    /// Defaults to 1000 (matches Python).
    #[arg(long, default_value_t = 1000)]
    mysql_chunk_size: usize,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();

    let bbox = match (&cli.gps_exclude_upper_left, &cli.gps_exclude_lower_right) {
        (Some(ul), Some(lr)) => Some(build_bbox(ul, lr)?),
        (None, None) => None,
        _ => {
            eprintln!("Error: --GPS-exclude-upper-left and --GPS-exclude-lower-right must both be given.");
            std::process::exit(1);
        }
    };

    if !cli.input.exists() {
        eprintln!("Error: input file {} does not exist.", cli.input.display());
        std::process::exit(1);
    }

    let conn = Connection::open_with_flags(
        &cli.input,
        rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY | rusqlite::OpenFlags::SQLITE_OPEN_URI,
    )?;

    let mut query = String::from(
        "SELECT bssid, ssid, lasttime, lastlat, lastlon, type, bestlat, bestlon \
         FROM network WHERE (type = 'B' or type = 'E')",
    );
    let mut params: Vec<rusqlite::types::Value> = Vec::new();
    if let Some(b) = &bbox {
        query.push_str(" AND (bestlat NOT BETWEEN ? AND ?) AND (bestlon NOT BETWEEN ? AND ?)");
        params.push(b.lower_lat.into());
        params.push(b.upper_lat.into());
        params.push(b.lower_lon.into());
        params.push(b.upper_lon.into());
    }
    if let Some(lim) = cli.limit {
        query.push_str(" LIMIT ?");
        params.push(lim.into());
    }
    if cli.offset > 0 {
        if cli.limit.is_none() {
            query.push_str(" LIMIT -1");
        }
        query.push_str(" OFFSET ?");
        params.push(cli.offset.into());
    }

    if !cli.quiet {
        println!("Reading Bluetooth entries from WiGLE SQLite database.");
    }

    let mut stmt = conn.prepare(&query)?;
    let network_rows: Vec<NetworkRow> = stmt
        .query_map(params_from_iter(params.iter()), |row| {
            Ok(NetworkRow {
                bssid: row.get(0)?,
                ssid: row.get::<_, Option<String>>(1)?.unwrap_or_default(),
                lasttime: row.get(2)?,
                lastlat: row.get(3)?,
                lastlon: row.get(4)?,
                type_: row.get(5)?,
                bestlat: row.get(6)?,
                bestlon: row.get(7)?,
            })
        })?
        .collect::<Result<Vec<_>, _>>()?;
    drop(stmt);

    // BLE bdaddr_random lookup. Collect every type='E' BDADDR (lowercased to
    // match how we'll emit them) and ask MySQL in bulk. Empty map means we'll
    // fall back to bdaddr_rand=1 for everything (same as Python's tie/miss case).
    let bdaddr_rand_map: HashMap<String, i64> = if cli.no_mysql_lookup {
        if !cli.quiet {
            println!("Skipping MySQL bdaddr_random lookup (--no-mysql-lookup); all BLE rows -> bdaddr_rand=1.");
        }
        HashMap::new()
    } else {
        let ble_bdaddrs: Vec<String> = network_rows
            .iter()
            .filter(|r| r.type_ == "E")
            .map(|r| r.bssid.to_lowercase())
            .collect();
        if !cli.quiet {
            let n_unique = ble_bdaddrs.iter().collect::<std::collections::HashSet<_>>().len();
            println!(
                "Looking up bdaddr_random for {} unique BLE BDADDRs in MySQL ({}/{}).",
                n_unique,
                if cli.use_test_db { "bttest" } else { "bt2" },
                cli.mysql_host
            );
        }
        let cfg = bdaddr_rand_lookup::MysqlConfig {
            host: cli.mysql_host.clone(),
            port: cli.mysql_port,
            user: cli.mysql_user.clone(),
            password: cli.mysql_password.clone(),
            database: if cli.use_test_db {
                "bttest".to_string()
            } else {
                "bt2".to_string()
            },
        };
        bdaddr_rand_lookup::fetch_map(&ble_bdaddrs, &cfg, cli.mysql_chunk_size)
    };
    if !cli.quiet && !cli.no_mysql_lookup {
        println!(
            "MySQL returned bdaddr_random for {} BLE BDADDRs.",
            bdaddr_rand_map.len()
        );
    }

    if !cli.quiet {
        println!(
            "Loading WiGLE location table into memory ({} network rows to process).",
            network_rows.len()
        );
    }

    let mut location_by_bssid: HashMap<String, Vec<LocationRow>> = HashMap::new();
    {
        let mut stmt = conn
            .prepare("SELECT bssid, level, lat, lon, time FROM location")?;
        let rows = stmt.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                LocationRow {
                    level: row.get(1)?,
                    lat: row.get(2)?,
                    lon: row.get(3)?,
                    time: row.get(4)?,
                },
            ))
        })?;
        for r in rows {
            let (bssid, loc) = r?;
            location_by_bssid.entry(bssid).or_default().push(loc);
        }
    }

    let mut bt = Btides::new();
    bt.set_verbose(cli.verbose_btides);
    let total = network_rows.len();
    let step = (total / 100).max(1);
    for (i, row) in network_rows.iter().enumerate() {
        if !cli.quiet && i % step == 0 {
            println!(
                "Processed {} out of {} records ({}%)",
                i,
                total,
                ((i as f64) / (total as f64) * 100.0) as u32
            );
        }
        if !row.lastlat.is_finite()
            || !row.lastlon.is_finite()
            || !row.bestlat.is_finite()
            || !row.bestlon.is_finite()
        {
            continue;
        }
        let bdaddr = row.bssid.to_lowercase();
        let bdaddr_rand: i64 = match row.type_.as_str() {
            "B" => 0,
            // BLE: map from MySQL lookup if available, else default to 1 (matches Python).
            "E" => *bdaddr_rand_map.get(&bdaddr).unwrap_or(&1),
            _ => continue,
        };

        let (lat, lon) = if row.bestlat != 0.0 || row.bestlon != 0.0 {
            (row.bestlat, row.bestlon)
        } else if row.lastlat != 0.0 || row.lastlon != 0.0 {
            (row.lastlat, row.lastlon)
        } else {
            continue;
        };
        if !(-90.0..=90.0).contains(&lat) || !(-180.0..=180.0).contains(&lon) {
            continue;
        }

        let mut best_rssi: Option<i64> = None;
        if let Some(locs) = location_by_bssid.get(&row.bssid) {
            for loc in locs {
                if loc.lat == lat && loc.lon == lon {
                    if best_rssi.map(|r| loc.level > r).unwrap_or(true) {
                        best_rssi = Some(loc.level);
                    }
                }
            }
        }

        export_gps(&mut bt, &bdaddr, bdaddr_rand, row.lasttime, lat, lon, best_rssi);

        if !row.ssid.is_empty() {
            // Python's BTIDES_export_HCI_Name_Response hardcodes random=0 for the
            // HCI_Remote_Name_Request_Complete record, since that event is a BR/EDR
            // concept. Mirror that here even for type='E' BLE rows — keeps the
            // entry counts and dual-rand split identical to the Python tool.
            export_remote_name(&mut bt, &bdaddr, 0, &row.ssid);
        }

        if cli.get_all_gps {
            if let Some(locs) = location_by_bssid.get(&row.bssid) {
                for loc in locs {
                    if !(-90.0..=90.0).contains(&loc.lat) || !(-180.0..=180.0).contains(&loc.lon) {
                        continue;
                    }
                    export_gps(
                        &mut bt,
                        &bdaddr,
                        bdaddr_rand,
                        loc.time,
                        loc.lat,
                        loc.lon,
                        Some(loc.level),
                    );
                }
            }
        }
    }

    if !cli.quiet {
        println!("Writing BTIDES data to {}", cli.output.display());
    }
    if cli.no_validate {
        std::fs::write(&cli.output, bt.to_json_bytes()?)?;
    } else {
        bt.write_btides(&cli.output, &cli.schema_dir)?;
    }
    if !cli.quiet {
        println!("Export completed with no errors.");
    }
    Ok(())
}
