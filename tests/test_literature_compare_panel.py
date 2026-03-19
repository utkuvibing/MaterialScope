from __future__ import annotations

from pathlib import Path
from contextlib import nullcontext
from types import SimpleNamespace

from ui.components import literature_compare_panel


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


def test_merge_literature_detail_into_record_updates_saved_result_fields():
    record = {
        "id": "xrd_demo",
        "dataset_key": "xrd_demo",
        "summary": {"match_status": "matched"},
        "processing": {"workflow": "before"},
        "citations": [],
    }
    detail = {
        "summary": {"match_status": "matched", "top_candidate_name": "Phase Alpha"},
        "processing": {"workflow": "after"},
        "provenance": {"saved_at_utc": "2026-03-19T00:00:00Z"},
        "validation": {"status": "pass"},
        "review": {"status": "screening"},
        "literature_context": {"comparison_run_id": "litcmp_demo_001"},
        "literature_claims": [{"claim_id": "C1"}],
        "literature_comparisons": [{"claim_id": "C1", "support_label": "supports"}],
        "citations": [{"citation_id": "ref1", "title": "Supporting paper"}],
    }

    updated = literature_compare_panel.merge_literature_detail_into_record(
        record,
        detail_payload=detail,
    )

    assert updated["summary"]["top_candidate_name"] == "Phase Alpha"
    assert updated["processing"]["workflow"] == "after"
    assert updated["literature_context"]["comparison_run_id"] == "litcmp_demo_001"
    assert updated["literature_claims"][0]["claim_id"] == "C1"
    assert updated["citations"][0]["citation_id"] == "ref1"


def test_build_literature_sections_handles_absent_payload():
    sections = literature_compare_panel.build_literature_sections({})

    assert sections["has_payload"] is False
    assert sections["comparisons"] == []
    assert sections["supporting_references"] == []
    assert sections["alternative_references"] == []


def test_render_literature_sections_no_crash_when_payload_absent(monkeypatch):
    captions: list[str] = []
    markdowns: list[str] = []

    fake_st = SimpleNamespace(
        caption=lambda text: captions.append(str(text)),
        markdown=lambda text: markdowns.append(str(text)),
    )
    monkeypatch.setattr(literature_compare_panel, "st", fake_st)

    literature_compare_panel.render_literature_sections({}, lang="en")

    assert markdowns == []
    assert any("No literature comparison has been run yet" in item for item in captions)


def test_render_literature_sections_renders_compact_payload(monkeypatch):
    captions: list[str] = []
    markdowns: list[str] = []

    fake_st = SimpleNamespace(
        caption=lambda text: captions.append(str(text)),
        markdown=lambda text: markdowns.append(str(text)),
    )
    monkeypatch.setattr(literature_compare_panel, "st", fake_st)

    literature_compare_panel.render_literature_sections(
        {
            "literature_context": {"restricted_content_used": False, "metadata_only_evidence": True},
            "literature_comparisons": [
                {
                    "claim_id": "C1",
                    "support_label": "supports",
                    "confidence": "moderate",
                    "rationale": "Accessible literature supports the claim in a cautionary, non-definitive way.",
                    "citation_ids": ["ref1"],
                }
            ],
            "citations": [
                {
                    "citation_id": "ref1",
                    "title": "Supporting paper",
                    "year": 2025,
                    "journal": "Fixture Journal",
                    "doi": "10.1000/support",
                    "access_class": "abstract_only",
                }
            ],
        },
        lang="en",
    )

    assert any("Literature Comparison" in item for item in markdowns)
    assert any("Supporting References" in item for item in markdowns)
    assert any("Contradictory or Alternative References" in item for item in markdowns)
    assert any("Recommended Follow-Up Literature Checks" in item for item in markdowns)
    assert any("Supporting paper" in item for item in markdowns)
    assert any("abstract_only" in item for item in markdowns)


def test_call_literature_compare_maps_backend_response_into_updated_record(monkeypatch):
    request_log: list[tuple[str, str]] = []

    def _fake_request(method: str, url: str, *, headers=None, json=None, timeout=None):
        del headers, json, timeout
        request_log.append((method, url))
        if url.endswith("/project/load"):
            return _FakeResponse(200, {"project_id": "proj_123"})
        if url.endswith("/workspace/proj_123/results/xrd_demo/literature/compare"):
            return _FakeResponse(
                200,
                {
                    "project_id": "proj_123",
                    "result_id": "xrd_demo",
                    "literature_context": {"comparison_run_id": "litcmp_demo_001"},
                    "detail": {
                        "result": {"id": "xrd_demo", "dataset_key": "xrd_demo"},
                        "summary": {"match_status": "matched", "top_candidate_name": "Phase Alpha"},
                        "processing": {"workflow": "xrd.general"},
                        "provenance": {"saved_at_utc": "2026-03-19T00:00:00Z"},
                        "validation": {"status": "pass"},
                        "review": {"status": "screening"},
                        "literature_context": {"comparison_run_id": "litcmp_demo_001"},
                        "literature_claims": [{"claim_id": "C1"}],
                        "literature_comparisons": [{"claim_id": "C1", "support_label": "supports"}],
                        "citations": [{"citation_id": "ref1", "title": "Supporting paper"}],
                    },
                },
            )
        raise AssertionError(f"Unexpected backend request: {method} {url}")

    monkeypatch.setattr(literature_compare_panel, "save_project_archive", lambda state: b"archive-bytes")
    monkeypatch.setattr(literature_compare_panel.httpx, "request", _fake_request)

    outcome = literature_compare_panel.call_literature_compare(
        session_state={"results": {"xrd_demo": {"id": "xrd_demo"}}},
        result_id="xrd_demo",
        current_record={"id": "xrd_demo", "summary": {"match_status": "matched"}},
    )

    assert [entry[1] for entry in request_log] == [
        "http://127.0.0.1:8000/project/load",
        "http://127.0.0.1:8000/workspace/proj_123/results/xrd_demo/literature/compare",
    ]
    assert outcome["project_id"] == "proj_123"
    assert outcome["updated_record"]["summary"]["top_candidate_name"] == "Phase Alpha"
    assert outcome["updated_record"]["literature_context"]["comparison_run_id"] == "litcmp_demo_001"
    assert outcome["updated_record"]["citations"][0]["citation_id"] == "ref1"


def test_render_literature_compare_panel_updates_session_state_on_success(monkeypatch):
    session_state = {"results": {"xrd_demo": {"id": "xrd_demo", "summary": {"match_status": "matched"}}}}
    markdowns: list[str] = []
    captions: list[str] = []

    fake_st = SimpleNamespace(
        session_state=session_state,
        button=lambda *args, **kwargs: True,
        spinner=lambda *args, **kwargs: nullcontext(),
        success=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        caption=lambda text: captions.append(str(text)),
        markdown=lambda text: markdowns.append(str(text)),
    )
    monkeypatch.setattr(literature_compare_panel, "st", fake_st)
    monkeypatch.setattr(
        literature_compare_panel,
        "call_literature_compare",
        lambda **kwargs: {
            "project_id": "proj_123",
            "response": {"result_id": "xrd_demo"},
            "detail": {"result": {"id": "xrd_demo"}},
            "updated_record": {
                "id": "xrd_demo",
                "summary": {"match_status": "matched"},
                "literature_context": {"comparison_run_id": "litcmp_demo_001"},
                "literature_claims": [{"claim_id": "C1"}],
                "literature_comparisons": [{"claim_id": "C1", "support_label": "supports", "confidence": "moderate", "rationale": "Cautionary rationale", "citation_ids": ["ref1"]}],
                "citations": [{"citation_id": "ref1", "title": "Supporting paper", "access_class": "metadata_only"}],
            },
        },
    )

    record, action = literature_compare_panel.render_literature_compare_panel(
        record={"id": "xrd_demo", "summary": {"match_status": "matched"}},
        result_id="xrd_demo",
        lang="en",
        key_prefix="xrd_literature_compare_demo",
    )

    assert action["status"] == "success"
    assert record["literature_context"]["comparison_run_id"] == "litcmp_demo_001"
    assert session_state["results"]["xrd_demo"]["literature_context"]["comparison_run_id"] == "litcmp_demo_001"


def test_xrd_page_results_summary_uses_literature_compare_panel():
    source = Path("C:/MaterialScope/ui/xrd_page.py").read_text(encoding="utf-8")

    assert "render_literature_compare_panel(" in source
