"""Shared spectral plot display settings for FTIR/Raman Dash pages."""

from __future__ import annotations

from typing import Any, Mapping

import dash_bootstrap_components as dbc
from dash import dcc, html


_SPECTRAL_PLOT_FALLBACK = {
    "legend_mode": "auto",
    "compact": False,
    "show_grid": True,
    "show_spikes": True,
    "line_width_scale": 1.0,
    "marker_size_scale": 1.0,
    "export_scale": 2,
    "reverse_x_axis": True,
    "x_range_enabled": False,
    "x_min": None,
    "x_max": None,
    "y_range_enabled": False,
    "y_min": None,
    "y_max": None,
    "show_raw": True,
    "show_smoothed": True,
    "show_corrected": True,
    "show_normalized": True,
    "show_peaks": True,
}


def _bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value) if value not in (None, "") else fallback


def _float(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


def _int(value: Any, fallback: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_spectral_plot_settings(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    source = payload if isinstance(payload, Mapping) else {}
    settings = dict(_SPECTRAL_PLOT_FALLBACK)
    legend = str(source.get("legend_mode") or settings["legend_mode"]).strip().lower()
    settings["legend_mode"] = legend if legend in {"auto", "external", "compact", "hidden"} else "auto"
    for key in (
        "compact",
        "show_grid",
        "show_spikes",
        "reverse_x_axis",
        "x_range_enabled",
        "y_range_enabled",
        "show_raw",
        "show_smoothed",
        "show_corrected",
        "show_normalized",
        "show_peaks",
    ):
        settings[key] = _bool(source.get(key), bool(settings[key]))
    settings["line_width_scale"] = _float(source.get("line_width_scale"), 1.0, 0.6, 1.8)
    settings["marker_size_scale"] = _float(source.get("marker_size_scale"), 1.0, 0.6, 1.8)
    settings["export_scale"] = _int(source.get("export_scale"), 2, 1, 4)
    settings["x_min"] = _optional_float(source.get("x_min"))
    settings["x_max"] = _optional_float(source.get("x_max"))
    settings["y_min"] = _optional_float(source.get("y_min"))
    settings["y_max"] = _optional_float(source.get("y_max"))
    if (
        settings["x_range_enabled"]
        and settings["x_min"] is not None
        and settings["x_max"] is not None
        and settings["x_min"] > settings["x_max"]
    ):
        settings["x_min"], settings["x_max"] = settings["x_max"], settings["x_min"]
    if (
        settings["y_range_enabled"]
        and settings["y_min"] is not None
        and settings["y_max"] is not None
        and settings["y_min"] > settings["y_max"]
    ):
        settings["y_min"], settings["y_max"] = settings["y_max"], settings["y_min"]
    return settings


def spectral_plot_settings_from_controls(
    legend_mode,
    compact,
    show_grid,
    show_spikes,
    line_width_scale,
    marker_size_scale,
    export_scale,
    reverse_x_axis,
    show_raw,
    show_smoothed,
    show_corrected,
    show_normalized,
    show_peaks,
    x_range_enabled,
    x_min,
    x_max,
    y_range_enabled,
    y_min,
    y_max,
) -> dict[str, Any]:
    return normalize_spectral_plot_settings(
        {
            "legend_mode": legend_mode,
            "compact": compact,
            "show_grid": show_grid,
            "show_spikes": show_spikes,
            "line_width_scale": line_width_scale,
            "marker_size_scale": marker_size_scale,
            "export_scale": export_scale,
            "reverse_x_axis": reverse_x_axis,
            "show_raw": show_raw,
            "show_smoothed": show_smoothed,
            "show_corrected": show_corrected,
            "show_normalized": show_normalized,
            "show_peaks": show_peaks,
            "x_range_enabled": x_range_enabled,
            "x_min": x_min if x_range_enabled else None,
            "x_max": x_max if x_range_enabled else None,
            "y_range_enabled": y_range_enabled,
            "y_min": y_min if y_range_enabled else None,
            "y_max": y_max if y_range_enabled else None,
        }
    )


def build_spectral_plot_settings_card(id_prefix: str) -> dbc.Card:
    defaults = normalize_spectral_plot_settings(None)
    legend_options = [
        {"label": "Auto", "value": "auto"},
        {"label": "External Right", "value": "external"},
        {"label": "Compact", "value": "compact"},
        {"label": "Hidden", "value": "hidden"},
    ]
    return dbc.Card(
        dbc.CardBody(
            [
                html.H6(id=f"{id_prefix}-plot-card-title", className="card-title mb-1"),
                html.P(id=f"{id_prefix}-plot-card-hint", className="small text-muted mb-2"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id=f"{id_prefix}-plot-legend-mode-label", html_for=f"{id_prefix}-plot-legend-mode", className="mb-1"),
                                dbc.Select(id=f"{id_prefix}-plot-legend-mode", options=legend_options, value=defaults["legend_mode"]),
                            ],
                            md=4,
                        ),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-compact", value=defaults["compact"], label="Compact layout"), md=4),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-show-grid", value=defaults["show_grid"], label="Show grid"), md=4),
                    ],
                    className="g-2 align-items-end mb-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-show-spikes", value=defaults["show_spikes"], label="Show crosshair spikes"), md=4),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-reverse-x-axis", value=defaults["reverse_x_axis"], label="Reverse x-axis"), md=4),
                        dbc.Col(
                            [
                                dbc.Label(id=f"{id_prefix}-plot-export-scale-label", html_for=f"{id_prefix}-plot-export-scale", className="mb-1"),
                                dbc.Select(
                                    id=f"{id_prefix}-plot-export-scale",
                                    options=[{"label": str(v), "value": v} for v in (1, 2, 3, 4)],
                                    value=defaults["export_scale"],
                                ),
                            ],
                            md=4,
                        ),
                    ],
                    className="g-2 align-items-end mb-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id=f"{id_prefix}-plot-line-width-label", html_for=f"{id_prefix}-plot-line-width-scale", className="mb-1"),
                                dcc.Slider(id=f"{id_prefix}-plot-line-width-scale", min=0.6, max=1.8, step=0.1, value=defaults["line_width_scale"], marks=None, tooltip={"placement": "bottom"}),
                            ],
                            md=6,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id=f"{id_prefix}-plot-marker-size-label", html_for=f"{id_prefix}-plot-marker-size-scale", className="mb-1"),
                                dcc.Slider(id=f"{id_prefix}-plot-marker-size-scale", min=0.6, max=1.8, step=0.1, value=defaults["marker_size_scale"], marks=None, tooltip={"placement": "bottom"}),
                            ],
                            md=6,
                        ),
                    ],
                    className="g-2 mb-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-show-raw", value=defaults["show_raw"], label="Show raw trace"), md=4),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-show-smoothed", value=defaults["show_smoothed"], label="Show smoothed trace"), md=4),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-show-corrected", value=defaults["show_corrected"], label="Show corrected trace"), md=4),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-show-normalized", value=defaults["show_normalized"], label="Show normalized trace"), md=4),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-show-peaks", value=defaults["show_peaks"], label="Show peak markers"), md=4),
                    ],
                    className="g-2 mb-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-x-range-enabled", value=False, label="Lock X range"), md=4),
                        dbc.Col(dbc.Input(id=f"{id_prefix}-plot-x-min", type="number", placeholder="X min"), md=4),
                        dbc.Col(dbc.Input(id=f"{id_prefix}-plot-x-max", type="number", placeholder="X max"), md=4),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-y-range-enabled", value=False, label="Lock Y range"), md=4),
                        dbc.Col(dbc.Input(id=f"{id_prefix}-plot-y-min", type="number", placeholder="Y min"), md=4),
                        dbc.Col(dbc.Input(id=f"{id_prefix}-plot-y-max", type="number", placeholder="Y max"), md=4),
                    ],
                    className="g-2",
                ),
            ]
        ),
        className="mb-3",
    )


def build_plotly_config(settings: Mapping[str, Any] | None, *, filename: str | None = None) -> dict[str, Any]:
    resolved = normalize_spectral_plot_settings(settings)
    opts: dict[str, Any] = {"format": "png", "filename": filename or "materialscope_spectrum", "scale": resolved["export_scale"]}
    return {"displaylogo": False, "responsive": True, "toImageButtonOptions": opts}


def spectral_legend_layout(trace_count: int, settings: Mapping[str, Any], *, theme: Mapping[str, str], legend_bg: str) -> tuple[bool, dict[str, Any]]:
    mode = str(settings.get("legend_mode") or "auto")
    if mode == "hidden":
        return False, {}
    if mode == "external" or mode == "compact" or (mode == "auto" and trace_count >= 5):
        return True, {
            "orientation": "v",
            "yanchor": "top",
            "y": 1.0,
            "xanchor": "left",
            "x": 1.02,
            "bgcolor": legend_bg,
            "bordercolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "font": {"size": 10 if settings.get("compact") else 11, "color": theme["text"]},
        }
    return True, {
        "orientation": "h",
        "yanchor": "bottom",
        "y": 1.02,
        "xanchor": "left",
        "x": 0,
        "bgcolor": legend_bg,
        "bordercolor": theme["grid"],
        "borderwidth": 1,
        "font": {"size": 11 if settings.get("compact") else 12, "color": theme["text"]},
    }
