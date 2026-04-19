"""TGA analysis page -- backend-driven first analysis slice.

Lets the user:
  1. Select an eligible TGA dataset from the workspace
  2. Select a TGA unit mode (auto / percent / absolute_mass)
  3. Select a TGA workflow template
  4. Run analysis through the backend /analysis/run endpoint
  5. View analysis summary, validation, main mass trace, DTG preview, steps,
     processing, raw metadata, literature compare, and auto-refresh workspace state
"""

from __future__ import annotations

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
from dash_app.theme import PLOT_THEME, apply_figure_theme, normalize_ui_theme
from utils.i18n import normalize_ui_locale, translate_ui

dash.register_page(__name__, path="/tga", title="TGA Analysis - MaterialScope")

_TGA_TEMPLATE_IDS = ["tga.general", "tga.single_step_decomposition", "tga.multi_step_decomposition"]
_TGA_UNIT_MODE_IDS = ["auto", "percent", "absolute_mass"]
_TGA_ELIGIBLE_TYPES = {"TGA", "UNKNOWN"}

_TGA_RESULT_CARD_ROLES = {
    "context": "dsc-result-context",
    "hero": "dsc-result-hero",
    "support": "dsc-result-support",
    "secondary": "dsc-result-secondary",
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


def _coerce_int_positive(value, *, default: int, minimum: int) -> int:
    try:
        if value in (None, ""):
            return max(default, minimum)
        parsed = int(float(value))
    except (TypeError, ValueError):
        return max(default, minimum)
    return max(parsed, minimum)


def _tga_result_section(child: Any, *, role: str = "support") -> html.Div:
    role_class = _TGA_RESULT_CARD_ROLES.get(role, _TGA_RESULT_CARD_ROLES["support"])
    return html.Div(child, className=f"dsc-result-section {role_class}")


def _tga_collapsible_section(loc: str, title_key: str, body: Any, *, open: bool = False) -> html.Details:
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


def _literature_compare_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id="tga-literature-card-title", className="card-title mb-3"),
                html.Div(id="tga-literature-hint", className="small text-muted mb-2"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(
                                    id="tga-literature-max-claims-label",
                                    html_for="tga-literature-max-claims",
                                ),
                                dbc.Input(
                                    id="tga-literature-max-claims",
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
                                    id="tga-literature-persist",
                                    options=[{"label": "", "value": "persist"}],
                                    value=[],
                                    switch=True,
                                    className="mt-4",
                                ),
                                dbc.Label(
                                    id="tga-literature-persist-label",
                                    html_for="tga-literature-persist",
                                    className="small",
                                ),
                            ],
                            md=6,
                        ),
                    ],
                    className="g-2 mb-2",
                ),
                dbc.Button(
                    id="tga-literature-compare-btn",
                    color="primary",
                    size="sm",
                    disabled=True,
                    className="mb-2",
                ),
                html.Div(id="tga-literature-status", className="small text-muted"),
                html.Div(id="tga-literature-output", className="mt-2"),
            ]
        ),
        className="mb-3",
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
        className="mb-4",
    )


layout = html.Div(
    analysis_page_stores("tga-refresh", "tga-latest-result-id")
    + [
        dcc.Store(id="tga-figure-captured", data={}),
        html.Div(id="tga-hero-slot"),
        dbc.Row(
            [
                dbc.Col(
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
                        execute_card("tga-run-status", "tga-run-btn", card_title_id="tga-execute-card-title"),
                    ],
                    md=4,
                ),
                dbc.Col(
                    [
                        _tga_result_section(result_placeholder_card("tga-result-analysis-summary"), role="context"),
                        _tga_result_section(result_placeholder_card("tga-result-metrics"), role="context"),
                        _tga_result_section(result_placeholder_card("tga-result-quality"), role="support"),
                        _tga_result_section(result_placeholder_card("tga-result-figure"), role="hero"),
                        _tga_result_section(result_placeholder_card("tga-result-dtg"), role="support"),
                        _tga_result_section(result_placeholder_card("tga-result-step-cards"), role="support"),
                        _tga_result_section(result_placeholder_card("tga-result-table"), role="support"),
                        _tga_result_section(result_placeholder_card("tga-result-processing"), role="support"),
                        _tga_result_section(result_placeholder_card("tga-result-raw-metadata"), role="support"),
                        _tga_result_section(_literature_compare_card(), role="secondary"),
                    ],
                    md=8,
                    className="dsc-results-surface",
                ),
            ]
        ),
    ]
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
    State("tga-refresh", "data"),
    State("workspace-refresh", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def run_tga_analysis(n_clicks, project_id, dataset_key, template_id, unit_mode, refresh_val, global_refresh, locale_data):
    loc = _loc(locale_data)
    if not n_clicks or not project_id or not dataset_key:
        raise dash.exceptions.PreventUpdate

    from dash_app.api_client import analysis_run

    try:
        result = analysis_run(
            project_id=project_id,
            dataset_key=dataset_key,
            analysis_type="TGA",
            workflow_template_id=template_id,
            unit_mode=unit_mode if unit_mode and unit_mode != "auto" else None,
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
        "dash.analysis.dsc.quality.card_title",
        html.P(translate_ui(loc, "dash.analysis.dsc.quality.empty"), className="text-muted mb-0"),
        open=False,
    )
    raw_meta_empty = _tga_collapsible_section(
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
    sample_name = resolve_sample_name(summary, result_meta, locale_data=locale_data)
    na = translate_ui(loc, "dash.analysis.na")

    total_loss_str = f"{total_mass_loss:.2f} %" if total_mass_loss is not None else na
    residue_str = f"{residue:.1f} %" if residue is not None else na

    metrics = metrics_row(
        [
            ("dash.analysis.metric.steps", str(step_count)),
            ("dash.analysis.metric.total_mass_loss", total_loss_str),
            ("dash.analysis.metric.residue", residue_str),
            ("dash.analysis.metric.template", str(processing.get("workflow_template_label", na))),
            ("dash.analysis.metric.sample", sample_name),
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
                f"{_TGA_LITERATURE_PREFIX}.error",
                "Literature compare failed: {error}",
            ).replace("{error}", str(exc)),
            color="danger",
            className="py-1 small",
        )
        return dash.no_update, err

    return (
        render_literature_output(payload, loc, i18n_prefix=_TGA_LITERATURE_PREFIX),
        literature_compare_status_alert(payload, loc, i18n_prefix=_TGA_LITERATURE_PREFIX),
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


def _build_tga_analysis_summary(
    dataset_detail: dict,
    summary: dict,
    result_meta: dict,
    processing: dict,
    loc: str,
    *,
    locale_data: str | None = None,
) -> html.Div:
    metadata = (dataset_detail or {}).get("metadata") or {}
    dataset_summary = (dataset_detail or {}).get("dataset") or {}
    na = translate_ui(loc, "dash.analysis.na")
    method_context = processing.get("method_context") or {}

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

    heating_rate = _format_dataset_metadata_value(summary.get("heating_rate")) or _format_dataset_metadata_value(
        metadata.get("heating_rate")
    )
    if heating_rate:
        heating_rate = f"{heating_rate} {translate_ui(loc, 'dash.analysis.dsc.summary.heating_rate_unit')}"
    else:
        heating_rate = na

    unit_resolved = _format_dataset_metadata_value(method_context.get("tga_unit_mode_resolved_label")) or _format_dataset_metadata_value(
        method_context.get("tga_unit_mode_label")
    ) or na
    unit_basis = _format_dataset_metadata_value(method_context.get("tga_unit_inference_basis")) or na

    def _meta_value(value: str) -> html.Span:
        return html.Span(value, className="dsc-meta-value", title=value)

    dl_rows: list[Any] = [
        html.Dt(translate_ui(loc, "dash.analysis.dsc.summary.dataset_label"), className="col-sm-4 text-muted dsc-meta-term"),
        html.Dd(_meta_value(dataset_label), className="col-sm-8 dsc-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.dsc.summary.sample_label"), className="col-sm-4 text-muted dsc-meta-term"),
        html.Dd(_meta_value(sample_label), className="col-sm-8 dsc-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.dsc.summary.mass_label"), className="col-sm-4 text-muted dsc-meta-term"),
        html.Dd(_meta_value(sample_mass), className="col-sm-8 dsc-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.dsc.summary.heating_rate_label"), className="col-sm-4 text-muted dsc-meta-term"),
        html.Dd(_meta_value(heating_rate), className="col-sm-8 dsc-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.tga.summary.unit_mode_label"), className="col-sm-4 text-muted dsc-meta-term"),
        html.Dd(_meta_value(unit_resolved), className="col-sm-8 dsc-meta-def"),
        html.Dt(translate_ui(loc, "dash.analysis.tga.summary.unit_inference_label"), className="col-sm-4 text-muted dsc-meta-term"),
        html.Dd(_meta_value(unit_basis), className="col-sm-8 dsc-meta-def"),
    ]
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
        body_children.append(
            html.Div(
                [
                    html.H6(translate_ui(loc, "dash.analysis.tga.quality.import_checks_heading"), className="small mt-2 mb-1"),
                    html.Ul([html.Li(item, className="small") for item in check_items], className="small mb-0 ps-3"),
                ],
                className="mb-0",
            )
        )

    inner = dbc.Alert(body_children, color=alert_color, className="mb-0 ta-quality-alert")
    return _tga_collapsible_section(loc, "dash.analysis.dsc.quality.card_title", inner, open=False)


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
        inner = html.P(translate_ui(loc, "dash.analysis.dsc.raw_metadata.empty"), className="text-muted mb-0")
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
                                translate_ui(loc, "dash.analysis.dsc.raw_metadata.technical_details") or "Technical details",
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
            else html.P(translate_ui(loc, "dash.analysis.dsc.raw_metadata.empty"), className="text-muted mb-0")
        )
    return _tga_collapsible_section(loc, "dash.analysis.dsc.raw_metadata.card_title", inner, open=False)


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
        className="ta-plot dsc-derivative-graph",
    )
    return html.Div(
        [
            html.H6(translate_ui(_ld, "dash.analysis.tga.dtg.card_title"), className="mb-2"),
            html.P(translate_ui(_ld, "dash.analysis.tga.dtg.caption"), className="small text-muted mb-2"),
            graph,
        ],
        className="dsc-derivative-helper",
    )


def _build_step_cards(rows: list, loc: str) -> html.Div:
    if not rows:
        return html.Div(
            [
                html.H5(translate_ui(loc, "dash.analysis.section.tga_key_steps"), className="mb-3"),
                html.P(translate_ui(loc, "dash.analysis.state.no_steps"), className="text-muted"),
            ]
        )

    cards = [html.H5(translate_ui(loc, "dash.analysis.section.tga_key_steps"), className="mb-3")]
    for idx, row in enumerate(rows):
        cards.append(_step_card(row, idx, loc))
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
    _ANNOTATION_MIN_SEP = 15.0
    annotated_temps: list[float] = []

    for row in step_rows:
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

    n_steps = len(step_rows)
    # Keep vertical guides readable: full onset/endset lines only for small step counts.
    show_step_vlines = n_steps <= 6
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
    return html.Div(
        [
            html.H5(translate_ui(loc, "dash.analysis.tga.figure.section_title"), className="mb-2"),
            dcc.Graph(
                figure=fig,
                config={"displaylogo": False, "responsive": True},
                className="ta-plot",
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
