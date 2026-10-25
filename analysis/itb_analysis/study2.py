"""Study 2 confirmatory analysis (docs/PREREGISTRATION-2.md §2–§8).

The hypotheses are not written here: they are read from the frozen Study 2 manifest (`design/campaign-study2.json`,
hashed in the second Memo), so this module only states how any such hypothesis is decided.

- **Race estimand** O_g(Δt) = P(`hi` lands before `lo` | `lo` was sent Δt ms earlier), over race pairs in evaluable
  windows of the hypothesis' frozen (target, client, ingress) groups whose two members both landed.
- **Equal-key estimand** P(first-sent member lands first) over equal-key pairs at Δt, pooled over the groups.
- **Test:** one-sided exact binomial against 0.5 in the hypothesis' direction; Holm over every hypothesis of the
  manifest at family α; *supported* when the Holm-adjusted p-value is below α. A hypothesis with no informative pair
  is *not evaluable* (p = 1).
- **Selection bound:** every pair of the same evaluable windows with fewer than two landed members is counted against
  the hypothesis; the claim is *selection-robust* if that worst case still passes at the Bonferroni level α/m.
- **Gates:** a race hypothesis is withdrawn when `hi`, sent first, lost to `lo` more than once in its groups (the
  pair did not compete on priority as designed); it is flagged when the median achieved send gap of its cell misses
  the nominal Δt by more than 1 ms.

The replication (hypothesis R) is the Study 1 procedure itself: `report.compute` with the Study 2 manifest.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binom

from . import outcomes, report, stats
from .load import load_runs

ALPHA = 0.05
#: gates (§8): more than this many hi-first losses withdraw a group's race hypotheses
CONTROL_LOSSES_ALLOWED = 1
#: |median achieved gap − nominal Δt| above this flags a race hypothesis
GAP_TOLERANCE_MS = 1.0
#: sensitivity (§6): races whose achieved gap is within this of the nominal Δt
GAP_WINDOW_MS = 0.5

#: docs/PREREGISTRATION-2.md §3: (id, statement, pair kind, Δt ms, side, target identities). `scripts/freeze.py --study 2`
#: writes them into the manifest with each target's frozen (client, ingress) group; the analysis reads them from there.
SPEC = (
    ("H1-agave", "Agave does not reorder against a 2 ms head start", "race", 2.0, "less",
     ("7QQGNm3ptwinipDCyaCF7jY5katgmFUu1ieP2f7nwLpE",)),
    ("H1-jito", "Jito-Solana does not reorder against a 2 ms head start", "race", 2.0, "less",
     ("HEL1USMZKAL2odpNBj2oCjffnFGaYwmbGmyewGv1e2TU",)),
    ("H2-firedancer", "Firedancer reorders against a 2 ms head start", "race", 2.0, "greater",
     ("EvnRmnMrd69kFdbLMxWkTn1icZ7DCceRhvmb2SJXqDo4",)),
    ("H2-firedancer-harmonic", "Firedancer + Harmonic reorders against a 2 ms head start", "race", 2.0, "greater",
     ("JUPiTERrZqgf1jUyR7dSkhMx4Kn2qJyekWsg3LT1h4b",)),
    ("H2-agave-harmonic", "Agave + Harmonic reorders against a 2 ms head start", "race", 2.0, "greater",
     ("Fd7btgySsrjuo25CJCj7oE7VPMyezDhnx7pZkj2v69Nk",)),
    ("H3-firedancer-ties", "Firedancer breaks equal-priority ties later-arrival-first", "equal_key", 10.0, "less",
     ("EvnRmnMrd69kFdbLMxWkTn1icZ7DCceRhvmb2SJXqDo4", "9eGrDohdNTAo61DRHyfMuqKWXqYnA3i254Wiszxe8FoY")),
)


def hypotheses(targets: list[dict]) -> list[dict]:
    """SPEC with each target's frozen group taken from the target list."""
    group = {t["identity"]: {"identity": t["identity"], "client_id": t["client_id"], "ingress": t["ingress"]} for t in targets}
    return [{"id": i, "statement": s, "pair_kind": k, "dt_ms": dt, "side": side, "groups": [group[t] for t in ts]}
            for i, s, k, dt, side, ts in SPEC]


def _rank(r) -> tuple[int, int]:
    return (int(r["slot"]), int(r["index_in_block"]))


def pair_table(probes: pd.DataFrame, windows: pd.DataFrame, sends: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per race or equal-key pair: its window's group, eligibility and exclusion, Δt and the achieved gap
    between the two streams' finish times, which label went first, which members landed, and the outcome:
    `success` when both landed (race: `hi` first; equal key: the first-sent member first) and `success_censored`
    when at least one did (a member that did not land is placed after one that did)."""
    cols = ["run_id", "pair_id", "target_identity", "client_id", "ingress", "kind", "dt_ms", "achieved_gap_ms",
            "first_label", "evaluable", "exclusion", "first_landed", "second_landed", "n_landed", "success",
            "success_censored"]
    if probes.empty or windows.empty:
        return pd.DataFrame(columns=cols)
    w = windows.set_index(["run_id", "target_identity", "seq"])
    finished = {}
    if sends is not None and len(sends) and "finished_unix_ns" in sends:
        finished = {(r, p): f for r, p, f in zip(sends["run_id"], sends["probe_id"], sends["finished_unix_ns"]) if pd.notna(f)}
    rows = []
    p = probes[probes["pair_kind"].isin(["race", "equal_key"])]
    for (run_id, pair_id), g in p.groupby(["run_id", "pair_id"]):
        if len(g) != 2:
            continue
        first = g[g["send_position_in_pair"] == 0].iloc[0]
        second = g[g["send_position_in_pair"] == 1].iloc[0]
        key = (run_id, first["target_identity"], first["seq"])
        win = w.loc[key] if key in w.index else None
        f1, f2 = finished.get((run_id, first["probe_id"])), finished.get((run_id, second["probe_id"]))
        # The member whose landing first is the hypothesis' event: `hi` in a race, the first-sent one for equal keys.
        if first["pair_kind"] == "race":
            a, b = (first, second) if first["label"] == "hi" else (second, first)
        else:
            a, b = first, second
        landed_a, landed_b = bool(a["landed"]), bool(b["landed"])
        success = float(_rank(a) < _rank(b)) if landed_a and landed_b else np.nan
        censored = np.nan if not (landed_a or landed_b) else float(landed_a and (not landed_b or _rank(a) < _rank(b)))
        rows.append({
            "run_id": run_id, "pair_id": pair_id, "target_identity": first["target_identity"],
            "client_id": None if win is None else win.get("client_id"), "ingress": None if win is None else win.get("ingress"),
            "kind": first["pair_kind"], "dt_ms": float(first["race_dt_ms"]),
            "achieved_gap_ms": (f2 - f1) / 1e6 if f1 is not None and f2 is not None else np.nan,
            "first_label": first["label"], "evaluable": bool(win is not None and win.get("evaluable")),
            "exclusion": "design_unavailable" if win is None else win.get("exclusion", ""),
            "first_landed": bool(first["landed"]), "second_landed": bool(second["landed"]),
            "n_landed": int(landed_a) + int(landed_b), "success": success, "success_censored": censored,
        })
    return pd.DataFrame(rows, columns=cols)


def _in_groups(pairs: pd.DataFrame, groups: list[dict]) -> np.ndarray:
    keys = {(g["identity"], g["client_id"], g["ingress"]) for g in groups}
    return np.array([(t, c, i) in keys for t, c, i in zip(pairs["target_identity"], pairs["client_id"], pairs["ingress"])],
                    dtype=bool)


def _selected(pairs: pd.DataFrame, h: dict) -> pd.DataFrame:
    sel = pairs[_in_groups(pairs, h["groups"]) & pairs["evaluable"].to_numpy(dtype=bool)
                & (pairs["kind"] == h["pair_kind"]).to_numpy() & np.isclose(pairs["dt_ms"].astype(float), float(h["dt_ms"]))]
    if h["pair_kind"] == "race":
        sel = sel[sel["first_label"] == "lo"]  # the head-start races: lo sent Δt ms before hi
    return sel


def _p_one_sided(k: int, n: int, side: str) -> float:
    if n == 0:
        return 1.0
    return float(binom.cdf(k, n, 0.5) if side == "less" else binom.sf(k - 1, n, 0.5))


def evaluate(pairs: pd.DataFrame, hypotheses: list[dict], alpha: float = ALPHA, coding: str = "cc") -> list[dict]:
    """Every hypothesis of the manifest, decided as stated in the module docstring. `coding="censored"` is the §6
    sensitivity: pairs with at least one landed member, scored by `success_censored`."""
    out = []
    for h in hypotheses:
        sel = _selected(pairs, h)
        if coding == "censored":
            scored, col = sel[sel["n_landed"] >= 1], "success_censored"
        else:
            scored, col = sel[sel["n_landed"] == 2], "success"
        k, n, incomplete = int(scored[col].sum()), int(len(scored)), int(len(sel) - len(scored))
        k_worst = k + incomplete if h["side"] == "less" else k
        lo, hi = stats.clopper_pearson(k, n, 0.05) if n else (float("nan"), float("nan"))
        out.append({
            "id": h["id"], "statement": h["statement"], "pair_kind": h["pair_kind"], "dt_ms": h["dt_ms"], "side": h["side"],
            "groups": h["groups"], "k": k, "n": n, "estimate": k / n if n else float("nan"), "ci95": [lo, hi],
            "p": _p_one_sided(k, n, h["side"]), "incomplete_pairs": incomplete,
            "p_worst": _p_one_sided(k_worst, n + incomplete, h["side"]),
        })
    holm = stats.holm({r["id"]: r["p"] for r in out})
    m = len(out)
    for r in out:
        r["p_holm"] = holm[r["id"]]
        r["verdict"] = "not evaluable" if r["n"] == 0 else ("supported" if r["p_holm"] < alpha else "not supported")
        r["selection_robust"] = r["verdict"] == "supported" and r["p_worst"] < alpha / m
    return out


def gates(pairs: pd.DataFrame, h: dict) -> dict:
    """§8 for one hypothesis: the hi-first control races of its groups, and the achieved gap of its cell."""
    if h["pair_kind"] != "race":
        return {"control_losses": None, "controls": None, "median_achieved_gap_ms": None, "withdrawn": False, "gap_flag": False}
    mine = pairs[_in_groups(pairs, h["groups"]) & pairs["evaluable"].to_numpy(dtype=bool) & (pairs["kind"] == "race").to_numpy()
                 & (pairs["n_landed"] == 2).to_numpy()]
    controls = mine[mine["first_label"] == "hi"]
    losses = int((controls["success"] == 0).sum())
    cell = _selected(pairs, h)["achieved_gap_ms"].dropna()
    gap = float(cell.median()) if len(cell) else None
    return {"control_losses": losses, "controls": int(len(controls)), "median_achieved_gap_ms": gap,
            "withdrawn": losses > CONTROL_LOSSES_ALLOWED,
            "gap_flag": gap is not None and abs(gap - float(h["dt_ms"])) > GAP_TOLERANCE_MS}


def published(h: dict, g: dict) -> str:
    """The claim REPORT prints for a hypothesis, after its gates and the selection qualifier."""
    if g["withdrawn"]:
        return "withdrawn: hi sent first lost to lo more than once (the pair did not compete on priority)"
    claim = h["verdict"] + (" (assumes selection)" if h["verdict"] == "supported" and not h["selection_robust"] else "")
    return claim + (f"; achieved gap {g['median_achieved_gap_ms']:.2f} ms" if g["gap_flag"] else "")


def horizon(points: list[tuple[float, int, int]]) -> tuple[float | None, float | None]:
    """Where the share of overtakes falls below one half: (last Δt at or above it, next Δt with data). The first is
    None when no cell reaches one half (the horizon is below the smallest Δt), the second when none follows."""
    above = [dt for dt, k, n in points if n and k / n >= 0.5]
    if not above:
        return None, points[0][0] if points else None
    later = [dt for dt, k, n in points if dt > max(above) and n]
    return max(above), (later[0] if later else None)


def curves(pairs: pd.DataFrame) -> dict:
    """Exploratory (§7), per observed group: overtakes against a head start, hi-first controls, equal-key order, and
    the achieved gaps per cell."""
    out: dict = {}
    ev = pairs[pairs["evaluable"] & (pairs["n_landed"] == 2)]
    for (t, c, i), g in ev.groupby(["target_identity", "client_id", "ingress"], dropna=False):
        races, eq = g[g["kind"] == "race"], g[g["kind"] == "equal_key"]

        def cells(df: pd.DataFrame) -> dict[str, list[int]]:
            return {f"{dt:g}": [int(x["success"].sum()), int(len(x))] for dt, x in df.groupby("dt_ms")}

        lo_first = races[races["first_label"] == "lo"]
        overtake = cells(lo_first)
        pts = [(float(dt), k, n) for dt, (k, n) in sorted(overtake.items(), key=lambda kv: float(kv[0]))]
        out[f"{t}|{c}|{i}"] = {
            "target_identity": t, "client_id": c, "ingress": i,
            "overtake_lo_first": overtake, "hi_first_wins": cells(races[races["first_label"] == "hi"]),
            "horizon_ms": list(horizon(pts)) if pts else None, "equal_key_first_sent_first": cells(eq),
            "median_achieved_gap_ms": {f"{dt:g}": float(x["achieved_gap_ms"].median()) for dt, x in lo_first.groupby("dt_ms")
                                       if x["achieved_gap_ms"].notna().any()},
        }
    return out


def analyse(dirs: list[Path], manifest: dict, designs: dict | None) -> dict:
    run = load_runs(dirs)
    windows = outcomes.window_table(run, designs)
    pairs = pair_table(outcomes.probe_table(run), windows, run.sends)
    hyps = manifest["hypotheses"]
    decided = evaluate(pairs, hyps)
    for h, spec in zip(decided, hyps):
        h["gates"] = gates(pairs, spec)
        h["published_claim"] = published(h, h["gates"])
    relaxed = pairs.assign(evaluable=pairs["exclusion"].isin(["", "mode:transition_ambiguous"]))
    near = pairs[(pairs["kind"] != "race") | (pairs["dt_ms"] == 0)
                 | ((pairs["achieved_gap_ms"] - pairs["dt_ms"]).abs() <= GAP_WINDOW_MS)]
    stage2 = windows[windows["kit"].isin(["r", "e"])] if "kit" in windows else windows.iloc[0:0]

    def brief(rs: list[dict]) -> dict:
        return {r["id"]: {k: r[k] for k in ("k", "n", "estimate", "p_holm", "verdict")} for r in rs}

    return {
        "runs": [{"run_id": s.get("run_id"), "stage": s.get("stage"), "started_at": s.get("started_at"), "budget": s.get("budget")}
                 for s in run.starts],
        "hypotheses": decided,
        "sensitivity": {"censored": brief(evaluate(pairs, hyps, coding="censored")),
                        "including_transition_ambiguous": brief(evaluate(relaxed, hyps)),
                        "achieved_gap_within_0.5ms": brief(evaluate(near, hyps))},
        "curves": curves(pairs),
        "funnel": {"windows": int(len(stage2)), "evaluable": int(stage2["evaluable"].sum()) if len(stage2) else 0,
                   "exclusions": stage2[~stage2["evaluable"]]["exclusion"].value_counts().to_dict() if len(stage2) else {}},
    }


def compute(raw: Path, manifest_path: Path, designs: dict) -> dict:
    """Study 2 in full: the replication (Study 1 procedure, Study 2 manifest) and the hypotheses with the curves."""
    manifest = report.load_manifest(manifest_path)
    dirs, rejected = report.select_runs(raw, manifest)
    result = {"manifest": str(manifest_path), "rejected_runs": rejected,
              "replication": report.compute(raw, manifest_path, designs=designs)}
    if dirs:
        result |= analyse(dirs, manifest, designs)
    return json.loads(json.dumps(result, default=float))
