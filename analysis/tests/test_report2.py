"""Study 2 summary tables: they print what `study2.compute` decided, including withdrawn claims and empty cells."""

from itb_analysis import report2


def test_summary_prints_claims_and_cells():
    res = {
        "replicated": [{"identity": "A" * 44, "client_id": "Agave", "ingress": "direct", "study1_claim": "reward_cost",
                        "study2_claim": "reward_cost", "replicated": True}],
        "hypotheses": [{"id": "H1-agave", "pair_kind": "race", "dt_ms": 2.0, "side": "less", "k": 1, "n": 30,
                        "estimate": 1 / 30, "ci95": [0.001, 0.17], "p_holm": 1e-7, "by_target": {"A" * 44: [1, 30]},
                        "published_claim": "withdrawn: achieved gap 3.20 ms, not the planned 2 ms"}],
        "sensitivity": {"censored": {"H1-agave": {"k": 1, "n": 31, "verdict": "supported"}}},
        "curves": {"x": {"target_identity": "A" * 44, "client_id": "Agave", "ingress": "direct",
                         "overtake_lo_first": {"0": [3, 6], "2": [1, 30]}, "horizon_ms": [0.0, 2.0],
                         "equal_key_first_sent_first": {"10": [9, 10]}}},
    }
    md = report2.markdown_summary(res)
    assert "| `AAAAAAAA` | Agave | direct | reward_cost | reward_cost | **yes** |" in md
    assert "**withdrawn: achieved gap 3.20 ms, not the planned 2 ms**" in md and "O(2 ms) < 0.5 | 1/30" in md
    assert "| 3/6 (0.12–0.88) | 1/30 (0.00–0.17) | 0–2 ms | 10 ms: 9/10 |" in md
    assert "| < 10⁻⁶ |" in report2.markdown_summary(res | {"hypotheses": [res["hypotheses"][0] | {"p_holm": 0.0}]})
    bam = res["curves"]["x"] | {"overtake_lo_first": {"5": [4, 6], "10": [5, 5], "50": [0, 5]}, "horizon_ms": [10.0, 50.0]}
    assert "10–50 ms (non-monotone)" in report2.curves_table({"curves": {"x": bam}})
    assert report2.markdown_summary({"replicated": []}).count("##") == 1, "no hypothesis tables before Study 2 data"
