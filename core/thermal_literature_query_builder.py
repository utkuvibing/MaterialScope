"""Deterministic thermal literature query builders for DSC, DTA, and TGA."""

from __future__ import annotations

from typing import Any, Mapping


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _clean_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _round_temperature(value: Any) -> int | None:
    numeric = _clean_float(value)
    if numeric is None:
        return None
    return int(round(numeric))


def _rows(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in (record.get("rows") or []) if isinstance(item, Mapping)]


def _summary(record: Mapping[str, Any]) -> dict[str, Any]:
    return dict(record.get("summary") or {})


def _metadata(record: Mapping[str, Any]) -> dict[str, Any]:
    return dict(record.get("metadata") or {})


def _sample_name(record: Mapping[str, Any]) -> str:
    summary = _summary(record)
    metadata = _metadata(record)
    return _clean_text(summary.get("sample_name") or metadata.get("sample_name") or metadata.get("display_name"))


def _workflow_label(record: Mapping[str, Any]) -> str:
    processing = dict(record.get("processing") or {})
    return _clean_text(processing.get("workflow_template_label") or processing.get("workflow_template"))


def _build_payload(
    *,
    analysis_type: str,
    query_text: str,
    fallback_queries: list[str],
    query_rationale: str,
    query_display_title: str,
    query_display_mode: str,
    query_display_terms: list[str],
    evidence_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "analysis_type": analysis_type,
        "query_text": _clean_text(query_text),
        "fallback_queries": [_clean_text(item) for item in fallback_queries if _clean_text(item)],
        "query_rationale": _clean_text(query_rationale),
        "query_display_title": _clean_text(query_display_title),
        "query_display_mode": _clean_text(query_display_mode),
        "query_display_terms": [_clean_text(item) for item in query_display_terms if _clean_text(item)],
        "evidence_snapshot": dict(evidence_snapshot or {}),
    }


def build_dsc_literature_query(record: Mapping[str, Any]) -> dict[str, Any]:
    summary = _summary(record)
    rows = _rows(record)
    sample_name = _sample_name(record)
    tg_midpoint = _round_temperature(summary.get("tg_midpoint"))
    first_peak = rows[0] if rows else {}
    peak_type = _clean_text(first_peak.get("peak_type")).lower()
    peak_temp = _round_temperature(first_peak.get("peak_temperature"))
    peak_count = _clean_int(summary.get("peak_count")) or len(rows)
    glass_transition_count = _clean_int(summary.get("glass_transition_count")) or 0

    if tg_midpoint is not None:
        query_text = " ".join(
            part
            for part in [
                f"\"{sample_name}\"" if sample_name else "",
                "DSC glass transition thermal analysis",
                f"{tg_midpoint} C",
            ]
            if part
        )
        fallback_queries = [
            " ".join(part for part in [f"\"{sample_name}\"" if sample_name else "", "DSC glass transition"] if part),
            "DSC glass transition calorimetry",
        ]
        display_title = sample_name or "DSC glass transition"
        rationale = (
            f"The DSC literature search is centered on a glass-transition signal near {tg_midpoint} C."
            if tg_midpoint is not None
            else "The DSC literature search is centered on the recorded thermal transition context."
        )
        display_terms = ["glass transition", "calorimetry", "thermal event"]
    else:
        event_label = peak_type or "thermal event"
        query_text = " ".join(
            part
            for part in [
                f"\"{sample_name}\"" if sample_name else "",
                "DSC thermal event calorimetry",
                event_label,
                f"{peak_temp} C" if peak_temp is not None else "",
            ]
            if part
        )
        fallback_queries = [
            " ".join(part for part in [f"\"{sample_name}\"" if sample_name else "", "DSC thermal event"] if part),
            "DSC endothermic exothermic event calorimetry",
        ]
        display_title = sample_name or "DSC thermal event"
        rationale = (
            f"The DSC literature search is centered on the leading {event_label} event"
            + (f" near {peak_temp} C." if peak_temp is not None else ".")
        )
        display_terms = ["thermal event", "calorimetry", event_label]

    return _build_payload(
        analysis_type="DSC",
        query_text=query_text,
        fallback_queries=fallback_queries,
        query_rationale=rationale,
        query_display_title=display_title,
        query_display_mode="DSC / thermal interpretation",
        query_display_terms=display_terms,
        evidence_snapshot={
            "sample_name": sample_name,
            "workflow_template": _workflow_label(record),
            "peak_count": peak_count,
            "glass_transition_count": glass_transition_count,
            "tg_midpoint": _clean_float(summary.get("tg_midpoint")),
            "peak_type": peak_type,
            "peak_temperature": _clean_float(first_peak.get("peak_temperature")),
        },
    )


def build_dta_literature_query(record: Mapping[str, Any]) -> dict[str, Any]:
    summary = _summary(record)
    rows = _rows(record)
    sample_name = _sample_name(record)
    first_peak = rows[0] if rows else {}
    direction = _clean_text(first_peak.get("peak_type") or first_peak.get("direction")).lower() or "thermal event"
    peak_temp = _round_temperature(first_peak.get("peak_temperature"))
    processing = dict(record.get("processing") or {})
    method_context = dict(processing.get("method_context") or {})

    query_text = " ".join(
        part
        for part in [
            f"\"{sample_name}\"" if sample_name else "",
            "DTA differential thermal analysis",
            direction,
            f"{peak_temp} C" if peak_temp is not None else "",
        ]
        if part
    )
    fallback_queries = [
        " ".join(part for part in [f"\"{sample_name}\"" if sample_name else "", "DTA thermal event"] if part),
        "DTA endothermic exothermic event differential thermal analysis",
    ]
    return _build_payload(
        analysis_type="DTA",
        query_text=query_text,
        fallback_queries=fallback_queries,
        query_rationale=(
            f"The DTA literature search is centered on the leading {direction} event"
            + (f" near {peak_temp} C." if peak_temp is not None else ".")
        ),
        query_display_title=sample_name or "DTA thermal event",
        query_display_mode="DTA / thermal events",
        query_display_terms=["thermal event", "differential thermal analysis", direction],
        evidence_snapshot={
            "sample_name": sample_name,
            "workflow_template": _workflow_label(record),
            "peak_count": _clean_int(summary.get("peak_count")) or len(rows),
            "event_direction": direction,
            "peak_temperature": _clean_float(first_peak.get("peak_temperature")),
            "sign_convention": _clean_text(method_context.get("sign_convention_label") or method_context.get("sign_convention")),
        },
    )


def build_tga_literature_query(record: Mapping[str, Any]) -> dict[str, Any]:
    summary = _summary(record)
    rows = _rows(record)
    sample_name = _sample_name(record)
    first_step = rows[0] if rows else {}
    midpoint = _round_temperature(first_step.get("midpoint_temperature"))
    total_mass_loss = _clean_float(summary.get("total_mass_loss_percent"))
    residue = _clean_float(summary.get("residue_percent"))

    query_text = " ".join(
        part
        for part in [
            f"\"{sample_name}\"" if sample_name else "",
            "TGA decomposition mass loss residue",
            f"{midpoint} C" if midpoint is not None else "",
        ]
        if part
    )
    fallback_queries = [
        " ".join(part for part in [f"\"{sample_name}\"" if sample_name else "", "TGA decomposition"] if part),
        "TGA mass loss residue thermogravimetric analysis",
    ]
    rationale = "The TGA literature search is centered on the decomposition profile"
    if midpoint is not None:
        rationale += f" with a leading step near {midpoint} C"
    if total_mass_loss is not None:
        rationale += f" and total mass loss around {total_mass_loss:.1f}%"
    rationale += "."
    return _build_payload(
        analysis_type="TGA",
        query_text=query_text,
        fallback_queries=fallback_queries,
        query_rationale=rationale,
        query_display_title=sample_name or "TGA decomposition profile",
        query_display_mode="TGA / decomposition profile",
        query_display_terms=["decomposition", "mass loss", "residue"],
        evidence_snapshot={
            "sample_name": sample_name,
            "workflow_template": _workflow_label(record),
            "step_count": _clean_int(summary.get("step_count")) or len(rows),
            "total_mass_loss_percent": total_mass_loss,
            "residue_percent": residue,
            "midpoint_temperature": _clean_float(first_step.get("midpoint_temperature")),
            "mass_loss_percent": _clean_float(first_step.get("mass_loss_percent")),
        },
    )


def build_thermal_query_presentation(query_payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "display_title": _clean_text(query_payload.get("query_display_title")) or _clean_text(query_payload.get("sample_name")) or "Thermal literature search",
        "display_mode": _clean_text(query_payload.get("query_display_mode")) or "Thermal / interpretation",
        "display_terms": [_clean_text(item) for item in (query_payload.get("query_display_terms") or []) if _clean_text(item)],
        "raw_query": _clean_text(query_payload.get("query_text")),
    }
