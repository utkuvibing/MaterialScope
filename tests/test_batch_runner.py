from __future__ import annotations

import io

import numpy as np
import pandas as pd

from core.batch_runner import execute_batch_template, filter_batch_summary_rows, normalize_batch_summary_rows, summarize_batch_outcomes
from core.data_io import ThermalDataset, read_thermal_data
from core.processing_schema import set_tga_unit_mode


def _make_tga_dataset(temperature_range, tga_signal, *, signal_unit="%"):
    return ThermalDataset(
        data=pd.DataFrame({"temperature": temperature_range, "signal": tga_signal}),
        metadata={
            "sample_name": "SyntheticTGA",
            "sample_mass": 10.0,
            "heating_rate": 20.0,
            "instrument": "TestInstrument",
            "vendor": "TestVendor",
            "display_name": "Synthetic TGA Run",
            "atmosphere": "Nitrogen",
            "atmosphere_status": "verified",
            "source_data_hash": "synthetic-tga-hash",
        },
        data_type="TGA",
        units={"temperature": "degC", "signal": signal_unit},
        original_columns={"temperature": "temperature", "signal": "signal"},
        file_path="",
    )


def test_execute_dsc_batch_template_saves_normalized_record(thermal_dataset):
    dataset = thermal_dataset.copy()
    dataset.metadata.update(
        {
            "vendor": "TestVendor",
            "display_name": "Synthetic DSC Run",
            "calibration_id": "DSC-CAL-01",
            "calibration_status": "verified",
        }
    )

    outcome = execute_batch_template(
        dataset_key="synthetic_dsc",
        dataset=dataset,
        analysis_type="DSC",
        workflow_template_id="dsc.polymer_tg",
        analysis_history=[{"event_id": "evt-batch-start"}],
        analyst_name="Ada",
        app_version="2.0",
        batch_run_id="batch_dsc_demo",
    )

    assert outcome["status"] == "saved"
    assert outcome["record"]["id"] == "dsc_synthetic_dsc"
    assert outcome["record"]["processing"]["workflow_template_id"] == "dsc.polymer_tg"
    assert outcome["record"]["processing"]["workflow_template_version"] == 1
    assert outcome["record"]["processing"]["method_context"]["batch_run_id"] == "batch_dsc_demo"
    assert outcome["record"]["provenance"]["batch_run_id"] == "batch_dsc_demo"
    assert outcome["record"]["review"]["batch_runner"] == "compare_workspace"
    assert outcome["validation"]["status"] in {"pass", "warn"}
    assert outcome["state"]["processing"]["workflow_template"] == "Polymer Tg"
    assert outcome["state"]["peaks"]
    assert outcome["summary_row"]["execution_status"] == "saved"


def test_execute_tga_batch_template_saves_normalized_record(temperature_range, tga_signal):
    dataset = _make_tga_dataset(temperature_range, tga_signal)

    outcome = execute_batch_template(
        dataset_key="synthetic_tga",
        dataset=dataset,
        analysis_type="TGA",
        workflow_template_id="tga.single_step_decomposition",
        analysis_history=[{"event_id": "evt-batch-start"}],
        analyst_name="Ada",
        app_version="2.0",
        batch_run_id="batch_tga_demo",
    )

    assert outcome["status"] == "saved"
    assert outcome["record"]["id"] == "tga_synthetic_tga"
    assert outcome["record"]["processing"]["workflow_template_id"] == "tga.single_step_decomposition"
    assert outcome["record"]["processing"]["workflow_template_version"] == 1
    assert outcome["record"]["processing"]["method_context"]["batch_run_id"] == "batch_tga_demo"
    assert outcome["record"]["processing"]["method_context"]["tga_unit_mode_declared"] == "auto"
    assert outcome["record"]["processing"]["method_context"]["tga_unit_mode_resolved"] == "percent"
    assert outcome["record"]["processing"]["method_context"]["tga_unit_auto_inference_used"] is True
    assert outcome["record"]["provenance"]["batch_run_id"] == "batch_tga_demo"
    assert outcome["state"]["tga_result"] is not None
    assert outcome["summary_row"]["step_count"] >= 1
    assert outcome["summary_row"]["execution_status"] == "saved"


def test_execute_batch_template_blocks_failed_validation(thermal_dataset):
    dataset = thermal_dataset.copy()
    dataset.data.loc[10, "temperature"] = dataset.data.loc[9, "temperature"]

    outcome = execute_batch_template(
        dataset_key="broken_dsc",
        dataset=dataset,
        analysis_type="DSC",
        workflow_template_id="dsc.general",
        batch_run_id="batch_broken_demo",
    )

    assert outcome["status"] == "blocked"
    assert outcome["record"] is None
    assert outcome["state"] is None
    assert outcome["validation"]["status"] == "fail"
    assert "strictly increasing" in " ".join(outcome["validation"]["issues"])
    assert outcome["summary_row"]["execution_status"] == "blocked"


def test_batch_summary_helpers_normalize_legacy_error_rows():
    rows = [
        {"dataset_key": "run_a", "execution_status": "saved"},
        {"dataset_key": "run_b", "execution_status": "blocked", "failure_reason": "Validation blocked", "error_id": "TA-DSC-1"},
        {"dataset_key": "run_c", "execution_status": "error", "message": "Processor exploded", "error_id": "TA-DSC-2"},
    ]

    normalized = normalize_batch_summary_rows(rows)
    totals = summarize_batch_outcomes(rows)
    failed_only = filter_batch_summary_rows(rows, execution_status="failed")

    assert [row["execution_status"] for row in normalized] == ["saved", "blocked", "failed"]
    assert normalized[2]["failure_reason"] == "Processor exploded"
    assert totals == {"total": 3, "saved": 1, "blocked": 1, "failed": 1}
    assert [row["dataset_key"] for row in failed_only] == ["run_c"]


def test_execute_dsc_batch_template_is_deterministic_for_same_input_and_template(thermal_dataset):
    dataset = thermal_dataset.copy()
    dataset.metadata.update(
        {
            "vendor": "TestVendor",
            "display_name": "Synthetic DSC Run",
            "calibration_id": "DSC-CAL-01",
            "calibration_status": "verified",
        }
    )

    first = execute_batch_template(
        dataset_key="synthetic_dsc",
        dataset=dataset,
        analysis_type="DSC",
        workflow_template_id="dsc.polymer_tg",
        batch_run_id="batch_dsc_first",
    )
    second = execute_batch_template(
        dataset_key="synthetic_dsc",
        dataset=dataset,
        analysis_type="DSC",
        workflow_template_id="dsc.polymer_tg",
        batch_run_id="batch_dsc_second",
    )

    first_processing = dict(first["record"]["processing"])
    second_processing = dict(second["record"]["processing"])
    first_context = dict(first_processing["method_context"])
    second_context = dict(second_processing["method_context"])
    first_context.pop("batch_run_id", None)
    second_context.pop("batch_run_id", None)
    first_processing["method_context"] = first_context
    second_processing["method_context"] = second_context

    assert first["status"] == second["status"] == "saved"
    assert first_processing == second_processing
    assert first["record"]["summary"] == second["record"]["summary"]
    assert first["record"]["rows"] == second["record"]["rows"]
    np.testing.assert_allclose(first["state"]["corrected"], second["state"]["corrected"])


def test_execute_tga_batch_template_is_deterministic_for_same_input_and_template(temperature_range, tga_signal):
    dataset = _make_tga_dataset(temperature_range, tga_signal)

    first = execute_batch_template(
        dataset_key="synthetic_tga",
        dataset=dataset,
        analysis_type="TGA",
        workflow_template_id="tga.single_step_decomposition",
        batch_run_id="batch_tga_first",
    )
    second = execute_batch_template(
        dataset_key="synthetic_tga",
        dataset=dataset,
        analysis_type="TGA",
        workflow_template_id="tga.single_step_decomposition",
        batch_run_id="batch_tga_second",
    )

    first_processing = dict(first["record"]["processing"])
    second_processing = dict(second["record"]["processing"])
    first_context = dict(first_processing["method_context"])
    second_context = dict(second_processing["method_context"])
    first_context.pop("batch_run_id", None)
    second_context.pop("batch_run_id", None)
    first_processing["method_context"] = first_context
    second_processing["method_context"] = second_context

    assert first["status"] == second["status"] == "saved"
    assert first_processing == second_processing
    assert first["record"]["summary"] == second["record"]["summary"]
    assert first["record"]["rows"] == second["record"]["rows"]
    np.testing.assert_allclose(first["state"]["smoothed"], second["state"]["smoothed"])


def test_execute_tga_batch_template_preserves_explicit_absolute_mass_mode(temperature_range, tga_percent_signal):
    dataset = _make_tga_dataset(temperature_range, tga_percent_signal, signal_unit="")
    dataset.metadata["sample_mass"] = 100.0
    existing_processing = set_tga_unit_mode(
        {"workflow_template_id": "tga.general", "workflow_template": "General TGA"},
        "absolute_mass",
    )

    outcome = execute_batch_template(
        dataset_key="explicit_mass_tga",
        dataset=dataset,
        analysis_type="TGA",
        workflow_template_id="tga.general",
        existing_processing=existing_processing,
        batch_run_id="batch_explicit_mass_tga",
    )

    method_context = outcome["record"]["processing"]["method_context"]
    assert outcome["status"] == "saved"
    assert method_context["tga_unit_mode_declared"] == "absolute_mass"
    assert method_context["tga_unit_mode_resolved"] == "absolute_mass"
    assert method_context["tga_unit_auto_inference_used"] is False
    assert method_context["tga_unit_reference_source"] == "initial_mass_mg"
