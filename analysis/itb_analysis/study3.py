"""Study 3 confirmatory analysis (docs/PREREGISTRATION-3.md): does the reward enter the ordering key?

Studies 1 and 2 rejected CU price, lamport fee, FIFO and "no rule", but every contrast they ran ranks the probes by
requested cost the same way reward ÷ (cost + 1) does. Study 3 adds two contrasts where the two disagree:
- **C4**, Y vs A: Y costs more (2,835 vs 2,335) but pays more per cost unit, whatever share of the signature fee
  counts as reward. Reward ÷ cost puts Y first; ascending requested cost puts A first.
- **C5**, hi vs A: equal cost, different reward. Reward ÷ cost puts hi first; cost alone ties.

Per core target and contrast, L = P(x lands before y) over evaluable windows where both members landed. One-sided
exact binomial test of L > 0.5, Holm over every hypothesis of the frozen manifest; supported when the Holm-adjusted
p-value is below α. Selection bound as in Study 2: incomplete pairs of evaluable windows counted against; a supported
hypothesis that fails the bound at α/m is published "(assumes selection)".

Positive controls (the frozen direct Agave and Firedancer targets, whose public code uses reward ÷ cost): if either
does not end with both hypotheses supported, every other target's claims are withdrawn. If they pass only with the
selection qualifier, every other target's verdict carries it too.

Identification (§5): among the candidates the three studies registered (CU price, lamport fee, ascending requested
cost, FIFO, random), a target's key is reward ÷ (cost + 1) when both its Study 3 hypotheses are supported and the
Study 1 and Study 2 published claims frozen in the manifest are `reward_cost`.
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
KINDS = ("c4", "c5")
QUALIFIER = " (assumes selection)"
STATEMENT = {
    "c4": "P(Y lands before A) > 0.5: the reward counts against a higher requested cost (cost alone predicts A first)",
    "c5": "P(hi lands before A) > 0.5: at equal cost the higher reward goes first (cost alone predicts a tie)",
}
#: what the analysis needs from `outcomes.pair_table`, so an empty run still yields every hypothesis (n = 0)
PAIR_COLUMNS = ["run_id", "seq", "target_identity", "client_id", "ingress", "evaluable", "pair_kind", "x_label",
                "landed_x", "landed_y", "both_landed", "same_slot", "x_first_cc", "x_first", "first_sent_first_cc"]


def hypotheses(targets: list[dict]) -> list[dict]:
    """Two hypotheses per core target, in the target list's order; `scripts/freeze.py --study 3` writes them."""
    out = []
    for t in (t for t in targets if t.get("tier", "core") == "core"):
        group = {"identity": t["identity"], "client_id": t["client_id"], "ingress": t["ingress"]}
        for kind, h in (("c4", "H4"), ("c5", "H5")):
            out.append({"id": f"{h}-{t['identity'][:8]}", "statement": STATEMENT[kind], "pair_kind": kind,
                        "side": "greater", "groups": [group]})
    return out


def _frame(pairs: pd.DataFrame | None) -> pd.DataFrame:
    if pairs is None or pairs.empty or not set(PAIR_COLUMNS) <= set(pairs.columns):
        return pd.DataFrame({c: pd.Series(dtype=object) for c in PAIR_COLUMNS})
    return pairs


def _p_greater(k: int, n: int) -> float:
    return 1.0 if n == 0 else float(binom.sf(k - 1, n, 0.5))


def _in_groups(pairs: pd.DataFrame, groups: list[dict]) -> np.ndarray:
    keys = {(g["identity"], g["client_id"], g["ingress"]) for g in groups}
    return np.array([(t, c, i) in keys for t, c, i in zip(pairs["target_identity"], pairs["client_id"], pairs["ingress"])],
                    dtype=bool)


def _selected(pairs: pd.DataFrame, h: dict) -> pd.DataFrame:
    return pairs[_in_groups(pairs, h["groups"]) & pairs["evaluable"].to_numpy(dtype=bool)
                 & (pairs["pair_kind"] == h["pair_kind"]).to_numpy(dtype=bool)]


def evaluate(pairs: pd.DataFrame | None, hyps: list[dict], alpha: float = ALPHA, coding: str = "cc") -> list[dict]:
    """Every hypothesis, decided as the module docstring states. `coding="censored"` (§8) scores pairs with at least
    one member landed, a non-landed member counting after a landed one."""
    pairs = _frame(pairs)
    out = []
    for h in hyps:
        sel = _selected(pairs, h)
        col = "x_first_cc" if coding == "cc" else "x_first"
        scored = sel[pd.to_numeric(sel[col], errors="coerce").notna()]
        k, n = int(pd.to_numeric(scored[col]).sum()), int(len(scored))
        incomplete = int(len(sel) - n)
        lo, hi = stats.clopper_pearson(k, n, 0.05) if n else (float("nan"), float("nan"))
        out.append({"id": h["id"], "statement": h["statement"], "pair_kind": h["pair_kind"], "groups": h["groups"],
                    "k": k, "n": n, "estimate": k / n if n else float("nan"), "ci95": [lo, hi], "p": _p_greater(k, n),
                    "incomplete_pairs": incomplete, "p_worst": _p_greater(k, n + incomplete)})
    holm = stats.holm({r["id"]: r["p"] for r in out})
    for r in out:
        r["p_holm"] = holm[r["id"]]
        r["verdict"] = "not evaluable" if r["n"] == 0 else ("supported" if r["p_holm"] < alpha else "not supported")
        r["selection_robust"] = r["verdict"] == "supported" and r["p_worst"] < alpha / len(out)
    return out


def control_state(decided: list[dict], positive_controls: list[str]) -> dict:
    """§6: failed if a control has a hypothesis not supported (or none at all); conditional if a control's support
    holds only with the selection qualifier."""
    mine = {t: [h for h in decided if h["groups"][0]["identity"] == t] for t in positive_controls}
    failed = [t for t, hs in mine.items() if not hs or any(h["verdict"] != "supported" for h in hs)]
    conditional = [t for t, hs in mine.items() if t not in failed and any(not h["selection_robust"] for h in hs)]
    return {"failed": failed, "conditional": conditional}


def published(decided: list[dict], positive_controls: list[str]) -> dict[str, str]:
    """Claims after the positive-control gate and the selection qualifier (PREREGISTRATION-3 §4, §6)."""
    state = control_state(decided, positive_controls)
    out = {}
    for h in decided:
        target = h["groups"][0]["identity"]
        if state["failed"] and target not in positive_controls:
            out[h["id"]] = "withdrawn: a positive control did not end with both hypotheses supported (method check)"
        else:
            out[h["id"]] = h["verdict"] + (QUALIFIER if h["verdict"] == "supported" and not h["selection_robust"] else "")
    return out


def identification(decided: list[dict], claims: dict[str, str], manifest: dict, state: dict | None = None) -> list[dict]:
    """Per core target, PREREGISTRATION-3 §5: Study 3's two published claims next to the Study 1 and Study 2 claims
    frozen in the manifest (`prior_claims`), and the verdict."""
    state = state or {"failed": [], "conditional": []}
    prior = manifest.get("prior_claims", {})
    rows = []
    for c in manifest["core_targets"]:
        mine = [h for h in decided if h["groups"][0]["identity"] == c["identity"]]
        s3 = {h["pair_kind"]: claims[h["id"]] for h in mine}
        s1, s2 = prior.get(c["identity"], {}).get("study1"), prior.get(c["identity"], {}).get("study2")
        ok = {k: s3.get(k, "").startswith("supported") for k in KINDS}
        qualified = any(v.endswith(QUALIFIER) for v in s3.values()) or bool(state["conditional"])
        q = QUALIFIER if qualified else ""
        prior_ok = s1 == s2 == "reward_cost"
        c4 = next((h for h in mine if h["pair_kind"] == "c4"), None)
        c4_below = c4 is not None and c4["n"] > 0 and c4["ci95"][1] < 0.5
        if any(v.startswith("withdrawn") for v in s3.values()):
            verdict = "withdrawn: method check failed"
        elif ok["c4"] and ok["c5"] and prior_ok:
            verdict = "reward ÷ (cost + 1) identified among the registered candidates" + q
        elif ok["c4"] and ok["c5"]:
            verdict = f"cost alone rejected and the reward effect shown; the Study 1 / Study 2 claims are {s1} / {s2}" + q
        elif ok["c4"]:
            verdict = "cost alone rejected; the equal-cost reward effect is not shown" + q
        elif ok["c5"]:
            verdict = "the equal-cost reward effect is supported; C4 is inconclusive" + q
            if c4_below:
                verdict += ". C4's interval lies below 0.5 (descriptive): compatible with cost first and the reward only between equal costs"
        else:
            verdict = "the reward term is not shown; cost alone is not rejected" + q
            if c4_below:
                verdict += ". C4's interval lies below 0.5 (descriptive): the order follows cost against reward"
        both = ok["c4"] and ok["c5"] and prior_ok and not any(v.startswith("withdrawn") for v in s3.values())
        rows.append({"identity": c["identity"], "client_id": c["client_id"], "ingress": c["ingress"],
                     "study1_claim": s1, "study2_claim": s2, "c4": s3.get("c4"), "c5": s3.get("c5"),
                     "reward_cost_identified": both and not qualified,
                     "reward_cost_identified_assuming_selection": both, "verdict": verdict})
    return rows


def diagnostics(pairs: pd.DataFrame | None, manifest: dict) -> list[dict]:
    """§9, descriptive: per target, observed group and contrast, the funnel, landing per label and send order."""
    pairs = _frame(pairs)
    frozen = {(c["identity"], c["client_id"], c["ingress"]) for c in manifest.get("core_targets", [])}
    out = []
    for (t, c, i, kind), g in pairs.groupby(["target_identity", "client_id", "ingress", "pair_kind"], dropna=False):
        ev = g[g["evaluable"].astype(bool)]
        fsf = pd.to_numeric(ev["first_sent_first_cc"], errors="coerce").dropna()
        x_label = g["x_label"].iloc[0]
        out.append({"target_identity": t, "client_id": c, "ingress": i, "pair_kind": kind,
                    "confirmatory_group": (t, c, i) in frozen, "pairs": int(len(g)), "evaluable_pairs": int(len(ev)),
                    "landed": {x_label: [int(ev["landed_x"].astype(bool).sum()), int(len(ev))],
                               "A": [int(ev["landed_y"].astype(bool).sum()), int(len(ev))]},
                    "both_landed": int(ev["both_landed"].astype(bool).sum()),
                    "first_sent_first": [int(fsf.sum()), int(len(fsf))]})
    return out


def _funnel(w: pd.DataFrame) -> dict:
    """Attempted windows of the Study 3 kit, how many were evaluable, and why the others were excluded."""
    return {"windows": int(len(w)), "evaluable": int(w["evaluable"].sum()) if len(w) else 0,
            "exclusions": w[~w["evaluable"].astype(bool)]["exclusion"].value_counts().to_dict() if len(w) else {}}


def analyse(dirs: list[Path], manifest: dict, designs: dict | None) -> dict:
    run = load_runs(dirs) if dirs else None
    windows = outcomes.window_table(run, designs) if run is not None else pd.DataFrame()
    pairs = _frame(outcomes.pair_table(run, kinds=KINDS, designs=designs, windows=windows) if run is not None else None)
    hyps = manifest["hypotheses"]
    decided = evaluate(pairs, hyps)
    claims = published(decided, manifest.get("positive_controls", []))
    state = control_state(decided, manifest.get("positive_controls", []))
    for h in decided:
        h["published_claim"] = claims[h["id"]]
    relaxed = pairs.copy()
    if len(relaxed) and len(windows):
        ok = {(r, s) for r, s, e in zip(windows["run_id"], windows["seq"], windows["exclusion"]) if e in ("", "mode:transition_ambiguous")}
        relaxed["evaluable"] = [(r, s) in ok for r, s in zip(relaxed["run_id"], relaxed["seq"])]
    same_slot = pairs.assign(x_first_cc=pairs["x_first_cc"].where(pairs["same_slot"].astype(bool) | ~pairs["both_landed"].astype(bool)))

    def brief(rs: list[dict]) -> dict:
        return {r["id"]: {k: r[k] for k in ("k", "n", "estimate", "p_holm", "verdict")} for r in rs}

    nw = windows[windows["kit"] == "n"] if "kit" in windows else windows.iloc[0:0]
    return {
        "runs": [{"run_id": s.get("run_id"), "started_at": s.get("started_at"), "budget": s.get("budget")}
                 for s in (run.starts if run is not None else [])],
        "hypotheses": decided,
        "positive_controls": state,
        "identification": identification(decided, claims, manifest, state),
        "sensitivity": {"censored": brief(evaluate(pairs, hyps, coding="censored")),
                        "including_transition_ambiguous": brief(evaluate(relaxed, hyps)),
                        "same_slot": brief(evaluate(same_slot, hyps))},
        "diagnostics": diagnostics(pairs, manifest),
        "funnel": _funnel(nw),
        "funnel_by_target": {t: _funnel(g) for t, g in nw.groupby("target_identity")} if len(nw) else {},
    }


def compute(raw: Path, manifest_path: str, designs: dict) -> dict:
    """Study 3 in full. Every registered hypothesis and every core target's verdict is emitted, also when no run is
    selected (n = 0, not evaluable). `manifest_path` goes in as a POSIX string: the results record it."""
    manifest = report.load_manifest(manifest_path)
    dirs, rejected = report.select_runs(raw, manifest)
    result = {"manifest": str(manifest_path), "rejected_runs": rejected} | analyse(dirs, manifest, designs)
    return json.loads(json.dumps(result, default=float))
