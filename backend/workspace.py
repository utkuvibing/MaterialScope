"""Workspace-state helpers for backend desktop flow."""

from __future__ import annotations

import copy
import re
from datetime import UTC, datetime
from typing import Any

from backend.models import DatasetSummary, ResultSummary
from core.validation import validate_thermal_dataset


WORKSPACE_DEFAULTS = {
    "ui_language": "tr",
    "datasets": {},
    "active_dataset": None,
    "results": {},
    "figures": {},
    "analysis_history": [],
    "support_events": [],
    "branding": {
        "report_title": "MaterialScope Professional Report",
        "company_name": "",
        "lab_name": "",
        "analyst_name": "",
        "report_notes": "",
        "logo_bytes": None,
        "logo_name": "",
    },
    "comparison_workspace": {
        "analysis_type": "DSC",
        "selected_datasets": [],
        "notes": "",
        "figure_key": None,
        "saved_at": None,
    },
}


def normalize_workspace_state(state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a state payload with required project/workspace keys."""
    normalized = copy.deepcopy(state or {})
    for key, default in WORKSPACE_DEFAULTS.items():
        if key not in normalized:
            normalized[key] = copy.deepcopy(default)
    if not isinstance(normalized.get("datasets"), dict):
        normalized["datasets"] = {}
    if not isinstance(normalized.get("results"), dict):
        normalized["results"] = {}
    if not isinstance(normalized.get("figures"), dict):
        normalized["figures"] = {}
    if not isinstance(normalized.get("analysis_history"), list):
        normalized["analysis_history"] = []
    if not isinstance(normalized.get("branding"), dict):
        normalized["branding"] = copy.deepcopy(WORKSPACE_DEFAULTS["branding"])
    if not isinstance(normalized.get("comparison_workspace"), dict):
        normalized["comparison_workspace"] = copy.deepcopy(WORKSPACE_DEFAULTS["comparison_workspace"])
    return normalized


def unique_dataset_key(existing: dict[str, Any], requested_name: str) -> str:
    """Return a collision-safe dataset key."""
    token = re.sub(r"[\\/]+", "_", requested_name.strip()) or "dataset"
    if token not in existing:
        return token
    index = 2
    while f"{token}_{index}" in existing:
        index += 1
    return f"{token}_{index}"


def add_history_event(
    state: dict[str, Any],
    *,
    action: str,
    details: str,
    page: str = "Desktop",
    dataset_key: str | None = None,
    result_id: str | None = None,
    status: str = "info",
) -> None:
    """Append a lightweight analysis-history event."""
    history = state.setdefault("analysis_history", [])
    history.append(
        {
            "step_number": len(history) + 1,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "action": action,
            "details": details,
            "page": page,
            "dataset_key": dataset_key,
            "result_id": result_id,
            "status": status,
        }
    )


def summarize_dataset(dataset_key: str, dataset) -> DatasetSummary:
    """Build a dataset summary with validation rollup for desktop list views."""
    validation = validate_thermal_dataset(dataset, analysis_type=getattr(dataset, "data_type", "unknown"))
    metadata = getattr(dataset, "metadata", {}) or {}
    return DatasetSummary(
        key=dataset_key,
        display_name=metadata.get("display_name") or metadata.get("file_name") or dataset_key,
        data_type=str(getattr(dataset, "data_type", "unknown")),
        points=len(getattr(dataset, "data", [])),
        vendor=metadata.get("vendor", "Generic"),
        sample_name=metadata.get("sample_name", ""),
        heating_rate=metadata.get("heating_rate"),
        import_confidence=metadata.get("import_confidence"),
        validation_status=validation.get("status", "unknown"),
        warning_count=len(validation.get("warnings") or []),
        issue_count=len(validation.get("issues") or []),
    )


def summarize_result(record: dict[str, Any]) -> ResultSummary:
    """Build a result summary for desktop list views."""
    validation = record.get("validation") or {}
    processing = record.get("processing") or {}
    method_context = processing.get("method_context") or {}
    provenance = record.get("provenance") or {}
    return ResultSummary(
        id=record.get("id", ""),
        analysis_type=record.get("analysis_type", ""),
        status=record.get("status", ""),
        dataset_key=record.get("dataset_key"),
        validation_status=validation.get("status"),
        warning_count=len(validation.get("warnings") or []),
        issue_count=len(validation.get("issues") or []),
        workflow_template=processing.get("workflow_template"),
        saved_at_utc=provenance.get("saved_at_utc"),
        calibration_state=method_context.get("calibration_state") or provenance.get("calibration_state"),
        reference_state=method_context.get("reference_state") or provenance.get("reference_state"),
    )
