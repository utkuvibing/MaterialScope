"""Dataset validation helpers for stable thermal-analysis workflows."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from core.processing_schema import ensure_processing_payload


SUPPORTED_ANALYSIS_TYPES = {"DSC", "TGA", "DTA", "UNKNOWN", "unknown"}
TEMPERATURE_MIN_C = -200.0
TEMPERATURE_MAX_C = 2000.0
TEMPERATURE_UNITS = {"°C", "degC", "K"}
SIGNAL_UNITS_BY_TYPE = {
    "DSC": {"mW", "mW/mg", "W/g"},
    "TGA": {"%", "mg"},
    "DTA": {"uV", "µV", "mV", "a.u."},
}
RECOMMENDED_METADATA_FIELDS = (
    "sample_name",
    "sample_mass",
    "heating_rate",
    "instrument",
    "vendor",
    "display_name",
)
OPTIONAL_METADATA_FIELDS = (
    "atmosphere",
    "atmosphere_status",
    "operator",
    "calibration_id",
    "calibration_status",
    "method_template_id",
    "source_data_hash",
)
ACCEPTED_CALIBRATION_STATUSES = {"verified", "current", "pass", "ok"}
BLOCKING_CALIBRATION_STATUSES = {"failed", "expired", "invalid", "out_of_date"}
ACCEPTED_ATMOSPHERE_STATUSES = {"verified", "recorded", "controlled", "current", "ok"}
BLOCKING_ATMOSPHERE_STATUSES = {"failed", "unstable", "unknown", "unverified", "invalid"}
TGA_PERCENT_MIN = -5.0
TGA_PERCENT_MAX = 120.0


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(result):
        return None
    return result


def _validation_status(*, issues: list[str], warnings: list[str]) -> str:
    if issues:
        return "fail"
    if warnings:
        return "warn"
    return "pass"


def _normalize_status_token(value: Any) -> str | None:
    if value in (None, ""):
        return None
    token = str(value).strip().lower()
    return token or None


def _processing_section(processing: dict[str, Any] | None, key: str) -> dict[str, Any]:
    processing = processing or {}
    nested = processing.get("signal_pipeline") or {}
    if key in nested and isinstance(nested[key], dict):
        return nested[key]

    nested = processing.get("analysis_steps") or {}
    if key in nested and isinstance(nested[key], dict):
        return nested[key]

    value = processing.get(key)
    return value if isinstance(value, dict) else {}


def _check_dsc_workflow(
    *,
    metadata: dict[str, Any],
    processing: dict[str, Any] | None,
    checks: dict[str, Any],
    issues: list[str],
    warnings: list[str],
) -> None:
    calibration_id = metadata.get("calibration_id")
    calibration_status = metadata.get("calibration_status")
    calibration_state = "unknown_calibration_state"
    if calibration_id and _normalize_status_token(calibration_status) in ACCEPTED_CALIBRATION_STATUSES:
        calibration_state = "calibrated"
    elif calibration_id in (None, "") and calibration_status in (None, ""):
        calibration_state = "missing_calibration"
    elif _normalize_status_token(calibration_status) in BLOCKING_CALIBRATION_STATUSES:
        calibration_state = "calibration_not_current"
    checks["calibration_id"] = calibration_id or "not recorded"
    checks["calibration_status"] = calibration_status or "not recorded"
    checks["calibration_state"] = calibration_state

    if not calibration_id:
        warnings.append("Calibration identifier is not recorded for this DSC dataset.")

    calibration_token = _normalize_status_token(calibration_status)
    if calibration_token is None:
        warnings.append("Calibration status is not recorded for this DSC dataset.")
    elif calibration_token in BLOCKING_CALIBRATION_STATUSES:
        issues.append("Calibration status indicates the DSC workflow is not currently verified.")
    elif calibration_token not in ACCEPTED_CALIBRATION_STATUSES:
        warnings.append(f"Calibration status '{calibration_status}' should be reviewed before stable reporting.")

    if not processing:
        return

    checks["workflow_template_id"] = processing.get("workflow_template_id") or "not recorded"
    checks["workflow_template_label"] = processing.get("workflow_template_label") or processing.get("workflow_template") or "not recorded"

    method_context = processing.get("method_context") or {}
    sign_convention = method_context.get("sign_convention_label") or processing.get("sign_convention")
    checks["sign_convention"] = sign_convention or "not recorded"
    checks["reference_state"] = method_context.get("reference_state") or "not recorded"
    checks["reference_name"] = method_context.get("reference_name") or "not recorded"
    if not sign_convention:
        warnings.append("DSC sign convention is not recorded in the saved method context.")

    baseline = _processing_section(processing, "baseline")
    baseline_method = baseline.get("method")
    checks["baseline_method"] = baseline_method or "not recorded"
    if not baseline_method:
        warnings.append("Baseline method is not recorded for this DSC result.")

    glass_transition = _processing_section(processing, "glass_transition")
    peak_detection = _processing_section(processing, "peak_detection")
    checks["glass_transition_context"] = "recorded" if glass_transition else "not recorded"
    checks["peak_detection_context"] = "recorded" if peak_detection else "not recorded"
    if not glass_transition and not peak_detection:
        warnings.append("DSC method context does not record Tg or peak-analysis settings.")


def _check_tga_workflow(
    *,
    metadata: dict[str, Any],
    processing: dict[str, Any] | None,
    signal: pd.Series,
    signal_unit: str | None,
    sample_mass: float | None,
    checks: dict[str, Any],
    issues: list[str],
    warnings: list[str],
) -> None:
    signal_min = float(signal.min())
    signal_max = float(signal.max())
    checks["signal_min"] = signal_min
    checks["signal_max"] = signal_max

    if signal_unit == "%":
        if signal_min < TGA_PERCENT_MIN or signal_max > TGA_PERCENT_MAX:
            warnings.append("TGA signal is labeled as % but falls outside a plausible mass-percent range.")
            checks["unit_plausibility"] = "review"
        else:
            checks["unit_plausibility"] = "pass"
        checks["tga_unit_mode"] = "mass_percent"
    elif signal_unit == "mg":
        checks["unit_plausibility"] = "pass"
        checks["tga_unit_mode"] = "absolute_mass"
        if sample_mass is None:
            warnings.append("Absolute-mass TGA data is recorded in mg but sample mass is not recorded.")
    elif signal_unit:
        checks["unit_plausibility"] = "review"
        checks["tga_unit_mode"] = "unusual"
    else:
        checks["unit_plausibility"] = "not_recorded"
        checks["tga_unit_mode"] = "not_recorded"
        warnings.append("Signal unit is not recorded for this TGA dataset.")

    atmosphere = metadata.get("atmosphere")
    atmosphere_status = metadata.get("atmosphere_status")
    calibration_id = metadata.get("calibration_id")
    calibration_status = metadata.get("calibration_status")
    checks["atmosphere"] = atmosphere or "not recorded"
    checks["atmosphere_status"] = atmosphere_status or "not recorded"
    checks["calibration_id"] = calibration_id or "not recorded"
    checks["calibration_status"] = calibration_status or "not recorded"
    if calibration_id and _normalize_status_token(calibration_status) in ACCEPTED_CALIBRATION_STATUSES:
        checks["calibration_state"] = "calibrated"
    elif calibration_id in (None, "") and calibration_status in (None, ""):
        checks["calibration_state"] = "missing_calibration"
    elif _normalize_status_token(calibration_status) in BLOCKING_CALIBRATION_STATUSES:
        checks["calibration_state"] = "calibration_not_current"
    else:
        checks["calibration_state"] = "unknown_calibration_state"

    if not atmosphere:
        warnings.append("Atmosphere is not recorded for this TGA dataset.")

    atmosphere_token = _normalize_status_token(atmosphere_status)
    if atmosphere_token is None:
        warnings.append("Atmosphere status is not recorded for this TGA dataset.")
    elif atmosphere_token in BLOCKING_ATMOSPHERE_STATUSES:
        issues.append("Atmosphere status indicates the TGA run conditions were not verified.")
    elif atmosphere_token not in ACCEPTED_ATMOSPHERE_STATUSES:
        warnings.append(f"Atmosphere status '{atmosphere_status}' should be reviewed before stable reporting.")

    if not processing:
        return

    checks["workflow_template_id"] = processing.get("workflow_template_id") or "not recorded"
    checks["workflow_template_label"] = processing.get("workflow_template_label") or processing.get("workflow_template") or "not recorded"

    step_detection = _processing_section(processing, "step_detection")
    method_context = processing.get("method_context") or {}
    checks["step_analysis_context"] = "recorded" if step_detection else "not recorded"
    checks["step_detection_method"] = step_detection.get("method") or "not recorded"
    checks["reference_state"] = method_context.get("reference_state") or "not recorded"
    checks["reference_name"] = method_context.get("reference_name") or "not recorded"
    if not step_detection:
        warnings.append("TGA method context does not record step-analysis settings.")


def validate_thermal_dataset(
    dataset,
    *,
    analysis_type: str | None = None,
    require_sample_mass: bool = False,
    require_heating_rate: bool = False,
    processing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a structured validation summary for a ThermalDataset-like object."""
    issues: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}

    if dataset is None:
        return {
            "status": "fail",
            "issues": ["Dataset is missing."],
            "warnings": [],
            "checks": {},
            "required_metadata": list(RECOMMENDED_METADATA_FIELDS),
            "optional_metadata": list(OPTIONAL_METADATA_FIELDS),
        }

    data = getattr(dataset, "data", None)
    metadata = getattr(dataset, "metadata", {}) or {}
    units = getattr(dataset, "units", {}) or {}
    dataset_type = getattr(dataset, "data_type", "unknown")

    checks["dataset_type"] = dataset_type

    if data is None or not isinstance(data, pd.DataFrame) or data.empty:
        issues.append("Dataset does not contain a non-empty DataFrame.")
        return {
            "status": "fail",
            "issues": issues,
            "warnings": warnings,
            "checks": checks,
            "required_metadata": list(RECOMMENDED_METADATA_FIELDS),
            "optional_metadata": list(OPTIONAL_METADATA_FIELDS),
        }

    missing_columns = [col for col in ("temperature", "signal") if col not in data.columns]
    if missing_columns:
        issues.append(f"Missing required standardized column(s): {', '.join(missing_columns)}.")
        return {
            "status": "fail",
            "issues": issues,
            "warnings": warnings,
            "checks": checks,
            "required_metadata": list(RECOMMENDED_METADATA_FIELDS),
            "optional_metadata": list(OPTIONAL_METADATA_FIELDS),
        }

    temperature = pd.to_numeric(data["temperature"], errors="coerce")
    signal = pd.to_numeric(data["signal"], errors="coerce")

    if temperature.isna().any():
        issues.append("Temperature column contains non-numeric or missing values.")
    else:
        diffs = temperature.diff().dropna()
        if (diffs <= 0).any():
            issues.append("Temperature column must be strictly increasing.")
        temp_min = float(temperature.min())
        temp_max = float(temperature.max())
        checks["temperature_min"] = temp_min
        checks["temperature_max"] = temp_max
        if temp_min < TEMPERATURE_MIN_C or temp_max > TEMPERATURE_MAX_C:
            issues.append(
                f"Temperature range {temp_min:.1f} to {temp_max:.1f} is outside the supported thermal-analysis bounds."
            )

    if signal.isna().all():
        issues.append("Signal column contains no usable numeric values.")
    elif signal.isna().any():
        warnings.append("Signal column contains missing values; affected rows were dropped during import.")
    checks["data_points"] = int(len(data))

    normalized_analysis_type = (analysis_type or dataset_type or "unknown").upper()
    if normalized_analysis_type not in SUPPORTED_ANALYSIS_TYPES:
        warnings.append(f"Dataset type '{normalized_analysis_type}' is not part of the stable workflow.")
    normalized_processing = None
    if processing:
        normalized_processing = ensure_processing_payload(processing, analysis_type=normalized_analysis_type)

    temperature_unit = units.get("temperature")
    if temperature_unit and temperature_unit not in TEMPERATURE_UNITS:
        warnings.append(f"Temperature unit '{temperature_unit}' is unusual; verify unit conversion before analysis.")
    checks["temperature_unit"] = temperature_unit or "unspecified"

    signal_unit = units.get("signal")
    recommended_signal_units = SIGNAL_UNITS_BY_TYPE.get(normalized_analysis_type, set())
    if signal_unit and recommended_signal_units and signal_unit not in recommended_signal_units:
        warnings.append(
            f"Signal unit '{signal_unit}' is unusual for {normalized_analysis_type}; verify instrument/export settings."
        )
    checks["signal_unit"] = signal_unit or "unspecified"

    missing_metadata = [field for field in RECOMMENDED_METADATA_FIELDS if not metadata.get(field)]
    if missing_metadata:
        warnings.append(f"Recommended metadata missing: {', '.join(missing_metadata)}.")
    checks["missing_metadata"] = missing_metadata

    sample_mass = _coerce_float(metadata.get("sample_mass"))
    checks["sample_mass"] = sample_mass
    if sample_mass is None:
        if require_sample_mass:
            issues.append("Sample mass is required for this workflow.")
        else:
            warnings.append("Sample mass is not recorded; mass-normalized workflows may be limited.")
    elif sample_mass <= 0:
        issues.append("Sample mass must be positive.")

    heating_rate = _coerce_float(metadata.get("heating_rate"))
    checks["heating_rate"] = heating_rate
    if heating_rate is None:
        if require_heating_rate:
            issues.append("Heating rate is required for this workflow.")
        else:
            warnings.append("Heating rate is not recorded; kinetic and comparison workflows may be limited.")
    elif heating_rate <= 0:
        issues.append("Heating rate must be positive.")

    if normalized_analysis_type == "DSC":
        _check_dsc_workflow(
            metadata=metadata,
            processing=normalized_processing,
            checks=checks,
            issues=issues,
            warnings=warnings,
        )
    elif normalized_analysis_type == "TGA":
        _check_tga_workflow(
            metadata=metadata,
            processing=normalized_processing,
            signal=signal,
            signal_unit=signal_unit,
            sample_mass=sample_mass,
            checks=checks,
            issues=issues,
            warnings=warnings,
        )

    return {
        "status": _validation_status(issues=issues, warnings=warnings),
        "issues": issues,
        "warnings": warnings,
        "checks": checks,
        "required_metadata": list(RECOMMENDED_METADATA_FIELDS),
        "optional_metadata": list(OPTIONAL_METADATA_FIELDS),
    }
