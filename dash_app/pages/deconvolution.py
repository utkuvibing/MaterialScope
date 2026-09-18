"""Peak Deconvolution page (preview module).

Workspace-backed multi-component peak fitting via
``POST /workspace/{project_id}/deconvolution/run``. Scientific state lives in
the backend; this page collects inputs and renders the saved record from its
persisted ``report_payload`` (no lmfit call and no re-fit on the client).

Honesty rules mirrored from the backend contract:

- the axis label, unit and component units come from the effective axis
  resolved by the backend — never from a hardcoded temperature assumption;
- a signal basis that does not exist is shown as unavailable with its reason
  and blocks the run; raw is never substituted;
- lmfit's ``amplitude`` is presented as an integrated area parameter, with
  ``height`` and ``fwhm`` in their own columns;
- inversion is explicit and never enabled automatically;
- blank initial-guess fields mean "automatic estimate" and are recorded as
  ``auto``, not as user input.
"""

from __future__ import annotations

from typing import Any

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, callback, dcc, html

from dash_app.components.analysis_page import (
    capture_result_figure_from_layout,
    empty_result_msg,
    metrics_row,
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
from utils.i18n import normalize_ui_locale, translate_ui
from utils.runtime_flags import preview_modules_enabled

dash.register_page(__name__, path="/deconvolution", title="Peak Deconvolution - MaterialScope")

_ELIGIBLE_TYPES = {"DSC", "DTA", "TGA", "FTIR", "RAMAN", "XRD"}
_PEAK_SHAPES = ("gaussian", "lorentzian", "pseudo_voigt")
_MIN_PEAKS = 1
_MAX_PEAKS = 10
# Vega tableau-10: distinguishable in both the light and dark Plotly templates.
_COMPONENT_COLORS = (
    "#4C78A8",
    "#F58518",
    "#54A24B",
    "#E45756",
    "#B279A2",
    "#72B7B2",
    "#EECA3B",
    "#FF9DA6",
    "#9D755D",
    "#BAB0AC",
)


def _loc(locale_data: str | None) -> str:
    return normalize_ui_locale(locale_data)


def _hidden(hidden: bool) -> dict[str, str]:
    return {"display": "none"} if hidden else {}


def _fmt(value: Any, digits: int = 5) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if number != number or number in (float("inf"), float("-inf")):
        return "N/A"
    return f"{number:.{digits}g}"


def _number_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _series(payload: dict[str, Any], key: str) -> list[Any]:
    values = (payload or {}).get(key)
    return list(values) if isinstance(values, list) else []


def _with_unit(loc: str, label: str, unit: str | None) -> str:
    """Append a real unit, or state honestly that it is unspecified."""
    resolved = str(unit or "").strip() or translate_ui(loc, "dash.deconvolution.unit_unspecified")
    return f"{label} ({resolved})"


def _basis_reason(loc: str, reason: str | None) -> str:
    key = f"dash.deconvolution.reason.{str(reason or '').strip()}"
    translated = translate_ui(loc, key)
    if translated != key:
        return translated
    return str(reason or translate_ui(loc, "dash.deconvolution.unit_unspecified"))


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div(
    [
        dcc.Store(id="deconvolution-refresh", data=0),
        dcc.Store(id="deconvolution-latest-result-id"),
        dcc.Store(id="deconvolution-figure-captured", data={}),
        dcc.Store(id="deconvolution-options", data={}),
        html.Div(id="deconvolution-hero-slot"),
        html.Div(id="deconvolution-guidance-slot", className="mb-2"),
        html.Div(id="deconvolution-disabled-slot"),
        html.Div(
            id="deconvolution-enabled-surface",
            children=[
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Card(
                                    dbc.CardBody(
                                        [
                                            html.H5(id="deconvolution-setup-title", className="mb-3"),
                                            dbc.Label(id="deconvolution-lbl-dataset"),
                                            dcc.Dropdown(
                                                id="deconvolution-dataset-select",
                                                className="ta-dropdown",
                                            ),
                                            html.Div(id="deconvolution-dataset-status", className="mt-2"),
                                            dbc.Label(id="deconvolution-lbl-basis", className="mt-3"),
                                            dcc.Dropdown(
                                                id="deconvolution-basis-select",
                                                className="ta-dropdown",
                                            ),
                                            html.Div(id="deconvolution-basis-status", className="mt-2"),
                                        ]
                                    ),
                                    className="mb-4",
                                ),
                                dbc.Card(
                                    dbc.CardBody(
                                        [
                                            html.H5(id="deconvolution-fit-title", className="mb-3"),
                                            dbc.Row(
                                                [
                                                    dbc.Col(
                                                        [
                                                            dbc.Label(id="deconvolution-lbl-n-peaks"),
                                                            dbc.Input(
                                                                id="deconvolution-n-peaks",
                                                                type="number",
                                                                value=2,
                                                                min=_MIN_PEAKS,
                                                                max=_MAX_PEAKS,
                                                                step=1,
                                                            ),
                                                        ]
                                                    ),
                                                    dbc.Col(
                                                        [
                                                            dbc.Label(id="deconvolution-lbl-shape"),
                                                            dcc.Dropdown(
                                                                id="deconvolution-peak-shape",
                                                                className="ta-dropdown",
                                                                clearable=False,
                                                            ),
                                                        ]
                                                    ),
                                                ],
                                                className="g-2",
                                            ),
                                            dbc.Checklist(
                                                id="deconvolution-use-range",
                                                options=[{"label": "—", "value": "on"}],
                                                value=[],
                                                switch=True,
                                                className="mt-3",
                                            ),
                                            html.Div(
                                                id="deconvolution-range-wrap",
                                                children=[
                                                    dbc.Row(
                                                        [
                                                            dbc.Col(
                                                                [
                                                                    dbc.Label(id="deconvolution-lbl-range-min"),
                                                                    dbc.Input(
                                                                        id="deconvolution-range-min",
                                                                        type="number",
                                                                    ),
                                                                ]
                                                            ),
                                                            dbc.Col(
                                                                [
                                                                    dbc.Label(id="deconvolution-lbl-range-max"),
                                                                    dbc.Input(
                                                                        id="deconvolution-range-max",
                                                                        type="number",
                                                                    ),
                                                                ]
                                                            ),
                                                        ],
                                                        className="g-2",
                                                    ),
                                                    html.Small(
                                                        id="deconvolution-range-help",
                                                        className="text-muted d-block",
                                                    ),
                                                ],
                                                style={"display": "none"},
                                            ),
                                            dbc.Checklist(
                                                id="deconvolution-invert",
                                                options=[{"label": "—", "value": "on"}],
                                                value=[],
                                                switch=True,
                                                className="mt-3",
                                            ),
                                            html.P(
                                                id="deconvolution-invert-help",
                                                className="text-muted small mb-0",
                                            ),
                                            dbc.Checklist(
                                                id="deconvolution-use-guesses",
                                                options=[{"label": "—", "value": "on"}],
                                                value=[],
                                                switch=True,
                                                className="mt-3",
                                            ),
                                            html.P(
                                                id="deconvolution-guesses-help",
                                                className="text-muted small mb-2",
                                            ),
                                            html.Div(id="deconvolution-guess-rows"),
                                        ]
                                    ),
                                    className="mb-4",
                                ),
                                dbc.Card(
                                    dbc.CardBody(
                                        [
                                            html.H5(id="deconvolution-run-title", className="mb-3"),
                                            html.Div(id="deconvolution-run-status"),
                                            dbc.Button(
                                                "",
                                                id="deconvolution-run-btn",
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
                                html.H5(id="deconvolution-result-title", className="mb-3"),
                                dbc.Card(
                                    dbc.CardBody(html.Div(id="deconvolution-result-metrics")),
                                    className="mb-4",
                                ),
                                dbc.Card(
                                    dbc.CardBody(html.Div(id="deconvolution-result-figure")),
                                    className="mb-4",
                                ),
                                dbc.Card(
                                    dbc.CardBody(html.Div(id="deconvolution-result-table")),
                                    className="mb-4",
                                ),
                                dbc.Card(
                                    dbc.CardBody(html.Div(id="deconvolution-result-residual")),
                                    className="mb-4",
                                ),
                                dbc.Card(
                                    dbc.CardBody(html.Div(id="deconvolution-result-scientific")),
                                    className="mb-4",
                                ),
                                dbc.Card(
                                    dbc.CardBody(html.Div(id="deconvolution-figure-artifacts")),
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
    Output("deconvolution-hero-slot", "children"),
    Output("deconvolution-guidance-slot", "children"),
    Output("deconvolution-setup-title", "children"),
    Output("deconvolution-lbl-dataset", "children"),
    Output("deconvolution-lbl-basis", "children"),
    Output("deconvolution-fit-title", "children"),
    Output("deconvolution-lbl-n-peaks", "children"),
    Output("deconvolution-lbl-shape", "children"),
    Output("deconvolution-peak-shape", "options"),
    Output("deconvolution-use-range", "options"),
    Output("deconvolution-invert", "options"),
    Output("deconvolution-invert-help", "children"),
    Output("deconvolution-use-guesses", "options"),
    Output("deconvolution-guesses-help", "children"),
    Output("deconvolution-run-title", "children"),
    Output("deconvolution-run-btn", "children"),
    Output("deconvolution-result-title", "children"),
    Input("ui-locale", "data"),
    prevent_initial_call=False,
)
def render_deconvolution_chrome(locale_data):
    loc = _loc(locale_data)
    hero = page_header(
        translate_ui(loc, "dash.deconvolution.title"),
        translate_ui(loc, "dash.deconvolution.caption"),
        badge=translate_ui(loc, "dash.deconvolution.badge"),
    )
    guidance = html.Div(
        [
            guidance_block(
                translate_ui(loc, "dash.deconvolution.guidance_what_title"),
                body=translate_ui(loc, "dash.deconvolution.guidance_what_body"),
            ),
            typical_workflow_block(
                [
                    translate_ui(loc, "dash.deconvolution.workflow_step1"),
                    translate_ui(loc, "dash.deconvolution.workflow_step2"),
                    translate_ui(loc, "dash.deconvolution.workflow_step3"),
                ],
                locale=loc,
            ),
            guidance_block(
                translate_ui(loc, "dash.deconvolution.usage_title"),
                bullets=[
                    translate_ui(loc, "dash.deconvolution.usage_bullet1"),
                    translate_ui(loc, "dash.deconvolution.usage_bullet2"),
                    translate_ui(loc, "dash.deconvolution.usage_bullet3"),
                ],
                tone="secondary",
            ),
            next_step_block(translate_ui(loc, "dash.deconvolution.next_step_body"), locale=loc),
        ]
    )
    shape_options = [
        {
            "label": translate_ui(loc, f"dash.deconvolution.shape.{shape}"),
            "value": shape,
        }
        for shape in _PEAK_SHAPES
    ]
    switch_option = [{"label": "—", "value": "on"}]
    return (
        hero,
        guidance,
        translate_ui(loc, "dash.deconvolution.setup_title"),
        translate_ui(loc, "dash.deconvolution.label_dataset"),
        translate_ui(loc, "dash.deconvolution.label_basis"),
        translate_ui(loc, "dash.deconvolution.fit_title"),
        translate_ui(loc, "dash.deconvolution.label_n_peaks"),
        translate_ui(loc, "dash.deconvolution.label_peak_shape"),
        shape_options,
        switch_option,
        switch_option,
        translate_ui(loc, "dash.deconvolution.invert_help"),
        switch_option,
        translate_ui(loc, "dash.deconvolution.guesses_help"),
        translate_ui(loc, "dash.deconvolution.run_title"),
        translate_ui(loc, "dash.deconvolution.btn_run"),
        translate_ui(loc, "dash.deconvolution.result_title"),
    )


@callback(
    Output("deconvolution-enabled-surface", "style"),
    Output("deconvolution-disabled-slot", "children"),
    Input("ui-locale", "data"),
    prevent_initial_call=False,
)
def gate_deconvolution_page(locale_data):
    """Preview gate: hide the workflow and block execution when disabled."""
    loc = _loc(locale_data)
    if preview_modules_enabled():
        return {}, ""
    disabled = prereq_or_empty_help(
        translate_ui(loc, "dash.deconvolution.disabled_body"),
        title=translate_ui(loc, "dash.deconvolution.disabled_title"),
        locale=loc,
    )
    return {"display": "none"}, disabled


# ---------------------------------------------------------------------------
# Dataset + signal basis resolution
# ---------------------------------------------------------------------------


@callback(
    Output("deconvolution-dataset-select", "options"),
    Input("project-id", "data"),
    Input("deconvolution-refresh", "data"),
    Input("workspace-refresh", "data"),
    prevent_initial_call=False,
)
def load_deconvolution_datasets(project_id, _refresh, _workspace_refresh):
    if not project_id:
        return []

    from dash_app.api_client import workspace_datasets

    try:
        payload = workspace_datasets(project_id)
    except Exception:
        return []

    options: list[dict[str, str]] = []
    for item in payload.get("datasets", []) or []:
        data_type = str(item.get("data_type") or "").upper()
        if data_type not in _ELIGIBLE_TYPES:
            continue
        key = str(item.get("key"))
        options.append(
            {
                "label": f"{item.get('display_name', key)} ({data_type})",
                "value": key,
            }
        )
    return options


@callback(
    Output("deconvolution-basis-select", "options"),
    Output("deconvolution-basis-select", "value"),
    Output("deconvolution-options", "data"),
    Output("deconvolution-dataset-status", "children"),
    Output("deconvolution-basis-status", "children"),
    Output("deconvolution-lbl-range-min", "children"),
    Output("deconvolution-lbl-range-max", "children"),
    Output("deconvolution-range-min", "placeholder"),
    Output("deconvolution-range-max", "placeholder"),
    Output("deconvolution-range-help", "children"),
    Input("project-id", "data"),
    Input("deconvolution-dataset-select", "value"),
    Input("ui-locale", "data"),
    State("deconvolution-basis-select", "value"),
    prevent_initial_call=False,
)
def resolve_deconvolution_basis(project_id, dataset_key, locale_data, current_basis):
    """Resolve available bases and effective axis semantics for the dataset."""
    loc = _loc(locale_data)
    unspecified = translate_ui(loc, "dash.deconvolution.unit_unspecified")
    default_labels = (
        translate_ui(loc, "dash.deconvolution.label_range_min", unit=unspecified),
        translate_ui(loc, "dash.deconvolution.label_range_max", unit=unspecified),
    )
    if not project_id or not dataset_key:
        return (
            [],
            None,
            {},
            html.P(
                translate_ui(loc, "dash.deconvolution.no_dataset_hint"),
                className="text-muted small mb-0",
            ),
            "",
            default_labels[0],
            default_labels[1],
            "—",
            "—",
            "",
        )

    from dash_app.api_client import deconvolution_options

    try:
        options = deconvolution_options(project_id, str(dataset_key))
    except Exception as exc:
        return (
            [],
            None,
            {},
            dbc.Alert(str(exc), color="danger", className="small mb-0"),
            "",
            default_labels[0],
            default_labels[1],
            "—",
            "—",
            "",
        )

    bases = options.get("bases") or []
    basis_options = []
    for entry in bases:
        name = str(entry.get("name") or "")
        label = translate_ui(loc, f"dash.deconvolution.basis.{name}")
        if not entry.get("available"):
            label = f"{label} — {_basis_reason(loc, entry.get('reason'))}"
        basis_options.append({"label": label, "value": name, "disabled": not entry.get("available")})

    available = [str(entry.get("name")) for entry in bases if entry.get("available")]
    selected = str(current_basis or "")
    if selected not in available:
        selected = "raw" if "raw" in available else (available[0] if available else None)

    axis_unit = options.get("axis_unit")
    domain = options.get("axis_domain") or []
    domain_text = f"[{_fmt(domain[0])}, {_fmt(domain[1])}]" if len(domain) == 2 else "—"

    dataset_status = html.P(
        translate_ui(
            loc,
            "dash.deconvolution.basis_ready",
            x_label=options.get("x_label") or "—",
            axis_role=options.get("axis_role") or "—",
            y_label=options.get("y_label") or "—",
            signal_role=options.get("signal_role") or "—",
            domain=domain_text,
        ),
        className="text-muted small mb-0",
    )
    if not options.get("has_analysis_state"):
        dataset_status = html.Div(
            [
                dataset_status,
                html.P(
                    translate_ui(loc, "dash.deconvolution.basis_ready_no_analysis"),
                    className="text-muted small mb-0",
                ),
            ]
        )

    selected_entry = next((entry for entry in bases if str(entry.get("name")) == selected), None)
    if selected_entry is not None and not selected_entry.get("available"):
        basis_status = prereq_or_empty_help(
            translate_ui(
                loc,
                "dash.deconvolution.basis_unavailable",
                basis=translate_ui(loc, f"dash.deconvolution.basis.{selected}"),
                reason=_basis_reason(loc, selected_entry.get("reason")),
            ),
            locale=loc,
        )
    else:
        basis_status = html.P(
            translate_ui(loc, "dash.deconvolution.amplitude_note"),
            className="text-muted small mb-0",
        )

    return (
        basis_options,
        selected,
        options,
        dataset_status,
        basis_status,
        translate_ui(loc, "dash.deconvolution.label_range_min", unit=axis_unit or unspecified),
        translate_ui(loc, "dash.deconvolution.label_range_max", unit=axis_unit or unspecified),
        _fmt(domain[0]) if len(domain) == 2 else "—",
        _fmt(domain[1]) if len(domain) == 2 else "—",
        domain_text,
    )


# ---------------------------------------------------------------------------
# Initial-guess rows
# ---------------------------------------------------------------------------


@callback(
    Output("deconvolution-guess-rows", "children"),
    Input("deconvolution-use-guesses", "value"),
    Input("deconvolution-n-peaks", "value"),
    Input("deconvolution-options", "data"),
    Input("ui-locale", "data"),
    prevent_initial_call=False,
)
def render_guess_rows(use_guesses, n_peaks, options, locale_data):
    """Editable rows, one per component; a blank field means auto estimate."""
    loc = _loc(locale_data)
    if not use_guesses:
        return html.P(translate_ui(loc, "dash.deconvolution.guess_hint"), className="text-muted small mb-0")

    try:
        count = int(n_peaks)
    except (TypeError, ValueError):
        count = 2
    count = max(_MIN_PEAKS, min(_MAX_PEAKS, count))

    axis_unit = (options or {}).get("axis_unit")
    placeholder = translate_ui(loc, "dash.deconvolution.field_auto_placeholder")
    rows: list[Any] = []
    for index in range(count):
        rows.append(
            html.Div(
                [
                    html.Div(
                        translate_ui(loc, "dash.deconvolution.component_title", index=index + 1),
                        className="fw-semibold small mb-1",
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    dbc.Label(
                                        _with_unit(loc, translate_ui(loc, "dash.deconvolution.guess_center"), axis_unit),
                                        className="small mb-0",
                                    ),
                                    dbc.Input(
                                        id={"type": "deconvolution-guess-center", "index": index},
                                        type="number",
                                        size="sm",
                                        placeholder=placeholder,
                                    ),
                                ]
                            ),
                            dbc.Col(
                                [
                                    dbc.Label(
                                        translate_ui(loc, "dash.deconvolution.guess_amplitude"),
                                        className="small mb-0",
                                    ),
                                    dbc.Input(
                                        id={"type": "deconvolution-guess-amplitude", "index": index},
                                        type="number",
                                        min=0,
                                        size="sm",
                                        placeholder=placeholder,
                                    ),
                                ]
                            ),
                            dbc.Col(
                                [
                                    dbc.Label(
                                        _with_unit(loc, translate_ui(loc, "dash.deconvolution.guess_sigma"), axis_unit),
                                        className="small mb-0",
                                    ),
                                    dbc.Input(
                                        id={"type": "deconvolution-guess-sigma", "index": index},
                                        type="number",
                                        min=0,
                                        size="sm",
                                        placeholder=placeholder,
                                    ),
                                ]
                            ),
                        ],
                        className="g-2",
                    ),
                ],
                className="border rounded p-2 mb-2",
            )
        )
    rows.append(html.Small(translate_ui(loc, "dash.deconvolution.guess_hint"), className="text-muted"))
    return rows


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def _collect_guesses(values: list[Any], ids: list[dict[str, Any]]) -> dict[int, dict[str, float]]:
    collected: dict[int, dict[str, float]] = {}
    for value, identifier in zip(values, ids):
        if value in (None, ""):
            continue
        parsed = _number_or_none(value)
        if parsed is None:
            continue
        index = int(identifier.get("index", 0) or 0)
        field = str(identifier.get("type", "")).rsplit("-", 1)[-1]
        collected.setdefault(index, {})[field] = parsed
    return collected


@callback(
    Output("deconvolution-run-status", "children"),
    Output("deconvolution-refresh", "data", allow_duplicate=True),
    Output("deconvolution-latest-result-id", "data", allow_duplicate=True),
    Output("workspace-refresh", "data", allow_duplicate=True),
    Input("deconvolution-run-btn", "n_clicks"),
    State("project-id", "data"),
    State("deconvolution-dataset-select", "value"),
    State("deconvolution-basis-select", "value"),
    State("deconvolution-n-peaks", "value"),
    State("deconvolution-peak-shape", "value"),
    State("deconvolution-use-range", "value"),
    State("deconvolution-range-min", "value"),
    State("deconvolution-range-max", "value"),
    State("deconvolution-invert", "value"),
    State("deconvolution-use-guesses", "value"),
    State({"type": "deconvolution-guess-center", "index": ALL}, "value"),
    State({"type": "deconvolution-guess-center", "index": ALL}, "id"),
    State({"type": "deconvolution-guess-amplitude", "index": ALL}, "value"),
    State({"type": "deconvolution-guess-amplitude", "index": ALL}, "id"),
    State({"type": "deconvolution-guess-sigma", "index": ALL}, "value"),
    State({"type": "deconvolution-guess-sigma", "index": ALL}, "id"),
    State("deconvolution-refresh", "data"),
    State("workspace-refresh", "data"),
    State("ui-locale", "data"),
    prevent_initial_call=True,
)
def run_deconvolution(
    n_clicks,
    project_id,
    dataset_key,
    basis,
    n_peaks,
    peak_shape,
    use_range,
    range_min,
    range_max,
    invert,
    use_guesses,
    center_values,
    center_ids,
    amplitude_values,
    amplitude_ids,
    sigma_values,
    sigma_ids,
    refresh_val,
    global_refresh,
    locale_data,
):
    loc = _loc(locale_data)
    if not n_clicks or not project_id:
        raise dash.exceptions.PreventUpdate
    if not preview_modules_enabled():
        alert = dbc.Alert(translate_ui(loc, "dash.deconvolution.disabled_body"), color="warning")
        return alert, dash.no_update, dash.no_update, dash.no_update
    if not dataset_key:
        alert = dbc.Alert(translate_ui(loc, "dash.deconvolution.no_dataset_hint"), color="warning")
        return alert, dash.no_update, dash.no_update, dash.no_update

    guesses: dict[int, dict[str, float]] = {}
    if use_guesses:
        for values, ids in (
            (center_values, center_ids),
            (amplitude_values, amplitude_ids),
            (sigma_values, sigma_ids),
        ):
            for index, entry in _collect_guesses(list(values or []), list(ids or [])).items():
                guesses.setdefault(index, {}).update(entry)

    try:
        peak_count = int(n_peaks)
    except (TypeError, ValueError):
        peak_count = 2
    peak_count = max(_MIN_PEAKS, min(_MAX_PEAKS, peak_count))

    initial_params = [dict(guesses.get(index) or {}) for index in range(peak_count)]

    payload: dict[str, Any] = {
        "dataset_key": str(dataset_key),
        "signal_basis": str(basis or "raw"),
        "n_peaks": peak_count,
        "peak_shape": str(peak_shape or "gaussian"),
        "initial_params": initial_params,
        "invert_signal_for_fit": bool(invert),
    }
    if use_range:
        payload["range_min"] = _number_or_none(range_min)
        payload["range_max"] = _number_or_none(range_max)

    from dash_app.api_client import deconvolution_run

    try:
        response = deconvolution_run(project_id, payload)
    except Exception as exc:
        return (
            dbc.Alert(
                translate_ui(loc, "dash.deconvolution.run_failed", error=str(exc)),
                color="danger",
            ),
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )

    result_id = response.get("result_id")
    children: list[Any] = [
        dbc.Alert(
            translate_ui(loc, "dash.deconvolution.run_saved", rid=result_id),
            color="success",
        )
    ]
    warnings = response.get("warnings") or []
    if warnings:
        children.append(
            dbc.Alert(
                html.Ul([html.Li(str(item)) for item in warnings], className="mb-0 ps-3"),
                color="warning",
            )
        )
    return (
        html.Div(children),
        int(refresh_val or 0) + 1,
        result_id,
        int(global_refresh or 0) + 1,
    )


# ---------------------------------------------------------------------------
# Hydration
# ---------------------------------------------------------------------------


@callback(
    Output("deconvolution-latest-result-id", "data", allow_duplicate=True),
    Input("url", "pathname"),
    Input("project-id", "data"),
    Input("workspace-refresh", "data"),
    State("deconvolution-latest-result-id", "data"),
    prevent_initial_call="initial_duplicate",
)
def hydrate_latest_deconvolution_result(pathname, project_id, _workspace_refresh, current_id):
    """Reopen the newest saved deconvolution result for the active workspace.

    Fires when the route is (re)opened, when ``project-id`` is populated, and
    when the workspace refresh bumps (e.g. a ``.scopezip`` load). Selection is
    explicit: records whose provenance carries ``analysis_scope ==
    "preview_deconvolution"`` — never title matching. A still-valid current
    selection is kept so a just-finished run is never regressed to an older
    result by this hydration pass.
    """
    if pathname and str(pathname) != "/deconvolution":
        raise dash.exceptions.PreventUpdate
    if not project_id:
        raise dash.exceptions.PreventUpdate

    from dash_app.api_client import workspace_results

    try:
        payload = workspace_results(project_id)
    except Exception:
        raise dash.exceptions.PreventUpdate

    candidates = [
        item
        for item in (payload.get("results") or [])
        if str(item.get("analysis_scope") or "") == "preview_deconvolution" and item.get("id")
    ]
    current = str(current_id) if current_id else None
    if current and any(str(item.get("id")) == current for item in candidates):
        raise dash.exceptions.PreventUpdate
    if not candidates:
        if current:
            return None
        raise dash.exceptions.PreventUpdate
    newest = max(
        candidates,
        key=lambda item: (str(item.get("saved_at_utc") or ""), str(item.get("id") or "")),
    )
    return str(newest["id"])


# ---------------------------------------------------------------------------
# Result rendering
# ---------------------------------------------------------------------------


def _metrics_panel(summary: dict[str, Any], loc: str) -> html.Div:
    unit = str(summary.get("signal_unit") or "").strip()
    pairs = [
        (translate_ui(loc, "dash.deconvolution.metric.r2"), _fmt(summary.get("r_squared"))),
        (translate_ui(loc, "dash.deconvolution.metric.rmse"), _with_unit(loc, _fmt(summary.get("rmse")), unit)),
        (translate_ui(loc, "dash.deconvolution.metric.mae"), _with_unit(loc, _fmt(summary.get("mae")), unit)),
        (
            translate_ui(loc, "dash.deconvolution.metric.max_residual"),
            _with_unit(loc, _fmt(summary.get("max_abs_residual")), unit),
        ),
        (
            translate_ui(loc, "dash.deconvolution.metric.sse_per_dof"),
            _fmt(summary.get("sse_per_dof")),
        ),
        (translate_ui(loc, "dash.deconvolution.metric.dof"), _fmt(summary.get("dof"), 6)),
    ]
    return metrics_row(pairs, locale_data=loc)


def _fit_figure(payload: dict[str, Any], ui_theme: str | None, loc: str) -> go.Figure:
    x = _series(payload, "x")
    fig = go.Figure()
    y = _series(payload, "y")
    if x and y:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                name=translate_ui(loc, "dash.deconvolution.series_input"),
                line=dict(color="#2B6CB0", width=2),
            )
        )
    fitted = _series(payload, "fitted")
    if x and fitted:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=fitted,
                mode="lines",
                name=translate_ui(loc, "dash.deconvolution.series_total"),
                line=dict(color="#E45756", width=2, dash="dash"),
            )
        )
    for index, component in enumerate(payload.get("components") or []):
        fig.add_trace(
            go.Scatter(
                x=x,
                y=list(component),
                mode="lines",
                name=translate_ui(loc, "dash.deconvolution.series_component", index=index + 1),
                line=dict(
                    color=_COMPONENT_COLORS[index % len(_COMPONENT_COLORS)],
                    width=1.4,
                    dash="dot",
                ),
            )
        )
    fig.update_layout(
        xaxis_title=payload.get("xlabel") or "",
        yaxis_title=payload.get("ylabel") or "",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=64, r=28, t=72, b=58),
    )
    apply_figure_theme(fig, ui_theme)
    return fig


def _residual_figure(payload: dict[str, Any], ui_theme: str | None, loc: str) -> go.Figure:
    x = _series(payload, "x")
    residual = _series(payload, "residual")
    fig = go.Figure()
    if x and residual:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=residual,
                mode="lines",
                name=translate_ui(loc, "dash.deconvolution.series_residual"),
                line=dict(color="#F58518", width=1.6),
            )
        )
    fig.add_hline(
        y=0,
        line=dict(color="rgba(128,128,128,0.9)", width=1, dash="dash"),
        annotation_text=translate_ui(loc, "dash.deconvolution.series_zero"),
        annotation_position="top left",
    )
    fig.update_layout(
        xaxis_title=payload.get("xlabel") or "",
        yaxis_title=payload.get("ylabel") or "",
        hovermode="x unified",
        showlegend=False,
        margin=dict(l=64, r=28, t=32, b=58),
    )
    apply_figure_theme(fig, ui_theme)
    return fig


def _result_table(rows: list[dict[str, Any]], summary: dict[str, Any], payload: dict[str, Any], loc: str) -> Any:
    if not rows:
        return empty_result_msg(locale_data=loc)

    axis_unit = payload.get("axis_unit") or summary.get("axis_unit")
    signal_unit = payload.get("signal_unit") or summary.get("signal_unit")
    has_fraction = any(row.get("fraction") is not None for row in rows)

    headers = [
        html.Th(translate_ui(loc, "dash.deconvolution.table.peak")),
        html.Th(_with_unit(loc, translate_ui(loc, "dash.deconvolution.table.center"), axis_unit)),
        html.Th(translate_ui(loc, "dash.deconvolution.table.amplitude")),
        html.Th(_with_unit(loc, translate_ui(loc, "dash.deconvolution.table.sigma"), axis_unit)),
        html.Th(_with_unit(loc, translate_ui(loc, "dash.deconvolution.table.fwhm"), axis_unit)),
        html.Th(_with_unit(loc, translate_ui(loc, "dash.deconvolution.table.height"), signal_unit)),
    ]
    if has_fraction:
        headers.append(html.Th(translate_ui(loc, "dash.deconvolution.table.fraction")))

    body_rows = []
    for row in rows:
        cells = [
            html.Td(str(row.get("peak") or "—")),
            html.Td(_fmt(row.get("center"))),
            html.Td(_fmt(row.get("amplitude"))),
            html.Td(_fmt(row.get("sigma"))),
            html.Td(_fmt(row.get("fwhm"))),
            html.Td(_fmt(row.get("height"))),
        ]
        if has_fraction:
            cells.append(html.Td(_fmt(row.get("fraction"), 3)))
        body_rows.append(html.Tr(cells))

    amplitude_unit = str(summary.get("amplitude_unit") or "").strip()
    note = translate_ui(loc, "dash.deconvolution.amplitude_note")
    if amplitude_unit:
        note = f"{note} [{amplitude_unit}]"
    return html.Div(
        [
            dbc.Table(
                [html.Thead(html.Tr(headers)), html.Tbody(body_rows)],
                bordered=True,
                hover=True,
                responsive=True,
                size="sm",
            ),
            html.P(note, className="text-muted small mb-0"),
        ]
    )


def _scientific_panel(detail: dict[str, Any], loc: str) -> html.Div:
    context = detail.get("scientific_context") or {}
    processing = detail.get("processing") or {}
    provenance = detail.get("provenance") or {}
    validation = detail.get("validation") or {}
    summary = detail.get("summary") or {}

    children: list[Any] = []

    if summary.get("inversion_applied") or processing.get("inversion_applied"):
        children.append(
            dbc.Alert(translate_ui(loc, "dash.deconvolution.inversion_note"), color="info", className="small")
        )

    warnings = [str(item) for item in (validation.get("warnings") or []) if item]
    if warnings:
        children.append(
            html.Div(
                [
                    html.H6(translate_ui(loc, "dash.deconvolution.warnings_title"), className="small fw-semibold"),
                    html.Ul([html.Li(text, className="small") for text in warnings], className="ps-3 mb-2"),
                ]
            )
        )

    limitations = [str(item) for item in (context.get("limitations") or []) if item]
    fit_quality_note = translate_ui(loc, "dash.deconvolution.fit_quality_note")
    children.append(
        html.Details(
            [
                html.Summary(
                    translate_ui(loc, "dash.deconvolution.limitations_title"),
                    className="small text-muted",
                ),
                html.Ul(
                    [html.Li(text, className="small") for text in limitations] + [html.Li(fit_quality_note, className="small")],
                    className="mt-2 mb-0 ps-3",
                ),
            ],
            className="mb-2",
        )
    )

    prov_lines: list[Any] = [
        html.P(f"dataset_key: {processing.get('dataset_key') or '—'}", className="small mb-1"),
        html.P(
            f"signal_basis: {processing.get('signal_basis') or '—'} "
            f"({processing.get('signal_basis_source') or '—'})",
            className="small mb-1",
        ),
        html.P(
            f"axis: {processing.get('axis_role') or '—'} / {processing.get('axis_unit') or '—'}",
            className="small mb-1",
        ),
        html.P(
            f"signal: {processing.get('signal_role') or '—'} / {processing.get('signal_unit') or '—'}",
            className="small mb-1",
        ),
        html.P(
            f"selected_range: {processing.get('selected_range') or '—'}",
            className="small mb-1",
        ),
        html.P(
            f"n_peaks: {processing.get('n_peaks')}; peak_shape: {processing.get('peak_shape')}",
            className="small mb-1",
        ),
        html.P(
            f"inversion_applied: {processing.get('inversion_applied')} "
            f"({processing.get('inversion_semantics') or '—'})",
            className="small mb-1",
        ),
        html.P(
            f"initial_guess_provenance: {processing.get('initial_guess_provenance') or '—'}",
            className="small mb-1",
        ),
        html.P(f"fit_engine: {processing.get('fit_engine') or '—'}", className="small mb-1"),
        html.P(
            f"component_parameter_semantics: {processing.get('component_parameter_semantics') or '—'}",
            className="small mb-1",
        ),
    ]
    auto_estimate = processing.get("auto_estimate") or {}
    if auto_estimate:
        prov_lines.append(
            html.P(
                "auto_estimate: "
                f"detected={auto_estimate.get('detected_peak_count')}; "
                f"fallback_spacing={auto_estimate.get('fallback_spacing_used')}; "
                f"positive_fraction={_fmt(auto_estimate.get('positive_point_fraction'), 4)}",
                className="small mb-1",
            )
        )
    if provenance.get("saved_at_utc"):
        prov_lines.append(html.P(f"saved_at_utc: {provenance['saved_at_utc']}", className="small mb-1"))
    if provenance.get("analysis_scope"):
        prov_lines.append(html.P(f"analysis_scope: {provenance['analysis_scope']}", className="small mb-0"))

    children.append(
        html.Details(
            [
                html.Summary(translate_ui(loc, "dash.deconvolution.provenance_title"), className="small text-muted"),
                html.Div(prov_lines, className="mt-2"),
            ],
            className="mb-0",
            open=True,
        )
    )
    return html.Div(children)


@callback(
    Output("deconvolution-result-metrics", "children"),
    Output("deconvolution-result-figure", "children"),
    Output("deconvolution-result-table", "children"),
    Output("deconvolution-result-residual", "children"),
    Output("deconvolution-result-scientific", "children"),
    Input("deconvolution-latest-result-id", "data"),
    Input("deconvolution-refresh", "data"),
    Input("ui-theme", "data"),
    Input("ui-locale", "data"),
    State("project-id", "data"),
    prevent_initial_call=False,
)
def display_deconvolution_result(result_id, _refresh, ui_theme, locale_data, project_id):
    loc = _loc(locale_data)
    empty = empty_result_msg(locale_data=locale_data)
    if not result_id or not project_id:
        return empty, empty, empty, empty, empty

    from dash_app.api_client import workspace_result_detail

    try:
        detail = workspace_result_detail(project_id, result_id)
    except Exception as exc:
        err = dbc.Alert(str(exc), color="danger")
        return err, empty, empty, empty, empty

    summary = detail.get("summary") or {}
    payload = detail.get("report_payload") or {}
    rows = detail.get("rows") or []

    metrics = html.Div(
        [
            _metrics_panel(summary, loc),
            html.P(
                translate_ui(loc, "dash.deconvolution.fit_quality_note"),
                className="small text-muted mt-2 mb-0",
            ),
        ]
    )

    if _series(payload, "x"):
        figure_area = dcc.Graph(
            figure=prepare_result_graph_figure(_fit_figure(payload, ui_theme, loc)),
            className=result_graph_class(),
            config=result_graph_config(),
            style={"height": "520px"},
        )
        residual_area = dcc.Graph(
            figure=prepare_result_graph_figure(_residual_figure(payload, ui_theme, loc)),
            className=result_graph_class(),
            config=result_graph_config(),
            style={"height": "320px"},
        )
    else:
        figure_area = empty
        residual_area = empty

    return (
        metrics,
        figure_area,
        _result_table(rows, summary, payload, loc),
        residual_area,
        _scientific_panel(detail, loc),
    )


@callback(
    Output("deconvolution-figure-captured", "data"),
    Input("deconvolution-latest-result-id", "data"),
    Input("deconvolution-result-figure", "children"),
    State("project-id", "data"),
    State("deconvolution-figure-captured", "data"),
    prevent_initial_call=True,
)
def capture_deconvolution_figure(result_id, figure_children, project_id, captured):
    return capture_result_figure_from_layout(
        result_id=result_id,
        project_id=project_id,
        figure_children=figure_children,
        captured=captured,
        analysis_type="Peak Deconvolution",
    )


@callback(
    Output("deconvolution-figure-artifacts", "children"),
    Input("deconvolution-latest-result-id", "data"),
    Input("deconvolution-figure-captured", "data"),
    Input("ui-locale", "data"),
    State("project-id", "data"),
    prevent_initial_call=False,
)
def render_deconvolution_figure_artifacts(result_id, _captured, locale_data, project_id):
    loc = _loc(locale_data)
    if not result_id or not project_id:
        return build_figure_artifacts_panel(None, loc)

    from dash_app.api_client import workspace_result_detail

    try:
        detail = workspace_result_detail(project_id, result_id)
    except Exception:
        return build_figure_artifacts_panel(None, loc)
    return build_figure_artifacts_panel(detail.get("figure_artifacts") or {}, loc)
