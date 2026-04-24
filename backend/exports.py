"""Export/report preparation helpers for desktop backend endpoints."""

from __future__ import annotations

import base64
import copy
import io
from typing import Any

from backend.detail import normalize_compare_workspace
import pandas as pd

from backend.workspace import normalize_branding_payload, summarize_result
from core.report_generator import generate_csv_summary, generate_docx_report, generate_pdf_report
from core.result_serialization import collect_figure_keys
from core.result_serialization import split_valid_results


def _selected_records(results: dict[str, dict[str, Any]], selected_result_ids: list[str] | None) -> dict[str, dict[str, Any]]:
    if not results:
        raise ValueError("No valid saved results are available for export/report.")

    if not selected_result_ids:
        return dict(results)

    selected: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for raw_id in selected_result_ids:
        result_id = str(raw_id)
        if result_id in selected:
            continue
        record = results.get(result_id)
        if record is None:
            missing.append(result_id)
            continue
        selected[result_id] = record

    if missing:
        raise ValueError(f"Unknown selected_result_ids: {', '.join(missing)}")
    if not selected:
        raise ValueError("No exportable saved results selected.")
    return selected


def build_export_preparation(state: dict[str, Any]) -> dict[str, Any]:
    valid_results, issues = split_valid_results((state.get("results") or {}))
    items = [summarize_result(record) for record in valid_results.values()]
    items.sort(key=lambda item: item.id)
    branding = normalize_branding_payload(state.get("branding"))
    return {
        "exportable_results": items,
        "skipped_record_issues": issues,
        "supported_outputs": ["results_csv", "results_xlsx", "report_docx", "report_pdf"],
        "branding": {
            "report_title": branding.get("report_title") or "MaterialScope Professional Report",
            "company_name": branding.get("company_name") or "",
            "lab_name": branding.get("lab_name") or "",
            "analyst_name": branding.get("analyst_name") or "",
            "report_notes": branding.get("report_notes") or "",
            "logo_name": branding.get("logo_name") or "",
            "has_logo": bool(branding.get("logo_bytes")),
            "logo_base64": (
                base64.b64encode(branding["logo_bytes"]).decode("ascii")
                if branding.get("logo_bytes")
                else None
            ),
        },
        "compare_workspace": normalize_compare_workspace(state),
    }


def generate_results_csv_artifact(state: dict[str, Any], *, selected_result_ids: list[str] | None) -> dict[str, Any]:
    valid_results, issues = split_valid_results((state.get("results") or {}))
    selected = _selected_records(valid_results, selected_result_ids)
    csv_text = generate_csv_summary(selected)
    csv_base64 = base64.b64encode(csv_text.encode("utf-8")).decode("ascii")
    return {
        "output_type": "results_csv",
        "file_name": "materialscope_results.csv",
        "mime_type": "text/csv",
        "included_result_ids": list(selected.keys()),
        "skipped_record_issues": issues,
        "artifact_base64": csv_base64,
    }


def _results_to_xlsx_bytes(results: dict[str, dict[str, Any]], issues: list[str]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        summary_rows = []
        for record in results.values():
            row = {
                "result_id": record["id"],
                "status": record["status"],
                "analysis_type": record["analysis_type"],
                "dataset_key": record.get("dataset_key"),
                "workflow_template": (record.get("processing") or {}).get("workflow_template"),
                "validation_status": (record.get("validation") or {}).get("status"),
                "saved_at_utc": (record.get("provenance") or {}).get("saved_at_utc"),
            }
            row.update(record.get("summary", {}))
            summary_rows.append(row)

        summary_df = pd.DataFrame(summary_rows) if summary_rows else pd.DataFrame([{"message": "No valid results"}])
        summary_df.to_excel(writer, sheet_name="Results", index=False)

        for record in results.values():
            if not record.get("rows"):
                continue
            sheet_name = f"{record['analysis_type']}_{record['id']}"[:31]
            pd.DataFrame(record["rows"]).to_excel(writer, sheet_name=sheet_name, index=False)

        if issues:
            pd.DataFrame({"issue": issues}).to_excel(writer, sheet_name="Skipped", index=False)

    buffer.seek(0)
    return buffer.getvalue()


def generate_results_xlsx_artifact(state: dict[str, Any], *, selected_result_ids: list[str] | None) -> dict[str, Any]:
    valid_results, issues = split_valid_results((state.get("results") or {}))
    selected = _selected_records(valid_results, selected_result_ids)
    xlsx_bytes = _results_to_xlsx_bytes(selected, issues)
    xlsx_base64 = base64.b64encode(xlsx_bytes).decode("ascii")
    return {
        "output_type": "results_xlsx",
        "file_name": "materialscope_results.xlsx",
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "included_result_ids": list(selected.keys()),
        "skipped_record_issues": issues,
        "artifact_base64": xlsx_base64,
    }


def _selected_figures(
    state: dict[str, Any],
    selected_results: dict[str, dict[str, Any]],
    *,
    include_figures: bool,
) -> dict[str, bytes] | None:
    if not include_figures:
        return None

    figure_keys = collect_figure_keys(selected_results)
    compare_figure = ((state.get("comparison_workspace") or {}).get("figure_key"))
    if compare_figure and compare_figure not in figure_keys:
        figure_keys.append(compare_figure)
    if not figure_keys:
        return None

    stored_figures = state.get("figures") or {}
    figures = {key: stored_figures[key] for key in figure_keys if key in stored_figures}
    return figures or None


def collect_figure_export_warnings(
    state: dict[str, Any],
    selected_results: dict[str, dict[str, Any]],
    *,
    include_figures: bool,
    figures_bundle: dict[str, bytes] | None,
) -> list[str]:
    """Surface missing PNG bytes or failed server-side figure capture for exports."""
    warnings: list[str] = []
    if not include_figures:
        return warnings
    bundle = figures_bundle or {}
    stored = state.get("figures") or {}
    for rid, rec in selected_results.items():
        art = rec.get("artifacts") or {}
        atype = str(rec.get("analysis_type") or "").upper()
        primary = art.get("report_figure_key")
        status = art.get("report_figure_status")
        err = str(art.get("report_figure_error") or "").strip()
        if status == "failed" and err:
            warnings.append(f"{atype} result {rid}: figure capture failed ({err}).")
        if primary and primary not in bundle:
            where = "project workspace" if primary not in stored else "export selection"
            warnings.append(
                f"{atype} result {rid}: primary figure '{primary}' was not embedded ({where} missing PNG bytes)."
            )
    return warnings


def generate_report_docx_artifact(
    state: dict[str, Any],
    *,
    selected_result_ids: list[str] | None,
    include_figures: bool = True,
) -> dict[str, Any]:
    valid_results, issues = split_valid_results((state.get("results") or {}))
    selected = _selected_records(valid_results, selected_result_ids)
    normalized_workspace = normalize_compare_workspace(state)
    if hasattr(normalized_workspace, "model_dump"):
        comparison_workspace = normalized_workspace.model_dump()
    else:  # pragma: no cover - pydantic v1 compatibility
        comparison_workspace = normalized_workspace.dict()
    figures = _selected_figures(state, selected, include_figures=include_figures)
    export_warnings = collect_figure_export_warnings(
        state,
        selected,
        include_figures=include_figures,
        figures_bundle=figures,
    )
    docx_bytes = generate_docx_report(
        results=selected,
        datasets=state.get("datasets") or {},
        figures=figures,
        branding=state.get("branding") or {},
        comparison_workspace=comparison_workspace,
        license_state=state.get("license_state") or {},
        figure_export_warnings=export_warnings,
    )
    docx_base64 = base64.b64encode(docx_bytes).decode("ascii")
    return {
        "output_type": "report_docx",
        "file_name": "materialscope_report.docx",
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "included_result_ids": list(selected.keys()),
        "skipped_record_issues": issues,
        "artifact_base64": docx_base64,
        "export_warnings": export_warnings,
    }


def generate_report_pdf_artifact(
    state: dict[str, Any],
    *,
    selected_result_ids: list[str] | None,
    include_figures: bool = True,
) -> dict[str, Any]:
    valid_results, issues = split_valid_results((state.get("results") or {}))
    selected = _selected_records(valid_results, selected_result_ids)
    normalized_workspace = normalize_compare_workspace(state)
    if hasattr(normalized_workspace, "model_dump"):
        comparison_workspace = normalized_workspace.model_dump()
    else:  # pragma: no cover - pydantic v1 compatibility
        comparison_workspace = normalized_workspace.dict()
    figures = _selected_figures(state, selected, include_figures=include_figures)
    export_warnings = collect_figure_export_warnings(
        state,
        selected,
        include_figures=include_figures,
        figures_bundle=figures,
    )
    pdf_bytes = generate_pdf_report(
        results=selected,
        datasets=state.get("datasets") or {},
        figures=figures,
        branding=state.get("branding") or {},
        comparison_workspace=comparison_workspace,
        license_state=state.get("license_state") or {},
        figure_export_warnings=export_warnings,
    )
    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")
    return {
        "output_type": "report_pdf",
        "file_name": "materialscope_report.pdf",
        "mime_type": "application/pdf",
        "included_result_ids": list(selected.keys()),
        "skipped_record_issues": issues,
        "artifact_base64": pdf_base64,
        "export_warnings": export_warnings,
    }
