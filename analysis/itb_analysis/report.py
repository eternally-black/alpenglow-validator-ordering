"""Derived results: everything the report states, recomputed from raw data only (deterministic, seeded).

Confirmatory cohort (PREREGISTRATION §2, §4): with a campaign manifest, only live runs whose design hash and genesis
hash match the manifest enter, the family is fixed at 6 core validators × 3 contrasts × 2 codings = 36 effects
(missing effects count as p = 1), and every validator is analysed per (client, ingress) actually observed in its
windows. Without a manifest (simulations, localnet tests) every run is analysed and the result is marked as such.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import outcomes, stats
from .load import Run, load_runs, run_dirs

FAMILY = stats.FAMILY_SIZE


def _effect(e: stats.Effect) -> dict:
    lo, hi = e.interval
    return {"k": e.k, "n": e.n, "estimate": None if e.n == 0 else round(e.estimate, 6), "ci_bonferroni": [round(lo, 6), round(hi, 6)]}


def _clean(x):
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, stats.Effect):
        return _effect(x)
    if isinstance(x, (np.floating, float)):
        return None if np.isnan(x) else round(float(x), 6)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def load_manifest(path: Path | None) -> dict | None:
    if path is None or not Path(path).exists():
        return None
    return json.loads(Path(path).read_text())


def select_runs(raw_root: Path, manifest: dict | None) -> tuple[list[Path], list[dict]]:
    chosen, rejected = [], []
    for d in run_dirs(raw_root):
        start = json.loads((d / "run_start.json").read_text())
        if manifest is not None:
            why = []
            if start.get("mode") != "live":
                why.append(f"mode={start.get('mode')}")
            if start.get("design_sha256") != manifest.get("design_sha256"):
                why.append("design_sha256 mismatch")
            if start.get("genesis_hash") != manifest.get("genesis_hash"):
                why.append("genesis mismatch")
            if start.get("run_id") in manifest.get("excluded_run_ids", []):
                why.append("excluded in manifest")
            if why:
                rejected.append({"run_id": start.get("run_id"), "reasons": why})
                continue
        chosen.append(d)
    return chosen, rejected


def _achieved_offsets(run: Run) -> pd.DataFrame:
    """Per window: first send (stream finished) minus the observed first shred of the target's first slot, in ms."""
    w, s = run.windows, run.sends
    if w.empty or s.empty or "finished_unix_ns" not in s:
        return pd.DataFrame(columns=["run_id", "target_identity", "seq", "achieved_offset_ms"])
    s = s.dropna(subset=["finished_unix_ns"]).copy()
    s["target8"] = s["probe_id"].str.split("/").str[0]
    s["seq"] = s["probe_id"].str.split("/").str[1].astype(int)
    first_send = s.groupby(["run_id", "target8", "seq"])["finished_unix_ns"].min()
    rows = []
    for _, r in w.iterrows():
        an = r.get("anchors") if isinstance(r.get("anchors"), dict) else {}
        ws = an.get("WindowSlot") or {}
        ps = an.get("PrevSlot") or {}
        ref = ws.get("anchor_unix_ns") if ws.get("observed") else (ps["anchor_unix_ns"] + ps.get("extra_ms", 0) * 1e6 if ps.get("observed") else None)
        key = (r["run_id"], r["target_identity"][:8], int(r["seq"]))
        if ref is None or key not in first_send.index:
            continue
        rows.append({"run_id": r["run_id"], "target_identity": r["target_identity"], "seq": int(r["seq"]),
                     "achieved_offset_ms": (first_send[key] - ref) / 1e6})
    return pd.DataFrame(rows)


def _session_bootstrap(pairs: pd.DataFrame, reps: int = 1000, seed: int = 0) -> dict:
    """Percentile 95 % intervals of L_c when whole sessions (runs) are resampled."""
    runs = pairs["run_id"].unique()
    out = {}
    if len(runs) < 2:
        return {c: None for c in stats.CONTRASTS} | {"sessions": int(len(runs))}
    rng = np.random.default_rng(seed)
    for c in stats.CONTRASTS:
        g = pairs[(pairs["pair_kind"] == c) & pairs["evaluable"]].dropna(subset=["x_first_cc"])
        by_run = {r: (g[g["run_id"] == r]["x_first_cc"].sum(), (g["run_id"] == r).sum()) for r in runs}
        est = []
        for _ in range(reps):
            pick = rng.choice(runs, size=len(runs), replace=True)
            k = sum(by_run[r][0] for r in pick)
            n = sum(by_run[r][1] for r in pick)
            if n:
                est.append(k / n)
        out[c] = [float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))] if est else None
    out["sessions"] = int(len(runs))
    return out


def _worst_case(pairs: pd.DataFrame) -> dict:
    """Bounds on L_c when every pair with exactly one landed member is counted against / for x."""
    out = {}
    for c in stats.CONTRASTS:
        g = pairs[(pairs["pair_kind"] == c) & pairs["evaluable"]]
        cc = g.dropna(subset=["x_first_cc"])
        single = int((g["landed_x"] ^ g["landed_y"]).sum())
        k, n = int(cc["x_first_cc"].sum()), len(cc)
        out[c] = {"complete": n, "single_landed": single,
                  "L_min": k / (n + single) if n + single else None, "L_max": (k + single) / (n + single) if n + single else None}
    return out


def _labels(eff: dict) -> dict:
    return {c: _effect(e) for c, e in eff["label"].items()}


def compute(raw_root: Path, manifest_path: Path | None = None, n_draws: int = stats.N_RANDOMISATION) -> dict:
    manifest = load_manifest(manifest_path)
    dirs, rejected = select_runs(raw_root, manifest)
    if not dirs:
        return {"runs": [], "rejected_runs": rejected, "note": f"no eligible runs under {raw_root}"}
    run = load_runs(dirs)
    pairs = outcomes.pair_table(run)
    windows = outcomes.window_table(run)
    offsets = _achieved_offsets(run)
    if len(pairs) and len(offsets):
        pairs = pairs.merge(offsets, on=["run_id", "target_identity", "seq"], how="left")
    core = set(manifest.get("core_targets", [])) if manifest else None
    result: dict = {
        "manifest": manifest is not None,
        "runs": [{"run_id": s.get("run_id"), "mode": s.get("mode"), "stage": s.get("stage"), "started_at": s.get("started_at"),
                  "budget": s.get("budget")} for s in run.starts],
        "rejected_runs": rejected,
        "funnel": outcomes.funnel(run).to_dict(orient="records"),
        "validators": {},
    }
    pvals = {}
    if not len(pairs):
        return _clean(result)
    main = pairs[pairs["pair_kind"].isin(["c1", "c2", "c3", "c2_uncontended"])]
    for (target, client, ingress), g in main.groupby(["target_identity", "client_id", "ingress"], dropna=False):
        key = f"{target}|{client}|{ingress}"
        eff = stats.validator_effects(g, n_draws=n_draws)
        relaxed = g.copy()
        wsub = windows[windows["target_identity"] == target].set_index(["run_id", "seq"])
        ambiguous_ok = [(r, s) for (r, s), row in wsub.iterrows() if row["exclusion"] in ("", "mode:transition_ambiguous")]
        relaxed["evaluable"] = [(r, s) in set(ambiguous_ok) for r, s in zip(relaxed["run_id"], relaxed["seq"])]
        sens = {
            "censored": _labels(stats.validator_effects(g, n_draws=min(n_draws, 2_000), estimand="censored")),
            "worst_case": _worst_case(g),
            "session_bootstrap_L": _session_bootstrap(g),
            "regime": {reg: _labels(stats.validator_effects(gg, n_draws=min(n_draws, 2_000))) for reg, gg in g.groupby("regime")},
            "including_transition_ambiguous": _labels(stats.validator_effects(relaxed, n_draws=min(n_draws, 2_000))),
        }
        if "achieved_offset_ms" in g:
            bins = pd.cut(g["achieved_offset_ms"], [-1e9, -100, 0, 100, 1e9], labels=["<-100ms", "-100..0ms", "0..100ms", ">100ms"])
            sens["achieved_offset"] = {str(b): _labels(stats.validator_effects(gg, n_draws=min(n_draws, 2_000))) for b, gg in g.groupby(bins, observed=True)}
        uncontended = g[(g["pair_kind"] == "c2_uncontended") & g["evaluable"]].dropna(subset=["x_first_cc"])
        result["validators"][key] = {
            "target_identity": target,
            "client_id": client,
            "ingress": ingress,
            "confirmatory": core is None or target in core,
            "label": _labels(eff),
            "order": {c: _effect(e) for c, e in eff["order"].items()},
            "randomisation_p": eff["pvalues"],
            "inclusion": eff["inclusion"],
            "rules": eff["rules"],
            "diagnosis": eff["diagnosis"],
            "strictness": eff["strictness"],
            "mixture": eff["mixture"],
            "selection": eff["selection"],
            "exploratory_uncontended_c2": {"k": int(uncontended["x_first_cc"].sum()), "n": len(uncontended)},
            "sensitivity": sens,
        }
        if core is None or target in core:
            for c, p in eff["pvalues"].items():
                pvals[f"{key}/{c}/label"] = p["label"]
                pvals[f"{key}/{c}/order"] = p["order"]
    result["holm"] = stats.holm(pvals, family_size=FAMILY if manifest else None)
    # §9 gates.
    if manifest:
        controls = manifest.get("positive_controls", [])
        ok = {t: any(v["target_identity"] == t and v["rules"]["reward_cost"]["status"] in ("SUPPORTED", "CONFIRMED")
                     for v in result["validators"].values()) for t in controls}
        result["positive_controls"] = ok
        result["closed_source_conclusions_withdrawn"] = not all(ok.values()) if ok else True
        buffered_broken = {}
        for k, v in result["validators"].items():
            reg = v["sensitivity"]["regime"].get("buffered")
            if v["ingress"] == "direct" and reg:
                buffered_broken[k] = False  # order effects in the buffered regime are inspected below
        result["buffer_assumption_checks"] = buffered_broken
    return _clean(result)


def write(result: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "results.json"
    path.write_text(json.dumps(result, indent=1, sort_keys=True))
    return path


def compare(a, b, tol: float = 1e-9, path: str = "") -> list[str]:
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
    lines = ["| Validator | Client | Ingress | L_C1 | L_C2 | L_C3 | Verdict | Non-rejected rules |", "|---|---|---|---|---|---|---|---|"]
    for r in result.get("validators", {}).values():
        def f(e):
            return "–" if e["n"] == 0 else f"{e['estimate']:.2f} [{e['ci_bonferroni'][0]:.2f}, {e['ci_bonferroni'][1]:.2f}] (n={e['n']})"
        keep = [f"{k} ({s['status']})" for k, s in r["rules"].items() if s["status"] != "REJECTED"]
        lines.append(f"| `{r['target_identity'][:8]}…` | {r['client_id']} | {r['ingress']} | {f(r['label']['c1'])} | {f(r['label']['c2'])} | "
                     f"{f(r['label']['c3'])} | **{r['diagnosis']['verdict']}** | {', '.join(keep) or 'none'} |")
    return "\n".join(lines)
