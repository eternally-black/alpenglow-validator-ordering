//! The probe atom (PLAN §2.2) and the fee / cost / priority arithmetic used to predict how each candidate rule ranks it.
//!
//! Every probe has the same shape — 1 signature, 2 writable accounts (payer, lock), 4 instructions, 31 bytes of
//! instruction data — so only the three treatment variables differ between probes:
//! `L` (requested CU limit), `p` (CU price, µlamports/CU) and `D` (requested loaded-accounts-data limit).
//!
//! Cost and priority follow agave v4.3.2:
//! - `cost-model/src/block_cost_limits.rs`: 720 CU per signature, 300 per write lock, 1 CU per 4 instruction-data bytes,
//!   8 CU per 32 KiB page of the requested loaded-accounts-data limit;
//! - `core/src/transaction_priority.rs`: `priority = reward * 1_000_000 / (cost + 1)`;
//! - `runtime/src/bank/fee_distribution.rs`: `reward = priority_fee + base_fee - 50 % burn`.
//!
//! Firedancer v26.10.4 (`fd_pack_cost.h`, `fd_pack.c`) uses the same constants and reward split.

use serde::{Deserialize, Serialize};
use solana_compute_budget_interface::ComputeBudgetInstruction;
use solana_hash::Hash;
use solana_instruction::Instruction;
use solana_keypair::Keypair;
use solana_message::Message;
use solana_pubkey::Pubkey;
use solana_signer::Signer;
use solana_transaction::Transaction;

pub const LAMPORTS_PER_SIGNATURE: u64 = 5_000;
pub const BASE_FEE_BURN_PERCENT: u64 = 50;
pub const SIGNATURE_COST: u64 = 720;
pub const WRITE_LOCK_UNITS: u64 = 300;
pub const INSTRUCTION_DATA_BYTES_COST: u64 = 4;
pub const LOADED_DATA_PAGE_BYTES: u64 = 32 * 1024;
pub const LOADED_DATA_COST_PER_PAGE: u64 = 8;
pub const PRIORITY_MULTIPLIER: u128 = 1_000_000;

/// CUs the atom actually consumes: 3 ComputeBudget instructions + 1 System transfer, 150 CU each
/// (mainnet `simulateTransaction`, 2026-10-23). `L` below this fails with ComputationalBudgetExceeded.
pub const ATOM_EXECUTED_CU: u32 = 600;
pub const ATOM_SIGNATURES: u64 = 1;
pub const ATOM_WRITABLE_ACCOUNTS: u64 = 2;
pub const ATOM_IX_DATA_BYTES: u64 = 5 + 9 + 5 + 12;

pub const KIB_32: u32 = 32 * 1024;
pub const MIB_64: u32 = 64 * 1024 * 1024;

/// The three treatment variables of a probe.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Template {
    pub cu_limit: u32,
    pub cu_price_micro_lamports: u64,
    pub loaded_data_limit: u32,
}

impl Template {
    pub const fn new(cu_limit: u32, cu_price_micro_lamports: u64, loaded_data_limit: u32) -> Self {
        Self {
            cu_limit,
            cu_price_micro_lamports,
            loaded_data_limit,
        }
    }

    /// `ceil(L * p / 1e6)` lamports.
    pub fn priority_fee(&self) -> u64 {
        let micro = self.cu_limit as u128 * self.cu_price_micro_lamports as u128;
        micro.div_ceil(1_000_000) as u64
    }

    pub fn total_fee(&self) -> u64 {
        LAMPORTS_PER_SIGNATURE * ATOM_SIGNATURES + self.priority_fee()
    }

    /// Lamports the leader keeps: the whole priority fee plus the unburned half of the signature fee.
    pub fn reward(&self) -> u64 {
        let base = LAMPORTS_PER_SIGNATURE * ATOM_SIGNATURES;
        self.priority_fee() + base - base * BASE_FEE_BURN_PERCENT / 100
    }

    pub fn loaded_data_cost(&self) -> u64 {
        (self.loaded_data_limit as u64).div_ceil(LOADED_DATA_PAGE_BYTES) * LOADED_DATA_COST_PER_PAGE
    }

    /// Scheduling cost from the *requested* limits (what the scheduler sees before execution).
    pub fn cost(&self) -> u64 {
        SIGNATURE_COST * ATOM_SIGNATURES
            + WRITE_LOCK_UNITS * ATOM_WRITABLE_ACCOUNTS
            + ATOM_IX_DATA_BYTES / INSTRUCTION_DATA_BYTES_COST
            + self.cu_limit as u64
            + self.loaded_data_cost()
    }

    /// Agave's scheduling priority, `floor(reward * 1e6 / (cost + 1))`.
    pub fn agave_priority(&self) -> u64 {
        (self.reward() as u128 * PRIORITY_MULTIPLIER / (self.cost() as u128 + 1)) as u64
    }

    pub fn instructions(&self, payer: &Pubkey, lock: &Pubkey) -> Vec<Instruction> {
        vec![
            ComputeBudgetInstruction::set_compute_unit_limit(self.cu_limit),
            ComputeBudgetInstruction::set_compute_unit_price(self.cu_price_micro_lamports),
            ComputeBudgetInstruction::set_loaded_accounts_data_size_limit(self.loaded_data_limit),
            solana_system_interface::instruction::transfer(payer, lock, 0),
        ]
    }

    /// Build and sign the probe. `lock` is a fresh, unfunded pubkey that only carries the write lock.
    pub fn build(&self, payer: &Keypair, lock: &Pubkey, recent_blockhash: Hash) -> Transaction {
        let message = Message::new(
            &self.instructions(&payer.pubkey(), lock),
            Some(&payer.pubkey()),
        );
        Transaction::new(&[payer], message, recent_blockhash)
    }
}

/// Named templates of the contrast library (PLAN §2.3).
pub mod library {
    use super::{KIB_32, MIB_64, Template};

    pub const A: Template = Template::new(1_000, 1_000_000, KIB_32);
    pub const B: Template = Template::new(3_000, 500_000, KIB_32);
    pub const A_PRIME: Template = Template::new(1_000, 1_000_000, MIB_64);
    pub const HI: Template = Template::new(1_000, 3_000_000, KIB_32);
    pub const LO: Template = Template::new(1_000, 1_000_000, MIB_64);
    /// Study 3: costs more than A (2,835 vs 2,335) but pays more per cost unit under any share of the signature fee in
    /// the reward (none, the unburned half, all of it), so ordering by cost alone and reward ÷ cost disagree on Y vs A.
    pub const Y: Template = Template::new(1_500, 4_000_000, KIB_32);

    pub const ALL: [(&str, Template); 6] = [
        ("A", A),
        ("B", B),
        ("A'", A_PRIME),
        ("hi", HI),
        ("lo", LO),
        ("Y", Y),
    ];
}

/// Candidate ordering keys; higher value = expected earlier.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Rule {
    CuPrice,
    LamportFee,
    RewardCost,
    /// Cheapest requested cost first, ignoring the fee (Study 3's alternative to reward ÷ cost).
    CostOnly,
}

impl Rule {
    pub const ALL: [Rule; 4] = [
        Rule::CuPrice,
        Rule::LamportFee,
        Rule::RewardCost,
        Rule::CostOnly,
    ];

    pub fn key(self, t: &Template) -> u128 {
        match self {
            Rule::CuPrice => t.cu_price_micro_lamports as u128,
            Rule::LamportFee => t.priority_fee() as u128,
            Rule::RewardCost => t.agave_priority() as u128,
            Rule::CostOnly => u128::from(u64::MAX - t.cost()),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Prediction {
    First,
    Second,
    Tie,
}

/// What `rule` predicts for the pair (first, second).
pub fn predict(rule: Rule, first: &Template, second: &Template) -> Prediction {
    match rule.key(first).cmp(&rule.key(second)) {
        std::cmp::Ordering::Greater => Prediction::First,
        std::cmp::Ordering::Less => Prediction::Second,
        std::cmp::Ordering::Equal => Prediction::Tie,
    }
}

#[cfg(test)]
mod tests {
    use super::library::*;
    use super::*;

    /// Golden values, cross-checked against `scripts/contrasts.py` and recomputed independently by the v2 plan review.
    #[test]
    fn contrast_library_golden_values() {
        let golden = [
            (A, 1_000, 6_000, 2_335, 1_498_287),
            (B, 1_500, 6_500, 4_335, 922_509),
            (A_PRIME, 1_000, 6_000, 18_711, 187_045),
            (HI, 3_000, 8_000, 2_335, 2_354_452),
            (Y, 6_000, 11_000, 2_835, 2_997_179),
        ];
        for (t, prio, total, cost, priority) in golden {
            assert_eq!(t.priority_fee(), prio, "{t:?}");
            assert_eq!(t.total_fee(), total, "{t:?}");
            assert_eq!(t.cost(), cost, "{t:?}");
            assert_eq!(t.agave_priority(), priority, "{t:?}");
        }
    }

    #[test]
    fn contrasts_separate_the_three_rules() {
        use Prediction::*;
        // (C1, C2, C3) joint patterns, PLAN §2.3.
        let cases = [(A, B), (A_PRIME, B), (A, A_PRIME)];
        let pattern = |r: Rule| cases.map(|(x, y)| predict(r, &x, &y));
        assert_eq!(pattern(Rule::CuPrice), [First, First, Tie]);
        assert_eq!(pattern(Rule::LamportFee), [Second, Second, Tie]);
        assert_eq!(pattern(Rule::RewardCost), [First, Second, First]);
        for r in Rule::ALL {
            assert_eq!(predict(r, &HI, &LO), First, "dominance must hold for {r:?}");
        }
        // The gap Studies 1 and 2 leave: on C1-C3, cost alone predicts exactly what reward ÷ cost does.
        assert_eq!(pattern(Rule::CostOnly), pattern(Rule::RewardCost));
    }

    #[test]
    fn study3_contrasts_separate_cost_only_from_reward_cost() {
        use Prediction::*;
        // C4 = Y vs A, C5 = hi vs A (x first).
        let c4 = |r: Rule| predict(r, &Y, &A);
        let c5 = |r: Rule| predict(r, &HI, &A);
        assert_eq!((c4(Rule::RewardCost), c5(Rule::RewardCost)), (First, First));
        assert_eq!((c4(Rule::CostOnly), c5(Rule::CostOnly)), (Second, Tie));
        for r in [Rule::CuPrice, Rule::LamportFee] {
            assert_eq!(
                (c4(r), c5(r)),
                (First, First),
                "{r:?} was rejected by C2 / C3 in Studies 1-2"
            );
        }
        // Whatever share of the 5,000-lamport signature fee a scheduler counts as reward, Y and hi still beat A per
        // cost unit.
        for base in [0u64, 2_500, 5_000] {
            let per_cost = |t: &Template| (base + t.priority_fee()) as f64 / (t.cost() + 1) as f64;
            assert!(per_cost(&Y) > per_cost(&A), "base share {base}");
            assert!(per_cost(&HI) > per_cost(&A), "base share {base}");
        }
        assert!(Y.cost() > A.cost() && HI.cost() == A.cost());
    }

    #[test]
    fn priority_fee_rounds_up() {
        assert_eq!(Template::new(600, 1_000, KIB_32).priority_fee(), 1); // 0.6 lamports -> 1
        assert_eq!(Template::new(1_000, 0, KIB_32).priority_fee(), 0);
        assert_eq!(Template::new(1_000, 1_000, KIB_32).priority_fee(), 1);
    }

    #[test]
    fn built_probe_has_the_atom_shape() {
        let payer = Keypair::new();
        let lock = Pubkey::new_unique();
        let tx = A.build(&payer, &lock, Hash::new_from_array([7; 32]));
        let msg = &tx.message;
        assert_eq!(tx.signatures.len() as u64, ATOM_SIGNATURES);
        assert_eq!(msg.header.num_required_signatures, 1);
        assert_eq!(msg.instructions.len(), 4);
        let data_bytes: usize = msg.instructions.iter().map(|ix| ix.data.len()).sum();
        assert_eq!(data_bytes as u64, ATOM_IX_DATA_BYTES);
        let h = &msg.header;
        let signed_writable = h.num_required_signatures - h.num_readonly_signed_accounts;
        let unsigned = msg.account_keys.len() as u8 - h.num_required_signatures;
        let unsigned_writable = unsigned - h.num_readonly_unsigned_accounts;
        assert_eq!(
            (signed_writable + unsigned_writable) as u64,
            ATOM_WRITABLE_ACCOUNTS
        );
        assert!(tx.verify().is_ok());
        let wire = bincode::serialize(&tx).unwrap();
        assert!(wire.len() <= 1232, "fits a packet: {} bytes", wire.len());
    }

    #[test]
    fn templates_meet_the_cu_floor() {
        for (name, t) in ALL {
            assert!(
                t.cu_limit >= ATOM_EXECUTED_CU,
                "{name} would fail with ComputationalBudgetExceeded"
            );
        }
    }
}
