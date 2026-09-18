"""Single resolver for a workspace dataset's effective analysis state.

Both ``analysis_state_curves`` and the preview deconvolution module need the
same reading of a saved modality analysis state: which axis array is
effective, which unit and role it carries, which signal bases are actually
stored and — when a basis is missing — why.  Keeping that interpretation in
one place prevents a second, contradictory reading of the stored arrays.

The resolver is deliberately permissive: it reports what exists.  Callers
decide what to do about a missing basis (the HTTP endpoint keeps its empty
response for datasets without a saved analysis; deconvolution blocks without
silently falling back to raw).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from core.modalities import analysis_state_key


# Signal bases a caller may request by name.  ``baseline`` and the DTG
# derivatives are reported as series but are not selectable fitting bases.
BASIS_NAMES: tuple[str, ...] = ("raw", "smoothed", "corrected", "normalized")


@dataclass(frozen=True)
class SignalBasisAvailability:
    """Whether one signal basis can be used, and why not when it cannot."""

    name: str
    available: bool
    source: str | None
    reason: str | None
    length: int


@dataclass(frozen=True)
class ResolvedAnalysisState:
    """Effective axis, units, roles and stored series for one dataset."""

    dataset_key: str
    analysis_type: str
    dataset: Any
    has_analysis_state: bool
    axis: list[float]
    axis_role: str | None
    axis_unit: str | None
    signal_role: str | None
    signal_unit: str | None
    series: dict[str, list[float]]
    bases: dict[str, SignalBasisAvailability]
    peaks: list[dict[str, Any]]
    diagnostics: dict[str, Any]
    processing: dict[str, Any]

    def series_for_basis(self, basis: str) -> list[float]:
        """Return the stored series for a selectable basis name."""
        return series_for_basis(self.series, basis)


def _to_list(values: Any) -> list[float]:
    """Convert a stored array to a list, mapping non-finite entries to None."""
    if values is None:
        return []
    array = np.asarray(values, dtype=float)
    array = np.where(np.isfinite(array), array, None)
    return array.tolist()


def _raw_axis_and_signal(dataset: Any) -> tuple[list[float], list[float]]:
    """Return the imported dataset's finite, sorted, deduplicated raw curve."""
    frame = getattr(dataset, "data", None)
    if frame is None or "temperature" not in frame.columns or "signal" not in frame.columns:
        return [], []

    raw_axis = np.asarray(frame["temperature"], dtype=float)
    raw_values = np.asarray(frame["signal"], dtype=float)
    finite_mask = np.isfinite(raw_axis) & np.isfinite(raw_values)
    raw_axis = raw_axis[finite_mask]
    raw_values = raw_values[finite_mask]
    if not raw_axis.size:
        return [], []

    order = np.argsort(raw_axis)
    raw_axis = raw_axis[order]
    raw_values = raw_values[order]
    unique_axis, unique_idx = np.unique(raw_axis, return_index=True)
    return unique_axis.tolist(), raw_values[unique_idx].tolist()


def _peak_to_dict(peak: Any) -> dict[str, Any]:
    if isinstance(peak, dict):
        return peak
    if hasattr(peak, "__dict__"):
        return vars(peak)
    if hasattr(peak, "_asdict"):
        return peak._asdict()
    return {}


def resolve_analysis_state(
    state: Mapping[str, Any] | None,
    analysis_type: str,
    dataset_key: str,
) -> ResolvedAnalysisState:
    """Resolve the effective axis, roles, units and stored bases for a dataset.

    Raises
    ------
    KeyError
        If the dataset is not present in the workspace state.
    ValueError
        If ``analysis_type`` is not a known stable modality.
    """
    workspace = state or {}
    datasets = workspace.get("datasets", {}) or {}
    dataset = datasets.get(dataset_key)
    if dataset is None:
        raise KeyError(dataset_key)

    # Raises ValueError for an unsupported analysis type.
    state_key = analysis_state_key(analysis_type, dataset_key)
    stored = workspace.get(state_key)
    has_analysis_state = isinstance(stored, Mapping)
    analysis_state: Mapping[str, Any] = stored if has_analysis_state else {}

    axis, raw_signal = _raw_axis_and_signal(dataset)
    # ``raw`` comes from the imported dataset itself; record why it cannot be
    # used when it is empty or no longer aligned with the effective axis.
    raw_reason: str | None = None if raw_signal else "no_usable_samples"
    state_axis = _to_list(analysis_state.get("axis"))
    if state_axis:
        axis = state_axis
        if raw_signal and len(raw_signal) != len(axis):
            raw_signal = []
            raw_reason = "raw_signal_not_aligned_with_effective_axis"

    diagnostics = analysis_state.get("diagnostics") or {}
    # PR-18: when the analysis axis was converted, raw samples (sorted on the
    # declared axis, often in the opposite order) cannot be paired with the
    # converted axis — report them as unavailable rather than misplacing them.
    if (diagnostics.get("axis_conversion") or {}).get("basis") == "converted":
        raw_signal = []
        raw_reason = "raw_signal_not_aligned_with_effective_axis"

    series = {
        "raw_signal": raw_signal,
        "smoothed": _to_list(analysis_state.get("smoothed")),
        "baseline": _to_list(analysis_state.get("baseline")),
        "corrected": _to_list(analysis_state.get("corrected")),
        "normalized": _to_list(analysis_state.get("normalized")),
        "dtg": _to_list(analysis_state.get("dtg")),
        "dtg_per_min": _to_list(analysis_state.get("dtg_per_min")),
    }

    raw_peaks = analysis_state.get("peak_table") or analysis_state.get("peaks") or []
    if not isinstance(raw_peaks, list):
        raw_peaks = []
    peaks = [_peak_to_dict(peak) for peak in raw_peaks]

    processing = analysis_state.get("processing")
    if not isinstance(processing, Mapping):
        processing = {}
    method_context = processing.get("method_context")
    if not isinstance(method_context, Mapping):
        method_context = {}

    metadata = getattr(dataset, "metadata", {}) or {}
    units = getattr(dataset, "units", {}) or {}
    normalized_analysis_type = str(analysis_type or "").upper()

    x_unit = units.get("temperature")
    y_unit = units.get("signal")
    axis_role: str | None = None
    signal_role: str | None = None
    if normalized_analysis_type == "FTIR":
        # PR-18: after an axis or signal conversion the effective unit/role
        # come from the stored analysis state, not the declared import units.
        x_unit = analysis_state.get("axis_unit") or x_unit
        y_unit = analysis_state.get("signal_unit") or y_unit
        axis_role = str(
            analysis_state.get("axis_role")
            or metadata.get("spectral_axis_role")
            or "wavenumber"
        )
        signal_role = str(
            analysis_state.get("signal_role")
            or diagnostics.get("signal_role")
            or method_context.get("ftir_signal_role")
            or ""
        ).strip() or None
    elif normalized_analysis_type == "RAMAN":
        x_unit = analysis_state.get("axis_unit") or x_unit
        y_unit = analysis_state.get("signal_unit") or y_unit
        axis_role = str(
            analysis_state.get("axis_role")
            or metadata.get("spectral_axis_role")
            or "raman_shift"
        )
        signal_role = str(
            analysis_state.get("signal_role")
            or diagnostics.get("signal_role")
            or method_context.get("raman_signal_role")
            or ""
        ).strip() or None
    elif normalized_analysis_type == "XRD":
        axis_role = str(
            method_context.get("xrd_axis_role")
            or metadata.get("xrd_axis_role")
            or "two_theta"
        )
        x_unit = (
            method_context.get("xrd_axis_unit")
            or metadata.get("xrd_axis_unit")
            or x_unit
        )
        signal_role = "intensity"
    elif normalized_analysis_type == "DSC":
        axis_role = "temperature"
        signal_role = "heat_flow"
    elif normalized_analysis_type == "TGA":
        axis_role = "temperature"
        signal_role = "mass"
    elif normalized_analysis_type == "DTA":
        axis_role = "temperature"
        signal_role = "delta_t"

    bases: dict[str, SignalBasisAvailability] = {}
    for name in BASIS_NAMES:
        if name == "raw" and raw_reason is not None:
            bases[name] = SignalBasisAvailability(
                name=name, available=False, source=None, reason=raw_reason, length=0
            )
            continue
        values = series_for_basis(series, name)
        if values:
            bases[name] = SignalBasisAvailability(
                name=name,
                available=True,
                source="dataset_import" if name == "raw" else "analysis_state",
                reason=None,
                length=len(values),
            )
        else:
            bases[name] = SignalBasisAvailability(
                name=name,
                available=False,
                source=None,
                reason="no_saved_analysis_state" if not has_analysis_state else f"no_saved_{name}_curve",
                length=0,
            )

    return ResolvedAnalysisState(
        dataset_key=dataset_key,
        analysis_type=normalized_analysis_type,
        dataset=dataset,
        has_analysis_state=has_analysis_state,
        axis=axis,
        axis_role=axis_role,
        axis_unit=str(x_unit) if x_unit not in (None, "") else None,
        signal_role=signal_role,
        signal_unit=str(y_unit) if y_unit not in (None, "") else None,
        series=series,
        bases=bases,
        peaks=peaks,
        diagnostics=dict(diagnostics),
        processing=dict(processing),
    )


def series_for_basis(series: Mapping[str, list[float]], basis: str) -> list[float]:
    """Map a selectable basis name onto its stored series key."""
    key = "raw_signal" if basis == "raw" else basis
    return list(series.get(key) or [])
