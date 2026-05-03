"""Tests for the FTIR Dash analysis page module."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture(autouse=True)
def _ensure_dash_app():
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


def _import_ftir_page():
    import dash_app.pages.ftir as mod
    return mod


def test_ftir_page_module_imports():
    mod = _import_ftir_page()
    assert hasattr(mod, "layout")
    assert hasattr(mod, "_FTIR_TEMPLATE_IDS")
    assert hasattr(mod, "_FTIR_ELIGIBLE_TYPES")


def test_layout_contains_section_ids_in_order():
    mod = _import_ftir_page()
    layout_str = str(mod.layout)
    expected_ids = [
        "ftir-left-tabs",
        "ftir-tab-setup-shell",
        "ftir-tab-processing-shell",
        "ftir-tab-run-shell",
        "ftir-processing-default",
        "ftir-processing-draft",
        "ftir-processing-undo-stack",
        "ftir-processing-redo-stack",
        "ftir-history-hydrate",
        "ftir-preset-refresh",
        "ftir-preset-hydrate",
        "ftir-preset-loaded-name",
        "ftir-preset-snapshot",
        "ftir-plot-settings",
        "ftir-workflow-guide-title",
        "ftir-raw-quality-card-title",
        "ftir-raw-quality-panel",
        "ftir-processing-undo-btn",
        "ftir-processing-redo-btn",
        "ftir-processing-reset-btn",
        "ftir-preset-select",
        "ftir-preset-load-btn",
        "ftir-preset-save-btn",
        "ftir-preset-saveas-btn",
        "ftir-preset-delete-btn",
        "ftir-preset-status",
        "ftir-smoothing-card-title",
        "ftir-baseline-card-title",
        "ftir-normalization-card-title",
        "ftir-peak-card-title",
        "ftir-similarity-card-title",
        "ftir-smooth-method",
        "ftir-baseline-method",
        "ftir-norm-method",
        "ftir-peak-prominence",
        "ftir-peak-distance",
        "ftir-peak-max-peaks",
        "ftir-sim-metric",
        "ftir-sim-top-n",
        "ftir-sim-minimum-score",
        "ftir-plot-card-title",
        "ftir-plot-legend-mode",
        "ftir-plot-show-raw",
        "ftir-plot-show-smoothed",
        "ftir-plot-show-corrected",
        "ftir-plot-show-normalized",
        "ftir-plot-show-peaks",
        "ftir-plot-x-range-enabled",
        "ftir-plot-y-range-enabled",
        "ftir-result-analysis-summary",
        "ftir-result-metrics",
        "ftir-result-quality",
        "ftir-result-figure",
        "ftir-figure-save-snapshot-btn",
        "ftir-figure-use-report-btn",
        "ftir-figure-artifact-status",
        "ftir-result-figure-artifacts",
        "ftir-figure-artifacts-summary",
        "ftir-figure-artifact-refresh",
        "ftir-result-top-match",
        "ftir-result-peak-cards",
        "ftir-result-match-table",
        "ftir-result-processing",
        "ftir-result-raw-metadata",
        "ftir-literature-compare-btn",
        "ftir-literature-max-claims",
        "ftir-literature-persist",
        "ftir-literature-output",
        "ftir-literature-status",
        "ftir-figure-captured",
    ]
    for element_id in expected_ids:
        assert element_id in layout_str, f"Missing layout element: {element_id}"

    assert layout_str.index("ftir-result-analysis-summary") < layout_str.index("ftir-result-metrics")
    assert layout_str.index("ftir-result-metrics") < layout_str.index("ftir-result-quality")
    assert layout_str.index("ftir-result-quality") < layout_str.index("ftir-result-figure")
    assert layout_str.index("ftir-result-figure") < layout_str.index("ftir-result-top-match")
    assert layout_str.index("ftir-result-top-match") < layout_str.index("ftir-result-peak-cards")
    assert layout_str.index("ftir-result-peak-cards") < layout_str.index("ftir-result-match-table")
    assert layout_str.index("ftir-result-match-table") < layout_str.index("ftir-result-processing")
    assert layout_str.index("ftir-result-processing") < layout_str.index("ftir-result-raw-metadata")
    assert layout_str.index("ftir-result-raw-metadata") < layout_str.index("ftir-literature-compare-btn")
    assert layout_str.index("ftir-left-tabs") < layout_str.index("ftir-result-analysis-summary")
    assert layout_str.index("ftir-tab-setup-shell") < layout_str.index("ftir-tab-processing-shell")
    assert layout_str.index("ftir-tab-processing-shell") < layout_str.index("ftir-tab-run-shell")


def test_layout_uses_results_surface_class():
    mod = _import_ftir_page()
    assert "ms-results-surface" in str(mod.layout)


def test_default_processing_draft_has_all_sections():
    mod = _import_ftir_page()
    defaults = mod._default_ftir_processing_draft()
    assert set(defaults.keys()) == {"smoothing", "baseline", "normalization", "peak_detection", "similarity_matching"}
    assert defaults["smoothing"]["method"] == "savgol"
    assert defaults["baseline"]["method"] == "asls"
    assert defaults["normalization"]["method"] == "vector"
    assert defaults["peak_detection"]["prominence"] == 0.035
    assert defaults["similarity_matching"]["metric"] == "cosine"
    assert defaults["similarity_matching"]["top_n"] == 3


def test_normalize_peak_detection_values_sanitizes_inputs():
    mod = _import_ftir_page()
    # Negative values fall back to defaults
    normalized = mod._normalize_peak_detection_values(-3, 0, 0)
    assert normalized["prominence"] == 0.035
    assert normalized["distance"] == 1
    assert normalized["max_peaks"] == 1

    explicit = mod._normalize_peak_detection_values(0.12, 8, 15)
    assert explicit["prominence"] == 0.12
    assert explicit["distance"] == 8
    assert explicit["max_peaks"] == 15


def test_normalize_baseline_values_optional_region():
    mod = _import_ftir_page()
    base = mod._normalize_baseline_values("asls", 1e6, 0.01, False, 10, 200)
    assert base["region"] is None

    restricted = mod._normalize_baseline_values("asls", 1e6, 0.01, True, 400.0, 1800.0)
    assert restricted["region"] == [400.0, 1800.0]


def test_normalize_normalization_values_defaults():
    mod = _import_ftir_page()
    assert mod._normalize_normalization_values("vector") == {"method": "vector"}
    assert mod._normalize_normalization_values("max") == {"method": "max"}
    assert mod._normalize_normalization_values("snv") == {"method": "snv"}
    assert mod._normalize_normalization_values("nonsense") == {"method": "vector"}


def test_normalize_similarity_matching_values():
    mod = _import_ftir_page()
    assert mod._normalize_similarity_matching_values("pearson", 5, 0.6) == {"metric": "pearson", "top_n": 5, "minimum_score": 0.6}


def test_undo_redo_reset_cycle_for_processing_draft():
    mod = _import_ftir_page()
    defaults = mod._default_ftir_processing_draft()
    edited = {
        **defaults,
        "smoothing": {"method": "gaussian", "sigma": 3.4},
    }
    from dash_app.components.ftir_explore import append_undo_after_edit, perform_undo, perform_redo

    past, fut = append_undo_after_edit([], [], defaults, edited)
    assert len(past) == 1
    assert len(fut) == 0

    res = perform_undo(past, fut, edited)
    assert res is not None
    prev, pl, fl = res
    assert prev == defaults
    assert len(pl) == 0
    assert len(fl) == 1

    res2 = perform_redo(pl, fl, prev)
    assert res2 is not None
    nxt, pl2, fl2 = res2
    assert nxt == edited
    assert len(pl2) == 1
    assert len(fl2) == 0


def test_ftir_overrides_from_draft_includes_all_sections():
    mod = _import_ftir_page()
    draft = {
        "smoothing": {"method": "savgol", "window_length": 15, "polyorder": 3},
        "baseline": {"method": "asls", "lam": 1e5, "p": 0.02, "region": [400.0, 1800.0]},
        "normalization": {"method": "snv"},
        "peak_detection": {"prominence": 0.08, "distance": 8, "max_peaks": 12},
        "similarity_matching": {"metric": "pearson", "top_n": 5, "minimum_score": 0.6},
    }
    overrides = mod._ftir_overrides_from_draft(draft)
    assert set(overrides.keys()) == {"smoothing", "baseline", "normalization", "peak_detection", "similarity_matching"}
    assert overrides["baseline"]["region"] == [400.0, 1800.0]
    assert overrides["similarity_matching"]["metric"] == "pearson"


def test_ftir_draft_from_loaded_processing_nested():
    mod = _import_ftir_page()
    processing = {
        "workflow_template_id": "ftir.functional_groups",
        "signal_pipeline": {"smoothing": {"method": "moving_average", "window_length": 9}},
        "analysis_steps": {
            "peak_detection": {"prominence": 0.08, "distance": 6, "max_peaks": 8},
            "similarity_matching": {"top_n": 4, "minimum_score": 0.5},
        },
    }
    draft = mod._ftir_draft_from_loaded_processing(processing)
    assert draft["smoothing"]["method"] == "moving_average"
    assert draft["peak_detection"]["prominence"] == 0.08
    assert draft["similarity_matching"]["metric"] == "cosine"


def test_ftir_preset_processing_body_for_save_includes_all_sections():
    mod = _import_ftir_page()
    draft = mod._normalize_ftir_processing_draft({
        "smoothing": {"method": "savgol", "window_length": 15, "polyorder": 3},
        "peak_detection": {"prominence": 0.1, "distance": 10, "max_peaks": 20},
    })
    body = mod._ftir_preset_processing_body_for_save(draft)
    assert set(body.keys()) == {"smoothing", "baseline", "normalization", "peak_detection", "similarity_matching"}
    assert body["smoothing"]["window_length"] == 15
    assert body["similarity_matching"]["metric"] == "cosine"


def test_ftir_snapshots_equal_for_dirty_tracking():
    mod = _import_ftir_page()
    d = mod._default_ftir_processing_draft()
    a = mod._ftir_ui_snapshot_dict("ftir.general", d)
    b = mod._ftir_ui_snapshot_dict("ftir.general", d)
    assert mod._ftir_snapshots_equal(a, b)
    c = mod._ftir_ui_snapshot_dict("ftir.functional_groups", d)
    assert not mod._ftir_snapshots_equal(a, c)


def test_ftir_controls_to_draft_normalizes_window_and_prominence():
    mod = _import_ftir_page()
    d = mod._ftir_draft_from_control_values(
        "savgol", 10, 3, 2.0,
        "asls", 1e6, 0.01, False, None, None,
        "vector",
        0.0, 1, 1,
        "pearson", 3, 0.45,
    )
    assert d["smoothing"]["window_length"] % 2 == 1
    assert d["peak_detection"]["prominence"] == 0.0
    assert d["similarity_matching"]["metric"] == "pearson"


def test_run_ftir_analysis_forwards_processing_overrides(monkeypatch):
    mod = _import_ftir_page()
    captured: dict = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"execution_status": "failed", "detail": "noop"}

    monkeypatch.setattr("dash_app.api_client.analysis_run", fake_run)
    mod.run_ftir_analysis(
        1,
        "proj-1",
        "ds-1",
        "ftir.general",
        {"smoothing": {"method": "savgol", "window_length": 21, "polyorder": 3}, "peak_detection": mod._default_ftir_processing_draft()["peak_detection"]},
        0,
        0,
        "en",
    )
    assert captured.get("processing_overrides") is not None
    assert captured["processing_overrides"]["smoothing"]["window_length"] == 21
    assert captured["processing_overrides"]["similarity_matching"]["metric"] == "cosine"


def test_build_ftir_quality_card_renders_validation_and_checks():
    mod = _import_ftir_page()
    detail = {
        "validation": {
            "status": "warn",
            "warnings": ["Low signal"],
            "issues": [],
            "warning_count": 1,
            "issue_count": 0,
        },
        "result": {},
    }
    card = mod._build_ftir_quality_card(detail, {}, "en")
    text = str(card)
    assert "warn" in text
    assert "Low signal" in text
    assert getattr(card, "open", False) is True


def test_build_ftir_quality_card_collapsed_when_clean():
    mod = _import_ftir_page()
    detail = {
        "validation": {
            "status": "ok",
            "warnings": [],
            "issues": [],
            "warning_count": 0,
            "issue_count": 0,
        },
        "result": {},
    }
    card = mod._build_ftir_quality_card(detail, {}, "en")
    assert getattr(card, "open", True) is False


def test_build_ftir_quality_card_warning_count_matches_warning_list():
    mod = _import_ftir_page()
    detail = {
        "validation": {
            "status": "warn",
            "warnings": ["a"] * 10,
            "issues": [],
            "warning_count": 11,
            "issue_count": 0,
        },
        "result": {},
    }
    card = mod._build_ftir_quality_card(detail, {}, "en")
    text = str(card).lower()
    assert "10 warnings" in text
    assert "11 warnings" not in text


def test_build_ftir_analysis_summary_shows_instrument_and_vendor():
    mod = _import_ftir_page()
    dataset_detail = {
        "metadata": {"instrument": "Bruker Alpha", "vendor": "Bruker", "file_name": "x.csv"},
        "dataset": {"display_name": "Demo"},
    }
    out = mod._build_ftir_analysis_summary(dataset_detail, {}, {}, "en", locale_data="en")
    s = str(out)
    assert "Bruker Alpha" in s
    assert "Bruker" in s


def test_build_ftir_raw_metadata_panel_splits_user_and_technical():
    mod = _import_ftir_page()
    metadata = {
        "sample_name": "Demo",
        "instrument": "Bruker",
        "internal_vendor_blob": {"x": 1},
    }
    panel = mod._build_ftir_raw_metadata_panel(metadata, "en")
    s = str(panel)
    assert "sample_name" in s
    assert "internal_vendor_blob" in s
    assert "Technical details" in s or "Teknik detaylar" in s


def test_build_top_match_panel_library_unavailable_is_configuration_message():
    mod = _import_ftir_page()
    panel = mod._build_top_match_panel({"match_status": "library_unavailable"}, [], "en")
    s = str(panel).lower()
    assert "reference library" in s
    assert "alert" in s


def test_ftir_summary_separates_peak_detection_from_skipped_library_matching():
    mod = _import_ftir_page()
    summary = {
        "peak_count": 12,
        "match_status": "library_unavailable",
        "caution_message": "Reference spectral library matching was unavailable or not configured for this run.",
    }

    assert mod._ftir_library_status_label("en", summary) == "Library matching skipped: no reference library"
    panel = mod._build_ftir_analysis_summary(
        {"metadata": {"file_name": "ftir_particleboard_50g_figshare.csv"}, "dataset": {}},
        summary,
        {"dataset_key": "ftir-demo"},
        "en",
        locale_data="en",
    )
    rendered = str(panel)
    assert "Peak detection" in rendered
    assert "Completed (12 peaks)" in rendered
    assert "Library matching skipped: no reference library" in rendered
    assert "Configure or import an FTIR reference library" in rendered


def test_build_top_match_panel_renders_hero_summary():
    mod = _import_ftir_page()
    rows = [
        {
            "candidate_name": "Polyethylene",
            "normalized_score": 0.92,
            "confidence_band": "high_confidence",
            "library_provider": "OpenSpecy",
            "library_package": "openspecy_ftir_core",
            "evidence": {"shared_peak_count": 5, "observed_peak_count": 6},
        }
    ]
    panel = mod._build_top_match_panel({"top_match_name": "Polyethylene"}, rows, "en")
    s = str(panel)
    assert "Polyethylene" in s
    assert "0.92" in s
    assert "5/6" in s


def test_build_peak_cards_from_curves_renders_cards(monkeypatch):
    mod = _import_ftir_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _p, _t, _k: {
            "temperature": [4000.0, 3000.0, 2000.0, 1000.0],
            "peaks": [
                {"position": 2920.0, "intensity": 0.85},
                {"position": 2850.0, "intensity": 0.72},
            ],
        },
    )
    cards = mod._build_peak_cards_from_curves("proj", "ds", {"peak_count": 2}, "en")
    s = str(cards)
    assert "2920.0" in s
    assert "2850.0" in s


def test_build_peak_cards_truncates_high_peak_count(monkeypatch):
    mod = _import_ftir_page()
    import dash_app.api_client as api_client

    peaks = [{"position": float(3000 - i * 10), "intensity": 0.5 + i * 0.01} for i in range(10)]
    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _p, _t, _k: {"temperature": [], "peaks": peaks},
    )
    cards = mod._build_peak_cards_from_curves("proj", "ds", {"peak_count": 10}, "en")
    s = str(cards)
    assert "10" in s
    assert "8" in s or "showing" in s.lower()


def test_build_match_table_renders_columns():
    mod = _import_ftir_page()
    rows = [
        {"rank": 1, "candidate_id": "c1", "candidate_name": "A", "normalized_score": 0.9, "confidence_band": "high", "library_provider": "p", "library_package": "pkg"},
    ]
    table = mod._build_match_table(rows, "en")
    s = str(table)
    assert "candidate_name" in s
    assert "normalized_score" in s


def test_build_figure_returns_graph_when_curves_present(monkeypatch):
    mod = _import_ftir_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _p, _t, _k: {
            "temperature": [4000.0, 3000.0, 2000.0, 1000.0],
            "raw_signal": [0.1, 0.5, 0.3, 0.2],
            "smoothed": [0.12, 0.48, 0.32, 0.18],
            "baseline": [0.05, 0.05, 0.05, 0.05],
            "corrected": [0.07, 0.43, 0.27, 0.13],
            "normalized": [0.1, 0.6, 0.4, 0.2],
            "peaks": [{"position": 2920.0, "intensity": 0.6}],
            "has_smoothed": True,
            "has_baseline": True,
            "has_corrected": True,
            "has_normalized": True,
        },
    )
    fig_div = mod._build_figure("proj", "ds", {"peak_count": 1, "top_match_name": "Test", "match_status": "matched", "confidence_band": "high_confidence"}, "light", "en")
    s = str(fig_div)
    assert "ta-plot" in s
    assert "Peaks:" in s or "Tepeler:" in s
    graph = next(c for c in fig_div.children if isinstance(c, dcc.Graph))
    assert graph.id == "ftir-result-plot-graph"
    assert graph.figure.layout.meta["plot_view_mode"] == "result"
    assert "plot_display_settings" in graph.figure.layout.meta
    assert graph.figure.layout.hovermode == "x unified"
    assert graph.figure.layout.legend.y >= 0
    assert graph.figure.layout.xaxis.title.text == "Wavenumber (cm⁻¹)"
    assert graph.figure.layout.yaxis.title.text == "Absorbance (a.u.)"
    assert graph.config["toImageButtonOptions"]["filename"] == "materialscope_ftir_spectrum"
    raw_trace = next(trace for trace in graph.figure.data if "Imported" in str(trace.name))
    baseline_trace = next(trace for trace in graph.figure.data if "Baseline" in str(trace.name))
    assert raw_trace.visible == "legendonly"
    assert baseline_trace.visible == "legendonly"
    assert graph.figure.layout.yaxis.range[1] < 1.0


def test_build_figure_preserves_drawn_shapes_with_theme_contrast(monkeypatch):
    mod = _import_ftir_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda *_: {
            "temperature": [4000.0, 3000.0, 2000.0, 1000.0],
            "raw_signal": [0.1, 0.5, 0.3, 0.2],
            "smoothed": [0.12, 0.48, 0.32, 0.18],
            "baseline": [0.05, 0.05, 0.05, 0.05],
            "corrected": [0.07, 0.43, 0.27, 0.13],
            "normalized": [],
            "peaks": [],
            "diagnostics": {"plot_normalized_primary_axis": False},
        },
    )
    shapes = [{"type": "line", "x0": 1000, "y0": 0.1, "x1": 2000, "y1": 0.2, "line": {"color": "#1C1A1A"}}]

    fig_div = mod._build_figure("proj", "ds", {}, "dark", "en", drawn_shapes=shapes)
    graph = next(c for c in fig_div.children if isinstance(c, dcc.Graph))

    assert mod._spectral_shapes_from_relayout({"shapes": shapes}) == shapes
    assert len(graph.figure.layout.shapes) == 1
    assert graph.figure.layout.shapes[0].line.color == "#F2F0EB"


def test_build_figure_no_data_when_empty_curves(monkeypatch):
    mod = _import_ftir_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _p, _t, _k: {"temperature": []},
    )
    fig = mod._build_figure("proj", "ds", {}, "light", "en")
    assert isinstance(fig, html.P)


def test_build_figure_uses_transmittance_label_when_signal_role_is_transmittance(monkeypatch):
    mod = _import_ftir_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda *_: {
            "temperature": [4000.0, 3000.0, 2000.0, 1000.0],
            "raw_signal": [90.0, 70.0, 60.0, 50.0],
            "smoothed": [90.0, 70.0, 60.0, 50.0],
            "baseline": [],
            "corrected": [],
            "normalized": [],
            "peaks": [],
            "y_unit": "%",
            "signal_role": "transmittance",
            "diagnostics": {"plot_normalized_primary_axis": False},
        },
    )
    fig_div = mod._build_figure("proj", "ds", {}, "light", "en")
    graph = next(c for c in fig_div.children if isinstance(c, dcc.Graph))
    assert graph.figure.layout.yaxis.title.text == "Transmittance (%)"


def test_ftir_layout_includes_raw_quality_section():
    mod = _import_ftir_page()
    layout_str = str(mod.layout)
    assert "ftir-raw-quality-panel" in layout_str
    assert "ftir-raw-quality-card-title" in layout_str


def test_render_ftir_literature_uses_ftir_prefix():
    mod = _import_ftir_page()
    outputs = mod.render_ftir_literature_chrome("en", "ftir_result_1")
    assert any("Literature Compare" in str(o) for o in outputs)
    assert mod._FTIR_LITERATURE_PREFIX == "dash.analysis.ftir.literature"


def test_capture_ftir_figure_delegates_to_shared_helper(monkeypatch):
    mod = _import_ftir_page()
    captured_kwargs: dict = {}

    def _fake_capture(**kwargs):
        captured_kwargs.update(kwargs)
        return {"ftir_r_2": {"status": "ok"}}

    monkeypatch.setattr(mod, "capture_result_figure_from_layout", _fake_capture)
    result = mod.capture_ftir_figure("ftir_r_2", "proj-1", {"graph": True}, {"old": "state"})
    assert result == {"ftir_r_2": {"status": "ok"}}
    assert captured_kwargs == {
        "result_id": "ftir_r_2",
        "project_id": "proj-1",
        "figure_children": {"graph": True},
        "captured": {"old": "state"},
        "analysis_type": "FTIR",
    }


def test_toggle_ftir_smoothing_inputs_disables_correct_fields():
    mod = _import_ftir_page()
    assert mod.toggle_ftir_smoothing_inputs("savgol") == (False, False, True)
    assert mod.toggle_ftir_smoothing_inputs("moving_average") == (False, True, True)
    assert mod.toggle_ftir_smoothing_inputs("gaussian") == (True, True, False)


def test_toggle_ftir_baseline_inputs_disables_correct_fields():
    mod = _import_ftir_page()
    assert mod.toggle_ftir_baseline_inputs("asls") == (False, False)
    assert mod.toggle_ftir_baseline_inputs("linear") == (True, True)


def test_toggle_ftir_baseline_region_inputs():
    mod = _import_ftir_page()
    assert mod.toggle_ftir_baseline_region_inputs(True) == (False, False)
    assert mod.toggle_ftir_baseline_region_inputs(False) == (True, True)


def test_display_result_returns_nine_outputs(monkeypatch):
    mod = _import_ftir_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "workspace_result_detail",
        lambda _project_id, _result_id: {
            "summary": {
                "peak_count": 3,
                "match_status": "matched",
                "top_match_score": 0.85,
                "top_match_name": "Polypropylene",
                "sample_name": "Sample A",
            },
            "result": {"dataset_key": "sample_a.csv", "validation_status": "ok"},
            "processing": {
                "workflow_template_label": "General FTIR",
                "workflow_template_version": 1,
                "signal_pipeline": {
                    "smoothing": {"method": "savgol", "window_length": 11, "polyorder": 3},
                    "baseline": {"method": "asls", "lam": 1e6, "p": 0.01},
                    "normalization": {"method": "vector"},
                },
                "analysis_steps": {
                    "peak_detection": {"prominence": 0.05, "distance": 5, "max_peaks": 10},
                    "similarity_matching": {"top_n": 3, "minimum_score": 0.45},
                },
                "method_context": {"library_access_mode": "cloud_full_access", "library_result_source": "cloud_search"},
            },
            "rows_preview": [
                {
                    "rank": 1,
                    "candidate_id": "c1",
                    "candidate_name": "Polypropylene",
                    "normalized_score": 0.85,
                    "confidence_band": "high_confidence",
                    "library_provider": "OpenSpecy",
                    "library_package": "openspecy_ftir_core",
                    "evidence": {"shared_peak_count": 4, "observed_peak_count": 5},
                }
            ],
            "validation": {"status": "ok", "warning_count": 0, "issue_count": 0, "warnings": [], "issues": []},
        },
    )
    monkeypatch.setattr(
        api_client,
        "workspace_dataset_detail",
        lambda _project_id, _dataset_key: {
            "dataset": {"display_name": "Sample A Dataset"},
            "metadata": {"file_name": "sample_a.csv", "instrument": "Bruker"},
        },
    )
    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _project_id, _analysis_type, _dataset_key: {
            "temperature": [4000.0, 3000.0, 2000.0, 1000.0],
            "raw_signal": [0.1, 0.5, 0.3, 0.2],
            "smoothed": [0.12, 0.48, 0.32, 0.18],
            "baseline": [0.05, 0.05, 0.05, 0.05],
            "corrected": [0.07, 0.43, 0.27, 0.13],
            "normalized": [0.1, 0.6, 0.4, 0.2],
            "peaks": [{"position": 2920.0, "intensity": 0.6}],
            "has_smoothed": True,
            "has_baseline": True,
            "has_corrected": True,
            "has_normalized": True,
        },
    )

    outputs = mod.display_result("ftir_sample_a", 1, "light", "en", None, "proj-1")
    assert len(outputs) == 9
    for item in outputs:
        assert item is not None


def test_literature_compare_uses_ftir_prefix(monkeypatch):
    mod = _import_ftir_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "literature_compare",
        lambda _project_id, _result_id, **kwargs: {
            "literature_claims": [],
            "literature_comparisons": [],
            "citations": [],
            "literature_context": {},
        },
    )
    output, status = mod.compare_ftir_literature(1, "proj", "ftir_r1", 3, ["persist"], "en")
    assert output is not None
    assert status is not None


def test_preset_dirty_flag_renders_clean_when_snapshot_matches():
    mod = _import_ftir_page()
    draft = mod._default_ftir_processing_draft()
    snap = mod._ftir_ui_snapshot_dict("ftir.general", draft)
    flag = mod.render_ftir_preset_dirty_flag(
        "en", "ftir.general",
        "savgol", 11, 3, 2.0,
        "asls", 1e6, 0.01, False, None, None,
        "vector",
        0.035, 5, 12,
        "cosine", 3, 0.45,
        snap,
    )
    assert "text-success" in str(flag)


def test_preset_dirty_flag_renders_dirty_when_snapshot_differs():
    mod = _import_ftir_page()
    draft = mod._default_ftir_processing_draft()
    snap = mod._ftir_ui_snapshot_dict("ftir.general", draft)
    flag = mod.render_ftir_preset_dirty_flag(
        "en", "ftir.general",
        "gaussian", 11, 3, 2.0,
        "asls", 1e6, 0.01, False, None, None,
        "vector",
        0.035, 5, 12,
        "cosine", 3, 0.45,
        snap,
    )
    assert "text-warning" in str(flag)


def test_build_figure_shows_diagnostics_when_present(monkeypatch):
    mod = _import_ftir_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _p, _t, _k: {
            "temperature": [4000.0, 3000.0, 2000.0, 1000.0],
            "raw_signal": [0.1, 0.5, 0.3, 0.2],
            "smoothed": [0.12, 0.48, 0.32, 0.18],
            "baseline": [],
            "corrected": [],
            "normalized": [],
            "peaks": [],
            "has_smoothed": True,
            "has_baseline": False,
            "has_corrected": False,
            "has_normalized": False,
            "diagnostics": {
                "signal_role": "transmittance",
                "inverted_for_transmittance": True,
                "baseline_suppressed": True,
                "baseline_suppression_reason": "Baseline fit increases signal variance",
                "normalization_skipped": True,
                "normalization_skip_reason": "Signal has zero range",
                "peak_detection_no_peaks": True,
                "peak_detection_reason": "No peaks found",
            },
        },
    )
    fig_div = mod._build_figure("proj", "ds", {"peak_count": 0, "top_match_name": None, "match_status": "no_match", "confidence_band": "no_match"}, "light", "en")
    s = str(fig_div)
    assert "inverted" in s.lower()
    assert "baseline suppressed" in s.lower()
    assert "normalization skipped" in s.lower()
    assert "no peaks detected" in s.lower()


def test_ftir_literature_technical_collapsible_no_raw_key_leak():
    from dash_app.components.literature_compare_ui import render_literature_output

    payload = {
        "literature_claims": [],
        "literature_comparisons": [],
        "citations": [],
        "literature_context": {"provider_query_status": "ok", "query_text": "FTIR binder example query"},
    }
    tree = render_literature_output(
        payload,
        "en",
        i18n_prefix="dash.analysis.ftir.literature",
        evidence_preview_limit=2,
        alternative_preview_limit=1,
    )
    html_s = str(tree)
    assert "dash.analysis.ftir.literature.technical_details_title" not in html_s
    assert "Technical search details" in html_s


def test_build_figure_omits_normalized_when_backend_flags_shared_axis_unhelpful(monkeypatch):
    mod = _import_ftir_page()
    import dash_app.api_client as api_client
    from utils.i18n import translate_ui

    legend_norm = translate_ui("en", "dash.analysis.ftir.legend_normalized_spectrum")

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda *_: {
            "temperature": [4000.0, 3000.0, 2000.0, 1000.0],
            "raw_signal": [0.1, 0.5, 0.3, 0.2],
            "smoothed": [0.12, 0.48, 0.32, 0.18],
            "baseline": [0.05, 0.05, 0.05, 0.05],
            "corrected": [7.0, 9.0, 8.0, 6.0],
            "normalized": [0.001, 0.0011, 0.001, 0.001],
            "peaks": [],
            "diagnostics": {"plot_normalized_primary_axis": False},
        },
    )
    fig_div = mod._build_figure("proj", "ds", {}, "light", "en")
    graph = next(c for c in fig_div.children if isinstance(c, dcc.Graph))
    names = [tr.name for tr in graph.figure.data]
    assert legend_norm not in names


def test_build_figure_honors_plot_settings_for_traces_and_ranges(monkeypatch):
    mod = _import_ftir_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda *_: {
            "temperature": [4000.0, 3000.0, 2000.0, 1000.0],
            "raw_signal": [0.1, 0.5, 0.3, 0.2],
            "smoothed": [0.12, 0.48, 0.32, 0.18],
            "baseline": [0.05, 0.05, 0.05, 0.05],
            "corrected": [0.07, 0.43, 0.27, 0.13],
            "normalized": [0.1, 0.6, 0.4, 0.2],
            "peaks": [{"position": 2920.0, "intensity": 0.6}],
            "diagnostics": {"plot_normalized_primary_axis": True},
        },
    )
    settings = mod.normalize_spectral_plot_settings(
        {
            "show_raw": False,
            "show_corrected": False,
            "show_normalized": False,
            "show_peaks": False,
            "show_smoothed": True,
            "x_range_enabled": True,
            "x_min": 1000,
            "x_max": 4000,
            "y_range_enabled": True,
            "y_min": -1,
            "y_max": 1,
        }
    )
    fig_div = mod._build_figure("proj", "ds", {}, "light", "en", plot_settings=settings)
    graph = next(c for c in fig_div.children if isinstance(c, dcc.Graph))
    names = [tr.name for tr in graph.figure.data]
    assert any("Smoothed" in str(name) for name in names)
    assert not any("Imported" in str(name) for name in names)
    assert not any("Normalized" in str(name) for name in names)
    assert not any(str(name).startswith("Peak") for name in names)
    assert list(graph.figure.layout.xaxis.range) == [4000.0, 1000.0]
    assert list(graph.figure.layout.yaxis.range) == [-1.0, 1.0]


def test_build_figure_sparse_peak_labels_for_dense_clusters(monkeypatch):
    mod = _import_ftir_page()
    import dash_app.api_client as api_client

    peaks = [
        {"position": 1000.0 + idx * 8.0, "intensity": 1.0 - idx * 0.03}
        for idx in range(10)
    ]
    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda *_: {
            "temperature": [900.0, 1000.0, 1100.0, 1200.0],
            "raw_signal": [10.0, 20.0, 15.0, 12.0],
            "smoothed": [0.12, 0.48, 0.32, 0.18],
            "baseline": [0.05, 0.05, 0.05, 0.05],
            "corrected": [0.07, 0.43, 0.27, 0.13],
            "normalized": [],
            "peaks": peaks,
            "diagnostics": {"plot_normalized_primary_axis": False},
        },
    )

    fig_div = mod._build_figure("proj", "ds", {}, "light", "en")
    graph = next(c for c in fig_div.children if isinstance(c, dcc.Graph))
    labels = [trace.text[0] for trace in graph.figure.data if str(trace.name).startswith("Peak") and trace.text[0]]
    assert len(labels) <= 4
    assert graph.figure.layout.yaxis.range[1] < 1.0


def test_render_ftir_plot_settings_chrome_localizes_options_and_placeholders():
    mod = _import_ftir_page()

    chrome = mod.render_ftir_plot_settings_chrome("tr")
    legend_options = chrome[3]

    assert [item["label"] for item in legend_options] == ["Otomatik", "Sağ dışta", "Kompakt", "Gizli"]
    assert chrome[17] == "X minimum"
    assert chrome[18] == "X maksimum"
    assert chrome[20] == "Y minimum"
    assert chrome[21] == "Y maksimum"

    rendered = " ".join(str(item) for item in chrome)
    for unexpected in ("Compact layout", "Show grid", "External Right", "Auto", "Hidden"):
        assert unexpected not in rendered


def test_build_match_table_library_unavailable_is_hidden():
    mod = _import_ftir_page()
    table = mod._build_match_table([], "en", summary={"match_status": "library_unavailable"})
    s = str(table).lower()
    assert "d-none" in s
    assert "match_data_table" not in s
    assert "no match" not in s
