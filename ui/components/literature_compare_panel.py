"""Reusable Streamlit helpers for backend-driven literature comparison."""

from __future__ import annotations

import base64
import copy
import os
from typing import Any, Mapping

import httpx
import streamlit as st

from core.project_io import save_project_archive
from utils.diagnostics import record_exception


DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
DEFAULT_LITERATURE_COMPARE_REQUEST = {
    "provider_ids": ["fixture_provider"],
    "persist": True,
    "max_claims": 3,
    "filters": {},
    "user_documents": [],
}


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _ui_text(lang: str, tr: str, en: str, **kwargs: Any) -> str:
    text = tr if _clean_text(lang).lower() == "tr" else en
    if kwargs:
        return text.format(**kwargs)
    return text


def _backend_base_url(base_url: str | None = None) -> str:
    explicit = _clean_text(base_url)
    if explicit:
        return explicit.rstrip("/")
    env_value = (
        os.getenv("THERMOANALYZER_BACKEND_URL")
        or os.getenv("TA_BACKEND_URL")
        or DEFAULT_BACKEND_URL
    )
    return _clean_text(env_value).rstrip("/")


def _backend_token(api_token: str | None = None) -> str:
    explicit = _clean_text(api_token)
    if explicit:
        return explicit
    return _clean_text(
        os.getenv("THERMOANALYZER_BACKEND_TOKEN")
        or os.getenv("TA_BACKEND_TOKEN")
        or ""
    )


def _backend_headers(api_token: str | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = _backend_token(api_token)
    if token:
        headers["X-TA-Token"] = token
    return headers


def _request_json(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    json_payload: Mapping[str, Any] | None = None,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    response = httpx.request(
        method=method,
        url=url,
        headers=dict(headers or {}),
        json=dict(json_payload or {}) if json_payload is not None else None,
        timeout=timeout_seconds,
    )
    try:
        payload = response.json()
    except Exception:
        payload = {}
    if not response.is_success:
        detail = payload.get("detail") if isinstance(payload, Mapping) else ""
        raise RuntimeError(_clean_text(detail) or f"Backend request failed ({response.status_code}).")
    return dict(payload or {})


def _project_archive_base64(session_state: Mapping[str, Any]) -> str:
    archive_bytes = save_project_archive(session_state)
    return base64.b64encode(archive_bytes).decode("ascii")


def _default_compare_request(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = copy.deepcopy(DEFAULT_LITERATURE_COMPARE_REQUEST)
    for key, value in dict(overrides or {}).items():
        payload[key] = copy.deepcopy(value)
    return payload


def _load_backend_project(
    session_state: Mapping[str, Any],
    *,
    base_url: str | None = None,
    api_token: str | None = None,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    return _request_json(
        "POST",
        f"{_backend_base_url(base_url)}/project/load",
        headers=_backend_headers(api_token),
        json_payload={"archive_base64": _project_archive_base64(session_state)},
        timeout_seconds=timeout_seconds,
    )


def _fetch_result_detail(
    *,
    project_id: str,
    result_id: str,
    base_url: str | None = None,
    api_token: str | None = None,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    return _request_json(
        "GET",
        f"{_backend_base_url(base_url)}/workspace/{project_id}/results/{result_id}",
        headers=_backend_headers(api_token),
        timeout_seconds=timeout_seconds,
    )


def merge_literature_detail_into_record(
    record: Mapping[str, Any] | None,
    *,
    compare_response: Mapping[str, Any] | None = None,
    detail_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    updated = copy.deepcopy(dict(record or {}))
    detail = dict(detail_payload or {})
    compare = dict(compare_response or {})

    for key in ("summary", "processing", "provenance", "validation", "review"):
        if isinstance(detail.get(key), Mapping):
            updated[key] = copy.deepcopy(detail[key])

    if detail.get("result") and not updated.get("id"):
        updated["id"] = detail["result"].get("id")

    if detail.get("result") and detail["result"].get("dataset_key") and not updated.get("dataset_key"):
        updated["dataset_key"] = detail["result"].get("dataset_key")

    updated["literature_context"] = copy.deepcopy(
        detail.get("literature_context")
        or compare.get("literature_context")
        or updated.get("literature_context")
        or {}
    )
    updated["literature_claims"] = copy.deepcopy(
        detail.get("literature_claims")
        or compare.get("literature_claims")
        or updated.get("literature_claims")
        or []
    )
    updated["literature_comparisons"] = copy.deepcopy(
        detail.get("literature_comparisons")
        or compare.get("literature_comparisons")
        or updated.get("literature_comparisons")
        or []
    )
    updated["citations"] = copy.deepcopy(
        detail.get("citations")
        or compare.get("citations")
        or updated.get("citations")
        or []
    )
    return updated


def call_literature_compare(
    *,
    session_state: Mapping[str, Any],
    result_id: str,
    current_record: Mapping[str, Any] | None = None,
    request_payload: Mapping[str, Any] | None = None,
    base_url: str | None = None,
    api_token: str | None = None,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    loaded = _load_backend_project(
        session_state,
        base_url=base_url,
        api_token=api_token,
        timeout_seconds=timeout_seconds,
    )
    project_id = _clean_text(loaded.get("project_id"))
    if not project_id:
        raise RuntimeError("Backend project load did not return a project_id.")

    compare_response = _request_json(
        "POST",
        f"{_backend_base_url(base_url)}/workspace/{project_id}/results/{result_id}/literature/compare",
        headers=_backend_headers(api_token),
        json_payload=_default_compare_request(request_payload),
        timeout_seconds=timeout_seconds,
    )
    detail_payload = compare_response.get("detail")
    if not isinstance(detail_payload, Mapping):
        detail_payload = _fetch_result_detail(
            project_id=project_id,
            result_id=result_id,
            base_url=base_url,
            api_token=api_token,
            timeout_seconds=timeout_seconds,
        )

    updated_record = merge_literature_detail_into_record(
        current_record,
        compare_response=compare_response,
        detail_payload=detail_payload,
    )
    return {
        "project_id": project_id,
        "response": compare_response,
        "detail": dict(detail_payload or {}),
        "updated_record": updated_record,
    }


def _citation_lookup(record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for item in record.get("citations") or []:
        if not isinstance(item, Mapping):
            continue
        citation_id = _clean_text(item.get("citation_id"))
        if citation_id:
            lookup[citation_id] = dict(item)
    return lookup


def build_literature_sections(record: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(record or {})
    comparisons = [dict(item) for item in (source.get("literature_comparisons") or []) if isinstance(item, Mapping)]
    citations_by_id = _citation_lookup(source)
    context = dict(source.get("literature_context") or {})

    if not comparisons and not citations_by_id and not context:
        return {
            "has_payload": False,
            "comparisons": [],
            "supporting_references": [],
            "alternative_references": [],
            "follow_up_checks": [],
            "context": {},
        }

    supporting_ids: list[str] = []
    alternative_ids: list[str] = []
    comparison_rows: list[dict[str, Any]] = []
    for item in comparisons:
        citation_ids = [
            _clean_text(token)
            for token in (item.get("citation_ids") or [])
            if _clean_text(token)
        ]
        comparison_rows.append(
            {
                "claim_id": _clean_text(item.get("claim_id")) or "C1",
                "support_label": _clean_text(item.get("support_label")) or "related_but_inconclusive",
                "confidence": _clean_text(item.get("confidence")) or "low",
                "rationale": _clean_text(item.get("rationale")) or "",
                "citation_ids": citation_ids,
            }
        )
        if _clean_text(item.get("support_label")) in {"supports", "partially_supports"}:
            for citation_id in citation_ids:
                if citation_id not in supporting_ids:
                    supporting_ids.append(citation_id)
        else:
            for citation_id in citation_ids:
                if citation_id not in alternative_ids:
                    alternative_ids.append(citation_id)

    follow_up_checks: list[str] = []
    if any(not row["citation_ids"] for row in comparison_rows):
        follow_up_checks.append(
            "At least one claim remained citation-limited; additional confirmatory experiments may be required before stronger literature alignment is inferred."
        )
    if any(row["confidence"].lower() == "low" for row in comparison_rows):
        follow_up_checks.append(
            "Low-confidence literature outcomes should be treated as screening context only, not as confirmation."
        )
    citation_access_classes = {
        _clean_text(item.get("access_class")).lower()
        for item in citations_by_id.values()
        if _clean_text(item.get("access_class"))
    }
    if context.get("metadata_only_evidence") or citation_access_classes & {"abstract_only", "metadata_only"}:
        follow_up_checks.append(
            "Some literature reasoning relies on metadata or abstract-level evidence only; broader open-access or user-provided documents could refine the comparison."
        )
    if context.get("restricted_content_used") is False:
        follow_up_checks.append(
            "Closed-access full text was intentionally excluded from reasoning; the comparison remains legal-safe by design."
        )

    return {
        "has_payload": True,
        "comparisons": comparison_rows,
        "supporting_references": [citations_by_id[citation_id] for citation_id in supporting_ids if citation_id in citations_by_id],
        "alternative_references": [citations_by_id[citation_id] for citation_id in alternative_ids if citation_id in citations_by_id],
        "follow_up_checks": follow_up_checks,
        "context": context,
    }


def _render_citation_item(citation: Mapping[str, Any]) -> None:
    title = _clean_text(citation.get("title")) or "Untitled source"
    year = _clean_text(citation.get("year")) or "n.d."
    journal = _clean_text(citation.get("journal"))
    doi = _clean_text(citation.get("doi"))
    url = _clean_text(citation.get("url"))
    access_class = _clean_text(citation.get("access_class")) or "metadata_only"

    line = f"**{title}** ({year})"
    if journal:
        line += f" | {journal}"
    line += f" | `{access_class}`"
    if doi:
        line += f" | DOI: `{doi}`"
    elif url:
        line += f" | {url}"
    st.markdown(line)


def render_literature_sections(record: Mapping[str, Any] | None, *, lang: str) -> None:
    sections = build_literature_sections(record)
    if not sections["has_payload"]:
        st.caption(
            _ui_text(
                lang,
                "Henüz literatür karşılaştırması çalıştırılmadı. Kaydedilmiş sonuç üzerinden karşılaştırmayı tetikleyin.",
                "No literature comparison has been run yet. Trigger compare from the saved result to populate this panel.",
            )
        )
        return

    st.markdown(f"**{_ui_text(lang, 'Literatür Karşılaştırması', 'Literature Comparison')}**")
    for row in sections["comparisons"]:
        citation_note = ", ".join(row["citation_ids"]) if row["citation_ids"] else _ui_text(lang, "yok", "none")
        st.markdown(
            f"- `{row['claim_id']}` | `{row['support_label']}` | `{row['confidence']}` | {row['rationale']} "
            f"({_ui_text(lang, 'Atıflar', 'Citations')}: {citation_note})"
        )

    st.markdown(f"**{_ui_text(lang, 'Destekleyen Kaynaklar', 'Supporting References')}**")
    if sections["supporting_references"]:
        for citation in sections["supporting_references"]:
            _render_citation_item(citation)
    else:
        st.caption(
            _ui_text(
                lang,
                "Destekleyen erişilebilir kaynak kaydedilmedi; çıktı niteliksel ve temkinli kalır.",
                "No supporting accessible references were retained; the output remains qualitative and cautionary.",
            )
        )

    st.markdown(f"**{_ui_text(lang, 'Çelişen veya Alternatif Kaynaklar', 'Contradictory or Alternative References')}**")
    if sections["alternative_references"]:
        for citation in sections["alternative_references"]:
            _render_citation_item(citation)
    else:
        st.caption(
            _ui_text(
                lang,
                "Çelişen erişilebilir kaynak kaydedilmedi; bu durum yine de doğrulama anlamına gelmez.",
                "No contradictory accessible references were retained; this still does not imply confirmation.",
            )
        )

    st.markdown(f"**{_ui_text(lang, 'Önerilen Takip Literatür Kontrolleri', 'Recommended Follow-Up Literature Checks')}**")
    for index, item in enumerate(sections["follow_up_checks"], start=1):
        st.markdown(f"- {item}")
    if not sections["follow_up_checks"]:
        st.caption(
            _ui_text(
                lang,
                "Ek takip kontrolü kaydedilmedi; yine de karşılaştırma doğrulama yerine tarama bağlamı sağlar.",
                "No additional follow-up checks were recorded; the comparison still provides screening context rather than confirmation.",
            )
        )


def render_literature_compare_panel(
    *,
    record: Mapping[str, Any] | None,
    result_id: str | None,
    lang: str,
    key_prefix: str,
    request_payload: Mapping[str, Any] | None = None,
    base_url: str | None = None,
    api_token: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    current_record = copy.deepcopy(dict(record or {})) if record else None
    action_result: dict[str, Any] | None = None

    button_label = _ui_text(lang, "Literatür Karşılaştırması", "Literature Compare")
    helper_caption = _ui_text(
        lang,
        "Karşılaştırma yalnızca metadata, abstract, açık erişim veya kullanıcı dokümanlarını kullanır; kapalı metin kullanılmaz.",
        "Comparison uses metadata, abstracts, open-access text, or user documents only; closed text is never used.",
    )

    if not current_record or not _clean_text(result_id):
        st.button(button_label, disabled=True, key=f"{key_prefix}_run")
        st.caption(
            _ui_text(
                lang,
                "Önce sonuç oturuma kaydedilmelidir; ardından literatür karşılaştırması tetiklenebilir.",
                "The result must be saved first; literature compare can then be triggered.",
            )
        )
        render_literature_sections({}, lang=lang)
        return current_record, action_result

    if st.button(button_label, key=f"{key_prefix}_run"):
        try:
            with st.spinner(_ui_text(lang, "Literatür karşılaştırması çalışıyor...", "Running literature compare...")):
                outcome = call_literature_compare(
                    session_state=st.session_state,
                    result_id=_clean_text(result_id),
                    current_record=current_record,
                    request_payload=request_payload,
                    base_url=base_url,
                    api_token=api_token,
                )
            updated_record = outcome["updated_record"]
            st.session_state.setdefault("results", {})[updated_record["id"]] = updated_record
            current_record = updated_record
            action_result = {"status": "success", **outcome}
            st.success(
                _ui_text(
                    lang,
                    "Literatür karşılaştırması tamamlandı ve kaydedilmiş sonuca işlendi.",
                    "Literature comparison completed and was applied to the saved result.",
                )
            )
        except Exception as exc:
            error_id = record_exception(
                st.session_state,
                area="literature_compare",
                action="backend_compare",
                message="Literature compare request failed.",
                context={"result_id": _clean_text(result_id)},
                exception=exc,
            )
            st.warning(
                _ui_text(
                    lang,
                    "Literatür karşılaştırması tamamlanamadı: {error}",
                    "Literature comparison could not be completed: {error}",
                    error=f"{exc} (Error ID: {error_id})",
                )
            )
            action_result = {"status": "error", "error": str(exc), "error_id": error_id}

    st.caption(helper_caption)
    render_literature_sections(current_record or {}, lang=lang)
    return current_record, action_result
