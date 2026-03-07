"""Helpers for stable DSC/TGA processing payloads."""

from __future__ import annotations

import copy
import re
from typing import Any


PROCESSING_SCHEMA_VERSION = 1

_SIGNAL_PIPELINE_SECTIONS = {
    "DSC": ("smoothing", "baseline"),
    "TGA": ("smoothing",),
}
_ANALYSIS_STEP_SECTIONS = {
    "DSC": ("glass_transition", "peak_detection"),
    "TGA": ("step_detection",),
}
_DEFAULT_WORKFLOW_TEMPLATE = {
    "DSC": "General DSC",
    "TGA": "General TGA",
}
_WORKFLOW_TEMPLATES = {
    "DSC": (
        {"id": "dsc.general", "label": "General DSC"},
        {"id": "dsc.polymer_tg", "label": "Polymer Tg"},
        {"id": "dsc.polymer_melting_crystallization", "label": "Polymer Melting/Crystallization"},
    ),
    "TGA": (
        {"id": "tga.general", "label": "General TGA"},
        {"id": "tga.single_step_decomposition", "label": "Single-Step Decomposition"},
        {"id": "tga.multi_step_decomposition", "label": "Multi-Step Decomposition"},
    ),
}
_METHOD_CONTEXT_DEFAULTS = {
    "DSC": {
        "sign_convention_id": "dsc.endotherm_up",
        "sign_convention_label": "Endotherm up / Exotherm down",
    },
    "TGA": {
        "step_analysis_basis": "DTG-derived onset, midpoint, and endset estimation",
    },
}


def _normalize_analysis_type(analysis_type: str | None) -> str:
    return (analysis_type or "UNKNOWN").upper()


def _copy_mapping(payload: Any) -> dict[str, Any]:
    return copy.deepcopy(payload) if isinstance(payload, dict) else {}


def _slugify(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    return text.strip("_") or "template"


def get_workflow_templates(analysis_type: str | None) -> list[dict[str, str]]:
    """Return a copy of the stable workflow template catalog for an analysis type."""
    normalized_type = _normalize_analysis_type(analysis_type)
    return [copy.deepcopy(entry) for entry in _WORKFLOW_TEMPLATES.get(normalized_type, ())]


def _fallback_template_entry(analysis_type: str, raw_value: Any) -> dict[str, str]:
    normalized_type = _normalize_analysis_type(analysis_type)
    label = str(raw_value or _DEFAULT_WORKFLOW_TEMPLATE.get(normalized_type, f"General {normalized_type}"))
    return {
        "id": f"{normalized_type.lower()}.custom.{_slugify(label)}",
        "label": label,
    }


def _resolve_workflow_template(
    analysis_type: str,
    *,
    workflow_template: Any = None,
    workflow_template_label: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    payload = payload or {}
    catalog = get_workflow_templates(analysis_type)
    template_inputs = [
        workflow_template,
        payload.get("workflow_template_id"),
        payload.get("workflow_template_label"),
        payload.get("workflow_template"),
    ]

    normalized_inputs = {str(item).strip().lower() for item in template_inputs if item not in (None, "")}
    for entry in catalog:
        if entry["id"].lower() in normalized_inputs or entry["label"].lower() in normalized_inputs:
            resolved = copy.deepcopy(entry)
            if workflow_template_label:
                resolved["label"] = workflow_template_label
            elif payload.get("workflow_template_label"):
                resolved["label"] = str(payload["workflow_template_label"])
            elif payload.get("workflow_template") and str(payload["workflow_template"]).strip().lower() == entry["id"].lower():
                resolved["label"] = entry["label"]
            return resolved

    raw_value = workflow_template or payload.get("workflow_template_label") or payload.get("workflow_template")
    resolved = _fallback_template_entry(analysis_type, raw_value)
    if workflow_template_label:
        resolved["label"] = workflow_template_label
    return resolved


def _extract_group(
    payload: dict[str, Any],
    group_key: str,
    section_names: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    nested = _copy_mapping(payload.get(group_key))
    group: dict[str, dict[str, Any]] = {}

    for section_name in section_names:
        if isinstance(nested.get(section_name), dict):
            group[section_name] = copy.deepcopy(nested[section_name])
        elif isinstance(payload.get(section_name), dict):
            group[section_name] = copy.deepcopy(payload[section_name])

    return group


def ensure_processing_payload(
    payload: dict[str, Any] | None = None,
    *,
    analysis_type: str,
    workflow_template: str | None = None,
    workflow_template_label: str | None = None,
) -> dict[str, Any]:
    """Return the standardized processing payload while preserving legacy aliases."""
    normalized_type = _normalize_analysis_type(analysis_type)
    payload = _copy_mapping(payload)
    template_entry = _resolve_workflow_template(
        normalized_type,
        workflow_template=workflow_template,
        workflow_template_label=workflow_template_label,
        payload=payload,
    )

    signal_sections = _extract_group(
        payload,
        "signal_pipeline",
        _SIGNAL_PIPELINE_SECTIONS.get(normalized_type, ()),
    )
    analysis_sections = _extract_group(
        payload,
        "analysis_steps",
        _ANALYSIS_STEP_SECTIONS.get(normalized_type, ()),
    )
    method_context = copy.deepcopy(_METHOD_CONTEXT_DEFAULTS.get(normalized_type, {}))
    method_context.update(_copy_mapping(payload.get("method_context")))

    normalized = {
        "schema_version": PROCESSING_SCHEMA_VERSION,
        "analysis_type": normalized_type,
        "workflow_template_id": template_entry["id"],
        "workflow_template_label": template_entry["label"],
        "workflow_template": template_entry["label"],
        "signal_pipeline": signal_sections,
        "analysis_steps": analysis_sections,
        "method_context": method_context,
    }

    for key, value in signal_sections.items():
        normalized[key] = copy.deepcopy(value)
    for key, value in analysis_sections.items():
        normalized[key] = copy.deepcopy(value)
    if method_context:
        if method_context.get("sign_convention_label"):
            normalized["sign_convention"] = method_context["sign_convention_label"]
        if method_context.get("step_analysis_basis"):
            normalized["step_analysis_basis"] = method_context["step_analysis_basis"]

    return normalized


def set_workflow_template(
    payload: dict[str, Any] | None,
    workflow_template: str,
    *,
    analysis_type: str | None = None,
    workflow_template_label: str | None = None,
) -> dict[str, Any]:
    """Update the workflow template while preserving standardized sections."""
    resolved_type = analysis_type or (payload or {}).get("analysis_type") or "UNKNOWN"
    return ensure_processing_payload(
        payload,
        analysis_type=resolved_type,
        workflow_template=workflow_template,
        workflow_template_label=workflow_template_label,
    )


def update_method_context(
    payload: dict[str, Any] | None,
    values: dict[str, Any] | None,
    *,
    analysis_type: str | None = None,
) -> dict[str, Any]:
    """Update the standardized method-context block."""
    resolved_type = analysis_type or (payload or {}).get("analysis_type") or "UNKNOWN"
    normalized = ensure_processing_payload(payload, analysis_type=resolved_type)
    method_context = normalized.get("method_context", {})
    method_context.update(_copy_mapping(values))
    normalized["method_context"] = method_context
    if method_context.get("sign_convention_label"):
        normalized["sign_convention"] = method_context["sign_convention_label"]
    if method_context.get("step_analysis_basis"):
        normalized["step_analysis_basis"] = method_context["step_analysis_basis"]
    return normalized


def update_processing_step(
    payload: dict[str, Any] | None,
    section_name: str,
    values: dict[str, Any] | None,
    *,
    analysis_type: str | None = None,
) -> dict[str, Any]:
    """Write a processing step into the correct standardized section and alias."""
    resolved_type = analysis_type or (payload or {}).get("analysis_type") or "UNKNOWN"
    normalized = ensure_processing_payload(payload, analysis_type=resolved_type)
    normalized_type = normalized["analysis_type"]
    values = _copy_mapping(values)

    if section_name in _SIGNAL_PIPELINE_SECTIONS.get(normalized_type, ()):
        normalized["signal_pipeline"][section_name] = copy.deepcopy(values)
    elif section_name in _ANALYSIS_STEP_SECTIONS.get(normalized_type, ()):
        normalized["analysis_steps"][section_name] = copy.deepcopy(values)
    else:
        raise ValueError(f"Unsupported processing section '{section_name}' for {normalized_type}")

    normalized[section_name] = copy.deepcopy(values)
    return normalized
