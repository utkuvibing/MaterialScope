"""Compatibility validation helpers for legacy tuple-based callers."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

import numpy as np
import pandas as pd

from core.validation import (
    TEMPERATURE_MAX_C,
    TEMPERATURE_MIN_C,
    validate_thermal_dataset as _validate_structured_dataset,
)

if TYPE_CHECKING:
    from core.data_io import ThermalDataset


ValidationResult = tuple[bool, str]

HEATING_RATE_MAX = 500.0
SAMPLE_MASS_MIN_MG = 0.01
SAMPLE_MASS_MAX_MG = 1000.0


def validate_temperature_range(temps: pd.Series) -> ValidationResult:
    """Validate a temperature series for numeric content and monotonicity."""
    if temps is None or len(temps) == 0:
        return False, "Temperature series is empty."

    if not pd.api.types.is_numeric_dtype(temps):
        return False, "Temperature column contains non-numeric values."

    nan_count = int(temps.isna().sum())
    if nan_count > 0:
        return False, f"Temperature column contains {nan_count} NaN value(s)."

    t_min = float(temps.min())
    t_max = float(temps.max())

    if t_min < TEMPERATURE_MIN_C:
        return False, f"Minimum temperature {t_min:.2f} C is below the allowed lower bound of {TEMPERATURE_MIN_C} C."

    if t_max > TEMPERATURE_MAX_C:
        return False, f"Maximum temperature {t_max:.2f} C exceeds the allowed upper bound of {TEMPERATURE_MAX_C} C."

    diffs = temps.diff().dropna()
    if (diffs <= 0).any():
        n_violations = int((diffs <= 0).sum())
        return False, f"Temperature column is not strictly monotonically increasing ({n_violations} non-positive step(s) detected)."

    return True, "Temperature range is valid."


def validate_numeric_column(series: pd.Series) -> ValidationResult:
    """Validate a numeric data column while surfacing NaN statistics."""
    if series is None or len(series) == 0:
        return False, "Column is empty."

    if not pd.api.types.is_numeric_dtype(series):
        return False, f"Column '{series.name}' has dtype '{series.dtype}', which is not numeric."

    nan_count = int(series.isna().sum())
    total = len(series)

    if nan_count == total:
        return False, f"Column '{series.name}' contains only NaN values."

    if nan_count > 0:
        pct = 100.0 * nan_count / total
        return True, (
            f"Column '{series.name}' is numeric but contains {nan_count} NaN value(s) ({pct:.1f} %). "
            "Consider interpolating or dropping missing rows before analysis."
        )

    return True, f"Column '{series.name}' is valid numeric data with no NaN values."


def validate_heating_rate(rate: float) -> ValidationResult:
    """Validate a heating rate value for positivity and practical limits."""
    if rate is None:
        return False, "Heating rate is None."

    try:
        rate = float(rate)
    except (TypeError, ValueError):
        return False, f"Heating rate '{rate}' cannot be converted to a number."

    if not np.isfinite(rate):
        return False, f"Heating rate must be a finite number, got {rate}."

    if rate <= 0:
        return False, f"Heating rate must be positive, got {rate} K/min."

    if rate > HEATING_RATE_MAX:
        return False, f"Heating rate {rate} K/min exceeds the practical maximum of {HEATING_RATE_MAX} K/min for standard instruments."

    return True, f"Heating rate {rate} K/min is valid."


def validate_sample_mass(mass: float) -> ValidationResult:
    """Validate a sample mass for positivity and practical DSC/TGA limits."""
    if mass is None:
        return False, "Sample mass is None."

    try:
        mass = float(mass)
    except (TypeError, ValueError):
        return False, f"Sample mass '{mass}' cannot be converted to a number."

    if not np.isfinite(mass):
        return False, f"Sample mass must be a finite number, got {mass}."

    if mass <= 0:
        return False, f"Sample mass must be positive, got {mass} mg."

    if mass < SAMPLE_MASS_MIN_MG:
        return False, f"Sample mass {mass} mg is below the practical minimum of {SAMPLE_MASS_MIN_MG} mg."

    if mass > SAMPLE_MASS_MAX_MG:
        return False, f"Sample mass {mass} mg exceeds the practical maximum of {SAMPLE_MASS_MAX_MG} mg."

    return True, f"Sample mass {mass} mg is valid."


def _format_structured_validation(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    status = summary.get("status")

    if status == "fail":
        lines.append("Validation failed.")
    elif status == "warn":
        lines.append("Validation passed with warnings.")
    else:
        lines.append("All checks passed.")

    issues = summary.get("issues") or []
    if issues:
        lines.append("Errors:")
        lines.extend(f"  {issue}" for issue in issues)

    warnings = summary.get("warnings") or []
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"  {warning}" for warning in warnings)

    return "\n".join(lines)


def validate_thermal_dataset(dataset: "ThermalDataset") -> ValidationResult:
    """Wrap the structured validator with the legacy (bool, message) API."""
    summary = _validate_structured_dataset(
        dataset,
        analysis_type=getattr(dataset, "data_type", None),
    )
    return summary.get("status") != "fail", _format_structured_validation(summary)
