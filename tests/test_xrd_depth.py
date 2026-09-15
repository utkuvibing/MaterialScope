"""PR-19 tests: XRD wavelength gate, honest baselines, and Scherrer sizing."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from core.baseline import als_baseline
from core.batch_runner import (
    _estimate_xrd_baseline,
    _extract_xrd_reference_peaks,
    _resolve_xrd_comparison_value,
    execute_batch_template,
)
from core.data_io import ThermalDataset
from core.xrd_depth import (
    analyze_xrd_scherrer,
    measure_fwhm_axis_bounds,
    scherrer_crystallite_size_nm,
)
from tests.test_batch_runner import _gaussian, _make_xrd_dataset


def _scherrer_reference_nm(two_theta_deg: float, fwhm_deg: float, wavelength: float, k: float) -> float:
    beta = math.radians(fwhm_deg)
    theta = math.radians(two_theta_deg / 2.0)
    return (k * wavelength) / (beta * math.cos(theta)) / 10.0


class TestScherrerPrimitive:
    def test_known_value_fixture(self):
        # beta = 0.5 deg = 0.0087266 rad; theta = 15 deg; cos = 0.965926
        size = scherrer_crystallite_size_nm(
            two_theta_deg=30.0,
            fwhm_two_theta_deg=0.5,
            wavelength_angstrom=1.5406,
            shape_factor=0.9,
        )
        expected = _scherrer_reference_nm(30.0, 0.5, 1.5406, 0.9)
        assert size == pytest.approx(expected, rel=1e-9)
        assert size == pytest.approx(16.44, abs=0.05)

    def test_invalid_inputs_return_none(self):
        assert scherrer_crystallite_size_nm(
            two_theta_deg=None, fwhm_two_theta_deg=0.5, wavelength_angstrom=1.5406, shape_factor=0.9
        ) is None
        assert scherrer_crystallite_size_nm(
            two_theta_deg=30.0, fwhm_two_theta_deg=0.0, wavelength_angstrom=1.5406, shape_factor=0.9
        ) is None
        assert scherrer_crystallite_size_nm(
            two_theta_deg=30.0, fwhm_two_theta_deg=0.5, wavelength_angstrom=None, shape_factor=0.9
        ) is None
        assert scherrer_crystallite_size_nm(
            two_theta_deg=30.0, fwhm_two_theta_deg=0.5, wavelength_angstrom=1.5406, shape_factor=0.0
        ) is None
        assert scherrer_crystallite_size_nm(
            two_theta_deg=200.0, fwhm_two_theta_deg=0.5, wavelength_angstrom=1.5406, shape_factor=0.9
        ) is None


class TestFwhmMeasurement:
    def test_gaussian_fwhm_in_axis_units(self):
        axis = np.linspace(10.0, 90.0, 2001)
        sigma = 0.30
        signal = _gaussian(axis, 40.0, sigma, 100.0)
        peak_index = int(np.argmax(signal))
        bounds = measure_fwhm_axis_bounds(axis, signal, peak_index)
        assert bounds is not None
        assert bounds["fwhm_axis"] == pytest.approx(2.3548 * sigma, rel=0.02)
        assert bounds["left_axis"] == pytest.approx(40.0 - 1.1774 * sigma, abs=0.05)
        assert bounds["right_axis"] == pytest.approx(40.0 + 1.1774 * sigma, abs=0.05)


class TestAnalyzeScherrer:
    def test_disabled_by_default(self):
        out = analyze_xrd_scherrer(
            axis=np.linspace(10, 90, 500),
            corrected_signal=np.ones(500),
            peaks=[{"rank": 1, "position": 30.0}],
            observed_space="two_theta",
            wavelength_angstrom=1.5406,
            config={},
        )
        assert out["status"] == "disabled"
        assert out["enabled"] is False

    def test_withheld_without_declared_wavelength(self):
        out = analyze_xrd_scherrer(
            axis=np.linspace(10, 90, 500),
            corrected_signal=np.ones(500),
            peaks=[{"rank": 1, "position": 30.0}],
            observed_space="two_theta",
            wavelength_angstrom=None,
            config={"enabled": True},
        )
        assert out["status"] == "withheld"
        assert "wavelength" in out["withheld_reason"]
        assert out["assumptions"]["wavelength_angstrom"] is None

    def test_computed_sizes_match_theory(self):
        axis = np.linspace(15.0, 50.0, 4001)
        sigma = 0.20
        signal = _gaussian(axis, 30.0, sigma, 100.0) + _gaussian(axis, 44.0, sigma, 60.0)
        peaks = [{"rank": 1, "position": 30.0}, {"rank": 2, "position": 44.0}]
        out = analyze_xrd_scherrer(
            axis=axis,
            corrected_signal=signal,
            peaks=peaks,
            observed_space="two_theta",
            wavelength_angstrom=1.5406,
            config={"enabled": True, "shape_factor": 0.9},
        )
        assert out["status"] == "computed"
        assert out["computed_count"] == 2
        expected_fwhm = 2.3548 * sigma
        for row in out["rows"]:
            assert row["status"] == "computed"
            assert row["fwhm_deg_2theta_observed"] == pytest.approx(expected_fwhm, rel=0.03)
            expected_nm = _scherrer_reference_nm(row["two_theta_deg"], row["fwhm_deg_2theta"], 1.5406, 0.9)
            assert row["crystallite_size_nm"] == pytest.approx(expected_nm, rel=1e-9)
        assumptions = out["assumptions"]
        assert assumptions["wavelength_angstrom"] == pytest.approx(1.5406)
        assert assumptions["shape_factor_k"] == pytest.approx(0.9)
        assert assumptions["fwhm_units"] == "degree_2theta"
        assert assumptions["instrumental_broadening_status"] == "not_corrected"
        assert "theta" in assumptions["theta_convention"]
        assert assumptions["instrumental_broadening_caveat"]

    def test_instrumental_broadening_quadrature_correction(self):
        axis = np.linspace(15.0, 45.0, 4001)
        sigma = 0.30
        signal = _gaussian(axis, 30.0, sigma, 100.0)
        inst_fwhm = 0.2
        out = analyze_xrd_scherrer(
            axis=axis,
            corrected_signal=signal,
            peaks=[{"rank": 1, "position": 30.0}],
            observed_space="two_theta",
            wavelength_angstrom=1.5406,
            config={"enabled": True, "shape_factor": 0.9, "instrumental_fwhm_deg": inst_fwhm},
        )
        row = out["rows"][0]
        assert row["status"] == "computed"
        observed = row["fwhm_deg_2theta_observed"]
        corrected = row["fwhm_deg_2theta"]
        assert corrected == pytest.approx(math.sqrt(observed**2 - inst_fwhm**2), rel=1e-9)
        assert out["assumptions"]["instrumental_broadening_status"] == "corrected"
        assert out["assumptions"]["instrumental_fwhm_deg_2theta"] == pytest.approx(inst_fwhm)
        assert out["assumptions"]["instrumental_broadening_caveat"] == ""

    def test_instrumental_fwhm_exceeding_observed_withheld(self):
        axis = np.linspace(15.0, 45.0, 4001)
        signal = _gaussian(axis, 30.0, 0.2, 100.0)
        out = analyze_xrd_scherrer(
            axis=axis,
            corrected_signal=signal,
            peaks=[{"rank": 1, "position": 30.0}],
            observed_space="two_theta",
            wavelength_angstrom=1.5406,
            config={"enabled": True, "instrumental_fwhm_deg": 5.0},
        )
        row = out["rows"][0]
        assert row["status"] == "withheld"
        assert row["withheld_reason"] == "instrumental_fwhm_exceeds_observed_fwhm"
        assert out["status"] == "withheld"

    def test_d_spacing_axis_exact_conversion(self):
        wavelength = 1.5406
        # Build the pattern directly on the d-spacing axis.
        d_axis = np.linspace(1.2, 6.0, 4000)
        target_d = 3.0
        sigma_d = 0.012
        signal = _gaussian(d_axis, target_d, sigma_d, 100.0)
        out = analyze_xrd_scherrer(
            axis=d_axis,
            corrected_signal=signal,
            peaks=[{"rank": 1, "position": target_d}],
            observed_space="d_spacing",
            wavelength_angstrom=wavelength,
            config={"enabled": True, "shape_factor": 0.9},
        )
        row = out["rows"][0]
        assert row["status"] == "computed"
        two_theta = math.degrees(2.0 * math.asin(wavelength / (2.0 * target_d)))
        assert row["two_theta_deg"] == pytest.approx(two_theta, rel=1e-9)
        # Exact endpoint conversion: FWHM bounds on d map through 2*asin(lam/2d).
        left_tt = math.degrees(2.0 * math.asin(wavelength / (2.0 * (target_d + 1.1774 * sigma_d))))
        right_tt = math.degrees(2.0 * math.asin(wavelength / (2.0 * (target_d - 1.1774 * sigma_d))))
        expected_fwhm = abs(right_tt - left_tt)
        assert row["fwhm_deg_2theta_observed"] == pytest.approx(expected_fwhm, rel=0.03)
        expected_nm = _scherrer_reference_nm(two_theta, row["fwhm_deg_2theta"], wavelength, 0.9)
        assert row["crystallite_size_nm"] == pytest.approx(expected_nm, rel=1e-9)


class TestBaselineHonesty:
    def test_asls_matches_pybaselines_implementation(self):
        axis = np.linspace(10.0, 90.0, 400)
        signal = 18.0 + 0.03 * axis + _gaussian(axis, 33.2, 0.5, 160.0)
        config: dict = {"method": "asls", "lam": 1e6, "p": 0.01}
        baseline = _estimate_xrd_baseline(signal, config)
        expected = als_baseline(np.arange(signal.size, dtype=float), signal, lam=1e6, p=0.01)
        np.testing.assert_allclose(baseline, expected, rtol=0, atol=0)
        assert config["applied"] is True
        assert config["status"] == "applied"
        assert config["implementation"] == "pybaselines.Baseline.asls"

    def test_asls_is_not_the_fake_endpoint_line(self):
        axis = np.linspace(10.0, 90.0, 400)
        true_background = 18.0 + 4.0 * np.sin(axis / 15.0)
        signal = true_background + _gaussian(axis, 33.2, 0.5, 160.0) + _gaussian(axis, 63.0, 0.5, 120.0)
        fake_line = np.linspace(float(signal[0]), float(signal[-1]), num=signal.size, endpoint=True)
        baseline = _estimate_xrd_baseline(signal, {"method": "asls", "lam": 1e5, "p": 0.01})
        assert not np.allclose(baseline, fake_line)
        # A real AsLS fit tracks the curved background; the endpoint line does not.
        rms_asls = float(np.sqrt(np.mean((baseline - true_background) ** 2)))
        rms_line = float(np.sqrt(np.mean((fake_line - true_background) ** 2)))
        assert rms_asls < rms_line

    def test_asls_params_normalized(self):
        signal = np.ones(200)
        config: dict = {"method": "asls", "lam": "bad", "p": 7.0}
        baseline = _estimate_xrd_baseline(signal, config)
        assert config["lam"] == pytest.approx(1e6)
        assert config["p"] == pytest.approx(0.01)
        np.testing.assert_allclose(baseline, als_baseline(np.arange(200.0), signal, lam=1e6, p=0.01))


class TestWavelengthGate:
    class _RecordingCloudClient:
        configured = True
        last_error = ""

        def __init__(self):
            self.search_calls = []

        def search(self, **kwargs):
            self.search_calls.append(kwargs)
            return None

    def test_reference_without_wavelength_keeps_raw_positions_only(self):
        entry = {
            "candidate_id": "no_lambda",
            "peaks": [{"position": 33.18, "intensity": 1.0}],
        }
        peaks = _extract_xrd_reference_peaks(entry)
        assert len(peaks) == 1
        assert peaks[0]["position"] == pytest.approx(33.18)
        assert "d_spacing" not in peaks[0]
        assert "reference_wavelength_angstrom" not in peaks[0]

    def test_reference_with_declared_wavelength_converts(self):
        entry = {
            "candidate_id": "with_lambda",
            "reference_wavelength_angstrom": 1.5406,
            "peaks": [{"position": 33.18, "intensity": 1.0}],
        }
        peaks = _extract_xrd_reference_peaks(entry)
        assert peaks[0]["reference_wavelength_angstrom"] == pytest.approx(1.5406)
        assert peaks[0]["d_spacing"] == pytest.approx(1.5406 / (2.0 * math.sin(math.radians(16.59))), rel=1e-6)

    def test_comparison_value_rejects_known_wavelength_mismatch(self):
        peak = {"position": 30.0, "reference_wavelength_angstrom": 2.2897}  # Co Ka, no d-spacing
        assert _resolve_xrd_comparison_value(
            peak, comparison_space="two_theta", wavelength_angstrom=1.5406
        ) is None
        # Same-wavelength positions still compare directly.
        peak_same = {"position": 30.0, "reference_wavelength_angstrom": 1.5406}
        assert _resolve_xrd_comparison_value(
            peak_same, comparison_space="two_theta", wavelength_angstrom=1.5406
        ) == pytest.approx(30.0)

    def test_missing_observed_wavelength_blocks_matching(self):
        dataset = _make_xrd_dataset()
        dataset.metadata.pop("xrd_wavelength_angstrom", None)
        outcome = execute_batch_template(
            dataset_key="xrd_missing_lambda_gate",
            dataset=dataset,
            analysis_type="XRD",
            workflow_template_id="xrd.general",
        )
        assert outcome["status"] == "saved"
        summary = outcome["record"]["summary"]
        assert summary["match_status"] == "not_run"
        assert summary["confidence_band"] == "not_run"
        assert summary["matching_blocked_reason"] == "xrd_two_theta_matching_requires_observed_wavelength"
        assert summary["caution_code"] == "xrd_matching_blocked_missing_wavelength"
        assert summary["candidate_count"] == 0
        # Reference candidates were still resolved and counted honestly.
        assert summary["reference_candidate_count"] >= 1
        mc = outcome["record"]["processing"]["method_context"]
        assert mc["xrd_matching_blocked_reason"] == "xrd_two_theta_matching_requires_observed_wavelength"

    def test_wavelength_gate_blocks_cloud_search_before_matching(self, monkeypatch):
        cloud_client = self._RecordingCloudClient()
        monkeypatch.setattr(
            "core.batch_runner.get_library_cloud_client", lambda: cloud_client
        )
        dataset = _make_xrd_dataset()
        dataset.metadata.pop("xrd_wavelength_angstrom", None)

        outcome = execute_batch_template(
            dataset_key="xrd_missing_lambda_cloud_gate",
            dataset=dataset,
            analysis_type="XRD",
            workflow_template_id="xrd.general",
        )

        summary = outcome["record"]["summary"]
        assert cloud_client.search_calls == []
        assert summary["match_status"] == "not_run"
        assert summary["confidence_band"] == "not_run"
        assert summary["matching_blocked_reason"] == (
            "xrd_two_theta_matching_requires_observed_wavelength"
        )
        assert summary["caution_code"] == "xrd_matching_blocked_missing_wavelength"

    def test_cloud_search_runs_with_valid_wavelength_provenance(self, monkeypatch):
        cloud_client = self._RecordingCloudClient()
        monkeypatch.setattr(
            "core.batch_runner.get_library_cloud_client", lambda: cloud_client
        )
        dataset = _make_xrd_dataset()

        outcome = execute_batch_template(
            dataset_key="xrd_valid_lambda_cloud_search",
            dataset=dataset,
            analysis_type="XRD",
            workflow_template_id="xrd.general",
        )

        assert outcome["status"] == "saved"
        assert len(cloud_client.search_calls) == 1
        assert cloud_client.search_calls[0]["payload"][
            "xrd_wavelength_angstrom"
        ] == pytest.approx(1.5406)
        assert outcome["record"]["summary"]["matching_blocked_reason"] == ""

    def test_position_only_reference_candidate_excluded_by_gate(self):
        dataset = _make_xrd_dataset()
        dataset.metadata["xrd_reference_library"] = [
            {
                "id": "lambda_less",
                "name": "No Wavelength Reference",
                "peaks": [
                    {"position": 18.37, "intensity": 0.62},
                    {"position": 33.18, "intensity": 1.0},
                ],
            }
        ]
        outcome = execute_batch_template(
            dataset_key="xrd_lambda_less_ref",
            dataset=dataset,
            analysis_type="XRD",
            workflow_template_id="xrd.general",
        )
        assert outcome["status"] == "saved"
        summary = outcome["record"]["summary"]
        assert summary["match_status"] in {"no_match", "matched"}
        assert summary["wavelength_gate_excluded_candidates"] >= 1
        assert summary["wavelength_gate_excluded_peaks"] >= 2
        row = next(r for r in outcome["record"]["rows"] if r["candidate_id"] == "lambda_less")
        evidence = row["evidence"]
        assert evidence["wavelength_compatible"] is False
        assert evidence["wavelength_excluded_peak_count"] == 2
        assert row["normalized_score"] == 0.0

    def test_declared_different_wavelength_reference_still_matches_via_d_spacing(self):
        # Reference declares Mo Ka (0.7107 A) positions for the same lattice as
        # the observed Cu Ka pattern; conversion through d-spacing must match.
        dataset = _make_xrd_dataset()
        mo_lambda = 0.7107
        cu_positions = [18.37, 33.18, 47.76, 63.52, 72.05]
        mo_positions = [
            math.degrees(2.0 * math.asin(mo_lambda / (2.0 * (1.5406 / (2.0 * math.sin(math.radians(p / 2.0)))))))
            for p in cu_positions
        ]
        dataset.metadata["xrd_reference_library"] = [
            {
                "id": "mo_phase_alpha",
                "name": "Phase Alpha (Mo)",
                "reference_wavelength_angstrom": mo_lambda,
                "peaks": [
                    {"position": pos, "intensity": inten}
                    for pos, inten in zip(mo_positions, [0.62, 1.0, 0.84, 0.51, 0.22])
                ],
            }
        ]
        outcome = execute_batch_template(
            dataset_key="xrd_mo_reference",
            dataset=dataset,
            analysis_type="XRD",
            workflow_template_id="xrd.general",
        )
        summary = outcome["record"]["summary"]
        assert summary["match_status"] == "matched"
        assert summary["top_phase_id"] == "mo_phase_alpha"
        assert outcome["record"]["rows"][0]["evidence"]["wavelength_compatible"] is True
        assert outcome["record"]["rows"][0]["evidence"]["reference_wavelengths_angstrom"] == [pytest.approx(mo_lambda)]

    def test_d_spacing_axis_dataset_matches_without_observed_wavelength(self):
        d_axis = np.linspace(1.2, 6.0, 800)
        signal = 12.0 + _gaussian(d_axis, 3.0, 0.02, 100.0) + _gaussian(d_axis, 2.1, 0.025, 70.0)
        dataset = ThermalDataset(
            data=pd.DataFrame({"temperature": d_axis, "signal": signal}),
            metadata={
                "sample_name": "DSpacingXRD",
                "xrd_axis_role": "d_spacing",
                "xrd_axis_unit": "angstrom",
                "xrd_reference_library": [
                    {
                        "id": "d_ref",
                        "name": "D Reference",
                        "peaks": [
                            {"d_spacing": 3.0, "intensity": 1.0},
                            {"d_spacing": 2.1, "intensity": 0.7},
                        ],
                    }
                ],
            },
            data_type="XRD",
            units={"temperature": "angstrom", "signal": "counts"},
            original_columns={"temperature": "d_spacing", "signal": "intensity"},
            file_path="",
        )
        outcome = execute_batch_template(
            dataset_key="xrd_d_axis",
            dataset=dataset,
            analysis_type="XRD",
            workflow_template_id="xrd.general",
        )
        summary = outcome["record"]["summary"]
        # d-spacing comparison is wavelength-independent on the observed side.
        assert summary["match_status"] in {"matched", "no_match"}
        assert summary["matching_blocked_reason"] == ""
        assert summary["candidate_count"] == 1


class TestScherrerEndToEnd:
    def test_batch_scherrer_computed_and_serialized(self):
        dataset = _make_xrd_dataset()
        outcome = execute_batch_template(
            dataset_key="xrd_scherrer",
            dataset=dataset,
            analysis_type="XRD",
            workflow_template_id="xrd.general",
            existing_processing={"analysis_steps": {"scherrer": {"enabled": True, "shape_factor": 0.9}}},
        )
        assert outcome["status"] == "saved"
        summary = outcome["record"]["summary"]
        assert summary["scherrer_enabled"] is True
        assert summary["scherrer_status"] == "computed"
        assert summary["scherrer_computed_count"] == summary["peak_count"]
        assert summary["scherrer_median_nm"] is not None
        assumptions = summary["scherrer_assumptions"]
        assert assumptions["wavelength_angstrom"] == pytest.approx(1.5406)
        assert assumptions["shape_factor_k"] == pytest.approx(0.9)
        assert assumptions["fwhm_units"] == "degree_2theta"
        assert assumptions["instrumental_broadening_status"] == "not_corrected"
        step = outcome["record"]["processing"]["analysis_steps"]["scherrer"]
        assert step["enabled"] is True
        assert step["status"] == "computed"
        for peak in outcome["state"]["peaks"]:
            assert peak["scherrer_status"] == "computed"
            assert peak["scherrer_crystallite_size_nm"] is not None
            assert peak["scherrer_fwhm_deg_2theta"] is not None

    def test_batch_scherrer_withheld_without_wavelength(self):
        dataset = _make_xrd_dataset()
        dataset.metadata.pop("xrd_wavelength_angstrom", None)
        outcome = execute_batch_template(
            dataset_key="xrd_scherrer_no_lambda",
            dataset=dataset,
            analysis_type="XRD",
            workflow_template_id="xrd.general",
            existing_processing={"analysis_steps": {"scherrer": {"enabled": True}}},
        )
        summary = outcome["record"]["summary"]
        assert summary["scherrer_status"] == "withheld"
        assert "wavelength" in summary["scherrer_withheld_reason"]
        assert summary["scherrer_assumptions"]["wavelength_angstrom"] is None

    def test_batch_asls_baseline_runs_real_fit(self):
        dataset = _make_xrd_dataset()
        outcome = execute_batch_template(
            dataset_key="xrd_asls",
            dataset=dataset,
            analysis_type="XRD",
            workflow_template_id="xrd.general",
            existing_processing={"signal_pipeline": {"baseline": {"method": "asls", "lam": 1e6, "p": 0.01}}},
        )
        assert outcome["status"] == "saved"
        baseline_step = outcome["record"]["processing"]["signal_pipeline"]["baseline"]
        assert baseline_step["method"] == "asls"
        assert baseline_step["status"] == "applied"
        assert baseline_step["lam"] == pytest.approx(1e6)
        baseline_curve = np.asarray(outcome["state"]["baseline"], dtype=float)
        signal = np.asarray(outcome["state"]["smoothed"], dtype=float)
        fake_line = np.linspace(float(signal[0]), float(signal[-1]), num=signal.size, endpoint=True)
        assert not np.allclose(baseline_curve, fake_line)
