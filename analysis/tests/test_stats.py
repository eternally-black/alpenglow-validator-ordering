import numpy as np
import pytest

from itb_analysis import stats


def test_clopper_pearson_known_values():
    lo, hi = stats.clopper_pearson(0, 10, 0.05)
    assert lo == 0.0 and hi == pytest.approx(0.3085, abs=1e-4)
    lo, hi = stats.clopper_pearson(10, 10, 0.05)
    assert hi == 1.0 and lo == pytest.approx(0.6915, abs=1e-4)
    lo, hi = stats.clopper_pearson(5, 10, 0.05)
    assert lo == pytest.approx(0.1871, abs=1e-4) and hi == pytest.approx(0.8129, abs=1e-4)


def test_zero_failures_bound_matches_rule_of_three():
    # 95 % one-sided lower bound with 40/40 ≈ 1 - 3/40
    assert stats.one_sided_lower(40, 40) == pytest.approx(0.05 ** (1 / 40), abs=1e-9)


def test_directional_and_tie_verdicts():
    a = stats.adjusted_alpha()
    assert stats.Effect(38, 40, a).verdict("x") == "confirmed"
    assert stats.Effect(38, 40, a).verdict("y") == "contradicted"
    assert stats.Effect(2, 40, a).verdict("y") == "confirmed"
    assert stats.Effect(22, 40, a).verdict("x") == "undetermined"
    # A tie needs a lot of data to be *confirmed* by equivalence at the family level.
    assert stats.Effect(20, 40, a).verdict("tie") == "undetermined"
    assert stats.Effect(500, 1000, a).verdict("tie") == "confirmed"
    assert stats.Effect(40, 40, a).verdict("tie") == "contradicted"


def test_rule_status_reward_cost_pattern():
    a = stats.adjusted_alpha()
    label = {"c1": stats.Effect(40, 40, a), "c2": stats.Effect(0, 40, a), "c3": stats.Effect(40, 40, a)}
    order = stats.Effect(60, 120, a)
    rules = stats.rule_status({"order": order}, label)
    assert rules["cu_price"]["status"] == "REJECTED"  # predicts A' first in C2
    assert rules["lamport_fee"]["status"] == "REJECTED"  # predicts B first in C1
    assert rules["fifo"]["status"] == "REJECTED"
    assert rules["random"]["status"] == "REJECTED"
    # reward/cost's directional predictions hold; its order-tie needs equivalence, which n=120 may not reach.
    assert rules["reward_cost"]["status"] in ("CONFIRMED", "SUPPORTED")
    assert rules["reward_cost"]["verdicts"]["c2"] == "confirmed"


def test_cu_price_truth_is_supported_and_only_survivor():
    a = stats.adjusted_alpha()
    label = {"c1": stats.Effect(39, 40, a), "c2": stats.Effect(38, 40, a), "c3": stats.Effect(21, 40, a)}
    rules = stats.rule_status({"order": stats.Effect(61, 120, a)}, label)
    assert rules["cu_price"]["status"] == "SUPPORTED"
    assert all(rules[r]["status"] == "REJECTED" for r in ("lamport_fee", "reward_cost", "fifo", "random"))


def test_fifo_truth():
    a = stats.adjusted_alpha()
    label = {c: stats.Effect(20, 40, a) for c in ("c1", "c2", "c3")}
    rules = stats.rule_status({"order": stats.Effect(118, 120, a)}, label)
    assert rules["fifo"]["status"] == "SUPPORTED"
    assert rules["random"]["status"] == "REJECTED"
    assert rules["reward_cost"]["status"] in ("UNDETERMINED", "REJECTED")


def test_randomisation_pvalues_separate_label_from_order():
    rng = np.random.default_rng(1)
    s = np.array([1.0, 0.0] * 20)
    rng.shuffle(s)
    label_rule = np.ones(40)  # x always first, whatever the send order
    p = stats.randomisation_pvalues(label_rule, s, n_draws=20_000)
    assert p["label"] < 0.001
    fifo = s.copy()  # whoever was sent first lands first
    p = stats.randomisation_pvalues(fifo, s, n_draws=20_000)
    assert p["order"] < 0.001


def test_holm():
    adj = stats.holm({"a": 0.01, "b": 0.02, "c": 0.04, "d": float("nan")})
    assert adj["a"] == pytest.approx(0.03) and adj["b"] == pytest.approx(0.04) and adj["c"] == pytest.approx(0.04)
    assert np.isnan(adj["d"])


def test_mcnemar_exact():
    assert stats.mcnemar_exact(np.array([1, 1, 0]), np.array([1, 1, 0])) == 1.0
    assert stats.mcnemar_exact(np.ones(12, bool), np.zeros(12, bool)) < 0.001
