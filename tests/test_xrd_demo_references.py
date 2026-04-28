from __future__ import annotations

from core.xrd_demo_references import load_demo_xrd_references


def test_demo_xrd_reference_seed_is_bundled_and_loadable():
    references = load_demo_xrd_references()

    assert references
    assert all(row["analysis_type"] == "XRD" for row in references)
    assert all(row.get("peaks") for row in references)
    assert {row["candidate_id"] for row in references} >= {"xrd_phase_alpha", "xrd_phase_beta"}
