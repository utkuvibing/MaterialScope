"""Unit tests for XRD processing draft helpers (Phase 9 / parity with Streamlit defaults)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dash_app.components.xrd_explore import append_undo_after_edit, perform_redo, perform_undo, xrd_draft_processing_equal
from dash_app.components.xrd_processing_draft import (
    default_xrd_draft_for_template,
    normalize_xrd_processing_draft,
    xrd_overrides_from_draft,
    xrd_template_ids,
    xrd_ui_snapshot_dict,
    xrd_snapshots_equal,
)


def test_xrd_template_ids_stable():
    assert xrd_template_ids() == ("xrd.general", "xrd.phase_screening")


def test_unknown_template_id_falls_back_to_general_shape():
    d = default_xrd_draft_for_template("xrd.unknown")
    g = default_xrd_draft_for_template("xrd.general")
    assert d["axis_normalization"] == g["axis_normalization"]


def test_phase_screening_axis_window_differs_from_general():
    g = default_xrd_draft_for_template("xrd.general")
    p = default_xrd_draft_for_template("xrd.phase_screening")
    assert g["axis_normalization"]["axis_min"] is None
    assert g["axis_normalization"]["axis_max"] is None
    assert p["axis_normalization"]["axis_min"] == 5.0
    assert p["axis_normalization"]["axis_max"] == 90.0


def test_phase_screening_match_and_peak_defaults_stricter_than_general():
    g = default_xrd_draft_for_template("xrd.general")
    p = default_xrd_draft_for_template("xrd.phase_screening")
    gmc, pmc = g["method_context"], p["method_context"]
    assert pmc["xrd_match_tolerance_deg"] < gmc["xrd_match_tolerance_deg"]
    assert pmc["xrd_match_top_n"] > gmc["xrd_match_top_n"]
    assert p["peak_detection"]["prominence"] > g["peak_detection"]["prominence"]
    assert p["peak_detection"]["max_peaks"] > g["peak_detection"]["max_peaks"]


def test_default_draft_has_all_sections_and_plot_settings():
    d = default_xrd_draft_for_template("xrd.general")
    assert set(d.keys()) == {"axis_normalization", "smoothing", "baseline", "peak_detection", "method_context"}
    mc = d["method_context"]
    assert isinstance(mc.get("xrd_plot_settings"), dict)
    assert mc["xrd_plot_settings"].get("show_peak_labels") is True
    assert mc["xrd_plot_settings"].get("show_matched_peaks") is False
    assert mc["xrd_plot_settings"].get("show_intermediate_traces") is False


def test_xrd_overrides_from_draft_matches_normalized_top_level():
    raw = {
        "axis_normalization": {"sort_axis": False, "deduplicate": "MEAN", "axis_min": None, "axis_max": None},
        "smoothing": {"method": "savgol", "window_length": 4, "polyorder": 99},
        "baseline": {"method": "rolling_minimum", "window_length": 10, "smoothing_window": 4},
        "peak_detection": {"method": "scipy_find_peaks", "prominence": -1, "distance": 0, "width": 0, "max_peaks": 0},
        "method_context": {},
    }
    norm = normalize_xrd_processing_draft(raw)
    ov = xrd_overrides_from_draft(raw)
    assert ov.keys() == norm.keys()
    assert xrd_draft_processing_equal(ov, norm)


def test_ui_snapshot_includes_workflow_template_id():
    d = default_xrd_draft_for_template("xrd.phase_screening")
    snap = xrd_ui_snapshot_dict("xrd.phase_screening", d)
    assert snap["workflow_template_id"] == "xrd.phase_screening"
    assert "smoothing" in snap and "method_context" in snap


def test_snapshots_equal_detects_identical_and_different():
    d = default_xrd_draft_for_template("xrd.general")
    a = xrd_ui_snapshot_dict("xrd.general", d)
    b = xrd_ui_snapshot_dict("xrd.general", copy.deepcopy(d))
    assert xrd_snapshots_equal(a, b)
    d2 = copy.deepcopy(d)
    d2["smoothing"]["window_length"] = 99
    c = xrd_ui_snapshot_dict("xrd.general", d2)
    assert not xrd_snapshots_equal(a, c)


def test_undo_redo_cycle_for_processing_draft():
    defaults = default_xrd_draft_for_template("xrd.general")
    edited = copy.deepcopy(defaults)
    edited["smoothing"] = {**edited["smoothing"], "window_length": 21}

    past, fut = append_undo_after_edit([], [], defaults, edited)
    assert len(past) == 1
    assert fut == []

    undone = perform_undo(past, fut, edited)
    assert undone is not None
    prev, pl, fl = undone
    assert prev["smoothing"]["window_length"] == defaults["smoothing"]["window_length"]
    assert len(pl) == 0
    assert len(fl) == 1

    redone = perform_redo(pl, fl, prev)
    assert redone is not None
    nxt, pl2, fl2 = redone
    assert nxt["smoothing"]["window_length"] == 21
    assert len(pl2) == 1
    assert pl2[0]["smoothing"]["window_length"] == defaults["smoothing"]["window_length"]
    assert fl2 == []
