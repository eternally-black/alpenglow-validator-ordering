"""`python -m itb_analysis.cli <command>` — the analysis entry point used by docker compose.

reproduce  offline: recompute every derived number from data/raw and compare with the committed data/derived
verify     re-check claims against the chain (sample) or the archived blocks
report     recompute and overwrite data/derived (after new data)
oc         operating characteristics on simulated scenarios
figures    redraw figures/ (light and dark SVG) from data/derived/results.json and data/raw
study2     Study 2 (docs/PREREGISTRATION-2.md): `report` writes data/derived/study2/, `reproduce` re-checks it
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import figures, oc, report, report2, study2, verify
from .load import load_designs, run_dirs


def _designs(paths: list[Path] | None):
    """Frozen designs to validate windows against: the given files, or every design/*.jsonl."""
    return load_designs(paths if paths else sorted(Path("design").glob("*.jsonl")))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="itb-analysis", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("reproduce", "report"):
        p = sub.add_parser(name)
        p.add_argument("--raw", type=Path, default=Path("data/raw"))
        p.add_argument("--derived", type=Path, default=Path("data/derived"))
        p.add_argument("--manifest", type=Path, default=None,
                       help="campaign manifest (design/campaign.json). Must exist when given; without it every run "
                            "under --raw is analysed and nothing is confirmatory")
        p.add_argument("--design", type=Path, action="append", default=None,
                       help="frozen design file(s) to validate windows against (default: every design/*.jsonl)")
        p.add_argument("--figures", type=Path, default=Path("figures"), help="committed figures to re-check (reproduce)")
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
    f = sub.add_parser("figures")
    f.add_argument("--results", type=Path, default=Path("data/derived/results.json"))
    f.add_argument("--raw", type=Path, default=Path("data/raw"))
    f.add_argument("--manifest", type=Path, default=Path("design/campaign.json"))
    f.add_argument("--design", type=Path, default=Path("design/design.jsonl"))
    f.add_argument("--out", type=Path, default=Path("figures"))
    s2 = sub.add_parser("study2")
    s2.add_argument("action", choices=["report", "reproduce"])
    s2.add_argument("--raw", type=Path, default=Path("data/raw"))
    s2.add_argument("--manifest", type=Path, default=Path("design/campaign-study2.json"))
    s2.add_argument("--derived", type=Path, default=Path("data/derived/study2"))
    s2.add_argument("--study1-results", type=Path, default=Path("data/derived/results.json"))
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if a.cmd == "report":
        path = report.write(report.compute(a.raw, a.manifest, designs=_designs(a.design)), a.derived)
        print(f"wrote {path}")
        return 0
    if a.cmd == "reproduce":
        fresh = report.compute(a.raw, a.manifest, designs=_designs(a.design))
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
        if a.manifest is not None and a.figures.is_dir():
            stale = figures.check(committed_path, a.raw, a.manifest, Path("design/design.jsonl"), a.figures)
            if stale:
                print(f"FIGURES NOT REPRODUCED: {', '.join(stale)} (redraw with `itb-analysis figures`)")
                return 1
            print(f"REPRODUCED: every figure in {a.figures}/ redrawn byte for byte.")
        # Study 2, once frozen and analysed: the same check against data/derived/study2. The manifest path goes in as a
        # POSIX string, because the results record it and must be the same bytes on every platform.
        manifest2, committed2 = Path("design/campaign-study2.json"), a.derived / "study2" / "results.json"
        if a.manifest is not None and manifest2.exists() and committed2.exists():
            fresh2 = report._clean(study2.compute(a.raw, manifest2.as_posix(), _designs(a.design), committed_path))
            diffs2 = report.compare(json.loads(json.dumps(fresh2)), json.loads(committed2.read_text()), tol=1e-9)
            print("\n" + report2.markdown_summary(fresh2))
            if diffs2:
                print(f"STUDY 2 REPRODUCTION FAILED: {len(diffs2)} differences, e.g.:\n  " + "\n  ".join(diffs2[:20]))
                return 1
            print(f"REPRODUCED: every Study 2 number in {committed2} recomputed from {a.raw}.")
        return 0
    if a.cmd == "verify":
        rep = verify.verify(run_dirs(a.raw), a.source, a.rpc_url, None if a.sample == 0 else a.sample)
        verify.print_ledger(rep)
        if a.json:
            a.json.write_text(json.dumps(rep, indent=1))
        return 0 if rep["passed"] else 1
    if a.cmd == "study2":
        fresh = report._clean(study2.compute(a.raw, a.manifest.as_posix(), _designs(None), a.study1_results))
        print(report2.markdown_summary(fresh))
        path = a.derived / "results.json"
        if a.action == "report":
            report.write(fresh, a.derived)
            (a.derived / "summary.md").write_bytes(report2.markdown_summary(fresh).encode())
            print(f"wrote {path}")
            return 0
        if not path.exists():
            print(f"no committed {path}; nothing to compare (run `study2 report` first)")
            return 1
        diffs = report.compare(json.loads(json.dumps(fresh)), json.loads(path.read_text()), tol=1e-9)
        if diffs:
            print(f"STUDY 2 REPRODUCTION FAILED: {len(diffs)} differences, e.g.:\n  " + "\n  ".join(diffs[:20]))
            return 1
        print(f"REPRODUCED: every Study 2 number in {path} recomputed from {a.raw}.")
        return 0
    if a.cmd == "figures":
        for path in figures.build(a.results, a.raw, a.manifest, a.design, a.out):
            print(f"wrote {path}")
        return 0
    if a.cmd == "oc":
        res = oc.run(a.design, a.targets, a.reps, a.n_draws)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(res, indent=1))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
