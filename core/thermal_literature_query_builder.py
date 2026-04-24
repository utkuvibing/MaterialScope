"""Deterministic thermal literature query builders for DSC, DTA, and TGA."""

from __future__ import annotations

import re
from pathlib import PurePath
from typing import Any, Mapping


FILENAME_EXTENSIONS = (".csv", ".txt", ".xlsx", ".xls", ".tsv", ".dat")
TECHNICAL_EDGE_TOKENS = {
    "analysis",
    "analiz",
    "dataset",
    "export",
    "file",
    "record",
    "result",
    "results",
    "run",
    "sample",
    "tga",
    "dsc",
    "dta",
    "tg",
}
PLACEHOLDER_SUBJECT_VALUES = {
    "unknown",
    "n/a",
    "na",
    "none",
    "null",
    "not recorded",
    "unnamed",
    "sample",
    "sample name",
    "specimen",
    "material",
}
PLACEHOLDER_SUBJECT_TOKENS = {
    "unknown",
    "unnamed",
    "sample",
    "specimen",
    "material",
    "dataset",
    "file",
    "record",
    "result",
    "name",
    "not",
    "recorded",
    "na",
    "none",
    "null",
}
TRUSTED_SUBJECT_SOURCES = {"summary.sample_name", "metadata.sample_name"}
CHEMICAL_ALIASES = {
    "caco3": ["calcium carbonate", "calcite"],
}
FORMULA_PATTERN = re.compile(r"\b(?:[A-Z][a-z]?\d*){2,}\b")


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


def _tokenize(value: str) -> list[str]:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in str(value or "").lower())
    return [token for token in cleaned.split() if token]


def _rows(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in (record.get("rows") or []) if isinstance(item, Mapping)]


def _summary(record: Mapping[str, Any]) -> dict[str, Any]:
    return dict(record.get("summary") or {})


def _metadata(record: Mapping[str, Any]) -> dict[str, Any]:
    return dict(record.get("metadata") or {})


def _workflow_label(record: Mapping[str, Any]) -> str:
    processing = dict(record.get("processing") or {})
    return _clean_text(processing.get("workflow_template_label") or processing.get("workflow_template"))


def _strip_filename_artifacts(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = PurePath(text).name
    lowered = text.lower()
    for extension in FILENAME_EXTENSIONS:
        if lowered.endswith(extension):
            text = text[: -len(extension)]
            break
    text = text.replace("_", " ").replace("\\", " ").replace("/", " ")
    text = re.sub(r"\s+", " ", text).strip(" -_.")
    tokens = [token for token in re.split(r"\s+", text) if token]
    while tokens and tokens[0].lower() in TECHNICAL_EDGE_TOKENS:
        tokens.pop(0)
    while tokens and tokens[-1].lower() in TECHNICAL_EDGE_TOKENS:
        tokens.pop()
    text = " ".join(tokens)
    text = re.sub(r"\s+", " ", text).strip(" -_.")
    return text


def _looks_like_filename(value: Any) -> bool:
    text = _clean_text(value)
    if not text:
        return False
    lowered = text.lower()
    if any(marker in text for marker in ("\\", "/")):
        return True
    if any(lowered.endswith(extension) for extension in FILENAME_EXTENSIONS):
        return True
    if re.search(r"\b(?:tga|dsc|dta|tg)[\s_-]", lowered):
        return True
    if lowered.startswith(("result_", "results_", "analysis_", "dataset_", "sample_")):
        return True
    if "__" in text or text.count("_") >= 1:
        return True
    return False


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in values:
        cleaned = _clean_text(item)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output


def _is_placeholder_subject(value: str) -> bool:
    lowered = _clean_text(value).lower()
    if lowered in PLACEHOLDER_SUBJECT_VALUES:
        return True
    tokens = _tokenize(lowered)
    if not tokens:
        return True
    return all(token in PLACEHOLDER_SUBJECT_TOKENS for token in tokens)


def _is_scientific_subject(value: str) -> bool:
    cleaned = _strip_filename_artifacts(value)
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if lowered in {"tga", "dsc", "dta", "thermal", "decomposition", "thermal event"}:
        return False
    if _is_placeholder_subject(cleaned):
        return False
    tokens = _tokenize(cleaned)
    if not tokens:
        return False
    return any(any(ch.isalpha() for ch in token) for token in tokens) or any(any(ch.isdigit() for ch in token) for token in tokens)


def _normalized_subject_candidates(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    summary = _summary(record)
    metadata = _metadata(record)
    raw_candidates = [
        ("summary.sample_name", summary.get("sample_name")),
        ("metadata.sample_name", metadata.get("sample_name")),
        ("metadata.display_name", metadata.get("display_name")),
        ("metadata.file_name", metadata.get("file_name")),
    ]
    ranked: list[dict[str, Any]] = []
    for index, (source, raw_value) in enumerate(raw_candidates):
        raw = _clean_text(raw_value)
        cleaned = _strip_filename_artifacts(raw)
        if not cleaned:
            continue
        if _is_placeholder_subject(cleaned):
            continue
        filename_like = _looks_like_filename(raw)
        score = 100 - index * 10
        if source.endswith("sample_name"):
            score += 20
        if filename_like:
            score -= 35
        if not _is_scientific_subject(cleaned):
            score -= 20
        ranked.append(
            {
                "source": source,
                "raw": raw,
                "cleaned": cleaned,
                "filename_like": filename_like,
                "quote_safe": not filename_like and _is_scientific_subject(cleaned),
                "score": score,
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["source"]))
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in ranked:
        key = item["cleaned"].casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _best_subject(record: Mapping[str, Any]) -> dict[str, Any]:
    candidates = _normalized_subject_candidates(record)
    if candidates:
        return candidates[0]
    return {
        "source": "",
        "raw": "",
        "cleaned": "",
        "filename_like": False,
        "quote_safe": False,
        "score": 0,
    }


def _infer_subject_trust(subject: Mapping[str, Any]) -> str:
    cleaned = _clean_text(subject.get("cleaned"))
    if not cleaned:
        return "absent"
    source = _clean_text(subject.get("source"))
    if source not in TRUSTED_SUBJECT_SOURCES:
        return "low_trust"
    if bool(subject.get("filename_like")):
        return "low_trust"
    if not _is_scientific_subject(cleaned):
        return "low_trust"
    return "trusted"


def _infer_search_mode(subject_trust: str) -> str:
    return "known_material" if _clean_text(subject_trust).lower() == "trusted" else "behavior_first"


def _quoted_subject(subject: Mapping[str, Any]) -> str:
    cleaned = _clean_text(subject.get("cleaned"))
    if cleaned and subject.get("quote_safe"):
        return f"\"{cleaned}\""
    return cleaned


def _subject_expansions(subject: Mapping[str, Any]) -> list[str]:
    subject_tokens = _tokenize(_clean_text(subject.get("cleaned")))
    expansions: list[str] = []
    for token in subject_tokens:
        expansions.extend(CHEMICAL_ALIASES.get(token.lower(), []))
    return _dedupe(expansions)


def _formula_like_tokens(value: str) -> list[str]:
    return _dedupe(FORMULA_PATTERN.findall(_clean_text(value)))


def _tga_process_expansions(*, subject: Mapping[str, Any], midpoint: int | None, total_mass_loss: float | None) -> list[str]:
    tokens = {token.lower() for token in _tokenize(_clean_text(subject.get("cleaned")))}
    expansions: list[str] = []
    if "caco3" in tokens or any(alias in _subject_expansions(subject) for alias in ("calcium carbonate", "calcite")):
        expansions.extend(["decarbonation", "calcination", "CaO", "CO2 release"])
    if midpoint is not None and 680 <= midpoint <= 820 and total_mass_loss is not None and 40.0 <= total_mass_loss <= 48.0:
        expansions.extend(["decarbonation", "calcination", "CO2 release"])
    return _dedupe(expansions)


def _generic_subject_query(subject: Mapping[str, Any], *, analysis_type: str, fallback_label: str) -> str:
    cleaned = _clean_text(subject.get("cleaned"))
    if cleaned:
        return " ".join(part for part in [cleaned, analysis_type, fallback_label] if part)
    return f"{analysis_type} {fallback_label}"


def _build_payload(
    *,
    analysis_type: str,
    search_mode: str,
    subject_trust: str,
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
        "search_mode": _clean_text(search_mode).lower(),
        "subject_trust": _clean_text(subject_trust).lower(),
        "query_text": _clean_text(query_text),
        "fallback_queries": _dedupe([_clean_text(item) for item in fallback_queries if _clean_text(item)]),
        "query_rationale": _clean_text(query_rationale),
        "query_display_title": _clean_text(query_display_title),
        "query_display_mode": _clean_text(query_display_mode),
        "query_display_terms": _dedupe([_clean_text(item) for item in query_display_terms if _clean_text(item)]),
        "evidence_snapshot": dict(evidence_snapshot or {}),
    }


def build_dsc_literature_query(record: Mapping[str, Any]) -> dict[str, Any]:
    summary = _summary(record)
    rows = _rows(record)
    subject = _best_subject(record)
    subject_trust = _infer_subject_trust(subject)
    search_mode = _infer_search_mode(subject_trust)
    subject_label = _clean_text(subject.get("cleaned"))
    quoted_subject = _quoted_subject(subject)
    tg_midpoint = _round_temperature(summary.get("tg_midpoint"))
    first_peak = rows[0] if rows else {}
    peak_type = _clean_text(first_peak.get("peak_type")).lower()
    peak_temp = _round_temperature(first_peak.get("peak_temperature"))
    peak_count = _clean_int(summary.get("peak_count")) or len(rows)
    glass_transition_count = _clean_int(summary.get("glass_transition_count")) or 0

    if tg_midpoint is not None:
        if search_mode == "known_material":
            query_text = " ".join(
                part for part in [quoted_subject, "DSC glass transition thermal analysis", f"{tg_midpoint} C"] if part
            )
            fallback_queries = [
                _generic_subject_query(subject, analysis_type="DSC", fallback_label="glass transition"),
                "DSC glass transition calorimetry",
                _generic_subject_query(subject, analysis_type="thermal analysis", fallback_label="glass transition polymer"),
            ]
            rationale = f"The DSC literature search is centered on a glass-transition signal near {tg_midpoint} C."
        else:
            query_text = " ".join(part for part in ["DSC glass transition thermal analysis", f"{tg_midpoint} C"] if part)
            fallback_queries = [
                "DSC glass transition calorimetry",
                "thermal analysis glass transition polymer",
                "differential scanning calorimetry glass transition",
            ]
            if subject_label:
                fallback_queries.append(_generic_subject_query(subject, analysis_type="DSC", fallback_label="glass transition"))
            fallback_queries.append(f"DSC glass transition {tg_midpoint} C polymer")
            rationale = f"The DSC literature search uses behavior-first semantics centered on a glass-transition signal near {tg_midpoint} C."
        display_title = subject_label or "DSC glass transition"
        display_terms = ["glass transition", "calorimetry", "thermal event"]
    else:
        event_label = peak_type or "thermal event"
        if search_mode == "known_material":
            query_text = " ".join(
                part
                for part in [quoted_subject, "DSC thermal event calorimetry", event_label, f"{peak_temp} C" if peak_temp is not None else ""]
                if part
            )
            fallback_queries = [
                _generic_subject_query(subject, analysis_type="DSC", fallback_label="thermal event"),
                "DSC endothermic exothermic event calorimetry",
                _generic_subject_query(subject, analysis_type="thermal analysis", fallback_label=event_label),
            ]
            rationale = f"The DSC literature search is centered on the leading {event_label} event" + (f" near {peak_temp} C." if peak_temp is not None else ".")
        else:
            query_text = " ".join(
                part for part in ["DSC thermal event calorimetry", event_label, f"{peak_temp} C" if peak_temp is not None else ""] if part
            )
            fallback_queries = [
                "DSC endothermic exothermic event calorimetry",
                "differential scanning calorimetry thermal analysis",
            ]
            if peak_type in ("endo", "endotherm", "endothermic"):
                fallback_queries.append("DSC endotherm endothermic peak calorimetry")
            elif peak_type in ("exo", "exotherm", "exothermic"):
                fallback_queries.append("DSC exotherm exothermic peak crystallization calorimetry")
            else:
                fallback_queries.append("DSC endothermic exothermic thermal event")
            if subject_label:
                fallback_queries.append(_generic_subject_query(subject, analysis_type="DSC", fallback_label=event_label))
            fallback_queries.append(_generic_subject_query(subject, analysis_type="thermal analysis", fallback_label=event_label))
            if peak_temp is not None:
                fallback_queries.append(f"DSC thermal event {peak_temp} C")
            rationale = f"The DSC literature search uses behavior-first semantics centered on the leading {event_label} event" + (
                f" near {peak_temp} C." if peak_temp is not None else "."
            )
        display_title = subject_label or "DSC thermal event"
        display_terms = ["thermal event", "calorimetry", event_label]

    return _build_payload(
        analysis_type="DSC",
        search_mode=search_mode,
        subject_trust=subject_trust,
        query_text=query_text,
        fallback_queries=fallback_queries,
        query_rationale=rationale,
        query_display_title=display_title,
        query_display_mode="DSC / thermal interpretation",
        query_display_terms=display_terms,
        evidence_snapshot={
            "sample_name": subject_label,
            "raw_subject": _clean_text(subject.get("raw")),
            "subject_source": _clean_text(subject.get("source")),
            "subject_trust": subject_trust,
            "search_mode": search_mode,
            "filename_like_subject": bool(subject.get("filename_like")),
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
    subject = _best_subject(record)
    subject_trust = _infer_subject_trust(subject)
    search_mode = _infer_search_mode(subject_trust)
    subject_label = _clean_text(subject.get("cleaned"))
    quoted_subject = _quoted_subject(subject)
    first_peak = rows[0] if rows else {}
    direction = _clean_text(first_peak.get("peak_type") or first_peak.get("direction")).lower() or "thermal event"
    peak_temp = _round_temperature(first_peak.get("peak_temperature"))
    processing = dict(record.get("processing") or {})
    method_context = dict(processing.get("method_context") or {})

    if search_mode == "known_material":
        query_text = " ".join(
            part for part in [quoted_subject, "DTA differential thermal analysis", direction, f"{peak_temp} C" if peak_temp is not None else ""] if part
        )
        fallback_queries = [
            _generic_subject_query(subject, analysis_type="DTA", fallback_label="thermal event"),
            "DTA endothermic exothermic event differential thermal analysis",
            _generic_subject_query(subject, analysis_type="DTA", fallback_label=direction),
        ]
        rationale = f"The DTA literature search is centered on the leading {direction} event" + (f" near {peak_temp} C." if peak_temp is not None else ".")
    else:
        query_text = " ".join(part for part in ["DTA differential thermal analysis", direction, f"{peak_temp} C" if peak_temp is not None else ""] if part)
        fallback_queries = [
            "DTA endothermic exothermic event differential thermal analysis",
            _generic_subject_query(subject, analysis_type="DTA", fallback_label=direction),
        ]
        if subject_label:
            fallback_queries.append(_generic_subject_query(subject, analysis_type="DTA", fallback_label="thermal event"))
        rationale = f"The DTA literature search uses behavior-first semantics centered on the leading {direction} event" + (
            f" near {peak_temp} C." if peak_temp is not None else "."
        )
    return _build_payload(
        analysis_type="DTA",
        search_mode=search_mode,
        subject_trust=subject_trust,
        query_text=query_text,
        fallback_queries=fallback_queries,
        query_rationale=rationale,
        query_display_title=subject_label or "DTA thermal event",
        query_display_mode="DTA / thermal events",
        query_display_terms=["thermal event", "differential thermal analysis", direction],
        evidence_snapshot={
            "sample_name": subject_label,
            "raw_subject": _clean_text(subject.get("raw")),
            "subject_source": _clean_text(subject.get("source")),
            "subject_trust": subject_trust,
            "search_mode": search_mode,
            "filename_like_subject": bool(subject.get("filename_like")),
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
    subject = _best_subject(record)
    subject_trust = _infer_subject_trust(subject)
    search_mode = _infer_search_mode(subject_trust)
    subject_label = _clean_text(subject.get("cleaned"))
    quoted_subject = _quoted_subject(subject)
    first_step = rows[0] if rows else {}
    midpoint = _round_temperature(first_step.get("midpoint_temperature"))
    total_mass_loss = _clean_float(summary.get("total_mass_loss_percent"))
    residue = _clean_float(summary.get("residue_percent"))
    subject_aliases = _subject_expansions(subject)
    subject_formulas = _formula_like_tokens(subject_label)
    process_terms = _tga_process_expansions(subject=subject, midpoint=midpoint, total_mass_loss=total_mass_loss)
    preferred_entity = subject_aliases[0] if subject_aliases else subject_label
    temperature_band = ""
    if midpoint is not None:
        lower = max(0, (midpoint // 100) * 100)
        upper = lower + 100
        temperature_band = f"{lower} {upper} C"

    prioritized_queries: list[str] = []
    if search_mode == "known_material":
        if preferred_entity:
            primary_process = "decarbonation" if "decarbonation" in [term.lower() for term in process_terms] else "decomposition"
            prioritized_queries.append(
                " ".join(part for part in [preferred_entity, "thermogravimetric analysis", primary_process] if part)
            )
        if subject_formulas:
            formula = subject_formulas[0]
            formula_parts = [formula, "calcination", "TGA"]
            if "CaO" in process_terms:
                formula_parts.append("CaO")
            if "CO2 release" in process_terms:
                formula_parts.append("CO2")
            prioritized_queries.append(" ".join(formula_parts))
        if len(subject_aliases) > 1:
            prioritized_queries.append(" ".join([subject_aliases[1], "decomposition", "thermogravimetric analysis"]))
        elif preferred_entity:
            prioritized_queries.append(" ".join([preferred_entity, "decomposition", "thermogravimetric analysis"]))
        if preferred_entity and temperature_band:
            prioritized_queries.append(" ".join([preferred_entity, "decomposition mass loss", temperature_band]))
        elif quoted_subject:
            prioritized_queries.append(" ".join(part for part in [quoted_subject, "decomposition mass loss residue", f"{midpoint} C" if midpoint is not None else ""] if part))
        prioritized_queries.append("thermogravimetric analysis decomposition mass loss residue")
        if subject_label and not subject.get("quote_safe"):
            prioritized_queries.insert(1, f"{subject_label} thermogravimetric analysis decomposition")
        if process_terms:
            process_query_parts = [preferred_entity] if preferred_entity else ([subject_label] if subject_label else [])
            prioritized_queries.append(" ".join(process_query_parts + process_terms + ["thermogravimetric analysis"]))
    else:
        primary_parts = ["thermogravimetric analysis", "decomposition mass loss residue"]
        if midpoint is not None:
            primary_parts.append(f"{midpoint} C")
        prioritized_queries.append(" ".join(primary_parts))
        if temperature_band:
            prioritized_queries.append(" ".join(["TGA decomposition mass loss", temperature_band]))
        if process_terms:
            prioritized_queries.append(" ".join(_dedupe(["TGA", *process_terms[:3], "thermogravimetric analysis"])))
        prioritized_queries.append("TGA thermogravimetric analysis decomposition mass loss residue")
        if subject_label:
            prioritized_queries.append(f"{subject_label} thermogravimetric analysis decomposition")
        if subject_formulas:
            prioritized_queries.append(" ".join([subject_formulas[0], "thermogravimetric analysis decomposition"]))
        if subject_aliases:
            prioritized_queries.append(" ".join([subject_aliases[0], "thermogravimetric analysis decomposition"]))
        if len(subject_aliases) > 1:
            prioritized_queries.append(" ".join([subject_aliases[1], "decomposition", "thermogravimetric analysis"]))

    query_text = prioritized_queries[0] if prioritized_queries else "thermogravimetric analysis decomposition mass loss residue"
    fallback_queries = prioritized_queries[1:]
    rationale = (
        "The TGA literature search is centered on the decomposition profile"
        if search_mode == "known_material"
        else "The TGA literature search uses behavior-first semantics centered on the decomposition profile"
    )
    if midpoint is not None:
        rationale += f" with a leading step near {midpoint} C"
    if total_mass_loss is not None:
        rationale += f" and total mass loss around {total_mass_loss:.1f}%"
    rationale += "."
    return _build_payload(
        analysis_type="TGA",
        search_mode=search_mode,
        subject_trust=subject_trust,
        query_text=query_text,
        fallback_queries=fallback_queries,
        query_rationale=rationale,
        query_display_title=subject_label or (subject_aliases[0] if subject_aliases else "TGA decomposition profile"),
        query_display_mode="TGA / decomposition profile",
        query_display_terms=["decomposition", "mass loss", "residue", *subject_aliases[:2], *process_terms[:2]],
        evidence_snapshot={
            "sample_name": subject_label,
            "raw_subject": _clean_text(subject.get("raw")),
            "subject_source": _clean_text(subject.get("source")),
            "subject_trust": subject_trust,
            "search_mode": search_mode,
            "filename_like_subject": bool(subject.get("filename_like")),
            "subject_aliases": subject_aliases,
            "subject_formulas": subject_formulas,
            "workflow_template": _workflow_label(record),
            "step_count": _clean_int(summary.get("step_count")) or len(rows),
            "total_mass_loss_percent": total_mass_loss,
            "residue_percent": residue,
            "midpoint_temperature": _clean_float(first_step.get("midpoint_temperature")),
            "mass_loss_percent": _clean_float(first_step.get("mass_loss_percent")),
            "process_terms": process_terms,
            "temperature_band_query": temperature_band,
        },
    )


def build_thermal_query_presentation(query_payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "display_title": _clean_text(query_payload.get("query_display_title")) or "Thermal literature search",
        "display_mode": _clean_text(query_payload.get("query_display_mode")) or "Thermal / interpretation",
        "display_terms": [_clean_text(item) for item in (query_payload.get("query_display_terms") or []) if _clean_text(item)],
        "raw_query": _clean_text(query_payload.get("query_text")),
    }
