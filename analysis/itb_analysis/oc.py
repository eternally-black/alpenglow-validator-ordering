"""Operating characteristics of the pre-registered procedure (PLAN §4.4, docs/POWER.md).

For each declared scenario: simulate the frozen design R times, apply the pre-registered stopping rule with the very
predicate `itb run` uses (`stop_informative`), and score the **published claim** of every target — the output of
`report.analyse`, the same function that produces REPORT.md: design validation, eligibility, (client, ingress)
grouping, the 36-effect inference, the strictness gate, the selection check and the §9 gates (positive controls,
buffer assumption). The positive controls (direct Agave / Firedancer core targets) follow their known reward/cost rule
in every scenario; every other target follows the scenario's mechanism. The simulator also injects observation
failures (failed streams, unproduced windows, gossip transitions), so eligibility and stopping are exercised.

Scoring against an explicit truth table:
- correct: the claim names the true mechanism;
- acceptable: an honest non-claim ("none", "unidentified…", a withdrawn claim) or an under-claim (`partial:R` when the
  truth is R) — not a full detection, not a falsehood;
- wrong: anything else (a rule or mixture the scenario does not contain).
"Any core target wrong" = the share of replicate campaigns in which at least one core target got a wrong claim, with an
exact 95 % upper bound; "robust wrong" counts wrong claims that also survive the worst-case selection bounds.

`--estimand censored` scores the censored-coding sensitivity on the raw verdict instead (a comparison of codings, not
the published procedure).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import outcomes, report, stats
from .load import load_designs, load_run
from .sim import Params, simulate

NONCLAIMS = ("none", "unidentified", "unidentified:selection")
CONTROL_CLIENTS = ("Agave", "Firedancer")

#: scenario -> (Params overrides, correct claims, additionally acceptable claims)
SCENARIOS: dict[str, tuple[dict, tuple[str, ...], tuple[str, ...]]] = {
    "reward_cost_greedy": ({}, ("reward_cost",), NONCLAIMS),
    "reward_cost_batch_20": ({"scenario": "reward_cost_batch", "t_ms": 20}, ("reward_cost",), NONCLAIMS),
    "cu_price_batch_20": ({"scenario": "cu_price_batch", "t_ms": 20}, ("cu_price",), NONCLAIMS),
    "cu_price_batch_50": ({"scenario": "cu_price_batch", "t_ms": 50}, ("cu_price",), NONCLAIMS),
    "cu_price_fifo_tie": ({"t_ms": 50}, ("cu_price",), NONCLAIMS),
    "lamport_fee_batch_50": ({"scenario": "lamport_fee_batch", "t_ms": 50}, ("lamport_fee",), NONCLAIMS),
    "fifo": ({}, ("fifo",), NONCLAIMS),
    "random": ({}, ("none",), ("unidentified", "unidentified:selection")),
    "streaming_pacing": ({}, ("reward_cost",), NONCLAIMS),
    "fifo_reorder": ({}, ("none",), ("unidentified", "fifo", "partial:fifo")),
    "label_blind_reorder": ({"reverse_q": 0.35}, ("fifo", "partial:fifo"), NONCLAIMS),
    "selective_drop_cu_price": ({"scenario": "selective_drop", "base": "cu_price_batch", "drop_q": 0.5}, ("cu_price",), NONCLAIMS),
    "correlated_pair_loss": ({"loss_q": 0.8}, ("unidentified:selection",), ("none", "unidentified", "fifo")),
    "balanced_double_loss": ({}, ("none", "unidentified", "unidentified:selection"), ()),
    "mode_switch_rc_fifo": ({"scenario": "mode_switch", "base": "reward_cost_greedy", "mode_b": "fifo"},
                            ("mixed:fifo+reward_cost", "partial:reward_cost", "partial:fifo"), ("none", "unidentified")),
    "low_landing_reward_cost": ({"scenario": "reward_cost_greedy", "landing": 0.5}, ("reward_cost",), NONCLAIMS),
    "low_landing_cu_price": ({"scenario": "cu_price_batch", "t_ms": 20, "landing": 0.5}, ("cu_price",), NONCLAIMS),
}

#: Pre-registered stopping (PREREGISTRATION §5): stop a target once each of C1, C2, C3 has this many informative pairs.
INFORMATIVE_TARGET = {"core": 40, "extended": 20}


def stop_seq(pairs, tiers: dict[str, str]) -> dict[str, int]:
    """Per target, the last plan sequence `itb run` would execute: windows in order until every main contrast has its
    informative target, counted with the shared predicate (`stop_informative`: all planned probes sent without error,
    the target produced a block, both members landed — gossip stability is not part of it)."""
    last = {}
    for target, g in pairs.groupby("target_identity"):
        need = INFORMATIVE_TARGET.get(tiers.get(target, "core"), 40)
        counts = {"c1": 0, "c2": 0, "c3": 0}
        for seq, w in g.sort_values("seq").groupby("seq", sort=True):
            last[target] = int(seq)
            for _, r in w[w["pair_kind"].isin(counts)].iterrows():
                counts[r["pair_kind"]] += bool(r["stop_informative"])
            if min(counts.values()) >= need:
                break
    return last


def truncate(run_dir: Path, last: dict[str, int]) -> None:
    """Rewrites a simulated run so it holds only the windows executed before stopping."""
    def keep(target: str | None, seq) -> bool:
        return target in last and seq is not None and int(seq) <= last[target]

    probes = [json.loads(l) for l in (run_dir / "probes.jsonl").read_text().splitlines() if l.strip()]
    kept = {p["probe_id"] for p in probes if keep(p["target_identity"], p["seq"])}
    for name, pick in (("probes.jsonl", lambda r: r["probe_id"] in kept),
                       ("windows.jsonl", lambda r: keep(r["target_identity"], r["seq"])),
                       ("outcomes.jsonl", lambda r: r["outcome"]["probe_id"] in kept),
                       ("sends.jsonl", lambda r: r["record"]["probe_id"] in kept)):
        rows = [l for l in (run_dir / name).read_text().splitlines() if l.strip() and pick(json.loads(l))]
        (run_dir / name).write_text("".join(r + "\n" for r in rows))


def sim_manifest(targets: list[dict], design: Path) -> dict:
    core = [t for t in targets if t.get("tier", "core") == "core"]
    return {
        "design_sha256": hashlib.sha256(Path(design).read_bytes()).hexdigest(),
        "core_targets": [{"identity": t["identity"], "client_id": t["client_id"], "ingress": t["ingress"]} for t in core],
        "positive_controls": [t["identity"] for t in core if t["client_id"] in CONTROL_CLIENTS and t["ingress"] == "direct"],
    }


def _claim(v: dict) -> str:
    c = v["published_claim"]
    if c.startswith("withdrawn"):
        return "withdrawn"
    return c.removeprefix("exploratory: ").removesuffix(report.ASSUMES_SELECTION)


def _replicate(job: tuple) -> dict[str, dict]:
    """One simulated campaign, scored on its published claims (a process-pool worker)."""
    design, targets_path, scenario, over, seed, n_draws, estimand = job
    targets = json.loads(Path(targets_path).read_text())
    tiers = {t["identity"]: t.get("tier", "core") for t in targets}
    manifest = sim_manifest(targets, design)
    designs = load_designs([design])
    params = Params(scenario=scenario, seed=seed, controls=tuple(manifest["positive_controls"]), **over)
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        simulate(design, targets_path, d, params, stage=1)
        full = outcomes.pair_table(load_run(d), designs=designs)
        truncate(d, stop_seq(full, tiers))
        if estimand != "cc":
            pairs = outcomes.pair_table(load_run(d), designs=designs)
            out = {}
            for target, g in pairs.groupby("target_identity"):
                eff = stats.validator_effects(g, n_draws=n_draws, estimand=estimand)
                out[target] = {"claim": eff["diagnosis"]["verdict"], "robust": None, "n_c1": eff["label"]["c1"].n,
                               "windows": int(g["seq"].nunique()), "control": target in manifest["positive_controls"]}
            return out
        res = report.analyse([d], manifest, designs, n_draws=n_draws, sensitivities=False)
        out = {}
        for v in res["validators"].values():
            t = v["target_identity"]
            # a target seen in several groups is scored on its confirmatory group (core) or its largest group
            prev = out.get(t)
            if prev and (prev["confirmatory"] or prev["n_c1"] >= v["label"]["c1"]["n"]) and not v["confirmatory"]:
                continue
            out[t] = {"claim": _claim(v), "robust": v["diagnosis"].get("selection_robust"), "n_c1": v["label"]["c1"]["n"],
                      "windows": None, "control": v["positive_control"], "confirmatory": v["confirmatory"]}
        return out


def _upper95(k: int, n: int) -> float:
    return 1.0 if n == 0 else float(stats.clopper_pearson(k, n, 0.10)[1])


def run(design: Path, targets: Path, reps: int, n_draws: int, seed0: int = 1000, estimand: str = "cc",
        only: list[str] | None = None, jobs: int = 1) -> dict:
    """Replicate r of every scenario uses seed seed0 + r, so results do not depend on `jobs`."""
    tiers = {t["identity"]: t.get("tier", "core") for t in json.loads(Path(targets).read_text())}
    results: dict[str, dict] = {}
    pool = ProcessPoolExecutor(max_workers=jobs) if jobs > 1 else None
    try:
        for name, (over, correct, acceptable) in SCENARIOS.items():
            if only and name not in only:
                continue
            over = dict(over)
            scenario = over.pop("scenario", name)
            batch = [(design, targets, scenario, over, seed0 + r, n_draws, estimand) for r in range(reps)]
            replicates = list(pool.map(_replicate, batch)) if pool else [_replicate(j) for j in batch]
            claims: Counter = Counter()
            by_tier: dict[str, Counter] = defaultdict(Counter)
            controls_ok, family_wrong, robust_wrong = 0, 0, 0
            n_obs = []
            for per_target in replicates:
                any_core_wrong = any_robust_wrong = False
                ctrl = [r for r in per_target.values() if r["control"]]
                controls_ok += bool(ctrl) and all(r["claim"] in report.CONTROL_PASS for r in ctrl)
                for target, res in per_target.items():
                    if res["control"]:
                        continue  # controls follow reward/cost in every scenario; scored separately
                    c = res["claim"]
                    claims[c] += 1
                    tier = tiers.get(target, "core")
                    # partial:R when the truth is R is an under-claim (R's key named, majority not proven), not a falsehood
                    under = tuple(f"partial:{r}" for r in correct if not r.startswith(("partial:", "mixed:")))
                    cls = "correct" if c in correct else "acceptable" if c in acceptable + under + ("withdrawn",) else "wrong"
                    by_tier[tier][cls] += 1
                    by_tier[tier]["n"] += 1
                    any_core_wrong |= tier == "core" and cls == "wrong"
                    any_robust_wrong |= tier == "core" and cls == "wrong" and res["robust"] is True
                    n_obs.append(res["n_c1"])
                family_wrong += any_core_wrong
                robust_wrong += any_robust_wrong
            total = sum(claims.values()) or 1
            median = lambda xs: sorted(xs)[len(xs) // 2] if xs else 0
            results[name] = {
                "correct": list(correct),
                "claims": {k: v / total for k, v in claims.most_common()},
                "by_tier": {t: {k: c[k] / c["n"] for k in ("correct", "acceptable", "wrong")} | {"n": c["n"]} for t, c in by_tier.items()},
                "family_wrong_rate": family_wrong / reps,
                "family_wrong_upper95": _upper95(family_wrong, reps),
                "family_robust_wrong_rate": robust_wrong / reps,
                "controls_pass_rate": controls_ok / reps,
                "median_pairs_c1": median(n_obs),
                "reps": reps,
                "estimand": estimand,
            }
            print(name, json.dumps(results[name]), flush=True)
    finally:
        if pool:
            pool.shutdown()
    return results


def markdown_table(results: dict) -> str:
    """The POWER.md table: per scenario, core-tier claim classes, family-wise wrong rate (with its exact 95 % upper
    bound), wrong claims that survive the worst-case selection bounds, positive-control pass rate and sample size."""
    pct = lambda x: f"{100 * x:.0f} %"
    rows = ["| Scenario | True mechanism | Correct | Honest non-claim | Wrong | Any core target wrong (≤ 95 % bound) | "
            "Robust wrong | Controls pass | Median C1 pairs |",
            "|---|---|---|---|---|---|---|---|---|"]
    for name, r in results.items():
        core = r["by_tier"].get("core", {"correct": 0, "acceptable": 0, "wrong": 0})
        rows.append(f"| `{name}` | {' / '.join(r['correct'])} | {pct(core['correct'])} | {pct(core['acceptable'])} | "
                    f"{pct(core['wrong'])} | {pct(r['family_wrong_rate'])} (≤ {pct(r['family_wrong_upper95'])}) | "
                    f"{pct(r['family_robust_wrong_rate'])} | {pct(r['controls_pass_rate'])} | {r['median_pairs_c1']} |")
    return "\n".join(rows) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--design", type=Path)
    ap.add_argument("--targets", type=Path)
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--n-draws", type=int, default=2_000)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--estimand", choices=sorted(stats.ESTIMANDS), default="cc",
                    help="cc = the published procedure; censored = the censored-coding sensitivity (raw verdict)")
    ap.add_argument("--markdown", type=Path, default=None, help="also write the POWER.md table here")
    ap.add_argument("--from-json", type=Path, default=None, help="render --markdown from an earlier --out file")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="worker processes (results do not depend on it)")
    ap.add_argument("--scenarios", nargs="*", choices=sorted(SCENARIOS), default=None)
    a = ap.parse_args()
    if a.from_json:
        res = json.loads(a.from_json.read_text())
    else:
        if not (a.design and a.targets):
            ap.error("--design and --targets are required unless --from-json is given")
        res = run(a.design, a.targets, a.reps, a.n_draws, estimand=a.estimand, only=a.scenarios, jobs=a.jobs)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(res, indent=1))
    if a.markdown:
        a.markdown.write_text(markdown_table(res), encoding="utf-8")


if __name__ == "__main__":
    main()

