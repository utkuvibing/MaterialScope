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

Signal semantics are resolved **per basis**, not once per dataset.  An FTIR
dataset imported as %T whose saved analysis converted the working signal to
absorbance therefore reports ``raw`` as transmittance while
``smoothed``/``corrected`` are absorbance, and ``normalized`` keeps the useful
role without claiming a physical unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from core.batch_runner import infer_spectral_signal_context
from core.modalities import analysis_state_key


# Signal bases a caller may request by name.  ``baseline`` and the DTG
# derivatives are reported as series but are not selectable fitting bases.
BASIS_NAMES: tuple[str, ...] = ("raw", "smoothed", "corrected", "normalized")

# Modality-level raw-signal roles for non-FTIR datasets: a raw imported curve
# carries the modality's physical quantity rather than any derived semantics.
_RAW_MODALITY_ROLES: dict[str, str] = {
    "RAMAN": "intensity",
    "XRD": "intensity",
    "DSC": "heat_flow",
    "TGA": "mass",
    "DTA": "delta_t",
}


def _clean_unit(unit: Any) -> str | None:
    token = str(unit or "").strip()
    return token or None


@dataclass(frozen=True)
class SignalBasisDescriptor:
    """Whether one signal basis can be used, plus its own signal semantics.

    Signal semantics are **basis-specific**: the imported raw signal and a
    derived working signal (e.g. absorbance after a %T conversion) do not share
    a role or a unit, and a normalized curve must not claim the physical unit
    of the signal it was derived from.
    """

    name: str
    available: bool
    source: str | None
    reason: str | None
    length: int
    signal_role: str | None = None
    signal_unit: str | None = None
    # "physical" | "normalized" | "unknown"; None when the basis is unavailable.
    dimensional_basis: str | None = None
    role_provenance: str | None = None


# Backwards-compatible alias: the descriptor supersedes the availability-only view.
SignalBasisAvailability = SignalBasisDescriptor


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


def _raw_signal_semantics(dataset: Any, analysis_type: str) -> tuple[str | None, str | None, str | None]:
    """Resolve the *imported* dataset's signal unit, role and role provenance.

    The raw basis is the imported curve, so it must not inherit the saved
    analysis working-signal semantics: an FTIR dataset imported as %T stays
    transmittance even when the saved analysis converted the working signal to
    absorbance.  FTIR reuses the spectral pipeline's own inference (declared
    unit first, then an explicitly mapped column header), so a generic token
    such as ``a.u.`` leaves the role unresolved instead of claiming absorbance.
    """
    if analysis_type == "FTIR":
        unit, role, provenance = infer_spectral_signal_context(dataset)
        return _clean_unit(unit), (None if role == "unknown" else role), provenance

    declared = getattr(dataset, "units", {}).get("signal") or getattr(dataset, "metadata", {}).get(
        "inferred_signal_unit"
    )
    role = _RAW_MODALITY_ROLES.get(analysis_type)
    return _clean_unit(declared), role, ("modality_default" if role else "unresolved")


def _working_signal_unit(
    *,
    analysis_type: str,
    analysis_state: Mapping[str, Any],
    processing: Mapping[str, Any],
    declared_unit: str | None,
) -> str | None:
    """Resolve the effective unit of a saved *working* (smoothed/corrected) signal.

    Recorded processing semantics win over the imported unit: a DSC run that
    normalized by mass saved mW/mg curves, and a TGA run saves its working curve
    as mass-% even for an mg input.  Values are never re-derived from the
    numbers themselves.
    """
    explicit = _clean_unit(analysis_state.get("signal_unit"))
    if explicit:
        return explicit

    # TGAProcessor converts the working curve to mass-% before smoothing, so
    # every saved TGA working signal is mass-% regardless of the input unit.
    if analysis_type == "TGA":
        return "%"

    normalization = (processing.get("signal_pipeline") or {}).get("normalization") or {}
    working = _clean_unit(normalization.get("working_signal_unit"))
    if working:
        return working

    return declared_unit


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

    # Effective *saved-analysis* semantics.  These describe the working signal
    # (e.g. absorbance after a %T conversion on FTIR, mW/mg after a mass
    # normalization on DSC) and are what the analysis-state curves endpoint
    # reports.  The raw basis has its own.
    working_unit = _working_signal_unit(
        analysis_type=normalized_analysis_type,
        analysis_state=analysis_state,
        processing=processing,
        declared_unit=_clean_unit(y_unit),
    )
    working_role = signal_role
    raw_unit, raw_role, raw_role_provenance = _raw_signal_semantics(dataset, normalized_analysis_type)

    bases: dict[str, SignalBasisDescriptor] = {}
    for name in BASIS_NAMES:
        if name == "raw" and raw_reason is not None:
            bases[name] = SignalBasisDescriptor(
                name=name, available=False, source=None, reason=raw_reason, length=0
            )
            continue
        values = series_for_basis(series, name)
        if not values:
            bases[name] = SignalBasisDescriptor(
                name=name,
                available=False,
                source=None,
                reason="no_saved_analysis_state" if not has_analysis_state else f"no_saved_{name}_curve",
                length=0,
            )
            continue

        if name == "raw":
            role, unit, role_provenance = raw_role, raw_unit, raw_role_provenance
            dimensional_basis = "physical" if unit else "unknown"
        elif name == "normalized":
            # A normalized curve keeps the useful semantic role but must not
            # claim the physical unit of the signal it was derived from.
            role, unit, role_provenance = working_role, None, "analysis_state"
            dimensional_basis = "normalized"
        else:
            role, unit, role_provenance = working_role, working_unit, "analysis_state"
            dimensional_basis = "physical" if unit else "unknown"

        bases[name] = SignalBasisDescriptor(
            name=name,
            available=True,
            source="dataset_import" if name == "raw" else "analysis_state",
            reason=None,
            length=len(values),
            signal_role=role,
            signal_unit=unit,
            dimensional_basis=dimensional_basis,
            role_provenance=role_provenance,
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
