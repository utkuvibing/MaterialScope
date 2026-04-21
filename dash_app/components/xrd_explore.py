"""XRD Dash exploration helpers: undo stacks (same semantics as Raman/TGA)."""

from __future__ import annotations

import copy
import json
from typing import Any

MAX_XRD_UNDO_DEPTH = 25


def xrd_draft_processing_equal(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return a == b
    try:

        def norm(d: dict[str, Any]) -> str:
            return json.dumps(d, sort_keys=True, default=str)

        return norm(a) == norm(b)
    except Exception:
        return a == b


def append_undo_after_edit(
    past: list[dict[str, Any]] | None,
    future: list[dict[str, Any]] | None,
    old_draft: dict[str, Any] | None,
    new_draft: dict[str, Any],
    *,
    max_depth: int = MAX_XRD_UNDO_DEPTH,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    past_list = [copy.deepcopy(x) for x in (past or []) if isinstance(x, dict)]
    if old_draft is None or xrd_draft_processing_equal(old_draft, new_draft):
        return past_list, [copy.deepcopy(x) for x in (future or []) if isinstance(x, dict)]
    past_list.append(copy.deepcopy(old_draft))
    if len(past_list) > max_depth:
        past_list = past_list[-max_depth:]
    return past_list, []


def perform_undo(
    past: list[dict[str, Any]] | None,
    future: list[dict[str, Any]] | None,
    current: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]] | None:
    if not past:
        return None
    past_list = [copy.deepcopy(x) for x in past if isinstance(x, dict)]
    future_list = [copy.deepcopy(x) for x in (future or []) if isinstance(x, dict)]
    previous = past_list.pop()
    if current is not None:
        future_list.append(copy.deepcopy(current))
    return previous, past_list, future_list


def perform_redo(
    past: list[dict[str, Any]] | None,
    future: list[dict[str, Any]] | None,
    current: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]] | None:
    if not future:
        return None
    past_list = [copy.deepcopy(x) for x in (past or []) if isinstance(x, dict)]
    future_list = [copy.deepcopy(x) for x in future if isinstance(x, dict)]
    nxt = future_list.pop()
    if current is not None:
        past_list.append(copy.deepcopy(current))
    return nxt, past_list, future_list
