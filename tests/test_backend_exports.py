from __future__ import annotations

import base64
import io
import zipfile

import pandas as pd
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.exports import (
    build_export_preparation,
    generate_report_docx_artifact,
    generate_report_pdf_artifact,
    generate_results_csv_artifact,
)
from core.data_io import ThermalDataset
from core.processing_schema import ensure_processing_payload, update_method_context, update_processing_step
from core.result_serialization import serialize_spectral_result, serialize_xrd_result


def _headers() -> dict[str, str]:
    return {"X-MaterialScope-Token": "exports-token"}


def _as_b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _seed_workspace_with_result(
    client: TestClient,
    thermal_dataset,
    *,
    data_type: str = "DSC",
    analysis_type: str = "DSC",
    workflow_template_id: str | None = None,
) -> tuple[str, str]:
    created = client.post("/workspace/new", headers=_headers()).json()
    project_id = created["project_id"]

    csv_bytes = thermal_dataset.data.to_csv(index=False).encode("utf-8")
    imported = client.post(
        "/dataset/import",
        headers=_headers(),
        json={
            "project_id": project_id,
            "file_name": "export_seed.csv",
            "file_base64": _as_b64(csv_bytes),
            "data_type": data_type,
        },
    )
    assert imported.status_code == 200
    dataset_key = imported.json()["dataset"]["key"]

    run = client.post(
        "/analysis/run",
        headers=_headers(),
        json={
            "project_id": project_id,
            "dataset_key": dataset_key,
            "analysis_type": analysis_type,
            "workflow_template_id": workflow_template_id or f"{analysis_type.lower()}.general",
        },
    )
    assert run.status_code == 200
    result_id = run.json()["result_id"]
    assert result_id
    return project_id, result_id


def test_export_preparation_and_csv_generation(thermal_dataset):
    app = create_app(api_token="exports-token")
    client = TestClient(app)
    project_id, result_id = _seed_workspace_with_result(client, thermal_dataset)

    prep = client.get(f"/workspace/{project_id}/exports/preparation", headers=_headers())
    assert prep.status_code == 200
    prep_payload = prep.json()
    assert prep_payload["project_id"] == project_id
    assert "results_csv" in prep_payload["supported_outputs"]
    assert "report_docx" in prep_payload["supported_outputs"]
    assert len(prep_payload["exportable_results"]) == 1
    assert prep_payload["exportable_results"][0]["id"] == result_id

    csv_export = client.post(
        f"/workspace/{project_id}/exports/results-csv",
        headers=_headers(),
        json={"selected_result_ids": [result_id]},
    )
    assert csv_export.status_code == 200
    csv_payload = csv_export.json()
    assert csv_payload["output_type"] == "results_csv"
    assert csv_payload["included_result_ids"] == [result_id]
    assert csv_payload["file_name"].endswith(".csv")

    csv_text = base64.b64decode(csv_payload["artifact_base64"].encode("ascii")).decode("utf-8")
    assert "result_id,status,analysis_type" in csv_text
    assert result_id in csv_text


def test_export_docx_generation_returns_docx_bytes(thermal_dataset):
    app = create_app(api_token="exports-token")
    client = TestClient(app)
    project_id, result_id = _seed_workspace_with_result(client, thermal_dataset)

    docx_export = client.post(
        f"/workspace/{project_id}/exports/report-docx",
        headers=_headers(),
        json={"selected_result_ids": [result_id]},
    )
    assert docx_export.status_code == 200
    payload = docx_export.json()
    assert payload["output_type"] == "report_docx"
    assert payload["included_result_ids"] == [result_id]
    assert payload["file_name"].endswith(".docx")
    docx_bytes = base64.b64decode(payload["artifact_base64"].encode("ascii"))
    assert docx_bytes[:4] == b"PK\x03\x04"


def test_export_results_xlsx_generation_returns_workbook(thermal_dataset):
    app = create_app(api_token="exports-token")
    client = TestClient(app)
    project_id, result_id = _seed_workspace_with_result(client, thermal_dataset)

    xlsx_export = client.post(
        f"/workspace/{project_id}/exports/results-xlsx",
        headers=_headers(),
        json={"selected_result_ids": [result_id]},
    )
    assert xlsx_export.status_code == 200
    payload = xlsx_export.json()
    assert payload["output_type"] == "results_xlsx"
    assert payload["included_result_ids"] == [result_id]
    workbook_bytes = base64.b64decode(payload["artifact_base64"].encode("ascii"))

    workbook = pd.ExcelFile(io.BytesIO(workbook_bytes))
    assert "Results" in workbook.sheet_names
    results_sheet = pd.read_excel(io.BytesIO(workbook_bytes), sheet_name="Results")
    assert result_id in results_sheet["result_id"].astype(str).tolist()


def test_export_report_pdf_generation_returns_pdf_bytes(thermal_dataset):
    app = create_app(api_token="exports-token")
    client = TestClient(app)
    project_id, result_id = _seed_workspace_with_result(client, thermal_dataset)

    pdf_export = client.post(
        f"/workspace/{project_id}/exports/report-pdf",
        headers=_headers(),
        json={"selected_result_ids": [result_id], "include_figures": True},
    )
    assert pdf_export.status_code == 200
    payload = pdf_export.json()
    assert payload["output_type"] == "report_pdf"
    assert payload["included_result_ids"] == [result_id]
    pdf_bytes = base64.b64decode(payload["artifact_base64"].encode("ascii"))
    assert pdf_bytes[:4] == b"%PDF"


def test_report_exports_include_saved_figure_payloads(monkeypatch):
    import backend.exports as exports_module

    state, result_id = _build_spectral_export_state()
    figure_key = "FTIR Analysis - ftir_export_seed"
    figure_bytes = b"\x89PNG\r\n\x1a\nSAVED"
    state["results"][result_id]["artifacts"] = {"figure_keys": [figure_key]}
    state["figures"] = {figure_key: figure_bytes}

    observed: dict[str, dict[str, bytes] | None] = {}

    def _fake_docx_report(**kwargs):
        observed["docx"] = kwargs.get("figures")
        return b"DOCX-BYTES"

    def _fake_pdf_report(**kwargs):
        observed["pdf"] = kwargs.get("figures")
        return b"%PDF-1.4\nFAKE"

    monkeypatch.setattr(exports_module, "generate_docx_report", _fake_docx_report)
    monkeypatch.setattr(exports_module, "generate_pdf_report", _fake_pdf_report)

    docx_artifact = generate_report_docx_artifact(state, selected_result_ids=[result_id], include_figures=True)
    pdf_artifact = generate_report_pdf_artifact(state, selected_result_ids=[result_id], include_figures=True)

    assert observed["docx"] == {figure_key: figure_bytes}
    assert observed["pdf"] == {figure_key: figure_bytes}
    assert base64.b64decode(docx_artifact["artifact_base64"].encode("ascii")) == b"DOCX-BYTES"
    assert base64.b64decode(pdf_artifact["artifact_base64"].encode("ascii")) == b"%PDF-1.4\nFAKE"


def test_export_docx_generation_keeps_dta_in_stable_partition(thermal_dataset):
    app = create_app(api_token="exports-token")
    client = TestClient(app)
    project_id, result_id = _seed_workspace_with_result(
        client,
        thermal_dataset,
        data_type="DTA",
        analysis_type="DTA",
        workflow_template_id="dta.general",
    )

    docx_export = client.post(
        f"/workspace/{project_id}/exports/report-docx",
        headers=_headers(),
        json={"selected_result_ids": [result_id]},
    )
    assert docx_export.status_code == 200
    payload = docx_export.json()
    assert payload["included_result_ids"] == [result_id]
    docx_bytes = base64.b64decode(payload["artifact_base64"].encode("ascii"))

    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as archive:
        xml = archive.read("word/document.xml").decode("utf-8")

    assert "Stable Analyses" in xml
    assert "DTA - export_seed" in xml
    assert "outside the stable workflow guarantee" not in xml


def test_export_rejects_unknown_selected_result_id(thermal_dataset):
    app = create_app(api_token="exports-token")
    client = TestClient(app)
    project_id, _result_id = _seed_workspace_with_result(client, thermal_dataset)

    response = client.post(
        f"/workspace/{project_id}/exports/results-csv",
        headers=_headers(),
        json={"selected_result_ids": ["missing_result_id"]},
    )
    assert response.status_code == 400
    assert "Unknown selected_result_ids" in response.json()["detail"]


def _build_spectral_export_state() -> tuple[dict, str]:
    dataset_key = "ftir_export_seed"
    dataset = ThermalDataset(
        data=pd.DataFrame({"temperature": [650.0, 980.0, 1450.0], "signal": [0.08, 0.52, 0.18]}),
        metadata={
            "sample_name": "SyntheticFTIR",
            "sample_mass": 1.0,
            "heating_rate": 1.0,
            "instrument": "SpecBench",
            "vendor": "TestVendor",
            "display_name": "Synthetic FTIR Spectrum",
        },
        data_type="FTIR",
        units={"temperature": "cm^-1", "signal": "a.u."},
        original_columns={"temperature": "wavenumber", "signal": "intensity"},
        file_path="",
    )
    processing = ensure_processing_payload(analysis_type="FTIR", workflow_template="ftir.general")
    processing = update_processing_step(processing, "similarity_matching", {"metric": "cosine", "top_n": 3, "minimum_score": 0.45})
    spectral_record = serialize_spectral_result(
        dataset_key,
        dataset,
        analysis_type="FTIR",
        summary={
            "peak_count": 3,
            "match_status": "no_match",
            "candidate_count": 1,
            "top_match_id": None,
            "top_match_name": None,
            "top_match_score": 0.31,
            "confidence_band": "no_match",
            "caution_code": "spectral_no_match",
        },
        rows=[
            {
                "rank": 1,
                "candidate_id": "ftir_ref_unknown",
                "candidate_name": "Unknown",
                "normalized_score": 0.31,
                "confidence_band": "no_match",
                "evidence": {"shared_peak_count": 0, "peak_overlap_ratio": 0.0},
            }
        ],
        artifacts={"figure_keys": []},
        processing=processing,
        validation={"status": "warn", "issues": [], "warnings": ["FTIR produced no confident library match."]},
    )
    state = {
        "datasets": {dataset_key: dataset},
        "results": {spectral_record["id"]: spectral_record},
        "figures": {},
        "comparison_workspace": {
            "analysis_type": "FTIR",
            "selected_datasets": [dataset_key],
            "notes": "Spectral caution lane",
        },
    }
    return state, spectral_record["id"]


def _build_xrd_export_state() -> tuple[dict, str]:
    dataset_key = "xrd_export_seed"
    dataset = ThermalDataset(
        data=pd.DataFrame({"temperature": [18.2, 27.5, 36.1, 44.8], "signal": [130.0, 290.0, 175.0, 120.0]}),
        metadata={
            "sample_name": "SyntheticXRD",
            "sample_mass": 1.0,
            "instrument": "XRDBench",
            "vendor": "TestVendor",
            "display_name": "Synthetic XRD Pattern",
            "xrd_axis_role": "two_theta",
            "xrd_axis_unit": "degree_2theta",
            "xrd_wavelength_angstrom": 1.5406,
        },
        data_type="XRD",
        units={"temperature": "degree_2theta", "signal": "counts"},
        original_columns={"temperature": "two_theta", "signal": "intensity"},
        file_path="",
    )
    processing = ensure_processing_payload(analysis_type="XRD", workflow_template="xrd.general")
    processing = update_method_context(
        processing,
        {
            "xrd_match_metric": "peak_overlap_weighted",
            "xrd_match_tolerance_deg": 0.28,
            "xrd_match_minimum_score": 0.42,
            "xrd_match_top_n": 5,
        },
        analysis_type="XRD",
    )
    xrd_record = serialize_xrd_result(
        dataset_key,
        dataset,
        summary={
            "peak_count": 4,
            "match_status": "no_match",
            "candidate_count": 1,
            "top_phase_id": None,
            "top_phase": None,
            "top_phase_score": 0.33,
            "confidence_band": "no_match",
            "caution_code": "xrd_no_match",
            "caution_message": "No candidate exceeded threshold; qualitative caution required.",
            "reference_candidate_count": 2,
            "match_tolerance_deg": 0.28,
        },
        rows=[
            {
                "rank": 1,
                "candidate_id": "xrd_phase_alpha",
                "candidate_name": "Phase Alpha",
                "normalized_score": 0.33,
                "confidence_band": "no_match",
                "evidence": {
                    "shared_peak_count": 0,
                    "weighted_overlap_score": 0.11,
                    "mean_delta_position": None,
                    "unmatched_major_peak_count": 3,
                    "tolerance_deg": 0.28,
                },
            }
        ],
        artifacts={"figure_keys": []},
        processing=processing,
        validation={"status": "warn", "issues": [], "warnings": ["XRD no-match should be interpreted cautiously."]},
    )
    state = {
        "datasets": {dataset_key: dataset},
        "results": {xrd_record["id"]: xrd_record},
        "figures": {},
        "comparison_workspace": {
            "analysis_type": "XRD",
            "selected_datasets": [dataset_key],
            "notes": "XRD qualitative caution lane",
        },
    }
    return state, xrd_record["id"]


def _build_rich_xrd_export_state(*, stale_report_payload: bool = False) -> tuple[dict, str]:
    dataset_key = "xrd_export_rich"
    dataset = ThermalDataset(
        data=pd.DataFrame({"temperature": [18.2, 27.5, 36.1], "signal": [130.0, 290.0, 175.0]}),
        metadata={
            "sample_name": "SyntheticXRDFormula",
            "sample_mass": 1.0,
            "instrument": "XRDBench",
            "vendor": "TestVendor",
            "display_name": "Synthetic XRD Formula Pattern",
            "xrd_axis_role": "two_theta",
            "xrd_axis_unit": "degree_2theta",
            "xrd_wavelength_angstrom": 1.5406,
        },
        data_type="XRD",
        units={"temperature": "degree_2theta", "signal": "counts"},
        original_columns={"temperature": "two_theta", "signal": "intensity"},
        file_path="",
    )
    processing = ensure_processing_payload(analysis_type="XRD", workflow_template="xrd.general")
    processing = update_method_context(
        processing,
        {
            "xrd_match_metric": "peak_overlap_weighted",
            "xrd_match_tolerance_deg": 0.28,
            "xrd_match_minimum_score": 0.42,
            "xrd_match_top_n": 5,
        },
        analysis_type="XRD",
    )
    xrd_record = serialize_xrd_result(
        dataset_key,
        dataset,
        summary={
            "peak_count": 3,
            "match_status": "matched",
            "candidate_count": 1,
            "top_phase": "COD 1000026",
            "top_phase_id": "cod_1000026",
            "top_phase_score": 0.91,
            "confidence_band": "high",
            "library_provider": "COD",
        },
        rows=[
            {
                "rank": 1,
                "candidate_id": "cod_1000026",
                "candidate_name": "COD 1000026",
                "formula": "MgB2",
                "source_id": "1000026",
                "normalized_score": 0.91,
                "confidence_band": "high",
                "library_provider": "COD",
                "library_package": "cod_xrd_core",
                "library_version": "2026.03-core",
                "reference_metadata": {
                    "source_url": "https://example.test/cod/1000026",
                    "provider_url": "https://provider.example.test/cod/1000026",
                    "provider_dataset_version": "2026.03",
                    "space_group": "P6/mmm",
                    "symmetry": "hexagonal",
                    "attribution": "COD reference dataset",
                },
                "reference_peaks": [
                    {
                        "peak_number": idx + 1,
                        "position": 27.5 + (idx * 0.37),
                        "d_spacing": 3.24 - (idx * 0.04),
                        "intensity": 100.0 - idx,
                    }
                    for idx in range(25)
                ],
                "source_assets": [
                    {
                        "kind": "source_url",
                        "label": "Source Reference",
                        "url": "https://example.test/cod/1000026",
                        "available": True,
                    },
                    {
                        "kind": "source_url",
                        "label": "Provider Reference",
                        "url": "https://provider.example.test/cod/1000026",
                        "available": True,
                    },
                ],
                "evidence": {
                    "shared_peak_count": 3,
                    "weighted_overlap_score": 0.91,
                    "coverage_ratio": 0.88,
                    "mean_delta_position": 0.04,
                    "unmatched_major_peak_count": 0,
                    "matched_peak_pairs": [{"observed_index": 0, "reference_index": 0}],
                },
            }
        ],
        artifacts={"report_figure_key": "XRD Snapshot - xrd_export_rich - r1_MgB2"},
        processing=processing,
        validation={"status": "pass", "issues": [], "warnings": []},
    )
    if stale_report_payload:
        xrd_record["report_payload"] = {
            "xrd_reference_dossier_limit": 3,
            "xrd_reference_peak_display_limit": 20,
            "xrd_reference_dossiers": [
                {
                    "rank": 1,
                    "candidate_overview": {"display_name_unicode": "MgB₂"},
                    "reference_peaks": {
                        "display_rows": [],
                        "displayed_peak_count": 0,
                        "total_peak_count": 0,
                        "truncated_count": 0,
                        "selection_policy": "matched_and_major_then_fill_to_top_20_by_intensity",
                    },
                    "reference_metadata": {"source_url": None, "provider_url": None},
                    "structure_payload": {
                        "availability": "none",
                        "source_asset_count": 0,
                        "rendered_asset_count": 0,
                    },
                    "source_assets": [],
                }
            ],
        }
    state = {
        "datasets": {dataset_key: dataset},
        "results": {xrd_record["id"]: xrd_record},
        "figures": {},
        "comparison_workspace": {
            "analysis_type": "XRD",
            "selected_datasets": [dataset_key],
            "notes": "XRD qualitative caution lane",
        },
    }
    return state, xrd_record["id"]


def test_export_preparation_includes_spectral_workspace_and_results():
    state, result_id = _build_spectral_export_state()
    prep = build_export_preparation(state)
    compare_workspace = prep["compare_workspace"]

    assert compare_workspace.analysis_type == "FTIR"
    assert compare_workspace.selected_datasets == ["ftir_export_seed"]
    assert len(prep["exportable_results"]) == 1
    assert prep["exportable_results"][0].id == result_id
    assert prep["exportable_results"][0].analysis_type == "FTIR"


def test_export_artifacts_preserve_spectral_caution_fields():
    state, result_id = _build_spectral_export_state()

    csv_artifact = generate_results_csv_artifact(state, selected_result_ids=[result_id])
    csv_text = base64.b64decode(csv_artifact["artifact_base64"].encode("ascii")).decode("utf-8")
    assert "spectral_no_match" in csv_text

    docx_artifact = generate_report_docx_artifact(state, selected_result_ids=[result_id])
    docx_bytes = base64.b64decode(docx_artifact["artifact_base64"].encode("ascii"))
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as archive:
        xml = archive.read("word/document.xml").decode("utf-8")

    assert "FTIR - ftir_export_seed" in xml
    assert "Match Status" in xml
    assert "Caution Code" in xml
    assert "spectral_no_match" in xml


def test_export_preparation_includes_xrd_workspace_and_results():
    state, result_id = _build_xrd_export_state()
    prep = build_export_preparation(state)
    compare_workspace = prep["compare_workspace"]

    assert compare_workspace.analysis_type == "XRD"
    assert compare_workspace.selected_datasets == ["xrd_export_seed"]
    assert len(prep["exportable_results"]) == 1
    assert prep["exportable_results"][0].id == result_id
    assert prep["exportable_results"][0].analysis_type == "XRD"


def test_export_artifacts_preserve_xrd_caution_fields_and_method_context():
    state, result_id = _build_xrd_export_state()

    csv_artifact = generate_results_csv_artifact(state, selected_result_ids=[result_id])
    csv_text = base64.b64decode(csv_artifact["artifact_base64"].encode("ascii")).decode("utf-8")
    assert "xrd_no_match" in csv_text
    assert "top_phase_score" in csv_text
    assert "xrd_match_metric" in csv_text

    docx_artifact = generate_report_docx_artifact(state, selected_result_ids=[result_id])
    docx_bytes = base64.b64decode(docx_artifact["artifact_base64"].encode("ascii"))
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as archive:
        xml = archive.read("word/document.xml").decode("utf-8")

    appendix_index = xml.index("Appendix A")
    main_xml = xml[:appendix_index]
    appendix_xml = xml[appendix_index:]

    assert "XRD - xrd_export_seed" in xml
    assert "Best Candidate" in main_xml
    assert "Caution Code" in xml
    assert "xrd_no_match" in xml
    assert "Match Metric" in main_xml
    assert "Top Candidates" in main_xml
    assert "Match Tolerance (deg)" not in main_xml
    assert "Match Tolerance (deg)" in appendix_xml
    assert "XRD Library and Access Context" in appendix_xml
    assert "XRD Match and Provenance Context" in appendix_xml
    assert "Candidate Evidence Summary" in appendix_xml


def test_export_docx_artifact_rebuilds_stale_xrd_dossier_payload_from_rows():
    state, result_id = _build_rich_xrd_export_state(stale_report_payload=True)

    docx_artifact = generate_report_docx_artifact(state, selected_result_ids=[result_id])
    docx_bytes = base64.b64decode(docx_artifact["artifact_base64"].encode("ascii"))
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as archive:
        xml = archive.read("word/document.xml").decode("utf-8")

    assert "Candidate Reference Dossier" in xml
    assert "Reference Peaks" in xml
    assert "Showing 20 of 25 reference peaks" in xml
    assert "Remaining peaks omitted from visible table by display policy" in xml
    assert "https://example.test/cod/1000026" in xml
    assert "https://provider.example.test/cod/1000026" in xml
    assert "Linked Source and Provider Assets" in xml
