"""Tests for the RAMAN Dash analysis page module."""

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


def _import_raman_page():
    import dash_app.pages.raman as mod
    return mod


def test_raman_page_module_imports():
    mod = _import_raman_page()
    assert hasattr(mod, "layout")
    assert hasattr(mod, "_RAMAN_TEMPLATE_IDS")
    assert hasattr(mod, "_RAMAN_ELIGIBLE_TYPES")
    assert hasattr(mod, "_RAMAN_WORKFLOW_TEMPLATES")


def test_raman_workflow_templates_have_expected_ids():
    mod = _import_raman_page()
    ids = {item["id"] for item in mod._RAMAN_WORKFLOW_TEMPLATES}
    assert ids == {"raman.general", "raman.polymorph_screening"}
    assert len(mod._TEMPLATE_OPTIONS) == len(mod._RAMAN_WORKFLOW_TEMPLATES)


def test_layout_contains_section_ids_in_order():
    mod = _import_raman_page()
    layout_str = str(mod.layout)
    expected_ids = [
        "raman-left-tabs",
        "raman-tab-setup-shell",
        "raman-tab-processing-shell",
        "raman-tab-run-shell",
        "raman-processing-default",
        "raman-processing-draft",
        "raman-processing-undo-stack",
        "raman-processing-redo-stack",
        "raman-history-hydrate",
        "raman-preset-refresh",
        "raman-preset-hydrate",
        "raman-preset-loaded-name",
        "raman-preset-snapshot",
        "raman-workflow-guide-title",
        "raman-processing-undo-btn",
        "raman-processing-redo-btn",
        "raman-processing-reset-btn",
        "raman-preset-select",
        "raman-preset-load-btn",
        "raman-preset-save-btn",
        "raman-preset-saveas-btn",
        "raman-preset-delete-btn",
        "raman-preset-status",
        "raman-smoothing-card-title",
        "raman-baseline-card-title",
        "raman-normalization-card-title",
        "raman-peak-card-title",
        "raman-similarity-card-title",
        "raman-smooth-method",
        "raman-baseline-method",
        "raman-norm-method",
        "raman-peak-prominence",
        "raman-peak-distance",
        "raman-peak-max-peaks",
        "raman-sim-top-n",
        "raman-sim-minimum-score",
        "raman-result-analysis-summary",
        "raman-result-metrics",
        "raman-result-quality",
        "raman-result-figure",
        "raman-result-top-match",
        "raman-result-peak-cards",
        "raman-result-match-table",
        "raman-result-processing",
        "raman-result-raw-metadata",
        "raman-literature-compare-btn",
        "raman-literature-max-claims",
        "raman-literature-persist",
        "raman-literature-output",
        "raman-literature-status",
        "raman-figure-captured",
    ]
    for element_id in expected_ids:
        assert element_id in layout_str, f"Missing layout element: {element_id}"

    assert layout_str.index("raman-result-analysis-summary") < layout_str.index("raman-result-metrics")
    assert layout_str.index("raman-result-metrics") < layout_str.index("raman-result-quality")
    assert layout_str.index("raman-result-quality") < layout_str.index("raman-result-figure")
    assert layout_str.index("raman-result-figure") < layout_str.index("raman-result-top-match")
    assert layout_str.index("raman-result-top-match") < layout_str.index("raman-result-peak-cards")
    assert layout_str.index("raman-result-peak-cards") < layout_str.index("raman-result-match-table")
    assert layout_str.index("raman-result-match-table") < layout_str.index("raman-result-processing")
    assert layout_str.index("raman-result-processing") < layout_str.index("raman-result-raw-metadata")
    assert layout_str.index("raman-result-raw-metadata") < layout_str.index("raman-literature-compare-btn")
    assert layout_str.index("raman-left-tabs") < layout_str.index("raman-result-analysis-summary")
    assert layout_str.index("raman-tab-setup-shell") < layout_str.index("raman-tab-processing-shell")
    assert layout_str.index("raman-tab-processing-shell") < layout_str.index("raman-tab-run-shell")


def test_layout_uses_results_surface_class():
    mod = _import_raman_page()
    assert "dsc-results-surface" in str(mod.layout)


def test_default_processing_draft_has_all_sections():
    mod = _import_raman_page()
    defaults = mod._default_raman_processing_draft()
    assert set(defaults.keys()) == {"smoothing", "baseline", "normalization", "peak_detection", "similarity_matching"}
    assert defaults["smoothing"]["method"] == "savgol"
    assert defaults["baseline"]["method"] == "asls"
    assert defaults["normalization"]["method"] == "vector"
    assert defaults["peak_detection"]["prominence"] == 0.035
    assert defaults["similarity_matching"]["top_n"] == 3


def test_normalize_peak_detection_values_sanitizes_inputs():
    mod = _import_raman_page()
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
    mod = _import_raman_page()
    base = mod._normalize_baseline_values("asls", 1e6, 0.01, False, 10, 200)
    assert base["region"] is None

    restricted = mod._normalize_baseline_values("asls", 1e6, 0.01, True, 400.0, 1800.0)
    assert restricted["region"] == [400.0, 1800.0]


def test_normalize_normalization_values_defaults():
    mod = _import_raman_page()
    assert mod._normalize_normalization_values("vector") == {"method": "vector"}
    assert mod._normalize_normalization_values("max") == {"method": "max"}
    assert mod._normalize_normalization_values("snv") == {"method": "snv"}
    assert mod._normalize_normalization_values("nonsense") == {"method": "vector"}


def test_normalize_similarity_matching_values():
    mod = _import_raman_page()
    assert mod._normalize_similarity_matching_values(5, 0.6) == {"top_n": 5, "minimum_score": 0.6}


def test_undo_redo_reset_cycle_for_processing_draft():
    mod = _import_raman_page()
    defaults = mod._default_raman_processing_draft()
    edited = {
        **defaults,
        "smoothing": {"method": "gaussian", "sigma": 3.4},
    }
    from dash_app.components.raman_explore import append_undo_after_edit, perform_undo, perform_redo

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


def test_raman_overrides_from_draft_includes_all_sections():
    mod = _import_raman_page()
    draft = {
        "smoothing": {"method": "savgol", "window_length": 15, "polyorder": 3},
        "baseline": {"method": "asls", "lam": 1e5, "p": 0.02, "region": [400.0, 1800.0]},
        "normalization": {"method": "snv"},
        "peak_detection": {"prominence": 0.08, "distance": 8, "max_peaks": 12},
        "similarity_matching": {"top_n": 5, "minimum_score": 0.6},
    }
    overrides = mod._raman_overrides_from_draft(draft)
    assert set(overrides.keys()) == {"smoothing", "baseline", "normalization", "peak_detection", "similarity_matching"}
    assert overrides["baseline"]["region"] == [400.0, 1800.0]


def test_raman_draft_from_loaded_processing_nested():
    mod = _import_raman_page()
    processing = {
        "signal_pipeline": {"smoothing": {"method": "moving_average", "window_length": 9}},
        "analysis_steps": {"peak_detection": {"prominence": 0.08, "distance": 6, "max_peaks": 8}},
    }
    draft = mod._raman_draft_from_loaded_processing(processing)
    assert draft["smoothing"]["method"] == "moving_average"
    assert draft["peak_detection"]["prominence"] == 0.08


def test_raman_preset_processing_body_for_save_includes_all_sections():
    mod = _import_raman_page()
    draft = mod._normalize_raman_processing_draft({
        "smoothing": {"method": "savgol", "window_length": 15, "polyorder": 3},
        "peak_detection": {"prominence": 0.1, "distance": 10, "max_peaks": 20},
    })
    body = mod._raman_preset_processing_body_for_save(draft)
    assert set(body.keys()) == {"smoothing", "baseline", "normalization", "peak_detection", "similarity_matching"}
    assert body["smoothing"]["window_length"] == 15


def test_raman_snapshots_equal_for_dirty_tracking():
    mod = _import_raman_page()
    d = mod._default_raman_processing_draft()
    a = mod._raman_ui_snapshot_dict("raman.general", d)
    b = mod._raman_ui_snapshot_dict("raman.general", d)
    assert mod._raman_snapshots_equal(a, b)
    c = mod._raman_ui_snapshot_dict("raman.polymorph_screening", d)
    assert not mod._raman_snapshots_equal(a, c)


def test_raman_controls_to_draft_normalizes_window_and_prominence():
    mod = _import_raman_page()
    d = mod._raman_draft_from_control_values(
        "savgol", 10, 3, 2.0,
        "asls", 1e6, 0.01, False, None, None,
        "vector",
        0.0, 1, 1,
        3, 0.45,
    )
    assert d["smoothing"]["window_length"] % 2 == 1
    assert d["peak_detection"]["prominence"] == 0.0


def test_run_raman_analysis_forwards_processing_overrides(monkeypatch):
    mod = _import_raman_page()
    captured: dict = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"execution_status": "failed", "detail": "noop"}

    monkeypatch.setattr("dash_app.api_client.analysis_run", fake_run)
    mod.run_raman_analysis(
        1,
        "proj-1",
        "ds-1",
        "raman.general",
        {"smoothing": {"method": "savgol", "window_length": 21, "polyorder": 3}, "peak_detection": mod._default_raman_processing_draft()["peak_detection"]},
        0,
        0,
        "en",
    )
    assert captured.get("processing_overrides") is not None
    assert captured["processing_overrides"]["smoothing"]["window_length"] == 21


def test_build_raman_quality_card_renders_validation_and_checks():
    mod = _import_raman_page()
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
    card = mod._build_raman_quality_card(detail, {}, "en")
    text = str(card)
    assert "warn" in text
    assert "Low signal" in text
    assert getattr(card, "open", False) is True


def test_build_raman_quality_card_collapsed_when_clean():
    mod = _import_raman_page()
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
    card = mod._build_raman_quality_card(detail, {}, "en")
    assert getattr(card, "open", True) is False


def test_build_raman_quality_card_warning_count_matches_warning_list():
    mod = _import_raman_page()
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
    card = mod._build_raman_quality_card(detail, {}, "en")
    text = str(card).lower()
    assert "10 warnings" in text
    assert "11 warnings" not in text


def test_build_raman_analysis_summary_shows_instrument_and_vendor():
    mod = _import_raman_page()
    dataset_detail = {
        "metadata": {"instrument": "Bruker Alpha", "vendor": "Bruker", "file_name": "x.csv"},
        "dataset": {"display_name": "Demo"},
    }
    out = mod._build_raman_analysis_summary(dataset_detail, {}, {}, "en", locale_data="en")
    s = str(out)
    assert "Bruker Alpha" in s
    assert "Bruker" in s


def test_build_raman_raw_metadata_panel_splits_user_and_technical():
    mod = _import_raman_page()
    metadata = {
        "sample_name": "Demo",
        "instrument": "Bruker",
        "internal_vendor_blob": {"x": 1},
    }
    panel = mod._build_raman_raw_metadata_panel(metadata, "en")
    s = str(panel)
    assert "sample_name" in s
    assert "internal_vendor_blob" in s
    assert "Technical details" in s or "Teknik detaylar" in s


def test_build_top_match_panel_library_unavailable_is_configuration_message():
    mod = _import_raman_page()
    panel = mod._build_top_match_panel({"match_status": "library_unavailable"}, [], "en")
    s = str(panel).lower()
    assert "reference library" in s
    assert "alert" in s


def test_build_top_match_panel_renders_hero_summary():
    mod = _import_raman_page()
    rows = [
        {
            "candidate_name": "Polyethylene",
            "normalized_score": 0.92,
            "confidence_band": "high_confidence",
            "library_provider": "OpenSpecy",
            "library_package": "openspecy_raman_core",
            "evidence": {"shared_peak_count": 5, "observed_peak_count": 6},
        }
    ]
    panel = mod._build_top_match_panel({"top_match_name": "Polyethylene"}, rows, "en")
    s = str(panel)
    assert "Polyethylene" in s
    assert "0.92" in s
    assert "5/6" in s


def test_build_peak_cards_from_curves_renders_cards(monkeypatch):
    mod = _import_raman_page()
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
    mod = _import_raman_page()
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
    mod = _import_raman_page()
    rows = [
        {"rank": 1, "candidate_id": "c1", "candidate_name": "A", "normalized_score": 0.9, "confidence_band": "high", "library_provider": "p", "library_package": "pkg"},
    ]
    table = mod._build_match_table(rows, "en")
    s = str(table)
    assert "candidate_name" in s
    assert "normalized_score" in s


def test_build_figure_returns_graph_when_curves_present(monkeypatch):
    mod = _import_raman_page()
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


def test_build_figure_no_data_when_empty_curves(monkeypatch):
    mod = _import_raman_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _p, _t, _k: {"temperature": []},
    )
    fig = mod._build_figure("proj", "ds", {}, "light", "en")
    assert isinstance(fig, html.P)


def test_raman_layout_excludes_raw_quality_section():
    mod = _import_raman_page()
    layout_str = str(mod.layout)
    assert "raman-raw-quality-panel" not in layout_str
    assert "raman-raw-quality-card-title" not in layout_str


def test_render_raman_literature_uses_raman_prefix():
    mod = _import_raman_page()
    outputs = mod.render_raman_literature_chrome("en", "raman_result_1")
    assert any("Literature Compare" in str(o) for o in outputs)
    assert mod._RAMAN_LITERATURE_PREFIX == "dash.analysis.raman.literature"


def test_capture_raman_figure_delegates_to_shared_helper(monkeypatch):
    mod = _import_raman_page()
    captured_kwargs: dict = {}

    def _fake_capture(**kwargs):
        captured_kwargs.update(kwargs)
        return {"raman_r_2": {"status": "ok"}}

    monkeypatch.setattr(mod, "capture_result_figure_from_layout", _fake_capture)
    result = mod.capture_raman_figure("raman_r_2", "proj-1", {"graph": True}, {"old": "state"})
    assert result == {"raman_r_2": {"status": "ok"}}
    assert captured_kwargs == {
        "result_id": "raman_r_2",
        "project_id": "proj-1",
        "figure_children": {"graph": True},
        "captured": {"old": "state"},
        "analysis_type": "RAMAN",
    }


def test_toggle_raman_smoothing_inputs_disables_correct_fields():
    mod = _import_raman_page()
    assert mod.toggle_raman_smoothing_inputs("savgol") == (False, False, True)
    assert mod.toggle_raman_smoothing_inputs("moving_average") == (False, True, True)
    assert mod.toggle_raman_smoothing_inputs("gaussian") == (True, True, False)


def test_toggle_raman_baseline_inputs_disables_correct_fields():
    mod = _import_raman_page()
    assert mod.toggle_raman_baseline_inputs("asls") == (False, False)
    assert mod.toggle_raman_baseline_inputs("linear") == (True, True)


def test_toggle_raman_baseline_region_inputs():
    mod = _import_raman_page()
    assert mod.toggle_raman_baseline_region_inputs(True) == (False, False)
    assert mod.toggle_raman_baseline_region_inputs(False) == (True, True)


def test_display_result_returns_nine_outputs(monkeypatch):
    mod = _import_raman_page()
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
                "workflow_template_label": "General RAMAN",
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
                    "library_package": "openspecy_raman_core",
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

    outputs = mod.display_result("raman_sample_a", 1, "light", "en", "proj-1")
    assert len(outputs) == 9
    for item in outputs:
        assert item is not None


def test_literature_compare_uses_raman_prefix(monkeypatch):
    mod = _import_raman_page()
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
    output, status = mod.compare_raman_literature(1, "proj", "raman_r1", 3, ["persist"], "en")
    assert output is not None
    assert status is not None


def test_preset_dirty_flag_renders_clean_when_snapshot_matches():
    mod = _import_raman_page()
    draft = mod._default_raman_processing_draft()
    snap = mod._raman_ui_snapshot_dict("raman.general", draft)
    flag = mod.render_raman_preset_dirty_flag(
        "en", "raman.general",
        "savgol", 11, 3, 2.0,
        "asls", 1e6, 0.01, False, None, None,
        "vector",
        0.035, 5, 12,
        3, 0.45,
        snap,
    )
    assert "text-success" in str(flag)


def test_preset_dirty_flag_renders_dirty_when_snapshot_differs():
    mod = _import_raman_page()
    draft = mod._default_raman_processing_draft()
    snap = mod._raman_ui_snapshot_dict("raman.general", draft)
    flag = mod.render_raman_preset_dirty_flag(
        "en", "raman.general",
        "gaussian", 11, 3, 2.0,
        "asls", 1e6, 0.01, False, None, None,
        "vector",
        0.035, 5, 12,
        3, 0.45,
        snap,
    )
    assert "text-warning" in str(flag)


def test_build_figure_shows_diagnostics_when_present(monkeypatch):
    mod = _import_raman_page()
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


def test_raman_literature_technical_collapsible_no_raw_key_leak():
    from dash_app.components.literature_compare_ui import render_literature_output

    payload = {
        "literature_claims": [],
        "literature_comparisons": [],
        "citations": [],
        "literature_context": {"provider_query_status": "ok", "query_text": "RAMAN binder example query"},
    }
    tree = render_literature_output(
        payload,
        "en",
        i18n_prefix="dash.analysis.raman.literature",
        evidence_preview_limit=2,
        alternative_preview_limit=1,
    )
    html_s = str(tree)
    assert "dash.analysis.raman.literature.technical_details_title" not in html_s
    assert "Technical search details" in html_s


def test_build_figure_omits_normalized_when_backend_flags_shared_axis_unhelpful(monkeypatch):
    mod = _import_raman_page()
    import dash_app.api_client as api_client
    from utils.i18n import translate_ui

    legend_norm = translate_ui("en", "dash.analysis.raman.legend_normalized_spectrum")

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


def test_build_match_table_library_unavailable_is_hidden():
    mod = _import_raman_page()
    table = mod._build_match_table([], "en", summary={"match_status": "library_unavailable"})
    s = str(table).lower()
    assert "d-none" in s
    assert "match_data_table" not in s
    assert "no match" not in s

