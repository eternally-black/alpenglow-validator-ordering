"""Derived results: everything the report states, recomputed from raw data only (deterministic, seeded)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import outcomes, stats
from .load import load_runs, run_dirs


def _effect_dict(e: stats.Effect) -> dict:
    lo, hi = e.interval
    return {"k": e.k, "n": e.n, "estimate": None if e.n == 0 else round(e.estimate, 6), "ci_bonferroni": [round(lo, 6), round(hi, 6)]}


def compute(raw_root: Path, n_draws: int = stats.N_RANDOMISATION) -> dict:
    dirs = [d for d in run_dirs(raw_root)]
    if not dirs:
        return {"runs": [], "note": f"no runs under {raw_root}"}
    run = load_runs(dirs)
    pairs = outcomes.pair_table(run)
    windows = outcomes.window_table(run)
    result: dict = {
        "runs": [{"run_id": s.get("run_id"), "mode": s.get("mode"), "stage": s.get("stage"), "started_at": s.get("started_at")}
                 for s in run.starts],
        "funnel": outcomes.funnel(run).replace({np.nan: None}).to_dict(orient="records"),
        "validators": {},
    }
    pvals = {}
    for target, g in pairs.groupby("target_identity"):
        eff = stats.validator_effects(g, n_draws=n_draws)
        meta = windows[windows["target_identity"] == target].iloc[0]
        result["validators"][target] = {
            "client_id": meta.get("client_id"),
            "ingress": meta.get("ingress"),
            "label": {c: _effect_dict(e) for c, e in eff["label"].items()},
            "order": _effect_dict(eff["order"]),
            "order_by_contrast": {c: _effect_dict(e) for c, e in eff["order_by_contrast"].items()},
            "randomisation_p": eff["pvalues"],
            "inclusion": eff["inclusion"],
            "rules": eff["rules"],
            "strictness": {r: stats.strictness(g, r) for r, v in eff["rules"].items() if v["status"] in ("SUPPORTED", "CONFIRMED")},
        }
        for c, p in eff["pvalues"].items():
            pvals[f"{target}/{c}/label"] = p["label"]
            pvals[f"{target}/{c}/order"] = p["order"]
    result["holm"] = stats.holm(pvals)
    return result


def write(result: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "results.json"
    path.write_text(json.dumps(result, indent=1, sort_keys=True, default=lambda o: None if isinstance(o, float) and np.isnan(o) else str(o)))
    return path


def compare(a: dict, b: dict, tol: float = 1e-9, path: str = "") -> list[str]:
    """Differences between two results dicts (numbers compared with tolerance)."""
    diffs = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                diffs.append(f"{path}/{k}: present in only one")
            else:
                diffs += compare(a[k], b[k], tol, f"{path}/{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: length {len(a)} != {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                diffs += compare(x, y, tol, f"{path}[{i}]")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if not (abs(a - b) <= tol * max(1.0, abs(a), abs(b))):
            diffs.append(f"{path}: {a} != {b}")
    elif a != b:
        diffs.append(f"{path}: {a!r} != {b!r}")
    return diffs


def markdown_summary(result: dict) -> str:
    lines = ["| Validator | Client | Ingress | L_C1 | L_C2 | L_C3 | O | Non-rejected rules |", "|---|---|---|---|---|---|---|---|"]
    for v, r in result.get("validators", {}).items():
        def f(e):
            return "–" if e["n"] == 0 else f"{e['estimate']:.2f} [{e['ci_bonferroni'][0]:.2f}, {e['ci_bonferroni'][1]:.2f}] (n={e['n']})"
        keep = [f"{k} ({s['status']})" for k, s in r["rules"].items() if s["status"] != "REJECTED"]
        lines.append(f"| `{v[:8]}…` | {r['client_id']} | {r['ingress']} | {f(r['label']['c1'])} | {f(r['label']['c2'])} | "
                     f"{f(r['label']['c3'])} | {f(r['order'])} | {', '.join(keep) or 'none'} |")
    return "\n".join(lines)
