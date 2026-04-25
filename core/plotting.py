"""Shared Plotly display helpers for MaterialScope.

This module is intentionally pure UI/display logic. It normalizes chart
appearance settings, applies the shared Plotly theme, and builds client config;
it does not interpret modality-specific analysis data.
"""

from __future__ import annotations

from typing import Any, Mapping

import plotly.graph_objects as go
import math

FONT_FAMILY = "'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif"
COLORWAY = [
    "#0F766E",
    "#2563EB",
    "#DC2626",
    "#7C3AED",
    "#D97706",
    "#0891B2",
    "#65A30D",
    "#475569",
]

PLOT_THEME = {
    "light": {
        "template": "plotly_white",
        "text": "#1C1A1A",
        "subtle_text": "#66645E",
        "paper_bg": "#FFFFFF",
        "plot_bg": "#FFFFFF",
        "grid": "#E0DDD6",
        "axis": "#D4D1CA",
        "hover_bg": "#FFFFFF",
        "hover_border": "#D4D1CA",
        "legend_bg": "rgba(255,255,255,0.86)",
        "annotation_bg": "rgba(255,255,255,0.92)",
        "annotation_border": "rgba(102,100,94,0.22)",
        "shape_line": "#1C1A1A",
    },
    "dark": {
        "template": "plotly_dark",
        "text": "#EEEDEA",
        "subtle_text": "#9E9A93",
        "paper_bg": "#1A1917",
        "plot_bg": "#121110",
        "grid": "#3D3B38",
        "axis": "#5A5650",
        "hover_bg": "#1A1917",
        "hover_border": "#3D3B38",
        "legend_bg": "rgba(26,25,23,0.86)",
        "annotation_bg": "rgba(26,25,23,0.92)",
        "annotation_border": "rgba(158,154,147,0.24)",
        "shape_line": "#F2F0EB",
    },
}

DEFAULT_EXPORT_WIDTH = 1400
DEFAULT_EXPORT_HEIGHT = 840
DEFAULT_DISPLAY_SETTINGS: dict[str, Any] = {
    "legend_mode": "auto",
    "compact": False,
    "show_grid": True,
    "show_spikes": True,
    "line_width_scale": 1.0,
    "marker_size_scale": 1.0,
    "export_scale": 2,
    "reverse_x_axis": False,
    "x_range_enabled": False,
    "x_min": None,
    "x_max": None,
    "y_range_enabled": False,
    "y_min": None,
    "y_max": None,
}

DEFAULT_PLOTLY_CONFIG: dict[str, Any] = {
    "displayModeBar": True,
    "scrollZoom": True,
    "modeBarButtonsToAdd": ["drawline", "drawopenpath", "eraseshape"],
    "modeBarButtonsToRemove": ["lasso2d"],
    "displaylogo": False,
    "responsive": True,
    "toImageButtonOptions": {
        "format": "png",
        "filename": "materialscope_plot",
        "width": DEFAULT_EXPORT_WIDTH,
        "height": DEFAULT_EXPORT_HEIGHT,
        "scale": 2,
    },
}


def normalize_plot_theme(theme: str | None) -> str:
    return theme if theme in PLOT_THEME else "light"


def _coerce_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value) if value not in (None, "") else fallback


def _coerce_float(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


def _coerce_int(value: Any, fallback: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def normalize_plot_display_settings(
    payload: Mapping[str, Any] | None,
    defaults: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source = payload if isinstance(payload, Mapping) else {}
    settings = dict(DEFAULT_DISPLAY_SETTINGS)
    if isinstance(defaults, Mapping):
        settings.update(defaults)

    legend = str(source.get("legend_mode", settings["legend_mode"]) or settings["legend_mode"]).strip().lower()
    settings["legend_mode"] = legend if legend in {"auto", "external", "compact", "hidden"} else "auto"
    for key in ("compact", "show_grid", "show_spikes", "reverse_x_axis", "x_range_enabled", "y_range_enabled"):
        settings[key] = _coerce_bool(source.get(key, settings[key]), bool(settings[key]))
    settings["line_width_scale"] = _coerce_float(source.get("line_width_scale", settings["line_width_scale"]), 1.0, 0.6, 1.8)
    settings["marker_size_scale"] = _coerce_float(source.get("marker_size_scale", settings["marker_size_scale"]), 1.0, 0.6, 1.8)
    settings["export_scale"] = _coerce_int(source.get("export_scale", settings["export_scale"]), 2, 1, 4)
    for key in ("x_min", "x_max", "y_min", "y_max"):
        settings[key] = _optional_float(source.get(key, settings.get(key)))
    if settings["x_range_enabled"] and settings["x_min"] is not None and settings["x_max"] is not None and settings["x_min"] > settings["x_max"]:
        settings["x_min"], settings["x_max"] = settings["x_max"], settings["x_min"]
    if settings["y_range_enabled"] and settings["y_min"] is not None and settings["y_max"] is not None and settings["y_min"] > settings["y_max"]:
        settings["y_min"], settings["y_max"] = settings["y_max"], settings["y_min"]
    return settings


def build_plotly_config(settings: Mapping[str, Any] | None = None, *, filename: str | None = None) -> dict[str, Any]:
    resolved = normalize_plot_display_settings(settings)
    export_options = dict(DEFAULT_PLOTLY_CONFIG["toImageButtonOptions"])
    export_options["scale"] = resolved["export_scale"]
    if filename:
        export_options["filename"] = filename
    config = dict(DEFAULT_PLOTLY_CONFIG)
    config["toImageButtonOptions"] = export_options
    return config


def legend_layout(
    trace_count: int,
    settings: Mapping[str, Any] | None = None,
    *,
    theme: str | None = None,
) -> tuple[bool, dict[str, Any]]:
    resolved = normalize_plot_display_settings(settings)
    tokens = PLOT_THEME[normalize_plot_theme(theme)]
    mode = str(resolved.get("legend_mode") or "auto")
    if mode == "hidden":
        return False, {}
    font_size = 10 if resolved["compact"] else 11
    if mode in {"external", "compact"} or (mode == "auto" and trace_count >= 5):
        return True, {
            "orientation": "v",
            "yanchor": "top",
            "y": 1.0,
            "xanchor": "left",
            "x": 1.02,
            "bgcolor": tokens["legend_bg"],
            "bordercolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "tracegroupgap": 4,
            "font": {"size": font_size, "color": tokens["text"]},
            "title": {"text": ""},
            "itemsizing": "constant",
        }
    return True, {
        "orientation": "h",
        "yanchor": "bottom",
        "y": 1.02,
        "xanchor": "left",
        "x": 0.0,
        "bgcolor": tokens["legend_bg"],
        "bordercolor": "rgba(0,0,0,0)",
        "borderwidth": 0,
        "font": {"size": font_size, "color": tokens["text"]},
        "title": {"text": ""},
        "itemsizing": "constant",
    }


def _compose_title(title: str | None, subtitle: str | None, *, compact: bool, theme: str) -> str:
    base = str(title or "").strip()
    sub = str(subtitle or "").strip()
    if not sub:
        return base
    sub_size = 11 if compact else 12
    subtle = PLOT_THEME[normalize_plot_theme(theme)]["subtle_text"]
    return f"{base}<br><span style='font-size:{sub_size}px;color:{subtle}'>{sub}</span>"


def _scale_trace_styles(fig: go.Figure, *, line_width_scale: float, marker_size_scale: float) -> None:
    for index, trace in enumerate(fig.data):
        mode = str(getattr(trace, "mode", "") or "")
        if hasattr(trace, "line"):
            current_width = getattr(trace.line, "width", None)
            if current_width in (None, 0) and "lines" in mode:
                current_width = 2.2 if index == 0 else 1.8
                trace.line.width = current_width
            if isinstance(current_width, (int, float)):
                trace.line.width = max(0.6, float(current_width) * line_width_scale)
        if hasattr(trace, "marker"):
            current_size = getattr(trace.marker, "size", None)
            if current_size in (None, 0) and "markers" in mode:
                current_size = 7.0
                trace.marker.size = current_size
            if isinstance(current_size, (int, float)):
                trace.marker.size = max(4.0, float(current_size) * marker_size_scale)


def _shape_line_needs_theme_contrast(color: Any) -> bool:
    if color in (None, ""):
        return True
    normalized = str(color).strip().lower().replace(" ", "")
    return normalized in {
        "black",
        "#000",
        "#000000",
        "#1c1a1a",
        "rgb(0,0,0)",
        "rgba(0,0,0,1)",
        "white",
        "#fff",
        "#ffffff",
        "#f2f0eb",
        "rgb(255,255,255)",
        "rgba(255,255,255,1)",
    }


def _apply_shape_contrast(fig: go.Figure, *, line_color: str) -> None:
    shapes = list(getattr(fig.layout, "shapes", None) or [])
    if not shapes:
        return
    for shape in shapes:
        line = getattr(shape, "line", None)
        color = getattr(line, "color", None) if line is not None else None
        if _shape_line_needs_theme_contrast(color):
            shape.line.color = line_color
        width = getattr(shape.line, "width", None)
        if width in (None, 0):
            shape.line.width = 2.5


def apply_materialscope_plot_theme(
    fig: go.Figure,
    settings: Mapping[str, Any] | None = None,
    *,
    theme: str | None = None,
    title: str | None = None,
    subtitle: str | None = None,
    view_mode: str = "result",
    for_export: bool = False,
    scale_traces: bool = True,
) -> go.Figure:
    resolved = normalize_plot_display_settings(settings)
    tone = normalize_plot_theme(theme)
    tokens = PLOT_THEME[tone]
    compact = bool(resolved["compact"]) and not for_export
    debug_mode = str(view_mode or "result").lower() == "debug"
    trace_count = sum(1 for trace in fig.data if getattr(trace, "showlegend", True) is not False)
    showlegend, legend = legend_layout(trace_count, resolved, theme=tone)
    right_margin = 142 if showlegend and legend.get("orientation") == "v" else 34 if compact else 44
    top_margin = 74 if compact else 90
    if showlegend and legend.get("orientation") == "h":
        top_margin += 20
    if subtitle:
        top_margin += 18
    bottom_margin = 54 if compact else 68
    plot_height = 520 if compact else 620
    if for_export:
        top_margin = 82 if subtitle else 68
        bottom_margin = 54
        plot_height = DEFAULT_EXPORT_HEIGHT

    fig.update_layout(
        template=tokens["template"],
        colorway=COLORWAY,
        font={"family": FONT_FAMILY, "size": 12, "color": tokens["text"]},
        hoverlabel={
            "bgcolor": tokens["hover_bg"],
            "bordercolor": tokens["hover_border"],
            "font": {"size": 12, "family": FONT_FAMILY, "color": tokens["text"]},
        },
        title={
            "text": _compose_title(title if title is not None else getattr(fig.layout.title, "text", ""), subtitle, compact=compact, theme=tone),
            "x": 0.0,
            "xanchor": "left",
            "y": 0.98,
            "yanchor": "top",
            "pad": {"b": 10},
            "font": {"size": 16 if compact else 18, "color": tokens["text"], "family": FONT_FAMILY},
        },
        paper_bgcolor=tokens["paper_bg"],
        plot_bgcolor=tokens["plot_bg"],
        showlegend=showlegend,
        legend=legend,
        hovermode="x unified",
        hoverdistance=80,
        spikedistance=1000,
        newshape={
            "line": {
                "color": tokens["shape_line"],
                "width": 2.5,
            }
        },
        margin={"l": 64 if compact else 76, "r": right_margin, "t": top_margin, "b": bottom_margin},
        height=plot_height,
    )
    _apply_shape_contrast(fig, line_color=tokens["shape_line"])
    if for_export:
        fig.update_layout(width=DEFAULT_EXPORT_WIDTH, height=DEFAULT_EXPORT_HEIGHT)
    fig.update_xaxes(
        showgrid=bool(resolved["show_grid"]),
        showspikes=bool(resolved["show_spikes"] or debug_mode),
        spikecolor=tokens["axis"],
        spikethickness=1,
        spikedash="dot",
        spikemode="across",
        gridcolor=tokens["grid"],
        gridwidth=1,
        linecolor=tokens["axis"],
        zeroline=False,
        tickfont={"size": 11, "color": tokens["text"]},
        title_font={"size": 12, "color": tokens["text"], "family": FONT_FAMILY},
        automargin=True,
    )
    fig.update_yaxes(
        showgrid=bool(resolved["show_grid"]),
        showspikes=bool(resolved["show_spikes"] or debug_mode),
        spikecolor=tokens["axis"],
        spikethickness=1,
        spikedash="dot",
        spikemode="across",
        gridcolor=tokens["grid"],
        gridwidth=1,
        linecolor=tokens["axis"],
        zeroline=False,
        tickfont={"size": 11, "color": tokens["text"]},
        title_font={"size": 12, "color": tokens["text"], "family": FONT_FAMILY},
        automargin=True,
    )
    if resolved["x_range_enabled"] and resolved["x_min"] is not None and resolved["x_max"] is not None:
        x_range = [resolved["x_min"], resolved["x_max"]]
        if resolved["reverse_x_axis"]:
            x_range = list(reversed(x_range))
        fig.update_xaxes(range=x_range)
    elif resolved["reverse_x_axis"]:
        fig.update_xaxes(autorange="reversed")
    if resolved["y_range_enabled"] and resolved["y_min"] is not None and resolved["y_max"] is not None:
        fig.update_yaxes(range=[resolved["y_min"], resolved["y_max"]])
    fig.update_annotations(
        font={"size": 10.5 if compact else 11, "color": tokens["subtle_text"], "family": FONT_FAMILY},
        bgcolor=tokens["annotation_bg"],
        bordercolor=tokens["annotation_border"],
        borderwidth=0,
        borderpad=2,
    )
    if scale_traces:
        _scale_trace_styles(
            fig,
            line_width_scale=float(resolved["line_width_scale"]),
            marker_size_scale=float(resolved["marker_size_scale"]),
        )
    meta = getattr(fig.layout, "meta", None)
    next_meta = dict(meta) if isinstance(meta, dict) else {}
    next_meta["plot_display_settings"] = resolved
    next_meta["plot_view_mode"] = "debug" if debug_mode else "result"
    fig.update_layout(meta=next_meta)
    return fig


def extract_plot_display_settings(fig: go.Figure) -> dict[str, Any]:
    meta = getattr(fig.layout, "meta", None)
    if isinstance(meta, Mapping):
        return normalize_plot_display_settings(meta.get("plot_display_settings"))
    return normalize_plot_display_settings(None)
