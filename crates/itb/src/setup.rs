//! Setup transactions: payer pool creation, funding, sweeping, and the on-chain Memo of the pre-registration hash.
//! They go through RPC `sendTransaction` (their timing is irrelevant) but through the same spend ledger as probes.

use crate::auth::LiveAuthorization;
use crate::collect::{self, Status, Tracked};
use crate::keys::{read_keypair, write_keypair};
use crate::ledger::{Kind, Ledger, Reservation};
use crate::probe::LAMPORTS_PER_SIGNATURE;
use crate::rpc::Rpc;
use anyhow::{Result, bail};
use base64::Engine;
use solana_instruction::{AccountMeta, Instruction};
use solana_keypair::Keypair;
use solana_message::Message;
use solana_pubkey::Pubkey;
use solana_signer::Signer;
use solana_transaction::Transaction;
use std::path::Path;
use std::str::FromStr;
use std::time::Duration;

pub const MEMO_PROGRAM: &str = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr";
/// Allowance for all setup transactions of the campaign (funding, sweeping, the Memo): 200 one-signature fees.
pub const SETUP_BUDGET_SOL: f64 = 0.001;
/// System transfers per funding transaction (well under the 1232-byte packet limit).
const TRANSFERS_PER_TX: usize = 16;

pub fn init_payers(dir: &Path, count: usize) -> Result<Vec<Pubkey>> {
    std::fs::create_dir_all(dir)?;
    let existing = crate::keys::payer_paths(dir)?;
    if !existing.is_empty() {
        bail!(
            "{} already contains {} payer keypairs; refusing to create more",
            dir.display(),
            existing.len()
        );
    }
    let mut out = vec![];
    for i in 0..count {
        let kp = Keypair::new();
        write_keypair(&dir.join(format!("payer-{i:03}.json")), &kp)?;
        out.push(kp.pubkey());
    }
    Ok(out)
}

/// Sends one setup transaction (reserved at its worst-case fee, against the "setup" budget) and resolves it with the
/// same evidence rules as probes. Success requires a confirmed block containing the transaction with `err == null`;
/// an on-chain failure, an expiry or an unresolved outcome is an error (the fee accounting is kept either way).
async fn send_setup(
    rpc: &Rpc,
    ledger: &Ledger,
    auth: &LiveAuthorization,
    signers: &[&Keypair],
    ixs: &[Instruction],
    label: &str,
) -> Result<String> {
    let bh = rpc.latest_blockhash().await?;
    let payer = signers[0].pubkey();
    let tx = Transaction::new(
        signers,
        Message::new(ixs, Some(&payer)),
        bh.blockhash.clone(),
    );
    let sig = tx.signatures[0].to_string();
    let max_fee = LAMPORTS_PER_SIGNATURE * tx.signatures.len() as u64;
    ledger.reserve_batch(&[Reservation {
        signature: sig.clone(),
        kind: Kind::Setup,
        label: label.to_string(),
        max_fee,
        payer: payer.to_string(),
        last_valid_block_height: bh.last_valid_block_height,
        budget: "setup".into(),
        provenance: None,
    }])?;
    let wire = base64::engine::general_purpose::STANDARD.encode(bincode::serialize(&tx)?);
    if let Err(e) = rpc.send_transaction(auth, &wire).await {
        // The node may still have forwarded it: resolve on evidence instead of assuming it was not sent.
        tracing::warn!(label, error = %e, "sendTransaction returned an error; resolving on chain evidence");
    }
    let tracked = Tracked {
        probe_id: label.to_string(),
        signature: sig.clone(),
        target_identity: String::new(),
        window_first_slot: 0,
        window_last_slot: 0,
        last_valid_block_height: bh.last_valid_block_height,
        max_fee,
        transport_error: None,
    };
    let outcome = collect::resolve(
        rpc,
        Some(ledger),
        &[tracked],
        None,
        Duration::from_secs(150),
    )
    .await?
    .remove(0);
    match outcome.status {
        Status::ExpiredConfirmed => {
            bail!("{label}: {sig} expired without landing (its fee stays charged)")
        }
        Status::Unresolved => {
            bail!("{label}: {sig} unresolved (reservation kept; run `itb reconcile` later)")
        }
        Status::LandedUnverified => bail!(
            "{label}: {sig} landed but its block could not be verified; check it before relying on it"
        ),
        Status::NotSent => unreachable!("setup transactions are always handed to the RPC"),
        _ => match outcome.err {
            Some(err) => bail!("{label}: {sig} landed but FAILED on-chain: {err}"),
            None => Ok(sig),
        },
    }
}

/// Tops every payer up to `target_lamports` from the master.
pub async fn fund(
    rpc: &Rpc,
    ledger: &Ledger,
    auth: &LiveAuthorization,
    master: &Keypair,
    payer_dir: &Path,
    target_lamports: u64,
) -> Result<()> {
    let payers = crate::keys::load_payers(payer_dir)?;
    if payers.is_empty() {
        bail!(
            "no payers in {}; run `itb init-payers` first",
            payer_dir.display()
        );
    }
    let keys: Vec<String> = payers.iter().map(|p| p.pubkey().to_string()).collect();
    let balances = rpc.balances(&keys).await?;
    let rent = rpc.minimum_balance_for_rent_exemption(0).await?;
    if target_lamports < rent + LAMPORTS_PER_SIGNATURE {
        bail!("target {target_lamports} is below rent-exempt minimum {rent} + one fee");
    }
    let need: Vec<(Pubkey, u64)> = payers
        .iter()
        .zip(&balances)
        .filter(|(_, b)| **b < target_lamports)
        .map(|(p, b)| (p.pubkey(), target_lamports - b))
        .collect();
    let total: u64 = need.iter().map(|(_, l)| l).sum();
    let master_balance = rpc.balances(&[master.pubkey().to_string()]).await?[0];
    if master_balance
        < total + LAMPORTS_PER_SIGNATURE * (need.len() as u64 / TRANSFERS_PER_TX as u64 + 1)
    {
        bail!("master holds {master_balance} lamports, needs {total} plus fees");
    }
    for (i, chunk) in need.chunks(TRANSFERS_PER_TX).enumerate() {
        let ixs: Vec<Instruction> = chunk
            .iter()
            .map(|(to, l)| solana_system_interface::instruction::transfer(&master.pubkey(), to, *l))
            .collect();
        let sig = send_setup(rpc, ledger, auth, &[master], &ixs, &format!("fund-{i}")).await?;
        tracing::info!(%sig, payers = chunk.len(), "funded");
    }
    Ok(())
}

/// Returns every payer's entire balance to the master; payer accounts close (rent comes back).
pub async fn sweep(
    rpc: &Rpc,
    ledger: &Ledger,
    auth: &LiveAuthorization,
    master: &Pubkey,
    payer_dir: &Path,
) -> Result<()> {
    for path in crate::keys::payer_paths(payer_dir)? {
        let kp = read_keypair(&path)?;
        let bal = rpc.balances(&[kp.pubkey().to_string()]).await?[0];
        if bal <= LAMPORTS_PER_SIGNATURE {
            continue;
        }
        let ix = solana_system_interface::instruction::transfer(
            &kp.pubkey(),
            master,
            bal - LAMPORTS_PER_SIGNATURE,
        );
        let sig = send_setup(
            rpc,
            ledger,
            auth,
            &[&kp],
            &[ix],
            &format!("sweep-{}", kp.pubkey()),
        )
        .await?;
        tracing::info!(%sig, payer = %kp.pubkey(), lamports = bal - LAMPORTS_PER_SIGNATURE, "swept");
    }
    Ok(())
}

/// Posts `text` as an SPL Memo signed by the master — used to timestamp the pre-registration hash on-chain.
pub async fn memo(
    rpc: &Rpc,
    ledger: &Ledger,
    auth: &LiveAuthorization,
    master: &Keypair,
    text: &str,
) -> Result<String> {
    if text.len() > 566 {
        bail!("memo too long");
    }
    let ix = Instruction {
        program_id: Pubkey::from_str(MEMO_PROGRAM).expect("memo program id"),
        accounts: vec![AccountMeta::new_readonly(master.pubkey(), true)],
        data: text.as_bytes().to_vec(),
    };
    send_setup(rpc, ledger, auth, &[master], &[ix], "prereg-memo").await
}
