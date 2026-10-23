"""Operating characteristics of the pre-registered procedure (PLAN §4.4, docs/POWER.md).

For each declared scenario: simulate the frozen design R times, run the *same* analysis object the report publishes
(`stats.validator_effects(...)["diagnosis"]`, after the pre-registered stopping rule), and score each target's
verdict against an explicit truth table:
- correct: the verdict names the true mechanism;
- acceptable: an honest non-claim ("none", "unidentified…") — not a false claim, but not a detection either;
- wrong: anything else (a rule or mixture the scenario does not contain).
Family-level error = the share of replicates in which *any* core target got a wrong verdict.
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

NONCLAIMS = ("none", "unidentified", "unidentified:selection")

#: scenario -> (Params overrides, correct verdicts, additionally acceptable verdicts)
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
    "fifo_reorder": ({}, ("none",), ("unidentified", "fifo")),
    "label_blind_reorder": ({"reverse_q": 0.35}, ("fifo",), NONCLAIMS),
    "selective_drop_cu_price": ({"scenario": "selective_drop", "base": "cu_price_batch", "drop_q": 0.5}, ("cu_price",), NONCLAIMS),
    "correlated_pair_loss": ({"loss_q": 0.8}, ("unidentified:selection",), ("none", "unidentified", "fifo")),
    "mode_switch_rc_fifo": ({"scenario": "mode_switch", "base": "reward_cost_greedy", "mode_b": "fifo"},
                            ("mixed:fifo+reward_cost",), ("none", "unidentified")),
    "low_landing_reward_cost": ({"scenario": "reward_cost_greedy", "landing": 0.5}, ("reward_cost",), NONCLAIMS),
    "low_landing_cu_price": ({"scenario": "cu_price_batch", "t_ms": 20, "landing": 0.5}, ("cu_price",), NONCLAIMS),
}

#: Pre-registered stopping (PREREGISTRATION §5), identical to `itb run`: stop a target once each of C1, C2, C3 has
#: this many pairs with both members landed in an evaluable window, or when its K-window plans run out.
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
            if not w["evaluable"].all():
                continue
            for _, r in w[w["pair_kind"].isin(counts)].iterrows():
                counts[r["pair_kind"]] += bool(r["both_landed"])
    return outcomes.pd.concat(keep, ignore_index=True) if keep else pairs.iloc[0:0]


def analyse_dir(run_dir: Path, n_draws: int, tiers: dict[str, str]) -> dict[str, dict]:
    run = load_run(run_dir)
    pairs = apply_stopping(outcomes.pair_table(run), tiers)
    per_target = {}
    for target, g in pairs.groupby("target_identity"):
        eff = stats.validator_effects(g, n_draws=n_draws)
        per_target[target] = {"verdict": eff["diagnosis"]["verdict"], "n_c1": eff["label"]["c1"].n, "windows": int(g["seq"].nunique())}
    return per_target


def run(design: Path, targets: Path, reps: int, n_draws: int, seed0: int = 1000) -> dict:
    tiers = {t["identity"]: t.get("tier", "core") for t in json.loads(Path(targets).read_text())}
    results: dict[str, dict] = {}
    for name, (over, correct, acceptable) in SCENARIOS.items():
        over = dict(over)
        scenario = over.pop("scenario", name)
        verdicts: Counter = Counter()
        by_tier: dict[str, Counter] = defaultdict(Counter)
        family_wrong = 0
        n_obs, windows = [], []
        for r in range(reps):
            with tempfile.TemporaryDirectory() as tmp:
                simulate(design, targets, Path(tmp), Params(scenario=scenario, seed=seed0 + r, **over), stage=1)
                per_target = analyse_dir(Path(tmp), n_draws, tiers)
            any_core_wrong = False
            for target, res in per_target.items():
                v = res["verdict"]
                verdicts[v] += 1
                tier = tiers.get(target, "core")
                cls = "correct" if v in correct else "acceptable" if v in acceptable else "wrong"
                by_tier[tier][cls] += 1
                by_tier[tier]["n"] += 1
                any_core_wrong |= tier == "core" and cls == "wrong"
                n_obs.append(res["n_c1"])
                windows.append(res["windows"])
            family_wrong += any_core_wrong
        total = sum(verdicts.values())
        median = lambda xs: sorted(xs)[len(xs) // 2] if xs else 0
        results[name] = {
            "correct": list(correct),
            "verdicts": {k: v / total for k, v in verdicts.most_common()},
            "by_tier": {t: {k: c[k] / c["n"] for k in ("correct", "acceptable", "wrong")} | {"n": c["n"]} for t, c in by_tier.items()},
            "family_wrong_rate": family_wrong / reps,
            "median_pairs_c1": median(n_obs),
            "median_windows_attempted": median(windows),
            "reps": reps,
        }
        print(name, json.dumps(results[name]), flush=True)
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--design", required=True, type=Path)
    ap.add_argument("--targets", required=True, type=Path)
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--n-draws", type=int, default=2_000)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    res = run(a.design, a.targets, a.reps, a.n_draws)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
