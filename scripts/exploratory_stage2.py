#!/usr/bin/env python3
"""Stage-2 exploratory summaries as markdown (PREREGISTRATION §7 — exploratory, labelled as such everywhere).

    PYTHONPATH=analysis python scripts/exploratory_stage2.py [--raw data/raw] [--design design/design.jsonl]

The counts come from `itb_analysis.exploratory`, which documents each kit; the figures draw the same counts.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from itb_analysis import exploratory
from itb_analysis.stats import clopper_pearson


def ci(k: int, n: int) -> str:
    if n == 0:
        return "–"
    lo, hi = clopper_pearson(k, n, 0.05)
    return f"{k}/{n} = {k / n:.2f} [{lo:.2f}, {hi:.2f}]"


def _order(kv):
    return tuple(str(x) if i < len(kv[0]) - 1 else x for i, x in enumerate(kv[0]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument("--design", type=Path, default=Path("design/design.jsonl"))
    a = ap.parse_args()
    s2 = exploratory.load_stage2(a.raw, a.design)
    w, p = s2.windows, s2.probes

    print(f"Stage-2 runs: {s2.run_ids}; windows {len(w)}, evaluable {int(w['evaluable'].sum())}\n")

    print("## Races (T kit, evaluable windows, both members landed): P(hi lands first)\n")
    print("| Client | Ingress | Δt ms | hi sent first | lo sent first (head start Δt) |")
    print("|---|---|---|---|---|")
    for (c, ing, dt), (k1, n1, k2, n2) in sorted(exploratory.races(p).items(), key=_order):
        print(f"| {c} | {ing} | {dt:.0f} | {ci(k1, n1)} | {ci(k2, n2)} |")

    print("\n## Equal key (two identical A probes): P(first-sent lands first)\n")
    print("| Client | Ingress | Δt ms | first-sent first |")
    print("|---|---|---|---|")
    for (c, ing, dt), (k, n) in sorted(exploratory.equal_key(p).items(), key=_order):
        print(f"| {c} | {ing} | {dt:.0f} | {ci(k, n)} |")

    print("\n## Hold cliff (H kit): status by send offset\n")
    print("| Client | Ingress | Offset s | landed in window | next window (same validator) | expired | not sent |")
    print("|---|---|---|---|---|---|---|")
    for (c, ing, off), s in sorted(exploratory.hold(p).items(), key=_order):
        print(f"| {c} | {ing} | {off} | {s.get('landed_target', 0)} | {s.get('spillover_same_validator_other_window', 0)} | "
              f"{s.get('expired_confirmed', 0)} | {s.get('not_sent', 0)} |")

    print("\n## Spill-over (S kit): status by send offset and ingress kind\n")
    print("| Ingress | Offset ms | landed in window | other leader | same validator, other window | expired | not sent |")
    print("|---|---|---|---|---|---|---|")
    for (ing, off), s in sorted(exploratory.spill(p).items(), key=_order):
        print(f"| {ing} | {off} | {s.get('landed_target', 0)} | {s.get('spillover_other_leader', 0)} | "
              f"{s.get('spillover_same_validator_other_window', 0)} | {s.get('expired_confirmed', 0)} | {s.get('not_sent', 0)} |")


if __name__ == "__main__":
    main()
