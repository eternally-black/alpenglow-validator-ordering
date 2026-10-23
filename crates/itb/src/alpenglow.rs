//! The bounty forbids mixing measurements from before and after the Alpenglow upgrade. Every run checks the
//! on-chain feature gate, and every analysed slot must be at or after the first Alpenglow block.

use crate::rpc::Rpc;
use anyhow::{Result, bail};
use serde::Serialize;

/// Feature gate as deployed on mainnet (the key printed in SIMD-0384, `a1penGLz8…`, does not exist on mainnet).
pub const FEATURE_GATE: &str = "A1pengvuM6JEcyNuTnMqepBKhwHE3N6PmUrdATGawhJS";
pub const FEATURE_PROGRAM: &str = "Feature111111111111111111111111111111111111";
/// First Alpenglow block on mainnet (parent 459,652,999 = last TowerBFT block, per `getAgGenesisCert`).
pub const FIRST_ALPENGLOW_SLOT: u64 = 459_653_008;

#[derive(Debug, Clone, Serialize)]
pub struct GateStatus {
    pub feature_gate: &'static str,
    pub activated_at_slot: u64,
    pub first_alpenglow_slot: u64,
}

/// Feature account data is bincode `Feature { activated_at: Option<u64> }`: tag byte, then u64 little-endian.
pub fn parse_feature_account(owner: &str, data: &[u8]) -> Result<Option<u64>> {
    if owner != FEATURE_PROGRAM {
        bail!("feature account owned by {owner}, expected {FEATURE_PROGRAM}");
    }
    match data.first() {
        Some(0) => Ok(None),
        Some(1) if data.len() >= 9 => Ok(Some(u64::from_le_bytes(data[1..9].try_into().expect("8 bytes")))),
        _ => bail!("malformed feature account data ({} bytes)", data.len()),
    }
}

/// Refuses to continue unless Alpenglow is active on the cluster behind `rpc`.
pub async fn require_active(rpc: &Rpc) -> Result<GateStatus> {
    let Some((owner, data, _)) = rpc.account(FEATURE_GATE).await? else {
        bail!("Alpenglow feature account {FEATURE_GATE} not found — wrong cluster?");
    };
    match parse_feature_account(&owner, &data)? {
        Some(slot) => Ok(GateStatus {
            feature_gate: FEATURE_GATE,
            activated_at_slot: slot,
            first_alpenglow_slot: FIRST_ALPENGLOW_SLOT,
        }),
        None => bail!("Alpenglow feature {FEATURE_GATE} is pending, not active — refusing to measure"),
    }
}

/// Slot filter applied at ingest and again at analysis.
pub fn is_post_alpenglow(slot: u64) -> bool {
    slot >= FIRST_ALPENGLOW_SLOT
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_activated_feature() {
        let mut data = vec![1u8];
        data.extend_from_slice(&459_648_000u64.to_le_bytes());
        assert_eq!(parse_feature_account(FEATURE_PROGRAM, &data).unwrap(), Some(459_648_000));
    }

    #[test]
    fn parses_pending_feature_and_rejects_wrong_owner() {
        assert_eq!(parse_feature_account(FEATURE_PROGRAM, &[0]).unwrap(), None);
        assert!(parse_feature_account("11111111111111111111111111111111", &[0]).is_err());
        assert!(parse_feature_account(FEATURE_PROGRAM, &[1, 2]).is_err());
    }

    #[test]
    fn slot_floor() {
        assert!(!is_post_alpenglow(459_652_999));
        assert!(is_post_alpenglow(FIRST_ALPENGLOW_SLOT));
    }
}
