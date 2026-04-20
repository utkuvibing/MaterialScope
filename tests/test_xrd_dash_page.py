"""Tests for the XRD Dash analysis page module."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import dash_bootstrap_components as dbc
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


def _import_xrd_page():
    import dash_app.pages.xrd as mod

    return mod


def test_xrd_page_module_imports():
    mod = _import_xrd_page()
    assert hasattr(mod, "layout")
    assert hasattr(mod, "_XRD_WORKFLOW_TEMPLATES")
    assert hasattr(mod, "_XRD_ELIGIBLE_TYPES")


def test_xrd_page_is_registered():
    import dash

    _import_xrd_page()
    pages = dash.page_registry
    xrd_pages = {key: value for key, value in pages.items() if "xrd" in key.lower()}
    assert len(xrd_pages) >= 1, "XRD page not found in dash.page_registry"


def test_xrd_workflow_templates_have_expected_ids():
    mod = _import_xrd_page()

    ids = {t["id"] for t in mod._XRD_WORKFLOW_TEMPLATES}
    assert "xrd.general" in ids
    assert "xrd.phase_screening" in ids
    assert len(mod._TEMPLATE_OPTIONS) == len(mod._XRD_WORKFLOW_TEMPLATES)


def test_xrd_eligible_types():
    mod = _import_xrd_page()
    assert "XRD" in mod._XRD_ELIGIBLE_TYPES
    assert "UNKNOWN" in mod._XRD_ELIGIBLE_TYPES


def test_layout_contains_key_div_ids():
    mod = _import_xrd_page()
    layout_str = str(mod.layout)

    expected_ids = [
        "xrd-dataset-selector-area",
        "xrd-template-select",
        "xrd-run-btn",
        "xrd-result-metrics",
        "xrd-result-figure",
        "xrd-result-candidate-cards",
        "xrd-result-table",
        "xrd-result-processing",
        "xrd-literature-compare-btn",
        "xrd-literature-max-claims",
        "xrd-literature-persist",
        "xrd-literature-output",
        "xrd-literature-status",
        "xrd-refresh",
        "xrd-latest-result-id",
        "xrd-figure-captured",
    ]
    for div_id in expected_ids:
        assert div_id in layout_str, f"Missing layout element: {div_id}"


def test_layout_places_figure_before_candidate_cards():
    mod = _import_xrd_page()
    layout_str = str(mod.layout)
    assert layout_str.index("xrd-result-figure") < layout_str.index("xrd-result-candidate-cards")


def test_layout_places_literature_compare_after_processing():
    mod = _import_xrd_page()
    layout_str = str(mod.layout)
    assert layout_str.index("xrd-result-processing") < layout_str.index("xrd-literature-compare-btn")


def test_match_card_renders_candidate_and_score():
    mod = _import_xrd_page()
    card = mod._match_card(
        {
            "display_name_unicode": "alpha-Al2O3",
            "normalized_score": 0.8123,
            "confidence_band": "moderate_confidence",
            "formula_unicode": "Al2O3",
            "library_provider": "COD",
            "evidence": {
                "shared_peak_count": 6,
                "weighted_overlap_score": 0.73,
                "coverage_ratio": 0.78,
                "mean_delta_position": 0.02,
            },
        },
        0,
    )
    assert isinstance(card, dbc.Card)
    card_html = str(card)
    assert "Candidate 1" in card_html
    assert "alpha-Al2O3" in card_html
    assert "0.8123" in card_html


def test_build_match_cards_empty():
    mod = _import_xrd_page()
    result = mod._build_match_cards([], {})
    assert isinstance(result, html.Div)
    assert "No candidate matches were returned." in str(result)


def test_build_match_cards_with_caution():
    mod = _import_xrd_page()
    result = mod._build_match_cards(
        [
            {
                "candidate_name": "Quartz",
                "normalized_score": 0.62,
                "confidence_band": "low_confidence",
                "evidence": {"shared_peak_count": 3},
            }
        ],
        {"caution_message": "Screening only.", "top_candidate_name": "Quartz"},
    )
    html_str = str(result)
    assert "Screening only." in html_str
    assert "Top candidate: Quartz" in html_str


def test_build_figure_uses_corrected_as_primary_trace(monkeypatch):
    mod = _import_xrd_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _project_id, _analysis_type, _dataset_key: {
            "temperature": [10.0, 20.0, 30.0, 40.0],
            "raw_signal": [20.0, 50.0, 35.0, 15.0],
            "smoothed": [21.0, 48.0, 34.0, 16.0],
            "baseline": [4.0, 4.0, 4.0, 4.0],
            "corrected": [17.0, 44.0, 30.0, 12.0],
        },
    )

    graph = mod._build_figure(
        "proj-1",
        "dataset-1",
        {"sample_name": "XRD Run A"},
        {"method_context": {"xrd_axis_role": "two_theta"}},
        "light",
    )

    assert isinstance(graph, dcc.Graph)
    corrected_trace = next(trace for trace in graph.figure.data if trace.name == "Corrected Diffractogram")
    raw_trace = next(trace for trace in graph.figure.data if trace.name == "Raw Diffractogram")
    assert corrected_trace.line.width == 3.0
    assert raw_trace.opacity < 0.4
    assert graph.figure.layout.xaxis.title.text == "2theta (deg)"


def test_build_figure_handles_missing_primary_signal(monkeypatch):
    mod = _import_xrd_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _project_id, _analysis_type, _dataset_key: {
            "temperature": [10.0, 20.0, 30.0],
            "raw_signal": [1.0, 2.0],
            "smoothed": [],
            "baseline": [0.2, 0.2, 0.2],
            "corrected": [],
        },
    )

    result = mod._build_figure(
        "proj-1",
        "dataset-1",
        {"sample_name": "XRD Run B"},
        {"method_context": {"xrd_axis_role": "two_theta"}},
        "light",
    )

    assert isinstance(result, html.P)
    assert "No processed XRD signal is available" in str(result)


def test_build_match_table_empty():
    mod = _import_xrd_page()
    result = mod._build_match_table([])
    assert "No match data." in str(result)


def test_xrd_dash_page_import_and_run_via_server():
    """Smoke test: import XRD data and run analysis through the combined server."""
    import base64

    from fastapi.testclient import TestClient

    from dash_app.sample_data import resolve_sample_request
    from dash_app.server import create_combined_app

    app = create_combined_app()
    client = TestClient(app)

    workspace = client.post("/workspace/new")
    assert workspace.status_code == 200
    project_id = workspace.json()["project_id"]

    sample_path, sample_type = resolve_sample_request("load-sample-xrd")
    assert sample_path is not None
    assert sample_type == "XRD"

    payload = base64.b64encode(sample_path.read_bytes()).decode("ascii")
    imported = client.post(
        "/dataset/import",
        json={
            "project_id": project_id,
            "file_name": sample_path.name,
            "file_base64": payload,
            "data_type": "XRD",
        },
    )
    assert imported.status_code == 200
    dataset_key = imported.json()["dataset"]["key"]
    assert imported.json()["dataset"]["data_type"] == "XRD"

    run_response = client.post(
        "/analysis/run",
        json={
            "project_id": project_id,
            "dataset_key": dataset_key,
            "analysis_type": "XRD",
            "workflow_template_id": "xrd.general",
        },
    )
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["execution_status"] == "saved"
    assert run_payload["result_id"].startswith("xrd_")

    detail_response = client.get(f"/workspace/{project_id}/results/{run_payload['result_id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["processing"]["workflow_template_id"] == "xrd.general"
    assert "candidate_count" in detail["summary"]

    curves_response = client.get(f"/workspace/{project_id}/analysis-state/XRD/{dataset_key}")
    assert curves_response.status_code == 200
    curves = curves_response.json()
    assert "temperature" in curves
    assert "raw_signal" in curves
    assert len(curves["temperature"]) > 0
