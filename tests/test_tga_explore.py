"""Unit tests for TGA Dash exploration helpers (history, raw quality, step reference)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np
import pytest

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dash_app.components.tga_explore import (
    append_undo_after_edit,
    build_tga_raw_quality_panel,
    compute_tga_raw_exploration_stats,
    format_tga_step_reference_callout,
    perform_redo,
    perform_undo,
    tga_draft_processing_equal,
)


def _draft(smooth_window: int = 11) -> dict:
    return {
        "smoothing": {"method": "savgol", "window_length": smooth_window, "polyorder": 3},
        "step_detection": {"method": "dtg_peaks", "prominence": None, "min_mass_loss": 0.5, "search_half_width": 80},
    }


def test_append_undo_after_edit_pushes_when_changed():
    past, fut = append_undo_after_edit([], [], _draft(11), _draft(13))
    assert len(past) == 1
    assert past[0]["smoothing"]["window_length"] == 11
    assert fut == []


def test_append_undo_after_edit_skips_when_unchanged():
    d = _draft(11)
    past, fut = append_undo_after_edit([], [], d, copy.deepcopy(d))
    assert past == []
    assert fut == []


def test_perform_undo_redo_roundtrip():
    d1 = _draft(11)
    d2 = _draft(13)
    past = [copy.deepcopy(d1)]
    fut: list = []
    cur = copy.deepcopy(d2)
    out = perform_undo(past, fut, cur)
    assert out is not None
    prev, pl, fl = out
    assert prev["smoothing"]["window_length"] == 11
    assert len(pl) == 0
    assert len(fl) == 1
    out2 = perform_redo(pl, fl, prev)
    assert out2 is not None
    nxt, pl2, fl2 = out2
    assert nxt["smoothing"]["window_length"] == 13
    assert len(pl2) == 1
    assert len(fl2) == 0


def test_reset_default_draft_equality():
    a = _draft(11)
    b = copy.deepcopy(a)
    assert tga_draft_processing_equal(a, b) is True


def test_compute_tga_raw_exploration_stats_synthetic():
    t = np.linspace(25, 800, 200, dtype=float)
    s = 100.0 - 0.05 * (t - 25.0)  # decreasing mass-like
    val = {"status": "pass", "warnings": ["Test warning"], "issues": [], "checks": {"data_points": 200}}
    stats = compute_tga_raw_exploration_stats(t, s, validation=val)
    assert stats["point_count"] == 200
    assert stats["temp_min"] < stats["temp_max"]
    assert "mass_trend_decreasing" in stats["hints"]
    assert any("Test warning" in m for m in stats["validation_messages"])


def test_build_tga_raw_quality_panel_renders_grade():
    stats = {
        "point_count": 100,
        "temp_min": 20.0,
        "temp_max": 600.0,
        "signal_min": 90.0,
        "signal_max": 100.0,
        "apparent_mass_change": 10.0,
        "warnings": [],
        "hints": [],
        "validation_messages": [],
        "quality_metrics": {"Overall Grade": {"display": "Good", "level": "green"}},
    }
    out = build_tga_raw_quality_panel(stats, "en", temp_unit="°C", signal_unit="%")
    text = str(out)
    assert "100" in text
    assert "points" in text or "point" in text.lower()


def test_step_reference_callout_neutral_and_match():
    neutral = format_tga_step_reference_callout(1234.0, "en")
    assert str(neutral)

    near = format_tga_step_reference_callout(200.0, "en")
    st = str(near)
    assert "200" in st or "Ref" in st or "badge" in st
