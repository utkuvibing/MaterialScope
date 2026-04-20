"""Tests for the TGA Dash analysis page module."""

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


def _import_tga_page():
    import dash_app.pages.tga as mod

    return mod


def test_tga_page_module_imports():
    mod = _import_tga_page()
    assert hasattr(mod, "layout")
    assert hasattr(mod, "_TGA_TEMPLATE_IDS")
    assert hasattr(mod, "_TGA_ELIGIBLE_TYPES")


def test_layout_contains_section_ids_in_order():
    mod = _import_tga_page()
    layout_str = str(mod.layout)
    expected_ids = [
        "tga-processing-draft",
        "tga-preset-refresh",
        "tga-preset-hydrate",
        "tga-preset-loaded-name",
        "tga-preset-snapshot",
        "tga-preset-select",
        "tga-preset-load-btn",
        "tga-preset-save-btn",
        "tga-preset-saveas-btn",
        "tga-preset-delete-btn",
        "tga-preset-status",
        "tga-smooth-method",
        "tga-step-prominence",
        "tga-step-min-mass",
        "tga-step-half-width",
        "tga-result-analysis-summary",
        "tga-result-metrics",
        "tga-result-quality",
        "tga-result-figure",
        "tga-result-dtg",
        "tga-result-step-cards",
        "tga-result-table",
        "tga-result-processing",
        "tga-result-raw-metadata",
        "tga-literature-compare-btn",
        "tga-literature-max-claims",
        "tga-literature-persist",
        "tga-literature-output",
        "tga-literature-status",
        "tga-figure-captured",
    ]
    for element_id in expected_ids:
        assert element_id in layout_str, f"Missing layout element: {element_id}"

    assert layout_str.index("tga-result-analysis-summary") < layout_str.index("tga-result-metrics")
    assert layout_str.index("tga-result-metrics") < layout_str.index("tga-result-quality")
    assert layout_str.index("tga-result-quality") < layout_str.index("tga-result-figure")
    assert layout_str.index("tga-result-figure") < layout_str.index("tga-result-dtg")
    assert layout_str.index("tga-result-dtg") < layout_str.index("tga-result-step-cards")
    assert layout_str.index("tga-result-raw-metadata") < layout_str.index("tga-literature-compare-btn")
    assert layout_str.index("tga-template-select") < layout_str.index("tga-preset-select")
    assert layout_str.index("tga-preset-select") < layout_str.index("tga-smooth-method")
    assert layout_str.index("tga-smooth-method") < layout_str.index("tga-run-btn")


def test_layout_uses_results_surface_class():
    mod = _import_tga_page()
    assert "dsc-results-surface" in str(mod.layout)


def test_build_tga_quality_card_renders_validation_and_checks():
    mod = _import_tga_page()
    detail = {
        "validation": {
            "status": "warn",
            "warnings": ["Low signal"],
            "issues": [],
            "warning_count": 1,
            "issue_count": 0,
            "checks": {
                "import_review_required": False,
                "tga_unit_inference_basis": "metadata_signal_range",
                "axis_direction": "increasing",
            },
        },
        "processing": {
            "method_context": {
                "calibration_state": "nominal",
                "reference_state": "not_required",
                "reference_name": "NIST SRM",
            }
        },
        "result": {},
    }
    card = mod._build_tga_quality_card(detail, {}, "en")
    text = str(card)
    assert "warn" in text
    assert "Low signal" in text
    assert "import_review_required" in text
    assert "tga_unit_inference_basis" in text
    assert "nominal" in text
    assert "Technical validation" in text
    assert getattr(card, "open", False) is True
    assert "warning" in text.lower()


def test_build_tga_quality_card_collapsed_when_clean():
    mod = _import_tga_page()
    detail = {
        "validation": {
            "status": "ok",
            "warnings": [],
            "issues": [],
            "warning_count": 0,
            "issue_count": 0,
            "checks": {},
        },
        "processing": {"method_context": {}},
        "result": {},
    }
    card = mod._build_tga_quality_card(detail, {}, "en")
    assert getattr(card, "open", True) is False


def test_build_step_cards_truncates_high_step_count():
    mod = _import_tga_page()
    rows = []
    for i in range(8):
        rows.append(
            {
                "onset_temperature": 100.0 + i * 10,
                "midpoint_temperature": 105.0 + i * 10,
                "endset_temperature": 110.0 + i * 10,
                "mass_loss_percent": float(i + 1),
                "residual_percent": 90.0 - i,
            }
        )
    div = mod._build_step_cards(rows, "en")
    s = str(div)
    assert s.count("bi-arrow-down-circle") == 6
    assert "8" in s
    assert "6" in s
    assert "source of truth" in s.lower()


def test_render_tga_literature_output_respects_preview_limit():
    from dash_app.components.literature_compare_ui import render_literature_output

    comparisons = [
        {
            "claim_text": f"Retained claim {i}",
            "provider": "openalex",
            "rationale": f"Note {i}",
            "support_label": "supports",
            "validation_posture": "validating",
        }
        for i in range(4)
    ]
    payload = {
        "literature_claims": [],
        "literature_comparisons": comparisons,
        "citations": [],
        "literature_context": {},
    }
    out = render_literature_output(
        payload,
        "en",
        i18n_prefix="dash.analysis.tga.literature",
        evidence_preview_limit=2,
        alternative_preview_limit=1,
    )
    text = str(out)
    assert "Show 2 more references" in text
    assert "(expand)" in text
    assert "Retained claim 0" in text
    assert "Retained claim 3" in text


def test_render_tga_literature_compacts_generated_claims():
    from dash_app.components.literature_compare_ui import render_literature_output

    claims = [{"claim_text": f"Claim line {i}"} for i in range(5)]
    payload = {
        "literature_claims": claims,
        "literature_comparisons": [],
        "citations": [],
        "literature_context": {},
    }
    out = render_literature_output(
        payload,
        "en",
        i18n_prefix="dash.analysis.tga.literature",
        evidence_preview_limit=2,
    )
    text = str(out)
    assert "Model-generated bullets" in text
    assert "Show 3 more claims" in text
    assert "Claim line 0" in text
    assert "Claim line 4" in text


def test_tga_validation_metric_value_formats_status():
    mod = _import_tga_page()
    detail_ok = {"validation": {"status": "ok", "warnings": [], "issues": [], "warning_count": 0, "issue_count": 0}}
    assert mod._tga_validation_metric_value(detail_ok, {}, "en") == "OK"
    detail_warn = {
        "validation": {
            "status": "warn",
            "warnings": ["x"],
            "issues": [],
            "warning_count": 2,
            "issue_count": 0,
        }
    }
    v = mod._tga_validation_metric_value(detail_warn, {}, "en")
    assert "warn" in v
    assert "2" in v


def test_build_tga_raw_metadata_panel_splits_user_and_technical():
    mod = _import_tga_page()
    metadata = {
        "sample_name": "Demo",
        "heating_rate": 10,
        "internal_vendor_blob": {"x": 1},
    }
    panel = mod._build_tga_raw_metadata_panel(metadata, "en")
    s = str(panel)
    assert "sample_name" in s
    assert "internal_vendor_blob" in s
    assert "Technical details" in s or "Teknik detaylar" in s


def test_build_tga_dtg_panel_renders_graph(monkeypatch):
    mod = _import_tga_page()
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
    panel = mod._build_tga_dtg_panel("proj", "ds", "light", "en", locale_data="en")
    assert "dsc-derivative-helper" in str(getattr(panel, "className", "") or "")
    assert isinstance(panel.children[2], dcc.Graph)


def test_build_tga_dtg_panel_hidden_without_dtg(monkeypatch):
    mod = _import_tga_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _p, _t, _k: {"temperature": [1.0], "dtg": [], "has_dtg": False},
    )
    panel = mod._build_tga_dtg_panel("proj", "ds", "light", "en", locale_data="en")
    assert isinstance(panel, html.Div)
    assert not panel.children


def test_extract_graph_from_wrapped_tga_figure_area(monkeypatch):
    from dash_app.components.analysis_page import _extract_graph_figure_payload

    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _p, _t, _k: {
            "temperature": [0.0, 1.0, 2.0],
            "raw_signal": [100.0, 99.0, 98.0],
            "smoothed": [],
            "has_smoothed": False,
        },
    )
    mod = _import_tga_page()
    summary = {"step_count": 3, "total_mass_loss_percent": 12.5, "residue_percent": 40.0}
    fig = mod._build_figure("p", "k", summary, [], "light", "en")
    payload = _extract_graph_figure_payload(fig)
    assert payload is not None
    assert "Steps:" in str(fig) or "Adımlar:" in str(fig)


def test_tga_processing_draft_defaults_and_overrides():
    mod = _import_tga_page()
    d0 = mod._default_tga_processing_draft()
    assert d0["smoothing"]["method"] == "savgol"
    assert d0["step_detection"]["search_half_width"] == 80
    ov = mod._tga_overrides_from_draft(d0)
    assert set(ov.keys()) == {"smoothing", "step_detection"}
    assert ov["smoothing"]["window_length"] == 11


def test_tga_draft_from_loaded_processing_nested_and_unit():
    mod = _import_tga_page()
    processing = {
        "signal_pipeline": {"smoothing": {"method": "moving_average", "window_length": 9}},
        "analysis_steps": {"step_detection": {"prominence": 0.02, "min_mass_loss": 0.4, "search_half_width": 60}},
        "method_context": {"tga_unit_mode_declared": "percent"},
    }
    draft, unit = mod._tga_draft_and_unit_from_loaded_processing(processing)
    assert unit == "percent"
    assert draft["smoothing"]["method"] == "moving_average"
    assert draft["step_detection"]["min_mass_loss"] == 0.4
    assert draft["step_detection"]["prominence"] == 0.02


def test_tga_preset_processing_body_for_save_includes_method_context():
    mod = _import_tga_page()
    draft = mod._normalize_tga_processing_draft(
        {
            "smoothing": {"method": "savgol", "window_length": 15, "polyorder": 3},
            "step_detection": {"min_mass_loss": 0.6, "search_half_width": 90},
        }
    )
    body = mod._tga_preset_processing_body_for_save(draft, "absolute_mass")
    assert body["method_context"]["tga_unit_mode_declared"] == "absolute_mass"
    assert body["smoothing"]["window_length"] == 15
    assert body["step_detection"]["search_half_width"] == 90


def test_tga_snapshots_equal_for_dirty_tracking():
    mod = _import_tga_page()
    d = mod._default_tga_processing_draft()
    a = mod._tga_ui_snapshot_dict("tga.general", "auto", d)
    b = mod._tga_ui_snapshot_dict("tga.general", "auto", d)
    assert mod._tga_snapshots_equal(a, b)
    c = mod._tga_ui_snapshot_dict("tga.multi_step_decomposition", "auto", d)
    assert not mod._tga_snapshots_equal(a, c)


def test_tga_controls_to_draft_normalizes_window_and_prominence():
    mod = _import_tga_page()
    d = mod._tga_draft_from_control_values("savgol", 10, 3, 2.0, "", 0.5, 80)
    assert d["smoothing"]["window_length"] % 2 == 1
    assert d["step_detection"]["prominence"] is None
    d2 = mod._tga_draft_from_control_values("savgol", 11, 3, 2.0, "0.05", 0.5, 80)
    assert d2["step_detection"]["prominence"] == 0.05


def test_run_tga_analysis_forwards_processing_overrides(monkeypatch):
    mod = _import_tga_page()
    captured: dict = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"execution_status": "failed", "detail": "noop"}

    monkeypatch.setattr("dash_app.api_client.analysis_run", fake_run)
    mod.run_tga_analysis(
        1,
        "proj-1",
        "ds-1",
        "tga.general",
        "auto",
        {"smoothing": {"method": "savgol", "window_length": 21, "polyorder": 3}, "step_detection": mod._default_tga_processing_draft()["step_detection"]},
        0,
        0,
        "en",
    )
    assert captured.get("processing_overrides") is not None
    assert captured["processing_overrides"]["smoothing"]["window_length"] == 21
