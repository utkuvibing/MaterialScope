"""Tests for the XRD Dash analysis page module."""

from __future__ import annotations

import inspect
import math
import sys
from pathlib import Path
from types import SimpleNamespace

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


def test_xrd_literature_i18n_prefix_is_xrd_native():
    mod = _import_xrd_page()
    assert mod._XRD_LITERATURE_PREFIX == "dash.analysis.xrd.literature"


def test_xrd_page_module_avoids_tga_literature_key_literals():
    """Phase 8 guard: XRD literature must not reference TGA i18n tree."""
    root = Path(__file__).resolve().parent.parent
    text = (root / "dash_app" / "pages" / "xrd.py").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "dash.analysis.tga.literature" not in lowered


def test_compare_xrd_literature_callback_uses_xrd_literature_prefix():
    mod = _import_xrd_page()
    src = inspect.getsource(mod.compare_xrd_literature)
    assert "_XRD_LITERATURE_PREFIX" in src or "dash.analysis.xrd.literature" in src


def test_layout_uses_results_surface_class():
    mod = _import_xrd_page()
    assert "ms-results-surface" in str(mod.layout)


def test_layout_tab_shells_in_processing_order():
    mod = _import_xrd_page()
    s = str(mod.layout)
    assert s.index("xrd-tab-setup-shell") < s.index("xrd-tab-processing-shell")
    assert s.index("xrd-tab-processing-shell") < s.index("xrd-tab-run-shell")
    assert s.index("xrd-left-tabs") < s.index("xrd-result-analysis-summary")


def test_layout_contains_mature_history_and_preset_stores():
    mod = _import_xrd_page()
    s = str(mod.layout)
    for sid in (
        "xrd-processing-default",
        "xrd-processing-undo-stack",
        "xrd-processing-redo-stack",
        "xrd-history-hydrate",
        "xrd-preset-refresh",
        "xrd-preset-hydrate",
        "xrd-preset-loaded-name",
        "xrd-preset-snapshot",
        "xrd-result-cache",
        "xrd-figure-artifact-refresh",
    ):
        assert sid in s, f"missing store/control: {sid}"


def test_layout_contains_key_div_ids():
    mod = _import_xrd_page()
    layout_str = str(mod.layout)

    expected_ids = [
        "xrd-dataset-selector-area",
        "xrd-template-select",
        "xrd-left-tabs",
        "xrd-run-btn",
        "xrd-result-analysis-summary",
        "xrd-result-metrics",
        "xrd-result-quality",
        "xrd-result-figure-controls",
        "xrd-figure-save-snapshot-btn",
        "xrd-figure-use-report-btn",
        "xrd-figure-artifact-status",
        "xrd-result-figure-artifacts",
        "xrd-figure-artifacts-summary",
        "xrd-result-figure",
        "xrd-result-top-match",
        "xrd-result-candidate-cards",
        "xrd-result-table",
        "xrd-result-processing",
        "xrd-result-raw-metadata",
        "xrd-literature-compare-btn",
        "xrd-literature-options-summary",
        "xrd-literature-max-claims",
        "xrd-literature-persist",
        "xrd-literature-output",
        "xrd-literature-status",
        "xrd-refresh",
        "xrd-latest-result-id",
        "xrd-figure-captured",
        "xrd-processing-draft",
    ]
    for div_id in expected_ids:
        assert div_id in layout_str, f"Missing layout element: {div_id}"


def test_layout_places_figure_before_candidate_cards():
    mod = _import_xrd_page()
    layout_str = str(mod.layout)
    assert layout_str.index("xrd-result-figure") < layout_str.index("xrd-result-candidate-cards")


def test_xrd_figure_artifact_callback_clear_on_result_change(monkeypatch):
    mod = _import_xrd_page()
    monkeypatch.setattr(mod.dash, "callback_context", SimpleNamespace(triggered_id="xrd-latest-result-id"))
    assert mod.xrd_figure_snapshot_or_report_figure(0, 0, "new-result", "proj", [], "en", 3) == ("", mod.dash.no_update)


def test_xrd_figure_artifact_callback_save_snapshot_registers(monkeypatch):
    import dash_app.api_client as api_client
    from dash import dcc
    import plotly.graph_objects as go

    mod = _import_xrd_page()
    captured: list[dict] = []

    def _fake_register(**kwargs):
        captured.append(dict(kwargs))
        return {"status": "ok", "figure_key": kwargs["label"]}

    monkeypatch.setattr(mod, "register_result_figure_from_layout_children", _fake_register)
    monkeypatch.setattr(
        api_client,
        "workspace_result_detail",
        lambda *_a, **_k: {"result": {"dataset_key": "sample_xrd"}},
    )

    monkeypatch.setattr(mod.dash, "callback_context", SimpleNamespace(triggered_id="xrd-figure-save-snapshot-btn"))
    fig_child = html.Div(dcc.Graph(figure=go.Figure(data=[go.Scatter(x=[1, 2], y=[1, 2])])))
    out, refresh = mod.xrd_figure_snapshot_or_report_figure(1, 0, "xrd_1", "proj-9", fig_child, "en", 4)
    assert captured and captured[0]["replace"] is False
    assert captured[0]["result_id"] == "xrd_1"
    assert "XRD Snapshot" in captured[0]["label"]
    assert isinstance(out, dbc.Alert)
    assert refresh == 5


def test_xrd_figure_artifact_callback_report_registers_replace(monkeypatch):
    import dash_app.api_client as api_client
    from dash import dcc
    import plotly.graph_objects as go

    mod = _import_xrd_page()
    captured: list[dict] = []

    def _fake_register(**kwargs):
        captured.append(dict(kwargs))
        return {"status": "ok", "figure_key": kwargs["label"]}

    monkeypatch.setattr(mod, "register_result_figure_from_layout_children", _fake_register)
    monkeypatch.setattr(
        api_client,
        "workspace_result_detail",
        lambda *_a, **_k: {"result": {"dataset_key": "sample_xrd"}},
    )

    monkeypatch.setattr(mod.dash, "callback_context", SimpleNamespace(triggered_id="xrd-figure-use-report-btn"))
    fig_child = html.Div(dcc.Graph(figure=go.Figure(data=[go.Scatter(x=[1, 2], y=[1, 2])])))
    out, refresh = mod.xrd_figure_snapshot_or_report_figure(0, 1, "xrd_1", "proj-9", fig_child, "en", 8)
    assert captured and captured[0]["replace"] is True
    assert captured[0]["label"] == "XRD Analysis - sample_xrd"
    assert isinstance(out, dbc.Alert)
    assert refresh == 9


def test_build_xrd_figure_artifacts_panel_lists_keys():
    mod = _import_xrd_page()
    panel = mod._build_xrd_figure_artifacts_panel(
        {
            "figure_keys": ["XRD Analysis - ds", "XRD Snapshot - ds - t"],
            "report_figure_key": "XRD Analysis - ds",
            "report_figure_status": "captured",
        },
        "en",
    )
    s = str(panel)
    assert "XRD Analysis - ds" in s
    from utils.i18n import translate_ui

    assert translate_ui("en", "dash.analysis.xrd.figure.artifacts_registry_summary") in s or "Kayıt" in s


def test_capture_xrd_figure_delegates_to_shared_helper(monkeypatch):
    mod = _import_xrd_page()
    captured_kwargs: dict = {}

    def _fake_capture(**kwargs):
        captured_kwargs.update(kwargs)
        return {"xrd_r_2": {"status": "ok"}}

    monkeypatch.setattr(mod, "capture_result_figure_from_layout", _fake_capture)
    result = mod.capture_xrd_figure("xrd_r_2", "proj-1", {"graph": True}, {"old": "state"})
    assert result == {"xrd_r_2": {"status": "ok"}}
    assert captured_kwargs == {
        "result_id": "xrd_r_2",
        "project_id": "proj-1",
        "figure_children": {"graph": True},
        "captured": {"old": "state"},
        "analysis_type": "XRD",
    }


def test_xrd_figure_artifact_i18n_keys_resolve():
    from utils.i18n import translate_ui

    loc = "en"
    assert translate_ui(loc, "dash.analysis.xrd.figure.btn_snapshot") != "dash.analysis.xrd.figure.btn_snapshot"
    assert translate_ui(loc, "dash.analysis.xrd.figure.btn_report") != "dash.analysis.xrd.figure.btn_report"
    assert "k1" in translate_ui(loc, "dash.analysis.xrd.figure.snapshot_ok", figure_key="k1")
    assert "k2" in translate_ui(loc, "dash.analysis.xrd.figure.report_ok", figure_key="k2")
    assert "r0" in translate_ui(loc, "dash.analysis.xrd.figure.artifact_skip", reason="r0")
    assert "e0" in translate_ui(loc, "dash.analysis.xrd.figure.artifact_error", reason="e0")
    assert translate_ui(loc, "dash.analysis.xrd.figure.artifacts_none") != "dash.analysis.xrd.figure.artifacts_none"
    assert translate_ui(loc, "dash.analysis.xrd.figure.artifacts_previews_heading") != "dash.analysis.xrd.figure.artifacts_previews_heading"
    assert "3" in translate_ui(loc, "dash.analysis.xrd.figure.artifacts_previews_truncated", n=3)


def test_layout_mature_result_surface_ordering():
    """Ordered surface: summary → metrics → quality → figure → top match → cards → table → processing → raw → literature."""
    mod = _import_xrd_page()
    s = str(mod.layout)
    pairs = [
        ("xrd-result-analysis-summary", "xrd-result-metrics"),
        ("xrd-result-metrics", "xrd-result-quality"),
        ("xrd-result-quality", "xrd-result-figure"),
        ("xrd-result-figure", "xrd-result-top-match"),
        ("xrd-result-top-match", "xrd-result-candidate-cards"),
        ("xrd-result-candidate-cards", "xrd-result-table"),
        ("xrd-result-table", "xrd-result-processing"),
        ("xrd-result-processing", "xrd-result-raw-metadata"),
        ("xrd-result-raw-metadata", "xrd-literature-compare-btn"),
    ]
    for a, b in pairs:
        assert s.index(a) < s.index(b), f"expected {a} before {b}"


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
    assert "0.812" in card_html


def test_build_match_cards_empty():
    mod = _import_xrd_page()
    result = mod._build_match_cards([], {})
    assert isinstance(result, html.Div)
    assert "No candidate matches were returned." in str(result)


def test_xrd_status_label_separates_peak_detection_from_unavailable_matching():
    mod = _import_xrd_page()
    summary = {
        "peak_count": 12,
        "match_status": "not_run",
        "caution_code": "xrd_reference_library_unavailable",
        "caution_message": "No XRD reference library/index configured.",
    }

    assert mod._xrd_phase_status_label("en", summary) == "Phase matching skipped: no reference library"
    panel = mod._build_xrd_analysis_summary(
        {"metadata": {"file_name": "xrd_2024_0304_zenodo.csv"}, "dataset": {}},
        summary,
        {"dataset_key": "xrd-demo"},
        "en",
        locale_data="en",
    )
    rendered = str(panel)
    assert "Peak detection" in rendered
    assert "Completed (12 peaks)" in rendered
    assert "Phase matching skipped: no reference library" in rendered
    assert "Configure or import an XRD reference library/index" in rendered


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
    assert graph.id == "xrd-result-plot-graph"
    corrected_trace = next(trace for trace in graph.figure.data if trace.name == "Corrected Diffractogram")
    raw_trace = next(trace for trace in graph.figure.data if trace.name == "Raw Diffractogram")
    assert corrected_trace.line.width == 3.0
    assert corrected_trace.visible in (None, True)
    assert raw_trace.visible == "legendonly"
    assert raw_trace.opacity < 0.4
    assert graph.figure.layout.xaxis.title.text == "2theta (deg)"
    assert graph.figure.layout.meta["plot_view_mode"] == "result"
    assert "plot_display_settings" in graph.figure.layout.meta
    assert graph.figure.layout.hovermode == "x unified"
    assert graph.figure.layout.legend.y >= 0
    assert graph.figure.layout.yaxis.range[1] < 60
    assert graph.config["displayModeBar"] is True
    assert graph.config["displaylogo"] is False
    assert graph.config["responsive"] is True
    assert graph.config["toImageButtonOptions"]["filename"] == "materialscope_xrd_diffractogram"
    assert graph.config["toImageButtonOptions"]["width"] == 1400


def test_xrd_relayout_shape_payload_is_carried_for_theme_rebuild():
    mod = _import_xrd_page()

    shapes = [{"type": "line", "x0": 10, "y0": 1, "x1": 20, "y1": 2, "line": {"color": "#000000"}}]
    assert mod._xrd_shapes_from_relayout({"shapes": shapes}) == shapes
    assert mod._xrd_shapes_from_relayout({"xaxis.range[0]": 10}) is None


def test_xrd_default_corrected_view_demotes_raw_from_autorange():
    from dash_app.components.xrd_result_plot import build_xrd_result_figure

    fig = build_xrd_result_figure(
        axis=[10.0, 20.0, 30.0, 40.0],
        raw_signal=[2000.0, 5000.0, 3500.0, 1500.0],
        smoothed=[21.0, 48.0, 34.0, 16.0],
        baseline=[4.0, 4.0, 4.0, 4.0],
        corrected=[17.0, 44.0, 30.0, 12.0],
        peaks=[],
        selected_match=None,
        plot_settings={},
        ui_theme="light",
        loc="en",
        sample_name="XRD Run A",
        axis_title="2theta (deg)",
    )

    raw_trace = next(trace for trace in fig.data if trace.name == "Raw Diffractogram")
    corrected_trace = next(trace for trace in fig.data if trace.name == "Corrected Diffractogram")
    assert raw_trace.visible == "legendonly"
    assert raw_trace.showlegend is True
    assert corrected_trace.visible in (None, True)
    assert corrected_trace.line.width == 3.0
    assert fig.layout.yaxis.range[1] < 60


def test_xrd_dense_peak_cluster_labels_are_sparse_and_readable():
    from dash_app.components.xrd_result_plot import build_xrd_result_figure

    peaks = [
        {"position": 10.0, "intensity": 100.0},
        {"position": 10.2, "intensity": 95.0},
        {"position": 10.4, "intensity": 90.0},
        {"position": 10.6, "intensity": 85.0},
        {"position": 10.8, "intensity": 80.0},
        {"position": 16.0, "intensity": 70.0},
        {"position": 16.3, "intensity": 68.0},
        {"position": 24.0, "intensity": 65.0},
        {"position": 32.0, "intensity": 60.0},
        {"position": 40.0, "intensity": 55.0},
    ]
    fig = build_xrd_result_figure(
        axis=[10.0, 20.0, 30.0, 40.0],
        raw_signal=[20.0, 50.0, 35.0, 15.0],
        smoothed=[21.0, 48.0, 34.0, 16.0],
        baseline=[4.0, 4.0, 4.0, 4.0],
        corrected=[17.0, 44.0, 30.0, 12.0],
        peaks=peaks,
        selected_match=None,
        plot_settings={},
        ui_theme="light",
        loc="en",
        sample_name="XRD Dense Peaks",
        axis_title="2theta (deg)",
    )

    label_trace = next(trace for trace in fig.data if trace.mode == "text")
    visible_labels = [label for label in label_trace.text if label]
    assert len(visible_labels) <= 4
    assert len(visible_labels) < len(peaks)
    assert "10.00 deg" in visible_labels[0]


def test_build_xrd_result_figure_preserves_log_y_range_after_shared_theme():
    from dash_app.components.xrd_result_plot import build_xrd_result_figure

    fig = build_xrd_result_figure(
        axis=[10.0, 20.0, 30.0, 40.0],
        raw_signal=[20.0, 50.0, 35.0, 15.0],
        smoothed=[21.0, 48.0, 34.0, 16.0],
        baseline=[4.0, 4.0, 4.0, 4.0],
        corrected=[17.0, 44.0, 30.0, 12.0],
        peaks=[],
        selected_match=None,
        plot_settings={
            "log_y": True,
            "y_range_enabled": True,
            "y_min": 1.0,
            "y_max": 100.0,
            "x_range_enabled": True,
            "x_min": 12.0,
            "x_max": 38.0,
        },
        ui_theme="light",
        loc="en",
        sample_name="XRD Run Log",
        axis_title="2theta (deg)",
    )

    assert fig.layout.yaxis.type == "log"
    assert list(fig.layout.yaxis.range) == [math.log10(1.0), math.log10(100.0)]
    assert list(fig.layout.xaxis.range) == [12.0, 38.0]
    assert fig.layout.xaxis.title.text == "2theta (deg)"
    assert fig.layout.yaxis.title.text == "Intensity (a.u.)"
    assert fig.layout.meta["plot_view_mode"] == "result"


def test_build_xrd_result_figure_preserves_drawn_shapes_with_theme_contrast():
    from dash_app.components.xrd_result_plot import build_xrd_result_figure

    fig = build_xrd_result_figure(
        axis=[10.0, 20.0, 30.0, 40.0],
        raw_signal=[20.0, 50.0, 35.0, 15.0],
        smoothed=[21.0, 48.0, 34.0, 16.0],
        baseline=[4.0, 4.0, 4.0, 4.0],
        corrected=[17.0, 44.0, 30.0, 12.0],
        peaks=[],
        selected_match=None,
        plot_settings={},
        ui_theme="dark",
        loc="en",
        sample_name="XRD Drawing",
        axis_title="2theta (deg)",
        drawn_shapes=[{"type": "line", "x0": 10, "y0": 1, "x1": 20, "y1": 2, "line": {"color": "#000000"}}],
    )

    assert len(fig.layout.shapes) == 1
    assert fig.layout.shapes[0].line.color != "#000000"


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
    assert "figure_artifacts" in detail
    assert isinstance(detail["figure_artifacts"], dict)
    assert "figure_keys" in detail["figure_artifacts"]

    curves_response = client.get(f"/workspace/{project_id}/analysis-state/XRD/{dataset_key}")
    assert curves_response.status_code == 200
    curves = curves_response.json()
    assert "temperature" in curves
    assert "raw_signal" in curves
    assert len(curves["temperature"]) > 0
