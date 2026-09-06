"""Dimensional honesty for DSC heat-flow quantities (PR-9).

Converts heat-flow measurements into honest physical units — ΔCp in
J/(g·K) and peak enthalpy in J/g — but only when the provenance supports
it.  When it does not, the measured quantity is kept under a name that
describes what it actually is, together with a recorded reason.

Three rules shape this module.

1. **A unit *class* is not enough; the exact unit is required.**
   ``normalize_by_mass`` divides by *milligrams*, so one raw-power class
   yields two different working units:

   ==========  ==================  =============  ===============
   source      after normalize()   working unit   factor -> W/g
   ==========  ==================  =============  ===============
   ``mW``      ``mW / mg``         ``mW/mg``      1.0
   ``W``       ``W / mg``          ``W/mg``       1000.0
   ==========  ==================  =============  ===============

   Conversion therefore consumes an exact canonical unit, never a class.

2. **Mass is consumed in exactly one place.**  The conversion helpers take
   no ``sample_mass`` argument — only ``working_signal_unit``.  If raw
   power reaches conversion the result is withheld rather than divided
   again, so a double division is structurally impossible.

3. **Absence of provenance is never permission to assume.**  A missing
   heating rate, an unverified one, or an unusable unit yields a
   ``value`` of ``None`` and a non-null ``withheld_reason``.

Pure module: no I/O and no pipeline imports, mirroring
``core/sign_convention.py``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

__all__ = [
    "UnitClass",
    "Conversion",
    "SECONDS_PER_MINUTE",
    "UNIT_TO_W_PER_G",
    "RAW_POWER_TO_WORKING",
    "SPECIFIC_POWER_UNITS",
    "RAW_POWER_UNITS",
    "BASIS_BETA_CORRECTED",
    "BASIS_RAW_SIGNAL_STEP",
    "BASIS_TEMPERATURE_DOMAIN_AREA",
    "BASIS_LEGACY_UNKNOWN",
    "WITHHELD_LEGACY_UNKNOWN",
    "WITHHELD_HEATING_RATE_MISSING",
    "WITHHELD_HEATING_RATE_INVALID",
    "WITHHELD_HEATING_RATE_UNVERIFIED",
    "WITHHELD_SIGNAL_UNIT_UNUSABLE",
    "WITHHELD_SIGNAL_NOT_MASS_NORMALIZED",
    "canonical_signal_unit",
    "classify_signal_unit",
    "factor_to_w_per_g",
    "resolve_working_unit",
    "resolve_beta",
    "heat_flow_step_to_delta_cp",
    "peak_area_to_enthalpy",
    "area_units_label",
]

SECONDS_PER_MINUTE = 60.0

# Specific power units and their exact factor to W/g.
UNIT_TO_W_PER_G: Dict[str, float] = {
    "mW/mg": 1.0,      # 1e-3 W / 1e-3 g
    "W/g": 1.0,
    "W/mg": 1000.0,    # 1 W / 1e-3 g
    "mW/g": 1e-3,
}

# Raw power units and the working unit produced by normalize() (divide by mg).
RAW_POWER_TO_WORKING: Dict[str, str] = {
    "mW": "mW/mg",
    "W": "W/mg",
}

SPECIFIC_POWER_UNITS = frozenset(UNIT_TO_W_PER_G)
RAW_POWER_UNITS = frozenset(RAW_POWER_TO_WORKING)

BASIS_BETA_CORRECTED = "beta_corrected"
BASIS_RAW_SIGNAL_STEP = "raw_signal_step"
BASIS_TEMPERATURE_DOMAIN_AREA = "temperature_domain_area"
BASIS_LEGACY_UNKNOWN = "legacy_unknown"

WITHHELD_LEGACY_UNKNOWN = "legacy_unknown"
WITHHELD_HEATING_RATE_MISSING = "heating_rate_missing"
WITHHELD_HEATING_RATE_INVALID = "heating_rate_invalid"
WITHHELD_HEATING_RATE_UNVERIFIED = "heating_rate_unverified"
WITHHELD_SIGNAL_UNIT_UNUSABLE = "signal_unit_unusable"
WITHHELD_SIGNAL_NOT_MASS_NORMALIZED = "signal_not_mass_normalized"

# Longest first so "W/mg" and "mW/g" are not mis-hit by "W" or "mW".
_CANONICAL_TOKENS: Tuple[str, ...] = ("mW/mg", "W/mg", "mW/g", "W/g", "mW", "W")

_VERIFIED_BETA_SOURCES = frozenset({"user", "parsed"})


class UnitClass(str, Enum):
    """Coarse dimensional family of a signal unit."""

    SPECIFIC_POWER = "specific_power"
    RAW_POWER = "raw_power"
    UNUSABLE = "unusable"


@dataclass(frozen=True)
class Conversion:
    """Outcome of a dimensional conversion attempt.

    ``value`` is ``None`` whenever the conversion was withheld; in that
    case ``withheld_reason`` states why.  ``basis`` always names what the
    stored quantity actually is.
    """

    value: Optional[float]
    basis: str
    withheld_reason: Optional[str]
    beta_k_min: Optional[float] = None
    signal_unit: Optional[str] = None
    factor_to_w_per_g: Optional[float] = None

    @property
    def corrected(self) -> bool:
        """True only when ``value`` carries real J/(g·K) or J/g meaning."""
        return self.basis == BASIS_BETA_CORRECTED and self.value is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "basis": self.basis,
            "withheld_reason": self.withheld_reason,
            "beta_k_min": self.beta_k_min,
            "signal_unit": self.signal_unit,
            "factor_to_w_per_g": self.factor_to_w_per_g,
        }


def canonical_signal_unit(unit: Optional[str]) -> Tuple[str, UnitClass]:
    """Return the canonical unit token and its class.

    Matching is longest-token-first so ``W/mg`` and ``mW/g`` are not
    mis-hit by ``W`` or ``mW`` (unlike the insertion-order substring
    match in ``core.data_io._SIGNAL_UNIT_KEYWORDS``).
    """
    token = str(unit or "").strip()
    if not token:
        return "", UnitClass.UNUSABLE

    direct = {tok.lower(): tok for tok in _CANONICAL_TOKENS}
    lowered = token.lower()
    if lowered in direct:
        resolved = direct[lowered]
    else:
        # Substring matching only for compound units: a bare "W" would
        # otherwise match any token containing the letter w ("unknown").
        resolved = ""
        for candidate in _CANONICAL_TOKENS:
            if "/" in candidate and candidate.lower() in lowered:
                resolved = candidate
                break

    if not resolved:
        return token, UnitClass.UNUSABLE
    if resolved in UNIT_TO_W_PER_G:
        return resolved, UnitClass.SPECIFIC_POWER
    return resolved, UnitClass.RAW_POWER


def classify_signal_unit(unit: Optional[str]) -> UnitClass:
    """Return only the coarse class of ``unit``."""
    return canonical_signal_unit(unit)[1]


def factor_to_w_per_g(unit: Optional[str]) -> Optional[float]:
    """Exact multiplicative factor from ``unit`` to W/g, or ``None``."""
    resolved, unit_class = canonical_signal_unit(unit)
    if unit_class is not UnitClass.SPECIFIC_POWER:
        return None
    return UNIT_TO_W_PER_G[resolved]


def resolve_working_unit(
    source_unit: Optional[str],
    sample_mass_mg: Optional[float],
    normalize_requested: bool,
    *,
    working_unit: Optional[str] = None,
    normalization_applied: bool = False,
) -> Tuple[str, bool, Optional[str]]:
    """Decide the working unit for a normalization step.

    Reads the *current* ``working_unit`` / ``normalization_applied`` so a
    second ``normalize()`` is a structural no-op rather than an incident.

    Returns ``(working_unit, normalization_applied, reason)`` where
    ``reason`` is ``None`` on success and otherwise names why the signal
    stays as it is.
    """
    resolved_source, unit_class = canonical_signal_unit(source_unit)

    if unit_class is UnitClass.SPECIFIC_POWER:
        return resolved_source, False, "already_specific_power"

    if unit_class is UnitClass.UNUSABLE:
        return (working_unit or resolved_source), False, WITHHELD_SIGNAL_UNIT_UNUSABLE

    # Raw power from here on.
    if normalization_applied:
        # Already divided by mass once; a second division is never correct.
        # ``applied`` is False so the caller performs no further division.
        return (working_unit or resolved_source), False, "already_normalized"

    if not normalize_requested:
        return resolved_source, False, "normalization_not_requested"

    if sample_mass_mg is None:
        return resolved_source, False, "sample_mass_missing"

    try:
        mass = float(sample_mass_mg)
    except (TypeError, ValueError):
        return resolved_source, False, "sample_mass_invalid"

    if not math.isfinite(mass) or mass <= 0.0:
        return resolved_source, False, "sample_mass_invalid"

    return RAW_POWER_TO_WORKING[resolved_source], True, None


def resolve_beta(
    heating_rate: Optional[float],
    heating_rate_source: Optional[str],
) -> Tuple[Optional[float], Optional[str]]:
    """Validate a heating rate and return ``(beta, withheld_reason)``.

    A heating rate is usable only when present, finite, positive, and
    traceable to ``user`` or ``parsed`` provenance.  A missing or
    unrecognized source is treated as ``legacy_unknown`` and withheld.
    """
    if heating_rate is None:
        return None, WITHHELD_HEATING_RATE_MISSING

    normalized_source = str(heating_rate_source or "").strip().lower()
    if normalized_source == "legacy_unknown":
        return None, WITHHELD_HEATING_RATE_UNVERIFIED
    if normalized_source and normalized_source not in _VERIFIED_BETA_SOURCES:
        return None, WITHHELD_HEATING_RATE_UNVERIFIED
    if not normalized_source:
        # Absent provenance is legacy: never trust the value.
        return None, WITHHELD_LEGACY_UNKNOWN

    try:
        beta = float(heating_rate)
    except (TypeError, ValueError):
        return None, WITHHELD_HEATING_RATE_INVALID

    if not math.isfinite(beta) or beta <= 0.0:
        return None, WITHHELD_HEATING_RATE_INVALID

    return beta, None


def _specific_power(
    working_signal_unit: Optional[str],
) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """Return ``(factor, canonical_unit, withheld_reason)`` for a working unit."""
    resolved, unit_class = canonical_signal_unit(working_signal_unit)

    if unit_class is UnitClass.UNUSABLE:
        return None, resolved or None, WITHHELD_SIGNAL_UNIT_UNUSABLE
    if unit_class is UnitClass.RAW_POWER:
        return None, resolved, WITHHELD_SIGNAL_NOT_MASS_NORMALIZED

    factor = UNIT_TO_W_PER_G[resolved]
    if not math.isfinite(factor):
        return None, resolved, WITHHELD_SIGNAL_UNIT_UNUSABLE
    return factor, resolved, None


def heat_flow_step_to_delta_cp(
    step: Optional[float],
    *,
    working_signal_unit: Optional[str],
    beta_k_min: Optional[float],
) -> Conversion:
    """Convert a heat-flow step to ΔCp in J/(g·K).

    ``ΔCp = step[W/g] × 60 / β``.  Takes no mass: ``working_signal_unit``
    must already be specific power.
    """
    factor, resolved_unit, unit_reason = _specific_power(working_signal_unit)
    basis = BASIS_RAW_SIGNAL_STEP

    if unit_reason is not None:
        return Conversion(
            value=None,
            basis=BASIS_LEGACY_UNKNOWN if not resolved_unit else basis,
            withheld_reason=unit_reason,
            beta_k_min=beta_k_min,
            signal_unit=resolved_unit,
            factor_to_w_per_g=factor,
        )

    beta, beta_reason = resolve_beta(beta_k_min, "user")
    if beta_reason is not None:
        return Conversion(
            value=None,
            basis=basis,
            withheld_reason=beta_reason,
            beta_k_min=beta_k_min,
            signal_unit=resolved_unit,
            factor_to_w_per_g=factor,
        )

    if step is None:
        return Conversion(
            value=None,
            basis=basis,
            withheld_reason="step_missing",
            beta_k_min=beta,
            signal_unit=resolved_unit,
            factor_to_w_per_g=factor,
        )

    try:
        magnitude = float(step)
    except (TypeError, ValueError):
        return Conversion(
            value=None,
            basis=basis,
            withheld_reason="step_invalid",
            beta_k_min=beta,
            signal_unit=resolved_unit,
            factor_to_w_per_g=factor,
        )

    if not math.isfinite(magnitude):
        return Conversion(
            value=None,
            basis=basis,
            withheld_reason="step_invalid",
            beta_k_min=beta,
            signal_unit=resolved_unit,
            factor_to_w_per_g=factor,
        )

    return Conversion(
        value=magnitude * factor * SECONDS_PER_MINUTE / beta,
        basis=BASIS_BETA_CORRECTED,
        withheld_reason=None,
        beta_k_min=beta,
        signal_unit=resolved_unit,
        factor_to_w_per_g=factor,
    )


def peak_area_to_enthalpy(
    area: Optional[float],
    *,
    working_signal_unit: Optional[str],
    beta_k_min: Optional[float],
) -> Conversion:
    """Convert a temperature-domain peak area to enthalpy in J/g.

    ``ΔH = area[W·K/g] × 60 / β``.  Takes no mass: ``working_signal_unit``
    must already be specific power.
    """
    factor, resolved_unit, unit_reason = _specific_power(working_signal_unit)
    basis = BASIS_TEMPERATURE_DOMAIN_AREA

    if unit_reason is not None:
        return Conversion(
            value=None,
            basis=BASIS_LEGACY_UNKNOWN if not resolved_unit else basis,
            withheld_reason=unit_reason,
            beta_k_min=beta_k_min,
            signal_unit=resolved_unit,
            factor_to_w_per_g=factor,
        )

    beta, beta_reason = resolve_beta(beta_k_min, "user")
    if beta_reason is not None:
        return Conversion(
            value=None,
            basis=basis,
            withheld_reason=beta_reason,
            beta_k_min=beta_k_min,
            signal_unit=resolved_unit,
            factor_to_w_per_g=factor,
        )

    if area is None:
        return Conversion(
            value=None,
            basis=basis,
            withheld_reason="area_missing",
            beta_k_min=beta,
            signal_unit=resolved_unit,
            factor_to_w_per_g=factor,
        )

    try:
        magnitude = float(area)
    except (TypeError, ValueError):
        return Conversion(
            value=None,
            basis=basis,
            withheld_reason="area_invalid",
            beta_k_min=beta,
            signal_unit=resolved_unit,
            factor_to_w_per_g=factor,
        )

    if not math.isfinite(magnitude):
        return Conversion(
            value=None,
            basis=basis,
            withheld_reason="area_invalid",
            beta_k_min=beta,
            signal_unit=resolved_unit,
            factor_to_w_per_g=factor,
        )

    return Conversion(
        value=magnitude * factor * SECONDS_PER_MINUTE / beta,
        basis=BASIS_BETA_CORRECTED,
        withheld_reason=None,
        beta_k_min=beta,
        signal_unit=resolved_unit,
        factor_to_w_per_g=factor,
    )


def area_units_label(working_signal_unit: Optional[str]) -> str:
    """Label for a temperature-domain area: working signal unit × K."""
    resolved, unit_class = canonical_signal_unit(working_signal_unit)
    if unit_class is UnitClass.UNUSABLE or not resolved:
        return "unknown units·K"
    return f"{resolved}·K"


def delta_cp_display(
    delta_cp_j_g_k: Optional[float],
    heat_flow_step: Optional[float],
    basis: Optional[str],
    working_signal_unit: Optional[str],
) -> Tuple[str, Optional[float]]:
    """Return ``(label, value)`` for a ΔCp display.

    A corrected value is labelled J/(g·K); anything else is labelled as
    the step height it actually is.  A legacy result never receives a
    J/(g·K) label.
    """
    resolved_basis = str(basis or BASIS_LEGACY_UNKNOWN)
    if resolved_basis == BASIS_BETA_CORRECTED and delta_cp_j_g_k is not None:
        return "ΔCp (J/(g·K))", delta_cp_j_g_k
    if resolved_basis == BASIS_LEGACY_UNKNOWN:
        return "ΔCp (unknown basis — legacy result)", None

    resolved_unit, unit_class = canonical_signal_unit(working_signal_unit)
    unit = resolved_unit if unit_class is not UnitClass.UNUSABLE else "signal units"
    return f"Step height ({unit})", heat_flow_step


def enthalpy_display(
    enthalpy_j_g: Optional[float],
    area: Optional[float],
    basis: Optional[str],
    working_signal_unit: Optional[str],
) -> Tuple[str, Optional[float]]:
    """Return ``(label, value)`` for a peak-area / enthalpy display.

    Only a β-corrected value is labelled J/g; otherwise the
    temperature-domain area is shown with its real units.
    """
    resolved_basis = str(basis or BASIS_LEGACY_UNKNOWN)
    if resolved_basis == BASIS_BETA_CORRECTED and enthalpy_j_g is not None:
        return "Enthalpy (J/g)", enthalpy_j_g
    if resolved_basis == BASIS_LEGACY_UNKNOWN:
        return f"Area ({area_units_label(working_signal_unit)}, legacy)", area
    return f"Area ({area_units_label(working_signal_unit)})", area
