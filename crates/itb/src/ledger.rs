//! Spend ledger — the hard fee cap (PLAN §5.1, layer 1).
//!
//! Every transaction that could cost lamports (probes and setup transactions alike) is *reserved* at its worst-case
//! fee before it is sent. The cap holds over `landed fees + open reservations`, so an unknown outcome is always counted
//! as spent. A reservation leaves the open state only on evidence:
//! - `landed`: the transaction is in a confirmed block (actual `meta.fee`, or the worst case if the fee is unknown);
//! - `expired_confirmed`: a *finalized* block height above its last valid height was observed first, and only then a
//!   history-capable status lookup still returned nothing (see `collect::resolve`);
//! - `cancelled_unsent`: provably never put on the wire (no stream was opened).
//!
//! The ledger also leases payers (a payer with an open reservation is busy, across restarts), enforces named
//! sub-budgets (e.g. "smoke", "pilot") inside the campaign cap, and stores the campaign's opening on-chain balance
//! for cumulative reconciliation. SQLite in WAL mode with `BEGIN IMMEDIATE` makes every check-and-insert atomic and
//! durable. One ledger file covers the whole campaign.

use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OptionalExtension, TransactionBehavior, params};
use serde::Serialize;
use std::collections::HashSet;
use std::path::Path;
use std::sync::Mutex;

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
#[error(
    "spend cap exceeded ({scope}): committed {committed} + requested {requested} > cap {cap} lamports"
)]
pub struct CapExceeded {
    pub scope: String,
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

impl Kind {
    fn as_str(self) -> &'static str {
        match self {
            Kind::Probe => "probe",
            Kind::Setup => "setup",
        }
    }
}

/// One intended send.
#[derive(Debug, Clone)]
pub struct Reservation {
    pub signature: String,
    pub kind: Kind,
    pub label: String,
    pub max_fee: u64,
    /// Fee payer pubkey (leased while the reservation is open).
    pub payer: String,
    pub last_valid_block_height: u64,
    /// Named sub-budget this send counts against (also always against the campaign cap).
    pub budget: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct OpenReservation {
    pub signature: String,
    pub label: String,
    pub payer: String,
    pub last_valid_block_height: u64,
    pub max_fee: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct Totals {
    pub cap: u64,
    /// Fees of transactions observed landed.
    pub spent: u64,
    /// Worst-case fees of transactions whose outcome is not yet proven.
    pub reserved: u64,
    pub landed_count: u64,
    pub open_count: u64,
    pub released_count: u64,
    pub cancelled_count: u64,
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

const COMMITTED_SQL: &str = "SELECT COALESCE(SUM(CASE WHEN status = 'landed' THEN actual_fee
                                                     WHEN status = 'reserved' THEN max_fee ELSE 0 END), 0)
                             FROM reservations";

impl Ledger {
    /// Opens (or creates) the ledger. The cap is fixed at creation; re-opening with a different cap is refused, so a
    /// later run cannot silently raise it.
    pub fn open(path: &Path, cap_lamports: u64) -> Result<Self> {
        let conn =
            Connection::open(path).with_context(|| format!("opening ledger {}", path.display()))?;
        conn.pragma_update(None, "journal_mode", "WAL")?;
        conn.pragma_update(None, "synchronous", "FULL")?;
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
             CREATE TABLE IF NOT EXISTS budgets (name TEXT PRIMARY KEY, cap INTEGER NOT NULL CHECK (cap >= 0));
             CREATE TABLE IF NOT EXISTS reservations (
                 signature   TEXT PRIMARY KEY,
                 kind        TEXT NOT NULL,
                 label       TEXT NOT NULL,
                 max_fee     INTEGER NOT NULL CHECK (max_fee >= 0),
                 status      TEXT NOT NULL CHECK (status IN ('reserved', 'landed', 'expired_confirmed', 'cancelled_unsent')),
                 actual_fee  INTEGER,
                 payer       TEXT NOT NULL,
                 last_valid_block_height INTEGER NOT NULL,
                 budget      TEXT NOT NULL,
                 created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                 resolved_at TEXT
             );",
        )?;
        let stored: Option<String> = conn
            .query_row(
                "SELECT value FROM meta WHERE key = 'cap_lamports'",
                [],
                |r| r.get(0),
            )
            .optional()?;
        match stored {
            None => {
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('cap_lamports', ?1)",
                    params![cap_lamports.to_string()],
                )?;
            }
            Some(s) if s.parse::<u64>().ok() == Some(cap_lamports) => {}
            Some(s) => bail!(
                "ledger {} was created with cap {s} lamports; refusing to reopen it with {cap_lamports}",
                path.display()
            ),
        }
        Ok(Self {
            conn: Mutex::new(conn),
            cap: cap_lamports,
        })
    }

    pub fn cap(&self) -> u64 {
        self.cap
    }

    /// Defines a named sub-budget once. Re-defining it with a different cap is refused.
    pub fn define_budget(&self, name: &str, cap: u64) -> Result<()> {
        let conn = self.conn.lock().expect("ledger mutex");
        let existing: Option<i64> = conn
            .query_row(
                "SELECT cap FROM budgets WHERE name = ?1",
                params![name],
                |r| r.get(0),
            )
            .optional()?;
        match existing {
            None => {
                conn.execute(
                    "INSERT INTO budgets (name, cap) VALUES (?1, ?2)",
                    params![name, cap as i64],
                )?;
                Ok(())
            }
            Some(c) if c as u64 == cap => Ok(()),
            Some(c) => bail!(
                "budget `{name}` already defined with cap {c}; refusing to change it to {cap}"
            ),
        }
    }

    /// Atomically reserves every item, or none of them. Checks the campaign cap and each item's sub-budget (if one is
    /// defined). Re-reserving a signature that already exists is refused (each signed transaction is reserved once).
    pub fn reserve_batch(&self, items: &[Reservation]) -> Result<()> {
        if items.is_empty() {
            return Ok(());
        }
        let mut conn = self.conn.lock().expect("ledger mutex");
        let tx = conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let committed: i64 = tx.query_row(COMMITTED_SQL, [], |r| r.get(0))?;
        let requested: u64 = items.iter().map(|i| i.max_fee).sum();
        if committed as u64 + requested > self.cap {
            return Err(CapExceeded {
                scope: "campaign".into(),
                committed: committed as u64,
                requested,
                cap: self.cap,
            }
            .into());
        }
        let budgets: HashSet<&str> = items.iter().map(|i| i.budget.as_str()).collect();
        for b in budgets {
            let cap: Option<i64> = tx
                .query_row("SELECT cap FROM budgets WHERE name = ?1", params![b], |r| {
                    r.get(0)
                })
                .optional()?;
            if let Some(cap) = cap {
                let used: i64 = tx.query_row(
                    "SELECT COALESCE(SUM(CASE WHEN status = 'landed' THEN actual_fee
                                              WHEN status = 'reserved' THEN max_fee ELSE 0 END), 0)
                     FROM reservations WHERE budget = ?1",
                    params![b],
                    |r| r.get(0),
                )?;
                let req: u64 = items
                    .iter()
                    .filter(|i| i.budget == b)
                    .map(|i| i.max_fee)
                    .sum();
                if used as u64 + req > cap as u64 {
                    return Err(CapExceeded {
                        scope: format!("budget {b}"),
                        committed: used as u64,
                        requested: req,
                        cap: cap as u64,
                    }
                    .into());
                }
            }
        }
        for i in items {
            tx.execute(
                "INSERT INTO reservations (signature, kind, label, max_fee, status, payer, last_valid_block_height, budget)
                 VALUES (?1, ?2, ?3, ?4, 'reserved', ?5, ?6, ?7)",
                params![i.signature, i.kind.as_str(), i.label, i.max_fee as i64, i.payer, i.last_valid_block_height as i64, i.budget],
            )
            .with_context(|| format!("reserving {}", i.signature))?;
        }
        tx.commit()?;
        Ok(())
    }

    fn transition(&self, signature: &str, to: &str, fee: u64) -> Result<()> {
        let conn = self.conn.lock().expect("ledger mutex");
        let n = conn.execute(
            "UPDATE reservations SET status = ?2, actual_fee = ?3, resolved_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
             WHERE signature = ?1 AND status = 'reserved'",
            params![signature, to, fee as i64],
        )?;
        if n == 0 {
            let cur: Option<String> = conn
                .query_row(
                    "SELECT status FROM reservations WHERE signature = ?1",
                    params![signature],
                    |r| r.get(0),
                )
                .optional()?;
            match (cur.as_deref(), to) {
                // A landing observed again (e.g. a re-run of reconciliation) is idempotent.
                (Some("landed"), "landed") => return Ok(()),
                (None, _) => {
                    bail!("{to}: unknown signature {signature} (every send must be reserved first)")
                }
                (Some(s), _) => bail!("{to}: {signature} is already {s}"),
            }
        }
        Ok(())
    }

    /// Records the fee actually charged (from the landed transaction's `meta.fee`).
    pub fn resolve_landed(&self, signature: &str, actual_fee: u64) -> Result<()> {
        self.transition(signature, "landed", actual_fee)
    }

    /// Releases a reservation after the expiry protocol in `collect::resolve` proved non-inclusion.
    pub fn resolve_expired(&self, signature: &str) -> Result<()> {
        self.transition(signature, "expired_confirmed", 0)
    }

    /// Releases a reservation whose transaction provably never left this process (no stream was opened).
    pub fn cancel_unsent(&self, signature: &str) -> Result<()> {
        self.transition(signature, "cancelled_unsent", 0)
    }

    pub fn open_reservations(&self) -> Result<Vec<OpenReservation>> {
        let conn = self.conn.lock().expect("ledger mutex");
        let mut st = conn.prepare(
            "SELECT signature, label, payer, last_valid_block_height, max_fee FROM reservations
             WHERE status = 'reserved' ORDER BY created_at",
        )?;
        let rows = st
            .query_map([], |r| {
                Ok(OpenReservation {
                    signature: r.get(0)?,
                    label: r.get(1)?,
                    payer: r.get(2)?,
                    last_valid_block_height: r.get::<_, i64>(3)? as u64,
                    max_fee: r.get::<_, i64>(4)? as u64,
                })
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        Ok(rows)
    }

    /// Payers that must not be reused: they have a reservation whose outcome is not yet proven.
    pub fn leased_payers(&self) -> Result<HashSet<String>> {
        Ok(self
            .open_reservations()?
            .into_iter()
            .map(|r| r.payer)
            .collect())
    }

    pub fn totals(&self) -> Result<Totals> {
        let conn = self.conn.lock().expect("ledger mutex");
        let count = |status: &str| -> rusqlite::Result<i64> {
            conn.query_row(
                "SELECT COUNT(*) FROM reservations WHERE status = ?1",
                params![status],
                |r| r.get(0),
            )
        };
        let spent: i64 = conn.query_row(
            "SELECT COALESCE(SUM(actual_fee), 0) FROM reservations WHERE status = 'landed'",
            [],
            |r| r.get(0),
        )?;
        let reserved: i64 = conn.query_row(
            "SELECT COALESCE(SUM(max_fee), 0) FROM reservations WHERE status = 'reserved'",
            [],
            |r| r.get(0),
        )?;
        Ok(Totals {
            cap: self.cap,
            spent: spent as u64,
            reserved: reserved as u64,
            landed_count: count("landed")? as u64,
            open_count: count("reserved")? as u64,
            released_count: count("expired_confirmed")? as u64,
            cancelled_count: count("cancelled_unsent")? as u64,
        })
    }

    /// The campaign's opening owned balance and owned-account set, recorded once (first live command). Later calls
    /// must present the same account set.
    pub fn campaign_opening(&self, owned: &[String], current_total: u64) -> Result<u64> {
        let conn = self.conn.lock().expect("ledger mutex");
        let accounts = serde_json::to_string(owned)?;
        let stored: Option<String> = conn
            .query_row(
                "SELECT value FROM meta WHERE key = 'owned_accounts'",
                [],
                |r| r.get(0),
            )
            .optional()?;
        match stored {
            None => {
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('owned_accounts', ?1)",
                    params![accounts],
                )?;
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('opening_total', ?1)",
                    params![current_total.to_string()],
                )?;
                Ok(current_total)
            }
            Some(s) => {
                let mut a: Vec<String> = serde_json::from_str(&s)?;
                let mut b = owned.to_vec();
                a.sort();
                b.sort();
                if a != b {
                    bail!(
                        "owned-account set differs from the one recorded at campaign start; refusing to reconcile against a different set"
                    );
                }
                let v: String = conn.query_row(
                    "SELECT value FROM meta WHERE key = 'opening_total'",
                    [],
                    |r| r.get(0),
                )?;
                Ok(v.parse()?)
            }
        }
    }

    pub fn external_deposits(&self) -> Result<u64> {
        let conn = self.conn.lock().expect("ledger mutex");
        let v: Option<String> = conn
            .query_row(
                "SELECT value FROM meta WHERE key = 'external_deposits'",
                [],
                |r| r.get(0),
            )
            .optional()?;
        Ok(v.and_then(|s| s.parse().ok()).unwrap_or(0))
    }

    /// Records SOL added to the owned accounts from outside the campaign (top-ups), so reconciliation stays exact.
    pub fn add_external_deposit(&self, lamports: u64) -> Result<u64> {
        let total = self.external_deposits()? + lamports;
        let conn = self.conn.lock().expect("ledger mutex");
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('external_deposits', ?1)
             ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            params![total.to_string()],
        )?;
        Ok(total)
    }
}

/// Layer 2 of the cap: cumulative on-chain reconciliation over *all* owned accounts since the campaign opened.
/// Transfers between owned accounts cancel out; only fees and external deposits change the sum. The on-chain drop must
/// not exceed the cap, nor exceed what the ledger has accounted for (committed) by more than `tolerance`.
pub fn reconcile(
    opening_total: u64,
    external_deposits: u64,
    current_total: u64,
    committed: u64,
    cap: u64,
    tolerance: u64,
) -> Result<u64> {
    let dropped = (opening_total + external_deposits).saturating_sub(current_total);
    if dropped > cap {
        bail!(
            "on-chain reconciliation: owned balance fell by {dropped} lamports > cap {cap} — aborting"
        );
    }
    if dropped > committed + tolerance {
        bail!(
            "on-chain reconciliation: owned balance fell by {dropped} lamports but the ledger accounts for only {committed} — unaccounted spend, aborting"
        );
    }
    Ok(dropped)
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

    fn r(sig: &str, fee: u64, payer: &str, budget: &str) -> Reservation {
        Reservation {
            signature: sig.into(),
            kind: Kind::Probe,
            label: sig.into(),
            max_fee: fee,
            payer: payer.into(),
            last_valid_block_height: 100,
            budget: budget.into(),
        }
    }

    #[test]
    fn refuses_a_batch_that_would_cross_the_cap_atomically() {
        let (l, _) = temp_ledger(10_000);
        l.reserve_batch(&[r("s1", 6_000, "p1", "run")]).unwrap();
        let err = l
            .reserve_batch(&[r("s2", 2_000, "p2", "run"), r("s3", 3_000, "p3", "run")])
            .unwrap_err();
        assert!(err.downcast_ref::<CapExceeded>().is_some());
        assert_eq!(
            l.totals().unwrap().open_count,
            1,
            "nothing of the failed batch was reserved"
        );
        l.reserve_batch(&[r("s4", 4_000, "p4", "run")]).unwrap(); // exactly at the cap is allowed
        assert_eq!(l.totals().unwrap().committed(), 10_000);
    }

    #[test]
    fn sub_budget_is_enforced_inside_the_campaign_cap() {
        let (l, _) = temp_ledger(50_000);
        l.define_budget("smoke", 10_000).unwrap();
        l.reserve_batch(&[r("s1", 6_000, "p1", "smoke")]).unwrap();
        let err = l
            .reserve_batch(&[r("s2", 6_000, "p2", "smoke")])
            .unwrap_err();
        assert_eq!(
            err.downcast_ref::<CapExceeded>().unwrap().scope,
            "budget smoke"
        );
        l.reserve_batch(&[r("s3", 6_000, "p3", "stage1")]).unwrap(); // other budgets unaffected
        assert!(
            l.define_budget("smoke", 20_000).is_err(),
            "a defined sub-budget cannot be raised"
        );
    }

    #[test]
    fn transitions_and_their_guards() {
        let (l, _) = temp_ledger(30_000);
        l.reserve_batch(&[
            r("s1", 6_500, "p1", "b"),
            r("s2", 6_500, "p2", "b"),
            r("s3", 6_500, "p3", "b"),
        ])
        .unwrap();
        l.resolve_landed("s1", 6_000).unwrap();
        l.resolve_landed("s1", 6_000).unwrap(); // idempotent
        l.resolve_expired("s2").unwrap();
        l.cancel_unsent("s3").unwrap();
        let t = l.totals().unwrap();
        assert_eq!(
            (
                t.spent,
                t.reserved,
                t.landed_count,
                t.open_count,
                t.released_count,
                t.cancelled_count
            ),
            (6_000, 0, 1, 0, 1, 1)
        );
        assert!(
            l.resolve_expired("s1").is_err(),
            "a landed tx can never be released"
        );
        assert!(l.cancel_unsent("s2").is_err());
        assert!(l.resolve_landed("nope", 1).is_err());
    }

    #[test]
    fn cap_and_payer_leases_survive_restart() {
        let (l, path) = temp_ledger(10_000);
        l.reserve_batch(&[r("s1", 9_000, "payerA", "b")]).unwrap();
        drop(l); // crash before the outcome is known
        let l = Ledger::open(&path, 10_000).unwrap();
        assert_eq!(l.totals().unwrap().reserved, 9_000);
        assert!(l.reserve_batch(&[r("s2", 5_000, "payerB", "b")]).is_err());
        assert!(l.leased_payers().unwrap().contains("payerA"));
        assert_eq!(
            l.open_reservations().unwrap()[0].last_valid_block_height,
            100
        );
    }

    #[test]
    fn reopening_with_a_different_cap_is_refused_and_duplicates_rejected() {
        let (l, path) = temp_ledger(10_000);
        l.reserve_batch(&[r("s1", 1_000, "p", "b")]).unwrap();
        assert!(l.reserve_batch(&[r("s1", 1_000, "p", "b")]).is_err());
        drop(l);
        assert!(Ledger::open(&path, 20_000).is_err());
    }

    #[test]
    fn campaign_opening_is_recorded_once_for_one_account_set() {
        let (l, _) = temp_ledger(10_000);
        let owned = vec!["a".to_string(), "b".to_string()];
        assert_eq!(l.campaign_opening(&owned, 1_000_000).unwrap(), 1_000_000);
        assert_eq!(l.campaign_opening(&owned, 900_000).unwrap(), 1_000_000);
        assert!(l.campaign_opening(&["a".to_string()], 1).is_err());
        assert_eq!(l.add_external_deposit(50_000).unwrap(), 50_000);
    }

    #[test]
    fn reconciliation_detects_overspend_and_unaccounted_spend() {
        assert_eq!(
            reconcile(100_000, 0, 90_000, 10_000, 50_000, 0).unwrap(),
            10_000
        );
        assert!(
            reconcile(100_000, 0, 40_000, 60_000, 50_000, 0).is_err(),
            "over the cap"
        );
        assert!(
            reconcile(100_000, 0, 90_000, 2_000, 50_000, 1_000).is_err(),
            "more lost than accounted"
        );
        assert_eq!(
            reconcile(100_000, 20_000, 110_000, 10_000, 50_000, 0).unwrap(),
            10_000
        );
    }
}
