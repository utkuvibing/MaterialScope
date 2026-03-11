from __future__ import annotations

import pandas as pd

from core.data_io import ThermalDataset
from core.peak_analysis import ThermalPeak
from core.processing_schema import ensure_processing_payload, update_processing_step
from core.result_serialization import (
    flatten_result_records,
    make_result_record,
    serialize_dta_result,
    split_valid_results,
    validate_result_record,
)


def _base_record():
    return make_result_record(
        result_id="demo_result",
        analysis_type="DSC",
        status="stable",
        dataset_key="demo_dataset",
        metadata={"sample_name": "Demo"},
        summary={"peak_count": 1},
        rows=[{"peak_temperature": 123.4}],
    )


def _dta_dataset() -> ThermalDataset:
    return ThermalDataset(
        data=pd.DataFrame({"temperature": [30.0, 50.0, 70.0], "signal": [0.2, 0.5, 0.1]}),
        metadata={
            "sample_name": "SyntheticDTA",
            "sample_mass": 5.0,
            "heating_rate": 10.0,
            "instrument": "TestInstrument",
            "vendor": "TestVendor",
            "display_name": "Synthetic DTA Run",
        },
        data_type="DTA",
        units={"temperature": "degC", "signal": "uV"},
        original_columns={"temperature": "temperature", "signal": "signal"},
        file_path="",
    )


def _dta_peak() -> ThermalPeak:
    return ThermalPeak(
        peak_index=1,
        peak_temperature=50.0,
        peak_signal=0.5,
        onset_temperature=45.0,
        endset_temperature=55.0,
        area=1.2,
        fwhm=3.0,
        peak_type="exo",
        height=0.4,
    )


def test_serialize_dta_result_stable_status_and_context_wording():
    dataset = _dta_dataset()
    processing = ensure_processing_payload(analysis_type="DTA", workflow_template="dta.general")
    processing = update_processing_step(processing, "peak_detection", {"method": "thermal_peaks", "prominence": 0.1})

    record = serialize_dta_result(
        "synthetic_dta",
        dataset,
        [_dta_peak()],
        processing=processing,
        validation={"status": "pass", "issues": [], "warnings": []},
    )

    assert record["status"] == "stable"
    assert record["summary"]["sample_name"] == "SyntheticDTA"
    assert record["summary"]["sample_mass"] == 5.0
    assert record["summary"]["heating_rate"] == 10.0
    assert record["scientific_context"]["methodology"]["workflow_template"] == "General DTA"
    limitations = " ".join(record["scientific_context"]["limitations"]).lower()
    assert "outside stable reporting guarantees" not in limitations
    assert "dta module is experimental" not in limitations


def test_serialize_dta_result_status_override_keeps_non_stable_path():
    dataset = _dta_dataset()

    record = serialize_dta_result(
        "synthetic_dta",
        dataset,
        [_dta_peak()],
        status="experimental",
        validation={"status": "warn", "issues": [], "warnings": ["review sign convention"]},
    )

    assert record["status"] == "experimental"
    assert record["analysis_type"] == "DTA"
    assert record["scientific_context"]["warnings"]


def test_validate_result_record_accepts_scientific_context_dict():
    record = _base_record()
    record["scientific_context"] = {
        "methodology": {"method": "demo"},
        "equations": [{"name": "E1", "formula": "y=x"}],
    }

    issues = validate_result_record("demo_result", record)

    assert issues == []


def test_validate_result_record_rejects_non_dict_scientific_context():
    record = _base_record()
    record["scientific_context"] = ["not", "a", "dict"]

    issues = validate_result_record("demo_result", record)

    assert any("scientific_context must be a dict" in issue for issue in issues)


def test_split_valid_results_backfills_scientific_context():
    record = _base_record()
    record.pop("scientific_context", None)

    valid, issues = split_valid_results({"demo_result": record})

    assert issues == []
    assert "demo_result" in valid
    assert valid["demo_result"]["scientific_context"] == {
        "methodology": {},
        "equations": [],
        "numerical_interpretation": [],
        "fit_quality": {},
        "warnings": [],
        "limitations": [],
        "scientific_claims": [],
        "evidence_map": {},
        "uncertainty_assessment": {},
        "alternative_hypotheses": [],
        "next_experiments": [],
    }


def test_flatten_result_records_emits_scientific_context_section():
    record = _base_record()
    record["scientific_context"] = {
        "methodology": {"workflow_template": "General DSC"},
        "equations": [{"name": "Energy", "formula": "DeltaH=int(q dT)"}],
    }

    flat_rows = flatten_result_records({"demo_result": record})

    assert any(row["section"] == "scientific_context" and row["field"] == "methodology" for row in flat_rows)
    assert any(row["section"] == "scientific_context" and row["field"] == "equations" for row in flat_rows)
