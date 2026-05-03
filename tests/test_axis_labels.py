from __future__ import annotations

from core.axis_labels import build_axis_title, canonical_unit_label, modality_axis_labels
from core.modality_specs import MODALITY_SPECS


def test_canonical_unit_label_normalizes_requested_conversions():
    assert canonical_unit_label("cm^-1") == "cm⁻¹"
    assert canonical_unit_label("1/cm") == "cm⁻¹"
    assert canonical_unit_label("mW/mg") == "mW mg⁻¹"
    assert canonical_unit_label("W/g") == "W g⁻¹"
    assert canonical_unit_label("%/°C") == "% °C⁻¹"
    assert canonical_unit_label("degree_2theta") == "°"
    assert canonical_unit_label("uV") == "µV"


def test_plotly_safe_unit_rendering_is_supported():
    assert canonical_unit_label("cm^-1", plotly_html=True) == "cm<sup>−1</sup>"
    assert canonical_unit_label("mW/mg", plotly_html=True) == "mW mg<sup>−1</sup>"


def test_build_axis_title_core_modalities():
    assert build_axis_title("FTIR", "x") == "Wavenumber (cm⁻¹)"
    assert build_axis_title("RAMAN", "x") == "Raman Shift (cm⁻¹)"
    assert build_axis_title("XRD", "x") == "2θ (°)"


def test_build_axis_title_thermal_temperature_units():
    assert build_axis_title("DSC", "x", detected_unit="K") == "Temperature (K)"
    assert build_axis_title("TGA", "x", detected_unit="degC") == "Temperature (°C)"
    assert build_axis_title("DTA", "x", detected_unit="°C") == "Temperature (°C)"


def test_build_axis_title_thermal_signal_units():
    assert build_axis_title("DSC", "y", detected_unit="mW/mg") == "Heat Flow (mW mg⁻¹)"
    assert build_axis_title("TGA", "y", detected_unit="mg") == "Mass (mg)"
    assert build_axis_title("DTA", "y", detected_unit="uV") == "ΔT (µV)"
    assert build_axis_title("TGA", "y", detected_unit="%/K", signal_kind="dtg") == "DTG (% K⁻¹)"


def test_build_axis_title_ftir_signal_semantics():
    assert build_axis_title("FTIR", "y", detected_unit="a.u.", signal_kind="absorbance") == "Absorbance (a.u.)"
    assert build_axis_title("FTIR", "y", detected_unit="%") == "Transmittance (%)"
    assert build_axis_title("FTIR", "y", detected_unit="a.u.", signal_kind="reflectance") == "Reflectance (%)"
    assert build_axis_title("FTIR", "y", detected_unit="counts", signal_kind="intensity") == "Intensity (a.u.)"


def test_spectral_descriptor_units_are_not_rendered_as_physical_units():
    ftir_absorbance = build_axis_title("FTIR", "y", detected_unit="absorbance")
    assert "(absorbance)" not in ftir_absorbance.lower()
    assert ftir_absorbance == "Absorbance (a.u.)"

    ftir_transmittance = build_axis_title("FTIR", "y", detected_unit="transmittance")
    assert "(transmittance)" not in ftir_transmittance.lower()
    assert "%" in ftir_transmittance

    raman_intensity = build_axis_title("RAMAN", "y", detected_unit="intensity")
    assert "(intensity)" not in raman_intensity.lower()
    assert raman_intensity == "Intensity (a.u.)"

    xrd_intensity = build_axis_title("XRD", "y", detected_unit="intensity")
    assert "(intensity)" not in xrd_intensity.lower()
    assert xrd_intensity == "Intensity (counts)"


def test_spectral_x_axis_edge_cases():
    assert build_axis_title("FTIR", "x", detected_unit="nm") == "Wavelength (nm)"
    xrd_q_axis = build_axis_title("XRD", "x", detected_unit="1/angstrom")
    assert xrd_q_axis.startswith("q ")
    assert "Å⁻¹" in xrd_q_axis
    assert "2θ" not in xrd_q_axis


def test_modality_axis_labels_returns_pair():
    x_title, y_title = modality_axis_labels("XRD", x_unit="degree_2theta", y_unit="cps")
    assert x_title == "2θ (°)"
    assert y_title == "Intensity (cps)"


def test_spectral_modality_specs_have_non_temperature_axis_roles():
    assert MODALITY_SPECS["FTIR"]["axis_role"] == "wavenumber"
    assert MODALITY_SPECS["RAMAN"]["axis_role"] == "raman_shift"
    assert MODALITY_SPECS["XRD"]["axis_role"] == "two_theta"
    assert MODALITY_SPECS["FTIR"]["axis_role"] != "temperature"
    assert MODALITY_SPECS["RAMAN"]["axis_role"] != "temperature"
    assert MODALITY_SPECS["XRD"]["axis_role"] != "temperature"
