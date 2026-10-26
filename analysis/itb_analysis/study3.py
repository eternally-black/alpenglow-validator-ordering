"""Study 3 confirmatory analysis (docs/PREREGISTRATION-3.md): does the reward enter the ordering key?

Studies 1 and 2 rejected CU price, lamport fee, FIFO and "no rule", but every contrast they ran ranks the probes by
requested cost the same way reward ÷ (cost + 1) does. Study 3 adds two contrasts where the two disagree:
- **C4**, Y vs A: Y costs more (4,335 vs 2,335) but pays more per cost unit. Reward ÷ cost puts Y first; cost alone
  puts A first.
- **C5**, hi vs A: equal cost, different reward. Reward ÷ cost puts hi first; cost alone ties.

Per core target and contrast, L = P(x lands before y) over evaluable windows where both members landed. One-sided
exact binomial test of L > 0.5, Holm over every hypothesis of the frozen manifest; supported when the Holm-adjusted
p-value is below α. Selection bound as in Study 2: incomplete pairs of evaluable windows counted against, selection-
robust at α/m. A positive control (the frozen direct Agave and Firedancer targets, whose public code uses reward ÷
cost) that does not end with both hypotheses supported withdraws every other target's claims.

Identification: a target's ordering key is reward ÷ (cost + 1), among every candidate the three studies registered
(CU price, lamport fee, cost alone, FIFO, random), when both its Study 3 hypotheses are supported and its Study 1 and
Study 2 published claims are `reward_cost`.
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
STATEMENT = {
    "c4": "P(Y lands before A) > 0.5: the reward counts against a higher cost (cost alone predicts A first)",
    "c5": "P(hi lands before A) > 0.5: at equal cost the higher reward goes first (cost alone predicts a tie)",
}


def hypotheses(targets: list[dict]) -> list[dict]:
    """Two hypotheses per core target, in the target list's order; `scripts/freeze.py --study 3` writes them."""
    out = []
    for t in (t for t in targets if t.get("tier", "core") == "core"):
        group = {"identity": t["identity"], "client_id": t["client_id"], "ingress": t["ingress"]}
        for kind, h in (("c4", "H4"), ("c5", "H5")):
            out.append({"id": f"{h}-{t['identity'][:8]}", "statement": STATEMENT[kind], "pair_kind": kind,
                        "side": "greater", "groups": [group]})
    return out


def _p_greater(k: int, n: int) -> float:
    return 1.0 if n == 0 else float(binom.sf(k - 1, n, 0.5))


def _selected(pairs: pd.DataFrame, h: dict) -> pd.DataFrame:
    keys = {(g["identity"], g["client_id"], g["ingress"]) for g in h["groups"]}
    in_group = np.array([(t, c, i) in keys for t, c, i in zip(pairs["target_identity"], pairs["client_id"], pairs["ingress"])],
                        dtype=bool)
    return pairs[in_group & pairs["evaluable"].to_numpy(dtype=bool) & (pairs["pair_kind"] == h["pair_kind"]).to_numpy()]


def evaluate(pairs: pd.DataFrame, hyps: list[dict], alpha: float = ALPHA, coding: str = "cc") -> list[dict]:
    """Every hypothesis, decided as the module docstring states. `coding="censored"` (§6) scores pairs with at least
    one member landed, a non-landed member counting after a landed one."""
    out = []
    for h in hyps:
        sel = _selected(pairs, h)
        col = "x_first_cc" if coding == "cc" else "x_first"
        scored = sel.dropna(subset=[col])
        k, n = int(scored[col].sum()), int(len(scored))
        incomplete = int(len(sel) - int(sel["both_landed"].sum())) if coding == "cc" else int(sel[col].isna().sum())
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


def published(decided: list[dict], positive_controls: list[str]) -> dict[str, str]:
    """Claims after the positive-control gate and the selection qualifier (PREREGISTRATION-3 §8)."""
    by_target: dict[str, list[dict]] = {}
    for h in decided:
        by_target.setdefault(h["groups"][0]["identity"], []).append(h)
    failed = [t for t in positive_controls if not all(h["verdict"] == "supported" for h in by_target.get(t, []))
              or t not in by_target]
    out = {}
    for h in decided:
        target = h["groups"][0]["identity"]
        if failed and target not in positive_controls:
            out[h["id"]] = "withdrawn: a positive control did not end with both hypotheses supported (method check)"
        else:
            out[h["id"]] = h["verdict"] + (" (assumes selection)" if h["verdict"] == "supported" and not h["selection_robust"] else "")
    return out


def identification(decided: list[dict], claims: dict[str, str], manifest: dict, prior: dict[str, dict]) -> list[dict]:
    """Per core target: Study 3's two published claims next to its Study 1 and Study 2 claims, and the verdict."""
    rows = []
    for c in manifest["core_targets"]:
        key = f"{c['identity']}|{c['client_id']}|{c['ingress']}"
        mine = [h for h in decided if h["groups"][0]["identity"] == c["identity"]]
        s3 = {h["pair_kind"]: claims[h["id"]] for h in mine}
        s1 = prior.get("study1", {}).get("validators", {}).get(key, {}).get("published_claim")
        s2 = prior.get("study2", {}).get("validators", {}).get(key, {}).get("published_claim")
        ok = {k: s3.get(k, "").startswith("supported") for k in KINDS}
        identified = ok["c4"] and ok["c5"] and s1 == s2 == "reward_cost"
        c4 = next((h for h in mine if h["pair_kind"] == "c4"), None)
        # PREREGISTRATION-3 §5
        if any(v.startswith("withdrawn") for v in s3.values()):
            verdict = "withdrawn: method check failed"
        elif identified:
            verdict = "reward ÷ (cost + 1) identified"
        elif ok["c4"] and ok["c5"]:
            verdict = f"cost alone rejected and the reward effect shown, but the earlier claims are {s1} / {s2}"
        elif ok["c4"]:
            verdict = "cost alone rejected; the equal-cost reward effect is not shown"
        else:
            verdict = "the reward term is not shown; cost alone is not rejected"
            if c4 is not None and c4["n"] and c4["ci95"][1] < 0.5:
                verdict += "; the order follows cost against reward (C4 interval below 0.5)"
        rows.append({"identity": c["identity"], "client_id": c["client_id"], "ingress": c["ingress"],
                     "study1_claim": s1, "study2_claim": s2, "c4": s3.get("c4"), "c5": s3.get("c5"),
                     "reward_cost_identified": identified, "verdict": verdict})
    return rows


def analyse(dirs: list[Path], manifest: dict, designs: dict | None) -> dict:
    run = load_runs(dirs)
    windows = outcomes.window_table(run, designs)
    pairs = outcomes.pair_table(run, kinds=KINDS, designs=designs, windows=windows)
    hyps = manifest["hypotheses"]
    decided = evaluate(pairs, hyps)
    claims = published(decided, manifest.get("positive_controls", []))
    for h in decided:
        h["published_claim"] = claims[h["id"]]
    relaxed = pairs.copy()
    if len(relaxed):
        ok = {(r, s) for r, s, e in zip(windows["run_id"], windows["seq"], windows["exclusion"]) if e in ("", "mode:transition_ambiguous")}
        relaxed["evaluable"] = [(r, s) in ok for r, s in zip(relaxed["run_id"], relaxed["seq"])]

    def brief(rs: list[dict]) -> dict:
        return {r["id"]: {k: r[k] for k in ("k", "n", "estimate", "p_holm", "verdict")} for r in rs}

    nw = windows[windows["kit"] == "n"] if "kit" in windows else windows.iloc[0:0]
    return {
        "runs": [{"run_id": s.get("run_id"), "started_at": s.get("started_at"), "budget": s.get("budget")} for s in run.starts],
        "hypotheses": decided,
        "sensitivity": {"censored": brief(evaluate(pairs, hyps, coding="censored")),
                        "including_transition_ambiguous": brief(evaluate(relaxed, hyps)),
                        "same_slot": brief(evaluate(pairs.assign(x_first_cc=pairs["x_first_cc"].where(pairs["same_slot"] | ~pairs["both_landed"])), hyps))
                        if len(pairs) else {}},
        "send_order": {kind: {"first_sent_first": int(g["first_sent_first_cc"].sum()), "n": int(g["first_sent_first_cc"].notna().sum())}
                       for kind, g in pairs[pairs["evaluable"]].groupby("pair_kind")} if len(pairs) else {},
        "funnel": {"windows": int(len(nw)), "evaluable": int(nw["evaluable"].sum()) if len(nw) else 0,
                   "exclusions": nw[~nw["evaluable"]]["exclusion"].value_counts().to_dict() if len(nw) else {}},
    }


def compute(raw: Path, manifest_path: str, designs: dict, study1_results: Path = Path("data/derived/results.json"),
            study2_results: Path = Path("data/derived/study2/results.json")) -> dict:
    """Study 3 in full: H4/H5 per core target with their gates and sensitivity analyses, and the identification table
    against the committed Study 1 and Study 2 claims. `manifest_path` goes in as a POSIX string (the results record
    it and must be the same bytes on every platform)."""
    manifest = report.load_manifest(manifest_path)
    dirs, rejected = report.select_runs(raw, manifest)
    prior = {"study1": json.loads(Path(study1_results).read_text()),
             "study2": json.loads(Path(study2_results).read_text()).get("replication", {})}
    result: dict = {"manifest": str(manifest_path), "rejected_runs": rejected}
    if dirs:
        result |= analyse(dirs, manifest, designs)
        claims = {h["id"]: h["published_claim"] for h in result["hypotheses"]}
        result["identification"] = identification(result["hypotheses"], claims, manifest, prior)
    return json.loads(json.dumps(result, default=float))
