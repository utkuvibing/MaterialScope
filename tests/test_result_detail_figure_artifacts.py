"""Result detail API includes non-binary figure artifact metadata."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.detail import build_result_detail


def _minimal_xrd_record(result_id: str) -> dict:
    return {
        "id": result_id,
        "analysis_type": "XRD",
        "status": "stable",
        "dataset_key": "synthetic_xrd",
        "metadata": {},
        "summary": {"match_status": "matched"},
        "rows": [],
        "artifacts": {
            "figure_keys": ["XRD Analysis - synthetic_xrd", "XRD Snapshot - synthetic_xrd - 20260101T000000Z"],
            "report_figure_key": "XRD Analysis - synthetic_xrd",
            "report_figure_status": "captured",
            "report_figure_error": "",
        },
        "processing": {"workflow_template_id": "xrd.general"},
        "provenance": {},
        "validation": {"status": "ok", "warnings": [], "issues": []},
        "review": {},
    }


def test_build_result_detail_includes_figure_artifacts_without_binary():
    state = {"results": {"xrd_t1": _minimal_xrd_record("xrd_t1")}}
    payload = build_result_detail(state, "xrd_t1")
    fa = payload.get("figure_artifacts") or {}
    assert fa["report_figure_key"] == "XRD Analysis - synthetic_xrd"
    assert fa["report_figure_status"] == "captured"
    assert len(fa["figure_keys"]) == 2
    assert "png" not in str(fa).lower()
