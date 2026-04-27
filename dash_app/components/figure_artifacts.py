"""Shared figure artifact UI helpers for Dash analysis pages.

This module intentionally stays UI/pure-helper only. Page modules own Dash
callbacks and API orchestration for registering and fetching figures.
"""

from __future__ import annotations

from typing import Any

import dash_bootstrap_components as dbc
from dash import html

from utils.i18n import translate_ui


FIGURE_ARTIFACT_PREVIEW_TILES = 6
FIGURE_ARTIFACT_PREVIEW_MAX_EDGE = 320
GENERIC_FIGURE_I18N_PREFIX = "dash.analysis.figure"
RESULT_GRAPH_STYLE = {"height": "420px", "minHeight": "420px", "width": "100%"}


def _classes(*values: str | None) -> str:
    return " ".join(str(v).strip() for v in values if str(v or "").strip())


def result_graph_class(*values: str | None) -> str:
    """Return the standard class list for browser-visible analysis graphs."""
    return _classes("ta-plot", "ms-result-graph", *values)


def result_graph_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ensure Plotly stays responsive without dropping page-specific options."""
    merged = dict(config or {})
    merged["responsive"] = True
    return merged


def prepare_result_graph_figure(fig: Any) -> Any:
    """Mark a Plotly figure as autosized for Dash's responsive Graph renderer."""
    update_layout = getattr(fig, "update_layout", None)
    if callable(update_layout):
        update_layout(autosize=True)
    return fig


def primary_report_figure_label(analysis_type: str, dataset_key: str | None, result_id: str | None) -> str:
    dk = str(dataset_key or "").strip() or str(result_id or "").strip() or "dataset"
    return f"{str(analysis_type or 'ANALYSIS').upper()} Analysis - {dk}"


def snapshot_figure_label(
    analysis_type: str,
    dataset_key: str | None,
    result_id: str | None,
    stamp: str,
) -> str:
    dk = str(dataset_key or "").strip() or str(result_id or "").strip() or "dataset"
    clean_stamp = str(stamp or "").strip()
    suffix = f" - {clean_stamp}" if clean_stamp else ""
    return f"{str(analysis_type or 'ANALYSIS').upper()} Snapshot - {dk}{suffix}"


def figure_action_metadata(
    action: str,
    *,
    analysis_type: str,
    dataset_key: str | None,
    result_id: str | None,
    snapshot_stamp: str = "",
) -> dict[str, Any]:
    clean_action = str(action or "").strip().lower()
    if clean_action == "snapshot":
        return {
            "action": "snapshot",
            "label": snapshot_figure_label(analysis_type, dataset_key, result_id, snapshot_stamp),
            "replace": False,
            "success_key": "snapshot_ok",
        }
    if clean_action == "report":
        return {
            "action": "report",
            "label": primary_report_figure_label(analysis_type, dataset_key, result_id),
            "replace": True,
            "success_key": "report_ok",
        }
    return {}


def figure_action_from_trigger(
    triggered_id: str | None,
    *,
    snapshot_button_id: str,
    report_button_id: str,
) -> str | None:
    if triggered_id == snapshot_button_id:
        return "snapshot"
    if triggered_id == report_button_id:
        return "report"
    return None


def ordered_figure_preview_keys(figure_artifacts: dict | None) -> list[str]:
    """Prefer report figure first, then remaining registered keys, deduped."""
    fa = figure_artifacts if isinstance(figure_artifacts, dict) else {}
    keys = [str(k).strip() for k in (fa.get("figure_keys") or []) if isinstance(k, str) and str(k).strip()]
    primary = str(fa.get("report_figure_key") or "").strip()
    ordered: list[str] = []
    if primary:
        ordered.append(primary)
    for key in keys:
        if key not in ordered:
            ordered.append(key)
    return ordered


def figure_artifact_count(figure_artifacts: dict | None) -> int:
    return len(ordered_figure_preview_keys(figure_artifacts))


def figure_artifact_button_labels(
    loc: str,
    *,
    i18n_prefix: str = GENERIC_FIGURE_I18N_PREFIX,
) -> tuple[str, str, str]:
    return (
        translate_ui(loc, f"{i18n_prefix}.btn_snapshot"),
        translate_ui(loc, f"{i18n_prefix}.btn_report"),
        translate_ui(loc, f"{i18n_prefix}.artifacts_details_summary"),
    )


def figure_action_status_alert(
    loc: str,
    *,
    i18n_prefix: str = GENERIC_FIGURE_I18N_PREFIX,
    action: str | None = None,
    status: str,
    figure_key: str | None = None,
    reason: str | None = None,
    class_prefix: str = "ms",
) -> dbc.Alert:
    clean_status = str(status or "").strip().lower()
    clean_action = str(action or "").strip().lower()
    if clean_status == "ok":
        key_name = "snapshot_ok" if clean_action == "snapshot" else "report_ok"
        return dbc.Alert(
            translate_ui(loc, f"{i18n_prefix}.{key_name}", figure_key=str(figure_key or "")),
            color="success",
            className=_classes("py-1 mb-0 small ms-figure-inline-alert", f"{class_prefix}-figure-inline-alert"),
        )
    if clean_status == "error":
        return dbc.Alert(
            translate_ui(loc, f"{i18n_prefix}.artifact_error", reason=str(reason or "")),
            color="danger",
            className=_classes("py-1 mb-0 small ms-figure-inline-alert", f"{class_prefix}-figure-inline-alert"),
        )
    return dbc.Alert(
        translate_ui(loc, f"{i18n_prefix}.artifact_skip", reason=str(reason or "")),
        color="secondary" if clean_status == "skipped" else "warning",
        className=_classes("py-1 mb-0 small ms-figure-inline-alert", f"{class_prefix}-figure-inline-alert"),
    )


def build_figure_artifact_surface(
    modality_id: str,
    *,
    figure_host_class: str = "mb-0",
    control_slot_id: str | None = None,
    control_slot_class: str = "",
    card_body_class: str = "",
    surface_class: str = "",
    artifacts_open: bool = False,
) -> html.Div:
    """Return a figure card that wraps the existing ``<modality>-result-figure`` slot."""
    prefix = str(modality_id).strip()
    controls: list[Any] = []
    if control_slot_id:
        controls.append(
            html.Div(
                id=control_slot_id,
                className=_classes(
                    "ms-figure-toolbar__overlay flex-grow-1 d-flex align-items-center",
                    f"{prefix}-figure-toolbar__overlay",
                    control_slot_class,
                ),
                style={"minWidth": "min(100%, 12.5rem)"},
            )
        )
    controls.append(
        dbc.ButtonGroup(
            [
                dbc.Button(
                    id=f"{prefix}-figure-save-snapshot-btn",
                    color="secondary",
                    size="sm",
                    outline=True,
                    disabled=True,
                    className="text-nowrap",
                ),
                dbc.Button(
                    id=f"{prefix}-figure-use-report-btn",
                    color="primary",
                    size="sm",
                    disabled=True,
                    className="text-nowrap",
                ),
            ],
            className=_classes(
                "ms-figure-toolbar__actions flex-shrink-0 align-self-center",
                f"{prefix}-figure-toolbar__actions",
            ),
        )
    )

    return html.Div(
        [
            dbc.Card(
                dbc.CardBody(
                    [
                        html.Div(
                            id=f"{prefix}-result-figure",
                            className=_classes("ms-figure-host", f"{prefix}-figure-host", figure_host_class),
                        ),
                        html.Div(
                            controls,
                            className=_classes(
                                "ms-figure-toolbar d-flex flex-wrap align-items-stretch gap-2 pt-2 mt-2 border-top border-secondary-subtle",
                                f"{prefix}-figure-toolbar",
                            ),
                        ),
                        html.Div(
                            id=f"{prefix}-figure-artifact-status",
                            className=_classes(
                                "ms-figure-artifact-status small mt-2 text-muted",
                                f"{prefix}-figure-artifact-status",
                            ),
                        ),
                    ],
                    className=_classes("ms-figure-shell-body", f"{prefix}-figure-shell-body", card_body_class),
                ),
                className="ms-result-figure-shell shadow-sm mb-0",
            ),
            html.Details(
                [
                    html.Summary(
                        [
                            html.Span(className="ta-details-chevron"),
                            html.Span(
                                id=f"{prefix}-figure-artifacts-summary",
                                className=_classes(
                                    "ms-1 small text-muted ms-figure-artifacts-summary-label",
                                    f"{prefix}-artifacts-summary-label",
                                ),
                            ),
                        ],
                        className=_classes(
                            "ta-details-summary py-1 ms-figure-artifacts-disclosure-summary",
                            f"{prefix}-artifacts-disclosure-summary",
                        ),
                    ),
                    html.Div(
                        id=f"{prefix}-result-figure-artifacts",
                        className=_classes(
                            "ta-details-body mt-2 small text-muted ms-figure-artifacts-body",
                            f"{prefix}-artifacts-body",
                        ),
                    ),
                ],
                className=_classes("ta-ms-details ms-figure-artifacts-disclosure mb-0 mt-2", f"ta-{prefix}-artifacts-disclosure"),
                open=artifacts_open,
            ),
        ],
        className=_classes("ms-figure-surface", f"{prefix}-figure-surface", surface_class),
    )


def build_figure_artifacts_panel(
    figure_artifacts: dict | None,
    loc: str,
    *,
    previews: dict[str, str] | None = None,
    i18n_prefix: str = GENERIC_FIGURE_I18N_PREFIX,
    class_prefix: str = "ms",
    max_preview_tiles: int = FIGURE_ARTIFACT_PREVIEW_TILES,
) -> html.Div:
    """Render saved figure metadata and optional inline preview data URLs."""
    fa = figure_artifacts if isinstance(figure_artifacts, dict) else {}
    keys = [str(k).strip() for k in (fa.get("figure_keys") or []) if isinstance(k, str) and str(k).strip()]
    primary = str(fa.get("report_figure_key") or "").strip()
    status = str(fa.get("report_figure_status") or "").strip()
    err = str(fa.get("report_figure_error") or "").strip()

    panel_class = _classes("ms-figure-artifacts-panel", f"{class_prefix}-figure-artifacts-panel")
    if not keys and not primary and not status and not err:
        return html.Div(
            html.P(translate_ui(loc, f"{i18n_prefix}.artifacts_none"), className="small text-muted mb-0"),
            className=panel_class,
        )

    primary_line = html.P(
        translate_ui(loc, f"{i18n_prefix}.artifacts_primary", label=primary)
        if primary
        else translate_ui(loc, f"{i18n_prefix}.artifacts_primary_none"),
        className=_classes(
            "small mb-1 ms-figure-artifacts-primary-line",
            "text-body-secondary" if primary else "text-muted opacity-75",
            f"{class_prefix}-artifacts-primary-line",
        ),
    )

    ordered = ordered_figure_preview_keys(fa)
    preview_children: list[Any] = []
    if previews is not None:
        preview_keys = ordered[: max(0, int(max_preview_tiles))]
        if preview_keys:
            preview_children.append(
                html.Div(
                    translate_ui(loc, f"{i18n_prefix}.artifacts_previews_heading"),
                    className=_classes("small text-muted mb-1 fw-normal ms-figure-artifacts-previews-label", f"{class_prefix}-artifacts-previews-label"),
                )
            )
            cols: list[Any] = []
            for key in preview_keys:
                src = str((previews or {}).get(key) or "").strip()
                badge = "* " if key == primary else ""
                label_short = key if len(key) <= 48 else key[:45] + "..."
                if src:
                    tile = [
                        html.Img(
                            src=src,
                            alt=key,
                            className=_classes(
                                "img-fluid rounded border border-secondary-subtle mb-1 ms-figure-artifact-preview-img",
                                f"{class_prefix}-artifact-preview-img",
                            ),
                            style={"maxHeight": "72px", "objectFit": "contain", "opacity": 0.94},
                        ),
                        html.Div(badge + label_short, className="small text-muted text-break opacity-90"),
                    ]
                else:
                    tile = [
                        html.Div(
                            translate_ui(loc, f"{i18n_prefix}.artifacts_preview_missing"),
                            className="border border-secondary-subtle rounded d-flex align-items-center justify-content-center text-muted small mb-1 bg-body-secondary bg-opacity-25",
                            style={"height": "72px"},
                        ),
                        html.Div(badge + label_short, className="small text-muted text-break opacity-90"),
                    ]
                cols.append(dbc.Col(tile, xs=12, sm=6, md=4, className="mb-1"))
            preview_children.append(dbc.Row(cols, className=_classes("g-2 mb-0 ms-figure-artifact-preview-row", f"{class_prefix}-artifact-preview-row")))
        if len(ordered) > max_preview_tiles:
            preview_children.append(
                html.P(
                    translate_ui(loc, f"{i18n_prefix}.artifacts_previews_truncated", n=len(ordered) - max_preview_tiles),
                    className="small text-muted mb-1",
                )
            )

    meta_lines: list[Any] = []
    if status:
        meta_lines.append(
            html.P(
                translate_ui(loc, f"{i18n_prefix}.artifacts_status", status=status),
                className=_classes("small text-muted mb-1 ms-figure-artifacts-registry-status opacity-80", f"{class_prefix}-artifacts-registry-status"),
            )
        )
    if err:
        meta_lines.append(
            html.P(
                translate_ui(loc, f"{i18n_prefix}.artifacts_error", err=err),
                className="small text-danger mb-0",
            )
        )

    if keys:
        keys_block = html.Ul(
            [html.Li(html.Code(key), className="small") for key in keys],
            className=_classes("small mb-0 ps-3 ms-figure-artifacts-key-list", f"{class_prefix}-artifacts-key-list"),
        )
    else:
        keys_block = html.P(
            translate_ui(loc, f"{i18n_prefix}.artifacts_empty"),
            className="small text-muted mb-0 opacity-85",
        )

    registry = html.Details(
        [
            html.Summary(
                [
                    html.Span(className="ta-details-chevron"),
                    html.Span(
                        translate_ui(loc, f"{i18n_prefix}.artifacts_registry_summary"),
                        className=_classes("ms-1 small text-muted ms-figure-artifacts-registry-summary-label", f"{class_prefix}-artifacts-registry-summary-label"),
                    ),
                ],
                className="ta-details-summary py-1",
            ),
            html.Div([*meta_lines, keys_block], className="ta-details-body mt-2"),
        ],
        className=_classes("ta-ms-details mb-0 mt-1 ms-figure-artifacts-registry-disclosure", f"{class_prefix}-artifacts-registry-disclosure"),
        open=False,
    )

    return html.Div([primary_line, *preview_children, registry], className=panel_class)
