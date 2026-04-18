"""Tests for Dash export page branding upload feedback."""

from __future__ import annotations

import sys
from pathlib import Path

import dash_bootstrap_components as dbc
import pytest
from dash import html

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture(autouse=True)
def _ensure_dash_app():
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


def _import_export_page():
    import dash_app.pages.export as mod

    return mod


def test_export_branding_layout_contains_pending_logo_feedback_slot():
    mod = _import_export_page()
    card = mod._build_branding_card("en")
    assert "branding-logo-selection" in str(card)


def test_preview_branding_logo_selection_shows_pending_logo_feedback():
    mod = _import_export_page()
    content = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
    rendered = mod.preview_branding_logo_selection(content, "logo.png", "en")
    assert isinstance(rendered, html.Div)
    rendered_text = str(rendered)
    assert "Selected logo (not saved yet): logo.png" in rendered_text
    assert "data:image/png;base64" in rendered_text


def test_preview_branding_logo_selection_rejects_non_image_payload():
    mod = _import_export_page()
    rendered = mod.preview_branding_logo_selection("data:text/plain;base64,Zm9v", "logo.txt", "en")
    assert isinstance(rendered, dbc.Alert)
    assert rendered.color == "warning"
    assert "could not be previewed" in str(rendered)
