#!/usr/bin/env python3
"""Operating characteristics of the Study 2 hypotheses (docs/POWER-2.md): the frozen Study 2 design, simulated with
schedulers whose horizon and tie-break are known, analysed by `itb_analysis.study2` exactly as the live data will be,
gates included: "supported" counts published claims that start with it, "selection-robust" those without the
"(assumes selection)" qualifier.

    PYTHONPATH=analysis python scripts/oc_study2.py [--reps 40] [--out data/derived/oc-study2.json]

Every scenario uses 90 % landing and Study 1's observation failures (lost streams, unproduced blocks, gossip changes).
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import defaultdict
from pathlib import Path

from itb_analysis import outcomes, study2
from itb_analysis.load import load_designs, load_run
from itb_analysis.sim import Params, simulate
from itb_analysis.stats import clopper_pearson

AGAVE, JITO, FD, DRPB, FD7B, JUPI, FD2 = (
    "7QQGNm3ptwinipDCyaCF7jY5katgmFUu1ieP2f7nwLpE", "HEL1USMZKAL2odpNBj2oCjffnFGaYwmbGmyewGv1e2TU",
    "EvnRmnMrd69kFdbLMxWkTn1icZ7DCceRhvmb2SJXqDo4", "DRpbCBMxVnDK7maPM5tGv6MvB3v1sRMC86PZ8okm21hy",
    "Fd7btgySsrjuo25CJCj7oE7VPMyezDhnx7pZkj2v69Nk", "JUPiTERrZqgf1jUyR7dSkhMx4Kn2qJyekWsg3LT1h4b",
    "9eGrDohdNTAo61DRHyfMuqKWXqYnA3i254Wiszxe8FoY")


def fifo():
    return {"scenario": "fifo"}


def greedy(pass_ms, tie="lifo"):
    return {"scenario": "reward_cost_greedy", "pass_ms": pass_ms, "tie": tie}


def batch(t_ms):
    return {"scenario": "reward_cost_batch", "t_ms": t_ms}


#: name -> (what is true, per-target schedulers). Study 1's picture, a weaker version of it, and its opposite.
SCENARIOS = {
    "study1_picture": ("Agave family FIFO; Firedancer priority passes every 15 ms with later-arrival-first ties; "
                       "Harmonic auctions every 25 / 60 ms; BAM every 50 ms",
                       {AGAVE: fifo(), JITO: fifo(), FD: greedy(15), FD2: greedy(15), JUPI: batch(25), FD7B: batch(60),
                        DRPB: batch(50)}),
    "weak_effects": ("Agave family arrival order with 2 ms of extra jitter; Firedancer passes every 6 ms; Harmonic "
                     "auctions every 8 ms (true O(2) ≈ 0.24 and ≈ 0.67–0.75)",
                     {AGAVE: {"scenario": "fifo_reorder"}, JITO: {"scenario": "fifo_reorder"}, FD: greedy(6),
                      FD2: greedy(6), JUPI: batch(8), FD7B: batch(8), DRPB: batch(8)}),
    "opposite": ("Agave family priority passes every 15 ms; Firedancer and Harmonic FIFO; Firedancer ties random "
                 "(every hypothesis false)",
                 {AGAVE: greedy(15, "random"), JITO: greedy(15, "random"), FD: fifo(), FD2: greedy(15, "random"),
                  JUPI: fifo(), FD7B: fifo(), DRPB: fifo()}),
    "boundary_null": ("every group at the null boundary: priority passes / auctions every 4 ms (O(2) = 0.5), "
                      "Firedancer ties random (E = 0.5); every hypothesis false",
                      {AGAVE: greedy(4, "random"), JITO: greedy(4, "random"), FD: greedy(4, "random"),
                       FD2: greedy(4, "random"), JUPI: batch(4), FD7B: batch(4), DRPB: batch(4)}),
}
#: scenarios in which every hypothesis is false: any support there is a family-wise error
NULLS = ("opposite", "boundary_null")


def run(design: Path, targets: Path, reps: int) -> dict:
    hyps = study2.hypotheses(json.loads(targets.read_text()))
    designs = load_designs([design])
    out = {}
    for name, (truth, per_target) in SCENARIOS.items():
        tally = defaultdict(lambda: defaultdict(int))
        n_pairs = defaultdict(list)
        any_support = 0
        for seed in range(reps):
            with tempfile.TemporaryDirectory() as tmp:
                r = load_run(simulate(design, targets, Path(tmp) / "r", Params("fifo", seed=seed, landing=0.9,
                                                                               target_scenarios=per_target), stage=2))
                pairs = study2.pair_table(outcomes.probe_table(r), outcomes.window_table(r, designs), r.sends)
            supported = 0
            for h, spec in zip(study2.evaluate(pairs, hyps), hyps):
                claim = study2.published(h, study2.gates(pairs, spec))  # after the §8 gates, as REPORT will print
                tally[h["id"]]["supported"] += claim.startswith("supported")
                tally[h["id"]]["robust"] += claim == "supported"
                n_pairs[h["id"]].append(h["n"])
                supported += claim.startswith("supported")
            any_support += supported > 0
        lo, hi = clopper_pearson(any_support, reps, 0.05)
        out[name] = {"truth": truth, "reps": reps, "campaigns_with_any_support": any_support,
                     "any_support_ci95": [lo, hi],
                     "rates": {i: {"supported": t["supported"] / reps, "selection_robust": t["robust"] / reps,
                                   "median_n": sorted(n_pairs[i])[len(n_pairs[i]) // 2]} for i, t in tally.items()}}
    return out


def markdown(res: dict) -> str:
    ids = [h[0] for h in study2.SPEC]
    lines = ["| Scenario | " + " | ".join(ids) + " | campaigns with any false support |", "|---|" + "---|" * (len(ids) + 1)]
    for name, r in res.items():
        cells = [f"{r['rates'][i]['supported']:.2f} (n≈{r['rates'][i]['median_n']})" for i in ids]
        fw = (f"{r['campaigns_with_any_support']}/{r['reps']} (95 % CI up to {r['any_support_ci95'][1]:.2f})"
              if name in NULLS else "—")
        lines.append(f"| `{name}` | " + " | ".join(cells) + f" | {fw} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--design", type=Path, default=Path("design/design-study2.jsonl"))
    ap.add_argument("--targets", type=Path, default=Path("design/targets-study2.json"))
    ap.add_argument("--reps", type=int, default=40)
    ap.add_argument("--out", type=Path, default=Path("data/derived/oc-study2.json"))
    a = ap.parse_args()
    res = run(a.design, a.targets, a.reps)
    a.out.write_bytes((json.dumps(res, indent=1) + "\n").encode())
    a.out.with_suffix(".md").write_bytes(markdown(res).encode())
    print(markdown(res))


if __name__ == "__main__":
    main()
