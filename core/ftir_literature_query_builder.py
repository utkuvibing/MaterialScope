"""Deterministic FTIR literature query payloads for spectral-similarity records."""

from __future__ import annotations

from typing import Any, Mapping

from core.thermal_literature_query_builder import (
    _best_subject,
    _build_payload,
    _clean_float,
    _clean_int,
    _clean_text,
    _infer_search_mode,
    _infer_subject_trust,
    _quoted_subject,
    _rows,
    _summary,
    _workflow_label,
)


def _top_row_evidence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    top = rows[0]
    return dict(top.get("evidence") or {}) if isinstance(top, Mapping) else {}


def _wavenumber_query_terms(evidence: Mapping[str, Any], *, limit: int = 6) -> list[str]:
    pairs = evidence.get("matched_peak_pairs") or []
    out: list[str] = []
    for pair in pairs[:limit]:
        if not isinstance(pair, Mapping):
            continue
        raw = pair.get("observed_position")
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if v > 0.0:
            out.append(f"{v:.0f} cm-1")
    return out


def _numeric_anchors_from_terms(terms: list[str]) -> list[str]:
    anchors: list[str] = []
    for term in terms:
        cleaned = _clean_text(term).replace("cm-1", "").replace("cm^-1", "").strip()
        parts = cleaned.replace(",", " ").split()
        for p in parts:
            if p.replace(".", "", 1).isdigit():
                anchors.append(p.split(".")[0] if "." in p else p)
    deduped: list[str] = []
    seen: set[str] = set()
    for a in anchors:
        key = a.casefold()
        if key in seen or not key:
            continue
        seen.add(key)
        deduped.append(a)
    return deduped[:8]


def build_ftir_literature_query(record: Mapping[str, Any]) -> dict[str, Any]:
    """Build a traceable FTIR literature query payload (spectral similarity / library context)."""
    summary = _summary(record)
    rows = _rows(record)
    processing = dict(record.get("processing") or {})
    method_context = dict(processing.get("method_context") or {})

    subject = _best_subject(record)
    subject_trust = _infer_subject_trust(subject)
    subject_label = _clean_text(subject.get("cleaned"))
    quoted_subject = _quoted_subject(subject)

    match_status = _clean_text(summary.get("match_status")).lower()
    confidence_band = _clean_text(summary.get("confidence_band")).lower()
    peak_count = _clean_int(summary.get("peak_count")) or 0
    top_name = _clean_text(summary.get("top_match_name"))
    top_score = _clean_float(summary.get("top_match_score"))

    evidence = _top_row_evidence(rows)
    wn_terms = _wavenumber_query_terms(evidence)
    shared_peaks = _clean_int(evidence.get("shared_peak_count")) or 0
    coverage = _clean_float(evidence.get("coverage_ratio"))

    signal_role = _clean_text(method_context.get("ftir_signal_role")).lower()

    modality_terms = [
        "FTIR",
        "Fourier transform infrared spectroscopy",
        "infrared spectroscopy",
        "vibrational spectroscopy",
    ]

    prioritized: list[str] = []
    rationale_parts: list[str] = []
    trust = subject_trust

    if match_status == "library_unavailable":
        search_mode = "behavior_first"
        trust = "absent" if subject_trust == "absent" else subject_trust
        prioritized.extend(
            [
                " ".join([modality_terms[0], modality_terms[1], "spectral library", "reference matching"]),
                " ".join([modality_terms[0], "spectral preprocessing", "baseline correction", "similarity metric"]),
                " ".join([modality_terms[2], "qualitative screening", "best practices"]),
            ]
        )
        rationale_parts.append(
            "The on-device reference spectral library was unavailable or not configured, so the literature query deliberately avoids "
            "asserting a ranked spectral identification and instead targets FTIR methodology and library-matching practice."
        )
    elif match_status == "matched" and top_name and confidence_band not in {"", "no_match"}:
        search_mode = "known_material" if subject_trust == "trusted" else "behavior_first"
        trust = subject_trust
        core = " ".join(part for part in [modality_terms[0], modality_terms[2], f"\"{top_name}\"", "reference spectrum"] if part)
        prioritized.append(core)
        if wn_terms:
            prioritized.append(" ".join([modality_terms[0], top_name, *wn_terms[:3], "absorption bands"]))
        if subject_label:
            prioritized.append(" ".join([quoted_subject or subject_label, modality_terms[0], top_name, "infrared"]))
        prioritized.append(" ".join([modality_terms[0], "spectral similarity", "library screening"]))
        rationale_parts.append(
            f"The literature search is anchored to the retained top spectral candidate ({top_name}) as a qualitative FTIR library outcome"
            + (f" (normalized score {top_score:.3f})." if top_score is not None else ".")
        )
        if shared_peaks:
            rationale_parts.append(f"Observed–reference overlap retained {shared_peaks} shared peak correspondences for query shaping.")
    else:
        search_mode = _infer_search_mode(subject_trust)
        trust = subject_trust
        if subject_label and search_mode == "known_material":
            prioritized.append(
                " ".join(part for part in [quoted_subject or subject_label, modality_terms[0], modality_terms[2], "absorption bands"] if part)
            )
        if wn_terms and peak_count >= 2:
            prioritized.append(" ".join([modality_terms[0], *wn_terms[:4], "infrared absorption"]))
        if peak_count >= 1 and not prioritized:
            prioritized.append(" ".join([modality_terms[0], modality_terms[3], "peak-resolved screening"]))
        prioritized.append(" ".join([modality_terms[0], modality_terms[2], "qualitative interpretation"]))
        if subject_label:
            prioritized.append(" ".join([quoted_subject or subject_label, "infrared spectroscopy", "functional groups"]))
        prioritized.append(" ".join([modality_terms[1], "spectral similarity"]))
        rationale_parts.append(
            "The FTIR literature search uses modality-first wording aligned to the current spectral-similarity summary"
            + (" and detected peak positions when available." if wn_terms else ".")
        )
        if match_status == "no_match":
            rationale_parts.append(
                "No candidate met the similarity threshold; external literature is framed as contextual vibrational spectroscopy guidance, "
                "not as validation of a library identification."
            )

    prioritized = [q for q in prioritized if _clean_text(q)]
    deduped: list[str] = []
    seen: set[str] = set()
    for q in prioritized:
        key = q.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)

    query_text = deduped[0] if deduped else " ".join([modality_terms[0], modality_terms[2], "qualitative screening"])
    fallback_queries = deduped[1:]
    rationale = " ".join(rationale_parts).strip()
    if signal_role and signal_role != "unknown":
        rationale += f" Recorded signal role: {signal_role}."

    display_title = subject_label or top_name or "FTIR spectral screening"
    display_mode = "FTIR / vibrational spectroscopy"
    display_terms = _clean_display_terms(
        modality_terms[:3],
        [top_name] if top_name else [],
        wn_terms[:3],
        [f"peaks:{peak_count}"] if peak_count else [],
    )

    evidence_snapshot: dict[str, Any] = {
        "sample_name": subject_label,
        "raw_subject": _clean_text(subject.get("raw")),
        "subject_source": _clean_text(subject.get("source")),
        "subject_trust": trust,
        "search_mode": search_mode,
        "filename_like_subject": bool(subject.get("filename_like")),
        "workflow_template": _workflow_label(record),
        "match_status": match_status,
        "confidence_band": confidence_band,
        "peak_count": peak_count,
        "top_match_name": top_name,
        "top_match_score": top_score,
        "shared_peak_count": shared_peaks,
        "coverage_ratio": coverage,
        "wavenumber_terms": wn_terms,
        "wavenumber_anchors": _numeric_anchors_from_terms(wn_terms),
        "signal_role": signal_role,
        "library_result_source": _clean_text(summary.get("library_result_source")),
    }

    return _build_payload(
        analysis_type="FTIR",
        search_mode=search_mode,
        subject_trust=trust,
        query_text=query_text,
        fallback_queries=fallback_queries,
        query_rationale=rationale,
        query_display_title=display_title,
        query_display_mode=display_mode,
        query_display_terms=display_terms,
        evidence_snapshot=evidence_snapshot,
    )


def _clean_display_terms(*groups: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            cleaned = _clean_text(item)
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(cleaned)
            if len(out) >= 10:
                return out
    return out


def build_ftir_query_presentation(query_payload: Mapping[str, Any]) -> dict[str, Any]:
    from core.thermal_literature_query_builder import build_thermal_query_presentation

    return build_thermal_query_presentation(query_payload)


def _ftir_query_is_too_narrow(query_payload: Mapping[str, Any]) -> bool:
    snap = dict(query_payload.get("evidence_snapshot") or {})
    if _clean_text(snap.get("match_status")).lower() == "library_unavailable":
        return False
    has_subject = bool(_clean_text(snap.get("sample_name")))
    has_top = bool(_clean_text(snap.get("top_match_name")))
    peaks = _clean_int(snap.get("peak_count")) or 0
    wn = snap.get("wavenumber_terms") or []
    return not has_subject and not has_top and peaks < 2 and not wn
