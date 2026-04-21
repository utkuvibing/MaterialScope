"""RAMAN Dash exploration helpers: undo stacks and lightweight data helpers.

Reuses the same patterns established by TGA exploration helpers.
"""

from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np

MAX_RAMAN_UNDO_DEPTH = 25


def raman_draft_processing_equal(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    """Deep-compare normalized RAMAN processing draft payloads."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return a == b
    try:
        import json

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
    max_depth: int = MAX_RAMAN_UNDO_DEPTH,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """After a user edit, push *old_draft* onto past and clear redo when draft actually changes."""
    past_list = [copy.deepcopy(x) for x in (past or []) if isinstance(x, dict)]
    if old_draft is None or raman_draft_processing_equal(old_draft, new_draft):
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


def downsample_rows(rows: list[dict[str, Any]], columns: list[str], max_points: int = 6000) -> tuple[np.ndarray, np.ndarray]:
    """Extract axis/signal as float arrays; stride if very long."""
    if not rows:
        return np.array([]), np.array([])
    t_key = "temperature" if "temperature" in columns else None
    s_key = "signal" if "signal" in columns else None
    if t_key is None or s_key is None:
        return np.array([]), np.array([])
    t_vals: list[float] = []
    s_vals: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            tv = float(row.get(t_key))
            sv = float(row.get(s_key))
        except (TypeError, ValueError):
            continue
        if math.isfinite(tv) and math.isfinite(sv):
            t_vals.append(tv)
            s_vals.append(sv)
    t_arr = np.asarray(t_vals, dtype=float)
    s_arr = np.asarray(s_vals, dtype=float)
    n = len(t_arr)
    if n <= max_points or n == 0:
        return t_arr, s_arr
    step = int(math.ceil(n / max_points))
    return t_arr[::step], s_arr[::step]

