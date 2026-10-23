//! Dry-run is the default, enforced by types: every function that can put transaction bytes on the wire takes a
//! `&LiveAuthorization`, and the only way to obtain one is [`LiveAuthorization::grant`], which the CLI calls after
//! validating `--live`, the cap, the keypair and the Alpenglow gate.

use crate::alpenglow::GateStatus;
use crate::ledger::Ledger;
use anyhow::{Result, bail};

pub const LAMPORTS_PER_SOL: u64 = 1_000_000_000;
/// Compiled maximum for any cap (the brief: "the entire measurement process should fit within approximately 0.05 SOL").
/// Raising it requires a code change, not a flag.
pub const COMPILED_MAX_SPEND_LAMPORTS: u64 = 50_000_000;

#[derive(Debug)]
pub struct LiveAuthorization {
    cap_lamports: u64,
    _private: (),
}

impl LiveAuthorization {
    pub fn grant(live: bool, max_spend_sol: Option<f64>, gate: &GateStatus, ledger: &Ledger) -> Result<Self> {
        if !live {
            bail!("live sending requires --live");
        }
        let Some(sol) = max_spend_sol else {
            bail!("live sending requires an explicit --max-spend-sol");
        };
        let cap = sol_to_lamports(sol)?;
        if cap > COMPILED_MAX_SPEND_LAMPORTS {
            bail!("--max-spend-sol {sol} exceeds the compiled maximum of {} SOL", COMPILED_MAX_SPEND_LAMPORTS as f64 / LAMPORTS_PER_SOL as f64);
        }
        if ledger.cap() != cap {
            bail!("ledger cap is {} lamports but --max-spend-sol is {cap}; use the same cap for the whole campaign", ledger.cap());
        }
        if gate.activated_at_slot == 0 {
            bail!("Alpenglow gate status missing");
        }
        Ok(Self { cap_lamports: cap, _private: () })
    }

    pub fn cap_lamports(&self) -> u64 {
        self.cap_lamports
    }

    #[cfg(test)]
    pub fn for_tests() -> Self {
        Self { cap_lamports: 1, _private: () }
    }
}

pub fn sol_to_lamports(sol: f64) -> Result<u64> {
    if !sol.is_finite() || sol <= 0.0 {
        bail!("spend cap must be a positive number of SOL, got {sol}");
    }
    Ok((sol * LAMPORTS_PER_SOL as f64).round() as u64)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::alpenglow::{FEATURE_GATE, FIRST_ALPENGLOW_SLOT};

    fn gate() -> GateStatus {
        GateStatus { feature_gate: FEATURE_GATE, activated_at_slot: 459_648_000, first_alpenglow_slot: FIRST_ALPENGLOW_SLOT }
    }

    fn ledger(cap: u64) -> Ledger {
        let dir = std::env::temp_dir().join(format!("itb-auth-test-{}", rand::random::<u64>()));
        std::fs::create_dir_all(&dir).unwrap();
        Ledger::open(&dir.join("l.sqlite"), cap).unwrap()
    }

    #[test]
    fn requires_flag_cap_and_matching_ledger() {
        let l = ledger(5_000_000);
        assert!(LiveAuthorization::grant(false, Some(0.005), &gate(), &l).is_err());
        assert!(LiveAuthorization::grant(true, None, &gate(), &l).is_err());
        assert!(LiveAuthorization::grant(true, Some(0.006), &gate(), &l).is_err());
        assert!(LiveAuthorization::grant(true, Some(0.005), &gate(), &l).is_ok());
    }

    #[test]
    fn compiled_maximum_is_enforced() {
        let l = ledger(60_000_000);
        assert!(LiveAuthorization::grant(true, Some(0.06), &gate(), &l).is_err());
        assert!(sol_to_lamports(-1.0).is_err());
        assert!(sol_to_lamports(f64::NAN).is_err());
    }
}
