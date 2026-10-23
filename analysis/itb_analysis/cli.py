"""`python -m itb_analysis.cli <command>` — the analysis entry point used by docker compose.

reproduce  offline: recompute every derived number from data/raw and compare with the committed data/derived
verify     re-check claims against the chain (sample) or the archived blocks
report     recompute and overwrite data/derived (after new data)
oc         operating characteristics on simulated scenarios
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import oc, report, verify
from .load import run_dirs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="itb-analysis", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("reproduce", "report"):
        p = sub.add_parser(name)
        p.add_argument("--raw", type=Path, default=Path("data/raw"))
        p.add_argument("--derived", type=Path, default=Path("data/derived"))
    v = sub.add_parser("verify")
    v.add_argument("--raw", type=Path, default=Path("data/raw"))
    v.add_argument("--source", choices=["chain", "archive"], default="chain")
    v.add_argument("--rpc-url", default="https://api.mainnet-beta.solana.com")
    v.add_argument("--sample", type=int, default=30, help="claims to check (0 = all)")
    v.add_argument("--json", type=Path, default=None)
    o = sub.add_parser("oc")
    o.add_argument("--design", type=Path, default=Path("design/design.jsonl"))
    o.add_argument("--targets", type=Path, default=Path("design/targets.json"))
    o.add_argument("--reps", type=int, default=20)
    o.add_argument("--n-draws", type=int, default=2_000)
    o.add_argument("--out", type=Path, default=Path("data/derived/oc.json"))
    a = ap.parse_args(argv)

    if a.cmd == "report":
        path = report.write(report.compute(a.raw), a.derived)
        print(f"wrote {path}")
        return 0
    if a.cmd == "reproduce":
        fresh = report.compute(a.raw)
        committed_path = a.derived / "results.json"
        if not committed_path.exists():
            print(f"no committed {committed_path}; nothing to compare (run `report` first)")
            return 1
        committed = json.loads(committed_path.read_text())
        diffs = report.compare(json.loads(json.dumps(fresh, default=str)), committed, tol=1e-9)
        print(report.markdown_summary(fresh))
        if diffs:
            print(f"\nREPRODUCTION FAILED: {len(diffs)} differences, e.g.:\n  " + "\n  ".join(diffs[:20]))
            return 1
        print(f"\nREPRODUCED: every number in {committed_path} recomputed from {a.raw} ({len(fresh.get('runs', []))} runs).")
        return 0
    if a.cmd == "verify":
        rep = verify.verify(run_dirs(a.raw), a.source, a.rpc_url, None if a.sample == 0 else a.sample)
        verify.print_ledger(rep)
        if a.json:
            a.json.write_text(json.dumps(rep, indent=1))
        return 0 if rep["claims_ok"] == rep["claims_checked"] else 1
    if a.cmd == "oc":
        res = oc.run(a.design, a.targets, a.reps, None, a.n_draws)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(res, indent=1))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
