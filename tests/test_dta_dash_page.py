"""Tests for the DTA Dash analysis page module."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# Ensure project root is importable
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import dash_bootstrap_components as dbc
from dash import dcc, html


# ---------------------------------------------------------------------------
# Fixture: ensure a Dash app exists before page module import
# ---------------------------------------------------------------------------

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


def _import_dta_page():
    """Import (or reimport) the DTA page module."""
    import dash_app.pages.dta as mod
    return mod


# ---------------------------------------------------------------------------
# Module import
# ---------------------------------------------------------------------------

def test_dta_page_module_imports():
    """DTA page module should import without errors."""
    mod = _import_dta_page()
    assert hasattr(mod, "layout")
    assert hasattr(mod, "_DTA_WORKFLOW_TEMPLATES")
    assert hasattr(mod, "_DTA_ELIGIBLE_TYPES")


def test_dta_page_is_registered():
    """DTA page should be a registered Dash page."""
    import dash
    _import_dta_page()
    pages = dash.page_registry
    dta_pages = {k: v for k, v in pages.items() if "dta" in k.lower()}
    assert len(dta_pages) >= 1, "DTA page not found in dash.page_registry"


# ---------------------------------------------------------------------------
# Workflow templates
# ---------------------------------------------------------------------------

def test_dta_workflow_templates_have_expected_ids():
    mod = _import_dta_page()

    ids = {t["id"] for t in mod._DTA_WORKFLOW_TEMPLATES}
    assert "dta.general" in ids
    assert "dta.thermal_events" in ids
    assert len(mod._TEMPLATE_OPTIONS) == len(mod._DTA_WORKFLOW_TEMPLATES)
    for opt in mod._TEMPLATE_OPTIONS:
        assert "label" in opt
        assert "value" in opt


def test_dta_eligible_types():
    mod = _import_dta_page()
    assert "DTA" in mod._DTA_ELIGIBLE_TYPES
    assert "UNKNOWN" in mod._DTA_ELIGIBLE_TYPES


# ---------------------------------------------------------------------------
# Layout structure
# ---------------------------------------------------------------------------

def test_layout_contains_key_div_ids():
    mod = _import_dta_page()
    layout = mod.layout

    layout_str = str(layout)
    expected_ids = [
        "dta-dataset-selector-area",
        "dta-template-select",
        "dta-run-btn",
        "dta-result-metrics",
        "dta-result-peak-cards",
        "dta-result-figure",
        "dta-result-table",
        "dta-result-processing",
        "dta-refresh",
        "dta-latest-result-id",
    ]
    for div_id in expected_ids:
        assert div_id in layout_str, f"Missing layout element: {div_id}"


def test_layout_places_figure_before_peak_cards():
    mod = _import_dta_page()
    layout_str = str(mod.layout)
    assert layout_str.index("dta-result-figure") < layout_str.index("dta-result-peak-cards")


# ---------------------------------------------------------------------------
# Peak card rendering
# ---------------------------------------------------------------------------

def test_peak_card_renders_exothermic():
    mod = _import_dta_page()

    row = {
        "direction": "exo",
        "peak_temperature": 250.0,
        "onset_temperature": 240.0,
        "endset_temperature": 260.0,
        "area": 1.234,
        "fwhm": 15.0,
        "height": 0.5,
    }
    card = mod._peak_card(row, 0)
    assert isinstance(card, dbc.Card)
    card_html = str(card)
    assert "Exo" in card_html
    assert "250.0" in card_html


def test_peak_card_renders_endothermic():
    mod = _import_dta_page()

    row = {
        "direction": "endo",
        "peak_temperature": 180.0,
        "onset_temperature": 170.0,
        "endset_temperature": 190.0,
        "area": 0.8,
        "fwhm": 12.0,
        "height": 0.3,
    }
    card = mod._peak_card(row, 1)
    card_html = str(card)
    assert "Endo" in card_html
    assert "180.0" in card_html


def test_peak_card_handles_missing_fields():
    mod = _import_dta_page()

    row = {"peak_temperature": 200.0}
    card = mod._peak_card(row, 0)
    assert isinstance(card, dbc.Card)
    card_html = str(card)
    assert "200.0" in card_html
    assert "--" in card_html


# ---------------------------------------------------------------------------
# Build helpers
# ---------------------------------------------------------------------------

def test_build_peak_cards_empty():
    mod = _import_dta_page()

    result = mod._build_peak_cards([])
    assert isinstance(result, html.Div)
    result_html = str(result)
    assert "No thermal events detected" in result_html


def test_build_peak_cards_with_data():
    mod = _import_dta_page()

    rows = [
        {"direction": "exo", "peak_temperature": 250.0, "onset_temperature": 240.0,
         "endset_temperature": 260.0, "area": 1.0, "fwhm": 15.0, "height": 0.5},
        {"direction": "endo", "peak_temperature": 180.0, "onset_temperature": 170.0,
         "endset_temperature": 190.0, "area": 0.8, "fwhm": 12.0, "height": 0.3},
    ]
    result = mod._build_peak_cards(rows)
    result_html = str(result)
    assert "Peak 1" in result_html
    assert "Peak 2" in result_html
    assert "Exo" in result_html
    assert "Endo" in result_html


def test_build_peak_cards_compacts_secondary_events():
    mod = _import_dta_page()

    rows = [
        {
            "direction": "exo" if idx % 2 == 0 else "endo",
            "peak_temperature": 120.0 + idx * 15.0,
            "onset_temperature": 115.0 + idx * 15.0,
            "endset_temperature": 125.0 + idx * 15.0,
            "area": float(10 - idx),
            "height": float(5 - idx * 0.2),
        }
        for idx in range(6)
    ]
    result = mod._build_peak_cards(rows)
    result_html = str(result)
    assert result_html.count("Peak ") == 4
    assert "Show 2 additional event(s)" in result_html


def test_derive_event_metrics_falls_back_to_rows_when_summary_counts_missing():
    mod = _import_dta_page()

    peak_count, exo_count, endo_count = mod._derive_event_metrics(
        {"peak_count": 3},
        [
            {"peak_type": "exo"},
            {"peak_type": "endotherm"},
            {"direction": "exo"},
        ],
    )

    assert peak_count == 3
    assert exo_count == 2
    assert endo_count == 1


def test_derive_event_metrics_prefers_rows_over_stale_summary_counts():
    mod = _import_dta_page()

    peak_count, exo_count, endo_count = mod._derive_event_metrics(
        {"peak_count": 9, "exotherm_count": 0, "endotherm_count": 0},
        [
            {"direction": "exo"},
            {"direction": "endo"},
        ],
    )

    assert peak_count == 2
    assert exo_count == 1
    assert endo_count == 1


def test_resolve_dta_sample_name_prefers_dataset_display_name_over_unknown():
    mod = _import_dta_page()

    sample_name = mod._resolve_dta_sample_name(
        {"sample_name": "Unknown"},
        {"dataset_key": "dta_run.csv"},
        {
            "dataset": {"display_name": "Ore Blend DTA Run"},
            "metadata": {"sample_name": "Ore Blend"},
        },
    )

    assert sample_name == "Ore Blend DTA Run"


def test_resolve_dta_sample_name_prefers_sample_name_over_file_name():
    mod = _import_dta_page()

    sample_name = mod._resolve_dta_sample_name(
        {"sample_name": "Unknown"},
        {"dataset_key": "dta_run.csv"},
        {
            "dataset": {"display_name": ""},
            "metadata": {"file_name": "raw_run.csv", "sample_name": "Ore Blend"},
        },
    )

    assert sample_name == "Ore Blend"


def test_resolve_dta_sample_name_prefers_workspace_display_when_summary_is_file_like_token():
    """Low-signal summary (mirrors file name or dataset-key stem) must not hide display_name."""
    mod = _import_dta_page()

    assert (
        mod._resolve_dta_sample_name(
            {"sample_name": "lab_import.csv"},
            {"dataset_key": "proj_lab_import_01.csv"},
            {
                "dataset": {"display_name": "Li-Ion Cell Batch A"},
                "metadata": {"file_name": "lab_import.csv"},
            },
        )
        == "Li-Ion Cell Batch A"
    )

    assert (
        mod._resolve_dta_sample_name(
            {"sample_name": "proj_run_dta"},
            {"dataset_key": "proj_run_dta.xlsx"},
            {
                "dataset": {"display_name": "Furnace Ramp Study"},
                "metadata": {},
            },
        )
        == "Furnace Ramp Study"
    )


def test_build_peak_table_empty():
    mod = _import_dta_page()

    result = mod._build_peak_table([])
    result_html = str(result)
    assert "No event data" in result_html


def test_build_peak_table_with_data():
    mod = _import_dta_page()

    rows = [
        {"direction": "exo", "peak_temperature": 250.0, "onset_temperature": 240.0,
         "endset_temperature": 260.0, "area": 1.0, "fwhm": 15.0, "height": 0.5},
    ]
    result = mod._build_peak_table(rows)
    result_html = str(result)
    assert "All Event Details" in result_html


def test_build_figure_uses_corrected_as_primary_trace(monkeypatch):
    mod = _import_dta_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _project_id, _analysis_type, _dataset_key: {
            "temperature": [100.0, 150.0, 200.0, 250.0],
            "raw_signal": [0.0, 1.2, -0.3, 0.6],
            "smoothed": [0.1, 1.0, -0.1, 0.5],
            "baseline": [0.05, 0.05, 0.05, 0.05],
            "corrected": [0.05, 0.95, -0.15, 0.45],
        },
    )

    graph = mod._build_figure(
        "proj-1",
        "dataset-1",
        "Synthetic DTA Run",
        [
            {
                "direction": "exo",
                "peak_temperature": 150.0,
                "onset_temperature": 140.0,
                "endset_temperature": 165.0,
                "area": 2.5,
                "height": 0.8,
            }
        ],
        "light",
    )

    assert isinstance(graph, dcc.Graph)
    corrected_trace = next(trace for trace in graph.figure.data if trace.name == "Corrected Signal")
    raw_trace = next(trace for trace in graph.figure.data if trace.name == "Raw Signal")
    assert corrected_trace.line.width == 2.8
    assert raw_trace.opacity < 0.3
    assert graph.figure.layout.height == 560
    assert graph.figure.layout.yaxis.range is not None
    assert len(graph.figure.layout.shapes) >= 2


def test_build_figure_handles_missing_primary_signal(monkeypatch):
    mod = _import_dta_page()
    import dash_app.api_client as api_client

    monkeypatch.setattr(
        api_client,
        "analysis_state_curves",
        lambda _project_id, _analysis_type, _dataset_key: {
            "temperature": [100.0, 150.0, 200.0],
            "raw_signal": [0.0, 1.0],
            "smoothed": [],
            "baseline": [0.1, 0.1, 0.1],
            "corrected": [],
        },
    )

    result = mod._build_figure(
        "proj-1",
        "dataset-1",
        "Synthetic DTA Run",
        [{"direction": "exo", "peak_temperature": 150.0}],
        "light",
    )

    assert isinstance(result, html.P)
    assert "No processed DTA signal is available" in str(result)


# ---------------------------------------------------------------------------
# Template descriptions
# ---------------------------------------------------------------------------

def test_template_descriptions_cover_all_templates():
    mod = _import_dta_page()

    for t in mod._DTA_WORKFLOW_TEMPLATES:
        assert t["id"] in mod._TEMPLATE_DESCRIPTIONS, f"Missing description for {t['id']}"


# ---------------------------------------------------------------------------
# Integration: DTA page with Dash server
# ---------------------------------------------------------------------------

def test_dta_dash_page_import_and_run_via_server():
    """Smoke test: import DTA data and run analysis through the combined server."""
    import base64

    from fastapi.testclient import TestClient
    from dash_app.sample_data import resolve_sample_request
    from dash_app.server import create_combined_app

    app = create_combined_app()
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200

    workspace = client.post("/workspace/new")
    assert workspace.status_code == 200
    project_id = workspace.json()["project_id"]

    # Import a DSC file as DTA (DSC data is valid DTA input in the real
    # processor -- both are thermal differential signals)
    sample_path, _ = resolve_sample_request("load-sample-dsc")
    assert sample_path is not None
    payload = base64.b64encode(sample_path.read_bytes()).decode("ascii")

    imported = client.post(
        "/dataset/import",
        json={
            "project_id": project_id,
            "file_name": sample_path.name,
            "file_base64": payload,
            "data_type": "DTA",
        },
    )
    assert imported.status_code == 200
    dataset_key = imported.json()["dataset"]["key"]
    assert imported.json()["dataset"]["data_type"] == "DTA"

    # Run DTA analysis
    run_response = client.post(
        "/analysis/run",
        json={
            "project_id": project_id,
            "dataset_key": dataset_key,
            "analysis_type": "DTA",
            "workflow_template_id": "dta.general",
        },
    )
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["execution_status"] == "saved"
    assert run_payload["result_id"].startswith("dta_")

    result_id = run_payload["result_id"]

    # Fetch result detail
    detail_response = client.get(f"/workspace/{project_id}/results/{result_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["processing"]["workflow_template_id"] == "dta.general"
    assert isinstance(detail["rows"], list)
    assert detail["row_count"] == len(detail["rows"])
    assert "exotherm_count" in detail["summary"]
    assert "endotherm_count" in detail["summary"]

    # Fetch analysis-state curves
    curves_response = client.get(f"/workspace/{project_id}/analysis-state/DTA/{dataset_key}")
    assert curves_response.status_code == 200
    curves = curves_response.json()
    assert "temperature" in curves
    assert "raw_signal" in curves
    assert len(curves["temperature"]) > 0


def test_dta_analysis_state_curves_sorted_temperature():
    """Verify DTA analysis-state curves return sorted temperature axis."""
    import base64

    from fastapi.testclient import TestClient
    from dash_app.sample_data import resolve_sample_request
    from dash_app.server import create_combined_app

    app = create_combined_app()
    client = TestClient(app)

    workspace = client.post("/workspace/new")
    project_id = workspace.json()["project_id"]

    sample_path, _ = resolve_sample_request("load-sample-dsc")
    payload = base64.b64encode(sample_path.read_bytes()).decode("ascii")

    imported = client.post(
        "/dataset/import",
        json={
            "project_id": project_id,
            "file_name": sample_path.name,
            "file_base64": payload,
            "data_type": "DTA",
        },
    )
    dataset_key = imported.json()["dataset"]["key"]

    client.post(
        "/analysis/run",
        json={
            "project_id": project_id,
            "dataset_key": dataset_key,
            "analysis_type": "DTA",
            "workflow_template_id": "dta.general",
        },
    )

    curves = client.get(f"/workspace/{project_id}/analysis-state/DTA/{dataset_key}").json()
    temps = curves["temperature"]
    assert temps == sorted(temps)


# ---------------------------------------------------------------------------
# Phase 1: smoothing draft / undo / redo / reset helpers
# ---------------------------------------------------------------------------

def test_default_processing_draft_matches_template_smoothing_defaults():
    mod = _import_dta_page()

    defaults = mod._default_processing_draft()
    assert defaults["smoothing"] == {
        "method": "savgol",
        "window_length": 11,
        "polyorder": 3,
    }


def test_normalize_smoothing_values_enforces_odd_window_and_bounds():
    mod = _import_dta_page()

    savgol = mod._normalize_smoothing_values("savgol", window_length=12, polyorder=3, sigma=None)
    assert savgol == {"method": "savgol", "window_length": 13, "polyorder": 3}

    mov_avg = mod._normalize_smoothing_values("moving_average", window_length=8, polyorder=None, sigma=None)
    assert mov_avg == {"method": "moving_average", "window_length": 9}

    gauss = mod._normalize_smoothing_values("gaussian", window_length=None, polyorder=None, sigma=1.5)
    assert gauss == {"method": "gaussian", "sigma": 1.5}

    # Unknown method falls back to savgol defaults (sanitizes bad input)
    fallback = mod._normalize_smoothing_values("exotic", window_length=15, polyorder=3, sigma=None)
    assert fallback == {"method": "savgol", "window_length": 15, "polyorder": 3}


def test_apply_draft_section_does_not_mutate_input():
    mod = _import_dta_page()

    base = mod._default_processing_draft()
    next_draft = mod._apply_draft_section(
        base, "smoothing", {"method": "gaussian", "sigma": 3.5}
    )

    assert base["smoothing"]["method"] == "savgol"  # unchanged
    assert next_draft["smoothing"] == {"method": "gaussian", "sigma": 3.5}


def test_undo_redo_cycle_restores_previous_and_future_drafts():
    mod = _import_dta_page()

    draft0 = mod._default_processing_draft()
    draft1 = mod._apply_draft_section(
        draft0, "smoothing", {"method": "savgol", "window_length": 21, "polyorder": 3}
    )
    undo_stack = mod._push_undo([], draft0)

    # Undo brings draft0 back and pushes draft1 onto redo
    restored, undo_after, redo_after = mod._do_undo(draft1, undo_stack, [])
    assert restored == draft0
    assert undo_after == []
    assert redo_after == [draft1]

    # Redo restores draft1 and pushes draft0 back onto undo
    reapplied, undo_next, redo_next = mod._do_redo(restored, undo_after, redo_after)
    assert reapplied == draft1
    assert undo_next == [draft0]
    assert redo_next == []


def test_undo_on_empty_stack_is_noop():
    mod = _import_dta_page()

    draft = mod._default_processing_draft()
    restored, undo_after, redo_after = mod._do_undo(draft, [], [])
    assert restored == draft
    assert undo_after == []
    assert redo_after == []


def test_reset_restores_defaults_and_pushes_current_to_undo():
    mod = _import_dta_page()

    defaults = mod._default_processing_draft()
    draft = mod._apply_draft_section(
        defaults, "smoothing", {"method": "gaussian", "sigma": 4.0}
    )

    next_draft, next_undo, next_redo = mod._do_reset(draft, [], [{"stale": True}], defaults)
    assert next_draft == defaults
    assert next_undo == [draft]
    # Reset clears redo stack even when previously populated
    assert next_redo == []

    # Reset when already at defaults is a no-op (does not push to undo)
    same_draft, same_undo, same_redo = mod._do_reset(defaults, [], [], defaults)
    assert same_draft == defaults
    assert same_undo == []
    assert same_redo == []


def test_smoothing_overrides_from_draft_returns_only_smoothing_section():
    mod = _import_dta_page()

    assert mod._smoothing_overrides_from_draft(None) == {}
    assert mod._smoothing_overrides_from_draft({}) == {}
    overrides = mod._smoothing_overrides_from_draft(
        {"smoothing": {"method": "savgol", "window_length": 21, "polyorder": 3}, "other": {}}
    )
    assert overrides == {"smoothing": {"method": "savgol", "window_length": 21, "polyorder": 3}}


def test_layout_includes_phase1_stores_and_smoothing_controls():
    mod = _import_dta_page()

    layout_str = str(mod.layout)
    for element_id in (
        "dta-processing-default",
        "dta-processing-draft",
        "dta-processing-undo",
        "dta-processing-redo",
        "dta-smooth-method",
        "dta-smooth-window",
        "dta-smooth-polyorder",
        "dta-smooth-sigma",
        "dta-smooth-apply-btn",
        "dta-undo-btn",
        "dta-redo-btn",
        "dta-reset-btn",
        "dta-smooth-status",
    ):
        assert element_id in layout_str, f"Missing Phase 1 element: {element_id}"


# ---------------------------------------------------------------------------
# Phase 1: backend override propagation via /analysis/run
# ---------------------------------------------------------------------------

def test_dta_analysis_run_honors_smoothing_overrides():
    """Per-step overrides must win over template defaults in persisted processing."""
    import base64

    from fastapi.testclient import TestClient
    from dash_app.sample_data import resolve_sample_request
    from dash_app.server import create_combined_app

    app = create_combined_app()
    client = TestClient(app)

    workspace = client.post("/workspace/new")
    project_id = workspace.json()["project_id"]

    sample_path, _ = resolve_sample_request("load-sample-dsc")
    payload = base64.b64encode(sample_path.read_bytes()).decode("ascii")

    imported = client.post(
        "/dataset/import",
        json={
            "project_id": project_id,
            "file_name": sample_path.name,
            "file_base64": payload,
            "data_type": "DTA",
        },
    )
    dataset_key = imported.json()["dataset"]["key"]

    run_response = client.post(
        "/analysis/run",
        json={
            "project_id": project_id,
            "dataset_key": dataset_key,
            "analysis_type": "DTA",
            "workflow_template_id": "dta.general",
            "processing_overrides": {
                "smoothing": {"method": "savgol", "window_length": 21, "polyorder": 3},
            },
        },
    )
    assert run_response.status_code == 200, run_response.text
    run_payload = run_response.json()
    assert run_payload["execution_status"] == "saved"
    result_id = run_payload["result_id"]

    detail = client.get(f"/workspace/{project_id}/results/{result_id}").json()
    smoothing = (detail.get("processing") or {}).get("signal_pipeline", {}).get("smoothing", {})
    assert smoothing.get("window_length") == 21
    assert smoothing.get("method") == "savgol"


def test_dta_analysis_run_rejects_unsupported_override_section():
    """Unknown processing sections for DTA must return a 400."""
    import base64

    from fastapi.testclient import TestClient
    from dash_app.sample_data import resolve_sample_request
    from dash_app.server import create_combined_app

    app = create_combined_app()
    client = TestClient(app)

    workspace = client.post("/workspace/new")
    project_id = workspace.json()["project_id"]

    sample_path, _ = resolve_sample_request("load-sample-dsc")
    payload = base64.b64encode(sample_path.read_bytes()).decode("ascii")

    imported = client.post(
        "/dataset/import",
        json={
            "project_id": project_id,
            "file_name": sample_path.name,
            "file_base64": payload,
            "data_type": "DTA",
        },
    )
    dataset_key = imported.json()["dataset"]["key"]

    run_response = client.post(
        "/analysis/run",
        json={
            "project_id": project_id,
            "dataset_key": dataset_key,
            "analysis_type": "DTA",
            "workflow_template_id": "dta.general",
            # normalization is NOT a DTA pipeline section
            "processing_overrides": {"normalization": {"method": "vector"}},
        },
    )
    assert run_response.status_code == 400, run_response.text


def test_dta_api_client_forwards_processing_overrides(monkeypatch):
    """dash_app.api_client.analysis_run must forward processing_overrides in the POST body."""
    import dash_app.api_client as api_client

    captured: dict = {}

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"execution_status": "saved", "result_id": "dta_fake"}

        def raise_for_status(self):
            return None

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def post(self, url, json=None):  # noqa: A002 - match httpx signature
            captured["url"] = url
            captured["json"] = json
            return _FakeResponse()

    monkeypatch.setattr(api_client, "_client", lambda: _FakeClient())
    monkeypatch.setattr(api_client, "_raise_with_detail", lambda _r: None)

    result = api_client.analysis_run(
        project_id="proj-1",
        dataset_key="ds-1",
        analysis_type="DTA",
        workflow_template_id="dta.general",
        processing_overrides={"smoothing": {"method": "savgol", "window_length": 21, "polyorder": 3}},
    )
    assert result == {"execution_status": "saved", "result_id": "dta_fake"}
    assert captured["url"] == "/analysis/run"
    assert captured["json"]["processing_overrides"] == {
        "smoothing": {"method": "savgol", "window_length": 21, "polyorder": 3}
    }
