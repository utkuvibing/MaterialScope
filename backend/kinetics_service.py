"""Workspace-backed kinetics workflow for the preview Kinetics module.

Runs ``core.kinetics`` against workspace datasets (or explicit manual input)
and returns a normalized result record ready for ``state["results"]``.

Scientific-honesty contract:

- Heating rates are used only when traceable: a value typed in the request
  is recorded as ``user``-declared; otherwise the dataset metadata value is
  accepted only through ``core.units_dimensional.resolve_beta`` (``user`` or
  ``parsed`` provenance). Missing or legacy/unknown provenance blocks the run
  with an explicit reason — there is no 10 °C/min convenience default.
- Kissinger peak temperatures are explicit user input or resolved from a
  saved DSC analysis peak table (``peak_index``, or the single detected
  peak). They are never synthesized.
- DSC isoconversional methods (OFW/Friedman) require the backend's saved
  baseline-corrected DSC analysis state; there is no silent raw-signal
  fallback.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from backend.models import KineticsRunRequest
from backend.workspace import add_history_event, unique_dataset_key
from core.kinetics import (
    KINETICS_DEFAULT_CONFIDENCE_LEVEL,
    _resolve_kinetic_method,
    compute_conversion,
    run_kinetic_analysis,
)
from core.provenance import build_result_provenance
from core.result_serialization import (
    serialize_friedman_results,
    serialize_kissinger_result,
    serialize_ofw_results,
)
from core.units_dimensional import resolve_beta

KINETICS_ELIGIBLE_TYPES = {"DSC", "TGA"}
ALPHA_GRID_DEFAULTS = (0.10, 0.90, 0.05)


class KineticsValidationError(ValueError):
    """Raised when kinetics prerequisites are unmet; message lists reasons."""


def _blocked(reasons: list[str]) -> KineticsValidationError:
    return KineticsValidationError("; ".join(str(r) for r in reasons if r))


def _dataset_temperature_signal(dataset: Any) -> tuple[np.ndarray, np.ndarray]:
    frame = getattr(dataset, "data", None)
    if frame is None or "temperature" not in frame.columns or "signal" not in frame.columns:
        raise KineticsValidationError("dataset has no temperature/signal columns.")
    temperature = np.asarray(frame["temperature"], dtype=float)
    signal = np.asarray(frame["signal"], dtype=float)
    finite = np.isfinite(temperature) & np.isfinite(signal)
    return temperature[finite], signal[finite]


def _resolve_heating_rate(
    *,
    dataset_key: str,
    dataset: Any,
    declared_rate: float | None,
) -> tuple[float, str]:
    """Return ``(beta, source_label)`` or raise with an explicit reason."""
    if declared_rate is not None:
        try:
            beta = float(declared_rate)
        except (TypeError, ValueError) as exc:
            raise KineticsValidationError(
                f"dataset '{dataset_key}': declared heating rate is not numeric."
            ) from exc
        if not math.isfinite(beta) or beta <= 0.0:
            raise KineticsValidationError(
                f"dataset '{dataset_key}': declared heating rate must be positive."
            )
        return beta, "user"

    metadata = getattr(dataset, "metadata", {}) or {}
    beta, withheld_reason = resolve_beta(
        metadata.get("heating_rate"),
        metadata.get("heating_rate_source"),
    )
    if beta is None:
        raise KineticsValidationError(
            f"dataset '{dataset_key}': no traceable heating rate "
            f"({withheld_reason}); enter a value explicitly."
        )
    source = str(metadata.get("heating_rate_source") or "").strip().lower()
    return float(beta), f"metadata_{source or 'unknown'}"


def _peak_temperature_value(peak: Any) -> float | None:
    value = getattr(peak, "peak_temperature", None)
    if value is None and isinstance(peak, dict):
        value = peak.get("peak_temperature")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _resolve_peak_temperature(
    *,
    state: dict[str, Any],
    dataset_key: str,
    data_type: str,
    declared_temp: float | None,
    peak_index: int | None,
) -> tuple[float, str]:
    """Return ``(peak_temperature_c, source_label)`` or raise."""
    if declared_temp is not None:
        try:
            temp = float(declared_temp)
        except (TypeError, ValueError) as exc:
            raise KineticsValidationError(
                f"dataset '{dataset_key}': declared peak temperature is not numeric."
            ) from exc
        if not math.isfinite(temp):
            raise KineticsValidationError(
                f"dataset '{dataset_key}': declared peak temperature must be finite."
            )
        return temp, "user"

    if data_type != "DSC":
        raise KineticsValidationError(
            f"dataset '{dataset_key}': peak_temperature is required; there is no "
            "traceable saved peak to reuse."
        )

    dsc_state = state.get(f"dsc_state_{dataset_key}") or {}
    peaks = dsc_state.get("peaks") or []
    if not isinstance(peaks, list):
        peaks = []
    peak_temperatures = [(idx, _peak_temperature_value(p)) for idx, p in enumerate(peaks)]
    peak_temperatures = [(idx, t) for idx, t in peak_temperatures if t is not None]

    if peak_index is not None:
        for idx, temp in peak_temperatures:
            if idx == int(peak_index):
                return temp, f"dsc_analysis_peak[{idx}]"
        raise KineticsValidationError(
            f"dataset '{dataset_key}': peak_index {peak_index} is not present in the "
            "saved DSC analysis peaks."
        )
    if len(peak_temperatures) == 1:
        idx, temp = peak_temperatures[0]
        return temp, f"dsc_analysis_peak[{idx}]"
    if len(peak_temperatures) > 1:
        raise KineticsValidationError(
            f"dataset '{dataset_key}': the saved DSC analysis detected "
            f"{len(peak_temperatures)} peaks; enter peak_temperature explicitly or "
            "select peak_index."
        )
    raise KineticsValidationError(
        f"dataset '{dataset_key}': peak_temperature is required; no saved DSC "
        "analysis peak exists to reuse."
    )


def _dsc_corrected_arrays(
    *,
    state: dict[str, Any],
    dataset_key: str,
    dataset: Any,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(temperature, corrected_signal)`` from the saved DSC state."""
    dsc_state = state.get(f"dsc_state_{dataset_key}") or {}
    corrected = np.asarray(dsc_state.get("corrected") or [], dtype=float)
    if corrected.size == 0:
        raise KineticsValidationError(
            f"dataset '{dataset_key}': no baseline-corrected DSC signal is stored; "
            "run the DSC analysis (baseline correction) first."
        )
    dataset_temp, _signal = _dataset_temperature_signal(dataset)
    state_axis = np.asarray(dsc_state.get("axis") or dsc_state.get("temperature") or [], dtype=float)
    if state_axis.size == corrected.size:
        return state_axis, corrected
    if dataset_temp.size == corrected.size:
        return dataset_temp, corrected
    raise KineticsValidationError(
        f"dataset '{dataset_key}': corrected DSC signal length does not match "
        "any stored temperature axis."
    )


def _conversion_input(
    *,
    state: dict[str, Any],
    dataset_key: str,
    dataset: Any,
    data_type: str,
) -> tuple[np.ndarray, np.ndarray, str]:
    """Return ``(temperature, alpha, signal_basis_label)`` for OFW/Friedman."""
    if data_type == "TGA":
        temperature, signal = _dataset_temperature_signal(dataset)
        alpha = compute_conversion(temperature, signal, mode="tga")
        return temperature, alpha, "tga_raw_mass"
    temperature, corrected = _dsc_corrected_arrays(
        state=state,
        dataset_key=dataset_key,
        dataset=dataset,
    )
    alpha = compute_conversion(
        temperature,
        corrected,
        baseline=np.zeros_like(corrected),
        mode="dsc",
    )
    return temperature, alpha, "dsc_corrected_signal"


def _resolve_alpha_grid(request: KineticsRunRequest) -> tuple[list[float], dict[str, float]]:
    alpha_min = request.alpha_min if request.alpha_min is not None else ALPHA_GRID_DEFAULTS[0]
    alpha_max = request.alpha_max if request.alpha_max is not None else ALPHA_GRID_DEFAULTS[1]
    alpha_step = request.alpha_step if request.alpha_step is not None else ALPHA_GRID_DEFAULTS[2]
    alpha_min = float(alpha_min)
    alpha_max = float(alpha_max)
    alpha_step = float(alpha_step)
    if not (math.isfinite(alpha_min) and math.isfinite(alpha_max) and math.isfinite(alpha_step)):
        raise KineticsValidationError("alpha_min, alpha_max, and alpha_step must be finite numbers.")
    if not 0.0 < alpha_min < alpha_max <= 1.0:
        raise KineticsValidationError("alpha_min must be > 0 and smaller than alpha_max (<= 1).")
    if not 0.0 < alpha_step <= (alpha_max - alpha_min):
        raise KineticsValidationError("alpha_step must be positive and no larger than the alpha range.")
    values = np.arange(alpha_min, alpha_max + alpha_step / 2.0, alpha_step)
    values = values[(values > 0.0) & (values <= 1.0)]
    if values.size == 0:
        raise KineticsValidationError("the requested alpha grid contains no usable conversion levels.")
    return values.tolist(), {"alpha_min": alpha_min, "alpha_max": alpha_max, "alpha_step": alpha_step}


def _collect_manual_inputs(request: KineticsRunRequest) -> tuple[list[float], list[float], list[dict[str, Any]]]:
    issues: list[str] = []
    rates: list[float] = []
    temps: list[float] = []
    inputs: list[dict[str, Any]] = []
    points = list(request.manual_points or [])
    if len(points) < 2:
        raise KineticsValidationError("Manual Kissinger input requires at least two (rate, Tp) points.")
    for idx, point in enumerate(points):
        try:
            rate = float(point.heating_rate)
        except (TypeError, ValueError):
            issues.append(f"manual point {idx + 1}: heating rate is not numeric.")
            continue
        try:
            temp = float(point.peak_temperature)
        except (TypeError, ValueError):
            issues.append(f"manual point {idx + 1}: peak temperature is not numeric.")
            continue
        if not math.isfinite(rate) or rate <= 0.0:
            issues.append(f"manual point {idx + 1}: heating rate must be positive.")
            continue
        if not math.isfinite(temp):
            issues.append(f"manual point {idx + 1}: peak temperature must be finite.")
            continue
        rates.append(rate)
        temps.append(temp)
        inputs.append(
            {
                "source": "manual_entry",
                "heating_rate": rate,
                "heating_rate_source": "user",
                "peak_temperature": temp,
                "peak_temperature_source": "user",
            }
        )
    if issues:
        raise _blocked(issues)
    if len({round(rate, 6) for rate in rates}) < 2:
        raise KineticsValidationError("Kissinger requires at least two distinct positive heating rates.")
    return rates, temps, inputs


def _collect_dataset_inputs(
    *,
    state: dict[str, Any],
    request: KineticsRunRequest,
    need_peak_temperatures: bool,
) -> tuple[list[str], list[float], list[float] | None, str, list[dict[str, Any]]]:
    """Validate dataset selections and return keys, rates, temps, data_type, inputs."""
    issues: list[str] = []
    selections = list(request.dataset_selections or [])
    if len(selections) < 2:
        raise KineticsValidationError("Select at least two datasets for the kinetic analysis.")

    keys = [str(item.dataset_key) for item in selections]
    if len(set(keys)) != len(keys):
        issues.append("Select each dataset only once.")

    datasets = state.get("datasets") or {}
    resolved: list[tuple[str, Any, str]] = []
    for key in keys:
        dataset = datasets.get(key)
        if dataset is None:
            issues.append(f"Unknown dataset_key: {key}")
            continue
        data_type = str(getattr(dataset, "data_type", "") or "").upper()
        if data_type not in KINETICS_ELIGIBLE_TYPES:
            issues.append(
                f"dataset '{key}': only DSC and TGA datasets are supported "
                f"(got {data_type or 'unknown'})."
            )
            continue
        resolved.append((key, dataset, data_type))
    if issues:
        raise _blocked(issues)

    data_types = {data_type for _key, _dataset, data_type in resolved}
    if len(data_types) != 1:
        raise KineticsValidationError("Kinetics requires datasets of the same analysis type.")
    data_type = data_types.pop()

    rates: list[float] = []
    temps: list[float] = []
    inputs: list[dict[str, Any]] = []
    input_errors: list[str] = []
    for (key, dataset, _dtype), selection in zip(resolved, selections):
        try:
            beta, beta_source = _resolve_heating_rate(
                dataset_key=key,
                dataset=dataset,
                declared_rate=selection.heating_rate,
            )
            entry: dict[str, Any] = {
                "dataset_key": key,
                "data_type": data_type,
                "heating_rate": beta,
                "heating_rate_source": beta_source,
            }
            if need_peak_temperatures:
                temp, temp_source = _resolve_peak_temperature(
                    state=state,
                    dataset_key=key,
                    data_type=data_type,
                    declared_temp=selection.peak_temperature,
                    peak_index=selection.peak_index,
                )
                entry["peak_temperature"] = temp
                entry["peak_temperature_source"] = temp_source
        except KineticsValidationError as exc:
            input_errors.append(str(exc))
            continue
        if need_peak_temperatures:
            temps.append(entry["peak_temperature"])
        rates.append(beta)
        inputs.append(entry)
    if input_errors:
        raise _blocked(input_errors)
    if len({round(rate, 6) for rate in rates}) < 2:
        raise KineticsValidationError("Heating rates must contain at least two distinct positive values.")
    return keys, rates, (temps if need_peak_temperatures else None), data_type, inputs


def _serialize_record(
    *,
    method_id: str,
    payload: dict[str, Any],
    processing: dict[str, Any],
    provenance: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    results = payload["results"]
    common = {
        "artifacts": {},
        "processing": processing,
        "provenance": provenance,
        "validation": validation,
        "review": {"commercial_scope": "preview_kinetics"},
        "scientific_context": payload["scientific_context"],
    }
    if method_id == "kissinger":
        return serialize_kissinger_result(results[0], **common)
    if method_id == "ofw":
        return serialize_ofw_results(results, **common)
    return serialize_friedman_results(results, **common)


def run_kinetics_workflow(
    *,
    state: dict[str, Any],
    request: KineticsRunRequest,
    app_version: str | None = None,
    analyst_name: str | None = None,
) -> dict[str, Any]:
    """Validate, run, and persist a kinetics result into workspace state.

    Mutates ``state`` (adds the result record and a history event); the
    caller persists the store. Returns the record plus the core payload.

    Raises ``KineticsValidationError`` for prerequisite/validation failures.
    """
    method_id, method_label = _resolve_kinetic_method(request.method)
    input_mode = str(request.input_mode or "datasets").strip().lower()
    confidence_level = (
        float(request.confidence_level)
        if request.confidence_level is not None
        else KINETICS_DEFAULT_CONFIDENCE_LEVEL
    )

    if method_id == "kissinger" and input_mode == "manual":
        rates, temps, inputs = _collect_manual_inputs(request)
        dataset_keys: list[str] = []
        data_type = "manual"
        temperature_data = conversion_data = dalpha_dt_data = None
        alpha_grid: dict[str, float] = {}
        warnings: list[str] = []
        run_kwargs: dict[str, Any] = {
            "heating_rates": rates,
            "peak_temperatures": temps,
            "confidence_level": confidence_level,
        }
    else:
        if input_mode not in {"datasets", "manual"}:
            raise KineticsValidationError(f"Unsupported kinetics input_mode: {request.input_mode}")
        keys, rates, temps, data_type, inputs = _collect_dataset_inputs(
            state=state,
            request=request,
            need_peak_temperatures=(method_id == "kissinger"),
        )
        dataset_keys = keys
        warnings = [
            f"dataset '{entry['dataset_key']}': heating rate is {entry['heating_rate_source']}-declared."
            for entry in inputs
            if entry.get("heating_rate_source") == "user"
        ]
        if method_id == "kissinger":
            run_kwargs = {
                "heating_rates": rates,
                "peak_temperatures": temps,
                "confidence_level": confidence_level,
            }
            temperature_data = conversion_data = dalpha_dt_data = None
            alpha_grid = {}
        else:
            alpha_values, alpha_grid = _resolve_alpha_grid(request)
            temperature_data = []
            conversion_data = []
            dalpha_dt_data = [] if method_id == "friedman" else None
            for entry in inputs:
                dataset = state["datasets"][entry["dataset_key"]]
                temperature, alpha, basis = _conversion_input(
                    state=state,
                    dataset_key=entry["dataset_key"],
                    dataset=dataset,
                    data_type=data_type,
                )
                entry["signal_basis"] = basis
                temperature_data.append(temperature)
                conversion_data.append(alpha)
                if method_id == "friedman":
                    # Convention from the shared workflow: dα/dt [min^-1] =
                    # gradient(α, T) [1/°C] × β [°C/min].
                    entry["dalpha_dt_derivation"] = "gradient(alpha, temperature) * heating_rate"
                    dalpha_dt_data.append(np.gradient(alpha, temperature) * float(entry["heating_rate"]))
            run_kwargs = {
                "heating_rates": rates,
                "temperature_data": temperature_data,
                "conversion_data": conversion_data,
                "alpha_values": alpha_values,
                "confidence_level": confidence_level,
            }
            if method_id == "friedman":
                run_kwargs["dalpha_dt_data"] = dalpha_dt_data

    try:
        payload = run_kinetic_analysis(method_id, **run_kwargs)
    except ValueError as exc:
        raise KineticsValidationError(str(exc)) from exc

    results = payload.get("results") or []
    if not results:
        raise KineticsValidationError(
            f"{method_label} produced no fitted points; check the alpha grid and conversion coverage."
        )

    provenance = build_result_provenance(
        dataset=None,
        dataset_key=None,
        analysis_history=state.get("analysis_history") or [],
        app_version=app_version,
        analyst_name=analyst_name,
        extra={
            "analysis_scope": "preview_kinetics",
            "input_mode": input_mode if method_id == "kissinger" else "datasets",
            "dataset_keys": dataset_keys,
            "data_type": data_type,
            "heating_rate_sources": sorted({entry.get("heating_rate_source", "") for entry in inputs}),
        },
    )
    processing: dict[str, Any] = {
        "method": method_label,
        "kinetics_method": method_id,
        "input_mode": input_mode if method_id == "kissinger" else "datasets",
        "inputs": inputs,
        "confidence_level": confidence_level,
    }
    if alpha_grid:
        processing["alpha_grid"] = alpha_grid
    if method_id == "friedman":
        processing["dalpha_dt_derivation"] = "np.gradient(alpha, temperature) * heating_rate (min^-1)"
    validation = {
        "status": "warn" if warnings else "pass",
        "warnings": warnings,
        "issues": [],
    }

    record = _serialize_record(
        method_id=method_id,
        payload=payload,
        processing=processing,
        provenance=provenance,
        validation=validation,
    )
    # The per-method serializers persist only a minimal summary; merge the
    # core's aggregate summary so ResultDetail/report consumers see the Ea
    # statistics, CI method/scope, and intercept semantics.
    record["summary"] = {
        **(record.get("summary") or {}),
        **(payload.get("summary") or {}),
    }

    results_map = state.setdefault("results", {})
    result_id = unique_dataset_key(results_map, f"kinetics_{method_id}")
    record["id"] = result_id
    record["metadata"] = {
        "dataset_keys": dataset_keys,
        "data_type": data_type,
        "input_mode": processing["input_mode"],
        "preview_module": True,
    }
    record["report_payload"] = {
        "plots": [
            dict(result.plot_data) for result in results if getattr(result, "plot_data", None)
        ],
        "inputs": inputs,
        "method_id": method_id,
        "method_label": method_label,
    }
    results_map[result_id] = record

    add_history_event(
        state,
        action="Kinetic Analysis",
        details=(
            f"{method_label} run on {len(inputs)} input(s); result '{result_id}' saved."
        ),
        page="Kinetics",
        result_id=result_id,
    )

    return {
        "result_id": result_id,
        "record": record,
        "method_id": method_id,
        "method_label": method_label,
        "analysis_type": record.get("analysis_type"),
        "payload": payload,
        "validation": validation,
        "provenance": provenance,
    }
