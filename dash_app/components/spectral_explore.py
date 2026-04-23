"""Shared raw-data exploration helpers for spectral Dash pages."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from dash import html

from utils.i18n import translate_ui


def downsample_spectral_rows(rows: list[dict[str, Any]], columns: list[str], max_points: int = 6000) -> tuple[np.ndarray, np.ndarray]:
    """Extract spectral axis and signal arrays from workspace rows."""
    if not rows:
        return np.array([]), np.array([])
    axis_key = "temperature" if "temperature" in columns else "wavenumber" if "wavenumber" in columns else None
    signal_key = "signal" if "signal" in columns else None
    if axis_key is None or signal_key is None:
        return np.array([]), np.array([])

    axis_vals: list[float] = []
    signal_vals: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            av = float(row.get(axis_key))
            sv = float(row.get(signal_key))
        except (TypeError, ValueError):
            continue
        if math.isfinite(av) and math.isfinite(sv):
            axis_vals.append(av)
            signal_vals.append(sv)

    axis = np.asarray(axis_vals, dtype=float)
    signal = np.asarray(signal_vals, dtype=float)
    n = len(axis)
    if n <= max_points or n == 0:
        return axis, signal
    step = int(math.ceil(n / max_points))
    return axis[::step], signal[::step]


def compute_spectral_raw_quality_stats(
    axis: np.ndarray,
    signal: np.ndarray,
    *,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pre-run spectral data stats and hints without Streamlit dependencies."""
    out: dict[str, Any] = {"warnings": [], "hints": [], "checks": {}, "validation_messages": []}
    val = validation if isinstance(validation, dict) else {}
    checks = val.get("checks") if isinstance(val.get("checks"), dict) else {}
    out["checks"] = dict(checks)

    for key in ("warnings", "issues"):
        for item in val.get(key) or []:
            if isinstance(item, str) and item.strip():
                out["validation_messages"].append(item.strip())

    if axis.size == 0 or signal.size == 0 or axis.size != signal.size:
        out["warnings"] = ["missing_series"]
        return out

    a = axis.astype(float)
    s = signal.astype(float)
    valid_mask = np.isfinite(a) & np.isfinite(s)
    missing = int(len(a) - np.sum(valid_mask))
    a = a[valid_mask]
    s = s[valid_mask]
    n = int(a.size)
    out["point_count"] = n
    out["missing_count"] = missing
    if n < 2:
        out["warnings"] = ["too_few_points"]
        return out

    out["axis_min"] = float(a.min())
    out["axis_max"] = float(a.max())
    out["signal_min"] = float(s.min())
    out["signal_max"] = float(s.max())

    da = np.diff(a)
    pos = int(np.sum(da > 0))
    neg = int(np.sum(da < 0))
    zero = int(np.sum(da == 0))
    dom = max(pos, neg, zero)
    if dom < len(da) * 0.85:
        out["hints"].append("axis_non_monotonic")
    elif neg > pos:
        out["hints"].append("axis_mostly_decreasing")
    elif pos > neg:
        out["hints"].append("axis_mostly_increasing")

    nonzero_spacing = np.abs(da[np.abs(da) > 1e-12])
    if nonzero_spacing.size > 1:
        spacing_cv = float(np.std(nonzero_spacing) / max(abs(float(np.mean(nonzero_spacing))), 1e-12))
    else:
        spacing_cv = 0.0
    out["spacing_cv"] = spacing_cv
    if spacing_cv > 0.15:
        out["hints"].append("irregular_spacing")
    elif spacing_cv > 0.05:
        out["hints"].append("somewhat_irregular_spacing")

    if n > 2 and float(np.ptp(s)) > 1e-12:
        coeffs = np.polyfit(np.arange(n), s, 1)
        drift = abs(float(coeffs[0])) * n / float(np.ptp(s))
    else:
        drift = 0.0
    out["baseline_drift"] = drift
    if drift > 0.5:
        out["hints"].append("strong_baseline_drift")
    elif drift > 0.2:
        out["hints"].append("moderate_baseline_drift")
    return out


def build_spectral_raw_quality_panel(
    stats: dict[str, Any],
    loc: str,
    *,
    i18n_prefix: str,
    signal_unit: str,
) -> html.Div:
    """Render raw spectral quality stats with modality-owned copy."""
    first_warning = (stats.get("warnings") or [None])[0]
    if first_warning in {"missing_series", "too_few_points"}:
        return html.Div(
            html.P(translate_ui(loc, f"{i18n_prefix}.empty_{first_warning}"), className="text-muted small mb-0"),
            className="ms-spectral-raw-quality-inner",
        )

    lines: list[Any] = [html.Li(translate_ui(loc, f"{i18n_prefix}.stat_points", n=int(stats.get("point_count") or 0)))]
    if stats.get("axis_min") is not None and stats.get("axis_max") is not None:
        lines.append(
            html.Li(
                translate_ui(
                    loc,
                    f"{i18n_prefix}.stat_axis_range",
                    a0=float(stats["axis_min"]),
                    a1=float(stats["axis_max"]),
                )
            )
        )
    if stats.get("signal_min") is not None and stats.get("signal_max") is not None:
        lines.append(
            html.Li(
                translate_ui(
                    loc,
                    f"{i18n_prefix}.stat_signal_range",
                    s0=float(stats["signal_min"]),
                    s1=float(stats["signal_max"]),
                    u=signal_unit,
                )
            )
        )
    lines.append(html.Li(translate_ui(loc, f"{i18n_prefix}.stat_missing", n=int(stats.get("missing_count") or 0))))
    lines.append(html.Li(translate_ui(loc, f"{i18n_prefix}.stat_baseline_drift", drift=f"{float(stats.get('baseline_drift') or 0):.3f}")))
    lines.append(html.Li(translate_ui(loc, f"{i18n_prefix}.stat_spacing_cv", cv=f"{float(stats.get('spacing_cv') or 0):.3f}")))

    hint_items = [
        html.Li(translate_ui(loc, f"{i18n_prefix}.hint.{str(h)}"), className="small")
        for h in (stats.get("hints") or [])
    ]
    warn_items = [html.Li(str(msg), className="small text-warning") for msg in (stats.get("validation_messages") or [])]

    return html.Div(
        [
            html.Ul(lines, className="small mb-2 ps-3"),
            html.Ul(hint_items, className="small mb-2 ps-3 text-muted") if hint_items else None,
            html.Ul(warn_items, className="small mb-0 ps-3") if warn_items else None,
        ],
        className="ms-spectral-raw-quality-inner",
    )
