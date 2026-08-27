"""Regression contract for Plotly/Kaleido static PNG export (PR-3).

These tests intentionally separate two outcomes that would otherwise be
indistinguishable to callers:

* ``render_mode_or_error is None`` -> genuine Plotly/Kaleido success;
* ``"matplotlib_fallback"``       -> fallback success because Kaleido failed.

A broken Kaleido installation must therefore surface as a skipped
Chrome-dependent integration test plus an explicit fallback/error contract,
never as a false "genuine renderer" pass.
"""

from __future__ import annotations

import importlib.util

import pytest

import core.figure_render as figure_render
from core.figure_render import render_plotly_figure_png

import plotly.graph_objects as go
import plotly.io as pio

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture(autouse=True)
def _clean_renderer_environment(monkeypatch):
    # Never let an outside setting push these tests into the fallback branch
    # silently; the point of this module is to pin renderer-mode semantics.
    monkeypatch.delenv(figure_render._FORCE_MPL_FALLBACK_ENV, raising=False)


def _sample_figure() -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[1, 2, 3], y=[2, 4, 6], mode="lines", name="Run 1"))
    fig.update_layout(width=480, height=320, template="none")
    return fig


def _kaleido_static_export_works() -> bool:
    """Probe whether Plotly can export through Kaleido right here, right now.

    Kaleido v1 requires a real Chrome/Chromium binary; when none is available
    the Chrome-dependent integration test below skips instead of passing.
    """
    probe = go.Figure(go.Scatter(x=[0, 1], y=[0, 1]))
    try:
        png = pio.to_image(probe, format="png", width=64, height=64)
    except Exception:
        return False
    return bool(png[:8] == PNG_MAGIC)


def test_primary_path_invokes_plotly_without_deprecated_engine_kwarg(monkeypatch):
    """The helper must delegate to Plotly's current invocation form."""
    captured_kwargs: dict[str, object] = {}

    def _fake_to_image(_fig, **kwargs):
        captured_kwargs.update(kwargs)
        return PNG_MAGIC + b"stubbed-bytes"

    monkeypatch.setattr(pio, "to_image", _fake_to_image)

    png_bytes, render_meta = render_plotly_figure_png(_sample_figure(), width=480, height=320)

    assert png_bytes[:8] == PNG_MAGIC
    # None is reserved for genuine Plotly/Kaleido success.
    assert render_meta is None
    assert captured_kwargs["format"] == "png"
    assert captured_kwargs["width"] == 480
    assert captured_kwargs["height"] == 320
    # The explicit ``engine="kaleido"`` kwarg is deprecated (Plotly 6+) and
    # must stay out of the supported invocation path.
    assert "engine" not in captured_kwargs


def test_kaleido_failure_is_distinguished_from_fallback_and_error(monkeypatch):
    """When the primary renderer fails, the mode tag must expose why."""

    def _always_fail(_fig, **kwargs):
        raise RuntimeError("kaleido is broken")

    monkeypatch.setattr(pio, "to_image", _always_fail)

    png_bytes, render_meta = render_plotly_figure_png(_sample_figure(), width=480, height=320)

    matplotlib_present = importlib.util.find_spec("matplotlib") is not None
    if matplotlib_present:
        # Fallback succeeded -> it must be labeled as fallback, never None.
        assert render_meta == "matplotlib_fallback"
        assert png_bytes[:8] == PNG_MAGIC
    else:
        # No fallback renderer exists -> hard error, definitely not a
        # silent "genuine renderer success".
        assert png_bytes is None
        assert render_meta is not None
        assert "kaleido" in str(render_meta).lower() or "failed" in str(render_meta).lower()


def test_full_plotly_kaleido_png_export_with_real_chrome():
    """Genuine end-to-end PNG export through Plotly/Kaleido and a real browser.

    Skipped (never faked) when Chrome/Chromium is unavailable so the locally
    runnable suite stays usable on machines without a browser.
    """
    if not _kaleido_static_export_works():
        pytest.skip(
            "Plotly/Kaleido cannot reach a Chrome/Chromium browser in this "
            "environment; genuine PNG export cannot be proven here."
        )

    png_bytes, render_meta = render_plotly_figure_png(_sample_figure(), width=480, height=320)

    assert render_meta is None, (
        "Primary renderer returned a non-Kaleido result even though the "
        f"fresh standalone probe succeeded: {render_meta!r}"
    )
    assert png_bytes is not None
    assert png_bytes[:8] == PNG_MAGIC
    assert len(png_bytes) > 500
