"""Shared processing-control input coercion helpers."""

from __future__ import annotations

import math


def coerce_int_positive(value, *, default: int, minimum: int) -> int:
    try:
        if value in (None, ""):
            return max(default, minimum)
        parsed = int(float(value))
    except (TypeError, ValueError):
        return max(default, minimum)
    return max(parsed, minimum)


def coerce_float_positive(value, *, default: float, minimum: float) -> float:
    try:
        if value in (None, ""):
            return max(default, minimum)
        parsed = float(value)
    except (TypeError, ValueError):
        return max(default, minimum)
    if not math.isfinite(parsed):
        return max(default, minimum)
    return max(parsed, minimum)


def coerce_float_non_negative(value, *, default: float) -> float:
    try:
        if value in (None, ""):
            return max(default, 0.0)
        parsed = float(value)
    except (TypeError, ValueError):
        return max(default, 0.0)
    if not math.isfinite(parsed) or parsed < 0:
        return max(default, 0.0)
    return parsed
