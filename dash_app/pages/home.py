"""Import page -- modality-first, multi-step import wizard with rich dataset cards."""

from __future__ import annotations

import base64

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, clientside_callback, dcc, html

from dash_app.components.chrome import page_header
from dash_app.components.data_preview import (
    dataset_table,
    metadata_list,
    metric_cards,
    original_columns_list,
    quick_plot,
    stats_table,
)
from dash_app.components.page_guidance import (
    guidance_block,
    next_step_block,
    prereq_or_empty_help,
    typical_workflow_block,
)
from dash_app.components.stepper import stepper_indicator
from dash_app.import_preview import build_import_preview
from dash_app.sample_data import list_sample_specs, resolve_sample_request

dash.register_page(__name__, path="/", title="Import - MaterialScope")

_NONE_VALUE = "__NONE__"

_MODALITY_OPTIONS = ["DSC", "TGA", "DTA", "FTIR", "RAMAN", "XRD"]
_MODALITY_DESCRIPTIONS = {
    "DSC": "Differential Scanning Calorimetry -- Temperature vs Heat Flow (mW/mg)",
    "TGA": "Thermogravimetric Analysis -- Temperature vs Mass (%/mg)",
    "DTA": "Differential Thermal Analysis -- Temperature vs ΔT (µV)",
    "FTIR": "Fourier Transform Infrared -- Wavenumber (cm⁻¹) vs Absorbance/Transmittance",
    "RAMAN": "Raman Spectroscopy -- Raman Shift (cm⁻¹) vs Intensity",
    "XRD": "X-Ray Diffraction -- 2θ (degrees) vs Intensity (counts)",
}
_MODALITY_AXIS_LABELS = {
    "DSC": "Temperature Column",
    "TGA": "Temperature Column",
    "DTA": "Temperature Column",
    "FTIR": "Wavenumber Column",
    "RAMAN": "Raman Shift Column",
    "XRD": "2θ Column",
}
_MODALITY_SIGNAL_LABELS = {
    "DSC": "Heat Flow Column",
    "TGA": "Mass Column",
    "DTA": "ΔT Column",
    "FTIR": "Absorbance/Transmittance Column",
    "RAMAN": "Intensity Column",
    "XRD": "Intensity Column",
}

_WIZARD_STEPS = [
    {"label": "1. Technique", "description": "Select measurement technique"},
    {"label": "2. Upload", "description": "Upload file or load sample data"},
    {"label": "3. Preview", "description": "Inspect raw data and detected format"},
    {"label": "4. Mapping", "description": "Map columns to axis/signal roles"},
    {"label": "5. Review", "description": "Review units, metadata, and warnings"},
    {"label": "6. Confirm", "description": "Validate and confirm import"},
]


def _mapping_options(columns: list[str]) -> list[dict[str, str]]:
    return [{"label": "-- None --", "value": _NONE_VALUE}] + [
        {"label": column, "value": column}
        for column in columns
    ]


def _summary_card(label: str, value: str) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody([html.Small(label, className="text-muted text-uppercase"), html.H4(value, className="mb-0")])
    )


def _build_metrics(datasets: list[dict]) -> dbc.Row:
    vendors = {item.get("vendor", "Generic") for item in datasets}
    by_type = {
        token: sum(1 for item in datasets if item.get("data_type") == token)
        for token in _MODALITY_OPTIONS
    }
    type_summary = " / ".join(str(by_type[token]) for token in _MODALITY_OPTIONS)
    return dbc.Row(
        [
            dbc.Col(_summary_card("Loaded Runs", str(len(datasets))), md=4),
            dbc.Col(_summary_card("D / T / DTA / F / R / X", type_summary), md=4),
            dbc.Col(_summary_card("Vendors", str(len(vendors))), md=4),
        ],
        className="g-3 mb-4",
    )


def _sample_buttons() -> list[dbc.Col]:
    cols: list[dbc.Col] = []
    for spec in list_sample_specs():
        cols.append(
            dbc.Col(
                dbc.Button(
                    spec["label"],
                    id={"type": "sample-load", "sample_id": spec["id"]},
                    color="secondary",
                    className="w-100",
                ),
                md=6,
                className="mb-2",
            )
        )
    return cols


def _modality_select_buttons() -> html.Div:
    """Render modality selection as large button group."""
    buttons = []
    for token in _MODALITY_OPTIONS:
        buttons.append(
            dbc.Col(
                dbc.Button(
                    [
                        html.Div(token, className="fw-bold fs-5"),
                        html.Small(_MODALITY_DESCRIPTIONS[token], className="d-block mt-1 text-start", style={"fontSize": "0.7rem"}),
                    ],
                    id={"type": "modality-select", "modality": token},
                    color="outline-secondary",
                    className="w-100 text-start p-3 modality-btn",
                ),
                md=4,
                className="mb-2",
            )
        )
    return dbc.Row(buttons)


def _validation_status_badge(status: str) -> html.Span:
    color_map = {
        "pass": "success",
        "pass_with_review": "info",
        "warn": "warning",
        "fail": "danger",
    }
    label_map = {
        "pass": "PASS",
        "pass_with_review": "REVIEW",
        "warn": "WARN",
        "fail": "FAIL",
    }
    color = color_map.get(status, "secondary")
    label = label_map.get(status, status.upper())
    return dbc.Badge(label, color=color, className="fs-6")


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div(
    [
        # -- Stores --
        dcc.Store(id="import-wizard-step", data=0),
        dcc.Store(id="import-selected-modality", data=""),
        dcc.Store(id="pending-upload-files", data=[]),
        dcc.Store(id="pending-import-preview"),
        dcc.Store(id="import-review-data"),
        dcc.Store(id="home-refresh", data=0),

        # -- Page header --
        page_header(
            "Data Import",
            "Modality-first import wizard: select technique, upload, map, review, and confirm.",
            badge="Import",
        ),

        # -- Guidance --
        html.Div(
            [
                guidance_block(
                    "Modality-first import",
                    body=(
                        "Select a measurement technique before uploading data. "
                        "This ensures the parser uses technique-specific rules for column detection, "
                        "unit validation, and scientific credibility checks."
                    ),
                ),
            ],
            className="mb-2",
        ),

        # -- Wizard stepper indicator --
        html.Div(id="wizard-stepper-display"),
        html.Div(id="import-metrics"),

        # =============================================
        # STEP 1: Modality Selection
        # =============================================
        html.Div(
            id="wizard-step-1",
            children=[
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.H5("Select Measurement Technique", className="mb-3"),
                            html.P(
                                "Choose the analysis technique for the data you are about to import. "
                                "This determines the expected axis roles, units, and validation rules.",
                                className="text-muted",
                            ),
                            _modality_select_buttons(),
                            html.Div(id="modality-select-status", className="mt-2"),
                        ]
                    ),
                    className="mb-4",
                ),
            ],
        ),

        # =============================================
        # STEP 2: File Upload + Sample Data
        # =============================================
        html.Div(
            id="wizard-step-2",
            children=[
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.H5(id="step2-title", children="Upload Data", className="mb-3"),
                            html.Div(id="step2-modality-badge", className="mb-3"),
                            dcc.Upload(
                                id="file-upload",
                                children=html.Div(
                                    [
                                        html.I(className="bi bi-cloud-arrow-up fs-1 d-block mb-2 text-muted"),
                                        "Drag and drop files here, or ",
                                        html.A("browse", className="ta-link-emphasis"),
                                    ],
                                    className="text-center py-4",
                                ),
                                className="upload-zone",
                                multiple=True,
                            ),
                            html.Div(id="upload-status", className="mt-3"),
                            dbc.Select(id="pending-file-select", className="mt-3"),
                            html.Div(id="pending-file-help", className="small text-muted mt-2"),
                            html.Hr(className="my-4"),
                            html.H5("Load Sample Data", className="mb-3"),
                            html.P(
                                "Load built-in sample datasets for testing. These are pre-tagged with their modality.",
                                className="text-muted",
                            ),
                            dbc.Row(_sample_buttons()),
                            html.Div(id="sample-status", className="mt-3"),
                        ]
                    ),
                    className="mb-4",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Button("Back", id="step2-prev-btn", color="secondary", outline=True),
                            width="auto",
                        ),
                        dbc.Col(
                            dbc.Button("Next: Preview", id="step2-next-btn", color="primary"),
                            width="auto",
                        ),
                    ],
                    className="g-2",
                ),
            ],
            style={"display": "none"},
        ),

        # =============================================
        # STEP 3: Raw Preview
        # =============================================
        html.Div(
            id="wizard-step-3",
            children=[
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.H5("Raw Data Preview", className="mb-3"),
                            html.Div(id="mapping-preview-status", className="mb-3"),
                            html.Div(id="mapping-preview-table"),
                        ]
                    ),
                    className="mb-4",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Button("Back", id="step3-prev-btn", color="secondary", outline=True),
                            width="auto",
                        ),
                        dbc.Col(
                            dbc.Button("Next: Map Columns", id="step3-next-btn", color="primary"),
                            width="auto",
                        ),
                    ],
                    className="g-2",
                ),
            ],
            style={"display": "none"},
        ),

        # =============================================
        # STEP 4: Column Mapping
        # =============================================
        html.Div(
            id="wizard-step-4",
            children=[
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.H5("Column Mapping", className="mb-3"),
                            html.P(
                                "Map raw columns to standardized axis/signal roles. "
                                "Values are pre-filled from modality-aware detection.",
                                className="text-muted",
                            ),
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            dbc.Label(id="mapping-axis-label", children="Axis Column", className="mt-3"),
                                            dbc.Select(id="mapping-temp-select"),
                                        ],
                                        md=4,
                                    ),
                                    dbc.Col(
                                        [
                                            dbc.Label(id="mapping-signal-label", children="Signal Column", className="mt-3"),
                                            dbc.Select(id="mapping-signal-select"),
                                        ],
                                        md=4,
                                    ),
                                    dbc.Col(
                                        [
                                            dbc.Label("Time Column (optional)", className="mt-3"),
                                            dbc.Select(id="mapping-time-select"),
                                        ],
                                        md=4,
                                    ),
                                ],
                                className="g-3",
                            ),
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            dbc.Label("Sample Name", className="mt-3"),
                                            dbc.Input(id="mapping-sample-name", type="text"),
                                        ],
                                        md=4,
                                    ),
                                    dbc.Col(
                                        [
                                            dbc.Label("Sample Mass (mg)", className="mt-3"),
                                            dbc.Input(id="mapping-sample-mass", type="number", value=0),
                                        ],
                                        md=4,
                                    ),
                                    dbc.Col(
                                        [
                                            dbc.Label(id="mapping-rate-label", children="Heating Rate (°C/min)", className="mt-3"),
                                            dbc.Input(id="mapping-heating-rate", type="number", value=10),
                                        ],
                                        md=4,
                                    ),
                                ],
                                className="g-3",
                            ),
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            dbc.Label("XRD Wavelength (Å)", className="mt-3"),
                                            dbc.Input(id="mapping-xrd-wavelength", type="number", value=1.5406),
                                        ],
                                        md=4,
                                    ),
                                ],
                                className="g-3",
                                id="xrd-wavelength-row",
                            ),
                        ]
                    ),
                    className="mb-4",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Button("Back", id="step4-prev-btn", color="secondary", outline=True),
                            width="auto",
                        ),
                        dbc.Col(
                            dbc.Button("Next: Review", id="step4-next-btn", color="primary"),
                            width="auto",
                        ),
                    ],
                    className="g-2",
                ),
            ],
            style={"display": "none"},
        ),

        # =============================================
        # STEP 5: Unit / Metadata Review
        # =============================================
        html.Div(
            id="wizard-step-5",
            children=[
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.H5("Unit & Metadata Review", className="mb-3"),
                            html.Div(id="review-unit-status"),
                            html.Div(id="review-metadata-summary"),
                            html.Div(id="review-warnings-list"),
                        ]
                    ),
                    className="mb-4",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Button("Back", id="step5-prev-btn", color="secondary", outline=True),
                            width="auto",
                        ),
                        dbc.Col(
                            dbc.Button("Next: Confirm Import", id="step5-next-btn", color="primary"),
                            width="auto",
                        ),
                    ],
                    className="g-2",
                ),
            ],
            style={"display": "none"},
        ),

        # =============================================
        # STEP 6: Validation Summary + Confirm
        # =============================================
        html.Div(
            id="wizard-step-6",
            children=[
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.H5("Validation Summary", className="mb-3"),
                            html.Div(id="validation-summary-status"),
                            html.Div(id="validation-summary-warnings"),
                            html.Div(id="validation-summary-details"),
                            html.Hr(className="my-3"),
                            dbc.Button(
                                "Confirm Import",
                                id="import-mapped-btn",
                                color="success",
                                size="lg",
                                className="w-100",
                            ),
                        ]
                    ),
                    className="mb-4",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Button("Back", id="step6-prev-btn", color="secondary", outline=True),
                            width="auto",
                        ),
                    ],
                    className="g-2",
                ),
            ],
            style={"display": "none"},
        ),

        # =============================================
        # Loaded Datasets Panel (always visible)
        # =============================================
        html.Hr(className="my-4"),
        html.H5("Loaded Datasets", className="mb-3"),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.Div(id="datasets-table"),
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                [
                                                    dbc.Label("Active Dataset"),
                                                    dbc.Select(id="active-dataset-select"),
                                                ],
                                                md=9,
                                            ),
                                            dbc.Col(
                                                dbc.Button(
                                                    "Remove",
                                                    id="remove-dataset-btn",
                                                    color="secondary",
                                                    className="ta-btn-remove w-100",
                                                ),
                                                md=3,
                                                className="d-flex align-items-center",
                                            ),
                                        ],
                                        className="g-2 align-items-center",
                                    ),
                                    html.Div(id="dataset-action-status", className="mt-3"),
                                ]
                            ),
                            className="mb-4",
                        ),
                    ],
                    md=6,
                ),
                dbc.Col(
                    [
                        dbc.Card(
                            dbc.CardBody([html.Div(id="dataset-detail-panel")]),
                            className="mb-4",
                        ),
                    ],
                    md=6,
                ),
            ]
        ),
    ]
)


# ---------------------------------------------------------------------------
# Step 1: Modality Selection
# ---------------------------------------------------------------------------

@callback(
    Output("import-selected-modality", "data"),
    Output("import-wizard-step", "data", allow_duplicate=True),
    Output("modality-select-status", "children"),
    Input({"type": "modality-select", "modality": ALL}, "n_clicks"),
    State({"type": "modality-select", "modality": ALL}, "id"),
    prevent_initial_call=True,
)
def select_modality(_clicks, ids):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        raise dash.exceptions.PreventUpdate
    modality = triggered.get("modality", "")
    if modality not in _MODALITY_OPTIONS:
        raise dash.exceptions.PreventUpdate
    status = dbc.Alert(
        f"Selected: {modality} -- {_MODALITY_DESCRIPTIONS.get(modality, '')}",
        color="success",
        dismissable=True,
    )
    return modality, 1, status


# ---------------------------------------------------------------------------
# Wizard Navigation (step visibility)
# ---------------------------------------------------------------------------

@callback(
    Output("wizard-stepper-display", "children"),
    Output("wizard-step-1", "style"),
    Output("wizard-step-2", "style"),
    Output("wizard-step-3", "style"),
    Output("wizard-step-4", "style"),
    Output("wizard-step-5", "style"),
    Output("wizard-step-6", "style"),
    Output("step2-modality-badge", "children"),
    Output("mapping-axis-label", "children"),
    Output("mapping-signal-label", "children"),
    Output("mapping-rate-label", "children"),
    Input("import-wizard-step", "data"),
    State("import-selected-modality", "data"),
    prevent_initial_call=False,
)
def update_wizard_visibility(step, modality):
    step = int(step or 0)
    modality = modality or ""
    display = {"display": "block"}
    hidden = {"display": "none"}
    styles = [hidden] * 6
    if 0 <= step < 6:
        styles[step] = display

    stepper = stepper_indicator(_WIZARD_STEPS, step)
    badge = dbc.Badge(modality, color="primary", className="fs-6") if modality else ""
    axis_label = _MODALITY_AXIS_LABELS.get(modality, "Axis Column")
    signal_label = _MODALITY_SIGNAL_LABELS.get(modality, "Signal Column")
    rate_label = "Heating Rate (°C/min)" if modality in {"DSC", "TGA", "DTA"} else "Heating Rate (°C/min)"

    return (
        stepper,
        styles[0], styles[1], styles[2], styles[3], styles[4], styles[5],
        badge,
        axis_label,
        signal_label,
        rate_label,
    )


@callback(
    Output("import-wizard-step", "data", allow_duplicate=True),
    Input("step2-prev-btn", "n_clicks"),
    Input("step2-next-btn", "n_clicks"),
    Input("step3-prev-btn", "n_clicks"),
    Input("step3-next-btn", "n_clicks"),
    Input("step4-prev-btn", "n_clicks"),
    Input("step4-next-btn", "n_clicks"),
    Input("step5-prev-btn", "n_clicks"),
    Input("step5-next-btn", "n_clicks"),
    Input("step6-prev-btn", "n_clicks"),
    State("import-wizard-step", "data"),
    prevent_initial_call=True,
)
def navigate_wizard(c2p, c2n, c3p, c3n, c4p, c4n, c5p, c5n, c6p, step):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    step = int(step or 0)
    triggered_id = ctx.triggered_id
    step_map = {
        "step2-prev-btn": 0, "step2-next-btn": 2,
        "step3-prev-btn": 1, "step3-next-btn": 3,
        "step4-prev-btn": 2, "step4-next-btn": 4,
        "step5-prev-btn": 3, "step5-next-btn": 5,
        "step6-prev-btn": 4,
    }
    target = step_map.get(triggered_id)
    if target is None:
        raise dash.exceptions.PreventUpdate
    return target


# ---------------------------------------------------------------------------
# Step 2: File Upload
# ---------------------------------------------------------------------------

@callback(
    Output("upload-status", "children"),
    Output("pending-upload-files", "data"),
    Output("pending-file-select", "value"),
    Input("file-upload", "contents"),
    State("file-upload", "filename"),
    State("pending-upload-files", "data"),
    prevent_initial_call=True,
)
def collect_pending_uploads(contents_list, filenames, pending_files):
    if not contents_list:
        return dash.no_update, dash.no_update, dash.no_update

    pending_files = list(pending_files or [])
    existing = {item["file_name"] for item in pending_files}
    added = []
    for content, file_name in zip(contents_list, filenames):
        _, content_string = content.split(",", 1)
        if file_name in existing:
            continue
        pending_files.append({"file_name": file_name, "file_base64": content_string})
        added.append(file_name)

    if not added:
        return dbc.Alert("Files already queued for import preview.", color="info"), pending_files, dash.no_update

    return (
        dbc.Alert(f"Queued for preview: {', '.join(added)}", color="success", dismissable=True),
        pending_files,
        added[0],
    )


@callback(
    Output("pending-file-select", "options"),
    Output("pending-file-help", "children"),
    Input("pending-upload-files", "data"),
)
def pending_file_options(pending_files):
    items = pending_files or []
    options = [{"label": item["file_name"], "value": item["file_name"]} for item in items]
    help_text = (
        "Upload a file to preview, map, and import into the workspace."
        if not items
        else f"{len(items)} pending file(s) ready for preview and import."
    )
    return options, help_text


# ---------------------------------------------------------------------------
# Steps 3-4: Preview + Column Mapping (modality-aware)
# ---------------------------------------------------------------------------

@callback(
    Output("pending-import-preview", "data"),
    Output("mapping-preview-status", "children"),
    Output("mapping-preview-table", "children"),
    Output("mapping-temp-select", "options"),
    Output("mapping-temp-select", "value"),
    Output("mapping-signal-select", "options"),
    Output("mapping-signal-select", "value"),
    Output("mapping-time-select", "options"),
    Output("mapping-time-select", "value"),
    Output("mapping-sample-name", "value"),
    Output("mapping-sample-mass", "value"),
    Output("mapping-heating-rate", "value"),
    Output("mapping-xrd-wavelength", "value"),
    Output("xrd-wavelength-row", "style"),
    Input("pending-file-select", "value"),
    Input("import-selected-modality", "data"),
    State("pending-upload-files", "data"),
    prevent_initial_call=False,
)
def build_pending_preview(selected_file, modality, pending_files):
    modality = modality or ""
    empty_options = _mapping_options([])
    empty_result = (
        None,
        prereq_or_empty_help(
            "Upload a file and select it to preview raw data.",
            tone="secondary",
            title="No file selected",
        ),
        "",
        empty_options, _NONE_VALUE,
        empty_options, _NONE_VALUE,
        empty_options, _NONE_VALUE,
        "", 0, 10, 1.5406,
        {"display": "none"},
    )

    if not selected_file:
        return empty_result

    pending = next((item for item in (pending_files or []) if item["file_name"] == selected_file), None)
    if pending is None:
        raise dash.exceptions.PreventUpdate

    try:
        preview = build_import_preview(
            pending["file_name"],
            pending["file_base64"],
            modality=modality or None,
        )
    except Exception as exc:
        return (
            None,
            dbc.Alert(f"Preview failed: {exc}", color="danger"),
            "",
            empty_options, _NONE_VALUE,
            empty_options, _NONE_VALUE,
            empty_options, _NONE_VALUE,
            "", 0, 10, 1.5406,
            {"display": "block" if modality == "XRD" else "none"},
        )

    guessed = preview.get("guessed_mapping") or {}
    columns = preview["columns"]
    options = _mapping_options(columns)

    suggested_type = str(
        guessed.get("inferred_analysis_type")
        or guessed.get("data_type")
        or modality
        or "DSC"
    ).upper()
    if suggested_type not in set(_MODALITY_OPTIONS):
        suggested_type = modality or "DSC"

    preview_rows = preview["preview_rows"]
    table = dataset_table(preview_rows, columns, page_size=min(10, len(preview_rows)), table_id="raw-preview-table")

    confidence = (guessed.get("confidence") or {}).get("overall", "review")
    warnings = guessed.get("warnings") or []
    status_color = "success" if confidence == "high" else ("warning" if confidence == "medium" else "info")
    status_text = (
        f"Preview ready: {preview['file_name']} | rows={preview['row_count']} | "
        f"detected type={suggested_type} | confidence={confidence}"
    )
    if warnings:
        status_text += f" | {len(warnings)} warning(s)"
    status = dbc.Alert(status_text, color=status_color)

    def _pick(column_name: str | None) -> str:
        return column_name if column_name in columns else _NONE_VALUE

    xrd_style = {"display": "block"} if modality == "XRD" else {"display": "none"}

    return (
        preview,
        status,
        table,
        options, _pick(guessed.get("temperature")),
        options, _pick(guessed.get("signal")),
        options, _pick(guessed.get("time")),
        "", 0, 10, 1.5406,
        xrd_style,
    )


# ---------------------------------------------------------------------------
# Step 5: Review units/metadata
# ---------------------------------------------------------------------------

@callback(
    Output("review-unit-status", "children"),
    Output("review-metadata-summary", "children"),
    Output("review-warnings-list", "children"),
    Output("import-review-data", "data"),
    Input("import-wizard-step", "data"),
    State("pending-import-preview", "data"),
    State("import-selected-modality", "data"),
    State("mapping-temp-select", "value"),
    State("mapping-signal-select", "value"),
    State("mapping-time-select", "value"),
    State("mapping-sample-name", "value"),
    State("mapping-sample-mass", "value"),
    State("mapping-heating-rate", "value"),
    State("mapping-xrd-wavelength", "value"),
    prevent_initial_call=False,
)
def build_review_data(
    step, preview, modality,
    temp_col, signal_col, time_col,
    sample_name, sample_mass, heating_rate, xrd_wavelength,
):
    step = int(step or 0)
    if step != 4:
        raise dash.exceptions.PreventUpdate

    if not preview:
        return prereq_or_empty_help("No preview data available. Go back and upload a file.", title="No data"), "", "", None

    guessed = preview.get("guessed_mapping") or {}
    modality = modality or ""
    confidence = (guessed.get("confidence") or {}).get("overall", "review")
    warnings = guessed.get("warnings") or []

    # Unit review
    detected_x_unit = guessed.get("inferred_signal_unit", "unknown")
    columns = preview.get("columns", [])

    # Build review display
    unit_rows = []
    if temp_col and temp_col != _NONE_VALUE:
        unit_rows.append(html.Tr([html.Td("Axis"), html.Td(temp_col)]))
    if signal_col and signal_col != _NONE_VALUE:
        unit_rows.append(html.Tr([html.Td("Signal"), html.Td(signal_col)]))
    if time_col and time_col != _NONE_VALUE:
        unit_rows.append(html.Tr([html.Td("Time"), html.Td(time_col)]))

    unit_table = dbc.Table(
        [html.Thead(html.Tr([html.Th("Role"), html.Th("Column")]))] + [html.Tbody(unit_rows)],
        bordered=True, size="sm", className="mt-2",
    )

    # Suspicious unit combos via modality specs
    spec_warnings = []
    if modality:
        try:
            from core.modality_specs import check_suspicious_unit_combo
            x_unit = guessed.get("inferred_x_unit", "")
            y_unit = guessed.get("inferred_signal_unit", "")
            spec_warnings = check_suspicious_unit_combo(modality, x_unit, y_unit)
        except ImportError:
            pass

    all_warnings = warnings + spec_warnings
    warning_items = []
    if all_warnings:
        for w in all_warnings:
            warning_items.append(html.Li(w, className="text-warning"))
        warning_list = html.Ul(warning_items, className="mt-2")
    else:
        warning_list = html.P("No warnings detected.", className="text-success")

    # Confidence badge
    conf_color = {"high": "success", "medium": "warning", "review": "info"}.get(confidence, "secondary")
    conf_badge = dbc.Badge(f"Confidence: {confidence}", color=conf_color, className="me-2")

    # Metadata summary
    meta_items = []
    meta_items.append(html.Tr([html.Td("Modality"), html.Td(dbc.Badge(modality, color="primary"))]))
    meta_items.append(html.Tr([html.Td("Sample Name"), html.Td(sample_name or "Unknown")]))
    meta_items.append(html.Tr([html.Td("Sample Mass"), html.Td(f"{sample_mass} mg" if sample_mass else "Not set")]))
    if modality in {"DSC", "TGA", "DTA"}:
        meta_items.append(html.Tr([html.Td("Heating Rate"), html.Td(f"{heating_rate} °C/min" if heating_rate else "Not set")]))
    if modality == "XRD":
        meta_items.append(html.Tr([html.Td("Wavelength"), html.Td(f"{xrd_wavelength} Å" if xrd_wavelength else "Not set")]))

    meta_table = dbc.Table(
        [html.Thead(html.Tr([html.Th("Field"), html.Th("Value")]))] + [html.Tbody(meta_items)],
        bordered=True, size="sm", className="mt-2",
    )

    review_data = {
        "modality": modality,
        "confidence": confidence,
        "temp_col": temp_col,
        "signal_col": signal_col,
        "time_col": time_col,
        "sample_name": sample_name,
        "sample_mass": sample_mass,
        "heating_rate": heating_rate,
        "xrd_wavelength": xrd_wavelength,
        "warnings": all_warnings,
    }

    return (
        html.Div([conf_badge, html.Span("Unit Review:"), unit_table]),
        html.Div([html.Strong("Metadata Summary:"), meta_table]),
        html.Div([html.Strong("Warnings & Flags:"), warning_list]),
        review_data,
    )


# ---------------------------------------------------------------------------
# Step 6: Validation summary
# ---------------------------------------------------------------------------

@callback(
    Output("validation-summary-status", "children"),
    Output("validation-summary-warnings", "children"),
    Output("validation-summary-details", "children"),
    Input("import-wizard-step", "data"),
    State("import-review-data", "data"),
    prevent_initial_call=False,
)
def build_validation_summary(step, review_data):
    step = int(step or 0)
    if step != 5:
        raise dash.exceptions.PreventUpdate

    if not review_data:
        return prereq_or_empty_help("No review data available.", title="No data"), "", ""

    modality = review_data.get("modality", "")
    confidence = review_data.get("confidence", "review")
    warnings = review_data.get("warnings") or []
    temp_col = review_data.get("temp_col", "")
    signal_col = review_data.get("signal_col", "")

    # Determine validation status
    has_blocking = temp_col == _NONE_VALUE or signal_col == _NONE_VALUE
    if has_blocking:
        status = "fail"
    elif confidence == "review" or any("suspicious" in w.lower() or "unusual" in w.lower() for w in warnings):
        status = "pass_with_review"
    elif warnings:
        status = "warn"
    else:
        status = "pass"

    status_badge = _validation_status_badge(status)
    status_text = {
        "pass": "All checks passed. Ready to import.",
        "pass_with_review": "Data is importable but review flags detected. Inspect warnings before confirming.",
        "warn": "Warnings detected. Review before confirming.",
        "fail": "Blocking issues detected. Go back and fix column mapping.",
    }.get(status, "")

    status_display = html.Div(
        [
            html.H6("Import Status:", className="d-inline me-2"),
            status_badge,
            html.P(status_text, className="mt-2"),
        ],
        className="mb-3",
    )

    warning_display = ""
    if warnings:
        items = [html.Li(w, className="text-warning") for w in warnings]
        warning_display = html.Div([html.Strong("Warnings:"), html.Ul(items, className="mt-1")])

    details = html.Div(
        [
            html.Strong("Summary:"),
            html.Ul(
                [
                    html.Li(f"Technique: {modality}"),
                    html.Li(f"Axis column: {temp_col}"),
                    html.Li(f"Signal column: {signal_col}"),
                    html.Li(f"Confidence: {confidence}"),
                ]
            ),
        ]
    )

    return status_display, warning_display, details


# ---------------------------------------------------------------------------
# Confirm Import
# ---------------------------------------------------------------------------

@callback(
    Output("upload-status", "children", allow_duplicate=True),
    Output("pending-upload-files", "data", allow_duplicate=True),
    Output("pending-file-select", "value", allow_duplicate=True),
    Output("home-refresh", "data", allow_duplicate=True),
    Output("import-wizard-step", "data", allow_duplicate=True),
    Input("import-mapped-btn", "n_clicks"),
    State("project-id", "data"),
    State("pending-import-preview", "data"),
    State("pending-upload-files", "data"),
    State("pending-file-select", "value"),
    State("import-selected-modality", "data"),
    State("mapping-temp-select", "value"),
    State("mapping-signal-select", "value"),
    State("mapping-time-select", "value"),
    State("mapping-sample-name", "value"),
    State("mapping-sample-mass", "value"),
    State("mapping-heating-rate", "value"),
    State("mapping-xrd-wavelength", "value"),
    State("home-refresh", "data"),
    prevent_initial_call=True,
)
def import_with_mapping(
    n_clicks,
    project_id,
    preview,
    pending_files,
    selected_file,
    modality,
    temp_col,
    signal_col,
    time_col,
    sample_name,
    sample_mass,
    heating_rate,
    xrd_wavelength,
    refresh_value,
):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate

    if not project_id:
        return (
            prereq_or_empty_help(
                "No active workspace. Open Project Workspace to start or load one, then import again.",
                title="Workspace required",
            ),
            dash.no_update, dash.no_update, dash.no_update, dash.no_update,
        )

    if not preview:
        return (
            prereq_or_empty_help(
                "Select a pending file to build a preview before importing.",
                tone="secondary",
                title="Preview required",
            ),
            dash.no_update, dash.no_update, dash.no_update, dash.no_update,
        )

    if temp_col == _NONE_VALUE or signal_col == _NONE_VALUE:
        return (
            dbc.Alert("Axis and signal columns are required.", color="warning"),
            dash.no_update, dash.no_update, dash.no_update, dash.no_update,
        )

    available_columns = set(preview.get("columns", []))
    if temp_col not in available_columns or signal_col not in available_columns:
        return (
            dbc.Alert(
                "Column mapping is stale. Select the file again, then re-map axis and signal columns.",
                color="warning",
            ),
            dash.no_update, dash.no_update, dash.no_update, dash.no_update,
        )

    from dash_app.api_client import dataset_import as api_dataset_import

    data_type = modality or "DSC"
    metadata = {
        "sample_name": sample_name or "Unknown",
        "sample_mass": float(sample_mass) if sample_mass not in (None, "", 0, 0.0) else None,
        "heating_rate": float(heating_rate) if data_type not in {"XRD", "FTIR", "RAMAN"} and heating_rate not in (None, "", 0, 0.0) else None,
        "xrd_wavelength_angstrom": float(xrd_wavelength) if data_type == "XRD" and xrd_wavelength not in (None, "", 0, 0.0) else None,
    }
    column_mapping = {
        "temperature": temp_col,
        "signal": signal_col,
    }
    if time_col and time_col != _NONE_VALUE:
        column_mapping["time"] = time_col

    try:
        result = api_dataset_import(
            project_id,
            preview["file_name"],
            preview["file_base64"],
            data_type=data_type,
            column_mapping=column_mapping,
            metadata=metadata,
        )
    except Exception as exc:
        exc_msg = str(exc)
        hint = ""
        if "thermal-analysis bounds" in exc_msg or "Temperature range" in exc_msg:
            hint = " Hint: the axis range looks like wavenumber data -- try selecting FTIR or RAMAN."
        elif "strictly increasing" in exc_msg:
            hint = " Hint: the axis is not monotonic -- check column mapping or try FTIR/RAMAN for spectral data."
        return (
            dbc.Alert(f"Import failed: {exc_msg}{hint}", color="danger", dismissable=True),
            dash.no_update, dash.no_update, dash.no_update, dash.no_update,
        )

    remaining = [item for item in (pending_files or []) if item["file_name"] != selected_file]
    next_selected = remaining[0]["file_name"] if remaining else None
    ds = result.get("dataset", {})
    return (
        dbc.Alert(
            (
                f"Imported: {ds.get('display_name', preview['file_name'])} ({ds.get('data_type', '?')}). "
                "Next: confirm workspace status in Project Workspace."
            ),
            color="success",
            dismissable=True,
        ),
        remaining,
        next_selected,
        int(refresh_value or 0) + 1,
        0,  # Reset wizard to step 0
    )


# ---------------------------------------------------------------------------
# Sample Data
# ---------------------------------------------------------------------------

@callback(
    Output("sample-status", "children"),
    Output("home-refresh", "data", allow_duplicate=True),
    Input({"type": "sample-load", "sample_id": ALL}, "n_clicks"),
    State({"type": "sample-load", "sample_id": ALL}, "id"),
    State("project-id", "data"),
    State("home-refresh", "data"),
    prevent_initial_call=True,
)
def load_sample(_clicks, ids, project_id, refresh_value):
    if not project_id:
        return (
            prereq_or_empty_help(
                "No active workspace. Open Project Workspace to start or load one, then load sample data.",
                title="Workspace required",
            ),
            dash.no_update,
        )
    ctx = dash.callback_context
    triggered = ctx.triggered_id
    if not triggered:
        raise dash.exceptions.PreventUpdate

    button_id = triggered.get("sample_id") if isinstance(triggered, dict) else None
    sample_path, dtype = resolve_sample_request(button_id or "")
    if sample_path is None or dtype is None:
        raise dash.exceptions.PreventUpdate

    if not sample_path.exists():
        return dbc.Alert(f"Sample file not found: {sample_path.name}", color="warning"), dash.no_update

    from dash_app.api_client import dataset_import

    try:
        result = dataset_import(
            project_id,
            sample_path.name,
            base64.b64encode(sample_path.read_bytes()).decode("ascii"),
            data_type=dtype,
        )
    except Exception as exc:
        return dbc.Alert(f"Sample load failed: {exc}", color="danger"), dash.no_update

    dataset = result.get("dataset", {})
    return (
        dbc.Alert(
            f"Loaded sample: {dataset.get('display_name', sample_path.name)}",
            color="success",
            dismissable=True,
        ),
        int(refresh_value or 0) + 1,
    )


# ---------------------------------------------------------------------------
# Loaded Datasets Panel
# ---------------------------------------------------------------------------

@callback(
    Output("import-metrics", "children"),
    Output("datasets-table", "children"),
    Output("active-dataset-select", "options"),
    Output("active-dataset-select", "value"),
    Input("project-id", "data"),
    Input("home-refresh", "data"),
    Input("ui-theme", "data"),
    prevent_initial_call=False,
)
def load_workspace_datasets(project_id, _refresh, _ui_theme):
    if not project_id:
        return (
            "",
            prereq_or_empty_help(
                "No active workspace. Open Project Workspace to create or load a workspace, then return to Import.",
                title="Workspace required",
            ),
            [],
            None,
        )

    from dash_app.api_client import workspace_datasets

    try:
        payload = workspace_datasets(project_id)
    except Exception as exc:
        error = html.P(f"Error: {exc}", className="text-danger")
        return "", error, [], None

    datasets = payload.get("datasets", [])
    if not datasets:
        return (
            _build_metrics([]),
            prereq_or_empty_help(
                "No datasets are loaded yet. Upload files or load sample datasets to populate this workspace.",
                tone="secondary",
                title="No datasets in workspace",
            ),
            [],
            None,
        )

    rows = [
        {
            "key": item.get("key"),
            "display_name": item.get("display_name"),
            "data_type": item.get("data_type"),
            "vendor": item.get("vendor"),
            "sample_name": item.get("sample_name"),
            "points": item.get("points"),
            "validation_status": item.get("validation_status"),
        }
        for item in datasets
    ]
    table = dataset_table(rows, ["key", "display_name", "data_type", "vendor", "sample_name", "points", "validation_status"], table_id="datasets-summary-table")
    options = [{"label": item.get("display_name", item.get("key")), "value": item.get("key")} for item in datasets]
    return _build_metrics(datasets), table, options, payload.get("active_dataset")


@callback(
    Output("home-refresh", "data", allow_duplicate=True),
    Input("active-dataset-select", "value"),
    State("project-id", "data"),
    State("home-refresh", "data"),
    prevent_initial_call=True,
)
def set_active_dataset(dataset_key, project_id, refresh_value):
    if not dataset_key or not project_id:
        raise dash.exceptions.PreventUpdate
    from dash_app.api_client import workspace_set_active_dataset

    workspace_set_active_dataset(project_id, dataset_key)
    return int(refresh_value or 0) + 1


@callback(
    Output("dataset-action-status", "children"),
    Output("home-refresh", "data", allow_duplicate=True),
    Input("remove-dataset-btn", "n_clicks"),
    State("active-dataset-select", "value"),
    State("project-id", "data"),
    State("home-refresh", "data"),
    prevent_initial_call=True,
)
def remove_dataset(n_clicks, dataset_key, project_id, refresh_value):
    if not n_clicks or not dataset_key or not project_id:
        raise dash.exceptions.PreventUpdate

    from dash_app.api_client import workspace_delete_dataset

    try:
        workspace_delete_dataset(project_id, dataset_key)
    except Exception as exc:
        return dbc.Alert(f"Remove failed: {exc}", color="danger"), dash.no_update
    return dbc.Alert(f"Removed dataset: {dataset_key}", color="warning"), int(refresh_value or 0) + 1


@callback(
    Output("dataset-detail-panel", "children"),
    Input("project-id", "data"),
    Input("active-dataset-select", "value"),
    Input("home-refresh", "data"),
    Input("ui-theme", "data"),
    prevent_initial_call=False,
)
def load_active_dataset_detail(project_id, dataset_key, _refresh, ui_theme):
    if not project_id:
        return prereq_or_empty_help(
            "No active workspace. Start or load a workspace in Project, then import datasets here.",
            title="Workspace required",
        )
    if not dataset_key:
        return prereq_or_empty_help(
            "Select an active dataset from the Loaded Datasets panel to inspect metadata, preview, and quick plot.",
            tone="secondary",
            title="Select a dataset",
        )

    from dash_app.api_client import workspace_dataset_data, workspace_dataset_detail

    try:
        detail = workspace_dataset_detail(project_id, dataset_key)
        data_payload = workspace_dataset_data(project_id, dataset_key)
    except Exception as exc:
        return html.P(f"Error: {exc}", className="text-danger")

    rows = data_payload.get("rows", [])
    columns = data_payload.get("columns", [])
    preview_rows = rows[:10]

    return html.Div(
        [
            html.H5(detail.get("dataset", {}).get("display_name", dataset_key), className="mb-3"),
            metric_cards(detail),
            dbc.Accordion(
                [
                    dbc.AccordionItem(metadata_list(detail), title="Metadata"),
                    dbc.AccordionItem(original_columns_list(detail), title="Column Mapping"),
                    dbc.AccordionItem(dataset_table(preview_rows, columns, page_size=min(10, len(preview_rows) or 1), table_id="active-dataset-table"), title="Data Preview"),
                    dbc.AccordionItem(stats_table(rows, columns), title="Statistics"),
                ],
                start_collapsed=True,
                always_open=True,
                className="mb-3",
            ),
            html.H6("Quick View", className="mb-2"),
            quick_plot(rows, detail, ui_theme=ui_theme),
        ]
    )
