#!/usr/bin/env python3
"""Build the probe explorer: docs/explorer/data.json and docs/explorer/index.html (template.html with the data embedded).

    python scripts/build_explorer.py

Every window of every confirmatory run of the three studies (runs selected by each study's frozen manifest), with its
eligibility, and every probe with its signature, status and landing position, so that each published claim can be
followed down to single transactions on the block explorer. Group summaries come from the committed results files;
nothing is recomputed differently here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from itb_analysis import outcomes, report  # noqa: E402
from itb_analysis.load import load_designs, load_runs  # noqa: E402

STUDIES = (
    {"id": 1, "manifest": "design/campaign.json", "results": "data/derived/results.json",
     "memo": "5vRM47a8LfMLm1rQyQKdap292hmXk68kbad6Vf12nCxuzaZVGJSuL4g2DyLGNyZjsphPQLtVAqFkT3VxmRmLQcyg"},
    {"id": 2, "manifest": "design/campaign-study2.json", "results": "data/derived/study2/results.json",
     "memo": "2T6ha9FDfjp524NLBXFB2WRHvEaYAoQLKFcd7Pmwqmf8FzqHi3Pxf8TcacHm7ixiN8UoyQizReCSSmh5LAR7D5ww"},
    {"id": 3, "manifest": "design/campaign-study3.json", "results": "data/derived/study3/results.json",
     "memo": "2C57e22K29Hj1v5z1J3Wrp3gXS717KQBrzVuMgPQKWhMX7Lv38VZmsWybxHK8A5JErxRW3JHq6dkXRtisRxbeUz5"},
)
STATUS = {"landed_target": "L", "expired_confirmed": "E", "not_sent": "N", "spillover_other_leader": "S",
          "spillover_same_validator_other_window": "W", "unresolved": "U"}


def _int(x):
    return None if x is None or x != x else int(x)


def study(s: dict, designs: dict) -> dict | None:
    manifest = report.load_manifest(Path(s["manifest"])) if Path(s["manifest"]).exists() else None
    if manifest is None:
        return None
    dirs, _ = report.select_runs(Path("data/raw"), manifest)
    if not dirs:
        return None
    run = load_runs(dirs)
    w = outcomes.window_table(run, designs)
    p = outcomes.probe_table(run)
    results_path = Path(s["results"])
    results = json.loads(results_path.read_text()) if results_path.exists() else {}
    validators = results.get("validators") or results.get("replication", {}).get("validators", {})
    windows = []
    for (run_id, target, seq), g in p.groupby(["run_id", "target_identity", "seq"]):
        row = w[(w["run_id"] == run_id) & (w["target_identity"] == target) & (w["seq"] == seq)]
        if row.empty:
            continue
        r = row.iloc[0]
        pairs = []
        for pair_id, q in g.groupby("pair_id", sort=True):
            q = q.sort_values("send_position_in_pair")
            pairs.append({
                "id": pair_id.split("/")[-1], "kind": q["pair_kind"].iloc[0],
                "dt": None if q["race_dt_ms"].isna().all() else float(q["race_dt_ms"].iloc[0]),
                "m": [{"l": m["label"], "sig": m["signature"], "st": STATUS.get(m["status"], "U"),
                       "slot": _int(m.get("slot")), "i": _int(m.get("index_in_block")), "n": _int(m.get("block_tx_count"))}
                      for _, m in q.iterrows()],
            })
        windows.append({
            "run": run_id, "t": target, "seq": int(seq), "c": r.get("client_id"), "ing": r.get("ingress"),
            "kit": r["kit"], "reg": r["regime"], "slots": [int(r["window_first_slot"]), int(r["window_first_slot"]) + 3],
            "ev": bool(r["evaluable"]), "ex": r.get("exclusion", "") or "", "pairs": pairs,
        })
    groups = {}
    for key, v in validators.items():
        groups[key] = {"claim": v.get("published_claim"), "confirmatory": v.get("confirmatory"),
                       "label": {c: {"est": e.get("estimate"), "n": e.get("n")} for c, e in v.get("label", {}).items()}}
    for r in results.get("identification", []):  # Study 3: the per-target verdict of PREREGISTRATION-3 §5
        groups[f"{r['identity']}|{r['client_id']}|{r['ingress']}"] = {"claim": r["verdict"], "confirmatory": True, "label": {}}
    return {"id": s["id"], "memo": s["memo"], "runs": [d.name for d in dirs], "groups": groups,
            "hypotheses": [{"id": h["id"], "statement": h["statement"], "k": h["k"], "n": h["n"],
                            "claim": h.get("published_claim"), "groups": h["groups"]} for h in results.get("hypotheses", [])],
            "windows": windows}


def main() -> None:
    designs = load_designs(sorted(Path("design").glob("*.jsonl")))
    out = {"studies": [x for x in (study(s, designs) for s in STUDIES) if x]}
    path = Path("docs/explorer/data.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(out, separators=(",", ":"), default=str).encode())
    # template.html is the page (title, styles, markup, script); index.html wraps it in a document and embeds the
    # ledger before the page script, so it opens from a plain file as well as from static hosting.
    page = (path.parent / "template.html").read_text(encoding="utf-8")
    ledger = json.dumps(out, separators=(",", ":"), default=str).replace("</", "<\\/")
    page = page.replace("<script>", f'<script id="ledger" type="application/json">{ledger}</script>\n<script>', 1)
    head, body = page.split("<header>", 1)
    (path.parent / "index.html").write_bytes(
        ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
         '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
         f"{head.strip()}\n</head>\n<body>\n<header>{body.rstrip()}\n</body>\n</html>\n").encode())
    n_w = sum(len(s["windows"]) for s in out["studies"])
    n_p = sum(len(m) for s in out["studies"] for w in s["windows"] for m in [x["m"] for x in w["pairs"]])
    print(f"wrote {path}: {len(out['studies'])} studies, {n_w} windows, {n_p} probes, {path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
