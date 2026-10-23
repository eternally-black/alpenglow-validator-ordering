//! Spend ledger — the hard fee cap (PLAN §5.1, layer 1).
//!
//! Every transaction that could cost lamports (probes and setup transactions alike) is *reserved* at its worst-case
//! fee before it is sent. The cap holds over `landed fees + open reservations`, so an unknown outcome is always counted
//! as spent. A reservation is released only on positive evidence that the transaction can never land
//! (`expired_confirmed`: its blockhash's last valid block height is finalized and the signature is still unknown).
//!
//! SQLite in WAL mode with `BEGIN IMMEDIATE` makes the check-and-insert atomic and durable, so the cap survives
//! crashes and restarts. One ledger file covers the whole campaign: smoke test, pilot, runs, funding and sweeps.

use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OptionalExtension, TransactionBehavior, params};
use serde::Serialize;
use std::path::Path;
use std::sync::Mutex;

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
#[error("spend cap exceeded: committed {committed} + requested {requested} > cap {cap} lamports")]
pub struct CapExceeded {
    pub committed: u64,
    pub requested: u64,
    pub cap: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Kind {
    Probe,
    Setup,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct Totals {
    pub cap: u64,
    /// Fees of transactions observed landed (from `meta.fee`).
    pub spent: u64,
    /// Worst-case fees of transactions whose outcome is not yet proven.
    pub reserved: u64,
    pub landed_count: u64,
    pub open_count: u64,
    pub released_count: u64,
}

impl Totals {
    pub fn committed(&self) -> u64 {
        self.spent + self.reserved
    }
    pub fn headroom(&self) -> u64 {
        self.cap.saturating_sub(self.committed())
    }
}

pub struct Ledger {
    conn: Mutex<Connection>,
    cap: u64,
}

impl Ledger {
    /// Opens (or creates) the ledger. The cap is fixed at creation; re-opening with a different cap is refused, so a
    /// later run cannot silently raise it.
    pub fn open(path: &Path, cap_lamports: u64) -> Result<Self> {
        let conn = Connection::open(path).with_context(|| format!("opening ledger {}", path.display()))?;
        conn.pragma_update(None, "journal_mode", "WAL")?;
        conn.pragma_update(None, "synchronous", "FULL")?;
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
             CREATE TABLE IF NOT EXISTS reservations (
                 signature   TEXT PRIMARY KEY,
                 kind        TEXT NOT NULL,
                 label       TEXT NOT NULL,
                 max_fee     INTEGER NOT NULL CHECK (max_fee >= 0),
                 status      TEXT NOT NULL CHECK (status IN ('reserved', 'landed', 'expired_confirmed')),
                 actual_fee  INTEGER,
                 created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                 resolved_at TEXT
             );",
        )?;
        let stored: Option<String> =
            conn.query_row("SELECT value FROM meta WHERE key = 'cap_lamports'", [], |r| r.get(0)).optional()?;
        match stored {
            None => {
                conn.execute("INSERT INTO meta (key, value) VALUES ('cap_lamports', ?1)", params![cap_lamports.to_string()])?;
            }
            Some(s) if s.parse::<u64>().ok() == Some(cap_lamports) => {}
            Some(s) => bail!("ledger {} was created with cap {s} lamports; refusing to reopen it with {cap_lamports}", path.display()),
        }
        Ok(Self { conn: Mutex::new(conn), cap: cap_lamports })
    }

    pub fn cap(&self) -> u64 {
        self.cap
    }

    /// Atomically reserves `max_fee` for `signature`, or fails without side effects if the cap would be exceeded.
    /// Re-reserving the same signature is a no-op (idempotent retries cost nothing extra: a signature lands at most once).
    pub fn reserve(&self, signature: &str, kind: Kind, label: &str, max_fee: u64) -> Result<()> {
        let mut conn = self.conn.lock().expect("ledger mutex");
        let tx = conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let exists: bool =
            tx.query_row("SELECT 1 FROM reservations WHERE signature = ?1", params![signature], |_| Ok(true)).optional()?.unwrap_or(false);
        if exists {
            return Ok(());
        }
        let committed = committed_in(&tx)?;
        if committed.saturating_add(max_fee) > self.cap {
            return Err(CapExceeded { committed, requested: max_fee, cap: self.cap }.into());
        }
        let kind_s = match kind {
            Kind::Probe => "probe",
            Kind::Setup => "setup",
        };
        tx.execute(
            "INSERT INTO reservations (signature, kind, label, max_fee, status) VALUES (?1, ?2, ?3, ?4, 'reserved')",
            params![signature, kind_s, label, max_fee as i64],
        )?;
        tx.commit()?;
        Ok(())
    }

    /// Records the fee actually charged (from the landed transaction's `meta.fee`).
    pub fn resolve_landed(&self, signature: &str, actual_fee: u64) -> Result<()> {
        let conn = self.conn.lock().expect("ledger mutex");
        let n = conn.execute(
            "UPDATE reservations SET status = 'landed', actual_fee = ?2,
                    resolved_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
             WHERE signature = ?1",
            params![signature, actual_fee as i64],
        )?;
        if n == 0 {
            bail!("resolve_landed: unknown signature {signature} (every send must be reserved first)");
        }
        Ok(())
    }

    /// Releases a reservation. Call only with proof of non-inclusion: the blockhash's last valid block height is
    /// finalized and `getSignatureStatuses(searchTransactionHistory)` still returns null.
    pub fn resolve_expired(&self, signature: &str) -> Result<()> {
        let conn = self.conn.lock().expect("ledger mutex");
        let n = conn.execute(
            "UPDATE reservations SET status = 'expired_confirmed', actual_fee = 0,
                    resolved_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
             WHERE signature = ?1 AND status = 'reserved'",
            params![signature],
        )?;
        if n == 0 {
            bail!("resolve_expired: {signature} is not an open reservation");
        }
        Ok(())
    }

    pub fn open_signatures(&self) -> Result<Vec<String>> {
        let conn = self.conn.lock().expect("ledger mutex");
        let mut st = conn.prepare("SELECT signature FROM reservations WHERE status = 'reserved' ORDER BY created_at")?;
        let rows = st.query_map([], |r| r.get(0))?.collect::<std::result::Result<Vec<String>, _>>()?;
        Ok(rows)
    }

    pub fn totals(&self) -> Result<Totals> {
        let conn = self.conn.lock().expect("ledger mutex");
        let (spent, landed_count): (i64, i64) = conn.query_row(
            "SELECT COALESCE(SUM(actual_fee), 0), COUNT(*) FROM reservations WHERE status = 'landed'",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )?;
        let (reserved, open_count): (i64, i64) = conn.query_row(
            "SELECT COALESCE(SUM(max_fee), 0), COUNT(*) FROM reservations WHERE status = 'reserved'",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )?;
        let released_count: i64 =
            conn.query_row("SELECT COUNT(*) FROM reservations WHERE status = 'expired_confirmed'", [], |r| r.get(0))?;
        Ok(Totals {
            cap: self.cap,
            spent: spent as u64,
            reserved: reserved as u64,
            landed_count: landed_count as u64,
            open_count: open_count as u64,
            released_count: released_count as u64,
        })
    }
}

fn committed_in(tx: &rusqlite::Transaction<'_>) -> Result<u64> {
    let v: i64 = tx.query_row(
        "SELECT COALESCE(SUM(CASE WHEN status = 'landed' THEN actual_fee
                                  WHEN status = 'reserved' THEN max_fee ELSE 0 END), 0)
         FROM reservations",
        [],
        |r| r.get(0),
    )?;
    Ok(v as u64)
}

/// Layer 2 of the cap: on-chain reconciliation over *all* owned accounts (master + payers). Transfers between owned
/// accounts cancel out, so rent moved into payers needs no adjustment; only fees and external deposits change the sum.
pub fn reconcile(initial_total: u64, external_deposits: u64, current_total: u64, cap: u64) -> Result<u64> {
    let spent_on_chain = (initial_total + external_deposits).saturating_sub(current_total);
    if spent_on_chain > cap {
        bail!("on-chain reconciliation: owned balance fell by {spent_on_chain} lamports > cap {cap} — aborting");
    }
    Ok(spent_on_chain)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_ledger(cap: u64) -> (Ledger, std::path::PathBuf) {
        let dir = std::env::temp_dir().join(format!("itb-ledger-test-{}", rand::random::<u64>()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("ledger.sqlite");
        (Ledger::open(&path, cap).unwrap(), path)
    }

    #[test]
    fn refuses_a_reservation_that_would_cross_the_cap() {
        let (l, _) = temp_ledger(10_000);
        l.reserve("s1", Kind::Probe, "a", 6_000).unwrap();
        let err = l.reserve("s2", Kind::Probe, "b", 6_000).unwrap_err();
        assert_eq!(err.downcast_ref::<CapExceeded>(), Some(&CapExceeded { committed: 6_000, requested: 6_000, cap: 10_000 }));
        l.reserve("s3", Kind::Probe, "c", 4_000).unwrap(); // exactly at the cap is allowed
        assert_eq!(l.totals().unwrap().committed(), 10_000);
    }

    #[test]
    fn landed_fee_replaces_the_reservation_and_expiry_releases_it() {
        let (l, _) = temp_ledger(20_000);
        l.reserve("s1", Kind::Probe, "a", 6_500).unwrap();
        l.reserve("s2", Kind::Probe, "b", 6_500).unwrap();
        l.resolve_landed("s1", 6_000).unwrap();
        l.resolve_expired("s2").unwrap();
        let t = l.totals().unwrap();
        assert_eq!((t.spent, t.reserved, t.landed_count, t.open_count, t.released_count), (6_000, 0, 1, 0, 1));
        assert!(l.resolve_expired("s1").is_err(), "a landed tx can never be released");
    }

    #[test]
    fn cap_survives_restart_and_unknown_outcomes_stay_charged() {
        let (l, path) = temp_ledger(10_000);
        l.reserve("s1", Kind::Probe, "a", 9_000).unwrap();
        drop(l); // crash before the outcome is known
        let l = Ledger::open(&path, 10_000).unwrap();
        assert_eq!(l.totals().unwrap().reserved, 9_000);
        assert!(l.reserve("s2", Kind::Setup, "fund", 5_000).is_err());
        assert_eq!(l.open_signatures().unwrap(), vec!["s1".to_string()]);
    }

    #[test]
    fn reopening_with_a_different_cap_is_refused() {
        let (l, path) = temp_ledger(10_000);
        drop(l);
        assert!(Ledger::open(&path, 20_000).is_err());
    }

    #[test]
    fn duplicate_reservation_is_idempotent() {
        let (l, _) = temp_ledger(10_000);
        l.reserve("s1", Kind::Probe, "a", 6_000).unwrap();
        l.reserve("s1", Kind::Probe, "a", 6_000).unwrap();
        assert_eq!(l.totals().unwrap().reserved, 6_000);
    }

    #[test]
    fn reconciliation_detects_overspend() {
        assert_eq!(reconcile(100_000, 0, 90_000, 50_000).unwrap(), 10_000);
        assert!(reconcile(100_000, 0, 40_000, 50_000).is_err());
        assert_eq!(reconcile(100_000, 20_000, 110_000, 50_000).unwrap(), 10_000);
    }
}
