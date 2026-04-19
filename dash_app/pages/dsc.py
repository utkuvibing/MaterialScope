"""DSC analysis page -- backend-driven first analysis slice.

Lets the user:
  1. Select an eligible DSC dataset from the workspace
  2. Select a DSC workflow template
  3. Run analysis through the backend /analysis/run endpoint
  4. View execution status, result summary, and DSC figure/preview
  5. Enriched display: Tg metric cards, smoothed/baseline/corrected overlay,
     labelled peak cards, auto-refresh of Project/Compare/Report pages
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
from dash_app.components.literature_compare_ui import (
    literature_compare_status_alert,
    literature_t,
    render_literature_output,
)
from dash_app.theme import apply_figure_theme, normalize_ui_theme
from utils.i18n import normalize_ui_locale, translate_ui

dash.register_page(__name__, path="/dsc", title="DSC Analysis - MaterialScope")

_DSC_TEMPLATE_IDS = ["dsc.general", "dsc.polymer_tg", "dsc.polymer_melting_crystallization"]


def _loc(locale_data: str | None) -> str:
    return normalize_ui_locale(locale_data)

_DSC_ELIGIBLE_TYPES = {"DSC", "DTA", "UNKNOWN"}

_PEAK_TYPE_COLORS = {
    "endotherm": "#0E7490",
    "exotherm": "#DC2626",
    "step": "#7C3AED",
}
_PEAK_TYPE_ICONS = {
    "endotherm": "bi-arrow-down-circle",
    "exotherm": "bi-arrow-up-circle",
    "step": "bi-arrow-right-circle",
}
_DSC_RESULT_CARD_ROLES = {
    "context": "dsc-result-context",
    "hero": "dsc-result-hero",
    "support": "dsc-result-support",
    "secondary": "dsc-result-secondary",
}
_DSC_LITERATURE_PREFIX = "dash.analysis.dsc.literature"

_SMOOTH_METHODS = ("savgol", "moving_average", "gaussian")
_DSC_SMOOTHING_DEFAULTS: dict[str, dict] = {
    "savgol": {"method": "savgol", "window_length": 11, "polyorder": 3},
    "moving_average": {"method": "moving_average", "window_length": 11},
    "gaussian": {"method": "gaussian", "sigma": 2.0},
}
_BASELINE_METHODS = ("asls", "linear", "rubberband")
_DSC_BASELINE_DEFAULTS: dict[str, dict] = {
    "asls": {"method": "asls", "lam": 1e6, "p": 0.01, "region": None},
    "linear": {"method": "linear", "region": None},
    "rubberband": {"method": "rubberband", "region": None},
}
_DSC_PEAK_DETECTION_DEFAULTS: dict = {
    "direction": "both",
    "prominence": 0.0,
    "distance": 1,
}
_DSC_GLASS_TRANSITION_DEFAULTS: dict = {
    "mode": "auto",
    "region": None,
}
_UNDO_STACK_LIMIT = 32
_ANNOTATION_MIN_SEP = 15.0


def _default_processing_draft() -> dict:
    return {
        "smoothing": copy.deepcopy(_DSC_SMOOTHING_DEFAULTS["savgol"]),
        "baseline": copy.deepcopy(_DSC_BASELINE_DEFAULTS["asls"]),
        "peak_detection": copy.deepcopy(_DSC_PEAK_DETECTION_DEFAULTS),
        "glass_transition": copy.deepcopy(_DSC_GLASS_TRANSITION_DEFAULTS),
    }


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


def _normalize_smoothing_values(method: str | None, window_length, polyorder, sigma) -> dict:
    token = str(method or "savgol").strip().lower()
    if token not in _SMOOTH_METHODS:
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


def _normalize_baseline_values(method: str | None, lam, p, region_enabled=None, region_min=None, region_max=None) -> dict:
    token = str(method or "asls").strip().lower()
    if token not in _BASELINE_METHODS:
        token = "asls"
    region = _normalize_baseline_region(region_enabled, region_min, region_max)
    if token == "asls":
        lam_value = _coerce_float_positive(lam, default=1e6, minimum=1e-3)
        p_value = _coerce_float_positive(p, default=0.01, minimum=1e-4)
        p_value = min(p_value, 0.5)
        return {"method": "asls", "lam": lam_value, "p": p_value, "region": region}
    return {"method": token, "region": region}


def _normalize_peak_detection_values(direction: str | None, prominence, distance) -> dict:
    dir_token = str(direction or "both").strip().lower()
    if dir_token not in {"both", "up", "down"}:
        dir_token = "both"
    return {
        "direction": dir_token,
        "prominence": _coerce_float_non_negative(prominence, default=0.0),
        "distance": _coerce_int_positive(distance, default=1, minimum=1),
    }


def _normalize_glass_transition_values(enabled, rmin, rmax) -> dict:
    if not enabled:
        return {"mode": "auto", "region": None}
    try:
        lower = float(rmin)
        upper = float(rmax)
    except (TypeError, ValueError):
        return {"mode": "auto", "region": None}
    if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
        return {"mode": "auto", "region": None}
    return {"mode": "auto", "region": [lower, upper]}


def _apply_draft_section(draft: dict | None, section: str, values: dict) -> dict:
    next_draft = copy.deepcopy(draft or {})
    next_draft[section] = copy.deepcopy(values)
    return next_draft


def _push_undo(undo: list | None, snapshot: dict | None) -> list:
    stack = list(undo or [])
    stack.append(copy.deepcopy(snapshot or {}))
    if len(stack) > _UNDO_STACK_LIMIT:
        stack = stack[-_UNDO_STACK_LIMIT:]
    return stack


def _do_undo(draft: dict, undo: list | None, redo: list | None) -> tuple[dict, list, list]:
    undo_stack = list(undo or [])
    redo_stack = list(redo or [])
    if not undo_stack:
        return copy.deepcopy(draft or {}), undo_stack, redo_stack
    previous = undo_stack.pop()
    redo_stack.append(copy.deepcopy(draft or {}))
    return copy.deepcopy(previous), undo_stack, redo_stack


def _do_redo(draft: dict, undo: list | None, redo: list | None) -> tuple[dict, list, list]:
    undo_stack = list(undo or [])
    redo_stack = list(redo or [])
    if not redo_stack:
        return copy.deepcopy(draft or {}), undo_stack, redo_stack
    following = redo_stack.pop()
    undo_stack.append(copy.deepcopy(draft or {}))
    return copy.deepcopy(following), undo_stack, redo_stack


def _do_reset(draft: dict, undo: list | None, redo: list | None, defaults: dict | None) -> tuple[dict, list, list]:
    reset_target = copy.deepcopy(defaults or _default_processing_draft())
    if (draft or {}) == reset_target:
        return reset_target, list(undo or []), list(redo or [])
    undo_stack = _push_undo(undo, draft)
    return reset_target, undo_stack, []


def _overrides_from_draft(draft: dict | None) -> dict:
    draft_payload = dict(draft or {})
    combined: dict[str, dict] = {}
    for section in ("smoothing", "baseline", "peak_detection", "glass_transition"):
        values = draft_payload.get(section)
        if isinstance(values, dict):
            combined[section] = copy.deepcopy(values)
    return combined


# ---------------------------------------------------------------------------
# DSC-specific cards
# ---------------------------------------------------------------------------

def _processing_draft_stores() -> list:
    defaults = _default_processing_draft()
    return [
        dcc.Store(id="dsc-processing-default", data=defaults),
        dcc.Store(id="dsc-processing-draft", data=copy.deepcopy(defaults)),
        dcc.Store(id="dsc-processing-undo", data=[]),
        dcc.Store(id="dsc-processing-redo", data=[]),
        dcc.Store(id="dsc-figure-captured", data={}),
        dcc.Store(id="dsc-preset-refresh", data=0),
    ]


_DSC_PRESET_ANALYSIS_TYPE = "DSC"


def _preset_controls_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="dsc-preset-card-title", className="card-title mb-1"),
                html.Small(id="dsc-preset-help", className="form-text text-muted d-block mb-2"),
                html.Div(id="dsc-preset-caption", className="small text-muted mb-2"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id="dsc-preset-select-label", html_for="dsc-preset-select"),
                                dbc.Select(id="dsc-preset-select", options=[], value=None),
                            ],
                            md=12,
                        ),
                    ],
                    className="mb-2",
                ),
                dbc.ButtonGroup(
                    [
                        dbc.Button(id="dsc-preset-apply-btn", color="primary", size="sm", disabled=True),
                        dbc.Button(id="dsc-preset-delete-btn", color="secondary", size="sm", outline=True, disabled=True),
                    ],
                    className="mb-3",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id="dsc-preset-save-name-label", html_for="dsc-preset-save-name"),
                                dbc.Input(id="dsc-preset-save-name", type="text", value="", maxLength=80),
                            ],
                            md=12,
                        ),
                    ],
                    className="mb-2",
                ),
                dbc.Button(id="dsc-preset-save-btn", color="primary", size="sm", className="mb-2"),
                html.Div(id="dsc-preset-status", className="small text-muted"),
            ]
        ),
        className="mb-3",
    )


def _smoothing_controls_card() -> dbc.Card:
    method_options = [
        {"label": "Savitzky-Golay", "value": "savgol"},
        {"label": "Moving Average", "value": "moving_average"},
        {"label": "Gaussian", "value": "gaussian"},
    ]
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="dsc-smoothing-card-title", className="card-title mb-3"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id="dsc-smooth-method-label", html_for="dsc-smooth-method"),
                                dbc.Select(id="dsc-smooth-method", options=method_options, value="savgol"),
                                html.Small(id="dsc-smooth-method-hint", className="form-text text-muted d-block mt-1"),
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
                                dbc.Label(id="dsc-smooth-window-label", html_for="dsc-smooth-window"),
                                dbc.Input(id="dsc-smooth-window", type="number", min=3, max=51, step=2, value=11),
                                html.Small(id="dsc-smooth-window-hint", className="form-text text-muted d-block mt-1"),
                            ],
                            md=4,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="dsc-smooth-polyorder-label", html_for="dsc-smooth-polyorder"),
                                dbc.Input(id="dsc-smooth-polyorder", type="number", min=1, max=7, step=1, value=3),
                                html.Small(id="dsc-smooth-polyorder-hint", className="form-text text-muted d-block mt-1"),
                            ],
                            md=4,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="dsc-smooth-sigma-label", html_for="dsc-smooth-sigma"),
                                dbc.Input(id="dsc-smooth-sigma", type="number", min=0.1, max=10.0, step=0.1, value=2.0, disabled=True),
                                html.Small(id="dsc-smooth-sigma-hint", className="form-text text-muted d-block mt-1"),
                            ],
                            md=4,
                        ),
                    ],
                    className="g-2 mb-2",
                ),
                dbc.ButtonGroup(
                    [
                        dbc.Button(id="dsc-smooth-apply-btn", color="primary", size="sm"),
                        dbc.Button(id="dsc-undo-btn", color="secondary", size="sm", outline=True),
                        dbc.Button(id="dsc-redo-btn", color="secondary", size="sm", outline=True),
                        dbc.Button(id="dsc-reset-btn", color="secondary", size="sm", outline=True),
                    ],
                    className="mb-2",
                ),
                html.Div(id="dsc-smooth-status", className="small text-muted"),
            ]
        ),
        className="mb-3",
    )


def _baseline_controls_card() -> dbc.Card:
    method_options = [
        {"label": "AsLS", "value": "asls"},
        {"label": "Linear", "value": "linear"},
        {"label": "Rubberband", "value": "rubberband"},
    ]
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="dsc-baseline-card-title", className="card-title mb-3"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id="dsc-baseline-method-label", html_for="dsc-baseline-method"),
                                dbc.Select(id="dsc-baseline-method", options=method_options, value="asls"),
                                html.Small(id="dsc-baseline-method-hint", className="form-text text-muted d-block mt-1"),
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
                                dbc.Label(id="dsc-baseline-lam-label", html_for="dsc-baseline-lam"),
                                dbc.Input(id="dsc-baseline-lam", type="number", min=1e-3, step=1e5, value=1e6),
                                html.Small(id="dsc-baseline-lam-hint", className="form-text text-muted d-block mt-1"),
                            ],
                            md=6,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="dsc-baseline-p-label", html_for="dsc-baseline-p"),
                                dbc.Input(id="dsc-baseline-p", type="number", min=1e-4, max=0.5, step=0.005, value=0.01),
                                html.Small(id="dsc-baseline-p-hint", className="form-text text-muted d-block mt-1"),
                            ],
                            md=6,
                        ),
                    ],
                    className="g-2 mb-2",
                ),
                html.H6(id="dsc-baseline-region-section-title", className="mt-2 mb-2 small text-muted text-uppercase"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Checkbox(id="dsc-baseline-region-enabled", value=False, label=" "),
                                html.Small(id="dsc-baseline-region-enable-hint", className="form-text text-muted d-block mt-1"),
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
                                dbc.Label(id="dsc-baseline-region-min-label", html_for="dsc-baseline-region-min"),
                                dbc.Input(id="dsc-baseline-region-min", type="number", value=None),
                                html.Small(id="dsc-baseline-region-min-hint", className="form-text text-muted d-block mt-1"),
                            ],
                            md=6,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="dsc-baseline-region-max-label", html_for="dsc-baseline-region-max"),
                                dbc.Input(id="dsc-baseline-region-max", type="number", value=None),
                                html.Small(id="dsc-baseline-region-max-hint", className="form-text text-muted d-block mt-1"),
                            ],
                            md=6,
                        ),
                    ],
                    className="g-2 mb-2",
                ),
                dbc.Button(id="dsc-baseline-apply-btn", color="primary", size="sm", className="mb-2"),
                html.Div(id="dsc-baseline-status", className="small text-muted"),
            ]
        ),
        className="mb-3",
    )


def _literature_compare_card() -> dbc.Card:
    """Manual literature compare (same interaction model as DTA)."""
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="dsc-literature-card-title", className="card-title mb-3"),
                html.Div(id="dsc-literature-hint", className="small text-muted mb-2"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(
                                    id="dsc-literature-max-claims-label",
                                    html_for="dsc-literature-max-claims",
                                ),
                                dbc.Input(
                                    id="dsc-literature-max-claims",
                                    type="number",
                                    min=1,
                                    max=10,
                                    step=1,
                                    value=3,
                                ),
                            ],
                            md=6,
                        ),
                        dbc.Col(
                            [
                                dbc.Checklist(
                                    id="dsc-literature-persist",
                                    options=[{"label": "", "value": "persist"}],
                                    value=[],
                                    switch=True,
                                    className="mt-4",
                                ),
                                dbc.Label(
                                    id="dsc-literature-persist-label",
                                    html_for="dsc-literature-persist",
                                    className="small",
                                ),
                            ],
                            md=6,
                        ),
                    ],
                    className="g-2 mb-2",
                ),
                dbc.Button(
                    id="dsc-literature-compare-btn",
                    color="primary",
                    size="sm",
                    disabled=True,
                    className="mb-2",
                ),
                html.Div(id="dsc-literature-status", className="small text-muted"),
                html.Div(id="dsc-literature-output", className="mt-2"),
            ]
        ),
        className="mb-3",
    )


def _peak_controls_card() -> dbc.Card:
    direction_options = [
        {"label": "Both", "value": "both"},
        {"label": "Upward (Exotherm)", "value": "up"},
        {"label": "Downward (Endotherm)", "value": "down"},
    ]
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="dsc-peak-card-title", className="card-title mb-3"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id="dsc-peak-direction-label", html_for="dsc-peak-direction"),
                                dbc.Select(id="dsc-peak-direction", options=direction_options, value="both"),
                                html.Small(id="dsc-peak-direction-hint", className="form-text text-muted d-block mt-1"),
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
                                dbc.Label(id="dsc-peak-prominence-label", html_for="dsc-peak-prominence"),
                                dbc.Input(id="dsc-peak-prominence", type="number", min=0.0, step=0.005, value=0.0),
                                html.Small(id="dsc-peak-prominence-hint", className="form-text text-muted d-block mt-1"),
                            ],
                            md=6,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="dsc-peak-distance-label", html_for="dsc-peak-distance"),
                                dbc.Input(id="dsc-peak-distance", type="number", min=1, step=1, value=1),
                                html.Small(id="dsc-peak-distance-hint", className="form-text text-muted d-block mt-1"),
                            ],
                            md=6,
                        ),
                    ],
                    className="g-2 mb-2",
                ),
                dbc.Button(id="dsc-peak-apply-btn", color="primary", size="sm", className="mb-2"),
                html.Div(id="dsc-peak-status", className="small text-muted"),
            ]
        ),
        className="mb-3",
    )


def _tg_controls_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="dsc-tg-card-title", className="card-title mb-3"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Checkbox(id="dsc-tg-region-enabled", value=False, label=" "),
                                html.Small(id="dsc-tg-region-enable-hint", className="form-text text-muted d-block mt-1"),
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
                                dbc.Label(id="dsc-tg-region-min-label", html_for="dsc-tg-region-min"),
                                dbc.Input(id="dsc-tg-region-min", type="number", value=None),
                                html.Small(id="dsc-tg-region-min-hint", className="form-text text-muted d-block mt-1"),
                            ],
                            md=6,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="dsc-tg-region-max-label", html_for="dsc-tg-region-max"),
                                dbc.Input(id="dsc-tg-region-max", type="number", value=None),
                                html.Small(id="dsc-tg-region-max-hint", className="form-text text-muted d-block mt-1"),
                            ],
                            md=6,
                        ),
                    ],
                    className="g-2 mb-2",
                ),
                dbc.Button(id="dsc-tg-apply-btn", color="primary", size="sm", className="mb-2"),
                html.Div(id="dsc-tg-status", className="small text-muted"),
            ]
        ),
        className="mb-3",
    )


def _dsc_left_column_tabs() -> dbc.Tabs:
    return dbc.Tabs(
        [
            dbc.Tab(
                [
                    dataset_selection_card("dsc-dataset-selector-area", card_title_id="dsc-dataset-card-title"),
                    html.Div(id="dsc-prerun-dataset-info", className="mb-3"),
                    workflow_template_card(
                        "dsc-template-select",
                        "dsc-template-description",
                        [],
                        "dsc.general",
                        card_title_id="dsc-workflow-card-title",
                    ),
                ],
                tab_id="dsc-tab-setup",
                label_class_name="ta-tab-label",
                id="dsc-tab-setup-shell",
            ),
            dbc.Tab(
                [
                    _preset_controls_card(),
                    _smoothing_controls_card(),
                    _baseline_controls_card(),
                    _peak_controls_card(),
                    _tg_controls_card(),
                ],
                tab_id="dsc-tab-processing",
                label_class_name="ta-tab-label",
                id="dsc-tab-processing-shell",
            ),
            dbc.Tab(
                [
                    execute_card("dsc-run-status", "dsc-run-btn", card_title_id="dsc-execute-card-title"),
                    html.Small(id="dsc-run-shortcut-hints", className="text-muted d-block mt-2"),
                ],
                tab_id="dsc-tab-run",
                label_class_name="ta-tab-label",
                id="dsc-tab-run-shell",
            ),
        ],
        id="dsc-left-tabs",
        active_tab="dsc-tab-setup",
        className="mb-3",
    )


def _dsc_result_section(child: Any, *, role: str = "support") -> html.Div:
    role_class = _DSC_RESULT_CARD_ROLES.get(role, _DSC_RESULT_CARD_ROLES["support"])
    return html.Div(child, className=f"dsc-result-section {role_class}")


def _peak_card(row: dict, idx: int, loc: str) -> dbc.Card:
    peak_type = str(row.get("peak_type", "unknown")).lower()
    color = _PEAK_TYPE_COLORS.get(peak_type, "#6B7280")
    icon = _PEAK_TYPE_ICONS.get(peak_type, "bi-circle")
    pt = row.get("peak_temperature")
    onset = row.get("onset_temperature")
    endset = row.get("endset_temperature")
    area = row.get("area")
    fwhm = row.get("fwhm")
    height = row.get("height")
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(
                    [
                        html.I(className=f"bi {icon} me-2", style={"color": color, "fontSize": "1.1rem"}),
                        html.Strong(translate_ui(loc, "dash.analysis.label.peak_n", n=idx + 1), className="me-2"),
                        html.Span(
                            peak_type.title(),
                            className="badge",
                            style={"backgroundColor": color, "color": "white", "fontSize": "0.75rem"},
                        ),
                        html.Span(f"  {pt:.1f} °C" if pt is not None else "  --", className="ms-2"),
                    ],
                    className="mb-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Small(translate_ui(loc, "dash.analysis.label.onset"), className="text-muted d-block"),
                                html.Span(f"{onset:.1f}" if onset is not None else "--"),
                            ],
                            md=3,
                        ),
                        dbc.Col(
                            [
                                html.Small(translate_ui(loc, "dash.analysis.label.endset"), className="text-muted d-block"),
                                html.Span(f"{endset:.1f}" if endset is not None else "--"),
                            ],
                            md=3,
                        ),
                        dbc.Col(
                            [
                                html.Small(translate_ui(loc, "dash.analysis.label.area"), className="text-muted d-block"),
                                html.Span(f"{area:.3f}" if area is not None else "--"),
                            ],
                            md=3,
                        ),
                        dbc.Col(
                            [
                                html.Small(translate_ui(loc, "dash.analysis.label.fwhm"), className="text-muted d-block"),
                                html.Span(f"{fwhm:.1f}" if fwhm is not None else "--"),
                                html.Small(f" {translate_ui(loc, 'dash.analysis.label.height')}", className="text-muted ms-2"),
                                html.Span(f"{height:.3f}" if height is not None else "--"),
                            ],
                            md=3,
                        ),
                    ],
                    className="g-2",
                ),
            ]
        ),
        className="mb-2",
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div(
    analysis_page_stores("dsc-refresh", "dsc-latest-result-id")
    + _processing_draft_stores()
    + [
        html.Div(id="dsc-hero-slot"),
        dbc.Row(
            [
                dbc.Col([_dsc_left_column_tabs()], md=4),
                dbc.Col(
                    [
                        _dsc_result_section(result_placeholder_card("dsc-result-dataset-summary"), role="context"),
                        _dsc_result_section(result_placeholder_card("dsc-result-metrics"), role="context"),
                        _dsc_result_section(result_placeholder_card("dsc-result-quality"), role="support"),
                        _dsc_result_section(result_placeholder_card("dsc-result-raw-metadata"), role="support"),
                        _dsc_result_section(result_placeholder_card("dsc-result-figure"), role="hero"),
                        _dsc_result_section(result_placeholder_card("dsc-result-derivative"), role="support"),
                        _dsc_result_section(result_placeholder_card("dsc-result-event-cards"), role="support"),
                        _dsc_result_section(result_placeholder_card("dsc-result-table"), role="support"),
                        _dsc_result_section(result_placeholder_card("dsc-result-processing"), role="support"),
                        _dsc_result_section(_literature_compare_card(), role="secondary"),
                    ],
                    md=8,
                    className="dsc-results-surface",
                ),
            ]
        ),
    ]
)


@callback(
    Output("dsc-hero-slot", "children"),
    Output("dsc-dataset-card-title", "children"),
    Output("dsc-workflow-card-title", "children"),
    Output("dsc-execute-card-title", "children"),
    Output("dsc-run-btn", "children"),
    Output("dsc-template-select", "options"),
    Output("dsc-template-select", "value"),
    Output("dsc-template-description", "children"),
    Input("ui-locale", "data"),
    Input("dsc-template-select", "value"),
)
def render_dsc_locale_chrome(locale_data, template_id):
    loc = _loc(locale_data)
    hero = page_header(
        translate_ui(loc, "dash.analysis.dsc.title"),
        translate_ui(loc, "dash.analysis.dsc.caption"),
        badge=translate_ui(loc, "dash.analysis.badge"),
    )
    opts = [
        {"label": translate_ui(loc, f"dash.analysis.dsc.template.{tid}.label"), "value": tid} for tid in _DSC_TEMPLATE_IDS
    ]
    valid = {o["value"] for o in opts}
    tid = template_id if template_id in valid else "dsc.general"
    desc_key = f"dash.analysis.dsc.template.{tid}.desc"
    desc = translate_ui(loc, desc_key)
    if desc == desc_key:
        desc = translate_ui(loc, "dash.analysis.dsc.workflow_fallback")
    return (
        hero,
        translate_ui(loc, "dash.analysis.dataset_selection_title"),
        translate_ui(loc, "dash.analysis.workflow_template_title"),
        translate_ui(loc, "dash.analysis.execute_title"),
        translate_ui(loc, "dash.analysis.dsc.run_btn"),
        opts,
        tid,
        desc,
    )


@callback(
    Output("dsc-tab-setup-shell", "label"),
    Output("dsc-tab-processing-shell", "label"),
    Output("dsc-tab-run-shell", "label"),
    Input("ui-locale", "data"),
)
def render_dsc_tab_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.dsc.tab.setup"),
        translate_ui(loc, "dash.analysis.dsc.tab.processing"),
        translate_ui(loc, "dash.analysis.dsc.tab.run"),
    )


@callback(
    Output("dsc-run-shortcut-hints", "children"),
    Input("ui-locale", "data"),
)
def render_dsc_run_shortcut_hints(locale_data):
    loc = _loc(locale_data)
    return html.Span(
        [
            translate_ui(loc, "dash.analysis.dsc.shortcuts.hint_undo"),
            html.Br(),
            translate_ui(loc, "dash.analysis.dsc.shortcuts.hint_redo"),
            html.Br(),
            translate_ui(loc, "dash.analysis.dsc.shortcuts.hint_run"),
        ],
        className="d-block",
    )


@callback(
    Output("dsc-preset-card-title", "children"),
    Output("dsc-preset-select-label", "children"),
    Output("dsc-preset-select", "placeholder"),
    Output("dsc-preset-apply-btn", "children"),
    Output("dsc-preset-delete-btn", "children"),
    Output("dsc-preset-save-name-label", "children"),
    Output("dsc-preset-save-name", "placeholder"),
    Output("dsc-preset-save-btn", "children"),
    Output("dsc-preset-help", "children"),
    Input("ui-locale", "data"),
)
def render_dsc_preset_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.dsc.presets.title"),
        translate_ui(loc, "dash.analysis.dsc.presets.select_label"),
        translate_ui(loc, "dash.analysis.dsc.presets.select_placeholder"),
        translate_ui(loc, "dash.analysis.dsc.presets.apply_btn"),
        translate_ui(loc, "dash.analysis.dsc.presets.delete_btn"),
        translate_ui(loc, "dash.analysis.dsc.presets.save_name_label"),
        translate_ui(loc, "dash.analysis.dsc.presets.save_name_placeholder"),
        translate_ui(loc, "dash.analysis.dsc.presets.save_btn"),
        translate_ui(loc, "dash.analysis.dsc.presets.help.overview"),
    )


@callback(
    Output("dsc-smoothing-card-title", "children"),
    Output("dsc-smooth-method-label", "children"),
    Output("dsc-smooth-window-label", "children"),
    Output("dsc-smooth-polyorder-label", "children"),
    Output("dsc-smooth-sigma-label", "children"),
    Output("dsc-smooth-apply-btn", "children"),
    Output("dsc-undo-btn", "children"),
    Output("dsc-redo-btn", "children"),
    Output("dsc-reset-btn", "children"),
    Output("dsc-smooth-method-hint", "children"),
    Output("dsc-smooth-window-hint", "children"),
    Output("dsc-smooth-polyorder-hint", "children"),
    Output("dsc-smooth-sigma-hint", "children"),
    Input("ui-locale", "data"),
)
def render_dsc_smoothing_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.dsc.smoothing.title"),
        translate_ui(loc, "dash.analysis.dsc.smoothing.method"),
        translate_ui(loc, "dash.analysis.dsc.smoothing.window"),
        translate_ui(loc, "dash.analysis.dsc.smoothing.polyorder"),
        translate_ui(loc, "dash.analysis.dsc.smoothing.sigma"),
        translate_ui(loc, "dash.analysis.dsc.smoothing.apply_btn"),
        translate_ui(loc, "dash.analysis.dsc.undo_btn"),
        translate_ui(loc, "dash.analysis.dsc.redo_btn"),
        translate_ui(loc, "dash.analysis.dsc.reset_btn"),
        translate_ui(loc, "dash.analysis.dsc.smoothing.help.method"),
        translate_ui(loc, "dash.analysis.dsc.smoothing.help.window"),
        translate_ui(loc, "dash.analysis.dsc.smoothing.help.polyorder"),
        translate_ui(loc, "dash.analysis.dsc.smoothing.help.sigma"),
    )


@callback(
    Output("dsc-baseline-card-title", "children"),
    Output("dsc-baseline-method-label", "children"),
    Output("dsc-baseline-lam-label", "children"),
    Output("dsc-baseline-p-label", "children"),
    Output("dsc-baseline-apply-btn", "children"),
    Output("dsc-baseline-method-hint", "children"),
    Output("dsc-baseline-lam-hint", "children"),
    Output("dsc-baseline-p-hint", "children"),
    Input("ui-locale", "data"),
)
def render_dsc_baseline_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.dsc.baseline.title"),
        translate_ui(loc, "dash.analysis.dsc.baseline.method"),
        translate_ui(loc, "dash.analysis.dsc.baseline.lam"),
        translate_ui(loc, "dash.analysis.dsc.baseline.p"),
        translate_ui(loc, "dash.analysis.dsc.baseline.apply_btn"),
        translate_ui(loc, "dash.analysis.dsc.baseline.help.method"),
        translate_ui(loc, "dash.analysis.dsc.baseline.help.lam"),
        translate_ui(loc, "dash.analysis.dsc.baseline.help.p"),
    )


@callback(
    Output("dsc-peak-card-title", "children"),
    Output("dsc-peak-direction-label", "children"),
    Output("dsc-peak-prominence-label", "children"),
    Output("dsc-peak-distance-label", "children"),
    Output("dsc-peak-apply-btn", "children"),
    Output("dsc-peak-direction-hint", "children"),
    Output("dsc-peak-prominence-hint", "children"),
    Output("dsc-peak-distance-hint", "children"),
    Input("ui-locale", "data"),
)
def render_dsc_peak_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.dsc.peaks.title"),
        translate_ui(loc, "dash.analysis.dsc.peaks.direction"),
        translate_ui(loc, "dash.analysis.dsc.peaks.prominence"),
        translate_ui(loc, "dash.analysis.dsc.peaks.distance"),
        translate_ui(loc, "dash.analysis.dsc.peaks.apply_btn"),
        translate_ui(loc, "dash.analysis.dsc.peaks.help.direction"),
        translate_ui(loc, "dash.analysis.dsc.peaks.help.prominence"),
        translate_ui(loc, "dash.analysis.dsc.peaks.help.distance"),
    )


@callback(
    Output("dsc-tg-card-title", "children"),
    Output("dsc-tg-region-enabled", "label"),
    Output("dsc-tg-region-min-label", "children"),
    Output("dsc-tg-region-max-label", "children"),
    Output("dsc-tg-apply-btn", "children"),
    Output("dsc-tg-region-enable-hint", "children"),
    Output("dsc-tg-region-min-hint", "children"),
    Output("dsc-tg-region-max-hint", "children"),
    Input("ui-locale", "data"),
)
def render_dsc_tg_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.dsc.tg.title"),
        translate_ui(loc, "dash.analysis.dsc.tg.enable_region"),
        translate_ui(loc, "dash.analysis.dsc.tg.region_min"),
        translate_ui(loc, "dash.analysis.dsc.tg.region_max"),
        translate_ui(loc, "dash.analysis.dsc.tg.apply_btn"),
        translate_ui(loc, "dash.analysis.dsc.tg.help.enable_region"),
        translate_ui(loc, "dash.analysis.dsc.tg.help.region_min"),
        translate_ui(loc, "dash.analysis.dsc.tg.help.region_max"),
    )


@callback(
    Output("dsc-prerun-dataset-info", "children"),
    Input("dsc-dataset-select", "value"),
    Input("dsc-refresh", "data"),
    Input("ui-locale", "data"),
    State("project-id", "data"),
)
def render_dsc_prerun_dataset_info(dataset_key, _refresh, locale_data, project_id):
    loc = _loc(locale_data)
    na = translate_ui(loc, "dash.analysis.na")
    if not project_id or not dataset_key:
        return html.Div()

    from dash_app.api_client import workspace_dataset_detail

    try:
        detail = workspace_dataset_detail(project_id, dataset_key)
    except Exception:
        return html.Div()

    validation = detail.get("validation") if isinstance(detail.get("validation"), dict) else {}
    checks = validation.get("checks") if isinstance(validation.get("checks"), dict) else {}
    meta = detail.get("metadata") if isinstance(detail.get("metadata"), dict) else {}

    tmin = checks.get("temperature_min")
    tmax = checks.get("temperature_max")
    n_pts = checks.get("data_points")
    if tmin is not None and tmax is not None:
        try:
            trange = translate_ui(loc, "dash.analysis.dsc.prerun.temp_range").format(
                tmin=float(tmin),
                tmax=float(tmax),
            )
        except (TypeError, ValueError):
            trange = na
    else:
        trange = na

    points_txt = str(int(n_pts)) if isinstance(n_pts, int) or (isinstance(n_pts, float) and math.isfinite(n_pts)) else na

    mass_raw = meta.get("sample_mass")
    mass_txt = _format_dataset_metadata_value(mass_raw) if mass_raw is not None else None
    if mass_txt:
        mass_txt = f"{mass_txt} {translate_ui(loc, 'dash.analysis.dsc.summary.mass_unit')}"
    else:
        mass_txt = na

    hr_raw = meta.get("heating_rate")
    hr_txt = _format_dataset_metadata_value(hr_raw) if hr_raw is not None else None
    if hr_txt:
        hr_txt = f"{hr_txt} {translate_ui(loc, 'dash.analysis.dsc.summary.heating_rate_unit')}"
    else:
        hr_txt = na

    return html.Div(
        [
            html.H6(translate_ui(loc, "dash.analysis.dsc.prerun.card_title"), className="mb-2"),
            html.Dl(
                [
                    html.Dt(translate_ui(loc, "dash.analysis.dsc.prerun.range"), className="col-sm-5 text-muted small"),
                    html.Dd(trange, className="col-sm-7 small"),
                    html.Dt(translate_ui(loc, "dash.analysis.dsc.prerun.points"), className="col-sm-5 text-muted small"),
                    html.Dd(points_txt, className="col-sm-7 small"),
                    html.Dt(translate_ui(loc, "dash.analysis.dsc.prerun.sample_mass"), className="col-sm-5 text-muted small"),
                    html.Dd(mass_txt, className="col-sm-7 small"),
                    html.Dt(translate_ui(loc, "dash.analysis.dsc.prerun.heating_rate"), className="col-sm-5 text-muted small"),
                    html.Dd(hr_txt, className="col-sm-7 small"),
                ],
                className="row mb-0 small",
            ),
        ],
        className="border rounded p-3 bg-light",
    )


@callback(
    Output("dsc-dataset-selector-area", "children"),
    Output("dsc-run-btn", "disabled"),
    Input("project-id", "data"),
    Input("dsc-refresh", "data"),
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
        selector_id="dsc-dataset-select",
        empty_msg=translate_ui(loc, "dash.analysis.dsc.empty_import"),
        eligible=eligible_datasets(all_datasets, _DSC_ELIGIBLE_TYPES),
        all_datasets=all_datasets,
        eligible_types=_DSC_ELIGIBLE_TYPES,
        active_dataset=payload.get("active_dataset"),
        locale_data=locale_data,
    )


@callback(
    Output("dsc-preset-select", "options"),
    Output("dsc-preset-caption", "children"),
    Input("dsc-preset-refresh", "data"),
    Input("ui-locale", "data"),
)
def refresh_dsc_preset_options(_refresh_token, locale_data):
    from dash_app import api_client

    loc = _loc(locale_data)
    try:
        payload = api_client.list_analysis_presets(_DSC_PRESET_ANALYSIS_TYPE)
    except Exception as exc:
        message = translate_ui(loc, "dash.analysis.dsc.presets.list_failed").format(error=str(exc))
        return [], message

    presets = payload.get("presets") or []
    options = [
        {"label": item.get("preset_name", ""), "value": item.get("preset_name", "")}
        for item in presets
        if isinstance(item, dict) and item.get("preset_name")
    ]
    caption = translate_ui(loc, "dash.analysis.dsc.presets.caption").format(
        analysis_type=payload.get("analysis_type", _DSC_PRESET_ANALYSIS_TYPE),
        count=int(payload.get("count", len(options)) or 0),
        max_count=int(payload.get("max_count", 10) or 10),
    )
    return options, caption


@callback(
    Output("dsc-preset-apply-btn", "disabled"),
    Output("dsc-preset-delete-btn", "disabled"),
    Input("dsc-preset-select", "value"),
)
def toggle_dsc_preset_action_buttons(selected_name):
    has_selection = bool(str(selected_name or "").strip())
    return (not has_selection, not has_selection)


@callback(
    Output("dsc-processing-draft", "data", allow_duplicate=True),
    Output("dsc-processing-undo", "data", allow_duplicate=True),
    Output("dsc-processing-redo", "data", allow_duplicate=True),
    Output("dsc-template-select", "value", allow_duplicate=True),
    Output("dsc-preset-status", "children", allow_duplicate=True),
    Output("dsc-left-tabs", "active_tab", allow_duplicate=True),
    Input("dsc-preset-apply-btn", "n_clicks"),
    State("dsc-preset-select", "value"),
    State("dsc-processing-draft", "data"),
    State("dsc-processing-undo", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def apply_dsc_preset(n_clicks, selected_name, draft, undo, locale_data):
    from dash_app import api_client

    loc = _loc(locale_data)
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    name = str(selected_name or "").strip()
    if not name:
        return (
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            translate_ui(loc, "dash.analysis.dsc.presets.select_required"),
            dash.no_update,
        )
    try:
        payload = api_client.load_analysis_preset(_DSC_PRESET_ANALYSIS_TYPE, name)
    except Exception as exc:
        return (
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            translate_ui(loc, "dash.analysis.dsc.presets.apply_failed").format(error=str(exc)),
            dash.no_update,
        )

    processing = dict(payload.get("processing") or {})
    next_draft = copy.deepcopy(draft or _default_processing_draft())
    for section in ("smoothing", "baseline", "peak_detection", "glass_transition"):
        values = processing.get(section)
        if isinstance(values, dict):
            next_draft[section] = copy.deepcopy(values)

    template_id_raw = str(payload.get("workflow_template_id") or "").strip()
    template_output = template_id_raw if template_id_raw in _DSC_TEMPLATE_IDS else dash.no_update
    next_undo = _push_undo(undo, draft)
    status = translate_ui(loc, "dash.analysis.dsc.presets.applied").format(preset=name)
    return next_draft, next_undo, [], template_output, status, "dsc-tab-run"


@callback(
    Output("dsc-preset-refresh", "data", allow_duplicate=True),
    Output("dsc-preset-save-name", "value", allow_duplicate=True),
    Output("dsc-preset-status", "children", allow_duplicate=True),
    Output("dsc-left-tabs", "active_tab", allow_duplicate=True),
    Input("dsc-preset-save-btn", "n_clicks"),
    State("dsc-preset-save-name", "value"),
    State("dsc-processing-draft", "data"),
    State("dsc-template-select", "value"),
    State("dsc-preset-refresh", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def save_dsc_preset(n_clicks, save_name, draft, template_id, refresh_token, locale_data):
    from dash_app import api_client

    loc = _loc(locale_data)
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    name = str(save_name or "").strip()
    if not name:
        return (
            dash.no_update,
            dash.no_update,
            translate_ui(loc, "dash.analysis.dsc.presets.save_name_required"),
            dash.no_update,
        )
    try:
        response = api_client.save_analysis_preset(
            _DSC_PRESET_ANALYSIS_TYPE,
            name,
            workflow_template_id=str(template_id or "").strip() or None,
            processing=_overrides_from_draft(draft or {}),
        )
    except Exception as exc:
        return (
            dash.no_update,
            dash.no_update,
            translate_ui(loc, "dash.analysis.dsc.presets.save_failed").format(error=str(exc)),
            dash.no_update,
        )
    resolved_template = str(response.get("workflow_template_id") or template_id or "")
    status = translate_ui(loc, "dash.analysis.dsc.presets.saved").format(preset=name, template=resolved_template)
    return int(refresh_token or 0) + 1, "", status, "dsc-tab-run"


@callback(
    Output("dsc-preset-refresh", "data", allow_duplicate=True),
    Output("dsc-preset-select", "value", allow_duplicate=True),
    Output("dsc-preset-status", "children", allow_duplicate=True),
    Input("dsc-preset-delete-btn", "n_clicks"),
    State("dsc-preset-select", "value"),
    State("dsc-preset-refresh", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def delete_dsc_preset(n_clicks, selected_name, refresh_token, locale_data):
    from dash_app import api_client

    loc = _loc(locale_data)
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    name = str(selected_name or "").strip()
    if not name:
        return dash.no_update, dash.no_update, translate_ui(loc, "dash.analysis.dsc.presets.select_required")
    try:
        api_client.delete_analysis_preset(_DSC_PRESET_ANALYSIS_TYPE, name)
    except Exception as exc:
        return (
            dash.no_update,
            dash.no_update,
            translate_ui(loc, "dash.analysis.dsc.presets.delete_failed").format(error=str(exc)),
        )
    status = translate_ui(loc, "dash.analysis.dsc.presets.deleted").format(preset=name)
    return int(refresh_token or 0) + 1, None, status


@callback(
    Output("dsc-smooth-window", "disabled"),
    Output("dsc-smooth-polyorder", "disabled"),
    Output("dsc-smooth-sigma", "disabled"),
    Input("dsc-smooth-method", "value"),
)
def toggle_smoothing_inputs(method):
    token = str(method or "savgol").strip().lower()
    if token == "savgol":
        return False, False, True
    if token == "moving_average":
        return False, True, True
    return True, True, False


@callback(
    Output("dsc-baseline-lam", "disabled"),
    Output("dsc-baseline-p", "disabled"),
    Input("dsc-baseline-method", "value"),
)
def toggle_baseline_inputs(method):
    token = str(method or "asls").strip().lower()
    if token == "asls":
        return False, False
    return True, True


@callback(
    Output("dsc-tg-region-min", "disabled"),
    Output("dsc-tg-region-max", "disabled"),
    Input("dsc-tg-region-enabled", "value"),
)
def toggle_tg_region_inputs(enabled):
    return (not bool(enabled), not bool(enabled))


@callback(
    Output("dsc-baseline-region-min", "disabled"),
    Output("dsc-baseline-region-max", "disabled"),
    Input("dsc-baseline-region-enabled", "value"),
)
def toggle_dsc_baseline_region_inputs(enabled):
    return (not bool(enabled), not bool(enabled))


@callback(
    Output("dsc-baseline-region-section-title", "children"),
    Output("dsc-baseline-region-enabled", "label"),
    Output("dsc-baseline-region-enable-hint", "children"),
    Output("dsc-baseline-region-min-label", "children"),
    Output("dsc-baseline-region-max-label", "children"),
    Output("dsc-baseline-region-min-hint", "children"),
    Output("dsc-baseline-region-max-hint", "children"),
    Input("ui-locale", "data"),
)
def render_dsc_baseline_region_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.dsc.baseline.region_section"),
        translate_ui(loc, "dash.analysis.dsc.baseline.enable_region"),
        translate_ui(loc, "dash.analysis.dsc.baseline.help.enable_region"),
        translate_ui(loc, "dash.analysis.dsc.baseline.region_min"),
        translate_ui(loc, "dash.analysis.dsc.baseline.region_max"),
        translate_ui(loc, "dash.analysis.dsc.baseline.help.region_min"),
        translate_ui(loc, "dash.analysis.dsc.baseline.help.region_max"),
    )


@callback(
    Output("dsc-processing-draft", "data", allow_duplicate=True),
    Output("dsc-processing-undo", "data", allow_duplicate=True),
    Output("dsc-processing-redo", "data", allow_duplicate=True),
    Input("dsc-smooth-apply-btn", "n_clicks"),
    State("dsc-smooth-method", "value"),
    State("dsc-smooth-window", "value"),
    State("dsc-smooth-polyorder", "value"),
    State("dsc-smooth-sigma", "value"),
    State("dsc-processing-draft", "data"),
    State("dsc-processing-undo", "data"),
    prevent_initial_call=True,
)
def apply_smoothing(n_clicks, method, window, polyorder, sigma, draft, undo):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    values = _normalize_smoothing_values(method, window, polyorder, sigma)
    next_undo = _push_undo(undo, draft)
    next_draft = _apply_draft_section(draft, "smoothing", values)
    return next_draft, next_undo, []


@callback(
    Output("dsc-processing-draft", "data", allow_duplicate=True),
    Output("dsc-processing-undo", "data", allow_duplicate=True),
    Output("dsc-processing-redo", "data", allow_duplicate=True),
    Input("dsc-baseline-apply-btn", "n_clicks"),
    State("dsc-baseline-method", "value"),
    State("dsc-baseline-lam", "value"),
    State("dsc-baseline-p", "value"),
    State("dsc-baseline-region-enabled", "value"),
    State("dsc-baseline-region-min", "value"),
    State("dsc-baseline-region-max", "value"),
    State("dsc-processing-draft", "data"),
    State("dsc-processing-undo", "data"),
    prevent_initial_call=True,
)
def apply_baseline(n_clicks, method, lam, p, region_enabled, region_min, region_max, draft, undo):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    values = _normalize_baseline_values(method, lam, p, region_enabled, region_min, region_max)
    next_undo = _push_undo(undo, draft)
    next_draft = _apply_draft_section(draft, "baseline", values)
    return next_draft, next_undo, []


@callback(
    Output("dsc-processing-draft", "data", allow_duplicate=True),
    Output("dsc-processing-undo", "data", allow_duplicate=True),
    Output("dsc-processing-redo", "data", allow_duplicate=True),
    Input("dsc-peak-apply-btn", "n_clicks"),
    State("dsc-peak-direction", "value"),
    State("dsc-peak-prominence", "value"),
    State("dsc-peak-distance", "value"),
    State("dsc-processing-draft", "data"),
    State("dsc-processing-undo", "data"),
    prevent_initial_call=True,
)
def apply_peak_detection(n_clicks, direction, prominence, distance, draft, undo):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    values = _normalize_peak_detection_values(direction, prominence, distance)
    next_undo = _push_undo(undo, draft)
    next_draft = _apply_draft_section(draft, "peak_detection", values)
    return next_draft, next_undo, []


@callback(
    Output("dsc-processing-draft", "data", allow_duplicate=True),
    Output("dsc-processing-undo", "data", allow_duplicate=True),
    Output("dsc-processing-redo", "data", allow_duplicate=True),
    Input("dsc-tg-apply-btn", "n_clicks"),
    State("dsc-tg-region-enabled", "value"),
    State("dsc-tg-region-min", "value"),
    State("dsc-tg-region-max", "value"),
    State("dsc-processing-draft", "data"),
    State("dsc-processing-undo", "data"),
    prevent_initial_call=True,
)
def apply_glass_transition(n_clicks, enabled, region_min, region_max, draft, undo):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    values = _normalize_glass_transition_values(enabled, region_min, region_max)
    next_undo = _push_undo(undo, draft)
    next_draft = _apply_draft_section(draft, "glass_transition", values)
    return next_draft, next_undo, []


@callback(
    Output("dsc-processing-draft", "data", allow_duplicate=True),
    Output("dsc-processing-undo", "data", allow_duplicate=True),
    Output("dsc-processing-redo", "data", allow_duplicate=True),
    Input("dsc-undo-btn", "n_clicks"),
    State("dsc-processing-draft", "data"),
    State("dsc-processing-undo", "data"),
    State("dsc-processing-redo", "data"),
    prevent_initial_call=True,
)
def undo_processing(n_clicks, draft, undo, redo):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    next_draft, next_undo, next_redo = _do_undo(draft or {}, undo, redo)
    return next_draft, next_undo, next_redo


@callback(
    Output("dsc-processing-draft", "data", allow_duplicate=True),
    Output("dsc-processing-undo", "data", allow_duplicate=True),
    Output("dsc-processing-redo", "data", allow_duplicate=True),
    Input("dsc-redo-btn", "n_clicks"),
    State("dsc-processing-draft", "data"),
    State("dsc-processing-undo", "data"),
    State("dsc-processing-redo", "data"),
    prevent_initial_call=True,
)
def redo_processing(n_clicks, draft, undo, redo):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    next_draft, next_undo, next_redo = _do_redo(draft or {}, undo, redo)
    return next_draft, next_undo, next_redo


@callback(
    Output("dsc-processing-draft", "data", allow_duplicate=True),
    Output("dsc-processing-undo", "data", allow_duplicate=True),
    Output("dsc-processing-redo", "data", allow_duplicate=True),
    Input("dsc-reset-btn", "n_clicks"),
    State("dsc-processing-draft", "data"),
    State("dsc-processing-undo", "data"),
    State("dsc-processing-redo", "data"),
    State("dsc-processing-default", "data"),
    prevent_initial_call=True,
)
def reset_processing(n_clicks, draft, undo, redo, defaults):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    next_draft, next_undo, next_redo = _do_reset(draft or {}, undo, redo, defaults)
    return next_draft, next_undo, next_redo


def _smoothing_status_text(draft: dict | None, loc: str) -> str:
    values = (draft or {}).get("smoothing") or {}
    method = str(values.get("method") or "savgol")
    method_label = {"savgol": "Savitzky-Golay", "moving_average": "Moving Average", "gaussian": "Gaussian"}.get(method, method)
    parts = [method_label]
    if "window_length" in values:
        parts.append(f"window={values['window_length']}")
    if "polyorder" in values:
        parts.append(f"polyorder={values['polyorder']}")
    if "sigma" in values:
        parts.append(f"sigma={values['sigma']}")
    applied = translate_ui(loc, "dash.analysis.dsc.smoothing.applied")
    return f"{applied}: {' - '.join(parts)}"


def _baseline_status_text(draft: dict | None, loc: str) -> str:
    values = (draft or {}).get("baseline") or {}
    method = str(values.get("method") or "asls")
    method_label = {"asls": "AsLS", "linear": "Linear", "rubberband": "Rubberband"}.get(method, method)
    parts = [method_label]
    if method == "asls":
        if "lam" in values:
            parts.append(f"lam={values['lam']:g}")
        if "p" in values:
            parts.append(f"p={values['p']:g}")
    region = values.get("region")
    if isinstance(region, (list, tuple)) and len(region) == 2:
        parts.append(
            translate_ui(loc, "dash.analysis.dsc.baseline.region_applied").format(tmin=region[0], tmax=region[1])
        )
    applied = translate_ui(loc, "dash.analysis.dsc.baseline.applied")
    return f"{applied}: {' - '.join(parts)}"


def _peak_status_text(draft: dict | None, loc: str) -> str:
    values = (draft or {}).get("peak_detection") or {}
    direction = str(values.get("direction") or "both")
    parts = [f"direction={direction}"]
    prominence = values.get("prominence")
    if prominence is not None:
        parts.append("prominence=auto" if float(prominence) == 0.0 else f"prominence={prominence:g}")
    distance = values.get("distance")
    if distance is not None:
        parts.append(f"distance={int(distance)}")
    applied = translate_ui(loc, "dash.analysis.dsc.peaks.applied")
    return f"{applied}: {' - '.join(parts)}"


def _tg_status_text(draft: dict | None, loc: str) -> str:
    values = (draft or {}).get("glass_transition") or {}
    region = values.get("region")
    applied = translate_ui(loc, "dash.analysis.dsc.tg.applied")
    if isinstance(region, (list, tuple)) and len(region) == 2:
        return f"{applied}: {translate_ui(loc, 'dash.analysis.dsc.tg.region_custom').format(tmin=region[0], tmax=region[1])}"
    return f"{applied}: {translate_ui(loc, 'dash.analysis.dsc.tg.region_auto')}"


@callback(
    Output("dsc-smooth-method", "value"),
    Output("dsc-smooth-window", "value"),
    Output("dsc-smooth-polyorder", "value"),
    Output("dsc-smooth-sigma", "value"),
    Output("dsc-smooth-status", "children"),
    Output("dsc-undo-btn", "disabled"),
    Output("dsc-redo-btn", "disabled"),
    Output("dsc-reset-btn", "disabled"),
    Input("dsc-processing-draft", "data"),
    Input("dsc-processing-undo", "data"),
    Input("dsc-processing-redo", "data"),
    Input("dsc-processing-default", "data"),
    Input("ui-locale", "data"),
)
def sync_smoothing_controls(draft, undo, redo, defaults, locale_data):
    loc = _loc(locale_data)
    values = (draft or {}).get("smoothing") or {}
    method = str(values.get("method") or "savgol")
    window_length = values.get("window_length", 11)
    polyorder = values.get("polyorder", 3)
    sigma = values.get("sigma", 2.0)
    status = _smoothing_status_text(draft, loc)
    undo_disabled = not bool(undo)
    redo_disabled = not bool(redo)
    reset_disabled = (draft or {}) == (defaults or {})
    return method, window_length, polyorder, sigma, status, undo_disabled, redo_disabled, reset_disabled


@callback(
    Output("dsc-baseline-method", "value"),
    Output("dsc-baseline-lam", "value"),
    Output("dsc-baseline-p", "value"),
    Output("dsc-baseline-region-enabled", "value"),
    Output("dsc-baseline-region-min", "value"),
    Output("dsc-baseline-region-max", "value"),
    Output("dsc-baseline-status", "children"),
    Input("dsc-processing-draft", "data"),
    Input("ui-locale", "data"),
)
def sync_baseline_controls(draft, locale_data):
    loc = _loc(locale_data)
    values = (draft or {}).get("baseline") or {}
    method = str(values.get("method") or "asls")
    lam = values.get("lam", 1e6)
    p = values.get("p", 0.01)
    region = values.get("region")
    enabled = isinstance(region, (list, tuple)) and len(region) == 2
    region_min = region[0] if enabled else None
    region_max = region[1] if enabled else None
    status = _baseline_status_text(draft, loc)
    return method, lam, p, bool(enabled), region_min, region_max, status


@callback(
    Output("dsc-peak-direction", "value"),
    Output("dsc-peak-prominence", "value"),
    Output("dsc-peak-distance", "value"),
    Output("dsc-peak-status", "children"),
    Input("dsc-processing-draft", "data"),
    Input("ui-locale", "data"),
)
def sync_peak_controls(draft, locale_data):
    loc = _loc(locale_data)
    values = (draft or {}).get("peak_detection") or {}
    direction = str(values.get("direction") or "both")
    prominence = values.get("prominence", 0.0)
    distance = values.get("distance", 1)
    status = _peak_status_text(draft, loc)
    return direction, prominence, distance, status


@callback(
    Output("dsc-tg-region-enabled", "value"),
    Output("dsc-tg-region-min", "value"),
    Output("dsc-tg-region-max", "value"),
    Output("dsc-tg-status", "children"),
    Input("dsc-processing-draft", "data"),
    Input("ui-locale", "data"),
)
def sync_tg_controls(draft, locale_data):
    loc = _loc(locale_data)
    values = (draft or {}).get("glass_transition") or {}
    region = values.get("region")
    enabled = isinstance(region, (list, tuple)) and len(region) == 2
    region_min = region[0] if enabled else None
    region_max = region[1] if enabled else None
    status = _tg_status_text(draft, loc)
    return bool(enabled), region_min, region_max, status


@callback(
    Output("dsc-run-status", "children"),
    Output("dsc-refresh", "data", allow_duplicate=True),
    Output("dsc-latest-result-id", "data", allow_duplicate=True),
    Output("workspace-refresh", "data", allow_duplicate=True),
    Input("dsc-run-btn", "n_clicks"),
    State("project-id", "data"),
    State("dsc-dataset-select", "value"),
    State("dsc-template-select", "value"),
    State("dsc-refresh", "data"),
    State("workspace-refresh", "data"),
    State("ui-locale", "data"),
    State("dsc-processing-draft", "data"),
    prevent_initial_call=True,
)
def run_dsc_analysis(
    n_clicks,
    project_id,
    dataset_key,
    template_id,
    refresh_val,
    global_refresh,
    locale_data,
    processing_draft,
):
    loc = _loc(locale_data)
    if not n_clicks or not project_id or not dataset_key:
        raise dash.exceptions.PreventUpdate

    from dash_app.api_client import analysis_run

    overrides = _overrides_from_draft(processing_draft) or None
    try:
        result = analysis_run(
            project_id=project_id,
            dataset_key=dataset_key,
            analysis_type="DSC",
            workflow_template_id=template_id,
            processing_overrides=overrides,
        )
    except Exception as exc:
        return dbc.Alert(translate_ui(loc, "dash.analysis.analysis_failed", error=str(exc)), color="danger"), dash.no_update, dash.no_update, dash.no_update

    alert, saved, result_id = interpret_run_result(result, locale_data=locale_data)
    refresh = (refresh_val or 0) + 1
    if saved:
        return alert, refresh, result_id, (global_refresh or 0) + 1
    return alert, refresh, dash.no_update, dash.no_update


@callback(
    Output("dsc-result-dataset-summary", "children"),
    Output("dsc-result-metrics", "children"),
    Output("dsc-result-quality", "children"),
    Output("dsc-result-raw-metadata", "children"),
    Output("dsc-result-figure", "children"),
    Output("dsc-result-derivative", "children"),
    Output("dsc-result-event-cards", "children"),
    Output("dsc-result-table", "children"),
    Output("dsc-result-processing", "children"),
    Input("dsc-latest-result-id", "data"),
    Input("dsc-refresh", "data"),
    Input("ui-theme", "data"),
    Input("ui-locale", "data"),
    State("project-id", "data"),
)
def display_result(result_id, _refresh, ui_theme, locale_data, project_id):
    loc = _loc(locale_data)
    empty_msg = empty_result_msg(locale_data=locale_data)
    summary_empty = html.P(translate_ui(loc, "dash.analysis.dsc.summary.empty"), className="text-muted")
    quality_empty = _dsc_collapsible_section(
        loc,
        "dash.analysis.dsc.quality.card_title",
        html.P(translate_ui(loc, "dash.analysis.dsc.quality.empty"), className="text-muted mb-0"),
        open=False,
    )
    raw_meta_empty = _dsc_collapsible_section(
        loc,
        "dash.analysis.dsc.raw_metadata.card_title",
        html.P(translate_ui(loc, "dash.analysis.dsc.raw_metadata.empty"), className="text-muted mb-0"),
        open=False,
    )
    if not result_id or not project_id:
        return summary_empty, empty_msg, quality_empty, raw_meta_empty, empty_msg, empty_msg, empty_msg, empty_msg, empty_msg

    from dash_app.api_client import workspace_dataset_detail, workspace_result_detail

    try:
        detail = workspace_result_detail(project_id, result_id)
    except Exception as exc:
        err = dbc.Alert(translate_ui(loc, "dash.analysis.error_loading_result", error=str(exc)), color="danger")
        return summary_empty, err, quality_empty, raw_meta_empty, empty_msg, empty_msg, empty_msg, empty_msg, empty_msg

    summary = detail.get("summary", {})
    result_meta = detail.get("result", {})
    processing = detail.get("processing", {})
    rows = _event_rows(detail.get("rows") or detail.get("rows_preview") or [])
    dataset_key = result_meta.get("dataset_key")

    dataset_detail = {}
    if dataset_key:
        try:
            dataset_detail = workspace_dataset_detail(project_id, dataset_key)
        except Exception:
            dataset_detail = {}

    dataset_summary_panel = _build_dsc_dataset_summary(
        dataset_detail,
        summary,
        result_meta,
        loc,
        locale_data=locale_data,
    )
    quality_panel = _build_dsc_quality_card(detail, result_meta, loc)
    raw_metadata_panel = _build_dsc_raw_metadata_panel((dataset_detail or {}).get("metadata"), loc)

    peak_count = int(summary.get("peak_count") or len(rows) or 0)
    tg_count = int(summary.get("glass_transition_count") or 0)
    fallback_display_name = _format_dataset_metadata_value(((dataset_detail or {}).get("dataset") or {}).get("display_name"))
    sample_name = resolve_sample_name(summary, result_meta, fallback_display_name=fallback_display_name, locale_data=locale_data)
    na = translate_ui(loc, "dash.analysis.na")
    metrics = metrics_row(
        [
            ("dash.analysis.metric.peaks", str(peak_count)),
            ("dash.analysis.metric.glass_transitions", str(tg_count)),
            ("dash.analysis.metric.template", str(processing.get("workflow_template_label", na))),
            ("dash.analysis.metric.sample", sample_name),
        ],
        locale_data=locale_data,
    )

    figure_area = empty_msg
    derivative_area = empty_msg
    if dataset_key:
        figure_area = _build_figure(project_id, dataset_key, summary, rows, ui_theme, loc, locale_data=locale_data)
        derivative_area = _build_derivative_panel(project_id, dataset_key, ui_theme, loc, locale_data=locale_data)

    event_cards = _build_event_cards(summary, rows, loc)
    table_area = _build_peak_table(rows, loc)

    proc_view = processing_details_section(
        processing,
        extra_lines=[
            html.P(translate_ui(loc, "dash.analysis.dsc.baseline", detail=processing.get("signal_pipeline", {}).get("baseline", {}))),
            html.P(
                translate_ui(
                    loc,
                    "dash.analysis.dsc.peak_detection",
                    detail=processing.get("analysis_steps", {}).get("peak_detection", {}),
                )
            ),
            html.P(
                translate_ui(
                    loc,
                    "dash.analysis.dsc.tg_detection",
                    detail=processing.get("analysis_steps", {}).get("glass_transition", {}),
                )
            ),
            html.P(
                translate_ui(
                    loc,
                    "dash.analysis.dsc.sign_convention",
                    detail=processing.get("method_context", {}).get("sign_convention_label", na),
                ),
                className="mb-0",
            ),
        ],
        locale_data=locale_data,
    )
    proc_view = _wrap_dsc_processing_details(proc_view, processing, loc)

    return (
        dataset_summary_panel,
        metrics,
        quality_panel,
        raw_metadata_panel,
        figure_area,
        derivative_area,
        event_cards,
        table_area,
        proc_view,
    )


@callback(
    Output("dsc-literature-card-title", "children"),
    Output("dsc-literature-hint", "children"),
    Output("dsc-literature-max-claims-label", "children"),
    Output("dsc-literature-persist-label", "children"),
    Output("dsc-literature-compare-btn", "children"),
    Input("ui-locale", "data"),
    Input("dsc-latest-result-id", "data"),
)
def render_dsc_literature_chrome(locale_data, result_id):
    loc = _loc(locale_data)
    if result_id:
        hint = literature_t(
            loc,
            f"{_DSC_LITERATURE_PREFIX}.ready",
            "Compare the saved DSC result to literature sources.",
        )
    else:
        hint = literature_t(
            loc,
            f"{_DSC_LITERATURE_PREFIX}.empty",
            "Run a DSC analysis first to enable literature comparison.",
        )
    return (
        literature_t(loc, f"{_DSC_LITERATURE_PREFIX}.title", "Literature Compare"),
        hint,
        literature_t(loc, f"{_DSC_LITERATURE_PREFIX}.max_claims", "Max Claims"),
        literature_t(loc, f"{_DSC_LITERATURE_PREFIX}.persist", "Persist to project"),
        literature_t(loc, f"{_DSC_LITERATURE_PREFIX}.compare_btn", "Compare"),
    )


@callback(
    Output("dsc-literature-compare-btn", "disabled"),
    Input("dsc-latest-result-id", "data"),
)
def toggle_dsc_literature_compare_button(result_id):
    return not bool(result_id)


@callback(
    Output("dsc-literature-output", "children"),
    Output("dsc-literature-status", "children"),
    Input("dsc-literature-compare-btn", "n_clicks"),
    State("project-id", "data"),
    State("dsc-latest-result-id", "data"),
    State("dsc-literature-max-claims", "value"),
    State("dsc-literature-persist", "value"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def compare_dsc_literature(n_clicks, project_id, result_id, max_claims, persist_values, locale_data):
    loc = _loc(locale_data)
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    if not project_id or not result_id:
        msg = literature_t(
            loc,
            f"{_DSC_LITERATURE_PREFIX}.missing_result",
            "Run a DSC analysis first.",
        )
        return dash.no_update, dbc.Alert(msg, color="warning", className="py-1 small")

    claims_limit = _coerce_int_positive(max_claims, default=3, minimum=1)
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
                f"{_DSC_LITERATURE_PREFIX}.error",
                "Literature compare failed: {error}",
            ).replace("{error}", str(exc)),
            color="danger",
            className="py-1 small",
        )
        return dash.no_update, err

    return (
        render_literature_output(payload, loc, i18n_prefix=_DSC_LITERATURE_PREFIX),
        literature_compare_status_alert(payload, loc, i18n_prefix=_DSC_LITERATURE_PREFIX),
    )


def _dsc_collapsible_section(loc: str, title_key: str, body: Any, *, open: bool = False) -> html.Details:
    return html.Details(
        [
            html.Summary(
                [
                    html.Span(className="ta-details-chevron"),
                    html.Span(translate_ui(loc, title_key), className="ms-1"),
                ],
                className="ta-details-summary",
            ),
            html.Div(body, className="ta-details-body mt-2"),
        ],
        className="ta-ms-details mb-0",
        open=open,
    )


@callback(
    Output("dsc-figure-captured", "data"),
    Input("dsc-latest-result-id", "data"),
    Input("project-id", "data"),
    Input("dsc-result-figure", "children"),
    State("dsc-figure-captured", "data"),
    prevent_initial_call=True,
)
def capture_dsc_figure(result_id, project_id, figure_children, captured):
    return capture_result_figure_from_layout(
        result_id=result_id,
        project_id=project_id,
        figure_children=figure_children,
        captured=captured,
        analysis_type="DSC",
    )


# ---------------------------------------------------------------------------
# DSC-specific builders
# ---------------------------------------------------------------------------

def _coerce_float(value) -> float | None:
    try:
        if value in (None, ""):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


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


def _series_for_temperature(series: list | tuple, temperature: list[float]) -> list[float]:
    if not isinstance(series, (list, tuple)) or len(series) != len(temperature):
        return []
    values: list[float] = []
    for item in series:
        parsed = _coerce_float(item)
        if parsed is None:
            return []
        values.append(parsed)
    return values


def _format_temp_c(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.1f} °C"


def _format_numeric(value: float | None, *, digits: int = 3) -> str:
    if value is None:
        return "--"
    return f"{value:.{digits}f}"


def _peak_type_label(peak_type: str | None, loc: str) -> str:
    token = str(peak_type or "").strip().lower()
    if token.startswith("endo"):
        return translate_ui(loc, "dash.analysis.dsc.peak_type.endotherm")
    if token.startswith("exo"):
        return translate_ui(loc, "dash.analysis.dsc.peak_type.exotherm")
    if token == "step":
        return translate_ui(loc, "dash.analysis.dsc.peak_type.step")
    return translate_ui(loc, "dash.analysis.dsc.peak_type.unknown")


def _event_rows(rows: list) -> list[dict]:
    clean = [dict(item) for item in rows if isinstance(item, dict)]
    return _sort_events_by_temperature(clean)


def _sort_events_by_temperature(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: _coerce_float(row.get("peak_temperature")) or float("inf"))


def _event_score(row: dict) -> float:
    area = abs(_coerce_float(row.get("area")) or 0.0)
    if area > 0:
        return area
    return abs(_coerce_float(row.get("height")) or 0.0)


def _split_primary_events(rows: list[dict], *, limit: int = 4) -> tuple[list[dict], list[dict]]:
    if len(rows) <= limit:
        return rows, []
    indexed = list(enumerate(rows))
    ranked = sorted(
        indexed,
        key=lambda item: (
            -_event_score(item[1]),
            _coerce_float(item[1].get("peak_temperature")) or float("inf"),
            item[0],
        ),
    )
    primary_idx = {idx for idx, _ in ranked[:limit]}
    primary = _sort_events_by_temperature([row for idx, row in indexed if idx in primary_idx])
    secondary = _sort_events_by_temperature([row for idx, row in indexed if idx not in primary_idx])
    return primary, secondary


def _trace_hover_template(trace_name: str, loc: str) -> str:
    return (
        f"<b>{trace_name}</b><br>"
        f"{translate_ui(loc, 'dash.analysis.dsc.figure.hover.temperature')}: %{{x:.2f}} °C<br>"
        f"{translate_ui(loc, 'dash.analysis.dsc.figure.hover.signal')}: %{{y:.5g}}"
        "<extra></extra>"
    )


def _event_hover_html(row: dict, y_value: float | None, loc: str) -> str:
    peak_type_label = _peak_type_label(row.get("peak_type"), loc)
    peak_temperature = _coerce_float(row.get("peak_temperature"))
    onset = _coerce_float(row.get("onset_temperature"))
    endset = _coerce_float(row.get("endset_temperature"))
    area = _coerce_float(row.get("area"))
    height = _coerce_float(row.get("height"))
    return (
        f"<b>{peak_type_label}</b><br>"
        f"{translate_ui(loc, 'dash.analysis.dsc.figure.hover.temperature')}: {_format_temp_c(peak_temperature)}<br>"
        f"{translate_ui(loc, 'dash.analysis.dsc.figure.hover.signal')}: {_format_numeric(y_value, digits=4)}<br>"
        f"{translate_ui(loc, 'dash.analysis.label.onset')}: {_format_temp_c(onset)}<br>"
        f"{translate_ui(loc, 'dash.analysis.label.endset')}: {_format_temp_c(endset)}<br>"
        f"{translate_ui(loc, 'dash.analysis.label.area')}: {_format_numeric(area)}<br>"
        f"{translate_ui(loc, 'dash.analysis.label.height')}: {_format_numeric(height)}"
        "<extra></extra>"
    )


def _build_tg_summary(summary: dict, loc: str) -> html.Div:
    tg_mid = _coerce_float(summary.get("tg_midpoint"))
    tg_onset = _coerce_float(summary.get("tg_onset"))
    tg_endset = _coerce_float(summary.get("tg_endset"))
    delta_cp = _coerce_float(summary.get("delta_cp"))
    tg_count = int(summary.get("glass_transition_count") or (1 if tg_mid is not None else 0) or 0)

    if tg_count == 0 or tg_mid is None:
        return html.Div(
            html.P(translate_ui(loc, "dash.analysis.state.not_detected"), className="text-muted mb-0 small"),
            className="mb-3",
        )

    onset_txt = f"{tg_onset:.1f}" if tg_onset is not None else "--"
    end_txt = f"{tg_endset:.1f}" if tg_endset is not None else "--"
    dcp_txt = f"{delta_cp:.4f}" if delta_cp is not None else "--"
    summary_line = translate_ui(loc, "dash.analysis.dsc.events.tg_one_liner").format(
        midpoint=f"{tg_mid:.1f}",
        onset=onset_txt,
        endset=end_txt,
        dcp=dcp_txt,
    )
    extra: list[Any] = []
    if tg_count > 1:
        extra.append(
            html.P(
                translate_ui(loc, "dash.analysis.state.more_transitions", n=tg_count - 1),
                className="text-muted small mb-0",
            )
        )
    return html.Div(
        [html.P(summary_line, className="small mb-1"), *extra],
        className="mb-3",
    )


def _build_event_cards(summary: dict, rows: list[dict], loc: str) -> html.Div:
    tg_block = _build_tg_summary(summary, loc)
    primary_rows, secondary_rows = _split_primary_events(rows, limit=4)

    cards: list[Any] = [
        html.H5(translate_ui(loc, "dash.analysis.section.key_thermal_events"), className="mb-2"),
        html.H6(translate_ui(loc, "dash.analysis.section.glass_transitions"), className="mb-2 text-muted small text-uppercase"),
        tg_block,
        html.H6(translate_ui(loc, "dash.analysis.section.detected_peaks"), className="mb-2 text-muted small text-uppercase"),
    ]

    if not rows:
        cards.append(html.P(translate_ui(loc, "dash.analysis.state.no_peaks"), className="text-muted mb-0"))
        if not summary.get("glass_transition_count"):
            cards.append(html.P(translate_ui(loc, "dash.analysis.dsc.events.empty"), className="text-muted small mt-2 mb-0"))
        return html.Div(cards)

    cards.append(
        html.P(
            translate_ui(loc, "dash.analysis.dsc.events_cards_intro", shown=len(primary_rows), total=len(rows)),
            className="text-muted small mb-2",
        )
    )
    cards.append(dbc.Row([dbc.Col(_peak_card(row, idx, loc), md=6) for idx, row in enumerate(primary_rows)], className="g-3"))

    if secondary_rows:
        cards.append(
            html.Details(
                [
                    html.Summary(translate_ui(loc, "dash.analysis.dsc.show_more_events", n=len(secondary_rows)), className="small"),
                    html.Div(
                        dataset_table(
                            secondary_rows,
                            ["peak_type", "peak_temperature", "onset_temperature", "endset_temperature", "area", "height"],
                            table_id="dsc-secondary-events-table",
                        ),
                        className="mt-3",
                    ),
                ],
                className="mt-3",
            )
        )
    return html.Div(cards)


def _build_peak_table(rows: list[dict], loc: str) -> html.Div:
    if not rows:
        return html.Div(
            [
                html.H5(translate_ui(loc, "dash.analysis.section.all_event_details"), className="mb-3"),
                html.P(translate_ui(loc, "dash.analysis.state.no_event_data"), className="text-muted"),
            ]
        )
    columns = ["peak_type", "peak_temperature", "onset_temperature", "endset_temperature", "area", "fwhm", "height"]
    return html.Div(
        [
            html.H5(translate_ui(loc, "dash.analysis.section.all_event_details"), className="mb-3"),
            dataset_table(rows, columns, table_id="dsc-peaks-table"),
        ]
    )


def _build_dsc_dataset_summary(
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

    sample_mass = _format_dataset_metadata_value(summary.get("sample_mass")) or _format_dataset_metadata_value(metadata.get("sample_mass"))
    if sample_mass:
        sample_mass = f"{sample_mass} {translate_ui(loc, 'dash.analysis.dsc.summary.mass_unit')}"
    else:
        sample_mass = na

    heating_rate = _format_dataset_metadata_value(summary.get("heating_rate")) or _format_dataset_metadata_value(metadata.get("heating_rate"))
    if heating_rate:
        heating_rate = f"{heating_rate} {translate_ui(loc, 'dash.analysis.dsc.summary.heating_rate_unit')}"
    else:
        heating_rate = na

    def _meta_value(value: str) -> html.Span:
        return html.Span(value, className="dsc-meta-value", title=value)

    rows: list[Any] = [
        html.Dt(translate_ui(loc, "dash.analysis.dsc.summary.dataset_label"), className="col-sm-4 text-muted dsc-meta-term"),
        html.Dd(_meta_value(dataset_label), className="col-sm-8 dsc-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.dsc.summary.sample_label"), className="col-sm-4 text-muted dsc-meta-term"),
        html.Dd(_meta_value(sample_label), className="col-sm-8 dsc-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.dsc.summary.mass_label"), className="col-sm-4 text-muted dsc-meta-term"),
        html.Dd(_meta_value(sample_mass), className="col-sm-8 dsc-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.dsc.summary.heating_rate_label"), className="col-sm-4 text-muted dsc-meta-term"),
        html.Dd(_meta_value(heating_rate), className="col-sm-8 dsc-meta-def"),
    ]
    return html.Div(
        [
            html.H5(translate_ui(loc, "dash.analysis.dsc.summary.card_title"), className="mb-3"),
            html.Dl(rows, className="row mb-0"),
        ]
    )


def _build_dsc_quality_card(detail: dict, result_meta: dict, loc: str) -> html.Details:
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
        html.P(
            [
                html.Strong(translate_ui(loc, "dash.analysis.dsc.quality.status_label")),
                f" {status}",
            ],
            className="mb-2",
        ),
        html.P(
            [
                html.Strong(translate_ui(loc, "dash.analysis.dsc.quality.warnings_label")),
                f" {wc}",
            ],
            className="mb-2",
        ),
        html.P(
            [
                html.Strong(translate_ui(loc, "dash.analysis.dsc.quality.issues_label")),
                f" {ic}",
            ],
            className="mb-0",
        ),
    ]
    if warnings_list:
        body_children.append(html.Ul([html.Li(str(w)) for w in warnings_list[:12]], className="small mb-0 mt-2"))
    if issues_list:
        body_children.append(html.Ul([html.Li(str(w)) for w in issues_list[:12]], className="small mb-0 mt-2"))

    inner = dbc.Alert(body_children, color=alert_color, className="mb-0 ta-quality-alert")
    return _dsc_collapsible_section(loc, "dash.analysis.dsc.quality.card_title", inner, open=False)


def _build_dsc_raw_metadata_panel(metadata: dict | None, loc: str) -> html.Details:
    meta = metadata if isinstance(metadata, dict) else {}
    if not meta:
        inner = html.P(translate_ui(loc, "dash.analysis.dsc.raw_metadata.empty"), className="text-muted mb-0")
    else:
        rows: list[Any] = []
        for key in sorted(meta.keys(), key=lambda k: str(k).lower()):
            value = meta[key]
            if isinstance(value, (dict, list)):
                text = json.dumps(value, ensure_ascii=False, indent=2)
            else:
                fv = _format_dataset_metadata_value(value)
                text = fv if fv is not None else str(value)
            rows.extend(
                [
                    html.Dt(str(key), className="col-sm-4 text-muted small"),
                    html.Dd(html.Pre(text, className="small mb-0 ta-code-block p-2 rounded"), className="col-sm-8 mb-2"),
                ]
            )
        inner = html.Dl(rows, className="row mb-0", id="dsc-raw-metadata-dl")
    return _dsc_collapsible_section(loc, "dash.analysis.dsc.raw_metadata.card_title", inner, open=False)


def _build_dsc_processing_expansion_blocks(processing: dict, loc: str) -> html.Div:
    sp = processing.get("signal_pipeline") or {}
    asteps = processing.get("analysis_steps") or {}
    blocks: list[Any] = []
    pairs = [
        ("dash.analysis.dsc.processing.block_smoothing", sp.get("smoothing")),
        ("dash.analysis.dsc.processing.block_baseline", sp.get("baseline")),
        ("dash.analysis.dsc.processing.block_peaks", asteps.get("peak_detection")),
        ("dash.analysis.dsc.processing.block_tg", asteps.get("glass_transition")),
    ]
    for title_key, data in pairs:
        if not isinstance(data, dict) or not data:
            continue
        blocks.append(html.H6(translate_ui(loc, title_key), className="mt-2 small text-muted mb-1"))
        blocks.append(html.Pre(json.dumps(data, indent=2, ensure_ascii=False), className="small ta-code-block p-2 rounded mb-0"))
    if not blocks:
        return html.Div()
    return html.Div(blocks, className="mt-3 pt-2 border-top")


def _wrap_dsc_processing_details(inner: html.Div, processing: dict, loc: str) -> html.Div:
    expansion = _build_dsc_processing_expansion_blocks(processing, loc)
    return html.Div(
        [
            html.Details(
                [
                    html.Summary(
                        [
                            html.Span(className="ta-details-chevron"),
                            html.Span(translate_ui(loc, "dash.analysis.dsc.processing.expand_summary"), className="ms-1"),
                        ],
                        className="ta-details-summary",
                    ),
                    html.Div([inner, expansion], className="ta-details-body mt-2"),
                ],
                className="ta-ms-details mb-0",
                open=False,
            )
        ]
    )


def _build_derivative_panel(
    project_id: str,
    dataset_key: str,
    ui_theme: str | None,
    loc: str,
    *,
    locale_data: str | None = None,
) -> html.Div:
    """Compact d(corrected signal)/dT vs temperature helper (uses backend ``dtg`` curve)."""
    _ld = locale_data if locale_data is not None else loc
    from dash_app.api_client import analysis_state_curves

    try:
        curves = analysis_state_curves(project_id, "DSC", dataset_key)
    except Exception:
        curves = {}

    if not curves.get("has_dtg") and not curves.get("dtg"):
        return html.Div()

    raw_temperature = curves.get("temperature") or []
    raw_dtg = curves.get("dtg") or []
    if not raw_temperature or not raw_dtg or len(raw_temperature) != len(raw_dtg):
        return html.Div()

    temperature: list[float] = []
    dtg: list[float] = []
    for tx, dx in zip(raw_temperature, raw_dtg):
        pt = _coerce_float(tx)
        pd = _coerce_float(dx)
        if pt is None or pd is None:
            continue
        temperature.append(pt)
        dtg.append(pd)
    if len(temperature) < 3:
        return html.Div()

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=temperature,
            y=dtg,
            mode="lines",
            name=translate_ui(loc, "dash.analysis.dsc.derivative.trace_name"),
            line=dict(color="#7C3AED", width=1.8),
        )
    )
    fig.update_layout(
        title=dict(
            text=translate_ui(loc, "dash.analysis.dsc.derivative.title"),
            x=0.01,
            xanchor="left",
            font=dict(size=14),
        ),
        xaxis_title=translate_ui(loc, "dash.analysis.figure.axis_temperature_c"),
        yaxis_title=translate_ui(loc, "dash.analysis.dsc.derivative.axis_label"),
        height=280,
        margin=dict(l=56, r=18, t=48, b=44),
        showlegend=False,
    )
    apply_figure_theme(fig, ui_theme)
    graph = dcc.Graph(
        figure=fig,
        config={
            "displaylogo": False,
            "responsive": True,
            "modeBarButtonsToRemove": ["lasso2d", "select2d", "toggleSpikelines", "hoverCompareCartesian"],
        },
        className="ta-plot dsc-derivative-graph",
    )
    return html.Div(
        [
            html.H6(translate_ui(loc, "dash.analysis.dsc.derivative.card_title"), className="mb-2"),
            html.P(translate_ui(loc, "dash.analysis.dsc.derivative.caption"), className="small text-muted mb-2"),
            graph,
        ],
        className="dsc-derivative-helper",
    )


def _build_dsc_go_figure(
    project_id: str,
    dataset_key: str,
    summary: dict,
    peak_rows: list[dict],
    ui_theme: str | None,
    loc: str,
) -> go.Figure | None:
    from dash_app.api_client import analysis_state_curves

    try:
        curves = analysis_state_curves(project_id, "DSC", dataset_key)
    except Exception:
        curves = {}

    raw_temperature = curves.get("temperature") or []
    if not raw_temperature:
        return None
    temperature: list[float] = []
    for item in raw_temperature:
        parsed = _coerce_float(item)
        if parsed is None:
            return None
        temperature.append(parsed)

    raw_signal = _series_for_temperature(curves.get("raw_signal", []), temperature)
    smoothed = _series_for_temperature(curves.get("smoothed", []), temperature)
    baseline = _series_for_temperature(curves.get("baseline", []), temperature)
    corrected = _series_for_temperature(curves.get("corrected", []), temperature)
    primary_signal = corrected or smoothed or raw_signal
    if not primary_signal:
        return None

    is_dark = normalize_ui_theme(ui_theme) == "dark"
    fig = go.Figure()

    legend_raw = translate_ui(loc, "dash.analysis.figure.legend_raw_signal")
    legend_smooth = translate_ui(loc, "dash.analysis.figure.legend_smoothed")
    legend_base = translate_ui(loc, "dash.analysis.figure.legend_baseline")
    legend_corrected = translate_ui(loc, "dash.analysis.figure.legend_corrected")

    primary_key = "corrected" if corrected else "smoothed" if smoothed else "raw"

    if raw_signal:
        fig.add_trace(
            go.Scatter(
                x=temperature,
                y=raw_signal,
                mode="lines",
                name=legend_raw,
                line=dict(color="#94A3B8", width=2.8 if primary_key == "raw" else 1.0),
                opacity=0.95 if primary_key == "raw" else 0.26,
                hovertemplate=_trace_hover_template(legend_raw, loc),
            )
        )
    if smoothed:
        fig.add_trace(
            go.Scatter(
                x=temperature,
                y=smoothed,
                mode="lines",
                name=legend_smooth,
                line=dict(color="#0E7490", width=2.8 if primary_key == "smoothed" else 1.5),
                opacity=0.98 if primary_key == "smoothed" else 0.64,
                hovertemplate=_trace_hover_template(legend_smooth, loc),
            )
        )
    if baseline:
        fig.add_trace(
            go.Scatter(
                x=temperature,
                y=baseline,
                mode="lines",
                name=legend_base,
                line=dict(color="#64748B", width=1.0, dash="dot"),
                opacity=0.42,
                hovertemplate=_trace_hover_template(legend_base, loc),
            )
        )
    if corrected:
        fig.add_trace(
            go.Scatter(
                x=temperature,
                y=corrected,
                mode="lines",
                name=legend_corrected,
                line=dict(color="#047857", width=3.0 if primary_key == "corrected" else 1.8),
                opacity=1.0 if primary_key == "corrected" else 0.72,
                hovertemplate=_trace_hover_template(legend_corrected, loc),
            )
        )

    annotated_temps: list[float] = []
    tg_midpoint = _coerce_float(summary.get("tg_midpoint"))
    tg_onset = _coerce_float(summary.get("tg_onset"))
    tg_endset = _coerce_float(summary.get("tg_endset"))
    if tg_midpoint is not None:
        fig.add_vline(
            x=tg_midpoint,
            line=dict(color="#EF4444", width=2, dash="dash"),
            annotation_text=translate_ui(loc, "dash.analysis.figure.annot_tg", v=f"{tg_midpoint:.1f}"),
            annotation_position="top left",
        )
        annotated_temps.append(tg_midpoint)
    if tg_onset is not None and all(abs(tg_onset - value) >= _ANNOTATION_MIN_SEP for value in annotated_temps):
        fig.add_vline(
            x=tg_onset,
            line=dict(color="#F59E0B", width=1, dash="dot"),
            annotation_text=translate_ui(loc, "dash.analysis.figure.annot_on", v=f"{tg_onset:.1f}"),
            annotation_position="top left",
        )
        annotated_temps.append(tg_onset)
    if tg_endset is not None and all(abs(tg_endset - value) >= _ANNOTATION_MIN_SEP for value in annotated_temps):
        fig.add_vline(
            x=tg_endset,
            line=dict(color="#F59E0B", width=1, dash="dot"),
            annotation_text=translate_ui(loc, "dash.analysis.figure.annot_end", v=f"{tg_endset:.1f}"),
            annotation_position="top left",
        )
        annotated_temps.append(tg_endset)

    for row in _sort_events_by_temperature(peak_rows):
        peak_temperature = _coerce_float(row.get("peak_temperature"))
        if peak_temperature is None:
            continue
        idx = min(range(len(temperature)), key=lambda i: abs(temperature[i] - peak_temperature))
        peak_type = str(row.get("peak_type", "unknown")).strip().lower()
        color = _PEAK_TYPE_COLORS.get(peak_type, "#B45309")
        too_close = any(abs(peak_temperature - value) < _ANNOTATION_MIN_SEP for value in annotated_temps)
        label = "" if too_close else f"{peak_temperature:.1f}°C"
        fig.add_trace(
            go.Scatter(
                x=[temperature[idx]],
                y=[primary_signal[idx]],
                mode="markers+text",
                marker=dict(size=8, color=color, symbol="diamond", line=dict(color="white", width=1.0)),
                text=[label],
                textposition="top center",
                textfont=dict(size=8, color=color),
                name=f"{_peak_type_label(peak_type, loc)} {_format_temp_c(peak_temperature)}",
                showlegend=False,
                hovertemplate=_event_hover_html(row, _coerce_float(primary_signal[idx]), loc),
            )
        )
        if label:
            annotated_temps.append(peak_temperature)

    sample_name = resolve_sample_name(summary, {"dataset_key": dataset_key}, fallback_display_name=dataset_key, locale_data=loc)
    y_grid_color = "rgba(61, 59, 56, 0.34)" if is_dark else "rgba(224, 221, 214, 0.52)"
    x_grid_color = "rgba(61, 59, 56, 0.26)" if is_dark else "rgba(224, 221, 214, 0.36)"
    axis_line_color = "rgba(61, 59, 56, 0.84)" if is_dark else "rgba(183, 177, 168, 0.9)"
    tick_color = "rgba(238, 237, 234, 0.9)" if is_dark else "rgba(28, 26, 26, 0.78)"

    fig.update_layout(
        title=dict(
            text=translate_ui(loc, "dash.analysis.figure.title_dsc", name=sample_name),
            x=0.01,
            xanchor="left",
            y=0.985,
            yanchor="top",
            font=dict(size=17),
        ),
        xaxis_title=translate_ui(loc, "dash.analysis.figure.axis_temperature_c"),
        yaxis_title=translate_ui(loc, "dash.analysis.figure.axis_heat_flow"),
        hovermode="x unified",
        margin=dict(l=70, r=34, t=86, b=62),
        height=600,
        hoverlabel=dict(namelength=-1),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.015,
            xanchor="right",
            x=1.0,
            traceorder="normal",
            itemclick="toggleothers",
            itemdoubleclick="toggle",
            font=dict(size=11),
            itemsizing="constant",
        ),
    )
    apply_figure_theme(fig, ui_theme)
    fig.update_xaxes(
        gridcolor=x_grid_color,
        showgrid=False,
        showline=True,
        linewidth=1,
        linecolor=axis_line_color,
        ticks="outside",
        ticklen=4,
        tickcolor=axis_line_color,
        tickfont=dict(size=12, color=tick_color),
        title_standoff=12,
    )
    fig.update_yaxes(
        gridcolor=y_grid_color,
        showgrid=True,
        showline=True,
        linewidth=1,
        linecolor=axis_line_color,
        ticks="outside",
        ticklen=4,
        tickcolor=axis_line_color,
        tickfont=dict(size=12, color=tick_color),
        title_standoff=12,
    )
    return fig


def _dsc_graph_config() -> dict[str, Any]:
    return {
        "displaylogo": False,
        "responsive": True,
        "modeBarButtonsToRemove": ["lasso2d", "select2d", "toggleSpikelines", "hoverCompareCartesian"],
        "toImageButtonOptions": {
            "format": "png",
            "filename": "dsc-analysis",
            "scale": 2,
        },
    }


def _build_figure(
    project_id: str,
    dataset_key: str,
    summary: dict,
    peak_rows: list[dict],
    ui_theme: str | None,
    loc: str,
    locale_data: str | None = None,
) -> html.Div:
    _ld = locale_data if locale_data is not None else loc
    fig = _build_dsc_go_figure(project_id, dataset_key, summary, peak_rows, ui_theme, loc)
    if fig is None:
        return no_data_figure_msg(text=translate_ui(loc, "dash.analysis.dsc.no_plot_signal"), locale_data=_ld)
    graph = dcc.Graph(figure=fig, config=_dsc_graph_config(), className="ta-plot dsc-result-graph")
    return html.Div(graph, className="dsc-result-figure-shell")
