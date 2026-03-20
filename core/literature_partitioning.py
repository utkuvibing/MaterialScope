"""Shared literature partitioning helpers for UI/report surfacing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def reference_bucket_for_comparison(
    comparison: Mapping[str, Any],
    *,
    context: Mapping[str, Any],
    citations: list[Mapping[str, Any]],
    analysis_type: str,
) -> str:
    raw_label = _clean_text(comparison.get("support_label") or "related_but_inconclusive").lower()
    posture = _clean_text(comparison.get("validation_posture") or "").lower()
    confidence = _clean_text(comparison.get("confidence") or "low").lower()
    access_classes = {
        _clean_text(citation.get("access_class") or "").lower()
        for citation in citations
        if _clean_text(citation.get("access_class") or "")
    }
    if not access_classes and _clean_text(comparison.get("access_class") or ""):
        access_classes.add(_clean_text(comparison.get("access_class") or "").lower())
    evidence_specificity = _clean_text(context.get("evidence_specificity_summary") or "").lower()

    if raw_label == "contradicts" or posture == "alternative_interpretation":
        return "alternative"
    if raw_label in {"supports", "partially_supports"} or posture == "related_support":
        return "supporting"
    if (
        _clean_text(analysis_type).upper() in {"DSC", "DTA", "TGA"}
        and confidence in {"moderate", "high"}
        and posture in {"related_support", "contextual_only"}
        and (
            evidence_specificity in {"abstract_backed", "mixed_metadata_and_abstract", "oa_backed"}
            or access_classes & {"abstract_only", "open_access_full_text", "user_provided_document"}
        )
    ):
        return "supporting"
    return "alternative"


def partition_reference_ids(
    comparisons: list[Mapping[str, Any]],
    *,
    citations_by_id: Mapping[str, Mapping[str, Any]],
    context: Mapping[str, Any],
    analysis_type: str,
) -> tuple[list[str], list[str]]:
    supporting_ids: list[str] = []
    alternative_ids: list[str] = []
    for comparison in comparisons:
        citation_ids = [
            _clean_text(token)
            for token in (comparison.get("citation_ids") or [])
            if _clean_text(token) and _clean_text(token) in citations_by_id
        ]
        cited_rows = [dict(citations_by_id[citation_id]) for citation_id in citation_ids if citation_id in citations_by_id]
        bucket = reference_bucket_for_comparison(
            comparison,
            context=context,
            citations=cited_rows,
            analysis_type=analysis_type,
        )
        target = supporting_ids if bucket == "supporting" else alternative_ids
        for citation_id in citation_ids:
            if citation_id not in target:
                target.append(citation_id)
    return supporting_ids, alternative_ids
