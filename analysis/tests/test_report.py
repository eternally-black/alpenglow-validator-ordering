"""PREREGISTRATION §9 report gates that depend on the regime split."""

from itb_analysis import stats
from itb_analysis.report import _regime_gates

ALPHA = 0.05 / stats.FAMILY_SIZE


def effects(**kn):
    return {c: stats.Effect(k, n, ALPHA) for c, (k, n) in kn.items()}


NULL = effects(c1=(20, 40), c2=(21, 40), c3=(19, 40))
STRONG = effects(c1=(38, 40), c2=(37, 40), c3=(39, 40))


def test_first_sent_wins_in_buffered_regime_withdraws_a_key_verdict_but_not_fifo():
    by_regime = {"buffered": {"label": NULL, "order": STRONG}, "streaming": {"label": NULL, "order": NULL}}
    g = _regime_gates("direct", by_regime, "reward_cost")
    assert g["buffer_assumption_broken"] is True
    assert g["key_conclusions_withdrawn"] is True
    assert _regime_gates("direct", by_regime, "fifo")["key_conclusions_withdrawn"] is False, "FIFO predicts exactly this"


def test_buffer_gate_only_applies_to_direct_ingress():
    by_regime = {"buffered": {"label": NULL, "order": STRONG}}
    assert _regime_gates("bam_node", by_regime, "cu_price")["buffer_assumption_broken"] is None
    assert _regime_gates("bam_node", by_regime, "cu_price")["key_conclusions_withdrawn"] is False


def test_label_effects_only_when_streaming_are_flagged():
    by_regime = {"buffered": {"label": NULL, "order": NULL}, "streaming": {"label": STRONG, "order": NULL}}
    g = _regime_gates("direct", by_regime, "none")
    assert g["label_effects_streaming_only"] is True
    assert g["buffer_assumption_broken"] is False


def test_label_effects_in_both_regimes_are_not_flagged():
    by_regime = {"buffered": {"label": STRONG, "order": NULL}, "streaming": {"label": STRONG, "order": NULL}}
    assert _regime_gates("direct", by_regime, "none")["label_effects_streaming_only"] is False


def test_a_requested_manifest_that_does_not_exist_is_an_error(tmp_path):
    import pytest

    from itb_analysis.report import load_manifest

    assert load_manifest(None) is None
    with pytest.raises(FileNotFoundError):
        load_manifest(tmp_path / "campaign.json")


def test_published_claims_carry_every_withdrawal():
    from itb_analysis.report import published_claim

    v = {"diagnosis": {"verdict": "cu_price"}, "gates": {"key_conclusions_withdrawn": False}, "confirmatory": True}
    assert published_claim(v, controls_failed=False, is_control=False) == "cu_price"
    assert published_claim(v, controls_failed=True, is_control=False) == "withdrawn: positive control failed"
    assert published_claim(v, controls_failed=True, is_control=True) == "cu_price"
    assert published_claim(v | {"confirmatory": False}, False, False) == "exploratory: cu_price"
    broken = v | {"gates": {"key_conclusions_withdrawn": True}}
    assert published_claim(broken, False, False) == "withdrawn: buffer assumption broken"
    fragile = v | {"diagnosis": {"verdict": "cu_price", "selection_robust": False}}
    assert published_claim(fragile, False, False) == "cu_price (assumes selection)"
