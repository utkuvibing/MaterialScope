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
    fig = mod._build_figure("p", "k", {}, [], "light", "en")
    payload = _extract_graph_figure_payload(fig)
    assert payload is not None
