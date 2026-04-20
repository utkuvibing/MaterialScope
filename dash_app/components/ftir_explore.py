"""FTIR Dash exploration helpers: raw-quality stats, undo stacks.

Reuses the same patterns established by TGA exploration helpers.
"""

from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np
from dash import html

from utils.i18n import translate_ui

MAX_FTIR_UNDO_DEPTH = 25


def ftir_draft_processing_equal(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    """Deep-compare normalized FTIR processing draft payloads."""
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
    max_depth: int = MAX_FTIR_UNDO_DEPTH,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """After a user edit, push *old_draft* onto past and clear redo when draft actually changes."""
    past_list = [copy.deepcopy(x) for x in (past or []) if isinstance(x, dict)]
    if old_draft is None or ftir_draft_processing_equal(old_draft, new_draft):
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
    """Extract axis/signal as float arrays; stride if very long."""
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


def compute_ftir_raw_exploration_stats(
    axis: np.ndarray,
    signal: np.ndarray,
    *,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pre-run / raw exploration stats and hints for FTIR datasets."""
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

    if axis.size == 0 or signal.size == 0 or axis.size != signal.size:
        out["warnings"] = ["missing_series"]
        return out

    a = axis.astype(float)
    s = signal.astype(float)
    mask = np.isfinite(a) & np.isfinite(s)
    a = a[mask]
    s = s[mask]
    n = int(a.size)
    out["point_count"] = n
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

    # Baseline drift hint
    if len(s) > 2:
        coeffs = np.polyfit(np.arange(len(s)), s, 1)
        slope = abs(coeffs[0])
        sig_range = float(np.ptp(s)) or 1.0
        norm_drift = slope * len(s) / sig_range
    else:
        norm_drift = 0.0
    out["baseline_drift"] = norm_drift
    if norm_drift > 0.5:
        out["hints"].append("strong_baseline_drift")
    elif norm_drift > 0.2:
        out["hints"].append("moderate_baseline_drift")

    # Spacing irregularity
    if len(da) > 1 and np.mean(np.abs(da)) > 1e-12:
        cv = float(np.std(da) / np.abs(np.mean(da)))
    else:
        cv = 0.0
    out["spacing_cv"] = cv
    if cv > 0.15:
        out["hints"].append("irregular_spacing")
    elif cv > 0.05:
        out["hints"].append("somewhat_irregular_spacing")

    total_points = axis.size
    out["missing_count"] = int(total_points - n)

    return out


def build_ftir_raw_quality_panel(stats: dict[str, Any], loc: str, *, signal_unit: str) -> html.Div:
    """Dash layout for FTIR raw-quality exploration block."""
    prefix = "dash.analysis.ftir.raw_quality"
    w0 = (stats.get("warnings") or [None])[0]
    if w0 in ("missing_series", "too_few_points"):
        key = f"{prefix}.empty_{w0}"
        return html.Div(
            html.P(translate_ui(loc, key), className="text-muted small mb-0"),
            className="ftir-raw-quality-inner",
        )

    n = int(stats.get("point_count") or 0)
    a0 = stats.get("axis_min")
    a1 = stats.get("axis_max")
    s0 = stats.get("signal_min")
    s1 = stats.get("signal_max")
    drift = stats.get("baseline_drift")
    spacing_cv = stats.get("spacing_cv")
    missing = stats.get("missing_count", 0)

    lines: list[Any] = [
        html.Li(translate_ui(loc, f"{prefix}.stat_points", n=n)),
    ]
    if a0 is not None and a1 is not None:
        lines.append(html.Li(translate_ui(loc, f"{prefix}.stat_axis_range", a0=a0, a1=a1)))
    if s0 is not None and s1 is not None:
        lines.append(html.Li(translate_ui(loc, f"{prefix}.stat_signal_range", s0=s0, s1=s1, u=signal_unit)))
    if missing:
        lines.append(html.Li(translate_ui(loc, f"{prefix}.stat_missing", n=missing), className="text-warning"))
    if drift is not None:
        lines.append(html.Li(translate_ui(loc, f"{prefix}.stat_baseline_drift", drift=f"{drift:.3f}")))
    if spacing_cv is not None:
        lines.append(html.Li(translate_ui(loc, f"{prefix}.stat_spacing_cv", cv=f"{spacing_cv:.4f}")))

    hint_items: list[html.Li] = []
    for h in stats.get("hints") or []:
        hint_items.append(html.Li(translate_ui(loc, f"{prefix}.hint.{h}"), className="small text-muted"))

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
        className="ftir-raw-quality-inner",
    )
