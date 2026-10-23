import numpy as np
import pandas as pd
import pytest

from itb_analysis import stats

A = stats.adjusted_alpha()


def test_clopper_pearson_known_values():
    lo, hi = stats.clopper_pearson(0, 10, 0.05)
    assert lo == 0.0 and hi == pytest.approx(0.3085, abs=1e-4)
    lo, hi = stats.clopper_pearson(10, 10, 0.05)
    assert hi == 1.0 and lo == pytest.approx(0.6915, abs=1e-4)
    lo, hi = stats.clopper_pearson(5, 10, 0.05)
    assert lo == pytest.approx(0.1871, abs=1e-4) and hi == pytest.approx(0.8129, abs=1e-4)


def test_zero_failures_bound_matches_rule_of_three():
    assert stats.one_sided_lower(40, 40) == pytest.approx(0.05 ** (1 / 40), abs=1e-9)


def test_directional_tie_and_none_verdicts():
    assert stats.Effect(38, 40, A).verdict("x") == "confirmed"
    assert stats.Effect(38, 40, A).verdict("y") == "contradicted"
    assert stats.Effect(2, 40, A).verdict("y") == "confirmed"
    assert stats.Effect(22, 40, A).verdict("x") == "undetermined"
    assert stats.Effect(20, 40, A).verdict("tie") == "undetermined"  # equivalence needs far more data
    assert stats.Effect(500, 1000, A).verdict("tie") == "confirmed"
    assert stats.Effect(40, 40, A).verdict("tie") == "contradicted"
    assert stats.Effect(40, 40, A).verdict("any") == "none"


def E(k, n=40):
    return stats.Effect(k, n, A)


def test_six_separate_predictions_reject_random_despite_cancelling_order_effects():
    # Reviewer counterexample: order 40/40, 0/40, 20/40 cancels to 60/120 when pooled; per contrast it rejects random.
    label = {"c1": E(20), "c2": E(20), "c3": E(20)}
    order = {"c1": E(40), "c2": E(0), "c3": E(20)}
    rules = stats.rule_status(label, order)
    assert rules["random"]["status"] == "REJECTED"


def test_reward_cost_truth_is_the_only_survivor():
    label = {"c1": E(40), "c2": E(0), "c3": E(40)}
    order = {"c1": E(20), "c2": E(21), "c3": E(19)}
    rules = stats.rule_status(label, order)
    assert rules["reward_cost"]["status"] in ("CONFIRMED", "SUPPORTED")
    assert all(rules[r]["status"] == "REJECTED" for r in ("cu_price", "lamport_fee", "fifo", "random"))


def test_cu_price_with_fifo_tie_break_is_not_rejected():
    # Reviewer counterexample: CU price sorting, FIFO only on equal prices (C3) -> O_C3 = 40/40 must not reject it.
    label = {"c1": E(40), "c2": E(40), "c3": E(20)}
    order = {"c1": E(20), "c2": E(20), "c3": E(40)}
    rules = stats.rule_status(label, order)
    assert rules["cu_price"]["status"] == "SUPPORTED"
    assert rules["cu_price"]["verdicts"]["order_c3"] == "none"
    assert rules["reward_cost"]["status"] == "REJECTED"


def test_fifo_truth():
    label = {c: E(20) for c in stats.CONTRASTS}
    order = {c: E(40) for c in stats.CONTRASTS}
    rules = stats.rule_status(label, order)
    assert rules["fifo"]["status"] == "SUPPORTED"
    assert rules["random"]["status"] == "REJECTED"
    assert all(rules[r]["status"] == "REJECTED" for r in ("cu_price", "lamport_fee", "reward_cost"))


def test_randomisation_pvalues_separate_label_from_order():
    rng = np.random.default_rng(1)
    s = np.array([1.0, 0.0] * 20)
    rng.shuffle(s)
    assert stats.randomisation_pvalues(np.ones(40), s, n_draws=20_000)["label"] < 0.001
    assert stats.randomisation_pvalues(s.copy(), s, n_draws=20_000)["order"] < 0.001


def test_holm_with_fixed_family():
    adj = stats.holm({"a": 0.01, "b": 0.02, "c": 0.04, "d": float("nan")})
    assert adj["a"] == pytest.approx(0.03) and adj["b"] == pytest.approx(0.04) and adj["c"] == pytest.approx(0.04)
    assert np.isnan(adj["d"])
    fixed = stats.holm({"a": 0.001}, family_size=36)
    assert fixed["a"] == pytest.approx(0.036)


def test_mcnemar_exact():
    assert stats.mcnemar_exact(np.array([1, 1, 0]), np.array([1, 1, 0])) == 1.0
    assert stats.mcnemar_exact(np.ones(12, bool), np.zeros(12, bool)) < 0.001


def _pairs(fn, n=80, seed=3):
    """Synthetic complete pairs: fn(contrast, x_sent_first, rng) -> x_first."""
    rng = np.random.default_rng(seed)
    rows = []
    for c in stats.CONTRASTS:
        for w in range(n):
            x_sent_first = w % 2 == 0
            x_first = bool(fn(c, x_sent_first, rng))
            rows.append({"run_id": "r", "seq": w, "pair_kind": c, "evaluable": True, "x_sent_first": x_sent_first,
                         "landed_x": True, "landed_y": True, "x_first_cc": float(x_first),
                         "first_sent_first_cc": float(x_first == x_sent_first)})
    return pd.DataFrame(rows)


RC_PRED = {"c1": True, "c2": False, "c3": True}


def test_label_blind_reordering_is_not_called_a_mixture():
    # Reviewer counterexample: FIFO obeyed 65 % of the time regardless of labels.
    pairs = _pairs(lambda c, xs, rng: xs if rng.random() < 0.65 else not xs)
    eff = stats.validator_effects(pairs, n_draws=2_000)
    assert not eff["diagnosis"]["verdict"].startswith("mixed")
    assert all(eff["mixture"][r]["p_holm"] > 0.01 for r in stats.ECONOMIC_RULES)


def test_real_mixture_is_detected_by_the_window_level_test():
    # Half the windows reward/cost, half FIFO: the key component shows in a window-level sign-flip test.
    pairs = _pairs(lambda c, xs, rng: xs if rng.random() < 0.5 else RC_PRED[c], n=200)
    eff = stats.validator_effects(pairs, n_draws=2_000)
    assert eff["mixture"]["reward_cost"]["consistent"] and eff["mixture"]["reward_cost"]["p_holm"] < 0.01
    assert eff["diagnosis"]["verdict"] in ("mixed:fifo+reward_cost", "unidentified")


def test_window_level_strictness_does_not_count_correlated_copies():
    pairs = _pairs(lambda c, xs, rng: RC_PRED[c], n=40)
    s = stats.strictness(pairs, "reward_cost")
    assert s["windows"] == 40 and s["windows_all_agree"] == 40
    assert s["lower95"] == pytest.approx(0.05 ** (1 / 40), abs=1e-9)  # 40 trials, not 120


def test_selection_imbalance_overrides_the_verdict():
    pairs = _pairs(lambda c, xs, rng: xs)  # FIFO
    biased = pairs[pairs["x_sent_first"] | (pairs["seq"] % 10 == 1)]  # keep mostly x-sent-first pairs
    eff = stats.validator_effects(biased, n_draws=1_000)
    assert eff["diagnosis"]["verdict"] == "unidentified:selection"
    assert stats.validator_effects(pairs, n_draws=1_000)["diagnosis"]["verdict"] == "fifo"


def _window_pairs(fn, n):
    """Complete or lost pairs per window: fn(contrast, window, x_sent_first) -> (x_first or None if both lost)."""
    rows = []
    for w in range(n):
        xs = w % 2 == 0
        for c in stats.CONTRASTS:
            x_first = fn(c, w, xs)
            lost = x_first is None
            rows.append({"run_id": "r", "seq": w, "pair_kind": c, "evaluable": True, "x_sent_first": xs,
                         "landed_x": not lost, "landed_y": not lost,
                         "x_first_cc": np.nan if lost else float(x_first),
                         "first_sent_first_cc": np.nan if lost else float(x_first == xs)})
    return pd.DataFrame(rows)


def test_strictness_is_scored_only_on_complete_windows():
    # Gate-1b counterexample (N10): only C1 is ever observed, always reward/cost's way; that cannot certify the rule.
    pairs = _pairs(lambda c, xs, rng: RC_PRED[c], n=40)
    pairs.loc[pairs["pair_kind"] != "c1", ["x_first_cc", "first_sent_first_cc"]] = np.nan
    s = stats.strictness(pairs, "reward_cost")
    assert (s["windows"], s["windows_incomplete"], s["lower95"]) == (0, 40, 0.0)


def test_a_mode_switching_leader_is_partial_not_the_rule():
    # 24 windows follow reward/cost, 16 follow arrival order: reward/cost is SUPPORTED, but it does not provably govern
    # most windows, so the verdict must say so.
    pairs = _window_pairs(lambda c, w, xs: RC_PRED[c] if w < 24 else xs, 40)
    eff = stats.validator_effects(pairs, n_draws=1_000)
    assert eff["rules"]["reward_cost"]["status"] == "SUPPORTED"
    assert eff["strictness"]["reward_cost"]["lower95"] < stats.STRICT_MAJORITY
    assert eff["diagnosis"]["verdict"] == "partial:reward_cost"
    strict = stats.validator_effects(_window_pairs(lambda c, w, xs: RC_PRED[c], 40), n_draws=1_000)
    assert strict["diagnosis"]["verdict"] == "reward_cost" and strict["diagnosis"]["selection_robust"] is True


def test_balanced_double_loss_is_flagged_as_not_selection_robust():
    # Gate-1b counterexample (R2): a label-blind winning position per window; C1/C2 pairs are lost entirely whenever
    # it would make y win. Retained pairs are balanced in send order and x wins all of them, so the complete-case
    # analysis names CU price — the claim must be marked as resting on the selection assumption.
    def fn(c, w, xs):
        win_first = (w // 2) % 2 == 0
        x_wins = xs == win_first
        return None if c in ("c1", "c2") and not x_wins else x_wins

    eff = stats.validator_effects(_window_pairs(fn, 80), n_draws=1_000)
    assert all(not v["flag"] for v in eff["selection"].values()), "the balance check alone cannot see it"
    assert eff["diagnosis"]["verdict"] == "cu_price"
    assert eff["diagnosis"]["selection_robust"] is False
    b = eff["selection_bounds"]["c1"]
    assert (b["complete"], b["neither_landed"]) == (40, 40) and b["L_lo"].estimate == 0.5
