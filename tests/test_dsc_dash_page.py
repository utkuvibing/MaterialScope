"""Tests for the DSC Dash analysis page module."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import dash
import dash_bootstrap_components as dbc

# Ensure project root is importable
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dash import dcc, html


@pytest.fixture(autouse=True)
def _ensure_dash_app():
    """Create a minimal Dash app so dash.register_page() works."""
    import dash

    try:
        dash.get_app()
    except Exception:
        app = dash.Dash(
            __name__,
            use_pages=True,
            pages_folder="",
            suppress_callback_exceptions=True,
        )
        app.layout = html.Div(dash.page_container)
    yield


def _import_dsc_page():
    import dash_app.pages.dsc as mod

    return mod


def test_dsc_page_module_imports():
    mod = _import_dsc_page()
    assert hasattr(mod, "layout")
    assert hasattr(mod, "_DSC_TEMPLATE_IDS")
    assert hasattr(mod, "_DSC_ELIGIBLE_TYPES")


def test_layout_contains_parity_ids_and_stores():
    mod = _import_dsc_page()
    layout_str = str(mod.layout)

    expected_ids = [
        "dsc-left-tabs",
        "dsc-tab-setup-shell",
        "dsc-tab-processing-shell",
        "dsc-tab-run-shell",
        "dsc-processing-default",
        "dsc-processing-draft",
        "dsc-processing-undo",
        "dsc-processing-redo",
        "dsc-preset-refresh",
        "dsc-preset-select",
        "dsc-preset-save-btn",
        "dsc-smooth-apply-btn",
        "dsc-baseline-apply-btn",
        "dsc-peak-apply-btn",
        "dsc-tg-apply-btn",
        "dsc-result-dataset-summary",
        "dsc-result-metrics",
        "dsc-result-quality",
        "dsc-result-raw-metadata",
        "dsc-result-figure",
        "dsc-result-event-cards",
        "dsc-result-table",
        "dsc-result-processing",
    ]
    for element_id in expected_ids:
        assert element_id in layout_str, f"Missing layout element: {element_id}"


def test_layout_places_figure_before_event_cards():
    mod = _import_dsc_page()
    layout_str = str(mod.layout)
    assert layout_str.index("dsc-result-figure") < layout_str.index("dsc-result-event-cards")


def test_default_processing_draft_has_all_sections():
    mod = _import_dsc_page()
    defaults = mod._default_processing_draft()

    assert set(defaults.keys()) == {"smoothing", "baseline", "peak_detection", "glass_transition"}
    assert defaults["smoothing"]["method"] == "savgol"
    assert defaults["baseline"]["method"] == "asls"
    assert defaults["peak_detection"]["direction"] == "both"
    assert defaults["peak_detection"]["distance"] == 1
    assert defaults["glass_transition"] == {"mode": "auto", "region": None}


def test_normalize_peak_detection_values_sanitizes_direction_and_distance():
    mod = _import_dsc_page()

    normalized = mod._normalize_peak_detection_values("nonsense", prominence=-3, distance=0)
    assert normalized == {"direction": "both", "prominence": 0.0, "distance": 1}

    up = mod._normalize_peak_detection_values("up", prominence=0.12, distance=8)
    assert up == {"direction": "up", "prominence": 0.12, "distance": 8}


def test_undo_redo_reset_cycle_for_processing_draft():
    mod = _import_dsc_page()

    defaults = mod._default_processing_draft()
    edited = mod._apply_draft_section(defaults, "smoothing", {"method": "gaussian", "sigma": 3.4})
    undo = mod._push_undo([], defaults)

    restored, undo_after, redo_after = mod._do_undo(edited, undo, [])
    assert restored == defaults
    assert undo_after == []
    assert redo_after == [edited]

    reapplied, undo_next, redo_next = mod._do_redo(restored, undo_after, redo_after)
    assert reapplied == edited
    assert undo_next == [defaults]
    assert redo_next == []

    reset, undo_reset, redo_reset = mod._do_reset(edited, [], [{"stale": True}], defaults)
    assert reset == defaults
    assert undo_reset == [edited]
    assert redo_reset == []


def test_overrides_from_draft_includes_all_user_sections():
    mod = _import_dsc_page()

    overrides = mod._overrides_from_draft(
        {
            "smoothing": {"method": "savgol", "window_length": 15, "polyorder": 3},
            "baseline": {"method": "asls", "lam": 1e6, "p": 0.01},
            "peak_detection": {"direction": "down", "prominence": 0.02, "distance": 4},
            "glass_transition": {"mode": "auto", "region": [90.0, 180.0]},
            "other": {"ignored": True},
        }
    )

    assert set(overrides.keys()) == {"smoothing", "baseline", "peak_detection", "glass_transition"}


def test_toggle_preset_action_buttons_requires_selection():
    mod = _import_dsc_page()

    assert mod.toggle_dsc_preset_action_buttons(None) == (True, True)
    assert mod.toggle_dsc_preset_action_buttons("  ") == (True, True)
    assert mod.toggle_dsc_preset_action_buttons("polymer-default") == (False, False)


def test_build_event_cards_compacts_secondary_events():
    mod = _import_dsc_page()

    rows = [
        {
            "peak_type": "exotherm" if idx % 2 == 0 else "endotherm",
            "peak_temperature": 120.0 + idx * 14.0,
            "onset_temperature": 116.0 + idx * 14.0,
            "endset_temperature": 124.0 + idx * 14.0,
            "area": float(10 - idx),
            "height": float(4 - idx * 0.2),
        }
        for idx in range(6)
    ]

    cards = mod._build_event_cards({"glass_transition_count": 0}, rows, "en")
    cards_html = str(cards)
    assert cards_html.count("Peak ") == 4
    assert "Show 2 additional event(s)" in cards_html


def test_build_figure_returns_result_shell_without_debug(monkeypatch):
    mod = _import_dsc_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _project_id, _analysis_type, _dataset_key: {
            "temperature": [100.0, 130.0, 160.0, 190.0],
            "raw_signal": [0.0, 0.8, -0.25, 0.4],
            "smoothed": [0.1, 0.7, -0.2, 0.35],
            "baseline": [0.05, 0.05, 0.05, 0.05],
            "corrected": [0.05, 0.65, -0.25, 0.3],
        },
    )

    panel = mod._build_figure(
        "proj-1",
        "dataset-1",
        {
            "glass_transition_count": 1,
            "tg_midpoint": 150.0,
            "tg_onset": 140.0,
            "tg_endset": 160.0,
        },
        [{"peak_type": "exotherm", "peak_temperature": 130.0, "onset_temperature": 124.0, "endset_temperature": 138.0}],
        "light",
        "en",
        locale_data="en",
    )

    assert isinstance(panel, html.Div)
    assert "dsc-result-figure-shell" in str(getattr(panel, "className", "") or "")
    graph = panel.children
    assert isinstance(graph, dcc.Graph)
    assert "dsc-result-graph" in str(getattr(graph, "className", "") or "")
    assert graph.figure.layout.height == 600


def test_dsc_graph_config_exposes_png_export_options():
    mod = _import_dsc_page()
    cfg = mod._dsc_graph_config()

    assert cfg["displaylogo"] is False
    assert cfg["responsive"] is True
    assert cfg["toImageButtonOptions"]["format"] == "png"
    assert cfg["toImageButtonOptions"]["scale"] == 2


def test_run_dsc_analysis_forwards_draft_overrides_and_refreshes(monkeypatch):
    mod = _import_dsc_page()
    import dash_app.api_client as api_client

    captured: dict = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)
        return {"execution_status": "saved", "result_id": "dsc_r_1"}

    monkeypatch.setattr(api_client, "analysis_run", _fake_run)
    monkeypatch.setattr(mod, "interpret_run_result", lambda *_a, **_k: (html.Div("ok"), True, "dsc_r_1"))

    draft = {
        "smoothing": {"method": "savgol", "window_length": 21, "polyorder": 3},
        "baseline": {"method": "asls", "lam": 1e5, "p": 0.02},
        "peak_detection": {"direction": "both", "prominence": 0.01, "distance": 2},
        "glass_transition": {"mode": "auto", "region": [90.0, 190.0]},
    }

    alert, refresh, latest_result_id, workspace_refresh = mod.run_dsc_analysis(
        1,
        "proj-1",
        "dataset-1",
        "dsc.general",
        4,
        7,
        "en",
        draft,
    )

    assert isinstance(alert, html.Div)
    assert refresh == 5
    assert latest_result_id == "dsc_r_1"
    assert workspace_refresh == 8

    assert captured["project_id"] == "proj-1"
    assert captured["dataset_key"] == "dataset-1"
    assert captured["analysis_type"] == "DSC"
    assert captured["workflow_template_id"] == "dsc.general"
    assert captured["processing_overrides"] == mod._overrides_from_draft(draft)


def test_run_dsc_analysis_returns_danger_alert_on_backend_error(monkeypatch):
    mod = _import_dsc_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(api_client, "analysis_run", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("backend down")))

    status, refresh, latest_result_id, workspace_refresh = mod.run_dsc_analysis(
        1,
        "proj-1",
        "dataset-1",
        "dsc.general",
        0,
        0,
        "en",
        mod._default_processing_draft(),
    )

    assert isinstance(status, dbc.Alert)
    assert status.color == "danger"
    assert "backend down" in str(status)
    assert refresh is dash.no_update
    assert latest_result_id is dash.no_update
    assert workspace_refresh is dash.no_update


def test_capture_dsc_figure_delegates_to_shared_helper(monkeypatch):
    mod = _import_dsc_page()
    captured_kwargs: dict = {}

    def _fake_capture(**kwargs):
        captured_kwargs.update(kwargs)
        return {"dsc_r_2": {"status": "ok"}}

    monkeypatch.setattr(mod, "capture_result_figure_from_layout", _fake_capture)

    result = mod.capture_dsc_figure("dsc_r_2", "proj-1", {"graph": True}, {"old": "state"})

    assert result == {"dsc_r_2": {"status": "ok"}}
    assert captured_kwargs == {
        "result_id": "dsc_r_2",
        "project_id": "proj-1",
        "figure_children": {"graph": True},
        "captured": {"old": "state"},
        "analysis_type": "DSC",
    }


def test_display_result_returns_new_surface_sections(monkeypatch):
    mod = _import_dsc_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "workspace_result_detail",
        lambda _project_id, _result_id: {
            "summary": {
                "peak_count": 2,
                "glass_transition_count": 1,
                "tg_midpoint": 152.0,
                "tg_onset": 145.0,
                "tg_endset": 160.0,
                "delta_cp": 0.12,
                "sample_name": "Polymer A",
                "sample_mass": 12.5,
                "heating_rate": 10,
            },
            "result": {"dataset_key": "polymer_a.csv", "validation_status": "ok"},
            "processing": {
                "workflow_template_label": "General DSC",
                "workflow_template_version": 1,
                "signal_pipeline": {
                    "smoothing": {"method": "savgol", "window_length": 11, "polyorder": 3},
                    "baseline": {"method": "asls", "lam": 1e6, "p": 0.01},
                },
                "analysis_steps": {
                    "peak_detection": {"direction": "both", "prominence": 0.0, "distance": 1},
                    "glass_transition": {"mode": "auto", "region": None},
                },
                "method_context": {"sign_convention_label": "Endo down"},
            },
            "rows": [
                {
                    "peak_type": "endotherm",
                    "peak_temperature": 130.0,
                    "onset_temperature": 124.0,
                    "endset_temperature": 138.0,
                    "area": 1.2,
                    "fwhm": 9.0,
                    "height": 0.4,
                }
            ],
            "validation": {"status": "ok", "warning_count": 0, "issue_count": 0, "warnings": [], "issues": []},
        },
    )
    monkeypatch.setattr(
        api_client,
        "workspace_dataset_detail",
        lambda _project_id, _dataset_key: {
            "dataset": {"display_name": "Polymer A Dataset"},
            "metadata": {"file_name": "polymer_a.csv", "sample_mass": 12.5, "heating_rate": 10},
        },
    )
    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _project_id, _analysis_type, _dataset_key: {
            "temperature": [100.0, 130.0, 160.0, 190.0],
            "raw_signal": [0.0, 0.8, -0.25, 0.4],
            "smoothed": [0.1, 0.7, -0.2, 0.35],
            "baseline": [0.05, 0.05, 0.05, 0.05],
            "corrected": [0.05, 0.65, -0.25, 0.3],
        },
    )

    outputs = mod.display_result("dsc_polymer_a", 1, "light", "en", "proj-1")

    assert len(outputs) == 8
    for item in outputs:
        assert item is not None
