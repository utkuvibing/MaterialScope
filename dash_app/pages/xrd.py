"""XRD analysis page — mature Dash shell aligned with Raman/FTIR (Setup / Processing / Run)."""

from __future__ import annotations

import base64
import copy
import math
from datetime import datetime, timezone
from typing import Any

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html

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
    finalized_validation_warning_issue_counts,
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
    primary_report_figure_label,
)
from dash_app.components.literature_compare_ui import (
    build_literature_compare_card,
    coerce_literature_max_claims,
    literature_compare_status_alert,
    literature_t,
    render_literature_output,
)
from dash_app.components.xrd_explore import (
    MAX_XRD_UNDO_DEPTH,
    append_undo_after_edit,
    perform_redo,
    perform_undo,
    xrd_draft_processing_equal,
)
from dash_app.components.xrd_processing_draft import (
    default_xrd_draft_for_template,
    normalize_xrd_processing_draft,
    xrd_draft_from_control_values,
    xrd_draft_from_loaded_processing,
    xrd_overrides_from_draft,
    xrd_preset_processing_body_for_save,
    xrd_snapshots_equal,
    xrd_template_ids,
    xrd_ui_snapshot_dict,
)
from dash_app.components.xrd_result_plot import build_xrd_result_figure
from core.plotting import build_plotly_config
from dash_app.theme import normalize_ui_theme
from utils.i18n import normalize_ui_locale, translate_ui

dash.register_page(__name__, path="/xrd", title="XRD Analysis - MaterialScope")

_XRD_TEMPLATE_IDS = list(xrd_template_ids())
# Streamlit-era template list shape + static select options (tests / external imports).
_XRD_WORKFLOW_TEMPLATES = [{"id": tid} for tid in _XRD_TEMPLATE_IDS]
_TEMPLATE_OPTIONS = [{"label": tid, "value": tid} for tid in _XRD_TEMPLATE_IDS]
_XRD_ELIGIBLE_TYPES = {"XRD", "UNKNOWN"}
_XRD_PRESET_ANALYSIS_TYPE = "XRD"
_XRD_LITERATURE_PREFIX = "dash.analysis.xrd.literature"
MAX_XRD_FIGURE_PREVIEW_TILES = FIGURE_ARTIFACT_PREVIEW_TILES
# Long edge cap for inline data-URL previews (server GET ``max_edge``; Slice 6).
MAX_XRD_FIGURE_PREVIEW_MAX_EDGE = FIGURE_ARTIFACT_PREVIEW_MAX_EDGE

_XRD_RESULT_CARD_ROLES = {
    "context": "ms-result-context",
    "hero": "ms-result-hero",
    "support": "ms-result-support",
    "secondary": "ms-result-secondary",
}

_XRD_LEFT_PANEL_CARD = "xrd-left-panel-card mb-2"

_XRD_USER_FACING_METADATA_KEYS: frozenset[str] = frozenset({
    "sample_name",
    "display_name",
    "instrument",
    "vendor",
    "file_name",
    "source_data_hash",
})

_CONFIDENCE_COLORS = {
    "high_confidence": "#059669",
    "moderate_confidence": "#D97706",
    "low_confidence": "#DC2626",
    "no_match": "#6B7280",
}


def _loc(locale_data: str | None) -> str:
    return normalize_ui_locale(locale_data)


def _coerce_float(value) -> float | None:
    try:
        if value in (None, ""):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _confidence_band_label(loc: str, band: str) -> str:
    token = str(band or "no_match").lower().replace(" ", "_")
    key = f"dash.analysis.confidence.{token}"
    text = translate_ui(loc, key)
    if text == key:
        return str(band).replace("_", " ").title()
    return text


def _match_status_label(loc: str, raw: str | None) -> str:
    token = str(raw or "no_match").lower().replace(" ", "_")
    key = f"dash.analysis.match_status.{token}"
    text = translate_ui(loc, key)
    if text == key:
        s = str(raw or "").replace("_", " ").strip()
        return s.title() if s else translate_ui(loc, "dash.analysis.na")
    return text


def _display_candidate_name(row: dict, loc: str) -> str:
    for key in ("display_name_unicode", "display_name", "candidate_name", "phase_name", "candidate_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return translate_ui(loc, "dash.analysis.xrd.candidate_unknown")


def _xrd_result_section(child: Any, *, role: str = "support") -> html.Div:
    """Wraps one band on the right-hand results column; spacing comes from ``xrd-result-surface-block`` in CSS."""
    role_class = _XRD_RESULT_CARD_ROLES.get(role, _XRD_RESULT_CARD_ROLES["support"])
    return html.Div(child, className=f"ms-result-section xrd-result-surface-block {role_class}")


def _xrd_collapsible_section(
    loc: str,
    title_key: str,
    body: Any,
    *,
    open: bool = False,
    summary_suffix: Any | None = None,
) -> html.Details:
    return build_collapsible_section(loc, title_key, body, open=open, summary_suffix=summary_suffix)


def _match_card(row: dict, idx: int, loc: str = "en") -> dbc.Card:
    score = _coerce_float(row.get("normalized_score")) or 0.0
    confidence = str(row.get("confidence_band", "no_match")).lower()
    color = _CONFIDENCE_COLORS.get(confidence, "#6B7280")
    evidence = row.get("evidence", {})
    shared_peaks = evidence.get("shared_peak_count", "--")
    overlap_score = evidence.get("weighted_overlap_score", "--")
    mean_delta = evidence.get("mean_delta_position", "--")
    coverage_ratio = evidence.get("coverage_ratio", "--")
    provider = str(row.get("library_provider") or "--")
    formula = str(row.get("formula_unicode") or row.get("formula_pretty") or row.get("formula") or "--")
    candidate = _display_candidate_name(row, loc)

    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(
                    [
                        html.I(className="bi bi-bullseye me-1", style={"color": color, "fontSize": "0.9rem", "opacity": 0.9}),
                        html.Strong(translate_ui(loc, "dash.analysis.label.candidate_n", n=idx + 1), className="me-2 small text-body-secondary"),
                        html.Span(
                            _confidence_band_label(loc, confidence),
                            className="badge",
                            style={"backgroundColor": color, "color": "white", "fontSize": "0.65rem", "fontWeight": 500},
                        ),
                    ],
                    className="mb-1",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [html.Small(translate_ui(loc, "dash.analysis.label.phase"), className="text-muted d-block"), html.Span(candidate, className="small")],
                            md=5,
                        ),
                        dbc.Col(
                            [html.Small(translate_ui(loc, "dash.analysis.label.score"), className="text-muted d-block"), html.Span(f"{score:.3f}", className="small")],
                            md=2,
                        ),
                        dbc.Col(
                            [
                                html.Small(translate_ui(loc, "dash.analysis.label.shared_peaks"), className="text-muted d-block"),
                                html.Span(shared_peaks, className="small"),
                            ],
                            md=2,
                        ),
                        dbc.Col(
                            [html.Small(translate_ui(loc, "dash.analysis.label.provider"), className="text-muted d-block"), html.Span(provider, className="small text-break")],
                            md=3,
                        ),
                    ],
                    className="g-1",
                ),
                html.Div(
                    [
                        html.Small(translate_ui(loc, "dash.analysis.label.formula"), className="text-muted me-1"),
                        html.Span(formula, className="small font-monospace"),
                    ],
                    className="mt-1",
                ),
                html.P(
                    translate_ui(
                        loc,
                        "dash.analysis.xrd.match_detail_line",
                        overlap=overlap_score,
                        coverage=coverage_ratio,
                        delta=mean_delta,
                    ),
                    className="mb-0 text-muted small mt-1 lh-sm",
                ),
            ],
            className="py-2 px-2 xrd-candidate-card-body",
        ),
        outline=True,
        className="mb-2 shadow-none xrd-candidate-card border-secondary-subtle",
    )


def _xrd_workflow_guide_block() -> html.Details:
    return html.Details(
        [
            html.Summary(
                [html.Span(className="ta-details-chevron"), html.Span(id="xrd-workflow-guide-title", className="ms-1")],
                className="ta-details-summary",
            ),
            html.Div(id="xrd-workflow-guide-body", className="ta-details-body mt-2 small"),
        ],
        className="ta-ms-details mb-3",
        open=False,
    )


def _xrd_setup_review_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H6(id="xrd-setup-review-title", className="card-title mb-2"),
                html.P(id="xrd-setup-review-hint", className="small text-muted mb-2"),
                dbc.Checkbox(id="xrd-review-axis-ok", value=False, className="mb-2"),
                dbc.Label(id="xrd-review-wavelength-label", html_for="xrd-review-wavelength", className="mb-1"),
                dbc.Input(id="xrd-review-wavelength", type="number", step=0.0001, min=0, value=None),
                html.Div(id="xrd-setup-import-warnings", className="small mt-2"),
                html.Div(id="xrd-setup-validation", className="small mt-2"),
            ],
            className="xrd-left-panel-card-body",
        ),
        className="xrd-left-panel-card mb-3",
    )


def _xrd_processing_history_card() -> dbc.Card:
    return build_processing_history_card(
        title_id="xrd-processing-history-title",
        hint_id="xrd-processing-history-hint",
        undo_button_id="xrd-processing-undo-btn",
        redo_button_id="xrd-processing-redo-btn",
        reset_button_id="xrd-processing-reset-btn",
        status_id="xrd-history-status",
        card_class_name=_XRD_LEFT_PANEL_CARD,
        body_class_name="xrd-left-panel-card-body",
    )


def _xrd_preset_card() -> dbc.Card:
    return build_load_saveas_preset_card(
        id_prefix="xrd",
        card_class_name=_XRD_LEFT_PANEL_CARD,
        body_class_name="xrd-left-panel-card-body",
    )


def _axis_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="xrd-axis-card-title", className="card-title mb-2"),
                html.P(id="xrd-axis-card-hint", className="small text-muted mb-2"),
                dbc.Checkbox(id="xrd-axis-sort", value=True, className="mb-2"),
                dbc.Label(id="xrd-axis-dedup-label", html_for="xrd-axis-dedup", className="mb-1"),
                dbc.Select(
                    id="xrd-axis-dedup",
                    options=[
                        {"label": "first", "value": "first"},
                        {"label": "last", "value": "last"},
                        {"label": "mean", "value": "mean"},
                    ],
                    value="first",
                ),
                dbc.Row(
                    [
                        dbc.Col([dbc.Label(id="xrd-axis-min-label", html_for="xrd-axis-min", className="mb-1"), dbc.Input(id="xrd-axis-min", type="number", value=None)], md=6),
                        dbc.Col([dbc.Label(id="xrd-axis-max-label", html_for="xrd-axis-max", className="mb-1"), dbc.Input(id="xrd-axis-max", type="number", value=None)], md=6),
                    ],
                    className="g-2 mt-2",
                ),
            ],
            className="xrd-left-panel-card-body",
        ),
        className=_XRD_LEFT_PANEL_CARD,
    )


def _smooth_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="xrd-smooth-card-title", className="card-title mb-2"),
                html.P(id="xrd-smooth-card-hint", className="small text-muted mb-2"),
                dbc.Label(id="xrd-smooth-method-label", html_for="xrd-smooth-method", className="mb-1"),
                dbc.Select(
                    id="xrd-smooth-method",
                    options=[
                        {"label": "Savitzky–Golay", "value": "savgol"},
                        {"label": "Moving average", "value": "moving_average"},
                    ],
                    value="savgol",
                ),
                dbc.Row(
                    [
                        dbc.Col([dbc.Label(id="xrd-smooth-window-label", html_for="xrd-smooth-window", className="mb-1"), dbc.Input(id="xrd-smooth-window", type="number", min=3, step=2, value=11)], md=6),
                        dbc.Col([dbc.Label(id="xrd-smooth-poly-label", html_for="xrd-smooth-poly", className="mb-1"), dbc.Input(id="xrd-smooth-poly", type="number", min=1, max=7, value=3)], md=6),
                    ],
                    className="g-2 mt-2",
                ),
            ],
            className="xrd-left-panel-card-body",
        ),
        className=_XRD_LEFT_PANEL_CARD,
    )


def _baseline_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="xrd-baseline-card-title", className="card-title mb-2"),
                html.P(id="xrd-baseline-card-hint", className="small text-muted mb-2"),
                dbc.Label(id="xrd-baseline-method-label", html_for="xrd-baseline-method", className="mb-1"),
                dbc.Select(
                    id="xrd-baseline-method",
                    options=[
                        {"label": "Rolling minimum", "value": "rolling_minimum"},
                        {"label": "Linear", "value": "linear"},
                    ],
                    value="rolling_minimum",
                ),
                dbc.Row(
                    [
                        dbc.Col([dbc.Label(id="xrd-baseline-window-label", html_for="xrd-baseline-window", className="mb-1"), dbc.Input(id="xrd-baseline-window", type="number", min=3, step=2, value=31)], md=6),
                        dbc.Col([dbc.Label(id="xrd-baseline-smooth-label", html_for="xrd-baseline-smooth", className="mb-1"), dbc.Input(id="xrd-baseline-smooth", type="number", min=3, step=2, value=9)], md=6),
                    ],
                    className="g-2 mt-2",
                ),
            ],
            className="xrd-left-panel-card-body",
        ),
        className=_XRD_LEFT_PANEL_CARD,
    )


def _peak_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="xrd-peak-card-title", className="card-title mb-2"),
                html.P(id="xrd-peak-card-hint", className="small text-muted mb-2"),
                dbc.Row(
                    [
                        dbc.Col([dbc.Label(id="xrd-peak-prom-label", html_for="xrd-peak-prom", className="mb-1"), dbc.Input(id="xrd-peak-prom", type="number", min=0, step=0.01, value=0.08)], md=3),
                        dbc.Col([dbc.Label(id="xrd-peak-dist-label", html_for="xrd-peak-dist", className="mb-1"), dbc.Input(id="xrd-peak-dist", type="number", min=1, step=1, value=6)], md=3),
                        dbc.Col([dbc.Label(id="xrd-peak-width-label", html_for="xrd-peak-width", className="mb-1"), dbc.Input(id="xrd-peak-width", type="number", min=1, step=1, value=2)], md=3),
                        dbc.Col([dbc.Label(id="xrd-peak-max-label", html_for="xrd-peak-max", className="mb-1"), dbc.Input(id="xrd-peak-max", type="number", min=1, step=1, value=12)], md=3),
                    ],
                    className="g-2",
                ),
            ],
            className="xrd-left-panel-card-body",
        ),
        className=_XRD_LEFT_PANEL_CARD,
    )


def _match_card_controls() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="xrd-match-card-title", className="card-title mb-2"),
                html.P(id="xrd-match-card-hint", className="small text-muted mb-2"),
                dbc.Label(id="xrd-match-metric-label", html_for="xrd-match-metric", className="mb-1"),
                dbc.Select(
                    id="xrd-match-metric",
                    options=[{"label": "Peak overlap (weighted)", "value": "peak_overlap_weighted"}],
                    value="peak_overlap_weighted",
                ),
                dbc.Row(
                    [
                        dbc.Col([dbc.Label(id="xrd-match-tol-label", html_for="xrd-match-tol", className="mb-1"), dbc.Input(id="xrd-match-tol", type="number", min=0.01, step=0.01, value=0.28)], md=4),
                        dbc.Col([dbc.Label(id="xrd-match-topn-label", html_for="xrd-match-topn", className="mb-1"), dbc.Input(id="xrd-match-topn", type="number", min=1, step=1, value=5)], md=4),
                        dbc.Col([dbc.Label(id="xrd-match-min-label", html_for="xrd-match-min", className="mb-1"), dbc.Input(id="xrd-match-min", type="number", min=0, max=1, step=0.01, value=0.42)], md=4),
                    ],
                    className="g-2 mt-2",
                ),
                dbc.Row(
                    [
                        dbc.Col([dbc.Label(id="xrd-match-iw-label", html_for="xrd-match-iw", className="mb-1"), dbc.Input(id="xrd-match-iw", type="number", min=0, max=1, step=0.01, value=0.35)], md=6),
                        dbc.Col([dbc.Label(id="xrd-match-maj-label", html_for="xrd-match-maj", className="mb-1"), dbc.Input(id="xrd-match-maj", type="number", min=0, max=1, step=0.01, value=0.4)], md=6),
                    ],
                    className="g-2 mt-2",
                ),
            ],
            className="xrd-left-panel-card-body",
        ),
        className=_XRD_LEFT_PANEL_CARD,
    )


def _xrd_plot_settings_advanced_block() -> html.Details:
    """Plot appearance controls — collapsed by default to reduce Processing-tab noise."""
    inner = dbc.Card(
        dbc.CardBody(
            [
                html.P(id="xrd-plot-advanced-hint", className="small text-muted mb-2"),
                dbc.Row(
                    [
                        dbc.Col(dbc.Checkbox(id="xrd-plot-labels", value=True), md=6),
                        dbc.Col(dbc.Checkbox(id="xrd-plot-matched", value=False), md=6),
                    ],
                    className="g-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(dbc.Checkbox(id="xrd-plot-uobs", value=False), md=6),
                        dbc.Col(dbc.Checkbox(id="xrd-plot-uref", value=False), md=6),
                    ],
                    className="g-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(dbc.Checkbox(id="xrd-plot-conn", value=False), md=6),
                        dbc.Col(dbc.Checkbox(id="xrd-plot-mlab", value=False), md=6),
                    ],
                    className="g-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Checkbox(id="xrd-plot-intermediate", value=False, className="me-2"),
                                html.Span(id="xrd-plot-intermediate-label", className="small align-middle"),
                            ],
                            width="auto",
                            className="d-flex align-items-center",
                        ),
                    ],
                    className="g-2 mb-1",
                ),
                html.H6(id="xrd-plot-advanced-title", className="mt-2 mb-2 small text-muted text-uppercase"),
                dbc.Label(id="xrd-plot-density-label", html_for="xrd-plot-density", className="mb-1"),
                dbc.Select(
                    id="xrd-plot-density",
                    options=[
                        {"label": "smart", "value": "smart"},
                        {"label": "all", "value": "all"},
                        {"label": "selected", "value": "selected"},
                    ],
                    value="smart",
                ),
                dbc.Row(
                    [
                        dbc.Col([dbc.Label(id="xrd-plot-maxlab-label", html_for="xrd-plot-maxlab", className="mb-1"), dbc.Input(id="xrd-plot-maxlab", type="number", min=1, max=60, value=8)], md=4),
                        dbc.Col([dbc.Label(id="xrd-plot-minratio-label", html_for="xrd-plot-minratio", className="mb-1"), dbc.Input(id="xrd-plot-minratio", type="number", min=0, max=1, step=0.01, value=0.12)], md=4),
                        dbc.Col([dbc.Label(id="xrd-plot-msize-label", html_for="xrd-plot-msize", className="mb-1"), dbc.Input(id="xrd-plot-msize", type="number", min=4, max=20, value=8)], md=4),
                    ],
                    className="g-2 mt-2",
                ),
                dbc.Row(
                    [
                        dbc.Col([dbc.Label(id="xrd-plot-pospr-label", html_for="xrd-plot-pospr", className="mb-1"), dbc.Input(id="xrd-plot-pospr", type="number", min=1, max=5, value=2)], md=4),
                        dbc.Col([dbc.Label(id="xrd-plot-intpr-label", html_for="xrd-plot-intpr", className="mb-1"), dbc.Input(id="xrd-plot-intpr", type="number", min=0, max=4, value=0)], md=4),
                        dbc.Col([dbc.Label(id="xrd-plot-style-label", html_for="xrd-plot-style", className="mb-1"), dbc.Select(id="xrd-plot-style", options=[], value="color_shape")], md=4),
                    ],
                    className="g-2 mt-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(dbc.Checkbox(id="xrd-plot-xlock", value=False), md=4),
                        dbc.Col([dbc.Label(id="xrd-plot-xmin-label", html_for="xrd-plot-xmin", className="mb-1"), dbc.Input(id="xrd-plot-xmin", type="number", value=None)], md=4),
                        dbc.Col([dbc.Label(id="xrd-plot-xmax-label", html_for="xrd-plot-xmax", className="mb-1"), dbc.Input(id="xrd-plot-xmax", type="number", value=None)], md=4),
                    ],
                    className="g-2 mt-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(dbc.Checkbox(id="xrd-plot-ylock", value=False), md=4),
                        dbc.Col([dbc.Label(id="xrd-plot-ymin-label", html_for="xrd-plot-ymin", className="mb-1"), dbc.Input(id="xrd-plot-ymin", type="number", value=None)], md=4),
                        dbc.Col([dbc.Label(id="xrd-plot-ymax-label", html_for="xrd-plot-ymax", className="mb-1"), dbc.Input(id="xrd-plot-ymax", type="number", value=None)], md=4),
                    ],
                    className="g-2 mt-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(dbc.Checkbox(id="xrd-plot-logy", value=False), md=6),
                        dbc.Col([dbc.Label(id="xrd-plot-lw-label", html_for="xrd-plot-lw", className="mb-1"), dbc.Input(id="xrd-plot-lw", type="number", min=0.8, max=5, step=0.1, value=2.0)], md=6),
                    ],
                    className="g-2 mt-2",
                ),
            ],
            className="py-2 px-2 xrd-left-panel-card-body",
        ),
        className="border-0 bg-transparent shadow-none",
    )
    return html.Details(
        [
            html.Summary(
                [
                    html.Span(className="ta-details-chevron"),
                    html.Span(id="xrd-plot-advanced-summary", className="ms-1 fw-semibold"),
                ],
                className="ta-details-summary py-2",
            ),
            html.Div(inner, className="ta-details-body mt-1"),
        ],
        className="ta-ms-details mb-1",
        open=False,
    )


def _left_tabs() -> dbc.Tabs:
    return dbc.Tabs(
        [
            dbc.Tab(
                [
                    dataset_selection_card("xrd-dataset-selector-area", card_title_id="xrd-dataset-card-title"),
                    workflow_template_card(
                        "xrd-template-select",
                        "xrd-template-description",
                        [],
                        "xrd.general",
                        card_title_id="xrd-workflow-card-title",
                    ),
                    _xrd_workflow_guide_block(),
                    _xrd_setup_review_card(),
                ],
                tab_id="xrd-tab-setup",
                label_class_name="ta-tab-label",
                id="xrd-tab-setup-shell",
            ),
            dbc.Tab(
                [
                    html.Div(
                        [
                            _xrd_processing_history_card(),
                            _xrd_preset_card(),
                            _axis_card(),
                            _smooth_card(),
                            _baseline_card(),
                            _peak_card(),
                            _match_card_controls(),
                            _xrd_plot_settings_advanced_block(),
                        ],
                        className="xrd-processing-tab-pane",
                    )
                ],
                tab_id="xrd-tab-processing",
                label_class_name="ta-tab-label",
                id="xrd-tab-processing-shell",
            ),
            dbc.Tab(
                [execute_card("xrd-run-status", "xrd-run-btn", card_title_id="xrd-execute-card-title")],
                tab_id="xrd-tab-run",
                label_class_name="ta-tab-label",
                id="xrd-tab-run-shell",
            ),
        ],
        id="xrd-left-tabs",
        active_tab="xrd-tab-setup",
        className="mb-3",
    )


layout = html.Div(
    analysis_page_stores("xrd-refresh", "xrd-latest-result-id")
    + [
        dcc.Store(id="xrd-figure-captured", data={}),
        dcc.Store(id="xrd-figure-artifact-refresh", data=0),
        dcc.Store(id="xrd-processing-default", data=copy.deepcopy(default_xrd_draft_for_template("xrd.general"))),
        dcc.Store(id="xrd-processing-draft", data=copy.deepcopy(default_xrd_draft_for_template("xrd.general"))),
        dcc.Store(id="xrd-processing-undo-stack", data=[]),
        dcc.Store(id="xrd-processing-redo-stack", data=[]),
        dcc.Store(id="xrd-history-hydrate", data=0),
        dcc.Store(id="xrd-preset-refresh", data=0),
        dcc.Store(id="xrd-preset-hydrate", data=0),
        dcc.Store(id="xrd-preset-loaded-name", data=""),
        dcc.Store(id="xrd-preset-snapshot", data=None),
        dcc.Store(id="xrd-result-cache", data=None),
        html.Div(id="xrd-hero-slot"),
        dbc.Row(
            [
                dbc.Col([_left_tabs()], md=4),
                dbc.Col(
                    [
                        _xrd_result_section(result_placeholder_card("xrd-result-analysis-summary"), role="context"),
                        _xrd_result_section(html.Div(id="xrd-result-metrics", className="mb-0"), role="context"),
                        _xrd_result_section(html.Div(id="xrd-result-quality", className="mb-0"), role="support"),
                        _xrd_result_section(
                            build_figure_artifact_surface(
                                "xrd",
                                figure_host_class="ta-xrd-figure-host mb-0",
                                control_slot_id="xrd-result-figure-controls",
                            ),
                            role="hero",
                        ),
                        _xrd_result_section(html.Div(id="xrd-result-top-match", className="mb-0"), role="support"),
                        _xrd_result_section(html.Div(id="xrd-result-candidate-cards", className="mb-0"), role="support"),
                        _xrd_result_section(html.Div(id="xrd-result-table", className="mb-0"), role="support"),
                        _xrd_result_section(html.Div(id="xrd-result-processing", className="mb-0"), role="support"),
                        _xrd_result_section(html.Div(id="xrd-result-raw-metadata", className="mb-0"), role="support"),
                        _xrd_result_section(
                            build_literature_compare_card(
                                id_prefix="xrd",
                                class_name="xrd-literature-card mb-0",
                                compact_toolbar=True,
                            ),
                            role="secondary",
                        ),
                    ],
                    md=8,
                    className="ms-results-surface",
                ),
            ]
        ),
    ],
    className="xrd-page",
)

# --- Callbacks: locale / tabs / guide ---


@callback(
    Output("xrd-hero-slot", "children"),
    Output("xrd-dataset-card-title", "children"),
    Output("xrd-workflow-card-title", "children"),
    Output("xrd-execute-card-title", "children"),
    Output("xrd-run-btn", "children"),
    Output("xrd-template-select", "options"),
    Output("xrd-template-select", "value"),
    Output("xrd-template-description", "children"),
    Input("ui-locale", "data"),
    Input("xrd-template-select", "value"),
)
def render_xrd_locale_chrome(locale_data, template_id):
    loc = _loc(locale_data)
    hero = page_header(
        translate_ui(loc, "dash.analysis.xrd.title"),
        translate_ui(loc, "dash.analysis.xrd.caption"),
        badge=translate_ui(loc, "dash.analysis.badge"),
    )
    opts = [{"label": translate_ui(loc, f"dash.analysis.xrd.template.{tid}.label"), "value": tid} for tid in _XRD_TEMPLATE_IDS]
    valid = {o["value"] for o in opts}
    tid = template_id if template_id in valid else "xrd.general"
    desc_key = f"dash.analysis.xrd.template.{tid}.desc"
    desc = translate_ui(loc, desc_key)
    if desc == desc_key:
        desc = translate_ui(loc, "dash.analysis.xrd.workflow_fallback")
    return (
        hero,
        translate_ui(loc, "dash.analysis.dataset_selection_title"),
        translate_ui(loc, "dash.analysis.workflow_template_title"),
        translate_ui(loc, "dash.analysis.execute_title"),
        translate_ui(loc, "dash.analysis.xrd.run_btn"),
        opts,
        tid,
        desc,
    )


@callback(
    Output("xrd-tab-setup-shell", "label"),
    Output("xrd-tab-processing-shell", "label"),
    Output("xrd-tab-run-shell", "label"),
    Input("ui-locale", "data"),
)
def render_xrd_tab_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.xrd.tab.setup"),
        translate_ui(loc, "dash.analysis.xrd.tab.processing"),
        translate_ui(loc, "dash.analysis.xrd.tab.run"),
    )


@callback(
    Output("xrd-workflow-guide-title", "children"),
    Output("xrd-workflow-guide-body", "children"),
    Input("ui-locale", "data"),
)
def render_xrd_workflow_guide_chrome(locale_data):
    loc = _loc(locale_data)
    pfx = "dash.analysis.xrd.workflow_guide"
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


# --- Dataset + setup review ---


@callback(
    Output("xrd-dataset-selector-area", "children"),
    Output("xrd-run-btn", "disabled"),
    Input("project-id", "data"),
    Input("xrd-refresh", "data"),
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
        selector_id="xrd-dataset-select",
        empty_msg=translate_ui(loc, "dash.analysis.xrd.empty_import"),
        eligible=eligible_datasets(all_datasets, _XRD_ELIGIBLE_TYPES),
        all_datasets=all_datasets,
        eligible_types=_XRD_ELIGIBLE_TYPES,
        active_dataset=payload.get("active_dataset"),
        locale_data=locale_data,
    ), False


@callback(
    Output("xrd-setup-review-title", "children"),
    Output("xrd-setup-review-hint", "children"),
    Output("xrd-review-axis-ok", "label"),
    Output("xrd-review-wavelength-label", "children"),
    Input("ui-locale", "data"),
)
def render_xrd_setup_review_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.xrd.setup.review_title"),
        translate_ui(loc, "dash.analysis.xrd.setup.review_hint"),
        translate_ui(loc, "dash.analysis.xrd.setup.axis_confirm"),
        translate_ui(loc, "dash.analysis.xrd.setup.wavelength_label"),
    )


@callback(
    Output("xrd-review-wavelength", "value"),
    Output("xrd-review-axis-ok", "value"),
    Output("xrd-setup-import-warnings", "children"),
    Output("xrd-setup-validation", "children"),
    Input("project-id", "data"),
    Input("xrd-dataset-select", "value"),
    Input("ui-locale", "data"),
)
def hydrate_xrd_setup_from_dataset(project_id, dataset_key, locale_data):
    loc = _loc(locale_data)
    if not project_id or not dataset_key:
        return None, False, "", ""
    from dash_app.api_client import workspace_dataset_detail

    try:
        detail = workspace_dataset_detail(project_id, dataset_key)
    except Exception:
        return None, False, "", ""
    meta = detail.get("metadata") or {}
    wl = meta.get("xrd_wavelength_angstrom")
    try:
        wl_out = float(wl) if wl not in (None, "") else None
    except (TypeError, ValueError):
        wl_out = None
    axis_ok = not bool(meta.get("xrd_axis_mapping_review_required"))
    warns = meta.get("import_warnings") if isinstance(meta.get("import_warnings"), list) else []
    warn_children: list = []
    if warns:
        warn_children = [
            html.Strong(translate_ui(loc, "dash.analysis.xrd.setup.import_warnings"), className="d-block mb-1"),
            html.Ul([html.Li(str(w), className="small") for w in warns], className="mb-0 ps-3"),
        ]
    val = detail.get("validation") if isinstance(detail.get("validation"), dict) else {}
    val_children: Any = ""
    if val:
        st = str(val.get("status") or "")
        issues = val.get("issues") if isinstance(val.get("issues"), list) else []
        warns_v = val.get("warnings") if isinstance(val.get("warnings"), list) else []
        if issues or warns_v or st:
            parts = [html.Strong(translate_ui(loc, "dash.analysis.xrd.setup.validation_hint"), className="d-block mb-1")]
            parts.append(html.Span(f"{translate_ui(loc, 'dash.analysis.xrd.quality.status_label')}: {st}", className="small d-block"))
            if issues:
                parts.append(html.Ul([html.Li(str(i), className="small text-danger") for i in issues], className="mb-1 ps-3"))
            if warns_v:
                parts.append(html.Ul([html.Li(str(w), className="small text-warning") for w in warns_v], className="mb-0 ps-3"))
            val_children = html.Div(parts)
    return wl_out, axis_ok, (html.Div(warn_children) if warn_children else ""), val_children


# --- Template switching ---


@callback(
    Output("xrd-processing-default", "data"),
    Output("xrd-processing-draft", "data", allow_duplicate=True),
    Output("xrd-processing-undo-stack", "data", allow_duplicate=True),
    Output("xrd-processing-redo-stack", "data", allow_duplicate=True),
    Output("xrd-history-hydrate", "data", allow_duplicate=True),
    Input("xrd-template-select", "value"),
    State("xrd-processing-draft", "data"),
    State("xrd-processing-undo-stack", "data"),
    State("xrd-processing-redo-stack", "data"),
    State("xrd-history-hydrate", "data"),
    prevent_initial_call=True,
)
def xrd_on_template_change(template_id, draft, undo_stack, redo_stack, hist_hydrate):
    tid = template_id if template_id in _XRD_TEMPLATE_IDS else "xrd.general"
    new_default = copy.deepcopy(default_xrd_draft_for_template(tid))
    old_norm = normalize_xrd_processing_draft(draft)
    new_norm = normalize_xrd_processing_draft(new_default)
    past2, fut2 = append_undo_after_edit(undo_stack, redo_stack, old_norm, new_norm)
    return new_default, new_norm, past2, fut2, int(hist_hydrate or 0) + 1


# --- Presets (Raman pattern) ---


@callback(
    Output("xrd-preset-card-title", "children"),
    Output("xrd-preset-help", "children"),
    Output("xrd-preset-select-label", "children"),
    Output("xrd-preset-load-btn", "children"),
    Output("xrd-preset-delete-btn", "children"),
    Output("xrd-preset-save-name-label", "children"),
    Output("xrd-preset-save-name", "placeholder"),
    Output("xrd-preset-save-btn", "children"),
    Output("xrd-preset-saveas-btn", "children"),
    Output("xrd-preset-save-hint", "children"),
    Input("ui-locale", "data"),
)
def render_xrd_preset_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.xrd.presets.title"),
        translate_ui(loc, "dash.analysis.xrd.presets.help.overview"),
        translate_ui(loc, "dash.analysis.xrd.presets.select_label"),
        translate_ui(loc, "dash.analysis.xrd.presets.load_btn"),
        translate_ui(loc, "dash.analysis.xrd.presets.delete_btn"),
        translate_ui(loc, "dash.analysis.xrd.presets.save_name_label"),
        translate_ui(loc, "dash.analysis.xrd.presets.save_name_placeholder"),
        translate_ui(loc, "dash.analysis.xrd.presets.save_btn"),
        translate_ui(loc, "dash.analysis.xrd.presets.saveas_btn"),
        translate_ui(loc, "dash.analysis.xrd.presets.save_hint"),
    )


@callback(
    Output("xrd-preset-select", "options"),
    Output("xrd-preset-caption", "children"),
    Input("xrd-preset-refresh", "data"),
    Input("ui-locale", "data"),
)
def refresh_xrd_preset_options(_refresh_token, locale_data):
    from dash_app import api_client

    loc = _loc(locale_data)
    try:
        payload = api_client.list_analysis_presets(_XRD_PRESET_ANALYSIS_TYPE)
    except Exception as exc:
        message = translate_ui(loc, "dash.analysis.xrd.presets.list_failed").format(error=str(exc))
        return [], message
    presets = payload.get("presets") or []
    options = [
        {"label": item.get("preset_name", ""), "value": item.get("preset_name", "")}
        for item in presets
        if isinstance(item, dict) and item.get("preset_name")
    ]
    caption = translate_ui(loc, "dash.analysis.xrd.presets.caption").format(
        analysis_type=payload.get("analysis_type", _XRD_PRESET_ANALYSIS_TYPE),
        count=int(payload.get("count", len(options)) or 0),
        max_count=int(payload.get("max_count", 10) or 10),
    )
    return options, caption


@callback(
    Output("xrd-preset-load-btn", "disabled"),
    Output("xrd-preset-delete-btn", "disabled"),
    Output("xrd-preset-save-btn", "disabled"),
    Input("xrd-preset-select", "value"),
)
def toggle_xrd_preset_action_buttons(selected_name):
    has_selection = bool(str(selected_name or "").strip())
    return (not has_selection, not has_selection, not has_selection)


@callback(
    Output("xrd-processing-draft", "data", allow_duplicate=True),
    Output("xrd-template-select", "value", allow_duplicate=True),
    Output("xrd-preset-status", "children", allow_duplicate=True),
    Output("xrd-preset-hydrate", "data", allow_duplicate=True),
    Output("xrd-preset-loaded-name", "data", allow_duplicate=True),
    Output("xrd-preset-snapshot", "data", allow_duplicate=True),
    Output("xrd-left-tabs", "active_tab", allow_duplicate=True),
    Output("xrd-processing-undo-stack", "data", allow_duplicate=True),
    Output("xrd-processing-redo-stack", "data", allow_duplicate=True),
    Input("xrd-preset-load-btn", "n_clicks"),
    State("xrd-preset-select", "value"),
    State("xrd-preset-hydrate", "data"),
    State("xrd-processing-draft", "data"),
    State("xrd-processing-undo-stack", "data"),
    State("xrd-processing-redo-stack", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def apply_xrd_preset(n_clicks, selected_name, hydrate_val, current_draft, undo_stack, redo_stack, locale_data):
    from dash_app import api_client

    loc = _loc(locale_data)
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    name = str(selected_name or "").strip()
    if not name:
        return (dash.no_update,) * 9
    try:
        payload = api_client.load_analysis_preset(_XRD_PRESET_ANALYSIS_TYPE, name)
    except Exception as exc:
        return (
            dash.no_update,
            dash.no_update,
            translate_ui(loc, "dash.analysis.xrd.presets.load_failed").format(error=str(exc)),
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )
    processing = dict(payload.get("processing") or {})
    draft = xrd_draft_from_loaded_processing(processing)
    template_id_raw = str(payload.get("workflow_template_id") or "").strip()
    template_out = template_id_raw if template_id_raw in _XRD_TEMPLATE_IDS else dash.no_update
    resolved_tid = template_id_raw if template_id_raw in _XRD_TEMPLATE_IDS else "xrd.general"
    snap = xrd_ui_snapshot_dict(resolved_tid, draft)
    status = translate_ui(loc, "dash.analysis.xrd.presets.loaded").format(preset=name)
    old_norm = normalize_xrd_processing_draft(current_draft)
    new_norm = normalize_xrd_processing_draft(draft)
    past2, fut2 = append_undo_after_edit(undo_stack, redo_stack, old_norm, new_norm)
    return (
        draft,
        template_out,
        status,
        int(hydrate_val or 0) + 1,
        name,
        snap,
        "xrd-tab-run",
        past2,
        fut2,
    )


@callback(
    Output("xrd-preset-refresh", "data", allow_duplicate=True),
    Output("xrd-preset-save-name", "value", allow_duplicate=True),
    Output("xrd-preset-status", "children", allow_duplicate=True),
    Output("xrd-preset-snapshot", "data", allow_duplicate=True),
    Output("xrd-left-tabs", "active_tab", allow_duplicate=True),
    Input("xrd-preset-save-btn", "n_clicks"),
    Input("xrd-preset-saveas-btn", "n_clicks"),
    State("xrd-preset-select", "value"),
    State("xrd-preset-save-name", "value"),
    State("xrd-processing-draft", "data"),
    State("xrd-template-select", "value"),
    State("xrd-preset-refresh", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def save_xrd_preset(n_save, n_saveas, selected_name, save_name, draft, template_id, refresh_token, locale_data):
    from dash_app import api_client

    loc = _loc(locale_data)
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    trig = ctx.triggered_id
    if trig == "xrd-preset-save-btn":
        name = str(selected_name or "").strip()
        if not name:
            return dash.no_update, dash.no_update, translate_ui(loc, "dash.analysis.xrd.presets.select_required"), dash.no_update, dash.no_update
        clear_name = dash.no_update
    elif trig == "xrd-preset-saveas-btn":
        name = str(save_name or "").strip()
        if not name:
            return dash.no_update, dash.no_update, translate_ui(loc, "dash.analysis.xrd.presets.save_name_required"), dash.no_update, dash.no_update
        clear_name = ""
    else:
        raise dash.exceptions.PreventUpdate
    processing_body = xrd_preset_processing_body_for_save(draft)
    try:
        response = api_client.save_analysis_preset(
            _XRD_PRESET_ANALYSIS_TYPE,
            name,
            workflow_template_id=str(template_id or "").strip() or None,
            processing=processing_body,
        )
    except Exception as exc:
        return dash.no_update, dash.no_update, translate_ui(loc, "dash.analysis.xrd.presets.save_failed").format(error=str(exc)), dash.no_update, dash.no_update
    resolved_template = str(response.get("workflow_template_id") or template_id or "")
    snap = xrd_ui_snapshot_dict(str(template_id or "").strip() or None, draft)
    status = translate_ui(loc, "dash.analysis.xrd.presets.saved").format(preset=name, template=resolved_template)
    return int(refresh_token or 0) + 1, clear_name, status, snap, "xrd-tab-run"


@callback(
    Output("xrd-preset-refresh", "data", allow_duplicate=True),
    Output("xrd-preset-select", "value", allow_duplicate=True),
    Output("xrd-preset-status", "children", allow_duplicate=True),
    Output("xrd-preset-loaded-name", "data", allow_duplicate=True),
    Output("xrd-preset-snapshot", "data", allow_duplicate=True),
    Input("xrd-preset-delete-btn", "n_clicks"),
    State("xrd-preset-select", "value"),
    State("xrd-preset-loaded-name", "data"),
    State("xrd-preset-refresh", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def delete_xrd_preset(n_clicks, selected_name, loaded_name, refresh_token, locale_data):
    from dash_app import api_client

    loc = _loc(locale_data)
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    name = str(selected_name or "").strip()
    if not name:
        return dash.no_update, dash.no_update, translate_ui(loc, "dash.analysis.xrd.presets.select_required"), dash.no_update, dash.no_update
    try:
        api_client.delete_analysis_preset(_XRD_PRESET_ANALYSIS_TYPE, name)
    except Exception as exc:
        return dash.no_update, dash.no_update, translate_ui(loc, "dash.analysis.xrd.presets.delete_failed").format(error=str(exc)), dash.no_update, dash.no_update
    status = translate_ui(loc, "dash.analysis.xrd.presets.deleted").format(preset=name)
    loaded = str(loaded_name or "").strip()
    if loaded == name:
        return int(refresh_token or 0) + 1, None, status, "", None
    return int(refresh_token or 0) + 1, None, status, dash.no_update, dash.no_update


@callback(
    Output("xrd-preset-loaded-line", "children"),
    Input("xrd-preset-loaded-name", "data"),
    Input("ui-locale", "data"),
)
def render_xrd_preset_loaded_line(loaded_name, locale_data):
    loc = _loc(locale_data)
    name = str(loaded_name or "").strip()
    if not name:
        return ""
    return translate_ui(loc, "dash.analysis.xrd.presets.loaded_line").format(preset=name)


@callback(
    Output("xrd-preset-dirty-flag", "children"),
    Input("ui-locale", "data"),
    Input("xrd-template-select", "value"),
    Input("xrd-processing-draft", "data"),
    State("xrd-preset-snapshot", "data"),
)
def render_xrd_preset_dirty_flag(locale_data, template_id, draft, snapshot):
    loc = _loc(locale_data)
    if not isinstance(snapshot, dict):
        return html.Span(translate_ui(loc, "dash.analysis.xrd.presets.dirty_no_baseline"), className="text-muted")
    current = xrd_ui_snapshot_dict(template_id, draft)
    if xrd_snapshots_equal(snapshot, current):
        return html.Span(translate_ui(loc, "dash.analysis.xrd.presets.clean"), className="text-success")
    return html.Span(translate_ui(loc, "dash.analysis.xrd.presets.dirty"), className="text-warning")


# --- Processing chrome, hydrate, sync, history, run ---


@callback(
    Output("xrd-processing-history-title", "children"),
    Output("xrd-processing-history-hint", "children"),
    Output("xrd-processing-undo-btn", "children"),
    Output("xrd-processing-redo-btn", "children"),
    Output("xrd-processing-reset-btn", "children"),
    Input("ui-locale", "data"),
)
def render_xrd_processing_history_chrome(locale_data):
    loc = _loc(locale_data)
    return (
        translate_ui(loc, "dash.analysis.xrd.processing.history_title"),
        translate_ui(loc, "dash.analysis.xrd.processing.history_hint"),
        translate_ui(loc, "dash.analysis.xrd.processing.undo_btn"),
        translate_ui(loc, "dash.analysis.xrd.processing.redo_btn"),
        translate_ui(loc, "dash.analysis.xrd.processing.reset_btn"),
    )


@callback(
    Output("xrd-axis-card-title", "children"),
    Output("xrd-axis-card-hint", "children"),
    Output("xrd-axis-sort", "label"),
    Output("xrd-axis-dedup-label", "children"),
    Output("xrd-axis-min-label", "children"),
    Output("xrd-axis-max-label", "children"),
    Output("xrd-smooth-card-title", "children"),
    Output("xrd-smooth-card-hint", "children"),
    Output("xrd-smooth-method-label", "children"),
    Output("xrd-smooth-window-label", "children"),
    Output("xrd-smooth-poly-label", "children"),
    Output("xrd-smooth-method", "options"),
    Output("xrd-baseline-card-title", "children"),
    Output("xrd-baseline-card-hint", "children"),
    Output("xrd-baseline-method-label", "children"),
    Output("xrd-baseline-window-label", "children"),
    Output("xrd-baseline-smooth-label", "children"),
    Output("xrd-baseline-method", "options"),
    Output("xrd-peak-card-title", "children"),
    Output("xrd-peak-card-hint", "children"),
    Output("xrd-peak-prom-label", "children"),
    Output("xrd-peak-dist-label", "children"),
    Output("xrd-peak-width-label", "children"),
    Output("xrd-peak-max-label", "children"),
    Output("xrd-match-card-title", "children"),
    Output("xrd-match-card-hint", "children"),
    Output("xrd-match-metric-label", "children"),
    Output("xrd-match-tol-label", "children"),
    Output("xrd-match-topn-label", "children"),
    Output("xrd-match-min-label", "children"),
    Output("xrd-match-iw-label", "children"),
    Output("xrd-match-maj-label", "children"),
    Output("xrd-plot-advanced-summary", "children"),
    Output("xrd-plot-advanced-hint", "children"),
    Output("xrd-plot-intermediate-label", "children"),
    Output("xrd-plot-advanced-title", "children"),
    Output("xrd-plot-density-label", "children"),
    Output("xrd-plot-maxlab-label", "children"),
    Output("xrd-plot-minratio-label", "children"),
    Output("xrd-plot-msize-label", "children"),
    Output("xrd-plot-pospr-label", "children"),
    Output("xrd-plot-intpr-label", "children"),
    Output("xrd-plot-style-label", "children"),
    Output("xrd-plot-style", "options"),
    Output("xrd-plot-xmin-label", "children"),
    Output("xrd-plot-xmax-label", "children"),
    Output("xrd-plot-ymin-label", "children"),
    Output("xrd-plot-ymax-label", "children"),
    Output("xrd-plot-lw-label", "children"),
    Output("xrd-plot-labels", "label"),
    Output("xrd-plot-matched", "label"),
    Output("xrd-plot-uobs", "label"),
    Output("xrd-plot-uref", "label"),
    Output("xrd-plot-conn", "label"),
    Output("xrd-plot-mlab", "label"),
    Output("xrd-plot-xlock", "label"),
    Output("xrd-plot-ylock", "label"),
    Output("xrd-plot-logy", "label"),
    Input("ui-locale", "data"),
)
def render_xrd_processing_cards_chrome(locale_data):
    loc = _loc(locale_data)
    smooth_opts = [
        {"label": translate_ui(loc, "dash.analysis.xrd.smoothing.savgol"), "value": "savgol"},
        {"label": translate_ui(loc, "dash.analysis.xrd.smoothing.moving_average"), "value": "moving_average"},
    ]
    bl_opts = [
        {"label": translate_ui(loc, "dash.analysis.xrd.baseline.rolling"), "value": "rolling_minimum"},
        {"label": translate_ui(loc, "dash.analysis.xrd.baseline.linear"), "value": "linear"},
    ]
    style_opts = [
        {"label": translate_ui(loc, "dash.analysis.xrd.plot.style.color_shape"), "value": "color_shape"},
        {"label": translate_ui(loc, "dash.analysis.xrd.plot.style.color_only"), "value": "color_only"},
        {"label": translate_ui(loc, "dash.analysis.xrd.plot.style.shape_only"), "value": "shape_only"},
    ]
    return (
        translate_ui(loc, "dash.analysis.xrd.axis.card_title"),
        translate_ui(loc, "dash.analysis.xrd.axis.hint"),
        translate_ui(loc, "dash.analysis.xrd.axis.sort"),
        translate_ui(loc, "dash.analysis.xrd.axis.dedup"),
        translate_ui(loc, "dash.analysis.xrd.axis.min"),
        translate_ui(loc, "dash.analysis.xrd.axis.max"),
        translate_ui(loc, "dash.analysis.xrd.smoothing.card_title"),
        translate_ui(loc, "dash.analysis.xrd.smoothing.hint"),
        translate_ui(loc, "dash.analysis.xrd.smoothing.method"),
        translate_ui(loc, "dash.analysis.xrd.smoothing.window"),
        translate_ui(loc, "dash.analysis.xrd.smoothing.polyorder"),
        smooth_opts,
        translate_ui(loc, "dash.analysis.xrd.baseline.card_title"),
        translate_ui(loc, "dash.analysis.xrd.baseline.hint"),
        translate_ui(loc, "dash.analysis.xrd.baseline.method"),
        translate_ui(loc, "dash.analysis.xrd.baseline.window"),
        translate_ui(loc, "dash.analysis.xrd.baseline.smoothing_window"),
        bl_opts,
        translate_ui(loc, "dash.analysis.xrd.peak.card_title"),
        translate_ui(loc, "dash.analysis.xrd.peak.hint"),
        translate_ui(loc, "dash.analysis.xrd.peak.prominence"),
        translate_ui(loc, "dash.analysis.xrd.peak.distance"),
        translate_ui(loc, "dash.analysis.xrd.peak.width"),
        translate_ui(loc, "dash.analysis.xrd.peak.max_peaks"),
        translate_ui(loc, "dash.analysis.xrd.match.card_title"),
        translate_ui(loc, "dash.analysis.xrd.match.hint"),
        translate_ui(loc, "dash.analysis.xrd.match.metric"),
        translate_ui(loc, "dash.analysis.xrd.match.tolerance"),
        translate_ui(loc, "dash.analysis.xrd.match.top_n"),
        translate_ui(loc, "dash.analysis.xrd.match.minimum_score"),
        translate_ui(loc, "dash.analysis.xrd.match.intensity_weight"),
        translate_ui(loc, "dash.analysis.xrd.match.major_fraction"),
        translate_ui(loc, "dash.analysis.xrd.plot.advanced_section"),
        translate_ui(loc, "dash.analysis.xrd.plot.advanced_hint"),
        translate_ui(loc, "dash.analysis.xrd.plot.show_intermediate"),
        translate_ui(loc, "dash.analysis.xrd.plot.advanced_title"),
        translate_ui(loc, "dash.analysis.xrd.plot.label_density"),
        translate_ui(loc, "dash.analysis.xrd.plot.max_labels"),
        translate_ui(loc, "dash.analysis.xrd.plot.min_intensity_ratio"),
        translate_ui(loc, "dash.analysis.xrd.plot.marker_size"),
        translate_ui(loc, "dash.analysis.xrd.plot.label_pos_precision"),
        translate_ui(loc, "dash.analysis.xrd.plot.label_int_precision"),
        translate_ui(loc, "dash.analysis.xrd.plot.style_preset"),
        style_opts,
        translate_ui(loc, "dash.analysis.xrd.plot.x_min"),
        translate_ui(loc, "dash.analysis.xrd.plot.x_max"),
        translate_ui(loc, "dash.analysis.xrd.plot.y_min"),
        translate_ui(loc, "dash.analysis.xrd.plot.y_max"),
        translate_ui(loc, "dash.analysis.xrd.plot.line_width"),
        translate_ui(loc, "dash.analysis.xrd.plot.show_peak_labels"),
        translate_ui(loc, "dash.analysis.xrd.plot.show_matched"),
        translate_ui(loc, "dash.analysis.xrd.plot.show_unmatched_obs"),
        translate_ui(loc, "dash.analysis.xrd.plot.show_unmatched_ref"),
        translate_ui(loc, "dash.analysis.xrd.plot.show_connectors"),
        translate_ui(loc, "dash.analysis.xrd.plot.show_match_labels"),
        translate_ui(loc, "dash.analysis.xrd.plot.x_lock"),
        translate_ui(loc, "dash.analysis.xrd.plot.y_lock"),
        translate_ui(loc, "dash.analysis.xrd.plot.log_y"),
    )


@callback(
    Output("xrd-smooth-poly", "disabled"),
    Input("xrd-smooth-method", "value"),
)
def toggle_xrd_smooth_poly(method):
    return str(method or "").strip().lower() != "savgol"


@callback(
    Output("xrd-baseline-window", "disabled"),
    Output("xrd-baseline-smooth", "disabled"),
    Input("xrd-baseline-method", "value"),
)
def toggle_xrd_baseline_windows(method):
    off = str(method or "").strip().lower() != "rolling_minimum"
    return off, off


@callback(
    Output("xrd-axis-sort", "value"),
    Output("xrd-axis-dedup", "value"),
    Output("xrd-axis-min", "value"),
    Output("xrd-axis-max", "value"),
    Output("xrd-smooth-method", "value"),
    Output("xrd-smooth-window", "value"),
    Output("xrd-smooth-poly", "value"),
    Output("xrd-baseline-method", "value"),
    Output("xrd-baseline-window", "value"),
    Output("xrd-baseline-smooth", "value"),
    Output("xrd-peak-prom", "value"),
    Output("xrd-peak-dist", "value"),
    Output("xrd-peak-width", "value"),
    Output("xrd-peak-max", "value"),
    Output("xrd-match-metric", "value"),
    Output("xrd-match-tol", "value"),
    Output("xrd-match-topn", "value"),
    Output("xrd-match-min", "value"),
    Output("xrd-match-iw", "value"),
    Output("xrd-match-maj", "value"),
    Output("xrd-plot-labels", "value"),
    Output("xrd-plot-matched", "value"),
    Output("xrd-plot-uobs", "value"),
    Output("xrd-plot-uref", "value"),
    Output("xrd-plot-conn", "value"),
    Output("xrd-plot-mlab", "value"),
    Output("xrd-plot-density", "value"),
    Output("xrd-plot-maxlab", "value"),
    Output("xrd-plot-minratio", "value"),
    Output("xrd-plot-msize", "value"),
    Output("xrd-plot-pospr", "value"),
    Output("xrd-plot-intpr", "value"),
    Output("xrd-plot-style", "value"),
    Output("xrd-plot-xlock", "value"),
    Output("xrd-plot-xmin", "value"),
    Output("xrd-plot-xmax", "value"),
    Output("xrd-plot-ylock", "value"),
    Output("xrd-plot-ymin", "value"),
    Output("xrd-plot-ymax", "value"),
    Output("xrd-plot-logy", "value"),
    Output("xrd-plot-lw", "value"),
    Output("xrd-plot-intermediate", "value"),
    Input("xrd-preset-hydrate", "data"),
    Input("xrd-history-hydrate", "data"),
    State("xrd-processing-draft", "data"),
)
def hydrate_xrd_processing_controls(_p, _h, draft):
    d = normalize_xrd_processing_draft(draft)
    ax = d["axis_normalization"]
    sm = d["smoothing"]
    bl = d["baseline"]
    pk = d["peak_detection"]
    mc = d["method_context"]
    ps = mc.get("xrd_plot_settings") if isinstance(mc.get("xrd_plot_settings"), dict) else {}
    return (
        bool(ax.get("sort_axis", True)),
        str(ax.get("deduplicate") or "first"),
        ax.get("axis_min"),
        ax.get("axis_max"),
        str(sm.get("method") or "savgol"),
        int(sm.get("window_length", 11)),
        int(sm.get("polyorder", 3)),
        str(bl.get("method") or "rolling_minimum"),
        int(bl.get("window_length", 31)),
        int(bl.get("smoothing_window", 9)),
        float(pk.get("prominence", 0.08)),
        int(pk.get("distance", 6)),
        int(pk.get("width", 2)),
        int(pk.get("max_peaks", 12)),
        str(mc.get("xrd_match_metric") or "peak_overlap_weighted"),
        float(mc.get("xrd_match_tolerance_deg", 0.28)),
        int(mc.get("xrd_match_top_n", 5)),
        float(mc.get("xrd_match_minimum_score", 0.42)),
        float(mc.get("xrd_match_intensity_weight", 0.35)),
        float(mc.get("xrd_match_major_peak_fraction", 0.4)),
        bool(ps.get("show_peak_labels", True)),
        bool(ps.get("show_matched_peaks", False)),
        bool(ps.get("show_unmatched_observed", False)),
        bool(ps.get("show_unmatched_reference", False)),
        bool(ps.get("show_match_connectors", False)),
        bool(ps.get("show_match_labels", False)),
        str(ps.get("label_density_mode") or "smart"),
        int(ps.get("max_labels", 10)),
        float(ps.get("min_label_intensity_ratio", 0.12)),
        int(ps.get("marker_size", 8)),
        int(ps.get("label_position_precision", 2)),
        int(ps.get("label_intensity_precision", 0)),
        str(ps.get("style_preset") or "color_shape"),
        bool(ps.get("x_range_enabled", False)),
        ps.get("x_min"),
        ps.get("x_max"),
        bool(ps.get("y_range_enabled", False)),
        ps.get("y_min"),
        ps.get("y_max"),
        bool(ps.get("log_y", False)),
        float(ps.get("line_width", 2.0)),
        bool(ps.get("show_intermediate_traces", False)),
    )


@callback(
    Output("xrd-processing-draft", "data", allow_duplicate=True),
    Output("xrd-processing-undo-stack", "data", allow_duplicate=True),
    Output("xrd-processing-redo-stack", "data", allow_duplicate=True),
    Input("xrd-axis-sort", "value"),
    Input("xrd-axis-dedup", "value"),
    Input("xrd-axis-min", "value"),
    Input("xrd-axis-max", "value"),
    Input("xrd-smooth-method", "value"),
    Input("xrd-smooth-window", "value"),
    Input("xrd-smooth-poly", "value"),
    Input("xrd-baseline-method", "value"),
    Input("xrd-baseline-window", "value"),
    Input("xrd-baseline-smooth", "value"),
    Input("xrd-peak-prom", "value"),
    Input("xrd-peak-dist", "value"),
    Input("xrd-peak-width", "value"),
    Input("xrd-peak-max", "value"),
    Input("xrd-match-metric", "value"),
    Input("xrd-match-tol", "value"),
    Input("xrd-match-topn", "value"),
    Input("xrd-match-min", "value"),
    Input("xrd-match-iw", "value"),
    Input("xrd-match-maj", "value"),
    Input("xrd-review-axis-ok", "value"),
    Input("xrd-review-wavelength", "value"),
    Input("xrd-plot-labels", "value"),
    Input("xrd-plot-matched", "value"),
    Input("xrd-plot-uobs", "value"),
    Input("xrd-plot-uref", "value"),
    Input("xrd-plot-conn", "value"),
    Input("xrd-plot-mlab", "value"),
    Input("xrd-plot-density", "value"),
    Input("xrd-plot-maxlab", "value"),
    Input("xrd-plot-minratio", "value"),
    Input("xrd-plot-msize", "value"),
    Input("xrd-plot-pospr", "value"),
    Input("xrd-plot-intpr", "value"),
    Input("xrd-plot-style", "value"),
    Input("xrd-plot-xlock", "value"),
    Input("xrd-plot-xmin", "value"),
    Input("xrd-plot-xmax", "value"),
    Input("xrd-plot-ylock", "value"),
    Input("xrd-plot-ymin", "value"),
    Input("xrd-plot-ymax", "value"),
    Input("xrd-plot-logy", "value"),
    Input("xrd-plot-lw", "value"),
    Input("xrd-plot-intermediate", "value"),
    State("xrd-processing-draft", "data"),
    State("xrd-processing-undo-stack", "data"),
    State("xrd-processing-redo-stack", "data"),
    prevent_initial_call="initial_duplicate",
)
def sync_xrd_processing_draft(
    axis_sort,
    axis_dedup,
    axis_min,
    axis_max,
    sm_m,
    sm_w,
    sm_p,
    bl_m,
    bl_w,
    bl_sw,
    pk_pr,
    pk_di,
    pk_wi,
    pk_mx,
    mm_met,
    mm_tol,
    mm_tn,
    mm_mi,
    mm_iw,
    mm_mj,
    rev_ax,
    rev_wl,
    pl_lab,
    pl_ma,
    pl_uo,
    pl_ur,
    pl_co,
    pl_ml,
    pl_den,
    pl_mxlb,
    pl_mnr,
    pl_ms,
    pl_pp,
    pl_ip,
    pl_st,
    pl_xe,
    pl_xa,
    pl_xb,
    pl_ye,
    pl_ya,
    pl_yb,
    pl_log,
    pl_lw,
    pl_intermediate,
    prev_draft,
    undo_stack,
    redo_stack,
):
    new_draft = xrd_draft_from_control_values(
        axis_sort=axis_sort,
        axis_dedup=axis_dedup,
        axis_min=axis_min,
        axis_max=axis_max,
        sm_method=sm_m,
        sm_window=sm_w,
        sm_poly=sm_p,
        bl_method=bl_m,
        bl_window=bl_w,
        bl_smooth_window=bl_sw,
        pk_prom=pk_pr,
        pk_dist=pk_di,
        pk_width=pk_wi,
        pk_max=pk_mx,
        match_metric=mm_met,
        match_tol=mm_tol,
        match_top_n=mm_tn,
        match_min_score=mm_mi,
        match_iw=mm_iw,
        match_maj=mm_mj,
        review_axis_ok=rev_ax,
        review_wavelength=rev_wl,
        plot_show_labels=pl_lab,
        plot_matched=pl_ma,
        plot_u_obs=pl_uo,
        plot_u_ref=pl_ur,
        plot_conn=pl_co,
        plot_m_lbl=pl_ml,
        plot_density=pl_den,
        plot_max_labels=pl_mxlb,
        plot_min_ratio=pl_mnr,
        plot_msize=pl_ms,
        plot_pos_prec=pl_pp,
        plot_int_prec=pl_ip,
        plot_style=pl_st,
        plot_x_en=pl_xe,
        plot_x_min=pl_xa,
        plot_x_max=pl_xb,
        plot_y_en=pl_ye,
        plot_y_min=pl_ya,
        plot_y_max=pl_yb,
        plot_log_y=pl_log,
        plot_lw=pl_lw,
        plot_show_intermediate=bool(pl_intermediate),
    )
    old_norm = normalize_xrd_processing_draft(prev_draft)
    new_norm = normalize_xrd_processing_draft(new_draft)
    past2, fut2 = append_undo_after_edit(undo_stack, redo_stack, old_norm, new_norm)
    return new_norm, past2, fut2


@callback(
    Output("xrd-processing-draft", "data", allow_duplicate=True),
    Output("xrd-processing-undo-stack", "data", allow_duplicate=True),
    Output("xrd-processing-redo-stack", "data", allow_duplicate=True),
    Output("xrd-history-hydrate", "data", allow_duplicate=True),
    Output("xrd-history-status", "children", allow_duplicate=True),
    Input("xrd-processing-undo-btn", "n_clicks"),
    Input("xrd-processing-redo-btn", "n_clicks"),
    Input("xrd-processing-reset-btn", "n_clicks"),
    State("xrd-processing-draft", "data"),
    State("xrd-processing-undo-stack", "data"),
    State("xrd-processing-redo-stack", "data"),
    State("xrd-history-hydrate", "data"),
    State("xrd-processing-default", "data"),
    State("xrd-template-select", "value"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def xrd_processing_history_actions(n_undo, n_redo, n_reset, draft, undo_stack, redo_stack, hist_hydrate, defaults, template_id, locale_data):
    loc = _loc(locale_data)
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    trig = ctx.triggered_id
    cur = normalize_xrd_processing_draft(draft)
    past = undo_stack or []
    fut = redo_stack or []
    h = int(hist_hydrate or 0)
    if trig == "xrd-processing-undo-btn":
        if not n_undo:
            raise dash.exceptions.PreventUpdate
        res = perform_undo(past, fut, cur)
        if res is None:
            raise dash.exceptions.PreventUpdate
        prev, pl, fl = res
        return prev, pl, fl, h + 1, translate_ui(loc, "dash.analysis.xrd.processing.history_status_undo")
    if trig == "xrd-processing-redo-btn":
        if not n_redo:
            raise dash.exceptions.PreventUpdate
        res = perform_redo(past, fut, cur)
        if res is None:
            raise dash.exceptions.PreventUpdate
        nxt, pl, fl = res
        return nxt, pl, fl, h + 1, translate_ui(loc, "dash.analysis.xrd.processing.history_status_redo")
    if trig == "xrd-processing-reset-btn":
        if not n_reset:
            raise dash.exceptions.PreventUpdate
        tid = template_id if template_id in _XRD_TEMPLATE_IDS else "xrd.general"
        base = copy.deepcopy(defaults) if isinstance(defaults, dict) and defaults else default_xrd_draft_for_template(tid)
        default_draft = normalize_xrd_processing_draft(base)
        if xrd_draft_processing_equal(cur, default_draft):
            raise dash.exceptions.PreventUpdate
        past_list = [copy.deepcopy(x) for x in past if isinstance(x, dict)]
        past_list.append(copy.deepcopy(cur))
        if len(past_list) > MAX_XRD_UNDO_DEPTH:
            past_list = past_list[-MAX_XRD_UNDO_DEPTH:]
        return default_draft, past_list, [], h + 1, translate_ui(loc, "dash.analysis.xrd.processing.history_status_reset")
    raise dash.exceptions.PreventUpdate


@callback(
    Output("xrd-processing-undo-btn", "disabled"),
    Output("xrd-processing-redo-btn", "disabled"),
    Input("xrd-processing-undo-stack", "data"),
    Input("xrd-processing-redo-stack", "data"),
)
def toggle_xrd_processing_history_buttons(undo_stack, redo_stack):
    u = undo_stack or []
    r = redo_stack or []
    return len(u) == 0, len(r) == 0


@callback(
    Output("xrd-run-status", "children"),
    Output("xrd-refresh", "data", allow_duplicate=True),
    Output("xrd-latest-result-id", "data", allow_duplicate=True),
    Output("workspace-refresh", "data", allow_duplicate=True),
    Input("xrd-run-btn", "n_clicks"),
    State("project-id", "data"),
    State("xrd-dataset-select", "value"),
    State("xrd-template-select", "value"),
    State("xrd-processing-draft", "data"),
    State("xrd-refresh", "data"),
    State("workspace-refresh", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def run_xrd_analysis(n_clicks, project_id, dataset_key, template_id, processing_draft, refresh_val, global_refresh, locale_data):
    loc = _loc(locale_data)
    if not n_clicks or not project_id or not dataset_key:
        raise dash.exceptions.PreventUpdate
    from dash_app.api_client import analysis_run

    overrides = xrd_overrides_from_draft(processing_draft)
    try:
        result = analysis_run(
            project_id=project_id,
            dataset_key=dataset_key,
            analysis_type="XRD",
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


def _xrd_ordered_figure_preview_keys(fa: dict) -> list[str]:
    return ordered_figure_preview_keys(fa)


def _xrd_fetch_figure_preview_data_urls(
    project_id: str,
    result_id: str,
    fa: dict,
    *,
    max_tiles: int,
    max_edge: int = MAX_XRD_FIGURE_PREVIEW_MAX_EDGE,
) -> dict[str, str]:
    """Fetch PNG bytes via authenticated API and return data URLs for inline ``html.Img``."""
    from dash_app.api_client import fetch_result_figure_png

    ordered = _xrd_ordered_figure_preview_keys(fa)[: max(0, int(max_tiles))]
    out: dict[str, str] = {}
    for label in ordered:
        try:
            raw = fetch_result_figure_png(project_id, result_id, label, max_edge=max_edge)
            if not raw:
                out[label] = ""
                continue
            out[label] = "data:image/png;base64," + base64.standard_b64encode(bytes(raw)).decode("ascii")
        except Exception:
            out[label] = ""
    return out


def _build_xrd_figure_artifacts_panel(
    figure_artifacts: dict | None,
    loc: str,
    *,
    previews: dict[str, str] | None = None,
) -> html.Div:
    return build_figure_artifacts_panel(
        figure_artifacts,
        loc,
        previews=previews,
        i18n_prefix="dash.analysis.xrd.figure",
        class_prefix="xrd",
        max_preview_tiles=MAX_XRD_FIGURE_PREVIEW_TILES,
    )


def _build_xrd_analysis_summary(dataset_detail: dict, summary: dict, result_meta: dict, loc: str, *, locale_data: str | None) -> html.Div:
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
    sample_label = resolve_sample_name(summary or {}, result_meta or {}, fallback_display_name=fallback_display_name, locale_data=locale_data) or na
    instrument = _format_dataset_metadata_value(metadata.get("instrument")) or na
    vendor = _format_dataset_metadata_value(metadata.get("vendor")) or na

    def _meta_value(value: str) -> html.Span:
        return html.Span(value, className="ms-meta-value", title=value)

    dl_rows: list[Any] = [
        html.Dt(translate_ui(loc, "dash.analysis.xrd.summary.dataset_label"), className="col-sm-4 text-muted ms-meta-term"),
        html.Dd(_meta_value(dataset_label), className="col-sm-8 ms-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.xrd.summary.sample_label"), className="col-sm-4 text-muted ms-meta-term"),
        html.Dd(_meta_value(sample_label), className="col-sm-8 ms-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.xrd.summary.instrument_label"), className="col-sm-4 text-muted ms-meta-term"),
        html.Dd(_meta_value(instrument), className="col-sm-8 ms-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.xrd.summary.vendor_label"), className="col-sm-4 text-muted ms-meta-term"),
        html.Dd(_meta_value(vendor), className="col-sm-8 ms-meta-def"),
    ]
    return html.Div(
        [
            html.H5(translate_ui(loc, "dash.analysis.xrd.summary.card_title"), className="mb-2"),
            html.Dl(dl_rows, className="row mb-0"),
        ]
    )


def _build_xrd_quality_card(detail: dict, result_meta: dict, loc: str) -> html.Details:
    validation = detail.get("validation") if isinstance(detail.get("validation"), dict) else {}
    status = str(validation.get("status") or result_meta.get("validation_status") or "unknown")
    warnings_list = validation.get("warnings") if isinstance(validation.get("warnings"), list) else []
    issues_list = validation.get("issues") if isinstance(validation.get("issues"), list) else []
    wc, ic = finalized_validation_warning_issue_counts(validation)
    status_token = status.strip().lower()
    if status_token in {"ok", "pass", "valid"} and wc == 0 and ic == 0:
        alert_color = "success"
    elif ic == 0:
        alert_color = "warning"
    else:
        alert_color = "danger"
    body_children: list[Any] = [
        html.P([html.Strong(translate_ui(loc, "dash.analysis.xrd.quality.status_label")), f" {status}"], className="mb-2"),
        html.P(
            [
                html.Strong(translate_ui(loc, "dash.analysis.xrd.quality.warnings_label")),
                f" {wc} · ",
                html.Strong(translate_ui(loc, "dash.analysis.xrd.quality.issues_label")),
                f" {ic}",
            ],
            className="mb-2 small",
        ),
    ]
    if warnings_list:
        body_children.append(html.H6(translate_ui(loc, "dash.analysis.xrd.setup.import_warnings"), className="small mt-2"))
        body_children.append(html.Ul([html.Li(str(w), className="small") for w in warnings_list], className="ps-3 mb-2"))
    if issues_list:
        body_children.append(html.Ul([html.Li(str(i), className="small text-danger") for i in issues_list], className="ps-3 mb-2"))
    checks = validation.get("checks")
    if isinstance(checks, dict) and checks:
        tech = html.Ul([html.Li(f"{k}: {v}", className="small") for k, v in checks.items()], className="mb-0 ps-3")
        body_children.append(
            _xrd_collapsible_section(loc, "dash.analysis.xrd.quality.checks_title", tech, open=False),
        )
    badge_row = html.Div(
        [
            dbc.Badge(f"{wc} warnings", color="warning", className="me-1") if wc else "",
            dbc.Badge(f"{ic} issues", color="danger", className="me-1") if ic else "",
        ],
        className="mb-2",
    )
    summary_line = html.Div(
        [badge_row, html.Div(body_children, className="small")],
        className="p-2 border rounded",
        style={"borderColor": "#e5e7eb"},
    )
    return html.Details(
        [
            html.Summary(
                [
                    html.Span(className="ta-details-chevron"),
                    html.Span(translate_ui(loc, "dash.analysis.xrd.quality.card_title"), className="ms-1"),
                ],
                className="ta-details-summary",
            ),
            html.Div(summary_line, className="ta-details-body mt-2"),
        ],
        className="ta-ms-details mb-0",
        open=bool(wc or ic),
    )


def _build_xrd_raw_metadata_panel(metadata: dict | None, loc: str) -> html.Details:
    meta = metadata if isinstance(metadata, dict) else {}
    if not meta:
        return _xrd_collapsible_section(
            loc,
            "dash.analysis.xrd.raw_metadata.card_title",
            html.P(translate_ui(loc, "dash.analysis.xrd.raw_metadata.empty"), className="text-muted mb-0"),
            open=False,
        )
    user_keys = [k for k in sorted(meta.keys()) if k in _XRD_USER_FACING_METADATA_KEYS]
    tech_keys = [k for k in sorted(meta.keys()) if k not in _XRD_USER_FACING_METADATA_KEYS]
    user_rows: list[Any] = []
    for key in user_keys:
        user_rows.extend(
            [
                html.Dt(str(key), className="col-sm-4 text-muted small ms-meta-term"),
                html.Dd(str(meta.get(key)), className="col-sm-8 small ms-meta-def"),
            ]
        )
    tech_body = html.Ul([html.Li(f"{k}: {meta.get(k)}", className="small") for k in tech_keys], className="mb-0 ps-3")
    body = html.Div(
        [
            html.H6(translate_ui(loc, "dash.analysis.xrd.raw_metadata.user_section"), className="small text-muted"),
            html.Dl(user_rows, className="row mb-2") if user_rows else html.P(translate_ui(loc, "dash.analysis.na"), className="small text-muted"),
            html.H6(translate_ui(loc, "dash.analysis.xrd.raw_metadata.technical_section"), className="small text-muted"),
            tech_body if tech_keys else html.P("—", className="small text-muted mb-0"),
        ]
    )
    return _xrd_collapsible_section(loc, "dash.analysis.xrd.raw_metadata.card_title", body, open=False)


def _build_xrd_top_match_hero(summary: dict, rows: list, loc: str) -> html.Div:
    if not rows:
        return html.P(translate_ui(loc, "dash.analysis.xrd.top_match.empty"), className="text-muted mb-0")
    top = rows[0]
    name = _display_candidate_name(top, loc)
    formula = str(top.get("formula_unicode") or top.get("formula") or "--")
    band = _confidence_band_label(loc, str(top.get("confidence_band") or "no_match"))
    score = _coerce_float(top.get("normalized_score"))
    score_s = f"{score:.4f}" if score is not None else translate_ui(loc, "dash.analysis.na")
    prov = str(top.get("library_provider") or "--")
    pkg = str(top.get("library_package") or "--")
    ev = top.get("evidence") if isinstance(top.get("evidence"), dict) else {}
    shared = ev.get("shared_peak_count", "--")
    overlap = ev.get("weighted_overlap_score", "--")
    cov = ev.get("coverage_ratio", "--")
    md = ev.get("mean_delta_position", "--")
    caution = str(summary.get("caution_message") or "").strip()
    rejected = str(summary.get("match_status") or "").lower() in {"no_match", "library_unavailable"}
    badge_color = "secondary" if rejected else "success"
    return html.Div(
        [
            html.H5(
                translate_ui(loc, "dash.analysis.xrd.section.top_match"),
                className="mb-2 small text-uppercase fw-semibold text-muted xrd-top-match-section-title",
            ),
            dbc.Card(
                dbc.CardBody(
                    [
                        html.Div([dbc.Badge(band, color=badge_color, className="me-2"), html.Strong(name, className="h5 mb-0")], className="mb-2"),
                        dbc.Row(
                            [
                                dbc.Col([html.Small(translate_ui(loc, "dash.analysis.xrd.hero.formula"), className="text-muted d-block"), html.Span(formula)], md=4),
                                dbc.Col([html.Small(translate_ui(loc, "dash.analysis.xrd.hero.score"), className="text-muted d-block"), html.Span(score_s)], md=4),
                                dbc.Col([html.Small(translate_ui(loc, "dash.analysis.xrd.hero.confidence"), className="text-muted d-block"), html.Span(band)], md=4),
                            ],
                            className="g-2 mb-2",
                        ),
                        dbc.Row(
                            [
                                dbc.Col([html.Small(translate_ui(loc, "dash.analysis.xrd.hero.provider"), className="text-muted d-block"), html.Span(prov)], md=4),
                                dbc.Col([html.Small(translate_ui(loc, "dash.analysis.xrd.hero.package"), className="text-muted d-block"), html.Span(pkg)], md=4),
                                dbc.Col([html.Small(translate_ui(loc, "dash.analysis.xrd.hero.shared_peaks"), className="text-muted d-block"), html.Span(shared)], md=4),
                            ],
                            className="g-2 mb-2",
                        ),
                        dbc.Row(
                            [
                                dbc.Col([html.Small(translate_ui(loc, "dash.analysis.xrd.hero.weighted_overlap"), className="text-muted d-block"), html.Span(overlap)], md=4),
                                dbc.Col([html.Small(translate_ui(loc, "dash.analysis.xrd.hero.coverage"), className="text-muted d-block"), html.Span(cov)], md=4),
                                dbc.Col([html.Small(translate_ui(loc, "dash.analysis.xrd.hero.mean_delta"), className="text-muted d-block"), html.Span(md)], md=4),
                            ],
                            className="g-2",
                        ),
                        dbc.Alert(translate_ui(loc, "dash.analysis.xrd.top_match.rejected"), color="warning", className="mt-2 mb-0 py-1 small")
                        if rejected
                        else (dbc.Alert(caution, color="warning", className="mt-2 mb-0 py-1 small") if caution else html.Div()),
                    ]
                ),
                className="border border-primary-subtle shadow-sm xrd-top-match-hero-card",
            ),
        ]
    )


def _build_match_cards(rows: list, summary: dict, loc: str = "en") -> html.Div:
    cards: list = [
        html.H6(
            translate_ui(loc, "dash.analysis.section.candidate_matches"),
            className="mb-2 text-muted text-uppercase small fw-semibold xrd-candidates-section-title",
        ),
    ]
    caution_message = str(summary.get("caution_message") or "").strip()
    if caution_message:
        cards.append(dbc.Alert(caution_message, color="warning", className="mb-2 py-1 small"))
    top_name = str(summary.get("top_candidate_name") or "").strip()
    if top_name:
        cards.append(
            html.P(translate_ui(loc, "dash.analysis.xrd.top_candidate", name=top_name), className="mb-2 text-muted")
        )
    if not rows:
        cards.append(html.P(translate_ui(loc, "dash.analysis.state.no_candidate_matches"), className="text-muted"))
        return html.Div(cards)
    for idx, row in enumerate(rows):
        cards.append(_match_card(row, idx, loc))
    return html.Div(cards)


def _flatten_xrd_table_row(row: dict) -> dict:
    out = dict(row)
    ev = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    out["evidence_shared_peaks"] = ev.get("shared_peak_count", "")
    out["evidence_overlap"] = ev.get("weighted_overlap_score", "")
    out["evidence_coverage"] = ev.get("coverage_ratio", "")
    out["evidence_mean_delta"] = ev.get("mean_delta_position", "")
    return out


def _build_xrd_match_table(rows: list, loc: str = "en") -> html.Div:
    if not rows:
        return html.Div(
            [
                html.H6(
                    translate_ui(loc, "dash.analysis.section.candidate_evidence_table"),
                    className="mb-2 text-body-secondary small fw-semibold xrd-evidence-table-title",
                ),
                html.P(translate_ui(loc, "dash.analysis.state.no_match_data"), className="text-muted small mb-0"),
            ],
            className="xrd-evidence-table-section",
        )
    flat = [_flatten_xrd_table_row(r) if isinstance(r, dict) else r for r in rows]
    columns = [
        "rank",
        "candidate_id",
        "display_name_unicode",
        "formula_unicode",
        "normalized_score",
        "confidence_band",
        "library_provider",
        "library_package",
        "evidence_shared_peaks",
        "evidence_overlap",
        "evidence_coverage",
        "evidence_mean_delta",
    ]
    return html.Div(
        [
            html.H6(
                translate_ui(loc, "dash.analysis.section.candidate_evidence_table"),
                className="mb-2 text-body-secondary small fw-semibold xrd-evidence-table-title",
            ),
            html.Div(dataset_table(flat, columns, table_id="xrd-matches-table"), className="xrd-evidence-table-wrap"),
        ],
        className="xrd-evidence-table-section",
    )


_build_match_table = _build_xrd_match_table


def _build_figure(project_id, dataset_key, summary, processing, ui_theme):
    """Programmatic / test entry point mirroring the live result figure path."""
    from dash_app.api_client import analysis_state_curves

    loc = "en"
    curves = analysis_state_curves(project_id, "XRD", dataset_key) or {}
    axis = list(curves.get("temperature", []) or [])
    raw_signal = list(curves.get("raw_signal", []) or [])
    smoothed = list(curves.get("smoothed", []) or [])
    baseline = list(curves.get("baseline", []) or [])
    corrected = list(curves.get("corrected", []) or [])
    peaks_raw = curves.get("peaks") or []
    peaks = peaks_raw if isinstance(peaks_raw, list) else []

    n = len(axis)
    has_corrected = bool(corrected and len(corrected) == n)
    has_smoothed = bool(smoothed and len(smoothed) == n)
    has_raw = bool(raw_signal and len(raw_signal) == n)
    if not n or not (has_corrected or has_smoothed or has_raw):
        return html.P(translate_ui(loc, "dash.analysis.xrd.no_plot_signal"), className="text-muted mb-0")

    proc = processing if isinstance(processing, dict) else {}
    method_context = proc.get("method_context", {}) if isinstance(proc.get("method_context"), dict) else {}
    plot_settings = method_context.get("xrd_plot_settings") or {}
    axis_role = str(method_context.get("xrd_axis_role") or "two_theta").strip().lower()
    if axis_role in {"two_theta", ""}:
        axis_title = translate_ui(loc, "dash.analysis.figure.axis_two_theta")
    else:
        axis_title = translate_ui(loc, "dash.analysis.figure.axis_x_generic", role=axis_role)

    summ = summary if isinstance(summary, dict) else {}
    sample_name = resolve_sample_name(summ, {}, fallback_display_name=dataset_key, locale_data=loc)
    fig = build_xrd_result_figure(
        axis=axis,
        raw_signal=raw_signal,
        smoothed=smoothed,
        baseline=baseline,
        corrected=corrected,
        peaks=peaks,
        selected_match=None,
        plot_settings=plot_settings if isinstance(plot_settings, dict) else {},
        ui_theme=ui_theme,
        loc=loc,
        sample_name=sample_name,
        axis_title=axis_title,
    )
    return dcc.Graph(
        id="xrd-result-plot-graph",
        figure=fig,
        config=build_plotly_config(plot_settings, filename="materialscope_xrd_diffractogram"),
        className="ta-plot",
    )


@callback(
    Output("xrd-result-analysis-summary", "children"),
    Output("xrd-result-metrics", "children"),
    Output("xrd-result-quality", "children"),
    Output("xrd-result-top-match", "children"),
    Output("xrd-result-candidate-cards", "children"),
    Output("xrd-result-table", "children"),
    Output("xrd-result-processing", "children"),
    Output("xrd-result-raw-metadata", "children"),
    Output("xrd-result-figure-controls", "children"),
    Output("xrd-result-cache", "data"),
    Input("xrd-latest-result-id", "data"),
    Input("xrd-refresh", "data"),
    Input("ui-locale", "data"),
    State("project-id", "data"),
)
def display_xrd_result(result_id, _refresh, locale_data, project_id):
    loc = _loc(locale_data)
    empty_msg = empty_result_msg(locale_data=locale_data)
    summary_empty = html.P(translate_ui(loc, "dash.analysis.xrd.summary.empty"), className="text-muted")
    quality_empty = _xrd_collapsible_section(
        loc,
        "dash.analysis.xrd.quality.card_title",
        html.P(translate_ui(loc, "dash.analysis.xrd.quality.empty"), className="text-muted mb-0"),
        open=False,
    )
    raw_empty = _build_xrd_raw_metadata_panel({}, loc)
    _hidden = html.Div(className="d-none")
    metrics_hint = html.P(translate_ui(loc, "dash.analysis.xrd.empty_results_hint"), className="text-muted mb-0")
    if not result_id or not project_id:
        return (summary_empty, metrics_hint, quality_empty, _hidden, _hidden, _hidden, empty_msg, raw_empty, "", None)
    from dash_app.api_client import workspace_dataset_detail, workspace_result_detail

    try:
        detail = workspace_result_detail(project_id, result_id)
    except Exception as exc:
        err = dbc.Alert(translate_ui(loc, "dash.analysis.error_loading_result", error=str(exc)), color="danger")
        return (summary_empty, err, quality_empty, _hidden, _hidden, _hidden, empty_msg, raw_empty, "", None)
    summary = detail.get("summary", {})
    result_meta = detail.get("result", {})
    processing = detail.get("processing", {})
    rows = detail.get("rows") or detail.get("rows_preview") or []
    dataset_key = result_meta.get("dataset_key")
    dataset_detail: dict = {}
    if dataset_key:
        try:
            dataset_detail = workspace_dataset_detail(project_id, dataset_key)
        except Exception:
            dataset_detail = {}
    analysis_summary = _build_xrd_analysis_summary(dataset_detail, summary, result_meta, loc, locale_data=locale_data)
    quality_panel = _build_xrd_quality_card(detail, result_meta, loc)
    raw_panel = _build_xrd_raw_metadata_panel((dataset_detail or {}).get("metadata"), loc)
    match_status = _match_status_label(loc, summary.get("match_status"))
    top_score = _coerce_float(summary.get("top_candidate_score"))
    na = translate_ui(loc, "dash.analysis.na")
    top_score_str = f"{top_score:.4f}" if top_score is not None else na
    peak_count = int(summary.get("peak_count") or 0)
    candidate_count = int(summary.get("candidate_count") or len(rows or []))
    sample_name = resolve_sample_name(summary, result_meta, locale_data=locale_data)
    metrics = metrics_row(
        [
            ("dash.analysis.metric.match_status", match_status),
            ("dash.analysis.metric.top_candidate_score", top_score_str),
            ("dash.analysis.metric.detected_peaks", str(peak_count)),
            ("dash.analysis.metric.candidates", str(candidate_count)),
            ("dash.analysis.metric.sample", sample_name),
        ],
        locale_data=locale_data,
    )
    top_hero = _build_xrd_top_match_hero(summary, rows, loc)
    cards = _build_match_cards(rows, summary, loc)
    table = _build_xrd_match_table(rows, loc)
    method_context = processing.get("method_context", {})
    provenance_state = str(summary.get("xrd_provenance_state") or method_context.get("xrd_provenance_state") or "unknown")
    provenance_warning = str(summary.get("xrd_provenance_warning") or method_context.get("xrd_provenance_warning") or "").strip()
    axis_role = str(method_context.get("xrd_axis_role") or "two_theta")
    wavelength = method_context.get("xrd_wavelength_angstrom")
    wl_display = str(wavelength) if wavelength not in (None, "") else translate_ui(loc, "dash.analysis.xrd.wavelength_not_provided")
    proc_extra = [
        html.P(translate_ui(loc, "dash.analysis.xrd.axis_role_note", role=axis_role)),
        html.P(translate_ui(loc, "dash.analysis.xrd.wavelength_line", value=wl_display)),
        html.P(translate_ui(loc, "dash.analysis.xrd.provenance_state", state=provenance_state)),
    ]
    if provenance_warning:
        proc_extra.append(html.P(translate_ui(loc, "dash.analysis.xrd.provenance_warning", warning=provenance_warning)))
    proc_extra.extend(
        [
            html.P(translate_ui(loc, "dash.analysis.xrd.qualitative_notice")),
            html.P(translate_ui(loc, "dash.analysis.xrd.peak_detection", detail=processing.get("analysis_steps", {}).get("peak_detection", {})), className="mb-0"),
            html.P(
                translate_ui(loc, "dash.analysis.xrd.processing.match_metric", raw=str(method_context.get("xrd_match_metric") or "")),
                className="small text-muted mb-0",
            ),
        ]
    )
    proc_view = html.Div(
        processing_details_section(processing, extra_lines=proc_extra, locale_data=locale_data),
        className="xrd-processing-details-wrap",
    )
    opts = [{"label": f"#{i + 1} {_display_candidate_name(r, loc)[:48]}", "value": i} for i, r in enumerate(rows) if isinstance(r, dict)]
    controls = html.Div(
        className="d-flex flex-wrap align-items-center gap-2 w-100 xrd-overlay-toolbar-inner",
        children=[
            dbc.Label(
                translate_ui(loc, "dash.analysis.xrd.figure.overlay_label"),
                className="small text-muted mb-0 text-nowrap flex-shrink-0 xrd-overlay-label",
            ),
            html.Div(
                dcc.Dropdown(
                    id="xrd-candidate-overlay",
                    options=opts,
                    value=0,
                    clearable=False,
                    className="xrd-overlay-dropdown-dash",
                    style={"minWidth": "min(100%, 10rem)", "maxWidth": "100%"},
                ),
                className="flex-grow-1",
                style={"minWidth": "min(100%, 10rem)"},
            ),
        ],
    )
    cache = {
        "project_id": project_id,
        "dataset_key": dataset_key,
        "summary": summary,
        "processing": processing,
        "rows": rows,
    }
    return (
        analysis_summary,
        metrics,
        quality_panel,
        top_hero,
        cards,
        table,
        proc_view,
        raw_panel,
        controls,
        cache,
    )


def _xrd_shapes_from_relayout(relayout_data):
    if not isinstance(relayout_data, dict):
        return None
    shapes = relayout_data.get("shapes")
    if isinstance(shapes, list):
        return [dict(shape) for shape in shapes if isinstance(shape, dict)]
    return None


@callback(
    Output("xrd-result-figure", "children"),
    Input("xrd-result-cache", "data"),
    Input("xrd-candidate-overlay", "value"),
    Input("ui-theme", "data"),
    Input("ui-locale", "data"),
    State("project-id", "data"),
    State("xrd-result-plot-graph", "relayoutData"),
)
def render_xrd_result_figure_area(cache, overlay_idx, ui_theme, locale_data, project_id, relayout_data):
    loc = _loc(locale_data)
    empty_msg = empty_result_msg(locale_data=locale_data)
    if not cache or not project_id:
        return empty_msg
    dataset_key = cache.get("dataset_key")
    summary = cache.get("summary") or {}
    processing = cache.get("processing") or {}
    rows = cache.get("rows") or []
    if not dataset_key:
        return empty_msg
    idx = int(overlay_idx) if overlay_idx is not None else 0
    selected = rows[idx] if 0 <= idx < len(rows) else None
    from dash_app.api_client import analysis_state_curves

    try:
        curves = analysis_state_curves(project_id, "XRD", dataset_key)
    except Exception:
        curves = {}
    axis = curves.get("temperature", [])
    raw_signal = curves.get("raw_signal", [])
    smoothed = curves.get("smoothed", [])
    baseline = curves.get("baseline", [])
    corrected = curves.get("corrected", [])
    peaks = curves.get("peaks") or []
    if not axis:
        return no_data_figure_msg(locale_data=locale_data)
    plot_settings = (processing.get("method_context") or {}).get("xrd_plot_settings") or {}
    method_context = processing.get("method_context", {})
    axis_role = str(method_context.get("xrd_axis_role") or "two_theta").strip().lower()
    if axis_role in {"two_theta", ""}:
        axis_title = translate_ui(loc, "dash.analysis.figure.axis_two_theta")
    else:
        axis_title = translate_ui(loc, "dash.analysis.figure.axis_x_generic", role=axis_role)
    sample_name = resolve_sample_name(summary, {}, fallback_display_name=dataset_key, locale_data=locale_data)
    fig = build_xrd_result_figure(
        axis=axis,
        raw_signal=raw_signal,
        smoothed=smoothed,
        baseline=baseline,
        corrected=corrected,
        peaks=peaks if isinstance(peaks, list) else [],
        selected_match=selected if isinstance(selected, dict) else None,
        plot_settings=plot_settings,
        ui_theme=ui_theme,
        loc=loc,
        sample_name=sample_name,
        axis_title=axis_title,
        drawn_shapes=_xrd_shapes_from_relayout(relayout_data),
    )
    return dcc.Graph(
        id="xrd-result-plot-graph",
        figure=fig,
        config=build_plotly_config(plot_settings, filename="materialscope_xrd_diffractogram"),
        className="ta-plot",
    )


@callback(
    Output("xrd-literature-card-title", "children"),
    Output("xrd-literature-hint", "children"),
    Output("xrd-literature-max-claims-label", "children"),
    Output("xrd-literature-persist-label", "children"),
    Output("xrd-literature-compare-btn", "children"),
    Output("xrd-literature-options-summary", "children"),
    Input("ui-locale", "data"),
    Input("xrd-latest-result-id", "data"),
)
def render_xrd_literature_chrome(locale_data, result_id):
    loc = _loc(locale_data)
    if result_id:
        hint = literature_t(loc, f"{_XRD_LITERATURE_PREFIX}.ready", "Compare the saved XRD result to literature sources.")
    else:
        hint = literature_t(loc, f"{_XRD_LITERATURE_PREFIX}.empty", "Run an XRD analysis first to enable literature comparison.")
    return (
        literature_t(loc, f"{_XRD_LITERATURE_PREFIX}.title", "Literature Compare"),
        hint,
        literature_t(loc, f"{_XRD_LITERATURE_PREFIX}.max_claims", "Max Claims"),
        literature_t(loc, f"{_XRD_LITERATURE_PREFIX}.persist", "Persist to project"),
        literature_t(loc, f"{_XRD_LITERATURE_PREFIX}.compare_btn", "Compare"),
        literature_t(loc, f"{_XRD_LITERATURE_PREFIX}.options_summary", "Compare options"),
    )


@callback(Output("xrd-literature-compare-btn", "disabled"), Input("xrd-latest-result-id", "data"))
def toggle_xrd_literature_compare_button(result_id):
    return not bool(result_id)


@callback(
    Output("xrd-literature-output", "children"),
    Output("xrd-literature-status", "children"),
    Input("xrd-literature-compare-btn", "n_clicks"),
    State("project-id", "data"),
    State("xrd-latest-result-id", "data"),
    State("xrd-literature-max-claims", "value"),
    State("xrd-literature-persist", "value"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def compare_xrd_literature(n_clicks, project_id, result_id, max_claims, persist_values, locale_data):
    loc = _loc(locale_data)
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    if not project_id or not result_id:
        msg = literature_t(loc, f"{_XRD_LITERATURE_PREFIX}.missing_result", "Run an XRD analysis first.")
        return dash.no_update, dbc.Alert(msg, color="warning", className="py-1 small")
    claims_limit = coerce_literature_max_claims(max_claims, default=3)
    persist = bool(persist_values) and "persist" in (persist_values or [])
    from dash_app.api_client import literature_compare

    try:
        payload = literature_compare(project_id, result_id, max_claims=claims_limit, persist=persist)
    except Exception as exc:
        err = dbc.Alert(
            literature_t(loc, f"{_XRD_LITERATURE_PREFIX}.error", "Literature compare failed: {error}").replace("{error}", str(exc)),
            color="danger",
            className="py-1 small",
        )
        return dash.no_update, err
    return (
        render_literature_output(
            payload,
            loc,
            i18n_prefix=_XRD_LITERATURE_PREFIX,
            evidence_preview_limit=1,
            alternative_preview_limit=1,
            collapse_retained_evidence=True,
        ),
        literature_compare_status_alert(payload, loc, i18n_prefix=_XRD_LITERATURE_PREFIX),
    )


def _xrd_primary_report_figure_label(dataset_key: str | None, result_id: str | None) -> str:
    return primary_report_figure_label("XRD", dataset_key, result_id)


@callback(
    Output("xrd-figure-save-snapshot-btn", "children"),
    Output("xrd-figure-use-report-btn", "children"),
    Output("xrd-figure-artifacts-summary", "children"),
    Input("ui-locale", "data"),
)
def render_xrd_figure_artifact_button_labels(locale_data):
    loc = _loc(locale_data)
    return figure_artifact_button_labels(loc, i18n_prefix="dash.analysis.xrd.figure")


@callback(
    Output("xrd-figure-save-snapshot-btn", "disabled"),
    Output("xrd-figure-use-report-btn", "disabled"),
    Input("xrd-latest-result-id", "data"),
)
def toggle_xrd_figure_artifact_buttons(result_id):
    dis = not bool(result_id)
    return dis, dis


@callback(
    Output("xrd-result-figure-artifacts", "children"),
    Input("xrd-latest-result-id", "data"),
    Input("xrd-figure-artifact-refresh", "data"),
    Input("ui-locale", "data"),
    State("project-id", "data"),
)
def refresh_xrd_figure_artifacts_panel(result_id, _artifact_refresh, locale_data, project_id):
    loc = _loc(locale_data)
    if not result_id or not project_id:
        return ""
    from dash_app.api_client import workspace_result_detail

    try:
        detail = workspace_result_detail(project_id, result_id)
    except Exception:
        return ""
    fa = detail.get("figure_artifacts") if isinstance(detail.get("figure_artifacts"), dict) else {}
    if not _xrd_ordered_figure_preview_keys(fa):
        return _build_xrd_figure_artifacts_panel(fa, loc, previews=None)
    previews = _xrd_fetch_figure_preview_data_urls(project_id, result_id, fa, max_tiles=MAX_XRD_FIGURE_PREVIEW_TILES)
    return _build_xrd_figure_artifacts_panel(fa, loc, previews=previews)


@callback(
    Output("xrd-figure-artifact-status", "children"),
    Output("xrd-figure-artifact-refresh", "data"),
    Input("xrd-figure-save-snapshot-btn", "n_clicks"),
    Input("xrd-figure-use-report-btn", "n_clicks"),
    Input("xrd-latest-result-id", "data"),
    State("project-id", "data"),
    State("xrd-result-figure", "children"),
    State("ui-locale", "data"),
    State("xrd-figure-artifact-refresh", "data"),
    prevent_initial_call=True,
)
def xrd_figure_snapshot_or_report_figure(snap_clicks, report_clicks, latest_result_id, project_id, figure_children, locale_data, refresh_value):
    loc = _loc(locale_data)
    ctx = dash.callback_context
    triggered_id = getattr(ctx, "triggered_id", None)
    if triggered_id is None:
        raise dash.exceptions.PreventUpdate
    if triggered_id == "xrd-latest-result-id":
        return "", dash.no_update
    action = figure_action_from_trigger(
        triggered_id,
        snapshot_button_id="xrd-figure-save-snapshot-btn",
        report_button_id="xrd-figure-use-report-btn",
    )
    if action is None:
        raise dash.exceptions.PreventUpdate
    if not project_id or not latest_result_id:
        return (
            figure_action_status_alert(
                loc,
                i18n_prefix="dash.analysis.xrd.figure",
                action=action,
                status="missing",
                reason="missing_project_or_result",
                class_prefix="xrd",
            ),
            dash.no_update,
        )

    from dash_app.api_client import workspace_result_detail

    try:
        detail = workspace_result_detail(project_id, latest_result_id)
    except Exception as exc:
        return (
            figure_action_status_alert(
                loc,
                i18n_prefix="dash.analysis.xrd.figure",
                action=action,
                status="error",
                reason=str(exc),
                class_prefix="xrd",
            ),
            dash.no_update,
        )
    result_meta = detail.get("result", {}) or {}
    dataset_key = result_meta.get("dataset_key")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    meta = figure_action_metadata(
        action,
        analysis_type="XRD",
        dataset_key=str(dataset_key or "").strip() or None,
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
            figure_action_status_alert(
                loc,
                i18n_prefix="dash.analysis.xrd.figure",
                action=action,
                status="ok",
                figure_key=key,
                class_prefix="xrd",
            ),
            (refresh_value or 0) + 1,
        )
    if outcome.get("status") == "error":
        return (
            figure_action_status_alert(
                loc,
                i18n_prefix="dash.analysis.xrd.figure",
                action=action,
                status="error",
                reason=str(outcome.get("reason") or ""),
                class_prefix="xrd",
            ),
            dash.no_update,
        )
    return (
        figure_action_status_alert(
            loc,
            i18n_prefix="dash.analysis.xrd.figure",
            action=action,
            status="skipped",
            reason=str(outcome.get("reason") or ""),
            class_prefix="xrd",
        ),
        dash.no_update,
    )


@callback(
    Output("xrd-figure-captured", "data"),
    Input("xrd-latest-result-id", "data"),
    Input("project-id", "data"),
    Input("xrd-result-figure", "children"),
    State("xrd-figure-captured", "data"),
    prevent_initial_call=True,
)
def capture_xrd_figure(result_id, project_id, figure_children, captured):
    return capture_result_figure_from_layout(
        result_id=result_id,
        project_id=project_id,
        figure_children=figure_children,
        captured=captured,
        analysis_type="XRD",
    )


