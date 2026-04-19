"""Shared literature compare rendering for Dash analysis pages (DTA, DSC, ...)."""

from __future__ import annotations

from typing import Any

import dash_bootstrap_components as dbc
from dash import html

from utils.i18n import translate_ui


def literature_t(loc: str, key: str, fallback: str) -> str:
    """Translate with a literal fallback when the key is missing from the bundle."""
    value = translate_ui(loc, key)
    return fallback if value == key else value


def _collapsible_section(loc: str, title_key: str, body: Any, *, open: bool = False) -> html.Details:
    return html.Details(
        [
            html.Summary(
                [
                    html.Span(className="ta-details-chevron"),
                    html.Span(translate_ui(loc, title_key), className="ms-1"),
                ],
                className="ta-details-summary",
            ),
            html.Div(body, className="ta-details-body mt-2"),
        ],
        className="ta-ms-details mb-0",
        open=open,
    )


def render_literature_output(payload: dict, loc: str, *, i18n_prefix: str) -> html.Div:
    """Render literature compare payload as curated product-facing sections."""
    claims = payload.get("literature_claims") or []
    comparisons = payload.get("literature_comparisons") or []
    citations = payload.get("citations") or []
    context = payload.get("literature_context") if isinstance(payload.get("literature_context"), dict) else {}

    def _k(suffix: str) -> str:
        return f"{i18n_prefix}.{suffix}"

    def _clean_text(value) -> str:
        if value in (None, ""):
            return ""
        return str(value).strip()

    def _entry_text(entry: dict) -> str:
        text = (
            entry.get("claim_text")
            or entry.get("statement")
            or entry.get("claim")
            or entry.get("title")
            or entry.get("summary")
            or entry.get("comparison_note")
            or entry.get("rationale")
            or ""
        )
        return _clean_text(text)

    def _is_meaningful_entry(entry: dict) -> bool:
        if _entry_text(entry):
            return True
        for key in ("doi", "source", "provider", "citation_id", "paper_title", "paper_doi"):
            if _clean_text(entry.get(key)):
                return True
        return False

    def _context_token(key: str) -> str:
        return _clean_text(context.get(key)).lower()

    def _context_bool(key: str) -> bool:
        return bool(context.get(key))

    def _citation_title(citation: dict) -> str:
        return _clean_text(
            citation.get("title")
            or citation.get("paper_title")
            or citation.get("citation_text")
            or citation.get("doi")
            or citation.get("url")
        )

    def _citation_meta(citation: dict) -> str:
        parts: list[str] = []
        year = _clean_text(citation.get("year"))
        journal = _clean_text(citation.get("journal"))
        doi = _clean_text(citation.get("doi"))
        if year:
            parts.append(year)
        if journal:
            parts.append(journal)
        if doi:
            parts.append(f"DOI: {doi}")
        return " | ".join(parts)

    def _reason_text() -> str:
        status_token = _context_token("provider_query_status")
        reason_token = _context_token("no_results_reason")
        token = reason_token or status_token
        if token == "provider_unavailable":
            return literature_t(loc, _k("status.reason.provider_unavailable"), "")
        if token == "request_failed":
            return literature_t(loc, _k("status.reason.request_failed"), "")
        if token == "not_configured":
            return literature_t(loc, _k("status.reason.not_configured"), "")
        if token == "query_too_narrow":
            return literature_t(loc, _k("status.reason.query_too_narrow"), "")
        return literature_t(loc, _k("status.reason.no_retained"), "")

    def _comparison_citation_ids(entry: dict) -> list[str]:
        raw_ids = entry.get("citation_ids") or []
        if isinstance(raw_ids, str):
            raw_ids = [raw_ids]
        return [_clean_text(item) for item in raw_ids if _clean_text(item)]

    citation_by_id: dict[str, dict] = {}
    for entry in citations:
        if not isinstance(entry, dict):
            continue
        citation_id = _clean_text(entry.get("citation_id"))
        if citation_id and citation_id not in citation_by_id:
            citation_by_id[citation_id] = entry

    retained_rows: list[dict[str, Any]] = []
    consumed_citation_ids: set[str] = set()

    for entry in comparisons:
        if not isinstance(entry, dict) or not _is_meaningful_entry(entry):
            continue
        citation_ids = _comparison_citation_ids(entry)
        linked_citations = [citation_by_id[citation_id] for citation_id in citation_ids if citation_id in citation_by_id]
        consumed_citation_ids.update(citation_ids)

        title = _entry_text(entry)
        if not title and linked_citations:
            title = _citation_title(linked_citations[0])
        if not title:
            title = literature_t(loc, _k("evidence.generic_title"), "Retained literature reference")

        provider = _clean_text(entry.get("provider") or entry.get("provider_id") or entry.get("source"))
        rationale = _clean_text(entry.get("rationale") or entry.get("comparison_note"))
        citation_titles = [_citation_title(item) for item in linked_citations if _citation_title(item)]

        support = _clean_text(entry.get("support_label")).lower()
        posture = _clean_text(entry.get("validation_posture")).lower()
        is_alternative = support == "contradicts" or posture == "alternative_interpretation"

        retained_rows.append(
            {
                "title": title,
                "provider": provider,
                "rationale": rationale,
                "citation_titles": citation_titles,
                "is_alternative": is_alternative,
            }
        )

    for entry in citations:
        if not isinstance(entry, dict) or not _is_meaningful_entry(entry):
            continue
        citation_id = _clean_text(entry.get("citation_id"))
        if citation_id and citation_id in consumed_citation_ids:
            continue
        title = _citation_title(entry)
        if not title:
            continue
        provider = _clean_text(entry.get("provider") or entry.get("source"))
        provenance = entry.get("provenance")
        if not provider and isinstance(provenance, dict):
            provider = _clean_text(provenance.get("provider_id"))
        retained_rows.append(
            {
                "title": title,
                "provider": provider,
                "rationale": _citation_meta(entry),
                "citation_titles": [],
                "is_alternative": False,
            }
        )

    relevant_rows = [row for row in retained_rows if not row.get("is_alternative")]
    alternative_rows = [row for row in retained_rows if row.get("is_alternative")]
    has_retained_evidence = bool(relevant_rows or alternative_rows)

    claim_items = []
    for entry in claims:
        if not isinstance(entry, dict):
            continue
        text = _entry_text(entry)
        if text:
            claim_items.append(html.Li(text, className="small"))

    def _render_evidence_rows(rows: list[dict[str, Any]]) -> list[html.Div]:
        rendered: list[html.Div] = []
        for row in rows:
            meta_parts: list[str] = []
            if row.get("provider"):
                meta_parts.append(
                    literature_t(loc, _k("evidence.provider_prefix"), "Source: {source}").replace("{source}", str(row["provider"]))
                )
            citation_titles = row.get("citation_titles") or []
            if citation_titles:
                cite_summary = ", ".join(citation_titles[:2])
                if len(citation_titles) > 2:
                    cite_summary += "..."
                meta_parts.append(
                    literature_t(loc, _k("evidence.citations_prefix"), "Linked citations: {titles}").replace("{titles}", cite_summary)
                )
            rendered.append(
                html.Div(
                    [
                        html.Div(row["title"], className="fw-semibold small"),
                        html.P(row["rationale"], className="small mb-1") if row.get("rationale") else None,
                        html.P(" | ".join(meta_parts), className="small text-muted mb-0") if meta_parts else None,
                    ],
                    className="border rounded p-2 mb-2",
                )
            )
        return rendered

    children: list[Any] = []

    if claim_items:
        children.append(
            html.Div(
                [
                    html.H6(literature_t(loc, _k("claims_generated"), "Generated interpretation claims"), className="mt-2 mb-1"),
                    html.P(
                        literature_t(
                            loc,
                            _k("claims_note"),
                            "These claims are generated from the analysis interpretation and are not retained external literature evidence on their own.",
                        ),
                        className="small text-muted mb-1",
                    ),
                    html.Ul(claim_items, className="mb-0 ps-3"),
                ],
                className="mb-3",
            )
        )

    children.append(
        html.Div(
            [
                html.H6(literature_t(loc, _k("retained_evidence_title"), "Retained literature evidence"), className="mt-2 mb-1"),
                html.Div(
                    [
                        html.H6(literature_t(loc, _k("relevant_references"), "Relevant retained references"), className="mt-2 mb-1"),
                        html.Div(_render_evidence_rows(relevant_rows))
                        if relevant_rows
                        else html.P(
                            literature_t(loc, _k("relevant_references_empty"), "No relevant retained references were found."),
                            className="small text-muted mb-1",
                        ),
                    ]
                ),
                html.Div(
                    [
                        html.H6(
                            literature_t(loc, _k("alternative_references"), "Alternative or non-validating references"),
                            className="mt-2 mb-1",
                        ),
                        html.Div(_render_evidence_rows(alternative_rows))
                        if alternative_rows
                        else html.P(
                            literature_t(loc, _k("alternative_references_empty"), "No alternative or non-validating references were retained."),
                            className="small text-muted mb-1",
                        ),
                    ]
                ),
            ],
            className="mb-2",
        )
    )

    if not has_retained_evidence:
        follow_up: list[str] = []
        reason_token = _context_token("no_results_reason") or _context_token("provider_query_status")
        if reason_token in {"query_too_narrow"} or _context_bool("low_specificity_retrieval"):
            follow_up.append(literature_t(loc, _k("follow_up.refine_query"), ""))
        if reason_token in {"provider_unavailable", "request_failed", "not_configured"}:
            follow_up.append(literature_t(loc, _k("follow_up.retry_provider"), ""))
        if _context_bool("metadata_only_evidence") or not _context_bool("real_literature_available"):
            follow_up.append(literature_t(loc, _k("follow_up.add_accessible_sources"), ""))
        follow_up = [x for x in follow_up if x][:2]
        children.append(
            html.Div(
                [
                    html.H6(literature_t(loc, _k("no_evidence_title"), "No retained literature evidence"), className="mt-2 mb-1"),
                    html.P(_reason_text(), className="small text-muted mb-1"),
                    html.Ul([html.Li(item, className="small") for item in follow_up], className="mb-0 ps-3") if follow_up else None,
                ],
                className="mt-2",
            )
        )

    technical_rows: list[Any] = []

    def _technical_line(key_suffix: str, fallback: str, value) -> None:
        text = _clean_text(value)
        if not text:
            return
        technical_rows.append(
            html.Li(
                [
                    html.Strong(f"{literature_t(loc, _k(key_suffix), fallback)}: "),
                    text,
                ],
                className="small",
            )
        )

    _technical_line("technical.provider_status", "Provider status", context.get("provider_query_status"))
    _technical_line("technical.no_results_reason", "No-results reason", context.get("no_results_reason"))
    if context.get("source_count") is not None:
        _technical_line("technical.source_count", "Source count", context.get("source_count"))
    if context.get("citation_count") is not None:
        _technical_line("technical.citation_count", "Citation count", context.get("citation_count"))
    _technical_line("technical.provider_note", "Provider note", context.get("provider_error_message"))
    _technical_line("technical.query", "Technical query", context.get("query_text"))

    if technical_rows:
        children.append(
            html.Div(
                _collapsible_section(
                    loc,
                    _k("technical_details_title"),
                    html.Ul(technical_rows, className="mb-0 ps-3"),
                    open=False,
                ),
                className="mt-2",
            )
        )

    return html.Div(children)


def literature_compare_status_alert(payload: dict, loc: str, *, i18n_prefix: str) -> dbc.Alert:
    """Build the summary status alert for a literature compare response."""

    def _k(suffix: str) -> str:
        return f"{i18n_prefix}.{suffix}"

    def _entry_text(entry: dict) -> str:
        text = (
            entry.get("claim_text")
            or entry.get("statement")
            or entry.get("claim")
            or entry.get("title")
            or entry.get("summary")
            or ""
        )
        return str(text).strip()

    def _has_meaningful_entries(items) -> bool:
        for item in items or []:
            if not isinstance(item, dict):
                continue
            if _entry_text(item):
                return True
            if str(item.get("doi") or "").strip():
                return True
            if str(item.get("source") or "").strip():
                return True
            if str(item.get("provider") or "").strip():
                return True
        return False

    context = payload.get("literature_context") if isinstance(payload.get("literature_context"), dict) else {}
    has_claims = _has_meaningful_entries(payload.get("literature_claims"))
    has_retained_comparisons = _has_meaningful_entries(payload.get("literature_comparisons"))
    has_retained_citations = _has_meaningful_entries(payload.get("citations"))
    has_retained_evidence = has_retained_comparisons or has_retained_citations
    limited_evidence = has_retained_evidence and bool(
        context.get("low_specificity_retrieval") or context.get("metadata_only_evidence")
    )

    status_token = str(context.get("provider_query_status") or "").strip().lower()
    reason_token = str(context.get("no_results_reason") or "").strip().lower()
    state_token = reason_token or status_token

    if state_token == "provider_unavailable":
        reason_text = literature_t(loc, _k("status.reason.provider_unavailable"), "")
    elif state_token == "request_failed":
        reason_text = literature_t(loc, _k("status.reason.request_failed"), "")
    elif state_token == "not_configured":
        reason_text = literature_t(loc, _k("status.reason.not_configured"), "")
    elif state_token == "query_too_narrow":
        reason_text = literature_t(loc, _k("status.reason.query_too_narrow"), "")
    else:
        reason_text = literature_t(loc, _k("status.reason.no_retained"), "")

    if has_retained_evidence and not limited_evidence:
        headline = literature_t(loc, _k("status.evidence_found"), "Retained literature evidence was found.")
        detail = literature_t(loc, _k("status.evidence_found_detail"), "Use retained references as contextual support for this interpretation.")
        color = "success"
    elif limited_evidence:
        headline = literature_t(loc, _k("status.limited_evidence"), "Retained literature evidence is limited.")
        detail = literature_t(loc, _k("status.limited_evidence_detail"), "")
        color = "info"
    elif has_claims:
        headline = literature_t(loc, _k("status.claims_without_evidence"), "")
        detail = reason_text
        color = "warning"
    else:
        headline = literature_t(loc, _k("status.no_evidence"), "")
        detail = reason_text
        color = "warning"

    return dbc.Alert(
        [html.Div(html.Strong(headline)), html.Div(detail, className="small mt-1")],
        color=color,
        className="py-2 small mb-2",
    )
