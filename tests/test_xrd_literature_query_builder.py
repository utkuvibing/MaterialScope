"""Phase 8 — XRD literature query builder stays XRD-native (no thermal/TGA wording)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.xrd_literature_query_builder import build_xrd_literature_query, build_xrd_query_presentation


def _minimal_record():
    return {
        "summary": {
            "match_status": "matched",
            "confidence_band": "moderate_confidence",
            "top_candidate_name": "Quartz",
            "top_candidate_display_name_unicode": "Quartz (alpha)",
            "top_candidate_formula": "SiO2",
            "top_candidate_score": 0.71,
            "top_candidate_shared_peak_count": 4,
        },
        "rows": [{"rank": 1, "display_name_unicode": "Quartz", "evidence": {"shared_peak_count": 4}}],
    }


def test_build_xrd_literature_query_centers_xrd_phase_language():
    q = build_xrd_literature_query(_minimal_record())
    text = (q.get("query_text") or "").lower()
    assert "xrd" in text
    assert "tga" not in text
    assert "dsc" not in text
    rationale = (q.get("query_rationale") or "").lower()
    assert "xrd" in rationale
    assert "thermal" not in rationale


def test_build_xrd_query_presentation_display_mode_is_xrd():
    q = build_xrd_literature_query(_minimal_record())
    pres = build_xrd_query_presentation(q)
    assert "xrd" in (pres.get("display_mode") or "").lower()
    raw = (pres.get("raw_query") or "").lower()
    assert "xrd" in raw
