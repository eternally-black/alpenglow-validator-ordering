"""Figures: horizon wording, deterministic LF output, and per-window hits consistent with strictness."""

import matplotlib.pyplot as plt
import pandas as pd

from itb_analysis import figures, stats


def test_horizon_brackets_the_crossing_of_one_half():
    assert figures._horizon([(5, 0, 7), (25, 0, 4)]) == "horizon < 5 ms"
    assert figures._horizon([(5, 5, 7), (25, 2, 6), (60, 0, 3)]) == "horizon ≈ 5–25 ms"
    assert figures._horizon([(5, 5, 6), (25, 3, 4), (60, 0, 5)]) == "horizon ≈ 25–60 ms"
    assert figures._horizon([(5, 1, 1), (25, 0, 0)]) == "horizon > 5 ms", "an empty cell is no evidence of a drop"


def _validator(identity: str, client: str, confirmatory: bool) -> dict:
    eff = {"ci_bonferroni": [0.7, 1.0], "estimate": 0.95}
    return {"target_identity": identity, "client_id": client, "ingress": "direct", "confirmatory": confirmatory,
            "label": {c: eff for c in stats.CONTRASTS}, "order": {c: eff | {"estimate": 0.5} for c in stats.CONTRASTS}}


def test_identification_svg_is_deterministic_lf_in_both_themes():
    res = {"validators": {"a": _validator("A" * 44, "Agave", True), "b": _validator("B" * 44, "Rakurai", False)}}
    for t in figures.THEMES:
        with plt.rc_context(figures._rc(t)):
            one, two = figures._svg(figures.fig_identification(res, t)), figures._svg(figures.fig_identification(res, t))
        assert one == two
        assert b"\r" not in one and t.surface.encode() in one


def test_window_hits_agree_with_strictness():
    # window 1: all three contrasts follow reward/cost (x, y, x); window 2: C2 breaks it; window 3: C3 missing.
    rows = []
    for seq, outcome in ((1, {"c1": 1.0, "c2": 0.0, "c3": 1.0}), (2, {"c1": 1.0, "c2": 1.0, "c3": 1.0}), (3, {"c1": 1.0, "c2": 0.0})):
        for c, x in outcome.items():
            rows.append({"run_id": "r", "seq": seq, "pair_kind": c, "evaluable": True, "x_first_cc": x, "first_sent_first_cc": 1.0})
    pairs = pd.DataFrame(rows)
    hits = stats.window_hits(pairs, "reward_cost")
    assert hits.loc[("r", 1), "all_hit"] == 1.0 and hits.loc[("r", 2), "all_hit"] == 0.0
    assert hits.loc[("r", 3), "n"] == 2 and hits.loc[("r", 3), "needed"] == 3
    s = stats.strictness(pairs, "reward_cost")
    assert (s["windows_all_agree"], s["windows"], s["windows_incomplete"]) == (1, 2, 1)
