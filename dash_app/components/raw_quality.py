"""Shared raw-data quality helpers for Dash analysis setup cards."""

from __future__ import annotations

import math
from typing import Any

from dash import html

from utils.i18n import translate_ui


def extract_xy_series(
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    axis_candidates: tuple[str, ...],
    signal_candidates: tuple[str, ...] = ("signal",),
    max_points: int = 6000,
) -> tuple[list[float], list[float]]:
    """Extract finite x/y vectors from workspace rows using known column aliases."""
    if not rows:
        return [], []
    available = set(columns or [])
    axis_key = next((key for key in axis_candidates if key in available), None)
    signal_key = next((key for key in signal_candidates if key in available), None)
    if axis_key is None or signal_key is None:
        return [], []

    axis: list[float] = []
    signal: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            av = float(row.get(axis_key))
            sv = float(row.get(signal_key))
        except (TypeError, ValueError):
            continue
        if math.isfinite(av) and math.isfinite(sv):
            axis.append(av)
            signal.append(sv)

    n = len(axis)
    if n <= max_points or n == 0:
        return axis, signal
    step = int(math.ceil(n / max_points))
    return axis[::step], signal[::step]


def compute_raw_quality_stats(
    axis: list[float],
    signal: list[float],
    *,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build small pre-run quality stats and hints without backend analysis."""
    out: dict[str, Any] = {"warnings": [], "hints": [], "validation_messages": []}
    val = validation if isinstance(validation, dict) else {}
    for key in ("warnings", "issues"):
        for item in val.get(key) or []:
            if isinstance(item, str) and item.strip():
                out["validation_messages"].append(item.strip())

    if not axis or not signal or len(axis) != len(signal):
        out["warnings"] = ["missing_series"]
        return out

    pairs: list[tuple[float, float]] = []
    for x, y in zip(axis, signal):
        try:
            xf = float(x)
            yf = float(y)
        except (TypeError, ValueError):
            continue
        if math.isfinite(xf) and math.isfinite(yf):
            pairs.append((xf, yf))
    missing = len(axis) - len(pairs)
    out["missing_count"] = missing
    if len(pairs) < 2:
        out["warnings"] = ["too_few_points"]
        return out

    x_vals = [p[0] for p in pairs]
    y_vals = [p[1] for p in pairs]
    out["point_count"] = len(pairs)
    out["axis_min"] = min(x_vals)
    out["axis_max"] = max(x_vals)
    out["signal_min"] = min(y_vals)
    out["signal_max"] = max(y_vals)

    dx = [b - a for a, b in zip(x_vals, x_vals[1:])]
    pos = sum(1 for item in dx if item > 0)
    neg = sum(1 for item in dx if item < 0)
    zero = sum(1 for item in dx if item == 0)
    if dx and max(pos, neg, zero) < len(dx) * 0.85:
        out["hints"].append("axis_non_monotonic")
    elif neg > pos:
        out["hints"].append("axis_mostly_decreasing")

    spacing = [abs(item) for item in dx if abs(item) > 1e-12]
    if len(spacing) > 1:
        mean = sum(spacing) / len(spacing)
        variance = sum((item - mean) ** 2 for item in spacing) / len(spacing)
        spacing_cv = math.sqrt(variance) / max(abs(mean), 1e-12)
    else:
        spacing_cv = 0.0
    out["spacing_cv"] = spacing_cv
    if spacing_cv > 0.15:
        out["hints"].append("irregular_spacing")
    elif spacing_cv > 0.05:
        out["hints"].append("somewhat_irregular_spacing")

    signal_range = max(y_vals) - min(y_vals)
    if signal_range > 1e-12:
        edge = max(1, len(y_vals) // 20)
        start_mean = sum(y_vals[:edge]) / edge
        end_mean = sum(y_vals[-edge:]) / edge
        drift = abs(end_mean - start_mean) / signal_range
    else:
        drift = 0.0
    out["edge_drift"] = drift
    if drift > 0.5:
        out["hints"].append("strong_edge_drift")
    elif drift > 0.2:
        out["hints"].append("moderate_edge_drift")
    return out


def build_raw_quality_panel(
    stats: dict[str, Any],
    loc: str,
    *,
    i18n_prefix: str,
    axis_unit: str,
    signal_unit: str,
) -> html.Div:
    first_warning = (stats.get("warnings") or [None])[0]
    if first_warning in {"missing_series", "too_few_points"}:
        return html.Div(
            html.P(translate_ui(loc, f"{i18n_prefix}.empty_{first_warning}"), className="text-muted small mb-0"),
            className="ms-raw-quality-inner",
        )

    lines: list[Any] = [
        html.Li(translate_ui(loc, f"{i18n_prefix}.stat_points", n=int(stats.get("point_count") or 0))),
        html.Li(
            translate_ui(
                loc,
                f"{i18n_prefix}.stat_axis_range",
                a0=float(stats.get("axis_min") or 0),
                a1=float(stats.get("axis_max") or 0),
                u=axis_unit,
            )
        ),
        html.Li(
            translate_ui(
                loc,
                f"{i18n_prefix}.stat_signal_range",
                s0=float(stats.get("signal_min") or 0),
                s1=float(stats.get("signal_max") or 0),
                u=signal_unit,
            )
        ),
        html.Li(translate_ui(loc, f"{i18n_prefix}.stat_missing", n=int(stats.get("missing_count") or 0))),
        html.Li(translate_ui(loc, f"{i18n_prefix}.stat_spacing_cv", cv=f"{float(stats.get('spacing_cv') or 0):.3f}")),
        html.Li(translate_ui(loc, f"{i18n_prefix}.stat_edge_drift", drift=f"{float(stats.get('edge_drift') or 0):.3f}")),
    ]
    hint_items = [html.Li(translate_ui(loc, f"{i18n_prefix}.hint.{str(h)}"), className="small") for h in (stats.get("hints") or [])]
    warn_items = [html.Li(str(msg), className="small text-warning") for msg in (stats.get("validation_messages") or [])]
    return html.Div(
        [
            html.Ul(lines, className="small mb-2 ps-3"),
            html.Ul(hint_items, className="small mb-2 ps-3 text-muted") if hint_items else None,
            html.Ul(warn_items, className="small mb-0 ps-3") if warn_items else None,
        ],
        className="ms-raw-quality-inner",
    )
