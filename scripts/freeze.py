#!/usr/bin/env python3
"""Freeze the campaign (PREREGISTRATION, "On freezing"): write design/campaign.json and print the Memo text.

The manifest fixes what the report treats as confirmatory: the design and genesis hashes a run must carry, the six
core targets (the 36-effect family), the positive controls and the stopping date. The Memo commits the hashes of
the pre-registration, the design and this manifest on mainnet before the first campaign window:

    python scripts/freeze.py --targets design/targets.json --design design/design.jsonl
    itb setup memo --live --max-spend-sol 0.05 --text "<printed text>"

A manifest is written once; an existing file is never overwritten (a change after freezing is a Deviation).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

MAINNET_GENESIS_HASH = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"
#: Clients whose scheduler is public: if the method cannot recover their rule, closed-source conclusions are withdrawn.
POSITIVE_CONTROL_CLIENTS = ("Agave", "Firedancer")


def sha256(path: Path) -> str:
    """Hash of the exact bytes a clone will hold. The repository stores LF (`.gitattributes`), so a CR in a hashed
    file would make the published hash unverifiable from a checkout: refuse it."""
    data = path.read_bytes()
    if b"\r" in data:
        raise SystemExit(f"{path} contains CR line endings; normalise it to LF before freezing")
    return hashlib.sha256(data).hexdigest()


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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--design", type=Path, required=True)
    ap.add_argument("--prereg", type=Path, default=Path("docs/PREREGISTRATION.md"))
    ap.add_argument("--not-after", default="2026-10-29T23:59:00Z")
    ap.add_argument("--out", type=Path, default=Path("design/campaign.json"))
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"{a.out} exists; a frozen manifest is never overwritten")
    m = manifest(json.loads(a.targets.read_text()), a.design, a.prereg, a.not_after)
    a.out.write_bytes((json.dumps(m, indent=1) + "\n").encode())  # LF on every platform
    print(f"itb-prereg v1 prereg={m['preregistration_sha256']} design={m['design_sha256']} manifest={sha256(a.out)}")


if __name__ == "__main__":
    main()
