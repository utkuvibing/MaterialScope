"""Tests for shared Dash literature compare rendering (links, DOI normalization)."""

from __future__ import annotations

import sys
from pathlib import Path

from dash import html

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def test_doi_to_https_url_normalizes_variants():
    from dash_app.components.literature_compare_ui import canonical_doi_string, doi_to_https_url

    doi = "10.1016/j.example.2024.01.001"
    assert doi_to_https_url(doi) == f"https://doi.org/{doi}"
    assert doi_to_https_url(f"doi:{doi}") == f"https://doi.org/{doi}"
    assert doi_to_https_url(f"https://doi.org/{doi}") == f"https://doi.org/{doi}"
    assert canonical_doi_string(f"  {doi}  ").startswith("10.")


def test_normalize_http_url():
    from dash_app.components.literature_compare_ui import normalize_http_url

    assert normalize_http_url("https://example.com/paper") == "https://example.com/paper"
    assert normalize_http_url("//example.com/x") == "https://example.com/x"
    assert normalize_http_url("not-a-url") is None


def test_resolve_literature_href_order():
    from dash_app.components.literature_compare_ui import resolve_literature_href

    d = "10.1000/182"
    assert resolve_literature_href(direct_doi=d, direct_url="https://example.com/a") == f"https://doi.org/{d}"
    assert resolve_literature_href(direct_doi="", direct_url="https://example.com/a") == "https://example.com/a"
    assert (
        resolve_literature_href(direct_doi="", direct_url="", fallback_doi=d, fallback_url="")
        == f"https://doi.org/{d}"
    )
    assert resolve_literature_href(
        direct_doi="",
        direct_url="",
        fallback_doi="",
        fallback_url="https://b.org/x",
    ) == "https://b.org/x"
    assert resolve_literature_href() is None


def test_citation_meta_children_links_doi():
    from dash_app.components.literature_compare_ui import citation_meta_children

    entry = {"year": "2020", "journal": "Test", "doi": "10.1000/xyz"}
    kids = citation_meta_children(entry)
    assert any(isinstance(c, html.A) for c in kids)
    a = next(c for c in kids if isinstance(c, html.A))
    assert a.href == "https://doi.org/10.1000/xyz"
    assert a.target == "_blank"
    assert a.rel == "noopener noreferrer"


def test_linkify_doi_fragments_in_rationale():
    from dash_app.components.literature_compare_ui import linkify_doi_fragments

    parts = linkify_doi_fragments("See 10.1000/abc for details.")
    assert any(isinstance(c, html.A) for c in parts)
    a = next(c for c in parts if isinstance(c, html.A))
    assert "doi.org/10.1000/abc" in a.href


def test_render_literature_output_title_link_doi_only_row():
    from dash_app.components.literature_compare_ui import render_literature_output

    payload = {
        "literature_claims": [],
        "literature_comparisons": [
            {
                "claim_text": "Polymer degradation study",
                "doi": "doi:10.1000/only",
                "provider": "openalex",
                "support_label": "supports",
                "validation_posture": "validating",
            }
        ],
        "citations": [],
        "literature_context": {},
    }
    out = render_literature_output(payload, "en", i18n_prefix="dash.analysis.dsc.literature")
    s = str(out)
    assert "https://doi.org/10.1000/only" in s
    assert "target='_blank'" in s
    assert "rel='noopener noreferrer'" in s


def test_render_literature_output_title_link_url_only_row():
    from dash_app.components.literature_compare_ui import render_literature_output

    payload = {
        "literature_claims": [],
        "literature_comparisons": [
            {
                "claim_text": "Paper without DOI",
                "url": "https://example.org/article/1",
                "provider": "x",
                "support_label": "supports",
                "validation_posture": "validating",
            }
        ],
        "citations": [],
        "literature_context": {},
    }
    out = render_literature_output(payload, "en", i18n_prefix="dash.analysis.dsc.literature")
    s = str(out)
    assert "https://example.org/article/1" in s
    assert "target='_blank'" in s


def test_render_literature_output_uses_linked_citation_doi_when_comparison_has_none():
    from dash_app.components.literature_compare_ui import render_literature_output

    payload = {
        "literature_claims": [],
        "literature_comparisons": [
            {
                "claim_text": "From linked cite",
                "citation_ids": ["c1"],
                "provider": "openalex",
                "support_label": "supports",
                "validation_posture": "validating",
            }
        ],
        "citations": [
            {
                "citation_id": "c1",
                "title": "Linked title",
                "doi": "10.1000/linked",
            }
        ],
        "literature_context": {},
    }
    out = render_literature_output(payload, "en", i18n_prefix="dash.analysis.dsc.literature")
    assert "https://doi.org/10.1000/linked" in str(out)


def test_render_literature_output_plain_title_when_no_link():
    from dash_app.components.literature_compare_ui import render_literature_output

    payload = {
        "literature_claims": [],
        "literature_comparisons": [
            {
                "claim_text": "No identifiers",
                "provider": "openalex",
                "support_label": "supports",
                "validation_posture": "validating",
            }
        ],
        "citations": [],
        "literature_context": {},
    }
    out = render_literature_output(payload, "en", i18n_prefix="dash.analysis.dsc.literature")
    s = str(out)
    assert "No identifiers" in s
    assert "https://doi.org/" not in s


def test_render_literature_output_preview_show_more_still_works_with_links():
    from dash_app.components.literature_compare_ui import render_literature_output

    comparisons = [
        {
            "claim_text": f"Ref {i}",
            "doi": f"10.1000/ref{i:03d}",
            "provider": "openalex",
            "support_label": "supports",
            "validation_posture": "validating",
        }
        for i in range(4)
    ]
    payload = {
        "literature_claims": [],
        "literature_comparisons": comparisons,
        "citations": [],
        "literature_context": {},
    }
    out = render_literature_output(
        payload,
        "en",
        i18n_prefix="dash.analysis.tga.literature",
        evidence_preview_limit=2,
    )
    text = str(out)
    assert "Show 2 more references" in text
    assert "https://doi.org/10.1000/ref000" in text
    assert "https://doi.org/10.1000/ref003" in text
