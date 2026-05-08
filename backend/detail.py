"""Detail payload helpers for dataset/result/compare backend endpoints."""

from __future__ import annotations

import copy
from datetime import datetime
import re
from typing import Any

import pandas as pd

from backend.models import CompareCandidate, CompareCandidatesResponse, CompareWorkspacePayload
from backend.workspace import summarize_dataset, summarize_result
from core.modalities import analysis_state_key, get_modality, stable_analysis_types
from core.result_serialization import split_valid_results
from core.validation import validate_thermal_dataset


def _figure_artifacts_meta(artifacts: Any) -> dict[str, Any]:
    """Expose figure registration metadata without binary payloads."""
    art = artifacts if isinstance(artifacts, dict) else {}
    raw_keys = art.get("figure_keys")
    keys: list[str] = []
    if isinstance(raw_keys, list):
        for item in raw_keys:
            if isinstance(item, str) and item.strip() and item not in keys:
                keys.append(item)
    return {
        "figure_keys": keys,
        "report_figure_key": art.get("report_figure_key"),
        "report_figure_status": art.get("report_figure_status"),
        "report_figure_error": art.get("report_figure_error"),
    }


def _records_payload(frame: pd.DataFrame, *, limit: int | None = None) -> list[dict[str, Any]]:
    payload = frame.head(limit).copy() if limit is not None else frame.copy()
    payload = payload.where(pd.notna(payload), None)
    return payload.to_dict(orient="records")


def _dataset_matches_analysis(dataset: Any, analysis_type: str) -> bool:
    modality = get_modality(analysis_type)
    if modality is None:
        return False
    dataset_type = str(getattr(dataset, "data_type", "UNKNOWN") or "UNKNOWN")
    return modality.adapter.is_dataset_eligible(dataset_type)


def _filter_selected_datasets(state: dict[str, Any], *, analysis_type: str, selected_datasets: list[str]) -> list[str]:
    datasets = state.get("datasets", {}) or {}
    filtered: list[str] = []
    for item in selected_datasets:
        key = str(item)
        dataset = datasets.get(key)
        if dataset is None:
            continue
        if not _dataset_matches_analysis(dataset, analysis_type):
            continue
        if key not in filtered:
            filtered.append(key)
    return filtered


def _enum_or_default(value: Any, allowed: set[str], default: str) -> str:
    token = str(value or "").strip().lower()
    return token if token in allowed else default


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = [item.strip() for item in value.replace(";", ",").split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw = [str(item).strip() for item in value]
    else:
        raw = []
    return [item for item in raw if item]


def _sample_metadata_for_dataset(dataset_key: str, dataset: Any) -> dict[str, Any]:
    metadata = copy.deepcopy(getattr(dataset, "metadata", {}) or {})
    sample_id = str(metadata.get("sample_id") or "").strip()
    if not sample_id:
        sample_id = dataset_key.rsplit(".", 1)[0]
    sample_name = str(metadata.get("sample_name") or metadata.get("display_name") or metadata.get("file_name") or dataset_key).strip()
    return {
        "sample_id": sample_id,
        "sample_name": sample_name,
        "material_type": str(metadata.get("material_type") or "").strip(),
        "processing_temperature_value": metadata.get("processing_temperature_value"),
        "processing_temperature_unit": str(metadata.get("processing_temperature_unit") or "°C").strip() or "°C",
        "composition": str(metadata.get("composition") or "").strip(),
        "tags": _string_list(metadata.get("tags")),
    }


def _series_prefix(sample_id: str) -> str:
    match = re.match(r"([A-Za-z]+)", str(sample_id or "").strip())
    return match.group(1).upper() if match else ""


def _temperature_label(value: Any, unit: str) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not pd.notna(number):
        return ""
    display = str(int(number)) if number.is_integer() else f"{number:g}"
    return f"{display}{unit or '°C'}"


def build_compare_candidates(state: dict[str, Any], analysis_type: str, *, project_id: str = "") -> CompareCandidatesResponse:
    """Build sample-aware same-technique compare candidates from workspace state."""
    normalized_analysis = str(analysis_type or "").upper()
    if normalized_analysis not in stable_analysis_types():
        raise ValueError(f"analysis_type must be one of: {', '.join(stable_analysis_types())}.")

    valid_results, _issues = split_valid_results(state.get("results", {}))
    result_ids_by_dataset: dict[str, list[str]] = {}
    for result_id, record in valid_results.items():
        if str(record.get("analysis_type") or "").upper() != normalized_analysis:
            continue
        dataset_key = str(record.get("dataset_key") or "").strip()
        if dataset_key:
            result_ids_by_dataset.setdefault(dataset_key, []).append(result_id)

    candidates: list[CompareCandidate] = []
    for dataset_key, dataset in (state.get("datasets") or {}).items():
        if not _dataset_matches_analysis(dataset, normalized_analysis):
            continue
        summary = summarize_dataset(dataset_key, dataset)
        sample = _sample_metadata_for_dataset(dataset_key, dataset)
        units = getattr(dataset, "units", {}) or {}
        try:
            has_analysis_state = state.get(analysis_state_key(normalized_analysis, dataset_key)) is not None
        except ValueError:
            has_analysis_state = False
        linked_result_ids = result_ids_by_dataset.get(dataset_key, [])
        candidates.append(
            CompareCandidate(
                dataset_key=dataset_key,
                display_name=summary.display_name,
                data_type=summary.data_type,
                points=summary.points,
                sample_id=sample["sample_id"],
                sample_name=sample["sample_name"],
                material_type=sample["material_type"],
                processing_temperature_value=sample["processing_temperature_value"],
                processing_temperature_unit=sample["processing_temperature_unit"],
                composition=sample["composition"],
                tags=sample["tags"],
                linked_result_ids=linked_result_ids,
                has_analysis_state=has_analysis_state,
                has_processed_result=bool(linked_result_ids),
                x_unit=units.get("temperature"),
                y_unit=units.get("signal"),
                signal_role=None,
            )
        )

    prefixes = sorted({prefix for item in candidates if (prefix := _series_prefix(item.sample_id))})
    temperatures = sorted(
        {
            label
            for item in candidates
            if (label := _temperature_label(item.processing_temperature_value, item.processing_temperature_unit))
        }
    )
    material_types = sorted({item.material_type for item in candidates if item.material_type})
    tags = sorted({tag for item in candidates for tag in item.tags})
    return CompareCandidatesResponse(
        project_id=project_id,
        analysis_type=normalized_analysis,
        candidates=candidates,
        available_series_prefixes=prefixes,
        available_processing_temperatures=temperatures,
        available_material_types=material_types,
        available_tags=tags,
    )


def build_dataset_detail(state: dict[str, Any], dataset_key: str) -> dict[str, Any]:
    datasets = state.get("datasets", {}) or {}
    dataset = datasets.get(dataset_key)
    if dataset is None:
        raise KeyError(f"Unknown dataset_key: {dataset_key}")

    validation = validate_thermal_dataset(dataset, analysis_type=getattr(dataset, "data_type", "unknown"))
    compare_workspace = normalize_compare_workspace(state)
    selected_datasets = compare_workspace.selected_datasets

    return {
        "dataset": summarize_dataset(dataset_key, dataset),
        "validation": validation,
        "metadata": copy.deepcopy(getattr(dataset, "metadata", {}) or {}),
        "units": copy.deepcopy(getattr(dataset, "units", {}) or {}),
        "original_columns": copy.deepcopy(getattr(dataset, "original_columns", {}) or {}),
        "data_preview": _records_payload(getattr(dataset, "data"), limit=20),
        "compare_selected": dataset_key in selected_datasets,
    }


def build_dataset_data(state: dict[str, Any], dataset_key: str) -> dict[str, Any]:
    datasets = state.get("datasets", {}) or {}
    dataset = datasets.get(dataset_key)
    if dataset is None:
        raise KeyError(f"Unknown dataset_key: {dataset_key}")

    frame = getattr(dataset, "data")
    return {
        "dataset_key": dataset_key,
        "columns": [str(column) for column in frame.columns],
        "rows": _records_payload(frame),
    }


def build_result_detail(state: dict[str, Any], result_id: str) -> dict[str, Any]:
    results = state.get("results", {}) or {}
    valid_results, issues = split_valid_results(results)
    record = valid_results.get(result_id)
    if record is None:
        if result_id in results:
            issue_text = "; ".join([issue for issue in issues if issue.startswith(f"{result_id}:")]) or "invalid result record"
            raise ValueError(f"Result '{result_id}' is present but invalid: {issue_text}")
        raise KeyError(f"Unknown result_id: {result_id}")

    rows = record.get("rows") or []
    frame = pd.DataFrame(rows) if rows else pd.DataFrame()
    return {
        "result": summarize_result(record),
        "summary": copy.deepcopy(record.get("summary") or {}),
        "processing": copy.deepcopy(record.get("processing") or {}),
        "provenance": copy.deepcopy(record.get("provenance") or {}),
        "validation": copy.deepcopy(record.get("validation") or {}),
        "review": copy.deepcopy(record.get("review") or {}),
        "literature_context": copy.deepcopy(record.get("literature_context") or {}),
        "literature_claims": copy.deepcopy(record.get("literature_claims") or []),
        "literature_comparisons": copy.deepcopy(record.get("literature_comparisons") or []),
        "citations": copy.deepcopy(record.get("citations") or []),
        "rows": copy.deepcopy(rows),
        "rows_preview": _records_payload(frame, limit=20) if not frame.empty else [],
        "row_count": len(rows),
        "figure_artifacts": _figure_artifacts_meta(record.get("artifacts")),
    }


def normalize_compare_workspace(state: dict[str, Any]) -> CompareWorkspacePayload:
    raw = state.get("comparison_workspace", {}) or {}
    stable_types = stable_analysis_types()
    default_type = stable_types[0] if stable_types else "DSC"
    analysis_type = str(raw.get("analysis_type") or default_type).upper()
    if analysis_type not in stable_types:
        analysis_type = default_type
    selected_datasets = _filter_selected_datasets(
        state,
        analysis_type=analysis_type,
        selected_datasets=list(raw.get("selected_datasets") or []),
    )
    return CompareWorkspacePayload(
        analysis_type=analysis_type,
        selected_datasets=selected_datasets,
        compare_display_mode=_enum_or_default(raw.get("compare_display_mode"), {"legacy", "academic"}, "legacy"),
        compare_group_mode=_enum_or_default(
            raw.get("compare_group_mode"),
            {"manual", "sample_series", "processing_temperature", "tag_composition"},
            "manual",
        ),
        series_filter=str(raw.get("series_filter") or ""),
        temperature_filter_value=raw.get("temperature_filter_value"),
        temperature_filter_unit=str(raw.get("temperature_filter_unit") or "°C"),
        material_type_filter=str(raw.get("material_type_filter") or ""),
        tag_filters=_string_list(raw.get("tag_filters")),
        composition_filter=str(raw.get("composition_filter") or ""),
        label_template=str(raw.get("label_template") or "{sample_id} at {temperature}"),
        signal_mode=_enum_or_default(raw.get("signal_mode"), {"best", "raw", "processed"}, "best"),
        normalize_mode=_enum_or_default(raw.get("normalize_mode"), {"none", "minmax", "max", "area"}, "none"),
        offset_mode=_enum_or_default(raw.get("offset_mode"), {"none", "stacked"}, "none"),
        reverse_x_axis=bool(raw.get("reverse_x_axis", False)),
        smoothing_enabled=bool(raw.get("smoothing_enabled", True)),
        notes=str(raw.get("notes") or ""),
        figure_key=raw.get("figure_key"),
        saved_at=raw.get("saved_at"),
        batch_run_id=raw.get("batch_run_id"),
        batch_template_id=raw.get("batch_template_id"),
        batch_template_label=raw.get("batch_template_label"),
        batch_completed_at=raw.get("batch_completed_at"),
        batch_summary=list(raw.get("batch_summary") or []),
        batch_result_ids=list(raw.get("batch_result_ids") or []),
        batch_last_feedback=dict(raw.get("batch_last_feedback") or {}),
    )


def update_compare_workspace(
    state: dict[str, Any],
    *,
    analysis_type: str | None,
    selected_datasets: list[str] | None,
    notes: str | None,
    compare_display_mode: str | None = None,
    compare_group_mode: str | None = None,
    series_filter: str | None = None,
    temperature_filter_value: float | None = None,
    temperature_filter_unit: str | None = None,
    material_type_filter: str | None = None,
    tag_filters: list[str] | None = None,
    composition_filter: str | None = None,
    label_template: str | None = None,
    signal_mode: str | None = None,
    normalize_mode: str | None = None,
    offset_mode: str | None = None,
    reverse_x_axis: bool | None = None,
    smoothing_enabled: bool | None = None,
) -> CompareWorkspacePayload:
    workspace = state.setdefault("comparison_workspace", {})
    stable_types = stable_analysis_types()
    default_type = stable_types[0] if stable_types else "DSC"
    existing_analysis = str(workspace.get("analysis_type") or default_type).upper()
    if existing_analysis not in stable_types:
        existing_analysis = default_type
    normalized_analysis = existing_analysis

    if analysis_type is not None:
        token = str(analysis_type or "").upper()
        if token not in stable_types:
            raise ValueError(f"analysis_type must be one of: {', '.join(stable_types)}.")
        normalized_analysis = token
    workspace["analysis_type"] = normalized_analysis

    if selected_datasets is not None:
        workspace["selected_datasets"] = _filter_selected_datasets(
            state,
            analysis_type=normalized_analysis,
            selected_datasets=selected_datasets,
        )
    elif analysis_type is not None:
        workspace["selected_datasets"] = _filter_selected_datasets(
            state,
            analysis_type=normalized_analysis,
            selected_datasets=list(workspace.get("selected_datasets") or []),
        )

    if notes is not None:
        workspace["notes"] = str(notes)
    if compare_display_mode is not None:
        workspace["compare_display_mode"] = _enum_or_default(compare_display_mode, {"legacy", "academic"}, "legacy")
    if compare_group_mode is not None:
        workspace["compare_group_mode"] = _enum_or_default(
            compare_group_mode,
            {"manual", "sample_series", "processing_temperature", "tag_composition"},
            "manual",
        )
    if series_filter is not None:
        workspace["series_filter"] = str(series_filter)
    if temperature_filter_value is not None:
        workspace["temperature_filter_value"] = temperature_filter_value
    if temperature_filter_unit is not None:
        workspace["temperature_filter_unit"] = str(temperature_filter_unit or "°C")
    if material_type_filter is not None:
        workspace["material_type_filter"] = str(material_type_filter)
    if tag_filters is not None:
        workspace["tag_filters"] = _string_list(tag_filters)
    if composition_filter is not None:
        workspace["composition_filter"] = str(composition_filter)
    if label_template is not None:
        workspace["label_template"] = str(label_template or "{sample_id} at {temperature}")
    if signal_mode is not None:
        workspace["signal_mode"] = _enum_or_default(signal_mode, {"best", "raw", "processed"}, "best")
    if normalize_mode is not None:
        workspace["normalize_mode"] = _enum_or_default(normalize_mode, {"none", "minmax", "max", "area"}, "none")
    if offset_mode is not None:
        workspace["offset_mode"] = _enum_or_default(offset_mode, {"none", "stacked"}, "none")
    if reverse_x_axis is not None:
        workspace["reverse_x_axis"] = bool(reverse_x_axis)
    if smoothing_enabled is not None:
        workspace["smoothing_enabled"] = bool(smoothing_enabled)

    workspace["saved_at"] = datetime.now().isoformat(timespec="seconds")
    payload = normalize_compare_workspace(state)
    if hasattr(payload, "model_dump"):
        workspace.update(payload.model_dump())
    else:  # pragma: no cover - pydantic v1 compatibility
        workspace.update(payload.dict())
    return payload
