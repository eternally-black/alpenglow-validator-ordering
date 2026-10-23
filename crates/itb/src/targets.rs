//! Who leads when, and through which door transactions reach them.
//!
//! "Leader type" is recorded per window as clientId × version × ingress kind (PLAN §3). Ingress kind matters because
//! ~69 % of stake advertises a TPU address that belongs to a shared BAM node or Harmonic Remote TPU, where an external
//! builder — not the validator — orders transactions.

use crate::rpc::{ClusterNode, Rpc, VoteAccount};
use anyhow::Result;
use serde::Serialize;
use std::collections::HashMap;
use std::net::SocketAddr;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IngressKind {
    /// `tpuQuic` is on the validator's own gossip IP.
    Direct,
    /// Jito-Solana validator whose TPU points elsewhere (self-hosted relayer; agave-jito default port 11228).
    Relayer,
    /// AgaveBam / FireBAM: TPU is a BAM node shared by many validators.
    BamNode,
    /// HarmonicAgave / HarmonicFiredancer: TPU is a Harmonic Remote TPU shared by many validators.
    HarmonicRemoteTpu,
    /// Any other client whose TPU IP differs from its gossip IP.
    OtherProxy,
    /// No `tpuQuic` advertised.
    None,
}

#[derive(Debug, Clone, Serialize)]
pub struct Validator {
    pub identity: String,
    pub vote_account: Option<String>,
    pub activated_stake: u64,
    pub client_id: String,
    pub version: String,
    pub tpu_quic: Option<String>,
    pub gossip: Option<String>,
    pub ingress: IngressKind,
}

impl Validator {
    pub fn tpu_addr(&self) -> Option<SocketAddr> {
        self.tpu_quic.as_deref().and_then(|s| s.parse().ok())
    }
}

fn ip_of(addr: &Option<String>) -> Option<String> {
    addr.as_deref().and_then(|s| s.parse::<SocketAddr>().ok()).map(|a| a.ip().to_string())
}

pub fn classify(node: &ClusterNode) -> IngressKind {
    let client = node.client_id.as_deref().unwrap_or("");
    let Some(_) = node.tpu_quic else { return IngressKind::None };
    match client {
        "AgaveBam" | "FireBAM" => IngressKind::BamNode,
        "HarmonicAgave" | "HarmonicFiredancer" | "HarmonicFrankendancer" => IngressKind::HarmonicRemoteTpu,
        _ => {
            // IP equality is a heuristic, not proof of direct ingress: a self-hosted Jito relayer can share the
            // validator's IP, so the relayer's default port (11228) marks a relayer either way.
            let same_ip = ip_of(&node.tpu_quic) == ip_of(&node.gossip);
            let relayer_port = node.tpu_quic.as_deref().is_some_and(|a| a.ends_with(":11228"));
            match (same_ip, client) {
                (_, "JitoLabs") if relayer_port => IngressKind::Relayer,
                (true, _) => IngressKind::Direct,
                (false, "JitoLabs") => IngressKind::Relayer,
                (false, _) => IngressKind::OtherProxy,
            }
        }
    }
}

/// Joins gossip with stake. Returns staked validators sorted by stake, plus the raw gossip JSON for archiving.
pub async fn snapshot(rpc: &Rpc) -> Result<(Vec<Validator>, serde_json::Value)> {
    let raw = rpc.cluster_nodes_raw().await?;
    let nodes: Vec<ClusterNode> = serde_json::from_value(raw.clone())?;
    let votes: Vec<VoteAccount> = rpc.vote_accounts().await?;
    let by_node: HashMap<&str, &VoteAccount> = votes.iter().map(|v| (v.node_pubkey.as_str(), v)).collect();
    let mut out: Vec<Validator> = nodes
        .iter()
        .filter_map(|n| {
            let v = by_node.get(n.pubkey.as_str())?;
            Some(Validator {
                identity: n.pubkey.clone(),
                vote_account: Some(v.vote_pubkey.clone()),
                activated_stake: v.activated_stake,
                client_id: n.client_id.clone().unwrap_or_else(|| "unknown".into()),
                version: n.version.clone().unwrap_or_else(|| "unknown".into()),
                tpu_quic: n.tpu_quic.clone(),
                gossip: n.gossip.clone(),
                ingress: classify(n),
            })
        })
        .filter(|v| v.activated_stake > 0)
        .collect();
    out.sort_by(|a, b| b.activated_stake.cmp(&a.activated_stake));
    Ok((out, raw))
}

/// Mechanism group label used for target selection and pooling (PLAN §2.1).
pub fn group(v: &Validator) -> String {
    format!("{}/{}", v.client_id, serde_json::to_value(v.ingress).ok().and_then(|x| x.as_str().map(String::from)).unwrap_or_default())
}

/// Highest-stake validator of each mechanism group, plus the `extra` next-highest on a *different* TPU IP
/// (so shared-builder groups contribute two distinct endpoints).
pub fn top_per_group(validators: &[Validator], extra: usize) -> Vec<Validator> {
    let mut picked: Vec<Validator> = vec![];
    let mut per_group: HashMap<String, Vec<String>> = HashMap::new(); // group -> TPU IPs already used
    for v in validators {
        if v.ingress == IngressKind::None {
            continue;
        }
        let g = group(v);
        let used = per_group.entry(g).or_default();
        let ip = ip_of(&v.tpu_quic).unwrap_or_default();
        if used.len() <= extra && !used.contains(&ip) {
            used.push(ip);
            picked.push(v.clone());
        }
    }
    picked
}

/// Leader windows as (first_slot, last_slot): leader slots grouped into the 4-slot, 4-aligned groups the schedule
/// assigns (`NUM_CONSECUTIVE_LEADER_SLOTS`). Two back-to-back windows of the same leader stay two windows.
pub fn windows(mut slots: Vec<u64>) -> Vec<(u64, u64)> {
    slots.sort_unstable();
    slots.dedup();
    let mut out: Vec<(u64, u64)> = vec![];
    for s in slots {
        match out.last_mut() {
            Some((first, end)) if *first / 4 == s / 4 => *end = s,
            _ => out.push((s, s)),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn node(client: &str, gossip: &str, tpu: Option<&str>) -> ClusterNode {
        ClusterNode {
            pubkey: "x".into(),
            gossip: Some(gossip.into()),
            tpu_quic: tpu.map(String::from),
            version: Some("4.3.2".into()),
            client_id: Some(client.into()),
            feature_set: None,
        }
    }

    #[test]
    fn ingress_classification() {
        assert_eq!(classify(&node("Agave", "1.2.3.4:8001", Some("1.2.3.4:8009"))), IngressKind::Direct);
        assert_eq!(classify(&node("JitoLabs", "1.2.3.4:8001", Some("5.6.7.8:11228"))), IngressKind::Relayer);
        assert_eq!(classify(&node("JitoLabs", "1.2.3.4:8001", Some("1.2.3.4:11228"))), IngressKind::Relayer, "same-IP relayer");
        assert_eq!(classify(&node("JitoLabs", "1.2.3.4:8001", Some("1.2.3.4:8002"))), IngressKind::Direct);
        assert_eq!(classify(&node("AgaveBam", "1.2.3.4:8001", Some("9.9.9.9:5010"))), IngressKind::BamNode);
        assert_eq!(classify(&node("HarmonicFiredancer", "1.2.3.4:8001", Some("8.8.8.8:9007"))), IngressKind::HarmonicRemoteTpu);
        assert_eq!(classify(&node("Firedancer", "1.2.3.4:8001", None)), IngressKind::None);
    }

    #[test]
    fn leader_windows_group_consecutive_slots() {
        assert_eq!(windows(vec![14, 12, 13, 15, 40, 41, 42, 43, 50]), vec![(12, 15), (40, 43), (50, 50)]);
        // back-to-back windows of one leader (and a single-leader localnet) stay separate 4-slot windows
        assert_eq!(windows((100..112).collect()), vec![(100, 103), (104, 107), (108, 111)]);
        assert!(windows(vec![]).is_empty());
    }
}
