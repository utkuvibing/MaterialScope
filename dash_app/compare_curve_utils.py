"""Pure helpers for Compare overlay axes and analysis-state series selection (no Dash page registration)."""

from __future__ import annotations

from core.axis_labels import build_axis_title


def axis_titles(
    analysis_type: str,
    *,
    x_unit: str | None = None,
    y_unit: str | None = None,
    signal_kind: str | None = None,
) -> tuple[str, str]:
    """X and Y axis titles for compare overlay."""
    modality = (analysis_type or "").upper()
    return (
        build_axis_title(modality, "x", detected_unit=x_unit),
        build_axis_title(modality, "y", detected_unit=y_unit, signal_kind=signal_kind),
    )


def pick_best_series(curves: dict) -> tuple[list, list, str] | None:
    """Return (x, y, source_label) from analysis-state payload, or None if unusable."""
    x = curves.get("temperature") or []
    if not x:
        return None
    n = len(x)
    corrected = curves.get("corrected") or []
    smoothed = curves.get("smoothed") or []
    raw = curves.get("raw_signal") or []
    if len(corrected) == n:
        return x, corrected, "corrected"
    if len(smoothed) == n:
        return x, smoothed, "smoothed"
    if len(raw) == n:
        return x, raw, "raw"
    return None
