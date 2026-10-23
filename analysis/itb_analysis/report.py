"""Derived results: everything the report states, recomputed from raw data only (deterministic, seeded).

Confirmatory cohort (PREREGISTRATION §2, §4, §9). It requires a campaign manifest (written by scripts/freeze.py),
passed explicitly — a missing manifest file is an error, never a silent fallback:
- only live runs on the manifest's genesis and design, with the campaign budget, started after the freeze and before
  the cutoff, and not listed as excluded, enter;
- the family is fixed: one group per core target — the (client, ingress) frozen for it in the manifest — × 3
  contrasts × 2 codings = 36 effects (missing effects count as p = 1). Any other (client, ingress) a validator shows
  is analysed but reported as exploratory, outside the family;
- every window's realised probes are checked against the frozen design.
Without a manifest (simulations, localnet tests, previews) every run is analysed and nothing is confirmatory.

Each group's `published_claim` is the verdict after every §9 gate: a broken buffer assumption or a failed positive
control withdraws it, and every renderer prints the published claim, not the raw verdict.
"""

from __future__ import annotations

import json
from datetime import datetime
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
    """None only when no manifest was requested; a requested but missing file is an error (fail closed)."""
    if path is None:
        return None
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"campaign manifest {path} does not exist (omit --manifest for a non-confirmatory preview)")
    return json.loads(path.read_text())


def _ts(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


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
            if start.get("budget") != manifest.get("budget", "campaign"):
                why.append(f"budget={start.get('budget')} (pilot or other purpose)")
            started, frozen, cutoff = _ts(start.get("started_at")), _ts(manifest.get("frozen_at")), _ts(manifest.get("not_after"))
            if started is None or (frozen and started < frozen):
                why.append("started before the freeze")
            if started is not None and cutoff and started > cutoff:
                why.append("started after the cutoff")
            if start.get("run_id") in manifest.get("excluded_run_ids", []):
                why.append("excluded in manifest")
            if why:
                rejected.append({"run_id": start.get("run_id"), "reasons": why})
                continue
        chosen.append(d)
    return chosen, rejected


def _achieved_offsets(run: Run) -> pd.DataFrame:
    """Per window: first send (stream finished) minus the *observed* first-shred event of the target's first slot, in
    ms (createdBank for localnet runs, which anchor on it). Windows without that observed event get no value — an
    estimated anchor is never substituted."""
    cols = ["run_id", "target_identity", "seq", "achieved_offset_ms", "achieved_offset_event"]
    w, s, ev = run.windows, run.sends, run.slot_events
    if w.empty or s.empty or "finished_unix_ns" not in s or ev.empty:
        return pd.DataFrame(columns=cols)
    kind_of = {st.get("run_id"): ("createdBank" if st.get("anchor_event") == "created_bank" else "firstShredReceived")
               for st in run.starts}
    first_ev = ev.sort_values("recv_unix_ns").drop_duplicates(subset=["run_id", "slot", "kind"]).set_index(["run_id", "slot", "kind"])["recv_unix_ns"]
    j = s.dropna(subset=["finished_unix_ns"]).merge(run.probes[["run_id", "probe_id", "target_identity", "seq"]], on=["run_id", "probe_id"])
    first_send = j.groupby(["run_id", "target_identity", "seq"])["finished_unix_ns"].min()
    rows = []
    for _, r in w.iterrows():
        kind = kind_of.get(r["run_id"], "firstShredReceived")
        ref = first_ev.get((r["run_id"], int(r["window_first_slot"]), kind))
        key = (r["run_id"], r["target_identity"], int(r["seq"]))
        if ref is None or key not in first_send.index:
            continue
        rows.append({"run_id": r["run_id"], "target_identity": r["target_identity"], "seq": int(r["seq"]),
                     "achieved_offset_ms": (first_send[key] - ref) / 1e6, "achieved_offset_event": kind})
    return pd.DataFrame(rows, columns=cols)


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


def _labels(eff: dict) -> dict:
    return {c: _effect(e) for c, e in eff["label"].items()}


#: Verdicts that claim an ordering *key*: the buffered regime exists to isolate it.
KEY_VERDICTS = {r for r in stats.ECONOMIC_RULES} | {f"partial:{r}" for r in stats.ECONOMIC_RULES}


def _regime_gates(ingress: str, by_regime: dict[str, dict], verdict: str) -> dict:
    """PREREGISTRATION §9 rows 2-3 for one validator group, from its per-regime effects.

    - buffer_assumption_broken: on direct ingress, some order effect is confirmed "first" in the buffered regime. For a
      key verdict that means the buffered probes did not compete on their key (they did not coexist in the queue), so
      the key conclusion is withdrawn. For an arrival-order verdict it is what FIFO predicts and withdraws nothing.
    - label_effects_streaming_only: label effects appear in streaming windows but in no buffered one."""
    def any_effect(effs: dict) -> bool:
        return any(e.n and (e.interval[0] > 0.5 or e.interval[1] < 0.5) for e in effs.values())

    buf, stream = by_regime.get("buffered"), by_regime.get("streaming")
    broken = any(e.verdict("first") == "confirmed" for e in buf["order"].values()) if ingress == "direct" and buf else None
    streaming_only = any_effect(stream["label"]) and not any_effect(buf["label"]) if buf and stream else None
    return {"buffer_assumption_broken": broken, "label_effects_streaming_only": streaming_only,
            "key_conclusions_withdrawn": bool(broken) and verdict in KEY_VERDICTS}


#: Qualifier of a rule claim that does not survive the worst-case selection bounds (PREREGISTRATION §1).
ASSUMES_SELECTION = " (assumes selection)"


def published_claim(v: dict, controls_failed: bool, is_control: bool) -> str:
    """The claim a group's verdict supports after every gate (PREREGISTRATION §1, §9)."""
    verdict = v["diagnosis"]["verdict"]
    if v["gates"].get("key_conclusions_withdrawn"):
        return "withdrawn: buffer assumption broken"
    if controls_failed and not is_control:
        return "withdrawn: positive control failed"
    if v["diagnosis"].get("selection_robust") is False:
        verdict += ASSUMES_SELECTION
    if not v["confirmatory"]:
        return f"exploratory: {verdict}"
    return verdict


def compute(raw_root: Path, manifest_path: Path | None = None, n_draws: int = stats.N_RANDOMISATION,
            designs: dict | None = None, sensitivities: bool = True) -> dict:
    """`designs`: {sha256: plans} from `load.load_designs`. With a manifest, the manifest's design must be among them."""
    manifest = load_manifest(manifest_path)
    if manifest is not None and (designs is None or manifest.get("design_sha256") not in designs):
        raise ValueError("the manifest's frozen design file was not supplied (--design); its windows cannot be validated")
    dirs, rejected = select_runs(raw_root, manifest)
    if not dirs:
        return {"manifest": manifest is not None, "runs": [], "rejected_runs": rejected, "note": f"no eligible runs under {raw_root}"}
    return analyse(dirs, manifest, designs, n_draws, sensitivities, rejected)


def analyse(dirs: list[Path], manifest: dict | None, designs: dict | None, n_draws: int = stats.N_RANDOMISATION,
            sensitivities: bool = True, rejected: list | None = None) -> dict:
    """Everything after run selection: validation, grouping, inference, gates and published claims. The simulation
    study (oc.py) calls this same function on simulated runs, so it scores the published procedure itself."""
    rejected = rejected or []
    run = load_runs(dirs)
    windows = outcomes.window_table(run, designs)
    pairs = outcomes.pair_table(run, designs=designs, windows=windows)
    all_pairs = pairs
    if sensitivities:
        offsets = _achieved_offsets(run)
        if len(pairs) and len(offsets):
            pairs = pairs.merge(offsets, on=["run_id", "target_identity", "seq"], how="left")
    core = {c["identity"]: (c["client_id"], c["ingress"]) for c in manifest.get("core_targets", [])} if manifest else {}
    controls = set(manifest.get("positive_controls", [])) if manifest else set()
    result: dict = {
        "manifest": manifest is not None,
        "runs": [{"run_id": s.get("run_id"), "mode": s.get("mode"), "stage": s.get("stage"), "started_at": s.get("started_at"),
                  "budget": s.get("budget")} for s in run.starts],
        "rejected_runs": rejected,
        "funnel": outcomes.funnel(run, designs, windows, all_pairs).to_dict(orient="records") if sensitivities else None,
        "validators": {},
    }
    pvals = {}
    if not len(pairs):
        return _clean(result)
    main = pairs[pairs["pair_kind"].isin(["c1", "c2", "c3", "c2_uncontended"])]
    for (target, client, ingress), g in main.groupby(["target_identity", "client_id", "ingress"], dropna=False):
        key = f"{target}|{client}|{ingress}"
        confirmatory = manifest is not None and core.get(target) == (client, ingress)
        eff = stats.validator_effects(g, n_draws=n_draws)
        by_regime = {reg: stats.validator_effects(gg, n_draws=min(n_draws, 2_000)) for reg, gg in g.groupby("regime")}
        sens = {"regime": {reg: {"label": _labels(e), "order": {c: _effect(x) for c, x in e["order"].items()},
                                 "verdict": e["diagnosis"]["verdict"]} for reg, e in by_regime.items()}}
        if sensitivities:
            relaxed = g.copy()
            wsub = windows[windows["target_identity"] == target].set_index(["run_id", "seq"])
            ambiguous_ok = {(r, s) for (r, s), row in wsub.iterrows() if row["exclusion"] in ("", "mode:transition_ambiguous")}
            relaxed["evaluable"] = [(r, s) in ambiguous_ok for r, s in zip(relaxed["run_id"], relaxed["seq"])]
            sens |= {
                "censored": _labels(stats.validator_effects(g, n_draws=min(n_draws, 2_000), estimand="censored")),
                "session_bootstrap_L": _session_bootstrap(g),
                "including_transition_ambiguous": _labels(stats.validator_effects(relaxed, n_draws=min(n_draws, 2_000))),
            }
            if "achieved_offset_ms" in g:
                bins = pd.cut(g["achieved_offset_ms"], [-1e9, -100, 0, 100, 1e9], labels=["<-100ms", "-100..0ms", "0..100ms", ">100ms"])
                sens["achieved_offset"] = {str(b): _labels(stats.validator_effects(gg, n_draws=min(n_draws, 2_000)))
                                           for b, gg in g.groupby(bins, observed=True)}
                sens["achieved_offset_unavailable_windows"] = int(g[g["achieved_offset_ms"].isna()][["run_id", "seq"]].drop_duplicates().shape[0])
        uncontended = g[(g["pair_kind"] == "c2_uncontended") & g["evaluable"]].dropna(subset=["x_first_cc"])
        result["validators"][key] = {
            "target_identity": target,
            "client_id": client,
            "ingress": ingress,
            "confirmatory": confirmatory,
            "positive_control": target in controls and confirmatory,
            "label": _labels(eff),
            "order": {c: _effect(e) for c, e in eff["order"].items()},
            "randomisation_p": eff["pvalues"],
            "inclusion": eff["inclusion"],
            "rules": eff["rules"],
            "diagnosis": eff["diagnosis"],
            "strictness": eff["strictness"],
            "mixture": eff["mixture"],
            "selection": eff["selection"],
            # worst-case bounds over every pair of the evaluable windows (single- and neither-landed), PREREGISTRATION §1
            "selection_bounds": eff["selection_bounds"],
            "exploratory_uncontended_c2": {"k": int(uncontended["x_first_cc"].sum()), "n": len(uncontended)},
            "sensitivity": sens,
            "gates": _regime_gates(ingress, by_regime, eff["diagnosis"]["verdict"]),
        }
        if confirmatory:
            for c, p in eff["pvalues"].items():
                pvals[f"{key}/{c}/label"] = p["label"]
                pvals[f"{key}/{c}/order"] = p["order"]
    result["holm"] = stats.holm(pvals, family_size=FAMILY if manifest else None)
    # §9 gates. A positive control passes only with the final (post-selection-check, strict) reward/cost verdict, in
    # its frozen (client, ingress) group.
    controls_failed = False
    if manifest:
        ok = {t: any(v["target_identity"] == t and v["positive_control"] and v["diagnosis"]["verdict"] == "reward_cost"
                     for v in result["validators"].values()) for t in controls}
        result["positive_controls"] = ok
        controls_failed = not all(ok.values()) if ok else True
        result["closed_source_conclusions_withdrawn"] = controls_failed
    for v in result["validators"].values():
        v["published_claim"] = published_claim(v, controls_failed, v["positive_control"])
    result["buffer_assumption_broken"] = sorted(k for k, v in result["validators"].items() if v["gates"]["buffer_assumption_broken"])
    result["label_effects_streaming_only"] = sorted(k for k, v in result["validators"].items() if v["gates"]["label_effects_streaming_only"])
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
    """The headline table. It prints each group's *published* claim (after every gate), with the raw verdict beside
    it, its strictness lower bound and whether it survives the worst-case selection bounds."""
    lines = ["| Validator | Client | Ingress | L_C1 | L_C2 | L_C3 | Published claim | Raw verdict | Strictness ≥ | Selection-robust |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    if result.get("closed_source_conclusions_withdrawn"):
        lines.insert(0, "**A positive control failed: conclusions for every other validator are withdrawn (PREREGISTRATION §9).**\n")
    for r in result.get("validators", {}).values():
        def f(e):
            return "–" if e["n"] == 0 else f"{e['estimate']:.2f} [{e['ci_bonferroni'][0]:.2f}, {e['ci_bonferroni'][1]:.2f}] (n={e['n']})"
        d = r["diagnosis"]
        lb = d.get("strictness_lower95")
        robust = d.get("selection_robust")
        lines.append(f"| `{r['target_identity'][:8]}…` | {r['client_id']} | {r['ingress']} | {f(r['label']['c1'])} | {f(r['label']['c2'])} | "
                     f"{f(r['label']['c3'])} | **{r.get('published_claim', d['verdict'])}** | {d['verdict']} | "
                     f"{'–' if lb is None else f'{lb:.2f}'} | {'–' if robust is None else ('yes' if robust else 'no')} |")
    return "\n".join(lines)
