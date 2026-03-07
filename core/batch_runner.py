"""Brownfield batch template execution for compare-workspace DSC/TGA runs."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from core.dsc_processor import DSCProcessor
from core.processing_schema import ensure_processing_payload, get_workflow_templates, update_method_context, update_processing_step
from core.provenance import build_calibration_reference_context, build_result_provenance
from core.result_serialization import serialize_dsc_result, serialize_tga_result
from core.tga_processor import TGAProcessor
from core.validation import validate_thermal_dataset


_DSC_TEMPLATE_DEFAULTS = {
    "dsc.general": {
        "smoothing": {"method": "savgol", "window_length": 11, "polyorder": 3},
        "baseline": {"method": "asls"},
        "peak_detection": {"direction": "both"},
        "glass_transition": {"mode": "auto", "region": None},
    },
    "dsc.polymer_tg": {
        "smoothing": {"method": "savgol", "window_length": 15, "polyorder": 3},
        "baseline": {"method": "asls"},
        "peak_detection": {"direction": "both"},
        "glass_transition": {"mode": "auto", "region": None},
    },
    "dsc.polymer_melting_crystallization": {
        "smoothing": {"method": "savgol", "window_length": 11, "polyorder": 3},
        "baseline": {"method": "asls"},
        "peak_detection": {"direction": "both"},
        "glass_transition": {"mode": "auto", "region": None},
    },
}

_TGA_TEMPLATE_DEFAULTS = {
    "tga.general": {
        "smoothing": {"method": "savgol", "window_length": 11, "polyorder": 3},
        "step_detection": {"method": "dtg_peaks", "prominence": None, "min_mass_loss": 0.5, "search_half_width": 80},
    },
    "tga.single_step_decomposition": {
        "smoothing": {"method": "savgol", "window_length": 11, "polyorder": 3},
        "step_detection": {"method": "dtg_peaks", "prominence": None, "min_mass_loss": 0.5, "search_half_width": 80},
    },
    "tga.multi_step_decomposition": {
        "smoothing": {"method": "savgol", "window_length": 15, "polyorder": 3},
        "step_detection": {"method": "dtg_peaks", "prominence": None, "min_mass_loss": 0.3, "search_half_width": 100},
    },
}
_VALID_EXECUTION_STATUSES = {"saved", "blocked", "failed"}


def execute_batch_template(
    *,
    dataset_key: str,
    dataset,
    analysis_type: str,
    workflow_template_id: str,
    existing_processing: Mapping[str, Any] | None = None,
    analysis_history: list[dict[str, Any]] | None = None,
    analyst_name: str | None = None,
    app_version: str | None = None,
    batch_run_id: str | None = None,
) -> dict[str, Any]:
    """Execute one batch template against one dataset without UI dependencies."""
    normalized_type = (analysis_type or "UNKNOWN").upper()
    processing = _build_processing_payload(
        analysis_type=normalized_type,
        workflow_template_id=workflow_template_id,
        existing_processing=existing_processing,
        batch_run_id=batch_run_id,
    )

    pre_validation = validate_thermal_dataset(dataset, analysis_type=normalized_type, processing=processing)
    if pre_validation["status"] == "fail":
        return {
            "status": "blocked",
            "analysis_type": normalized_type,
            "dataset_key": dataset_key,
            "processing": processing,
            "validation": pre_validation,
            "record": None,
            "state": None,
            "summary_row": _make_summary_row(
                dataset_key=dataset_key,
                dataset=dataset,
                analysis_type=normalized_type,
                processing=processing,
                validation=pre_validation,
                execution_status="blocked",
                failure_reason="; ".join(pre_validation["issues"]) or "Dataset blocked by validation.",
            ),
        }

    if normalized_type == "DSC":
        return _execute_dsc_batch(
            dataset_key=dataset_key,
            dataset=dataset,
            processing=processing,
            analysis_history=analysis_history,
            analyst_name=analyst_name,
            app_version=app_version,
            batch_run_id=batch_run_id,
        )
    if normalized_type == "TGA":
        return _execute_tga_batch(
            dataset_key=dataset_key,
            dataset=dataset,
            processing=processing,
            analysis_history=analysis_history,
            analyst_name=analyst_name,
            app_version=app_version,
            batch_run_id=batch_run_id,
        )
    raise ValueError(f"Unsupported batch analysis type '{analysis_type}'")


def _build_processing_payload(
    *,
    analysis_type: str,
    workflow_template_id: str,
    existing_processing: Mapping[str, Any] | None,
    batch_run_id: str | None,
) -> dict[str, Any]:
    template_label = _workflow_template_label(analysis_type, workflow_template_id)
    processing = ensure_processing_payload(
        dict(existing_processing or {}),
        analysis_type=analysis_type,
        workflow_template=workflow_template_id,
        workflow_template_label=template_label,
    )
    defaults = _template_defaults(analysis_type, workflow_template_id)
    for section_name, values in defaults.items():
        if section_name == "method_context":
            processing = update_method_context(processing, values, analysis_type=analysis_type)
        else:
            processing = update_processing_step(processing, section_name, values, analysis_type=analysis_type)

    method_context = {
        "batch_template_runner": "compare_workspace",
        "batch_run_id": batch_run_id or "",
    }
    return update_method_context(processing, method_context, analysis_type=analysis_type)


def _execute_dsc_batch(
    *,
    dataset_key: str,
    dataset,
    processing: dict[str, Any],
    analysis_history: list[dict[str, Any]] | None,
    analyst_name: str | None,
    app_version: str | None,
    batch_run_id: str | None,
) -> dict[str, Any]:
    temperature = dataset.data["temperature"].values
    signal = dataset.data["signal"].values
    sample_mass = dataset.metadata.get("sample_mass")
    heating_rate = dataset.metadata.get("heating_rate")

    smoothing = copy.deepcopy((processing.get("signal_pipeline") or {}).get("smoothing") or {})
    baseline = copy.deepcopy((processing.get("signal_pipeline") or {}).get("baseline") or {})
    peak_detection = copy.deepcopy((processing.get("analysis_steps") or {}).get("peak_detection") or {})
    glass_transition = copy.deepcopy((processing.get("analysis_steps") or {}).get("glass_transition") or {})

    processor = DSCProcessor(
        temperature,
        signal,
        sample_mass=sample_mass,
        heating_rate=heating_rate,
    )

    smooth_method = smoothing.pop("method", "savgol")
    processor.smooth(method=smooth_method, **smoothing)
    processor.normalize()
    smoothed_signal = processor._signal.copy()

    baseline_method = baseline.pop("method", "asls")
    processor.correct_baseline(method=baseline_method, **baseline)
    corrected_signal = processor._signal.copy()

    processor.find_peaks(**peak_detection)
    tg_region = glass_transition.get("region")
    processor.detect_glass_transition(region=tuple(tg_region) if isinstance(tg_region, (list, tuple)) and len(tg_region) == 2 else None)
    result = processor.get_result()

    calibration_context = build_calibration_reference_context(
        dataset=dataset,
        analysis_type="DSC",
        reference_temperature_c=_select_dsc_reference_temperature(result),
    )
    processing = update_method_context(processing, calibration_context, analysis_type="DSC")
    validation = validate_thermal_dataset(dataset, analysis_type="DSC", processing=processing)
    provenance = build_result_provenance(
        dataset=dataset,
        dataset_key=dataset_key,
        analysis_history=analysis_history,
        app_version=app_version,
        analyst_name=analyst_name,
        extra={
            "batch_run_id": batch_run_id,
            "batch_runner": "compare_workspace",
            "calibration_state": calibration_context.get("calibration_state"),
            "reference_state": calibration_context.get("reference_state"),
            "reference_name": calibration_context.get("reference_name"),
            "reference_delta_c": calibration_context.get("reference_delta_c"),
        },
    )
    record = serialize_dsc_result(
        dataset_key,
        dataset,
        result.peaks,
        glass_transitions=result.glass_transitions,
        artifacts={},
        processing=processing,
        provenance=provenance,
        validation=validation,
        review={"commercial_scope": "stable_dsc", "batch_runner": "compare_workspace"},
    )
    state = {
        "smoothed": smoothed_signal,
        "baseline": result.baseline,
        "corrected": corrected_signal,
        "peaks": result.peaks,
        "glass_transitions": result.glass_transitions,
        "processor": None,
        "processing": processing,
    }
    return {
        "status": "saved",
        "analysis_type": "DSC",
        "dataset_key": dataset_key,
        "processing": processing,
        "validation": validation,
        "record": record,
        "state": state,
        "summary_row": _make_summary_row(
            dataset_key=dataset_key,
            dataset=dataset,
            analysis_type="DSC",
            processing=processing,
            validation=validation,
            execution_status="saved",
            record=record,
            failure_reason="",
        ),
    }


def _execute_tga_batch(
    *,
    dataset_key: str,
    dataset,
    processing: dict[str, Any],
    analysis_history: list[dict[str, Any]] | None,
    analyst_name: str | None,
    app_version: str | None,
    batch_run_id: str | None,
) -> dict[str, Any]:
    temperature = dataset.data["temperature"].values
    signal = dataset.data["signal"].values
    initial_mass_mg = dataset.metadata.get("sample_mass")

    smoothing = copy.deepcopy((processing.get("signal_pipeline") or {}).get("smoothing") or {})
    step_detection = copy.deepcopy((processing.get("analysis_steps") or {}).get("step_detection") or {})

    processor = TGAProcessor(
        temperature,
        signal,
        initial_mass_mg=initial_mass_mg,
        metadata=dataset.metadata,
    )

    smooth_method = smoothing.pop("method", "savgol")
    processor.smooth(method=smooth_method, **smoothing)
    processor.compute_dtg(
        smooth_dtg=True,
        window_length=smoothing.get("window_length", 11),
        polyorder=smoothing.get("polyorder", 3),
    )
    step_detection.pop("method", None)
    processor.detect_steps(
        prominence=step_detection.pop("prominence", None),
        min_mass_loss=step_detection.pop("min_mass_loss", 0.5),
        search_half_width=step_detection.pop("search_half_width", 80),
        **step_detection,
    )
    result = processor.get_result()

    calibration_context = build_calibration_reference_context(
        dataset=dataset,
        analysis_type="TGA",
        reference_temperature_c=_select_tga_reference_temperature(result),
    )
    processing = update_method_context(processing, calibration_context, analysis_type="TGA")
    validation = validate_thermal_dataset(dataset, analysis_type="TGA", processing=processing)
    provenance = build_result_provenance(
        dataset=dataset,
        dataset_key=dataset_key,
        analysis_history=analysis_history,
        app_version=app_version,
        analyst_name=analyst_name,
        extra={
            "batch_run_id": batch_run_id,
            "batch_runner": "compare_workspace",
            "calibration_state": calibration_context.get("calibration_state"),
            "reference_state": calibration_context.get("reference_state"),
            "reference_name": calibration_context.get("reference_name"),
            "reference_delta_c": calibration_context.get("reference_delta_c"),
        },
    )
    record = serialize_tga_result(
        dataset_key,
        dataset,
        result,
        artifacts={},
        processing=processing,
        provenance=provenance,
        validation=validation,
        review={"commercial_scope": "stable_tga", "batch_runner": "compare_workspace"},
    )
    state = {
        "smoothed": result.smoothed_signal,
        "dtg": result.dtg_signal,
        "tga_result": result,
        "processing": processing,
    }
    return {
        "status": "saved",
        "analysis_type": "TGA",
        "dataset_key": dataset_key,
        "processing": processing,
        "validation": validation,
        "record": record,
        "state": state,
        "summary_row": _make_summary_row(
            dataset_key=dataset_key,
            dataset=dataset,
            analysis_type="TGA",
            processing=processing,
            validation=validation,
            execution_status="saved",
            record=record,
            failure_reason="",
        ),
    }


def _template_defaults(analysis_type: str, workflow_template_id: str) -> dict[str, Any]:
    catalog = _DSC_TEMPLATE_DEFAULTS if analysis_type == "DSC" else _TGA_TEMPLATE_DEFAULTS
    if workflow_template_id in catalog:
        return copy.deepcopy(catalog[workflow_template_id])
    fallback = "dsc.general" if analysis_type == "DSC" else "tga.general"
    return copy.deepcopy(catalog[fallback])


def _workflow_template_label(analysis_type: str, workflow_template_id: str) -> str:
    for entry in get_workflow_templates(analysis_type):
        if entry["id"] == workflow_template_id:
            return entry["label"]
    return workflow_template_id


def _select_dsc_reference_temperature(result) -> float | None:
    peaks = getattr(result, "peaks", []) or []
    if peaks:
        return getattr(peaks[0], "peak_temperature", None)
    glass_transitions = getattr(result, "glass_transitions", []) or []
    if glass_transitions:
        return getattr(glass_transitions[0], "tg_midpoint", None)
    return None


def _select_tga_reference_temperature(result) -> float | None:
    steps = getattr(result, "steps", []) or []
    if steps:
        return getattr(steps[0], "midpoint_temperature", None) or getattr(steps[0], "onset_temperature", None)
    return None


def _make_summary_row(
    *,
    dataset_key: str,
    dataset,
    analysis_type: str,
    processing: Mapping[str, Any],
    validation: Mapping[str, Any],
    execution_status: str,
    record: Mapping[str, Any] | None = None,
    failure_reason: str = "",
) -> dict[str, Any]:
    method_context = (processing.get("method_context") or {}) if isinstance(processing, Mapping) else {}
    summary = (record or {}).get("summary") or {}
    row = {
        "dataset_key": dataset_key,
        "analysis_type": analysis_type,
        "sample_name": (dataset.metadata or {}).get("sample_name") or dataset_key,
        "workflow_template_id": processing.get("workflow_template_id"),
        "workflow_template": processing.get("workflow_template"),
        "execution_status": execution_status,
        "validation_status": validation.get("status"),
        "warning_count": len(validation.get("warnings") or []),
        "issue_count": len(validation.get("issues") or []),
        "calibration_state": method_context.get("calibration_state") or (validation.get("checks") or {}).get("calibration_state"),
        "reference_state": method_context.get("reference_state") or (validation.get("checks") or {}).get("reference_state"),
        "result_id": (record or {}).get("id"),
        "failure_reason": failure_reason,
        "message": failure_reason,
        "error_id": "",
    }
    row.update(summary)
    return row


def normalize_batch_summary_rows(summary_rows: list[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Return backward-compatible normalized batch-summary rows."""
    normalized_rows: list[dict[str, Any]] = []
    for row in summary_rows or []:
        payload = dict(row or {})
        status = str(payload.get("execution_status") or "").strip().lower()
        if status == "error":
            status = "failed"
        if status not in _VALID_EXECUTION_STATUSES:
            status = "failed" if payload.get("error_id") else "blocked" if payload.get("issue_count") else "saved"
        failure_reason = payload.get("failure_reason")
        if failure_reason in (None, ""):
            failure_reason = payload.get("message", "")
        payload["execution_status"] = status
        payload["failure_reason"] = failure_reason or ""
        payload["message"] = payload["failure_reason"]
        payload["error_id"] = payload.get("error_id") or ""
        normalized_rows.append(payload)
    return normalized_rows


def summarize_batch_outcomes(summary_rows: list[Mapping[str, Any]] | None) -> dict[str, int]:
    """Return counts for normalized batch outcome categories."""
    rows = normalize_batch_summary_rows(summary_rows)
    return {
        "total": len(rows),
        "saved": sum(1 for row in rows if row["execution_status"] == "saved"),
        "blocked": sum(1 for row in rows if row["execution_status"] == "blocked"),
        "failed": sum(1 for row in rows if row["execution_status"] == "failed"),
    }


def filter_batch_summary_rows(
    summary_rows: list[Mapping[str, Any]] | None,
    *,
    execution_status: str = "all",
) -> list[dict[str, Any]]:
    """Filter normalized batch-summary rows by outcome label."""
    rows = normalize_batch_summary_rows(summary_rows)
    token = str(execution_status or "all").strip().lower()
    if token in {"all", ""}:
        return rows
    return [row for row in rows if row["execution_status"] == token]
