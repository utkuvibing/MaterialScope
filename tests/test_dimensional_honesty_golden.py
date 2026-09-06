"""PR-9 golden gates: dimensional honesty for ΔCp and peak enthalpy."""

from __future__ import annotations

import numpy as np
import pytest

from core.dsc_processor import DSCProcessor, GlassTransition
from core.peak_analysis import ThermalPeak, characterize_peaks, find_thermal_peaks
from core.project_io import _deserialize_dsc_state, _serialize_dsc_state
from core.result_serialization import (
    glass_transition_from_dict,
    glass_transition_to_dict,
    thermal_peak_from_dict,
)
from core.units_dimensional import BASIS_BETA_CORRECTED, BASIS_LEGACY_UNKNOWN

TEMPERATURES = np.arange(40.0, 200.5, 0.5)


def _gaussian_peak(enthalpy_j_g: float, beta: float, sigma: float = 7.0, center: float = 130.0):
    """Peak whose analytic area equals ``enthalpy_j_g`` at the given rate.

    Mirrors generate_test_data.py: A = H * beta / 60 / (sigma * sqrt(2pi)).
    """
    amplitude = (enthalpy_j_g * beta / 60.0) / (sigma * np.sqrt(2.0 * np.pi))
    return amplitude * np.exp(-0.5 * ((TEMPERATURES - center) / sigma) ** 2)


def _tanh_step(amplitude: float = 0.08, center: float = 120.0, width: float = 4.0):
    return amplitude * np.tanh((TEMPERATURES - center) / width)


def _copy_peaks(peaks):
    """Independent copies: characterize_peaks mutates the peaks it is given."""
    return [
        ThermalPeak(
            peak_index=p.peak_index,
            peak_temperature=p.peak_temperature,
            peak_signal=p.peak_signal,
        )
        for p in peaks
    ]


def _run(signal, *, beta, source, sample_mass=None, baseline=None):
    processor = DSCProcessor(
        TEMPERATURES,
        signal,
        sample_mass=sample_mass,
        heating_rate=beta,
        heating_rate_source="user",
        signal_unit=source,
    )
    processor.smooth(method="savgol", window_length=11, polyorder=3)
    processor.normalize()
    if baseline is not None:
        processor.correct_baseline(method=baseline)
    return processor


class TestKnownBetaEnthalpy:
    @pytest.mark.parametrize("beta", [10.0, 20.0])
    def test_recovers_input_enthalpy(self, beta):
        """β-scaling proof: the same J/g must come back at 10 and 20 K/min."""
        signal = _gaussian_peak(25.0, beta)
        processor = _run(signal, beta=beta, source="W/g")
        processor.find_peaks(direction="up")

        peaks = processor.get_result().peaks
        assert peaks, "expected at least one characterised peak"
        peak = peaks[0]
        assert peak.enthalpy_basis == BASIS_BETA_CORRECTED
        assert peak.enthalpy_withheld_reason is None
        # 5%: the integration window is 2x FWHM, not the full Gaussian tail.
        assert peak.enthalpy_j_g == pytest.approx(25.0, rel=0.05)

    def test_area_scales_with_beta_but_enthalpy_does_not(self):
        """The whole point: area changes with β, corrected enthalpy does not."""
        slow = _run(_gaussian_peak(25.0, 10.0), beta=10.0, source="W/g")
        slow.find_peaks(direction="up")
        fast = _run(_gaussian_peak(25.0, 20.0), beta=20.0, source="W/g")
        fast.find_peaks(direction="up")

        slow_peak = slow.get_result().peaks[0]
        fast_peak = fast.get_result().peaks[0]
        assert fast_peak.area == pytest.approx(2.0 * slow_peak.area, rel=0.05)
        assert fast_peak.enthalpy_j_g == pytest.approx(slow_peak.enthalpy_j_g, rel=0.02)


class TestKnownBetaDeltaCp:
    @pytest.mark.parametrize("beta", [10.0, 20.0])
    def test_converted_step_matches_60_over_beta(self, beta):
        signal = _tanh_step(amplitude=0.08)
        processor = _run(signal, beta=beta, source="W/g", baseline="linear")
        processor.detect_glass_transition(region=(95.0, 148.0))

        transitions = processor.get_result().glass_transitions
        assert transitions, "expected a detected glass transition"
        tg = transitions[0]
        assert tg.delta_cp_basis == BASIS_BETA_CORRECTED
        expected = tg.heat_flow_step * 60.0 / beta
        assert tg.delta_cp_j_g_k == pytest.approx(expected, rel=1e-6)

    def test_raw_step_stays_raw_when_beta_unverified(self):
        """A step is never silently promoted to a corrected ΔCp."""
        processor = DSCProcessor(
            TEMPERATURES,
            _tanh_step(),
            heating_rate=10.0,
            heating_rate_source=None,  # legacy: no provenance
            signal_unit="W/g",
        )
        processor.detect_glass_transition(region=(95.0, 148.0))
        tg = processor.get_result().glass_transitions[0]
        assert tg.delta_cp_j_g_k is None
        assert tg.delta_cp_basis != BASIS_BETA_CORRECTED
        assert tg.delta_cp_withheld_reason == "legacy_unknown"
        # The measured quantity is still reported honestly.
        assert tg.heat_flow_step > 0.0


class TestNormalizedOnceEquivalence:
    def test_raw_mw_plus_mass_matches_already_specific_w_per_g(self):
        """The mass regression: raw mW + mass must be divided exactly once."""
        mass = 5.0
        specific = _gaussian_peak(25.0, 10.0)
        raw = specific * mass  # same physics expressed as raw power

        raw_proc = _run(raw, beta=10.0, source="mW", sample_mass=mass)
        raw_proc.find_peaks(direction="up")
        specific_proc = _run(specific, beta=10.0, source="W/g")
        specific_proc.find_peaks(direction="up")

        raw_peak = raw_proc.get_result().peaks[0]
        specific_peak = specific_proc.get_result().peaks[0]

        assert raw_proc.normalization_applied is True
        assert raw_proc.working_signal_unit == "mW/mg"
        assert specific_proc.normalization_applied is False
        assert specific_proc.working_signal_unit == "W/g"

        assert raw_peak.enthalpy_j_g == pytest.approx(
            specific_peak.enthalpy_j_g, rel=1e-6
        )
        assert raw_peak.enthalpy_basis == BASIS_BETA_CORRECTED

    def test_w_source_uses_thousand_factor(self):
        """W/mg is 1000x mW/mg — the error a class-only design would make."""
        mass = 5.0
        specific_mw = _gaussian_peak(25.0, 10.0)
        as_w = specific_mw * mass / 1000.0  # same power expressed in W

        proc = _run(as_w, beta=10.0, source="W", sample_mass=mass)
        proc.find_peaks(direction="up")
        peak = proc.get_result().peaks[0]
        assert proc.working_signal_unit == "W/mg"
        assert peak.enthalpy_j_g == pytest.approx(25.0, rel=0.05)

    def test_second_normalize_is_noop(self):
        processor = DSCProcessor(
            TEMPERATURES,
            _gaussian_peak(25.0, 10.0),
            sample_mass=5.0,
            heating_rate=10.0,
            heating_rate_source="user",
            signal_unit="mW",
        )
        processor.normalize()
        once = processor.get_result().smoothed_signal.copy()
        first_unit, first_applied = (
            processor.working_signal_unit,
            processor.normalization_applied,
        )
        processor.normalize()
        assert processor.working_signal_unit == first_unit
        assert processor.normalization_applied is first_applied
        np.testing.assert_allclose(processor.get_result().smoothed_signal, once)


class TestConversionGating:
    @pytest.mark.parametrize(
        "beta,source",
        [
            (None, "user"),
            (0.0, "user"),
            (-5.0, "user"),
            (float("nan"), "user"),
            (10.0, None),
            (10.0, "ui_default"),
        ],
    )
    def test_unusable_beta_withholds_enthalpy(self, beta, source):
        signal = _gaussian_peak(25.0, 10.0)
        processor = DSCProcessor(
            TEMPERATURES,
            signal,
            heating_rate=beta,
            heating_rate_source=source,
            signal_unit="W/g",
        )
        processor.find_peaks(direction="up")
        peaks = processor.get_result().peaks
        if not peaks:
            pytest.skip("no peak detected for this configuration")
        for peak in peaks:
            assert peak.enthalpy_j_g is None
            assert peak.enthalpy_withheld_reason is not None
            assert peak.area is not None

    def test_raw_power_without_mass_withholds(self):
        processor = DSCProcessor(
            TEMPERATURES,
            _gaussian_peak(25.0, 10.0),
            heating_rate=10.0,
            heating_rate_source="user",
            signal_unit="mW",
        )
        processor.find_peaks(direction="up")
        peaks = processor.get_result().peaks
        if not peaks:
            pytest.skip("no peak detected for this configuration")
        for peak in peaks:
            assert peak.enthalpy_j_g is None
            assert peak.enthalpy_withheld_reason == "signal_not_mass_normalized"

    def test_arbitrary_units_withhold(self):
        processor = DSCProcessor(
            TEMPERATURES,
            _gaussian_peak(25.0, 10.0),
            sample_mass=5.0,
            heating_rate=10.0,
            heating_rate_source="user",
            signal_unit="a.u.",
        )
        processor.normalize()
        processor.find_peaks(direction="up")
        peaks = processor.get_result().peaks
        if not peaks:
            pytest.skip("no peak detected for this configuration")
        for peak in peaks:
            assert peak.enthalpy_j_g is None
            assert peak.enthalpy_withheld_reason == "signal_unit_unusable"


class TestNoDoubleSubtraction:
    """A non-zero baseline must not be subtracted twice (PR-8 handoff)."""

    def _peak_on_sloped_baseline(self):
        baseline = 2.0 + 0.03 * (TEMPERATURES - 40.0)
        amplitude, sigma, center = 1.5, 6.0, 120.0
        peak = amplitude * np.exp(-0.5 * ((TEMPERATURES - center) / sigma) ** 2)
        return baseline + peak, baseline, amplitude, sigma

    def test_dsc_area_height_and_fwhm_are_undistorted(self):
        signal, _baseline, amplitude, sigma = self._peak_on_sloped_baseline()
        processor = DSCProcessor(
            TEMPERATURES, signal, signal_unit="W/g", heating_rate=10.0,
            heating_rate_source="user",
        )
        processor.correct_baseline(method="linear")
        processor.find_peaks(direction="up")

        peak = processor.get_result().peaks[0]
        # Analytical area of the Gaussian: A * sigma * sqrt(2*pi).
        expected_area = amplitude * sigma * np.sqrt(2.0 * np.pi)
        assert peak.area == pytest.approx(expected_area, rel=0.10)
        assert peak.height == pytest.approx(amplitude, rel=0.10)
        assert peak.fwhm == pytest.approx(2.3548 * sigma, rel=0.20)

    def test_dta_call_site_does_not_double_subtract(self):
        """Same defect, DTA path: corrected signal must pair with a zero baseline."""
        signal, baseline, amplitude, sigma = self._peak_on_sloped_baseline()
        raw_peaks = find_thermal_peaks(TEMPERATURES, signal - baseline, direction="up")
        assert raw_peaks, "expected a detected peak"

        corrected = signal - baseline
        # characterize_peaks mutates in place, so each pairing needs its
        # own copies or the second call overwrites the first result.
        buggy = characterize_peaks(
            TEMPERATURES, corrected, _copy_peaks(raw_peaks), baseline=baseline
        )
        fixed = characterize_peaks(
            TEMPERATURES,
            corrected,
            _copy_peaks(raw_peaks),
            baseline=np.zeros_like(corrected),
        )

        expected_area = amplitude * sigma * np.sqrt(2.0 * np.pi)
        assert fixed[0].area == pytest.approx(expected_area, rel=0.10)
        # The bug materially changes the result, so the guard is meaningful.
        assert buggy[0].area != pytest.approx(fixed[0].area, rel=0.10)


class TestLegacyPayloads:
    def test_legacy_tg_payload_is_not_corrected_deltacp(self):
        payload = {
            "tg_midpoint": 120.0,
            "tg_onset": 115.0,
            "tg_endset": 125.0,
            "delta_cp": 0.12,  # pre-PR-9: unlabeled, unknown provenance
        }
        tg = glass_transition_from_dict(payload)
        assert tg.delta_cp_basis == BASIS_LEGACY_UNKNOWN
        assert tg.delta_cp_j_g_k is None
        assert tg.delta_cp_withheld_reason == "legacy_unknown"
        # Preserved as the step it actually is, not discarded.
        assert tg.heat_flow_step == pytest.approx(0.12)

        serialized = glass_transition_to_dict(tg)
        assert "delta_cp" not in serialized, "legacy step must not re-emit as delta_cp"
        assert serialized["heat_flow_step"] == pytest.approx(0.12)

    def test_legacy_peak_area_is_not_enthalpy(self):
        payload = {
            "peak_index": 0,
            "peak_temperature": 130.0,
            "peak_signal": 1.2,
            "area": 4.5,  # pre-PR-9: temperature-domain area, never J/g
        }
        peak = thermal_peak_from_dict(payload)
        assert peak.enthalpy_basis == BASIS_LEGACY_UNKNOWN
        assert peak.enthalpy_j_g is None
        assert peak.area == pytest.approx(4.5)

    def test_archive_roundtrip_preserves_legacy_flags(self):
        state = {
            "smoothed": list(TEMPERATURES),
            "baseline": None,
            "corrected": list(TEMPERATURES),
            "peaks": [
                ThermalPeak(
                    peak_index=0,
                    peak_temperature=130.0,
                    peak_signal=1.2,
                    area=4.5,
                )
            ],
            "glass_transitions": [
                GlassTransition(
                    tg_midpoint=120.0,
                    tg_onset=115.0,
                    tg_endset=125.0,
                    heat_flow_step=0.12,
                )
            ],
            "processing": {},
        }
        restored = _deserialize_dsc_state(_serialize_dsc_state(state))

        peak = restored["peaks"][0]
        assert peak.enthalpy_j_g is None
        assert peak.enthalpy_basis == BASIS_LEGACY_UNKNOWN
        assert peak.area == pytest.approx(4.5)

        tg = restored["glass_transitions"][0]
        assert tg.delta_cp_j_g_k is None
        assert tg.delta_cp_basis == BASIS_LEGACY_UNKNOWN
        assert tg.heat_flow_step == pytest.approx(0.12)

    def test_corrected_payload_roundtrips(self):
        tg = GlassTransition(
            tg_midpoint=120.0,
            tg_onset=115.0,
            tg_endset=125.0,
            heat_flow_step=0.08,
            delta_cp_j_g_k=0.48,
            delta_cp_basis=BASIS_BETA_CORRECTED,
        )
        payload = glass_transition_to_dict(tg)
        assert payload["delta_cp"] == pytest.approx(0.48)

        restored = glass_transition_from_dict(payload)
        assert restored.delta_cp_basis == BASIS_BETA_CORRECTED
        assert restored.delta_cp_j_g_k == pytest.approx(0.48)
