"""Shared literature compare rendering and layout for Dash analysis pages."""

from __future__ import annotations

import re
from typing import Any

import dash_bootstrap_components as dbc
from dash import html

from utils.i18n import translate_ui

# Default compact evidence layout for Dash analysis pages (matches TGA / DSC / DTA).
LITERATURE_COMPACT_EVIDENCE_PREVIEW_LIMIT = 2
LITERATURE_COMPACT_ALTERNATIVE_PREVIEW_LIMIT = 1


def coerce_literature_max_claims(value: Any, *, default: int = 3) -> int:
    """Clamp manual max-claims input to 1..10."""
    try:
        if value in (None, ""):
            return max(1, default)
        n = int(float(value))
    except (TypeError, ValueError):
        return max(1, default)
    return max(1, min(10, n))


def build_literature_compare_card(
    *,
    id_prefix: str,
    class_name: str = "mb-3",
    compact_toolbar: bool = False,
) -> dbc.Card:
    """Reusable literature compare card; element ids are ``{id_prefix}-literature-*``.

    When *compact_toolbar* is True, compare options are tucked behind a collapsed summary
    so the card leads with title, hint, status, and output (used on XRD for calmer UX).
    """
    controls_row = dbc.Row(
        [
            dbc.Col(
                [
                    dbc.Label(
                        id=f"{id_prefix}-literature-max-claims-label",
                        html_for=f"{id_prefix}-literature-max-claims",
                    ),
                    dbc.Input(
                        id=f"{id_prefix}-literature-max-claims",
                        type="number",
                        min=1,
                        max=10,
                        step=1,
                        value=3,
                    ),
                ],
                md=6,
            ),
            dbc.Col(
                [
                    dbc.Checklist(
                        id=f"{id_prefix}-literature-persist",
                        options=[{"label": "", "value": "persist"}],
                        value=[],
                        switch=True,
                        className="mt-2",
                    ),
                    dbc.Label(
                        id=f"{id_prefix}-literature-persist-label",
                        html_for=f"{id_prefix}-literature-persist",
                        className="small",
                    ),
                ],
                md=6,
            ),
        ],
        className="g-2 mb-2",
    )
    compare_btn = dbc.Button(
        id=f"{id_prefix}-literature-compare-btn",
        color="primary",
        size="sm",
        disabled=True,
        className="mb-2",
    )
    if compact_toolbar:
        options_block = html.Details(
            [
                html.Summary(
                    [
                        html.Span(className="ta-details-chevron"),
                        html.Span(
                            id=f"{id_prefix}-literature-options-summary",
                            className="ms-1 small fw-semibold",
                        ),
                    ],
                    className="ta-details-summary py-1",
                ),
                html.Div([controls_row, compare_btn], className="ta-details-body mt-2"),
            ],
            className="ta-ms-details mb-2",
            open=False,
        )
        body_top: list[Any] = [
            html.H6(id=f"{id_prefix}-literature-card-title", className="card-title mb-2"),
            html.Div(id=f"{id_prefix}-literature-hint", className="small text-muted mb-2"),
            options_block,
        ]
    else:
        body_top = [
            html.H5(id=f"{id_prefix}-literature-card-title", className="card-title mb-3"),
            html.Div(id=f"{id_prefix}-literature-hint", className="small text-muted mb-2"),
            controls_row,
            compare_btn,
        ]
    return dbc.Card(
        dbc.CardBody(
            body_top
            + [
                html.Div(id=f"{id_prefix}-literature-status", className="small text-muted"),
                html.Div(id=f"{id_prefix}-literature-output", className="mt-2"),
            ]
        ),
        className=class_name,
    )


_DOI_IN_TEXT = re.compile(r"(10\.\d{4,9}/[^\s\],;)}\]]+)", re.IGNORECASE)


def _clean_str(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip()


def canonical_doi_string(raw: str) -> str:
    """Strip wrappers and return a bare DOI path (``10.xxxx/...``) or empty string."""
    s = _clean_str(raw)
    if not s:
        return ""
    low = s.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/"):
        if low.startswith(prefix):
            s = s[len(prefix) :].strip()
            low = s.lower()
            break
    if low.startswith("doi:"):
        s = s[4:].lstrip()
    return s.rstrip(").,]}\"").strip()


def doi_to_https_url(doi_or_raw: str) -> str | None:
    """Normalize a DOI or doi-prefixed string to ``https://doi.org/...``."""
    d = canonical_doi_string(doi_or_raw)
    if not d or not re.match(r"^10\.\d{4,9}/\S+$", d):
        return None
    return f"https://doi.org/{d}"


def normalize_http_url(url: str) -> str | None:
    """Return an absolute http(s) URL, or None if *url* is missing or not usable."""
    u = _clean_str(url)
    if not u:
        return None
    low = u.lower()
    if low.startswith("//"):
        return "https:" + u
    if low.startswith("http://") or low.startswith("https://"):
        return u
    return None


def resolve_literature_href(
    *,
    direct_doi: str = "",
    direct_url: str = "",
    fallback_doi: str = "",
    fallback_url: str = "",
) -> str | None:
    """Pick the best external link: direct DOI, direct URL, citation DOI, citation URL."""
    dd = _clean_str(direct_doi)
    du = _clean_str(direct_url)
    fd = _clean_str(fallback_doi)
    fu = _clean_str(fallback_url)
    if dd:
        u = doi_to_https_url(dd)
        if u:
            return u
    if du:
        u = normalize_http_url(du)
        if u:
            return u
    if fd:
        u = doi_to_https_url(fd)
        if u:
            return u
    if fu:
        u = normalize_http_url(fu)
        if u:
            return u
    return None


def linkify_doi_fragments(text: str) -> list[Any]:
    """Split *text* into strings and ``html.A`` nodes for bare DOI tokens."""
    if not text:
        return []
    parts: list[Any] = []
    pos = 0
    for m in _DOI_IN_TEXT.finditer(text):
        if m.start() > pos:
            parts.append(text[pos : m.start()])
        display = m.group(0)
        href = doi_to_https_url(m.group(1))
        if href:
            parts.append(
                html.A(
                    display,
                    href=href,
                    target="_blank",
                    rel="noopener noreferrer",
                    className="text-reset",
                )
            )
        else:
            parts.append(display)
        pos = m.end()
    if pos < len(text):
        parts.append(text[pos:])
    return [p for p in parts if p != ""]


def citation_meta_children(entry: dict) -> list[Any]:
    """Year / journal / DOI line as inline children; DOI (or bare URL) is linked when possible."""
    parts: list[Any] = []
    year = _clean_str(entry.get("year"))
    journal = _clean_str(entry.get("journal"))
    doi = _clean_str(entry.get("doi") or entry.get("paper_doi"))
    url = _clean_str(entry.get("url") or entry.get("paper_url") or entry.get("link"))

    def _sep() -> None:
        if parts:
            parts.append(" | ")

    if year:
        parts.append(year)
    if journal:
        _sep()
        parts.append(journal)
    href_d = doi_to_https_url(doi) if doi else None
    href_u = normalize_http_url(url) if url else None
    if doi and href_d:
        _sep()
        parts.append("DOI: ")
        parts.append(
            html.A(
                doi,
                href=href_d,
                target="_blank",
                rel="noopener noreferrer",
                className="text-reset",
            )
        )
    elif doi:
        _sep()
        parts.append(f"DOI: {doi}")
    elif url and href_u:
        _sep()
        parts.append(
            html.A(
                url,
                href=href_u,
                target="_blank",
                rel="noopener noreferrer",
                className="text-reset text-break",
            )
        )
    return parts


def literature_t(loc: str, key: str, fallback: str) -> str:
    """Translate with a literal fallback when the key is missing from the bundle."""
    value = translate_ui(loc, key)
    return fallback if value == key else value


def _collapsible_section(
    loc: str, title_key: str, body: Any, *, open: bool = False, title_fallback: str = "Details"
) -> html.Details:
    title_text = literature_t(loc, title_key, title_fallback)
    return html.Details(
        [
            html.Summary(
                [
                    html.Span(className="ta-details-chevron"),
                    html.Span(title_text, className="ms-1"),
                ],
                className="ta-details-summary",
            ),
            html.Div(body, className="ta-details-body mt-2"),
        ],
        className="ta-ms-details mb-0",
        open=open,
    )


def render_literature_output(
    payload: dict,
    loc: str,
    *,
    i18n_prefix: str,
    evidence_preview_limit: int | None = None,
    alternative_preview_limit: int | None = None,
    collapse_retained_evidence: bool = False,
) -> html.Div:
    """Render literature compare payload as curated product-facing sections.

    When *evidence_preview_limit* is set, only that many relevant retained references are
    shown inline; the rest appear behind a collapsed details section. Dash analysis pages
    pass the module constants LITERATURE_COMPACT_EVIDENCE_PREVIEW_LIMIT for a consistent
    compact layout; pass None for the legacy full inline layout.

    When *collapse_retained_evidence* is True, the retained-reference sections are wrapped
    in a collapsed ``Details`` so the first read stays on interpretation claims and previews.
    """
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

        entry_doi = _clean_text(entry.get("doi") or entry.get("paper_doi"))
        entry_url = _clean_text(entry.get("url") or entry.get("paper_url") or entry.get("link"))
        fc = linked_citations[0] if linked_citations else {}
        cite_doi = _clean_text(fc.get("doi") or fc.get("paper_doi")) if fc else ""
        cite_url = _clean_text(fc.get("url") or fc.get("paper_url") or fc.get("link")) if fc else ""
        row_href = resolve_literature_href(
            direct_doi=entry_doi,
            direct_url=entry_url,
            fallback_doi=cite_doi,
            fallback_url=cite_url,
        )

        retained_rows.append(
            {
                "title": title,
                "provider": provider,
                "rationale": rationale,
                "citation_titles": citation_titles,
                "is_alternative": is_alternative,
                "href": row_href,
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
        cite_href = resolve_literature_href(
            direct_doi=_clean_text(entry.get("doi") or entry.get("paper_doi")),
            direct_url=_clean_text(entry.get("url") or entry.get("paper_url") or entry.get("link")),
        )
        meta_nodes = citation_meta_children(entry)
        retained_rows.append(
            {
                "title": title,
                "provider": provider,
                "rationale": "",
                "rationale_nodes": meta_nodes,
                "citation_titles": [],
                "is_alternative": False,
                "href": cite_href,
            }
        )

    relevant_rows = [row for row in retained_rows if not row.get("is_alternative")]
    alternative_rows = [row for row in retained_rows if row.get("is_alternative")]
    has_retained_evidence = bool(relevant_rows or alternative_rows)

    alt_limit = alternative_preview_limit
    if alt_limit is None and evidence_preview_limit is not None:
        alt_limit = 1

    compact_lit = evidence_preview_limit is not None
    claims_cap = 2 if compact_lit else None

    claim_items: list[html.Li] = []
    for entry in claims:
        if not isinstance(entry, dict):
            continue
        text = _entry_text(entry)
        if text:
            claim_items.append(html.Li(text, className="small mb-0"))

    def _render_evidence_rows(rows: list[dict[str, Any]], *, compact: bool = False) -> list[html.Div]:
        if compact:
            row_class = "mb-1 pb-1 border-bottom ta-literature-evidence-compact py-0"
        else:
            row_class = "border rounded p-2 mb-2"
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
            title_cls = "fw-semibold small lh-sm mb-0" if compact else "fw-semibold small"
            title_link_cls = f"{title_cls} link-primary text-decoration-underline"
            rationale_cls = "small text-muted mb-0 lh-sm mt-1" if compact else "small mb-1"
            meta_cls = "small text-muted mb-0 lh-sm mt-1" if compact else "small text-muted mb-0"
            href = row.get("href")
            title = row.get("title") or ""
            title_el: Any = (
                html.A(
                    title,
                    href=href,
                    target="_blank",
                    rel="noopener noreferrer",
                    className=title_link_cls,
                )
                if href
                else html.Div(title, className=title_cls)
            )
            rat_nodes = row.get("rationale_nodes")
            if rat_nodes is not None:
                rat_el = html.P(rat_nodes, className=rationale_cls) if rat_nodes else None
            elif row.get("rationale"):
                chunks = linkify_doi_fragments(str(row["rationale"]))
                rat_el = html.P(chunks, className=rationale_cls) if chunks else None
            else:
                rat_el = None
            rendered.append(
                html.Div(
                    [
                        title_el,
                        rat_el,
                        html.P(" | ".join(meta_parts), className=meta_cls) if meta_parts else None,
                    ],
                    className=row_class,
                )
            )
        return rendered

    def _evidence_rows_block(rows: list[dict[str, Any]], preview_limit: int | None) -> html.Div:
        if not rows:
            return html.Div()
        use_compact = preview_limit is not None
        if preview_limit is None or len(rows) <= preview_limit:
            return html.Div(_render_evidence_rows(rows, compact=use_compact))
        head = rows[:preview_limit]
        tail = rows[preview_limit:]
        n_more = len(tail)
        show_more_key = _k("evidence_show_more")
        formatted = translate_ui(loc, show_more_key, n=n_more)
        show_more_label = formatted if formatted != show_more_key else f"Show {n_more} more references"
        return html.Div(
            [
                html.Div(_render_evidence_rows(head, compact=True)),
                html.Details(
                    [
                        html.Summary(
                            [
                                html.Span(className="ta-details-chevron"),
                                html.Span(show_more_label, className="ms-1 small fw-semibold text-primary"),
                                html.Span(
                                    literature_t(loc, _k("evidence_show_more_hint"), " (expand)"),
                                    className="small text-muted ms-1",
                                ),
                            ],
                            className="ta-details-summary py-1 border border-secondary-subtle rounded px-2",
                        ),
                        html.Div(
                            html.Div(_render_evidence_rows(tail, compact=True)),
                            className="ta-details-body mt-2",
                        ),
                    ],
                    className="ta-ms-details mb-0 mt-2",
                    open=False,
                ),
            ]
        )

    children: list[Any] = []

    if claim_items:
        if compact_lit and claims_cap is not None and len(claim_items) > claims_cap:
            head_li, tail_li = claim_items[:claims_cap], claim_items[claims_cap:]
            n_claim_more = len(tail_li)
            claims_more_key = _k("claims_show_more")
            claims_more_fmt = translate_ui(loc, claims_more_key, n=n_claim_more)
            claims_more_label = claims_more_fmt if claims_more_fmt != claims_more_key else f"Show {n_claim_more} more claims"
            claims_block = html.Div(
                [
                    html.Div(
                        literature_t(loc, _k("claims_generated"), "Generated interpretation claims"),
                        className="small fw-semibold mt-2 mb-1",
                    ),
                    html.P(
                        literature_t(
                            loc,
                            _k("claims_note_compact"),
                            "Model-generated bullets; not external literature.",
                        ),
                        className="small text-muted mb-1 lh-sm",
                    ),
                    html.Ul(head_li, className="mb-1 ps-3 small"),
                    html.Details(
                        [
                            html.Summary(
                                [
                                    html.Span(className="ta-details-chevron"),
                                    html.Span(claims_more_label, className="ms-1 small fw-semibold text-primary"),
                                ],
                                className="ta-details-summary py-1 border border-secondary-subtle rounded px-2",
                            ),
                            html.Div(html.Ul(tail_li, className="mb-0 ps-3 small"), className="ta-details-body mt-2"),
                        ],
                        className="ta-ms-details mb-0",
                        open=False,
                    ),
                ],
                className="mb-2",
            )
        elif compact_lit:
            claims_block = html.Div(
                [
                    html.Div(
                        literature_t(loc, _k("claims_generated"), "Generated interpretation claims"),
                        className="small fw-semibold mt-2 mb-1",
                    ),
                    html.P(
                        literature_t(
                            loc,
                            _k("claims_note_compact"),
                            "Model-generated bullets; not external literature.",
                        ),
                        className="small text-muted mb-1 lh-sm",
                    ),
                    html.Ul(claim_items, className="mb-0 ps-3 small"),
                ],
                className="mb-2",
            )
        else:
            claims_block = html.Div(
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
        children.append(claims_block)

    retained_inner = html.Div(
        [
            html.H6(literature_t(loc, _k("retained_evidence_title"), "Retained literature evidence"), className="mt-2 mb-1"),
            html.Div(
                [
                    html.H6(literature_t(loc, _k("relevant_references"), "Relevant retained references"), className="mt-2 mb-1"),
                    _evidence_rows_block(relevant_rows, evidence_preview_limit)
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
                    _evidence_rows_block(alternative_rows, alt_limit)
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
    if collapse_retained_evidence:
        n_refs = len(relevant_rows) + len(alternative_rows)
        show_refs_key = _k("evidence_list_summary")
        show_refs = translate_ui(loc, show_refs_key, n=n_refs)
        if show_refs == show_refs_key:
            show_refs = literature_t(loc, show_refs_key, "Full reference evidence ({n})").replace("{n}", str(n_refs))
        retained_block = html.Details(
            [
                html.Summary(
                    [
                        html.Span(className="ta-details-chevron"),
                        html.Span(show_refs, className="ms-1 small fw-semibold"),
                    ],
                    className="ta-details-summary py-1",
                ),
                html.Div(retained_inner, className="ta-details-body mt-2"),
            ],
            className="ta-ms-details mb-2",
            open=False,
        )
    else:
        retained_block = retained_inner
    children.append(retained_block)

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
    _technical_line("technical.search_mode", "Search mode", context.get("search_mode"))
    _technical_line("technical.subject_trust", "Subject trust", context.get("subject_trust"))
    display_terms = context.get("query_display_terms")
    if display_terms:
        _technical_line("technical.display_terms", "Display terms", ", ".join(str(t) for t in display_terms if t))
    executed_queries_list = context.get("executed_queries") or []
    if len(executed_queries_list) > 1:
        fallback_text = "; ".join(executed_queries_list[1:])
        _technical_line("technical.fallback_queries", "Fallback queries", fallback_text)

    if technical_rows:
        children.append(
            html.Div(
                _collapsible_section(
                    loc,
                    _k("technical_details_title"),
                    html.Ul(technical_rows, className="mb-0 ps-3"),
                    open=False,
                    title_fallback="Technical search details",
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

    if state_token == "not_configured" and not has_retained_evidence and color == "warning":
        color = "danger"

    alert_children: list = [html.Div(html.Strong(headline)), html.Div(detail, className="small mt-1")]
    if state_token == "not_configured":
        setup_hint = literature_t(
            loc,
            _k("status.not_configured_setup_hint"),
            "Set MATERIALSCOPE_OPENALEX_EMAIL (recommended) or MATERIALSCOPE_OPENALEX_API_KEY in the server environment, "
            "or enable demo fixtures with MATERIALSCOPE_LITERATURE_FIXTURE_FALLBACK=1. Restart the app after changing environment variables.",
        )
        if setup_hint:
            alert_children.append(
                html.Div(setup_hint, className="small mt-2 border-start border-3 ps-2 text-body-secondary"),
            )

    return dbc.Alert(
        alert_children,
        color=color,
        className="py-2 small mb-2",
    )
