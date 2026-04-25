"""Plotly figure builder for XRD Dash results (curves + peak markers + optional match overlay)."""

from __future__ import annotations

import math
from typing import Any, Mapping

import plotly.graph_objects as go

from core.plotting import apply_materialscope_plot_theme
from utils.i18n import translate_ui

_XRD_MATCH_STYLE = {
    "matched_observed": {"color": "#22C55E", "symbol": "diamond"},
    "unmatched_observed": {"color": "#EF4444", "symbol": "x"},
    "matched_reference": {"color": "#2563EB", "symbol": "square"},
    "unmatched_reference": {"color": "#F59E0B", "symbol": "triangle-up"},
}

_XRD_PLOT_FALLBACK = {
    "show_peak_labels": True,
    "label_density_mode": "smart",
    "max_labels": 8,
    "min_label_intensity_ratio": 0.12,
    "marker_size": 8,
    "label_position_precision": 2,
    "label_intensity_precision": 0,
    "show_matched_peaks": False,
    "show_unmatched_observed": False,
    "show_unmatched_reference": False,
    "show_match_connectors": False,
    "show_match_labels": False,
    "show_intermediate_traces": False,
    "style_preset": "color_shape",
    "x_range_enabled": False,
    "x_min": None,
    "x_max": None,
    "y_range_enabled": False,
    "y_min": None,
    "y_max": None,
    "log_y": False,
    "line_width": 2.0,
}


def _coerce_plot_bool(value, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value) if value not in (None, "") else fallback


def _coerce_plot_int(value, fallback: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


def _coerce_plot_float(value, fallback: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


def _coerce_optional_plot_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_xrd_plot_settings(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    source = payload if isinstance(payload, Mapping) else {}
    settings = dict(_XRD_PLOT_FALLBACK)
    settings["show_peak_labels"] = _coerce_plot_bool(source.get("show_peak_labels"), settings["show_peak_labels"])
    label_density = str(source.get("label_density_mode") or settings["label_density_mode"]).strip().lower()
    settings["label_density_mode"] = label_density if label_density in {"smart", "all", "selected"} else "smart"
    settings["max_labels"] = _coerce_plot_int(source.get("max_labels"), settings["max_labels"], 1, 60)
    settings["min_label_intensity_ratio"] = _coerce_plot_float(
        source.get("min_label_intensity_ratio"),
        settings["min_label_intensity_ratio"],
        0.0,
        1.0,
    )
    settings["marker_size"] = _coerce_plot_int(source.get("marker_size"), settings["marker_size"], 4, 20)
    settings["label_position_precision"] = _coerce_plot_int(
        source.get("label_position_precision"),
        settings["label_position_precision"],
        1,
        5,
    )
    settings["label_intensity_precision"] = _coerce_plot_int(
        source.get("label_intensity_precision"),
        settings["label_intensity_precision"],
        0,
        4,
    )
    settings["show_matched_peaks"] = _coerce_plot_bool(source.get("show_matched_peaks"), settings["show_matched_peaks"])
    settings["show_unmatched_observed"] = _coerce_plot_bool(
        source.get("show_unmatched_observed"),
        settings["show_unmatched_observed"],
    )
    settings["show_unmatched_reference"] = _coerce_plot_bool(
        source.get("show_unmatched_reference"),
        settings["show_unmatched_reference"],
    )
    settings["show_match_connectors"] = _coerce_plot_bool(
        source.get("show_match_connectors"),
        settings["show_match_connectors"],
    )
    settings["show_match_labels"] = _coerce_plot_bool(source.get("show_match_labels"), settings["show_match_labels"])
    settings["show_intermediate_traces"] = _coerce_plot_bool(
        source.get("show_intermediate_traces"),
        settings.get("show_intermediate_traces", False),
    )
    style_preset = str(source.get("style_preset") or settings["style_preset"]).strip().lower()
    settings["style_preset"] = style_preset if style_preset in {"color_shape", "color_only", "shape_only"} else "color_shape"
    settings["x_range_enabled"] = _coerce_plot_bool(source.get("x_range_enabled"), settings["x_range_enabled"])
    settings["x_min"] = _coerce_optional_plot_float(source.get("x_min"))
    settings["x_max"] = _coerce_optional_plot_float(source.get("x_max"))
    if (
        settings["x_range_enabled"]
        and settings["x_min"] is not None
        and settings["x_max"] is not None
        and settings["x_min"] > settings["x_max"]
    ):
        settings["x_min"], settings["x_max"] = settings["x_max"], settings["x_min"]
    settings["y_range_enabled"] = _coerce_plot_bool(source.get("y_range_enabled"), settings["y_range_enabled"])
    settings["y_min"] = _coerce_optional_plot_float(source.get("y_min"))
    settings["y_max"] = _coerce_optional_plot_float(source.get("y_max"))
    if (
        settings["y_range_enabled"]
        and settings["y_min"] is not None
        and settings["y_max"] is not None
        and settings["y_min"] > settings["y_max"]
    ):
        settings["y_min"], settings["y_max"] = settings["y_max"], settings["y_min"]
    settings["log_y"] = _coerce_plot_bool(source.get("log_y"), settings["log_y"])
    settings["line_width"] = _coerce_plot_float(source.get("line_width"), float(settings["line_width"]), 0.8, 5.0)
    return settings


def _shared_display_settings_from_xrd(settings: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "legend_mode": "auto",
        "compact": False,
        "show_grid": True,
        "show_spikes": True,
        "line_width_scale": 1.0,
        "marker_size_scale": 1.0,
        "export_scale": 2,
        "reverse_x_axis": False,
        "x_range_enabled": bool(settings.get("x_range_enabled")),
        "x_min": settings.get("x_min"),
        "x_max": settings.get("x_max"),
        "y_range_enabled": bool(settings.get("y_range_enabled")) and not bool(settings.get("log_y")),
        "y_min": settings.get("y_min"),
        "y_max": settings.get("y_max"),
    }


def _reference_marker_y(value: Any, observed_max_intensity: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 0.0
    if parsed <= 1.5:
        return max(parsed * max(observed_max_intensity, 1.0), 0.0)
    return max(parsed, 0.0)


def _xrd_match_marker_style(kind: str, settings: Mapping[str, Any]) -> dict[str, Any]:
    base = dict(_XRD_MATCH_STYLE.get(kind) or {"color": "#94A3B8", "symbol": "circle"})
    style_preset = str(settings.get("style_preset") or "color_shape").lower()
    if style_preset == "color_only":
        base["symbol"] = "circle"
    elif style_preset == "shape_only":
        base["color"] = "#CBD5E1"
    return base


def _xrd_peak_label(position: float, intensity: float, *, settings: Mapping[str, Any], lang: str) -> str:
    pos_precision = int(settings.get("label_position_precision", 2))
    intensity_precision = int(settings.get("label_intensity_precision", 0))
    angle_unit = "°" if lang == "tr" else " deg"
    return f"{position:.{pos_precision}f}{angle_unit} | I={intensity:.{intensity_precision}f}"


def _pick_peak_label_indices(peaks: list[dict[str, float]], settings: Mapping[str, Any]) -> set[int]:
    if not peaks or not bool(settings.get("show_peak_labels", True)):
        return set()

    label_mode = str(settings.get("label_density_mode") or "smart").lower()
    if label_mode == "selected":
        label_mode = "smart"

    max_labels = int(settings.get("max_labels", 10))
    if max_labels <= 0:
        return set()

    intensities = [max(float(item.get("intensity", 0.0)), 0.0) for item in peaks]
    max_intensity = max(intensities) if intensities else 0.0
    ratio_threshold = float(settings.get("min_label_intensity_ratio", 0.12))
    threshold = max_intensity * max(ratio_threshold, 0.0)

    ranked_indices = sorted(
        range(len(peaks)),
        key=lambda idx: (
            -float(peaks[idx].get("intensity", 0.0)),
            float(peaks[idx].get("position", 0.0)),
        ),
    )
    chosen: set[int] = set()
    if label_mode == "all":
        for idx in ranked_indices[:max_labels]:
            chosen.add(idx)
        return chosen

    for idx in ranked_indices:
        if float(peaks[idx].get("intensity", 0.0)) >= threshold:
            chosen.add(idx)
        if len(chosen) >= max_labels:
            break
    if not chosen:
        for idx in ranked_indices[:max_labels]:
            chosen.add(idx)
    return chosen


def build_xrd_result_figure(
    *,
    axis: list[float],
    raw_signal: list[float],
    smoothed: list[float],
    baseline: list[float],
    corrected: list[float],
    peaks: list[dict[str, Any]],
    selected_match: dict[str, Any] | None,
    plot_settings: Mapping[str, Any] | None,
    ui_theme: str | None,
    loc: str,
    sample_name: str,
    axis_title: str,
) -> go.Figure:
    settings = normalize_xrd_plot_settings(plot_settings)
    line_width = float(settings.get("line_width", 2.0))
    line_primary = "#1C1A1A" if ui_theme != "dark" else "#EEEDEA"

    has_corrected = bool(corrected and len(corrected) == len(axis))
    has_smoothed = bool(smoothed and len(smoothed) == len(axis))
    has_raw = bool(raw_signal and len(raw_signal) == len(axis))
    has_baseline = bool(baseline and len(baseline) == len(axis))
    primary_signal = corrected if has_corrected else smoothed if has_smoothed else raw_signal

    legend_raw = translate_ui(loc, "dash.analysis.figure.legend_raw_diffractogram")
    legend_smooth = translate_ui(loc, "dash.analysis.figure.legend_smoothed_diffractogram")
    legend_corr = translate_ui(loc, "dash.analysis.figure.legend_corrected_diffractogram")
    primary_name = legend_corr if has_corrected else legend_smooth if has_smoothed else legend_raw
    has_overlay = has_corrected or has_smoothed

    fig = go.Figure()
    show_intermediate = bool(settings.get("show_intermediate_traces"))
    if has_raw:
        fig.add_trace(
            go.Scatter(
                x=axis,
                y=raw_signal,
                mode="lines",
                name=legend_raw,
                line=dict(color="#94A3B8", width=max(0.8, line_width - 0.4)),
                opacity=0.35 if has_overlay else 0.95,
                showlegend=bool(show_intermediate) or not has_overlay,
            )
        )
    if show_intermediate and has_smoothed:
        fig.add_trace(
            go.Scatter(
                x=axis,
                y=smoothed,
                mode="lines",
                name=legend_smooth,
                line=dict(color="#0369A1", width=max(1.0, line_width - 0.2)),
                opacity=0.85 if has_corrected else 1.0,
            )
        )
    if show_intermediate and has_baseline:
        fig.add_trace(
            go.Scatter(
                x=axis,
                y=baseline,
                mode="lines",
                name=translate_ui(loc, "dash.analysis.figure.legend_baseline"),
                line=dict(color="#6D28D9", width=max(0.9, line_width - 0.8), dash="dash"),
                opacity=0.7,
            )
        )

    fig.add_trace(
        go.Scatter(
            x=axis,
            y=primary_signal,
            mode="lines",
            name=primary_name,
            line=dict(color=line_primary, width=line_width + 1.0),
        )
    )

    peak_x: list[float] = []
    peak_y: list[float] = []
    peak_text: list[str] = []
    if peaks:
        label_indices = _pick_peak_label_indices(peaks, settings)
        peak_x = [float(item.get("position", 0.0)) for item in peaks]
        peak_y = [float(item.get("intensity", 0.0)) for item in peaks]
        peak_text = [
            _xrd_peak_label(peak_x[idx], peak_y[idx], settings=settings, lang=loc) if idx in label_indices else ""
            for idx in range(len(peaks))
        ]
        fig.add_trace(
            go.Scatter(
                x=peak_x,
                y=peak_y,
                mode="markers",
                name=translate_ui(loc, "dash.analysis.xrd.figure.peaks"),
                marker=dict(color="#D97706", size=int(settings.get("marker_size", 8)), symbol="diamond"),
            )
        )

    subtitle = None
    if selected_match:
        evidence = dict((selected_match.get("evidence") or {}))
        matched_pairs = [item for item in (evidence.get("matched_peak_pairs") or []) if isinstance(item, Mapping)]
        unmatched_observed = [item for item in (evidence.get("unmatched_observed_peaks") or []) if isinstance(item, Mapping)]
        unmatched_reference = [item for item in (evidence.get("unmatched_reference_peaks") or []) if isinstance(item, Mapping)]

        cand = (
            str(selected_match.get("display_name_unicode") or "").strip()
            or str(selected_match.get("display_name") or "").strip()
            or str(selected_match.get("candidate_name") or "").strip()
            or translate_ui(loc, "dash.analysis.xrd.candidate_unknown")
        )
        subtitle = translate_ui(loc, "dash.analysis.xrd.figure.selected_candidate", name=cand)

        observed_max = max([float(item.get("intensity", 0.0)) for item in peaks] + [1.0])

        if settings.get("show_match_connectors") and matched_pairs:
            for pair in matched_pairs:
                try:
                    obs_x = float(pair.get("observed_position"))
                    obs_y = float(pair.get("observed_intensity"))
                    ref_x = float(pair.get("reference_position"))
                    ref_y = _reference_marker_y(pair.get("reference_intensity"), observed_max)
                except (TypeError, ValueError):
                    continue
                fig.add_shape(
                    type="line",
                    x0=obs_x,
                    y0=obs_y,
                    x1=ref_x,
                    y1=ref_y,
                    line=dict(color="rgba(148, 163, 184, 0.55)", width=1.0, dash="dot"),
                )

        if settings.get("show_matched_peaks") and matched_pairs:
            mo_style = _xrd_match_marker_style("matched_observed", settings)
            mr_style = _xrd_match_marker_style("matched_reference", settings)
            matched_text = (
                [
                    f"Δ2θ={float(item.get('delta_position') or 0.0):.3f}"
                    for item in matched_pairs
                ]
                if settings.get("show_match_labels")
                else None
            )
            fig.add_trace(
                go.Scatter(
                    x=[float(item.get("observed_position", 0.0)) for item in matched_pairs],
                    y=[float(item.get("observed_intensity", 0.0)) for item in matched_pairs],
                    mode="markers+text" if matched_text else "markers",
                    name=translate_ui(loc, "dash.analysis.xrd.figure.matched_observed"),
                    marker=dict(
                        color=mo_style["color"],
                        size=int(settings.get("marker_size", 8)) + 1,
                        symbol=mo_style["symbol"],
                        line=dict(width=1, color="#052E16"),
                    ),
                    text=matched_text,
                    textposition="top center",
                    textfont=dict(size=9.5, color="#3F5E4B"),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=[float(item.get("reference_position", 0.0)) for item in matched_pairs],
                    y=[_reference_marker_y(item.get("reference_intensity"), observed_max) for item in matched_pairs],
                    mode="markers",
                    name=translate_ui(loc, "dash.analysis.xrd.figure.matched_reference"),
                    marker=dict(
                        color=mr_style["color"],
                        size=int(settings.get("marker_size", 8)),
                        symbol=mr_style["symbol"],
                    ),
                )
            )

        if settings.get("show_unmatched_observed") and unmatched_observed:
            uo_style = _xrd_match_marker_style("unmatched_observed", settings)
            fig.add_trace(
                go.Scatter(
                    x=[float(item.get("position", 0.0)) for item in unmatched_observed],
                    y=[float(item.get("intensity", 0.0)) for item in unmatched_observed],
                    mode="markers",
                    name=translate_ui(loc, "dash.analysis.xrd.figure.unmatched_observed"),
                    marker=dict(
                        color=uo_style["color"],
                        size=int(settings.get("marker_size", 8)),
                        symbol=uo_style["symbol"],
                    ),
                )
            )

        if settings.get("show_unmatched_reference") and unmatched_reference:
            ur_style = _xrd_match_marker_style("unmatched_reference", settings)
            ref_y = [_reference_marker_y(item.get("intensity"), observed_max) for item in unmatched_reference]
            fig.add_trace(
                go.Scatter(
                    x=[float(item.get("position", 0.0)) for item in unmatched_reference],
                    y=ref_y,
                    mode="markers",
                    name=translate_ui(loc, "dash.analysis.xrd.figure.unmatched_reference"),
                    marker=dict(
                        color=ur_style["color"],
                        size=int(settings.get("marker_size", 8)),
                        symbol=ur_style["symbol"],
                    ),
                )
            )

    if any(peak_text):
        fig.add_trace(
            go.Scatter(
                x=peak_x,
                y=peak_y,
                mode="text",
                text=peak_text,
                textposition="top center",
                textfont=dict(size=10.5, color="#475569"),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    title_main = translate_ui(loc, "dash.analysis.figure.title_xrd_main")
    subtitle_parts = [sample_name]
    if subtitle:
        subtitle_parts.append(subtitle)
    apply_materialscope_plot_theme(
        fig,
        _shared_display_settings_from_xrd(settings),
        theme=ui_theme,
        title=title_main,
        subtitle=" | ".join(part for part in subtitle_parts if part),
        view_mode="result",
        scale_traces=False,
    )
    fig.update_xaxes(title_text=axis_title)
    fig.update_yaxes(title_text=translate_ui(loc, "dash.analysis.figure.axis_intensity_au"))

    x_min = settings.get("x_min")
    x_max = settings.get("x_max")
    if settings.get("x_range_enabled") and x_min is not None and x_max is not None:
        fig.update_xaxes(range=[float(x_min), float(x_max)])
    else:
        fig.update_xaxes(autorange=True)

    y_min = settings.get("y_min")
    y_max = settings.get("y_max")
    if settings.get("log_y"):
        fig.update_yaxes(type="log")
        if settings.get("y_range_enabled") and y_min is not None and y_max is not None:
            fig.update_yaxes(
                range=[math.log10(max(float(y_min), 1e-6)), math.log10(max(float(y_max), 1e-6))]
            )
    else:
        fig.update_yaxes(type="linear")
        if settings.get("y_range_enabled") and y_min is not None and y_max is not None:
            fig.update_yaxes(range=[float(y_min), float(y_max)])

    return fig
