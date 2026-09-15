"""XRD scientific-depth primitives (Phase 2 / PR-19).

Pure helpers for Scherrer crystallite-size estimation on detected XRD peaks.
Every quantity either carries explicit provenance (wavelength, shape factor,
FWHM definition/units, theta vs 2theta handling, instrumental-broadening
correction status) or is withheld with an explicit reason.

Honesty contract
----------------
- Scherrer requires a declared radiation wavelength. When it is missing the
  whole analysis is withheld; no default wavelength is ever assumed.
- FWHM is measured on the baseline-corrected signal at half prominence via
  ``scipy.signal.peak_widths(rel_height=0.5)``; fractional crossing indices are
  interpolated onto the measured axis.
- The Scherrer equation is evaluated on the 2theta scale:
  ``D = K * lambda / (beta * cos(theta))`` with ``theta = two_theta / 2`` and
  ``beta`` the FWHM in *radians of 2theta*.
- For patterns recorded on a d-spacing axis, the FWHM bounds are converted to
  the 2theta scale exactly via ``2*arcsin(lambda / (2*d))`` evaluated at each
  half-height crossing (no small-angle approximation).
- Instrumental broadening is only subtracted when an instrumental FWHM is
  explicitly declared (quadrature subtraction). Otherwise the assumptions
  record ``instrumental_broadening_status == "not_corrected"`` so the size is
  explicitly a lower-bound estimate biased low.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np
from scipy.signal import peak_widths

SCHERRER_DEFAULT_SHAPE_FACTOR = 0.9
SCHERRER_FWHM_REL_HEIGHT = 0.5
SCHERRER_FWHM_DEFINITION = (
    "full width at half prominence via scipy.signal.peak_widths "
    "(rel_height=0.5) on the baseline-corrected intensity"
)
SCHERRER_THETA_CONVENTION = (
    "theta = two_theta / 2 inside cos(theta); beta is the peak FWHM on the "
    "2theta scale expressed in radians"
)


def _coerce_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def scherrer_crystallite_size_nm(
    *,
    two_theta_deg: float,
    fwhm_two_theta_deg: float,
    wavelength_angstrom: float,
    shape_factor: float = SCHERRER_DEFAULT_SHAPE_FACTOR,
) -> float | None:
    """Evaluate ``D = K * lambda / (beta * cos(theta))`` and return nm.

    ``two_theta_deg`` and ``fwhm_two_theta_deg`` are on the 2theta scale in
    degrees; ``wavelength_angstrom`` is the radiation wavelength in angstrom;
    ``shape_factor`` is the Scherrer constant K. Returns ``None`` when any
    input is non-finite, non-positive, or outside the domain where the
    equation is meaningful (beta must be a positive sub-radian width and
    cos(theta) must be positive).
    """
    tt = _coerce_optional_float(two_theta_deg)
    beta_deg = _coerce_optional_float(fwhm_two_theta_deg)
    wavelength = _coerce_optional_float(wavelength_angstrom)
    k = _coerce_optional_float(shape_factor)
    if tt is None or beta_deg is None or wavelength is None or k is None:
        return None
    if tt <= 0.0 or tt >= 180.0 or beta_deg <= 0.0 or beta_deg >= 180.0:
        return None
    if wavelength <= 0.0 or k <= 0.0:
        return None
    theta_rad = math.radians(tt / 2.0)
    cos_theta = math.cos(theta_rad)
    if cos_theta <= 0.0:
        return None
    beta_rad = math.radians(beta_deg)
    size_angstrom = (k * wavelength) / (beta_rad * cos_theta)
    if not math.isfinite(size_angstrom) or size_angstrom <= 0.0:
        return None
    return float(size_angstrom / 10.0)


def measure_fwhm_axis_bounds(
    axis: np.ndarray,
    signal: np.ndarray,
    peak_index: int,
    *,
    rel_height: float = SCHERRER_FWHM_REL_HEIGHT,
) -> dict[str, float] | None:
    """Measure the FWHM of one peak in axis units.

    Uses ``scipy.signal.peak_widths`` at ``rel_height`` (0.5 = half prominence,
    i.e. full width at half maximum above the estimated baseline) and
    interpolates the fractional crossing indices onto the measured axis so the
    returned width is in axis units, not samples.
    """
    axis = np.asarray(axis, dtype=float)
    signal = np.asarray(signal, dtype=float)
    if axis.size < 3 or signal.size != axis.size:
        return None
    if peak_index < 0 or peak_index >= signal.size:
        return None
    try:
        widths, heights, left_ips, right_ips = peak_widths(
            signal,
            [int(peak_index)],
            rel_height=float(rel_height),
        )
    except Exception:
        return None
    index_axis = np.arange(axis.size, dtype=float)
    left_axis = float(np.interp(float(left_ips[0]), index_axis, axis))
    right_axis = float(np.interp(float(right_ips[0]), index_axis, axis))
    fwhm_axis = right_axis - left_axis
    if not all(math.isfinite(v) for v in (left_axis, right_axis, fwhm_axis)):
        return None
    if fwhm_axis <= 0.0:
        return None
    return {
        "fwhm_axis": float(fwhm_axis),
        "left_axis": left_axis,
        "right_axis": right_axis,
        "half_height": float(heights[0]),
    }


def _d_spacing_to_two_theta(d_spacing: float, wavelength_angstrom: float) -> float | None:
    value = _coerce_optional_float(d_spacing)
    if value is None or value <= 0.0 or wavelength_angstrom <= 0.0:
        return None
    ratio = wavelength_angstrom / (2.0 * value)
    if ratio <= 0.0 or ratio >= 1.0:
        return None
    return float(math.degrees(2.0 * math.asin(ratio)))


def _fwhm_two_theta_deg(
    *,
    left_axis: float,
    right_axis: float,
    position: float,
    observed_space: str,
    wavelength_angstrom: float,
) -> tuple[float, float] | None:
    """Resolve (two_theta_deg, fwhm_deg_2theta) for one peak.

    For a two_theta axis the bounds are used directly. For a d-spacing axis
    each half-height crossing is converted exactly via Bragg's law; no
    linearized approximation is used.
    """
    if observed_space == "d_spacing":
        left_tt = _d_spacing_to_two_theta(left_axis, wavelength_angstrom)
        right_tt = _d_spacing_to_two_theta(right_axis, wavelength_angstrom)
        center_tt = _d_spacing_to_two_theta(position, wavelength_angstrom)
        if left_tt is None or right_tt is None or center_tt is None:
            return None
        # d-spacing decreases as 2theta increases, so left/right swap.
        fwhm = abs(right_tt - left_tt)
        if fwhm <= 0.0:
            return None
        return center_tt, float(fwhm)
    fwhm = right_axis - left_axis
    if fwhm <= 0.0:
        return None
    return float(position), float(fwhm)


def analyze_xrd_scherrer(
    *,
    axis: np.ndarray,
    corrected_signal: np.ndarray,
    peaks: list[Mapping[str, Any]],
    observed_space: str,
    wavelength_angstrom: float | None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run optional Scherrer crystallite-size estimation over detected peaks.

    Returns ``{"enabled", "status", "assumptions", "rows", "computed_count",
    "withheld_reason"}``. ``status`` is one of ``"disabled"``, ``"computed"``
    (at least one peak sized), or ``"withheld"`` (enabled but nothing could be
    computed, with ``withheld_reason`` set).
    """
    cfg = dict(config or {})
    enabled = bool(cfg.get("enabled", False))
    shape_factor = _coerce_optional_float(cfg.get("shape_factor"))
    if shape_factor is None or shape_factor <= 0.0:
        shape_factor = SCHERRER_DEFAULT_SHAPE_FACTOR
    instrumental_fwhm = _coerce_optional_float(cfg.get("instrumental_fwhm_deg"))
    if instrumental_fwhm is not None and instrumental_fwhm <= 0.0:
        instrumental_fwhm = None

    wavelength = _coerce_optional_float(wavelength_angstrom)
    if wavelength is not None and wavelength <= 0.0:
        wavelength = None

    correction = "quadrature_subtraction" if instrumental_fwhm is not None else "none"
    assumptions = {
        "method": "scherrer",
        "wavelength_angstrom": wavelength,
        "shape_factor_k": float(shape_factor),
        "fwhm_definition": SCHERRER_FWHM_DEFINITION,
        "fwhm_rel_height": SCHERRER_FWHM_REL_HEIGHT,
        "fwhm_units": "degree_2theta",
        "theta_convention": SCHERRER_THETA_CONVENTION,
        "observed_axis_space": str(observed_space or "two_theta"),
        "instrumental_broadening_correction": correction,
        "instrumental_fwhm_deg_2theta": instrumental_fwhm,
        "instrumental_broadening_status": "corrected" if instrumental_fwhm is not None else "not_corrected",
        "instrumental_broadening_caveat": (
            ""
            if instrumental_fwhm is not None
            else "Instrumental broadening was not corrected; reported sizes are biased low."
        ),
        "signal_basis": "baseline_corrected_intensity",
    }

    result = {
        "enabled": enabled,
        "status": "disabled",
        "assumptions": assumptions,
        "rows": [],
        "computed_count": 0,
        "withheld_reason": "",
        "resolved_config": {
            "enabled": enabled,
            "shape_factor": float(shape_factor),
            "instrumental_fwhm_deg": instrumental_fwhm,
        },
    }
    if not enabled:
        return result

    if wavelength is None:
        result["status"] = "withheld"
        result["withheld_reason"] = (
            "xrd_scherrer_requires_declared_wavelength"
        )
        return result
    if not peaks:
        result["status"] = "withheld"
        result["withheld_reason"] = "xrd_scherrer_no_detected_peaks"
        return result

    axis_arr = np.asarray(axis, dtype=float)
    signal_arr = np.asarray(corrected_signal, dtype=float)
    rows: list[dict[str, Any]] = []
    computed = 0
    for rank, peak in enumerate(peaks, start=1):
        position = _coerce_optional_float(peak.get("position"))
        row: dict[str, Any] = {
            "peak_rank": int(peak.get("rank") or rank),
            "position": position,
            "axis_space": str(observed_space or "two_theta"),
            "status": "withheld",
            "withheld_reason": "",
            "two_theta_deg": None,
            "fwhm_deg_2theta_observed": None,
            "fwhm_deg_2theta": None,
            "instrumental_fwhm_deg_2theta": instrumental_fwhm,
            "crystallite_size_nm": None,
        }
        if position is None:
            row["withheld_reason"] = "peak_position_missing"
            rows.append(row)
            continue
        peak_index = int(np.argmin(np.abs(axis_arr - position)))
        fwhm_bounds = measure_fwhm_axis_bounds(
            axis_arr,
            signal_arr,
            peak_index,
            rel_height=SCHERRER_FWHM_REL_HEIGHT,
        )
        if fwhm_bounds is None:
            row["withheld_reason"] = "fwhm_not_resolvable"
            rows.append(row)
            continue
        resolved = _fwhm_two_theta_deg(
            left_axis=fwhm_bounds["left_axis"],
            right_axis=fwhm_bounds["right_axis"],
            position=position,
            observed_space=str(observed_space or "two_theta"),
            wavelength_angstrom=wavelength,
        )
        if resolved is None:
            row["withheld_reason"] = "fwhm_not_convertible_to_two_theta"
            rows.append(row)
            continue
        two_theta_deg, fwhm_deg = resolved
        row["two_theta_deg"] = float(two_theta_deg)
        row["fwhm_deg_2theta_observed"] = float(fwhm_deg)

        beta_deg = fwhm_deg
        if instrumental_fwhm is not None:
            if instrumental_fwhm >= fwhm_deg:
                row["withheld_reason"] = "instrumental_fwhm_exceeds_observed_fwhm"
                rows.append(row)
                continue
            beta_deg = math.sqrt(fwhm_deg * fwhm_deg - instrumental_fwhm * instrumental_fwhm)
        row["fwhm_deg_2theta"] = float(beta_deg)

        size_nm = scherrer_crystallite_size_nm(
            two_theta_deg=two_theta_deg,
            fwhm_two_theta_deg=beta_deg,
            wavelength_angstrom=wavelength,
            shape_factor=shape_factor,
        )
        if size_nm is None:
            row["withheld_reason"] = "scherrer_size_undefined"
            rows.append(row)
            continue
        row["status"] = "computed"
        row["crystallite_size_nm"] = float(size_nm)
        computed += 1
        rows.append(row)

    result["rows"] = rows
    result["computed_count"] = computed
    if computed:
        result["status"] = "computed"
    else:
        result["status"] = "withheld"
        result["withheld_reason"] = "xrd_scherrer_no_peak_satisfied_requirements"
    return result


def scherrer_median_nm(rows: list[Mapping[str, Any]]) -> float | None:
    """Median crystallite size over computed rows (None when none computed)."""
    sizes = [
        float(row["crystallite_size_nm"])
        for row in rows
        if row.get("status") == "computed" and row.get("crystallite_size_nm") is not None
    ]
    if not sizes:
        return None
    return float(np.median(np.asarray(sizes, dtype=float)))
