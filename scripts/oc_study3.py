#!/usr/bin/env python3
"""Operating characteristics of Study 3 (docs/POWER-3.md): the frozen Study 3 design, simulated with schedulers whose
key is known, analysed by `itb_analysis.study3` exactly as the live data will be (positive-control gate included).

    PYTHONPATH=analysis python scripts/oc_study3.py [--reps 100] [--out data/derived/oc-study3.json]

Every scenario uses 90 % landing and Study 1's observation failures. "Identified" assumes the target's Study 1 and
Study 2 claims are reward_cost (they are, for all six core targets).
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import defaultdict
from pathlib import Path

from itb_analysis import outcomes, study3
from itb_analysis.load import load_designs, load_run
from itb_analysis.sim import Params, simulate
from itb_analysis.stats import clopper_pearson

AGAVE, JITO, FD, DRPB, FD7B, JUPI = (
    "7QQGNm3ptwinipDCyaCF7jY5katgmFUu1ieP2f7nwLpE", "HEL1USMZKAL2odpNBj2oCjffnFGaYwmbGmyewGv1e2TU",
    "EvnRmnMrd69kFdbLMxWkTn1icZ7DCceRhvmb2SJXqDo4", "DRpbCBMxVnDK7maPM5tGv6MvB3v1sRMC86PZ8okm21hy",
    "Fd7btgySsrjuo25CJCj7oE7VPMyezDhnx7pZkj2v69Nk", "JUPiTERrZqgf1jUyR7dSkhMx4Kn2qJyekWsg3LT1h4b")
ALL = (AGAVE, JITO, FD, DRPB, FD7B, JUPI)
COST = {"scenario": "cost_only_greedy", "tie": "random"}
SCENARIOS = {
    "reward_cost": ("every target orders by reward ÷ (cost + 1): the truth Studies 1-2 point to", {}),
    "weak": ("half of each target's windows order by reward ÷ cost, the other half FIFO (L ≈ 0.75)",
             {t: {"scenario": "mode_switch", "base": "reward_cost_greedy", "mode_b": "fifo"} for t in ALL}),
    "cost_only": ("every target orders by requested cost alone, ties random: every hypothesis false (C5 exactly at "
                  "its null)", {t: COST for t in ALL}),
    "control_fails": ("Agave orders by cost alone, the rest by reward ÷ cost: the positive-control gate must withdraw "
                      "the non-control targets", {AGAVE: COST}),
}
NULLS = ("cost_only",)


def run(design: Path, targets: Path, reps: int) -> dict:
    specs = json.loads(targets.read_text())
    hyps = study3.hypotheses(specs)
    controls = [AGAVE, FD]
    manifest = {"core_targets": [{k: t[k] for k in ("identity", "client_id", "ingress")} for t in specs]}
    prior = {s: {"validators": {f"{t['identity']}|{t['client_id']}|{t['ingress']}": {"published_claim": "reward_cost"}
                                for t in specs}} for s in ("study1", "study2")}
    designs = load_designs([design])
    out = {}
    for name, (truth, per_target) in SCENARIOS.items():
        supported, identified, withdrawn, n = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(list)
        any_support = 0
        for seed in range(reps):
            with tempfile.TemporaryDirectory() as tmp:
                r = load_run(simulate(design, targets, Path(tmp) / "r", Params("reward_cost_greedy", seed=seed, landing=0.9,
                                                                               target_scenarios=per_target), stage=1))
                pairs = outcomes.pair_table(r, kinds=study3.KINDS, designs=designs, windows=outcomes.window_table(r, designs))
            decided = study3.evaluate(pairs, hyps)
            claims = study3.published(decided, controls)
            for h in decided:
                supported[h["id"]] += claims[h["id"]].startswith("supported")
                withdrawn[h["id"]] += claims[h["id"]].startswith("withdrawn")
                n[h["id"]].append(h["n"])
            for row in study3.identification(decided, claims, manifest, prior):
                identified[row["identity"][:8]] += row["reward_cost_identified"]
            any_support += any(c.startswith("supported") for c in claims.values())
        lo, hi = clopper_pearson(any_support, reps, 0.05)
        out[name] = {"truth": truth, "reps": reps, "campaigns_with_any_support": any_support, "any_support_ci95": [lo, hi],
                     "identified": {t: identified[t] / reps for t in identified},
                     "rates": {i: {"supported": supported[i] / reps, "withdrawn": withdrawn[i] / reps,
                                   "median_n": sorted(n[i])[len(n[i]) // 2]} for i in supported}}
    return out


def markdown(res: dict) -> str:
    targets = list(next(iter(res.values()))["identified"])
    lines = ["| Scenario | " + " | ".join(f"`{t}`" for t in targets) + " | campaigns with any support |",
             "|---|" + "---|" * (len(targets) + 1)]
    for name, r in res.items():
        cells = [f"{r['identified'][t]:.2f}" for t in targets]
        fw = (f"{r['campaigns_with_any_support']}/{r['reps']} (95 % CI up to {r['any_support_ci95'][1]:.2f})"
              if name in NULLS else "—")
        lines.append(f"| `{name}` | " + " | ".join(cells) + f" | {fw} |")
    return "Share of campaigns in which each target's ordering key is identified as reward ÷ (cost + 1):\n\n" + "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--design", type=Path, default=Path("design/design-study3.jsonl"))
    ap.add_argument("--targets", type=Path, default=Path("design/targets-study3.json"))
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--out", type=Path, default=Path("data/derived/oc-study3.json"))
    a = ap.parse_args()
    res = run(a.design, a.targets, a.reps)
    a.out.write_bytes((json.dumps(res, indent=1) + "\n").encode())
    a.out.with_suffix(".md").write_bytes(markdown(res).encode())
    print(markdown(res))


if __name__ == "__main__":
    main()
