"""TGA analysis page -- backend-driven first analysis slice.

Lets the user:
  1. Use **Setup / Processing / Run** tabs (aligned with DSC and DTA)
  2. **Setup:** dataset, unit mode (auto / percent / absolute_mass), workflow template
  3. **Processing:** presets and separate **Smoothing** / **Step detection** cards
     (parameters flow into ``processing_overrides`` and preset payloads)
  4. **Run:** execute via the backend ``/analysis/run`` endpoint
  5. View analysis summary, validation, main mass trace, DTG preview, steps,
     processing, raw metadata, literature compare, and auto-refresh workspace state
"""

from __future__ import annotations

import base64
import copy
import json
import math
from datetime import datetime, timezone
from typing import Any

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html
import plotly.graph_objects as go

from dash_app.components.analysis_boilerplate import (
    build_collapsible_section,
    build_load_saveas_preset_card,
    build_processing_history_card,
)
from dash_app.components.analysis_page import (
    analysis_page_stores,
    capture_result_figure_from_layout,
    register_result_figure_from_layout_children,
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
from dash_app.components.figure_artifacts import (
    FIGURE_ARTIFACT_PREVIEW_MAX_EDGE,
    FIGURE_ARTIFACT_PREVIEW_TILES,
    build_figure_artifact_surface,
    build_figure_artifacts_panel,
    figure_action_from_trigger,
    figure_action_metadata,
    figure_action_status_alert,
    figure_artifact_button_labels,
    ordered_figure_preview_keys,
    prepare_result_graph_figure,
    result_graph_class,
    result_graph_config,
    RESULT_GRAPH_STYLE,
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
from dash_app.components.tga_explore import (
    MAX_TGA_UNDO_DEPTH,
    append_undo_after_edit,
    build_tga_raw_quality_panel,
    compute_tga_raw_exploration_stats,
    downsample_rows,
    format_tga_step_reference_callout,
    perform_redo,
    perform_undo,
    tga_draft_processing_equal,
)
from dash_app.components.processing_inputs import (
    coerce_float_non_negative as _coerce_float_non_negative,
    coerce_float_positive as _coerce_float_positive,
    coerce_int_positive as _coerce_int_positive,
)
from dash_app.theme import PLOT_THEME, apply_figure_theme, normalize_ui_theme
from utils.i18n import normalize_ui_locale, translate_ui

dash.register_page(__name__, path="/tga", title="TGA Analysis - MaterialScope")

_TGA_TEMPLATE_IDS = ["tga.general", "tga.single_step_decomposition", "tga.multi_step_decomposition"]
_TGA_UNIT_MODE_IDS = ["auto", "percent", "absolute_mass"]
_TGA_ELIGIBLE_TYPES = {"TGA", "UNKNOWN"}

_TGA_RESULT_CARD_ROLES = {
    "context": "ms-result-context",
    "hero": "ms-result-hero",
    "support": "ms-result-support",
    "secondary": "ms-result-secondary",
}
_TGA_LITERATURE_PREFIX = "dash.analysis.tga.literature"

_TGA_USER_FACING_METADATA_KEYS: frozenset[str] = frozenset({
    "sample_name",
    "display_name",
    "sample_mass",
    "heating_rate",
    "instrument",
    "vendor",
    "file_name",
    "source_data_hash",
})

_TGA_MAX_STEP_CARDS = 6
_TGA_TRUNCATE_STEP_CARDS_WHEN = 7

_TGA_PRESET_ANALYSIS_TYPE = "TGA"
_TGA_SMOOTH_METHODS = frozenset({"savgol", "moving_average", "gaussian"})
_TGA_SMOOTHING_DEFAULTS: dict[str, dict[str, Any]] = {
    "savgol": {"method": "savgol", "window_length": 11, "polyorder": 3},
    "moving_average": {"method": "moving_average", "window_length": 11},
    "gaussian": {"method": "gaussian", "sigma": 2.0},
}
_TGA_STEP_DETECTION_DEFAULTS: dict[str, Any] = {
    "method": "dtg_peaks",
    "prominence": None,
    "min_mass_loss": 0.5,
    "search_half_width": 80,
}


def _default_tga_processing_draft() -> dict[str, Any]:
    return {
        "smoothing": copy.deepcopy(_TGA_SMOOTHING_DEFAULTS["savgol"]),
        "step_detection": copy.deepcopy(_TGA_STEP_DETECTION_DEFAULTS),
    }


def _merge_tga_smoothing_defaults(values: dict | None) -> dict[str, Any]:
    base = copy.deepcopy(_TGA_SMOOTHING_DEFAULTS["savgol"])
    if isinstance(values, dict):
        method = str(values.get("method") or "savgol").strip().lower()
        if method in _TGA_SMOOTH_METHODS:
            base = copy.deepcopy(_TGA_SMOOTHING_DEFAULTS.get(method, _TGA_SMOOTHING_DEFAULTS["savgol"]))
        for k, v in values.items():
            if k == "method":
                continue
            if v is not None:
                base[k] = copy.deepcopy(v)
    return _normalize_tga_smoothing_section(base)


def _merge_tga_step_defaults(values: dict | None) -> dict[str, Any]:
    base = copy.deepcopy(_TGA_STEP_DETECTION_DEFAULTS)
    if isinstance(values, dict):
        for k, v in values.items():
            if k == "method":
                continue
            if v is not None or k == "prominence":
                base[k] = copy.deepcopy(v)
    return _normalize_tga_step_section(base)


def _normalize_tga_smoothing_section(smoothing: dict[str, Any]) -> dict[str, Any]:
    method = str(smoothing.get("method") or "savgol").strip().lower()
    if method not in _TGA_SMOOTH_METHODS:
        method = "savgol"
    if method == "savgol":
        wl = _coerce_int_positive(smoothing.get("window_length"), default=11, minimum=5)
        if wl % 2 == 0:
            wl += 1
        po = _coerce_int_positive(smoothing.get("polyorder"), default=3, minimum=1)
        po = min(po, max(wl - 2, 1))
        return {"method": "savgol", "window_length": wl, "polyorder": po}
    if method == "moving_average":
        wl = _coerce_int_positive(smoothing.get("window_length"), default=11, minimum=3)
        if wl % 2 == 0:
            wl += 1
        return {"method": "moving_average", "window_length": wl}
    sigma = _coerce_float_positive(smoothing.get("sigma"), default=2.0, minimum=0.1)
    return {"method": "gaussian", "sigma": sigma}


def _normalize_tga_step_section(step: dict[str, Any]) -> dict[str, Any]:
    prom_raw = step.get("prominence", _TGA_STEP_DETECTION_DEFAULTS["prominence"])
    prominence: float | None
    if prom_raw in (None, ""):
        prominence = None
    else:
        try:
            pv = float(prom_raw)
        except (TypeError, ValueError):
            prominence = None
        else:
            prominence = None if not math.isfinite(pv) or pv <= 0 else pv
    min_ml = _coerce_float_non_negative(step.get("min_mass_loss"), default=float(_TGA_STEP_DETECTION_DEFAULTS["min_mass_loss"]))
    if min_ml <= 0:
        min_ml = float(_TGA_STEP_DETECTION_DEFAULTS["min_mass_loss"])
    half = _coerce_int_positive(step.get("search_half_width"), default=80, minimum=3)
    return {
        "method": "dtg_peaks",
        "prominence": prominence,
        "min_mass_loss": min_ml,
        "search_half_width": half,
    }


def _normalize_tga_processing_draft(draft: dict | None) -> dict[str, Any]:
    d = dict(draft or {})
    sm = d.get("smoothing")
    st = d.get("step_detection")
    return {
        "smoothing": _merge_tga_smoothing_defaults(sm if isinstance(sm, dict) else None),
        "step_detection": _merge_tga_step_defaults(st if isinstance(st, dict) else None),
    }


def _tga_overrides_from_draft(draft: dict | None) -> dict[str, Any]:
    norm = _normalize_tga_processing_draft(draft)
    return {
        "smoothing": copy.deepcopy(norm["smoothing"]),
        "step_detection": copy.deepcopy(norm["step_detection"]),
    }


def _tga_draft_and_unit_from_loaded_processing(processing: dict | None) -> tuple[dict[str, Any], str]:
    if not isinstance(processing, dict):
        return copy.deepcopy(_default_tga_processing_draft()), "auto"
    sp = processing.get("signal_pipeline") or {}
    ast = processing.get("analysis_steps") or {}
    sm = sp.get("smoothing") if isinstance(sp.get("smoothing"), dict) else processing.get("smoothing")
    st = ast.get("step_detection") if isinstance(ast.get("step_detection"), dict) else processing.get("step_detection")
    mc = processing.get("method_context") if isinstance(processing.get("method_context"), dict) else {}
    unit = str(mc.get("tga_unit_mode_declared") or "auto").strip().lower()
    if unit not in _TGA_UNIT_MODE_IDS:
        unit = "auto"
    draft = {
        "smoothing": _merge_tga_smoothing_defaults(sm if isinstance(sm, dict) else None),
        "step_detection": _merge_tga_step_defaults(st if isinstance(st, dict) else None),
    }
    return draft, unit


def _tga_preset_processing_body_for_save(draft: dict | None, unit_mode: str | None) -> dict[str, Any]:
    from core.processing_schema import get_tga_unit_modes

    norm = _normalize_tga_processing_draft(draft)
    mode = str(unit_mode or "auto").strip().lower()
    if mode not in _TGA_UNIT_MODE_IDS:
        mode = "auto"
    labels = {entry["id"]: entry["label"] for entry in get_tga_unit_modes()}
    label = labels.get(mode, mode.replace("_", " ").title())
    return {
        "smoothing": copy.deepcopy(norm["smoothing"]),
        "step_detection": copy.deepcopy(norm["step_detection"]),
        "method_context": {
            "tga_unit_mode_declared": mode,
            "tga_unit_mode_label": label,
        },
    }


def _tga_ui_snapshot_dict(template_id: str | None, unit_mode: str | None, draft: dict | None) -> dict[str, Any]:
    tid = template_id if template_id in _TGA_TEMPLATE_IDS else "tga.general"
    u = unit_mode if unit_mode in _TGA_UNIT_MODE_IDS else "auto"
    norm = _normalize_tga_processing_draft(draft)
    return {
        "workflow_template_id": tid,
        "unit_mode": u,
        "smoothing": norm["smoothing"],
        "step_detection": norm["step_detection"],
    }


def _tga_snapshots_equal(a: dict | None, b: dict | None) -> bool:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


_TGA_QUALITY_CHECK_ORDER: tuple[str, ...] = (
    "import_review_required",
    "import_confidence",
    "inferred_analysis_type",
    "inferred_signal_unit",
    "tga_unit_mode_resolved",
    "tga_unit_inference_basis",
    "tga_unit_interpretation_status",
    "tga_unit_auto_inference_used",
    "unit_plausibility",
    "axis_direction",
    "temperature_min",
    "temperature_max",
    "vendor_detection_confidence",
)


def _loc(locale_data: str | None) -> str:
    return normalize_ui_locale(locale_data)


def _tga_result_section(child: Any, *, role: str = "support") -> html.Div:
    role_class = _TGA_RESULT_CARD_ROLES.get(role, _TGA_RESULT_CARD_ROLES["support"])
    return html.Div(child, className=f"ms-result-section {role_class}")


def _tga_collapsible_section(
    loc: str,
    title_key: str,
    body: Any,
    *,
    open: bool = False,
    summary_suffix: Any | None = None,
) -> html.Details:
    return build_collapsible_section(loc, title_key, body, open=open, summary_suffix=summary_suffix)


def _literature_compare_card() -> dbc.Card:
    return build_literature_compare_card(id_prefix="tga")


def _tga_workflow_guide_block() -> html.Details:
    return html.Details(
        [
            html.Summary(
                [html.Span(className="ta-details-chevron"), html.Span(id="tga-workflow-guide-title", className="ms-1")],
                className="ta-details-summary",
            ),
            html.Div(id="tga-workflow-guide-body", className="ta-details-body mt-2 small"),
        ],
        className="ta-ms-details mb-3",
        open=False,
    )


def _tga_raw_quality_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H6(id="tga-raw-quality-card-title", className="card-title mb-1"),
                html.P(id="tga-raw-quality-card-hint", className="small text-muted mb-2"),
                html.Div(id="tga-raw-quality-panel", className="tga-raw-quality-panel"),
            ]
        ),
        className="mb-3",
    )


def _tga_processing_history_card() -> dbc.Card:
    return build_processing_history_card(
        title_id="tga-processing-history-title",
        hint_id="tga-processing-history-hint",
        undo_button_id="tga-processing-undo-btn",
        redo_button_id="tga-processing-redo-btn",
        reset_button_id="tga-processing-reset-btn",
        status_id="tga-history-status",
    )


def _step_card(step: dict, idx: int, loc: str) -> dbc.Card:
    onset = step.get("onset_temperature")
    midpoint = step.get("midpoint_temperature")
    endset = step.get("endset_temperature")
    mass_loss = step.get("mass_loss_percent")
    residual = step.get("residual_percent")
    mass_loss_mg = step.get("mass_loss_mg")
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(
                    [
                        html.I(className="bi bi-arrow-down-circle me-2", style={"color": "#059669", "fontSize": "1.1rem"}),
                        html.Strong(translate_ui(loc, "dash.analysis.label.step_n", n=idx + 1), className="me-2"),
                        html.Span(
                            f"{mass_loss:.2f} %" if mass_loss is not None else "--",
                            className="badge",
                            style={"backgroundColor": "#059669", "color": "white", "fontSize": "0.75rem"},
                        ),
                    ],
                    className="mb-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Small(translate_ui(loc, "dash.analysis.label.onset"), className="text-muted d-block"),
                                html.Span(f"{onset:.1f} C" if onset is not None else "--"),
                            ],
                            md=3,
                        ),
                        dbc.Col(
                            [
                                html.Small(translate_ui(loc, "dash.analysis.label.midpoint"), className="text-muted d-block"),
                                html.Span(f"{midpoint:.1f} C" if midpoint is not None else "--"),
                            ],
                            md=3,
                        ),
                        dbc.Col(
                            [
                                html.Small(translate_ui(loc, "dash.analysis.label.endset"), className="text-muted d-block"),
                                html.Span(f"{endset:.1f} C" if endset is not None else "--"),
                            ],
                            md=3,
                        ),
                        dbc.Col(
                            [
                                html.Small(translate_ui(loc, "dash.analysis.label.mass_loss"), className="text-muted d-block"),
                                html.Span(f"{mass_loss:.2f} %" if mass_loss is not None else "--"),
                                html.Small(f" {translate_ui(loc, 'dash.analysis.label.residual')}", className="text-muted ms-1"),
                                html.Span(f"{residual:.1f} %" if residual is not None else "--"),
                            ],
                            md=3,
                        ),
                    ],
                    className="g-2",
                ),
                *(
                    [html.P(translate_ui(loc, "dash.analysis.tga.mass_loss_mg", v=mass_loss_mg), className="text-muted small mb-0 mt-1")]
                    if mass_loss_mg is not None
                    else []
                ),
                format_tga_step_reference_callout(midpoint, loc),
            ]
        ),
        className="mb-2",
    )


def _unit_mode_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="tga-unit-card-title", children="", className="mb-3"),
                dbc.Select(id="tga-unit-mode-select", options=[], value="auto"),
                html.P("", className="text-muted small mt-2", id="tga-unit-mode-description"),
            ]
        ),
        className="mb-3",
    )


def _tga_preset_card() -> dbc.Card:
    return build_load_saveas_preset_card(id_prefix="tga")


def _tga_smoothing_controls_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="tga-smoothing-card-title", className="card-title mb-2"),
                html.P(id="tga-smoothing-card-hint", className="small text-muted mb-3"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id="tga-smooth-method-label", html_for="tga-smooth-method", className="mb-1"),
                                dbc.Select(
                                    id="tga-smooth-method",
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
                                dbc.Label(id="tga-smooth-window-label", html_for="tga-smooth-window", className="mb-1"),
                                dbc.Input(id="tga-smooth-window", type="number", min=3, step=2, value=11),
                            ],
                            md=4,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="tga-smooth-polyorder-label", html_for="tga-smooth-polyorder", className="mb-1"),
                                dbc.Input(id="tga-smooth-polyorder", type="number", min=1, max=7, step=1, value=3),
                            ],
                            md=4,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="tga-smooth-sigma-label", html_for="tga-smooth-sigma", className="mb-1"),
                                dbc.Input(id="tga-smooth-sigma", type="number", min=0.1, step=0.1, value=2.0),
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


def _tga_step_detection_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="tga-step-card-title", className="card-title mb-2"),
                html.P(id="tga-step-card-hint", className="small text-muted mb-3"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id="tga-step-prominence-label", html_for="tga-step-prominence", className="mb-1"),
                                dbc.Input(id="tga-step-prominence", type="text", value="", placeholder=""),
                            ],
                            md=4,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="tga-step-min-mass-label", html_for="tga-step-min-mass", className="mb-1"),
                                dbc.Input(id="tga-step-min-mass", type="number", min=0, step=0.05, value=0.5),
                            ],
                            md=4,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(id="tga-step-half-width-label", html_for="tga-step-half-width", className="mb-1"),
                                dbc.Input(id="tga-step-half-width", type="number", min=3, step=1, value=80),
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


def _tga_left_column_tabs() -> dbc.Tabs:
    """Setup / Processing / Run tabs — same structure as DSC and DTA left columns."""
    return dbc.Tabs(
        [
            dbc.Tab(
                [
                    dataset_selection_card("tga-dataset-selector-area", card_title_id="tga-dataset-card-title"),
                    _unit_mode_card(),
                    workflow_template_card(
                        "tga-template-select",
                        "tga-template-description",
                        [],
                        "tga.general",
                        card_title_id="tga-workflow-card-title",
                    ),
                    _tga_workflow_guide_block(),
                    _tga_raw_quality_card(),
                ],
                tab_id="tga-tab-setup",
                label_class_name="ta-tab-label",
                id="tga-tab-setup-shell",
            ),
            dbc.Tab(
                [
                    _tga_processing_history_card(),
                    _tga_preset_card(),
                    _tga_smoothing_controls_card(),
                    _tga_step_detection_card(),
                ],
                tab_id="tga-tab-processing",
                label_class_name="ta-tab-label",
                id="tga-tab-processing-shell",
            ),
            dbc.Tab(
                [
                    execute_card("tga-run-status", "tga-run-btn", card_title_id="tga-execute-card-title"),
                ],
                tab_id="tga-tab-run",
                label_class_name="ta-tab-label",
                id="tga-tab-run-shell",
            ),
        ],
        id="tga-left-tabs",
        active_tab="tga-tab-setup",
        className="mb-3",
    )


layout = html.Div(
    analysis_page_stores("tga-refresh", "tga-latest-result-id")
    + [
        dcc.Store(id="tga-figure-captured", data={}),
        dcc.Store(id="tga-figure-artifact-refresh", data=0),
        dcc.Store(id="tga-processing-draft", data=copy.deepcopy(_default_tga_processing_draft())),
        dcc.Store(id="tga-processing-undo-stack", data=[]),
        dcc.Store(id="tga-processing-redo-stack", data=[]),
        dcc.Store(id="tga-history-hydrate", data=0),
        dcc.Store(id="tga-preset-refresh", data=0),
        dcc.Store(id="tga-preset-hydrate", data=0),
        dcc.Store(id="tga-preset-loaded-name", data=""),
        dcc.Store(id="tga-preset-snapshot", data=None),
        html.Div(id="tga-hero-slot"),
        dbc.Row(
            [
                dbc.Col(
                    [_tga_left_column_tabs()],
                    md=4,
                ),
                dbc.Col(
                    [
                        _tga_result_section(result_placeholder_card("tga-result-analysis-summary"), role="context"),
                        _tga_result_section(result_placeholder_card("tga-result-metrics"), role="context"),
                        _tga_result_section(result_placeholder_card("tga-result-quality"), role="support"),
                        _tga_result_section(build_figure_artifact_surface("tga"), role="hero"),
                        _tga_result_section(result_placeholder_card("tga-result-dtg"), role="support"),
                        _tga_result_section(result_placeholder_card("tga-result-step-cards"), role="support"),
                        _tga_result_section(result_placeholder_card("tga-result-table"), role="support"),
                        _tga_result_section(result_placeholder_card("tga-result-processing"), role="support"),
                        _tga_result_section(result_placeholder_card("tga-result-raw-metadata"), role="support"),
                        _tga_result_section(_literature_compare_card(), role="secondary"),
                    ],
                    md=8,
                    className="ms-results-surface",
                ),
            ]
        ),
    ],
    className="tga-page",
)


@callback(
    Output("tga-hero-slot", "children"),
    Output("tga-dataset-card-title", "children"),
    Output("tga-unit-card-title", "children"),
    Output("tga-workflow-card-title", "children"),
    Output("tga-execute-card-title", "children"),
    Output("tga-run-btn", "children"),
    Output("tga-template-select", "options"),
    Output("tga-template-select", "value"),
    Output("tga-template-description", "children"),
    Output("tga-unit-mode-select", "options"),
    Output("tga-unit-mode-select", "value"),
    Input("ui-locale", "data"),
    Input("tga-template-select", "value"),
    Input("tga-unit-mode-select", "value"),
)
def render_tga_locale_chrome(locale_data, template_id, unit_mode):
    loc = _loc(locale_data)
    hero = page_header(
        translate_ui(loc, "dash.analysis.tga.title"),
        translate_ui(loc, "dash.analysis.tga.caption"),
        badge=translate_ui(loc, "dash.analysis.badge"),
    )
    opts = [{"label": translate_ui(loc, f"dash.analysis.tga.template.{tid}.label"), "value": tid} for tid in _TGA_TEMPLATE_IDS]
    valid_t = {o["value"] for o in opts}
    tid = template_id if template_id in valid_t else "tga.general"
    desc_key = f"dash.analysis.tga.template.{tid}.desc"
    desc = translate_ui(loc, desc_key)
    if desc == desc_key:
        desc = translate_ui(loc, "dash.analysis.tga.workflow_fallback")

    unit_opts = [{"label": translate_ui(loc, f"dash.analysis.tga.unit.{m}.label"), "value": m} for m in _TGA_UNIT_MODE_IDS]
    valid_u = {o["value"] for o in unit_opts}
    uval = unit_mode if unit_mode in valid_u else "auto"

    return (
        hero,
        translate_ui(loc, "dash.analysis.dataset_selection_title"),
        translate_ui(loc, "dash.analysis.unit_mode_title"),
        translate_ui(loc, "dash.analysis.workflow_template_title"),
        translate_ui(loc, "dash.analysis.execute_title"),
        translate_ui(loc, "dash.analysis.tga.run_btn"),
        opts,
        tid,
        desc,
        unit_opts,
        uval,
    )


@callback(
    Output("tga-tab-setup-shell", "label"),
    Output("tga-tab-processing-shell", "label"),
    Output("tga-tab-run-shell", "label"),
    Input("ui-locale", "data"),
)
def render_tga_tab_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.tga.tab.setup"),
        translate_ui(loc, "dash.analysis.tga.tab.processing"),
        translate_ui(loc, "dash.analysis.tga.tab.run"),
    )


@callback(
    Output("tga-unit-mode-description", "children"),
    Input("ui-locale", "data"),
    Input("tga-unit-mode-select", "value"),
)
def update_tga_unit_mode_description(locale_data, unit_mode):
    loc = _loc(locale_data)
    mid = unit_mode or "auto"
    key = f"dash.analysis.tga.unit.{mid}.desc"
    text = translate_ui(loc, key)
    if text == key:
        text = translate_ui(loc, "dash.analysis.tga.unit.fallback")
    return text


def _tga_draft_from_control_values(
    smooth_method,
    smooth_window,
    smooth_poly,
    smooth_sigma,
    step_prominence,
    step_min_mass,
    step_half_width,
) -> dict[str, Any]:
    token = str(smooth_method or "savgol").strip().lower()
    if token not in _TGA_SMOOTH_METHODS:
        token = "savgol"
    smooth: dict[str, Any] = {"method": token}
    if token == "savgol":
        smooth["window_length"] = smooth_window
        smooth["polyorder"] = smooth_poly
    elif token == "moving_average":
        smooth["window_length"] = smooth_window
    else:
        smooth["sigma"] = smooth_sigma
    step: dict[str, Any] = {
        "method": "dtg_peaks",
        "prominence": step_prominence,
        "min_mass_loss": step_min_mass,
        "search_half_width": step_half_width,
    }
    return _normalize_tga_processing_draft({"smoothing": smooth, "step_detection": step})


@callback(
    Output("tga-preset-card-title", "children"),
    Output("tga-preset-help", "children"),
    Output("tga-preset-select-label", "children"),
    Output("tga-preset-load-btn", "children"),
    Output("tga-preset-delete-btn", "children"),
    Output("tga-preset-save-name-label", "children"),
    Output("tga-preset-save-name", "placeholder"),
    Output("tga-preset-save-btn", "children"),
    Output("tga-preset-saveas-btn", "children"),
    Output("tga-preset-save-hint", "children"),
    Input("ui-locale", "data"),
)
def render_tga_preset_chrome(locale_data):
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
    Output("tga-smoothing-card-title", "children"),
    Output("tga-smoothing-card-hint", "children"),
    Output("tga-step-card-title", "children"),
    Output("tga-step-card-hint", "children"),
    Output("tga-smooth-method-label", "children"),
    Output("tga-smooth-window-label", "children"),
    Output("tga-smooth-polyorder-label", "children"),
    Output("tga-smooth-sigma-label", "children"),
    Output("tga-step-prominence-label", "children"),
    Output("tga-step-prominence", "placeholder"),
    Output("tga-step-min-mass-label", "children"),
    Output("tga-step-half-width-label", "children"),
    Output("tga-smooth-method", "options"),
    Input("ui-locale", "data"),
)
def render_tga_processing_chrome(locale_data):
    loc = _loc(locale_data)
    smooth_opts = [
        {"label": translate_ui(loc, "dash.analysis.tga.processing.smooth.savgol"), "value": "savgol"},
        {"label": translate_ui(loc, "dash.analysis.tga.processing.smooth.moving_average"), "value": "moving_average"},
        {"label": translate_ui(loc, "dash.analysis.tga.processing.smooth.gaussian"), "value": "gaussian"},
    ]
    return (
        translate_ui(loc, "dash.analysis.tga.processing.smoothing_card_title"),
        translate_ui(loc, "dash.analysis.tga.processing.smoothing_card_hint"),
        translate_ui(loc, "dash.analysis.tga.processing.step_card_title"),
        translate_ui(loc, "dash.analysis.tga.processing.step_card_hint"),
        translate_ui(loc, "dash.analysis.tga.processing.smooth.method"),
        translate_ui(loc, "dash.analysis.tga.processing.smooth.window"),
        translate_ui(loc, "dash.analysis.tga.processing.smooth.polyorder"),
        translate_ui(loc, "dash.analysis.tga.processing.smooth.sigma"),
        translate_ui(loc, "dash.analysis.tga.processing.step.prominence"),
        translate_ui(loc, "dash.analysis.tga.processing.step.prominence_ph"),
        translate_ui(loc, "dash.analysis.tga.processing.step.min_mass"),
        translate_ui(loc, "dash.analysis.tga.processing.step.half_width"),
        smooth_opts,
    )


@callback(
    Output("tga-preset-select", "options"),
    Output("tga-preset-caption", "children"),
    Input("tga-preset-refresh", "data"),
    Input("ui-locale", "data"),
)
def refresh_tga_preset_options(_refresh_token, locale_data):
    from dash_app import api_client

    loc = _loc(locale_data)
    try:
        payload = api_client.list_analysis_presets(_TGA_PRESET_ANALYSIS_TYPE)
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
        analysis_type=payload.get("analysis_type", _TGA_PRESET_ANALYSIS_TYPE),
        count=int(payload.get("count", len(options)) or 0),
        max_count=int(payload.get("max_count", 10) or 10),
    )
    return options, caption


@callback(
    Output("tga-preset-load-btn", "disabled"),
    Output("tga-preset-delete-btn", "disabled"),
    Output("tga-preset-save-btn", "disabled"),
    Input("tga-preset-select", "value"),
)
def toggle_tga_preset_action_buttons(selected_name):
    has_selection = bool(str(selected_name or "").strip())
    return (not has_selection, not has_selection, not has_selection)


@callback(
    Output("tga-processing-draft", "data", allow_duplicate=True),
    Output("tga-template-select", "value", allow_duplicate=True),
    Output("tga-unit-mode-select", "value", allow_duplicate=True),
    Output("tga-preset-status", "children", allow_duplicate=True),
    Output("tga-preset-hydrate", "data", allow_duplicate=True),
    Output("tga-preset-loaded-name", "data", allow_duplicate=True),
    Output("tga-preset-snapshot", "data", allow_duplicate=True),
    Output("tga-left-tabs", "active_tab", allow_duplicate=True),
    Output("tga-processing-undo-stack", "data", allow_duplicate=True),
    Output("tga-processing-redo-stack", "data", allow_duplicate=True),
    Input("tga-preset-load-btn", "n_clicks"),
    State("tga-preset-select", "value"),
    State("tga-preset-hydrate", "data"),
    State("tga-processing-draft", "data"),
    State("tga-processing-undo-stack", "data"),
    State("tga-processing-redo-stack", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def apply_tga_preset(n_clicks, selected_name, hydrate_val, current_draft, undo_stack, redo_stack, locale_data):
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
            translate_ui(loc, "dash.analysis.tga.presets.select_required"),
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )
    try:
        payload = api_client.load_analysis_preset(_TGA_PRESET_ANALYSIS_TYPE, name)
    except Exception as exc:
        return (
            dash.no_update,
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
    draft, unit_mode = _tga_draft_and_unit_from_loaded_processing(processing)
    template_id_raw = str(payload.get("workflow_template_id") or "").strip()
    template_out = template_id_raw if template_id_raw in _TGA_TEMPLATE_IDS else dash.no_update
    unit_out = unit_mode if unit_mode in _TGA_UNIT_MODE_IDS else dash.no_update
    resolved_tid = template_id_raw if template_id_raw in _TGA_TEMPLATE_IDS else "tga.general"
    snap = _tga_ui_snapshot_dict(resolved_tid, unit_mode, draft)
    status = translate_ui(loc, "dash.analysis.tga.presets.loaded").format(preset=name)
    old_norm = _normalize_tga_processing_draft(current_draft)
    new_norm = _normalize_tga_processing_draft(draft)
    past2, fut2 = append_undo_after_edit(undo_stack, redo_stack, old_norm, new_norm)
    return (
        draft,
        template_out,
        unit_out,
        status,
        int(hydrate_val or 0) + 1,
        name,
        snap,
        "tga-tab-run",
        past2,
        fut2,
    )


@callback(
    Output("tga-preset-refresh", "data", allow_duplicate=True),
    Output("tga-preset-save-name", "value", allow_duplicate=True),
    Output("tga-preset-status", "children", allow_duplicate=True),
    Output("tga-preset-snapshot", "data", allow_duplicate=True),
    Output("tga-left-tabs", "active_tab", allow_duplicate=True),
    Input("tga-preset-save-btn", "n_clicks"),
    Input("tga-preset-saveas-btn", "n_clicks"),
    State("tga-preset-select", "value"),
    State("tga-preset-save-name", "value"),
    State("tga-processing-draft", "data"),
    State("tga-template-select", "value"),
    State("tga-unit-mode-select", "value"),
    State("tga-preset-refresh", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def save_tga_preset(n_save, n_saveas, selected_name, save_name, draft, template_id, unit_mode, refresh_token, locale_data):
    from dash_app import api_client

    loc = _loc(locale_data)
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    trig = ctx.triggered_id
    if trig == "tga-preset-save-btn":
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
    elif trig == "tga-preset-saveas-btn":
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

    processing_body = _tga_preset_processing_body_for_save(draft, unit_mode)
    try:
        response = api_client.save_analysis_preset(
            _TGA_PRESET_ANALYSIS_TYPE,
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
    snap = _tga_ui_snapshot_dict(str(template_id or "").strip() or None, unit_mode, draft)
    status = translate_ui(loc, "dash.analysis.tga.presets.saved").format(preset=name, template=resolved_template)
    return int(refresh_token or 0) + 1, clear_name, status, snap, "tga-tab-run"


@callback(
    Output("tga-preset-refresh", "data", allow_duplicate=True),
    Output("tga-preset-select", "value", allow_duplicate=True),
    Output("tga-preset-status", "children", allow_duplicate=True),
    Output("tga-preset-loaded-name", "data", allow_duplicate=True),
    Output("tga-preset-snapshot", "data", allow_duplicate=True),
    Input("tga-preset-delete-btn", "n_clicks"),
    State("tga-preset-select", "value"),
    State("tga-preset-loaded-name", "data"),
    State("tga-preset-refresh", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def delete_tga_preset(n_clicks, selected_name, loaded_name, refresh_token, locale_data):
    from dash_app import api_client

    loc = _loc(locale_data)
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    name = str(selected_name or "").strip()
    if not name:
        return dash.no_update, dash.no_update, translate_ui(loc, "dash.analysis.tga.presets.select_required"), dash.no_update, dash.no_update
    try:
        api_client.delete_analysis_preset(_TGA_PRESET_ANALYSIS_TYPE, name)
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
    Output("tga-smooth-method", "value"),
    Output("tga-smooth-window", "value"),
    Output("tga-smooth-polyorder", "value"),
    Output("tga-smooth-sigma", "value"),
    Output("tga-step-prominence", "value"),
    Output("tga-step-min-mass", "value"),
    Output("tga-step-half-width", "value"),
    Input("tga-preset-hydrate", "data"),
    Input("tga-history-hydrate", "data"),
    State("tga-processing-draft", "data"),
)
def hydrate_tga_processing_controls(_preset_hydrate, _history_hydrate, draft):
    d = _normalize_tga_processing_draft(draft)
    sm = d["smoothing"]
    st = d["step_detection"]
    method = str(sm.get("method") or "savgol")
    wl = int(sm.get("window_length", 11))
    po = int(sm.get("polyorder", 3))
    sigma = float(sm.get("sigma", 2.0))
    prom = st.get("prominence")
    prom_s = "" if prom in (None, "") else str(prom)
    min_ml = float(st.get("min_mass_loss", 0.5))
    half = int(st.get("search_half_width", 80))
    return method, wl, po, sigma, prom_s, min_ml, half


@callback(
    Output("tga-processing-draft", "data", allow_duplicate=True),
    Output("tga-processing-undo-stack", "data", allow_duplicate=True),
    Output("tga-processing-redo-stack", "data", allow_duplicate=True),
    Input("tga-smooth-method", "value"),
    Input("tga-smooth-window", "value"),
    Input("tga-smooth-polyorder", "value"),
    Input("tga-smooth-sigma", "value"),
    Input("tga-step-prominence", "value"),
    Input("tga-step-min-mass", "value"),
    Input("tga-step-half-width", "value"),
    State("tga-processing-draft", "data"),
    State("tga-processing-undo-stack", "data"),
    State("tga-processing-redo-stack", "data"),
    prevent_initial_call="initial_duplicate",
)
def sync_tga_processing_draft_from_controls(sm_m, sm_w, sm_p, sm_s, st_pr, st_min, st_half, prev_draft, undo_stack, redo_stack):
    new_draft = _tga_draft_from_control_values(sm_m, sm_w, sm_p, sm_s, st_pr, st_min, st_half)
    old_norm = _normalize_tga_processing_draft(prev_draft)
    new_norm = _normalize_tga_processing_draft(new_draft)
    past2, fut2 = append_undo_after_edit(undo_stack, redo_stack, old_norm, new_norm)
    return new_norm, past2, fut2


@callback(
    Output("tga-processing-draft", "data", allow_duplicate=True),
    Output("tga-processing-undo-stack", "data", allow_duplicate=True),
    Output("tga-processing-redo-stack", "data", allow_duplicate=True),
    Output("tga-history-hydrate", "data", allow_duplicate=True),
    Output("tga-history-status", "children", allow_duplicate=True),
    Input("tga-processing-undo-btn", "n_clicks"),
    Input("tga-processing-redo-btn", "n_clicks"),
    Input("tga-processing-reset-btn", "n_clicks"),
    State("tga-processing-draft", "data"),
    State("tga-processing-undo-stack", "data"),
    State("tga-processing-redo-stack", "data"),
    State("tga-history-hydrate", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def tga_processing_history_actions(n_undo, n_redo, n_reset, draft, undo_stack, redo_stack, hist_hydrate, locale_data):
    loc = _loc(locale_data)
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    trig = ctx.triggered_id
    cur = _normalize_tga_processing_draft(draft)
    past = undo_stack or []
    fut = redo_stack or []
    h = int(hist_hydrate or 0)

    if trig == "tga-processing-undo-btn":
        if not n_undo:
            raise dash.exceptions.PreventUpdate
        res = perform_undo(past, fut, cur)
        if res is None:
            raise dash.exceptions.PreventUpdate
        prev, pl, fl = res
        return prev, pl, fl, h + 1, translate_ui(loc, "dash.analysis.tga.processing.history_status_undo")

    if trig == "tga-processing-redo-btn":
        if not n_redo:
            raise dash.exceptions.PreventUpdate
        res = perform_redo(past, fut, cur)
        if res is None:
            raise dash.exceptions.PreventUpdate
        nxt, pl, fl = res
        return nxt, pl, fl, h + 1, translate_ui(loc, "dash.analysis.tga.processing.history_status_redo")

    if trig == "tga-processing-reset-btn":
        if not n_reset:
            raise dash.exceptions.PreventUpdate
        default_draft = _normalize_tga_processing_draft(copy.deepcopy(_default_tga_processing_draft()))
        if tga_draft_processing_equal(cur, default_draft):
            raise dash.exceptions.PreventUpdate
        past_list = [copy.deepcopy(x) for x in past if isinstance(x, dict)]
        past_list.append(copy.deepcopy(cur))
        if len(past_list) > MAX_TGA_UNDO_DEPTH:
            past_list = past_list[-MAX_TGA_UNDO_DEPTH:]
        return default_draft, past_list, [], h + 1, translate_ui(loc, "dash.analysis.tga.processing.history_status_reset")

    raise dash.exceptions.PreventUpdate


@callback(
    Output("tga-processing-undo-btn", "disabled"),
    Output("tga-processing-redo-btn", "disabled"),
    Input("tga-processing-undo-stack", "data"),
    Input("tga-processing-redo-stack", "data"),
)
def toggle_tga_processing_history_buttons(undo_stack, redo_stack):
    u = undo_stack or []
    r = redo_stack or []
    return len(u) == 0, len(r) == 0


@callback(
    Output("tga-workflow-guide-title", "children"),
    Output("tga-workflow-guide-body", "children"),
    Input("ui-locale", "data"),
)
def render_tga_workflow_guide_chrome(locale_data):
    loc = _loc(locale_data)
    pfx = "dash.analysis.tga.workflow_guide"
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


@callback(
    Output("tga-raw-quality-card-title", "children"),
    Output("tga-raw-quality-card-hint", "children"),
    Input("ui-locale", "data"),
)
def render_tga_raw_quality_chrome(locale_data):
    loc = _loc(locale_data)
    return translate_ui(loc, "dash.analysis.tga.raw_quality.card_title"), translate_ui(loc, "dash.analysis.tga.raw_quality.card_hint")


@callback(
    Output("tga-processing-history-title", "children"),
    Output("tga-processing-history-hint", "children"),
    Input("ui-locale", "data"),
)
def render_tga_processing_history_chrome(locale_data):
    loc = _loc(locale_data)
    return translate_ui(loc, "dash.analysis.tga.processing.history_title"), translate_ui(loc, "dash.analysis.tga.processing.history_hint")


@callback(
    Output("tga-processing-undo-btn", "children"),
    Output("tga-processing-redo-btn", "children"),
    Output("tga-processing-reset-btn", "children"),
    Input("ui-locale", "data"),
)
def render_tga_processing_history_button_labels(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.tga.processing.undo_btn"),
        translate_ui(loc, "dash.analysis.tga.processing.redo_btn"),
        translate_ui(loc, "dash.analysis.tga.processing.reset_btn"),
    )


@callback(
    Output("tga-raw-quality-panel", "children"),
    Input("project-id", "data"),
    Input("tga-dataset-select", "value"),
    Input("tga-refresh", "data"),
    Input("ui-locale", "data"),
)
def render_tga_raw_quality_panel(project_id, dataset_key, _refresh, locale_data):
    loc = _loc(locale_data)
    if not project_id or not dataset_key:
        return html.P(translate_ui(loc, "dash.analysis.tga.raw_quality.pick_dataset"), className="text-muted small mb-0")
    from dash_app.api_client import workspace_dataset_data, workspace_dataset_detail

    try:
        detail = workspace_dataset_detail(project_id, dataset_key)
        data = workspace_dataset_data(project_id, dataset_key)
    except Exception as exc:
        return html.P(translate_ui(loc, "dash.analysis.tga.raw_quality.load_failed", error=str(exc)), className="text-danger small mb-0")

    rows = data.get("rows") or []
    columns = data.get("columns") or []
    t_arr, s_arr = downsample_rows(rows, columns)
    validation = detail.get("validation") if isinstance(detail.get("validation"), dict) else {}
    stats = compute_tga_raw_exploration_stats(t_arr, s_arr, validation=validation)
    units = detail.get("units") or {}
    temp_u = str(units.get("temperature") or "°C")
    sig_u = str(units.get("signal") or "")
    return build_tga_raw_quality_panel(stats, loc, temp_unit=temp_u, signal_unit=sig_u)


@callback(
    Output("tga-smooth-window", "disabled"),
    Output("tga-smooth-polyorder", "disabled"),
    Output("tga-smooth-sigma", "disabled"),
    Input("tga-smooth-method", "value"),
)
def toggle_tga_smoothing_inputs(method):
    token = str(method or "savgol").strip().lower()
    if token == "savgol":
        return False, False, True
    if token == "moving_average":
        return False, True, True
    return True, True, False


@callback(
    Output("tga-preset-loaded-line", "children"),
    Input("tga-preset-loaded-name", "data"),
    Input("ui-locale", "data"),
)
def render_tga_preset_loaded_line(loaded_name, locale_data):
    loc = _loc(locale_data)
    name = str(loaded_name or "").strip()
    if not name:
        return ""
    return translate_ui(loc, "dash.analysis.tga.presets.loaded_line").format(preset=name)


@callback(
    Output("tga-preset-dirty-flag", "children"),
    Input("ui-locale", "data"),
    Input("tga-template-select", "value"),
    Input("tga-unit-mode-select", "value"),
    Input("tga-smooth-method", "value"),
    Input("tga-smooth-window", "value"),
    Input("tga-smooth-polyorder", "value"),
    Input("tga-smooth-sigma", "value"),
    Input("tga-step-prominence", "value"),
    Input("tga-step-min-mass", "value"),
    Input("tga-step-half-width", "value"),
    State("tga-preset-snapshot", "data"),
)
def render_tga_preset_dirty_flag(locale_data, template_id, unit_mode, sm_m, sm_w, sm_p, sm_s, st_pr, st_min, st_half, snapshot):
    loc = _loc(locale_data)
    if not isinstance(snapshot, dict):
        return html.Span(translate_ui(loc, "dash.analysis.tga.presets.dirty_no_baseline"), className="text-muted")
    current = _tga_ui_snapshot_dict(
        template_id,
        unit_mode,
        _tga_draft_from_control_values(sm_m, sm_w, sm_p, sm_s, st_pr, st_min, st_half),
    )
    if _tga_snapshots_equal(snapshot, current):
        return html.Span(translate_ui(loc, "dash.analysis.tga.presets.clean"), className="text-success")
    return html.Span(translate_ui(loc, "dash.analysis.tga.presets.dirty"), className="text-warning")


@callback(
    Output("tga-dataset-selector-area", "children"),
    Output("tga-run-btn", "disabled"),
    Input("project-id", "data"),
    Input("tga-refresh", "data"),
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
        selector_id="tga-dataset-select",
        empty_msg=translate_ui(loc, "dash.analysis.tga.empty_import"),
        eligible=eligible_datasets(all_datasets, _TGA_ELIGIBLE_TYPES),
        all_datasets=all_datasets,
        eligible_types=_TGA_ELIGIBLE_TYPES,
        active_dataset=payload.get("active_dataset"),
        locale_data=locale_data,
    )


@callback(
    Output("tga-run-status", "children"),
    Output("tga-refresh", "data", allow_duplicate=True),
    Output("tga-latest-result-id", "data", allow_duplicate=True),
    Output("workspace-refresh", "data", allow_duplicate=True),
    Input("tga-run-btn", "n_clicks"),
    State("project-id", "data"),
    State("tga-dataset-select", "value"),
    State("tga-template-select", "value"),
    State("tga-unit-mode-select", "value"),
    State("tga-processing-draft", "data"),
    State("tga-refresh", "data"),
    State("workspace-refresh", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def run_tga_analysis(n_clicks, project_id, dataset_key, template_id, unit_mode, processing_draft, refresh_val, global_refresh, locale_data):
    loc = _loc(locale_data)
    if not n_clicks or not project_id or not dataset_key:
        raise dash.exceptions.PreventUpdate

    from dash_app.api_client import analysis_run

    overrides = _tga_overrides_from_draft(processing_draft)
    try:
        result = analysis_run(
            project_id=project_id,
            dataset_key=dataset_key,
            analysis_type="TGA",
            workflow_template_id=template_id,
            unit_mode=unit_mode if unit_mode and unit_mode != "auto" else None,
            processing_overrides=overrides or None,
        )
    except Exception as exc:
        return dbc.Alert(translate_ui(loc, "dash.analysis.analysis_failed", error=str(exc)), color="danger"), dash.no_update, dash.no_update, dash.no_update

    alert, saved, result_id = interpret_run_result(result, locale_data=locale_data)
    refresh = (refresh_val or 0) + 1
    if saved:
        return alert, refresh, result_id, (global_refresh or 0) + 1
    return alert, refresh, dash.no_update, dash.no_update


@callback(
    Output("tga-result-analysis-summary", "children"),
    Output("tga-result-metrics", "children"),
    Output("tga-result-quality", "children"),
    Output("tga-result-figure", "children"),
    Output("tga-result-dtg", "children"),
    Output("tga-result-step-cards", "children"),
    Output("tga-result-table", "children"),
    Output("tga-result-processing", "children"),
    Output("tga-result-raw-metadata", "children"),
    Input("tga-latest-result-id", "data"),
    Input("tga-refresh", "data"),
    Input("ui-theme", "data"),
    Input("ui-locale", "data"),
    State("project-id", "data"),
)
def display_result(result_id, _refresh, ui_theme, locale_data, project_id):
    loc = _loc(locale_data)
    empty_msg = empty_result_msg(locale_data=locale_data)
    summary_empty = html.P(translate_ui(loc, "dash.analysis.tga.summary.empty"), className="text-muted")
    quality_empty = _tga_collapsible_section(
        loc,
        "dash.analysis.tga.quality.card_title",
        html.P(translate_ui(loc, "dash.analysis.tga.quality.empty"), className="text-muted mb-0"),
        open=False,
    )
    raw_meta_empty = _tga_collapsible_section(
        loc,
        "dash.analysis.tga.raw_metadata.card_title",
        html.P(translate_ui(loc, "dash.analysis.tga.raw_metadata.empty"), className="text-muted mb-0"),
        open=False,
    )
    if not result_id or not project_id:
        return (
            summary_empty,
            empty_msg,
            quality_empty,
            empty_msg,
            html.Div(),
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
        return summary_empty, err, quality_empty, empty_msg, html.Div(), empty_msg, empty_msg, empty_msg, raw_meta_empty

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

    analysis_summary = _build_tga_analysis_summary(
        dataset_detail,
        summary,
        result_meta,
        processing,
        loc,
        locale_data=locale_data,
    )
    quality_panel = _build_tga_quality_card(detail, result_meta, loc)
    raw_metadata_panel = _build_tga_raw_metadata_panel((dataset_detail or {}).get("metadata"), loc)

    step_count = summary.get("step_count", 0)
    total_mass_loss = summary.get("total_mass_loss_percent")
    residue = summary.get("residue_percent")
    na = translate_ui(loc, "dash.analysis.na")

    total_loss_str = f"{total_mass_loss:.2f} %" if total_mass_loss is not None else na
    residue_str = f"{residue:.1f} %" if residue is not None else na
    unit_metric = _tga_resolved_unit_label(processing, loc)
    validation_metric = _tga_validation_metric_value(detail, result_meta, loc)

    metrics = metrics_row(
        [
            ("dash.analysis.metric.steps", str(step_count)),
            ("dash.analysis.metric.total_mass_loss", total_loss_str),
            ("dash.analysis.metric.residue", residue_str),
            ("dash.analysis.metric.tga_unit_mode", unit_metric),
            ("dash.analysis.metric.validation_status", validation_metric),
        ],
        locale_data=locale_data,
    )

    step_cards = _build_step_cards(rows, loc)

    figure_area = empty_msg
    dtg_area = html.Div()
    if dataset_key:
        figure_area = _build_figure(project_id, dataset_key, summary, rows, ui_theme, loc)
        dtg_area = _build_tga_dtg_panel(project_id, dataset_key, ui_theme, loc, locale_data=locale_data)

    table_area = _build_step_table(rows, loc)

    proc_view = processing_details_section(
        processing,
        extra_lines=[
            html.P(translate_ui(loc, "dash.analysis.tga.step_detection", detail=processing.get("analysis_steps", {}).get("step_detection", {}))),
        ],
        locale_data=locale_data,
    )

    return (
        analysis_summary,
        metrics,
        quality_panel,
        figure_area,
        dtg_area,
        step_cards,
        table_area,
        proc_view,
        raw_metadata_panel,
    )


@callback(
    Output("tga-literature-card-title", "children"),
    Output("tga-literature-hint", "children"),
    Output("tga-literature-max-claims-label", "children"),
    Output("tga-literature-persist-label", "children"),
    Output("tga-literature-compare-btn", "children"),
    Input("ui-locale", "data"),
    Input("tga-latest-result-id", "data"),
)
def render_tga_literature_chrome(locale_data, result_id):
    loc = _loc(locale_data)
    if result_id:
        hint = literature_t(
            loc,
            f"{_TGA_LITERATURE_PREFIX}.ready",
            "Compare the saved TGA result to literature sources.",
        )
    else:
        hint = literature_t(
            loc,
            f"{_TGA_LITERATURE_PREFIX}.empty",
            "Run a TGA analysis first to enable literature comparison.",
        )
    return (
        literature_t(loc, f"{_TGA_LITERATURE_PREFIX}.title", "Literature Compare"),
        hint,
        literature_t(loc, f"{_TGA_LITERATURE_PREFIX}.max_claims", "Max Claims"),
        literature_t(loc, f"{_TGA_LITERATURE_PREFIX}.persist", "Persist to project"),
        literature_t(loc, f"{_TGA_LITERATURE_PREFIX}.compare_btn", "Compare"),
    )


@callback(
    Output("tga-literature-compare-btn", "disabled"),
    Input("tga-latest-result-id", "data"),
)
def toggle_tga_literature_compare_button(result_id):
    return not bool(result_id)


@callback(
    Output("tga-literature-output", "children"),
    Output("tga-literature-status", "children"),
    Input("tga-literature-compare-btn", "n_clicks"),
    State("project-id", "data"),
    State("tga-latest-result-id", "data"),
    State("tga-literature-max-claims", "value"),
    State("tga-literature-persist", "value"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def compare_tga_literature(n_clicks, project_id, result_id, max_claims, persist_values, locale_data):
    loc = _loc(locale_data)
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    if not project_id or not result_id:
        msg = literature_t(
            loc,
            f"{_TGA_LITERATURE_PREFIX}.missing_result",
            "Run a TGA analysis first.",
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
                f"{_TGA_LITERATURE_PREFIX}.error",
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
            i18n_prefix=_TGA_LITERATURE_PREFIX,
            evidence_preview_limit=LITERATURE_COMPACT_EVIDENCE_PREVIEW_LIMIT,
            alternative_preview_limit=LITERATURE_COMPACT_ALTERNATIVE_PREVIEW_LIMIT,
        ),
        literature_compare_status_alert(payload, loc, i18n_prefix=_TGA_LITERATURE_PREFIX),
    )


def _tga_fetch_figure_preview_data_urls(project_id: str, result_id: str, figure_artifacts: dict) -> dict[str, str]:
    from dash_app.api_client import fetch_result_figure_png

    out: dict[str, str] = {}
    for label in ordered_figure_preview_keys(figure_artifacts)[:FIGURE_ARTIFACT_PREVIEW_TILES]:
        try:
            raw = fetch_result_figure_png(project_id, result_id, label, max_edge=FIGURE_ARTIFACT_PREVIEW_MAX_EDGE)
            out[label] = "data:image/png;base64," + base64.standard_b64encode(bytes(raw)).decode("ascii") if raw else ""
        except Exception:
            out[label] = ""
    return out


@callback(
    Output("tga-figure-save-snapshot-btn", "children"),
    Output("tga-figure-use-report-btn", "children"),
    Output("tga-figure-artifacts-summary", "children"),
    Input("ui-locale", "data"),
)
def render_tga_figure_artifact_button_labels(locale_data):
    return figure_artifact_button_labels(_loc(locale_data))


@callback(
    Output("tga-figure-save-snapshot-btn", "disabled"),
    Output("tga-figure-use-report-btn", "disabled"),
    Input("tga-latest-result-id", "data"),
)
def toggle_tga_figure_artifact_buttons(result_id):
    disabled = not bool(result_id)
    return disabled, disabled


@callback(
    Output("tga-result-figure-artifacts", "children"),
    Input("tga-latest-result-id", "data"),
    Input("tga-figure-artifact-refresh", "data"),
    Input("ui-locale", "data"),
    State("project-id", "data"),
)
def refresh_tga_figure_artifacts_panel(result_id, _artifact_refresh, locale_data, project_id):
    loc = _loc(locale_data)
    if not result_id or not project_id:
        return ""
    from dash_app.api_client import workspace_result_detail

    try:
        detail = workspace_result_detail(project_id, result_id)
    except Exception:
        return ""
    artifacts = detail.get("figure_artifacts") if isinstance(detail.get("figure_artifacts"), dict) else {}
    previews = _tga_fetch_figure_preview_data_urls(project_id, result_id, artifacts) if ordered_figure_preview_keys(artifacts) else None
    return build_figure_artifacts_panel(artifacts, loc, previews=previews)


@callback(
    Output("tga-figure-artifact-status", "children"),
    Output("tga-figure-artifact-refresh", "data"),
    Input("tga-figure-save-snapshot-btn", "n_clicks"),
    Input("tga-figure-use-report-btn", "n_clicks"),
    Input("tga-latest-result-id", "data"),
    State("project-id", "data"),
    State("tga-result-figure", "children"),
    State("ui-locale", "data"),
    State("tga-figure-artifact-refresh", "data"),
    prevent_initial_call=True,
)
def tga_figure_snapshot_or_report_figure(_snap_clicks, _report_clicks, latest_result_id, project_id, figure_children, locale_data, refresh_value):
    loc = _loc(locale_data)
    triggered_id = getattr(dash.callback_context, "triggered_id", None)
    if triggered_id == "tga-latest-result-id":
        return "", dash.no_update
    action = figure_action_from_trigger(
        triggered_id,
        snapshot_button_id="tga-figure-save-snapshot-btn",
        report_button_id="tga-figure-use-report-btn",
    )
    if action is None:
        raise dash.exceptions.PreventUpdate
    if not project_id or not latest_result_id:
        return (
            figure_action_status_alert(loc, action=action, status="missing", reason="missing_project_or_result", class_prefix="tga"),
            dash.no_update,
        )

    from dash_app.api_client import workspace_result_detail

    try:
        detail = workspace_result_detail(project_id, latest_result_id)
    except Exception as exc:
        return (
            figure_action_status_alert(loc, action=action, status="error", reason=str(exc), class_prefix="tga"),
            dash.no_update,
        )
    result_meta = detail.get("result", {}) or {}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    meta = figure_action_metadata(
        action,
        analysis_type="TGA",
        dataset_key=result_meta.get("dataset_key"),
        result_id=latest_result_id,
        snapshot_stamp=stamp,
    )
    outcome = register_result_figure_from_layout_children(
        figure_children=figure_children,
        project_id=project_id,
        result_id=latest_result_id,
        label=str(meta.get("label") or ""),
        replace=bool(meta.get("replace")),
    )
    if outcome.get("status") == "ok":
        key = str(outcome.get("figure_key") or meta.get("label") or "")
        return (
            figure_action_status_alert(loc, action=action, status="ok", figure_key=key, class_prefix="tga"),
            (refresh_value or 0) + 1,
        )
    if outcome.get("status") == "error":
        return (
            figure_action_status_alert(loc, action=action, status="error", reason=str(outcome.get("reason") or ""), class_prefix="tga"),
            dash.no_update,
        )
    return (
        figure_action_status_alert(loc, action=action, status="skipped", reason=str(outcome.get("reason") or ""), class_prefix="tga"),
        dash.no_update,
    )


@callback(
    Output("tga-figure-captured", "data"),
    Input("tga-latest-result-id", "data"),
    Input("project-id", "data"),
    Input("tga-result-figure", "children"),
    State("tga-figure-captured", "data"),
    prevent_initial_call=True,
)
def capture_tga_figure(result_id, project_id, figure_children, captured):
    return capture_result_figure_from_layout(
        result_id=result_id,
        project_id=project_id,
        figure_children=figure_children,
        captured=captured,
        analysis_type="TGA",
    )


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


def _tga_step_significance_key(row: dict) -> tuple[float, float]:
    """Sort key: larger mass loss magnitude first, then lower midpoint temperature."""
    m = row.get("mass_loss_percent")
    try:
        mag = abs(float(m)) if m is not None else 0.0
    except (TypeError, ValueError):
        mag = 0.0
    mid = row.get("midpoint_temperature")
    try:
        midv = float(mid) if mid is not None else float("nan")
    except (TypeError, ValueError):
        midv = float("nan")
    if not math.isfinite(midv):
        midv = float("inf")
    return (-mag, midv)


def _tga_steps_ranked_for_display(rows: list) -> list[dict]:
    dict_rows = [r for r in rows if isinstance(r, dict)]
    return sorted(dict_rows, key=_tga_step_significance_key)


def _tga_curated_step_rows_for_ui(rows: list) -> tuple[list[dict], int, bool]:
    """Same ranking and cap as key-step cards; use for figure midpoint markers."""
    ranked = _tga_steps_ranked_for_display(rows)
    total = len(ranked)
    truncated = total >= _TGA_TRUNCATE_STEP_CARDS_WHEN
    shown = ranked[:_TGA_MAX_STEP_CARDS] if truncated else ranked
    return shown, total, truncated


def _tga_resolved_unit_label(processing: dict, loc: str) -> str:
    method_context = (processing or {}).get("method_context") or {}
    return (
        _format_dataset_metadata_value(method_context.get("tga_unit_mode_resolved_label"))
        or _format_dataset_metadata_value(method_context.get("tga_unit_mode_label"))
        or translate_ui(loc, "dash.analysis.na")
    )


def _tga_validation_metric_value(detail: dict, result_meta: dict, loc: str) -> str:
    validation = detail.get("validation") if isinstance(detail.get("validation"), dict) else {}
    status = str(validation.get("status") or result_meta.get("validation_status") or "unknown")
    warnings_list = validation.get("warnings") if isinstance(validation.get("warnings"), list) else []
    issues_list = validation.get("issues") if isinstance(validation.get("issues"), list) else []
    wc = int(validation.get("warning_count", len(warnings_list)) or 0)
    ic = int(validation.get("issue_count", len(issues_list)) or 0)
    status_token = status.strip().lower()
    if status_token in {"ok", "pass", "valid"} and wc == 0 and ic == 0:
        return translate_ui(loc, "dash.analysis.tga.metric.validation_ok")
    parts: list[str] = [status]
    if wc:
        parts.append(translate_ui(loc, "dash.analysis.tga.metric.validation_warnings", n=wc))
    if ic:
        parts.append(translate_ui(loc, "dash.analysis.tga.metric.validation_issues", n=ic))
    return " · ".join(parts)


def _build_tga_analysis_summary(
    dataset_detail: dict,
    summary: dict,
    result_meta: dict,
    _processing: dict,
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
        sample_mass = f"{sample_mass} {translate_ui(loc, 'dash.analysis.tga.summary.mass_unit')}"
    else:
        sample_mass = na

    heating_rate = _format_dataset_metadata_value(summary.get("heating_rate")) or _format_dataset_metadata_value(
        metadata.get("heating_rate")
    )
    if heating_rate:
        heating_rate = f"{heating_rate} {translate_ui(loc, 'dash.analysis.tga.summary.heating_rate_unit')}"
    else:
        heating_rate = na

    def _meta_value(value: str) -> html.Span:
        return html.Span(value, className="ms-meta-value", title=value)

    dl_rows: list[Any] = [
        html.Dt(translate_ui(loc, "dash.analysis.tga.summary.dataset_label"), className="col-sm-4 text-muted ms-meta-term"),
        html.Dd(_meta_value(dataset_label), className="col-sm-8 ms-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.tga.summary.sample_label"), className="col-sm-4 text-muted ms-meta-term"),
        html.Dd(_meta_value(sample_label), className="col-sm-8 ms-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.tga.summary.mass_label"), className="col-sm-4 text-muted ms-meta-term"),
        html.Dd(_meta_value(sample_mass), className="col-sm-8 ms-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.tga.summary.heating_rate_label"), className="col-sm-4 text-muted ms-meta-term"),
        html.Dd(_meta_value(heating_rate), className="col-sm-8 ms-meta-def"),
    ]
    atmosphere = _format_dataset_metadata_value(metadata.get("atmosphere"))
    if atmosphere:
        dl_rows.extend(
            [
                html.Dt(translate_ui(loc, "dash.analysis.tga.summary.atmosphere_label"), className="col-sm-4 text-muted ms-meta-term"),
                html.Dd(_meta_value(atmosphere), className="col-sm-8 ms-meta-def"),
            ]
        )
    return html.Div(
        [
            html.H5(translate_ui(loc, "dash.analysis.tga.summary.card_title"), className="mb-3"),
            html.Dl(dl_rows, className="row mb-0"),
        ]
    )


def _build_tga_quality_card(detail: dict, result_meta: dict, loc: str) -> html.Details:
    validation = detail.get("validation") if isinstance(detail.get("validation"), dict) else {}
    processing = detail.get("processing") if isinstance(detail.get("processing"), dict) else {}
    method_context = processing.get("method_context") or {}
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
                html.Strong(translate_ui(loc, "dash.analysis.tga.quality.status_label")),
                f" {status}",
            ],
            className="mb-2",
        ),
        html.P(
            [
                html.Strong(translate_ui(loc, "dash.analysis.tga.quality.warnings_label")),
                f" {wc}",
            ],
            className="mb-2",
        ),
        html.P(
            [
                html.Strong(translate_ui(loc, "dash.analysis.tga.quality.issues_label")),
                f" {ic}",
            ],
            className="mb-2",
        ),
    ]
    if warnings_list:
        body_children.append(
            html.Div(
                [
                    html.H6(translate_ui(loc, "dash.analysis.tga.quality.major_warnings_heading"), className="small mb-1"),
                    html.Ul([html.Li(str(w)) for w in warnings_list[:12]], className="small mb-0"),
                ],
                className="mb-2",
            )
        )
    if issues_list:
        body_children.append(html.Ul([html.Li(str(w)) for w in issues_list[:12]], className="small mb-0 mt-2"))

    cal_state = method_context.get("calibration_state")
    ref_state = method_context.get("reference_state")
    ref_name = method_context.get("reference_name")
    cal_text = _format_dataset_metadata_value(cal_state) or translate_ui(loc, "dash.analysis.tga.quality.context_na")
    ref_bits = [x for x in (_format_dataset_metadata_value(ref_state), _format_dataset_metadata_value(ref_name)) if x]
    ref_text = " | ".join(ref_bits) if ref_bits else translate_ui(loc, "dash.analysis.tga.quality.context_na")

    body_children.append(
        html.Div(
            [
                html.H6(translate_ui(loc, "dash.analysis.tga.quality.calibration_reference_heading"), className="small mt-2 mb-1"),
                html.P(
                    [
                        html.Strong(translate_ui(loc, "dash.analysis.tga.quality.calibration_label")),
                        f" {cal_text}",
                    ],
                    className="small mb-1",
                ),
                html.P(
                    [
                        html.Strong(translate_ui(loc, "dash.analysis.tga.quality.reference_label")),
                        f" {ref_text}",
                    ],
                    className="small mb-0",
                ),
            ],
            className="mb-2",
        )
    )

    checks = validation.get("checks")
    check_items = _tga_quality_check_entries(checks)
    if check_items:
        technical_checks = html.Ul([html.Li(item, className="small") for item in check_items], className="small mb-0 ps-3")
        body_children.append(
            html.Details(
                [
                    html.Summary(
                        [
                            html.Span(className="ta-details-chevron"),
                            html.Span(
                                translate_ui(loc, "dash.analysis.tga.quality.technical_validation_title"),
                                className="ms-1 small",
                            ),
                        ],
                        className="ta-details-summary",
                    ),
                    html.Div(technical_checks, className="ta-details-body mt-2"),
                ],
                className="ta-ms-details mb-0 mt-2",
                open=False,
            )
        )

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
    return _tga_collapsible_section(
        loc,
        "dash.analysis.tga.quality.card_title",
        inner,
        open=has_attention,
        summary_suffix=badges if badges else None,
    )


def _tga_quality_check_entries(checks: Any) -> list[str]:
    if not isinstance(checks, dict) or not checks:
        return []
    seen: set[str] = set()
    lines: list[str] = []
    for key in (*_TGA_QUALITY_CHECK_ORDER,):
        if key in checks and key not in seen:
            val = checks[key]
            if isinstance(val, (dict, list)):
                text = json.dumps(val, ensure_ascii=False)
            else:
                text = str(val)
            lines.append(f"{key}: {text}")
            seen.add(key)
    for key in sorted(checks.keys(), key=lambda k: str(k).lower()):
        if key in seen:
            continue
        val = checks[key]
        if isinstance(val, (dict, list)):
            text = json.dumps(val, ensure_ascii=False)
        else:
            text = str(val)
        lines.append(f"{key}: {text}")
        if len(lines) >= 28:
            break
    return lines


def _build_tga_raw_metadata_panel(metadata: dict | None, loc: str) -> html.Details:
    meta = metadata if isinstance(metadata, dict) else {}
    if not meta:
        inner = html.P(translate_ui(loc, "dash.analysis.tga.raw_metadata.empty"), className="text-muted mb-0")
    else:
        user_keys = sorted(
            [k for k in meta if k in _TGA_USER_FACING_METADATA_KEYS],
            key=lambda k: str(k).lower(),
        )
        tech_keys = sorted(
            [k for k in meta if k not in _TGA_USER_FACING_METADATA_KEYS],
            key=lambda k: str(k).lower(),
        )

        def _make_rows(keys: list[str]) -> list[Any]:
            rows: list[Any] = []
            for key in keys:
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
                            html.Span(
                                translate_ui(loc, "dash.analysis.tga.raw_metadata.technical_details") or "Technical details",
                                className="ms-1",
                            ),
                        ],
                        className="ta-details-summary",
                    ),
                    html.Div(html.Dl(_make_rows(tech_keys), className="row mb-0"), className="ta-details-body mt-2"),
                ],
                className="ta-ms-details mb-0",
                open=False,
            )
            body_parts.append(html.Div(tech_collapsible, className="mt-2"))

        inner = (
            html.Div(body_parts)
            if body_parts
            else html.P(translate_ui(loc, "dash.analysis.tga.raw_metadata.empty"), className="text-muted mb-0")
        )
    return _tga_collapsible_section(loc, "dash.analysis.tga.raw_metadata.card_title", inner, open=False)


def _coerce_float_pair(tx: Any, dx: Any) -> tuple[float, float] | None:
    try:
        pt = float(tx)
        pd = float(dx)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(pt) or not math.isfinite(pd):
        return None
    return pt, pd


def _build_tga_dtg_panel(
    project_id: str,
    dataset_key: str,
    ui_theme: str | None,
    loc: str,
    *,
    locale_data: str | None = None,
) -> html.Div:
    _ld = locale_data if locale_data is not None else loc
    from dash_app.api_client import analysis_state_curves

    try:
        curves = analysis_state_curves(project_id, "TGA", dataset_key)
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
        pair = _coerce_float_pair(tx, dx)
        if pair is None:
            continue
        temperature.append(pair[0])
        dtg.append(pair[1])
    if len(temperature) < 3:
        return html.Div()

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=temperature,
            y=dtg,
            mode="lines",
            name=translate_ui(_ld, "dash.analysis.tga.dtg.trace_name"),
            line=dict(color="#DC2626", width=1.8),
        )
    )
    fig.update_layout(
        title=dict(
            text=translate_ui(_ld, "dash.analysis.tga.dtg.title"),
            x=0.01,
            xanchor="left",
            font=dict(size=14),
        ),
        xaxis_title=translate_ui(_ld, "dash.analysis.figure.axis_temperature_c"),
        yaxis_title=translate_ui(_ld, "dash.analysis.figure.axis_dtg"),
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
        className="ta-plot tga-derivative-graph",
    )
    return html.Div(
        [
            html.H6(translate_ui(_ld, "dash.analysis.tga.dtg.card_title"), className="mb-2"),
            html.P(translate_ui(_ld, "dash.analysis.tga.dtg.caption"), className="small text-muted mb-2"),
            graph,
        ],
        className="tga-derivative-helper",
    )


def _build_step_cards(rows: list, loc: str) -> html.Div:
    if not rows:
        return html.Div(
            [
                html.H5(translate_ui(loc, "dash.analysis.section.tga_key_steps"), className="mb-3"),
                html.P(translate_ui(loc, "dash.analysis.state.no_steps"), className="text-muted"),
            ]
        )

    display_rows, total, truncated = _tga_curated_step_rows_for_ui(rows)

    cards: list[Any] = [html.H5(translate_ui(loc, "dash.analysis.section.tga_key_steps"), className="mb-3")]
    for idx, row in enumerate(display_rows):
        cards.append(_step_card(row, idx, loc))
    if truncated:
        cards.append(
            html.P(
                translate_ui(loc, "dash.analysis.tga.steps.truncation_note", shown=len(display_rows), total=total),
                className="small text-muted mb-1",
            )
        )
        cards.append(
            html.P(
                translate_ui(loc, "dash.analysis.tga.steps.table_authority_note"),
                className="small text-muted mb-0 fst-italic",
            )
        )
    return html.Div(cards)


def _build_figure(project_id: str, dataset_key: str, summary: dict, step_rows: list, ui_theme: str | None, loc: str) -> html.Div:
    from dash_app.api_client import analysis_state_curves

    try:
        curves = analysis_state_curves(project_id, "TGA", dataset_key)
    except Exception:
        curves = {}

    temperature = curves.get("temperature", [])
    raw_signal = curves.get("raw_signal", [])
    smoothed = curves.get("smoothed", [])
    has_smoothed = curves.get("has_smoothed")

    if not temperature:
        return no_data_figure_msg(locale_data=loc)

    na = translate_ui(loc, "dash.analysis.na")
    sample_name = resolve_sample_name(summary, {}, fallback_display_name=dataset_key, locale_data=loc)

    fig = go.Figure()

    raw_alpha = 0.35 if has_smoothed else 1.0
    raw_width = 1.0 if has_smoothed else 1.5
    fig.add_trace(
        go.Scatter(
            x=temperature,
            y=raw_signal,
            mode="lines",
            name=translate_ui(loc, "dash.analysis.figure.legend_raw_mass"),
            line=dict(color="#94A3B8", width=raw_width),
            opacity=raw_alpha,
        )
    )

    if smoothed and len(smoothed) == len(temperature):
        fig.add_trace(
            go.Scatter(
                x=temperature,
                y=smoothed,
                mode="lines",
                name=translate_ui(loc, "dash.analysis.figure.legend_smoothed_mass"),
                line=dict(color="#0E7490", width=1.5),
            )
        )

    # Midpoint markers only on the main mass axis; DTG is shown in the dedicated card below.
    # Use the same curated ranked subset as key-step cards so markers match the UI.
    n_steps = len(step_rows)
    marker_rows, _, _ = _tga_curated_step_rows_for_ui(step_rows)

    _ANNOTATION_MIN_SEP = 18.0 if n_steps > _TGA_MAX_STEP_CARDS else 15.0
    annotated_temps: list[float] = []

    for row in marker_rows:
        midpoint = row.get("midpoint_temperature")
        if midpoint is not None and temperature:
            idx = min(range(len(temperature)), key=lambda i: abs(temperature[i] - midpoint))
            too_close = any(abs(midpoint - t) < _ANNOTATION_MIN_SEP for t in annotated_temps)
            text_str = f"{midpoint:.1f}" if not too_close else ""
            y_at = raw_signal[idx] if idx < len(raw_signal or []) else None
            if y_at is None and smoothed and idx < len(smoothed):
                y_at = smoothed[idx]
            if y_at is not None:
                fig.add_trace(
                    go.Scatter(
                        x=[temperature[idx]],
                        y=[y_at],
                        mode="markers+text",
                        marker=dict(size=9, color="#059669", symbol="diamond"),
                        text=[text_str],
                        textposition="bottom center",
                        textfont=dict(size=9, color="#059669"),
                        name=translate_ui(loc, "dash.analysis.figure.step_mid", v=f"{midpoint:.1f}"),
                        showlegend=False,
                    )
                )
            if text_str:
                annotated_temps.append(midpoint)

    # Keep vertical guides readable: full onset/endset lines only for small step counts.
    show_step_vlines = n_steps <= 4
    annotate_onset_endset = n_steps <= 4

    if show_step_vlines:
        for row in step_rows:
            onset = row.get("onset_temperature")
            endset = row.get("endset_temperature")
            if onset is not None:
                ann_text = translate_ui(loc, "dash.analysis.figure.annot_on", v=f"{onset:.1f}") if annotate_onset_endset else ""
                fig.add_vline(
                    x=onset,
                    line=dict(color="#F59E0B", width=1, dash="dot"),
                    annotation_text=ann_text or None,
                    annotation_position="top left",
                )
            if endset is not None:
                ann_text = translate_ui(loc, "dash.analysis.figure.annot_end", v=f"{endset:.1f}") if annotate_onset_endset else ""
                fig.add_vline(
                    x=endset,
                    line=dict(color="#F59E0B", width=1, dash="dot"),
                    annotation_text=ann_text or None,
                    annotation_position="top left",
                )

    fig.update_layout(
        title=translate_ui(loc, "dash.analysis.figure.title_tga", name=sample_name),
        xaxis_title=translate_ui(loc, "dash.analysis.figure.axis_temperature_c"),
        yaxis_title=translate_ui(loc, "dash.analysis.figure.axis_mass_pct"),
        margin=dict(l=56, r=24, t=56, b=48),
        height=480,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    apply_figure_theme(fig, ui_theme)
    ink = PLOT_THEME[normalize_ui_theme(ui_theme)]["text"]
    fig.update_layout(
        yaxis=dict(title=dict(text=translate_ui(loc, "dash.analysis.figure.axis_mass_pct"), font=dict(color=ink)), tickfont=dict(color=ink))
    )

    step_count_disp = summary.get("step_count", n_steps)
    total_mass_loss = summary.get("total_mass_loss_percent")
    residue_pct = summary.get("residue_percent")
    loss_str = f"{total_mass_loss:.2f} %" if total_mass_loss is not None else na
    res_str = f"{residue_pct:.1f} %" if residue_pct is not None else na
    run_caption = translate_ui(
        loc,
        "dash.analysis.tga.figure.run_summary",
        steps=str(step_count_disp),
        loss=loss_str,
        residue=res_str,
    )

    return html.Div(
        [
            html.H5(translate_ui(loc, "dash.analysis.tga.figure.section_title"), className="mb-2"),
            html.P(run_caption, className="small text-muted mb-2"),
            dcc.Graph(
                figure=prepare_result_graph_figure(fig),
                config=result_graph_config({"displaylogo": False}),
                className=result_graph_class(),
                style=RESULT_GRAPH_STYLE,
            ),
        ]
    )


def _build_step_table(rows: list, loc: str) -> html.Div:
    if not rows:
        return html.Div(
            [
                html.H5(translate_ui(loc, "dash.analysis.section.step_table"), className="mb-3"),
                html.P(translate_ui(loc, "dash.analysis.state.no_step_data"), className="text-muted"),
            ]
        )

    columns = [
        "onset_temperature",
        "midpoint_temperature",
        "endset_temperature",
        "mass_loss_percent",
        "mass_loss_mg",
        "residual_percent",
    ]
    return html.Div(
        [
            html.H5(translate_ui(loc, "dash.analysis.section.step_table"), className="mb-3"),
            dataset_table(rows, columns, table_id="tga-steps-table"),
        ]
    )
