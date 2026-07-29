//! Native Rust query engine for BTPL v4.
//!
//! The legacy-query operation returns reconstructed BTIDES JSON through the
//! Tell_Me_Everything subprocess. The native-query operation is a normalized, lossless
//! view of the existing MySQL schema: select candidate devices in a handful
//! of batched queries, then fetch all rows for those devices once per table.
//! This removes the legacy N-devices × N-tables round-trip explosion without
//! migrating or duplicating the production database.

use btidalpool_proto::{NativeQueryResult, QueryParams};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum NativeQueryError {
    #[error("query engine produced no records")]
    Empty,
    #[error("unsupported native-query filter: {0}")]
    Unsupported(String),
    #[error("bad query: {0}")]
    BadRequest(String),
    #[error("backend error: {0}")]
    Backend(String),
}

pub trait NativeQueryEngine: Send + Sync {
    fn run(
        &self,
        params: &QueryParams,
        max_devices: u32,
        max_rows: u64,
        use_test_db: bool,
    ) -> Result<NativeQueryResult, NativeQueryError>;
}

pub struct UnavailableNativeQueryEngine;

impl NativeQueryEngine for UnavailableNativeQueryEngine {
    fn run(
        &self,
        _params: &QueryParams,
        _max_devices: u32,
        _max_rows: u64,
        _use_test_db: bool,
    ) -> Result<NativeQueryResult, NativeQueryError> {
        Err(NativeQueryError::Backend(
            "server was built without the sql-ingest/native-query feature".into(),
        ))
    }
}

/// Deterministic in-memory engine used by handler/HTTP tests.
pub struct StubNativeQueryEngine {
    result: Option<NativeQueryResult>,
}

impl StubNativeQueryEngine {
    pub fn ok(result: NativeQueryResult) -> Self {
        Self {
            result: Some(result),
        }
    }

    pub fn empty() -> Self {
        Self { result: None }
    }
}

impl NativeQueryEngine for StubNativeQueryEngine {
    fn run(
        &self,
        _params: &QueryParams,
        _max_devices: u32,
        _max_rows: u64,
        _use_test_db: bool,
    ) -> Result<NativeQueryResult, NativeQueryError> {
        self.result.clone().ok_or(NativeQueryError::Empty)
    }
}

#[cfg(feature = "sql-ingest")]
mod mysql_engine {
    use std::collections::{BTreeMap, BTreeSet};

    use btidalpool_proto::{DbValue, NativeDevice, NativeQueryResult, NativeTable, QueryParams};
    use mysql::prelude::Queryable;
    use mysql::{Opts, OptsBuilder, Params, Pool, Row, Value};
    use regex::Regex;

    use super::{NativeQueryEngine, NativeQueryError};

    #[derive(Clone, Debug)]
    struct TableSpec {
        name: String,
        columns: Vec<String>,
        bdaddr_index: usize,
        has_bdaddr_random: bool,
    }

    pub struct MysqlNativeQueryEngine {
        production: Pool,
        test: Pool,
        production_tables: Vec<TableSpec>,
        test_tables: Vec<TableSpec>,
    }

    impl MysqlNativeQueryEngine {
        pub fn connect(host: &str, user: &str, pass: &str) -> Result<Self, NativeQueryError> {
            let production = build_pool(host, user, pass, "bt2")?;
            let test = build_pool(host, user, pass, "bttest")?;
            let production_tables = discover_tables(&production, "bt2")?;
            let test_tables = discover_tables(&test, "bttest")?;
            if production_tables.is_empty() || test_tables.is_empty() {
                return Err(NativeQueryError::Backend(
                    "no tables containing a bdaddr column were discovered".into(),
                ));
            }
            Ok(Self {
                production,
                test,
                production_tables,
                test_tables,
            })
        }
    }

    impl NativeQueryEngine for MysqlNativeQueryEngine {
        fn run(
            &self,
            params: &QueryParams,
            max_devices: u32,
            max_rows: u64,
            use_test_db: bool,
        ) -> Result<NativeQueryResult, NativeQueryError> {
            validate_supported(params)?;
            let pool = if use_test_db {
                &self.test
            } else {
                &self.production
            };
            let tables = if use_test_db {
                &self.test_tables
            } else {
                &self.production_tables
            };
            let mut conn = pool
                .get_conn()
                .map_err(|e| NativeQueryError::Backend(e.to_string()))?;

            let max_devices = max_devices.max(1) as usize;
            // A broad `.*` can match millions of addresses. We only return
            // max_devices, but retain headroom for NOT/require filters.
            let candidate_limit = max_devices.saturating_mul(100).clamp(1_000, 100_000);
            let mut candidates =
                collect_positive_candidates(&mut conn, tables, params, candidate_limit)?;
            if candidates.is_empty() {
                return Err(NativeQueryError::Empty);
            }

            apply_negative_filters(&mut conn, tables, params, &mut candidates)?;
            apply_requirements(&mut conn, params, &mut candidates)?;
            if candidates.is_empty() {
                return Err(NativeQueryError::Empty);
            }

            let selected: Vec<String> = candidates.into_iter().take(max_devices).collect();
            fetch_rows(&mut conn, tables, &selected, max_rows.max(1))
        }
    }

    fn build_pool(
        host: &str,
        user: &str,
        pass: &str,
        database: &str,
    ) -> Result<Pool, NativeQueryError> {
        let opts: Opts = OptsBuilder::new()
            .ip_or_hostname(Some(host))
            .user(Some(user))
            .pass(Some(pass))
            .db_name(Some(database))
            .into();
        Pool::new(opts).map_err(|e| NativeQueryError::Backend(e.to_string()))
    }

    fn discover_tables(pool: &Pool, schema: &str) -> Result<Vec<TableSpec>, NativeQueryError> {
        let mut conn = pool
            .get_conn()
            .map_err(|e| NativeQueryError::Backend(e.to_string()))?;
        let rows: Vec<(String, String)> = conn
            .exec(
                "SELECT c.TABLE_NAME, c.COLUMN_NAME \
                 FROM INFORMATION_SCHEMA.COLUMNS c \
                 JOIN INFORMATION_SCHEMA.TABLES t \
                   ON t.TABLE_SCHEMA = c.TABLE_SCHEMA \
                  AND t.TABLE_NAME = c.TABLE_NAME \
                 WHERE c.TABLE_SCHEMA = ? AND t.TABLE_TYPE = 'BASE TABLE' \
                 ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION",
                (schema,),
            )
            .map_err(|e| NativeQueryError::Backend(e.to_string()))?;
        let mut grouped: BTreeMap<String, Vec<String>> = BTreeMap::new();
        for (table, column) in rows {
            grouped.entry(table).or_default().push(column);
        }
        Ok(grouped
            .into_iter()
            .filter_map(|(name, columns)| {
                if !safe_identifier(&name) || columns.iter().any(|c| !safe_identifier(c)) {
                    log::warn!("native query skipped table with unsafe SQL identifier");
                    return None;
                }
                let bdaddr_index = columns.iter().position(|c| c == "bdaddr")?;
                let has_bdaddr_random = columns.iter().any(|c| c == "bdaddr_random");
                Some(TableSpec {
                    name,
                    columns,
                    bdaddr_index,
                    has_bdaddr_random,
                })
            })
            .collect())
    }

    fn validate_supported(params: &QueryParams) -> Result<(), NativeQueryError> {
        if params.company_regex.as_ref().is_some_and(|v| !v.is_empty())
            || params
                .NOT_company_regex
                .as_ref()
                .is_some_and(|v| !v.is_empty())
        {
            return Err(NativeQueryError::Unsupported(
                "company_regex requires TME's external assigned-number and CLUES metadata; use legacy_query"
                    .into(),
            ));
        }
        if params.GPS_exclude_upper_left.is_some() || params.GPS_exclude_lower_right.is_some() {
            return Err(NativeQueryError::Unsupported(
                "GPS exclusion boxes are currently available through legacy_query".into(),
            ));
        }
        Ok(())
    }

    fn collect_positive_candidates(
        conn: &mut mysql::PooledConn,
        tables: &[TableSpec],
        params: &QueryParams,
        cap: usize,
    ) -> Result<BTreeSet<String>, NativeQueryError> {
        let mut out = BTreeSet::new();
        if let Some(address) = params.bdaddr.as_ref().filter(|s| !s.is_empty()) {
            out.insert(address.to_ascii_lowercase());
        }
        for pattern in params.bdaddr_regex.iter().flatten() {
            collect_bdaddr_regex(conn, tables, pattern, cap, &mut out)?;
            if out.len() >= cap {
                break;
            }
        }
        for pattern in params.name_regex.iter().flatten() {
            collect_name_regex(conn, pattern, &mut out)?;
        }
        for pattern in params.UUID_regex.iter().flatten() {
            collect_uuid_regex(conn, pattern, cap, &mut out)?;
        }
        for pattern in params.MSD_regex.iter().flatten() {
            for (table, column) in [
                ("EIR_bdaddr_to_MSD", "manufacturer_specific_data"),
                ("LE_bdaddr_to_MSD", "manufacturer_specific_data"),
            ] {
                collect_sql_regex(conn, table, column, pattern, cap, &mut out)?;
            }
        }
        if let Some(spec) = params.LL_VERSION_IND.as_ref().filter(|s| !s.is_empty()) {
            collect_version(conn, "LL_VERSION_IND", "ll", spec, cap, &mut out)?;
        }
        if let Some(spec) = params.LMP_VERSION_RES.as_ref().filter(|s| !s.is_empty()) {
            collect_version(conn, "LMP_VERSION_RES", "lmp", spec, cap, &mut out)?;
        }
        if out.len() > cap {
            out = out.into_iter().take(cap).collect();
        }
        Ok(out)
    }

    fn collect_bdaddr_regex(
        conn: &mut mysql::PooledConn,
        tables: &[TableSpec],
        pattern: &str,
        cap: usize,
        out: &mut BTreeSet<String>,
    ) -> Result<(), NativeQueryError> {
        let pattern = normalize_glob(pattern);
        Regex::new(&pattern)
            .map_err(|e| NativeQueryError::BadRequest(format!("invalid bdaddr regex: {e}")))?;
        for table in tables {
            if out.len() >= cap {
                break;
            }
            collect_sql_regex(conn, &table.name, "bdaddr", &pattern, cap - out.len(), out)?;
        }
        Ok(())
    }

    fn collect_name_regex(
        conn: &mut mysql::PooledConn,
        pattern: &str,
        out: &mut BTreeSet<String>,
    ) -> Result<(), NativeQueryError> {
        let re = Regex::new(pattern)
            .map_err(|e| NativeQueryError::BadRequest(format!("invalid name regex: {e}")))?;
        for table in [
            "EIR_bdaddr_to_name",
            "HCI_bdaddr_to_name",
            "LE_bdaddr_to_name",
        ] {
            let sql = format!("SELECT bdaddr, name_hex_str FROM `{table}`");
            let rows: Vec<(String, String)> = conn
                .query(sql)
                .map_err(|e| NativeQueryError::Backend(e.to_string()))?;
            for (address, hex_name) in rows {
                if let Ok(bytes) = hex::decode(hex_name) {
                    if re.is_match(&String::from_utf8_lossy(&bytes)) {
                        out.insert(address.to_ascii_lowercase());
                    }
                }
            }
        }
        let rows: Vec<(String, Vec<u8>)> = conn
            .query(
                "SELECT cv.bdaddr, cv.byte_values \
                 FROM GATT_characteristics_values cv \
                 JOIN GATT_characteristics c \
                   ON cv.char_value_handle = c.char_value_handle \
                  AND cv.bdaddr = c.bdaddr \
                  AND cv.bdaddr_random = c.bdaddr_random \
                 WHERE LOWER(c.UUID) = '2a00'",
            )
            .map_err(|e| NativeQueryError::Backend(e.to_string()))?;
        for (address, bytes) in rows {
            if re.is_match(&String::from_utf8_lossy(&bytes)) {
                out.insert(address.to_ascii_lowercase());
            }
        }
        Ok(())
    }

    fn collect_uuid_regex(
        conn: &mut mysql::PooledConn,
        pattern: &str,
        cap: usize,
        out: &mut BTreeSet<String>,
    ) -> Result<(), NativeQueryError> {
        let pattern = pattern.replace('-', "");
        for (table, column) in [
            ("EIR_bdaddr_to_UUID128s", "str_UUID128s"),
            ("LE_bdaddr_to_UUID128s_list", "str_UUID128s"),
            ("LE_bdaddr_to_UUID128_service_solicit", "str_UUID128s"),
            ("LE_bdaddr_to_UUID128_service_data", "UUID128_hex_str"),
            ("EIR_bdaddr_to_UUID32s", "str_UUID32s"),
            ("LE_bdaddr_to_UUID32s_list", "str_UUID32s"),
            ("LE_bdaddr_to_UUID32_service_solicit", "str_UUID32s"),
            ("LE_bdaddr_to_UUID32_service_data", "UUID32_hex_str"),
            ("EIR_bdaddr_to_UUID16s", "str_UUID16s"),
            ("LE_bdaddr_to_UUID16s_list", "str_UUID16s"),
            ("LE_bdaddr_to_UUID16_service_solicit", "str_UUID16s"),
            ("LE_bdaddr_to_UUID16_service_data", "UUID16_hex_str"),
            ("GATT_services", "UUID"),
            ("GATT_characteristics", "UUID"),
            ("GATT_attribute_handles", "UUID"),
        ] {
            collect_sql_regex(conn, table, column, &pattern, cap, out)?;
        }
        Ok(())
    }

    fn collect_sql_regex(
        conn: &mut mysql::PooledConn,
        table: &str,
        column: &str,
        pattern: &str,
        cap: usize,
        out: &mut BTreeSet<String>,
    ) -> Result<(), NativeQueryError> {
        if cap == 0 {
            return Ok(());
        }
        let sql =
            format!("SELECT DISTINCT bdaddr FROM `{table}` WHERE `{column}` REGEXP ? LIMIT {cap}");
        let rows: Vec<String> = conn
            .exec(sql, (pattern,))
            .map_err(|e| NativeQueryError::Backend(e.to_string()))?;
        out.extend(rows.into_iter().map(|s| s.to_ascii_lowercase()));
        Ok(())
    }

    fn collect_version(
        conn: &mut mysql::PooledConn,
        table: &str,
        prefix: &str,
        spec: &str,
        cap: usize,
        out: &mut BTreeSet<String>,
    ) -> Result<(), NativeQueryError> {
        let parts: Vec<&str> = spec.split(':').collect();
        if parts.len() != 3 {
            return Err(NativeQueryError::BadRequest(format!(
                "{table} must be AA:BBBB:CCCC"
            )));
        }
        let version = u8::from_str_radix(parts[0], 16)
            .map_err(|_| NativeQueryError::BadRequest(format!("invalid {table} version")))?;
        let company = u16::from_str_radix(parts[1], 16)
            .map_err(|_| NativeQueryError::BadRequest(format!("invalid {table} company ID")))?;
        let subversion = u16::from_str_radix(parts[2], 16)
            .map_err(|_| NativeQueryError::BadRequest(format!("invalid {table} subversion")))?;
        let sql = format!(
            "SELECT DISTINCT bdaddr FROM `{table}` \
             WHERE `{prefix}_version` = ? AND device_BT_CID = ? \
               AND `{prefix}_sub_version` = ? LIMIT {cap}"
        );
        let rows: Vec<String> = conn
            .exec(sql, (version, company, subversion))
            .map_err(|e| NativeQueryError::Backend(e.to_string()))?;
        out.extend(rows.into_iter().map(|s| s.to_ascii_lowercase()));
        Ok(())
    }

    fn apply_negative_filters(
        conn: &mut mysql::PooledConn,
        tables: &[TableSpec],
        params: &QueryParams,
        candidates: &mut BTreeSet<String>,
    ) -> Result<(), NativeQueryError> {
        if let Some(addresses) = &params.NOT_bdaddr {
            for address in addresses {
                candidates.remove(&address.to_ascii_lowercase());
            }
        }
        for pattern in params.NOT_bdaddr_regex.iter().flatten() {
            let re = Regex::new(&normalize_glob(pattern)).map_err(|e| {
                NativeQueryError::BadRequest(format!("invalid NOT bdaddr regex: {e}"))
            })?;
            candidates.retain(|address| !re.is_match(address));
        }
        for pattern in params.NOT_name_regex.iter().flatten() {
            let mut matched = BTreeSet::new();
            collect_name_regex(conn, pattern, &mut matched)?;
            candidates.retain(|address| !matched.contains(address));
        }
        for pattern in params.NOT_UUID_regex.iter().flatten() {
            let mut matched = BTreeSet::new();
            collect_uuid_regex(conn, pattern, candidates.len().max(1), &mut matched)?;
            candidates.retain(|address| !matched.contains(address));
        }
        // Keep `tables` in the signature because bdaddr exclusions operate
        // over the discovered catalog; this also makes additions symmetric.
        let _ = tables;
        Ok(())
    }

    fn apply_requirements(
        conn: &mut mysql::PooledConn,
        params: &QueryParams,
        candidates: &mut BTreeSet<String>,
    ) -> Result<(), NativeQueryError> {
        if params.require_GPS {
            retain_present(conn, candidates, &[("bdaddr_to_GPS", None)])?;
        }
        if params.require_GATT_any {
            retain_present(
                conn,
                candidates,
                &[
                    ("GATT_services", None),
                    ("GATT_attribute_handles", None),
                    ("GATT_characteristics", None),
                    ("GATT_characteristics_values", None),
                ],
            )?;
        }
        if params.require_GATT_values {
            retain_present(conn, candidates, &[("GATT_characteristics_values", None)])?;
        }
        if params.require_SMP {
            retain_present(conn, candidates, &[("SMP_Pairing_Req_Res", None)])?;
        }
        if params.require_SMP_legacy_pairing {
            retain_present(
                conn,
                candidates,
                &[("SMP_Pairing_Req_Res", Some("(auth_req & 8) = 0"))],
            )?;
        }
        if params.require_SDP {
            retain_present(conn, candidates, &[("SDP_Common", None)])?;
        }
        if params.require_LL_VERSION_IND {
            retain_present(conn, candidates, &[("LL_VERSION_IND", None)])?;
        }
        if params.require_LMP_VERSION_RES {
            retain_present(conn, candidates, &[("LMP_VERSION_RES", None)])?;
        }
        Ok(())
    }

    fn retain_present(
        conn: &mut mysql::PooledConn,
        candidates: &mut BTreeSet<String>,
        sources: &[(&str, Option<&str>)],
    ) -> Result<(), NativeQueryError> {
        if candidates.is_empty() {
            return Ok(());
        }
        let values: Vec<Value> = candidates
            .iter()
            .cloned()
            .map(|s| Value::Bytes(s.into_bytes()))
            .collect();
        let placeholders = vec!["?"; values.len()].join(",");
        let mut found = BTreeSet::new();
        for (table, predicate) in sources {
            let extra = predicate.map(|p| format!(" AND {p}")).unwrap_or_default();
            let sql = format!(
                "SELECT DISTINCT bdaddr FROM `{table}` \
                 WHERE bdaddr IN ({placeholders}){extra}"
            );
            let rows: Vec<String> = conn
                .exec(sql, Params::Positional(values.clone()))
                .map_err(|e| NativeQueryError::Backend(e.to_string()))?;
            found.extend(rows.into_iter().map(|s| s.to_ascii_lowercase()));
        }
        candidates.retain(|address| found.contains(address));
        Ok(())
    }

    fn fetch_rows(
        conn: &mut mysql::PooledConn,
        tables: &[TableSpec],
        addresses: &[String],
        row_limit: u64,
    ) -> Result<NativeQueryResult, NativeQueryError> {
        let mut devices: BTreeMap<String, NativeDevice> = addresses
            .iter()
            .map(|address| {
                (
                    address.clone(),
                    NativeDevice {
                        bdaddr: address.clone(),
                        tables: BTreeMap::new(),
                    },
                )
            })
            .collect();
        let params: Vec<Value> = addresses
            .iter()
            .cloned()
            .map(|s| Value::Bytes(s.into_bytes()))
            .collect();
        let placeholders = vec!["?"; params.len()].join(",");
        let mut total_rows = 0u64;
        let mut globally_truncated = false;

        for table in tables {
            let remaining = row_limit.saturating_sub(total_rows);
            if remaining == 0 {
                globally_truncated = true;
                break;
            }
            let query_limit = remaining.saturating_add(1);
            let random_hint = if table.has_bdaddr_random {
                " AND bdaddr_random IN (0, 1)"
            } else {
                ""
            };
            let sql = format!(
                "SELECT * FROM `{}` WHERE bdaddr IN ({placeholders}){random_hint} \
                 ORDER BY bdaddr LIMIT {query_limit}",
                table.name
            );
            let mut rows: Vec<Row> = conn
                .exec(sql, Params::Positional(params.clone()))
                .map_err(|e| NativeQueryError::Backend(e.to_string()))?;
            let table_truncated = rows.len() as u64 > remaining;
            if table_truncated {
                rows.truncate(remaining as usize);
                globally_truncated = true;
            }
            for row in rows {
                let address = value_as_address(
                    row.as_ref(table.bdaddr_index)
                        .ok_or_else(|| NativeQueryError::Backend("missing bdaddr cell".into()))?,
                )?;
                let values = row.unwrap().into_iter().map(db_value).collect();
                let device = devices
                    .entry(address.clone())
                    .or_insert_with(|| NativeDevice {
                        bdaddr: address,
                        tables: BTreeMap::new(),
                    });
                let output =
                    device
                        .tables
                        .entry(table.name.clone())
                        .or_insert_with(|| NativeTable {
                            columns: table.columns.clone(),
                            rows: Vec::new(),
                            truncated: false,
                        });
                output.rows.push(values);
                output.truncated |= table_truncated;
                total_rows += 1;
            }
            if table_truncated {
                break;
            }
        }
        let devices: Vec<NativeDevice> = devices
            .into_values()
            .filter(|device| !device.tables.is_empty())
            .collect();
        if devices.is_empty() {
            return Err(NativeQueryError::Empty);
        }
        Ok(NativeQueryResult {
            devices,
            total_rows,
            row_limit,
            truncated: globally_truncated,
        })
    }

    fn value_as_address(value: &Value) -> Result<String, NativeQueryError> {
        match value {
            Value::Bytes(bytes) => Ok(String::from_utf8_lossy(bytes).to_ascii_lowercase()),
            other => Err(NativeQueryError::Backend(format!(
                "unexpected bdaddr value type: {other:?}"
            ))),
        }
    }

    fn db_value(value: Value) -> DbValue {
        match value {
            Value::NULL => DbValue::Null,
            Value::Bytes(bytes) => DbValue::Bytes(bytes),
            Value::Int(value) => DbValue::Signed(value),
            Value::UInt(value) => DbValue::Unsigned(value),
            Value::Float(value) => DbValue::Float(value as f64),
            Value::Double(value) => DbValue::Float(value),
            Value::Date(year, month, day, hour, minute, second, micros) => DbValue::Date {
                year,
                month,
                day,
                hour,
                minute,
                second,
                micros,
            },
            Value::Time(negative, days, hours, minutes, seconds, micros) => DbValue::Time {
                negative,
                days,
                hours,
                minutes,
                seconds,
                micros,
            },
        }
    }

    fn normalize_glob(pattern: &str) -> String {
        let chars: Vec<char> = pattern.chars().collect();
        let mut out = String::with_capacity(pattern.len() + 4);
        for (index, ch) in chars.iter().enumerate() {
            if *ch == '*' && (index == 0 || chars[index - 1] != '.') {
                out.push_str(".*");
            } else {
                out.push(*ch);
            }
        }
        out
    }

    fn safe_identifier(identifier: &str) -> bool {
        !identifier.is_empty()
            && identifier
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
    }

    pub use MysqlNativeQueryEngine as ExportedMysqlNativeQueryEngine;

    #[cfg(test)]
    mod tests {
        use super::*;

        #[test]
        fn bare_star_is_translated_but_regex_star_is_not() {
            assert_eq!(normalize_glob("*Samsung.*"), ".*Samsung.*");
            assert_eq!(normalize_glob("aa:.*"), "aa:.*");
        }

        #[test]
        fn mysql_values_convert_losslessly() {
            assert_eq!(
                db_value(Value::Bytes(vec![0, 255])),
                DbValue::Bytes(vec![0, 255])
            );
            assert_eq!(db_value(Value::Int(-7)), DbValue::Signed(-7));
            assert_eq!(db_value(Value::UInt(9)), DbValue::Unsigned(9));
        }

        #[test]
        fn only_simple_catalog_identifiers_are_interpolated() {
            assert!(safe_identifier("LE_bdaddr_to_MSD"));
            assert!(!safe_identifier("x` UNION SELECT secret"));
            assert!(!safe_identifier(""));
        }
    }
}

#[cfg(feature = "sql-ingest")]
pub use mysql_engine::ExportedMysqlNativeQueryEngine as MysqlNativeQueryEngine;
