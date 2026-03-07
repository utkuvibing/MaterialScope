"""Helpers for backward-compatible result provenance payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from utils.reference_data import evaluate_reference_check


_ACCEPTED_CALIBRATION_STATUSES = {"verified", "current", "pass", "ok"}
_BLOCKING_CALIBRATION_STATUSES = {"failed", "expired", "invalid", "out_of_date"}
_CALIBRATION_ACCEPTANCE = {
    "calibrated": "accepted",
    "missing_calibration": "missing",
    "calibration_not_current": "rejected",
    "unknown_calibration_state": "review",
}
_REFERENCE_ACCEPTANCE = {
    "reference_checked": "accepted",
    "reference_out_of_window": "review",
    "reference_candidate_missing": "missing",
    "reference_candidate_invalid": "review",
}


def _normalize_status_token(value: Any) -> str | None:
    if value in (None, ""):
        return None
    token = str(value).strip().lower()
    return token or None


def classify_calibration_state(
    *,
    calibration_id: Any = None,
    calibration_status: Any = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify calibration status in a single backward-compatible place."""
    metadata = metadata or {}
    calibration_id = metadata.get("calibration_id", calibration_id)
    calibration_status = metadata.get("calibration_status", calibration_status)
    calibration_token = _normalize_status_token(calibration_status)

    if calibration_id and calibration_token in _ACCEPTED_CALIBRATION_STATUSES:
        calibration_state = "calibrated"
    elif calibration_id in (None, "") and calibration_token is None:
        calibration_state = "missing_calibration"
    elif calibration_token in _BLOCKING_CALIBRATION_STATUSES:
        calibration_state = "calibration_not_current"
    else:
        calibration_state = "unknown_calibration_state"

    return {
        "calibration_state": calibration_state,
        "calibration_acceptance": _CALIBRATION_ACCEPTANCE[calibration_state],
        "calibration_id": calibration_id or "",
        "calibration_status": calibration_status or "",
    }


def classify_reference_acceptance(reference_state: Any) -> str:
    """Return an additive acceptance label for a saved reference state."""
    return _REFERENCE_ACCEPTANCE.get(str(reference_state or ""), "review")


def build_calibration_reference_context(
    *,
    dataset,
    analysis_type: str,
    reference_temperature_c: float | None = None,
    threshold_c: float = 15.0,
) -> dict[str, Any]:
    """Build calibration/reference context for saved processing and provenance payloads."""
    metadata = getattr(dataset, "metadata", {}) or {}
    context = classify_calibration_state(metadata=metadata)
    reference_context = evaluate_reference_check(
        reference_temperature_c,
        analysis_type=analysis_type,
        threshold_c=threshold_c,
    )
    reference_context["reference_acceptance"] = classify_reference_acceptance(reference_context.get("reference_state"))
    context.update(reference_context)
    return context


def build_result_provenance(
    *,
    dataset,
    dataset_key: str | None,
    analysis_history: list[dict[str, Any]] | None = None,
    app_version: str | None = None,
    analyst_name: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact provenance mapping for a saved result record."""
    metadata = getattr(dataset, "metadata", {}) or {}
    analysis_history = analysis_history or []
    recent_events = analysis_history[-5:]

    provenance = {
        "saved_at_utc": datetime.now(UTC).isoformat(),
        "dataset_key": dataset_key,
        "source_data_hash": metadata.get("source_data_hash"),
        "vendor": metadata.get("vendor"),
        "instrument": metadata.get("instrument"),
        "analyst_name": analyst_name or metadata.get("operator") or "",
        "calibration_id": metadata.get("calibration_id"),
        "calibration_status": metadata.get("calibration_status"),
        "calibration_acceptance": classify_calibration_state(metadata=metadata)["calibration_acceptance"],
        "analysis_event_count": len(analysis_history),
        "recent_event_ids": [event.get("event_id") for event in recent_events if event.get("event_id")],
    }
    if app_version:
        provenance["app_version"] = app_version
    if extra:
        provenance.update(dict(extra))
    return provenance
