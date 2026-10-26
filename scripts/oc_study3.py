#!/usr/bin/env python3
"""Operating characteristics of Study 3 (docs/POWER-3.md): the frozen Study 3 design, simulated with schedulers whose
key is known, analysed by `itb_analysis.study3` exactly as the live data will be (positive-control gate and selection
qualifier included).

    PYTHONPATH=analysis python scripts/oc_study3.py [--reps 100] [--out data/derived/oc-study3.json]

Every scenario uses Study 1's observation failures and the measured in-window slot (≈ 198 ms). Each member lands
with probability 0.90, except in `reward_cost_observed_landing`, which uses each target's Study 2 rate. The Study 1
and Study 2 claims are taken as reward_cost for every core target, as they are.
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
MEASURED_SLOT_MS = 198.0
COST = {"scenario": "cost_only_greedy", "tie": "random"}
#: per-member landing of the small probes (A, B) in Study 2's evaluable C1 pairs, per target. Drawn independently per
#: member here; BAM's Study 2 losses were whole windows (no incomplete pair), so its row is pessimistic.
OBSERVED_LANDING = {AGAVE: 80 / 80, JITO: 80 / 80, FD: 96 / 102, DRPB: 78 / 88, FD7B: 86 / 92, JUPI: 87 / 94}
SCENARIOS = {
    "reward_cost": ("every target orders by reward ÷ (cost + 1): the truth Studies 1-2 point to", {}),
    "reward_cost_observed_landing": ("every target orders by reward ÷ (cost + 1), each member landing at its target's "
                                     "Study 2 rate for small probes (Agave, Jito 1.00; Firedancer 0.94; Harmonic 0.93; "
                                     "BAM 0.89) instead of 0.90", {t: {"landing": x} for t, x in OBSERVED_LANDING.items()}),
    "weak": ("half of each target's windows order by reward ÷ cost, the other half FIFO (L ≈ 0.75)",
             {t: {"scenario": "mode_switch", "base": "reward_cost_greedy", "mode_b": "fifo"} for t in ALL}),
    "cost_only": ("every target orders by requested cost alone, ties random: every hypothesis false (C5 exactly at "
                  "its null)", {t: COST for t in ALL}),
    "control_fails": ("Agave orders by cost alone, the rest by reward ÷ cost: the positive-control gate must withdraw "
                      "the non-control targets", {AGAVE: COST}),
    "additive": ("every target orders by reward − cost: a key outside the registered candidates that ranks every "
                 "registered pair as reward ÷ cost does, so Study 3 cannot tell them apart",
                 {t: {"scenario": "additive_greedy"} for t in ALL}),
}
NULLS = ("cost_only",)


def _share(k: int, n: int) -> dict:
    lo, hi = clopper_pearson(k, n, 0.05)
    return {"k": k, "n": n, "share": k / n, "ci95": [lo, hi]}


def run(design: Path, targets: Path, reps: int) -> dict:
    specs = json.loads(targets.read_text())
    hyps = study3.hypotheses(specs)
    controls = [AGAVE, FD]
    manifest = {"core_targets": [{k: t[k] for k in ("identity", "client_id", "ingress")} for t in specs],
                "prior_claims": {t["identity"]: {"study1": "reward_cost", "study2": "reward_cost"} for t in specs}}
    designs = load_designs([design])
    out = {}
    for name, (truth, per_target) in SCENARIOS.items():
        supported, withdrawn, n = defaultdict(int), defaultdict(int), defaultdict(list)
        robust, conditional = defaultdict(int), defaultdict(int)
        any_support = gate_passed = gate_unconditional = 0
        for seed in range(reps):
            with tempfile.TemporaryDirectory() as tmp:
                params = Params("reward_cost_greedy", seed=seed, landing=0.9, target_scenarios=per_target,
                                slot_ms=MEASURED_SLOT_MS)
                r = load_run(simulate(design, targets, Path(tmp) / "r", params, stage=1))
                pairs = outcomes.pair_table(r, kinds=study3.KINDS, designs=designs, windows=outcomes.window_table(r, designs))
            decided = study3.evaluate(pairs, hyps)
            claims = study3.published(decided, controls)
            state = study3.control_state(decided, controls)
            for h in decided:
                supported[h["id"]] += claims[h["id"]].startswith("supported")
                withdrawn[h["id"]] += claims[h["id"]].startswith("withdrawn")
                n[h["id"]].append(h["n"])
            for row in study3.identification(decided, claims, manifest, state):
                robust[row["identity"][:8]] += row["reward_cost_identified"]
                conditional[row["identity"][:8]] += row["reward_cost_identified_assuming_selection"]
            any_support += any(c.startswith("supported") for c in claims.values())
            gate_passed += not state["failed"]
            gate_unconditional += not state["failed"] and not state["conditional"]
        out[name] = {"truth": truth, "reps": reps, "slot_ms": MEASURED_SLOT_MS,
                     "any_support": _share(any_support, reps), "gate_passed": _share(gate_passed, reps),
                     "gate_passed_unconditionally": _share(gate_unconditional, reps),
                     "identified": {t: _share(robust[t], reps) for t in robust},
                     "identified_assuming_selection": {t: _share(conditional[t], reps) for t in conditional},
                     "rates": {i: {"supported": supported[i] / reps, "withdrawn": withdrawn[i] / reps,
                                   "median_n": sorted(n[i])[len(n[i]) // 2]} for i in supported}}
    return out


def _cell(s: dict) -> str:
    return f"{s['share']:.2f} ({s['ci95'][0]:.2f}–{s['ci95'][1]:.2f})"


def markdown(res: dict) -> str:
    targets = list(next(iter(res.values()))["identified"])
    head = "| Scenario | " + " | ".join(f"`{t}`" for t in targets) + " |"
    rule = "|---|" + "---|" * len(targets)
    ident = [head, rule] + [f"| `{name}` | " + " | ".join(_cell(r["identified"][t]) for t in targets) + " |"
                            for name, r in res.items()]
    cond = [head, rule] + [f"| `{name}` | " + " | ".join(_cell(r["identified_assuming_selection"][t]) for t in targets) + " |"
                           for name, r in res.items()]
    gate = ["| Scenario | gate passed | gate passed without the selection qualifier | campaigns with any support |",
            "|---|---|---|---|"] + [
        f"| `{name}` | {_cell(r['gate_passed'])} | {_cell(r['gate_passed_unconditionally'])} | "
        + (f"{r['any_support']['k']}/{r['reps']} (95 % CI up to {r['any_support']['ci95'][1]:.2f})" if name in NULLS else "—")
        + " |" for name, r in res.items()]
    return ("Share of campaigns in which each target's key is identified as reward ÷ (cost + 1), robust to selection "
            "(95 % Clopper–Pearson interval over the replicates):\n\n" + "\n".join(ident)
            + "\n\nIdentified, counting verdicts that assume selection:\n\n" + "\n".join(cond)
            + "\n\nPositive-control gate:\n\n" + "\n".join(gate) + "\n")


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
