"""Shared pure Dash UI boilerplate for analysis pages."""

from __future__ import annotations

import json
from typing import Any, Callable

import dash_bootstrap_components as dbc
from dash import html

from dash_app.components.analysis_page import finalized_validation_warning_issue_counts
from utils.i18n import translate_ui


def build_collapsible_section(
    loc: str,
    title_key: str,
    body: Any,
    *,
    open: bool = False,
    summary_suffix: Any | None = None,
) -> html.Details:
    summary_children: list[Any] = [
        html.Span(className="ta-details-chevron"),
        html.Span(translate_ui(loc, title_key), className="ms-1"),
    ]
    if summary_suffix is not None:
        if isinstance(summary_suffix, (list, tuple)):
            summary_children.extend(summary_suffix)
        else:
            summary_children.append(summary_suffix)
    return html.Details(
        [
            html.Summary(summary_children, className="ta-details-summary"),
            html.Div(body, className="ta-details-body mt-2"),
        ],
        className="ta-ms-details mb-0",
        open=open,
    )


def build_processing_history_card(
    *,
    title_id: str,
    hint_id: str,
    undo_button_id: str,
    redo_button_id: str,
    reset_button_id: str,
    status_id: str,
    card_class_name: str = "mb-3",
    body_class_name: str | None = None,
) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H6(id=title_id, className="card-title mb-1"),
                html.P(id=hint_id, className="small text-muted mb-2"),
                dbc.Row(
                    [
                        dbc.Col(dbc.Button(id=undo_button_id, color="secondary", size="sm", outline=True, disabled=True), width="auto"),
                        dbc.Col(dbc.Button(id=redo_button_id, color="secondary", size="sm", outline=True, disabled=True), width="auto"),
                        dbc.Col(dbc.Button(id=reset_button_id, color="secondary", size="sm", outline=True), width="auto"),
                    ],
                    className="g-2 align-items-center mb-1",
                ),
                html.Div(id=status_id, className="small text-muted"),
            ],
            className=body_class_name,
        ),
        className=card_class_name,
    )


def build_apply_preset_card(
    *,
    id_prefix: str,
    card_class_name: str = "mb-3",
    body_class_name: str | None = None,
    include_dirty_state: bool = False,
) -> dbc.Card:
    dirty_children: list[Any] = []
    if include_dirty_state:
        dirty_children = [
            html.Div(id=f"{id_prefix}-preset-loaded-line", className="small mb-1"),
            html.Div(id=f"{id_prefix}-preset-dirty-flag", className="small mb-2"),
        ]
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id=f"{id_prefix}-preset-card-title", className="card-title mb-1"),
                html.Small(id=f"{id_prefix}-preset-help", className="form-text text-muted d-block mb-2"),
                html.Div(id=f"{id_prefix}-preset-caption", className="small text-muted mb-2"),
                *dirty_children,
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id=f"{id_prefix}-preset-select-label", html_for=f"{id_prefix}-preset-select"),
                                dbc.Select(id=f"{id_prefix}-preset-select", options=[], value=None),
                            ],
                            md=12,
                        ),
                    ],
                    className="mb-2",
                ),
                dbc.ButtonGroup(
                    [
                        dbc.Button(id=f"{id_prefix}-preset-apply-btn", color="primary", size="sm", disabled=True),
                        dbc.Button(id=f"{id_prefix}-preset-delete-btn", color="secondary", size="sm", outline=True, disabled=True),
                    ],
                    className="mb-3",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(id=f"{id_prefix}-preset-save-name-label", html_for=f"{id_prefix}-preset-save-name"),
                                dbc.Input(id=f"{id_prefix}-preset-save-name", type="text", value="", maxLength=80),
                            ],
                            md=12,
                        ),
                    ],
                    className="mb-2",
                ),
                dbc.Button(id=f"{id_prefix}-preset-save-btn", color="primary", size="sm", className="mb-2"),
                html.Div(id=f"{id_prefix}-preset-status", className="small text-muted"),
            ],
            className=body_class_name,
        ),
        className=card_class_name,
    )


def build_load_saveas_preset_card(
    *,
    id_prefix: str,
    card_class_name: str = "mb-3",
    body_class_name: str | None = None,
) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5(id=f"{id_prefix}-preset-card-title", className="card-title mb-1"),
                html.Small(id=f"{id_prefix}-preset-help", className="form-text text-muted d-block mb-2"),
                html.Div(id=f"{id_prefix}-preset-caption", className="small text-muted mb-2"),
                html.Div(id=f"{id_prefix}-preset-loaded-line", className="small mb-1"),
                html.Div(id=f"{id_prefix}-preset-dirty-flag", className="small mb-2"),
                dbc.Label(id=f"{id_prefix}-preset-select-label", html_for=f"{id_prefix}-preset-select", className="mb-1"),
                dbc.Select(id=f"{id_prefix}-preset-select", options=[], value=None),
                dbc.Row(
                    [
                        dbc.Col(dbc.Button(id=f"{id_prefix}-preset-load-btn", color="primary", size="sm", disabled=True, className="me-2"), width="auto"),
                        dbc.Col(dbc.Button(id=f"{id_prefix}-preset-delete-btn", color="secondary", size="sm", outline=True, disabled=True), width="auto"),
                    ],
                    className="g-2 my-2 align-items-center",
                ),
                dbc.Label(id=f"{id_prefix}-preset-save-name-label", html_for=f"{id_prefix}-preset-save-name", className="mb-1"),
                dbc.Input(id=f"{id_prefix}-preset-save-name", type="text", value="", maxLength=80),
                html.Small(id=f"{id_prefix}-preset-save-hint", className="text-muted d-block my-1"),
                dbc.Row(
                    [
                        dbc.Col(dbc.Button(id=f"{id_prefix}-preset-save-btn", color="primary", size="sm", className="me-2"), width="auto"),
                        dbc.Col(dbc.Button(id=f"{id_prefix}-preset-saveas-btn", color="secondary", size="sm", outline=True), width="auto"),
                    ],
                    className="g-2 mb-2 align-items-center",
                ),
                html.Div(id=f"{id_prefix}-preset-status", className="small text-muted"),
            ],
            className=body_class_name,
        ),
        className=card_class_name,
    )


def build_validation_quality_card(
    detail: dict,
    result_meta: dict,
    loc: str,
    *,
    i18n_prefix: str,
    collapsible_builder: Callable[..., html.Details] = build_collapsible_section,
    derive_counts_from_lists: bool = True,
    open_when_attention: bool = False,
    include_attention_badges: bool = False,
) -> html.Details:
    validation = detail.get("validation") if isinstance(detail.get("validation"), dict) else {}
    status = str(validation.get("status") or result_meta.get("validation_status") or "unknown")
    warnings_list = validation.get("warnings") if isinstance(validation.get("warnings"), list) else []
    issues_list = validation.get("issues") if isinstance(validation.get("issues"), list) else []
    if derive_counts_from_lists:
        wc, ic = finalized_validation_warning_issue_counts(validation)
    else:
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
        html.P([html.Strong(translate_ui(loc, f"{i18n_prefix}.status_label")), f" {status}"], className="mb-2"),
        html.P([html.Strong(translate_ui(loc, f"{i18n_prefix}.warnings_label")), f" {wc}"], className="mb-2"),
        html.P([html.Strong(translate_ui(loc, f"{i18n_prefix}.issues_label")), f" {ic}"], className="mb-0"),
    ]
    if warnings_list:
        body_children.append(html.Ul([html.Li(str(w)) for w in warnings_list[:12]], className="small mb-0 mt-2"))
    if issues_list:
        body_children.append(html.Ul([html.Li(str(w)) for w in issues_list[:12]], className="small mb-0 mt-2"))

    summary_suffix: list[Any] | None = None
    if include_attention_badges:
        summary_suffix = []
        if wc:
            summary_suffix.append(
                dbc.Badge(
                    translate_ui(loc, f"{i18n_prefix}.badge_warnings", n=wc),
                    color="warning",
                    text_color="dark",
                    className="ms-2",
                    pill=True,
                )
            )
        if ic:
            summary_suffix.append(
                dbc.Badge(
                    translate_ui(loc, f"{i18n_prefix}.badge_issues", n=ic),
                    color="danger",
                    className="ms-2",
                    pill=True,
                )
            )
        if not summary_suffix:
            summary_suffix = None

    inner = dbc.Alert(body_children, color=alert_color, className="mb-0 ta-quality-alert")
    return collapsible_builder(
        loc,
        f"{i18n_prefix}.card_title",
        inner,
        open=(wc > 0 or ic > 0) if open_when_attention else False,
        summary_suffix=summary_suffix,
    )


def build_split_raw_metadata_panel(
    metadata: dict | None,
    loc: str,
    *,
    i18n_prefix: str,
    user_facing_keys: frozenset[str],
    value_formatter: Callable[[Any], str | None],
    collapsible_builder: Callable[..., html.Details] = build_collapsible_section,
) -> html.Details:
    meta = metadata if isinstance(metadata, dict) else {}
    if not meta:
        inner = html.P(translate_ui(loc, f"{i18n_prefix}.empty"), className="text-muted mb-0")
    else:
        user_keys = sorted([k for k in meta if k in user_facing_keys], key=lambda k: str(k).lower())
        tech_keys = sorted([k for k in meta if k not in user_facing_keys], key=lambda k: str(k).lower())

        def _make_rows(keys: list[str]) -> list[Any]:
            rows: list[Any] = []
            for key in keys:
                value = meta[key]
                if isinstance(value, (dict, list)):
                    text = json.dumps(value, ensure_ascii=False, indent=2)
                else:
                    formatted = value_formatter(value)
                    text = formatted if formatted is not None else str(value)
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
            tech_collapsible = build_collapsible_section(
                loc,
                f"{i18n_prefix}.technical_details",
                html.Dl(_make_rows(tech_keys), className="row mb-0"),
                open=False,
            )
            body_parts.append(html.Div(tech_collapsible, className="mt-2"))
        inner = html.Div(body_parts) if body_parts else html.P(translate_ui(loc, f"{i18n_prefix}.empty"), className="text-muted mb-0")
    return collapsible_builder(loc, f"{i18n_prefix}.card_title", inner, open=False)
