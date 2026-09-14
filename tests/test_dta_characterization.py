"""PR-11: DTA characterization — reuse characterize_peaks, fix documented-kwarg crashes.

Covers:
- DTAProcessor.find_peaks populates onset/endset/area/FWHM/height via
  core.peak_analysis.characterize_peaks.
- Documented kwargs (min_width, rel_height, height, distance, width,
  min_peak_height) work without crashing.
- Unknown kwargs raise a named TypeError instead of crashing inside scipy.
- process() routes stage-scoped kwargs to the correct stage only.
- PR-8 sign-convention behaviour (direction tags, unknown polarity) preserved.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.dta_processor import DTAProcessor
from core.peak_analysis import ThermalPeak, characterize_peaks, compute_fwhm


def _dta_signal():
    """Two clearly separated events: endo trough then exo peak (exo-up frame)."""
    t = np.linspace(30.0, 400.0, 1500)
    signal = (
        0.0003 * (t - 30.0)
        - 1.4 * np.exp(-0.5 * ((t - 140.0) / 18.0) ** 2)   # endotherm (down)
        + 1.8 * np.exp(-0.5 * ((t - 290.0) / 20.0) ** 2)  # exotherm (up)
    )
    return t, signal


class TestCharacterizedPeaks:
    def test_find_peaks_populates_characterized_fields(self):
        t, s = _dta_signal()
        result = DTAProcessor(t, s).process(baseline_method="linear", prominence=0.3)

        assert len(result.peaks) == 2
        for peak in result.peaks:
            assert isinstance(peak, ThermalPeak)
            assert peak.onset_temperature is not None
            assert peak.endset_temperature is not None
            assert peak.area is not None and np.isfinite(peak.area)
            assert peak.fwhm is not None and peak.fwhm > 0
            assert peak.height is not None and np.isfinite(peak.height)

    def test_endo_peak_has_negative_signed_height_and_area(self):
        t, s = _dta_signal()
        result = DTAProcessor(t, s).process(baseline_method="linear", prominence=0.3)

        endo = next(p for p in result.peaks if getattr(p, "direction", "") == "endo")
        assert endo.height < 0
        assert endo.area < 0
        assert endo.fwhm > 0  # PR-11: no longer a degenerate ~0 for down-peaks

    def test_batch_style_manual_pipeline_also_characterizes(self):
        t, s = _dta_signal()
        processor = (
            DTAProcessor(t, s)
            .smooth(method="savgol", window_length=11, polyorder=3)
            .correct_baseline(method="linear")
            .find_peaks()
        )
        result = processor.get_result()
        assert all(p.height is not None for p in result.peaks)
        assert all(p.area is not None for p in result.peaks)


class TestDocumentedKwargs:
    def test_min_width_kwarg_no_longer_crashes(self):
        t, s = _dta_signal()
        result = DTAProcessor(t, s).process(baseline_method="linear", prominence=0.3, min_width=5)
        assert len(result.peaks) == 2

    def test_rel_height_kwarg_no_longer_crashes(self):
        t, s = _dta_signal()
        result = DTAProcessor(t, s).process(baseline_method="linear", prominence=0.3, rel_height=0.8)
        assert len(result.peaks) == 2
        assert all(p.fwhm is not None for p in result.peaks)

    def test_min_peak_height_filters_by_absolute_height(self):
        t, s = _dta_signal()
        # 1.5 keeps only the exo event (height ~1.8); the endo event
        # (~1.4 abs) would previously survive an unsigned comparison on a
        # negative height — abs() now applies to both directions.
        result = DTAProcessor(t, s).process(baseline_method="linear", prominence=0.3, min_peak_height=1.5)
        assert len(result.peaks) == 1
        assert result.peaks[0].direction == "exo"

    def test_height_distance_width_kwargs_pass_through(self):
        t, s = _dta_signal()
        result = DTAProcessor(t, s).process(baseline_method="linear", prominence=0.3, peak_kwargs={"distance": 40, "width": 3})
        assert len(result.peaks) == 2

    def test_find_peaks_direct_kwargs(self):
        t, s = _dta_signal()
        processor = DTAProcessor(t, s).find_peaks(
            prominence=0.1,
            min_width=4,
            rel_height=0.7,
            height=0.05,
            distance=30,
            min_peak_height=0.2,
        )
        assert processor.get_result().peaks

    def test_unknown_kwarg_raises_named_typeerror(self):
        t, s = _dta_signal()
        with pytest.raises(TypeError, match="bogus_option"):
            DTAProcessor(t, s).find_peaks(bogus_option=1)

    def test_process_unknown_kwarg_raises_named_typeerror(self):
        t, s = _dta_signal()
        with pytest.raises(TypeError, match="definitely_not_a_kwarg"):
            DTAProcessor(t, s).process(baseline_method="linear", definitely_not_a_kwarg=2)

    def test_process_routes_stage_kwargs_to_the_right_stage(self):
        t, s = _dta_signal()
        # window_length/polyorder belong to smooth, lam/p to baseline; the
        # historical implementation forwarded the same dict to every stage,
        # which crashed at find_thermal_peaks.
        result = DTAProcessor(t, s).process(baseline_method="linear", 
            prominence=0.3,
            window_length=15,
            polyorder=3,
            lam=1e5,
            p=0.02,
        )
        assert len(result.peaks) == 2

    def test_process_explicit_stage_dicts(self):
        t, s = _dta_signal()
        result = DTAProcessor(t, s).process(baseline_method="linear", 
            prominence=0.3,
            smooth_kwargs={"window_length": 13, "polyorder": 2},
            baseline_kwargs={"lam": 5e4},
            peak_kwargs={"distance": 25},
        )
        assert len(result.peaks) == 2


def _dta_shoulder_ripple_signal():
    """Two broad exotherms, one small separated event, three flank dips.

    The dips sit on the flanks of the large peaks, so their prominence is
    large (deep key cols on both sides) while their own amplitude is
    < 3 % of the signal range.  This mirrors the tracked mendeley DTA
    samples where auto detection reported ~12 events, half of them
    sub-1 %-amplitude shoulder ripples.
    """
    t = np.linspace(20.0, 210.0, 4000)
    signal = (
        0.9 * np.exp(-0.5 * ((t - 60.0) / 8.0) ** 2)
        + 0.7 * np.exp(-0.5 * ((t - 140.0) / 9.0) ** 2)
        + 0.07 * np.exp(-0.5 * ((t - 185.0) / 4.0) ** 2)   # small real event
        - 0.02 * np.exp(-0.5 * ((t - 78.0) / 2.0) ** 2)    # flank dip
        - 0.015 * np.exp(-0.5 * ((t - 115.0) / 2.5) ** 2)  # flank dip
        - 0.012 * np.exp(-0.5 * ((t - 160.0) / 2.0) ** 2)  # flank dip
    )
    return t, signal


class TestAutoProminenceAmplitudeFloor:
    """Auto mode (prominence=None) derives a scale-relative amplitude floor.

    Prominence alone cannot reject dips between large excursions — their
    key cols reach deep, so a dip of |height| ~ 1 % of the range can carry
    > 50 % of the range in prominence.  The automatic floor filters on
    characterised amplitude instead.
    """

    def test_auto_mode_suppresses_shoulder_ripples(self):
        t, s = _dta_shoulder_ripple_signal()
        result = (
            DTAProcessor(t, s)
            .smooth()
            .find_peaks(prominence=None, distance=1)
            .get_result()
        )
        temps = [p.peak_temperature for p in result.peaks]
        # Three real events retained; none of the ~2 %-scale dips
        # (they surface near ~113.5 and ~172.5 under sensitive settings).
        assert any(abs(tp - 60.0) < 5 for tp in temps)
        assert any(abs(tp - 140.0) < 5 for tp in temps)
        assert any(abs(tp - 185.0) < 5 for tp in temps)
        assert not any(abs(tp - 113.5) < 4 for tp in temps)
        assert not any(abs(tp - 172.5) < 4 for tp in temps)

    def test_auto_mode_keeps_small_real_event(self):
        t, s = _dta_shoulder_ripple_signal()
        result = (
            DTAProcessor(t, s)
            .smooth()
            .find_peaks(prominence=None, distance=1)
            .get_result()
        )
        small = [p for p in result.peaks if abs(p.peak_temperature - 185.0) < 5]
        assert len(small) == 1
        assert abs(small[0].height) > 0.04

    def test_explicit_prominence_keeps_legacy_sensitivity(self):
        """Explicit prominence with no min_peak_height preserves the
        previous behaviour — the user asked for sensitive detection."""
        t, s = _dta_shoulder_ripple_signal()
        result = (
            DTAProcessor(t, s)
            .smooth()
            .find_peaks(prominence=0.005, distance=1)
            .get_result()
        )
        temps = [p.peak_temperature for p in result.peaks]
        assert any(abs(tp - 113.5) < 4 for tp in temps)

    def test_explicit_min_peak_height_overrides_auto_floor(self):
        t, s = _dta_shoulder_ripple_signal()
        result = (
            DTAProcessor(t, s)
            .smooth()
            .find_peaks(prominence=None, min_peak_height=0.5, distance=1)
            .get_result()
        )
        temps = [p.peak_temperature for p in result.peaks]
        assert any(abs(tp - 60.0) < 5 for tp in temps)
        assert any(abs(tp - 140.0) < 5 for tp in temps)
        assert not any(abs(tp - 185.0) < 5 for tp in temps)  # below 0.5 floor


class TestSyntheticSampleAutoDetection:
    """Regression on generated DTA samples: auto detection must not report
    sub-1 %-amplitude shoulder dips as thermal events."""

    @staticmethod
    def _run_sample(path):
        from core.data_io import read_thermal_data

        ds = read_thermal_data(path)
        t = np.asarray(ds.data["temperature"], dtype=float)
        s = np.asarray(ds.data["signal"], dtype=float)
        return (
            DTAProcessor(t, s)
            .smooth()
            .correct_baseline()
            .find_peaks(prominence=None, distance=1)
            .get_result()
        )

    def test_dta_5c_reports_only_strong_events(self):
        from synthetic_samples import dta_events_path

        result = self._run_sample(dta_events_path("5c"))
        heights = [abs(p.height) for p in result.peaks]
        assert len(result.peaks) == 6
        assert min(heights) > 0.015
        assert all(p.direction == "exo" for p in result.peaks)

    def test_dta_10c_reports_only_strong_events(self):
        from synthetic_samples import dta_events_path

        result = self._run_sample(dta_events_path("10c"))
        heights = [abs(p.height) for p in result.peaks]
        assert len(result.peaks) == 5
        assert min(heights) > 0.02


class TestSignConventionPreserved:
    def test_canonical_exo_up_direction_tags(self):
        t, s = _dta_signal()
        result = DTAProcessor(t, s, sign_convention="exo_up").process(baseline_method="linear", prominence=0.3)
        directions = {p.direction for p in result.peaks}
        assert directions == {"exo", "endo"}

    def test_unknown_polarity_withholds_direction(self):
        t, s = _dta_signal()
        result = DTAProcessor(t, s, sign_convention="unknown").process(baseline_method="linear", prominence=0.3)
        assert all(getattr(p, "direction", "unknown") == "unknown" for p in result.peaks)


class TestComputeFwhmDirectionAware:
    def test_down_peak_fwhm_is_nonzero(self):
        t = np.linspace(0.0, 100.0, 500)
        s = -2.0 * np.exp(-0.5 * ((t - 50.0) / 8.0) ** 2)
        idx = int(np.argmin(s))
        fwhm = compute_fwhm(t, s, idx, baseline_value=0.0)
        assert fwhm == pytest.approx(2.3548 * 8.0, rel=0.10)

    def test_up_peak_fwhm_unchanged(self):
        t = np.linspace(0.0, 100.0, 500)
        s = 2.0 * np.exp(-0.5 * ((t - 50.0) / 8.0) ** 2)
        idx = int(np.argmax(s))
        fwhm = compute_fwhm(t, s, idx, baseline_value=0.0)
        assert fwhm == pytest.approx(2.3548 * 8.0, rel=0.10)

    def test_rel_height_changes_measured_width(self):
        t = np.linspace(0.0, 100.0, 500)
        s = 2.0 * np.exp(-0.5 * ((t - 50.0) / 8.0) ** 2)
        idx = int(np.argmax(s))
        narrow = compute_fwhm(t, s, idx, baseline_value=0.0, rel_height=0.8)
        wide = compute_fwhm(t, s, idx, baseline_value=0.0, rel_height=0.3)
        assert narrow < wide

    def test_rel_height_bounds_enforced(self):
        t = np.linspace(0.0, 100.0, 50)
        s = np.zeros_like(t)
        s[25] = 1.0
        with pytest.raises(ValueError, match="rel_height"):
            compute_fwhm(t, s, 25, rel_height=1.5)


class TestCharacterizePeaksContract:
    def test_characterize_peaks_rel_height_forwarded(self):
        t = np.linspace(0.0, 100.0, 500)
        s = 2.0 * np.exp(-0.5 * ((t - 50.0) / 8.0) ** 2)
        peak = ThermalPeak(peak_index=int(np.argmax(s)), peak_temperature=50.0, peak_signal=2.0)
        [out] = characterize_peaks(t, s, [peak], baseline=np.zeros_like(s), rel_height=0.9)
        assert out.fwhm is not None and out.fwhm > 0
