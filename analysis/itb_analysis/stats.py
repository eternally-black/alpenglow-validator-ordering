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
    out["diagnosis"] = diagnosis(out["rules"], out["mixture"], out["label"], out["selection"])
    return out


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
    """Window-level strictness: share of windows in which *every* directional prediction of `rule` held (among its
    evaluable contrasts in that window), with an exact one-sided 95 % lower bound — one Bernoulli trial per window."""
    xc, oc_ = ESTIMANDS[estimand]
    if rule == "fifo":
        df = pairs[pairs["pair_kind"].isin(CONTRASTS) & pairs["evaluable"]].dropna(subset=[oc_])
        per_window = df.groupby(["run_id", "seq"])[oc_].min()
    else:
        per_window = _window_agreement(pairs, rule, estimand)
        per_window = (per_window == 1.0).astype(float)
    k, n = int(per_window.sum()), int(len(per_window))
    return {"windows_all_agree": k, "windows": n, "rate": k / n if n else float("nan"), "lower95": one_sided_lower(k, n)}


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


def diagnosis(rules: dict[str, dict], mixture: dict, label: dict[str, Effect], selection: dict | None = None) -> dict:
    """One-line verdict per validator (PREREGISTRATION §4). Secondary diagnostics never resurrect a rule that the
    confirmatory contrasts rejected, except to describe a mixture with arrival order. A failed selection check
    overrides everything: the analysed subset is not assignment-invariant."""
    if selection and any(v["flag"] for v in selection.values()):
        return {"verdict": "unidentified:selection", "component": None}
    supported = [r for r, v in rules.items() if v["status"] in ("SUPPORTED", "CONFIRMED") and r != "random"]
    if len(supported) > 1:
        return {"verdict": "ambiguous:" + ",".join(sorted(supported)), "component": None}
    if supported == ["fifo"]:
        named = [r for r in ECONOMIC_RULES if mixture[r]["consistent"] and mixture[r]["p_holm"] < FAMILY_ALPHA]
        if len(named) == 1:
            return {"verdict": f"mixed:fifo+{named[0]}", "component": named[0]}
        return {"verdict": "fifo", "component": None}
    if supported:
        return {"verdict": supported[0], "component": None}
    if rules["random"]["status"] == "REJECTED":
        return {"verdict": "unidentified", "component": None}
    return {"verdict": "none", "component": None}
