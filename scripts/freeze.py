#!/usr/bin/env python3
"""Freeze a study (PREREGISTRATION, "On freezing"): write its manifest and print the Memo text.

The manifest fixes what the report treats as confirmatory: the design and genesis hashes a run must carry, the six
core targets (the 36-effect family), the positive controls and the stopping date. The Memo commits the hashes of
the pre-registration, the design and this manifest on mainnet before the study's first window:

    python scripts/freeze.py --targets design/targets.json --design design/design.jsonl
    PYTHONPATH=analysis python scripts/freeze.py --study 2 --targets design/targets-study2.json \\
        --design design/design-study2.jsonl
    itb setup memo --live --max-spend-sol 0.05 --text "<printed text>"

Study 2 adds its hypotheses (from `itb_analysis.study2.SPEC`), the spend carried over from Study 1, and the git tree
of `analysis/` at the freeze commit, so the Memo also fixes the code that decides the hypotheses (`analysis/` must be
committed and clean). A manifest is written once; an existing file is never overwritten (a change after freezing is a
Deviation).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

MAINNET_GENESIS_HASH = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"
#: Clients whose scheduler is public: if the method cannot recover their rule, closed-source conclusions are withdrawn.
POSITIVE_CONTROL_CLIENTS = ("Agave", "Firedancer")
#: Study 1's measured total cost (docs/CAMPAIGN-LOG.md): 0.1 SOL + 13,023 deposits − 75,295,523 returned.
STUDY1_COST_LAMPORTS = 24_717_500
#: Studies 1 and 2 together, everything included (REPORT §11): 24,717,500 + 18,208,500.
STUDIES_1_2_COST_LAMPORTS = 42_926_000
STUDIES = {
    1: {"prereg": "docs/PREREGISTRATION.md", "out": "design/campaign.json", "budget": "campaign",
        "not_after": "2026-10-29T23:59:00Z"},
    2: {"prereg": "docs/PREREGISTRATION-2.md", "out": "design/campaign-study2.json", "budget": "study2",
        "not_after": "2026-10-30T23:59:00Z"},
    3: {"prereg": "docs/PREREGISTRATION-3.md", "out": "design/campaign-study3.json", "budget": "study3",
        "not_after": "2026-11-03T23:59:00Z"},
}


def sha256(path: Path) -> str:
    """Hash of the exact bytes a clone will hold. The repository stores LF (`.gitattributes`), so a CR in a hashed
    file would make the published hash unverifiable from a checkout: refuse it."""
    data = path.read_bytes()
    if b"\r" in data:
        raise SystemExit(f"{path} contains CR line endings; normalise it to LF before freezing")
    return hashlib.sha256(data).hexdigest()


def analysis_tree() -> str:
    """Git tree id of `analysis/` at HEAD, after checking that the working tree adds nothing to it."""
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "analysis"], capture_output=True, text=True, check=True)
    if dirty.stdout.strip():
        raise SystemExit("analysis/ has uncommitted changes; commit them before freezing")
    return subprocess.run(["git", "rev-parse", "HEAD:analysis"], capture_output=True, text=True, check=True).stdout.strip()


def manifest(targets: list[dict], design: Path, prereg: Path, not_after: str, budget: str = "campaign") -> dict:
    core_t = [t for t in targets if t.get("tier", "core") == "core"]
    if len(core_t) != 6:
        raise SystemExit(f"the confirmatory family needs exactly 6 core targets, got {len(core_t)}")
    # Each core target is frozen together with the (client, ingress) group that is confirmatory for it: windows in any
    # other group (the validator switched BAM/Harmonic on or off) are analysed as exploratory, outside the family.
    core = [{"identity": t["identity"], "client_id": t["client_id"], "ingress": t["ingress"]} for t in core_t]
    controls = [t["identity"] for t in core_t if t["client_id"] in POSITIVE_CONTROL_CLIENTS and t["ingress"] == "direct"]
    if {t["client_id"] for t in core_t if t["identity"] in controls} != set(POSITIVE_CONTROL_CLIENTS):
        raise SystemExit("core targets must include a direct-ingress Agave and a direct-ingress Firedancer validator")
    if len({t["client_id"] for t in targets}) < 3:
        raise SystemExit("the brief requires at least 3 client types")
    return {
        "frozen_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "genesis_hash": MAINNET_GENESIS_HASH,
        "design_sha256": sha256(design),
        "preregistration_sha256": sha256(prereg),
        "core_targets": core,
        "extended_targets": [t["identity"] for t in targets if t not in core_t],
        "positive_controls": controls,
        "budget": budget,
        "not_after": not_after,
        "excluded_run_ids": [],
    }


def planned_n(design: Path, h: dict) -> int:
    """Pairs the design plans for a hypothesis: its kind and Δt on its targets (races: `lo` sent first)."""
    ids = {g["identity"] for g in h["groups"]}
    n = 0
    for line in design.read_text().splitlines():
        plan = json.loads(line)
        if plan["target_identity"] in ids:
            n += sum(1 for q in plan["pairs"] if q["kind"] == h["pair_kind"] and q.get("race_dt_ms") == h["dt_ms"]
                     and (h["pair_kind"] != "race" or q["first_sent_label"] == "lo"))
    return n


def study2_fields(targets: list[dict], design: Path) -> dict:
    from itb_analysis import study2  # PYTHONPATH=analysis

    hyps = study2.hypotheses(targets)
    for h in hyps:
        h["planned_n"] = planned_n(design, h)
        if h["planned_n"] == 0:
            raise SystemExit(f"{h['id']}: the design plans no pair for it")
    return {"study": 2, "hypotheses": hyps, "carry_over_lamports": STUDY1_COST_LAMPORTS, "analysis_tree": analysis_tree()}


#: the committed results whose per-target published claims Study 3's identification verdict combines with (§5)
PRIOR_RESULTS = {"study1": (Path("data/derived/results.json"), ()),
                 "study2": (Path("data/derived/study2/results.json"), ("replication",))}


def prior_claims(targets: list[dict]) -> tuple[dict, dict]:
    """Study 1 and Study 2 published claims per core target, frozen with their source files' hashes and commit, so the
    identification verdict cannot depend on files edited after the freeze."""
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    claims: dict[str, dict] = {}
    provenance = {}
    for study, (path, keys) in PRIOR_RESULTS.items():
        dirty = subprocess.run(["git", "status", "--porcelain", "--", str(path)], capture_output=True, text=True, check=True)
        if dirty.stdout.strip():
            raise SystemExit(f"{path} has uncommitted changes; commit it before freezing")
        # The committed blob, byte for byte what a clone holds (a Windows checkout may carry CRLF in the working copy).
        blob = subprocess.run(["git", "show", f"HEAD:{path.as_posix()}"], capture_output=True, check=True).stdout
        doc = json.loads(blob)
        for k in keys:
            doc = doc[k]
        for t in (t for t in targets if t.get("tier", "core") == "core"):
            v = doc["validators"].get(f"{t['identity']}|{t['client_id']}|{t['ingress']}")
            if v is None:
                raise SystemExit(f"{path}: no {study} claim for {t['identity']} ({t['client_id']}, {t['ingress']})")
            claims.setdefault(t["identity"], {})[study] = v["published_claim"]
        provenance[study] = {"path": path.as_posix(), "sha256": hashlib.sha256(blob).hexdigest(), "commit": head}
    return claims, provenance


def study3_fields(targets: list[dict], design: Path) -> dict:
    from itb_analysis import study3  # PYTHONPATH=analysis

    hyps = study3.hypotheses(targets)
    for h in hyps:
        h["planned_n"] = planned_n(design, h | {"dt_ms": None})
        if h["planned_n"] == 0:
            raise SystemExit(f"{h['id']}: the design plans no pair for it")
    claims, provenance = prior_claims(targets)
    return {"study": 3, "hypotheses": hyps, "prior_claims": claims, "prior_claims_source": provenance,
            "carry_over_lamports": STUDIES_1_2_COST_LAMPORTS, "analysis_tree": analysis_tree()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--study", type=int, choices=sorted(STUDIES), default=1)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--design", type=Path, required=True)
    ap.add_argument("--prereg", type=Path, default=None)
    ap.add_argument("--not-after", default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    s = STUDIES[a.study]
    prereg, out = a.prereg or Path(s["prereg"]), a.out or Path(s["out"])
    if out.exists():
        raise SystemExit(f"{out} exists; a frozen manifest is never overwritten")
    targets = json.loads(a.targets.read_text())
    m = manifest(targets, a.design, prereg, a.not_after or s["not_after"], s["budget"])
    if a.study == 2:
        m |= study2_fields(targets, a.design)
    elif a.study == 3:
        m |= study3_fields(targets, a.design)
    out.write_bytes((json.dumps(m, indent=1) + "\n").encode())  # LF on every platform
    print(f"itb-prereg v{a.study} prereg={m['preregistration_sha256']} design={m['design_sha256']} manifest={sha256(out)}")


if __name__ == "__main__":
    main()
