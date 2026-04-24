"""TGA Dash exploration helpers: raw-quality stats, step reference callouts, undo stacks.

Reuses Streamlit-side quality metrics computation where practical.
"""

from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np
from dash import html

from utils.i18n import translate_ui
from utils.reference_data import find_nearest_reference

MAX_TGA_UNDO_DEPTH = 25


def _compute_signal_quality_metrics(temperature: np.ndarray, signal: np.ndarray) -> dict[str, Any]:
    """Same logic as ``ui.components.quality_dashboard.compute_quality_metrics`` (no Streamlit)."""

    metrics: dict[str, Any] = {}

    nan_count = int(np.isnan(signal).sum() + np.isnan(temperature).sum())
    metrics["NaN Count"] = {
        "value": nan_count,
        "display": str(nan_count),
        "level": "green" if nan_count == 0 else "red",
    }

    mask = np.isfinite(temperature) & np.isfinite(signal)
    t = temperature[mask]
    s = signal[mask]

    if len(s) < 10:
        return metrics

    noise = float(np.std(np.diff(s)))
    nlevel = "green" if noise < 0.01 else "yellow" if noise < 0.1 else "red"
    metrics["Noise Level"] = {"value": noise, "display": f"{noise:.4f}", "level": nlevel}

    dt = np.diff(t)
    if len(dt) > 1 and np.mean(np.abs(dt)) > 1e-12:
        cv = float(np.std(dt) / np.abs(np.mean(dt)))
    else:
        cv = 0.0
    cvlevel = "green" if cv < 0.05 else "yellow" if cv < 0.15 else "red"
    metrics["Heating Rate CV"] = {"value": cv, "display": f"{cv:.4f}", "level": cvlevel}

    if len(s) > 2:
        coeffs = np.polyfit(np.arange(len(s)), s, 1)
        slope = abs(coeffs[0])
        sig_range = float(np.ptp(s)) or 1.0
        norm_drift = slope * len(s) / sig_range
    else:
        norm_drift = 0.0
    dlevel = "green" if norm_drift < 0.2 else "yellow" if norm_drift < 0.5 else "red"
    metrics["Baseline Drift"] = {"value": norm_drift, "display": f"{norm_drift:.3f}", "level": dlevel}

    win = max(5, len(s) // 50)
    kernel = np.ones(win) / win
    rolling_mean = np.convolve(s, kernel, mode="same")
    residuals = np.abs(s - rolling_mean)
    threshold = 3 * np.std(residuals)
    outlier_frac = float(np.sum(residuals > threshold) / len(s)) if threshold > 0 else 0.0
    olevel = "green" if outlier_frac == 0 else "yellow" if outlier_frac < 0.005 else "red"
    metrics["Outliers (>3σ)"] = {"value": outlier_frac, "display": f"{outlier_frac * 100:.2f}%", "level": olevel}

    snr = float(np.ptp(s) / np.std(np.diff(s))) if np.std(np.diff(s)) > 0 else 999.0
    slevel = "green" if snr > 10 else "yellow" if snr > 5 else "red"
    metrics["SNR"] = {"value": snr, "display": f"{snr:.1f}", "level": slevel}

    red_count = sum(1 for m in metrics.values() if m["level"] == "red")
    yellow_count = sum(1 for m in metrics.values() if m["level"] == "yellow")
    if red_count > 0:
        grade, glevel = "Poor", "red"
    elif yellow_count > 1:
        grade, glevel = "Fair", "yellow"
    else:
        grade, glevel = "Good", "green"
    metrics["Overall Grade"] = {"value": grade, "display": grade, "level": glevel}

    return metrics


def tga_draft_processing_equal(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    """Deep-compare normalized TGA processing draft payloads (smoothing + step_detection)."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return a == b
    try:
        import json

        def norm(d: dict[str, Any]) -> str:
            return json.dumps(d, sort_keys=True, default=str)

        return norm(a) == norm(b)
    except Exception:
        return a == b


def append_undo_after_edit(
    past: list[dict[str, Any]] | None,
    future: list[dict[str, Any]] | None,
    old_draft: dict[str, Any] | None,
    new_draft: dict[str, Any],
    *,
    max_depth: int = MAX_TGA_UNDO_DEPTH,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """After a user edit, push *old_draft* onto past and clear redo when draft actually changes."""
    past_list = [copy.deepcopy(x) for x in (past or []) if isinstance(x, dict)]
    if old_draft is None or tga_draft_processing_equal(old_draft, new_draft):
        return past_list, [copy.deepcopy(x) for x in (future or []) if isinstance(x, dict)]
    past_list.append(copy.deepcopy(old_draft))
    if len(past_list) > max_depth:
        past_list = past_list[-max_depth:]
    return past_list, []


def perform_undo(
    past: list[dict[str, Any]] | None,
    future: list[dict[str, Any]] | None,
    current: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]] | None:
    if not past:
        return None
    past_list = [copy.deepcopy(x) for x in past if isinstance(x, dict)]
    future_list = [copy.deepcopy(x) for x in (future or []) if isinstance(x, dict)]
    previous = past_list.pop()
    if current is not None:
        future_list.append(copy.deepcopy(current))
    return previous, past_list, future_list


def perform_redo(
    past: list[dict[str, Any]] | None,
    future: list[dict[str, Any]] | None,
    current: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]] | None:
    if not future:
        return None
    past_list = [copy.deepcopy(x) for x in (past or []) if isinstance(x, dict)]
    future_list = [copy.deepcopy(x) for x in future if isinstance(x, dict)]
    nxt = future_list.pop()
    if current is not None:
        past_list.append(copy.deepcopy(current))
    return nxt, past_list, future_list


def downsample_rows(rows: list[dict[str, Any]], columns: list[str], max_points: int = 6000) -> tuple[np.ndarray, np.ndarray]:
    """Extract temperature/signal as float arrays; stride if very long."""
    if not rows:
        return np.array([]), np.array([])
    t_key = "temperature" if "temperature" in columns else None
    s_key = "signal" if "signal" in columns else None
    if t_key is None or s_key is None:
        return np.array([]), np.array([])
    t_vals: list[float] = []
    s_vals: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            tv = float(row.get(t_key))
            sv = float(row.get(s_key))
        except (TypeError, ValueError):
            continue
        if math.isfinite(tv) and math.isfinite(sv):
            t_vals.append(tv)
            s_vals.append(sv)
    t_arr = np.asarray(t_vals, dtype=float)
    s_arr = np.asarray(s_vals, dtype=float)
    n = len(t_arr)
    if n <= max_points or n == 0:
        return t_arr, s_arr
    step = int(math.ceil(n / max_points))
    return t_arr[::step], s_arr[::step]


def compute_tga_raw_exploration_stats(
    temperature: np.ndarray,
    signal: np.ndarray,
    *,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pre-run / raw exploration stats and hints (no Streamlit dependency)."""
    out: dict[str, Any] = {"warnings": [], "hints": [], "checks": {}, "validation_messages": []}
    val = validation if isinstance(validation, dict) else {}
    out["validation_status"] = str(val.get("status") or "")
    for w in val.get("warnings") or []:
        if isinstance(w, str) and w.strip():
            out["validation_messages"].append(w.strip())
    for issue in val.get("issues") or []:
        if isinstance(issue, str) and issue.strip():
            out["validation_messages"].append(issue.strip())
    vchecks = val.get("checks") if isinstance(val.get("checks"), dict) else {}
    out["checks"] = dict(vchecks)

    if temperature.size == 0 or signal.size == 0 or temperature.size != signal.size:
        out["warnings"] = ["missing_series"]
        return out

    t = temperature.astype(float)
    s = signal.astype(float)
    mask = np.isfinite(t) & np.isfinite(s)
    t = t[mask]
    s = s[mask]
    n = int(t.size)
    out["point_count"] = n
    if n < 2:
        out["warnings"] = ["too_few_points"]
        return out

    out["temp_min"] = float(t.min())
    out["temp_max"] = float(t.max())
    out["signal_min"] = float(s.min())
    out["signal_max"] = float(s.max())
    out["apparent_mass_change"] = float(s.max() - s.min())

    dt = np.diff(t)
    pos = int(np.sum(dt > 0))
    neg = int(np.sum(dt < 0))
    zero = int(np.sum(dt == 0))
    dom = max(pos, neg, zero)
    if dom < len(dt) * 0.85:
        out["hints"].append("temperature_non_monotonic")
    elif neg > pos:
        out["hints"].append("temperature_mostly_decreasing")

    ds = np.diff(s)
    frac_inc = float(np.sum(ds > 0) / len(ds)) if len(ds) else 0.0
    frac_dec = float(np.sum(ds < 0) / len(ds)) if len(ds) else 0.0
    if frac_inc > 0.55 and frac_dec < 0.35:
        out["hints"].append("mass_trend_increasing")
    elif frac_dec > 0.55 and frac_inc < 0.35:
        out["hints"].append("mass_trend_decreasing")

    qm = _compute_signal_quality_metrics(t, s)
    out["quality_metrics"] = {k: {"display": v.get("display"), "level": v.get("level")} for k, v in qm.items()}

    return out


def build_tga_raw_quality_panel(stats: dict[str, Any], loc: str, *, temp_unit: str, signal_unit: str) -> html.Div:
    """Dash layout for raw-quality exploration block."""
    prefix = "dash.analysis.tga.raw_quality"
    w0 = (stats.get("warnings") or [None])[0]
    if w0 in ("missing_series", "too_few_points"):
        key = f"{prefix}.empty_{w0}"
        return html.Div(
            html.P(translate_ui(loc, key), className="text-muted small mb-0"),
            className="tga-raw-quality-inner",
        )

    n = int(stats.get("point_count") or 0)
    t0 = stats.get("temp_min")
    t1 = stats.get("temp_max")
    s0 = stats.get("signal_min")
    s1 = stats.get("signal_max")
    chg = stats.get("apparent_mass_change")

    lines: list[Any] = [
        html.Li(translate_ui(loc, f"{prefix}.stat_points", n=n)),
    ]
    if t0 is not None and t1 is not None:
        lines.append(html.Li(translate_ui(loc, f"{prefix}.stat_temp_range", t0=t0, t1=t1, u=temp_unit)))
    if s0 is not None and s1 is not None:
        lines.append(html.Li(translate_ui(loc, f"{prefix}.stat_mass_range", s0=s0, s1=s1, u=signal_unit)))
    if chg is not None:
        lines.append(html.Li(translate_ui(loc, f"{prefix}.stat_apparent_change", chg=chg, u=signal_unit)))

    qm = stats.get("quality_metrics") or {}
    og = qm.get("Overall Grade") or {}
    if og.get("display"):
        gdisp = str(og.get("display"))
        grade_key = {"Good": f"{prefix}.grade_good", "Fair": f"{prefix}.grade_fair", "Poor": f"{prefix}.grade_poor"}.get(gdisp)
        if grade_key:
            gdisp = translate_ui(loc, grade_key)
        lines.append(
            html.Li(
                [
                    html.Span(translate_ui(loc, f"{prefix}.grade_label"), className="me-1"),
                    html.Span(gdisp, className=f"text-{_level_to_bootstrap(og.get('level'))}"),
                ]
            )
        )

    hint_items: list[html.Li] = []
    for h in stats.get("hints") or []:
        hint_items.append(html.Li(translate_ui(loc, f"{prefix}.hint.{h}"), className="small"))

    warn_items: list[html.Li] = []
    for w in stats.get("warnings") or []:
        if w in ("missing_series", "too_few_points"):
            continue
        ikey = f"{prefix}.warn.{w}"
        label = translate_ui(loc, ikey) if translate_ui(loc, ikey) != ikey else w
        warn_items.append(html.Li(label, className="small text-warning"))
    for msg in stats.get("validation_messages") or []:
        warn_items.append(html.Li(msg, className="small text-warning"))

    return html.Div(
        [
            html.Ul(lines, className="small mb-2 ps-3"),
            html.Ul(hint_items, className="small mb-2 ps-3 text-muted") if hint_items else None,
            html.Ul(warn_items, className="small mb-0 ps-3") if warn_items else None,
        ],
        className="tga-raw-quality-inner",
    )


def _level_to_bootstrap(level: str | None) -> str:
    if level == "red":
        return "danger"
    if level == "yellow":
        return "warning"
    return "success"


def format_tga_step_reference_callout(midpoint_c: float | None, loc: str) -> html.Div:
    """Compact reference line for a TGA step midpoint (decomposition standards)."""
    prefix = "dash.analysis.tga.step_ref"
    if midpoint_c is None or not math.isfinite(float(midpoint_c)):
        return html.Div(translate_ui(loc, f"{prefix}.no_midpoint"), className="small text-muted mt-1")
    mp = float(midpoint_c)
    ref = find_nearest_reference(mp, threshold_c=15.0, analysis_type="TGA")
    if ref is None:
        return html.Div(translate_ui(loc, f"{prefix}.neutral"), className="small text-muted mt-1")
    delta = mp - ref.temperature_c
    ad = abs(delta)
    if ad < 2.0:
        tone = "success"
    elif ad < 5.0:
        tone = "warning"
    else:
        tone = "danger"
    sign = "+" if delta >= 0 else ""
    line = translate_ui(
        loc,
        f"{prefix}.line",
        name=ref.name,
        rt=ref.temperature_c,
        sg=sign,
        dv=delta,
    )
    extra = ref.standard or ""
    return html.Div(
        [
            html.Span(translate_ui(loc, f"{prefix}.badge"), className=f"badge bg-{tone} me-1 align-middle"),
            html.Span(line, className="small"),
            html.Span(f" · {extra}", className="small text-muted") if extra else None,
        ],
        className="mt-1",
    )
