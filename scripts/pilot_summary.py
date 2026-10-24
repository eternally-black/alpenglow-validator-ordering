#!/usr/bin/env python3
"""Pilot calibration summary (PREREGISTRATION: pilot data are reported, never confirmatory).

    PYTHONPATH=analysis python scripts/pilot_summary.py --raw data/pilot

Per validator group: windows attempted / evaluable and the exclusion reasons, probe landing rate, the share of
contrast pairs with both members landed (what the stopping rule counts), achieved send offsets against the observed
first shred, reconnects, and not-sent reasons. These numbers decide what the freeze can rely on (landing per ingress,
timing, which targets reach the informative target within their plans).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from itb_analysis import outcomes, report
from itb_analysis.load import load_designs, load_runs, run_dirs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=Path("data/pilot"))
    ap.add_argument("--design", type=Path, action="append", default=None,
                    help="pilot design file(s); default design/design.pilot*.jsonl")
    a = ap.parse_args()
    dirs = [d for d in run_dirs(a.raw) if json.loads((d / "run_start.json").read_text()).get("mode") == "live"]
    run = load_runs(dirs)
    designs = load_designs(a.design or sorted(Path("design").glob("design.pilot*.jsonl")))
    w = outcomes.window_table(run, designs)
    pairs = outcomes.pair_table(run, designs=designs, windows=w)
    probes = outcomes.probe_table(run)
    offsets = report._achieved_offsets(run)

    print(f"live pilot runs: {[d.name for d in dirs]}\n")
    print("| Validator | Client | Ingress | Windows (evaluable) | Probes landed | Main pairs both landed | "
          "Median achieved offset ms | Reconnects | Exclusions |")
    print("|---|---|---|---|---|---|---|---|---|")
    for (t, client, ingress), g in w.groupby(["target_identity", "client_id", "ingress"], dropna=False):
        pt = probes[probes["target_identity"] == t]
        pp = pairs[(pairs["target_identity"] == t) & pairs["pair_kind"].isin(["c1", "c2", "c3"])]
        off = offsets[offsets["target_identity"] == t]["achieved_offset_ms"]
        rec = sum(len(r) for r in g.get("reconnects", []) if isinstance(r, list))
        excl = Counter(x for e in g["exclusion"] for x in e.split(",") if x)
        print(f"| `{t[:8]}` | {client} | {ingress} | {len(g)} ({int(g['evaluable'].sum())}) | "
              f"{int(pt['landed'].sum())}/{len(pt)} | {int(pp['both_landed'].sum())}/{len(pp)} | "
              f"{np.median(off):.0f} | {rec} | {dict(excl) or '—'} |" if len(off) else
              f"| `{t[:8]}` | {client} | {ingress} | {len(g)} ({int(g['evaluable'].sum())}) | "
              f"{int(pt['landed'].sum())}/{len(pt)} | {int(pp['both_landed'].sum())}/{len(pp)} | – | {rec} | {dict(excl) or '—'} |")
    print("\nprobe statuses:", dict(Counter(probes["status"])))
    reasons = Counter(v for r in w.get("not_sent_reasons", []) if isinstance(r, dict) for v in r.values())
    print("not-sent reasons:", dict(reasons) or "none")
    by_regime = pairs[pairs["pair_kind"].isin(["c1", "c2", "c3"])].groupby("regime")["both_landed"].mean()
    print("both-landed share by regime:", {k: round(float(v), 3) for k, v in by_regime.items()})
    ends = [e.get("ledger") for e in run.ends if e.get("ledger")]
    if ends:
        print("ledger at the end of the last run:", ends[-1])


if __name__ == "__main__":
    main()
