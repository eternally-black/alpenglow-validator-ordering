"""Eligibility evidence must fail closed (gate-1b N12)."""

import pandas as pd

from itb_analysis.outcomes import _gossip_mode

USED = {"client_id": "Agave", "tpu_quic": "1.2.3.4:8009", "ingress": "direct"}


def states(after=None, before=None):
    snap = dict(USED)
    rows = [{"identity": "T", "at_unix_ns": 0, "present": True, **(before or snap)},
            {"identity": "T", "at_unix_ns": 20, "present": True, **(after or snap)}]
    return pd.DataFrame(rows)


def test_complete_matching_evidence_is_stable():
    assert _gossip_mode(states(), "T", 10, USED) == "stable"


def test_missing_used_endpoint_is_unknown_not_stable():
    assert _gossip_mode(states(), "T", 10, {"client_id": "Agave", "tpu_quic": None, "ingress": "direct"}) == "unknown"
    assert _gossip_mode(states(), "T", 10, None) == "unknown"


def test_snapshot_without_a_tpu_is_unknown_and_does_not_crash():
    assert _gossip_mode(states(after={**USED, "tpu_quic": None}), "T", 10, USED) == "unknown"


def test_changed_or_disappeared_endpoint_is_a_transition():
    assert _gossip_mode(states(after={**USED, "ingress": "bam_node"}), "T", 10, USED) == "transition_ambiguous"
    gone = states()
    gone.loc[1, "present"] = False
    assert _gossip_mode(gone, "T", 10, USED) == "transition_ambiguous"



def test_the_alpenglow_floor_follows_the_run_cluster():
    from itb_analysis.outcomes import FIRST_ALPENGLOW_SLOT, MAINNET_GENESIS_HASH, _alpenglow_floor

    assert _alpenglow_floor({"genesis_hash": MAINNET_GENESIS_HASH, "alpenglow": {"activated_at_slot": 0}}) == FIRST_ALPENGLOW_SLOT
    assert _alpenglow_floor({}) == FIRST_ALPENGLOW_SLOT
    assert _alpenglow_floor({"genesis_hash": "localnet", "alpenglow": {"activated_at_slot": 0}}) == 0
