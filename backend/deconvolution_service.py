"""Workspace-backed peak deconvolution workflow for the preview module.

Runs ``core.peak_deconvolution`` against a single workspace dataset and
returns a normalized result record ready for ``state["results"]``.

Scientific-honesty contract:

- The axis is treated generically.  Labels and units come from the effective
  axis resolved by ``backend.analysis_state`` (temperature for DSC/DTA/TGA,
  wavenumber/raman-shift/wavelength for FTIR/Raman, two_theta/q for XRD) —
  never from a hardcoded temperature assumption.
- A requested signal basis must actually exist.  A missing basis blocks the
  run with an explicit reason; there is no silent fallback to raw.
- Signal polarity is never inferred.  ``invert_signal_for_fit`` is the only
  sign control, it defaults to off, and it is recorded in processing,
  provenance and the report payload when used.
- The automatic estimator is diagnostic: a signal with no positive structure
  at all cannot be represented by the core's non-negative components and is
  blocked instead of being reshaped.
- lmfit's ``amplitude`` is an integrated area parameter, not a peak height;
  the fitted rows also carry lmfit's derived ``fwhm`` and ``height``.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from backend.analysis_state import ResolvedAnalysisState, resolve_analysis_state
from backend.models import DeconvolutionRunRequest
from backend.workspace import add_history_event, unique_dataset_key
from core.axis_labels import build_axis_title
from core.modalities import stable_analysis_types
from core.peak_deconvolution import auto_estimate_peaks, deconvolve_peaks
from core.provenance import build_result_provenance
from core.result_serialization import serialize_deconvolution_result

DECONVOLUTION_ANALYSIS_SCOPE = "preview_deconvolution"
BASIS_NAMES: tuple[str, ...] = ("raw", "smoothed", "corrected", "normalized")
PEAK_SHAPES: tuple[str, ...] = ("gaussian", "lorentzian", "pseudo_voigt")
MIN_USABLE_POINTS = 10
MAX_PEAKS = 10
TRANSMITTANCE_ROLES = {"transmittance", "%t", "transmission", "t"}
BASIS_REASON_COPY = {
    "no_usable_samples": "the imported dataset has no finite axis/signal samples",
    "no_saved_analysis_state": "no saved modality analysis exists for this dataset yet",
    "raw_signal_not_aligned_with_effective_axis": (
        "the raw data exists only on the original imported axis while the saved analysis state uses a "
        "converted effective axis; use the smoothed, corrected or normalized basis instead"
    ),
}


class DeconvolutionValidationError(ValueError):
    """Raised when deconvolution prerequisites are unmet; the message says why."""


def _json_series(values: Any) -> list[float | None]:
    """Convert an array to a JSON-safe list, mapping non-finite values to None."""
    array = np.asarray(values, dtype=float)
    array = np.where(np.isfinite(array), array, None)
    return array.tolist()


def _basis_unavailable_message(basis: str, reason: str | None) -> str:
    detail = BASIS_REASON_COPY.get(
        str(reason or ""),
        f"the requested basis is not present in the saved analysis state ({reason or 'unknown'})",
    )
    return (
        f"Signal basis '{basis}' is unavailable: {detail}. "
        "No fallback basis is substituted; choose an available basis or run the modality analysis first."
    )


def _coerce_initial_params(
    request: DeconvolutionRunRequest,
    *,
    n_peaks: int,
    domain_low: float,
    domain_high: float,
) -> list[dict]:
    """Validate and convert user-supplied initial guesses.

    Only fields the caller actually supplied are kept, so the core can record
    per-field provenance (the omitted fields stay ``auto``).
    """
    guesses = list(request.initial_params or [])
    if len(guesses) > n_peaks:
        raise DeconvolutionValidationError(
            f"initial_params provides {len(guesses)} entries for {n_peaks} requested peaks; "
            "remove the extra entries instead of having them silently ignored."
        )

    converted: list[dict] = []
    for index, guess in enumerate(guesses):
        entry: dict[str, float] = {}
        for field in ("center", "amplitude", "sigma"):
            raw_value = getattr(guess, field, None)
            if raw_value is None:
                continue
            value = float(raw_value)
            if not math.isfinite(value):
                raise DeconvolutionValidationError(f"initial_params[{index}].{field} must be finite.")
            if field == "sigma" and value <= 0:
                raise DeconvolutionValidationError(f"initial_params[{index}].sigma must be > 0.")
            if field == "amplitude" and value < 0:
                raise DeconvolutionValidationError(
                    f"initial_params[{index}].amplitude must be >= 0; peak components are non-negative."
                )
            if field == "center" and not (domain_low <= value <= domain_high):
                raise DeconvolutionValidationError(
                    f"initial_params[{index}].center={value} is outside the selected axis domain "
                    f"[{domain_low}, {domain_high}]."
                )
            entry[field] = value
        converted.append(entry)
    return converted


def _select_signal(
    resolved: ResolvedAnalysisState,
    basis: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the finite, axis-sorted (axis, signal) pair for a basis."""
    availability = resolved.bases.get(basis)
    if availability is None or not availability.available:
        raise DeconvolutionValidationError(
            _basis_unavailable_message(basis, availability.reason if availability else None)
        )

    axis = np.asarray(resolved.axis, dtype=float)
    values = np.asarray(resolved.series_for_basis(basis), dtype=float)
    if axis.size == 0 or values.size == 0:
        raise DeconvolutionValidationError(f"Signal basis '{basis}' has no usable samples.")
    if axis.size != values.size:
        raise DeconvolutionValidationError(
            f"Axis and '{basis}' signal lengths differ ({axis.size} vs {values.size}); "
            "the saved analysis state is inconsistent."
        )

    finite = np.isfinite(axis) & np.isfinite(values)
    if not np.any(finite):
        raise DeconvolutionValidationError(f"Signal basis '{basis}' contains no finite samples.")

    axis = axis[finite]
    values = values[finite]
    order = np.argsort(axis, kind="stable")
    return axis[order], values[order]


def _apply_range(
    axis: np.ndarray,
    values: np.ndarray,
    request: DeconvolutionRunRequest,
) -> tuple[np.ndarray, np.ndarray, list[float]]:
    """Restrict the curve to the requested axis window; never extrapolate."""
    limits: list[float | None] = []
    for name, raw_value in (("range_min", request.range_min), ("range_max", request.range_max)):
        if raw_value is None:
            limits.append(None)
            continue
        value = float(raw_value)
        if not math.isfinite(value):
            raise DeconvolutionValidationError(f"{name} must be finite.")
        limits.append(value)

    range_min, range_max = limits
    if range_min is not None and range_max is not None and not range_min < range_max:
        raise DeconvolutionValidationError(
            f"range_min ({range_min}) must be less than range_max ({range_max})."
        )

    domain_low = float(axis.min())
    domain_high = float(axis.max())
    if range_min is None and range_max is None:
        return axis, values, [domain_low, domain_high]

    low = domain_low if range_min is None else float(range_min)
    high = domain_high if range_max is None else float(range_max)
    if high < domain_low or low > domain_high:
        raise DeconvolutionValidationError(
            f"Selected range [{low}, {high}] does not intersect the measured axis domain "
            f"[{domain_low}, {domain_high}]."
        )

    mask = (axis >= low) & (axis <= high)
    axis = axis[mask]
    values = values[mask]
    if axis.size < MIN_USABLE_POINTS:
        raise DeconvolutionValidationError(
            f"At least {MIN_USABLE_POINTS} usable points are required after range filtering; got {axis.size}."
        )
    return axis, values, [float(axis.min()), float(axis.max())]


def _transmittance_warning(
    analysis_type: str,
    signal_role: str | None,
    *,
    inversion_applied: bool,
) -> str | None:
    """Advisory for a transmittance *basis*; never a silent conversion."""
    if analysis_type != "FTIR" or inversion_applied:
        return None
    role = str(signal_role or "").strip().lower()
    if role not in TRANSMITTANCE_ROLES:
        return None
    return (
        "FTIR transmittance basis: %T absorption bands are typically downward-going while this fit uses "
        "non-negative peak components. Prefer the absorbance basis (signal conversion) or enable "
        "'Invert signal for fitting'. No conversion or inversion was applied automatically."
    )


def run_deconvolution_workflow(
    *,
    state: dict[str, Any],
    request: DeconvolutionRunRequest,
    app_version: str | None = None,
    analyst_name: str | None = None,
) -> dict[str, Any]:
    """Run a workspace-backed peak deconvolution and persist the result.

    Raises
    ------
    KeyError
        If ``dataset_key`` is not present in the workspace.
    DeconvolutionValidationError
        If any prerequisite is unmet.
    """
    dataset_key = str(request.dataset_key or "").strip()
    if not dataset_key:
        raise DeconvolutionValidationError("dataset_key is required.")

    datasets = (state or {}).get("datasets", {}) or {}
    dataset = datasets.get(dataset_key)
    if dataset is None:
        raise KeyError(dataset_key)

    analysis_type = str(getattr(dataset, "data_type", "") or "").strip().upper()
    if analysis_type not in stable_analysis_types():
        raise DeconvolutionValidationError(
            f"Unsupported modality for peak deconvolution: {analysis_type or 'unknown'}. "
            f"Supported modalities: {', '.join(stable_analysis_types())}."
        )

    try:
        resolved = resolve_analysis_state(state, analysis_type, dataset_key)
    except ValueError as exc:  # pragma: no cover - guarded by the check above
        raise DeconvolutionValidationError(str(exc)) from exc

    basis = str(request.signal_basis or "").strip().lower()
    if basis not in BASIS_NAMES:
        raise DeconvolutionValidationError(
            f"signal_basis must be one of {', '.join(BASIS_NAMES)}; got {request.signal_basis!r}."
        )

    n_peaks = int(request.n_peaks)
    if n_peaks < 1 or n_peaks > MAX_PEAKS:
        raise DeconvolutionValidationError(f"n_peaks must be between 1 and {MAX_PEAKS}; got {n_peaks}.")

    peak_shape = str(request.peak_shape or "").strip().lower()
    if peak_shape not in PEAK_SHAPES:
        raise DeconvolutionValidationError(
            f"peak_shape must be one of {', '.join(PEAK_SHAPES)}; got {request.peak_shape!r}."
        )

    axis, values = _select_signal(resolved, basis)
    # Signal semantics belong to the *selected* basis: the imported raw curve
    # and a converted working signal (e.g. %T -> absorbance) do not share a
    # role or a unit, and a normalized curve carries no physical unit.
    descriptor = resolved.bases[basis]
    basis_signal_role = descriptor.signal_role
    basis_signal_unit = descriptor.signal_unit
    basis_dimensional = descriptor.dimensional_basis

    axis, values, selected_range = _apply_range(axis, values, request)
    if axis.size < MIN_USABLE_POINTS:
        raise DeconvolutionValidationError(
            f"At least {MIN_USABLE_POINTS} usable points are required; got {axis.size}."
        )

    domain_low = float(axis.min())
    domain_high = float(axis.max())
    initial_params = _coerce_initial_params(
        request, n_peaks=n_peaks, domain_low=domain_low, domain_high=domain_high
    )

    warnings: list[str] = []
    inversion_applied = bool(request.invert_signal_for_fit)
    fit_values = -values if inversion_applied else values

    estimate = auto_estimate_peaks(axis, fit_values, n_peaks)
    if not estimate["usable_positive_structure"]:
        if estimate["reason"] == "no_positive_structure":
            raise DeconvolutionValidationError(
                "The selected signal basis has no positive structure for non-negative peak components "
                "(amplitude is constrained to >= 0). Enable 'Invert signal for fitting' if the features of "
                "interest are negative-going, or choose a different signal basis. The signal is never "
                "modified automatically."
            )
        warnings.append(
            "automatic_estimate_no_detected_peaks: the automatic estimator found no peaks in the selected "
            "signal and distributed the component centers evenly. Supply initial guesses or choose a "
            "different basis if that spacing is not physically meaningful."
        )
    elif estimate["fallback_spacing_used"]:
        warnings.append(
            "automatic_estimate_partial_fallback: fewer peaks were detected than requested, so some component "
            "centers were spaced evenly across the axis. Review the initial guesses."
        )

    transmittance_warning = _transmittance_warning(
        resolved.analysis_type, basis_signal_role, inversion_applied=inversion_applied
    )
    if transmittance_warning:
        warnings.append(transmittance_warning)

    try:
        result = deconvolve_peaks(
            axis,
            fit_values,
            n_peaks=n_peaks,
            peak_shape=peak_shape,
            initial_params=initial_params or None,
        )
    except (ValueError, RuntimeError) as exc:
        # The run is allowed by policy; if the numerics genuinely fail we say so
        # and repeat any advisory guidance that explains the likely cause.
        guidance = f" {transmittance_warning}" if transmittance_warning else ""
        raise DeconvolutionValidationError(f"Peak fit failed: {exc}.{guidance}") from exc

    guess_sources = sorted(
        {str(entry.get("source") or "auto") for entry in result.get("initial_guesses") or []}
    )

    provenance = build_result_provenance(
        dataset=dataset,
        dataset_key=dataset_key,
        analysis_history=state.get("analysis_history") or [],
        app_version=app_version,
        analyst_name=analyst_name,
        extra={
            "analysis_scope": DECONVOLUTION_ANALYSIS_SCOPE,
            "dataset_key": dataset_key,
            "signal_basis": basis,
            "signal_basis_source": descriptor.source,
            "signal_role_provenance": descriptor.role_provenance,
            "signal_dimensional_basis": basis_dimensional,
            "fit_axis_role": resolved.axis_role,
            "fit_axis_unit": resolved.axis_unit,
            "fit_signal_role": basis_signal_role,
            "fit_signal_unit": basis_signal_unit,
            "selected_range": selected_range,
            "n_peaks": n_peaks,
            "peak_shape": peak_shape,
            "inversion_applied": inversion_applied,
            "initial_guess_sources": guess_sources,
            "preview_module": True,
        },
    )

    processing: dict[str, Any] = {
        "dataset_key": dataset_key,
        "signal_basis": basis,
        "signal_basis_source": descriptor.source,
        # Semantics of the *selected* basis, not of the dataset as a whole.
        "signal_role": basis_signal_role,
        "signal_unit": basis_signal_unit,
        "signal_dimensional_basis": basis_dimensional,
        "signal_role_provenance": descriptor.role_provenance,
        "axis_role": resolved.axis_role,
        "axis_unit": resolved.axis_unit,
        "selected_range": selected_range,
        "n_peaks": n_peaks,
        "peak_shape": peak_shape,
        "inversion_applied": inversion_applied,
        "inversion_semantics": (
            "the selected signal was multiplied by -1 before fitting at explicit user request"
            if inversion_applied
            else "the selected signal was fitted exactly as stored (no sign change)"
        ),
        "initial_guesses": result.get("initial_guesses") or [],
        "initial_guess_provenance": guess_sources,
        "auto_estimate": {
            "detected_peak_count": estimate["detected_peak_count"],
            "prominence_threshold": estimate["prominence_threshold"],
            "fallback_spacing_used": estimate["fallback_spacing_used"],
            "positive_point_fraction": estimate["positive_point_fraction"],
            "amplitude_semantics": estimate.get("amplitude_semantics"),
            "estimate_method": estimate.get("estimate_method"),
            "shape_area_factor": estimate.get("shape_area_factor"),
        },
        "fit_engine": "lmfit",
        "component_parameter_semantics": (
            "lmfit amplitude is an integrated area parameter, not a peak height; "
            "fwhm and height are reported separately when lmfit derives them"
        ),
        "preview_module": True,
    }

    validation = {
        "status": "warn" if warnings else "pass",
        "warnings": warnings,
        "issues": [],
    }

    x_label = build_axis_title(
        resolved.analysis_type, "x", detected_unit=resolved.axis_unit, axis_role=resolved.axis_role
    )
    y_label = build_axis_title(
        resolved.analysis_type, "y", detected_unit=basis_signal_unit, signal_kind=basis_signal_role
    )
    if basis != "raw":
        y_label = f"{y_label} [{basis}]"
    if inversion_applied:
        y_label = f"{y_label} (negated for fit)"

    report_payload = {
        "signal_basis": basis,
        "inversion_applied": inversion_applied,
        "x": _json_series(axis),
        "y": _json_series(fit_values),
        "fitted": _json_series(result.get("fitted")),
        "components": [_json_series(component) for component in result.get("components") or []],
        "residual": _json_series(result.get("residual")),
        "xlabel": x_label,
        "ylabel": y_label,
        "axis_role": resolved.axis_role,
        "axis_unit": resolved.axis_unit,
        "signal_role": basis_signal_role,
        "signal_unit": basis_signal_unit,
        "signal_dimensional_basis": basis_dimensional,
        "selected_range": selected_range,
        "peak_count": n_peaks,
        "peak_shape": peak_shape,
    }

    record = serialize_deconvolution_result(
        dataset_key,
        dataset,
        result,
        peak_shape,
        processing=processing,
        provenance=provenance,
        validation=validation,
        review={"commercial_scope": DECONVOLUTION_ANALYSIS_SCOPE},
        report_payload=report_payload,
    )

    results_map = state.setdefault("results", {})
    result_id = unique_dataset_key(results_map, f"deconv_{dataset_key}")
    record["id"] = result_id
    record["metadata"] = {
        **(record.get("metadata") or {}),
        "dataset_key": dataset_key,
        "data_type": analysis_type,
        "signal_basis": basis,
        "preview_module": True,
    }
    results_map[result_id] = record

    add_history_event(
        state,
        action="Peak Deconvolution",
        details=(
            f"{n_peaks}-component {peak_shape} fit on {basis} signal of '{dataset_key}'; "
            f"result '{result_id}' saved."
        ),
        page="Deconvolution",
        dataset_key=dataset_key,
        result_id=result_id,
    )

    return {
        "result_id": result_id,
        "record": record,
        "analysis_type": record.get("analysis_type"),
        "signal_basis": basis,
        "axis_role": resolved.axis_role,
        "axis_unit": resolved.axis_unit,
        "signal_role": basis_signal_role,
        "signal_unit": basis_signal_unit,
        "signal_dimensional_basis": basis_dimensional,
        "inversion_applied": inversion_applied,
        "warnings": warnings,
        "validation": validation,
        "provenance": provenance,
    }


def describe_options(resolved: ResolvedAnalysisState) -> dict[str, Any]:
    """Describe selectable bases, effective axis semantics and domain for the UI.

    This is the read-only companion to the run endpoint: the Dash page needs
    the effective axis/unit labels, the axis domain, and *why* a basis is
    unavailable before it can offer an honest workflow.  Each basis also
    carries its own signal role/unit so the page can label the selection
    honestly instead of assuming the dataset has one signal semantics.
    """
    x_label = build_axis_title(
        resolved.analysis_type, "x", detected_unit=resolved.axis_unit, axis_role=resolved.axis_role
    )
    y_label = build_axis_title(
        resolved.analysis_type, "y", detected_unit=resolved.signal_unit, signal_kind=resolved.signal_role
    )

    axis = np.asarray(resolved.axis, dtype=float)
    finite_axis = axis[np.isfinite(axis)] if axis.size else axis
    axis_domain = (
        [float(finite_axis.min()), float(finite_axis.max())] if finite_axis.size else []
    )

    return {
        "dataset_key": resolved.dataset_key,
        "analysis_type": resolved.analysis_type,
        "has_analysis_state": resolved.has_analysis_state,
        "axis_role": resolved.axis_role,
        "axis_unit": resolved.axis_unit,
        "signal_role": resolved.signal_role,
        "signal_unit": resolved.signal_unit,
        "x_label": x_label,
        "y_label": y_label,
        "axis_domain": axis_domain,
        "sample_count": int(finite_axis.size),
        "bases": [
            {
                "name": info.name,
                "available": info.available,
                "source": info.source,
                "reason": info.reason,
                "length": info.length,
                "signal_role": info.signal_role,
                "signal_unit": info.signal_unit,
                "dimensional_basis": info.dimensional_basis,
                "role_provenance": info.role_provenance,
                # Rendered with the backend's own axis-title rules so the UI
                # labels the selected basis, not the dataset as a whole.
                "signal_label": (
                    build_axis_title(
                        resolved.analysis_type,
                        "y",
                        detected_unit=info.signal_unit,
                        signal_kind=info.signal_role,
                    )
                    + (" [normalized]" if info.dimensional_basis == "normalized" else "")
                    if info.available
                    else None
                ),
            }
            for info in resolved.bases.values()
        ],
    }
