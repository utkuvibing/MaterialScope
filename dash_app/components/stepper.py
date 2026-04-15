"""Reusable multi-step wizard / stepper component for Dash pages."""

from __future__ import annotations

from typing import Any

import dash_bootstrap_components as dbc
from dash import html


def stepper_indicator(
    steps: list[dict[str, str]],
    active_step: int,
    completed_steps: set[int] | None = None,
) -> html.Div:
    """Render a horizontal step indicator.

    Parameters
    ----------
    steps : list of dict
        Each dict has keys ``label`` and ``description``.
    active_step : int
        Zero-based index of the currently active step.
    completed_steps : set of int, optional
        Zero-based indices of completed steps.
    """
    completed_steps = completed_steps or set()
    items: list[Any] = []
    for i, step in enumerate(steps):
        if i in completed_steps:
            variant = "success"
            icon = "bi-check-circle-fill"
        elif i == active_step:
            variant = "primary"
            icon = "bi-circle-fill"
        else:
            variant = "secondary"
            icon = "bi-circle"
        items.append(
            html.Div(
                [
                    html.I(className=f"bi {icon} me-1 text-{variant}"),
                    html.Span(step["label"], className=f"fw-{('bold' if i == active_step else 'normal')}"),
                ],
                className="d-flex align-items-center me-3",
            )
        )
        if i < len(steps) - 1:
            items.append(html.I(className="bi bi-chevron-right me-3 text-muted"))
    return html.Div(items, className="d-flex align-items-center flex-wrap mb-3 stepper-bar")


def step_container(step_id: str, content: list[Any], visible: bool = True) -> html.Div:
    """Wrap step content in a toggleable div."""
    return html.Div(
        content,
        id=step_id,
        style={"display": "block" if visible else "none"},
    )


def step_navigation(
    *,
    prev_id: str,
    next_id: str,
    confirm_id: str | None = None,
    show_prev: bool = True,
    show_next: bool = True,
    show_confirm: bool = False,
) -> dbc.Row:
    """Render step navigation buttons."""
    buttons: list[dbc.Col] = []
    if show_prev:
        buttons.append(
            dbc.Col(
                dbc.Button("Back", id=prev_id, color="secondary", outline=True),
                width="auto",
            )
        )
    if show_next:
        buttons.append(
            dbc.Col(
                dbc.Button("Next", id=next_id, color="primary"),
                width="auto",
            )
        )
    if show_confirm:
        buttons.append(
            dbc.Col(
                dbc.Button("Confirm Import", id=confirm_id, color="success"),
                width="auto",
            )
        )
    return dbc.Row(buttons, className="g-2 mt-3")
