"""Confirmatory statistics exactly as pre-registered (docs/PREREGISTRATION.md §3–4).

Each evaluable K-window contributes one binary observation per contrast and coding, so every confirmatory estimate
is a binomial proportion over independent windows:
- six separate predictions per rule (label and send-order coding for each of C1, C2, C3) — contrasts are never pooled
  into one denominator, because the three pairs of a window are not independent;
- intervals: exact Clopper–Pearson, Bonferroni-adjusted over the 36-effect family;
- directional predictions: confirmed if the adjusted interval is entirely on the predicted side of 0.5;
- tie predictions: confirmed by TOST equivalence within [0.35, 0.65] at level 1 − 2α_adj;
- "any": the rule makes no prediction (a key-tied contrast, whose tie-break is unspecified);
- p-values: randomisation tests under sharp nulls that respect the balanced send-order assignment, Holm-adjusted.
Window-level quantities (strictness, mixture diagnostic) are computed per window first, never from pooled pairs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats as sps

FAMILY_SIZE = 36
FAMILY_ALPHA = 0.05
TIE_MARGIN = 0.15
N_RANDOMISATION = 100_000
CONTRASTS = ("c1", "c2", "c3")

#: rule -> {"label": contrast -> x|y|tie, "order": contrast -> first|tie|any}
RULES: dict[str, dict[str, dict[str, str]]] = {
    "cu_price": {"label": {"c1": "x", "c2": "x", "c3": "tie"}, "order": {"c1": "tie", "c2": "tie", "c3": "any"}},
    "lamport_fee": {"label": {"c1": "y", "c2": "y", "c3": "tie"}, "order": {"c1": "tie", "c2": "tie", "c3": "any"}},
    "reward_cost": {"label": {"c1": "x", "c2": "y", "c3": "x"}, "order": {"c1": "tie", "c2": "tie", "c3": "tie"}},
    "fifo": {"label": {"c1": "tie", "c2": "tie", "c3": "tie"}, "order": {"c1": "first", "c2": "first", "c3": "first"}},
    "random": {"label": {"c1": "tie", "c2": "tie", "c3": "tie"}, "order": {"c1": "tie", "c2": "tie", "c3": "tie"}},
}
ECONOMIC_RULES = ("cu_price", "lamport_fee", "reward_cost")
ESTIMANDS = {"cc": ("x_first_cc", "first_sent_first_cc"), "censored": ("x_first", "first_sent_first")}


def clopper_pearson(k: int, n: int, alpha: float) -> tuple[float, float]:
    """Two-sided exact interval at level 1 − alpha."""
    if n == 0:
        return (0.0, 1.0)
    lo = 0.0 if k == 0 else sps.beta.ppf(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else sps.beta.ppf(1 - alpha / 2, k + 1, n - k)
    return (float(lo), float(hi))


def one_sided_lower(k: int, n: int, alpha: float = 0.05) -> float:
    if n == 0 or k == 0:
        return 0.0
    return float(sps.beta.ppf(alpha, k, n - k + 1))


def adjusted_alpha(family: int = FAMILY_SIZE, alpha: float = FAMILY_ALPHA) -> float:
    return alpha / family


@dataclass(frozen=True)
class Effect:
    """One binomial effect (a contrast in one coding) for one validator; one Bernoulli trial per window."""

    k: int
    n: int
    alpha_adj: float

    @property
    def estimate(self) -> float:
        return self.k / self.n if self.n else float("nan")

    @property
    def interval(self) -> tuple[float, float]:
        return clopper_pearson(self.k, self.n, self.alpha_adj)

    @property
    def equivalence_interval(self) -> tuple[float, float]:
        return clopper_pearson(self.k, self.n, 2 * self.alpha_adj)

    def verdict(self, prediction: str) -> str:
        """'confirmed' / 'contradicted' / 'undetermined' / 'none' (no prediction) for x|first, y, tie, any."""
        if prediction == "any":
            return "none"
        if self.n == 0:
            return "undetermined"
        lo, hi = self.interval
        if prediction in ("x", "first"):
            return "confirmed" if lo > 0.5 else "contradicted" if hi < 0.5 else "undetermined"
        if prediction == "y":
            return "confirmed" if hi < 0.5 else "contradicted" if lo > 0.5 else "undetermined"
        if prediction == "tie":
            elo, ehi = self.equivalence_interval
            if elo >= 0.5 - TIE_MARGIN and ehi <= 0.5 + TIE_MARGIN:
                return "confirmed"
            return "contradicted" if lo > 0.5 or hi < 0.5 else "undetermined"
        raise ValueError(prediction)


def rule_status(label: dict[str, Effect], order: dict[str, Effect]) -> dict[str, dict]:
    """Status of every candidate rule for one validator from its six effects (PREREGISTRATION §4).

    REJECTED: any prediction contradicted. CONFIRMED: every prediction confirmed (ties by equivalence).
    SUPPORTED: every directional prediction confirmed and no tie contradicted. UNDETERMINED: otherwise.
    """
    out = {}
    for rule, preds in RULES.items():
        verdicts = {f"label_{c}": label[c].verdict(preds["label"][c]) for c in CONTRASTS}
        verdicts |= {f"order_{c}": order[c].verdict(preds["order"][c]) for c in CONTRASTS}
        expected = {f"label_{c}": preds["label"][c] for c in CONTRASTS} | {f"order_{c}": preds["order"][c] for c in CONTRASTS}
        scored = {k: v for k, v in verdicts.items() if v != "none"}
        directional = [k for k, p in expected.items() if p in ("x", "y", "first")]
        if any(v == "contradicted" for v in scored.values()):
            status = "REJECTED"
        elif all(v == "confirmed" for v in scored.values()):
            status = "CONFIRMED"
        elif directional and all(verdicts[k] == "confirmed" for k in directional):
            status = "SUPPORTED"
        else:
            status = "UNDETERMINED"
        out[rule] = {"status": status, "verdicts": verdicts}
    return out


def randomisation_pvalues(x_first: np.ndarray, x_sent_first: np.ndarray, n_draws: int = N_RANDOMISATION, seed: int = 0) -> dict[str, float]:
    """Two-sided p-values for the label effect and the send-order effect of one contrast.

    Label null (outcome depends only on send position): z = [x_first == x_sent_first] is held fixed and the balanced
    send-order assignment is re-drawn (a permutation of x_sent_first); L* = mean(z == s*).
    Order null (outcome depends only on label): x_first is held fixed; O* = mean(x_first == s*).
    Valid conditional on the set of windows in the analysis not depending on the assignment (see PREREGISTRATION §4,
    selection assumption) — the worst-case bounds of §6 cover departures from it.
    """
    y = np.asarray(x_first, dtype=float)
    s = np.asarray(x_sent_first, dtype=float)
    ok = ~np.isnan(y)
    y, s = y[ok], s[ok]
    n = len(y)
    if n == 0:
        return {"label": float("nan"), "order": float("nan"), "n": 0}
    z = (y == s).astype(float)
    l_obs, o_obs = y.mean(), z.mean()
    rng = np.random.default_rng(seed)
    perms = s[np.argsort(rng.random((n_draws, n)), axis=1)]
    l_star = (z[None, :] == perms).mean(axis=1)
    o_star = (y[None, :] == perms).mean(axis=1)
    p_label = (np.sum(np.abs(l_star - 0.5) >= abs(l_obs - 0.5) - 1e-12) + 1) / (n_draws + 1)
    p_order = (np.sum(np.abs(o_star - 0.5) >= abs(o_obs - 0.5) - 1e-12) + 1) / (n_draws + 1)
    return {"label": float(p_label), "order": float(p_order), "n": n}


def holm(pvalues: dict[str, float], family_size: int | None = None) -> dict[str, float]:
    """Holm step-down adjusted p-values. With `family_size`, the family is fixed at that size (missing effects count
    as p = 1) instead of shrinking to whatever happened to be available."""
    items = sorted(((k, v) for k, v in pvalues.items() if not np.isnan(v)), key=lambda kv: kv[1])
    m = max(len(items), family_size or 0)
    adjusted, running = {}, 0.0
    for i, (k, v) in enumerate(items):
        running = max(running, min(1.0, (m - i) * v))
        adjusted[k] = running
    for k, v in pvalues.items():
        if np.isnan(v):
            adjusted[k] = float("nan")
    return adjusted


def mcnemar_exact(landed_x: np.ndarray, landed_y: np.ndarray) -> float:
    """Exact two-sided McNemar p-value for paired landing indicators."""
    lx, ly = np.asarray(landed_x, bool), np.asarray(landed_y, bool)
    b = int(np.sum(lx & ~ly))
    c = int(np.sum(~lx & ly))
    if b + c == 0:
        return 1.0
    return float(sps.binomtest(b, b + c, 0.5).pvalue)


def _evaluable(pairs: pd.DataFrame, c: str, col: str) -> pd.DataFrame:
    return pairs[(pairs["pair_kind"] == c) & pairs["evaluable"]].dropna(subset=[col])


def validator_effects(pairs: pd.DataFrame, alpha_adj: float | None = None, n_draws: int = N_RANDOMISATION, estimand: str = "cc") -> dict:
    """All confirmatory quantities for one validator from its evaluable contended K-window pairs."""
    alpha_adj = adjusted_alpha() if alpha_adj is None else alpha_adj
    xc, oc_ = ESTIMANDS[estimand]
    out: dict = {"label": {}, "order": {}, "pvalues": {}, "inclusion": {}}
    for c in CONTRASTS:
        obs = _evaluable(pairs, c, xc)
        out["label"][c] = Effect(int(obs[xc].sum()), len(obs), alpha_adj)
        out["order"][c] = Effect(int(obs[oc_].sum()), len(obs), alpha_adj)
        out["pvalues"][c] = randomisation_pvalues(obs[xc].to_numpy(), obs["x_sent_first"].to_numpy(dtype=float), n_draws=n_draws)
        g = pairs[(pairs["pair_kind"] == c) & pairs["evaluable"]]
        kx, ky, n = int(g["landed_x"].sum()), int(g["landed_y"].sum()), len(g)
        out["inclusion"][c] = {
            "windows": n,
            "x_rate": kx / n if n else float("nan"),
            "x_ci": clopper_pearson(kx, n, alpha_adj),
            "y_rate": ky / n if n else float("nan"),
            "y_ci": clopper_pearson(ky, n, alpha_adj),
            "mcnemar_p": mcnemar_exact(g["landed_x"].to_numpy(), g["landed_y"].to_numpy()) if n else float("nan"),
            "both": int((g["landed_x"] & g["landed_y"]).sum()),
            "neither": int((~g["landed_x"] & ~g["landed_y"]).sum()),
        }
    out["rules"] = rule_status(out["label"], out["order"])
    out["strictness"] = {r: strictness(pairs, r, estimand) for r in RULES if r != "random"}
    out["mixture"] = mixture_diagnostic(pairs, estimand, n_draws=min(n_draws, 20_000))
    out["selection"] = selection_balance(pairs, estimand)
    out["selection_bounds"] = selection_bounds(pairs, alpha_adj)
    out["diagnosis"] = diagnosis(out["rules"], out["mixture"], out["label"], out["selection"], out["strictness"],
                                 out["selection_bounds"], out["order"])
    return out


def selection_bounds(pairs: pd.DataFrame, alpha_adj: float | None = None) -> dict:
    """Selection-robust (worst-case) bounds over *every* pair of the evaluable windows (PREREGISTRATION §1).

    Complete-case effects are interpretable as ordering rules only under the selection assumption. Without it, every
    pair that is not complete — one member landed, or neither — could have gone either way. L_lo counts them all
    against x, L_hi all for x (likewise O for the first-sent member). A directional claim is *selection-robust* when it
    survives that worst case at the adjusted level, i.e. when no inclusion mechanism, however adversarial, could have
    produced it from a label-blind (or order-blind) ordering."""
    alpha_adj = adjusted_alpha() if alpha_adj is None else alpha_adj
    out = {}
    for c in CONTRASTS:
        g = pairs[(pairs["pair_kind"] == c) & pairs["evaluable"]]
        cc = g.dropna(subset=["x_first_cc"])
        n, total = len(cc), len(g)
        rest = total - n  # single-landed + neither-landed
        k_label, k_order = int(cc["x_first_cc"].sum()), int(cc["first_sent_first_cc"].sum())
        out[c] = {
            "complete": n,
            "single_landed": int((g["landed_x"] ^ g["landed_y"]).sum()),
            "neither_landed": int((~g["landed_x"] & ~g["landed_y"]).sum()),
            "L_lo": Effect(k_label, total, alpha_adj), "L_hi": Effect(k_label + rest, total, alpha_adj),
            "O_lo": Effect(k_order, total, alpha_adj), "O_hi": Effect(k_order + rest, total, alpha_adj),
        }
    return out


def selection_robust(rule: str, bounds: dict) -> bool | None:
    """Whether every directional prediction of `rule` holds even under the worst-case bounds (None: no prediction)."""
    checks = []
    for c in CONTRASTS:
        b = bounds[c]
        pl, po = RULES[rule]["label"][c], RULES[rule]["order"][c]
        if pl == "x":
            checks.append(b["L_lo"].n > 0 and b["L_lo"].interval[0] > 0.5)
        elif pl == "y":
            checks.append(b["L_hi"].n > 0 and b["L_hi"].interval[1] < 0.5)
        if po == "first":
            checks.append(b["O_lo"].n > 0 and b["O_lo"].interval[0] > 0.5)
    return all(checks) if checks else None


SELECTION_ALPHA = 0.01


def selection_balance(pairs: pd.DataFrame, estimand: str = "cc") -> dict:
    """Assignment-invariance check for the analysed subset (PREREGISTRATION §4, selection assumption).

    Send order is balanced by design, so among the pairs that enter the analysis the share with x sent first should
    be ≈ 0.5. A significant imbalance (exact binomial, p < 0.01) means inclusion depended on the assignment, and the
    label/order comparison for that contrast is not interpretable as an ordering rule.
    """
    xc, _ = ESTIMANDS[estimand]
    out = {}
    for c in CONTRASTS:
        g = _evaluable(pairs, c, xc)
        k, n = int(g["x_sent_first"].astype(bool).sum()), len(g)
        p = float(sps.binomtest(k, n, 0.5).pvalue) if n else float("nan")
        out[c] = {"x_sent_first": k, "n": n, "p": p, "flag": bool(n and p < SELECTION_ALPHA)}
    return out


def _window_agreement(pairs: pd.DataFrame, rule: str, estimand: str) -> pd.Series:
    """Per window: mean over the rule's directional label contrasts of [rule-preferred member landed first]."""
    xc, _ = ESTIMANDS[estimand]
    rows = []
    for c in CONTRASTS:
        pred = RULES[rule]["label"][c]
        if pred not in ("x", "y"):
            continue
        g = _evaluable(pairs, c, xc)
        hit = (g[xc] == (1.0 if pred == "x" else 0.0)).astype(float)
        rows.append(pd.DataFrame({"window": list(zip(g["run_id"], g["seq"])), "hit": hit.to_numpy(), "contrast": c}))
    if not rows:
        return pd.Series(dtype=float)
    df = pd.concat(rows)
    return df.groupby("window")["hit"].mean()


def strictness(pairs: pd.DataFrame, rule: str, estimand: str = "cc") -> dict:
    """Window-level strictness: share of *complete* windows in which every directional prediction of `rule` held,
    with an exact one-sided 95 % lower bound — one Bernoulli trial per window. A window is complete for `rule` only if
    every contrast carrying one of its directional predictions was observed there (both members landed): a window
    with a single surviving contrast cannot certify the whole rule. Incomplete windows are counted, not scored."""
    xc, oc_ = ESTIMANDS[estimand]
    if rule == "fifo":
        needed, col, want = list(CONTRASTS), oc_, {c: 1.0 for c in CONTRASTS}
    else:
        needed = [c for c in CONTRASTS if RULES[rule]["label"][c] in ("x", "y")]
        col = xc
        want = {c: 1.0 if RULES[rule]["label"][c] == "x" else 0.0 for c in needed}
    df = pairs[pairs["pair_kind"].isin(needed) & pairs["evaluable"]].dropna(subset=[col])
    hits = df.assign(hit=[float(v == want[c]) for v, c in zip(df[col], df["pair_kind"])])
    per_window = hits.groupby(["run_id", "seq"]).agg(n=("hit", "size"), all_hit=("hit", "min"))
    complete = per_window[per_window["n"] == len(needed)]
    k, n = int(complete["all_hit"].sum()), int(len(complete))
    incomplete = int(len(per_window) - n)
    # `lower95_worst` counts every incomplete window as a failure: what strictness is without the selection assumption.
    return {"windows_all_agree": k, "windows": n, "windows_incomplete": incomplete,
            "rate": k / n if n else float("nan"), "lower95": one_sided_lower(k, n),
            "lower95_worst": one_sided_lower(k, n + incomplete)}


def mixture_diagnostic(pairs: pd.DataFrame, estimand: str = "cc", n_draws: int = 20_000, seed: int = 0) -> dict:
    """Secondary (not part of the 36-effect family): is there a key-dependent component on top of arrival order?

    For each economic rule R: per window, d_w = (share of R's directional contrasts where R's preferred member landed
    first) − 0.5. Under a label-blind mechanism (any mixture of arrival order and label-blind noise), d_w is symmetric
    about 0 because send order is randomised independently of labels, so a sign-flip randomisation test over windows
    is valid. A component R is named only if (a) the test is significant after Holm over the three rules and (b) every
    one of R's directional contrasts points R's way (estimate on R's side of 0.5).
    """
    xc, _ = ESTIMANDS[estimand]
    rng = np.random.default_rng(seed)
    res, pvals = {}, {}
    for r in ECONOMIC_RULES:
        a = _window_agreement(pairs, r, estimand)
        d = (a - 0.5).to_numpy()
        if len(d) == 0:
            res[r] = {"windows": 0, "mean_agreement": float("nan"), "p": float("nan"), "consistent": False}
            pvals[r] = float("nan")
            continue
        obs = d.mean()
        flips = rng.choice([-1.0, 1.0], size=(n_draws, len(d)))
        p = (np.sum(np.abs((flips * d).mean(axis=1)) >= abs(obs) - 1e-12) + 1) / (n_draws + 1)
        consistent = True
        for c in CONTRASTS:
            pred = RULES[r]["label"][c]
            if pred not in ("x", "y"):
                continue
            g = _evaluable(pairs, c, xc)
            if len(g) == 0:
                consistent = False
                continue
            est = g[xc].mean()
            consistent &= est > 0.5 if pred == "x" else est < 0.5
        res[r] = {"windows": int(len(d)), "mean_agreement": float(a.mean()), "p": float(p), "consistent": bool(consistent)}
        pvals[r] = float(p)
    adj = holm(pvals)
    for r in res:
        res[r]["p_holm"] = adj.get(r, float("nan"))
    return res


#: A detected rule is reported as the validator's rule only if it provably governs the majority of windows.
STRICT_MAJORITY = 0.5


def governed_share_lower(rule: str, label: dict[str, Effect], order: dict[str, Effect], alpha: float = 0.05) -> float:
    """One-sided (1 − alpha) lower bound on the share s of windows that `rule` governs, if the other windows order its
    pairs label-blind: a contrast is then won by the rule's preferred member with probability L = (1 + s) / 2, so
    s ≥ 2·L_lower − 1. The bound is the minimum over the rule's directional predictions (label coding for a key rule,
    send-order coding for FIFO). Each contrast uses all of its complete pairs — no window has to be complete in every
    contrast, so the bound does not starve when landing rates are low."""
    bounds = []
    for c in CONTRASTS:
        for coding, preds, effs in (("label", RULES[rule]["label"], label), ("order", RULES[rule]["order"], order)):
            p, e = preds[c], effs[c]
            if p not in ("x", "y", "first"):
                continue
            k = e.k if p in ("x", "first") else e.n - e.k  # wins of the rule's preferred member
            bounds.append(2 * one_sided_lower(k, e.n, alpha) - 1)
    return max(min(bounds), 0.0) if bounds else 0.0


def diagnosis(rules: dict[str, dict], mixture: dict, label: dict[str, Effect], selection: dict | None = None,
              strict: dict | None = None, bounds: dict | None = None, order: dict[str, Effect] | None = None) -> dict:
    """One-line verdict per validator (PREREGISTRATION §4). Secondary diagnostics never resurrect a rule that the
    confirmatory contrasts rejected, except to describe a mixture with arrival order. A failed selection check
    overrides everything: the analysed subset is not assignment-invariant.

    A SUPPORTED/CONFIRMED rule R becomes the verdict `R` only if it provably governs the majority of windows
    (`governed_share_lower` > 0.5); otherwise the verdict is `partial:R` (R's key is visible, but other windows follow
    something else — a mode-switching leader, say). This split can only weaken a claim. Every rule verdict carries
    `selection_robust`: whether it survives the worst-case selection bounds; a mixture's economic component cannot be
    bounded that way, so a mixture is never selection-robust."""
    def out(verdict: str, rule: str | None = None, component: str | None = None, robust: bool | None = None,
            share: float | None = None) -> dict:
        if robust is None and rule and bounds:
            robust = selection_robust(rule, bounds)
        s = strict.get(rule) if rule and strict else None
        return {"verdict": verdict, "component": component, "selection_robust": robust, "governed_share_lower95": share,
                "strictness_lower95": s["lower95"] if s else None}

    if selection and any(v["flag"] for v in selection.values()):
        return out("unidentified:selection")
    supported = [r for r, v in rules.items() if v["status"] in ("SUPPORTED", "CONFIRMED") and r != "random"]
    if len(supported) > 1:
        return out("ambiguous:" + ",".join(sorted(supported)))

    def split(r: str) -> dict:
        if order is None:
            return out(r, r)
        share = governed_share_lower(r, label, order)
        return out(r if share > STRICT_MAJORITY else f"partial:{r}", r, share=share)

    if supported == ["fifo"]:
        named = [r for r in ECONOMIC_RULES if mixture[r]["consistent"] and mixture[r]["p_holm"] < FAMILY_ALPHA]
        if len(named) == 1:
            return out(f"mixed:fifo+{named[0]}", "fifo", named[0], robust=False if bounds else None)
        return split("fifo")
    if supported:
        return split(supported[0])
    if rules["random"]["status"] == "REJECTED":
        return out("unidentified")
    return out("none")
