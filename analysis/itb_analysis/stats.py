"""Confirmatory statistics exactly as pre-registered (docs/PREREGISTRATION.md §3–4).

Each evaluable K-window contributes one binary observation per contrast and coding, so every estimate is a
binomial proportion over windows:
- intervals: exact Clopper–Pearson, Bonferroni-adjusted over the 36-effect family;
- directional predictions: confirmed if the adjusted interval is entirely on the predicted side of 0.5;
- tie predictions: confirmed by TOST equivalence within [0.35, 0.65] at level 1 − 2α_adj;
- p-values: randomisation tests under sharp nulls that respect the balanced send-order assignment, Holm-adjusted.
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

#: rule -> contrast -> prediction for the label coding ("x" / "y" / "tie"), plus the send-order coding.
RULES: dict[str, dict[str, str]] = {
    "cu_price": {"c1": "x", "c2": "x", "c3": "tie", "order": "tie"},
    "lamport_fee": {"c1": "y", "c2": "y", "c3": "tie", "order": "tie"},
    "reward_cost": {"c1": "x", "c2": "y", "c3": "x", "order": "tie"},
    "fifo": {"c1": "tie", "c2": "tie", "c3": "tie", "order": "first"},
    "random": {"c1": "tie", "c2": "tie", "c3": "tie", "order": "tie"},
}


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
    """One binomial effect (a contrast in one coding) for one validator."""

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
        """'confirmed' / 'contradicted' / 'undetermined' for a prediction in {'x' or 'first', 'y', 'tie'}."""
        if self.n == 0:
            return "undetermined"
        lo, hi = self.interval
        if prediction in ("x", "first"):
            if lo > 0.5:
                return "confirmed"
            if hi < 0.5:
                return "contradicted"
            return "undetermined"
        if prediction == "y":
            if hi < 0.5:
                return "confirmed"
            if lo > 0.5:
                return "contradicted"
            return "undetermined"
        if prediction == "tie":
            elo, ehi = self.equivalence_interval
            if elo >= 0.5 - TIE_MARGIN and ehi <= 0.5 + TIE_MARGIN:
                return "confirmed"
            if lo > 0.5 or hi < 0.5:
                return "contradicted"
            return "undetermined"
        raise ValueError(prediction)


def rule_status(effects: dict[str, Effect], label_effects: dict[str, Effect]) -> dict[str, dict]:
    """Status of every candidate rule for one validator (PREREGISTRATION §4).

    `label_effects[c]` is L_c (x-first rate) for c in c1..c3; `effects['order']` is O pooled over c1..c3
    (first-sent-first rate).
    - REJECTED: any prediction contradicted.
    - CONFIRMED: every prediction confirmed (ties by equivalence).
    - SUPPORTED: every *directional* prediction confirmed and no tie prediction contradicted (ties may be
      undetermined — at 40 windows an equivalence test at the family level is usually too wide to pass).
    - UNDETERMINED: otherwise. The "random" rule has no directional prediction, so it is either CONFIRMED,
      REJECTED or UNDETERMINED ("not rejected").
    """
    out = {}
    for rule, preds in RULES.items():
        verdicts = {c: label_effects[c].verdict(preds[c]) for c in ("c1", "c2", "c3")}
        verdicts["order"] = effects["order"].verdict(preds["order"])
        directional = [k for k, p in {**{c: preds[c] for c in ("c1", "c2", "c3")}, "order": preds["order"]}.items() if p != "tie"]
        if any(v == "contradicted" for v in verdicts.values()):
            status = "REJECTED"
        elif all(v == "confirmed" for v in verdicts.values()):
            status = "CONFIRMED"
        elif directional and all(verdicts[k] == "confirmed" for k in directional):
            status = "SUPPORTED"
        else:
            status = "UNDETERMINED"
        out[rule] = {"status": status, "verdicts": verdicts}
    return out


def randomisation_pvalues(x_first: np.ndarray, x_sent_first: np.ndarray, n_draws: int = N_RANDOMISATION, seed: int = 0) -> dict[str, float]:
    """Two-sided p-values for the label effect and the send-order effect.

    Label null (outcome depends only on send position): z = [x_first == x_sent_first] is held fixed and the balanced
    send-order assignment is re-drawn (a permutation of x_sent_first); L* = mean(z == s*).
    Order null (outcome depends only on label): x_first is held fixed; O* = mean(x_first == s*).
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


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values (NaNs ignored)."""
    items = sorted(((k, v) for k, v in pvalues.items() if not np.isnan(v)), key=lambda kv: kv[1])
    m = len(items)
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


def validator_effects(pairs: pd.DataFrame, alpha_adj: float | None = None, n_draws: int = N_RANDOMISATION) -> dict:
    """All confirmatory quantities for one validator from its evaluable contended K-window pairs."""
    alpha_adj = adjusted_alpha() if alpha_adj is None else alpha_adj
    out: dict = {"label": {}, "order_by_contrast": {}, "pvalues": {}, "inclusion": {}}
    order_k = order_n = 0
    for c in ("c1", "c2", "c3"):
        g = pairs[(pairs["pair_kind"] == c) & pairs["evaluable"]]
        obs = g.dropna(subset=["x_first"])
        k, n = int(obs["x_first"].sum()), len(obs)
        out["label"][c] = Effect(k, n, alpha_adj)
        ko, no = int(obs["first_sent_first"].sum()), len(obs)
        out["order_by_contrast"][c] = Effect(ko, no, alpha_adj)
        order_k, order_n = order_k + ko, order_n + no
        out["pvalues"][c] = randomisation_pvalues(obs["x_first"].to_numpy(), obs["x_sent_first"].to_numpy(dtype=float), n_draws=n_draws)
        out["inclusion"][c] = {
            "x_rate": float(g["landed_x"].mean()) if len(g) else float("nan"),
            "y_rate": float(g["landed_y"].mean()) if len(g) else float("nan"),
            "mcnemar_p": mcnemar_exact(g["landed_x"].to_numpy(), g["landed_y"].to_numpy()) if len(g) else float("nan"),
            "neither": int((~g["landed_x"] & ~g["landed_y"]).sum()),
            "windows": len(g),
        }
    out["order"] = Effect(order_k, order_n, alpha_adj)
    out["rules"] = rule_status({"order": out["order"]}, out["label"])
    return out


def strictness(pairs: pd.DataFrame, rule: str) -> dict:
    """Share of evaluable windows whose outcome matches a rule's directional predictions, with a one-sided 95 % lower bound."""
    preds = RULES[rule]
    k = n = 0
    for c in ("c1", "c2", "c3"):
        if preds[c] not in ("x", "y"):
            continue
        g = pairs[(pairs["pair_kind"] == c) & pairs["evaluable"]].dropna(subset=["x_first"])
        hit = g["x_first"] == (1.0 if preds[c] == "x" else 0.0)
        k, n = k + int(hit.sum()), n + len(g)
    if preds["order"] == "first":
        g = pairs[pairs["pair_kind"].isin(["c1", "c2", "c3"]) & pairs["evaluable"]].dropna(subset=["first_sent_first"])
        k, n = k + int(g["first_sent_first"].sum()), n + len(g)
    return {"agree": k, "n": n, "rate": k / n if n else float("nan"), "lower95": one_sided_lower(k, n)}
