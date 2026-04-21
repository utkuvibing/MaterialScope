"""XRD processing draft normalization and API payload helpers (Streamlit-default aligned)."""

from __future__ import annotations

import copy
import json
import math
from typing import Any

_XRD_TEMPLATE_IDS = ("xrd.general", "xrd.phase_screening")

_XRD_TEMPLATE_DEFAULTS: dict[str, dict[str, Any]] = {
    "xrd.general": {
        "axis_normalization": {"sort_axis": True, "deduplicate": "first", "axis_min": None, "axis_max": None},
        "smoothing": {"method": "savgol", "window_length": 11, "polyorder": 3},
        "baseline": {"method": "rolling_minimum", "window_length": 31, "smoothing_window": 9},
        "peak_detection": {"method": "scipy_find_peaks", "prominence": 0.08, "distance": 6, "width": 2, "max_peaks": 12},
        "method_context": {
            "xrd_match_metric": "peak_overlap_weighted",
            "xrd_match_tolerance_deg": 0.28,
            "xrd_match_top_n": 5,
            "xrd_match_minimum_score": 0.42,
            "xrd_match_intensity_weight": 0.35,
            "xrd_match_major_peak_fraction": 0.4,
        },
    },
    "xrd.phase_screening": {
        "axis_normalization": {"sort_axis": True, "deduplicate": "first", "axis_min": 5.0, "axis_max": 90.0},
        "smoothing": {"method": "savgol", "window_length": 15, "polyorder": 3},
        "baseline": {"method": "rolling_minimum", "window_length": 41, "smoothing_window": 9},
        "peak_detection": {"method": "scipy_find_peaks", "prominence": 0.12, "distance": 8, "width": 3, "max_peaks": 16},
        "method_context": {
            "xrd_match_metric": "peak_overlap_weighted",
            "xrd_match_tolerance_deg": 0.24,
            "xrd_match_top_n": 7,
            "xrd_match_minimum_score": 0.45,
            "xrd_match_intensity_weight": 0.4,
            "xrd_match_major_peak_fraction": 0.45,
        },
    },
}

_XRD_PLOT_DEFAULTS: dict[str, Any] = {
    "show_peak_labels": True,
    "label_density_mode": "smart",
    "max_labels": 8,
    "min_label_intensity_ratio": 0.12,
    "marker_size": 8,
    "label_position_precision": 2,
    "label_intensity_precision": 0,
    # Match overlays off by default — enable under Plot appearance (advanced).
    "show_matched_peaks": False,
    "show_unmatched_observed": False,
    "show_unmatched_reference": False,
    "show_match_connectors": False,
    "show_match_labels": False,
    # Smoothed / baseline as separate traces (advanced).
    "show_intermediate_traces": False,
    "style_preset": "color_shape",
    "only_selected_candidate": True,
    "x_range_enabled": False,
    "x_min": None,
    "x_max": None,
    "y_range_enabled": False,
    "y_min": None,
    "y_max": None,
    "log_y": False,
    "line_width": 2.0,
}


def xrd_template_ids() -> tuple[str, ...]:
    return _XRD_TEMPLATE_IDS


def default_xrd_draft_for_template(template_id: str | None) -> dict[str, Any]:
    tid = str(template_id or "").strip() if str(template_id or "").strip() in _XRD_TEMPLATE_IDS else "xrd.general"
    src = _XRD_TEMPLATE_DEFAULTS[tid]
    mc = copy.deepcopy(src["method_context"])
    mc["xrd_plot_settings"] = copy.deepcopy(_XRD_PLOT_DEFAULTS)
    return {
        "axis_normalization": copy.deepcopy(src["axis_normalization"]),
        "smoothing": copy.deepcopy(src["smoothing"]),
        "baseline": copy.deepcopy(src["baseline"]),
        "peak_detection": copy.deepcopy(src["peak_detection"]),
        "method_context": mc,
    }


def _coerce_int_positive(value, *, default: int, minimum: int) -> int:
    try:
        if value in (None, ""):
            return max(default, minimum)
        parsed = int(float(value))
    except (TypeError, ValueError):
        return max(default, minimum)
    return max(parsed, minimum)


def _coerce_float_bounds(value, *, default: float, minimum: float, maximum: float) -> float:
    try:
        if value in (None, ""):
            parsed = default
        else:
            parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if not math.isfinite(parsed):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _coerce_optional_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _normalize_axis_norm(d: dict | None) -> dict[str, Any]:
    src = dict(d or {})
    sort_axis = bool(src.get("sort_axis", True))
    dedup = str(src.get("deduplicate") or "first").strip().lower()
    if dedup not in {"first", "last", "mean"}:
        dedup = "first"
    return {
        "sort_axis": sort_axis,
        "deduplicate": dedup,
        "axis_min": _coerce_optional_float(src.get("axis_min")),
        "axis_max": _coerce_optional_float(src.get("axis_max")),
    }


def _normalize_smoothing(d: dict | None) -> dict[str, Any]:
    src = dict(d or {})
    method = str(src.get("method") or "savgol").strip().lower()
    if method not in {"savgol", "moving_average", "mean"}:
        method = "savgol"
    if method in {"moving_average", "mean"}:
        wl = _coerce_int_positive(src.get("window_length"), default=11, minimum=3)
        if wl % 2 == 0:
            wl += 1
        return {"method": "moving_average", "window_length": wl}
    wl = _coerce_int_positive(src.get("window_length"), default=11, minimum=5)
    if wl % 2 == 0:
        wl += 1
    po = _coerce_int_positive(src.get("polyorder"), default=3, minimum=1)
    po = min(po, max(wl - 2, 1))
    return {"method": "savgol", "window_length": wl, "polyorder": po}


def _normalize_baseline(d: dict | None) -> dict[str, Any]:
    src = dict(d or {})
    method = str(src.get("method") or "rolling_minimum").strip().lower()
    if method not in {"rolling_minimum", "linear", "asls", "none", "off"}:
        method = "rolling_minimum"
    if method in {"none", "off"}:
        return {"method": "none"}
    if method == "linear":
        return {"method": "linear"}
    wl = _coerce_int_positive(src.get("window_length"), default=31, minimum=5)
    if wl % 2 == 0:
        wl += 1
    sw = _coerce_int_positive(src.get("smoothing_window"), default=9, minimum=3)
    if sw % 2 == 0:
        sw += 1
    return {"method": "rolling_minimum", "window_length": wl, "smoothing_window": sw}


def _normalize_peak_detection(d: dict | None) -> dict[str, Any]:
    src = dict(d or {})
    prom = _coerce_float_bounds(src.get("prominence"), default=0.08, minimum=1e-9, maximum=1e9)
    dist = _coerce_int_positive(src.get("distance"), default=6, minimum=1)
    width = _coerce_int_positive(src.get("width"), default=2, minimum=1)
    max_peaks = _coerce_int_positive(src.get("max_peaks"), default=12, minimum=1)
    return {
        "method": "scipy_find_peaks",
        "prominence": prom,
        "distance": dist,
        "width": width,
        "max_peaks": max_peaks,
    }


def _normalize_method_context(mc: dict | None, plot: dict | None) -> dict[str, Any]:
    src = dict(mc or {})
    metric = str(src.get("xrd_match_metric") or "peak_overlap_weighted").strip()
    tol = _coerce_float_bounds(src.get("xrd_match_tolerance_deg"), default=0.28, minimum=1e-6, maximum=10.0)
    top_n = _coerce_int_positive(src.get("xrd_match_top_n"), default=5, minimum=1)
    min_score = _coerce_float_bounds(src.get("xrd_match_minimum_score"), default=0.42, minimum=0.0, maximum=1.0)
    iw = _coerce_float_bounds(src.get("xrd_match_intensity_weight"), default=0.35, minimum=0.0, maximum=1.0)
    mj = _coerce_float_bounds(src.get("xrd_match_major_peak_fraction"), default=0.4, minimum=0.0, maximum=1.0)
    out = {
        "xrd_match_metric": metric,
        "xrd_match_tolerance_deg": tol,
        "xrd_match_top_n": top_n,
        "xrd_match_minimum_score": min_score,
        "xrd_match_intensity_weight": iw,
        "xrd_match_major_peak_fraction": mj,
    }
    for key in (
        "xrd_axis_role",
        "xrd_axis_unit",
        "xrd_wavelength_angstrom",
        "xrd_axis_mapping_review_required",
        "xrd_stable_matching_blocked",
        "xrd_provenance_state",
        "xrd_provenance_warning",
    ):
        if key in src and src[key] is not None:
            out[key] = copy.deepcopy(src[key])
    ps = plot if isinstance(plot, dict) else src.get("xrd_plot_settings")
    out["xrd_plot_settings"] = _normalize_plot_settings(ps if isinstance(ps, dict) else {})
    return out


def _normalize_plot_settings(src: dict) -> dict[str, Any]:
    from dash_app.components.xrd_result_plot import normalize_xrd_plot_settings

    return normalize_xrd_plot_settings(src)


def normalize_xrd_processing_draft(draft: dict | None) -> dict[str, Any]:
    d = dict(draft or {})
    axis = _normalize_axis_norm(d.get("axis_normalization") if isinstance(d.get("axis_normalization"), dict) else {})
    sm = _normalize_smoothing(d.get("smoothing") if isinstance(d.get("smoothing"), dict) else {})
    bl = _normalize_baseline(d.get("baseline") if isinstance(d.get("baseline"), dict) else {})
    pk = _normalize_peak_detection(d.get("peak_detection") if isinstance(d.get("peak_detection"), dict) else {})
    mc_in = d.get("method_context") if isinstance(d.get("method_context"), dict) else {}
    plot_in = mc_in.get("xrd_plot_settings") if isinstance(mc_in.get("xrd_plot_settings"), dict) else {}
    mc = _normalize_method_context(mc_in, plot_in)
    return {
        "axis_normalization": axis,
        "smoothing": sm,
        "baseline": bl,
        "peak_detection": pk,
        "method_context": mc,
    }


def xrd_overrides_from_draft(draft: dict | None) -> dict[str, Any]:
    norm = normalize_xrd_processing_draft(draft)
    mc = copy.deepcopy(norm["method_context"])
    return {
        "axis_normalization": copy.deepcopy(norm["axis_normalization"]),
        "smoothing": copy.deepcopy(norm["smoothing"]),
        "baseline": copy.deepcopy(norm["baseline"]),
        "peak_detection": copy.deepcopy(norm["peak_detection"]),
        "method_context": mc,
    }


def xrd_draft_from_loaded_processing(processing: dict | None) -> dict[str, Any]:
    if not isinstance(processing, dict):
        return default_xrd_draft_for_template("xrd.general")
    sp = processing.get("signal_pipeline") or {}
    ast = processing.get("analysis_steps") or {}
    ax = sp.get("axis_normalization") if isinstance(sp.get("axis_normalization"), dict) else processing.get("axis_normalization")
    sm = sp.get("smoothing") if isinstance(sp.get("smoothing"), dict) else processing.get("smoothing")
    bl = sp.get("baseline") if isinstance(sp.get("baseline"), dict) else processing.get("baseline")
    pk = ast.get("peak_detection") if isinstance(ast.get("peak_detection"), dict) else processing.get("peak_detection")
    mc = processing.get("method_context") if isinstance(processing.get("method_context"), dict) else {}
    return normalize_xrd_processing_draft(
        {
            "axis_normalization": ax,
            "smoothing": sm,
            "baseline": bl,
            "peak_detection": pk,
            "method_context": mc,
        }
    )


def xrd_preset_processing_body_for_save(draft: dict | None) -> dict[str, Any]:
    return xrd_overrides_from_draft(draft)


def xrd_ui_snapshot_dict(template_id: str | None, draft: dict | None) -> dict[str, Any]:
    tid = template_id if template_id in _XRD_TEMPLATE_IDS else "xrd.general"
    norm = normalize_xrd_processing_draft(draft)
    return {
        "workflow_template_id": tid,
        **{k: copy.deepcopy(norm[k]) for k in ("axis_normalization", "smoothing", "baseline", "peak_detection")},
        "method_context": copy.deepcopy(norm["method_context"]),
    }


def xrd_snapshots_equal(a: dict | None, b: dict | None) -> bool:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def apply_dataset_review_to_method_context(
    draft: dict | None,
    *,
    axis_confirmed: bool,
    wavelength_value: Any,
) -> dict[str, Any]:
    norm = normalize_xrd_processing_draft(draft)
    mc = copy.deepcopy(norm["method_context"])
    if axis_confirmed:
        mc["xrd_axis_role"] = "two_theta"
        mc["xrd_axis_unit"] = "degree_2theta"
        mc["xrd_axis_mapping_review_required"] = False
        mc["xrd_stable_matching_blocked"] = False
    wl = _coerce_optional_float(wavelength_value)
    if wl is not None and wl > 0:
        mc["xrd_wavelength_angstrom"] = float(wl)
        mc["xrd_provenance_state"] = "complete"
        mc["xrd_provenance_warning"] = ""
    norm["method_context"] = _normalize_method_context(mc, mc.get("xrd_plot_settings"))
    return norm


def xrd_draft_from_control_values(
    *,
    axis_sort,
    axis_dedup,
    axis_min,
    axis_max,
    sm_method,
    sm_window,
    sm_poly,
    bl_method,
    bl_window,
    bl_smooth_window,
    pk_prom,
    pk_dist,
    pk_width,
    pk_max,
    match_metric,
    match_tol,
    match_top_n,
    match_min_score,
    match_iw,
    match_maj,
    review_axis_ok,
    review_wavelength,
    plot_show_labels,
    plot_density,
    plot_max_labels,
    plot_min_ratio,
    plot_msize,
    plot_pos_prec,
    plot_int_prec,
    plot_matched,
    plot_u_obs,
    plot_u_ref,
    plot_conn,
    plot_m_lbl,
    plot_style,
    plot_x_en,
    plot_x_min,
    plot_x_max,
    plot_y_en,
    plot_y_min,
    plot_y_max,
    plot_log_y,
    plot_lw,
    plot_show_intermediate,
) -> dict[str, Any]:
    plot = {
        "show_peak_labels": bool(plot_show_labels),
        "label_density_mode": str(plot_density or "smart"),
        "max_labels": plot_max_labels,
        "min_label_intensity_ratio": plot_min_ratio,
        "marker_size": plot_msize,
        "label_position_precision": plot_pos_prec,
        "label_intensity_precision": plot_int_prec,
        "show_matched_peaks": bool(plot_matched),
        "show_unmatched_observed": bool(plot_u_obs),
        "show_unmatched_reference": bool(plot_u_ref),
        "show_match_connectors": bool(plot_conn),
        "show_match_labels": bool(plot_m_lbl),
        "show_intermediate_traces": bool(plot_show_intermediate),
        "style_preset": str(plot_style or "color_shape"),
        "x_range_enabled": bool(plot_x_en),
        "x_min": plot_x_min,
        "x_max": plot_x_max,
        "y_range_enabled": bool(plot_y_en),
        "y_min": plot_y_min,
        "y_max": plot_y_max,
        "log_y": bool(plot_log_y),
        "line_width": plot_lw,
    }
    mc = {
        "xrd_match_metric": str(match_metric or "peak_overlap_weighted"),
        "xrd_match_tolerance_deg": match_tol,
        "xrd_match_top_n": match_top_n,
        "xrd_match_minimum_score": match_min_score,
        "xrd_match_intensity_weight": match_iw,
        "xrd_match_major_peak_fraction": match_maj,
        "xrd_plot_settings": plot,
    }
    draft = {
        "axis_normalization": {
            "sort_axis": bool(axis_sort),
            "deduplicate": str(axis_dedup or "first"),
            "axis_min": axis_min,
            "axis_max": axis_max,
        },
        "smoothing": {"method": sm_method, "window_length": sm_window, "polyorder": sm_poly},
        "baseline": {"method": bl_method, "window_length": bl_window, "smoothing_window": bl_smooth_window},
        "peak_detection": {
            "prominence": pk_prom,
            "distance": pk_dist,
            "width": pk_width,
            "max_peaks": pk_max,
        },
        "method_context": mc,
    }
    norm = normalize_xrd_processing_draft(draft)
    return apply_dataset_review_to_method_context(norm, axis_confirmed=bool(review_axis_ok), wavelength_value=review_wavelength)
