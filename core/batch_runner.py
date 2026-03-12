"""Brownfield batch template execution for compare-workspace stable modalities."""

from __future__ import annotations

import copy
from typing import Any, Mapping

import numpy as np

from core.dta_processor import DTAProcessor
from core.dsc_processor import DSCProcessor
from core.peak_analysis import characterize_peaks
from core.processing_schema import (
    ensure_processing_payload,
    get_workflow_templates,
    update_method_context,
    update_processing_step,
    update_tga_unit_context,
)
from core.provenance import build_calibration_reference_context, build_result_provenance
from core.result_serialization import serialize_dsc_result, serialize_dta_result, serialize_spectral_result, serialize_tga_result
from core.tga_processor import TGAProcessor, resolve_tga_unit_interpretation
from core.validation import enrich_spectral_result_validation, validate_thermal_dataset


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
_DTA_TEMPLATE_DEFAULTS = {
    "dta.general": {
        "smoothing": {"method": "savgol", "window_length": 11, "polyorder": 3},
        "baseline": {"method": "asls"},
        "peak_detection": {
            "detect_endothermic": True,
            "detect_exothermic": True,
        },
    },
    "dta.thermal_events": {
        "smoothing": {"method": "savgol", "window_length": 15, "polyorder": 3},
        "baseline": {"method": "asls"},
        "peak_detection": {
            "detect_endothermic": True,
            "detect_exothermic": True,
            "prominence": 0.0,
            "distance": 8,
        },
    },
}
_FTIR_TEMPLATE_DEFAULTS = {
    "ftir.general": {
        "smoothing": {"method": "moving_average", "window_length": 11},
        "baseline": {"method": "linear"},
        "normalization": {"method": "vector"},
        "peak_detection": {"prominence": 0.05, "min_distance": 6, "max_peaks": 12},
        "similarity_matching": {"metric": "cosine", "top_n": 3, "minimum_score": 0.45},
    },
    "ftir.functional_groups": {
        "smoothing": {"method": "moving_average", "window_length": 9},
        "baseline": {"method": "linear"},
        "normalization": {"method": "vector"},
        "peak_detection": {"prominence": 0.04, "min_distance": 5, "max_peaks": 16},
        "similarity_matching": {"metric": "cosine", "top_n": 5, "minimum_score": 0.42},
    },
}
_RAMAN_TEMPLATE_DEFAULTS = {
    "raman.general": {
        "smoothing": {"method": "moving_average", "window_length": 9},
        "baseline": {"method": "linear"},
        "normalization": {"method": "snv"},
        "peak_detection": {"prominence": 0.04, "min_distance": 5, "max_peaks": 14},
        "similarity_matching": {"metric": "cosine", "top_n": 3, "minimum_score": 0.45},
    },
    "raman.polymorph_screening": {
        "smoothing": {"method": "moving_average", "window_length": 7},
        "baseline": {"method": "linear"},
        "normalization": {"method": "snv"},
        "peak_detection": {"prominence": 0.03, "min_distance": 4, "max_peaks": 18},
        "similarity_matching": {"metric": "pearson", "top_n": 5, "minimum_score": 0.4},
    },
}
_VALID_EXECUTION_STATUSES = {"saved", "blocked", "failed"}


def _resolve_batch_tga_processing(processing: dict[str, Any], dataset) -> tuple[dict[str, Any], dict[str, Any]]:
    method_context = processing.get("method_context") or {}
    unit_context = resolve_tga_unit_interpretation(
        dataset.data["signal"].values,
        unit_mode=method_context.get("tga_unit_mode_declared") or "auto",
        signal_unit=(dataset.units or {}).get("signal"),
        initial_mass_mg=dataset.metadata.get("sample_mass"),
    )
    return update_tga_unit_context(processing, unit_context), unit_context


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
    if normalized_type == "DTA":
        return _execute_dta_batch(
            dataset_key=dataset_key,
            dataset=dataset,
            processing=processing,
            analysis_history=analysis_history,
            analyst_name=analyst_name,
            app_version=app_version,
            batch_run_id=batch_run_id,
        )
    if normalized_type in {"FTIR", "RAMAN"}:
        return _execute_spectral_batch(
            dataset_key=dataset_key,
            dataset=dataset,
            analysis_type=normalized_type,
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
    smoothed_signal = processor.get_result().smoothed_signal.copy()

    baseline_method = baseline.pop("method", "asls")
    processor.correct_baseline(method=baseline_method, **baseline)
    corrected_signal = processor.get_result().smoothed_signal.copy()

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
    processing, unit_context = _resolve_batch_tga_processing(processing, dataset)

    smoothing = copy.deepcopy((processing.get("signal_pipeline") or {}).get("smoothing") or {})
    step_detection = copy.deepcopy((processing.get("analysis_steps") or {}).get("step_detection") or {})

    processor = TGAProcessor(
        temperature,
        signal,
        initial_mass_mg=initial_mass_mg,
        metadata=dataset.metadata,
        unit_mode=str(unit_context["resolved_unit_mode"]),
        signal_unit=(dataset.units or {}).get("signal"),
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
    if analysis_type == "DSC":
        catalog = _DSC_TEMPLATE_DEFAULTS
        fallback = "dsc.general"
    elif analysis_type == "TGA":
        catalog = _TGA_TEMPLATE_DEFAULTS
        fallback = "tga.general"
    elif analysis_type == "DTA":
        catalog = _DTA_TEMPLATE_DEFAULTS
        fallback = "dta.general"
    elif analysis_type == "FTIR":
        catalog = _FTIR_TEMPLATE_DEFAULTS
        fallback = "ftir.general"
    elif analysis_type == "RAMAN":
        catalog = _RAMAN_TEMPLATE_DEFAULTS
        fallback = "raman.general"
    else:
        raise ValueError(f"Unsupported batch analysis type '{analysis_type}'")

    if workflow_template_id in catalog:
        return copy.deepcopy(catalog[workflow_template_id])
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


def _execute_dta_batch(
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

    smoothing = copy.deepcopy((processing.get("signal_pipeline") or {}).get("smoothing") or {})
    baseline = copy.deepcopy((processing.get("signal_pipeline") or {}).get("baseline") or {})
    peak_detection = copy.deepcopy((processing.get("analysis_steps") or {}).get("peak_detection") or {})

    processor = DTAProcessor(
        temperature,
        signal,
        metadata=dataset.metadata,
    )

    smooth_method = smoothing.pop("method", "savgol")
    processor.smooth(method=smooth_method, **smoothing)

    baseline_method = baseline.pop("method", "asls")
    processor.correct_baseline(method=baseline_method, **baseline)

    direction = str(peak_detection.pop("direction", "both") or "both").lower()
    detect_endothermic = peak_detection.pop("detect_endothermic", None)
    detect_exothermic = peak_detection.pop("detect_exothermic", None)
    if detect_endothermic is None:
        detect_endothermic = direction in {"both", "down", "endo", "endothermic"}
    if detect_exothermic is None:
        detect_exothermic = direction in {"both", "up", "exo", "exothermic"}
    if not detect_endothermic and not detect_exothermic:
        detect_endothermic = True
        detect_exothermic = True
    if peak_detection.get("prominence") in ("", 0, 0.0):
        peak_detection["prominence"] = None
    if peak_detection.get("distance") in ("", 0, 0.0):
        peak_detection["distance"] = None
    if peak_detection.get("min_peak_height") in ("", 0, 0.0):
        peak_detection["min_peak_height"] = None

    processor.find_peaks(
        detect_endothermic=bool(detect_endothermic),
        detect_exothermic=bool(detect_exothermic),
        **peak_detection,
    )
    result = processor.get_result()
    if result.peaks:
        result.peaks = characterize_peaks(
            temperature,
            result.smoothed_signal,
            list(result.peaks),
            baseline=result.baseline,
        )

    calibration_context = build_calibration_reference_context(
        dataset=dataset,
        analysis_type="DTA",
        reference_temperature_c=_select_dta_reference_temperature(result),
    )
    processing = update_method_context(processing, calibration_context, analysis_type="DTA")
    validation = validate_thermal_dataset(dataset, analysis_type="DTA", processing=processing)
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
    record = serialize_dta_result(
        dataset_key,
        dataset,
        result.peaks,
        artifacts={},
        processing=processing,
        provenance=provenance,
        validation=validation,
        review={"commercial_scope": "stable_dta", "batch_runner": "compare_workspace"},
    )
    state = {
        "smoothed": result.smoothed_signal,
        "baseline": result.baseline,
        "corrected": result.smoothed_signal,
        "peaks": result.peaks,
        "processing": processing,
    }
    return {
        "status": "saved",
        "analysis_type": "DTA",
        "dataset_key": dataset_key,
        "processing": processing,
        "validation": validation,
        "record": record,
        "state": state,
        "summary_row": _make_summary_row(
            dataset_key=dataset_key,
            dataset=dataset,
            analysis_type="DTA",
            processing=processing,
            validation=validation,
            execution_status="saved",
            record=record,
            failure_reason="",
        ),
    }


def _select_dta_reference_temperature(result) -> float | None:
    peaks = getattr(result, "peaks", []) or []
    if peaks:
        return getattr(peaks[0], "peak_temperature", None) or getattr(peaks[0], "temperature", None)
    return None


def _slug_token(value: Any) -> str:
    text = "".join(char.lower() if char.isalnum() else "_" for char in str(value or "").strip())
    token = "_".join(part for part in text.split("_") if part)
    return token or "reference"


def _to_float_array(values: Any) -> np.ndarray | None:
    if values is None:
        return None
    try:
        array = np.asarray(values, dtype=float)
    except Exception:
        return None
    if array.ndim != 1 or array.size < 3:
        return None
    if not np.isfinite(array).all():
        return None
    return array


def _sorted_axis_signal(axis: np.ndarray, signal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(axis)
    sorted_axis = axis[order]
    sorted_signal = signal[order]
    unique_axis, unique_idx = np.unique(sorted_axis, return_index=True)
    return unique_axis, sorted_signal[unique_idx]


def _apply_spectral_smoothing(signal: np.ndarray, config: Mapping[str, Any]) -> np.ndarray:
    method = str(config.get("method") or "moving_average").strip().lower()
    if method in {"none", "off"}:
        return signal.copy()
    window = int(config.get("window_length") or 9)
    if window < 3:
        window = 3
    if window % 2 == 0:
        window += 1
    kernel = np.ones(window, dtype=float) / float(window)
    pad = window // 2
    padded = np.pad(signal, (pad, pad), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def _estimate_spectral_baseline(axis: np.ndarray, signal: np.ndarray, config: Mapping[str, Any]) -> np.ndarray:
    method = str(config.get("method") or "linear").strip().lower()
    if method in {"none", "off"}:
        return np.zeros_like(signal)
    if method in {"linear", "asls", "rubberband"}:
        start = float(signal[0])
        end = float(signal[-1])
        if float(axis[-1]) == float(axis[0]):
            return np.full_like(signal, start)
        slope = (end - start) / (float(axis[-1]) - float(axis[0]))
        return start + slope * (axis - float(axis[0]))
    offset = float(np.min(signal))
    return np.full_like(signal, offset)


def _normalize_spectral_signal(signal: np.ndarray, config: Mapping[str, Any]) -> np.ndarray:
    method = str(config.get("method") or "vector").strip().lower()
    centered = signal - float(np.mean(signal))
    if method == "snv":
        std = float(np.std(centered))
        return centered / std if std > 0 else centered
    if method == "max":
        scale = float(np.max(np.abs(signal)))
        return signal / scale if scale > 0 else signal.copy()
    norm = float(np.linalg.norm(signal))
    return signal / norm if norm > 0 else signal.copy()


def _detect_spectral_peaks(axis: np.ndarray, signal: np.ndarray, config: Mapping[str, Any]) -> list[dict[str, float]]:
    prominence = float(config.get("prominence") or 0.05)
    min_distance = int(config.get("min_distance") or 5)
    max_peaks = int(config.get("max_peaks") or 10)

    candidate_indices: list[int] = []
    for idx in range(1, signal.size - 1):
        if signal[idx] < prominence:
            continue
        if signal[idx] >= signal[idx - 1] and signal[idx] >= signal[idx + 1]:
            candidate_indices.append(idx)

    selected: list[int] = []
    for idx in sorted(candidate_indices, key=lambda item: float(signal[item]), reverse=True):
        if any(abs(idx - prev) < min_distance for prev in selected):
            continue
        selected.append(idx)
        if len(selected) >= max_peaks:
            break

    return [
        {"position": float(axis[idx]), "intensity": float(signal[idx])}
        for idx in sorted(selected)
    ]


def _extract_reference_signal(entry: Mapping[str, Any]) -> tuple[np.ndarray | None, np.ndarray | None]:
    axis = _to_float_array(entry.get("axis") or entry.get("temperature") or entry.get("x"))
    signal = _to_float_array(entry.get("signal") or entry.get("intensity") or entry.get("y"))
    if axis is None or signal is None or axis.size != signal.size:
        return None, None
    return _sorted_axis_signal(axis, signal)


def _resolve_spectral_references(
    *,
    dataset,
    processing: Mapping[str, Any],
) -> list[dict[str, Any]]:
    metadata = getattr(dataset, "metadata", {}) or {}
    method_context = (processing.get("method_context") or {}) if isinstance(processing, Mapping) else {}
    raw_references = (
        metadata.get("spectral_reference_library")
        or metadata.get("reference_library")
        or method_context.get("spectral_reference_library")
        or []
    )
    if not isinstance(raw_references, list):
        return []

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw_references, start=1):
        if not isinstance(item, Mapping):
            continue
        candidate_id = str(item.get("id") or item.get("candidate_id") or f"reference_{index}")
        candidate_name = str(item.get("name") or item.get("candidate_name") or candidate_id)
        axis, signal = _extract_reference_signal(item)
        if axis is None or signal is None:
            continue
        normalized.append(
            {
                "candidate_id": _slug_token(candidate_id),
                "candidate_name": candidate_name,
                "axis": axis,
                "signal": signal,
            }
        )
    return normalized


def _spectral_similarity(observed: np.ndarray, reference: np.ndarray, metric: str) -> float:
    token = metric.strip().lower()
    if token == "pearson":
        obs = observed - float(np.mean(observed))
        ref = reference - float(np.mean(reference))
        obs_norm = float(np.linalg.norm(obs))
        ref_norm = float(np.linalg.norm(ref))
        if obs_norm == 0.0 or ref_norm == 0.0:
            return 0.0
        correlation = float(np.dot(obs, ref) / (obs_norm * ref_norm))
        return max(0.0, min(1.0, (correlation + 1.0) / 2.0))
    obs_norm = float(np.linalg.norm(observed))
    ref_norm = float(np.linalg.norm(reference))
    if obs_norm == 0.0 or ref_norm == 0.0:
        return 0.0
    similarity = float(np.dot(observed, reference) / (obs_norm * ref_norm))
    return max(0.0, min(1.0, (similarity + 1.0) / 2.0))


def _confidence_band(score: float, minimum_score: float) -> str:
    if score >= max(minimum_score + 0.35, 0.85):
        return "high"
    if score >= max(minimum_score + 0.15, 0.65):
        return "medium"
    if score >= minimum_score:
        return "low"
    return "no_match"


def _shared_peak_count(observed_peaks: list[dict[str, float]], reference_peaks: list[dict[str, float]], tolerance: float = 12.0) -> int:
    if not observed_peaks or not reference_peaks:
        return 0
    remaining = [float(item["position"]) for item in reference_peaks]
    shared = 0
    for observed in observed_peaks:
        position = float(observed["position"])
        closest_index = None
        closest_delta = None
        for idx, candidate in enumerate(remaining):
            delta = abs(position - candidate)
            if closest_delta is None or delta < closest_delta:
                closest_delta = delta
                closest_index = idx
        if closest_delta is not None and closest_delta <= tolerance and closest_index is not None:
            shared += 1
            remaining.pop(closest_index)
    return shared


def _rank_spectral_matches(
    *,
    axis: np.ndarray,
    normalized_signal: np.ndarray,
    observed_peaks: list[dict[str, float]],
    references: list[dict[str, Any]],
    matching_config: Mapping[str, Any],
    peak_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    metric = str(matching_config.get("metric") or "cosine")
    top_n = int(matching_config.get("top_n") or 3)
    minimum_score = float(matching_config.get("minimum_score") or 0.45)
    if top_n < 1:
        top_n = 1

    ranked: list[dict[str, Any]] = []
    for reference in references:
        reference_axis = reference["axis"]
        reference_signal = reference["signal"]
        interpolated = np.interp(axis, reference_axis, reference_signal)
        reference_smoothed = _apply_spectral_smoothing(interpolated, {"method": "none"})
        reference_normalized = _normalize_spectral_signal(reference_smoothed, {"method": "vector"})
        score = _spectral_similarity(normalized_signal, reference_normalized, metric)
        confidence_band = _confidence_band(score, minimum_score)
        reference_peaks = _detect_spectral_peaks(axis, reference_normalized, peak_config)
        shared = _shared_peak_count(observed_peaks, reference_peaks)
        overlap_ratio = float(shared / max(len(observed_peaks), len(reference_peaks), 1))
        ranked.append(
            {
                "candidate_id": reference["candidate_id"],
                "candidate_name": reference["candidate_name"],
                "normalized_score": round(score, 4),
                "confidence_band": confidence_band,
                "evidence": {
                    "metric": metric.lower(),
                    "observed_peak_count": len(observed_peaks),
                    "reference_peak_count": len(reference_peaks),
                    "shared_peak_count": shared,
                    "peak_overlap_ratio": round(overlap_ratio, 4),
                },
            }
        )

    ranked.sort(key=lambda item: (-float(item["normalized_score"]), str(item["candidate_id"])))
    trimmed = ranked[:top_n]
    for rank, item in enumerate(trimmed, start=1):
        item["rank"] = rank
    return trimmed


def _execute_spectral_batch(
    *,
    dataset_key: str,
    dataset,
    analysis_type: str,
    processing: dict[str, Any],
    analysis_history: list[dict[str, Any]] | None,
    analyst_name: str | None,
    app_version: str | None,
    batch_run_id: str | None,
) -> dict[str, Any]:
    axis = np.asarray(dataset.data["temperature"], dtype=float)
    signal = np.asarray(dataset.data["signal"], dtype=float)
    axis, signal = _sorted_axis_signal(axis, signal)

    smoothing = copy.deepcopy((processing.get("signal_pipeline") or {}).get("smoothing") or {})
    baseline = copy.deepcopy((processing.get("signal_pipeline") or {}).get("baseline") or {})
    normalization = copy.deepcopy((processing.get("signal_pipeline") or {}).get("normalization") or {})
    peak_detection = copy.deepcopy((processing.get("analysis_steps") or {}).get("peak_detection") or {})
    similarity_matching = copy.deepcopy((processing.get("analysis_steps") or {}).get("similarity_matching") or {})

    smoothed = _apply_spectral_smoothing(signal, smoothing)
    baseline_curve = _estimate_spectral_baseline(axis, smoothed, baseline)
    corrected = smoothed - baseline_curve
    normalized_signal = _normalize_spectral_signal(corrected, normalization)
    observed_peaks = _detect_spectral_peaks(axis, normalized_signal, peak_detection)

    references = _resolve_spectral_references(dataset=dataset, processing=processing)
    ranked_matches = _rank_spectral_matches(
        axis=axis,
        normalized_signal=normalized_signal,
        observed_peaks=observed_peaks,
        references=references,
        matching_config=similarity_matching,
        peak_config=peak_detection,
    )

    minimum_score = float(similarity_matching.get("minimum_score") or 0.45)
    top_match = ranked_matches[0] if ranked_matches else None
    matched = bool(top_match) and float(top_match["normalized_score"]) >= minimum_score
    match_status = "matched" if matched else "no_match"
    top_score = float(top_match["normalized_score"]) if top_match else 0.0
    confidence_band = top_match["confidence_band"] if matched and top_match else "no_match"
    caution_payload = (
        {}
        if matched
        else {
            "code": "spectral_no_match",
            "message": "No reference candidate met the minimum similarity threshold.",
            "minimum_score": minimum_score,
            "top_candidate_score": round(top_score, 4),
        }
    )

    processing = update_method_context(
        processing,
        {
            "batch_run_id": batch_run_id or "",
            "batch_template_runner": "compare_workspace",
            "reference_candidate_count": len(references),
            "matching_metric": str(similarity_matching.get("metric") or "cosine").lower(),
            "matching_top_n": int(similarity_matching.get("top_n") or 3),
            "matching_minimum_score": minimum_score,
        },
        analysis_type=analysis_type,
    )
    validation = validate_thermal_dataset(dataset, analysis_type=analysis_type, processing=processing)
    provenance = build_result_provenance(
        dataset=dataset,
        dataset_key=dataset_key,
        analysis_history=analysis_history,
        app_version=app_version,
        analyst_name=analyst_name,
        extra={
            "batch_run_id": batch_run_id,
            "batch_runner": "compare_workspace",
            "analysis_type": analysis_type,
            "match_status": match_status,
            "reference_candidate_count": len(references),
        },
    )

    summary = {
        "peak_count": len(observed_peaks),
        "match_status": match_status,
        "candidate_count": len(ranked_matches),
        "top_match_id": top_match["candidate_id"] if matched and top_match else None,
        "top_match_name": top_match["candidate_name"] if matched and top_match else None,
        "top_match_score": round(top_score, 4),
        "confidence_band": confidence_band,
        "caution_code": caution_payload.get("code", ""),
    }
    rows = [
        {
            "rank": item["rank"],
            "candidate_id": item["candidate_id"],
            "candidate_name": item["candidate_name"],
            "normalized_score": item["normalized_score"],
            "confidence_band": item["confidence_band"],
            "evidence": item["evidence"],
        }
        for item in ranked_matches
    ]
    validation = enrich_spectral_result_validation(
        validation,
        analysis_type=analysis_type,
        summary=summary,
        rows=rows,
    )
    record = serialize_spectral_result(
        dataset_key,
        dataset,
        analysis_type=analysis_type,
        summary=summary,
        rows=rows,
        status="stable",
        artifacts={},
        processing=processing,
        provenance=provenance,
        validation=validation,
        review={
            "commercial_scope": f"stable_{analysis_type.lower()}",
            "batch_runner": "compare_workspace",
            "caution": caution_payload,
        },
    )
    state = {
        "axis": axis.tolist(),
        "smoothed": smoothed.tolist(),
        "baseline": baseline_curve.tolist(),
        "corrected": corrected.tolist(),
        "normalized": normalized_signal.tolist(),
        "peaks": observed_peaks,
        "matches": ranked_matches,
        "processing": processing,
    }

    return {
        "status": "saved",
        "analysis_type": analysis_type,
        "dataset_key": dataset_key,
        "processing": processing,
        "validation": validation,
        "record": record,
        "state": state,
        "summary_row": _make_summary_row(
            dataset_key=dataset_key,
            dataset=dataset,
            analysis_type=analysis_type,
            processing=processing,
            validation=validation,
            execution_status="saved",
            record=record,
            failure_reason="",
        ),
    }


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
