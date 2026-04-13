"""DSC analysis page -- backend-driven first analysis slice.

Lets the user:
  1. Select an eligible DSC dataset from the workspace
  2. Select a DSC workflow template
  3. Run analysis through the backend /analysis/run endpoint
  4. View execution status, result summary, and DSC figure/preview
"""

from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html
import plotly.graph_objects as go

from dash_app.components.chrome import page_header
from dash_app.components.data_preview import dataset_table

dash.register_page(__name__, path="/dsc", title="DSC Analysis - MaterialScope")

_DSC_WORKFLOW_TEMPLATES = [
    {"id": "dsc.general", "label": "General DSC"},
    {"id": "dsc.polymer_tg", "label": "Polymer Tg"},
    {"id": "dsc.polymer_melting_crystallization", "label": "Polymer Melting/Crystallization"},
]

_TEMPLATE_OPTIONS = [{"label": t["label"], "value": t["id"]} for t in _DSC_WORKFLOW_TEMPLATES]


def _metric_card(label: str, value: str) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody([html.Small(label, className="text-muted text-uppercase"), html.H4(value, className="mb-0")])
    )


def _eligible_datasets(datasets: list[dict]) -> list[dict]:
    """Filter datasets eligible for DSC analysis (DSC, DTA, UNKNOWN types)."""
    eligible_types = {"DSC", "DTA", "UNKNOWN"}
    return [d for d in datasets if (d.get("data_type") or "").upper() in eligible_types]


def _dataset_options(datasets: list[dict]) -> list[dict]:
    return [
        {"label": f"{d.get('display_name', d.get('key', '?'))} ({d.get('data_type', '?')})", "value": d["key"]}
        for d in datasets
    ]


layout = html.Div(
    [
        dcc.Store(id="dsc-refresh", data=0),
        dcc.Store(id="dsc-latest-result-id"),
        page_header(
            "DSC Analysis",
            "Select a DSC-eligible dataset, choose a workflow template, and run thermal analysis.",
            badge="Analysis",
        ),
        dbc.Row(
            [
                # --- Left column: configuration + execution ---
                dbc.Col(
                    [
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.H5("Dataset Selection", className="mb-3"),
                                    html.Div(id="dsc-dataset-selector-area"),
                                ]
                            ),
                            className="mb-4",
                        ),
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.H5("Workflow Template", className="mb-3"),
                                    dbc.Select(
                                        id="dsc-template-select",
                                        options=_TEMPLATE_OPTIONS,
                                        value="dsc.general",
                                    ),
                                    html.P(
                                        "General DSC: smoothing + baseline + peak detection + Tg detection.",
                                        className="text-muted small mt-2",
                                        id="dsc-template-description",
                                    ),
                                ]
                            ),
                            className="mb-4",
                        ),
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.H5("Execute", className="mb-3"),
                                    html.Div(id="dsc-run-status"),
                                    dbc.Button(
                                        "Run DSC Analysis",
                                        id="dsc-run-btn",
                                        color="primary",
                                        className="w-100",
                                        disabled=True,
                                    ),
                                ]
                            ),
                            className="mb-4",
                        ),
                    ],
                    md=4,
                ),
                # --- Right column: result display ---
                dbc.Col(
                    [
                        dbc.Card(
                            dbc.CardBody(html.Div(id="dsc-result-metrics")),
                            className="mb-4",
                        ),
                        dbc.Card(
                            dbc.CardBody(html.Div(id="dsc-result-figure")),
                            className="mb-4",
                        ),
                        dbc.Card(
                            dbc.CardBody(html.Div(id="dsc-result-table")),
                            className="mb-4",
                        ),
                        dbc.Card(
                            dbc.CardBody(html.Div(id="dsc-result-processing")),
                            className="mb-4",
                        ),
                    ],
                    md=8,
                ),
            ]
        ),
    ]
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

_TEMPLATE_DESCRIPTIONS = {
    "dsc.general": "General DSC: Savitzky-Golay smoothing, ASLS baseline, peak detection (both directions), automatic Tg detection.",
    "dsc.polymer_tg": "Polymer Tg: Wider smoothing window for clearer glass transition, ASLS baseline, automatic Tg detection.",
    "dsc.polymer_melting_crystallization": "Polymer Melting/Crystallization: Standard smoothing, ASLS baseline, peak detection for melting and crystallization events.",
}


@callback(
    Output("dsc-template-description", "children"),
    Input("dsc-template-select", "value"),
)
def update_template_description(template_id):
    return _TEMPLATE_DESCRIPTIONS.get(template_id, "DSC analysis workflow.")


@callback(
    Output("dsc-dataset-selector-area", "children"),
    Output("dsc-run-btn", "disabled"),
    Input("project-id", "data"),
    Input("dsc-refresh", "data"),
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
    eligible = _eligible_datasets(all_datasets)

    if not eligible:
        return html.P("No DSC-eligible datasets found. Import a DSC file first.", className="text-muted"), True

    options = _dataset_options(eligible)
    active = payload.get("active_dataset")
    default_value = None
    if active:
        eligible_keys = {d["key"] for d in eligible}
        if active in eligible_keys:
            default_value = active

    selector = dbc.Select(
        id="dsc-dataset-select",
        options=options,
        value=default_value or (options[0]["value"] if options else None),
    )
    info = html.P(
        f"{len(eligible)} of {len(all_datasets)} datasets are DSC-eligible "
        f"(types: DSC, DTA, UNKNOWN).",
        className="text-muted small mt-2",
    )
    return html.Div([selector, info]), False


@callback(
    Output("dsc-run-status", "children"),
    Output("dsc-refresh", "data", allow_duplicate=True),
    Output("dsc-latest-result-id", "data", allow_duplicate=True),
    Input("dsc-run-btn", "n_clicks"),
    State("project-id", "data"),
    State("dsc-dataset-select", "value"),
    State("dsc-template-select", "value"),
    State("dsc-refresh", "data"),
    prevent_initial_call=True,
)
def run_dsc_analysis(n_clicks, project_id, dataset_key, template_id, refresh_val):
    if not n_clicks or not project_id or not dataset_key:
        raise dash.exceptions.PreventUpdate

    from dash_app.api_client import analysis_run

    try:
        result = analysis_run(
            project_id=project_id,
            dataset_key=dataset_key,
            analysis_type="DSC",
            workflow_template_id=template_id,
        )
    except Exception as exc:
        return dbc.Alert(f"Analysis failed: {exc}", color="danger"), dash.no_update, dash.no_update

    status = result.get("execution_status", "unknown")
    result_id = result.get("result_id")
    failure = result.get("failure_reason")
    validation = result.get("validation", {})

    if status == "saved" and result_id:
        msg = dbc.Alert(
            f"Analysis saved (result: {result_id}). "
            f"Validation: {validation.get('status', 'N/A')}, "
            f"warnings: {validation.get('warning_count', 0)}.",
            color="success",
        )
        return msg, (refresh_val or 0) + 1, result_id

    if status == "blocked":
        return dbc.Alert(f"Analysis blocked: {failure}", color="warning"), (refresh_val or 0) + 1, dash.no_update

    return dbc.Alert(f"Analysis failed: {failure or 'Unknown error'}", color="danger"), (refresh_val or 0) + 1, dash.no_update


@callback(
    Output("dsc-result-metrics", "children"),
    Output("dsc-result-figure", "children"),
    Output("dsc-result-table", "children"),
    Output("dsc-result-processing", "children"),
    Input("dsc-latest-result-id", "data"),
    Input("dsc-refresh", "data"),
    State("project-id", "data"),
)
def display_result(result_id, _refresh, project_id):
    empty_msg = html.P("Run an analysis to see results here.", className="text-muted")
    if not result_id or not project_id:
        return empty_msg, empty_msg, empty_msg, empty_msg

    from dash_app.api_client import workspace_result_detail, workspace_dataset_data

    try:
        detail = workspace_result_detail(project_id, result_id)
    except Exception as exc:
        err = dbc.Alert(f"Error loading result: {exc}", color="danger")
        return err, empty_msg, empty_msg, empty_msg

    summary = detail.get("summary", {})
    result_meta = detail.get("result", {})
    processing = detail.get("processing", {})
    rows = detail.get("rows_preview", [])

    # --- Metrics ---
    peak_count = summary.get("peak_count", 0)
    tg_count = summary.get("glass_transition_count", 0)
    tg_midpoint = summary.get("tg_midpoint")
    tg_onset = summary.get("tg_onset")
    tg_endset = summary.get("tg_endset")
    delta_cp = summary.get("delta_cp")

    tg_text = "Not detected"
    if tg_count > 0 and tg_midpoint is not None:
        tg_text = f"Tg mid: {tg_midpoint:.1f} C  |  Onset: {tg_onset:.1f} C  |  Endset: {tg_endset:.1f} C  |  dCp: {delta_cp:.4f}"

    metrics = html.Div(
        [
            html.H5("Result Summary", className="mb-3"),
            dbc.Row(
                [
                    dbc.Col(_metric_card("Peaks", str(peak_count)), md=3),
                    dbc.Col(_metric_card("Glass Transitions", str(tg_count)), md=3),
                    dbc.Col(_metric_card("Template", str(processing.get("workflow_template_label", "N/A"))), md=3),
                    dbc.Col(_metric_card("Status", str(result_meta.get("status", "N/A"))), md=3),
                ],
                className="g-3 mb-3",
            ),
            html.P(tg_text, className="mb-0"),
        ]
    )

    # --- Figure ---
    dataset_key = result_meta.get("dataset_key")
    figure_area = empty_msg
    if dataset_key:
        try:
            data_payload = workspace_dataset_data(project_id, dataset_key)
            data_rows = data_payload.get("rows", [])
            if data_rows and "temperature" in (data_payload.get("columns") or []):
                temperature = [r.get("temperature") for r in data_rows]
                signal = [r.get("signal") for r in data_rows]
                fig = go.Figure()
                fig.add_trace(
                    go.Scatter(
                        x=temperature,
                        y=signal,
                        mode="lines",
                        name="Raw Signal",
                        line=dict(color="#0E7490", width=1.5),
                    )
                )

                # Overlay peak markers
                for row in rows:
                    pt = row.get("peak_temperature")
                    if pt is not None:
                        idx = min(range(len(temperature)), key=lambda i: abs(temperature[i] - pt)) if temperature else None
                        if idx is not None:
                            fig.add_trace(
                                go.Scatter(
                                    x=[temperature[idx]],
                                    y=[signal[idx]],
                                    mode="markers",
                                    marker=dict(size=10, color="#B45309", symbol="diamond"),
                                    name=f"Peak {pt:.1f} C",
                                    showlegend=False,
                                )
                            )

                # Tg vertical lines
                if tg_count > 0 and tg_midpoint is not None:
                    fig.add_vline(x=tg_midpoint, line=dict(color="#EF4444", width=2, dash="dash"), annotation_text=f"Tg mid {tg_midpoint:.1f}")
                    if tg_onset is not None:
                        fig.add_vline(x=tg_onset, line=dict(color="#F59E0B", width=1, dash="dot"), annotation_text=f"Onset {tg_onset:.1f}")
                    if tg_endset is not None:
                        fig.add_vline(x=tg_endset, line=dict(color="#F59E0B", width=1, dash="dot"), annotation_text=f"Endset {tg_endset:.1f}")

                fig.update_layout(
                    title=f"DSC - {summary.get('sample_name', dataset_key)}",
                    template="plotly_white",
                    xaxis_title="Temperature (C)",
                    yaxis_title="Heat Flow (a.u.)",
                    margin=dict(l=56, r=24, t=56, b=48),
                    height=420,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                figure_area = dcc.Graph(figure=fig, config={"displaylogo": False, "responsive": True})
        except Exception:
            figure_area = dbc.Alert("Could not generate DSC figure.", color="warning")

    # --- Peak table ---
    if rows:
        table_area = html.Div(
            [
                html.H5("Detected Peaks", className="mb-3"),
                dataset_table(
                    rows,
                    ["peak_type", "peak_temperature", "onset_temperature", "endset_temperature", "area", "fwhm", "height"],
                    table_id="dsc-peaks-table",
                ),
            ]
        )
    else:
        table_area = html.Div([html.H5("Detected Peaks", className="mb-3"), html.P("No peaks detected.", className="text-muted")])

    # --- Processing info ---
    signal_pipeline = processing.get("signal_pipeline", {})
    analysis_steps = processing.get("analysis_steps", {})
    method_context = processing.get("method_context", {})
    proc_view = html.Div(
        [
            html.H5("Processing Details", className="mb-3"),
            html.P(f"Workflow: {processing.get('workflow_template_label', 'N/A')} (v{processing.get('workflow_template_version', '?')})"),
            html.P(f"Smoothing: {signal_pipeline.get('smoothing', {})}"),
            html.P(f"Baseline: {signal_pipeline.get('baseline', {})}"),
            html.P(f"Peak Detection: {analysis_steps.get('peak_detection', {})}"),
            html.P(f"Tg Detection: {analysis_steps.get('glass_transition', {})}"),
            html.P(f"Sign Convention: {method_context.get('sign_convention_label', 'N/A')}", className="mb-0"),
        ]
    )

    return metrics, figure_area, table_area, proc_view
