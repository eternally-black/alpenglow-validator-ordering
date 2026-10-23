//! Minimal JSON-RPC client. Responses are kept as `serde_json::Value` where we archive them verbatim (blocks,
//! gossip), and decoded into small structs where we compute with them. Raw JSON keeps the collector independent of
//! the agave client types, so v1 transactions and new metadata fields pass through untouched.

use anyhow::{Context, Result, anyhow, bail};
use serde::Deserialize;
use serde_json::{Value, json};
use solana_hash::Hash;
use std::str::FromStr;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

/// `getBlock` errors that mean "no block for this slot" rather than a transport failure.
const SLOT_SKIPPED_CODES: [i64; 3] = [-32007, -32009, -32004];
/// Agave's `MAX_PROCESSING_AGE`: a blockhash is valid while the bank's block height is ≤ its block height + 150.
pub const MAX_PROCESSING_AGE: u64 = 150;

#[derive(Debug, thiserror::Error)]
#[error("rpc error {code}: {message}")]
pub struct RpcError {
    pub code: i64,
    pub message: String,
}

pub struct Rpc {
    http: reqwest::Client,
    url: String,
    next_id: AtomicU64,
    max_attempts: u32,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct EpochInfo {
    pub absolute_slot: u64,
    pub block_height: u64,
    pub epoch: u64,
    pub slot_index: u64,
    pub slots_in_epoch: u64,
}

impl EpochInfo {
    pub fn first_slot_of_epoch(&self) -> u64 {
        self.absolute_slot - self.slot_index
    }
}

#[derive(Debug, Clone, Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ClusterNode {
    pub pubkey: String,
    pub gossip: Option<String>,
    pub tpu_quic: Option<String>,
    pub version: Option<String>,
    pub client_id: Option<String>,
    pub feature_set: Option<u64>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct VoteAccount {
    pub vote_pubkey: String,
    pub node_pubkey: String,
    pub activated_stake: u64,
}

#[derive(Debug, Clone, Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SignatureStatus {
    pub slot: u64,
    pub confirmations: Option<u64>,
    pub err: Option<Value>,
    pub confirmation_status: Option<String>,
}

/// A blockhash together with the exact block height after which transactions using it are rejected.
#[derive(Debug, Clone)]
pub struct DatedBlockhash {
    pub blockhash: Hash,
    pub slot: u64,
    pub block_height: u64,
    pub last_valid_block_height: u64,
}

impl Rpc {
    pub fn new(url: impl Into<String>) -> Self {
        let http = reqwest::Client::builder()
            .timeout(Duration::from_secs(60))
            .build()
            .expect("reqwest client");
        Self { http, url: url.into(), next_id: AtomicU64::new(1), max_attempts: 6 }
    }

    pub fn url(&self) -> &str {
        &self.url
    }

    /// One JSON-RPC call. HTTP 429 and 5xx are retried with backoff (honouring `Retry-After`); RPC-level errors are
    /// returned as [`RpcError`] without retry so callers can tell "skipped slot" from "provider down".
    pub async fn call(&self, method: &str, params: Value) -> Result<Value> {
        let mut delay = Duration::from_millis(500);
        for attempt in 1..=self.max_attempts {
            let id = self.next_id.fetch_add(1, Ordering::Relaxed);
            let body = json!({"jsonrpc": "2.0", "id": id, "method": method, "params": params});
            let resp = match self.http.post(&self.url).json(&body).send().await {
                Ok(r) => r,
                Err(e) if attempt < self.max_attempts => {
                    tracing::warn!(method, attempt, error = %e, "rpc transport error, retrying");
                    tokio::time::sleep(delay).await;
                    delay *= 2;
                    continue;
                }
                Err(e) => return Err(e).with_context(|| format!("{method}: transport")),
            };
            let status = resp.status();
            if status.as_u16() == 429 || status.is_server_error() {
                let wait = resp
                    .headers()
                    .get("retry-after")
                    .and_then(|v| v.to_str().ok())
                    .and_then(|s| s.parse::<u64>().ok())
                    .map(Duration::from_secs)
                    .unwrap_or(delay);
                if attempt < self.max_attempts {
                    tracing::warn!(method, attempt, %status, wait_ms = wait.as_millis() as u64, "rpc throttled, retrying");
                    tokio::time::sleep(wait).await;
                    delay *= 2;
                    continue;
                }
                bail!("{method}: HTTP {status} after {attempt} attempts");
            }
            let v: Value = resp.json().await.with_context(|| format!("{method}: decoding response"))?;
            if let Some(err) = v.get("error") {
                return Err(RpcError {
                    code: err.get("code").and_then(Value::as_i64).unwrap_or(0),
                    message: err.get("message").and_then(Value::as_str).unwrap_or("").to_string(),
                }
                .into());
            }
            return v.get("result").cloned().ok_or_else(|| anyhow!("{method}: response without result"));
        }
        unreachable!("loop returns on the last attempt")
    }

    async fn call_as<T: serde::de::DeserializeOwned>(&self, method: &str, params: Value) -> Result<T> {
        let v = self.call(method, params).await?;
        serde_json::from_value(v).with_context(|| format!("{method}: unexpected result shape"))
    }

    pub async fn get_slot(&self, commitment: &str) -> Result<u64> {
        self.call_as("getSlot", json!([{"commitment": commitment}])).await
    }

    pub async fn get_block_height(&self, commitment: &str) -> Result<u64> {
        self.call_as("getBlockHeight", json!([{"commitment": commitment}])).await
    }

    pub async fn get_epoch_info(&self) -> Result<EpochInfo> {
        self.call_as("getEpochInfo", json!([{"commitment": "processed"}])).await
    }

    /// Absolute leader slots of `identity` in the epoch containing `slot`.
    pub async fn leader_slots(&self, slot: u64, identity: &str, epoch_first_slot: u64) -> Result<Vec<u64>> {
        let v = self.call("getLeaderSchedule", json!([slot, {"identity": identity}])).await?;
        if v.is_null() {
            return Ok(vec![]);
        }
        let rel: Vec<u64> = v
            .get(identity)
            .map(|x| serde_json::from_value(x.clone()))
            .transpose()?
            .unwrap_or_default();
        Ok(rel.into_iter().map(|r| epoch_first_slot + r).collect())
    }

    /// Slots in `[start, end]` that have a confirmed block (skipped slots are absent).
    pub async fn blocks_in_range(&self, start: u64, end: u64) -> Result<Vec<u64>> {
        self.call_as("getBlocks", json!([start, end, {"commitment": "confirmed"}])).await
    }

    pub async fn slot_leaders(&self, start: u64, limit: u64) -> Result<Vec<String>> {
        self.call_as("getSlotLeaders", json!([start, limit])).await
    }

    pub async fn cluster_nodes_raw(&self) -> Result<Value> {
        self.call("getClusterNodes", json!([])).await
    }

    pub async fn vote_accounts(&self) -> Result<Vec<VoteAccount>> {
        #[derive(Deserialize)]
        struct R {
            current: Vec<VoteAccount>,
            delinquent: Vec<VoteAccount>,
        }
        let r: R = self.call_as("getVoteAccounts", json!([])).await?;
        Ok(r.current.into_iter().chain(r.delinquent).collect())
    }

    /// Raw block (v1-capable, full transaction details). `Ok(None)` when the slot was skipped or has no block.
    pub async fn block_raw(&self, slot: u64, commitment: &str) -> Result<Option<Value>> {
        let params = json!([slot, {
            "encoding": "json",
            "maxSupportedTransactionVersion": 1,
            "transactionDetails": "full",
            "rewards": true,
            "commitment": commitment,
        }]);
        match self.call("getBlock", params).await {
            Ok(v) if v.is_null() => Ok(None),
            Ok(v) => Ok(Some(v)),
            Err(e) => match e.downcast_ref::<RpcError>() {
                Some(re) if SLOT_SKIPPED_CODES.contains(&re.code) => Ok(None),
                _ => Err(e),
            },
        }
    }

    /// Block header only (no transactions): used to date blockhashes.
    pub async fn block_header(&self, slot: u64) -> Result<Option<(Hash, u64)>> {
        let params = json!([slot, {"transactionDetails": "none", "rewards": false, "commitment": "confirmed",
                                   "maxSupportedTransactionVersion": 1}]);
        let v = match self.call("getBlock", params).await {
            Ok(v) if v.is_null() => return Ok(None),
            Ok(v) => v,
            Err(e) => match e.downcast_ref::<RpcError>() {
                Some(re) if SLOT_SKIPPED_CODES.contains(&re.code) => return Ok(None),
                _ => return Err(e),
            },
        };
        let hash = v["blockhash"].as_str().ok_or_else(|| anyhow!("block {slot}: no blockhash"))?;
        let height = v["blockHeight"].as_u64().ok_or_else(|| anyhow!("block {slot}: no blockHeight"))?;
        Ok(Some((Hash::from_str(hash).map_err(|e| anyhow!("{e:?}"))?, height)))
    }

    /// A blockhash roughly `age_slots` old, with its exact last valid block height. Walks forward over skipped slots.
    pub async fn aged_blockhash(&self, age_slots: u64) -> Result<DatedBlockhash> {
        let tip = self.get_slot("confirmed").await?;
        let mut slot = tip.saturating_sub(age_slots);
        for _ in 0..16 {
            if let Some((blockhash, block_height)) = self.block_header(slot).await? {
                return Ok(DatedBlockhash {
                    blockhash,
                    slot,
                    block_height,
                    last_valid_block_height: block_height + MAX_PROCESSING_AGE,
                });
            }
            slot += 1;
        }
        bail!("no block found in 16 slots from {}", tip.saturating_sub(age_slots))
    }

    pub async fn latest_blockhash(&self) -> Result<DatedBlockhash> {
        let v = self.call("getLatestBlockhash", json!([{"commitment": "confirmed"}])).await?;
        let hash = v["value"]["blockhash"].as_str().ok_or_else(|| anyhow!("no blockhash"))?;
        let last_valid = v["value"]["lastValidBlockHeight"].as_u64().ok_or_else(|| anyhow!("no lastValidBlockHeight"))?;
        Ok(DatedBlockhash {
            blockhash: Hash::from_str(hash).map_err(|e| anyhow!("{e:?}"))?,
            slot: v["context"]["slot"].as_u64().unwrap_or(0),
            block_height: last_valid - MAX_PROCESSING_AGE,
            last_valid_block_height: last_valid,
        })
    }

    pub async fn signature_statuses(&self, sigs: &[String]) -> Result<Vec<Option<SignatureStatus>>> {
        let mut out = Vec::with_capacity(sigs.len());
        for chunk in sigs.chunks(256) {
            let v = self
                .call("getSignatureStatuses", json!([chunk, {"searchTransactionHistory": true}]))
                .await?;
            let part: Vec<Option<SignatureStatus>> = serde_json::from_value(v["value"].clone())?;
            out.extend(part);
        }
        Ok(out)
    }

    /// (owner, data, lamports) or `None` when the account does not exist.
    pub async fn account(&self, pubkey: &str) -> Result<Option<(String, Vec<u8>, u64)>> {
        use base64::Engine;
        let v = self
            .call("getAccountInfo", json!([pubkey, {"encoding": "base64", "commitment": "confirmed"}]))
            .await?;
        let value = &v["value"];
        if value.is_null() {
            return Ok(None);
        }
        let owner = value["owner"].as_str().unwrap_or_default().to_string();
        let data_b64 = value["data"][0].as_str().unwrap_or_default();
        let data = base64::engine::general_purpose::STANDARD.decode(data_b64)?;
        Ok(Some((owner, data, value["lamports"].as_u64().unwrap_or(0))))
    }

    /// Lamport balances; missing accounts count as 0.
    pub async fn balances(&self, pubkeys: &[String]) -> Result<Vec<u64>> {
        let mut out = Vec::with_capacity(pubkeys.len());
        for chunk in pubkeys.chunks(100) {
            let v = self
                .call("getMultipleAccounts", json!([chunk, {"encoding": "base64", "commitment": "confirmed",
                                                            "dataSlice": {"offset": 0, "length": 0}}]))
                .await?;
            for acc in v["value"].as_array().cloned().unwrap_or_default() {
                out.push(acc["lamports"].as_u64().unwrap_or(0));
            }
        }
        Ok(out)
    }

    /// Fee charged to a landed transaction (`meta.fee`), or `None` if the RPC does not have it yet.
    pub async fn transaction_fee(&self, signature: &str) -> Result<Option<u64>> {
        let v = self
            .call("getTransaction", json!([signature, {"encoding": "json", "commitment": "confirmed",
                                                       "maxSupportedTransactionVersion": 1}]))
            .await?;
        Ok(v["meta"]["fee"].as_u64())
    }

    pub async fn minimum_balance_for_rent_exemption(&self, size: usize) -> Result<u64> {
        self.call_as("getMinimumBalanceForRentExemption", json!([size])).await
    }

    pub async fn simulate(&self, tx_base64: &str) -> Result<Value> {
        self.call(
            "simulateTransaction",
            json!([tx_base64, {"encoding": "base64", "sigVerify": true, "commitment": "confirmed"}]),
        )
        .await
    }

    /// Used only for setup transactions (funding, sweeping, the pre-registration Memo) — never for probes.
    pub async fn send_transaction(&self, tx_base64: &str) -> Result<String> {
        self.call_as(
            "sendTransaction",
            json!([tx_base64, {"encoding": "base64", "skipPreflight": false, "preflightCommitment": "confirmed",
                               "maxRetries": 10}]),
        )
        .await
    }
}

/// JSON fields we rely on, so a renamed field fails loudly instead of silently producing zeros.
pub fn require_u64(v: &Value, field: &str) -> Result<u64> {
    v.get(field).and_then(Value::as_u64).ok_or_else(|| anyhow!("missing u64 field `{field}`"))
}
