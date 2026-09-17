"""Kinetic Analysis page (preview module) -- Kissinger, OFW, and Friedman.

Multi-heating-rate activation-energy workflow backed by the workspace API
(``POST /workspace/{project_id}/kinetics/run``). Scientific state lives in
the backend; this page only collects inputs and renders the saved record.

Honesty rules mirrored from the backend contract:
- heating-rate inputs are left blank when dataset metadata is not traceable
  (no 10 °C/min default);
- Kissinger peak temperatures are typed in or taken from a saved DSC peak
  table hint -- never prefilled with synthetic values;
- preview gating is enforced here and server-side.
"""

from __future__ import annotations

from typing import Any

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, callback, dash_table, dcc, html

from dash_app.components.analysis_page import (
    capture_result_figure_from_layout,
    empty_result_msg,
    metric_card,
)
from dash_app.components.chrome import page_header
from dash_app.components.figure_artifacts import (
    build_figure_artifacts_panel,
    prepare_result_graph_figure,
    result_graph_class,
    result_graph_config,
)
from dash_app.components.page_guidance import (
    guidance_block,
    next_step_block,
    prereq_or_empty_help,
    typical_workflow_block,
)
from dash_app.theme import apply_figure_theme
from core.units_dimensional import resolve_beta
from utils.i18n import normalize_ui_locale, translate_ui
from utils.runtime_flags import preview_modules_enabled

dash.register_page(__name__, path="/kinetics", title="Kinetic Analysis - MaterialScope")

_KINETICS_ELIGIBLE_TYPES = {"DSC", "TGA"}
_METHODS = ("kissinger", "ofw", "friedman")


def _loc(locale_data: str | None) -> str:
    return normalize_ui_locale(locale_data)


def _hidden(hidden: bool) -> dict[str, str]:
    return {"display": "none"} if hidden else {}


def _rate_hint(loc: str, meta_entry: dict[str, Any]) -> str:
    """Helper text under a per-dataset heating-rate input."""
    rate = (meta_entry or {}).get("heating_rate")
    source = (meta_entry or {}).get("heating_rate_source")
    beta, _withheld = resolve_beta(rate, source)
    if beta is not None:
        return translate_ui(loc, "dash.kinetics.rate_hint_metadata", value=beta, source=source)
    return translate_ui(loc, "dash.kinetics.rate_hint_missing")


def _peak_temperature_hint(
    loc: str,
    peaks: list[dict[str, Any]] | None,
) -> str:
    """Helper text under a Kissinger peak-temperature input."""
    usable = [
        p.get("peak_temperature")
        for p in (peaks or [])
        if isinstance(p, dict) and p.get("peak_temperature") is not None
    ]
    if len(usable) == 1:
        return translate_ui(loc, "dash.kinetics.tp_hint_single", value=f"{float(usable[0]):.2f}")
    if len(usable) > 1:
        return translate_ui(loc, "dash.kinetics.tp_hint_multi", count=len(usable))
    return translate_ui(loc, "dash.kinetics.tp_hint_required")


def _fmt(value: Any, digits: int = 2, suffix: str = "") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if number != number or number in (float("inf"), float("-inf")):
        return "N/A"
    return f"{number:.{digits}f}{suffix}"


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div(
    [
        dcc.Store(id="kinetics-refresh", data=0),
        dcc.Store(id="kinetics-latest-result-id"),
        dcc.Store(id="kinetics-figure-captured", data={}),
        dcc.Store(id="kinetics-dataset-meta", data={}),
        html.Div(id="kinetics-hero-slot"),
        html.Div(id="kinetics-guidance-slot", className="mb-2"),
        html.Div(id="kinetics-disabled-slot"),
        html.Div(
            id="kinetics-enabled-surface",
            children=[
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Card(
                                    dbc.CardBody(
                                        [
                                            html.H5(id="kinetics-setup-title", className="mb-3"),
                                            dbc.Label(id="kinetics-lbl-method"),
                                            dbc.RadioItems(
                                                id="kinetics-method",
                                                options=[
                                                    {"label": "Kissinger", "value": "kissinger"},
                                                    {"label": "OFW", "value": "ofw"},
                                                    {"label": "Friedman", "value": "friedman"},
                                                ],
                                                value="kissinger",
                                            ),
                                            html.Div(
                                                id="kinetics-input-mode-wrap",
                                                children=[
                                                    dbc.Label(id="kinetics-lbl-input-mode", className="mt-3"),
                                                    dbc.RadioItems(
                                                        id="kinetics-input-mode",
                                                        options=[
                                                            {"label": "—", "value": "datasets"},
                                                            {"label": "—", "value": "manual"},
                                                        ],
                                                        value="datasets",
                                                        inline=True,
                                                    ),
                                                ],
                                            ),
                                            html.Div(
                                                id="kinetics-datasets-panel",
                                                children=[
                                                    dbc.Label(id="kinetics-lbl-datasets", className="mt-3"),
                                                    dcc.Dropdown(
                                                        id="kinetics-dataset-select",
                                                        multi=True,
                                                        className="ta-dropdown",
                                                    ),
                                                    html.Div(id="kinetics-dataset-inputs", className="mt-2"),
                                                ],
                                            ),
                                            html.Div(
                                                id="kinetics-manual-panel",
                                                children=[
                                                    html.P(id="kinetics-manual-help", className="text-muted small mt-3"),
                                                    dash_table.DataTable(
                                                        id="kinetics-manual-table",
                                                        columns=[
                                                            {"name": "β (°C/min)", "id": "heating_rate", "type": "numeric"},
                                                            {"name": "Tp (°C)", "id": "peak_temperature", "type": "numeric"},
                                                        ],
                                                        data=[
                                                            {"heating_rate": None, "peak_temperature": None},
                                                            {"heating_rate": None, "peak_temperature": None},
                                                        ],
                                                        editable=True,
                                                        row_deletable=True,
                                                        style_table={"overflowX": "auto"},
                                                    ),
                                                    dbc.Button(
                                                        "",
                                                        id="kinetics-add-point-btn",
                                                        color="secondary",
                                                        outline=True,
                                                        size="sm",
                                                        className="mt-2",
                                                    ),
                                                ],
                                                style={"display": "none"},
                                            ),
                                        ]
                                    ),
                                    className="mb-4",
                                ),
                                dbc.Card(
                                    dbc.CardBody(
                                        [
                                            html.H5(id="kinetics-params-title", className="mb-3"),
                                            html.Div(
                                                id="kinetics-alpha-panel",
                                                children=[
                                                    dbc.Row(
                                                        [
                                                            dbc.Col(
                                                                [
                                                                    dbc.Label(id="kinetics-lbl-alpha-min"),
                                                                    dbc.Input(
                                                                        id="kinetics-alpha-min",
                                                                        type="number",
                                                                        value=0.10,
                                                                        min=0.01,
                                                                        max=0.99,
                                                                        step=0.01,
                                                                    ),
                                                                ]
                                                            ),
                                                            dbc.Col(
                                                                [
                                                                    dbc.Label(id="kinetics-lbl-alpha-max"),
                                                                    dbc.Input(
                                                                        id="kinetics-alpha-max",
                                                                        type="number",
                                                                        value=0.90,
                                                                        min=0.01,
                                                                        max=0.99,
                                                                        step=0.01,
                                                                    ),
                                                                ]
                                                            ),
                                                            dbc.Col(
                                                                [
                                                                    dbc.Label(id="kinetics-lbl-alpha-step"),
                                                                    dbc.Input(
                                                                        id="kinetics-alpha-step",
                                                                        type="number",
                                                                        value=0.05,
                                                                        min=0.01,
                                                                        max=0.5,
                                                                        step=0.01,
                                                                    ),
                                                                ]
                                                            ),
                                                        ],
                                                        className="g-2",
                                                    ),
                                                ],
                                                style={"display": "none"},
                                            ),
                                            dbc.Label(id="kinetics-lbl-confidence", className="mt-3"),
                                            dbc.Input(
                                                id="kinetics-confidence",
                                                type="number",
                                                value=0.95,
                                                min=0.5,
                                                max=0.999,
                                                step=0.01,
                                            ),
                                        ]
                                    ),
                                    className="mb-4",
                                ),
                                dbc.Card(
                                    dbc.CardBody(
                                        [
                                            html.H5(id="kinetics-run-title", className="mb-3"),
                                            html.Div(id="kinetics-run-status"),
                                            dbc.Button(
                                                "",
                                                id="kinetics-run-btn",
                                                color="primary",
                                                className="w-100",
                                            ),
                                        ]
                                    ),
                                    className="mb-4",
                                ),
                            ],
                            md=5,
                        ),
                        dbc.Col(
                            [
                                html.H5(id="kinetics-result-title", className="mb-3"),
                                dbc.Card(
                                    dbc.CardBody(html.Div(id="kinetics-result-metrics")),
                                    className="mb-4",
                                ),
                                dbc.Card(
                                    dbc.CardBody(html.Div(id="kinetics-result-figure")),
                                    className="mb-4",
                                ),
                                dbc.Card(
                                    dbc.CardBody(
                                        [
                                            dbc.Label(id="kinetics-lbl-iso-alpha"),
                                            dcc.Dropdown(
                                                id="kinetics-iso-alpha-select",
                                                clearable=False,
                                                className="ta-dropdown mb-2",
                                            ),
                                            html.Div(id="kinetics-iso-figure"),
                                        ]
                                    ),
                                    id="kinetics-iso-panel",
                                    className="mb-4",
                                    style={"display": "none"},
                                ),
                                dbc.Card(
                                    dbc.CardBody(html.Div(id="kinetics-result-table")),
                                    className="mb-4",
                                ),
                                dbc.Card(
                                    dbc.CardBody(html.Div(id="kinetics-result-scientific")),
                                    className="mb-4",
                                ),
                                dbc.Card(
                                    dbc.CardBody(html.Div(id="kinetics-figure-artifacts")),
                                    className="mb-4",
                                ),
                            ],
                            md=7,
                        ),
                    ]
                ),
            ],
        ),
    ]
)


# ---------------------------------------------------------------------------
# Chrome + gating
# ---------------------------------------------------------------------------


@callback(
    Output("kinetics-hero-slot", "children"),
    Output("kinetics-guidance-slot", "children"),
    Output("kinetics-setup-title", "children"),
    Output("kinetics-lbl-method", "children"),
    Output("kinetics-method", "options"),
    Output("kinetics-lbl-input-mode", "children"),
    Output("kinetics-input-mode", "options"),
    Output("kinetics-lbl-datasets", "children"),
    Output("kinetics-params-title", "children"),
    Output("kinetics-lbl-alpha-min", "children"),
    Output("kinetics-lbl-alpha-max", "children"),
    Output("kinetics-lbl-alpha-step", "children"),
    Output("kinetics-lbl-confidence", "children"),
    Output("kinetics-manual-help", "children"),
    Output("kinetics-add-point-btn", "children"),
    Output("kinetics-run-title", "children"),
    Output("kinetics-run-btn", "children"),
    Output("kinetics-result-title", "children"),
    Output("kinetics-lbl-iso-alpha", "children"),
    Input("ui-locale", "data"),
    prevent_initial_call=False,
)
def render_kinetics_chrome(locale_data):
    loc = _loc(locale_data)
    hero = page_header(
        translate_ui(loc, "dash.kinetics.title"),
        translate_ui(loc, "dash.kinetics.caption"),
        badge=translate_ui(loc, "dash.kinetics.badge"),
    )
    guidance = html.Div(
        [
            guidance_block(
                translate_ui(loc, "dash.kinetics.guidance_what_title"),
                body=translate_ui(loc, "dash.kinetics.guidance_what_body"),
            ),
            typical_workflow_block(
                [
                    translate_ui(loc, "dash.kinetics.workflow_step1"),
                    translate_ui(loc, "dash.kinetics.workflow_step2"),
                    translate_ui(loc, "dash.kinetics.workflow_step3"),
                ],
                locale=loc,
            ),
            guidance_block(
                translate_ui(loc, "dash.kinetics.usage_title"),
                bullets=[
                    translate_ui(loc, "dash.kinetics.usage_bullet1"),
                    translate_ui(loc, "dash.kinetics.usage_bullet2"),
                ],
                tone="secondary",
            ),
            next_step_block(translate_ui(loc, "dash.kinetics.next_step_body"), locale=loc),
        ]
    )
    method_options = [
        {"label": translate_ui(loc, "dash.kinetics.method.kissinger"), "value": "kissinger"},
        {"label": translate_ui(loc, "dash.kinetics.method.ofw"), "value": "ofw"},
        {"label": translate_ui(loc, "dash.kinetics.method.friedman"), "value": "friedman"},
    ]
    mode_options = [
        {"label": translate_ui(loc, "dash.kinetics.mode.datasets"), "value": "datasets"},
        {"label": translate_ui(loc, "dash.kinetics.mode.manual"), "value": "manual"},
    ]
    return (
        hero,
        guidance,
        translate_ui(loc, "dash.kinetics.setup_title"),
        translate_ui(loc, "dash.kinetics.label_method"),
        method_options,
        translate_ui(loc, "dash.kinetics.label_input_mode"),
        mode_options,
        translate_ui(loc, "dash.kinetics.label_datasets"),
        translate_ui(loc, "dash.kinetics.params_title"),
        translate_ui(loc, "dash.kinetics.label_alpha_min"),
        translate_ui(loc, "dash.kinetics.label_alpha_max"),
        translate_ui(loc, "dash.kinetics.label_alpha_step"),
        translate_ui(loc, "dash.kinetics.label_confidence"),
        translate_ui(loc, "dash.kinetics.manual_table_help"),
        translate_ui(loc, "dash.kinetics.btn_add_point"),
        translate_ui(loc, "dash.kinetics.run_title"),
        translate_ui(loc, "dash.kinetics.btn_run"),
        translate_ui(loc, "dash.kinetics.result_title"),
        translate_ui(loc, "dash.kinetics.table.alpha"),
    )


@callback(
    Output("kinetics-enabled-surface", "style"),
    Output("kinetics-disabled-slot", "children"),
    Input("ui-locale", "data"),
    prevent_initial_call=False,
)
def gate_kinetics_page(locale_data):
    """Preview gate: hide the workflow and block execution when disabled."""
    loc = _loc(locale_data)
    if preview_modules_enabled():
        return {}, ""
    disabled = prereq_or_empty_help(
        translate_ui(loc, "dash.kinetics.disabled_body"),
        title=translate_ui(loc, "dash.kinetics.disabled_title"),
        locale=loc,
    )
    return {"display": "none"}, disabled


@callback(
    Output("kinetics-input-mode-wrap", "style"),
    Output("kinetics-alpha-panel", "style"),
    Input("kinetics-method", "value"),
)
def toggle_method_panels(method):
    is_kissinger = str(method or "kissinger") == "kissinger"
    return _hidden(not is_kissinger), _hidden(is_kissinger)


@callback(
    Output("kinetics-datasets-panel", "style"),
    Output("kinetics-manual-panel", "style"),
    Input("kinetics-method", "value"),
    Input("kinetics-input-mode", "value"),
)
def toggle_input_panels(method, input_mode):
    manual = str(method or "") == "kissinger" and str(input_mode or "datasets") == "manual"
    return _hidden(manual), _hidden(not manual)


# ---------------------------------------------------------------------------
# Dataset selection + per-dataset input rows
# ---------------------------------------------------------------------------


@callback(
    Output("kinetics-dataset-select", "options"),
    Output("kinetics-dataset-meta", "data"),
    Input("project-id", "data"),
    Input("kinetics-refresh", "data"),
    Input("workspace-refresh", "data"),
    prevent_initial_call=False,
)
def load_kinetics_datasets(project_id, _refresh, _workspace_refresh):
    if not project_id:
        return [], {}

    from dash_app.api_client import workspace_datasets

    try:
        payload = workspace_datasets(project_id)
    except Exception:
        return [], {}

    options: list[dict[str, str]] = []
    meta: dict[str, dict[str, Any]] = {}
    for item in payload.get("datasets", []) or []:
        data_type = str(item.get("data_type") or "").upper()
        if data_type not in _KINETICS_ELIGIBLE_TYPES:
            continue
        key = str(item.get("key"))
        options.append(
            {
                "label": f"{item.get('display_name', key)} ({data_type})",
                "value": key,
            }
        )
        meta[key] = {
            "display_name": item.get("display_name", key),
            "data_type": data_type,
            "heating_rate": item.get("heating_rate"),
            "heating_rate_source": item.get("heating_rate_source"),
        }
    return options, meta


@callback(
    Output("kinetics-dataset-inputs", "children"),
    Input("kinetics-dataset-select", "value"),
    Input("kinetics-method", "value"),
    Input("ui-locale", "data"),
    State("kinetics-dataset-meta", "data"),
    State("project-id", "data"),
    prevent_initial_call=False,
)
def render_dataset_inputs(selected, method, locale_data, dataset_meta, project_id):
    loc = _loc(locale_data)
    keys = [str(k) for k in (selected or [])]
    if not keys:
        return html.P(
            translate_ui(loc, "dash.kinetics.select_datasets_hint"),
            className="text-muted small",
        )

    method_id = str(method or "kissinger")
    need_tp = method_id == "kissinger"

    peak_counts: dict[str, list[dict[str, Any]]] = {}
    if need_tp and project_id:
        from dash_app.api_client import analysis_state_curves

        for key in keys:
            if str((dataset_meta or {}).get(key, {}).get("data_type") or "").upper() != "DSC":
                continue
            try:
                curves = analysis_state_curves(project_id, "DSC", key)
            except Exception:
                curves = {}
            peak_counts[key] = curves.get("peaks") or []

    rows: list[Any] = []
    for key in keys:
        entry = (dataset_meta or {}).get(key) or {}
        data_type = str(entry.get("data_type") or "").upper()
        name = entry.get("display_name") or key
        children: list[Any] = [
            html.Div(f"{name} ({data_type})", className="fw-semibold small mb-1"),
            dbc.Label(translate_ui(loc, "dash.kinetics.rate_label"), className="small mb-0"),
            dbc.Input(
                id={"type": "kinetics-rate-input", "index": key},
                type="number",
                min=0,
                step=0.1,
                size="sm",
                placeholder="—",
            ),
            html.Small(_rate_hint(loc, entry), className="text-muted d-block mb-2"),
        ]
        if need_tp:
            children.extend(
                [
                    dbc.Label(translate_ui(loc, "dash.kinetics.tp_label"), className="small mb-0"),
                    dbc.Input(
                        id={"type": "kinetics-tp-input", "index": key},
                        type="number",
                        step=0.1,
                        size="sm",
                        placeholder="—",
                    ),
                    html.Small(
                        _peak_temperature_hint(loc, peak_counts.get(key)),
                        className="text-muted d-block mb-2",
                    ),
                ]
            )
        rows.append(html.Div(children, className="border rounded p-2 mb-2"))
    return rows


@callback(
    Output("kinetics-manual-table", "data", allow_duplicate=True),
    Input("kinetics-add-point-btn", "n_clicks"),
    State("kinetics-manual-table", "data"),
    prevent_initial_call=True,
)
def add_manual_point(n_clicks, data):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    rows = list(data or [])
    rows.append({"heating_rate": None, "peak_temperature": None})
    return rows


# ---------------------------------------------------------------------------
# Run + result rendering
# ---------------------------------------------------------------------------


def _number_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


@callback(
    Output("kinetics-run-status", "children"),
    Output("kinetics-refresh", "data", allow_duplicate=True),
    Output("kinetics-latest-result-id", "data", allow_duplicate=True),
    Output("workspace-refresh", "data", allow_duplicate=True),
    Input("kinetics-run-btn", "n_clicks"),
    State("project-id", "data"),
    State("kinetics-method", "value"),
    State("kinetics-input-mode", "value"),
    State("kinetics-dataset-select", "value"),
    State({"type": "kinetics-rate-input", "index": ALL}, "value"),
    State({"type": "kinetics-rate-input", "index": ALL}, "id"),
    State({"type": "kinetics-tp-input", "index": ALL}, "value"),
    State({"type": "kinetics-tp-input", "index": ALL}, "id"),
    State("kinetics-manual-table", "data"),
    State("kinetics-alpha-min", "value"),
    State("kinetics-alpha-max", "value"),
    State("kinetics-alpha-step", "value"),
    State("kinetics-confidence", "value"),
    State("kinetics-refresh", "data"),
    State("workspace-refresh", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def run_kinetics(
    n_clicks,
    project_id,
    method,
    input_mode,
    selected_datasets,
    rate_values,
    rate_ids,
    tp_values,
    tp_ids,
    manual_rows,
    alpha_min,
    alpha_max,
    alpha_step,
    confidence,
    refresh_val,
    global_refresh,
    locale_data,
):
    loc = _loc(locale_data)
    if not n_clicks or not project_id:
        raise dash.exceptions.PreventUpdate
    if not preview_modules_enabled():
        alert = dbc.Alert(
            translate_ui(loc, "dash.kinetics.disabled_body"),
            color="warning",
        )
        return alert, dash.no_update, dash.no_update, dash.no_update

    method_id = str(method or "kissinger")
    payload: dict[str, Any] = {"method": method_id, "confidence_level": _number_or_none(confidence)}
    if method_id == "kissinger":
        payload["input_mode"] = str(input_mode or "datasets")

    if method_id == "kissinger" and payload["input_mode"] == "manual":
        points = []
        for row in manual_rows or []:
            if not isinstance(row, dict):
                continue
            rate = _number_or_none(row.get("heating_rate"))
            temp = _number_or_none(row.get("peak_temperature"))
            if rate is None and temp is None:
                continue
            points.append({"heating_rate": rate, "peak_temperature": temp})
        payload["manual_points"] = points
    else:
        rate_by_key = {
            str(item.get("index")): _number_or_none(value)
            for item, value in zip(rate_ids or [], rate_values or [])
            if isinstance(item, dict)
        }
        tp_by_key = {
            str(item.get("index")): _number_or_none(value)
            for item, value in zip(tp_ids or [], tp_values or [])
            if isinstance(item, dict)
        }
        payload["dataset_selections"] = [
            {
                "dataset_key": key,
                "heating_rate": rate_by_key.get(key),
                "peak_temperature": tp_by_key.get(key) if method_id == "kissinger" else None,
            }
            for key in (selected_datasets or [])
        ]
        if method_id != "kissinger":
            payload["alpha_min"] = _number_or_none(alpha_min)
            payload["alpha_max"] = _number_or_none(alpha_max)
            payload["alpha_step"] = _number_or_none(alpha_step)

    from dash_app.api_client import kinetics_run

    try:
        response = kinetics_run(project_id, payload)
    except Exception as exc:
        return (
            dbc.Alert(
                translate_ui(loc, "dash.kinetics.run_failed", error=str(exc)),
                color="danger",
            ),
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )

    result_id = response.get("result_id")
    alert = dbc.Alert(
        translate_ui(loc, "dash.kinetics.run_saved", rid=result_id),
        color="success",
    )
    return (
        alert,
        int(refresh_val or 0) + 1,
        result_id,
        int(global_refresh or 0) + 1,
    )


def _ci_text(summary: dict[str, Any], loc: str) -> str | None:
    status = str(summary.get("ea_ci_status") or "")
    if status == "computed" and summary.get("activation_energy_ci_low_kj_mol") is not None:
        level = summary.get("confidence_level")
        level_label = f"{float(level) * 100:.0f}%" if isinstance(level, (int, float)) else "95%"
        return (
            f"{translate_ui(loc, 'dash.kinetics.ci_label', level=level_label)}: "
            f"[{_fmt(summary.get('activation_energy_ci_low_kj_mol'), 1)}, "
            f"{_fmt(summary.get('activation_energy_ci_high_kj_mol'), 1)}] kJ/mol"
        )
    if status == "withheld":
        return translate_ui(
            loc,
            "dash.kinetics.ci_withheld",
            reason=summary.get("ea_ci_withheld_reason") or "—",
        )
    return None


def _metrics_panel(summary: dict[str, Any], method_id: str, loc: str) -> html.Div:
    pairs: list[tuple[str, str]] = []
    if method_id == "kissinger":
        pairs.append((translate_ui(loc, "dash.kinetics.metric.ea"), f"{_fmt(summary.get('activation_energy_kj_mol'), 1)} kJ/mol"))
        pairs.append((translate_ui(loc, "dash.kinetics.metric.r2"), _fmt(summary.get("r_squared"), 4)))
        pairs.append((translate_ui(loc, "dash.kinetics.metric.points"), str(summary.get("n_points") or "—")))
        intercept = summary.get("regression_intercept")
        if intercept is not None:
            pairs.append((translate_ui(loc, "dash.kinetics.intercept_label"), _fmt(intercept, 2)))
        if summary.get("ln_a_min_inv") is not None:
            pairs.append((translate_ui(loc, "dash.kinetics.ln_a_label"), _fmt(summary.get("ln_a_min_inv"), 2)))
    else:
        pairs.append(
            (
                translate_ui(loc, "dash.kinetics.metric.ea_range"),
                f"{_fmt(summary.get('activation_energy_min_kj_mol'), 1)} – "
                f"{_fmt(summary.get('activation_energy_max_kj_mol'), 1)} kJ/mol",
            )
        )
        pairs.append(
            (
                translate_ui(loc, "dash.kinetics.metric.ea_mean"),
                f"{_fmt(summary.get('activation_energy_mean_kj_mol'), 1)} kJ/mol",
            )
        )
        pairs.append((translate_ui(loc, "dash.kinetics.metric.r2"), _fmt(summary.get("mean_r_squared"), 4)))
        pairs.append(
            (
                translate_ui(loc, "dash.kinetics.metric.conversion_points"),
                str(summary.get("conversion_point_count") or "—"),
            )
        )
    cards = [dbc.Col(metric_card(label, value)) for label, value in pairs]
    return html.Div(dbc.Row(cards, className="g-3"))


def _kissinger_figure(plot: dict[str, Any], summary: dict[str, Any], ui_theme: str, loc: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=plot.get("inv_tp") or [],
            y=plot.get("ln_beta_tp2") or [],
            mode="markers",
            name=translate_ui(loc, "dash.kinetics.series_observed"),
            marker=dict(size=9, color="#2563EB"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=plot.get("x_fit") or [],
            y=plot.get("y_fit") or [],
            mode="lines",
            name=translate_ui(loc, "dash.kinetics.series_fit"),
            line=dict(color="#111827", width=2),
        )
    )
    ea = _fmt(summary.get("activation_energy_kj_mol"), 1)
    r2 = _fmt(summary.get("r_squared"), 4)
    fig.update_layout(
        title=f"Kissinger — Ea = {ea} kJ/mol, R² = {r2}",
        xaxis_title=plot.get("xlabel") or "1/Tp (K⁻¹)",
        yaxis_title=plot.get("ylabel") or "ln(β / Tp²)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=64, r=28, t=72, b=58),
    )
    apply_figure_theme(fig, ui_theme)
    return fig


def _isoconversional_figure(rows: list[dict[str, Any]], ui_theme: str, loc: str) -> go.Figure:
    alphas: list[float] = []
    eas: list[float] = []
    err_minus: list[float] = []
    err_plus: list[float] = []
    for row in rows or []:
        alpha = row.get("alpha")
        ea = row.get("activation_energy_kj_mol")
        if alpha is None or ea is None:
            continue
        alphas.append(float(alpha))
        eas.append(float(ea))
        low = row.get("activation_energy_ci_low_kj_mol")
        high = row.get("activation_energy_ci_high_kj_mol")
        if low is None or high is None:
            err_minus.append(0.0)
            err_plus.append(0.0)
        else:
            err_minus.append(max(0.0, float(ea) - float(low)))
            err_plus.append(max(0.0, float(high) - float(ea)))
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=alphas,
            y=eas,
            mode="lines+markers",
            name="Ea",
            error_y=dict(type="data", symmetric=False, array=err_plus, arrayminus=err_minus, visible=True),
            marker=dict(size=8, color="#2563EB"),
            line=dict(color="#2563EB", width=2),
        )
    )
    fig.update_layout(
        title=translate_ui(loc, "dash.kinetics.ea_vs_alpha_title"),
        xaxis_title="Conversion α",
        yaxis_title="Ea (kJ/mol)",
        hovermode="x unified",
        margin=dict(l=64, r=28, t=72, b=58),
    )
    apply_figure_theme(fig, ui_theme)
    return fig


def _per_alpha_figure(plot: dict[str, Any], row: dict[str, Any] | None, ui_theme: str, loc: str, method_label: str) -> go.Figure:
    fig = go.Figure()
    x_obs = plot.get("inv_t") or plot.get("inv_tp") or []
    y_obs = plot.get("log_beta") or plot.get("ln_dalpha_dt") or plot.get("ln_beta_tp2") or []
    fig.add_trace(
        go.Scatter(
            x=x_obs,
            y=y_obs,
            mode="markers",
            name=translate_ui(loc, "dash.kinetics.series_observed"),
            marker=dict(size=9, color="#2563EB"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=plot.get("x_fit") or [],
            y=plot.get("y_fit") or [],
            mode="lines",
            name=translate_ui(loc, "dash.kinetics.series_fit"),
            line=dict(color="#111827", width=2),
        )
    )
    alpha = plot.get("alpha")
    ea = _fmt((row or {}).get("activation_energy_kj_mol"), 1)
    fig.update_layout(
        title=f"{method_label} — α = {_fmt(alpha, 2)}, Ea = {ea} kJ/mol",
        xaxis_title=plot.get("xlabel") or "1/T (K⁻¹)",
        yaxis_title=plot.get("ylabel") or "",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=64, r=28, t=72, b=58),
    )
    apply_figure_theme(fig, ui_theme)
    return fig


def _result_table(rows: list[dict[str, Any]], method_id: str, loc: str) -> Any:
    if method_id == "kissinger":
        return html.P(translate_ui(loc, "dash.kinetics.intercept_semantics_title"), className="text-muted small")
    if not rows:
        return empty_result_msg(locale_data=loc)
    header = html.Thead(
        html.Tr(
            [
                html.Th(translate_ui(loc, "dash.kinetics.table.alpha")),
                html.Th(translate_ui(loc, "dash.kinetics.table.ea")),
                html.Th(translate_ui(loc, "dash.kinetics.table.ci_low")),
                html.Th(translate_ui(loc, "dash.kinetics.table.ci_high")),
                html.Th(translate_ui(loc, "dash.kinetics.table.r2")),
                html.Th(translate_ui(loc, "dash.kinetics.table.n")),
                html.Th(translate_ui(loc, "dash.kinetics.table.ci_status")),
            ]
        )
    )
    body_rows = []
    for row in rows:
        ci_status = row.get("ea_ci_status") or ""
        status_text = (
            str(row.get("ea_ci_withheld_reason") or "withheld")
            if ci_status == "withheld"
            else ci_status
        )
        body_rows.append(
            html.Tr(
                [
                    html.Td(_fmt(row.get("alpha"), 3)),
                    html.Td(_fmt(row.get("activation_energy_kj_mol"), 1)),
                    html.Td(_fmt(row.get("activation_energy_ci_low_kj_mol"), 1)),
                    html.Td(_fmt(row.get("activation_energy_ci_high_kj_mol"), 1)),
                    html.Td(_fmt(row.get("r_squared"), 4)),
                    html.Td(str(row.get("n_points") or "—")),
                    html.Td(html.Small(status_text, className="text-muted")),
                ]
            )
        )
    return dbc.Table(
        [header, html.Tbody(body_rows)],
        bordered=True,
        hover=True,
        responsive=True,
        size="sm",
    )


def _scientific_panel(
    detail: dict[str, Any],
    method_id: str,
    loc: str,
) -> html.Div:
    summary = detail.get("summary") or {}
    processing = detail.get("processing") or {}
    provenance = detail.get("provenance") or {}
    context = detail.get("scientific_context") or {}

    children: list[Any] = []

    semantics = summary.get("intercept_semantics") or (context.get("methodology") or {}).get("intercept_semantics")
    if semantics:
        children.append(
            html.P(
                f"{translate_ui(loc, 'dash.kinetics.intercept_semantics_title')}: {semantics}",
                className="small",
            )
        )

    ci_method = summary.get("ea_ci_method") or (context.get("methodology") or {}).get("ea_ci_method")
    ci_scope = summary.get("ea_ci_scope") or (context.get("methodology") or {}).get("ea_ci_scope")
    assumptions = summary.get("ea_ci_ols_assumptions") or (context.get("methodology") or {}).get("ea_ci_ols_assumptions")
    limitations = [item for item in (context.get("limitations") or []) if item]
    limit_children: list[Any] = []
    for text in [ci_method, ci_scope, assumptions, *limitations]:
        if text:
            limit_children.append(html.Li(str(text), className="small"))
    if limit_children:
        children.append(
            html.Details(
                [
                    html.Summary(translate_ui(loc, "dash.kinetics.limitations_title"), className="small text-muted"),
                    html.Ul(limit_children, className="mt-2 mb-0 ps-3"),
                ],
                className="mb-2",
            )
        )

    inputs = processing.get("inputs") or []
    prov_lines: list[Any] = [
        html.P(f"method: {processing.get('method') or method_id}", className="small mb-1"),
        html.P(f"input_mode: {processing.get('input_mode') or 'datasets'}", className="small mb-1"),
    ]
    alpha_grid = processing.get("alpha_grid")
    if isinstance(alpha_grid, dict) and alpha_grid:
        prov_lines.append(
            html.P(
                f"alpha grid: min={alpha_grid.get('alpha_min')}, max={alpha_grid.get('alpha_max')}, "
                f"step={alpha_grid.get('alpha_step')}",
                className="small mb-1",
            )
        )
    if processing.get("dalpha_dt_derivation"):
        prov_lines.append(
            html.P(f"dα/dt: {processing['dalpha_dt_derivation']}", className="small mb-1")
        )
    prov_lines.append(
        html.P(
            f"confidence_level: {processing.get('confidence_level')}",
            className="small mb-1",
        )
    )
    for entry in inputs:
        bits = [f"dataset={entry.get('dataset_key')}", f"β={entry.get('heating_rate')} ({entry.get('heating_rate_source')})"]
        if entry.get("peak_temperature") is not None:
            bits.append(f"Tp={entry.get('peak_temperature')} °C ({entry.get('peak_temperature_source')})")
        if entry.get("signal_basis"):
            bits.append(f"signal={entry.get('signal_basis')}")
        prov_lines.append(html.P("; ".join(str(b) for b in bits), className="small mb-1"))
    if provenance.get("saved_at_utc"):
        prov_lines.append(html.P(f"saved_at_utc: {provenance['saved_at_utc']}", className="small mb-0"))
    children.append(
        html.Details(
            [
                html.Summary(translate_ui(loc, "dash.kinetics.provenance_title"), className="small text-muted"),
                html.Div(prov_lines, className="mt-2"),
            ],
            className="mb-0",
            open=True,
        )
    )
    return html.Div(children)


@callback(
    Output("kinetics-result-metrics", "children"),
    Output("kinetics-result-figure", "children"),
    Output("kinetics-result-table", "children"),
    Output("kinetics-result-scientific", "children"),
    Output("kinetics-iso-panel", "style"),
    Output("kinetics-iso-alpha-select", "options"),
    Output("kinetics-iso-alpha-select", "value"),
    Input("kinetics-latest-result-id", "data"),
    Input("kinetics-refresh", "data"),
    Input("ui-theme", "data"),
    Input("ui-locale", "data"),
    State("project-id", "data"),
    prevent_initial_call=False,
)
def display_kinetics_result(result_id, _refresh, ui_theme, locale_data, project_id):
    loc = _loc(locale_data)
    empty = empty_result_msg(locale_data=locale_data)
    if not result_id or not project_id:
        return empty, empty, empty, empty, _hidden(True), [], None

    from dash_app.api_client import workspace_result_detail

    try:
        detail = workspace_result_detail(project_id, result_id)
    except Exception as exc:
        err = dbc.Alert(str(exc), color="danger")
        return err, empty, empty, empty, _hidden(True), [], None

    summary = detail.get("summary") or {}
    processing = detail.get("processing") or {}
    method_id = str(processing.get("kinetics_method") or "").strip() or "kissinger"
    rows = detail.get("rows") or []
    report_payload = detail.get("report_payload") or {}
    plots = report_payload.get("plots") or []

    metrics = html.Div(
        [
            _metrics_panel(summary, method_id, loc),
            html.P(_ci_text(summary, loc) or "", className="small text-muted mt-2 mb-0"),
        ]
    )

    if method_id == "kissinger" and plots:
        fig = _kissinger_figure(plots[0], summary, ui_theme, loc)
        figure_area = dcc.Graph(
            figure=prepare_result_graph_figure(fig),
            className=result_graph_class(),
            config=result_graph_config(),
            style={"height": "520px"},
        )
    elif rows:
        fig = _isoconversional_figure(rows, ui_theme, loc)
        figure_area = dcc.Graph(
            figure=prepare_result_graph_figure(fig),
            className=result_graph_class(),
            config=result_graph_config(),
            style={"height": "520px"},
        )
    else:
        figure_area = empty

    iso_style = _hidden(method_id == "kissinger" or not plots)
    alpha_options = []
    if method_id != "kissinger":
        for row in rows:
            alpha = row.get("alpha")
            if alpha is not None:
                alpha_options.append({"label": f"α = {float(alpha):.3f}", "value": str(alpha)})
    alpha_value = alpha_options[0]["value"] if alpha_options else None

    table_area = _result_table(rows, method_id, loc)
    scientific = _scientific_panel(detail, method_id, loc)
    return metrics, figure_area, table_area, scientific, iso_style, alpha_options, alpha_value


@callback(
    Output("kinetics-iso-figure", "children"),
    Input("kinetics-iso-alpha-select", "value"),
    Input("ui-theme", "data"),
    Input("ui-locale", "data"),
    State("kinetics-latest-result-id", "data"),
    State("project-id", "data"),
    prevent_initial_call=False,
)
def render_iso_fit(selected_alpha, ui_theme, locale_data, result_id, project_id):
    loc = _loc(locale_data)
    if not selected_alpha or not result_id or not project_id:
        raise dash.exceptions.PreventUpdate

    from dash_app.api_client import workspace_result_detail

    try:
        detail = workspace_result_detail(project_id, result_id)
    except Exception:
        raise dash.exceptions.PreventUpdate

    processing = detail.get("processing") or {}
    method_id = str(processing.get("kinetics_method") or "")
    method_label = str(processing.get("method") or method_id)
    rows = detail.get("rows") or []
    plots = (detail.get("report_payload") or {}).get("plots") or []

    try:
        target = float(selected_alpha)
    except (TypeError, ValueError):
        raise dash.exceptions.PreventUpdate

    plot = None
    for item in plots:
        if abs(float(item.get("alpha", -1.0)) - target) < 1e-9:
            plot = item
            break
    if plot is None:
        raise dash.exceptions.PreventUpdate
    row = next(
        (r for r in rows if r.get("alpha") is not None and abs(float(r["alpha"]) - target) < 1e-9),
        None,
    )
    fig = _per_alpha_figure(plot, row, ui_theme, loc, method_label)
    return dcc.Graph(
        figure=prepare_result_graph_figure(fig),
        className=result_graph_class(),
        config=result_graph_config(),
        style={"height": "420px"},
    )


@callback(
    Output("kinetics-figure-captured", "data"),
    Input("kinetics-latest-result-id", "data"),
    Input("kinetics-result-figure", "children"),
    State("project-id", "data"),
    State("kinetics-figure-captured", "data"),
    prevent_initial_call=True,
)
def capture_kinetics_figure(result_id, figure_children, project_id, captured):
    return capture_result_figure_from_layout(
        result_id=result_id,
        project_id=project_id,
        figure_children=figure_children,
        captured=captured,
        analysis_type="KINETICS",
    )


@callback(
    Output("kinetics-figure-artifacts", "children"),
    Input("kinetics-latest-result-id", "data"),
    Input("kinetics-figure-captured", "data"),
    Input("ui-locale", "data"),
    State("project-id", "data"),
    prevent_initial_call=False,
)
def render_figure_artifacts(result_id, _captured, locale_data, project_id):
    loc = _loc(locale_data)
    if not result_id or not project_id:
        return build_figure_artifacts_panel(None, loc)

    from dash_app.api_client import workspace_result_detail

    try:
        detail = workspace_result_detail(project_id, result_id)
    except Exception:
        return build_figure_artifacts_panel(None, loc)
    return build_figure_artifacts_panel(detail.get("figure_artifacts") or {}, loc)
