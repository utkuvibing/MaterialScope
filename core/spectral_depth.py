"""
spectral_depth.py
-----------------
PR-18 — FTIR / Raman scientific depth primitives.

Pure, side-effect-free helpers for:

  - transmittance -> absorbance conversion (A = -log10(T))
  - FTIR absolute wavelength <-> wavenumber conversion
  - Raman absolute wavelength <-> Raman shift conversion, gated on an
    explicitly declared excitation (laser) wavelength
  - region (band-area) integration over a declared axis window
  - annotated peak-table assembly for export

Honesty rules
-------------
  - Transmittance values <= 0 are undefined under -log10; they are clipped
    to the absorbance ceiling implied by the smallest positive measured
    transmittance and the clipped count is reported.  If no positive
    transmittance exists at all, the conversion is withheld.
  - Raman shift is NEVER derived from a scattered wavelength without an
    explicitly declared excitation wavelength — missing, non-finite, or
    non-positive laser wavelengths produce a withheld result, not a guess.
  - Region areas are trapezoid integrals over the supplied signal; regions
    containing fewer than two in-range samples are withheld with a reason.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Unit vocabulary
# ---------------------------------------------------------------------------

# Canonical axis-unit tokens understood by the conversion helpers.
WAVENUMBER_CM1 = "cm-1"          # spectroscopic wavenumber
WAVELENGTH_UM = "um"             # micrometres
WAVELENGTH_NM = "nm"             # nanometres
RAMAN_SHIFT_CM1 = "raman_shift_cm-1"

_FTIR_AXIS_UNITS = {WAVENUMBER_CM1, WAVELENGTH_UM, WAVELENGTH_NM}
_RAMAN_AXIS_UNITS = {RAMAN_SHIFT_CM1, WAVELENGTH_NM, WAVENUMBER_CM1}

# nm <-> cm-1 via ν̃[cm⁻¹] = 1e7 / λ[nm];  um <-> cm-1 via 1e4 / λ[um]
_NM_PER_CM_INV = 1.0e7
_UM_PER_CM_INV = 1.0e4


def normalize_spectral_axis_unit(unit: Any) -> str:
    """Normalize an axis-unit token to the canonical vocabulary."""
    token = str(unit or "").strip().lower().replace("⁻", "-").replace("−", "-")
    token = token.replace(" ", "").replace("_", "-")
    aliases = {
        "cm-1": WAVENUMBER_CM1,
        "cm^-1": WAVENUMBER_CM1,
        "1/cm": WAVENUMBER_CM1,
        "wavenumber": WAVENUMBER_CM1,
        "wavenumbers": WAVENUMBER_CM1,
        "um": WAVELENGTH_UM,
        "µm": WAVELENGTH_UM,
        "micron": WAVELENGTH_UM,
        "microns": WAVELENGTH_UM,
        "micrometer": WAVELENGTH_UM,
        "micrometre": WAVELENGTH_UM,
        "micrometers": WAVELENGTH_UM,
        "micrometres": WAVELENGTH_UM,
        "nm": WAVELENGTH_NM,
        "nanometer": WAVELENGTH_NM,
        "nanometre": WAVELENGTH_NM,
        "nanometers": WAVELENGTH_NM,
        "nanometres": WAVELENGTH_NM,
        "raman-shift": RAMAN_SHIFT_CM1,
        "ramanshift": RAMAN_SHIFT_CM1,
        "raman-shift-cm-1": RAMAN_SHIFT_CM1,
        "delta-cm-1": RAMAN_SHIFT_CM1,
    }
    return aliases.get(token, token)


# ---------------------------------------------------------------------------
# Transmittance -> absorbance
# ---------------------------------------------------------------------------

@dataclass
class AbsorbanceConversion:
    """Result of a transmittance -> absorbance conversion."""

    absorbance: Optional[np.ndarray]
    basis: str                      # 'converted' | 'withheld' | 'not_applicable'
    input_unit: str                 # '%T' | 'transmittance_fraction' | ''
    clipped_points: int = 0
    withheld_reason: Optional[str] = None


def transmittance_to_absorbance(
    signal: Iterable[float],
    *,
    signal_unit: Any,
) -> AbsorbanceConversion:
    """Convert a transmittance signal to absorbance via ``A = -log10(T)``.

    ``signal_unit`` distinguishes percent transmittance (``%T`` →
    ``T = signal/100``) from fractional transmittance (``0..1``).
    Absorbance is only defined for ``T > 0``; non-positive samples are
    clipped to the absorbance ceiling implied by the smallest positive
    transmittance in the signal (the instrument-saturation convention) and
    counted in ``clipped_points``.  When no positive transmittance exists
    the conversion is withheld — nothing is fabricated.
    """
    arr = np.asarray(list(signal), dtype=float)
    unit = str(signal_unit or "").strip().lower()
    if unit in {"%t", "percent_transmittance", "percent-t"}:
        fraction = arr / 100.0
        input_unit = "%T"
    elif unit in {"transmittance", "t", "fraction"}:
        fraction = arr
        input_unit = "transmittance_fraction"
    else:
        return AbsorbanceConversion(
            absorbance=None,
            basis="withheld",
            input_unit="",
            withheld_reason="signal_unit_not_transmittance",
        )

    if arr.size == 0 or not np.isfinite(arr).all():
        return AbsorbanceConversion(
            absorbance=None,
            basis="withheld",
            input_unit=input_unit,
            withheld_reason="signal_not_finite",
        )

    positive = fraction > 0.0
    if not positive.any():
        return AbsorbanceConversion(
            absorbance=None,
            basis="withheld",
            input_unit=input_unit,
            withheld_reason="no_positive_transmittance",
        )

    clipped = int(np.count_nonzero(~positive))
    clipped_fraction = np.where(positive, fraction, float(np.min(fraction[positive])))
    absorbance = -np.log10(clipped_fraction)
    return AbsorbanceConversion(
        absorbance=absorbance,
        basis="converted",
        input_unit=input_unit,
        clipped_points=clipped,
    )


# ---------------------------------------------------------------------------
# FTIR wavelength <-> wavenumber (absolute conversions, no extra metadata)
# ---------------------------------------------------------------------------

def wavelength_to_wavenumber(wavelength: Iterable[float], *, unit: Any) -> np.ndarray:
    """Convert absolute wavelength to spectroscopic wavenumber (cm⁻¹).

    ``unit`` must resolve to ``um`` or ``nm``.  Non-positive wavelengths
    produce ``nan`` — the caller decides whether the axis is usable.
    """
    arr = np.asarray(list(wavelength), dtype=float)
    canonical = normalize_spectral_axis_unit(unit)
    if canonical == WAVELENGTH_UM:
        factor = _UM_PER_CM_INV
    elif canonical == WAVELENGTH_NM:
        factor = _NM_PER_CM_INV
    else:
        raise ValueError(f"wavelength_to_wavenumber requires um/nm input, got {unit!r}")
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(arr > 0, factor / arr, np.nan)


def wavenumber_to_wavelength(wavenumber: Iterable[float], *, unit: Any) -> np.ndarray:
    """Convert spectroscopic wavenumber (cm⁻¹) to absolute wavelength.

    ``unit`` selects the output unit (``um`` or ``nm``).  Non-positive
    wavenumbers produce ``nan``.
    """
    arr = np.asarray(list(wavenumber), dtype=float)
    canonical = normalize_spectral_axis_unit(unit)
    if canonical == WAVELENGTH_UM:
        factor = _UM_PER_CM_INV
    elif canonical == WAVELENGTH_NM:
        factor = _NM_PER_CM_INV
    else:
        raise ValueError(f"wavenumber_to_wavelength requires um/nm output, got {unit!r}")
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(arr > 0, factor / arr, np.nan)


# ---------------------------------------------------------------------------
# Raman wavelength <-> Raman shift (excitation-gated)
# ---------------------------------------------------------------------------

def resolve_laser_wavelength_nm(
    declared: Any = None,
    metadata: Mapping[str, Any] | None = None,
) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """Resolve the Raman excitation wavelength to ``(nm, source, reason)``.

    Only an explicitly declared value is accepted — from the processing
    configuration (``source='user'``) or dataset metadata
    (``source='parsed'``).  A missing, non-finite, or non-positive value is
    withheld; the Raman shift is never estimated.
    """
    meta = metadata or {}
    value = declared if declared not in (None, "") else meta.get("laser_wavelength")
    source = "user" if declared not in (None, "") else ("parsed" if meta.get("laser_wavelength") not in (None, "") else None)
    if value in (None, ""):
        return None, None, "excitation_wavelength_missing"
    try:
        wl = float(value)
    except (TypeError, ValueError):
        return None, source, "excitation_wavelength_invalid"
    if not math.isfinite(wl) or wl <= 0.0:
        return None, source, "excitation_wavelength_invalid"
    # A plausible laser line is sub-nm to tens of µm; values stored in µm
    # (e.g. 0.785) are converted when the unit is declared accordingly.
    unit = normalize_spectral_axis_unit(
        meta.get("laser_wavelength_unit") or meta.get("excitation_wavelength_unit")
    )
    if unit == WAVELENGTH_UM:
        wl = wl * 1000.0
    return wl, source, None


def wavelength_to_raman_shift(
    scattered_wavelength_nm: Iterable[float],
    *,
    laser_wavelength_nm: float,
) -> np.ndarray:
    """Convert absolute scattered wavelength (nm) to Raman shift (cm⁻¹).

    ``Δν̃ = 1e7·(1/λ_laser − 1/λ_scattered)``.  The caller must have
    resolved ``laser_wavelength_nm`` through :func:`resolve_laser_wavelength_nm`.
    """
    arr = np.asarray(list(scattered_wavelength_nm), dtype=float)
    laser = float(laser_wavelength_nm)
    laser_wn = _NM_PER_CM_INV / laser
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(arr > 0, laser_wn - (_NM_PER_CM_INV / arr), np.nan)


def raman_shift_to_wavelength(
    shift_cm1: Iterable[float],
    *,
    laser_wavelength_nm: float,
) -> np.ndarray:
    """Convert Raman shift (cm⁻¹) back to absolute scattered wavelength (nm).

    ``λ_scattered = 1e7 / (ν̃_laser − Δν̃)``.  Shifts that reach or exceed
    the laser wavenumber (anti-Stokes beyond the line) produce ``nan``.
    """
    arr = np.asarray(list(shift_cm1), dtype=float)
    laser = float(laser_wavelength_nm)
    laser_wn = _NM_PER_CM_INV / laser
    scatter_wn = laser_wn - arr
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(scatter_wn > 0, _NM_PER_CM_INV / scatter_wn, np.nan)


# ---------------------------------------------------------------------------
# Axis conversion orchestration
# ---------------------------------------------------------------------------

@dataclass
class AxisConversion:
    """Outcome of a spectral-axis conversion request."""

    axis: Optional[np.ndarray]
    target_unit: str
    source_unit: str
    applied: bool = False
    basis: str = "not_requested"    # 'converted' | 'identity' | 'withheld' | 'not_requested'
    withheld_reason: Optional[str] = None
    laser_wavelength_nm: Optional[float] = None
    laser_wavelength_source: Optional[str] = None
    notes: list[str] = field(default_factory=list)


def convert_spectral_axis(
    axis: Iterable[float],
    *,
    analysis_type: str,
    source_unit: Any,
    target_unit: Any,
    laser_wavelength_nm: Any = None,
    dataset_metadata: Mapping[str, Any] | None = None,
    source_role: Any = None,
) -> AxisConversion:
    """Convert a spectral axis to a declared target unit.

    FTIR supports absolute wavelength (µm/nm) <-> wavenumber (cm⁻¹).
    RAMAN additionally supports scattered-wavelength (nm) <-> Raman shift
    (cm⁻¹), which is withheld unless an explicitly declared excitation
    wavelength resolves to a finite positive nm value.

    ``source_role`` carries the dataset-declared physical role of the source
    axis (``raman_shift`` / ``wavenumber`` / ``wavelength`` / ``ambiguous``)
    for the "from dataset" path.  A generic cm⁻¹ source declared as a Raman
    shift is converted through the excitation-gated shift path, never through
    the absolute wavenumber path; an ``ambiguous`` cm⁻¹ role withholds the
    conversion outright rather than silently choosing an interpretation.
    An explicit caller-selected source unit should pass ``source_role=None``
    — the explicit unit declaration stands on its own.

    A request whose source already equals the target is an honest
    ``identity`` no-op.  Unknown or physically impossible conversions are
    withheld with a reason — the axis is never silently transformed.
    """
    arr = np.asarray(list(axis), dtype=float)
    modality = str(analysis_type or "").strip().upper()
    src = normalize_spectral_axis_unit(source_unit)
    tgt = normalize_spectral_axis_unit(target_unit)

    result = AxisConversion(axis=None, target_unit=tgt, source_unit=src)

    if tgt in ("", "none", "asis", "as-is"):
        result.axis = arr.copy()
        result.basis = "identity"
        result.notes.append("no conversion requested")
        return result

    if src == tgt:
        result.axis = arr.copy()
        result.basis = "identity"
        result.target_unit = tgt or src
        result.notes.append("source axis already in target unit")
        return result

    if modality == "FTIR":
        if src == WAVENUMBER_CM1 and tgt in {WAVELENGTH_UM, WAVELENGTH_NM}:
            converted = wavenumber_to_wavelength(arr, unit=tgt)
        elif src in {WAVELENGTH_UM, WAVELENGTH_NM} and tgt == WAVENUMBER_CM1:
            converted = wavelength_to_wavenumber(arr, unit=src)
        else:
            result.basis = "withheld"
            result.withheld_reason = f"unsupported_axis_conversion:{src}->{tgt}"
            return result
    elif modality == "RAMAN":
        role = str(source_role or "").strip().lower()
        if src == WAVENUMBER_CM1 and role == "raman_shift":
            # The dataset declares the generic cm-1 axis as a Raman shift:
            # route it through the excitation-gated shift path, never the
            # absolute wavenumber path.
            src = RAMAN_SHIFT_CM1
            result.source_unit = src
        elif src == WAVENUMBER_CM1 and role not in {"", "wavenumber"}:
            # The cm-1 axis is declared as something other than an absolute
            # spectroscopic wavenumber — or its physical role is unresolved.
            # Withhold rather than silently select an interpretation.
            result.basis = "withheld"
            result.withheld_reason = "source_axis_role_ambiguous"
            return result
        if src == RAMAN_SHIFT_CM1 and tgt == WAVELENGTH_NM:
            laser, laser_src, reason = resolve_laser_wavelength_nm(
                laser_wavelength_nm, dataset_metadata
            )
            result.laser_wavelength_source = laser_src
            if laser is None:
                result.basis = "withheld"
                result.withheld_reason = reason
                return result
            result.laser_wavelength_nm = laser
            converted = raman_shift_to_wavelength(arr, laser_wavelength_nm=laser)
        elif src == WAVELENGTH_NM and tgt == RAMAN_SHIFT_CM1:
            laser, laser_src, reason = resolve_laser_wavelength_nm(
                laser_wavelength_nm, dataset_metadata
            )
            result.laser_wavelength_source = laser_src
            if laser is None:
                result.basis = "withheld"
                result.withheld_reason = reason
                return result
            result.laser_wavelength_nm = laser
            converted = wavelength_to_raman_shift(arr, laser_wavelength_nm=laser)
        elif src == WAVELENGTH_NM and tgt == WAVENUMBER_CM1:
            # Absolute scattered wavelength -> absolute wavenumber (not a
            # Raman shift); allowed and clearly distinct.
            converted = wavelength_to_wavenumber(arr, unit=WAVELENGTH_NM)
        elif src == WAVENUMBER_CM1 and tgt == WAVELENGTH_NM:
            converted = wavenumber_to_wavelength(arr, unit=WAVELENGTH_NM)
        else:
            result.basis = "withheld"
            result.withheld_reason = f"unsupported_axis_conversion:{src}->{tgt}"
            return result
    else:
        result.basis = "withheld"
        result.withheld_reason = f"axis_conversion_not_supported_for:{modality or 'unknown'}"
        return result

    finite = np.isfinite(converted)
    if not finite.all():
        dropped = int(np.count_nonzero(~finite))
        result.notes.append(f"{dropped} samples became non-finite after conversion")
    result.axis = converted
    result.applied = True
    result.basis = "converted"
    return result


# ---------------------------------------------------------------------------
# Region (band-area) integration
# ---------------------------------------------------------------------------

@dataclass
class RegionIntegral:
    """Trapezoid area of a signal over a declared axis region."""

    lo: float
    hi: float
    label: str = ""
    area: Optional[float] = None
    n_points: int = 0
    withheld_reason: Optional[str] = None


def integrate_region(
    axis: Iterable[float],
    signal: Iterable[float],
    lo: float,
    hi: float,
    *,
    label: str = "",
) -> RegionIntegral:
    """Trapezoid-integrate ``signal`` over ``[lo, hi]`` on ``axis``.

    Bounds are used verbatim after ordering; samples are linearly
    interpolated at the region edges so the integrated window matches the
    declared bounds rather than the nearest sampled points.  Regions with
    no interior samples are withheld.
    """
    x = np.asarray(list(axis), dtype=float)
    y = np.asarray(list(signal), dtype=float)
    a, b = float(lo), float(hi)
    if a > b:
        a, b = b, a
    out = RegionIntegral(lo=a, hi=b, label=label)
    if x.size < 2 or y.size != x.size:
        out.withheld_reason = "axis_or_signal_too_short"
        return out
    if not (np.isfinite(a) and np.isfinite(b)) or a == b:
        out.withheld_reason = "region_bounds_not_finite_or_empty"
        return out

    order = np.argsort(x)
    xs, ys = x[order], y[order]
    x_min, x_max = float(xs[0]), float(xs[-1])
    if b < x_min or a > x_max:
        out.withheld_reason = "region_outside_measured_range"
        return out

    a = max(a, x_min)
    b = min(b, x_max)
    mask = (xs > a) & (xs < b)
    xs_w = np.concatenate(([a], xs[mask], [b]))
    ys_w = np.concatenate(([np.interp(a, xs, ys)], ys[mask], [np.interp(b, xs, ys)]))
    finite = np.isfinite(ys_w)
    if np.count_nonzero(finite) < 2:
        out.withheld_reason = "region_has_insufficient_finite_samples"
        return out
    out.lo, out.hi = float(a), float(b)
    out.n_points = int(np.count_nonzero(finite))
    out.area = float(np.trapezoid(ys_w[finite], xs_w[finite]))
    return out


def integrate_regions(
    axis: Iterable[float],
    signal: Iterable[float],
    regions: Iterable[Mapping[str, Any]],
) -> list[RegionIntegral]:
    """Integrate a list of ``{lo, hi, label?}`` region dicts."""
    results: list[RegionIntegral] = []
    for item in regions or []:
        if not isinstance(item, Mapping):
            results.append(
                RegionIntegral(lo=float("nan"), hi=float("nan"), withheld_reason="region_not_a_mapping")
            )
            continue
        try:
            lo = float(item.get("lo"))
            hi = float(item.get("hi"))
        except (TypeError, ValueError):
            results.append(
                RegionIntegral(lo=float("nan"), hi=float("nan"), withheld_reason="region_bounds_not_finite_or_empty")
            )
            continue
        results.append(
            integrate_region(axis, signal, lo, hi, label=str(item.get("label") or ""))
        )
    return results


# ---------------------------------------------------------------------------
# Annotated peak table
# ---------------------------------------------------------------------------

def annotate_peak_table(
    peaks: Iterable[Mapping[str, Any]],
    *,
    axis_unit: Any,
    signal_basis: str,
    regions: Iterable[RegionIntegral] | None = None,
    analysis_type: str = "",
    axis_role: Any = None,
) -> list[dict[str, Any]]:
    """Annotate detected peaks with axis/signal provenance for export.

    Each row carries the raw detector values plus the effective axis unit and
    axis role, the signal basis the peak was detected on (e.g. ``corrected``,
    ``normalized``, ``absorbance_converted``), and the label of any declared
    integration region the peak falls inside.  No chemical assignments are
    invented — annotation is limited to what the analysis actually produced.
    """
    region_list = list(regions or [])
    rows: list[dict[str, Any]] = []
    for rank, peak in enumerate(peaks or [], start=1):
        position = peak.get("position")
        region_label = ""
        if position is not None:
            for region in region_list:
                if region.withheld_reason is None and region.lo <= float(position) <= region.hi:
                    region_label = region.label or f"{region.lo:g}-{region.hi:g}"
                    break
        rows.append(
            {
                "rank": int(peak.get("rank") or rank),
                "position": position,
                "axis_unit": str(axis_unit or ""),
                "axis_role": str(axis_role or ""),
                "intensity": peak.get("intensity"),
                "prominence": peak.get("prominence"),
                "signal_basis": signal_basis,
                "region": region_label,
                "analysis_type": str(analysis_type or "").upper(),
            }
        )
    return rows
