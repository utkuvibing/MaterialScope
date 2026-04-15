"""XRD analysis page -- backend-driven stable first slice."""

from __future__ import annotations

import math

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html
import plotly.graph_objects as go

from dash_app.components.analysis_page import (
    analysis_page_stores,
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
from dash_app.theme import PLOT_THEME, apply_figure_theme, normalize_ui_theme

dash.register_page(__name__, path="/xrd", title="XRD Analysis - MaterialScope")

_XRD_WORKFLOW_TEMPLATES = [
    {"id": "xrd.general", "label": "General XRD"},
    {"id": "xrd.phase_screening", "label": "Phase Screening"},
]
_TEMPLATE_OPTIONS = [{"label": t["label"], "value": t["id"]} for t in _XRD_WORKFLOW_TEMPLATES]
_XRD_ELIGIBLE_TYPES = {"XRD", "UNKNOWN"}

_CONFIDENCE_COLORS = {
    "high_confidence": "#059669",
    "moderate_confidence": "#D97706",
    "low_confidence": "#DC2626",
    "no_match": "#6B7280",
}


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


def _display_candidate_name(row: dict) -> str:
    for key in ("display_name_unicode", "display_name", "candidate_name", "phase_name", "candidate_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return "Unknown Candidate"


def _match_card(row: dict, idx: int) -> dbc.Card:
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
    candidate = _display_candidate_name(row)

    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(
                    [
                        html.I(className="bi bi-bullseye me-2", style={"color": color, "fontSize": "1.1rem"}),
                        html.Strong(f"Candidate {idx + 1}", className="me-2"),
                        html.Span(
                            confidence.replace("_", " ").title(),
                            className="badge",
                            style={"backgroundColor": color, "color": "white", "fontSize": "0.75rem"},
                        ),
                    ],
                    className="mb-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [html.Small("Phase", className="text-muted d-block"), html.Span(candidate)],
                            md=4,
                        ),
                        dbc.Col(
                            [html.Small("Formula", className="text-muted d-block"), html.Span(formula)],
                            md=2,
                        ),
                        dbc.Col(
                            [html.Small("Score", className="text-muted d-block"), html.Span(f"{score:.4f}")],
                            md=2,
                        ),
                        dbc.Col(
                            [
                                html.Small("Shared Peaks", className="text-muted d-block"),
                                html.Span(shared_peaks),
                            ],
                            md=2,
                        ),
                        dbc.Col(
                            [html.Small("Provider", className="text-muted d-block"), html.Span(provider)],
                            md=2,
                        ),
                    ],
                    className="g-2",
                ),
                html.Hr(className="my-2"),
                html.P(
                    f"Weighted overlap: {overlap_score}; coverage: {coverage_ratio}; mean delta 2theta: {mean_delta}",
                    className="mb-0 text-muted small",
                ),
            ]
        ),
        className="mb-2",
    )


layout = html.Div(
    analysis_page_stores("xrd-refresh", "xrd-latest-result-id")
    + [
        page_header(
            "XRD Analysis",
            "Select an XRD-eligible dataset, choose a workflow template, and run qualitative phase screening.",
            badge="Analysis",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dataset_selection_card("xrd-dataset-selector-area"),
                        workflow_template_card(
                            "xrd-template-select",
                            "xrd-template-description",
                            _TEMPLATE_OPTIONS,
                            "xrd.general",
                        ),
                        execute_card("xrd-run-status", "xrd-run-btn", "Run XRD Analysis"),
                    ],
                    md=4,
                ),
                dbc.Col(
                    [
                        result_placeholder_card("xrd-result-metrics"),
                        result_placeholder_card("xrd-result-figure"),
                        result_placeholder_card("xrd-result-candidate-cards"),
                        result_placeholder_card("xrd-result-table"),
                        result_placeholder_card("xrd-result-processing"),
                    ],
                    md=8,
                ),
            ]
        ),
    ]
)

_TEMPLATE_DESCRIPTIONS = {
    "xrd.general": "General XRD: axis normalization, smoothing, baseline correction, and weighted peak-overlap screening.",
    "xrd.phase_screening": "Phase Screening: tighter peak filters and qualitative top-N candidate review.",
}


@callback(
    Output("xrd-template-description", "children"),
    Input("xrd-template-select", "value"),
)
def update_template_description(template_id):
    return _TEMPLATE_DESCRIPTIONS.get(template_id, "XRD analysis workflow.")


@callback(
    Output("xrd-dataset-selector-area", "children"),
    Output("xrd-run-btn", "disabled"),
    Input("project-id", "data"),
    Input("xrd-refresh", "data"),
)
def load_eligible_datasets(project_id, _refresh):
    if not project_id:
        return html.P("No workspace active. Create one first.", className="text-muted"), True

    from dash_app.api_client import workspace_datasets

    try:
        payload = workspace_datasets(project_id)
    except Exception as exc:
        return dbc.Alert(f"Error loading datasets: {exc}", color="danger"), True

    all_datasets = payload.get("datasets", [])
    return dataset_selector_block(
        selector_id="xrd-dataset-select",
        empty_msg="Import an XRD file first.",
        eligible=eligible_datasets(all_datasets, _XRD_ELIGIBLE_TYPES),
        all_datasets=all_datasets,
        eligible_types=_XRD_ELIGIBLE_TYPES,
        active_dataset=payload.get("active_dataset"),
    )


@callback(
    Output("xrd-run-status", "children"),
    Output("xrd-refresh", "data", allow_duplicate=True),
    Output("xrd-latest-result-id", "data", allow_duplicate=True),
    Output("workspace-refresh", "data", allow_duplicate=True),
    Input("xrd-run-btn", "n_clicks"),
    State("project-id", "data"),
    State("xrd-dataset-select", "value"),
    State("xrd-template-select", "value"),
    State("xrd-refresh", "data"),
    State("workspace-refresh", "data"),
    prevent_initial_call=True,
)
def run_xrd_analysis(n_clicks, project_id, dataset_key, template_id, refresh_val, global_refresh):
    if not n_clicks or not project_id or not dataset_key:
        raise dash.exceptions.PreventUpdate

    from dash_app.api_client import analysis_run

    try:
        result = analysis_run(
            project_id=project_id,
            dataset_key=dataset_key,
            analysis_type="XRD",
            workflow_template_id=template_id,
        )
    except Exception as exc:
        return dbc.Alert(f"Analysis failed: {exc}", color="danger"), dash.no_update, dash.no_update, dash.no_update

    alert, saved, result_id = interpret_run_result(result)
    refresh = (refresh_val or 0) + 1
    if saved:
        return alert, refresh, result_id, (global_refresh or 0) + 1
    return alert, refresh, dash.no_update, dash.no_update


@callback(
    Output("xrd-result-metrics", "children"),
    Output("xrd-result-candidate-cards", "children"),
    Output("xrd-result-figure", "children"),
    Output("xrd-result-table", "children"),
    Output("xrd-result-processing", "children"),
    Input("xrd-latest-result-id", "data"),
    Input("xrd-refresh", "data"),
    Input("ui-theme", "data"),
    State("project-id", "data"),
)
def display_result(result_id, _refresh, ui_theme, project_id):
    empty_msg = empty_result_msg()
    if not result_id or not project_id:
        return empty_msg, empty_msg, empty_msg, empty_msg, empty_msg

    from dash_app.api_client import workspace_result_detail

    try:
        detail = workspace_result_detail(project_id, result_id)
    except Exception as exc:
        err = dbc.Alert(f"Error loading result: {exc}", color="danger")
        return err, empty_msg, empty_msg, empty_msg, empty_msg

    summary = detail.get("summary", {})
    result_meta = detail.get("result", {})
    processing = detail.get("processing", {})
    rows = detail.get("rows") or detail.get("rows_preview") or []

    match_status = str(summary.get("match_status", "no_match")).replace("_", " ").title()
    top_score = _coerce_float(summary.get("top_candidate_score"))
    top_score_str = f"{top_score:.4f}" if top_score is not None else "N/A"
    peak_count = int(summary.get("peak_count") or 0)
    candidate_count = int(summary.get("candidate_count") or len(rows or []))
    sample_name = resolve_sample_name(summary, result_meta)

    metrics = metrics_row(
        [
            ("Match Status", match_status),
            ("Top Candidate Score", top_score_str),
            ("Detected Peaks", str(peak_count)),
            ("Candidates", str(candidate_count)),
            ("Sample", sample_name),
        ]
    )

    candidate_cards = _build_match_cards(rows, summary)

    dataset_key = result_meta.get("dataset_key")
    figure_area = empty_msg
    if dataset_key:
        figure_area = _build_figure(project_id, dataset_key, summary, processing, ui_theme)

    table_area = _build_match_table(rows)
    method_context = processing.get("method_context", {})
    provenance_state = str(
        summary.get("xrd_provenance_state")
        or method_context.get("xrd_provenance_state")
        or "unknown"
    )
    provenance_warning = str(
        summary.get("xrd_provenance_warning")
        or method_context.get("xrd_provenance_warning")
        or ""
    ).strip()
    axis_role = str(method_context.get("xrd_axis_role") or "two_theta")
    wavelength = method_context.get("xrd_wavelength_angstrom")

    proc_extra = [
        html.P(f"Axis role: {axis_role}; output shown as 2theta-oriented diffractogram."),
        html.P(f"Wavelength (angstrom): {wavelength if wavelength not in (None, '') else 'not provided'}"),
        html.P(f"XRD provenance state: {provenance_state}"),
    ]
    if provenance_warning:
        proc_extra.append(html.P(f"Provenance warning: {provenance_warning}"))
    proc_extra.extend(
        [
            html.P("This page is for qualitative phase-screening; do not treat top candidates as definitive identification."),
            html.P(
                f"Peak Detection: {processing.get('analysis_steps', {}).get('peak_detection', {})}",
                className="mb-0",
            ),
        ]
    )

    proc_view = processing_details_section(processing, extra_lines=proc_extra)
    return metrics, candidate_cards, figure_area, table_area, proc_view


def _build_match_cards(rows: list, summary: dict) -> html.Div:
    cards: list = [html.H5("Candidate Matches", className="mb-3")]
    caution_message = str(summary.get("caution_message") or "").strip()
    if caution_message:
        cards.append(dbc.Alert(caution_message, color="warning", className="mb-3"))

    top_name = str(
        summary.get("top_candidate_display_name")
        or summary.get("top_candidate_name")
        or summary.get("top_phase_display_name")
        or summary.get("top_phase")
        or ""
    ).strip()
    if top_name:
        cards.append(html.P(f"Top candidate: {top_name}", className="mb-2"))

    if not rows:
        cards.append(html.P("No candidate matches were returned.", className="text-muted"))
        return html.Div(cards)

    for idx, row in enumerate(rows):
        cards.append(_match_card(row, idx))
    return html.Div(cards)


def _build_figure(project_id: str, dataset_key: str, summary: dict, processing: dict, ui_theme: str | None) -> html.Div:
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

    if not axis:
        return no_data_figure_msg()

    has_corrected = bool(corrected and len(corrected) == len(axis))
    has_smoothed = bool(smoothed and len(smoothed) == len(axis))
    has_raw = bool(raw_signal and len(raw_signal) == len(axis))
    has_baseline = bool(baseline and len(baseline) == len(axis))
    if not any((has_corrected, has_smoothed, has_raw)):
        return no_data_figure_msg("No processed XRD signal is available for plotting.")

    primary_signal = corrected if has_corrected else smoothed if has_smoothed else raw_signal
    primary_name = "Corrected Diffractogram" if has_corrected else "Smoothed Diffractogram" if has_smoothed else "Raw Diffractogram"
    has_overlay = has_corrected or has_smoothed
    sample_name = resolve_sample_name(summary, {}, fallback_display_name=dataset_key)
    tone = normalize_ui_theme(ui_theme)
    pt = PLOT_THEME[tone]
    muted = "#66645E" if tone == "light" else "#9E9A93"
    line_primary = pt["text"]
    method_context = processing.get("method_context", {})
    axis_role = str(method_context.get("xrd_axis_role") or "two_theta").strip().lower()
    axis_title = "2theta (deg)" if axis_role in {"two_theta", ""} else f"X axis ({axis_role})"

    fig = go.Figure()
    if has_raw:
        fig.add_trace(
            go.Scatter(
                x=axis,
                y=raw_signal,
                mode="lines",
                name="Raw Diffractogram",
                line=dict(color="#94A3B8", width=1.4),
                opacity=0.35 if has_overlay else 0.95,
            )
        )
    if has_smoothed:
        fig.add_trace(
            go.Scatter(
                x=axis,
                y=smoothed,
                mode="lines",
                name="Smoothed Diffractogram",
                line=dict(color="#0369A1", width=2.0),
                opacity=0.85 if has_corrected else 1.0,
            )
        )
    if has_baseline:
        fig.add_trace(
            go.Scatter(
                x=axis,
                y=baseline,
                mode="lines",
                name="Baseline",
                line=dict(color="#6D28D9", width=1.2, dash="dash"),
                opacity=0.7,
            )
        )

    fig.add_trace(
        go.Scatter(
            x=axis,
            y=primary_signal,
            mode="lines",
            name=primary_name,
            line=dict(color=line_primary, width=3.0),
        )
    )

    fig.update_layout(
        title=("XRD Primary Diffractogram" f"<br><span style='font-size:0.82em;color:{muted}'>{sample_name}</span>"),
        paper_bgcolor=pt["paper_bg"],
        plot_bgcolor=pt["plot_bg"],
        hovermode="x unified",
        xaxis_title=axis_title,
        yaxis_title="Intensity (a.u.)",
        margin=dict(l=64, r=28, t=82, b=56),
        height=520,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    apply_figure_theme(fig, ui_theme)
    return dcc.Graph(figure=fig, config={"displaylogo": False, "responsive": True}, className="ta-plot")


def _build_match_table(rows: list) -> html.Div:
    if not rows:
        return html.Div(
            [html.H5("Candidate Evidence Table", className="mb-3"), html.P("No match data.", className="text-muted")]
        )

    columns = [
        "rank",
        "candidate_id",
        "display_name_unicode",
        "formula_unicode",
        "normalized_score",
        "confidence_band",
        "library_provider",
        "library_package",
    ]
    return html.Div(
        [
            html.H5("Candidate Evidence Table", className="mb-3"),
            dataset_table(rows, columns, table_id="xrd-matches-table"),
        ]
    )
