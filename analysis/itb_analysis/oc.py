"""Operating characteristics of the pre-registered procedure (PLAN §4.4, docs/POWER.md).

For each declared scenario: simulate the frozen design R times, run the real analysis, and tabulate per target how
often each rule ends SUPPORTED/CONFIRMED, REJECTED or UNDETERMINED. The "right" answer per scenario is stated next to
it; look-alike scenarios whose correct answer is "unidentified" are included on purpose.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from . import outcomes, stats
from .load import load_run
from .sim import Params, simulate

#: scenario name -> (Params overrides, expected answer for the pre-registered rule set)
SCENARIOS: dict[str, tuple[dict, str]] = {
    "reward_cost_greedy": ({}, "reward_cost"),
    "reward_cost_batch_20": ({"scenario": "reward_cost_batch", "t_ms": 20}, "reward_cost"),
    "cu_price_batch_20": ({"scenario": "cu_price_batch", "t_ms": 20}, "cu_price"),
    "cu_price_batch_50": ({"scenario": "cu_price_batch", "t_ms": 50}, "cu_price"),
    "lamport_fee_batch_50": ({"scenario": "lamport_fee_batch", "t_ms": 50}, "lamport_fee"),
    "fifo": ({}, "fifo"),
    "random": ({}, "none"),
    "streaming_pacing": ({}, "reward_cost"),
    "fifo_reorder": ({}, "fifo"),
    "selective_drop_cu_price": ({"scenario": "selective_drop", "base": "cu_price_batch", "drop_q": 0.5}, "cu_price"),
    "mode_switch_rc_fifo": ({"scenario": "mode_switch", "base": "reward_cost_greedy", "mode_b": "fifo"}, "mixed"),
    "low_landing_reward_cost": ({"scenario": "reward_cost_greedy", "landing": 0.5}, "reward_cost"),
    "low_landing_cu_price": ({"scenario": "cu_price_batch", "t_ms": 20, "landing": 0.5}, "cu_price"),
}

SUPPORT = ("SUPPORTED", "CONFIRMED")


#: Pre-registered stopping (PREREGISTRATION §5): stop a target once *each* of C1, C2, C3 has this many evaluable
#: pairs with both members landed, or when its attempted K-windows run out (the design holds 2x the target).
INFORMATIVE_TARGET = {"core": 40, "extended": 20}


def apply_stopping(pairs, tiers: dict[str, str]):
    """Keep each target's K-windows in execution order until every main contrast has reached its informative target."""
    keep = []
    for target, g in pairs.groupby("target_identity"):
        need = INFORMATIVE_TARGET.get(tiers.get(target, "core"), 40)
        counts = {"c1": 0, "c2": 0, "c3": 0}
        for _, w in g.sort_values("seq").groupby("seq", sort=True):
            if min(counts.values()) >= need:
                break
            keep.append(w)
            for _, r in w[w["pair_kind"].isin(counts)].iterrows():
                counts[r["pair_kind"]] += bool(r["both_landed"] and r["evaluable"])
    return outcomes.pd.concat(keep, ignore_index=True) if keep else pairs.iloc[0:0]


def analyse_dir(run_dir: Path, n_draws: int, tiers: dict[str, str] | None = None) -> dict[str, dict]:
    run = load_run(run_dir)
    pairs = outcomes.pair_table(run)
    if tiers is not None:
        pairs = apply_stopping(pairs, tiers)
    per_target = {}
    for target, g in pairs.groupby("target_identity"):
        eff = stats.validator_effects(g, n_draws=n_draws)
        per_target[target] = {r: v["status"] for r, v in eff["rules"].items()}
        per_target[target]["_n"] = {c: eff["label"][c].n for c in ("c1", "c2", "c3")}
        per_target[target]["_windows"] = int(g["seq"].nunique())
    return per_target


def run(design: Path, targets: Path, reps: int, windows_per_target: int | None, n_draws: int, seed0: int = 1000) -> dict:
    tiers = {t["identity"]: t.get("tier", "core") for t in json.loads(Path(targets).read_text())}
    results: dict[str, dict] = {}
    for name, (over, expected) in SCENARIOS.items():
        over = dict(over)
        scenario = over.pop("scenario", name)
        tally: dict[str, Counter] = defaultdict(Counter)
        by_tier: dict[str, Counter] = defaultdict(Counter)
        n_obs, windows_used = [], []
        for r in range(reps):
            params = Params(scenario=scenario, seed=seed0 + r, **over)
            with tempfile.TemporaryDirectory() as tmp:
                simulate(design, targets, Path(tmp), params, stage=1, windows_per_target=windows_per_target)
                per_target = analyse_dir(Path(tmp), n_draws, tiers)
            for target, statuses in per_target.items():
                n_obs.append(statuses.pop("_n"))
                windows_used.append(statuses.pop("_windows"))
                supported = [rule for rule, s in statuses.items() if s in SUPPORT and rule != "random"]
                label = ",".join(sorted(supported)) or "none"
                tally["supported:" + label][target] += 1
                tier = tiers.get(target, "core")
                by_tier[tier]["n"] += 1
                by_tier[tier]["correct"] += label == expected or (expected == "none" and label == "none")
                by_tier[tier]["wrong_rule"] += label not in ("none", expected)
                if expected in statuses:
                    tally["expected_rejected"][target] += statuses[expected] == "REJECTED"
                tally["random_not_rejected"][target] += statuses["random"] != "REJECTED"
                tally["targets"][target] += 1
        total = sum(tally["targets"].values())
        summary = {
            "expected": expected,
            "target_runs": total,
            "outcomes": {k.removeprefix("supported:"): sum(v.values()) / total for k, v in tally.items() if k.startswith("supported:")},
            "expected_rule_rejected_rate": sum(tally["expected_rejected"].values()) / total,
            "random_not_rejected_rate": sum(tally["random_not_rejected"].values()) / total,
            "median_windows_per_contrast": sorted(n["c1"] for n in n_obs)[len(n_obs) // 2] if n_obs else 0,
            "median_windows_attempted": sorted(windows_used)[len(windows_used) // 2] if windows_used else 0,
            "by_tier": {t: {"correct": c["correct"] / c["n"], "wrong_rule": c["wrong_rule"] / c["n"], "n": c["n"]} for t, c in by_tier.items()},
        }
        results[name] = summary
        print(name, json.dumps(summary))
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--design", required=True, type=Path)
    ap.add_argument("--targets", required=True, type=Path)
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--windows-per-target", type=int, default=None)
    ap.add_argument("--n-draws", type=int, default=2_000)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    res = run(a.design, a.targets, a.reps, a.windows_per_target, a.n_draws)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
