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
