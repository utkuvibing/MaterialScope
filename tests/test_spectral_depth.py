"""
test_spectral_depth.py
----------------------
PR-18 — FTIR / Raman scientific depth.

Covers:
- %T -> absorbance conversion (A = -log10 T), incl. non-positive clipping
  and explicit withholding when conversion is not justifiable.
- Absolute wavelength <-> wavenumber conversion (distinct from Raman shift).
- Raman shift <-> scattered wavelength, gated on an explicitly declared /
  traceable excitation wavelength — withheld otherwise.
- Region (band-area) trapezoid integration on the corrected trace.
- Annotated peak-table rows carrying axis unit, detection signal basis, and
  region labels — no invented chemistry.
- Batch-runner plumbing, result-record serialization, and XLSX export.

All numeric assertions use pytest.approx / allclose — spectral conversions
are floating-point, never bit-exact.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.spectral_depth import (
    annotate_peak_table,
    convert_spectral_axis,
    integrate_region,
    integrate_regions,
    normalize_spectral_axis_unit,
    raman_shift_to_wavelength,
    resolve_laser_wavelength_nm,
    transmittance_to_absorbance,
    wavelength_to_raman_shift,
    wavelength_to_wavenumber,
    wavenumber_to_wavelength,
)


# ---------------------------------------------------------------------------
# Unit normalization
# ---------------------------------------------------------------------------

class TestUnitNormalization:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("cm-1", "cm-1"),
            ("cm^-1", "cm-1"),
            ("Wavenumber", "cm-1"),
            ("µm", "um"),
            ("microns", "um"),
            ("nm", "nm"),
            ("raman-shift", "raman_shift_cm-1"),
        ],
    )
    def test_aliases(self, raw, expected):
        assert normalize_spectral_axis_unit(raw) == expected


# ---------------------------------------------------------------------------
# Transmittance -> absorbance
# ---------------------------------------------------------------------------

class TestTransmittanceToAbsorbance:
    def test_percent_values(self):
        conv = transmittance_to_absorbance([100.0, 10.0, 1.0], signal_unit="%T")
        assert conv.basis == "converted"
        np.testing.assert_allclose(conv.absorbance, [0.0, 1.0, 2.0], atol=1e-12)
        assert conv.clipped_points == 0

    def test_fractional_values(self):
        conv = transmittance_to_absorbance([1.0, 0.5, 0.25], signal_unit="transmittance")
        assert conv.basis == "converted"
        np.testing.assert_allclose(
            conv.absorbance, [0.0, -np.log10(0.5), -np.log10(0.25)], atol=1e-12
        )

    def test_non_positive_clipped_to_ceiling(self):
        conv = transmittance_to_absorbance([100.0, 0.0, -5.0, 10.0], signal_unit="%T")
        assert conv.basis == "converted"
        assert conv.clipped_points == 2
        # Ceiling = absorbance of smallest positive transmittance (10%T -> A=1)
        assert conv.absorbance[1] == pytest.approx(1.0)
        assert conv.absorbance[2] == pytest.approx(1.0)

    def test_withheld_when_no_positive(self):
        conv = transmittance_to_absorbance([0.0, -1.0], signal_unit="%T")
        assert conv.basis == "withheld"
        assert conv.withheld_reason == "no_positive_transmittance"
        assert conv.absorbance is None

    def test_withheld_for_non_transmittance_unit(self):
        conv = transmittance_to_absorbance([1.0, 2.0], signal_unit="absorbance")
        assert conv.basis == "withheld"
        assert conv.withheld_reason == "signal_unit_not_transmittance"


# ---------------------------------------------------------------------------
# Absolute wavelength <-> wavenumber
# ---------------------------------------------------------------------------

class TestAbsoluteAxisConversion:
    def test_um_to_cm1(self):
        out = wavelength_to_wavenumber([10.0, 2.5], unit="um")
        np.testing.assert_allclose(out, [1000.0, 4000.0], rtol=1e-9)

    def test_nm_to_cm1(self):
        out = wavelength_to_wavenumber([1000.0], unit="nm")
        np.testing.assert_allclose(out, [10000.0], rtol=1e-9)

    def test_cm1_to_um(self):
        out = wavenumber_to_wavelength([1000.0, 4000.0], unit="um")
        np.testing.assert_allclose(out, [10.0, 2.5], rtol=1e-9)

    def test_non_positive_produces_nan(self):
        out = wavelength_to_wavenumber([0.0, -2.0, 5.0], unit="um")
        assert np.isnan(out[0]) and np.isnan(out[1])
        assert out[2] == pytest.approx(2000.0)

    def test_roundtrip(self):
        wn = np.linspace(400.0, 4000.0, 200)
        rt = wavelength_to_wavenumber(wavenumber_to_wavelength(wn, unit="um"), unit="um")
        np.testing.assert_allclose(rt, wn, rtol=1e-9)


# ---------------------------------------------------------------------------
# Raman shift <-> wavelength (excitation-gated)
# ---------------------------------------------------------------------------

class TestRamanShiftConversion:
    def test_zero_shift_at_laser_line(self):
        out = wavelength_to_raman_shift([532.0], laser_wavelength_nm=532.0)
        assert out[0] == pytest.approx(0.0, abs=1e-9)

    def test_stokes_shift_positive(self):
        out = wavelength_to_raman_shift([633.0], laser_wavelength_nm=532.0)
        assert out[0] > 0
        # 1e7*(1/532 - 1/633) ≈ 2997 cm-1
        assert out[0] == pytest.approx(1e7 * (1 / 532.0 - 1 / 633.0), rel=1e-9)

    def test_roundtrip(self):
        shifts = np.array([100.0, 500.0, 1600.0, 3000.0])
        wl = raman_shift_to_wavelength(shifts, laser_wavelength_nm=785.0)
        back = wavelength_to_raman_shift(wl, laser_wavelength_nm=785.0)
        np.testing.assert_allclose(back, shifts, rtol=1e-9)


class TestLaserWavelengthResolution:
    def test_declared_user_value(self):
        wl, src, reason = resolve_laser_wavelength_nm(532.0, {})
        assert wl == pytest.approx(532.0)
        assert src == "user"
        assert reason is None

    def test_metadata_parsed_value(self):
        wl, src, _ = resolve_laser_wavelength_nm(None, {"laser_wavelength": 785})
        assert wl == pytest.approx(785.0)
        assert src == "parsed"

    def test_um_unit_converted(self):
        wl, _, _ = resolve_laser_wavelength_nm(
            None, {"laser_wavelength": 0.785, "laser_wavelength_unit": "um"}
        )
        assert wl == pytest.approx(785.0)

    def test_missing_withheld(self):
        wl, src, reason = resolve_laser_wavelength_nm(None, {})
        assert wl is None and reason == "excitation_wavelength_missing"

    def test_invalid_withheld(self):
        for bad in (0.0, -10.0, float("nan"), "abc"):
            wl, _, reason = resolve_laser_wavelength_nm(bad, {})
            assert wl is None
            assert reason == "excitation_wavelength_invalid"


# ---------------------------------------------------------------------------
# convert_spectral_axis orchestration
# ---------------------------------------------------------------------------

class TestConvertSpectralAxis:
    def test_ftir_cm1_to_um(self):
        conv = convert_spectral_axis(
            [1000.0, 2000.0],
            analysis_type="FTIR",
            source_unit="cm-1",
            target_unit="um",
        )
        assert conv.applied and conv.basis == "converted"
        np.testing.assert_allclose(conv.axis, [10.0, 5.0], rtol=1e-9)
        assert conv.target_unit == "um"

    def test_identity_when_source_equals_target(self):
        conv = convert_spectral_axis(
            [1000.0], analysis_type="FTIR", source_unit="cm-1", target_unit="wavenumber"
        )
        assert conv.basis == "identity"
        np.testing.assert_allclose(conv.axis, [1000.0])

    def test_ftir_unsupported_withheld(self):
        conv = convert_spectral_axis(
            [1000.0], analysis_type="FTIR", source_unit="cm-1", target_unit="raman_shift"
        )
        assert conv.basis == "withheld"
        assert conv.withheld_reason

    def test_raman_nm_to_shift_requires_laser(self):
        conv = convert_spectral_axis(
            [600.0, 633.0],
            analysis_type="RAMAN",
            source_unit="nm",
            target_unit="raman_shift",
        )
        assert conv.basis == "withheld"
        assert conv.withheld_reason == "excitation_wavelength_missing"
        assert conv.axis is None

    def test_raman_nm_to_shift_with_declared_laser(self):
        conv = convert_spectral_axis(
            [532.0, 633.0],
            analysis_type="RAMAN",
            source_unit="nm",
            target_unit="raman_shift",
            laser_wavelength_nm=532.0,
        )
        assert conv.applied
        assert conv.axis[0] == pytest.approx(0.0, abs=1e-9)
        assert conv.laser_wavelength_nm == pytest.approx(532.0)
        assert conv.laser_wavelength_source == "user"

    def test_raman_laser_from_metadata(self):
        conv = convert_spectral_axis(
            [600.0],
            analysis_type="RAMAN",
            source_unit="nm",
            target_unit="raman_shift",
            dataset_metadata={"laser_wavelength": 785},
        )
        assert conv.applied
        assert conv.laser_wavelength_source == "parsed"

    def test_raman_absolute_wavenumber_distinct_from_shift(self):
        # nm -> absolute cm-1 does NOT require a laser line.
        conv = convert_spectral_axis(
            [500.0],
            analysis_type="RAMAN",
            source_unit="nm",
            target_unit="wavenumber",
        )
        assert conv.applied
        assert conv.axis[0] == pytest.approx(20000.0, rel=1e-9)

    def test_other_modality_withheld(self):
        conv = convert_spectral_axis(
            [100.0], analysis_type="XRD", source_unit="cm-1", target_unit="um"
        )
        assert conv.basis == "withheld"


# ---------------------------------------------------------------------------
# Region integration
# ---------------------------------------------------------------------------

class TestRegionIntegration:
    def _gaussian_axis(self):
        x = np.linspace(0.0, 100.0, 1001)
        y = np.exp(-0.5 * ((x - 50.0) / 5.0) ** 2)
        return x, y

    def test_trapezoid_area(self):
        x, y = self._gaussian_axis()
        region = integrate_region(x, y, 30.0, 70.0, label="band")
        assert region.withheld_reason is None
        assert region.area == pytest.approx(5.0 * np.sqrt(2 * np.pi), rel=0.01)
        assert region.label == "band"
        assert region.n_points > 100

    def test_bounds_swapped(self):
        x, y = self._gaussian_axis()
        region = integrate_region(x, y, 70.0, 30.0)
        assert region.withheld_reason is None
        assert region.area > 0

    def test_outside_range_withheld(self):
        x, y = self._gaussian_axis()
        region = integrate_region(x, y, 200.0, 300.0)
        assert region.area is None
        assert region.withheld_reason == "region_outside_measured_range"

    def test_sub_spacing_window_integrates_via_edge_interpolation(self):
        # A window narrower than the sample spacing has no interior samples;
        # both edges are interpolated, and the trapezoid over the declared
        # window is still honest — n_points counts the interpolated edges.
        region = integrate_region([0.0, 1.0], [1.0, 1.0], 0.4, 0.6)
        assert region.withheld_reason is None
        assert region.n_points == 2
        assert region.area == pytest.approx(0.2)

    def test_degenerate_axis_withheld(self):
        region = integrate_region([0.5], [1.0], 0.0, 1.0)
        assert region.withheld_reason == "axis_or_signal_too_short"

    def test_integrate_regions_skips_bad_items(self):
        x, y = self._gaussian_axis()
        results = integrate_regions(
            x, y, [{"lo": 40, "hi": 60, "label": "a"}, "bogus", {"lo": "x", "hi": 1}]
        )
        assert results[0].area is not None
        assert results[1].withheld_reason == "region_not_a_mapping"
        assert results[2].withheld_reason == "region_bounds_not_finite_or_empty"


# ---------------------------------------------------------------------------
# Annotated peak table
# ---------------------------------------------------------------------------

class TestAnnotatePeakTable:
    def test_rows_carry_provenance(self):
        peaks = [
            {"rank": 1, "position": 1600.0, "intensity": 0.9, "prominence": 0.2},
            {"rank": 2, "position": 2900.0, "intensity": 0.4, "prominence": 0.1},
        ]
        regions = integrate_regions(
            np.linspace(400, 4000, 100), np.zeros(100),
            [{"lo": 1500, "hi": 1700, "label": "carbonyl"}],
        )
        rows = annotate_peak_table(
            peaks,
            axis_unit="cm-1",
            signal_basis="corrected",
            regions=regions,
            analysis_type="FTIR",
        )
        assert len(rows) == 2
        assert rows[0]["axis_unit"] == "cm-1"
        assert rows[0]["signal_basis"] == "corrected"
        assert rows[0]["region"] == "carbonyl"
        assert rows[1]["region"] == ""
        assert rows[0]["analysis_type"] == "FTIR"
        # No chemical assignment fields are invented.
        assert "assignment" not in rows[0]
        assert "functional_group" not in rows[0]

    def test_empty_peaks(self):
        assert annotate_peak_table([], axis_unit="cm-1", signal_basis="corrected") == []


# ---------------------------------------------------------------------------
# Batch-runner plumbing
# ---------------------------------------------------------------------------

def _ftir_dataset(axis, signal, *, signal_unit="%T", axis_unit="cm-1", **metadata):
    import pandas as pd
    from core.data_io import ThermalDataset

    return ThermalDataset(
        data=pd.DataFrame({"temperature": np.asarray(axis), "signal": np.asarray(signal)}),
        metadata={"sample_name": "DepthSpec", **metadata},
        data_type="FTIR",
        units={"temperature": axis_unit, "signal": signal_unit},
        original_columns={"temperature": "temperature", "signal": "signal"},
        file_path="",
    )


def _raman_dataset(axis, signal, *, axis_unit="cm-1", **metadata):
    import pandas as pd
    from core.data_io import ThermalDataset

    return ThermalDataset(
        data=pd.DataFrame({"temperature": np.asarray(axis), "signal": np.asarray(signal)}),
        metadata={"sample_name": "DepthRaman", **metadata},
        data_type="RAMAN",
        units={"temperature": axis_unit, "signal": "counts"},
        original_columns={"temperature": "temperature", "signal": "signal"},
        file_path="",
    )


def _ftir_spectrum():
    """%T spectrum on 400-4000 cm-1 with two absorption dips."""
    x = np.linspace(400.0, 4000.0, 1801)
    y = (
        95.0
        - 60.0 * np.exp(-0.5 * ((x - 1700.0) / 40.0) ** 2)
        - 45.0 * np.exp(-0.5 * ((x - 2950.0) / 60.0) ** 2)
    )
    return x, np.clip(y, 1.0, 100.0)


class TestBatchPlumbing:
    def test_axis_conversion_applies_to_state(self):
        from core.batch_runner import execute_batch_template

        x, y = _ftir_spectrum()
        dataset = _ftir_dataset(x, y)
        outcome = execute_batch_template(
            dataset_key="depth_ftir",
            dataset=dataset,
            analysis_type="FTIR",
            workflow_template_id="ftir.general",
            existing_processing={
                "signal_pipeline": {
                    "axis_conversion": {"enabled": True, "target": "um"},
                }
            },
        )
        assert outcome["status"] == "saved"
        state = outcome["state"]
        summary = outcome["record"]["summary"]
        # 400..4000 cm-1 -> 25..2.5 um
        np.testing.assert_allclose(
            np.sort(np.asarray(state["axis"], dtype=float)),
            np.sort(1e4 / x),
            rtol=1e-9,
        )
        assert state["axis_unit"] == "um"
        assert state["axis_role"] == "wavelength"
        assert summary["spectral_axis_unit_effective"] == "um"
        assert summary["spectral_axis_role_effective"] == "wavelength"
        assert state["peak_table"]
        assert all(r["axis_unit"] == "um" for r in state["peak_table"])

    def test_absorbance_conversion_replaces_inversion(self):
        from core.batch_runner import execute_batch_template

        x, y = _ftir_spectrum()
        outcome = execute_batch_template(
            dataset_key="depth_ftir",
            dataset=_ftir_dataset(x, y),
            analysis_type="FTIR",
            workflow_template_id="ftir.general",
            existing_processing={
                "signal_pipeline": {"signal_conversion": {"enabled": True}}
            },
        )
        assert outcome["status"] == "saved"
        summary = outcome["record"]["summary"]
        assert summary["converted_to_absorbance"] is True
        diag = outcome["state"]["diagnostics"]
        assert diag["signal_role"] == "absorbance"
        assert diag["absorbance_conversion"]["converted"] is True
        assert diag["inverted_for_transmittance"] is False
        # Smoothed trace should look like absorbance, not inverted %T.
        smoothed = np.asarray(outcome["state"]["smoothed"], dtype=float)
        assert smoothed.max() == pytest.approx(-np.log10(0.35), abs=0.35)

    def test_absorbance_conversion_withheld_for_absorbance_input(self):
        from core.batch_runner import execute_batch_template

        x = np.linspace(400.0, 4000.0, 801)
        y = np.exp(-0.5 * ((x - 1700.0) / 60.0) ** 2)
        outcome = execute_batch_template(
            dataset_key="depth_ftir",
            dataset=_ftir_dataset(x, y, signal_unit="absorbance"),
            analysis_type="FTIR",
            workflow_template_id="ftir.general",
            existing_processing={
                "signal_pipeline": {"signal_conversion": {"enabled": True}}
            },
        )
        assert outcome["status"] == "saved"
        assert outcome["record"]["summary"]["converted_to_absorbance"] is False

    def test_region_integration_in_summary(self):
        from core.batch_runner import execute_batch_template

        x, y = _ftir_spectrum()
        outcome = execute_batch_template(
            dataset_key="depth_ftir",
            dataset=_ftir_dataset(x, y),
            analysis_type="FTIR",
            workflow_template_id="ftir.general",
            existing_processing={
                "analysis_steps": {
                    "region_integration": {
                        "enabled": True,
                        "regions": [
                            {"lo": 1600, "hi": 1800, "label": "carbonyl"},
                            {"lo": 100, "hi": 200, "label": "out_of_range"},
                        ],
                    }
                }
            },
        )
        assert outcome["status"] == "saved"
        regions = outcome["record"]["summary"]["region_integrals"]
        assert len(regions) == 2
        in_range = next(r for r in regions if r["label"] == "carbonyl")
        assert in_range["area"] is not None and in_range["area"] > 0
        assert in_range["basis"] in {"corrected", "smoothed"}
        out = next(r for r in regions if r["label"] == "out_of_range")
        assert out["withheld_reason"] == "region_outside_measured_range"

    def test_peak_table_annotates_region(self):
        from core.batch_runner import execute_batch_template

        x, y = _ftir_spectrum()
        outcome = execute_batch_template(
            dataset_key="depth_ftir",
            dataset=_ftir_dataset(x, y),
            analysis_type="FTIR",
            workflow_template_id="ftir.general",
            existing_processing={
                "analysis_steps": {
                    "region_integration": {
                        "enabled": True,
                        "regions": [{"lo": 1600, "hi": 1800, "label": "carbonyl"}],
                    }
                }
            },
        )
        assert outcome["status"] == "saved"
        table = outcome["record"]["summary"]["peak_table"]
        assert table
        regioned = [r for r in table if r["region"] == "carbonyl"]
        assert regioned, "expected a detected peak inside the carbonyl region"
        assert all(r["signal_basis"] in {"corrected", "normalized"} for r in table)

    def test_raman_shift_conversion_requires_laser(self):
        from core.batch_runner import execute_batch_template

        x = np.linspace(560.0, 700.0, 400)
        y = np.exp(-0.5 * ((x - 620.0) / 5.0) ** 2) * 1000
        outcome = execute_batch_template(
            dataset_key="depth_raman",
            dataset=_raman_dataset(x, y, axis_unit="nm"),
            analysis_type="RAMAN",
            workflow_template_id="raman.general",
            existing_processing={
                "signal_pipeline": {
                    "axis_conversion": {"enabled": True, "target": "raman_shift"},
                }
            },
        )
        assert outcome["status"] == "saved"
        summary = outcome["record"]["summary"]
        # Withheld: no excitation wavelength declared anywhere.
        assert summary["spectral_axis_conversion_basis"] == "withheld"
        assert summary["spectral_axis_conversion_withheld_reason"] == "excitation_wavelength_missing"
        np.testing.assert_allclose(outcome["state"]["axis"], x)

    def test_raman_shift_conversion_with_laser(self):
        from core.batch_runner import execute_batch_template

        x = np.linspace(540.0, 700.0, 400)
        y = np.exp(-0.5 * ((x - 630.0) / 5.0) ** 2) * 1000
        outcome = execute_batch_template(
            dataset_key="depth_raman",
            dataset=_raman_dataset(x, y, axis_unit="nm"),
            analysis_type="RAMAN",
            workflow_template_id="raman.general",
            existing_processing={
                "signal_pipeline": {
                    "axis_conversion": {
                        "enabled": True,
                        "target": "raman_shift",
                        "laser_wavelength_nm": 532.0,
                    },
                }
            },
        )
        assert outcome["status"] == "saved"
        summary = outcome["record"]["summary"]
        assert summary["spectral_axis_conversion_basis"] == "converted"
        expected = 1e7 * (1 / 532.0 - 1 / x)
        np.testing.assert_allclose(
            np.asarray(outcome["state"]["axis"], dtype=float), expected, rtol=1e-9
        )
        assert outcome["state"]["axis_role"] == "raman_shift"
        assert outcome["state"]["axis_unit"] == "cm-1"
        mc = outcome["record"]["processing"]["method_context"]
        assert mc["laser_wavelength_nm"] == pytest.approx(532.0)
        assert mc["laser_wavelength_source"] == "user"

    def test_disabled_by_default(self):
        from core.batch_runner import execute_batch_template

        x, y = _ftir_spectrum()
        outcome = execute_batch_template(
            dataset_key="depth_ftir",
            dataset=_ftir_dataset(x, y),
            analysis_type="FTIR",
            workflow_template_id="ftir.general",
        )
        assert outcome["status"] == "saved"
        summary = outcome["record"]["summary"]
        assert summary["spectral_axis_unit_effective"] == "cm-1"
        assert summary["converted_to_absorbance"] is False
        # Peak table is still produced (annotations on the declared basis).
        assert summary["peak_table"]
        assert all(r["axis_unit"] == "cm-1" for r in summary["peak_table"])


# ---------------------------------------------------------------------------
# Serialization + export
# ---------------------------------------------------------------------------

class TestSerializationAndExport:
    def test_record_roundtrip_preserves_depth_fields(self):
        from core.batch_runner import execute_batch_template
        from core.result_serialization import split_valid_results

        x, y = _ftir_spectrum()
        outcome = execute_batch_template(
            dataset_key="depth_ftir",
            dataset=_ftir_dataset(x, y),
            analysis_type="FTIR",
            workflow_template_id="ftir.general",
            existing_processing={
                "signal_pipeline": {"signal_conversion": {"enabled": True}},
                "analysis_steps": {
                    "region_integration": {
                        "enabled": True,
                        "regions": [{"lo": 1600, "hi": 1800, "label": "carbonyl"}],
                    }
                },
            },
        )
        assert outcome["status"] == "saved"
        record = outcome["record"]
        valid, issues = split_valid_results({"r1": record})
        assert "r1" in valid, issues
        summary = valid["r1"]["summary"]
        assert summary["peak_table"]
        assert summary["region_integrals"]
        assert summary["converted_to_absorbance"] is True

    def test_xlsx_peak_table_sheet(self):
        from backend.exports import _results_to_xlsx_bytes
        from core.batch_runner import execute_batch_template
        import pandas as pd
        import io

        x, y = _ftir_spectrum()
        outcome = execute_batch_template(
            dataset_key="depth_ftir",
            dataset=_ftir_dataset(x, y),
            analysis_type="FTIR",
            workflow_template_id="ftir.general",
        )
        record = outcome["record"]
        blob = _results_to_xlsx_bytes({record["id"]: record}, [])
        book = pd.read_excel(io.BytesIO(blob), sheet_name=None)
        peak_sheets = [name for name in book if name.endswith("_peaks")]
        assert peak_sheets, "annotated peak table should be its own sheet"
        peaks_df = book[peak_sheets[0]]
        assert "position" in peaks_df.columns
        assert "axis_unit" in peaks_df.columns
        assert "signal_basis" in peaks_df.columns


# ---------------------------------------------------------------------------
# Dash draft plumbing (unit-level; callbacks fire through the same helpers)
# ---------------------------------------------------------------------------

@pytest.fixture
def _dash_app():
    import dash
    from dash import html

    try:
        dash.get_app()
    except Exception:
        app = dash.Dash(
            __name__,
            use_pages=True,
            pages_folder="",
            suppress_callback_exceptions=True,
        )
        app.layout = html.Div(dash.page_container)
    yield


@pytest.mark.usefixtures("_dash_app")
class TestDashDraftPlumbing:
    def test_ftir_draft_normalizes_new_sections(self):
        import dash_app.pages.ftir as page

        draft = page._normalize_ftir_processing_draft(
            {
                "axis_conversion": {"target": "um", "source_unit": "auto"},
                "signal_conversion": {"enabled": True},
                "region_integration": {
                    "enabled": True,
                    "regions": [{"lo": 1600, "hi": 1800, "label": "c=O"}],
                },
            }
        )
        assert draft["axis_conversion"]["enabled"] is True
        assert draft["axis_conversion"]["target"] == "um"
        # "auto" must never reach the converter as a physical unit.
        assert draft["axis_conversion"]["source_unit"] is None
        assert draft["signal_conversion"]["enabled"] is True
        assert draft["region_integration"]["regions"][0]["label"] == "c=O"

    def test_ftir_draft_from_controls_parses_regions(self):
        import dash_app.pages.ftir as page

        draft = page._ftir_draft_from_control_values(
            "savgol", 11, 3, None,
            "asls", 1e6, 0.01, [], None, None,
            "vector",
            0.035, 5, 10,
            "cosine", 3, 0.45,
            "wavenumber", "cm-1", ["enabled"], "1600 1800 carbonyl\nbad line",
        )
        assert draft["signal_conversion"]["enabled"] is True
        regions = draft["region_integration"]["regions"]
        assert regions == [{"lo": 1600.0, "hi": 1800.0, "label": "carbonyl"}]

    def test_raman_draft_normalizes_new_sections(self):
        import dash_app.pages.raman as page

        draft = page._normalize_raman_processing_draft(
            {
                "axis_conversion": {
                    "target": "raman_shift",
                    "source_unit": "nm",
                    "laser_wavelength_nm": 532.0,
                },
                "region_integration": {
                    "enabled": True,
                    "regions": [{"lo": 1300, "hi": 1400, "label": "D"}],
                },
            }
        )
        assert draft["axis_conversion"]["enabled"] is True
        assert draft["axis_conversion"]["laser_wavelength_nm"] == pytest.approx(532.0)
        assert draft["region_integration"]["enabled"] is True

    def test_raman_invalid_laser_dropped(self):
        import dash_app.pages.raman as page

        draft = page._normalize_raman_processing_draft(
            {"axis_conversion": {"target": "raman_shift", "laser_wavelength_nm": -5}}
        )
        # Non-positive excitation is dropped -> converter will withhold.
        assert draft["axis_conversion"]["laser_wavelength_nm"] is None


# ---------------------------------------------------------------------------
# Import-provenance -> signal conversion (manual-QA regression)
# ---------------------------------------------------------------------------

_FTIR_TRANSMITTANCE_FILENAME = "ftir_transmittance.csv"


def _ftir_transmittance_csv_bytes() -> bytes:
    """Deterministic synthetic FTIR %T spectrum — the same shape as the
    manual-QA file ``testing_data/ftir_transmittance.csv`` (which is
    gitignored), generated in-test so the suite is self-contained:
    descending wavenumber axis, absorption bands as downward %T dips."""
    wn = np.arange(400.0, 4000.0001, 2.0)[::-1]  # 4000 -> 400 descending
    rng = np.random.default_rng(20260403)

    def band(center: float, depth: float, width: float) -> np.ndarray:
        return depth * np.exp(-0.5 * ((wn - center) / width) ** 2)

    pct_t = (
        92.0
        - 0.001 * (4000.0 - wn)          # slight baseline tilt
        - band(3400.0, 35.0, 220.0)      # O-H broad
        - band(2920.0, 22.0, 45.0)       # C-H asym
        - band(2850.0, 15.0, 35.0)       # C-H sym
        - band(1715.0, 55.0, 30.0)       # C=O
        - band(1450.0, 18.0, 35.0)       # CH2 bend
        - band(1050.0, 70.0, 60.0)       # Si-O / C-O strong
        + rng.normal(0.0, 0.15, wn.size)
    )
    lines = [
        "# Synthetic FTIR %T — bands 3400/2920/2850/1715/1450/1050 cm-1, descending axis",
        "Wavenumber (cm-1),Transmittance (%T)",
    ]
    lines += [f"{w:g},{t:.4f}" for w, t in zip(wn, pct_t)]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _import_ftir_transmittance():
    """Reproduce the manual-QA import: ``ftir_transmittance.csv`` imported as
    FTIR with the explicit column mapping the wizard records."""
    import io

    from core.data_io import read_thermal_data

    buf = io.BytesIO(_ftir_transmittance_csv_bytes())
    buf.name = _FTIR_TRANSMITTANCE_FILENAME
    return read_thermal_data(
        buf,
        column_mapping={
            "temperature": "Wavenumber (cm-1)",
            "signal": "Transmittance (%T)",
        },
        data_type="FTIR",
        metadata={"sample_name": "ftir_transmittance"},
    )


class TestImportProvenanceSignalConversion:
    """An explicit ``Transmittance (%T)`` column mapping must carry enough
    provenance for the FTIR pipeline to treat the signal as transmittance, so
    an enabled absorbance conversion actually runs (A = -log10 T) instead of
    silently no-op'ing on ``signal_role == 'unknown'``."""

    def test_explicit_percent_t_mapping_converts_to_absorbance(self):
        from core.batch_runner import execute_batch_template

        dataset = _import_ftir_transmittance()
        # Import provenance: the mapped column declares percent transmittance.
        assert dataset.units["signal"] == "%T"
        assert dataset.metadata["inferred_signal_unit"] == "%T"

        outcome = execute_batch_template(
            dataset_key="qa_ftir_t",
            dataset=dataset,
            analysis_type="FTIR",
            workflow_template_id="ftir.general",
            existing_processing={
                "signal_pipeline": {
                    "axis_conversion": {"enabled": True, "target": "um"},
                    "signal_conversion": {"enabled": True},
                    "smoothing": {"method": "none"},
                }
            },
        )
        assert outcome["status"] == "saved"
        state = outcome["state"]
        diag = state["diagnostics"]
        summary = outcome["record"]["summary"]

        assert diag["signal_role"] == "absorbance"
        assert diag["inverted_for_transmittance"] is False
        assert diag["absorbance_conversion"]["converted"] is True
        assert diag["absorbance_conversion"]["basis"] == "converted"
        assert summary["converted_to_absorbance"] is True
        assert summary["spectral_signal_role_effective"] == "absorbance"
        # Effective signal basis is recorded on the state for downstream
        # surfaces (figure axis labels, curves endpoint, exports).
        assert state["signal_role"] == "absorbance"
        assert state["signal_unit"] == "absorbance"

        # Curve values are true absorbance: A = -log10(T/100) evaluated on the
        # converted + sorted axis (smoothing disabled for exact equality).
        raw_wn = dataset.data["temperature"].to_numpy(dtype=float)
        raw_t = dataset.data["signal"].to_numpy(dtype=float)
        um_axis = 1e4 / raw_wn
        order = np.argsort(um_axis)
        unique_axis, unique_idx = np.unique(um_axis[order], return_index=True)
        expected = -np.log10(raw_t[order][unique_idx] / 100.0)
        np.testing.assert_allclose(
            np.asarray(state["axis"], dtype=float), unique_axis, rtol=1e-9
        )
        np.testing.assert_allclose(
            np.asarray(state["smoothed"], dtype=float), expected, rtol=1e-9
        )
        # Sanity: absorbance scale, not the ~20-90 %T input range.
        assert float(np.max(expected)) < 1.5

        warnings = " ".join(str(w) for w in outcome["validation"]["warnings"])
        assert "converted to absorbance" in warnings

    def test_conversion_disabled_preserves_transmittance(self):
        from core.batch_runner import execute_batch_template

        outcome = execute_batch_template(
            dataset_key="qa_ftir_t_off",
            dataset=_import_ftir_transmittance(),
            analysis_type="FTIR",
            workflow_template_id="ftir.general",
            existing_processing={
                "signal_pipeline": {
                    "axis_conversion": {"enabled": True, "target": "um"},
                    "smoothing": {"method": "none"},
                }
            },
        )
        assert outcome["status"] == "saved"
        state = outcome["state"]
        diag = state["diagnostics"]

        assert diag["signal_role"] == "transmittance"
        assert diag["inverted_for_transmittance"] is True
        assert "absorbance_conversion" not in diag
        assert outcome["record"]["summary"]["converted_to_absorbance"] is False
        # The %T signal basis is preserved for downstream surfaces.
        assert state["signal_unit"] == "%T"
        # Inversion fallback keeps the percent scale (max - T), not -log10.
        smoothed = np.asarray(state["smoothed"], dtype=float)
        assert float(smoothed.max()) > 10.0

    def test_already_absorbance_input_is_not_double_converted(self):
        import io

        from core.batch_runner import execute_batch_template
        from core.data_io import read_thermal_data

        buf = io.StringIO(
            "Wavenumber (cm-1),Absorbance\n"
            "4000.0,0.04\n"
            "3000.0,0.32\n"
            "2000.0,0.55\n"
            "1000.0,0.21\n"
            "500.0,0.05\n"
        )
        dataset = read_thermal_data(
            buf,
            column_mapping={
                "temperature": "Wavenumber (cm-1)",
                "signal": "Absorbance",
            },
            data_type="FTIR",
        )
        outcome = execute_batch_template(
            dataset_key="qa_ftir_a",
            dataset=dataset,
            analysis_type="FTIR",
            workflow_template_id="ftir.general",
            existing_processing={
                "signal_pipeline": {
                    "signal_conversion": {"enabled": True},
                    "smoothing": {"method": "none"},
                }
            },
        )
        assert outcome["status"] == "saved"
        state = outcome["state"]
        diag = state["diagnostics"]

        assert diag["signal_role"] == "absorbance"
        assert diag["absorbance_conversion"]["basis"] == "not_applicable"
        assert outcome["record"]["summary"]["converted_to_absorbance"] is False
        # Values are the declared absorbance signal, unchanged (no -log10 of
        # an already-absorbance trace).
        raw_signal = dataset.data["signal"].to_numpy(dtype=float)
        order = np.argsort(dataset.data["temperature"].to_numpy(dtype=float))
        np.testing.assert_allclose(
            np.asarray(state["smoothed"], dtype=float), raw_signal[order], rtol=1e-9
        )

    def test_ambiguous_signal_role_withholds_with_reason(self):
        import io

        from core.batch_runner import execute_batch_template
        from core.data_io import read_thermal_data

        buf = io.StringIO(
            "Wavenumber (cm-1),Signal\n"
            "4000.0,0.04\n"
            "3000.0,0.32\n"
            "2000.0,0.55\n"
            "1000.0,0.21\n"
            "500.0,0.05\n"
        )
        dataset = read_thermal_data(
            buf,
            column_mapping={
                "temperature": "Wavenumber (cm-1)",
                "signal": "Signal",
            },
            data_type="FTIR",
        )
        outcome = execute_batch_template(
            dataset_key="qa_ftir_unknown",
            dataset=dataset,
            analysis_type="FTIR",
            workflow_template_id="ftir.general",
            existing_processing={
                "signal_pipeline": {"signal_conversion": {"enabled": True}},
            },
        )
        assert outcome["status"] == "saved"
        diag = outcome["state"]["diagnostics"]

        # enabled=True must never silently no-op on an unproven role.
        assert diag["signal_role"] == "unknown"
        assert diag["absorbance_conversion"]["basis"] == "withheld"
        assert diag["absorbance_conversion"]["withheld_reason"]
        assert outcome["record"]["summary"]["converted_to_absorbance"] is False
        warnings = " ".join(str(w) for w in outcome["validation"]["warnings"])
        assert "withheld" in warnings

    def test_generic_percent_signal_is_not_promoted_to_transmittance(self):
        import io

        from core.batch_runner import execute_batch_template
        from core.data_io import read_thermal_data

        buf = io.StringIO(
            "Wavenumber (cm-1),Signal (%)\n"
            "4000.0,91.0\n"
            "3000.0,62.0\n"
            "2000.0,35.0\n"
            "1000.0,58.0\n"
            "500.0,90.0\n"
        )
        dataset = read_thermal_data(
            buf,
            column_mapping={
                "temperature": "Wavenumber (cm-1)",
                "signal": "Signal (%)",
            },
            data_type="FTIR",
        )
        outcome = execute_batch_template(
            dataset_key="qa_ftir_pct",
            dataset=dataset,
            analysis_type="FTIR",
            workflow_template_id="ftir.general",
            existing_processing={
                "signal_pipeline": {"signal_conversion": {"enabled": True}},
            },
        )
        assert outcome["status"] == "saved"
        diag = outcome["state"]["diagnostics"]

        # An arbitrary percentage column is not transmittance provenance.
        assert diag["signal_role"] == "unknown"
        assert diag["absorbance_conversion"]["basis"] == "withheld"
        assert outcome["record"]["summary"]["converted_to_absorbance"] is False

    def test_legacy_percent_unit_recovers_transmittance_from_column_header(self):
        """A dataset imported before the %T parse fix has units '%', but the
        recorded original column header still declares transmittance — that
        provenance is sufficient to convert."""
        import pandas as pd

        from core.batch_runner import execute_batch_template
        from core.data_io import ThermalDataset

        x, y = _ftir_spectrum()
        dataset = ThermalDataset(
            data=pd.DataFrame({"temperature": x, "signal": y}),
            metadata={"sample_name": "legacy", "inferred_signal_unit": "%"},
            data_type="FTIR",
            units={"temperature": "cm^-1", "signal": "%"},
            original_columns={
                "temperature": "Wavenumber (cm-1)",
                "signal": "Transmittance (%T)",
            },
            file_path="",
        )
        outcome = execute_batch_template(
            dataset_key="qa_ftir_legacy",
            dataset=dataset,
            analysis_type="FTIR",
            workflow_template_id="ftir.general",
            existing_processing={
                "signal_pipeline": {"signal_conversion": {"enabled": True}},
            },
        )
        assert outcome["status"] == "saved"
        diag = outcome["state"]["diagnostics"]
        assert diag["signal_role"] == "absorbance"
        assert diag["absorbance_conversion"]["converted"] is True


class TestManualQAEndToEnd:
    """Drive the exact manual-QA path through the combined app: dataset
    import with explicit mapping -> analysis run with depth overrides ->
    analysis-state curves -> figure axis title."""

    def test_ftir_transmittance_to_absorbance_end_to_end(self):
        import base64

        from fastapi.testclient import TestClient

        from core.axis_labels import build_axis_title
        from dash_app.server import create_combined_app

        client = TestClient(create_combined_app())
        project_id = client.post("/workspace/new").json()["project_id"]

        payload = base64.b64encode(_ftir_transmittance_csv_bytes()).decode("ascii")
        imported = client.post(
            "/dataset/import",
            json={
                "project_id": project_id,
                "file_name": _FTIR_TRANSMITTANCE_FILENAME,
                "file_base64": payload,
                "data_type": "FTIR",
                "column_mapping": {
                    "temperature": "Wavenumber (cm-1)",
                    "signal": "Transmittance (%T)",
                },
                "metadata": {"sample_name": "ftir_transmittance"},
            },
        )
        assert imported.status_code == 200
        dataset_key = imported.json()["dataset"]["key"]

        detail = client.get(f"/workspace/{project_id}/datasets/{dataset_key}")
        assert detail.status_code == 200
        assert detail.json()["units"]["signal"] == "%T"

        run = client.post(
            "/analysis/run",
            json={
                "project_id": project_id,
                "dataset_key": dataset_key,
                "analysis_type": "FTIR",
                "workflow_template_id": "ftir.general",
                "processing_overrides": {
                    "axis_conversion": {"enabled": True, "target": "um"},
                    "signal_conversion": {"enabled": True},
                },
            },
        )
        assert run.status_code == 200
        run_body = run.json()
        assert run_body["execution_status"] == "saved"
        # The conversion provenance warning is counted in the run validation
        # rollup; the full warning text rides on the saved result record.
        assert run_body["validation"]["warning_count"] >= 1
        result = client.get(
            f"/workspace/{project_id}/results/{run_body['result_id']}"
        )
        assert result.status_code == 200
        result_warnings = " ".join(
            str(w)
            for w in (result.json().get("validation") or {}).get("warnings") or []
        )
        assert "converted to absorbance" in result_warnings
        result_summary = result.json().get("summary") or {}
        assert result_summary["converted_to_absorbance"] is True
        assert result_summary["spectral_signal_role_effective"] == "absorbance"

        curves = client.get(
            f"/workspace/{project_id}/analysis-state/FTIR/{dataset_key}"
        )
        assert curves.status_code == 200
        curves = curves.json()
        assert curves["signal_role"] == "absorbance"
        assert curves["x_unit"] == "um"
        assert curves["y_unit"] == "absorbance"

        smoothed = np.asarray(curves["smoothed"], dtype=float)
        assert float(np.nanmax(smoothed)) < 1.5
        assert float(np.nanmin(smoothed)) >= -0.2

        y_title = build_axis_title(
            "FTIR",
            "y",
            detected_unit=curves["y_unit"],
            signal_kind=curves["signal_role"],
        )
        assert y_title == "Absorbance (a.u.)"


# ---------------------------------------------------------------------------
# Raman-shift axis provenance — manual-QA regression
# ---------------------------------------------------------------------------
# A `Raman Shift (cm-1)` axis was imported as generic `wavenumber`, which
# routed the "from dataset" source through the ungated absolute
# wavenumber -> wavelength conversion: fabricated thousands-of-nm values and
# bypassed the excitation gate.  These tests pin the fixed behaviour.

_RAMAN_SHIFT_FILENAME = "raman_shift.csv"


def _raman_shift_csv_bytes() -> bytes:
    """Deterministic stand-in for the manual-QA fixture
    ``testing_data/raman_shift.csv`` (gitignored): a ``Raman Shift (cm-1)``
    axis with sharp bands on a sloped baseline.  The header carries the
    shift provenance — the values only need realistic peaks."""
    shift = np.arange(200.0, 3500.0001, 1.5)
    rng = np.random.default_rng(20260917)

    def band(center: float, amp: float, fwhm: float) -> np.ndarray:
        sigma = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0)))
        return amp * np.exp(-0.5 * ((shift - center) / sigma) ** 2)

    intensity = (
        300.0
        + 0.35 * (shift - 200.0)
        + band(520.0, 4200.0, 8.0)
        + band(1080.0, 1500.0, 18.0)
        + band(1600.0, 2800.0, 22.0)
        + band(2900.0, 900.0, 40.0)
        + rng.normal(0.0, 8.0, shift.size)
    )
    lines = [
        "# Synthetic Raman — peaks 520/1080/1600/2900 cm-1",
        "Raman Shift (cm-1),Raman Signal (CPS)",
    ]
    lines += [f"{s:g},{t:.4f}" for s, t in zip(shift, intensity)]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _generic_raman_csv_bytes(axis_header: str) -> bytes:
    """Generic cm-1 Raman file with a single band; the axis header carries
    whatever physical declaration the caller wants to exercise.  The signal
    column deliberately avoids ``counts``/``intensity`` tokens so the file
    is not captured by the XRD measured-pattern detector."""
    x = np.arange(200.0, 3500.0001, 2.0)
    rng = np.random.default_rng(7)
    intensity = (
        500.0
        + 2000.0 * np.exp(-0.5 * ((x - 1000.0) / 15.0) ** 2)
        + rng.normal(0.0, 5.0, x.size)
    )
    lines = [f"{axis_header},Signal (CPS)"]
    lines += [f"{v:g},{t:.3f}" for v, t in zip(x, intensity)]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _import_raman_csv(file_name: str, csv_bytes: bytes, column_mapping: dict):
    """Reproduce the manual-QA import: CSV imported as RAMAN through
    ``read_thermal_data`` with the explicit column mapping the wizard records."""
    import io

    from core.data_io import read_thermal_data

    buf = io.BytesIO(csv_bytes)
    buf.name = file_name
    return read_thermal_data(
        buf,
        column_mapping=column_mapping,
        data_type="RAMAN",
        metadata={"sample_name": file_name.rsplit(".", 1)[0]},
    )


def _import_raman_shift():
    return _import_raman_csv(
        _RAMAN_SHIFT_FILENAME,
        _raman_shift_csv_bytes(),
        {"temperature": "Raman Shift (cm-1)", "signal": "Raman Signal (CPS)"},
    )


def _run_raman_batch(dataset, axis_conversion: dict):
    from core.batch_runner import execute_batch_template

    return execute_batch_template(
        dataset_key="qa_raman_axis",
        dataset=dataset,
        analysis_type="RAMAN",
        workflow_template_id="raman.general",
        existing_processing={"signal_pipeline": {"axis_conversion": axis_conversion}},
    )


class TestRamanShiftAxisProvenance:
    def test_raman_shift_header_preserves_shift_role(self):
        dataset = _import_raman_shift()
        assert dataset.units["temperature"] == "cm^-1"
        # Traceable shift provenance must not collapse to generic wavenumber.
        assert dataset.metadata["spectral_axis_role"] == "raman_shift"

    def test_wavenumber_header_preserves_absolute_role(self):
        dataset = _import_raman_csv(
            "abs_wavenumber.csv",
            _generic_raman_csv_bytes("Wavenumber (cm-1)"),
            {"temperature": "Wavenumber (cm-1)", "signal": "Signal (CPS)"},
        )
        assert dataset.metadata["spectral_axis_role"] == "wavenumber"

    def test_generic_cm1_header_is_ambiguous(self):
        dataset = _import_raman_csv(
            "sample.csv",
            _generic_raman_csv_bytes("X (cm-1)"),
            {"temperature": "X (cm-1)", "signal": "Signal (CPS)"},
        )
        assert dataset.metadata["spectral_axis_role"] == "ambiguous"
        warnings = " ".join(str(w) for w in dataset.metadata.get("import_warnings") or [])
        assert "does not declare" in warnings

    def test_shift_to_nm_without_excitation_is_withheld(self):
        dataset = _import_raman_shift()
        outcome = _run_raman_batch(dataset, {"enabled": True, "target": "nm"})
        assert outcome["status"] == "saved"
        state = outcome["state"]
        summary = outcome["record"]["summary"]

        # Withheld — no converted axis may be emitted.
        assert summary["spectral_axis_conversion_basis"] == "withheld"
        assert (
            summary["spectral_axis_conversion_withheld_reason"]
            == "excitation_wavelength_missing"
        )
        assert state["diagnostics"]["axis_conversion"]["basis"] == "withheld"

        # The original Raman-shift basis is retained end to end.
        raw_axis = np.sort(dataset.data["temperature"].to_numpy(dtype=float))
        np.testing.assert_allclose(
            np.asarray(state["axis"], dtype=float), raw_axis, rtol=1e-9
        )
        assert state["axis_unit"] == "cm-1"
        assert state["axis_role"] == "raman_shift"
        assert summary["spectral_axis_unit_effective"] == "cm-1"
        assert summary["spectral_axis_role_effective"] == "raman_shift"
        assert state["peak_table"]
        assert all(r["axis_unit"] == "cm-1" for r in state["peak_table"])
        assert all(r["axis_role"] == "raman_shift" for r in state["peak_table"])
        # Peak positions stay on the shift axis — no fabricated nm values.
        positions = [p["position"] for p in state["peaks"]]
        assert positions and max(positions) < 4000.0

    def test_shift_to_nm_with_532_converts_via_shift_math(self):
        dataset = _import_raman_shift()
        outcome = _run_raman_batch(
            dataset,
            {"enabled": True, "target": "nm", "laser_wavelength_nm": 532.0},
        )
        assert outcome["status"] == "saved"
        state = outcome["state"]
        summary = outcome["record"]["summary"]

        assert summary["spectral_axis_conversion_basis"] == "converted"
        # raman_shift_to_wavelength numerics on the imported shift axis.
        raw_axis = dataset.data["temperature"].to_numpy(dtype=float)
        expected = raman_shift_to_wavelength(raw_axis, laser_wavelength_nm=532.0)
        np.testing.assert_allclose(
            np.asarray(state["axis"], dtype=float),
            np.unique(expected),
            rtol=1e-9,
        )
        # Physically plausible visible/NIR — not the fabricated
        # ~3000-20000 nm the absolute-wavenumber misroute produced.
        axis = np.asarray(state["axis"], dtype=float)
        assert float(axis.min()) > 533.0
        assert float(axis.max()) < 700.0
        assert state["axis_unit"] == "nm"
        assert state["axis_role"] == "wavelength"
        assert summary["spectral_axis_unit_effective"] == "nm"
        assert summary["spectral_axis_role_effective"] == "wavelength"
        assert all(r["axis_unit"] == "nm" for r in state["peak_table"])
        assert all(r["axis_role"] == "wavelength" for r in state["peak_table"])

        mc = outcome["record"]["processing"]["method_context"]
        assert mc["laser_wavelength_nm"] == pytest.approx(532.0)
        assert mc["laser_wavelength_source"] == "user"

    def test_shift_conversion_anchor_1000cm1_at_532nm(self):
        # Known fixture sanity anchor: a 1000 cm-1 shift under 532 nm
        # excitation scatters near ~561.88 nm.
        out = raman_shift_to_wavelength([1000.0], laser_wavelength_nm=532.0)
        assert out[0] == pytest.approx(561.88, abs=0.02)

    def test_declared_absolute_wavenumber_uses_absolute_path(self):
        dataset = _import_raman_csv(
            "abs_wavenumber.csv",
            _generic_raman_csv_bytes("Wavenumber (cm-1)"),
            {"temperature": "Wavenumber (cm-1)", "signal": "Signal (CPS)"},
        )
        assert dataset.metadata["spectral_axis_role"] == "wavenumber"
        outcome = _run_raman_batch(dataset, {"enabled": True, "target": "nm"})
        assert outcome["status"] == "saved"
        summary = outcome["record"]["summary"]
        # Genuinely declared absolute wavenumber still converts ungated.
        assert summary["spectral_axis_conversion_basis"] == "converted"
        raw_axis = dataset.data["temperature"].to_numpy(dtype=float)
        np.testing.assert_allclose(
            np.asarray(outcome["state"]["axis"], dtype=float),
            np.unique(1e7 / raw_axis),
            rtol=1e-9,
        )

    def test_ambiguous_cm1_source_withholds_auto_conversion(self):
        dataset = _import_raman_csv(
            "sample.csv",
            _generic_raman_csv_bytes("X (cm-1)"),
            {"temperature": "X (cm-1)", "signal": "Signal (CPS)"},
        )
        outcome = _run_raman_batch(dataset, {"enabled": True, "target": "nm"})
        assert outcome["status"] == "saved"
        summary = outcome["record"]["summary"]
        # Neither physical interpretation may be silently chosen.
        assert summary["spectral_axis_conversion_basis"] == "withheld"
        assert (
            summary["spectral_axis_conversion_withheld_reason"]
            == "source_axis_role_ambiguous"
        )
        raw_axis = np.sort(dataset.data["temperature"].to_numpy(dtype=float))
        np.testing.assert_allclose(
            np.asarray(outcome["state"]["axis"], dtype=float), raw_axis, rtol=1e-9
        )

    def test_explicit_cm1_source_on_ambiguous_uses_absolute_path(self):
        dataset = _import_raman_csv(
            "sample.csv",
            _generic_raman_csv_bytes("X (cm-1)"),
            {"temperature": "X (cm-1)", "signal": "Signal (CPS)"},
        )
        # An explicit source-unit selection is itself the declaration.
        outcome = _run_raman_batch(
            dataset, {"enabled": True, "target": "nm", "source_unit": "cm-1"}
        )
        assert outcome["status"] == "saved"
        summary = outcome["record"]["summary"]
        assert summary["spectral_axis_conversion_basis"] == "converted"
        raw_axis = dataset.data["temperature"].to_numpy(dtype=float)
        np.testing.assert_allclose(
            np.asarray(outcome["state"]["axis"], dtype=float),
            np.unique(1e7 / raw_axis),
            rtol=1e-9,
        )

    def test_explicit_raman_shift_source_is_excitation_gated(self):
        dataset = _import_raman_csv(
            "sample.csv",
            _generic_raman_csv_bytes("X (cm-1)"),
            {"temperature": "X (cm-1)", "signal": "Signal (CPS)"},
        )
        outcome = _run_raman_batch(
            dataset,
            {"enabled": True, "target": "nm", "source_unit": "raman_shift"},
        )
        assert outcome["status"] == "saved"
        summary = outcome["record"]["summary"]
        assert summary["spectral_axis_conversion_basis"] == "withheld"
        assert (
            summary["spectral_axis_conversion_withheld_reason"]
            == "excitation_wavelength_missing"
        )


class TestRamanShiftExportProvenance:
    def test_annotated_peak_table_and_xlsx_carry_axis_role(self):
        import io

        import pandas as pd
        from backend.exports import _results_to_xlsx_bytes

        outcome = _run_raman_batch(
            _import_raman_shift(),
            {"enabled": True, "target": "nm", "laser_wavelength_nm": 532.0},
        )
        assert outcome["status"] == "saved"
        record = outcome["record"]
        assert all(
            r["axis_role"] == "wavelength" for r in record["summary"]["peak_table"]
        )

        blob = _results_to_xlsx_bytes({record["id"]: record}, [])
        book = pd.read_excel(io.BytesIO(blob), sheet_name=None)
        peak_sheets = [name for name in book if name.endswith("_peaks")]
        assert peak_sheets
        peaks_df = book[peak_sheets[0]]
        assert "axis_role" in peaks_df.columns
        assert "axis_unit" in peaks_df.columns
        assert set(peaks_df["axis_role"]) == {"wavelength"}
        assert set(peaks_df["axis_unit"]) == {"nm"}


class TestManualQARamanEndToEnd:
    """Drive the exact manual-QA path through the combined app: RAMAN import
    with explicit mapping -> nm target with/without excitation ->
    analysis-state curves -> axis title."""

    def _import(self, client):
        import base64

        project_id = client.post("/workspace/new").json()["project_id"]
        payload = base64.b64encode(_raman_shift_csv_bytes()).decode("ascii")
        imported = client.post(
            "/dataset/import",
            json={
                "project_id": project_id,
                "file_name": _RAMAN_SHIFT_FILENAME,
                "file_base64": payload,
                "data_type": "RAMAN",
                "column_mapping": {
                    "temperature": "Raman Shift (cm-1)",
                    "signal": "Raman Signal (CPS)",
                },
                "metadata": {"sample_name": "raman_shift"},
            },
        )
        assert imported.status_code == 200
        return project_id, imported.json()["dataset"]["key"]

    def _run(self, client, project_id, dataset_key, overrides):
        run = client.post(
            "/analysis/run",
            json={
                "project_id": project_id,
                "dataset_key": dataset_key,
                "analysis_type": "RAMAN",
                "workflow_template_id": "raman.general",
                "processing_overrides": overrides,
            },
        )
        assert run.status_code == 200
        body = run.json()
        assert body["execution_status"] == "saved"
        return body

    def test_raman_shift_axis_conversion_end_to_end(self):
        from fastapi.testclient import TestClient

        from core.axis_labels import build_axis_title
        from dash_app.server import create_combined_app

        client = TestClient(create_combined_app())
        project_id, dataset_key = self._import(client)

        detail = client.get(f"/workspace/{project_id}/datasets/{dataset_key}")
        assert detail.status_code == 200
        assert detail.json()["metadata"]["spectral_axis_role"] == "raman_shift"
        assert detail.json()["units"]["temperature"] == "cm^-1"

        # --- QA step 1: nm target, no excitation -> withheld ----------------
        self._run(
            client,
            project_id,
            dataset_key,
            {"axis_conversion": {"enabled": True, "target": "nm"}},
        )
        curves = client.get(
            f"/workspace/{project_id}/analysis-state/RAMAN/{dataset_key}"
        )
        assert curves.status_code == 200
        curves = curves.json()
        assert curves["axis_role"] == "raman_shift"
        assert curves["x_unit"] == "cm-1"
        axis = np.asarray(curves["temperature"], dtype=float)
        assert float(axis.min()) == pytest.approx(200.0)
        assert float(axis.max()) == pytest.approx(3500.0)
        assert curves["peaks"]
        assert all(p["axis_unit"] == "cm-1" for p in curves["peaks"])
        assert all(p["axis_role"] == "raman_shift" for p in curves["peaks"])
        x_title = build_axis_title(
            "RAMAN",
            "x",
            detected_unit=curves["x_unit"],
            axis_role=curves["axis_role"],
        )
        assert "Raman Shift" in x_title

        # --- QA step 2: nm target + 532 nm excitation -> converted ---------
        run = self._run(
            client,
            project_id,
            dataset_key,
            {
                "axis_conversion": {
                    "enabled": True,
                    "target": "nm",
                    "laser_wavelength_nm": 532.0,
                }
            },
        )
        result = client.get(f"/workspace/{project_id}/results/{run['result_id']}")
        assert result.status_code == 200
        result_summary = result.json().get("summary") or {}
        assert result_summary["spectral_axis_conversion_basis"] == "converted"
        assert result_summary["spectral_axis_unit_effective"] == "nm"
        assert result_summary["spectral_axis_role_effective"] == "wavelength"
        method_context = (result.json().get("processing") or {}).get(
            "method_context"
        ) or {}
        assert method_context["laser_wavelength_nm"] == pytest.approx(532.0)

        curves = client.get(
            f"/workspace/{project_id}/analysis-state/RAMAN/{dataset_key}"
        ).json()
        assert curves["axis_role"] == "wavelength"
        assert curves["x_unit"] == "nm"
        axis = np.asarray(curves["temperature"], dtype=float)
        assert float(axis.min()) > 533.0
        assert float(axis.max()) < 700.0
        assert curves["peaks"]
        assert all(p["axis_unit"] == "nm" for p in curves["peaks"])
        assert all(p["axis_role"] == "wavelength" for p in curves["peaks"])
        positions = [float(p["position"]) for p in curves["peaks"]]
        assert all(533.0 < p < 700.0 for p in positions)
        x_title = build_axis_title(
            "RAMAN",
            "x",
            detected_unit=curves["x_unit"],
            axis_role=curves["axis_role"],
        )
        assert "Wavelength" in x_title
