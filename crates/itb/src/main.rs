//! `itb` — Inside the Block. Measures how Solana mainnet leaders order transactions in their blocks, using probe
//! transactions we send ourselves. Dry-run unless `--live` and `--max-spend-sol` are given.

mod alpenglow;
mod auth;
mod campaign;
mod collect;
mod design;
mod keys;
mod ledger;
mod probe;
mod quic;
mod recover;
mod rpc;
mod run;
mod setup;
mod smoke;
mod store;
mod targets;
mod timing;

use anyhow::{Context, Result, bail};
use clap::{Parser, Subcommand};
use std::path::PathBuf;
use std::sync::Arc;

#[derive(Parser)]
#[command(
    name = "itb",
    version,
    about = "Inside the Block — Solana intra-block ordering measurement"
)]
struct Cli {
    /// JSON-RPC endpoint. Only `scheme://host` of it ever reaches a log or data file.
    #[arg(
        long,
        env = "RPC_URL",
        default_value = "https://api.mainnet-beta.solana.com",
        global = true
    )]
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
    /// Check the Alpenglow gate, the cluster identity and RPC/WebSocket reachability.
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
        /// Payer directory (part of the campaign's owned-account set; smoke itself signs with the master).
        #[arg(long, env = "ITB_PAYER_DIR", default_value = "/keys/payers")]
        payer_dir: PathBuf,
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
        /// Sub-budget for the smoke test inside the campaign cap (defined once in the ledger).
        #[arg(long, default_value_t = 0.001)]
        budget_sol: f64,
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
        #[arg(
            long,
            env = "ITB_LEDGER",
            default_value = "state/ledger.sqlite",
            global = true
        )]
        ledger: PathBuf,
        #[arg(long, env = "ITB_KEYPAIR_PATH", global = true)]
        keypair: Option<PathBuf>,
        #[arg(
            long,
            env = "ITB_PAYER_DIR",
            default_value = "/keys/payers",
            global = true
        )]
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
        /// Attempt journal. Defaults to state/progress.jsonl for live runs and state/progress.dryrun.jsonl for dry runs.
        #[arg(long, env = "ITB_PROGRESS")]
        progress: Option<PathBuf>,
        #[arg(long, value_delimiter = ',')]
        targets: Vec<String>,
        #[arg(long, default_value_t = usize::MAX)]
        max_windows: usize,
        #[arg(long, default_value_t = 240)]
        max_minutes: u64,
        /// Campaign cutoff (RFC 3339, e.g. 2026-10-29T23:59:00Z): nothing is prepared or sent after it.
        #[arg(long)]
        not_after: Option<String>,
        #[arg(long, default_value_t = 2)]
        concurrency: usize,
        #[arg(long, default_value_t = 0.0, allow_hyphen_values = true)]
        obs_lag_ms: f64,
        #[arg(long, default_value_t = 200.0)]
        nominal_slot_ms: f64,
        #[arg(long, value_enum, default_value_t = timing::AnchorEvent::FirstShred)]
        anchor_event: timing::AnchorEvent,
        #[arg(long, default_value_t = 20.0)]
        max_lateness_ms: f64,
        /// Sub-budget name for this run's probes (e.g. pilot, stage1, stage2) and, the first time, its cap.
        #[arg(long, default_value = "campaign")]
        budget: String,
        #[arg(long)]
        budget_sol: Option<f64>,
        /// Allow a non-mainnet cluster (localnet tests only).
        #[arg(long)]
        allow_non_mainnet: bool,
        #[arg(long, env = "ITB_TPU_OVERRIDE")]
        tpu_override: Option<std::net::SocketAddr>,
    },
    /// Resolve every open reservation on chain evidence (after a crash or timeout) and restore each probe's outcome and
    /// landing block into its original run directory.
    Reconcile {
        #[arg(long, env = "ITB_LEDGER", default_value = "state/ledger.sqlite")]
        ledger: PathBuf,
        #[arg(long)]
        max_spend_sol: f64,
        #[arg(long, env = "ITB_KEYPAIR_PATH")]
        keypair: Option<PathBuf>,
        #[arg(long, env = "ITB_PAYER_DIR", default_value = "/keys/payers")]
        payer_dir: PathBuf,
        /// Where the original runs live (`data/raw` for `itb run`, `data/smoke` for smoke runs).
        #[arg(long, value_delimiter = ',', default_value = "data/raw,data/smoke")]
        runs: Vec<PathBuf>,
        /// Attempt journal that receives a terminal record for each restored window.
        #[arg(long, env = "ITB_PROGRESS", default_value = "state/progress.jsonl")]
        progress: PathBuf,
    },
    /// Write the frozen experimental design (design.jsonl) for a target list. Refuses to overwrite.
    Design {
        /// JSON file with a list of TargetSpec objects.
        #[arg(long)]
        targets: PathBuf,
        #[arg(long)]
        seed: u64,
        #[arg(long)]
        out: PathBuf,
        /// 1: the Study 1 generator (frozen design/design.jsonl); 2: Study 2 (docs/STUDY2-PLAN.md).
        #[arg(long, default_value_t = 1, value_parser = clap::value_parser!(u8).range(1..=2))]
        study: u8,
    },
    /// Show spend-ledger totals and open reservations.
    Ledger {
        #[arg(long, env = "ITB_LEDGER", default_value = "state/ledger.sqlite")]
        ledger: PathBuf,
        #[arg(long)]
        max_spend_sol: f64,
        /// Record an external top-up of the owned accounts (keeps on-chain reconciliation exact).
        #[arg(long)]
        add_deposit_lamports: Option<u64>,
        /// On a fresh ledger: record what earlier studies cost, so this ledger's cap covers them too.
        #[arg(long, requires = "carry_over_reason")]
        carry_over_lamports: Option<u64>,
        /// Where the carried-over spend is documented.
        #[arg(long, requires = "carry_over_lamports")]
        carry_over_reason: Option<String>,
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
            let file = std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(path)?;
            registry
                .with(fmt::layer().json().with_writer(std::sync::Mutex::new(file)))
                .init();
        }
        None => registry.init(),
    }
    Ok(())
}

fn derive_ws(rpc_url: &str) -> String {
    rpc_url
        .replacen("https://", "wss://", 1)
        .replacen("http://", "ws://", 1)
}

fn ensure_parent(p: &std::path::Path) -> Result<()> {
    if let Some(dir) = p.parent().filter(|d| !d.as_os_str().is_empty()) {
        std::fs::create_dir_all(dir)?;
    }
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    init_logging(cli.log_json.as_ref())?;
    let rpc = Arc::new(rpc::Rpc::new(&cli.rpc_url));
    let ws_url = cli
        .ws_url
        .clone()
        .unwrap_or_else(|| derive_ws(&cli.rpc_url));

    match cli.cmd {
        Cmd::Check => {
            let gate = alpenglow::require_active(&rpc).await?;
            let version = rpc.call("getVersion", serde_json::json!([])).await?;
            let genesis = rpc.genesis_hash().await?;
            let clock = timing::SlotClock::start(
                &ws_url,
                timing::RunClock::new(),
                200.0,
                timing::AnchorEvent::FirstShred,
            )
            .await?;
            tokio::time::sleep(std::time::Duration::from_secs(5)).await;
            println!(
                "{}",
                serde_json::to_string_pretty(&serde_json::json!({
                    "rpc": rpc::redact_url(&cli.rpc_url),
                    "ws": rpc::redact_url(&ws_url),
                    "version": version,
                    "genesis_hash": genesis,
                    "is_mainnet_beta": genesis == rpc::MAINNET_GENESIS_HASH,
                    "alpenglow": gate,
                    "latest_observed_slot": clock.latest_slot(),
                    "anchor_event": clock.anchor_kind(),
                    "cadence": clock.cadence(),
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
            use probe::library::*;
            for (c, x, y) in [
                ("C1", ("A", A), ("B", B)),
                ("C2", ("A'", A_PRIME), ("B", B)),
                ("C3", ("A", A), ("A'", A_PRIME)),
            ] {
                let preds: Vec<String> = probe::Rule::ALL
                    .iter()
                    .map(|r| format!("{r:?}={:?}", probe::predict(*r, &x.1, &y.1)))
                    .collect();
                println!("{c} {} vs {}: {}", x.0, y.0, preds.join(" "));
            }
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
        Cmd::Smoke {
            live,
            max_spend_sol,
            ledger,
            keypair,
            payer_dir,
            out,
            targets,
            per_group,
            probes,
            offset_ms,
            blockhash_age_slots,
            max_targets,
            budget_sol,
        } => {
            if probes == 0 || probes > quic::MAX_STREAMS_PER_100MS {
                bail!("--probes must be 1..={}", quic::MAX_STREAMS_PER_100MS);
            }
            smoke::run(
                rpc,
                &ws_url,
                smoke::SmokeArgs {
                    live,
                    max_spend_sol,
                    ledger,
                    keypair,
                    payer_dir,
                    out,
                    targets,
                    per_group,
                    probes,
                    offset_ms,
                    blockhash_age_slots,
                    max_targets,
                    budget_sol,
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
            not_after,
            concurrency,
            obs_lag_ms,
            nominal_slot_ms,
            anchor_event,
            max_lateness_ms,
            budget,
            budget_sol,
            allow_non_mainnet,
            tpu_override,
        } => {
            let progress = progress.unwrap_or_else(|| {
                PathBuf::from(if live {
                    "state/progress.jsonl"
                } else {
                    "state/progress.dryrun.jsonl"
                })
            });
            let not_after_unix = not_after
                .map(|s| {
                    time::OffsetDateTime::parse(&s, &time::format_description::well_known::Rfc3339)
                        .map(|t| t.unix_timestamp())
                        .with_context(|| format!("--not-after {s}: expected RFC 3339"))
                })
                .transpose()?;
            for p in [&ledger, &progress] {
                ensure_parent(p)?;
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
                    not_after_unix,
                    concurrency,
                    obs_lag_ms,
                    nominal_slot_ms,
                    anchor_event,
                    max_lateness_ms,
                    budget,
                    budget_cap_sol: budget_sol,
                    require_mainnet: !allow_non_mainnet,
                    tpu_override,
                },
            )
            .await?;
        }
        Cmd::Reconcile {
            ledger,
            max_spend_sol,
            keypair,
            payer_dir,
            runs,
            progress,
        } => {
            let gate = alpenglow::require_active(&rpc).await?;
            ensure_parent(&progress)?;
            // Reconciliation is itself checked: a balance drop the ledger cannot explain is charged before anything.
            let c = campaign::Campaign::open(
                &rpc,
                &gate,
                campaign::OpenArgs {
                    ledger: &ledger,
                    max_spend_sol: Some(max_spend_sol),
                    keypair: keypair.as_deref(),
                    payer_dir: &payer_dir,
                    holder: "reconcile",
                },
            )
            .await?;
            let report = recover::reconcile(&rpc, &c, &runs, &progress).await?;
            c.reconcile_now(&rpc).await?;
            println!("{}", serde_json::to_string_pretty(&report)?);
        }
        Cmd::InitPayers { dir, count } => {
            for pk in setup::init_payers(&dir, count)? {
                println!("{pk}");
            }
        }
        Cmd::Setup {
            action,
            live,
            max_spend_sol,
            ledger,
            keypair,
            payer_dir,
        } => {
            if !live {
                bail!("setup sends transactions: it requires --live");
            }
            let gate = alpenglow::require_active(&rpc).await?;
            let c = campaign::Campaign::open(
                &rpc,
                &gate,
                campaign::OpenArgs {
                    ledger: &ledger,
                    max_spend_sol,
                    keypair: keypair.as_deref(),
                    payer_dir: &payer_dir,
                    holder: "setup",
                },
            )
            .await?;
            c.budget("setup", Some(setup::SETUP_BUDGET_SOL))?;
            let master =
                keys::read_keypair(&keypair.ok_or_else(|| {
                    anyhow::anyhow!("setup requires --keypair / ITB_KEYPAIR_PATH")
                })?)?;
            match action {
                SetupAction::Fund { lamports_per_payer } => {
                    // A transfer to a payer with a pending probe would write-lock an account that probe uses.
                    c.refuse_if_payers_leased()?;
                    setup::fund(
                        &rpc,
                        &c.ledger,
                        &c.auth,
                        &master,
                        &payer_dir,
                        lamports_per_payer,
                    )
                    .await?
                }
                SetupAction::Sweep => {
                    c.refuse_if_payers_leased()?;
                    setup::sweep(&rpc, &c.ledger, &c.auth, &c.master, &payer_dir).await?
                }
                SetupAction::Memo { text } => println!(
                    "{}",
                    setup::memo(&rpc, &c.ledger, &c.auth, &master, &text).await?
                ),
            }
            c.reconcile_now(&rpc).await?;
            println!("{}", serde_json::to_string_pretty(&c.ledger.totals()?)?);
        }
        Cmd::Design {
            targets,
            seed,
            out,
            study,
        } => {
            let specs: Vec<design::TargetSpec> =
                serde_json::from_str(&std::fs::read_to_string(&targets)?)?;
            let plans = if study == 2 {
                design::generate_study2(seed, &specs)?
            } else {
                design::generate(seed, &specs)
            };
            design::validate(&plans)?;
            let mut text = String::new();
            for p in &plans {
                text.push_str(&serde_json::to_string(p)?);
                text.push('\n');
            }
            // Never append: a design is written once, whole, and then frozen.
            use std::io::Write;
            let mut f = std::fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&out)
                .with_context(|| {
                    format!(
                        "{} exists; a design is never overwritten or appended",
                        out.display()
                    )
                })?;
            f.write_all(text.as_bytes())?;
            f.sync_all()?;
            let worst: u64 = plans.iter().map(design::max_fee).sum();
            use sha2::Digest;
            println!(
                "{} windows, worst-case fees {} lamports ({:.4} SOL), sha256 {:x}",
                plans.len(),
                worst,
                worst as f64 / 1e9,
                sha2::Sha256::digest(text.as_bytes())
            );
        }
        Cmd::Ledger {
            ledger,
            max_spend_sol,
            add_deposit_lamports,
            carry_over_lamports,
            carry_over_reason,
        } => {
            // Recording a deposit or a carry-over writes the ledger: hold the campaign lock for it.
            let _lock = (add_deposit_lamports.is_some() || carry_over_lamports.is_some())
                .then(|| campaign::CampaignLock::acquire(&ledger, "ledger-write"))
                .transpose()?;
            let l = ledger::Ledger::open(&ledger, auth::sol_to_lamports(max_spend_sol)?)?;
            if let (Some(n), Some(reason)) = (carry_over_lamports, &carry_over_reason) {
                l.record_carry_over(n, reason)?;
                println!("carry-over of {n} lamports recorded: {reason}");
            }
            if let Some(d) = add_deposit_lamports {
                println!(
                    "external deposits now {} lamports",
                    l.add_external_deposit(d)?
                );
            }
            println!("{}", serde_json::to_string_pretty(&l.totals()?)?);
            for r in l.open_reservations()? {
                println!(
                    "open: {} {} payer {} lvbh {}",
                    r.signature, r.label, r.payer, r.last_valid_block_height
                );
            }
        }
    }
    Ok(())
}
