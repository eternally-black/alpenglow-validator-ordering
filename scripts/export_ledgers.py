#!/usr/bin/env python3
"""Export the two spend ledgers to data/derived/ledgers/ (REPORT §11).

    python scripts/export_ledgers.py

The ledgers (`state/ledger.sqlite`, Study 1; `state/ledger-study2.sqlite`, Study 2) are local working state. This
writes every reservation they hold (signature, purpose, status, worst-case and actual fee, payer, run and probe) as
CSV, plus each ledger's cap, carry-over, opening balance, deposits, adjustments and totals, so the cost tables can be
recomputed without the database and each landed fee can be checked on chain by its signature. Nothing secret is in a
ledger: payers appear by public key.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

LEDGERS = {"study1": Path("state/ledger.sqlite"), "study2": Path("state/ledger-study2.sqlite")}
COLUMNS = ["signature", "kind", "label", "budget", "status", "max_fee", "actual_fee", "charged_fee", "payer", "run_id",
           "probe_id", "target_identity", "window_first_slot", "created_at", "resolved_at"]


def export(name: str, path: Path, out: Path) -> dict:
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM reservations ORDER BY created_at, signature")]
    for r in rows:
        # What the cap counts (ledger.rs CHARGED_FEE_SQL): landed at the actual fee, open or expired at the worst case.
        r["charged_fee"] = {"landed": r["actual_fee"], "reserved": r["max_fee"], "expired_charged": r["max_fee"]}.get(r["status"], 0)
    with (out / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    meta = {k: v for k, v in con.execute("SELECT key, value FROM meta")}
    totals: dict = {}
    for r in rows:
        t = totals.setdefault(r["budget"], {}).setdefault(r["status"], {"count": 0, "fee": 0})
        t["count"] += 1
        t["fee"] += r["actual_fee"] if r["status"] == "landed" else (r["max_fee"] if r["status"] != "cancelled_unsent" else 0)
    return {
        "ledger": str(path), "cap_lamports": int(meta["cap_lamports"]),
        "carry_over_lamports": int(meta.get("carry_over_lamports", 0)), "carry_over_reason": meta.get("carry_over_reason"),
        "opening_total_lamports": int(meta["opening_total"]), "external_deposits_lamports": int(meta.get("external_deposits", 0)),
        "owned_accounts": json.loads(meta["owned_accounts"]),
        "adjustments": [dict(a) for a in con.execute("SELECT lamports, reason, at FROM adjustments")],
        "landed_fees_lamports": sum(r["actual_fee"] for r in rows if r["status"] == "landed"),
        "charged_lamports": sum(r["charged_fee"] or 0 for r in rows),
        "by_budget_and_status": totals,
    }


def main() -> None:
    out = Path("data/derived/ledgers")
    out.mkdir(parents=True, exist_ok=True)
    summary = {name: export(name, path, out) for name, path in LEDGERS.items() if path.exists()}
    (out / "summary.json").write_bytes((json.dumps(summary, indent=1) + "\n").encode())
    for name, s in summary.items():
        print(f"{name}: landed fees {s['landed_fees_lamports']:,}, charged {s['charged_lamports']:,} (+ carry-over "
              f"{s['carry_over_lamports']:,}), cap {s['cap_lamports']:,}")


if __name__ == "__main__":
    main()
