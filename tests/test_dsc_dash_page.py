"""Tests for the DSC Dash analysis page module."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

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
        "dsc-preset-loaded-name",
        "dsc-preset-snapshot",
        "dsc-preset-dirty-flag",
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
        "dsc-figure-save-snapshot-btn",
        "dsc-figure-use-report-btn",
        "dsc-figure-artifact-status",
        "dsc-result-figure-artifacts",
        "dsc-figure-artifacts-summary",
        "dsc-figure-artifact-refresh",
        "dsc-result-derivative",
        "dsc-result-event-cards",
        "dsc-result-table",
        "dsc-result-processing",
        "dsc-prerun-dataset-info",
        "dsc-normalization-card-title",
        "dsc-normalization-enabled",
        "dsc-literature-compare-btn",
    ]
    for element_id in expected_ids:
        assert element_id in layout_str, f"Missing layout element: {element_id}"


def test_layout_places_figure_before_event_cards():
    mod = _import_dsc_page()
    layout_str = str(mod.layout)
    assert layout_str.index("dsc-result-figure") < layout_str.index("dsc-result-derivative")
    assert layout_str.index("dsc-result-derivative") < layout_str.index("dsc-result-event-cards")


def test_default_processing_draft_has_all_sections():
    mod = _import_dsc_page()
    defaults = mod._default_processing_draft()

    assert set(defaults.keys()) == {"smoothing", "baseline", "normalization", "peak_detection", "glass_transition"}
    assert defaults["smoothing"]["method"] == "savgol"
    assert defaults["baseline"]["method"] == "asls"
    assert defaults["baseline"].get("region") is None
    assert defaults["normalization"] == {"enabled": True}
    assert defaults["peak_detection"]["direction"] == "both"
    assert defaults["peak_detection"]["prominence"] is None
    assert defaults["peak_detection"]["distance"] is None
    assert defaults["glass_transition"] == {"mode": "auto", "region": None}


def test_normalize_normalization_values_defaults_to_enabled():
    mod = _import_dsc_page()

    assert mod._normalize_normalization_values(None) == {"enabled": True}
    assert mod._normalize_normalization_values(True) == {"enabled": True}
    assert mod._normalize_normalization_values(False) == {"enabled": False}
    assert mod._normalize_normalization_values("off") == {"enabled": False}


def test_normalize_peak_detection_values_sanitizes_direction_and_distance():
    mod = _import_dsc_page()

    normalized = mod._normalize_peak_detection_values("nonsense", prominence=-3, distance=0)
    assert normalized == {"direction": "both", "prominence": None, "distance": None}

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


def test_sync_dsc_normalization_from_setup_updates_draft_and_undo():
    mod = _import_dsc_page()
    defaults = mod._default_processing_draft()

    next_draft, undo, redo = mod.sync_dsc_normalization_from_setup(False, defaults, [])

    assert next_draft["normalization"] == {"enabled": False}
    assert undo == [defaults]
    assert redo == []
    assert mod.sync_normalization_control(next_draft) is False


def test_overrides_from_draft_includes_all_user_sections():
    mod = _import_dsc_page()

    overrides = mod._overrides_from_draft(
        {
            "smoothing": {"method": "savgol", "window_length": 15, "polyorder": 3},
            "baseline": {"method": "asls", "lam": 1e6, "p": 0.01, "region": [40.0, 200.0]},
            "normalization": {"enabled": False},
            "peak_detection": {"direction": "down", "prominence": 0.02, "distance": 4},
            "glass_transition": {"mode": "auto", "region": [90.0, 180.0]},
            "other": {"ignored": True},
        }
    )

    assert set(overrides.keys()) == {"smoothing", "baseline", "normalization", "peak_detection", "glass_transition"}
    assert overrides["baseline"]["region"] == [40.0, 200.0]
    assert overrides["normalization"] == {"enabled": False}


def test_normalize_baseline_values_optional_region():
    mod = _import_dsc_page()

    base = mod._normalize_baseline_values("asls", 1e6, 0.01, region_enabled=False, region_min=10, region_max=200)
    assert base["region"] is None

    restricted = mod._normalize_baseline_values("asls", 1e6, 0.01, region_enabled=True, region_min=30.0, region_max=180.0)
    assert restricted["region"] == [30.0, 180.0]


def test_render_dsc_baseline_chrome_emits_extended_parameter_hints():
    mod = _import_dsc_page()

    tr = mod.render_dsc_baseline_chrome("tr")
    en = mod.render_dsc_baseline_chrome("en")

    assert len(tr) == 14 and len(en) == 14
    assert "airPLS" in tr[2] and "airPLS" in en[2]
    assert "polinom" in tr[11].lower() and "polynomial" in en[11].lower()
    assert "snip" in tr[12].lower() and "snip" in en[12].lower()
    assert "ankraj" in tr[13].lower() and "anchor" in en[13].lower()


def test_build_derivative_panel_renders_when_dtg_present(monkeypatch):
    mod = _import_dsc_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _p, _t, _k: {
            "temperature": [100.0, 110.0, 120.0],
            "dtg": [0.01, 0.02, -0.01],
            "has_dtg": True,
        },
    )

    panel = mod._build_derivative_panel("proj", "ds", "light", "en", locale_data="en")
    assert "dsc-derivative-helper" in str(getattr(panel, "className", "") or "")
    assert isinstance(panel.children[2], dcc.Graph)


def test_build_derivative_panel_hidden_without_dtg(monkeypatch):
    mod = _import_dsc_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _p, _t, _k: {"temperature": [1.0], "dtg": [], "has_dtg": False},
    )

    panel = mod._build_derivative_panel("proj", "ds", "light", "en", locale_data="en")
    assert isinstance(panel, html.Div)
    assert not panel.children


def test_toggle_preset_action_buttons_requires_selection():
    mod = _import_dsc_page()

    assert mod.toggle_dsc_preset_action_buttons(None) == (True, True)
    assert mod.toggle_dsc_preset_action_buttons("  ") == (True, True)
    assert mod.toggle_dsc_preset_action_buttons("polymer-default") == (False, False)


def test_apply_dsc_preset_loads_normalization_from_processing(monkeypatch):
    mod = _import_dsc_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "load_analysis_preset",
        lambda *_args, **_kwargs: {
            "workflow_template_id": "dsc.general",
            "processing": {
                "signal_pipeline": {
                    "smoothing": {"method": "savgol", "window_length": 17, "polyorder": 3},
                    "baseline": {"method": "asls", "lam": 1e5, "p": 0.02},
                    "normalization": {"enabled": False},
                },
                "analysis_steps": {
                    "peak_detection": {"direction": "up", "prominence": 0.01, "distance": 3},
                    "glass_transition": {"mode": "auto", "region": [95.0, 180.0]},
                },
            },
        },
    )

    defaults = mod._default_processing_draft()
    next_draft, undo, redo, template_value, status, active_tab, loaded_name, snapshot = mod.apply_dsc_preset(
        1,
        "preset-a",
        defaults,
        [],
        "en",
    )

    assert next_draft["normalization"] == {"enabled": False}
    assert next_draft["smoothing"]["window_length"] == 17
    assert undo == [defaults]
    assert redo == []
    assert template_value == "dsc.general"
    assert active_tab == "dsc-tab-run"
    assert loaded_name == "preset-a"
    assert snapshot == mod._dsc_ui_snapshot_dict("dsc.general", next_draft)
    assert "preset-a" in status


def test_dsc_preset_dirty_flag_renders_clean_when_snapshot_matches():
    mod = _import_dsc_page()
    draft = mod._default_processing_draft()
    snap = mod._dsc_ui_snapshot_dict("dsc.general", draft)
    flag = mod.render_dsc_preset_dirty_flag(
        "en",
        "dsc.general",
        True,
        "savgol",
        11,
        3,
        2.0,
        "asls",
        1e6,
        0.01,
        6,
        40,
        6,
        False,
        None,
        None,
        "both",
        0.0,
        1,
        False,
        None,
        None,
        snap,
    )
    assert "text-success" in str(flag)


def test_dsc_preset_dirty_flag_renders_dirty_when_controls_differ():
    mod = _import_dsc_page()
    draft = mod._default_processing_draft()
    snap = mod._dsc_ui_snapshot_dict("dsc.general", draft)
    flag = mod.render_dsc_preset_dirty_flag(
        "en",
        "dsc.general",
        True,
        "gaussian",
        11,
        3,
        2.0,
        "asls",
        1e6,
        0.01,
        6,
        40,
        6,
        False,
        None,
        None,
        "both",
        0.0,
        1,
        False,
        None,
        None,
        snap,
    )
    assert "text-warning" in str(flag)


def test_dsc_preset_dirty_flag_renders_no_baseline_without_snapshot():
    mod = _import_dsc_page()
    flag = mod.render_dsc_preset_dirty_flag(
        "en",
        "dsc.general",
        True,
        "savgol",
        11,
        3,
        2.0,
        "asls",
        1e6,
        0.01,
        6,
        40,
        6,
        False,
        None,
        None,
        "both",
        0.0,
        1,
        False,
        None,
        None,
        None,
    )
    assert "text-muted" in str(flag)


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
    assert "ms-result-figure-shell" in str(getattr(panel, "className", "") or "")
    graph = panel.children
    assert isinstance(graph, dcc.Graph)
    assert "ms-result-graph" in str(getattr(graph, "className", "") or "")
    assert graph.figure.layout.height == 600
    assert graph.figure.layout.xaxis.title.text == "Temperature (°C)"
    assert graph.figure.layout.yaxis.title.text == "Heat Flow (mW)"


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
        "normalization": {"enabled": False},
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


def test_dsc_manual_figure_actions_use_expected_replace_semantics(monkeypatch):
    import dash_app.api_client as api_client
    import plotly.graph_objects as go

    mod = _import_dsc_page()
    calls: list[dict] = []

    def _fake_register(**kwargs):
        calls.append(dict(kwargs))
        return {"status": "ok", "figure_key": kwargs["label"]}

    monkeypatch.setattr(mod, "register_result_figure_from_layout_children", _fake_register)
    monkeypatch.setattr(api_client, "workspace_result_detail", lambda *_a, **_k: {"result": {"dataset_key": "dsc_ds"}})
    fig_child = html.Div(dcc.Graph(figure=go.Figure(data=[go.Scatter(x=[1], y=[1])])))

    monkeypatch.setattr(mod.dash, "callback_context", SimpleNamespace(triggered_id="dsc-figure-save-snapshot-btn"))
    _status, refresh = mod.dsc_figure_snapshot_or_report_figure(1, 0, "dsc_r", "proj", fig_child, "en", 0)
    assert calls[-1]["replace"] is False
    assert calls[-1]["label"].startswith("DSC Snapshot - dsc_ds - ")
    assert refresh == 1

    monkeypatch.setattr(mod.dash, "callback_context", SimpleNamespace(triggered_id="dsc-figure-use-report-btn"))
    _status, refresh = mod.dsc_figure_snapshot_or_report_figure(1, 1, "dsc_r", "proj", fig_child, "en", 1)
    assert calls[-1]["replace"] is True
    assert calls[-1]["label"] == "DSC Analysis - dsc_ds"
    assert refresh == 2


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
                    "normalization": {"enabled": False},
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
            "dtg": [0.0, 0.01, -0.02, 0.0],
            "has_dtg": True,
        },
    )

    outputs = mod.display_result("dsc_polymer_a", 1, "light", "en", "proj-1")

    assert len(outputs) == 9
    for item in outputs:
        assert item is not None
    assert "Mass normalization: disabled" in str(outputs[7])


def test_layout_places_figure_before_raw_metadata():
    mod = _import_dsc_page()
    layout_str = str(mod.layout)
    assert layout_str.index("dsc-result-figure") < layout_str.index("dsc-result-raw-metadata")


def test_build_dsc_raw_metadata_panel_splits_user_and_technical_keys():
    mod = _import_dsc_page()
    metadata = {
        "sample_name": "Polymer A",
        "sample_mass": 12.5,
        "heating_rate": 10,
        "import_method": "auto",
        "import_confidence": "medium",
        "source_data_hash": "abc123",
        "inferred_analysis_type": "DSC",
    }
    panel = mod._build_dsc_raw_metadata_panel(metadata, "en")
    panel_html = str(panel)

    assert "sample_name" in panel_html
    assert "sample_mass" in panel_html
    assert "import_method" in panel_html
    assert "inferred_analysis_type" in panel_html
    assert panel_html.count("Details(") >= 2


def test_build_dsc_raw_metadata_panel_empty_metadata():
    mod = _import_dsc_page()
    panel = mod._build_dsc_raw_metadata_panel(None, "en")
    panel_html = str(panel)
    assert "dsc-raw-metadata" not in panel_html.lower() or "empty" in panel_html.lower() or "text-muted" in panel_html


def test_normalize_peak_detection_values_maps_explicit_zero_to_none():
    mod = _import_dsc_page()
    normalized = mod._normalize_peak_detection_values("both", prominence=0.0, distance=1)
    assert normalized["prominence"] is None
    assert normalized["distance"] is None

    explicit = mod._normalize_peak_detection_values("both", prominence=0.12, distance=8)
    assert explicit["prominence"] == 0.12
    assert explicit["distance"] == 8


def test_literature_diagnostics_show_search_mode_and_trust():
    from dash_app.components.literature_compare_ui import render_literature_output

    payload = {
        "literature_claims": [],
        "literature_comparisons": [],
        "citations": [],
        "literature_context": {
            "provider_query_status": "no_results",
            "no_results_reason": "no_real_results",
            "source_count": 0,
            "citation_count": 0,
            "query_text": "DSC thermal event calorimetry",
            "search_mode": "behavior_first",
            "subject_trust": "low_trust",
        },
    }
    output = render_literature_output(payload, "en", i18n_prefix="dash.analysis.dsc.literature")
    output_html = str(output)

    assert "behavior_first" in output_html
    assert "low_trust" in output_html


def test_literature_diagnostics_show_fallback_queries():
    from dash_app.components.literature_compare_ui import render_literature_output

    payload = {
        "literature_claims": [],
        "literature_comparisons": [],
        "citations": [],
        "literature_context": {
            "provider_query_status": "no_results",
            "no_results_reason": "query_too_narrow",
            "source_count": 0,
            "citation_count": 0,
            "query_text": "DSC glass transition calorimetry",
            "search_mode": "behavior_first",
            "subject_trust": "low_trust",
            "executed_queries": [
                "DSC glass transition calorimetry",
                "thermal analysis glass transition polymer",
                "differential scanning calorimetry glass transition",
            ],
        },
    }
    output = render_literature_output(payload, "en", i18n_prefix="dash.analysis.dsc.literature")
    output_html = str(output)

    assert "thermal analysis glass transition polymer" in output_html
    assert "differential scanning calorimetry glass transition" in output_html


def test_literature_compare_status_alert_not_configured_includes_setup_hint():
    from dash_app.components.literature_compare_ui import literature_compare_status_alert

    payload = {
        "literature_claims": [{"claim_text": "Qualitative interpretation"}],
        "literature_comparisons": [],
        "citations": [],
        "literature_context": {
            "provider_query_status": "not_configured",
            "no_results_reason": "not_configured",
        },
    }
    alert = literature_compare_status_alert(payload, "en", i18n_prefix="dash.analysis.dsc.literature")
    alert_html = str(alert)
    assert "MATERIALSCOPE_OPENALEX_EMAIL" in alert_html
    assert "MATERIALSCOPE_LITERATURE_FIXTURE_FALLBACK" in alert_html


def test_raw_metadata_technical_details_label_does_not_leak_i18n_key():
    mod = _import_dsc_page()
    metadata = {
        "sample_name": "Polymer A",
        "import_method": "auto",
    }
    panel = mod._build_dsc_raw_metadata_panel(metadata, "en")
    panel_html = str(panel)
    assert "Technical details" in panel_html
    assert "dash.analysis.dsc.raw_metadata.technical_details" not in panel_html


def test_raw_metadata_technical_details_label_turkish():
    mod = _import_dsc_page()
    metadata = {
        "sample_name": "Polimer A",
        "import_method": "auto",
    }
    panel = mod._build_dsc_raw_metadata_panel(metadata, "tr")
    panel_html = str(panel)
    assert "Teknik detaylar" in panel_html
    assert "dash.analysis.dsc.raw_metadata.technical_details" not in panel_html


def test_dsc_page_avoids_tga_processing_key_literals():
    """Guard: DSC must not reference TGA processing i18n keys."""
    root = Path(__file__).resolve().parent.parent
    text = (root / "dash_app" / "pages" / "dsc.py").read_text(encoding="utf-8")
    assert "dash.analysis.tga.processing." not in text


def test_render_dsc_processing_history_chrome_uses_dsc_namespace(monkeypatch):
    mod = _import_dsc_page()
    monkeypatch.setattr(mod, "translate_ui", lambda loc, key, **kw: key)
    result = mod.render_dsc_processing_history_chrome("en")
    for output in result:
        assert "dash.analysis.dsc.processing." in output, f"Leaked key: {output}"
