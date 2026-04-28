"""Regression tests for shared analysis result figure rendering."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
import inspect

import dash
import pytest
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


def _iter_children(node: Any):
    if isinstance(node, (list, tuple)):
        for child in node:
            yield child
        return
    children = getattr(node, "children", None)
    if children is None:
        return
    if isinstance(children, (list, tuple)):
        yield from children
    else:
        yield children


def _find_graph(node: Any) -> dcc.Graph | None:
    if isinstance(node, dcc.Graph):
        return node
    for child in _iter_children(node):
        found = _find_graph(child)
        if found is not None:
            return found
    return None


def _assert_non_empty_graph(component: Any, expected_id: str | None = None) -> None:
    graph = _find_graph(component)
    assert isinstance(graph, dcc.Graph)
    if expected_id is not None:
        assert graph.id == expected_id
    assert "ms-result-graph" in str(getattr(graph, "className", "") or "")
    style = getattr(graph, "style", {}) or {}
    assert style.get("height") == "420px"
    assert style.get("minHeight") == "420px"
    assert style.get("width") == "100%"
    assert graph.config["responsive"] is True
    figure = graph.figure
    assert figure is not None
    assert len(getattr(figure, "data", []) or []) > 0
    assert figure.layout.autosize is True


def test_all_analysis_builders_return_visible_non_empty_result_graphs(monkeypatch):
    import dash_app.api_client as api_client
    import dash_app.pages.dsc as dsc
    import dash_app.pages.dta as dta
    import dash_app.pages.ftir as ftir
    import dash_app.pages.raman as raman
    import dash_app.pages.tga as tga
    import dash_app.pages.xrd as xrd

    curves = {
        "temperature": [100.0, 150.0, 200.0, 250.0],
        "raw_signal": [0.0, 1.2, -0.3, 0.6],
        "smoothed": [0.1, 1.0, -0.1, 0.5],
        "baseline": [0.05, 0.05, 0.05, 0.05],
        "corrected": [0.05, 0.95, -0.15, 0.45],
        "normalized": [0.1, 1.0, 0.2, 0.7],
        "peaks": [{"position": 150.0, "height": 0.95}],
        "has_smoothed": True,
        "diagnostics": {},
    }
    monkeypatch.setattr(api_client, "analysis_state_curves", lambda *_args: dict(curves))

    _assert_non_empty_graph(
        xrd._build_figure(
            "proj-1",
            "dataset-1",
            {"sample_name": "XRD Run"},
            {"method_context": {"xrd_axis_role": "two_theta"}},
            "light",
        ),
        "xrd-result-plot-graph",
    )
    _assert_non_empty_graph(
        dsc._build_figure(
            "proj-1",
            "dataset-1",
            {"tg_midpoint": 150.0},
            [{"peak_type": "exotherm", "peak_temperature": 150.0}],
            "light",
            "en",
            locale_data="en",
        )
    )
    _assert_non_empty_graph(
        tga._build_figure(
            "proj-1",
            "dataset-1",
            {"step_count": 1, "total_mass_loss_percent": 12.5, "residue_percent": 87.5},
            [{"midpoint_temperature": 150.0}],
            "light",
            "en",
        )
    )
    _assert_non_empty_graph(
        dta._build_figure(
            "proj-1",
            "dataset-1",
            "DTA Run",
            [{"direction": "exo", "peak_temperature": 150.0}],
            "light",
        )
    )
    _assert_non_empty_graph(
        ftir._build_figure(
            "proj-1",
            "dataset-1",
            {"peak_count": 1, "match_status": "no_match", "confidence_band": "no_match"},
            "light",
            "en",
        ),
        "ftir-result-plot-graph",
    )
    _assert_non_empty_graph(
        raman._build_figure(
            "proj-1",
            "dataset-1",
            {"peak_count": 1, "match_status": "no_match", "confidence_band": "no_match"},
            "light",
            "en",
        ),
        "raman-result-plot-graph",
    )


@pytest.mark.parametrize(
    ("module_name", "analysis_type", "expected_graph_id", "expected_prefix"),
    [
        ("dash_app.pages.ftir", "FTIR", "ftir-result-plot-graph", "ftir"),
        ("dash_app.pages.raman", "RAMAN", "raman-result-plot-graph", "raman"),
    ],
)
def test_spectral_result_callback_returns_visible_graph(
    monkeypatch,
    module_name: str,
    analysis_type: str,
    expected_graph_id: str,
    expected_prefix: str,
) -> None:
    import importlib
    import dash_app.api_client as api_client

    mod = importlib.import_module(module_name)

    monkeypatch.setattr(
        api_client,
        "workspace_result_detail",
        lambda _project_id, _result_id: {
            "summary": {
                "peak_count": 1,
                "match_status": "no_match",
                "confidence_band": "no_match",
                "top_match_score": 0.0,
            },
            "result": {"dataset_key": "dataset-1", "analysis_type": analysis_type},
            "processing": {"signal_pipeline": {}, "analysis_steps": {}, "method_context": {}},
            "rows_preview": [],
            "validation": {"status": "pass", "warnings": [], "issues": []},
        },
    )
    monkeypatch.setattr(
        api_client,
        "workspace_dataset_detail",
        lambda _project_id, _dataset_key: {
            "metadata": {"sample_name": "Spectral Sample", "display_name": "Spectral Sample"}
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
            "diagnostics": {},
        },
    )

    outputs = mod.display_result(
        "result-1",
        1,
        "light",
        "en",
        None,
        "project-1",
        None,
    )

    graph = _find_graph(outputs[3])
    assert graph is not None
    assert graph.id == expected_graph_id
    assert expected_prefix in expected_graph_id
    _assert_non_empty_graph(outputs[3], expected_graph_id)


@pytest.mark.parametrize(
    ("module_name", "required_fragments"),
    [
        (
            "dash_app.pages.ftir",
            [
                'Input("ftir-dataset-select", "value", allow_optional=True)',
                'State("ftir-dataset-select", "value", allow_optional=True)',
                'State("ftir-result-plot-graph", "relayoutData", allow_optional=True)',
            ],
        ),
        (
            "dash_app.pages.raman",
            [
                'Input("raman-dataset-select", "value", allow_optional=True)',
                'State("raman-dataset-select", "value", allow_optional=True)',
                'State("raman-result-plot-graph", "relayoutData", allow_optional=True)',
            ],
        ),
    ],
)
def test_spectral_callbacks_use_optional_dynamic_ids(module_name: str, required_fragments: list[str]) -> None:
    import importlib

    mod = importlib.import_module(module_name)
    source = inspect.getsource(mod)
    for fragment in required_fragments:
        assert fragment in source
