"""Shared XRD candidate display-name helpers."""

from __future__ import annotations

import re
from typing import Any, Mapping

_COD_RAW_LABEL_RE = re.compile(r"^\s*cod[\s#:_-]*0*(\d+)\s*$", re.IGNORECASE)
_COD_ID_RE = re.compile(r"\bcod[\s#:_-]*0*(\d+)\b", re.IGNORECASE)
_MP_RAW_LABEL_RE = re.compile(r"^\s*(?:materials[\s_-]*project[\s_-]*)?mp[\s#:_-]*0*(\d+)\s*$", re.IGNORECASE)
_MP_ID_RE = re.compile(r"\bmp[\s#:_-]*0*(\d+)\b", re.IGNORECASE)
_FORMULA_SEGMENT_RE = re.compile(r"[A-Z][A-Za-z0-9().·+\-]*")
_FORMULA_COUNT_RE = re.compile(r"(?<=[A-Za-z\)])(\d+(?:\.\d+)?)")
_UNICODE_SUBSCRIPTS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def _text(value: Any) -> str | None:
    token = str(value or "").strip()
    return token or None


def _first_text(payloads: tuple[Mapping[str, Any], ...], *keys: str) -> str | None:
    for payload in payloads:
        for key in keys:
            token = _text(payload.get(key))
            if token:
                return token
    return None


def _normalize_provider(value: Any) -> str:
    token = str(value or "").strip().lower().replace(" ", "_")
    if token in {"materialsproject", "materials_project", "materials-project", "mp"}:
        return "materials_project"
    return token


def _extract_cod_id(*values: Any) -> str | None:
    for value in values:
        token = _text(value)
        if not token:
            continue
        exact = _COD_RAW_LABEL_RE.match(token)
        if exact:
            return exact.group(1)
        partial = _COD_ID_RE.search(token)
        if partial:
            return partial.group(1)
        if token.isdigit():
            return token
    return None


def _extract_materials_project_id(*values: Any) -> str | None:
    for value in values:
        token = _text(value)
        if not token:
            continue
        exact = _MP_RAW_LABEL_RE.match(token)
        if exact:
            return f"mp-{int(exact.group(1))}"
        partial = _MP_ID_RE.search(token.replace("_", "-"))
        if partial:
            return f"mp-{int(partial.group(1))}"
    return None


def _is_raw_provider_label(label: str | None, *, provider: str, candidate_id: str | None, source_id: str | None) -> bool:
    token = _text(label)
    if not token:
        return False
    if provider == "cod":
        return _COD_RAW_LABEL_RE.match(token) is not None
    if provider == "materials_project":
        return _MP_RAW_LABEL_RE.match(token.replace("_", "-")) is not None
    normalized = token.lower().replace(" ", "_")
    return normalized in {
        str(candidate_id or "").strip().lower().replace("-", "_"),
        str(source_id or "").strip().lower().replace("-", "_"),
    }


def _format_formula_count(value: str, *, target: str) -> str:
    if target == "html":
        return f"<sub>{value}</sub>"
    if target == "unicode":
        return value.translate(_UNICODE_SUBSCRIPTS)
    return value


def _format_formula_segment(segment: str, *, target: str) -> str:
    return _FORMULA_COUNT_RE.sub(lambda match: _format_formula_count(match.group(1), target=target), segment)


def format_scientific_formula_text(value: Any, target: str = "unicode") -> str | None:
    text = _text(value)
    if text is None:
        return None
    if target == "plain":
        return text
    if target not in {"unicode", "html"}:
        raise ValueError(f"Unsupported scientific formula target: {target}")

    def _replace(match: re.Match[str]) -> str:
        segment = match.group(0)
        if not _FORMULA_COUNT_RE.search(segment):
            return segment
        return _format_formula_segment(segment, target=target)

    return _FORMULA_SEGMENT_RE.sub(_replace, text)


def xrd_candidate_display_payload(
    match_or_row: Mapping[str, Any] | None,
    reference_entry: Mapping[str, Any] | None = None,
) -> dict[str, str | None]:
    primary = dict(match_or_row or {})
    reference = dict(reference_entry or {})
    payloads = (primary, reference)

    provider = _first_text(payloads, "library_provider", "top_candidate_provider", "provider")
    package = _first_text(payloads, "library_package", "top_candidate_package", "package_id")
    candidate_name = _first_text(payloads, "candidate_name", "top_candidate_name", "top_phase", "top_match_name")
    candidate_id = _first_text(payloads, "candidate_id", "top_candidate_id", "top_phase_id", "top_match_id")
    source_id = _first_text(payloads, "source_id", "top_candidate_source_id")
    phase_name = _first_text(payloads, "phase_name", "top_candidate_phase_name")
    formula_pretty = _first_text(payloads, "formula_pretty", "top_candidate_formula_pretty")
    formula = _first_text(payloads, "formula", "top_candidate_formula")
    cod_id = _extract_cod_id(candidate_name, candidate_id, source_id)
    mp_id = _extract_materials_project_id(candidate_name, candidate_id, source_id)
    provider_token = _normalize_provider(provider)
    if not provider_token:
        if cod_id:
            provider_token = "cod"
        elif mp_id:
            provider_token = "materials_project"

    explicit_display = _first_text(payloads, "display_name", "top_candidate_display_name", "top_phase_display_name")
    if explicit_display:
        display_name = explicit_display
    elif phase_name:
        display_name = phase_name
    elif formula_pretty:
        display_name = formula_pretty
    elif formula:
        display_name = formula
    else:
        if candidate_name and not _is_raw_provider_label(
            candidate_name,
            provider=provider_token,
            candidate_id=candidate_id,
            source_id=source_id,
        ):
            display_name = candidate_name
        else:
            display_name = None
            if provider_token == "cod":
                if cod_id:
                    display_name = f"COD #{cod_id}"
            elif provider_token == "materials_project":
                if mp_id:
                    display_name = f"Materials Project {mp_id}"
            if not display_name:
                display_name = candidate_name or candidate_id or source_id

    return {
        "display_name": _text(display_name),
        "phase_name": phase_name,
        "formula_pretty": formula_pretty,
        "formula": formula,
        "candidate_name": candidate_name,
        "candidate_id": candidate_id,
        "source_id": source_id,
        "library_provider": provider,
        "library_package": package,
    }


def xrd_candidate_display_name(
    match_or_row: Mapping[str, Any] | None,
    reference_entry: Mapping[str, Any] | None = None,
    *,
    target: str = "plain",
) -> str | None:
    if target == "plain":
        return xrd_candidate_display_payload(match_or_row, reference_entry).get("display_name")
    return xrd_candidate_display_variants(match_or_row, reference_entry).get(f"{target}_display_name")


def xrd_candidate_display_variants(
    match_or_row: Mapping[str, Any] | None,
    reference_entry: Mapping[str, Any] | None = None,
) -> dict[str, str | None]:
    base_label = xrd_candidate_display_payload(match_or_row, reference_entry).get("display_name")
    return {
        "raw_display_name": base_label,
        "plain_display_name": format_scientific_formula_text(base_label, target="plain"),
        "unicode_display_name": format_scientific_formula_text(base_label, target="unicode"),
        "html_display_name": format_scientific_formula_text(base_label, target="html"),
    }
