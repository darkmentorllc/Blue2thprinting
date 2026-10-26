//! Shared 24-hour IP bans, compatible with the Python listeners' SQLite file.

use std::net::IpAddr;
use std::path::Path;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use parking_lot::Mutex;
use rusqlite::{params, Connection, OptionalExtension};

const BAN_SECONDS: f64 = 24.0 * 60.0 * 60.0;

pub struct IpBanStore {
    db: Mutex<Connection>,
}

impl IpBanStore {
    pub fn open(path: &Path) -> rusqlite::Result<Self> {
        let db = Connection::open(path)?;
        db.busy_timeout(Duration::from_secs(2))?;
        db.execute(
            "CREATE TABLE IF NOT EXISTS bans (ip TEXT PRIMARY KEY, expires REAL NOT NULL)",
            [],
        )?;
        db.execute("DELETE FROM bans WHERE expires <= ?1", params![now()])?;
        Ok(Self { db: Mutex::new(db) })
    }

    pub fn ban(&self, ip: IpAddr) -> rusqlite::Result<()> {
        let now = now();
        let db = self.db.lock();
        db.execute("DELETE FROM bans WHERE expires <= ?1", params![now])?;
        db.execute(
            "INSERT INTO bans (ip, expires) VALUES (?1, ?2) \
             ON CONFLICT(ip) DO UPDATE SET expires = excluded.expires",
            params![ip.to_string(), now + BAN_SECONDS],
        )?;
        log::warn!("banned {ip} for 24 hours after an invalid BTIDALPOOL request");
        Ok(())
    }

    pub fn is_banned(&self, ip: IpAddr) -> rusqlite::Result<bool> {
        let db = self.db.lock();
        let expires: Option<f64> = db
            .query_row(
                "SELECT expires FROM bans WHERE ip = ?1",
                params![ip.to_string()],
                |row| row.get(0),
            )
            .optional()?;
        match expires {
            Some(expires) if expires <= now() => {
                db.execute("DELETE FROM bans WHERE ip = ?1", params![ip.to_string()])?;
                Ok(false)
            }
            Some(_) => Ok(true),
            None => Ok(false),
        }
    }
}

fn now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shares_python_schema_and_expires_entries() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("bans.sqlite3");
        let ip: IpAddr = "192.0.2.42".parse().unwrap();
        let store = IpBanStore::open(&path).unwrap();
        store.ban(ip).unwrap();
        assert!(store.is_banned(ip).unwrap());

        let python_connection = Connection::open(&path).unwrap();
        let expiry: f64 = python_connection
            .query_row(
                "SELECT expires FROM bans WHERE ip = ?1",
                [ip.to_string()],
                |row| row.get(0),
            )
            .unwrap();
        assert!(expiry > now());
        python_connection
            .execute(
                "UPDATE bans SET expires = 0 WHERE ip = ?1",
                [ip.to_string()],
            )
            .unwrap();
        assert!(!store.is_banned(ip).unwrap());

        let other_ip: IpAddr = "198.51.100.7".parse().unwrap();
        python_connection
            .execute(
                "INSERT INTO bans (ip, expires) VALUES (?1, ?2)",
                params![other_ip.to_string(), now() + BAN_SECONDS],
            )
            .unwrap();
        assert!(store.is_banned(other_ip).unwrap());
    }
}
