"""FTIR analysis page -- product-grade implementation aligned with DSC/TGA/DTA standard.

Left column tabs:
  - Setup: dataset, workflow template, raw-quality exploration, workflow guide
  - Processing: undo/redo/reset, presets, smoothing, baseline, normalization,
    peak detection, similarity matching
  - Run: execute analysis

Right column results surface:
  1. analysis summary
  2. result metrics
  3. validation and quality
  4. main FTIR figure
  5. top-match hero summary
  6. key spectral peaks / feature cards
  7. full match table
  8. applied processing summary
  9. raw metadata
  10. literature compare
"""

from __future__ import annotations

import copy
import json
import math
from typing import Any

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html
import plotly.graph_objects as go

from dash_app.components.analysis_page import (
    analysis_page_stores,
    capture_result_figure_from_layout,
    dataset_selection_card,
    dataset_selector_block,
    eligible_datasets,
    empty_result_msg,
    execute_card,
    interpret_run_result,
    metrics_row,
    no_data_figure_msg,
    processing_details_section,
    resolve_sample_name,
    result_placeholder_card,
    workflow_template_card,
)
from dash_app.components.chrome import page_header
from dash_app.components.data_preview import dataset_table
from dash_app.components.ftir_explore import (
    MAX_FTIR_UNDO_DEPTH,
    append_undo_after_edit,
    build_ftir_raw_quality_panel,
    compute_ftir_raw_exploration_stats,
    downsample_rows,
    ftir_draft_processing_equal,
    perform_redo,
    perform_undo,
)
from dash_app.components.literature_compare_ui import (
    LITERATURE_COMPACT_ALTERNATIVE_PREVIEW_LIMIT,
    LITERATURE_COMPACT_EVIDENCE_PREVIEW_LIMIT,
    build_literature_compare_card,
    coerce_literature_max_claims,
    literature_compare_status_alert,
    literature_t,
    render_literature_output,
)
from dash_app.theme import PLOT_THEME, normalize_ui_theme
from utils.i18n import normalize_ui_locale, translate_ui

dash.register_page(__name__, path="/ftir", title="FTIR Analysis - MaterialScope")

_FTIR_TEMPLATE_IDS = ["ftir.general", "ftir.functional_groups"]
_FTIR_ELIGIBLE_TYPES = {"FTIR", "UNKNOWN"}

_FTIR_PRESET_ANALYSIS_TYPE = "FTIR"
_FTIR_LITERATURE_PREFIX = "dash.analysis.ftir.literature"

_FTIR_RESULT_CARD_ROLES = {
    "context": "dsc-result-context",
    "hero": "dsc-result-hero",
    "support": "dsc-result-support",
    "secondary": "dsc-result-secondary",
}

_FTIR_USER_FACING_METADATA_KEYS: frozenset[str] = frozenset({
    "sample_name",
    "display_name",
    "instrument",
    "vendor",
    "file_name",
    "source_data_hash",
})

_FTIR_SMOOTH_METHODS = frozenset({"savgol", "moving_average", "gaussian"})
_FTIR_SMOOTHING_DEFAULTS: dict[str, dict[str, Any]] = {
    "savgol": {"method": "savgol", "window_length": 11, "polyorder": 3},
    "moving_average": {"method": "moving_average", "window_length": 11},
    "gaussian": {"method": "gaussian", "sigma": 2.0},
}

_FTIR_BASELINE_METHODS = frozenset({"asls", "linear", "rubberband"})
_FTIR_BASELINE_DEFAULTS: dict[str, dict[str, Any]] = {
    "asls": {"method": "asls", "lam": 1e6, "p": 0.01, "region": None},
    "linear": {"method": "linear", "region": None},
    "rubberband": {"method": "rubberband", "region": None},
}

_FTIR_NORMALIZATION_MODES = frozenset({"vector", "max", "snv"})
_FTIR_NORMALIZATION_DEFAULTS: dict[str, Any] = {"method": "vector"}

_FTIR_PEAK_DETECTION_DEFAULTS: dict[str, Any] = {
    "prominence": 0.035,
    "distance": 5,
    "max_peaks": 12,
}

_FTIR_SIMILARITY_MATCHING_DEFAULTS: dict[str, Any] = {
    "top_n": 3,
    "minimum_score": 0.45,
}

_FTIR_MAX_PEAK_CARDS = 8
_FTIR_TRUNCATE_PEAK_CARDS_WHEN = 9


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def _coerce_int_positive(value, *, default: int, minimum: int) -> int:
    try:
        if value in (None, ""):
            return max(default, minimum)
        parsed = int(float(value))
    except (TypeError, ValueError):
        return max(default, minimum)
    return max(parsed, minimum)


def _coerce_float_positive(value, *, default: float, minimum: float) -> float:
    try:
        if value in (None, ""):
            return max(default, minimum)
        parsed = float(value)
    except (TypeError, ValueError):
        return max(default, minimum)
    if not math.isfinite(parsed):
        return max(default, minimum)
    return max(parsed, minimum)


def _coerce_float_non_negative(value, *, default: float) -> float:
    try:
        if value in (None, ""):
            return max(default, 0.0)
        parsed = float(value)
    except (TypeError, ValueError):
        return max(default, 0.0)
    if not math.isfinite(parsed) or parsed < 0:
        return max(default, 0.0)
    return parsed


# ---------------------------------------------------------------------------
# Processing draft model
# ---------------------------------------------------------------------------


def _default_ftir_processing_draft() -> dict[str, Any]:
    return {
        "smoothing": copy.deepcopy(_FTIR_SMOOTHING_DEFAULTS["savgol"]),
        "baseline": copy.deepcopy(_FTIR_BASELINE_DEFAULTS["asls"]),
        "normalization": copy.deepcopy(_FTIR_NORMALIZATION_DEFAULTS),
        "peak_detection": copy.deepcopy(_FTIR_PEAK_DETECTION_DEFAULTS),
        "similarity_matching": copy.deepcopy(_FTIR_SIMILARITY_MATCHING_DEFAULTS),
    }


def _normalize_smoothing_values(method: str | None, window_length, polyorder, sigma) -> dict[str, Any]:
    token = str(method or "savgol").strip().lower()
    if token not in _FTIR_SMOOTH_METHODS:
        token = "savgol"
    if token == "savgol":
        wl = _coerce_int_positive(window_length, default=11, minimum=5)
        if wl % 2 == 0:
            wl += 1
        po = _coerce_int_positive(polyorder, default=3, minimum=1)
        po = min(po, max(wl - 2, 1))
        return {"method": "savgol", "window_length": wl, "polyorder": po}
    if token == "moving_average":
        wl = _coerce_int_positive(window_length, default=11, minimum=3)
        if wl % 2 == 0:
            wl += 1
        return {"method": "moving_average", "window_length": wl}
    sg = _coerce_float_positive(sigma, default=2.0, minimum=0.1)
    return {"method": "gaussian", "sigma": sg}


def _normalize_baseline_region(enabled, rmin, rmax) -> list[float] | None:
    if not enabled:
        return None
    try:
        lower = float(rmin)
        upper = float(rmax)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
        return None
    return [lower, upper]


def _normalize_baseline_values(method: str | None, lam, p, region_enabled=None, region_min=None, region_max=None) -> dict[str, Any]:
    token = str(method or "asls").strip().lower()
    if token not in _FTIR_BASELINE_METHODS:
        token = "asls"
    region = _normalize_baseline_region(region_enabled, region_min, region_max)
    if token == "asls":
        lam_value = _coerce_float_positive(lam, default=1e6, minimum=1e-3)
        p_value = _coerce_float_positive(p, default=0.01, minimum=1e-4)
        p_value = min(p_value, 0.5)
        return {"method": "asls", "lam": lam_value, "p": p_value, "region": region}
    return {"method": token, "region": region}


def _normalize_normalization_values(method: str | None) -> dict[str, Any]:
    token = str(method or "vector").strip().lower()
    if token not in _FTIR_NORMALIZATION_MODES:
        token = "vector"
    return {"method": token}


def _normalize_peak_detection_values(prominence, distance, max_peaks) -> dict[str, Any]:
    prom = _coerce_float_non_negative(prominence, default=0.035)
    dist = _coerce_int_positive(distance, default=5, minimum=1)
    mp = _coerce_int_positive(max_peaks, default=10, minimum=1)
    return {"prominence": prom, "distance": dist, "max_peaks": mp}


def _normalize_similarity_matching_values(top_n, minimum_score) -> dict[str, Any]:
    tn = _coerce_int_positive(top_n, default=3, minimum=1)
    ms = _coerce_float_non_negative(minimum_score, default=0.45)
    return {"top_n": tn, "minimum_score": ms}


def _normalize_ftir_processing_draft(draft: dict | None) -> dict[str, Any]:
    d = dict(draft or {})
    sm = d.get("smoothing")
    bl = d.get("baseline")
    nm = d.get("normalization")
    pk = d.get("peak_detection")
    sim = d.get("similarity_matching")

    if isinstance(sm, dict):
        sm = _normalize_smoothing_values(sm.get("method"), sm.get("window_length"), sm.get("polyorder"), sm.get("sigma"))
    else:
        sm = copy.deepcopy(_FTIR_SMOOTHING_DEFAULTS["savgol"])

    if isinstance(bl, dict):
        bl = _normalize_baseline_values(bl.get("method"), bl.get("lam"), bl.get("p"), bl.get("region") is not None, (bl.get("region") or [None, None])[0], (bl.get("region") or [None, None])[1])
    else:
        bl = copy.deepcopy(_FTIR_BASELINE_DEFAULTS["asls"])

    if isinstance(nm, dict):
        nm = _normalize_normalization_values(nm.get("method"))
    else:
        nm = copy.deepcopy(_FTIR_NORMALIZATION_DEFAULTS)

    if isinstance(pk, dict):
        pk = _normalize_peak_detection_values(pk.get("prominence"), pk.get("distance"), pk.get("max_peaks"))
    else:
        pk = copy.deepcopy(_FTIR_PEAK_DETECTION_DEFAULTS)

    if isinstance(sim, dict):
        sim = _normalize_similarity_matching_values(sim.get("top_n"), sim.get("minimum_score"))
    else:
        sim = copy.deepcopy(_FTIR_SIMILARITY_MATCHING_DEFAULTS)

    return {
        "smoothing": sm,
        "baseline": bl,
        "normalization": nm,
        "peak_detection": pk,
        "similarity_matching": sim,
    }


def _ftir_draft_from_control_values(
    smooth_method,
    smooth_window,
    smooth_poly,
    smooth_sigma,
    baseline_method,
    baseline_lam,
    baseline_p,
    baseline_region_enabled,
    baseline_region_min,
    baseline_region_max,
    norm_method,
    peak_prominence,
    peak_distance,
    peak_max_peaks,
    sim_top_n,
    sim_minimum_score,
) -> dict[str, Any]:
    return {
        "smoothing": _normalize_smoothing_values(smooth_method, smooth_window, smooth_poly, smooth_sigma),
        "baseline": _normalize_baseline_values(baseline_method, baseline_lam, baseline_p, baseline_region_enabled, baseline_region_min, baseline_region_max),
        "normalization": _normalize_normalization_values(norm_method),
        "peak_detection": _normalize_peak_detection_values(peak_prominence, peak_distance, peak_max_peaks),
        "similarity_matching": _normalize_similarity_matching_values(sim_top_n, sim_minimum_score),
    }


def _ftir_overrides_from_draft(draft: dict | None) -> dict[str, Any]:
    norm = _normalize_ftir_processing_draft(draft)
    return {
        "smoothing": copy.deepcopy(norm["smoothing"]),
        "baseline": copy.deepcopy(norm["baseline"]),
        "normalization": copy.deepcopy(norm["normalization"]),
        "peak_detection": copy.deepcopy(norm["peak_detection"]),
        "similarity_matching": copy.deepcopy(norm["similarity_matching"]),
    }


def _ftir_draft_from_loaded_processing(processing: dict | None) -> dict[str, Any]:
    if not isinstance(processing, dict):
        return copy.deepcopy(_default_ftir_processing_draft())
    sp = processing.get("signal_pipeline") or {}
    ast = processing.get("analysis_steps") or {}
    sm = sp.get("smoothing") if isinstance(sp.get("smoothing"), dict) else processing.get("smoothing")
    bl = sp.get("baseline") if isinstance(sp.get("baseline"), dict) else processing.get("baseline")
    nm = sp.get("normalization") if isinstance(sp.get("normalization"), dict) else processing.get("normalization")
    pk = ast.get("peak_detection") if isinstance(ast.get("peak_detection"), dict) else processing.get("peak_detection")
    sim = ast.get("similarity_matching") if isinstance(ast.get("similarity_matching"), dict) else processing.get("similarity_matching")
    return _normalize_ftir_processing_draft({
        "smoothing": sm,
        "baseline": bl,
        "normalization": nm,
        "peak_detection": pk,
        "similarity_matching": sim,
    })


def _ftir_preset_processing_body_for_save(draft: dict | None) -> dict[str, Any]:
    norm = _normalize_ftir_processing_draft(draft)
    return {
        "smoothing": copy.deepcopy(norm["smoothing"]),
        "baseline": copy.deepcopy(norm["baseline"]),
        "normalization": copy.deepcopy(norm["normalization"]),
        "peak_detection": copy.deepcopy(norm["peak_detection"]),
        "similarity_matching": copy.deepcopy(norm["similarity_matching"]),
    }


def _ftir_ui_snapshot_dict(template_id: str | None, draft: dict | None) -> dict[str, Any]:
    tid = template_id if template_id in _FTIR_TEMPLATE_IDS else "ftir.general"
    norm = _normalize_ftir_processing_draft(draft)
    return {
        "workflow_template_id": tid,
        "smoothing": norm["smoothing"],
        "baseline": norm["baseline"],
        "normalization": norm["normalization"],
        "peak_detection": norm["peak_detection"],
        "similarity_matching": norm["similarity_matching"],
    }


def _ftir_snapshots_equal(a: dict | None, b: dict | None) -> bool:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------


def _loc(locale_data: str | None) -> str:
    return normalize_ui_locale(locale_data)


# ---------------------------------------------------------------------------
# Layout primitives
# ---------------------------------------------------------------------------


def _ftir_result_section(child: Any, *, role: str = "support") -> html.Div:
    role_class = _FTIR_RESULT_CARD_ROLES.get(role, _FTIR_RESULT_CARD_ROLES["support"])
    return html.Div(child, className=f"dsc-result-section {role_class}")


def _ftir_collapsible_section(
    loc: str,
    title_key: str,
    body: Any,
    *,
    open: bool = False,
    summary_suffix: Any | None = None,
) -> html.Details:
    summary_children: list[Any] = [
        html.Span(className="ta-details-chevron"),
        html.Span(translate_ui(loc, title_key), className="ms-1"),
    ]
    if summary_suffix is not None:
        if isinstance(summary_suffix, (list, tuple)):
            summary_children.extend(summary_suffix)
        else:
            summary_children.append(summary_suffix)
    return html.Details(
        [
            html.Summary(summary_children, className="ta-details-summary"),
            html.Div(body, className="ta-details-body mt-2"),
        ],
        className="ta-ms-details mb-0",
        open=open,
    )


# ---------------------------------------------------------------------------
# Left-column cards
# ---------------------------------------------------------------------------


def _ftir_workflow_guide_block() -> html.Details:
    return html.Details(
        [
            html.Summary(
                [html.Span(className="ta-details-chevron"), html.Span(id="ftir-workflow-guide-title", className="ms-1")],
                className="ta-details-summary",
            ),
            html.Div(id="ftir-workflow-guide-body", className="ta-details-body mt-2 small"),
        ],
        className="ta-ms-details mb-3",
        open=False,
    )


def _ftir_raw_quality_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H6(id="ftir-raw-quality-card-title", className="card-title mb-1"),
                html.P(id="ftir-raw-quality-card-hint", className="small text-muted mb-2"),
                html.Div(id="ftir-raw-quality-panel", className="ftir-raw-quality-panel"),
            ]
        ),
        className="mb-3",
    )


def _ftir_processing_history_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H6(id="ftir-processing-history-title", className="card-title mb-1"),
                html.P(id="ftir-processing-history-hint", className="small text-muted mb-2"),
                dbc.Row(
                    [
                        dbc.Col(dbc.Button(id="ftir-processing-undo-btn", color="secondary", size="sm", outline=True, disabled=True), width="auto"),
                        dbc.Col(dbc.Button(id="ftir-processing-redo-btn", color="secondary", size="sm", outline=True, disabled=True), width="auto"),
                        dbc.Col(dbc.Button(id="ftir-processing-reset-btn", color="secondary", size="sm", outline=True), width="auto"),
                    ],
                    className="g-2 align-items-center mb-1",
                ),
                html.Div(id="ftir-history-status", className="small text-muted"),
            ]
        ),
        className="mb-3",
    )


def _ftir_preset_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="ftir-preset-card-title", className="card-title mb-1"),
                html.Small(id="ftir-preset-help", className="form-text text-muted d-block mb-2"),
                html.Div(id="ftir-preset-caption", className="small text-muted mb-2"),
                html.Div(id="ftir-preset-loaded-line", className="small mb-1"),
                html.Div(id="ftir-preset-dirty-flag", className="small mb-2"),
                dbc.Label(id="ftir-preset-select-label", html_for="ftir-preset-select", className="mb-1"),
                dbc.Select(id="ftir-preset-select", options=[], value=None),
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Button(id="ftir-preset-load-btn", color="primary", size="sm", disabled=True, className="me-2"),
                            width="auto",
                        ),
                        dbc.Col(
                            dbc.Button(id="ftir-preset-delete-btn", color="secondary", size="sm", outline=True, disabled=True),
                            width="auto",
                        ),
                    ],
                    className="g-2 my-2 align-items-center",
                ),
                dbc.Label(id="ftir-preset-save-name-label", html_for="ftir-preset-save-name", className="mb-1"),
                dbc.Input(id="ftir-preset-save-name", type="text", value="", maxLength=80),
                html.Small(id="ftir-preset-save-hint", className="text-muted d-block my-1"),
                dbc.Row(
                    [
                        dbc.Col(dbc.Button(id="ftir-preset-save-btn", color="primary", size="sm", className="me-2"), width="auto"),
                        dbc.Col(dbc.Button(id="ftir-preset-saveas-btn", color="secondary", size="sm", outline=True), width="auto"),
                    ],
                    className="g-2 mb-2 align-items-center",
                ),
                html.Div(id="ftir-preset-status", className="small text-muted"),
            ]
        ),
        className="mb-3",
    )


def _ftir_smoothing_controls_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="ftir-smoothing-card-title", className="card-title mb-2"),
                html.P(id="ftir-smoothing-card-hint", className="small text-muted mb-3"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id="ftir-smooth-method-label", html_for="ftir-smooth-method", className="mb-1"),
                                dbc.Select(
                                    id="ftir-smooth-method",
                                    options=[
                                        {"label": "Savitzky–Golay", "value": "savgol"},
                                        {"label": "Moving average", "value": "moving_average"},
                                        {"label": "Gaussian", "value": "gaussian"},
                                    ],
                                    value="savgol",
                                ),
                            ],
                            md=12,
                        ),
                    ],
                    className="g-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id="ftir-smooth-window-label", html_for="ftir-smooth-window", className="mb-1"),
                                dbc.Input(id="ftir-smooth-window", type="number", min=3, step=2, value=11),
                            ],
                            md=4,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="ftir-smooth-polyorder-label", html_for="ftir-smooth-polyorder", className="mb-1"),
                                dbc.Input(id="ftir-smooth-polyorder", type="number", min=1, max=7, step=1, value=3),
                            ],
                            md=4,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="ftir-smooth-sigma-label", html_for="ftir-smooth-sigma", className="mb-1"),
                                dbc.Input(id="ftir-smooth-sigma", type="number", min=0.1, step=0.1, value=2.0),
                            ],
                            md=4,
                        ),
                    ],
                    className="g-2",
                ),
            ]
        ),
        className="mb-3",
    )


def _ftir_baseline_controls_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="ftir-baseline-card-title", className="card-title mb-2"),
                html.P(id="ftir-baseline-card-hint", className="small text-muted mb-3"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id="ftir-baseline-method-label", html_for="ftir-baseline-method", className="mb-1"),
                                dbc.Select(
                                    id="ftir-baseline-method",
                                    options=[
                                        {"label": "AsLS", "value": "asls"},
                                        {"label": "Linear", "value": "linear"},
                                        {"label": "Rubberband", "value": "rubberband"},
                                    ],
                                    value="asls",
                                ),
                            ],
                            md=12,
                        ),
                    ],
                    className="g-2 mb-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id="ftir-baseline-lam-label", html_for="ftir-baseline-lam", className="mb-1"),
                                dbc.Input(id="ftir-baseline-lam", type="number", min=1e-3, step=1e5, value=1e6),
                            ],
                            md=6,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="ftir-baseline-p-label", html_for="ftir-baseline-p", className="mb-1"),
                                dbc.Input(id="ftir-baseline-p", type="number", min=1e-4, max=0.5, step=0.005, value=0.01),
                            ],
                            md=6,
                        ),
                    ],
                    className="g-2 mb-2",
                ),
                html.H6(id="ftir-baseline-region-section-title", className="mt-2 mb-2 small text-muted text-uppercase"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Checkbox(id="ftir-baseline-region-enabled", value=False, label=" "),
                                html.Small(id="ftir-baseline-region-enable-hint", className="form-text text-muted d-block mt-1"),
                            ],
                            md=12,
                        ),
                    ],
                    className="mb-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id="ftir-baseline-region-min-label", html_for="ftir-baseline-region-min", className="mb-1"),
                                dbc.Input(id="ftir-baseline-region-min", type="number", value=None),
                            ],
                            md=6,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="ftir-baseline-region-max-label", html_for="ftir-baseline-region-max", className="mb-1"),
                                dbc.Input(id="ftir-baseline-region-max", type="number", value=None),
                            ],
                            md=6,
                        ),
                    ],
                    className="g-2 mb-2",
                ),
            ]
        ),
        className="mb-3",
    )


def _ftir_normalization_controls_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="ftir-normalization-card-title", className="card-title mb-2"),
                html.P(id="ftir-normalization-card-hint", className="small text-muted mb-3"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id="ftir-norm-method-label", html_for="ftir-norm-method", className="mb-1"),
                                dbc.Select(
                                    id="ftir-norm-method",
                                    options=[
                                        {"label": "Vector", "value": "vector"},
                                        {"label": "Max", "value": "max"},
                                        {"label": "SNV", "value": "snv"},
                                    ],
                                    value="vector",
                                ),
                            ],
                            md=12,
                        ),
                    ],
                    className="g-2",
                ),
            ]
        ),
        className="mb-3",
    )


def _ftir_peak_detection_controls_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="ftir-peak-card-title", className="card-title mb-2"),
                html.P(id="ftir-peak-card-hint", className="small text-muted mb-3"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id="ftir-peak-prominence-label", html_for="ftir-peak-prominence", className="mb-1"),
                                dbc.Input(id="ftir-peak-prominence", type="number", min=0, step=0.001, value=0.035),
                            ],
                            md=4,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="ftir-peak-distance-label", html_for="ftir-peak-distance", className="mb-1"),
                                dbc.Input(id="ftir-peak-distance", type="number", min=1, step=1, value=5),
                            ],
                            md=4,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="ftir-peak-max-peaks-label", html_for="ftir-peak-max-peaks", className="mb-1"),
                                dbc.Input(id="ftir-peak-max-peaks", type="number", min=1, step=1, value=10),
                            ],
                            md=4,
                        ),
                    ],
                    className="g-2",
                ),
            ]
        ),
        className="mb-3",
    )


def _ftir_similarity_matching_controls_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="ftir-similarity-card-title", className="card-title mb-2"),
                html.P(id="ftir-similarity-card-hint", className="small text-muted mb-3"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id="ftir-sim-top-n-label", html_for="ftir-sim-top-n", className="mb-1"),
                                dbc.Input(id="ftir-sim-top-n", type="number", min=1, step=1, value=3),
                            ],
                            md=6,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="ftir-sim-minimum-score-label", html_for="ftir-sim-minimum-score", className="mb-1"),
                                dbc.Input(id="ftir-sim-minimum-score", type="number", min=0, max=1, step=0.01, value=0.45),
                            ],
                            md=6,
                        ),
                    ],
                    className="g-2",
                ),
            ]
        ),
        className="mb-3",
    )


# ---------------------------------------------------------------------------
# Left-column tabs
# ---------------------------------------------------------------------------


def _ftir_left_column_tabs() -> dbc.Tabs:
    return dbc.Tabs(
        [
            dbc.Tab(
                [
                    dataset_selection_card("ftir-dataset-selector-area", card_title_id="ftir-dataset-card-title"),
                    workflow_template_card(
                        "ftir-template-select",
                        "ftir-template-description",
                        [],
                        "ftir.general",
                        card_title_id="ftir-workflow-card-title",
                    ),
                    _ftir_workflow_guide_block(),
                    _ftir_raw_quality_card(),
                ],
                tab_id="ftir-tab-setup",
                label_class_name="ta-tab-label",
                id="ftir-tab-setup-shell",
            ),
            dbc.Tab(
                [
                    _ftir_processing_history_card(),
                    _ftir_preset_card(),
                    _ftir_smoothing_controls_card(),
                    _ftir_baseline_controls_card(),
                    _ftir_normalization_controls_card(),
                    _ftir_peak_detection_controls_card(),
                    _ftir_similarity_matching_controls_card(),
                ],
                tab_id="ftir-tab-processing",
                label_class_name="ta-tab-label",
                id="ftir-tab-processing-shell",
            ),
            dbc.Tab(
                [
                    execute_card("ftir-run-status", "ftir-run-btn", card_title_id="ftir-execute-card-title"),
                ],
                tab_id="ftir-tab-run",
                label_class_name="ta-tab-label",
                id="ftir-tab-run-shell",
            ),
        ],
        id="ftir-left-tabs",
        active_tab="ftir-tab-setup",
        className="mb-3",
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div(
    analysis_page_stores("ftir-refresh", "ftir-latest-result-id")
    + [
        dcc.Store(id="ftir-figure-captured", data={}),
        dcc.Store(id="ftir-processing-default", data=copy.deepcopy(_default_ftir_processing_draft())),
        dcc.Store(id="ftir-processing-draft", data=copy.deepcopy(_default_ftir_processing_draft())),
        dcc.Store(id="ftir-processing-undo-stack", data=[]),
        dcc.Store(id="ftir-processing-redo-stack", data=[]),
        dcc.Store(id="ftir-history-hydrate", data=0),
        dcc.Store(id="ftir-preset-refresh", data=0),
        dcc.Store(id="ftir-preset-hydrate", data=0),
        dcc.Store(id="ftir-preset-loaded-name", data=""),
        dcc.Store(id="ftir-preset-snapshot", data=None),
        html.Div(id="ftir-hero-slot"),
        dbc.Row(
            [
                dbc.Col(
                    [_ftir_left_column_tabs()],
                    md=4,
                ),
                dbc.Col(
                    [
                        _ftir_result_section(result_placeholder_card("ftir-result-analysis-summary"), role="context"),
                        _ftir_result_section(result_placeholder_card("ftir-result-metrics"), role="context"),
                        _ftir_result_section(result_placeholder_card("ftir-result-quality"), role="support"),
                        _ftir_result_section(result_placeholder_card("ftir-result-figure"), role="hero"),
                        _ftir_result_section(result_placeholder_card("ftir-result-top-match"), role="support"),
                        _ftir_result_section(result_placeholder_card("ftir-result-peak-cards"), role="support"),
                        _ftir_result_section(result_placeholder_card("ftir-result-match-table"), role="support"),
                        _ftir_result_section(result_placeholder_card("ftir-result-processing"), role="support"),
                        _ftir_result_section(result_placeholder_card("ftir-result-raw-metadata"), role="support"),
                        _ftir_result_section(build_literature_compare_card(id_prefix="ftir"), role="secondary"),
                    ],
                    md=8,
                    className="dsc-results-surface",
                ),
            ]
        ),
    ]
)


# ---------------------------------------------------------------------------
# Locale / chrome callbacks
# ---------------------------------------------------------------------------


@callback(
    Output("ftir-hero-slot", "children"),
    Output("ftir-dataset-card-title", "children"),
    Output("ftir-workflow-card-title", "children"),
    Output("ftir-execute-card-title", "children"),
    Output("ftir-run-btn", "children"),
    Output("ftir-template-select", "options"),
    Output("ftir-template-select", "value"),
    Output("ftir-template-description", "children"),
    Input("ui-locale", "data"),
    Input("ftir-template-select", "value"),
)
def render_ftir_locale_chrome(locale_data, template_id):
    loc = _loc(locale_data)
    hero = page_header(
        translate_ui(loc, "dash.analysis.ftir.title"),
        translate_ui(loc, "dash.analysis.ftir.caption"),
        badge=translate_ui(loc, "dash.analysis.badge"),
    )
    opts = [{"label": translate_ui(loc, f"dash.analysis.ftir.template.{tid}.label"), "value": tid} for tid in _FTIR_TEMPLATE_IDS]
    valid = {o["value"] for o in opts}
    tid = template_id if template_id in valid else "ftir.general"
    desc_key = f"dash.analysis.ftir.template.{tid}.desc"
    desc = translate_ui(loc, desc_key)
    if desc == desc_key:
        desc = translate_ui(loc, "dash.analysis.ftir.workflow_fallback")
    return (
        hero,
        translate_ui(loc, "dash.analysis.dataset_selection_title"),
        translate_ui(loc, "dash.analysis.workflow_template_title"),
        translate_ui(loc, "dash.analysis.execute_title"),
        translate_ui(loc, "dash.analysis.ftir.run_btn"),
        opts,
        tid,
        desc,
    )


@callback(
    Output("ftir-tab-setup-shell", "label"),
    Output("ftir-tab-processing-shell", "label"),
    Output("ftir-tab-run-shell", "label"),
    Input("ui-locale", "data"),
)
def render_ftir_tab_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.tga.tab.setup"),
        translate_ui(loc, "dash.analysis.tga.tab.processing"),
        translate_ui(loc, "dash.analysis.tga.tab.run"),
    )


@callback(
    Output("ftir-workflow-guide-title", "children"),
    Output("ftir-workflow-guide-body", "children"),
    Input("ui-locale", "data"),
)
def render_ftir_workflow_guide_chrome(locale_data):
    loc = _loc(locale_data)
    pfx = "dash.analysis.ftir.workflow_guide"
    body = html.Div(
        [
            html.P(translate_ui(loc, f"{pfx}.intro"), className="mb-2"),
            html.Ul(
                [
                    html.Li(translate_ui(loc, f"{pfx}.step1"), className="mb-1"),
                    html.Li(translate_ui(loc, f"{pfx}.step2"), className="mb-1"),
                    html.Li(translate_ui(loc, f"{pfx}.step3"), className="mb-1"),
                    html.Li(translate_ui(loc, f"{pfx}.step4"), className="mb-0"),
                ],
                className="ps-3 mb-0",
            ),
        ]
    )
    return translate_ui(loc, f"{pfx}.title"), body


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


@callback(
    Output("ftir-dataset-selector-area", "children"),
    Output("ftir-run-btn", "disabled"),
    Input("project-id", "data"),
    Input("ftir-refresh", "data"),
    Input("ui-locale", "data"),
)
def load_eligible_datasets(project_id, _refresh, locale_data):
    loc = _loc(locale_data)
    if not project_id:
        return html.P(translate_ui(loc, "dash.analysis.workspace_inactive"), className="text-muted"), True

    from dash_app.api_client import workspace_datasets

    try:
        payload = workspace_datasets(project_id)
    except Exception as exc:
        return dbc.Alert(translate_ui(loc, "dash.analysis.error_loading_datasets", error=str(exc)), color="danger"), True

    all_datasets = payload.get("datasets", [])
    return dataset_selector_block(
        selector_id="ftir-dataset-select",
        empty_msg=translate_ui(loc, "dash.analysis.ftir.empty_import"),
        eligible=eligible_datasets(all_datasets, _FTIR_ELIGIBLE_TYPES),
        all_datasets=all_datasets,
        eligible_types=_FTIR_ELIGIBLE_TYPES,
        active_dataset=payload.get("active_dataset"),
        locale_data=locale_data,
    )


# ---------------------------------------------------------------------------
# Preset callbacks
# ---------------------------------------------------------------------------


@callback(
    Output("ftir-preset-card-title", "children"),
    Output("ftir-preset-help", "children"),
    Output("ftir-preset-select-label", "children"),
    Output("ftir-preset-load-btn", "children"),
    Output("ftir-preset-delete-btn", "children"),
    Output("ftir-preset-save-name-label", "children"),
    Output("ftir-preset-save-name", "placeholder"),
    Output("ftir-preset-save-btn", "children"),
    Output("ftir-preset-saveas-btn", "children"),
    Output("ftir-preset-save-hint", "children"),
    Input("ui-locale", "data"),
)
def render_ftir_preset_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.tga.presets.title"),
        translate_ui(loc, "dash.analysis.tga.presets.help.overview"),
        translate_ui(loc, "dash.analysis.tga.presets.select_label"),
        translate_ui(loc, "dash.analysis.tga.presets.load_btn"),
        translate_ui(loc, "dash.analysis.tga.presets.delete_btn"),
        translate_ui(loc, "dash.analysis.tga.presets.save_name_label"),
        translate_ui(loc, "dash.analysis.tga.presets.save_name_placeholder"),
        translate_ui(loc, "dash.analysis.tga.presets.save_btn"),
        translate_ui(loc, "dash.analysis.tga.presets.saveas_btn"),
        translate_ui(loc, "dash.analysis.tga.presets.save_hint"),
    )


@callback(
    Output("ftir-preset-select", "options"),
    Output("ftir-preset-caption", "children"),
    Input("ftir-preset-refresh", "data"),
    Input("ui-locale", "data"),
)
def refresh_ftir_preset_options(_refresh_token, locale_data):
    from dash_app import api_client

    loc = _loc(locale_data)
    try:
        payload = api_client.list_analysis_presets(_FTIR_PRESET_ANALYSIS_TYPE)
    except Exception as exc:
        message = translate_ui(loc, "dash.analysis.tga.presets.list_failed").format(error=str(exc))
        return [], message

    presets = payload.get("presets") or []
    options = [
        {"label": item.get("preset_name", ""), "value": item.get("preset_name", "")}
        for item in presets
        if isinstance(item, dict) and item.get("preset_name")
    ]
    caption = translate_ui(loc, "dash.analysis.tga.presets.caption").format(
        analysis_type=payload.get("analysis_type", _FTIR_PRESET_ANALYSIS_TYPE),
        count=int(payload.get("count", len(options)) or 0),
        max_count=int(payload.get("max_count", 10) or 10),
    )
    return options, caption


@callback(
    Output("ftir-preset-load-btn", "disabled"),
    Output("ftir-preset-delete-btn", "disabled"),
    Output("ftir-preset-save-btn", "disabled"),
    Input("ftir-preset-select", "value"),
)
def toggle_ftir_preset_action_buttons(selected_name):
    has_selection = bool(str(selected_name or "").strip())
    return (not has_selection, not has_selection, not has_selection)


@callback(
    Output("ftir-processing-draft", "data", allow_duplicate=True),
    Output("ftir-template-select", "value", allow_duplicate=True),
    Output("ftir-preset-status", "children", allow_duplicate=True),
    Output("ftir-preset-hydrate", "data", allow_duplicate=True),
    Output("ftir-preset-loaded-name", "data", allow_duplicate=True),
    Output("ftir-preset-snapshot", "data", allow_duplicate=True),
    Output("ftir-left-tabs", "active_tab", allow_duplicate=True),
    Output("ftir-processing-undo-stack", "data", allow_duplicate=True),
    Output("ftir-processing-redo-stack", "data", allow_duplicate=True),
    Input("ftir-preset-load-btn", "n_clicks"),
    State("ftir-preset-select", "value"),
    State("ftir-preset-hydrate", "data"),
    State("ftir-processing-draft", "data"),
    State("ftir-processing-undo-stack", "data"),
    State("ftir-processing-redo-stack", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def apply_ftir_preset(n_clicks, selected_name, hydrate_val, current_draft, undo_stack, redo_stack, locale_data):
    from dash_app import api_client

    loc = _loc(locale_data)
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    name = str(selected_name or "").strip()
    if not name:
        return (
            dash.no_update,
            dash.no_update,
            translate_ui(loc, "dash.analysis.tga.presets.select_required"),
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )
    try:
        payload = api_client.load_analysis_preset(_FTIR_PRESET_ANALYSIS_TYPE, name)
    except Exception as exc:
        return (
            dash.no_update,
            dash.no_update,
            translate_ui(loc, "dash.analysis.tga.presets.load_failed").format(error=str(exc)),
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )

    processing = dict(payload.get("processing") or {})
    draft = _ftir_draft_from_loaded_processing(processing)
    template_id_raw = str(payload.get("workflow_template_id") or "").strip()
    template_out = template_id_raw if template_id_raw in _FTIR_TEMPLATE_IDS else dash.no_update
    resolved_tid = template_id_raw if template_id_raw in _FTIR_TEMPLATE_IDS else "ftir.general"
    snap = _ftir_ui_snapshot_dict(resolved_tid, draft)
    status = translate_ui(loc, "dash.analysis.tga.presets.loaded").format(preset=name)
    old_norm = _normalize_ftir_processing_draft(current_draft)
    new_norm = _normalize_ftir_processing_draft(draft)
    past2, fut2 = append_undo_after_edit(undo_stack, redo_stack, old_norm, new_norm)
    return (
        draft,
        template_out,
        status,
        int(hydrate_val or 0) + 1,
        name,
        snap,
        "ftir-tab-run",
        past2,
        fut2,
    )


@callback(
    Output("ftir-preset-refresh", "data", allow_duplicate=True),
    Output("ftir-preset-save-name", "value", allow_duplicate=True),
    Output("ftir-preset-status", "children", allow_duplicate=True),
    Output("ftir-preset-snapshot", "data", allow_duplicate=True),
    Output("ftir-left-tabs", "active_tab", allow_duplicate=True),
    Input("ftir-preset-save-btn", "n_clicks"),
    Input("ftir-preset-saveas-btn", "n_clicks"),
    State("ftir-preset-select", "value"),
    State("ftir-preset-save-name", "value"),
    State("ftir-processing-draft", "data"),
    State("ftir-template-select", "value"),
    State("ftir-preset-refresh", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def save_ftir_preset(n_save, n_saveas, selected_name, save_name, draft, template_id, refresh_token, locale_data):
    from dash_app import api_client

    loc = _loc(locale_data)
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    trig = ctx.triggered_id
    if trig == "ftir-preset-save-btn":
        name = str(selected_name or "").strip()
        if not name:
            return (
                dash.no_update,
                dash.no_update,
                translate_ui(loc, "dash.analysis.tga.presets.select_required"),
                dash.no_update,
                dash.no_update,
            )
        clear_name = dash.no_update
    elif trig == "ftir-preset-saveas-btn":
        name = str(save_name or "").strip()
        if not name:
            return (
                dash.no_update,
                dash.no_update,
                translate_ui(loc, "dash.analysis.tga.presets.save_name_required"),
                dash.no_update,
                dash.no_update,
            )
        clear_name = ""
    else:
        raise dash.exceptions.PreventUpdate

    processing_body = _ftir_preset_processing_body_for_save(draft)
    try:
        response = api_client.save_analysis_preset(
            _FTIR_PRESET_ANALYSIS_TYPE,
            name,
            workflow_template_id=str(template_id or "").strip() or None,
            processing=processing_body,
        )
    except Exception as exc:
        return (
            dash.no_update,
            dash.no_update,
            translate_ui(loc, "dash.analysis.tga.presets.save_failed").format(error=str(exc)),
            dash.no_update,
            dash.no_update,
        )
    resolved_template = str(response.get("workflow_template_id") or template_id or "")
    snap = _ftir_ui_snapshot_dict(str(template_id or "").strip() or None, draft)
    status = translate_ui(loc, "dash.analysis.tga.presets.saved").format(preset=name, template=resolved_template)
    return int(refresh_token or 0) + 1, clear_name, status, snap, "ftir-tab-run"


@callback(
    Output("ftir-preset-refresh", "data", allow_duplicate=True),
    Output("ftir-preset-select", "value", allow_duplicate=True),
    Output("ftir-preset-status", "children", allow_duplicate=True),
    Output("ftir-preset-loaded-name", "data", allow_duplicate=True),
    Output("ftir-preset-snapshot", "data", allow_duplicate=True),
    Input("ftir-preset-delete-btn", "n_clicks"),
    State("ftir-preset-select", "value"),
    State("ftir-preset-loaded-name", "data"),
    State("ftir-preset-refresh", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def delete_ftir_preset(n_clicks, selected_name, loaded_name, refresh_token, locale_data):
    from dash_app import api_client

    loc = _loc(locale_data)
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    name = str(selected_name or "").strip()
    if not name:
        return dash.no_update, dash.no_update, translate_ui(loc, "dash.analysis.tga.presets.select_required"), dash.no_update, dash.no_update
    try:
        api_client.delete_analysis_preset(_FTIR_PRESET_ANALYSIS_TYPE, name)
    except Exception as exc:
        return (
            dash.no_update,
            dash.no_update,
            translate_ui(loc, "dash.analysis.tga.presets.delete_failed").format(error=str(exc)),
            dash.no_update,
            dash.no_update,
        )
    status = translate_ui(loc, "dash.analysis.tga.presets.deleted").format(preset=name)
    loaded = str(loaded_name or "").strip()
    if loaded == name:
        return int(refresh_token or 0) + 1, None, status, "", None
    return int(refresh_token or 0) + 1, None, status, dash.no_update, dash.no_update


@callback(
    Output("ftir-preset-loaded-line", "children"),
    Input("ftir-preset-loaded-name", "data"),
    Input("ui-locale", "data"),
)
def render_ftir_preset_loaded_line(loaded_name, locale_data):
    loc = _loc(locale_data)
    name = str(loaded_name or "").strip()
    if not name:
        return ""
    return translate_ui(loc, "dash.analysis.tga.presets.loaded_line").format(preset=name)


@callback(
    Output("ftir-preset-dirty-flag", "children"),
    Input("ui-locale", "data"),
    Input("ftir-template-select", "value"),
    Input("ftir-smooth-method", "value"),
    Input("ftir-smooth-window", "value"),
    Input("ftir-smooth-polyorder", "value"),
    Input("ftir-smooth-sigma", "value"),
    Input("ftir-baseline-method", "value"),
    Input("ftir-baseline-lam", "value"),
    Input("ftir-baseline-p", "value"),
    Input("ftir-baseline-region-enabled", "value"),
    Input("ftir-baseline-region-min", "value"),
    Input("ftir-baseline-region-max", "value"),
    Input("ftir-norm-method", "value"),
    Input("ftir-peak-prominence", "value"),
    Input("ftir-peak-distance", "value"),
    Input("ftir-peak-max-peaks", "value"),
    Input("ftir-sim-top-n", "value"),
    Input("ftir-sim-minimum-score", "value"),
    State("ftir-preset-snapshot", "data"),
)
def render_ftir_preset_dirty_flag(
    locale_data,
    template_id,
    sm_m, sm_w, sm_p, sm_s,
    bl_m, bl_l, bl_p, bl_re, bl_rmin, bl_rmax,
    nm_m,
    pk_pr, pk_dist, pk_mp,
    sim_tn, sim_ms,
    snapshot,
):
    loc = _loc(locale_data)
    if not isinstance(snapshot, dict):
        return html.Span(translate_ui(loc, "dash.analysis.tga.presets.dirty_no_baseline"), className="text-muted")
    current = _ftir_ui_snapshot_dict(
        template_id,
        _ftir_draft_from_control_values(
            sm_m, sm_w, sm_p, sm_s,
            bl_m, bl_l, bl_p, bl_re, bl_rmin, bl_rmax,
            nm_m,
            pk_pr, pk_dist, pk_mp,
            sim_tn, sim_ms,
        ),
    )
    if _ftir_snapshots_equal(snapshot, current):
        return html.Span(translate_ui(loc, "dash.analysis.tga.presets.clean"), className="text-success")
    return html.Span(translate_ui(loc, "dash.analysis.tga.presets.dirty"), className="text-warning")


# ---------------------------------------------------------------------------
# Processing controls chrome
# ---------------------------------------------------------------------------


@callback(
    Output("ftir-processing-history-title", "children"),
    Output("ftir-processing-history-hint", "children"),
    Output("ftir-processing-undo-btn", "children"),
    Output("ftir-processing-redo-btn", "children"),
    Output("ftir-processing-reset-btn", "children"),
    Input("ui-locale", "data"),
)
def render_ftir_processing_history_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.tga.processing.history_title"),
        translate_ui(loc, "dash.analysis.tga.processing.history_hint"),
        translate_ui(loc, "dash.analysis.tga.processing.undo_btn"),
        translate_ui(loc, "dash.analysis.tga.processing.redo_btn"),
        translate_ui(loc, "dash.analysis.tga.processing.reset_btn"),
    )


@callback(
    Output("ftir-smoothing-card-title", "children"),
    Output("ftir-smoothing-card-hint", "children"),
    Output("ftir-smooth-method-label", "children"),
    Output("ftir-smooth-window-label", "children"),
    Output("ftir-smooth-polyorder-label", "children"),
    Output("ftir-smooth-sigma-label", "children"),
    Output("ftir-smooth-method", "options"),
    Input("ui-locale", "data"),
)
def render_ftir_smoothing_chrome(locale_data):
    loc = _loc(locale_data)
    smooth_opts = [
        {"label": translate_ui(loc, "dash.analysis.tga.processing.smooth.savgol"), "value": "savgol"},
        {"label": translate_ui(loc, "dash.analysis.tga.processing.smooth.moving_average"), "value": "moving_average"},
        {"label": translate_ui(loc, "dash.analysis.tga.processing.smooth.gaussian"), "value": "gaussian"},
    ]
    return (
        translate_ui(loc, "dash.analysis.tga.processing.smoothing_card_title"),
        translate_ui(loc, "dash.analysis.tga.processing.smoothing_card_hint"),
        translate_ui(loc, "dash.analysis.tga.processing.smooth.method"),
        translate_ui(loc, "dash.analysis.tga.processing.smooth.window"),
        translate_ui(loc, "dash.analysis.tga.processing.smooth.polyorder"),
        translate_ui(loc, "dash.analysis.tga.processing.smooth.sigma"),
        smooth_opts,
    )


@callback(
    Output("ftir-baseline-card-title", "children"),
    Output("ftir-baseline-card-hint", "children"),
    Output("ftir-baseline-method-label", "children"),
    Output("ftir-baseline-lam-label", "children"),
    Output("ftir-baseline-p-label", "children"),
    Output("ftir-baseline-region-section-title", "children"),
    Output("ftir-baseline-region-enable-hint", "children"),
    Output("ftir-baseline-region-min-label", "children"),
    Output("ftir-baseline-region-max-label", "children"),
    Input("ui-locale", "data"),
)
def render_ftir_baseline_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.dsc.baseline.title"),
        translate_ui(loc, "dash.analysis.dsc.baseline.help.method"),
        translate_ui(loc, "dash.analysis.dsc.baseline.method"),
        translate_ui(loc, "dash.analysis.dsc.baseline.lam"),
        translate_ui(loc, "dash.analysis.dsc.baseline.p"),
        translate_ui(loc, "dash.analysis.dsc.baseline.region_section"),
        translate_ui(loc, "dash.analysis.dsc.baseline.help.enable_region"),
        translate_ui(loc, "dash.analysis.dsc.baseline.region_min"),
        translate_ui(loc, "dash.analysis.dsc.baseline.region_max"),
    )


@callback(
    Output("ftir-normalization-card-title", "children"),
    Output("ftir-normalization-card-hint", "children"),
    Output("ftir-norm-method-label", "children"),
    Output("ftir-norm-method", "options"),
    Input("ui-locale", "data"),
)
def render_ftir_normalization_chrome(locale_data):
    loc = _loc(locale_data)
    opts = [
        {"label": translate_ui(loc, "dash.analysis.ftir.norm.vector"), "value": "vector"},
        {"label": translate_ui(loc, "dash.analysis.ftir.norm.max"), "value": "max"},
        {"label": translate_ui(loc, "dash.analysis.ftir.norm.snv"), "value": "snv"},
    ]
    return (
        translate_ui(loc, "dash.analysis.ftir.normalization.title"),
        translate_ui(loc, "dash.analysis.ftir.normalization.hint"),
        translate_ui(loc, "dash.analysis.ftir.normalization.method"),
        opts,
    )


@callback(
    Output("ftir-peak-card-title", "children"),
    Output("ftir-peak-card-hint", "children"),
    Output("ftir-peak-prominence-label", "children"),
    Output("ftir-peak-distance-label", "children"),
    Output("ftir-peak-max-peaks-label", "children"),
    Input("ui-locale", "data"),
)
def render_ftir_peak_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.ftir.peaks.title"),
        translate_ui(loc, "dash.analysis.ftir.peaks.hint"),
        translate_ui(loc, "dash.analysis.ftir.peaks.prominence"),
        translate_ui(loc, "dash.analysis.ftir.peaks.distance"),
        translate_ui(loc, "dash.analysis.ftir.peaks.max_peaks"),
    )


@callback(
    Output("ftir-similarity-card-title", "children"),
    Output("ftir-similarity-card-hint", "children"),
    Output("ftir-sim-top-n-label", "children"),
    Output("ftir-sim-minimum-score-label", "children"),
    Input("ui-locale", "data"),
)
def render_ftir_similarity_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.ftir.similarity.title"),
        translate_ui(loc, "dash.analysis.ftir.similarity.hint"),
        translate_ui(loc, "dash.analysis.ftir.similarity.top_n"),
        translate_ui(loc, "dash.analysis.ftir.similarity.minimum_score"),
    )


# ---------------------------------------------------------------------------
# Toggle inputs based on method
# ---------------------------------------------------------------------------


@callback(
    Output("ftir-smooth-window", "disabled"),
    Output("ftir-smooth-polyorder", "disabled"),
    Output("ftir-smooth-sigma", "disabled"),
    Input("ftir-smooth-method", "value"),
)
def toggle_ftir_smoothing_inputs(method):
    token = str(method or "savgol").strip().lower()
    if token == "savgol":
        return False, False, True
    if token == "moving_average":
        return False, True, True
    return True, True, False


@callback(
    Output("ftir-baseline-lam", "disabled"),
    Output("ftir-baseline-p", "disabled"),
    Input("ftir-baseline-method", "value"),
)
def toggle_ftir_baseline_inputs(method):
    token = str(method or "asls").strip().lower()
    if token == "asls":
        return False, False
    return True, True


@callback(
    Output("ftir-baseline-region-min", "disabled"),
    Output("ftir-baseline-region-max", "disabled"),
    Input("ftir-baseline-region-enabled", "value"),
)
def toggle_ftir_baseline_region_inputs(enabled):
    return (not bool(enabled), not bool(enabled))


# ---------------------------------------------------------------------------
# Hydrate controls from draft
# ---------------------------------------------------------------------------


@callback(
    Output("ftir-smooth-method", "value"),
    Output("ftir-smooth-window", "value"),
    Output("ftir-smooth-polyorder", "value"),
    Output("ftir-smooth-sigma", "value"),
    Output("ftir-baseline-method", "value"),
    Output("ftir-baseline-lam", "value"),
    Output("ftir-baseline-p", "value"),
    Output("ftir-baseline-region-enabled", "value"),
    Output("ftir-baseline-region-min", "value"),
    Output("ftir-baseline-region-max", "value"),
    Output("ftir-norm-method", "value"),
    Output("ftir-peak-prominence", "value"),
    Output("ftir-peak-distance", "value"),
    Output("ftir-peak-max-peaks", "value"),
    Output("ftir-sim-top-n", "value"),
    Output("ftir-sim-minimum-score", "value"),
    Input("ftir-preset-hydrate", "data"),
    Input("ftir-history-hydrate", "data"),
    State("ftir-processing-draft", "data"),
)
def hydrate_ftir_processing_controls(_preset_hydrate, _history_hydrate, draft):
    d = _normalize_ftir_processing_draft(draft)
    sm = d["smoothing"]
    bl = d["baseline"]
    nm = d["normalization"]
    pk = d["peak_detection"]
    sim = d["similarity_matching"]

    method = str(sm.get("method") or "savgol")
    wl = int(sm.get("window_length", 11))
    po = int(sm.get("polyorder", 3))
    sigma = float(sm.get("sigma", 2.0))

    bl_method = str(bl.get("method") or "asls")
    lam = float(bl.get("lam", 1e6))
    p = float(bl.get("p", 0.01))
    region = bl.get("region")
    enabled = isinstance(region, (list, tuple)) and len(region) == 2
    region_min = region[0] if enabled else None
    region_max = region[1] if enabled else None

    norm_method = str(nm.get("method") or "vector")

    prom = float(pk.get("prominence", 0.035))
    dist = int(pk.get("distance", 5))
    mp = int(pk.get("max_peaks", 10))

    top_n = int(sim.get("top_n", 3))
    min_score = float(sim.get("minimum_score", 0.45))

    return (
        method, wl, po, sigma,
        bl_method, lam, p, bool(enabled), region_min, region_max,
        norm_method,
        prom, dist, mp,
        top_n, min_score,
    )


# ---------------------------------------------------------------------------
# Sync draft from controls + history
# ---------------------------------------------------------------------------


@callback(
    Output("ftir-processing-draft", "data", allow_duplicate=True),
    Output("ftir-processing-undo-stack", "data", allow_duplicate=True),
    Output("ftir-processing-redo-stack", "data", allow_duplicate=True),
    Input("ftir-smooth-method", "value"),
    Input("ftir-smooth-window", "value"),
    Input("ftir-smooth-polyorder", "value"),
    Input("ftir-smooth-sigma", "value"),
    Input("ftir-baseline-method", "value"),
    Input("ftir-baseline-lam", "value"),
    Input("ftir-baseline-p", "value"),
    Input("ftir-baseline-region-enabled", "value"),
    Input("ftir-baseline-region-min", "value"),
    Input("ftir-baseline-region-max", "value"),
    Input("ftir-norm-method", "value"),
    Input("ftir-peak-prominence", "value"),
    Input("ftir-peak-distance", "value"),
    Input("ftir-peak-max-peaks", "value"),
    Input("ftir-sim-top-n", "value"),
    Input("ftir-sim-minimum-score", "value"),
    State("ftir-processing-draft", "data"),
    State("ftir-processing-undo-stack", "data"),
    State("ftir-processing-redo-stack", "data"),
    prevent_initial_call="initial_duplicate",
)
def sync_ftir_processing_draft_from_controls(
    sm_m, sm_w, sm_p, sm_s,
    bl_m, bl_l, bl_p, bl_re, bl_rmin, bl_rmax,
    nm_m,
    pk_pr, pk_dist, pk_mp,
    sim_tn, sim_ms,
    prev_draft, undo_stack, redo_stack,
):
    new_draft = _ftir_draft_from_control_values(
        sm_m, sm_w, sm_p, sm_s,
        bl_m, bl_l, bl_p, bl_re, bl_rmin, bl_rmax,
        nm_m,
        pk_pr, pk_dist, pk_mp,
        sim_tn, sim_ms,
    )
    old_norm = _normalize_ftir_processing_draft(prev_draft)
    new_norm = _normalize_ftir_processing_draft(new_draft)
    past2, fut2 = append_undo_after_edit(undo_stack, redo_stack, old_norm, new_norm)
    return new_norm, past2, fut2


@callback(
    Output("ftir-processing-draft", "data", allow_duplicate=True),
    Output("ftir-processing-undo-stack", "data", allow_duplicate=True),
    Output("ftir-processing-redo-stack", "data", allow_duplicate=True),
    Output("ftir-history-hydrate", "data", allow_duplicate=True),
    Output("ftir-history-status", "children", allow_duplicate=True),
    Input("ftir-processing-undo-btn", "n_clicks"),
    Input("ftir-processing-redo-btn", "n_clicks"),
    Input("ftir-processing-reset-btn", "n_clicks"),
    State("ftir-processing-draft", "data"),
    State("ftir-processing-undo-stack", "data"),
    State("ftir-processing-redo-stack", "data"),
    State("ftir-history-hydrate", "data"),
    State("ftir-processing-default", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def ftir_processing_history_actions(n_undo, n_redo, n_reset, draft, undo_stack, redo_stack, hist_hydrate, defaults, locale_data):
    loc = _loc(locale_data)
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    trig = ctx.triggered_id
    cur = _normalize_ftir_processing_draft(draft)
    past = undo_stack or []
    fut = redo_stack or []
    h = int(hist_hydrate or 0)

    if trig == "ftir-processing-undo-btn":
        if not n_undo:
            raise dash.exceptions.PreventUpdate
        res = perform_undo(past, fut, cur)
        if res is None:
            raise dash.exceptions.PreventUpdate
        prev, pl, fl = res
        return prev, pl, fl, h + 1, translate_ui(loc, "dash.analysis.tga.processing.history_status_undo")

    if trig == "ftir-processing-redo-btn":
        if not n_redo:
            raise dash.exceptions.PreventUpdate
        res = perform_redo(past, fut, cur)
        if res is None:
            raise dash.exceptions.PreventUpdate
        nxt, pl, fl = res
        return nxt, pl, fl, h + 1, translate_ui(loc, "dash.analysis.tga.processing.history_status_redo")

    if trig == "ftir-processing-reset-btn":
        if not n_reset:
            raise dash.exceptions.PreventUpdate
        default_draft = _normalize_ftir_processing_draft(copy.deepcopy(defaults or _default_ftir_processing_draft()))
        if ftir_draft_processing_equal(cur, default_draft):
            raise dash.exceptions.PreventUpdate
        past_list = [copy.deepcopy(x) for x in past if isinstance(x, dict)]
        past_list.append(copy.deepcopy(cur))
        if len(past_list) > MAX_FTIR_UNDO_DEPTH:
            past_list = past_list[-MAX_FTIR_UNDO_DEPTH:]
        return default_draft, past_list, [], h + 1, translate_ui(loc, "dash.analysis.tga.processing.history_status_reset")

    raise dash.exceptions.PreventUpdate


@callback(
    Output("ftir-processing-undo-btn", "disabled"),
    Output("ftir-processing-redo-btn", "disabled"),
    Input("ftir-processing-undo-stack", "data"),
    Input("ftir-processing-redo-stack", "data"),
)
def toggle_ftir_processing_history_buttons(undo_stack, redo_stack):
    u = undo_stack or []
    r = redo_stack or []
    return len(u) == 0, len(r) == 0


# ---------------------------------------------------------------------------
# Raw quality callbacks
# ---------------------------------------------------------------------------


@callback(
    Output("ftir-raw-quality-card-title", "children"),
    Output("ftir-raw-quality-card-hint", "children"),
    Input("ui-locale", "data"),
)
def render_ftir_raw_quality_chrome(locale_data):
    loc = _loc(locale_data)
    return translate_ui(loc, "dash.analysis.ftir.raw_quality.card_title"), translate_ui(loc, "dash.analysis.ftir.raw_quality.card_hint")


@callback(
    Output("ftir-raw-quality-panel", "children"),
    Input("project-id", "data"),
    Input("ftir-dataset-select", "value"),
    Input("ftir-refresh", "data"),
    Input("ui-locale", "data"),
)
def render_ftir_raw_quality_panel(project_id, dataset_key, _refresh, locale_data):
    loc = _loc(locale_data)
    if not project_id or not dataset_key:
        return html.P(translate_ui(loc, "dash.analysis.ftir.raw_quality.pick_dataset"), className="text-muted small mb-0")
    from dash_app.api_client import workspace_dataset_data, workspace_dataset_detail

    try:
        detail = workspace_dataset_detail(project_id, dataset_key)
        data = workspace_dataset_data(project_id, dataset_key)
    except Exception as exc:
        return html.P(translate_ui(loc, "dash.analysis.ftir.raw_quality.load_failed", error=str(exc)), className="text-danger small mb-0")

    rows = data.get("rows") or []
    columns = data.get("columns") or []
    t_arr, s_arr = downsample_rows(rows, columns)
    validation = detail.get("validation") if isinstance(detail.get("validation"), dict) else {}
    stats = compute_ftir_raw_exploration_stats(t_arr, s_arr, validation=validation)
    units = detail.get("units") or {}
    sig_u = str(units.get("signal") or "")
    return build_ftir_raw_quality_panel(stats, loc, signal_unit=sig_u)


# ---------------------------------------------------------------------------
# Run analysis
# ---------------------------------------------------------------------------


@callback(
    Output("ftir-run-status", "children"),
    Output("ftir-refresh", "data", allow_duplicate=True),
    Output("ftir-latest-result-id", "data", allow_duplicate=True),
    Output("workspace-refresh", "data", allow_duplicate=True),
    Input("ftir-run-btn", "n_clicks"),
    State("project-id", "data"),
    State("ftir-dataset-select", "value"),
    State("ftir-template-select", "value"),
    State("ftir-processing-draft", "data"),
    State("ftir-refresh", "data"),
    State("workspace-refresh", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def run_ftir_analysis(n_clicks, project_id, dataset_key, template_id, processing_draft, refresh_val, global_refresh, locale_data):
    loc = _loc(locale_data)
    if not n_clicks or not project_id or not dataset_key:
        raise dash.exceptions.PreventUpdate

    from dash_app.api_client import analysis_run

    overrides = _ftir_overrides_from_draft(processing_draft)
    try:
        result = analysis_run(
            project_id=project_id,
            dataset_key=dataset_key,
            analysis_type="FTIR",
            workflow_template_id=template_id,
            processing_overrides=overrides or None,
        )
    except Exception as exc:
        return dbc.Alert(translate_ui(loc, "dash.analysis.analysis_failed", error=str(exc)), color="danger"), dash.no_update, dash.no_update, dash.no_update

    alert, saved, result_id = interpret_run_result(result, locale_data=locale_data)
    refresh = (refresh_val or 0) + 1
    if saved:
        return alert, refresh, result_id, (global_refresh or 0) + 1
    return alert, refresh, dash.no_update, dash.no_update


# ---------------------------------------------------------------------------
# Display result (right-column surface)
# ---------------------------------------------------------------------------


@callback(
    Output("ftir-result-analysis-summary", "children"),
    Output("ftir-result-metrics", "children"),
    Output("ftir-result-quality", "children"),
    Output("ftir-result-figure", "children"),
    Output("ftir-result-top-match", "children"),
    Output("ftir-result-peak-cards", "children"),
    Output("ftir-result-match-table", "children"),
    Output("ftir-result-processing", "children"),
    Output("ftir-result-raw-metadata", "children"),
    Input("ftir-latest-result-id", "data"),
    Input("ftir-refresh", "data"),
    Input("ui-theme", "data"),
    Input("ui-locale", "data"),
    State("project-id", "data"),
)
def display_result(result_id, _refresh, ui_theme, locale_data, project_id):
    loc = _loc(locale_data)
    empty_msg = empty_result_msg(locale_data=locale_data)
    summary_empty = html.P(translate_ui(loc, "dash.analysis.ftir.summary.empty"), className="text-muted")
    quality_empty = _ftir_collapsible_section(
        loc,
        "dash.analysis.dsc.quality.card_title",
        html.P(translate_ui(loc, "dash.analysis.dsc.quality.empty"), className="text-muted mb-0"),
        open=False,
    )
    raw_meta_empty = _ftir_collapsible_section(
        loc,
        "dash.analysis.dsc.raw_metadata.card_title",
        html.P(translate_ui(loc, "dash.analysis.dsc.raw_metadata.empty"), className="text-muted mb-0"),
        open=False,
    )
    if not result_id or not project_id:
        return (
            summary_empty,
            empty_msg,
            quality_empty,
            empty_msg,
            empty_msg,
            empty_msg,
            empty_msg,
            empty_msg,
            raw_meta_empty,
        )

    from dash_app.api_client import workspace_dataset_detail, workspace_result_detail

    try:
        detail = workspace_result_detail(project_id, result_id)
    except Exception as exc:
        err = dbc.Alert(translate_ui(loc, "dash.analysis.error_loading_result", error=str(exc)), color="danger")
        return summary_empty, err, quality_empty, empty_msg, empty_msg, empty_msg, empty_msg, empty_msg, raw_meta_empty

    summary = detail.get("summary", {})
    result_meta = detail.get("result", {})
    processing = detail.get("processing", {})
    rows = detail.get("rows_preview", [])
    dataset_key = result_meta.get("dataset_key")

    dataset_detail: dict = {}
    if dataset_key:
        try:
            dataset_detail = workspace_dataset_detail(project_id, dataset_key)
        except Exception:
            dataset_detail = {}

    analysis_summary = _build_ftir_analysis_summary(
        dataset_detail,
        summary,
        result_meta,
        loc,
        locale_data=locale_data,
    )
    quality_panel = _build_ftir_quality_card(detail, result_meta, loc)
    raw_metadata_panel = _build_ftir_raw_metadata_panel((dataset_detail or {}).get("metadata"), loc)

    peak_count = summary.get("peak_count", 0)
    match_status = _match_status_label(loc, summary.get("match_status"))
    top_score = summary.get("top_match_score", 0.0)
    sample_name = resolve_sample_name(summary, result_meta, locale_data=locale_data)
    na = translate_ui(loc, "dash.analysis.na")
    top_score_str = f"{top_score:.4f}" if top_score else na

    metrics = metrics_row(
        [
            ("dash.analysis.metric.peaks", str(peak_count)),
            ("dash.analysis.metric.match_status", match_status),
            ("dash.analysis.metric.top_score", top_score_str),
            ("dash.analysis.metric.sample", sample_name),
        ],
        locale_data=locale_data,
    )

    figure_area = empty_msg
    top_match_area = empty_msg
    peak_cards_area = empty_msg
    if dataset_key:
        figure_area = _build_figure(project_id, dataset_key, summary, ui_theme, loc)
        top_match_area = _build_top_match_panel(summary, rows, loc)
        peak_cards_area = _build_peak_cards_from_curves(project_id, dataset_key, summary, loc)

    table_area = _build_match_table(rows, loc, summary=summary)

    proc_view = processing_details_section(
        processing,
        extra_lines=[
            html.P(translate_ui(loc, "dash.analysis.ftir.baseline", detail=processing.get("signal_pipeline", {}).get("baseline", {}))),
            html.P(translate_ui(loc, "dash.analysis.ftir.normalization", detail=processing.get("signal_pipeline", {}).get("normalization", {}))),
            html.P(translate_ui(loc, "dash.analysis.ftir.peak_detection", detail=processing.get("analysis_steps", {}).get("peak_detection", {}))),
            html.P(translate_ui(loc, "dash.analysis.ftir.similarity_matching", detail=processing.get("analysis_steps", {}).get("similarity_matching", {}))),
            html.P(
                translate_ui(
                    loc,
                    "dash.analysis.ftir.library",
                    mode=processing.get("method_context", {}).get("library_access_mode", na),
                    source=processing.get("method_context", {}).get("library_result_source", na),
                ),
                className="mb-0",
            ),
        ],
        locale_data=locale_data,
    )

    return (
        analysis_summary,
        metrics,
        quality_panel,
        figure_area,
        top_match_area,
        peak_cards_area,
        table_area,
        proc_view,
        raw_metadata_panel,
    )


# ---------------------------------------------------------------------------
# Literature callbacks
# ---------------------------------------------------------------------------


@callback(
    Output("ftir-literature-card-title", "children"),
    Output("ftir-literature-hint", "children"),
    Output("ftir-literature-max-claims-label", "children"),
    Output("ftir-literature-persist-label", "children"),
    Output("ftir-literature-compare-btn", "children"),
    Input("ui-locale", "data"),
    Input("ftir-latest-result-id", "data"),
)
def render_ftir_literature_chrome(locale_data, result_id):
    loc = _loc(locale_data)
    if result_id:
        hint = literature_t(
            loc,
            f"{_FTIR_LITERATURE_PREFIX}.ready",
            "Compare the saved FTIR result to literature sources.",
        )
    else:
        hint = literature_t(
            loc,
            f"{_FTIR_LITERATURE_PREFIX}.empty",
            "Run an FTIR analysis first to enable literature comparison.",
        )
    return (
        literature_t(loc, f"{_FTIR_LITERATURE_PREFIX}.title", "Literature Compare"),
        hint,
        literature_t(loc, f"{_FTIR_LITERATURE_PREFIX}.max_claims", "Max Claims"),
        literature_t(loc, f"{_FTIR_LITERATURE_PREFIX}.persist", "Persist to project"),
        literature_t(loc, f"{_FTIR_LITERATURE_PREFIX}.compare_btn", "Compare"),
    )


@callback(
    Output("ftir-literature-compare-btn", "disabled"),
    Input("ftir-latest-result-id", "data"),
)
def toggle_ftir_literature_compare_button(result_id):
    return not bool(result_id)


@callback(
    Output("ftir-literature-output", "children"),
    Output("ftir-literature-status", "children"),
    Input("ftir-literature-compare-btn", "n_clicks"),
    State("project-id", "data"),
    State("ftir-latest-result-id", "data"),
    State("ftir-literature-max-claims", "value"),
    State("ftir-literature-persist", "value"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def compare_ftir_literature(n_clicks, project_id, result_id, max_claims, persist_values, locale_data):
    loc = _loc(locale_data)
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    if not project_id or not result_id:
        msg = literature_t(
            loc,
            f"{_FTIR_LITERATURE_PREFIX}.missing_result",
            "Run an FTIR analysis first.",
        )
        return dash.no_update, dbc.Alert(msg, color="warning", className="py-1 small")

    claims_limit = coerce_literature_max_claims(max_claims, default=3)
    persist = bool(persist_values) and "persist" in (persist_values or [])

    from dash_app.api_client import literature_compare

    try:
        payload = literature_compare(
            project_id,
            result_id,
            max_claims=claims_limit,
            persist=persist,
        )
    except Exception as exc:
        err = dbc.Alert(
            literature_t(
                loc,
                f"{_FTIR_LITERATURE_PREFIX}.error",
                "Literature compare failed: {error}",
            ).replace("{error}", str(exc)),
            color="danger",
            className="py-1 small",
        )
        return dash.no_update, err

    return (
        render_literature_output(
            payload,
            loc,
            i18n_prefix=_FTIR_LITERATURE_PREFIX,
            evidence_preview_limit=LITERATURE_COMPACT_EVIDENCE_PREVIEW_LIMIT,
            alternative_preview_limit=LITERATURE_COMPACT_ALTERNATIVE_PREVIEW_LIMIT,
        ),
        literature_compare_status_alert(payload, loc, i18n_prefix=_FTIR_LITERATURE_PREFIX),
    )


# ---------------------------------------------------------------------------
# Figure capture
# ---------------------------------------------------------------------------


@callback(
    Output("ftir-figure-captured", "data"),
    Input("ftir-latest-result-id", "data"),
    Input("project-id", "data"),
    Input("ftir-result-figure", "children"),
    State("ftir-figure-captured", "data"),
    prevent_initial_call=True,
)
def capture_ftir_figure(result_id, project_id, figure_children, captured):
    return capture_result_figure_from_layout(
        result_id=result_id,
        project_id=project_id,
        figure_children=figure_children,
        captured=captured,
        analysis_type="FTIR",
    )


# ---------------------------------------------------------------------------
# FTIR-specific result builders
# ---------------------------------------------------------------------------


def _format_dataset_metadata_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        if value != value:
            return None
        text = f"{value:g}"
    else:
        text = str(value).strip()
    return text or None


def _match_status_label(loc: str, raw: str | None) -> str:
    token = str(raw or "no_match").lower().replace(" ", "_")
    key = f"dash.analysis.match_status.{token}"
    text = translate_ui(loc, key)
    if text == key:
        s = str(raw or "").replace("_", " ").strip()
        return s.title() if s else translate_ui(loc, "dash.analysis.na")
    return text


def _confidence_band_label(loc: str, band: str | None) -> str:
    token = str(band or "no_match").lower().replace(" ", "_")
    key = f"dash.analysis.confidence.{token}"
    text = translate_ui(loc, key)
    if text == key:
        return str(band).replace("_", " ").title()
    return text


_CONFIDENCE_COLORS = {
    "high_confidence": "#059669",
    "moderate_confidence": "#D97706",
    "low_confidence": "#DC2626",
    "no_match": "#6B7280",
}

_FTIR_FIGURE_COLORS = {
    "query": "#0F172A",
    "smoothed": "#0E7490",
    "raw": "#94A3B8",
    "baseline": "#B45309",
    "normalized": "#7C3AED",
    "grid": "rgba(148, 163, 184, 0.18)",
    "axis": "#475569",
    "panel": "#FCFDFE",
}


def _build_ftir_analysis_summary(
    dataset_detail: dict,
    summary: dict,
    result_meta: dict,
    loc: str,
    *,
    locale_data: str | None = None,
) -> html.Div:
    metadata = (dataset_detail or {}).get("metadata") or {}
    dataset_summary = (dataset_detail or {}).get("dataset") or {}
    na = translate_ui(loc, "dash.analysis.na")

    dataset_label = (
        _format_dataset_metadata_value(metadata.get("file_name"))
        or _format_dataset_metadata_value(dataset_summary.get("display_name"))
        or _format_dataset_metadata_value(result_meta.get("dataset_key"))
        or na
    )
    fallback_display_name = _format_dataset_metadata_value(dataset_summary.get("display_name"))
    sample_label = resolve_sample_name(
        summary or {},
        result_meta or {},
        fallback_display_name=fallback_display_name,
        locale_data=locale_data,
    ) or na

    instrument = _format_dataset_metadata_value(metadata.get("instrument")) or na
    vendor = _format_dataset_metadata_value(metadata.get("vendor")) or na

    def _meta_value(value: str) -> html.Span:
        return html.Span(value, className="dsc-meta-value", title=value)

    dl_rows: list[Any] = [
        html.Dt(translate_ui(loc, "dash.analysis.dsc.summary.dataset_label"), className="col-sm-4 text-muted dsc-meta-term"),
        html.Dd(_meta_value(dataset_label), className="col-sm-8 dsc-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.dsc.summary.sample_label"), className="col-sm-4 text-muted dsc-meta-term"),
        html.Dd(_meta_value(sample_label), className="col-sm-8 dsc-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.ftir.summary.instrument_label"), className="col-sm-4 text-muted dsc-meta-term"),
        html.Dd(_meta_value(instrument), className="col-sm-8 dsc-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.ftir.summary.vendor_label"), className="col-sm-4 text-muted dsc-meta-term"),
        html.Dd(_meta_value(vendor), className="col-sm-8 dsc-meta-def"),
    ]
    return html.Div(
        [
            html.H5(translate_ui(loc, "dash.analysis.ftir.summary.card_title"), className="mb-3"),
            html.Dl(dl_rows, className="row mb-0"),
        ]
    )


def _build_ftir_quality_card(detail: dict, result_meta: dict, loc: str) -> html.Details:
    validation = detail.get("validation") if isinstance(detail.get("validation"), dict) else {}
    status = str(validation.get("status") or result_meta.get("validation_status") or "unknown")
    warnings_list = validation.get("warnings") if isinstance(validation.get("warnings"), list) else []
    issues_list = validation.get("issues") if isinstance(validation.get("issues"), list) else []
    wc = int(validation.get("warning_count", len(warnings_list)) or 0)
    ic = int(validation.get("issue_count", len(issues_list)) or 0)

    status_token = status.strip().lower()
    if status_token in {"ok", "pass", "valid"} and wc == 0 and ic == 0:
        alert_color = "success"
    elif ic == 0:
        alert_color = "warning"
    else:
        alert_color = "danger"

    body_children: list[Any] = [
        html.P([html.Strong(translate_ui(loc, "dash.analysis.dsc.quality.status_label")), f" {status}"], className="mb-2"),
        html.P([html.Strong(translate_ui(loc, "dash.analysis.dsc.quality.warnings_label")), f" {wc}"], className="mb-2"),
        html.P([html.Strong(translate_ui(loc, "dash.analysis.dsc.quality.issues_label")), f" {ic}"], className="mb-0"),
    ]
    if warnings_list:
        body_children.append(html.Ul([html.Li(str(w)) for w in warnings_list[:12]], className="small mb-0 mt-2"))
    if issues_list:
        body_children.append(html.Ul([html.Li(str(w)) for w in issues_list[:12]], className="small mb-0 mt-2"))

    inner = dbc.Alert(body_children, color=alert_color, className="mb-0 ta-quality-alert")
    has_attention = wc > 0 or ic > 0
    badges: list[Any] = []
    if wc:
        badges.append(
            dbc.Badge(
                translate_ui(loc, "dash.analysis.tga.quality.badge_warnings", n=wc),
                color="warning",
                text_color="dark",
                className="ms-2",
                pill=True,
            )
        )
    if ic:
        badges.append(
            dbc.Badge(
                translate_ui(loc, "dash.analysis.tga.quality.badge_issues", n=ic),
                color="danger",
                className="ms-2",
                pill=True,
            )
        )
    return _ftir_collapsible_section(
        loc,
        "dash.analysis.dsc.quality.card_title",
        inner,
        open=has_attention,
        summary_suffix=badges if badges else None,
    )


def _build_ftir_raw_metadata_panel(metadata: dict | None, loc: str) -> html.Details:
    meta = metadata if isinstance(metadata, dict) else {}
    if not meta:
        inner = html.P(translate_ui(loc, "dash.analysis.dsc.raw_metadata.empty"), className="text-muted mb-0")
    else:
        user_keys = sorted([k for k in meta if k in _FTIR_USER_FACING_METADATA_KEYS], key=lambda k: str(k).lower())
        tech_keys = sorted([k for k in meta if k not in _FTIR_USER_FACING_METADATA_KEYS], key=lambda k: str(k).lower())

        def _make_rows(keys: list[str]) -> list[Any]:
            rows: list[Any] = []
            for key in keys:
                value = meta[key]
                if isinstance(value, (dict, list)):
                    text = json.dumps(value, ensure_ascii=False, indent=2)
                else:
                    fv = _format_dataset_metadata_value(value)
                    text = fv if fv is not None else str(value)
                rows.extend([
                    html.Dt(str(key), className="col-sm-4 text-muted small"),
                    html.Dd(html.Pre(text, className="small mb-0 ta-code-block p-2 rounded"), className="col-sm-8 mb-2"),
                ])
            return rows

        body_parts: list[Any] = []
        if user_keys:
            body_parts.append(html.Dl(_make_rows(user_keys), className="row mb-0"))
        if tech_keys:
            tech_collapsible = html.Details(
                [
                    html.Summary(
                        [
                            html.Span(className="ta-details-chevron"),
                            html.Span(translate_ui(loc, "dash.analysis.dsc.raw_metadata.technical_details") or "Technical details", className="ms-1"),
                        ],
                        className="ta-details-summary",
                    ),
                    html.Div(html.Dl(_make_rows(tech_keys), className="row mb-0"), className="ta-details-body mt-2"),
                ],
                className="ta-ms-details mb-0",
                open=False,
            )
            body_parts.append(html.Div(tech_collapsible, className="mt-2"))
        inner = html.Div(body_parts) if body_parts else html.P(translate_ui(loc, "dash.analysis.dsc.raw_metadata.empty"), className="text-muted mb-0")
    return _ftir_collapsible_section(loc, "dash.analysis.dsc.raw_metadata.card_title", inner, open=False)


def _finite_series(values: list | None) -> list[float]:
    series: list[float] = []
    for value in values or []:
        if value is None:
            continue
        numeric = float(value)
        if math.isfinite(numeric):
            series.append(numeric)
    return series


def _y_axis_range(*series: list | None) -> list[float] | None:
    values: list[float] = []
    for entry in series:
        values.extend(_finite_series(entry))
    if not values:
        return None
    y_min = min(values)
    y_max = max(values)
    span = y_max - y_min
    padding = span * 0.08 if span > 0 else max(abs(y_max) * 0.12, 0.05)
    return [y_min - padding, y_max + padding]


def _build_figure(project_id: str, dataset_key: str, summary: dict, ui_theme: str | None, loc: str) -> html.Div:
    from dash_app.api_client import analysis_state_curves

    try:
        curves = analysis_state_curves(project_id, "FTIR", dataset_key)
    except Exception:
        curves = {}

    wavenumber = curves.get("temperature", [])
    raw_signal = curves.get("raw_signal", [])
    smoothed = curves.get("smoothed", [])
    baseline = curves.get("baseline", [])
    corrected = curves.get("corrected", [])
    normalized = curves.get("normalized", [])
    peaks = curves.get("peaks", [])
    diagnostics = curves.get("diagnostics") or {}

    has_corrected = bool(corrected and len(corrected) == len(wavenumber))
    has_smoothed = bool(smoothed and len(smoothed) == len(wavenumber))
    has_normalized_curve = bool(normalized and len(normalized) == len(wavenumber))
    has_baseline = bool(baseline and len(baseline) == len(wavenumber))
    plot_norm_primary = diagnostics.get("plot_normalized_primary_axis") is not False
    show_normalized_trace = bool(has_normalized_curve and plot_norm_primary)
    show_intermediate_smoothed = bool(has_smoothed and not has_corrected)
    show_baseline_trace = bool(has_baseline and has_corrected)

    has_overlay = bool(
        show_baseline_trace
        or show_intermediate_smoothed
        or has_corrected
        or show_normalized_trace
        or (bool(raw_signal and len(raw_signal) == len(wavenumber)) and (has_corrected or show_intermediate_smoothed))
    )

    if not wavenumber:
        return no_data_figure_msg(locale_data=loc)

    sample_name = resolve_sample_name(summary, {}, fallback_display_name=dataset_key, locale_data=loc)
    tone = normalize_ui_theme(ui_theme)
    pt = PLOT_THEME[tone]
    muted = "#66645E" if tone == "light" else "#9E9A93"
    legend_bg = "rgba(255,255,255,0.9)" if tone == "light" else "rgba(26,25,23,0.94)"
    hover_bg = "rgba(255,255,255,0.96)" if tone == "light" else "rgba(34,33,30,0.96)"
    hover_fg = "#1C1A1A" if tone == "light" else "#EEEDEA"

    dominant_signal = corrected if has_corrected else smoothed if has_smoothed else raw_signal
    legend_query = translate_ui(loc, "dash.analysis.figure.legend_query_spectrum")
    legend_smooth = translate_ui(loc, "dash.analysis.figure.legend_smoothed_spectrum")
    legend_imported = translate_ui(loc, "dash.analysis.figure.legend_imported_spectrum")
    legend_baseline = translate_ui(loc, "dash.analysis.figure.legend_estimated_baseline")
    legend_normalized = translate_ui(loc, "dash.analysis.ftir.legend_normalized_spectrum")

    if diagnostics.get("inverted_for_transmittance"):
        suffix = " (inverted)"
        legend_smooth += suffix
        legend_query += suffix
        legend_normalized += suffix

    y_series_for_range = [dominant_signal, raw_signal]
    if show_baseline_trace:
        y_series_for_range.append(baseline)
    if show_intermediate_smoothed:
        y_series_for_range.append(smoothed)
    if show_normalized_trace:
        y_series_for_range.append(normalized)
    y_range = _y_axis_range(*y_series_for_range)

    fig = go.Figure()

    if show_baseline_trace:
        fig.add_trace(
            go.Scatter(
                x=wavenumber,
                y=baseline,
                mode="lines",
                name=legend_baseline,
                line=dict(color=_FTIR_FIGURE_COLORS["baseline"], width=1.3, dash="dash"),
                opacity=0.65,
            )
        )

    if raw_signal and len(raw_signal) == len(wavenumber):
        fig.add_trace(
            go.Scatter(
                x=wavenumber,
                y=raw_signal,
                mode="lines",
                name=legend_imported,
                line=dict(color=_FTIR_FIGURE_COLORS["raw"], width=1.6),
                opacity=0.45 if has_overlay else 0.95,
            )
        )

    if show_intermediate_smoothed:
        fig.add_trace(
            go.Scatter(
                x=wavenumber,
                y=smoothed,
                mode="lines",
                name=legend_smooth,
                line=dict(color=_FTIR_FIGURE_COLORS["smoothed"], width=2.0),
                opacity=0.95,
            )
        )

    if has_corrected:
        fig.add_trace(
            go.Scatter(
                x=wavenumber,
                y=corrected,
                mode="lines",
                name=legend_query,
                line=dict(color=_FTIR_FIGURE_COLORS["query"], width=3.2),
                opacity=0.95 if show_normalized_trace else 1.0,
            )
        )

    if show_normalized_trace:
        fig.add_trace(
            go.Scatter(
                x=wavenumber,
                y=normalized,
                mode="lines",
                name=legend_normalized,
                line=dict(color=_FTIR_FIGURE_COLORS["normalized"], width=2.4),
            )
        )

    def _peak_display_y(index: int) -> float | None:
        if has_corrected and index < len(corrected):
            return float(corrected[index])
        if show_intermediate_smoothed and index < len(smoothed):
            return float(smoothed[index])
        if raw_signal and index < len(raw_signal):
            return float(raw_signal[index])
        return None

    # Peak annotations (top 8 only to avoid clutter)
    _ANNOTATION_MIN_SEP = 20.0
    annotated_positions: list[float] = []
    peak_count = len(peaks)
    for i, peak in enumerate(peaks[:_FTIR_MAX_PEAK_CARDS]):
        pos = peak.get("position")
        intensity = peak.get("intensity")
        if pos is None or not wavenumber:
            continue
        idx = min(range(len(wavenumber)), key=lambda i: abs(wavenumber[i] - pos))
        too_close = any(abs(pos - p) < _ANNOTATION_MIN_SEP for p in annotated_positions)
        label = "" if too_close else f"{pos:.0f}"
        y_at = _peak_display_y(idx)
        if y_at is None:
            continue
        fig.add_trace(
            go.Scatter(
                x=[wavenumber[idx]],
                y=[y_at],
                mode="markers+text",
                marker=dict(size=7, color="#DC2626", symbol="diamond", line=dict(color="white", width=1)),
                text=[label],
                textposition="top center",
                textfont=dict(size=8, color="#DC2626"),
                name=f"Peak {pos:.0f}",
                showlegend=False,
            )
        )
        if label:
            annotated_positions.append(pos)

    title_main = translate_ui(loc, "dash.analysis.figure.title_ftir_main")
    fig.update_layout(
        title=(f"{title_main}<br><span style='font-size:0.82em;color:{muted}'>{sample_name}</span>"),
        paper_bgcolor=pt["paper_bg"],
        plot_bgcolor=pt["plot_bg"],
        hovermode="x unified",
        xaxis_title=translate_ui(loc, "dash.analysis.figure.axis_wavenumber"),
        yaxis_title=translate_ui(loc, "dash.analysis.figure.axis_signal_au"),
        xaxis=dict(
            autorange="reversed",
            showgrid=True,
            gridcolor=pt["grid"],
            linecolor=pt["grid"],
            tickfont=dict(size=12, color=pt["text"]),
            title_font=dict(size=13, color=pt["text"]),
            zeroline=False,
        ),
        yaxis=dict(
            range=y_range,
            showgrid=True,
            gridcolor=pt["grid"],
            linecolor=pt["grid"],
            tickfont=dict(size=12, color=pt["text"]),
            title_font=dict(size=13, color=pt["text"]),
            zeroline=False,
        ),
        margin=dict(l=64, r=28, t=82, b=56),
        height=520,
        title_font=dict(size=20, color=pt["text"]),
        title_x=0.01,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            bgcolor=legend_bg,
            bordercolor=pt["grid"],
            borderwidth=1,
            font=dict(size=12, color=pt["text"]),
        ),
        hoverlabel=dict(bgcolor=hover_bg, font=dict(color=hover_fg)),
    )
    fig.update_layout(template=pt["template"])

    peak_count_disp = summary.get("peak_count", peak_count)
    top_match_name = summary.get("top_match_name")
    match_status = _match_status_label(loc, summary.get("match_status"))
    confidence = _confidence_band_label(loc, summary.get("confidence_band"))
    na = translate_ui(loc, "dash.analysis.na")
    match_str = f"{top_match_name}" if top_match_name else na

    run_caption = translate_ui(
        loc,
        "dash.analysis.ftir.figure.run_summary",
        peaks=str(peak_count_disp),
        match=match_str,
        status=match_status,
        confidence=confidence,
    )

    diag_notes: list[str] = []
    if diagnostics.get("inverted_for_transmittance"):
        diag_notes.append("Signal interpreted as transmittance; inverted for analysis.")
    if diagnostics.get("baseline_suppressed"):
        diag_notes.append(f"Baseline suppressed: {diagnostics.get('baseline_suppression_reason', '')}")
    if diagnostics.get("normalization_skipped"):
        diag_notes.append(f"Normalization skipped: {diagnostics.get('normalization_skip_reason', '')}")
    if diagnostics.get("peak_detection_fallback"):
        diag_notes.append(f"Peak detection fallback: {diagnostics.get('peak_detection_reason', '')}")
    if diagnostics.get("peak_detection_no_peaks"):
        diag_notes.append(f"No peaks detected: {diagnostics.get('peak_detection_reason', '')}")

    diag_children = [html.P(note, className="small text-warning mb-1") for note in diag_notes]

    return html.Div(
        [
            html.H5(translate_ui(loc, "dash.analysis.ftir.figure.section_title"), className="mb-2"),
            html.P(run_caption, className="small text-muted mb-2"),
            dcc.Graph(figure=fig, config={"displaylogo": False, "responsive": True}, className="ta-plot"),
            *diag_children,
        ]
    )


def _build_top_match_panel(summary: dict, rows: list, loc: str) -> html.Div:
    if not rows:
        if str(summary.get("match_status") or "").lower() == "library_unavailable":
            body = translate_ui(loc, "dash.analysis.ftir.match.library_unavailable_body")
        else:
            body = translate_ui(loc, "dash.analysis.state.no_library_matches")
        return html.Div(
            [
                html.H5(translate_ui(loc, "dash.analysis.ftir.top_match.title"), className="mb-3"),
                html.P(body, className="text-muted"),
            ]
        )

    top = rows[0]
    score = top.get("normalized_score", 0.0)
    band = str(top.get("confidence_band", "no_match")).lower()
    color = _CONFIDENCE_COLORS.get(band, "#6B7280")
    candidate_name = top.get("candidate_name", translate_ui(loc, "dash.analysis.unknown_candidate"))
    candidate_id = top.get("candidate_id", "")
    provider = top.get("library_provider", "")
    package = top.get("library_package", "")
    evidence = top.get("evidence", {})
    shared = evidence.get("shared_peak_count", "--")
    observed = evidence.get("observed_peak_count", "--")

    return html.Div(
        [
            html.H5(translate_ui(loc, "dash.analysis.ftir.top_match.title"), className="mb-3"),
            dbc.Card(
                dbc.CardBody(
                    [
                        html.Div(
                            [
                                html.I(className="bi bi-trophy me-2", style={"color": color, "fontSize": "1.1rem"}),
                                html.Strong(candidate_name, className="me-2"),
                                html.Span(
                                    _confidence_band_label(loc, band),
                                    className="badge",
                                    style={"backgroundColor": color, "color": "white", "fontSize": "0.75rem"},
                                ),
                            ],
                            className="mb-2",
                        ),
                        dbc.Row(
                            [
                                dbc.Col([html.Small(translate_ui(loc, "dash.analysis.label.score"), className="text-muted d-block"), html.Span(f"{score:.4f}")], md=3),
                                dbc.Col([html.Small(translate_ui(loc, "dash.analysis.label.provider"), className="text-muted d-block"), html.Span(provider or "--")], md=3),
                                dbc.Col([html.Small(translate_ui(loc, "dash.analysis.label.package"), className="text-muted d-block"), html.Span(package or "--")], md=3),
                                dbc.Col([html.Small(translate_ui(loc, "dash.analysis.label.peak_overlap"), className="text-muted d-block"), html.Span(f"{shared}/{observed}")], md=3),
                            ],
                            className="g-2",
                        ),
                        *(
                            [html.P(translate_ui(loc, "dash.analysis.id_label", id=candidate_id), className="text-muted small mb-0 mt-1")]
                            if candidate_id
                            else []
                        ),
                    ]
                ),
                className="mb-3",
            ),
        ]
    )


def _build_peak_cards_from_curves(project_id: str, dataset_key: str, summary: dict, loc: str) -> html.Div:
    from dash_app.api_client import analysis_state_curves

    try:
        curves = analysis_state_curves(project_id, "FTIR", dataset_key)
    except Exception:
        curves = {}

    peaks = curves.get("peaks", [])
    if not peaks:
        return html.Div(
            [
                html.H5(translate_ui(loc, "dash.analysis.ftir.peaks.title"), className="mb-3"),
                html.P(translate_ui(loc, "dash.analysis.state.no_peaks"), className="text-muted"),
            ]
        )

    total = len(peaks)
    truncated = total >= _FTIR_TRUNCATE_PEAK_CARDS_WHEN
    shown = peaks[:_FTIR_MAX_PEAK_CARDS] if truncated else peaks

    cards: list[Any] = [html.H5(translate_ui(loc, "dash.analysis.ftir.peaks.title"), className="mb-3")]
    for idx, peak in enumerate(shown):
        pos = peak.get("position")
        intensity = peak.get("intensity")
        cards.append(
            dbc.Card(
                dbc.CardBody(
                    [
                        html.Div(
                            [
                                html.I(className="bi bi-activity me-2", style={"color": "#DC2626", "fontSize": "1.1rem"}),
                                html.Strong(translate_ui(loc, "dash.analysis.label.peak_n", n=idx + 1), className="me-2"),
                            ],
                            className="mb-2",
                        ),
                        dbc.Row(
                            [
                                dbc.Col([html.Small(translate_ui(loc, "dash.analysis.label.position"), className="text-muted d-block"), html.Span(f"{pos:.1f}" if pos is not None else "--")], md=6),
                                dbc.Col([html.Small(translate_ui(loc, "dash.analysis.label.intensity"), className="text-muted d-block"), html.Span(f"{intensity:.4f}" if intensity is not None else "--")], md=6),
                            ],
                            className="g-2",
                        ),
                    ]
                ),
                className="mb-2",
            )
        )
    if truncated:
        cards.append(
            html.P(
                translate_ui(loc, "dash.analysis.ftir.peaks.truncation_note", shown=len(shown), total=total),
                className="small text-muted mb-1",
            )
        )
    return html.Div(cards)


def _build_match_table(rows: list, loc: str, *, summary: dict | None = None) -> html.Div:
    if not rows:
        summary = summary or {}
        if str(summary.get("match_status") or "").lower() == "library_unavailable":
            body = translate_ui(loc, "dash.analysis.ftir.match.library_unavailable_body")
        else:
            body = translate_ui(loc, "dash.analysis.state.no_match_data")
        return html.Div(
            [
                html.H5(translate_ui(loc, "dash.analysis.section.match_data_table"), className="mb-3"),
                html.P(body, className="text-muted"),
            ]
        )

    columns = [
        "rank",
        "candidate_id",
        "candidate_name",
        "normalized_score",
        "confidence_band",
        "library_provider",
        "library_package",
    ]
    return html.Div(
        [
            html.H5(translate_ui(loc, "dash.analysis.section.match_data_table"), className="mb-3"),
            dataset_table(rows, columns, table_id="ftir-matches-table"),
        ]
    )
