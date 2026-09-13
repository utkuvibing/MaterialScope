"""PR-12: normalization & confidence guards.

Covers:
- resolve_working_unit / DSCProcessor.normalize opt-in re-normalization
  of already-specific signals (force), while a signal already normalized
  this session can never be divided twice.
- Skip-reason provenance on the processor and in the serialized record.
- fit_quality_band defaults to "low" (not "moderate") when no fit
  statistic was reported.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.batch_runner import execute_batch_template
from core.dsc_processor import DSCProcessor
from core.uncertainty_rules import fit_quality_band
from core.units_dimensional import resolve_working_unit


# ---------------------------------------------------------------------------
# resolve_working_unit / DSCProcessor.normalize — opt-in re-normalization
# ---------------------------------------------------------------------------


class TestResolveWorkingUnitForce:
    def test_already_specific_skips_by_default(self):
        unit, applied, reason = resolve_working_unit("mW/mg", 5.0, True)
        assert applied is False
        assert reason == "already_specific_power"
        assert unit == "mW/mg"

    def test_force_overrides_already_specific(self):
        unit, applied, reason = resolve_working_unit(
            "mW/mg", 5.0, True, force_renormalize=True
        )
        assert applied is True
        assert reason is None
        assert unit == "mW/mg"

    def test_force_still_requires_sample_mass(self):
        unit, applied, reason = resolve_working_unit(
            "mW/mg", None, True, force_renormalize=True
        )
        assert applied is False
        assert reason == "sample_mass_missing"

    def test_force_never_divides_twice(self):
        unit, applied, reason = resolve_working_unit(
            "mW",
            5.0,
            True,
            working_unit="mW/mg",
            normalization_applied=True,
            force_renormalize=True,
        )
        assert applied is False
        assert reason == "already_normalized"
        assert unit == "mW/mg"

    def test_force_does_not_rescue_unusable_unit(self):
        unit, applied, reason = resolve_working_unit(
            "definitely-not-a-unit", 5.0, True, force_renormalize=True
        )
        assert applied is False
        assert reason is not None


def _dsc_processor(signal_unit, sample_mass=5.0):
    t = np.linspace(30.0, 300.0, 200)
    signal = np.sin(t / 40.0) + 2.0
    return DSCProcessor(
        t,
        signal,
        sample_mass=sample_mass,
        signal_unit=signal_unit,
    )


class TestProcessorNormalize:
    def test_already_specific_skips_and_records_reason(self):
        processor = _dsc_processor("mW/mg")
        processor.normalize()
        assert processor.normalization_applied is False
        assert processor.normalization_skip_reason == "already_specific_power"
        assert processor.get_result().metadata["normalization_skip_reason"] == (
            "already_specific_power"
        )

    def test_force_renormalizes_specific_signal(self):
        processor = _dsc_processor("mW/mg", sample_mass=5.0)
        before = processor._signal.copy()
        processor.normalize(force=True)
        assert processor.normalization_applied is True
        assert processor.normalization_skip_reason is None
        np.testing.assert_allclose(processor._signal, before / 5.0)
        steps = processor.get_result().metadata["steps"]
        norm_steps = [s for s in steps if s.get("step") == "normalize"]
        assert norm_steps and norm_steps[0].get("forced") is True
        assert norm_steps[0].get("overrode") == "already_specific_power"

    def test_raw_power_normalizes_without_force(self):
        processor = _dsc_processor("mW", sample_mass=5.0)
        before = processor._signal.copy()
        processor.normalize()
        assert processor.normalization_applied is True
        np.testing.assert_allclose(processor._signal, before / 5.0)

    def test_second_normalize_never_divides_twice(self):
        processor = _dsc_processor("mW", sample_mass=5.0)
        processor.normalize()
        once = processor._signal.copy()
        processor.normalize(force=True)
        assert processor._signal.tolist() == pytest.approx(once.tolist())
        assert processor.normalization_skip_reason == "already_normalized"

    def test_process_accepts_normalize_force(self):
        processor = _dsc_processor("mW/mg", sample_mass=5.0)
        result = processor.process(normalize_force=True)
        assert result.metadata["normalization_applied"] is True

    def test_process_default_leaves_specific_signal_untouched(self):
        processor = _dsc_processor("mW/mg", sample_mass=5.0)
        result = processor.process()
        assert result.metadata["normalization_applied"] is False
        assert result.metadata["normalization_skip_reason"] == "already_specific_power"


# ---------------------------------------------------------------------------
# Batch path — provenance lands in the serialized record
# ---------------------------------------------------------------------------


def _run_dsc_batch(dataset, processing=None):
    return execute_batch_template(
        dataset_key="synthetic_dsc_pr12",
        dataset=dataset,
        analysis_type="DSC",
        workflow_template_id="dsc.general",
        existing_processing=processing,
        batch_run_id="batch_pr12",
    )


class TestBatchNormalizationProvenance:
    def test_skip_reason_recorded_for_specific_unit(self, thermal_dataset):
        # thermal_dataset fixture declares mW/mg — already specific.
        outcome = _run_dsc_batch(thermal_dataset.copy())
        assert outcome["status"] == "saved"
        step = outcome["record"]["processing"]["signal_pipeline"]["normalization"]
        assert step["enabled"] is True
        assert step["applied"] is False
        assert step["skip_reason"] == "already_specific_power"
        assert outcome["record"]["summary"]["normalization_skip_reason"] == (
            "already_specific_power"
        )
        assert outcome["record"]["summary"]["renormalization_forced"] is False

    def test_force_renormalizes_and_is_recorded(self, thermal_dataset):
        dataset = thermal_dataset.copy()
        outcome = _run_dsc_batch(
            dataset,
            processing={
                "signal_pipeline": {
                    "normalization": {"enabled": True, "force": True}
                }
            },
        )
        assert outcome["status"] == "saved"
        step = outcome["record"]["processing"]["signal_pipeline"]["normalization"]
        assert step["force"] is True
        assert step["applied"] is True
        assert step["skip_reason"] is None
        assert outcome["record"]["summary"]["normalization_applied"] is True
        assert outcome["record"]["summary"]["renormalization_forced"] is True

    def test_missing_mass_records_skip_reason(self, thermal_dataset):
        dataset = thermal_dataset.copy()
        dataset.units["signal"] = "mW"  # raw power so normalization is attempted
        dataset.metadata["sample_mass"] = None
        outcome = _run_dsc_batch(dataset)
        assert outcome["record"]["summary"]["normalization_applied"] is False
        assert outcome["record"]["summary"]["normalization_skip_reason"] == (
            "sample_mass_missing"
        )


# ---------------------------------------------------------------------------
# fit_quality_band — defaults to "low" without statistics
# ---------------------------------------------------------------------------


class TestFitQualityBandDefault:
    @pytest.mark.parametrize("analysis", ["TGA", "DSC", "DTA"])
    def test_thermal_no_stats_defaults_low(self, analysis):
        band, reason = fit_quality_band(analysis, {})
        assert band == "low"
        assert "no formal fit statistic" in reason.lower()

    def test_non_thermal_no_stats_defaults_low(self):
        band, _ = fit_quality_band("FTIR", {})
        assert band == "low"

    def test_stats_still_produce_bands(self):
        assert fit_quality_band("DSC", {"r_squared": 0.995})[0] == "high"
        assert fit_quality_band("DSC", {"r_squared": 0.95})[0] == "moderate"
        assert fit_quality_band("DSC", {"r_squared": 0.5})[0] == "low"

    def test_validation_fail_still_forces_low(self):
        band, _ = fit_quality_band(
            "DSC", {"r_squared": 0.999}, validation={"status": "fail"}
        )
        assert band == "low"
