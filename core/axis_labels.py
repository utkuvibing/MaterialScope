"""Centralized modality-aware axis label and unit formatting helpers."""

from __future__ import annotations

import re
from typing import Literal

from core.modality_specs import get_modality_spec

_SUP_MINUS_ONE_UNICODE = "⁻¹"
_SUP_MINUS_ONE_HTML = "<sup>−1</sup>"

_SUP_PATTERN = re.compile(r"<\s*sup\s*>\s*[-−]?\s*1\s*<\s*/\s*sup\s*>", re.IGNORECASE)


def _normalize_unit_key(unit: str | None) -> str:
    token = str(unit or "").strip()
    if not token:
        return ""
    token = token.replace("μ", "µ").replace("−", "-").replace("–", "-")
    lowered = token.lower()
    lowered = _SUP_PATTERN.sub("^-1", lowered)
    lowered = (
        lowered.replace("⁻¹", "^-1")
        .replace("⁻", "-")
        .replace("¹", "1")
        .replace(" ", "")
    )
    return lowered


def canonical_unit_token(unit: str | None) -> str:
    """Map raw/imported unit strings to a canonical token used across the app."""
    key = _normalize_unit_key(unit)
    if not key:
        return ""

    mapping = {
        "cm^-1": "cm^-1",
        "cm-1": "cm^-1",
        "cm**-1": "cm^-1",
        "1/cm": "cm^-1",
        "1/cm.": "cm^-1",
        "cm<sup>-1</sup>": "cm^-1",
        "cm<sup>−1</sup>": "cm^-1",
        "degree_2theta": "degree_2theta",
        "2theta": "degree_2theta",
        "deg": "degree_2theta",
        "degree": "degree_2theta",
        "°": "degree_2theta",
        "°c": "°C",
        "degc": "°C",
        "celsius": "°C",
        "c": "°C",
        "k": "K",
        "°f": "°F",
        "degf": "°F",
        "mw": "mW",
        "mw/mg": "mW/mg",
        "w/g": "W/g",
        "%": "%",
        "%t": "%",
        "wt%": "%",
        "weight%": "%",
        "mg": "mg",
        "g": "g",
        "uv": "uV",
        "µv": "uV",
        "mv": "mV",
        "a.u.": "a.u.",
        "au": "a.u.",
        "arb.": "a.u.",
        "arbitrary": "a.u.",
        "counts": "counts",
        "count": "counts",
        "cps": "cps",
        "intensity": "intensity",
        "absorbance": "absorbance",
        "transmittance": "transmittance",
        "reflectance": "reflectance",
        "nm": "nm",
        "1/angstrom": "1/angstrom",
        "angstrom^-1": "1/angstrom",
        "å^-1": "1/angstrom",
        "1/å": "1/angstrom",
        "a^-1": "1/angstrom",
        "%/°c": "%/°C",
        "%/degc": "%/°C",
        "%/c": "%/°C",
        "%/k": "%/K",
    }
    return mapping.get(key, str(unit or "").strip())


def canonical_unit_label(unit: str | None, *, plotly_html: bool = False) -> str:
    """Return a display-safe unit label with scientific formatting."""
    token = canonical_unit_token(unit)
    if not token:
        return ""

    if plotly_html:
        html_map = {
            "cm^-1": f"cm{_SUP_MINUS_ONE_HTML}",
            "mW/mg": f"mW mg{_SUP_MINUS_ONE_HTML}",
            "W/g": f"W g{_SUP_MINUS_ONE_HTML}",
            "%/°C": f"% °C{_SUP_MINUS_ONE_HTML}",
            "%/K": f"% K{_SUP_MINUS_ONE_HTML}",
            "degree_2theta": "°",
            "1/angstrom": f"Å{_SUP_MINUS_ONE_HTML}",
            "uV": "µV",
        }
        if token in html_map:
            return html_map[token]

    unicode_map = {
        "cm^-1": f"cm{_SUP_MINUS_ONE_UNICODE}",
        "mW/mg": f"mW mg{_SUP_MINUS_ONE_UNICODE}",
        "W/g": f"W g{_SUP_MINUS_ONE_UNICODE}",
        "%/°C": f"% °C{_SUP_MINUS_ONE_UNICODE}",
        "%/K": f"% K{_SUP_MINUS_ONE_UNICODE}",
        "degree_2theta": "°",
        "1/angstrom": f"Å{_SUP_MINUS_ONE_UNICODE}",
        "uV": "µV",
    }
    if token in unicode_map:
        return unicode_map[token]
    return token


def _normalize_signal_kind(signal_kind: str | None) -> str:
    token = str(signal_kind or "").strip().lower().replace(" ", "_").replace("-", "_")
    if token in {"dtg", "derivative", "mass_derivative"}:
        return "dtg"
    if token in {"delta_t", "deltat", "Δt".lower()}:
        return "delta_t"
    if token in {"signal"}:
        return "signal"
    if token in {"absorbance", "transmittance", "reflectance", "intensity", "mass", "heat_flow"}:
        return token
    return ""


def _default_unit_token(modality: str, axis: Literal["x", "y"]) -> str:
    spec = get_modality_spec(modality)
    if not spec:
        return "°C" if axis == "x" else "a.u."
    key = "default_x_unit" if axis == "x" else "default_y_unit"
    return canonical_unit_token(spec.get(key))


def _allowed_unit_tokens(modality: str, axis: Literal["x", "y"]) -> set[str]:
    spec = get_modality_spec(modality)
    if not spec:
        return set()
    key = "allowed_x_units" if axis == "x" else "allowed_y_units"
    return {canonical_unit_token(item) for item in spec.get(key, ())}


def _safe_unit_token(modality: str, axis: Literal["x", "y"], detected_unit: str | None) -> str:
    detected = canonical_unit_token(detected_unit)
    if not detected:
        return _default_unit_token(modality, axis)

    allowed = _allowed_unit_tokens(modality, axis)
    if not allowed:
        return detected
    if detected in allowed:
        return detected
    return _default_unit_token(modality, axis)


def _infer_signal_kind(modality: str, unit_token: str, signal_kind: str | None) -> str:
    explicit = _normalize_signal_kind(signal_kind)
    if explicit:
        return explicit

    modality_token = str(modality or "").upper()
    if modality_token == "FTIR":
        if unit_token in {"transmittance", "%"}:
            return "transmittance"
        if unit_token == "reflectance":
            return "reflectance"
        if unit_token in {"counts", "cps", "intensity"}:
            return "intensity"
        if unit_token == "absorbance":
            return "absorbance"
        return "absorbance"
    if modality_token in {"RAMAN", "XRD"}:
        return "intensity"
    if modality_token == "TGA":
        return "mass"
    if modality_token == "DSC":
        return "heat_flow"
    if modality_token == "DTA":
        return "delta_t"
    return "signal"


def _title_with_unit(title: str, unit_token: str, *, plotly_html: bool) -> str:
    label = canonical_unit_label(unit_token, plotly_html=plotly_html)
    return f"{title} ({label})" if label else title


def _spectral_signal_display_unit(modality: str, inferred_kind: str, unit_token: str) -> str:
    modality_token = str(modality or "").upper()
    raw_unit = str(unit_token or "").strip()

    if modality_token == "FTIR":
        if inferred_kind in {"transmittance", "reflectance"}:
            return "%"
        if inferred_kind == "absorbance":
            if raw_unit in {"", "a.u.", "absorbance", "transmittance", "reflectance", "intensity"}:
                return "a.u."
            return raw_unit
        if inferred_kind == "intensity":
            if raw_unit in {"counts", "cps", "a.u."}:
                return raw_unit
            return "a.u."
        if inferred_kind == "signal":
            if raw_unit in {"", "absorbance", "transmittance", "reflectance", "intensity"}:
                return "a.u."
            return raw_unit or "a.u."
        return raw_unit or "a.u."

    if modality_token in {"RAMAN", "XRD"}:
        fallback = "counts" if modality_token == "XRD" else "a.u."
        if raw_unit in {"counts", "cps", "a.u."}:
            return raw_unit
        if raw_unit in {"", "intensity"}:
            return fallback
        return fallback

    return raw_unit


def build_axis_title(
    modality: str,
    axis: Literal["x", "y"],
    detected_unit: str | None = None,
    signal_kind: str | None = None,
    *,
    plotly_html: bool = False,
) -> str:
    """Build a modality-aware axis title from modality, axis role, and units."""
    modality_token = str(modality or "").upper()
    axis_token = str(axis or "").lower()
    if axis_token not in {"x", "y"}:
        raise ValueError("axis must be 'x' or 'y'.")

    raw_unit_token = canonical_unit_token(detected_unit)
    unit_token = _safe_unit_token(modality_token, axis_token, detected_unit)
    inferred_kind = _infer_signal_kind(modality_token, unit_token, signal_kind)

    if axis_token == "x":
        if modality_token == "FTIR":
            if unit_token == "nm":
                return _title_with_unit("Wavelength", unit_token, plotly_html=plotly_html)
            return _title_with_unit("Wavenumber", unit_token or "cm^-1", plotly_html=plotly_html)
        if modality_token == "RAMAN":
            return _title_with_unit("Raman Shift", unit_token or "cm^-1", plotly_html=plotly_html)
        if modality_token == "XRD":
            if unit_token == "1/angstrom":
                return _title_with_unit("q", unit_token, plotly_html=plotly_html)
            return _title_with_unit("2θ", "degree_2theta", plotly_html=plotly_html)
        if unit_token not in {"°C", "K", "°F"}:
            unit_token = "°C"
        return _title_with_unit("Temperature", unit_token, plotly_html=plotly_html)

    if modality_token == "DSC":
        return _title_with_unit("Heat Flow", unit_token or "mW", plotly_html=plotly_html)
    if modality_token == "TGA":
        if inferred_kind == "dtg":
            dtg_unit_token = raw_unit_token if raw_unit_token in {"%/°C", "%/K"} else unit_token
            if dtg_unit_token in {"", "%", "a.u.", "unknown", "intensity"}:
                dtg_unit_token = "%/°C"
            return _title_with_unit("DTG", dtg_unit_token, plotly_html=plotly_html)
        return _title_with_unit("Mass", unit_token or "%", plotly_html=plotly_html)
    if modality_token == "DTA":
        title = "Signal" if inferred_kind == "signal" else "ΔT"
        return _title_with_unit(title, unit_token or "uV", plotly_html=plotly_html)
    if modality_token == "FTIR":
        spectral_unit = _spectral_signal_display_unit(modality_token, inferred_kind, unit_token)
        if inferred_kind == "transmittance":
            return _title_with_unit("Transmittance", spectral_unit, plotly_html=plotly_html)
        if inferred_kind == "reflectance":
            return _title_with_unit("Reflectance", spectral_unit, plotly_html=plotly_html)
        if inferred_kind == "intensity":
            return _title_with_unit("Intensity", spectral_unit, plotly_html=plotly_html)
        if inferred_kind == "signal":
            return _title_with_unit("Signal", spectral_unit, plotly_html=plotly_html)
        return _title_with_unit("Absorbance", spectral_unit, plotly_html=plotly_html)
    if modality_token in {"RAMAN", "XRD"}:
        spectral_unit = _spectral_signal_display_unit(modality_token, inferred_kind, unit_token)
        return _title_with_unit("Intensity", spectral_unit, plotly_html=plotly_html)
    return _title_with_unit("Signal", unit_token or "a.u.", plotly_html=plotly_html)


def modality_axis_labels(
    modality: str,
    x_unit: str | None = None,
    y_unit: str | None = None,
) -> tuple[str, str]:
    """Return x/y axis titles for a modality with optional detected units."""
    return (
        build_axis_title(modality, "x", detected_unit=x_unit),
        build_axis_title(modality, "y", detected_unit=y_unit),
    )
