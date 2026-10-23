//! Setup transactions: payer pool creation, funding, sweeping, and the on-chain Memo of the pre-registration hash.
//! They go through RPC `sendTransaction` (their timing is irrelevant) but through the same spend ledger as probes.

use crate::auth::LiveAuthorization;
use crate::keys::{read_keypair, write_keypair};
use crate::ledger::{Kind, Ledger};
use crate::probe::LAMPORTS_PER_SIGNATURE;
use crate::rpc::Rpc;
use anyhow::{Context, Result, bail};
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
/// System transfers per funding transaction (well under the 1232-byte packet limit).
const TRANSFERS_PER_TX: usize = 16;

pub fn init_payers(dir: &Path, count: usize) -> Result<Vec<Pubkey>> {
    std::fs::create_dir_all(dir)?;
    let existing = crate::keys::payer_paths(dir)?;
    if !existing.is_empty() {
        bail!("{} already contains {} payer keypairs; refusing to create more", dir.display(), existing.len());
    }
    let mut out = vec![];
    for i in 0..count {
        let kp = Keypair::new();
        write_keypair(&dir.join(format!("payer-{i:03}.json")), &kp)?;
        out.push(kp.pubkey());
    }
    Ok(out)
}

/// Sends one setup transaction (reserved at its worst-case fee) and waits until it is confirmed or proven expired.
async fn send_setup(rpc: &Rpc, ledger: &Ledger, _auth: &LiveAuthorization, signers: &[&Keypair], ixs: &[Instruction], label: &str) -> Result<String> {
    let bh = rpc.latest_blockhash().await?;
    let payer = signers[0].pubkey();
    let tx = Transaction::new(signers, Message::new(ixs, Some(&payer)), bh.blockhash.clone());
    let sig = tx.signatures[0].to_string();
    let max_fee = LAMPORTS_PER_SIGNATURE * tx.signatures.len() as u64;
    ledger.reserve(&sig, Kind::Setup, label, max_fee)?;
    let wire = base64::engine::general_purpose::STANDARD.encode(bincode::serialize(&tx)?);
    rpc.send_transaction(&wire).await.with_context(|| format!("{label}: sendTransaction"))?;
    for _ in 0..60 {
        tokio::time::sleep(Duration::from_secs(2)).await;
        if let Some(Some(st)) = rpc.signature_statuses(std::slice::from_ref(&sig)).await?.into_iter().next() {
            if let Some(err) = st.err {
                tracing::error!(%sig, ?err, label, "setup transaction failed on-chain");
            }
            let fee = rpc.transaction_fee(&sig).await?.unwrap_or(max_fee);
            ledger.resolve_landed(&sig, fee)?;
            return Ok(sig);
        }
        if rpc.get_block_height("finalized").await? > bh.last_valid_block_height {
            ledger.resolve_expired(&sig)?;
            bail!("{label}: {sig} expired without landing");
        }
    }
    bail!("{label}: {sig} unresolved after 120 s (reservation kept)")
}

/// Tops every payer up to `target_lamports` from the master.
pub async fn fund(rpc: &Rpc, ledger: &Ledger, auth: &LiveAuthorization, master: &Keypair, payer_dir: &Path, target_lamports: u64) -> Result<()> {
    let payers = crate::keys::load_payers(payer_dir)?;
    if payers.is_empty() {
        bail!("no payers in {}; run `itb init-payers` first", payer_dir.display());
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
    if master_balance < total + LAMPORTS_PER_SIGNATURE * (need.len() as u64 / TRANSFERS_PER_TX as u64 + 1) {
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
pub async fn sweep(rpc: &Rpc, ledger: &Ledger, auth: &LiveAuthorization, master: &Pubkey, payer_dir: &Path) -> Result<()> {
    for path in crate::keys::payer_paths(payer_dir)? {
        let kp = read_keypair(&path)?;
        let bal = rpc.balances(&[kp.pubkey().to_string()]).await?[0];
        if bal <= LAMPORTS_PER_SIGNATURE {
            continue;
        }
        let ix = solana_system_interface::instruction::transfer(&kp.pubkey(), master, bal - LAMPORTS_PER_SIGNATURE);
        let sig = send_setup(rpc, ledger, auth, &[&kp], &[ix], &format!("sweep-{}", kp.pubkey())).await?;
        tracing::info!(%sig, payer = %kp.pubkey(), lamports = bal - LAMPORTS_PER_SIGNATURE, "swept");
    }
    Ok(())
}

/// Posts `text` as an SPL Memo signed by the master — used to timestamp the pre-registration hash on-chain.
pub async fn memo(rpc: &Rpc, ledger: &Ledger, auth: &LiveAuthorization, master: &Keypair, text: &str) -> Result<String> {
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
