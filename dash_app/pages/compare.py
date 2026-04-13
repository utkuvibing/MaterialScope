"""Compare workspace core page -- raw overlay only, no batch runner."""

from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html
import plotly.graph_objects as go

from core.modalities import get_modality, stable_analysis_types
from dash_app.components.chrome import page_header
from dash_app.components.data_preview import dataset_table

dash.register_page(__name__, path="/compare", title="Compare - MaterialScope")


def _eligible_dataset(dataset: dict, analysis_type: str) -> bool:
    modality = get_modality(analysis_type)
    if modality is None:
        return False
    return modality.adapter.is_dataset_eligible(str(dataset.get("data_type") or "UNKNOWN"))


def _available_types(datasets: list[dict]) -> list[str]:
    options: list[str] = []
    for token in stable_analysis_types():
        if any(_eligible_dataset(dataset, token) for dataset in datasets):
            options.append(token)
    return options


layout = html.Div(
    [
        dcc.Store(id="compare-refresh", data=0),
        page_header(
            "Compare Workspace",
            "Build a raw overlay workspace for eligible runs without entering modality-specific analysis flows.",
            badge="Compare Core",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    dbc.Label("Analysis Type"),
                                    dbc.Select(id="compare-analysis-type"),
                                    dbc.Label("Selected Runs", className="mt-3"),
                                    dcc.Dropdown(id="compare-selected-runs", multi=True),
                                    dbc.Label("Workspace Notes", className="mt-3"),
                                    dbc.Textarea(id="compare-notes", style={"height": "140px"}),
                                    dbc.Button("Save Compare Workspace", id="save-compare-workspace-btn", color="primary", className="mt-3"),
                                    html.Div(id="compare-status", className="mt-3"),
                                ]
                            ),
                            className="mb-4",
                        ),
                        dbc.Card(dbc.CardBody(html.Div(id="compare-overlay-panel")), className="mb-4"),
                    ],
                    md=8,
                ),
                dbc.Col(
                    [
                        dbc.Card(dbc.CardBody(html.Div(id="compare-summary-panel")), className="mb-4"),
                        dbc.Card(dbc.CardBody(html.Div(id="compare-saved-result-preview")), className="mb-4"),
                    ],
                    md=4,
                ),
            ]
        ),
    ]
)


@callback(
    Output("compare-analysis-type", "options"),
    Output("compare-analysis-type", "value"),
    Output("compare-selected-runs", "options"),
    Output("compare-selected-runs", "value"),
    Output("compare-notes", "value"),
    Input("project-id", "data"),
    Input("compare-refresh", "data"),
    Input("workspace-refresh", "data"),
    prevent_initial_call=False,
)
def load_compare_workspace(project_id, _refresh, _global_refresh):
    if not project_id:
        return [], None, [], [], ""

    from dash_app.api_client import compare_workspace, workspace_datasets

    datasets = workspace_datasets(project_id).get("datasets", [])
    available_types = _available_types(datasets)
    if not available_types:
        return [], None, [], [], ""

    workspace = compare_workspace(project_id).get("compare_workspace", {})
    analysis_type = workspace.get("analysis_type")
    if analysis_type not in available_types:
        analysis_type = available_types[0]
    eligible = [item for item in datasets if _eligible_dataset(item, analysis_type)]
    run_options = [{"label": item.get("display_name", item.get("key")), "value": item.get("key")} for item in eligible]
    selected = [key for key in (workspace.get("selected_datasets") or []) if key in {item["value"] for item in run_options}]
    return (
        [{"label": token, "value": token} for token in available_types],
        analysis_type,
        run_options,
        selected,
        workspace.get("notes") or "",
    )


@callback(
    Output("compare-selected-runs", "options", allow_duplicate=True),
    Output("compare-selected-runs", "value", allow_duplicate=True),
    Input("compare-analysis-type", "value"),
    State("project-id", "data"),
    State("compare-selected-runs", "value"),
    prevent_initial_call=True,
)
def update_compare_eligible_runs(analysis_type, project_id, selected_runs):
    if not analysis_type or not project_id:
        raise dash.exceptions.PreventUpdate
    from dash_app.api_client import workspace_datasets

    datasets = workspace_datasets(project_id).get("datasets", [])
    eligible = [item for item in datasets if _eligible_dataset(item, analysis_type)]
    run_options = [{"label": item.get("display_name", item.get("key")), "value": item.get("key")} for item in eligible]
    allowed = {item["value"] for item in run_options}
    selected = [key for key in (selected_runs or []) if key in allowed]
    return run_options, selected


@callback(
    Output("compare-status", "children"),
    Output("compare-refresh", "data", allow_duplicate=True),
    Input("save-compare-workspace-btn", "n_clicks"),
    State("project-id", "data"),
    State("compare-analysis-type", "value"),
    State("compare-selected-runs", "value"),
    State("compare-notes", "value"),
    State("compare-refresh", "data"),
    prevent_initial_call=True,
)
def save_compare_workspace(n_clicks, project_id, analysis_type, selected_runs, notes, refresh_value):
    if not n_clicks or not project_id or not analysis_type:
        raise dash.exceptions.PreventUpdate
    from dash_app.api_client import update_compare_workspace

    try:
        update_compare_workspace(
            project_id,
            analysis_type=analysis_type,
            selected_datasets=selected_runs or [],
            notes=notes or "",
        )
    except Exception as exc:
        return dbc.Alert(f"Compare workspace save failed: {exc}", color="danger"), dash.no_update
    return dbc.Alert("Compare workspace saved.", color="success"), int(refresh_value or 0) + 1


@callback(
    Output("compare-overlay-panel", "children"),
    Output("compare-summary-panel", "children"),
    Output("compare-saved-result-preview", "children"),
    Input("project-id", "data"),
    Input("compare-analysis-type", "value"),
    Input("compare-selected-runs", "value"),
    Input("compare-refresh", "data"),
    prevent_initial_call=False,
)
def render_compare_workspace(project_id, analysis_type, selected_runs, _refresh):
    if not project_id:
        empty = html.P("No workspace active.", className="text-muted")
        return empty, empty, empty
    if not analysis_type:
        empty = html.P("Select an analysis type.", className="text-muted")
        return empty, empty, empty

    from dash_app.api_client import workspace_dataset_data, workspace_datasets, workspace_results

    datasets = {item.get("key"): item for item in workspace_datasets(project_id).get("datasets", [])}
    selected_runs = selected_runs or []
    results = workspace_results(project_id).get("results", [])
    result_keys = {
        item.get("dataset_key")
        for item in results
        if item.get("analysis_type") == analysis_type
    }

    if len(selected_runs) < 2:
        overlay = html.P("Select at least two runs to build an overlay workspace.", className="text-muted")
    else:
        fig = go.Figure()
        x_label = "Axis X"
        y_label = "Axis Y"
        for dataset_key in selected_runs:
            payload = workspace_dataset_data(project_id, dataset_key)
            rows = payload.get("rows", [])
            columns = payload.get("columns", [])
            x_column = "temperature" if "temperature" in columns else (columns[0] if columns else None)
            preferred_y = next((item for item in ["signal", "heat_flow", "mass_percent", "intensity", "absorbance"] if item in columns), None)
            y_column = preferred_y or (columns[1] if len(columns) > 1 else None)
            if x_column is None or y_column is None:
                continue
            x_label = x_column
            y_label = y_column
            x = [row.get(x_column) for row in rows]
            y = [row.get(y_column) for row in rows]
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=datasets.get(dataset_key, {}).get("display_name", dataset_key)))
        fig.update_layout(
            title=f"{analysis_type} Compare Workspace",
            xaxis_title=x_label,
            yaxis_title=y_label,
            template="plotly_white",
            margin=dict(l=48, r=24, t=56, b=48),
            height=420,
        )
        overlay = dcc.Graph(figure=fig, config={"displaylogo": False, "responsive": True})

    summary_rows = []
    for dataset_key in selected_runs:
        dataset = datasets.get(dataset_key) or {}
        summary_rows.append(
            {
                "run": dataset_key,
                "sample_name": dataset.get("sample_name"),
                "vendor": dataset.get("vendor"),
                "heating_rate": dataset.get("heating_rate"),
                "points": dataset.get("points"),
                "saved_result": "Yes" if dataset_key in result_keys else "No",
            }
        )
    summary = html.Div(
        [
            html.H5("Workspace Summary", className="mb-3"),
            dataset_table(summary_rows, ["run", "sample_name", "vendor", "heating_rate", "points", "saved_result"], table_id="compare-summary-table")
            if summary_rows
            else html.P("No runs selected yet.", className="text-muted"),
        ]
    )

    preview_rows = [
        {
            "id": item.get("id"),
            "dataset_key": item.get("dataset_key"),
            "status": item.get("status"),
            "saved_at_utc": item.get("saved_at_utc"),
        }
        for item in results
        if item.get("analysis_type") == analysis_type and item.get("dataset_key") in selected_runs
    ]
    preview = html.Div(
        [
            html.H5("Saved Result Preview", className="mb-3"),
            dataset_table(preview_rows, ["id", "dataset_key", "status", "saved_at_utc"], table_id="compare-result-preview-table")
            if preview_rows
            else html.P("No saved results for the selected runs yet.", className="text-muted"),
        ]
    )
    return overlay, summary, preview
