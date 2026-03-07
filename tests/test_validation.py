from __future__ import annotations

import io

from core.data_io import read_thermal_data
from core.processing_schema import ensure_processing_payload, set_tga_unit_mode, update_processing_step
from core.provenance import build_calibration_reference_context, classify_calibration_state
from core.validation import validate_thermal_dataset
from utils.validators import validate_thermal_dataset as legacy_validate_thermal_dataset


def test_validate_thermal_dataset_passes_for_synthetic_fixture(thermal_dataset):
    summary = validate_thermal_dataset(thermal_dataset, analysis_type="DSC")
    assert summary["status"] in {"pass", "warn"}
    assert not summary["issues"]
    assert summary["checks"]["data_points"] == len(thermal_dataset.data)


def test_validate_thermal_dataset_fails_for_non_monotonic_temperature(thermal_dataset):
    broken = thermal_dataset.copy()
    broken.data.loc[10, "temperature"] = broken.data.loc[9, "temperature"]

    summary = validate_thermal_dataset(broken, analysis_type="DSC")

    assert summary["status"] == "fail"
    assert any("strictly increasing" in issue for issue in summary["issues"])


def test_read_thermal_data_populates_source_data_hash():
    dataset = read_thermal_data(
        io.StringIO("Temperature,HeatFlow\n30.0,0.0\n50.0,0.5\n70.0,0.1\n")
    )
    assert dataset.metadata["source_data_hash"]
    assert len(dataset.metadata["source_data_hash"]) == 64


def test_validate_thermal_dataset_warns_when_required_metadata_missing():
    dataset = read_thermal_data(io.StringIO("Temperature,Weight\n30.0,100.0\n50.0,95.0\n70.0,90.0\n"))
    summary = validate_thermal_dataset(dataset, analysis_type="TGA")

    assert summary["status"] == "warn"
    assert any("Recommended metadata missing" in warning for warning in summary["warnings"])


def test_ensure_processing_payload_backfills_legacy_workflow_template_label():
    processing = ensure_processing_payload({"workflow_template": "Polymer Tg"}, analysis_type="DSC")

    assert processing["workflow_template"] == "Polymer Tg"
    assert processing["workflow_template_id"] == "dsc.polymer_tg"
    assert processing["workflow_template_label"] == "Polymer Tg"
    assert processing["workflow_template_version"] == 1


def test_validate_dsc_processing_records_calibration_and_sign_convention(thermal_dataset):
    dataset = thermal_dataset.copy()
    dataset.metadata.update(
        {
            "vendor": "TestVendor",
            "display_name": "Synthetic DSC Run",
            "calibration_id": "DSC-CAL-01",
            "calibration_status": "verified",
        }
    )
    processing = ensure_processing_payload(
        analysis_type="DSC",
        workflow_template="dsc.polymer_tg",
        workflow_template_label="Polymer Tg",
    )
    processing = update_processing_step(processing, "baseline", {"method": "asls"})
    processing = update_processing_step(processing, "peak_detection", {"direction": "both", "peak_count": 1})

    summary = validate_thermal_dataset(dataset, analysis_type="DSC", processing=processing)

    assert summary["status"] == "pass"
    assert summary["checks"]["workflow_template_id"] == "dsc.polymer_tg"
    assert summary["checks"]["workflow_template_version"] == 1
    assert summary["checks"]["calibration_state"] == "calibrated"
    assert summary["checks"]["calibration_acceptance"] == "accepted"
    assert summary["checks"]["calibration_status"] == "verified"
    assert summary["checks"]["sign_convention"] == "Endotherm up / Exotherm down"
    assert summary["checks"]["reference_state"] == "not recorded"
    assert summary["checks"]["reference_acceptance"] == "review"
    assert summary["checks"]["peak_detection_context"] == "recorded"


def test_validate_dsc_processing_blocks_failed_calibration(thermal_dataset):
    dataset = thermal_dataset.copy()
    dataset.metadata.update(
        {
            "vendor": "TestVendor",
            "display_name": "Synthetic DSC Run",
            "calibration_id": "DSC-CAL-EXPIRED",
            "calibration_status": "expired",
        }
    )
    processing = ensure_processing_payload(
        analysis_type="DSC",
        workflow_template="dsc.general",
        workflow_template_label="General DSC",
    )

    summary = validate_thermal_dataset(dataset, analysis_type="DSC", processing=processing)

    assert summary["status"] == "fail"
    assert summary["checks"]["calibration_state"] == "calibration_not_current"
    assert any("not currently verified" in issue for issue in summary["issues"])


def test_validate_tga_processing_checks_unit_plausibility_and_step_context():
    dataset = read_thermal_data(io.StringIO("Temperature,Weight\n30.0,130.0\n50.0,125.0\n70.0,118.0\n"))
    dataset.units["signal"] = "%"
    dataset.metadata.update(
        {
            "sample_name": "SyntheticTGA",
            "sample_mass": 10.0,
            "heating_rate": 20.0,
            "instrument": "TestInstrument",
            "vendor": "TestVendor",
            "display_name": "Synthetic TGA Run",
            "atmosphere": "Nitrogen",
            "atmosphere_status": "verified",
        }
    )
    processing = ensure_processing_payload(
        analysis_type="TGA",
        workflow_template="tga.single_step_decomposition",
        workflow_template_label="Single-Step Decomposition",
    )
    processing = update_processing_step(
        processing,
        "step_detection",
        {"method": "savgol", "prominence": 0.1, "min_mass_loss": 0.5},
    )

    summary = validate_thermal_dataset(dataset, analysis_type="TGA", processing=processing)

    assert summary["status"] == "warn"
    assert summary["checks"]["workflow_template_id"] == "tga.single_step_decomposition"
    assert summary["checks"]["workflow_template_version"] == 1
    assert summary["checks"]["tga_unit_mode_declared"] == "auto"
    assert summary["checks"]["tga_unit_mode_resolved"] == "percent"
    assert summary["checks"]["tga_unit_auto_inference_used"] is True
    assert summary["checks"]["tga_unit_interpretation_status"] == "accepted"
    assert summary["checks"]["atmosphere_status"] == "verified"
    assert summary["checks"]["calibration_state"] == "missing_calibration"
    assert summary["checks"]["calibration_acceptance"] == "missing"
    assert summary["checks"]["step_analysis_context"] == "recorded"
    assert summary["checks"]["reference_state"] == "not recorded"
    assert summary["checks"]["reference_acceptance"] == "review"
    assert summary["checks"]["unit_plausibility"] == "review"
    assert any("plausible mass-percent range" in warning for warning in summary["warnings"])


def test_validate_tga_auto_mode_on_ambiguous_low_range_warns_for_review():
    dataset = read_thermal_data(io.StringIO("Temperature,Weight\n30.0,100.0\n50.0,95.0\n70.0,90.0\n"))
    dataset.metadata.update(
        {
            "sample_name": "AmbiguousLowRangeTGA",
            "sample_mass": 10.0,
            "heating_rate": 20.0,
            "instrument": "TestInstrument",
            "vendor": "TestVendor",
            "display_name": "Ambiguous TGA Run",
            "atmosphere": "Nitrogen",
            "atmosphere_status": "verified",
        }
    )
    processing = ensure_processing_payload(analysis_type="TGA", workflow_template="tga.general")

    summary = validate_thermal_dataset(dataset, analysis_type="TGA", processing=processing)

    assert summary["status"] == "warn"
    assert summary["checks"]["tga_unit_mode_declared"] == "auto"
    assert summary["checks"]["tga_unit_mode_resolved"] == "percent"
    assert summary["checks"]["tga_unit_auto_inference_used"] is True
    assert summary["checks"]["tga_unit_interpretation_status"] == "review"
    assert summary["checks"]["unit_plausibility"] == "review"
    assert any("defaulted to percent" in warning for warning in summary["warnings"])


def test_validate_tga_explicit_absolute_mass_mode_overrides_low_range_ambiguity():
    dataset = read_thermal_data(io.StringIO("Temperature,Weight\n30.0,100.0\n50.0,95.0\n70.0,90.0\n"))
    dataset.metadata.update(
        {
            "sample_name": "ExplicitMassModeTGA",
            "sample_mass": 100.0,
            "heating_rate": 20.0,
            "instrument": "TestInstrument",
            "vendor": "TestVendor",
            "display_name": "Explicit Mass TGA Run",
            "atmosphere": "Nitrogen",
            "atmosphere_status": "verified",
        }
    )
    processing = ensure_processing_payload(analysis_type="TGA", workflow_template="tga.general")
    processing = set_tga_unit_mode(processing, "absolute_mass")
    dataset.units["signal"] = ""

    summary = validate_thermal_dataset(dataset, analysis_type="TGA", processing=processing)

    assert summary["checks"]["tga_unit_mode_declared"] == "absolute_mass"
    assert summary["checks"]["tga_unit_mode_resolved"] == "absolute_mass"
    assert summary["checks"]["tga_unit_auto_inference_used"] is False
    assert summary["checks"]["tga_unit_interpretation_status"] == "accepted"
    assert summary["checks"]["unit_plausibility"] == "pass"


def test_tga_reference_lookup_does_not_fall_back_to_dsc_standards():
    dataset = read_thermal_data(io.StringIO("Temperature,Weight\n30.0,100.0\n50.0,95.0\n70.0,90.0\n"))
    dataset.metadata.update(
        {
            "sample_name": "SyntheticTGA",
            "sample_mass": 10.0,
            "heating_rate": 20.0,
            "instrument": "TestInstrument",
        }
    )

    context = build_calibration_reference_context(
        dataset=dataset,
        analysis_type="TGA",
        reference_temperature_c=155.0,
    )

    assert context["reference_state"] == "reference_out_of_window"
    assert context["reference_checked"] is False
    assert context["reference_acceptance"] == "review"
    assert "reference_name" not in context


def test_classify_calibration_state_distinguishes_all_supported_states():
    assert classify_calibration_state(calibration_id="CAL-01", calibration_status="verified") == {
        "calibration_state": "calibrated",
        "calibration_acceptance": "accepted",
        "calibration_id": "CAL-01",
        "calibration_status": "verified",
    }
    assert classify_calibration_state(calibration_id="", calibration_status=None)["calibration_state"] == "missing_calibration"
    assert classify_calibration_state(calibration_id="CAL-02", calibration_status="expired")["calibration_state"] == "calibration_not_current"
    assert classify_calibration_state(calibration_id="CAL-03", calibration_status="pending_review")["calibration_state"] == "unknown_calibration_state"


def test_legacy_validator_wraps_structured_validation_for_current_dataset(thermal_dataset):
    is_valid, message = legacy_validate_thermal_dataset(thermal_dataset)

    assert is_valid is True
    assert "Validation passed" in message or "All checks passed" in message


def test_legacy_validator_surfaces_structured_failures(thermal_dataset):
    broken = thermal_dataset.copy()
    broken.data.loc[10, "temperature"] = broken.data.loc[9, "temperature"]

    is_valid, message = legacy_validate_thermal_dataset(broken)

    assert is_valid is False
    assert "strictly increasing" in message
