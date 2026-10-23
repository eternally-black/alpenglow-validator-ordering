//! `itb` — Inside the Block. Measures how Solana mainnet leaders order transactions in their blocks, using probe
//! transactions we send ourselves. Dry-run unless `--live` and `--max-spend-sol` are given.

mod alpenglow;
mod auth;
mod collect;
mod design;
mod keys;
mod ledger;
mod probe;
mod quic;
mod rpc;
mod run;
mod setup;
mod smoke;
mod store;
mod targets;
mod timing;

use anyhow::Result;
use clap::{Parser, Subcommand};
use std::path::PathBuf;
use std::sync::Arc;

#[derive(Parser)]
#[command(name = "itb", version, about = "Inside the Block — Solana intra-block ordering measurement")]
struct Cli {
    /// JSON-RPC endpoint. API keys in the URL are redacted from every log and data file.
    #[arg(long, env = "RPC_URL", default_value = "https://api.mainnet-beta.solana.com", global = true)]
    rpc_url: String,
    /// WebSocket endpoint for slot updates (defaults to the RPC URL with ws/wss).
    #[arg(long, env = "WS_URL", global = true)]
    ws_url: Option<String>,
    /// Also write JSON-lines logs to this file.
    #[arg(long, env = "ITB_LOG_JSON", global = true)]
    log_json: Option<PathBuf>,
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Check the Alpenglow gate and RPC/WebSocket reachability.
    Check,
    /// Print staked validators grouped by client and ingress kind.
    Targets {
        #[arg(long, default_value_t = 2)]
        per_group: usize,
    },
    /// Print the contrast-library probe templates with fee, cost and Agave priority.
    ProbeTable,
    /// Send a few probes into the next window of one or two validators per mechanism group (dry-run by default).
    Smoke {
        #[arg(long)]
        live: bool,
        #[arg(long)]
        max_spend_sol: Option<f64>,
        #[arg(long, env = "ITB_LEDGER", default_value = "state/ledger.sqlite")]
        ledger: PathBuf,
        #[arg(long, env = "ITB_KEYPAIR_PATH")]
        keypair: Option<PathBuf>,
        #[arg(long, default_value = "data/smoke")]
        out: PathBuf,
        /// Explicit target identities (default: top validators per mechanism group).
        #[arg(long, value_delimiter = ',')]
        targets: Vec<String>,
        #[arg(long, default_value_t = 2)]
        per_group: usize,
        #[arg(long, default_value_t = 3)]
        probes: usize,
        /// Send offset relative to the predicted (observed-frame) window start, ms.
        #[arg(long, default_value_t = 100, allow_hyphen_values = true)]
        offset_ms: i64,
        #[arg(long, default_value_t = 100)]
        blockhash_age_slots: u64,
        #[arg(long, default_value_t = 12)]
        max_targets: usize,
    },
    /// Generate N payer keypairs into a (writable) directory. Writes keys only, sends nothing.
    InitPayers {
        #[arg(long, env = "ITB_PAYER_DIR", default_value = "/keys/payers")]
        dir: PathBuf,
        #[arg(long, default_value_t = 24)]
        count: usize,
    },
    /// Live setup transactions (funding, sweeping, pre-registration memo). Each requires --live and the campaign cap.
    Setup {
        #[command(subcommand)]
        action: SetupAction,
        #[arg(long, global = true)]
        live: bool,
        #[arg(long, global = true)]
        max_spend_sol: Option<f64>,
        #[arg(long, env = "ITB_LEDGER", default_value = "state/ledger.sqlite", global = true)]
        ledger: PathBuf,
        #[arg(long, env = "ITB_KEYPAIR_PATH", global = true)]
        keypair: Option<PathBuf>,
        #[arg(long, env = "ITB_PAYER_DIR", default_value = "/keys/payers", global = true)]
        payer_dir: PathBuf,
    },
    /// Execute one stage of the frozen design against mainnet leader windows (dry-run by default).
    Run {
        #[arg(long)]
        live: bool,
        #[arg(long)]
        max_spend_sol: Option<f64>,
        #[arg(long, env = "ITB_LEDGER", default_value = "state/ledger.sqlite")]
        ledger: PathBuf,
        #[arg(long, env = "ITB_KEYPAIR_PATH")]
        keypair: Option<PathBuf>,
        #[arg(long, env = "ITB_PAYER_DIR", default_value = "/keys/payers")]
        payer_dir: PathBuf,
        #[arg(long, default_value = "design/design.jsonl")]
        design: PathBuf,
        /// Refuse to run unless the design file hashes to this (the pre-registered value).
        #[arg(long)]
        design_sha256: Option<String>,
        #[arg(long, default_value_t = 1)]
        stage: u8,
        #[arg(long, default_value = "data/raw")]
        out: PathBuf,
        #[arg(long, env = "ITB_PROGRESS", default_value = "state/progress.jsonl")]
        progress: PathBuf,
        #[arg(long, value_delimiter = ',')]
        targets: Vec<String>,
        #[arg(long, default_value_t = usize::MAX)]
        max_windows: usize,
        #[arg(long, default_value_t = 240)]
        max_minutes: u64,
        #[arg(long, default_value_t = 2)]
        concurrency: usize,
        #[arg(long, default_value_t = 0.0, allow_hyphen_values = true)]
        obs_lag_ms: f64,
        #[arg(long, default_value_t = 200.0)]
        nominal_slot_ms: f64,
        #[arg(long, env = "ITB_TPU_OVERRIDE")]
        tpu_override: Option<std::net::SocketAddr>,
    },
    /// Write the frozen experimental design (design.jsonl) for a target list.
    Design {
        /// JSON file with a list of TargetSpec objects.
        #[arg(long)]
        targets: PathBuf,
        #[arg(long)]
        seed: u64,
        #[arg(long)]
        out: PathBuf,
    },
    /// Show spend-ledger totals.
    Ledger {
        #[arg(long, env = "ITB_LEDGER", default_value = "state/ledger.sqlite")]
        ledger: PathBuf,
        #[arg(long)]
        max_spend_sol: f64,
    },
}

#[derive(Subcommand)]
enum SetupAction {
    /// Top every payer up to this many lamports.
    Fund {
        #[arg(long)]
        lamports_per_payer: u64,
    },
    /// Return all payer balances to the master (payer accounts close).
    Sweep,
    /// Post a text memo (the pre-registration hash) signed by the master.
    Memo {
        #[arg(long)]
        text: String,
    },
}

fn init_logging(json: Option<&PathBuf>) -> Result<()> {
    use tracing_subscriber::{EnvFilter, fmt, prelude::*};
    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    let stderr = fmt::layer().with_writer(std::io::stderr).with_target(false);
    let registry = tracing_subscriber::registry().with(filter).with(stderr);
    match json {
        Some(path) => {
            let file = std::fs::OpenOptions::new().create(true).append(true).open(path)?;
            registry.with(fmt::layer().json().with_writer(std::sync::Mutex::new(file))).init();
        }
        None => registry.init(),
    }
    Ok(())
}

fn derive_ws(rpc_url: &str) -> String {
    rpc_url.replacen("https://", "wss://", 1).replacen("http://", "ws://", 1)
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    init_logging(cli.log_json.as_ref())?;
    let rpc = Arc::new(rpc::Rpc::new(&cli.rpc_url));
    let ws_url = cli.ws_url.clone().unwrap_or_else(|| derive_ws(&cli.rpc_url));

    match cli.cmd {
        Cmd::Check => {
            let gate = alpenglow::require_active(&rpc).await?;
            let version = rpc.call("getVersion", serde_json::json!([])).await?;
            let clock = timing::SlotClock::start(&ws_url, timing::RunClock::new(), 200.0).await?;
            tokio::time::sleep(std::time::Duration::from_secs(3)).await;
            println!(
                "{}",
                serde_json::to_string_pretty(&serde_json::json!({
                    "rpc": smoke::redact_url(&cli.rpc_url),
                    "ws": smoke::redact_url(&ws_url),
                    "version": version,
                    "alpenglow": gate,
                    "latest_observed_slot": clock.latest_slot(),
                    "observed_slot_ms": clock.slot_ms_estimate(),
                }))?
            );
        }
        Cmd::Targets { per_group } => {
            let (validators, _) = targets::snapshot(&rpc).await?;
            let total: u64 = validators.iter().map(|v| v.activated_stake).sum();
            for v in targets::top_per_group(&validators, per_group.saturating_sub(1)) {
                println!(
                    "{:<34} {:>6.3}%  {:<22} {:<10} {}",
                    targets::group(&v),
                    v.activated_stake as f64 / total as f64 * 100.0,
                    v.tpu_quic.clone().unwrap_or_default(),
                    v.version,
                    v.identity
                );
            }
        }
        Cmd::ProbeTable => {
            for (name, t) in probe::library::ALL {
                println!(
                    "{name:3} L={:5} p={:>9} D={:>9} prio_fee={:5} total_fee={:5} cost={:6} P={:>9}",
                    t.cu_limit,
                    t.cu_price_micro_lamports,
                    t.loaded_data_limit,
                    t.priority_fee(),
                    t.total_fee(),
                    t.cost(),
                    t.agave_priority()
                );
            }
        }
        Cmd::Smoke { live, max_spend_sol, ledger, keypair, out, targets, per_group, probes, offset_ms, blockhash_age_slots, max_targets } => {
            if live {
                if let Some(dir) = ledger.parent() {
                    std::fs::create_dir_all(dir)?;
                }
            }
            smoke::run(
                rpc,
                &ws_url,
                smoke::SmokeArgs {
                    live,
                    max_spend_sol,
                    ledger,
                    keypair,
                    out,
                    targets,
                    per_group,
                    probes,
                    offset_ms,
                    blockhash_age_slots,
                    max_targets,
                },
            )
            .await?;
        }
        Cmd::Run {
            live,
            max_spend_sol,
            ledger,
            keypair,
            payer_dir,
            design,
            design_sha256,
            stage,
            out,
            progress,
            targets,
            max_windows,
            max_minutes,
            concurrency,
            obs_lag_ms,
            nominal_slot_ms,
            tpu_override,
        } => {
            for p in [&ledger, &progress] {
                if let Some(dir) = p.parent() {
                    std::fs::create_dir_all(dir)?;
                }
            }
            run::run(
                rpc,
                &ws_url,
                run::RunArgs {
                    live,
                    max_spend_sol,
                    ledger,
                    keypair,
                    payer_dir,
                    design,
                    design_sha256,
                    stage,
                    out,
                    progress,
                    targets,
                    max_windows,
                    max_minutes,
                    concurrency,
                    obs_lag_ms,
                    nominal_slot_ms,
                    tpu_override,
                },
            )
            .await?;
        }
        Cmd::InitPayers { dir, count } => {
            for pk in setup::init_payers(&dir, count)? {
                println!("{pk}");
            }
        }
        Cmd::Setup { action, live, max_spend_sol, ledger, keypair, payer_dir } => {
            let gate = alpenglow::require_active(&rpc).await?;
            let cap = auth::sol_to_lamports(max_spend_sol.ok_or_else(|| anyhow::anyhow!("setup requires --max-spend-sol"))?)?;
            if let Some(dir) = ledger.parent() {
                std::fs::create_dir_all(dir)?;
            }
            let l = ledger::Ledger::open(&ledger, cap)?;
            let live_auth = auth::LiveAuthorization::grant(live, max_spend_sol, &gate, &l)?;
            let master = keys::read_keypair(&keypair.ok_or_else(|| anyhow::anyhow!("setup requires --keypair / ITB_KEYPAIR_PATH"))?)?;
            match action {
                SetupAction::Fund { lamports_per_payer } => setup::fund(&rpc, &l, &live_auth, &master, &payer_dir, lamports_per_payer).await?,
                SetupAction::Sweep => {
                    use solana_signer::Signer;
                    setup::sweep(&rpc, &l, &live_auth, &master.pubkey(), &payer_dir).await?
                }
                SetupAction::Memo { text } => println!("{}", setup::memo(&rpc, &l, &live_auth, &master, &text).await?),
            }
            println!("{}", serde_json::to_string_pretty(&l.totals()?)?);
        }
        Cmd::Design { targets, seed, out } => {
            let specs: Vec<design::TargetSpec> = serde_json::from_str(&std::fs::read_to_string(&targets)?)?;
            let plans = design::generate(seed, &specs);
            let file = store::Jsonl::open(&out)?;
            for p in &plans {
                file.append(p)?;
            }
            let worst: u64 = plans.iter().map(design::max_fee).sum();
            let bytes = std::fs::read(&out)?;
            use sha2::Digest;
            println!(
                "{} windows, worst-case fees {} lamports ({:.4} SOL), sha256 {:x}",
                plans.len(),
                worst,
                worst as f64 / 1e9,
                sha2::Sha256::digest(&bytes)
            );
        }
        Cmd::Ledger { ledger, max_spend_sol } => {
            let l = ledger::Ledger::open(&ledger, auth::sol_to_lamports(max_spend_sol)?)?;
            println!("{}", serde_json::to_string_pretty(&l.totals()?)?);
        }
    }
    Ok(())
}
