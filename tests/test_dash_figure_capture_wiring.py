"""Shared Dash figure-capture wiring across stable modality pages."""

from __future__ import annotations

import importlib

import pytest
from dash import html


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


_MODALITY_PAGES = [
    ("dash_app.pages.dsc", "dsc-figure-captured", "capture_dsc_figure", "DSC"),
    ("dash_app.pages.tga", "tga-figure-captured", "capture_tga_figure", "TGA"),
    ("dash_app.pages.ftir", "ftir-figure-captured", "capture_ftir_figure", "FTIR"),
    ("dash_app.pages.raman", "raman-figure-captured", "capture_raman_figure", "RAMAN"),
    ("dash_app.pages.xrd", "xrd-figure-captured", "capture_xrd_figure", "XRD"),
]


@pytest.mark.parametrize("module_name,store_id,_callback_name,_analysis_type", _MODALITY_PAGES)
def test_page_layout_contains_figure_capture_store(module_name, store_id, _callback_name, _analysis_type):
    mod = importlib.import_module(module_name)
    assert store_id in str(mod.layout)


@pytest.mark.parametrize("module_name,_store_id,callback_name,analysis_type", _MODALITY_PAGES)
def test_capture_callback_delegates_to_shared_helper(monkeypatch, module_name, _store_id, callback_name, analysis_type):
    mod = importlib.import_module(module_name)

    captured_kwargs: dict = {}

    def _fake_capture(**kwargs):
        captured_kwargs.update(kwargs)
        return {"result_id": kwargs["result_id"], "status": "ok"}

    monkeypatch.setattr(mod, "capture_result_figure_from_layout", _fake_capture)

    callback_fn = getattr(mod, callback_name)
    output = callback_fn("result-1", "project-1", [{"props": {"children": []}}], {})

    assert output == {"result_id": "result-1", "status": "ok"}
    assert captured_kwargs["result_id"] == "result-1"
    assert captured_kwargs["project_id"] == "project-1"
    assert captured_kwargs["analysis_type"] == analysis_type
