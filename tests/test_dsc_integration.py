"""PR-15 tests: configurable DSC peak integration bounds + sensitivity.

Covers:
- integrate_peak_bounds windowed integration construction
- DSCProcessor.integrate_peaks: characterized / custom / custom_snapped modes
- enthalpy recomputed through the PR-9 beta-aware path
- bound-perturbation sensitivity record (NOT a metrological uncertainty)
- serialization round-trip of the integration record
- batch runner plumbing for the ``integration`` analysis-step section
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from core.dsc_processor import DSCProcessor
from core.peak_analysis import integrate_peak_bounds
from core.result_serialization import thermal_peak_from_dict, thermal_peak_to_dict
from core.units_dimensional import BASIS_BETA_CORRECTED

TEMPERATURES = np.arange(40.0, 220.5, 0.5)


def _gaussian(enthalpy_j_g: float, beta: float, sigma: float = 7.0, center: float = 130.0):
    """Peak whose analytic area equals ``enthalpy_j_g`` at the given rate."""
    amplitude = (enthalpy_j_g * beta / 60.0) / (sigma * np.sqrt(2.0 * np.pi))
    return amplitude * np.exp(-0.5 * ((TEMPERATURES - center) / sigma) ** 2)


def _two_peaks():
    sig = _gaussian(25.0, 10.0, sigma=6.0, center=110.0)
    sig = sig + _gaussian(15.0, 10.0, sigma=6.0, center=175.0)
    return sig


def _processor(signal, *, beta=10.0, source="W/g", beta_source="user", mass=None):
    return DSCProcessor(
        TEMPERATURES,
        signal,
        sample_mass=mass,
        heating_rate=beta,
        heating_rate_source=beta_source,
        signal_unit=source,
    )


# ---------------------------------------------------------------------------
# integrate_peak_bounds
# ---------------------------------------------------------------------------

class TestIntegratePeakBounds:
    def test_gaussian_area_matches_analytic(self):
        """Windowed integration over +/-4 sigma recovers ~99.99% of the area."""
        signal = _gaussian(25.0, 10.0)
        area = integrate_peak_bounds(TEMPERATURES, signal, 102.0, 158.0)
        expected = 25.0 * 10.0 / 60.0  # W/g * K
        assert area == pytest.approx(expected, rel=0.01)

    def test_degenerate_and_disjoint_windows_return_zero(self):
        signal = _gaussian(25.0, 10.0)
        assert integrate_peak_bounds(TEMPERATURES, signal, 130.0, 130.0) == 0.0
        assert integrate_peak_bounds(TEMPERATURES, signal, 200.0, 150.0) == 0.0
        # Window entirely below the measured range clamps to a degenerate
        # single point -> zero area, not a fabricated value.
        assert integrate_peak_bounds(TEMPERATURES, signal, -500.0, -400.0) == 0.0

    def test_sloped_local_baseline_is_subtracted(self):
        """A linear residual slope under the window must not inflate area."""
        baseline = 0.5 + 0.02 * (TEMPERATURES - 40.0)
        signal = baseline + _gaussian(25.0, 10.0)
        area = integrate_peak_bounds(TEMPERATURES, signal, 102.0, 158.0)
        expected = 25.0 * 10.0 / 60.0
        assert area == pytest.approx(expected, rel=0.01)


# ---------------------------------------------------------------------------
# DSCProcessor.integrate_peaks
# ---------------------------------------------------------------------------

class TestIntegratePeaks:
    def test_characterized_mode_uses_onset_endset(self):
        proc = _processor(_gaussian(25.0, 10.0))
        proc.find_peaks(direction="up")
        proc.integrate_peaks()

        peak = proc.get_result().peaks[0]
        assert peak.integration_mode == "characterized"
        assert peak.integration_bounds == pytest.approx(
            (peak.onset_temperature, peak.endset_temperature)
        )
        assert peak.integration_baseline == "local_linear_endpoints"
        # The area must equal the same construction recomputed directly.
        expected = integrate_peak_bounds(
            TEMPERATURES,
            proc.get_result().smoothed_signal,
            peak.onset_temperature,
            peak.endset_temperature,
        )
        assert peak.area == pytest.approx(expected, rel=1e-9)

    def test_custom_window_selects_only_enclosed_peak(self):
        proc = _processor(_two_peaks())
        proc.find_peaks(direction="up")
        proc.integrate_peaks(bounds=(95.0, 135.0))

        peaks = proc.get_result().peaks
        assert len(peaks) == 2
        left, right = sorted(peaks, key=lambda p: p.peak_temperature)
        assert left.integration_mode == "custom"
        assert left.integration_bounds == (95.0, 135.0)
        # The right peak apex is outside the window: untouched defaults.
        assert right.integration_mode is None
        assert right.integration_bounds is None

    def test_snap_to_characterized(self):
        proc = _processor(_gaussian(25.0, 10.0))
        proc.find_peaks(direction="up")
        # Loose window around the peak; snap replaces it with onset/endset.
        proc.integrate_peaks(bounds=(90.0, 170.0), snap_to_characterized=True)

        peak = proc.get_result().peaks[0]
        assert peak.integration_mode == "custom_snapped"
        assert peak.integration_bounds == pytest.approx(
            (peak.onset_temperature, peak.endset_temperature)
        )

    def test_snap_falls_back_to_custom_when_bounds_missing(self):
        """A peak without characterised bounds keeps the custom window."""
        proc = _processor(_gaussian(25.0, 10.0))
        proc.find_peaks(direction="up")
        peak = proc.get_result().peaks[0]
        # Simulate missing characterisation.
        proc._peaks[0].onset_temperature = None
        proc._peaks[0].endset_temperature = None
        proc.integrate_peaks(bounds=(95.0, 165.0), snap_to_characterized=True)

        peak = proc.get_result().peaks[0]
        assert peak.integration_mode == "custom"
        assert peak.integration_bounds == (95.0, 165.0)

    def test_enthalpy_recomputed_through_beta_path(self):
        """Re-integrated areas must flow through peak_area_to_enthalpy."""
        proc = _processor(_gaussian(25.0, 10.0))
        proc.find_peaks(direction="up")
        proc.integrate_peaks()

        peak = proc.get_result().peaks[0]
        assert peak.enthalpy_basis == BASIS_BETA_CORRECTED
        assert peak.enthalpy_withheld_reason is None
        # Enthalpy is exactly the PR-9 conversion of the new area.
        assert peak.enthalpy_j_g == pytest.approx(
            peak.area * 60.0 / 10.0, rel=1e-9
        )

    def test_wide_custom_window_recovers_analytic_enthalpy(self):
        """A ±4σ+ custom window recovers the full analytic enthalpy."""
        proc = _processor(_gaussian(25.0, 10.0))
        proc.find_peaks(direction="up")
        proc.integrate_peaks(bounds=(98.0, 162.0))

        peak = proc.get_result().peaks[0]
        assert peak.integration_mode == "custom"
        assert peak.enthalpy_j_g == pytest.approx(25.0, rel=0.05)

    def test_enthalpy_withheld_without_traceable_beta(self):
        proc = _processor(
            _gaussian(25.0, 10.0), beta=10.0, beta_source=None
        )
        proc.find_peaks(direction="up")
        proc.integrate_peaks()

        peak = proc.get_result().peaks[0]
        assert peak.area is not None
        assert peak.enthalpy_j_g is None
        assert peak.enthalpy_withheld_reason == "legacy_unknown"
        assert peak.integration_mode == "characterized"

    def test_sensitivity_record_is_bound_perturbation_not_uncertainty(self):
        proc = _processor(_gaussian(25.0, 10.0))
        proc.find_peaks(direction="up")
        proc.integrate_peaks()

        sens = proc.get_result().peaks[0].integration_sensitivity
        assert sens is not None
        assert sens["method"] == "bound_perturbation"
        assert sens["delta_temperature"] > 0.0
        assert sens["area_delta_abs"] >= 0.0
        assert sens["area_delta_rel"] is not None and sens["area_delta_rel"] >= 0.0
        # The record states what it is — and what it is not.
        assert "not" in sens["interpretation"].lower()
        assert "uncertainty" in sens["interpretation"].lower()
        # Enthalpy-scale sensitivity carried through the same conversion.
        assert sens["enthalpy_delta_j_g"] == pytest.approx(
            sens["area_delta_abs"] * 60.0 / 10.0, rel=1e-9
        )

    def test_sensitivity_grows_with_perturbation(self):
        """Larger bound perturbation -> larger reported sensitivity."""
        small = _processor(_gaussian(25.0, 10.0))
        small.find_peaks(direction="up")
        small.integrate_peaks(sensitivity_delta_fraction=0.01)
        large = _processor(_gaussian(25.0, 10.0))
        large.find_peaks(direction="up")
        large.integrate_peaks(sensitivity_delta_fraction=0.10)

        s_small = small.get_result().peaks[0].integration_sensitivity
        s_large = large.get_result().peaks[0].integration_sensitivity
        assert s_large["area_delta_abs"] > s_small["area_delta_abs"]

    def test_invalid_delta_fraction_rejected(self):
        proc = _processor(_gaussian(25.0, 10.0))
        proc.find_peaks(direction="up")
        with pytest.raises(ValueError):
            proc.integrate_peaks(sensitivity_delta_fraction=0.75)

    def test_invalid_bounds_rejected(self):
        proc = _processor(_gaussian(25.0, 10.0))
        proc.find_peaks(direction="up")
        with pytest.raises(ValueError):
            proc.integrate_peaks(bounds=(150.0, 100.0))
        with pytest.raises(ValueError):
            proc.integrate_peaks(bounds=(float("nan"), 150.0))

    def test_no_peaks_warns_and_records(self):
        proc = _processor(_gaussian(25.0, 10.0))
        with pytest.warns(RuntimeWarning, match="nothing to integrate"):
            proc.integrate_peaks()
        steps = proc.get_result().metadata["steps"]
        assert steps[-1]["outcome"] == "no_peaks"

    def test_peak_without_characterized_bounds_keeps_fwhm(self):
        proc = _processor(_gaussian(25.0, 10.0))
        proc.find_peaks(direction="up")
        proc._peaks[0].onset_temperature = None
        proc._peaks[0].endset_temperature = None
        proc.integrate_peaks()
        peak = proc.get_result().peaks[0]
        assert peak.integration_mode == "fwhm_window"
        assert peak.integration_bounds is None


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestIntegrationSerialization:
    def test_peak_dict_roundtrip_preserves_integration(self):
        proc = _processor(_gaussian(25.0, 10.0))
        proc.find_peaks(direction="up")
        proc.integrate_peaks(bounds=(95.0, 165.0))
        peak = proc.get_result().peaks[0]

        payload = thermal_peak_to_dict(peak)
        assert payload["integration_mode"] == "custom"
        assert payload["integration_bounds"] == pytest.approx([95.0, 165.0])
        assert payload["integration_baseline"] == "local_linear_endpoints"
        assert payload["integration_sensitivity"]["method"] == "bound_perturbation"

        restored = thermal_peak_from_dict(payload)
        assert restored.integration_mode == "custom"
        assert restored.integration_bounds == pytest.approx((95.0, 165.0))
        assert restored.integration_baseline == "local_linear_endpoints"
        assert restored.integration_sensitivity["area_delta_abs"] == pytest.approx(
            peak.integration_sensitivity["area_delta_abs"]
        )

    def test_legacy_peak_payload_has_no_integration_fields(self):
        """Pre-PR-15 payloads must not grow integration claims."""
        peak = thermal_peak_from_dict(
            {"peak_index": 0, "peak_temperature": 130.0, "peak_signal": 1.2, "area": 4.5}
        )
        assert peak.integration_mode is None
        assert peak.integration_bounds is None
        payload = thermal_peak_to_dict(peak)
        assert "integration_mode" not in payload
        assert "integration_bounds" not in payload


# ---------------------------------------------------------------------------
# Batch-runner plumbing
# ---------------------------------------------------------------------------

def _dataset(signal, *, beta=10.0, beta_source="user", unit="W/g", mass=None):
    import pandas as pd

    return SimpleNamespace(
        data=pd.DataFrame({"temperature": TEMPERATURES, "signal": signal}),
        metadata={
            "sample_mass": mass,
            "heating_rate": beta,
            "heating_rate_source": beta_source,
            "sample_name": "integration-sample",
        },
        units={"temperature": "°C", "signal": unit},
        data_type="DSC",
    )


def _run_batch(dataset, *, integration):
    from core.batch_runner import execute_batch_template
    from core.processing_schema import (
        ensure_processing_payload,
        update_processing_step,
    )

    processing = ensure_processing_payload(
        {"workflow_template_id": "dsc.general"}, analysis_type="DSC"
    )
    processing = update_processing_step(
        processing, "integration", integration, analysis_type="DSC"
    )
    return execute_batch_template(
        dataset_key="ds1",
        dataset=dataset,
        analysis_type="DSC",
        workflow_template_id="dsc.general",
        existing_processing=processing,
    )


class TestBatchRunnerIntegration:
    def test_disabled_integration_preserves_default_windows(self):
        dataset = _dataset(_gaussian(25.0, 10.0))
        execution = _run_batch(dataset, integration={"enabled": False})

        assert execution["status"] == "saved"
        section = execution["processing"]["analysis_steps"]["integration"]
        assert section["enabled"] is False
        assert section["outcome"] == "disabled"
        for row in execution["record"]["rows"]:
            assert row["integration_mode"] is None

    def test_custom_bounds_reach_record_rows(self):
        dataset = _dataset(_gaussian(25.0, 10.0))
        execution = _run_batch(
            dataset,
            integration={
                "enabled": True,
                "bounds": [95.0, 165.0],
                "snap_to_characterized": False,
                "sensitivity_delta_fraction": 0.02,
            },
        )

        assert execution["status"] == "saved"
        section = execution["processing"]["analysis_steps"]["integration"]
        assert section["enabled"] is True
        assert section["bounds"] == [95.0, 165.0]
        assert section["integrated_count"] >= 1

        rows = [r for r in execution["record"]["rows"] if r["integration_mode"] == "custom"]
        assert rows, "expected at least one custom-integrated peak row"
        row = rows[0]
        assert row["integration_bounds"] == pytest.approx([95.0, 165.0])
        assert row["integration_baseline"] == "local_linear_endpoints"
        assert row["integration_sensitivity"]["method"] == "bound_perturbation"
        assert row["enthalpy_basis"] == BASIS_BETA_CORRECTED
        assert row["enthalpy_j_g"] == pytest.approx(25.0, rel=0.10)

    def test_characterized_mode_through_overrides(self):
        dataset = _dataset(_gaussian(25.0, 10.0))
        execution = _run_batch(dataset, integration={"enabled": True, "bounds": None})

        rows = [
            r for r in execution["record"]["rows"]
            if r["integration_mode"] == "characterized"
        ]
        assert rows
        for row in rows:
            assert row["integration_bounds"] == pytest.approx(
                [row["onset_temperature"], row["endset_temperature"]]
            )
