"""Modality-first import contracts for thermal and spectral analysis.

Each modality defines the expected axis roles, units, column-name aliases,
suspicious combinations, and metadata requirements so that the import pipeline
can operate deterministically when the user selects a technique up-front.
"""

from __future__ import annotations

from typing import Any


def _spec(
    *,
    label: str,
    axis_label: str,
    axis_role: str,
    signal_label: str,
    signal_role: str,
    allowed_x_units: tuple[str, ...],
    allowed_y_units: tuple[str, ...],
    default_x_unit: str,
    default_y_unit: str,
    x_aliases: tuple[str, ...],
    y_aliases: tuple[str, ...],
    required_columns: tuple[str, ...],
    optional_columns: tuple[str, ...],
    optional_metadata: tuple[str, ...],
    axis_monotonic_required: bool = True,
    spectral_modality: bool = False,
    suspicious_x_units: tuple[str, ...] = (),
    suspicious_y_units: tuple[str, ...] = (),
    axis_range_hint: tuple[float, float] | None = None,
    description: str = "",
) -> dict[str, Any]:
    return {
        "label": label,
        "axis_label": axis_label,
        "axis_role": axis_role,
        "signal_label": signal_label,
        "signal_role": signal_role,
        "allowed_x_units": allowed_x_units,
        "allowed_y_units": allowed_y_units,
        "default_x_unit": default_x_unit,
        "default_y_unit": default_y_unit,
        "x_aliases": x_aliases,
        "y_aliases": y_aliases,
        "required_columns": required_columns,
        "optional_columns": optional_columns,
        "optional_metadata": optional_metadata,
        "axis_monotonic_required": axis_monotonic_required,
        "spectral_modality": spectral_modality,
        "suspicious_x_units": suspicious_x_units,
        "suspicious_y_units": suspicious_y_units,
        "axis_range_hint": axis_range_hint,
        "description": description,
    }


MODALITY_SPECS: dict[str, dict[str, Any]] = {
    "DSC": _spec(
        label="Differential Scanning Calorimetry",
        axis_label="Temperature",
        axis_role="temperature",
        signal_label="Heat Flow",
        signal_role="signal",
        allowed_x_units=("°C", "degC", "K", "°F"),
        allowed_y_units=("mW", "mW/mg", "W/g", "a.u."),
        default_x_unit="°C",
        default_y_unit="mW",
        x_aliases=(
            r"[Tt]emp",
            r"\u00b0[Cc]",
            r"[Cc]elsius",
            r"[Kk]elvin",
            r"^T\b",
            r"^T_",
        ),
        y_aliases=(
            r"[Hh]eat\s*[Ff]low",
            r"\bDSC\b",
            r"[Mm][Ww]",
            r"[Ee]ndo",
            r"[Ee]xo",
            r"Cp\b",
        ),
        required_columns=("temperature", "signal"),
        optional_columns=("time",),
        optional_metadata=("sample_mass", "heating_rate", "instrument"),
        axis_monotonic_required=True,
        axis_range_hint=(-200.0, 2000.0),
        description="Measures heat flow as a function of temperature. X-axis is temperature (°C/K), Y-axis is heat flow (mW or mW/mg).",
    ),
    "TGA": _spec(
        label="Thermogravimetric Analysis",
        axis_label="Temperature",
        axis_role="temperature",
        signal_label="Mass",
        signal_role="signal",
        allowed_x_units=("°C", "degC", "K", "°F"),
        allowed_y_units=("%", "mg", "g", "a.u."),
        default_x_unit="°C",
        default_y_unit="%",
        x_aliases=(
            r"[Tt]emp",
            r"\u00b0[Cc]",
            r"[Cc]elsius",
            r"[Kk]elvin",
            r"^T\b",
            r"^T_",
        ),
        y_aliases=(
            r"[Mm]ass",
            r"[Ww]eight",
            r"\bTG(?!A)\b",
            r"\bTGA\b",
            r"[Ww]t\.?\s*%",
        ),
        required_columns=("temperature", "signal"),
        optional_columns=("time",),
        optional_metadata=("sample_mass", "heating_rate", "instrument"),
        axis_monotonic_required=True,
        axis_range_hint=(-200.0, 2000.0),
        description="Measures mass change as a function of temperature. X-axis is temperature (°C/K), Y-axis is mass (wt% or mg).",
    ),
    "DTA": _spec(
        label="Differential Thermal Analysis",
        axis_label="Temperature",
        axis_role="temperature",
        signal_label="ΔT",
        signal_role="signal",
        allowed_x_units=("°C", "degC", "K", "°F"),
        allowed_y_units=("µV", "uV", "mV", "a.u."),
        default_x_unit="°C",
        default_y_unit="µV",
        x_aliases=(
            r"[Tt]emp",
            r"\u00b0[Cc]",
            r"[Cc]elsius",
            r"[Kk]elvin",
            r"^T\b",
            r"^T_",
        ),
        y_aliases=(
            r"\bDTA\b",
            r"[Dd]elta\s*T",
            r"\u0394T",
            r"\u00b5[Vv]",
        ),
        required_columns=("temperature", "signal"),
        optional_columns=("time",),
        optional_metadata=("sample_mass", "heating_rate", "instrument"),
        axis_monotonic_required=True,
        axis_range_hint=(-200.0, 2000.0),
        description="Measures temperature difference between sample and reference. X-axis is temperature (°C/K), Y-axis is ΔT (µV).",
    ),
    "FTIR": _spec(
        label="Fourier Transform Infrared Spectroscopy",
        axis_label="Wavenumber",
        axis_role="temperature",
        signal_label="Absorbance / Transmittance",
        signal_role="signal",
        allowed_x_units=("cm^-1", "1/cm", "nm"),
        allowed_y_units=("absorbance", "transmittance", "%T", "a.u."),
        default_x_unit="cm^-1",
        default_y_unit="a.u.",
        x_aliases=(
            r"[Ww]avenumber",
            r"\bcm[-\^]?\s*1\b",
            r"\b1/cm\b",
            r"[Cc]m[-\^]1",
        ),
        y_aliases=(
            r"\bFTIR\b",
            r"[Aa]bsorb",
            r"[Tt]ransmitt",
            r"[Rr]eflect",
            r"%\s*T\b",
        ),
        required_columns=("temperature", "signal"),
        optional_columns=(),
        optional_metadata=("instrument",),
        axis_monotonic_required=False,
        spectral_modality=True,
        suspicious_x_units=("°C", "K", "°F"),
        suspicious_y_units=("mW", "mW/mg", "%", "mg", "µV"),
        description="Infrared absorption spectrum. X-axis is wavenumber (cm⁻¹), Y-axis is absorbance or transmittance.",
    ),
    "RAMAN": _spec(
        label="Raman Spectroscopy",
        axis_label="Raman Shift",
        axis_role="temperature",
        signal_label="Intensity",
        signal_role="signal",
        allowed_x_units=("cm^-1", "1/cm"),
        allowed_y_units=("counts", "cps", "intensity", "a.u."),
        default_x_unit="cm^-1",
        default_y_unit="a.u.",
        x_aliases=(
            r"[Rr]aman\s*[Ss]hift",
            r"\bcm[-\^]?\s*1\b",
            r"\b1/cm\b",
            r"[Ss]hift\s*\(cm",
        ),
        y_aliases=(
            r"\bRAMAN\b",
            r"[Ii]ntensity",
            r"\bCPS\b",
            r"[Cc]ounts?",
            r"[Rr]aman",
        ),
        required_columns=("temperature", "signal"),
        optional_columns=(),
        optional_metadata=("instrument", "laser_wavelength"),
        axis_monotonic_required=False,
        spectral_modality=True,
        suspicious_x_units=("°C", "K", "°F"),
        suspicious_y_units=("mW", "mW/mg", "%", "mg", "µV", "absorbance", "transmittance"),
        description="Inelastic scattering spectrum. X-axis is Raman shift (cm⁻¹), Y-axis is intensity (counts or CPS).",
    ),
    "XRD": _spec(
        label="X-Ray Diffraction",
        axis_label="2θ",
        axis_role="temperature",
        signal_label="Intensity",
        signal_role="signal",
        allowed_x_units=("degree_2theta", "deg", "2theta", "1/angstrom"),
        allowed_y_units=("counts", "cps", "intensity", "a.u."),
        default_x_unit="degree_2theta",
        default_y_unit="counts",
        x_aliases=(
            r"2\s*theta",
            r"2\u03b8",
            r"[Tt]wo\s*theta",
            r"[Aa]ngle",
            r"\bXRD\b",
            r"[Dd]iffract",
        ),
        y_aliases=(
            r"\bXRD\b",
            r"[Dd]iffract",
            r"[Ii]ntensity",
            r"[Cc]ounts?",
            r"\bCPS\b",
        ),
        required_columns=("temperature", "signal"),
        optional_columns=(),
        optional_metadata=("xrd_wavelength_angstrom", "instrument"),
        axis_monotonic_required=True,
        suspicious_x_units=("°C", "K", "°F", "cm^-1"),
        suspicious_y_units=("mW", "mW/mg", "%", "mg", "µV", "absorbance", "transmittance"),
        description="Powder diffraction pattern. X-axis is 2θ (degrees), Y-axis is intensity (counts).",
    ),
}

SUPPORTED_MODALITIES = tuple(MODALITY_SPECS.keys())


def get_modality_spec(modality: str) -> dict[str, Any] | None:
    """Return the spec dict for a modality, or None if unknown."""
    return MODALITY_SPECS.get(str(modality).upper())


def modality_allowed_x_units(modality: str) -> tuple[str, ...]:
    spec = get_modality_spec(modality)
    return spec["allowed_x_units"] if spec else ()


def modality_allowed_y_units(modality: str) -> tuple[str, ...]:
    spec = get_modality_spec(modality)
    return spec["allowed_y_units"] if spec else ()


def modality_default_x_unit(modality: str) -> str:
    spec = get_modality_spec(modality)
    return spec["default_x_unit"] if spec else "unknown"


def modality_default_y_unit(modality: str) -> str:
    spec = get_modality_spec(modality)
    return spec["default_y_unit"] if spec else "unknown"


def check_suspicious_unit_combo(
    modality: str,
    x_unit: str,
    y_unit: str,
) -> list[str]:
    """Return warning strings for suspicious unit combinations given a modality."""
    spec = get_modality_spec(modality)
    if spec is None:
        return []

    warnings: list[str] = []
    if x_unit in spec["suspicious_x_units"]:
        warnings.append(
            f"{modality} axis unit '{x_unit}' is unusual for this modality; "
            f"expected one of {spec['allowed_x_units']}."
        )
    if y_unit in spec["suspicious_y_units"]:
        warnings.append(
            f"{modality} signal unit '{y_unit}' is unusual for this modality; "
            f"expected one of {spec['allowed_y_units']}."
        )
    if x_unit not in spec["allowed_x_units"] and x_unit not in spec["suspicious_x_units"]:
        warnings.append(
            f"{modality} axis unit '{x_unit}' is not in the known allowed set "
            f"{spec['allowed_x_units']}; verify before proceeding."
        )
    if y_unit not in spec["allowed_y_units"] and y_unit not in spec["suspicious_y_units"]:
        warnings.append(
            f"{modality} signal unit '{y_unit}' is not in the known allowed set "
            f"{spec['allowed_y_units']}; verify before proceeding."
        )
    return warnings


def modality_signal_pattern_key(modality: str) -> str | None:
    """Map modality to the signal pattern key used in data_io._PATTERNS."""
    mapping = {
        "DSC": "signal_dsc",
        "TGA": "signal_tga",
        "DTA": "signal_dta",
        "FTIR": "signal_ftir",
        "RAMAN": "signal_raman",
        "XRD": "signal_xrd",
    }
    return mapping.get(str(modality).upper())


def modality_is_spectral(modality: str) -> bool:
    spec = get_modality_spec(modality)
    return bool(spec and spec.get("spectral_modality"))
