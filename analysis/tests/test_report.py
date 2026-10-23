"""PREREGISTRATION §9 report gates that depend on the regime split."""

from itb_analysis import stats
from itb_analysis.report import _regime_gates

ALPHA = 0.05 / stats.FAMILY_SIZE


def effects(**kn):
    return {c: stats.Effect(k, n, ALPHA) for c, (k, n) in kn.items()}


NULL = effects(c1=(20, 40), c2=(21, 40), c3=(19, 40))
STRONG = effects(c1=(38, 40), c2=(37, 40), c3=(39, 40))


def test_first_sent_wins_in_buffered_regime_breaks_the_buffer_assumption():
    by_regime = {"buffered": {"label": NULL, "order": STRONG}, "streaming": {"label": NULL, "order": NULL}}
    g = _regime_gates("direct", by_regime)
    assert g["buffer_assumption_broken"] is True
    assert g["key_conclusions_withdrawn"] is True


def test_buffer_gate_only_applies_to_direct_ingress():
    by_regime = {"buffered": {"label": NULL, "order": STRONG}}
    assert _regime_gates("bam_node", by_regime)["buffer_assumption_broken"] is None
    assert _regime_gates("bam_node", by_regime)["key_conclusions_withdrawn"] is False


def test_label_effects_only_when_streaming_are_flagged():
    by_regime = {"buffered": {"label": NULL, "order": NULL}, "streaming": {"label": STRONG, "order": NULL}}
    g = _regime_gates("direct", by_regime)
    assert g["label_effects_streaming_only"] is True
    assert g["buffer_assumption_broken"] is False


def test_label_effects_in_both_regimes_are_not_flagged():
    by_regime = {"buffered": {"label": STRONG, "order": NULL}, "streaming": {"label": STRONG, "order": NULL}}
    assert _regime_gates("direct", by_regime)["label_effects_streaming_only"] is False
