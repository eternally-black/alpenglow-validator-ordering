#!/usr/bin/env python3
"""Re-decide Study 3 with the analysis code the Memo froze, not the checkout's.

    python scripts/verify_frozen_study3.py [--results data/derived/study3/results.json]

The Study 3 manifest (hashed in the Memo) records `analysis_tree`, the git tree of `analysis/` at the freeze commit.
This script extracts exactly that tree with `git archive`, imports `itb_analysis` from it, recomputes Study 3 from
`data/raw`, and compares every number with the published results. Later commits may add reporting code to
`analysis/`; this shows that none of it changed a decision. The Study 1 and Study 2 claims the verdict combines with
are read from the manifest itself (`prior_claims`), so they are frozen too.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, default=Path("design/campaign-study3.json"))
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument("--results", type=Path, default=Path("data/derived/study3/results.json"))
    a = ap.parse_args()
    tree = json.loads(a.manifest.read_text())["analysis_tree"]
    archive = subprocess.run(["git", "archive", "--format=tar", tree], capture_output=True, check=True).stdout
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(tmp, filter="data")
        sys.path.insert(0, tmp)
        from itb_analysis import load, report, study3  # the frozen modules

        assert Path(study3.__file__).resolve().is_relative_to(Path(tmp).resolve()), "imported the checkout, not the tree"
        designs = load.load_designs(sorted(Path("design").glob("*.jsonl")))
        fresh = report._clean(study3.compute(a.raw, a.manifest.as_posix(), designs))
        diffs = report.compare(json.loads(json.dumps(fresh)), json.loads(a.results.read_text()), tol=1e-9)
    if diffs:
        print(f"MISMATCH with the frozen analysis tree {tree}: {len(diffs)} differences, e.g.:\n  " + "\n  ".join(diffs[:20]))
        return 1
    print(f"VERIFIED: the analysis tree frozen in the manifest ({tree}) reproduces every number in {a.results}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
