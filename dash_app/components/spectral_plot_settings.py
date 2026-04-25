"""Shared spectral plot display settings for FTIR/Raman Dash pages."""

from __future__ import annotations

from typing import Any, Mapping

import dash_bootstrap_components as dbc
from dash import dcc, html

from core.plotting import build_plotly_config as build_shared_plotly_config
from core.plotting import legend_layout as shared_legend_layout
from core.plotting import normalize_plot_display_settings
from utils.i18n import normalize_ui_locale, translate_ui


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

_SPECTRAL_PLOT_I18N_PREFIX = "dash.analysis.spectral_plot"
_LEGEND_OPTION_KEYS = (
    ("auto", "legend_auto"),
    ("external", "legend_external_right"),
    ("compact", "legend_compact"),
    ("hidden", "legend_hidden"),
)


def spectral_plot_settings_chrome(locale: str | None) -> dict[str, Any]:
    loc = normalize_ui_locale(locale)
    pfx = _SPECTRAL_PLOT_I18N_PREFIX
    return {
        "card_title": translate_ui(loc, f"{pfx}.card_title"),
        "card_hint": translate_ui(loc, f"{pfx}.card_hint"),
        "legend_label": translate_ui(loc, f"{pfx}.legend"),
        "legend_options": [
            {"label": translate_ui(loc, f"{pfx}.{key}"), "value": value}
            for value, key in _LEGEND_OPTION_KEYS
        ],
        "compact_label": translate_ui(loc, f"{pfx}.compact"),
        "show_grid_label": translate_ui(loc, f"{pfx}.show_grid"),
        "show_spikes_label": translate_ui(loc, f"{pfx}.show_spikes"),
        "reverse_x_axis_label": translate_ui(loc, f"{pfx}.reverse_x_axis"),
        "export_scale_label": translate_ui(loc, f"{pfx}.export_scale"),
        "line_width_label": translate_ui(loc, f"{pfx}.line_width"),
        "marker_size_label": translate_ui(loc, f"{pfx}.marker_size"),
        "show_raw_label": translate_ui(loc, f"{pfx}.show_raw"),
        "show_smoothed_label": translate_ui(loc, f"{pfx}.show_smoothed"),
        "show_corrected_label": translate_ui(loc, f"{pfx}.show_corrected"),
        "show_normalized_label": translate_ui(loc, f"{pfx}.show_normalized"),
        "show_peaks_label": translate_ui(loc, f"{pfx}.show_peaks"),
        "x_lock_label": translate_ui(loc, f"{pfx}.x_lock"),
        "y_lock_label": translate_ui(loc, f"{pfx}.y_lock"),
        "x_min_placeholder": translate_ui(loc, f"{pfx}.x_min"),
        "x_max_placeholder": translate_ui(loc, f"{pfx}.x_max"),
        "y_min_placeholder": translate_ui(loc, f"{pfx}.y_min"),
        "y_max_placeholder": translate_ui(loc, f"{pfx}.y_max"),
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
    settings = normalize_plot_display_settings(source, defaults=_SPECTRAL_PLOT_FALLBACK)
    for key in ("show_raw", "show_smoothed", "show_corrected", "show_normalized", "show_peaks"):
        settings[key] = _bool(source.get(key), bool(settings[key]))
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
    chrome = spectral_plot_settings_chrome("en")
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
                                dbc.Select(id=f"{id_prefix}-plot-legend-mode", options=chrome["legend_options"], value=defaults["legend_mode"]),
                            ],
                            md=4,
                        ),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-compact", value=defaults["compact"], label=chrome["compact_label"]), md=4),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-show-grid", value=defaults["show_grid"], label=chrome["show_grid_label"]), md=4),
                    ],
                    className="g-2 align-items-end mb-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-show-spikes", value=defaults["show_spikes"], label=chrome["show_spikes_label"]), md=4),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-reverse-x-axis", value=defaults["reverse_x_axis"], label=chrome["reverse_x_axis_label"]), md=4),
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
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-show-raw", value=defaults["show_raw"], label=chrome["show_raw_label"]), md=4),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-show-smoothed", value=defaults["show_smoothed"], label=chrome["show_smoothed_label"]), md=4),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-show-corrected", value=defaults["show_corrected"], label=chrome["show_corrected_label"]), md=4),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-show-normalized", value=defaults["show_normalized"], label=chrome["show_normalized_label"]), md=4),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-show-peaks", value=defaults["show_peaks"], label=chrome["show_peaks_label"]), md=4),
                    ],
                    className="g-2 mb-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-x-range-enabled", value=defaults["x_range_enabled"], label=chrome["x_lock_label"]), md=4),
                        dbc.Col(dbc.Input(id=f"{id_prefix}-plot-x-min", type="number", placeholder=chrome["x_min_placeholder"]), md=4),
                        dbc.Col(dbc.Input(id=f"{id_prefix}-plot-x-max", type="number", placeholder=chrome["x_max_placeholder"]), md=4),
                        dbc.Col(dbc.Checkbox(id=f"{id_prefix}-plot-y-range-enabled", value=defaults["y_range_enabled"], label=chrome["y_lock_label"]), md=4),
                        dbc.Col(dbc.Input(id=f"{id_prefix}-plot-y-min", type="number", placeholder=chrome["y_min_placeholder"]), md=4),
                        dbc.Col(dbc.Input(id=f"{id_prefix}-plot-y-max", type="number", placeholder=chrome["y_max_placeholder"]), md=4),
                    ],
                    className="g-2",
                ),
            ]
        ),
        className="mb-3",
    )


def build_plotly_config(settings: Mapping[str, Any] | None, *, filename: str | None = None) -> dict[str, Any]:
    return build_shared_plotly_config(
        normalize_spectral_plot_settings(settings),
        filename=filename or "materialscope_spectrum",
    )


def spectral_legend_layout(trace_count: int, settings: Mapping[str, Any], *, theme: Mapping[str, str], legend_bg: str) -> tuple[bool, dict[str, Any]]:
    show, legend = shared_legend_layout(trace_count, normalize_spectral_plot_settings(settings))
    if legend:
        legend["bgcolor"] = legend_bg
        legend["font"] = dict(legend.get("font") or {}, color=theme["text"])
    return show, legend
