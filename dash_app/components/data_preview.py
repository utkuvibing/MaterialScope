"""Dash data preview helpers."""

from __future__ import annotations

import math
from typing import Any

import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html
import plotly.graph_objects as go

from dash_app.theme import apply_figure_theme


def metric_cards(detail: dict[str, Any]) -> dbc.Row:
    dataset = detail.get("dataset") or {}
    metadata = detail.get("metadata") or {}
    return dbc.Row(
        [
            dbc.Col(_metric_card("Data Type", dataset.get("data_type", "N/A")), md=3),
            dbc.Col(_metric_card("Points", str(dataset.get("points", 0))), md=3),
            dbc.Col(_metric_card("Vendor", dataset.get("vendor", "Generic")), md=3),
            dbc.Col(
                _metric_card(
                    "Heating Rate",
                    str(metadata.get("heating_rate") or "—"),
                ),
                md=3,
            ),
        ],
        className="g-3 mb-3",
    )


def dataset_table(rows: list[dict[str, Any]], columns: list[str], *, page_size: int = 10, table_id: str = "dataset-preview-table"):
    return html.Div(
        dash_table.DataTable(
            id=table_id,
            data=rows,
            columns=[{"name": column, "id": column} for column in columns],
            page_size=page_size,
            sort_action="native",
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "left", "padding": "0.5rem", "fontSize": "0.85rem"},
            style_header={"fontWeight": 700},
        ),
        className="ta-datatable",
    )


def metadata_list(detail: dict[str, Any]) -> html.Div:
    metadata = {
        key: value
        for key, value in (detail.get("metadata") or {}).items()
        if value not in (None, "", [])
    }
    if not metadata:
        return html.P("No metadata.", className="text-muted")
    return html.Ul([html.Li(f"{key}: {value}") for key, value in metadata.items()], className="mb-0")


def original_columns_list(detail: dict[str, Any]) -> html.Div:
    original_columns = detail.get("original_columns") or {}
    if not original_columns:
        return html.P("No column mapping stored.", className="text-muted")
    return html.Ul(
        [html.Li(f"{key} ← {value}") for key, value in original_columns.items()],
        className="mb-0",
    )


def quick_plot(rows: list[dict[str, Any]], detail: dict[str, Any], *, ui_theme: str | None = None):
    if not rows:
        return html.P("No data available for plotting.", className="text-muted")
    first = rows[0]
    if "temperature" not in first or "signal" not in first:
        return html.P("No standard temperature/signal axes available.", className="text-muted")

    x = [row.get("temperature") for row in rows]
    y = [row.get("signal") for row in rows]
    dataset = detail.get("dataset") or {}
    units = detail.get("units") or {}
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=dataset.get("display_name", "Signal")))
    fig.update_layout(
        title=f"{dataset.get('data_type', 'Data')} - {dataset.get('display_name', dataset.get('key', 'Dataset'))}",
        margin=dict(l=48, r=24, t=56, b=48),
        xaxis_title=f"Temperature ({units.get('temperature', '°C')})",
        yaxis_title=f"Signal ({units.get('signal', 'a.u.')})",
        height=360,
    )
    apply_figure_theme(fig, ui_theme)
    return dcc.Graph(figure=fig, config={"displaylogo": False, "responsive": True}, className="ta-plot")


def stats_table(rows: list[dict[str, Any]], columns: list[str]):
    if not rows:
        return html.P("No statistics available.", className="text-muted")
    numeric_rows: list[dict[str, float]] = []
    for row in rows:
        numeric_row: dict[str, float] = {}
        for column in columns:
            value = row.get(column)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isnan(value):
                numeric_row[column] = float(value)
        if numeric_row:
            numeric_rows.append(numeric_row)
    if not numeric_rows:
        return html.P("No numeric statistics available.", className="text-muted")
    import pandas as pd

    frame = pd.DataFrame(numeric_rows).describe().round(4).reset_index().rename(columns={"index": "stat"})
    return dataset_table(frame.to_dict(orient="records"), list(frame.columns), page_size=min(8, len(frame)), table_id="dataset-stats-table")


def _metric_card(label: str, value: str) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.Small(label, className="text-muted text-uppercase"),
                html.H4(value, className="mb-0"),
            ]
        )
    )
