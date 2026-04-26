"""About page -- product information for MaterialScope."""

from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, html

from dash_app.components.chrome import page_header
from utils.i18n import normalize_ui_locale, translate_ui

dash.register_page(__name__, path="/about", title="About - MaterialScope")


AUDIENCES = [
    (
        "research",
        "research_title",
        "research_copy",
    ),
    (
        "qc",
        "qc_title",
        "qc_copy",
    ),
    (
        "graduate",
        "graduate_title",
        "graduate_copy",
    ),
    (
        "testing",
        "testing_title",
        "testing_copy",
    ),
    (
        "partners",
        "partners_title",
        "partners_copy",
    ),
]

CAPABILITIES = ["import", "visualization", "analysis", "comparison", "workspace", "figures", "reporting"]

MODALITIES = [
    (
        "DSC",
        "Differential Scanning Calorimetry",
        "dsc_scope",
    ),
    (
        "TGA",
        "Thermogravimetric Analysis",
        "tga_scope",
    ),
    (
        "DTA",
        "Differential Thermal Analysis",
        "dta_scope",
    ),
    (
        "FTIR",
        "Fourier-Transform Infrared Spectroscopy",
        "ftir_scope",
    ),
    (
        "Raman",
        "Raman Spectroscopy",
        "raman_scope",
    ),
    (
        "XRD",
        "X-Ray Diffraction",
        "xrd_scope",
    ),
]

WORKFLOW_STEPS = ["import", "select", "inspect", "compare", "capture", "report"]

ARCHITECTURE_POINTS = ["frontend", "backend", "core", "workspace"]


def _loc(locale_data: str | None) -> str:
    return normalize_ui_locale(locale_data)


def _t(loc: str, key: str) -> str:
    return translate_ui(loc, f"dash.about.{key}")


def _section_card(title: str, children: list) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H3(title, className="about-section-title"),
                *children,
            ]
        ),
        className="about-section-card",
    )


def _audience_grid(loc: str) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(label, className="about-audience-label"),
                            html.H4(title, className="about-audience-title"),
                        ],
                        className="about-audience-heading",
                    ),
                    html.P(description, className="about-audience-copy"),
                ],
                className="about-audience-item",
            )
            for label, title, description in (
                (_t(loc, f"audience.{label}"), _t(loc, f"audience.{title}"), _t(loc, f"audience.{description}"))
                for label, title, description in AUDIENCES
            )
        ],
        className="about-audience-grid",
    )


def _capability_grid(loc: str) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Span(f"{idx:02d}", className="about-capability-index"),
                    html.Span(_t(loc, f"capability.{item}"), className="about-capability-text"),
                ],
                className="about-capability-item",
            )
            for idx, item in enumerate(CAPABILITIES, start=1)
        ],
        className="about-capability-grid",
    )


def _modality_table(loc: str) -> dbc.Table:
    return dbc.Table(
        [
            html.Thead(
                html.Tr(
                    [
                        html.Th(_t(loc, "modalities.modality")),
                        html.Th(_t(loc, "modalities.full_name")),
                        html.Th(_t(loc, "modalities.current_scope")),
                    ]
                )
            ),
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td(html.Strong(modality)),
                            html.Td(full_name),
                            html.Td(_t(loc, f"modalities.{scope}")),
                        ]
                    )
                    for modality, full_name, scope in MODALITIES
                ]
            ),
        ],
        responsive=True,
        bordered=False,
        hover=True,
        className="about-modality-table mb-0",
    )


def _workflow_diagram(loc: str) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(str(idx), className="about-workflow-number"),
                    html.Div(_t(loc, f"workflow.{step}"), className="about-workflow-text"),
                ],
                className="about-workflow-step",
            )
            for idx, step in enumerate(WORKFLOW_STEPS, start=1)
        ],
        className="about-workflow-diagram",
    )


def _architecture_points(loc: str) -> html.Ul:
    return html.Ul(
        [html.Li(_t(loc, f"architecture.{point}")) for point in ARCHITECTURE_POINTS],
        className="about-architecture-list",
    )


def _render_about_page(loc: str) -> html.Div:
    return html.Div(
        [
            page_header(
                _t(loc, "header.title"),
                _t(loc, "header.subtitle"),
                badge=_t(loc, "header.badge"),
            ),
            html.Div(
                [
                    _section_card(
                        _t(loc, "what.title"),
                        [
                            html.P(
                                _t(loc, "what.copy_1"),
                                className="about-lead",
                            ),
                            html.P(
                                _t(loc, "what.copy_2"),
                                className="mb-0",
                            ),
                        ],
                    ),
                    _section_card(_t(loc, "audience.title"), [_audience_grid(loc)]),
                    _section_card(_t(loc, "capability.title"), [_capability_grid(loc)]),
                    _section_card(_t(loc, "modalities.title"), [_modality_table(loc)]),
                    _section_card(_t(loc, "workflow.title"), [_workflow_diagram(loc)]),
                    _section_card(
                        _t(loc, "architecture.title"),
                        [
                            html.P(
                                _t(loc, "architecture.copy"),
                                className="mb-3",
                            ),
                            _architecture_points(loc),
                            html.P(
                                _t(loc, "architecture.note"),
                                className="about-note mb-0",
                            ),
                        ],
                    ),
                    _section_card(
                        _t(loc, "status.title"),
                        [
                            html.P(
                                _t(loc, "status.copy"),
                                className="mb-0",
                            ),
                        ],
                    ),
                    html.Div(
                        [
                            html.H3(_t(loc, "notice.title"), className="about-notice-title"),
                            html.P(
                                _t(loc, "notice.copy"),
                                className="mb-0",
                            ),
                        ],
                        className="about-validation-notice",
                    ),
                ],
                className="about-page-content",
            ),
        ],
        className="about-page",
    )


layout = html.Div(html.Div(id="about-page-slot"))


@callback(
    Output("about-page-slot", "children"),
    Input("ui-locale", "data"),
)
def render_about_page(locale_data):
    return _render_about_page(_loc(locale_data))
