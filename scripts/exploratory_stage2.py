#!/usr/bin/env python3
"""Stage-2 exploratory summaries (PREREGISTRATION §7 — exploratory, labelled as such everywhere).

    PYTHONPATH=analysis python scripts/exploratory_stage2.py [--raw data/raw] [--design design/design.jsonl]

Only evaluable windows (same eligibility rules as Stage 1) enter the race and equal-key summaries; the hold-cliff
and spill-over kits are summarised per probe status.
- **Races** (T kit): `hi` (3,000,000 µlamports/CU) vs `lo` (1,000,000 µlamports/CU with a 64 MiB data request), one
  sent Δt ms after the other. P(hi lands first) separately when `hi` was sent first and when `lo` had the head start
  of Δt ms: how long a head start the higher-priority probe can overcome — the effective reordering horizon.
- **Equal key**: two identical template-A probes, Δt apart. P(first-sent lands first): FIFO predicts ≈ 1; the
  Firedancer later-arrival-first tie-break predicts < 0.5.
- **Hold cliff** (H kit): status of probes sent 7 s, 3 s and 0.5 s before the window, per client.
- **Spill-over** (S kit): where pre-window probes land, per ingress kind.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from itb_analysis import outcomes
from itb_analysis.load import load_designs, load_runs, run_dirs
from itb_analysis.stats import clopper_pearson


def ci(k: int, n: int) -> str:
    if n == 0:
        return "–"
    lo, hi = clopper_pearson(k, n, 0.05)
    return f"{k}/{n} = {k / n:.2f} [{lo:.2f}, {hi:.2f}]"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument("--design", type=Path, default=Path("design/design.jsonl"))
    a = ap.parse_args()
    dirs = [d for d in run_dirs(a.raw) if json.loads((d / "run_start.json").read_text()).get("stage") == 2
            and json.loads((d / "run_start.json").read_text()).get("mode") == "live"]
    run = load_runs(dirs)
    designs = load_designs([a.design])
    w = outcomes.window_table(run, designs)
    p = outcomes.probe_table(run)
    ev = set(zip(w[w["evaluable"]]["run_id"], w[w["evaluable"]]["target_identity"], w[w["evaluable"]]["seq"]))
    client = {(r["run_id"], r["target_identity"], r["seq"]): (r.get("client_id"), r.get("ingress")) for _, r in w.iterrows()}
    p["evaluable"] = [(r, t, s) in ev for r, t, s in zip(p["run_id"], p["target_identity"], p["seq"])]
    p["client"] = [client.get((r, t, s), (None, None))[0] for r, t, s in zip(p["run_id"], p["target_identity"], p["seq"])]
    p["ingress"] = [client.get((r, t, s), (None, None))[1] for r, t, s in zip(p["run_id"], p["target_identity"], p["seq"])]

    def rank(r):
        return (int(r["slot"]), int(r["index_in_block"]))

    print(f"Stage-2 runs: {[d.name for d in dirs]}; windows {len(w)}, evaluable {int(w['evaluable'].sum())}\n")

    # ---- races
    print("## Races (T kit, evaluable windows, both members landed): P(hi lands first)\n")
    print("| Client | Ingress | Δt ms | hi sent first | lo sent first (head start Δt) |")
    print("|---|---|---|---|---|")
    races = defaultdict(lambda: [0, 0, 0, 0])  # hi-first: k, n ; lo-first: k, n
    for (_, pair_id), g in p[(p["pair_kind"] == "race") & p["evaluable"]].groupby(["run_id", "pair_id"]):
        if len(g) != 2 or not g["landed"].all():
            continue
        hi, lo = g[g["label"] == "hi"].iloc[0], g[g["label"] == "lo"].iloc[0]
        key = (hi["client"], hi["ingress"], float(hi["race_dt_ms"]))
        hi_first = rank(hi) < rank(lo)
        if int(hi["send_position_in_pair"]) == 0:
            races[key][0] += hi_first
            races[key][1] += 1
        else:
            races[key][2] += hi_first
            races[key][3] += 1
    for (c, ing, dt), (k1, n1, k2, n2) in sorted(races.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]), kv[0][2])):
        print(f"| {c} | {ing} | {dt:.0f} | {ci(k1, n1)} | {ci(k2, n2)} |")

    # ---- equal key
    print("\n## Equal key (two identical A probes): P(first-sent lands first)\n")
    print("| Client | Ingress | Δt ms | first-sent first |")
    print("|---|---|---|---|")
    eq = defaultdict(lambda: [0, 0])
    for (_, pair_id), g in p[(p["pair_kind"] == "equal_key") & p["evaluable"]].groupby(["run_id", "pair_id"]):
        if len(g) != 2 or not g["landed"].all():
            continue
        first = g[g["send_position_in_pair"] == 0].iloc[0]
        second = g[g["send_position_in_pair"] == 1].iloc[0]
        key = (first["client"], first["ingress"], float(first["race_dt_ms"]))
        eq[key][0] += rank(first) < rank(second)
        eq[key][1] += 1
    for (c, ing, dt), (k, n) in sorted(eq.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]), kv[0][2])):
        print(f"| {c} | {ing} | {dt:.0f} | {ci(k, n)} |")

    # ---- hold cliff
    print("\n## Hold cliff (H kit): status by send offset\n")
    print("| Client | Ingress | Offset s | landed in window | next window (same validator) | expired | not sent |")
    print("|---|---|---|---|---|---|---|")
    h = defaultdict(lambda: defaultdict(int))
    for _, r in p[p["kit"] == "h"].iterrows():
        h[(r["client"], r["ingress"], round(r["nominal_offset_ms"] / 1000, 1))][r["status"]] += 1
    for (c, ing, off), s in sorted(h.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]), kv[0][2])):
        print(f"| {c} | {ing} | {off} | {s['landed_target']} | {s['spillover_same_validator_other_window']} | "
              f"{s['expired_confirmed']} | {s['not_sent']} |")

    # ---- spill-over
    print("\n## Spill-over (S kit): status by send offset and ingress kind\n")
    print("| Ingress | Offset ms | landed in window | other leader | same validator, other window | expired | not sent |")
    print("|---|---|---|---|---|---|---|")
    sp = defaultdict(lambda: defaultdict(int))
    for _, r in p[p["kit"] == "s"].iterrows():
        sp[(r["ingress"], round(r["nominal_offset_ms"]))][r["status"]] += 1
    for (ing, off), s in sorted(sp.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        print(f"| {ing} | {off} | {s['landed_target']} | {s['spillover_other_leader']} | "
              f"{s['spillover_same_validator_other_window']} | {s['expired_confirmed']} | {s['not_sent']} |")


if __name__ == "__main__":
    main()
