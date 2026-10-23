//! The live-campaign guard shared by every command that can spend or change the ledger (`run`, `smoke`, `setup`,
//! `reconcile`), so they all hold the same invariants:
//! - one process at a time: an OS file lock next to the ledger, released by the OS when the process dies (no stale lock
//!   to delete by hand);
//! - one ledger with the compiled cap and one live authorization;
//! - one owned-account set (master + every payer in the payer directory), fixed at the first live command;
//! - cumulative on-chain reconciliation before any send is admitted: a balance drop the ledger cannot explain is charged
//!   to the ledger and stops every further send of this process (`stopped()`), while already-sent transactions are
//!   still collected.

use crate::alpenglow::GateStatus;
use crate::auth::{LiveAuthorization, sol_to_lamports};
use crate::ledger::{Ledger, ReconcileError, reconcile};
use crate::rpc::Rpc;
use anyhow::{Context, Result, bail};
use solana_pubkey::Pubkey;
use solana_signer::Signer;
use std::fs::{File, TryLockError};
use std::path::Path;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

/// Exclusive, process-lifetime lock on `<ledger>.lock`.
pub struct CampaignLock {
    _file: File,
}

impl CampaignLock {
    pub fn acquire(ledger: &Path, holder: &str) -> Result<Self> {
        let path = ledger.with_extension("lock");
        let mut file = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(&path)
            .with_context(|| format!("opening {}", path.display()))?;
        match file.try_lock() {
            Ok(()) => {}
            Err(TryLockError::WouldBlock) => bail!(
                "another itb process holds the campaign lock {} (one live command at a time per ledger)",
                path.display()
            ),
            Err(TryLockError::Error(e)) => {
                return Err(e).with_context(|| format!("locking {}", path.display()));
            }
        }
        use std::io::Write;
        file.set_len(0)?;
        writeln!(file, "{holder} pid {}", std::process::id())?;
        Ok(Self { _file: file })
    }
}

pub struct Campaign {
    pub ledger: Arc<Ledger>,
    pub auth: Arc<LiveAuthorization>,
    pub master: Pubkey,
    /// Master + payers, in a fixed order (the campaign's owned-account set).
    pub owned: Vec<String>,
    pub opening: u64,
    stopped: AtomicBool,
    _lock: CampaignLock,
}

pub struct OpenArgs<'a> {
    pub ledger: &'a Path,
    pub max_spend_sol: Option<f64>,
    pub keypair: Option<&'a Path>,
    pub payer_dir: &'a Path,
    pub holder: &'a str,
}

impl Campaign {
    /// Takes the lock, opens the ledger, grants the live authorization and reconciles before anything can be sent.
    pub async fn open(rpc: &Rpc, gate: &GateStatus, a: OpenArgs<'_>) -> Result<Self> {
        let sol = a
            .max_spend_sol
            .context("live sending requires --max-spend-sol")?;
        if let Some(dir) = a.ledger.parent().filter(|d| !d.as_os_str().is_empty()) {
            std::fs::create_dir_all(dir)?;
        }
        let lock = CampaignLock::acquire(a.ledger, a.holder)?;
        let ledger = Arc::new(Ledger::open(a.ledger, sol_to_lamports(sol)?)?);
        let auth = Arc::new(LiveAuthorization::grant(true, Some(sol), gate, &ledger)?);
        let master = crate::keys::read_keypair(
            a.keypair
                .context("live sending requires --keypair (or ITB_KEYPAIR_PATH)")?,
        )?
        .pubkey();
        let payers: Vec<String> = if a.payer_dir.exists() {
            crate::keys::load_payers(a.payer_dir)?
                .iter()
                .map(|k| k.pubkey().to_string())
                .collect()
        } else {
            vec![]
        };
        if payers.contains(&master.to_string()) {
            bail!("the master key must not also be a payer");
        }
        let owned: Vec<String> = std::iter::once(master.to_string()).chain(payers).collect();
        let current: u64 = rpc.balances(&owned).await?.iter().sum();
        let opening = ledger.campaign_opening(&owned, current)?;
        let c = Self {
            ledger,
            auth,
            master,
            owned,
            opening,
            stopped: AtomicBool::new(false),
            _lock: lock,
        };
        c.reconcile_at(current)?;
        Ok(c)
    }

    pub fn stopped(&self) -> bool {
        self.stopped.load(Ordering::SeqCst)
    }

    /// Fails once reconciliation has failed in this process: call it right before reserving anything.
    pub fn ensure_running(&self) -> Result<()> {
        if self.stopped() {
            bail!("sending stopped: on-chain reconciliation failed earlier in this process");
        }
        Ok(())
    }

    /// Reads every owned balance now and reconciles. On a discrepancy the excess is charged to the ledger, every
    /// further send of this process is refused, and the error is returned.
    pub async fn reconcile_now(&self, rpc: &Rpc) -> Result<u64> {
        let current: u64 = rpc.balances(&self.owned).await?.iter().sum();
        self.reconcile_at(current)
    }

    fn reconcile_at(&self, current: u64) -> Result<u64> {
        let t = self.ledger.totals()?;
        match reconcile(
            self.opening,
            self.ledger.external_deposits()?,
            current,
            t.committed(),
            t.cap,
        ) {
            Ok(dropped) => Ok(dropped),
            Err(e) => {
                self.stopped.store(true, Ordering::SeqCst);
                if let ReconcileError::Unaccounted { excess, .. } = e {
                    self.ledger
                        .charge_adjustment(excess, &format!("reconciliation: {e}"))?;
                }
                Err(anyhow::Error::new(e).context("all further sends stopped"))
            }
        }
    }

    /// Payer pubkeys with an unresolved transaction: funding or sweeping them would touch an account a pending probe
    /// write-locks, so setup refuses while any exist.
    pub fn refuse_if_payers_leased(&self) -> Result<()> {
        let leased = self.ledger.leased_payers()?;
        let n = self.owned.iter().filter(|p| leased.contains(*p)).count();
        if n > 0 {
            bail!(
                "{n} owned accounts have unresolved transactions; run `itb reconcile` until none are open"
            );
        }
        Ok(())
    }

    /// Defines a named sub-budget if a cap is given; every send must count against a defined budget.
    pub fn budget(&self, name: &str, cap_sol: Option<f64>) -> Result<()> {
        if let Some(sol) = cap_sol {
            self.ledger.define_budget(name, sol_to_lamports(sol)?)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn campaign_lock_is_exclusive_and_released_on_drop() {
        let dir = std::env::temp_dir().join(format!("itb-lock-{}", rand::random::<u64>()));
        std::fs::create_dir_all(&dir).unwrap();
        let ledger = dir.join("ledger.sqlite");
        let a = CampaignLock::acquire(&ledger, "run-a").unwrap();
        assert!(CampaignLock::acquire(&ledger, "run-b").is_err());
        drop(a); // the OS releases the lock with the handle (also on process death)
        assert!(CampaignLock::acquire(&ledger, "run-c").is_ok());
    }
}
