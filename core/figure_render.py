"""Shared Plotly-to-PNG rendering helpers with resilient fallbacks."""

from __future__ import annotations

import io
import math
import os
import re
from typing import Any

import plotly.graph_objects as go
import plotly.io as pio

_FORCE_MPL_FALLBACK_ENV = "MATERIALSCOPE_FORCE_MPL_FIG_CAPTURE"
_DASH_RE = re.compile(r"<[^>]+>")


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return _DASH_RE.sub("", text).strip()


def _dash_to_linestyle(dash: str | None) -> str:
    token = str(dash or "").strip().lower()
    if token in {"dash", "longdash"}:
        return "--"
    if token in {"dot", "longdashdot"}:
        return ":"
    if token == "dashdot":
        return "-."
    return "-"


def _to_float_list(values: Any) -> list[float]:
    if values is None:
        return []
    out: list[float] = []
    for item in list(values):
        try:
            num = float(item)
        except (TypeError, ValueError):
            return []
        if not math.isfinite(num):
            return []
        out.append(num)
    return out


def _matplotlib_fallback_png(fig: go.Figure, *, width: int | None, height: int | None) -> bytes | None:
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        from matplotlib import pyplot as plt
    except Exception:
        return None

    width_px = int(width or fig.layout.width or 980)
    height_px = int(height or fig.layout.height or 560)
    width_in = max(width_px / 100.0, 4.0)
    height_in = max(height_px / 100.0, 3.0)

    figure = plt.figure(figsize=(width_in, height_in), dpi=120)
    axis = figure.add_subplot(1, 1, 1)
    plotted = 0
    legend_entries = 0

    for trace in list(fig.data):
        x = _to_float_list(getattr(trace, "x", None))
        y = _to_float_list(getattr(trace, "y", None))
        if not x or not y or len(x) != len(y):
            continue

        mode = str(getattr(trace, "mode", "lines") or "lines").lower()
        draw_markers = "markers" in mode
        color = getattr(getattr(trace, "line", None), "color", None) or getattr(getattr(trace, "marker", None), "color", None)
        if isinstance(color, (list, tuple, dict)):
            color = None
        width_px_line = getattr(getattr(trace, "line", None), "width", None)
        try:
            linewidth = float(width_px_line) if width_px_line is not None else 1.8
        except (TypeError, ValueError):
            linewidth = 1.8
        opacity = getattr(trace, "opacity", None)
        try:
            alpha = float(opacity) if opacity is not None else 1.0
        except (TypeError, ValueError):
            alpha = 1.0
        alpha = min(max(alpha, 0.1), 1.0)
        linestyle = _dash_to_linestyle(getattr(getattr(trace, "line", None), "dash", None))
        label = str(getattr(trace, "name", "") or "").strip()
        showlegend = getattr(trace, "showlegend", True)
        if not label or showlegend is False:
            label = None
        if label:
            legend_entries += 1

        axis.plot(
            x,
            y,
            linestyle=linestyle,
            marker="o" if draw_markers else None,
            markersize=3.2 if draw_markers else 0,
            linewidth=linewidth,
            color=color,
            alpha=alpha,
            label=label,
        )
        plotted += 1

    if plotted == 0:
        plt.close(figure)
        return None

    x_title = _clean_text(getattr(getattr(fig.layout, "xaxis", None), "title", None).text if getattr(getattr(fig.layout, "xaxis", None), "title", None) else "")
    y_title = _clean_text(getattr(getattr(fig.layout, "yaxis", None), "title", None).text if getattr(getattr(fig.layout, "yaxis", None), "title", None) else "")
    title = _clean_text(getattr(getattr(fig.layout, "title", None), "text", ""))
    if x_title:
        axis.set_xlabel(x_title)
    if y_title:
        axis.set_ylabel(y_title)
    if title:
        axis.set_title(title, fontsize=11)
    axis.grid(True, alpha=0.18, linewidth=0.7)
    if legend_entries > 0:
        axis.legend(loc="best", fontsize=8)
    figure.tight_layout()

    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=140)
    plt.close(figure)
    return buffer.getvalue()


def render_plotly_figure_png(
    fig: go.Figure,
    *,
    width: int | None = None,
    height: int | None = None,
) -> tuple[bytes | None, str | None]:
    """Render a Plotly figure to PNG.

    Returns
    -------
    (png_bytes, render_mode_or_error)
        ``png_bytes`` is ``None`` only if every renderer failed.
        ``render_mode_or_error`` is:
          - ``None`` for Plotly/Kaleido success,
          - a renderer tag (for example ``matplotlib_fallback``) on fallback success,
          - an error message on failure.
    """
    force_fallback = os.getenv(_FORCE_MPL_FALLBACK_ENV, "").strip().lower() in {"1", "true", "yes"}
    primary_error: str | None = None

    if not force_fallback:
        try:
            return pio.to_image(
                fig,
                format="png",
                engine="kaleido",
                width=width,
                height=height,
            ), None
        except Exception as exc:  # pragma: no cover - depends on runtime renderer availability.
            primary_error = str(exc)

    fallback_png = _matplotlib_fallback_png(fig, width=width, height=height)
    if fallback_png:
        return fallback_png, "matplotlib_fallback"

    if primary_error:
        return None, primary_error
    return None, "Figure rendering failed: neither Kaleido nor matplotlib fallback produced PNG bytes."
