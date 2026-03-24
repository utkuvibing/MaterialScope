"""Provider abstraction for legal-safe literature metadata and text retrieval."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

import httpx

from core.citation_formatter import format_citation_text
from core.literature_models import normalize_literature_sources


ACCESS_CLASS_PRIORITY = {
    "restricted_external": 0,
    "metadata_only": 1,
    "abstract_only": 2,
    "open_access_full_text": 3,
    "user_provided_document": 4,
}


def _tokenize(value: str) -> list[str]:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in str(value or "").lower())
    return [token for token in cleaned.split() if len(token) >= 3]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _as_str_list(value: Any) -> list[str]:
    if value in (None, "", [], (), {}):
        return []
    if isinstance(value, str):
        cleaned = _clean_text(value)
        return [cleaned] if cleaned else []
    if isinstance(value, (list, tuple, set)):
        output: list[str] = []
        for item in value:
            cleaned = _clean_text(item)
            if cleaned:
                output.append(cleaned)
        return output
    cleaned = _clean_text(value)
    return [cleaned] if cleaned else []


def _access_rank(access_class: Any) -> int:
    return ACCESS_CLASS_PRIORITY.get(_clean_text(access_class).lower(), 0)


def citation_identity_key(candidate: Mapping[str, Any]) -> str:
    doi = _clean_text(candidate.get("doi")).lower()
    if doi:
        return f"doi:{doi}"
    url = _clean_text(candidate.get("url")).lower()
    if url:
        return f"url:{url}"
    title = _clean_text(candidate.get("title")).casefold()
    year = _clean_text(candidate.get("year"))
    if title:
        return f"title_year:{title}|{year}"
    provider_id = _clean_text((candidate.get("provenance") or {}).get("provider_id")).lower()
    source_id = _clean_text(candidate.get("source_id")).lower()
    return f"provider_source:{provider_id}|{source_id}"


def merge_literature_candidates(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    incoming_map = dict(incoming)

    for key in ("title", "journal", "doi", "url", "citation_text", "source_license_note"):
        if not _clean_text(merged.get(key)) and _clean_text(incoming_map.get(key)):
            merged[key] = incoming_map.get(key)

    if not merged.get("year") and incoming_map.get("year"):
        merged["year"] = incoming_map.get("year")

    merged_authors = _as_str_list(merged.get("authors"))
    for author in _as_str_list(incoming_map.get("authors")):
        if author not in merged_authors:
            merged_authors.append(author)
    merged["authors"] = merged_authors

    merged_fields = _as_str_list(merged.get("available_fields"))
    for field_name in _as_str_list(incoming_map.get("available_fields")):
        if field_name not in merged_fields:
            merged_fields.append(field_name)
    merged["available_fields"] = merged_fields

    if _access_rank(incoming_map.get("access_class")) > _access_rank(merged.get("access_class")):
        merged["access_class"] = incoming_map.get("access_class")
        if _clean_text(incoming_map.get("abstract_text")):
            merged["abstract_text"] = incoming_map.get("abstract_text")
        if _clean_text(incoming_map.get("oa_full_text")):
            merged["oa_full_text"] = incoming_map.get("oa_full_text")
    else:
        if not _clean_text(merged.get("abstract_text")) and _clean_text(incoming_map.get("abstract_text")):
            merged["abstract_text"] = incoming_map.get("abstract_text")
        if not _clean_text(merged.get("oa_full_text")) and _clean_text(incoming_map.get("oa_full_text")):
            merged["oa_full_text"] = incoming_map.get("oa_full_text")

    existing_provenance = dict(existing.get("provenance") or {})
    incoming_provenance = dict(incoming_map.get("provenance") or {})
    provider_scope = _as_str_list(existing_provenance.get("provider_scope"))
    for provider_id in _as_str_list(incoming_provenance.get("provider_scope") or incoming_provenance.get("provider_id")):
        if provider_id not in provider_scope:
            provider_scope.append(provider_id)
    request_ids = _as_str_list(existing_provenance.get("provider_request_ids") or existing_provenance.get("request_id"))
    for request_id in _as_str_list(incoming_provenance.get("provider_request_ids") or incoming_provenance.get("request_id")):
        if request_id not in request_ids:
            request_ids.append(request_id)

    merged["provenance"] = {
        **existing_provenance,
        **incoming_provenance,
        "provider_id": _clean_text(existing_provenance.get("provider_id") or incoming_provenance.get("provider_id")),
        "provider_scope": provider_scope,
        "provider_request_ids": request_ids,
        "result_source": _clean_text(existing_provenance.get("result_source") or incoming_provenance.get("result_source")),
        "query": _clean_text(existing_provenance.get("query") or incoming_provenance.get("query")),
    }
    return merged


class LiteratureProvider(Protocol):
    provider_id: str
    provider_result_source: str
    last_request_id: str
    last_query_status: str
    last_error_message: str

    def search(self, query: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        ...

    def fetch_accessible_text(self, candidate: dict[str, Any]) -> dict[str, Any] | None:
        ...


class MetadataSearchClient(Protocol):
    """Expected injected metadata-search client contract for live provider adapters.

    The client is responsible for performing a query against a legal-safe metadata API.
    It should accept `(query, filters)` and return either:
    - a mapping with `results` plus optional request/status metadata, or
    - a list of already-normalized metadata rows.
    """

    def __call__(self, query: str, filters: dict[str, Any]) -> Any:
        ...


class OpenAlexLikeClient(Protocol):
    """Production-shaped client contract for OpenAlex-like metadata providers."""

    def search_metadata(self, query: str, filters: Mapping[str, Any]) -> Any:
        ...


def _invoke_search_client(
    search_client: MetadataSearchClient | OpenAlexLikeClient | Any,
    query: str,
    filters: dict[str, Any],
) -> Any:
    if callable(search_client):
        return search_client(query, filters)
    search_metadata = getattr(search_client, "search_metadata", None)
    if callable(search_metadata):
        return search_metadata(query, filters)
    raise TypeError("Injected literature search client must be callable or expose search_metadata(query, filters).")


def _clean_doi(value: Any) -> str:
    token = _clean_text(value)
    if not token:
        return ""
    lowered = token.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if lowered.startswith(prefix):
            return token[len(prefix) :].strip()
    return token


def _nested_get(mapping: Mapping[str, Any] | None, *path: str) -> Any:
    current: Any = mapping or {}
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _first_non_empty(*values: Any) -> str:
    for value in values:
        cleaned = _clean_text(value)
        if cleaned:
            return cleaned
    return ""


def _abstract_from_inverted_index(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    positions: dict[int, str] = {}
    for token, offsets in value.items():
        cleaned_token = _clean_text(token)
        if not cleaned_token:
            continue
        for offset in offsets if isinstance(offsets, list) else []:
            try:
                index = int(offset)
            except (TypeError, ValueError):
                continue
            positions[index] = cleaned_token
    if not positions:
        return ""
    return _clean_text(" ".join(positions[index] for index in sorted(positions)))


def _extract_accessible_abstract_text(source: Mapping[str, Any]) -> str:
    direct_text = _first_non_empty(
        source.get("abstract_text"),
        source.get("abstract"),
        source.get("summary"),
        source.get("excerpt"),
        _nested_get(source, "primary_location", "abstract"),
        _nested_get(source, "primary_location", "summary"),
        _nested_get(source, "best_oa_location", "abstract"),
        _nested_get(source, "best_oa_location", "summary"),
    )
    if direct_text:
        return direct_text
    return _abstract_from_inverted_index(
        source.get("abstract_inverted_index") or source.get("abstract_inverted_index_v3") or source.get("inverted_index")
    )


def _extract_accessible_oa_text(source: Mapping[str, Any]) -> str:
    return _first_non_empty(
        source.get("oa_full_text"),
        source.get("fulltext"),
        source.get("full_text"),
        source.get("open_access_text"),
        _nested_get(source, "best_oa_location", "fulltext"),
        _nested_get(source, "best_oa_location", "text"),
        _nested_get(source, "open_access", "text"),
    )


def _provider_env(*suffixes: str) -> str:
    for suffix in suffixes:
        for prefix in ("MATERIALSCOPE_OPENALEX_", "THERMOANALYZER_OPENALEX_"):
            value = _clean_text(os.getenv(f"{prefix}{suffix}"))
            if value:
                return value
    return ""


def _provider_env_explicit(*suffixes: str) -> tuple[str, bool]:
    for suffix in suffixes:
        for prefix in ("MATERIALSCOPE_OPENALEX_", "THERMOANALYZER_OPENALEX_"):
            env_name = f"{prefix}{suffix}"
            raw = os.getenv(env_name)
            if raw is None:
                continue
            cleaned = _clean_text(raw)
            if cleaned:
                return cleaned, True
    return "", False


class OpenAlexHTTPClient:
    """Small legal-safe adapter for OpenAlex-like metadata APIs.

    The client retrieves bibliographic metadata only. It does not scrape pages,
    automate browsers, or fetch closed/paywalled full text.
    """

    def __init__(
        self,
        *,
        email: str = "",
        api_key: str = "",
        base_url: str = "https://api.openalex.org",
        timeout: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.email = _clean_text(email)
        self.api_key = _clean_text(api_key)
        self.base_url = (_clean_text(base_url) or "https://api.openalex.org").rstrip("/")
        self.timeout = float(timeout)
        self._http_client = http_client

    def _request_params(self, query: str, filters: Mapping[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {
            "search": _clean_text(query),
            "per-page": max(1, min(int(filters.get("top_k") or 5), 25)),
        }
        if self.email:
            params["mailto"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def _query_status_for_response(self, response: httpx.Response, detail: str) -> str:
        if response.status_code >= 500 or response.status_code == 429:
            return "provider_unavailable"
        lowered = detail.lower()
        if "too narrow" in lowered or "too broad" in lowered or "query" in lowered and "invalid" in lowered:
            return "query_too_narrow"
        return "request_failed"

    def search_metadata(self, query: str, filters: Mapping[str, Any]) -> dict[str, Any]:
        params = self._request_params(query, filters)
        request_id = f"litreq_openalex_like_provider_{uuid.uuid4().hex[:12]}"
        result_source = "openalex_api"
        owns_client = self._http_client is None
        client = self._http_client or httpx.Client(
            timeout=self.timeout,
            headers={"User-Agent": "MaterialScope/1.0 (legal-safe metadata-only literature lookup)"},
        )
        try:
            response = client.get(f"{self.base_url}/works", params=params)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            return {
                "request_id": request_id,
                "result_source": result_source,
                "query_status": "provider_unavailable",
                "error": _clean_text(exc) or "request timed out",
                "results": [],
            }
        except httpx.RequestError as exc:
            return {
                "request_id": request_id,
                "result_source": result_source,
                "query_status": "provider_unavailable",
                "error": _clean_text(exc) or exc.__class__.__name__,
                "results": [],
            }
        except httpx.HTTPStatusError as exc:
            detail = _clean_text(exc.response.text) or f"HTTP {exc.response.status_code}"
            return {
                "request_id": request_id,
                "result_source": result_source,
                "query_status": self._query_status_for_response(exc.response, detail),
                "error": detail,
                "results": [],
            }
        finally:
            if owns_client:
                client.close()

        try:
            payload = response.json() if response.content else {}
        except ValueError:
            return {
                "request_id": request_id,
                "result_source": result_source,
                "query_status": "request_failed",
                "error": "Provider response was not valid JSON.",
                "results": [],
            }
        meta = dict(payload.get("meta") or {}) if isinstance(payload, Mapping) else {}
        rows = payload.get("results") if isinstance(payload, Mapping) else []
        if not isinstance(rows, list):
            return {
                "request_id": request_id,
                "result_source": result_source,
                "query_status": "request_failed",
                "error": "Provider response did not contain a list of results.",
                "results": [],
            }
        return {
            "request_id": _first_non_empty(meta.get("request_id"), payload.get("request_id"), request_id),
            "result_source": result_source,
            "query_status": "success" if rows else "no_results",
            "results": rows,
        }


def build_openalex_like_client_from_env() -> OpenAlexHTTPClient | None:
    email = _provider_env("EMAIL")
    api_key = _provider_env("API_KEY")
    base_url, base_url_explicit = _provider_env_explicit("BASE_URL")
    configured = bool(email or api_key or base_url_explicit)
    if not configured:
        return None
    return OpenAlexHTTPClient(
        email=email,
        api_key=api_key,
        base_url=base_url or "https://api.openalex.org",
    )


class FixtureLiteratureProvider:
    """Synthetic provider used for MVP development and test coverage."""

    provider_id = "fixture_provider"
    provider_result_source = "fixture_search"

    def __init__(self, fixture_path: str | Path | None = None) -> None:
        self.fixture_path = Path(fixture_path) if fixture_path else (
            Path(__file__).resolve().parents[1] / "sample_data" / "literature_fixture_sources.json"
        )
        raw_payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        self._sources = normalize_literature_sources(raw_payload.get("sources") or [])
        self.last_request_id = ""
        self.last_query_status = ""
        self.last_error_message = ""

    def search(self, query: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = dict(filters or {})
        modality_filter = {
            str(item).upper()
            for item in (filters.get("modalities") or [])
            if str(item).strip()
        }
        access_filter = {
            str(item).lower()
            for item in (filters.get("access_classes") or [])
            if str(item).strip()
        }
        query_tokens = _tokenize(query)
        request_id = f"litreq_{self.provider_id}_{uuid.uuid4().hex[:12]}"
        self.last_request_id = request_id
        self.last_query_status = "success"
        self.last_error_message = ""

        ranked: list[tuple[int, dict[str, Any]]] = []
        for source in self._sources:
            provenance = dict(source.get("provenance") or {})
            source_modalities = {
                str(item).upper()
                for item in (provenance.get("modalities") or [])
                if str(item).strip()
            }
            if modality_filter and not (modality_filter & source_modalities):
                continue
            if access_filter and str(source.get("access_class") or "").lower() not in access_filter:
                continue

            searchable = " ".join(
                [
                    str(source.get("title") or ""),
                    str(source.get("abstract_text") or ""),
                    str(source.get("oa_full_text") or ""),
                    " ".join(str(item) for item in (provenance.get("keywords") or [])),
                ]
            ).lower()
            score = 0
            for token in query_tokens:
                if token in searchable:
                    score += 3
            for keyword in provenance.get("keywords") or []:
                if str(keyword).lower() in str(query).lower():
                    score += 2
            if query_tokens and score <= 0:
                continue

            candidate = dict(source)
            candidate["citation_text"] = candidate.get("citation_text") or format_citation_text(candidate)
            candidate["provenance"] = {
                **provenance,
                "provider_id": self.provider_id,
                "request_id": request_id,
                "result_source": self.provider_result_source,
                "query": query,
                "provider_scope": [self.provider_id],
                "provider_request_ids": [request_id],
            }
            ranked.append((score, candidate))

        ranked.sort(
            key=lambda item: (
                -item[0],
                -(item[1].get("year") or 0),
                str(item[1].get("title") or ""),
            )
        )
        results = [candidate for _score, candidate in ranked[: int(filters.get("top_k") or 5)]]
        self.last_query_status = "success" if results else "no_results"
        return results

    def fetch_accessible_text(self, candidate: dict[str, Any]) -> dict[str, Any] | None:
        access_class = str(candidate.get("access_class") or "metadata_only").lower()
        source_id = str(candidate.get("source_id") or "")

        # Legal guardrail: restricted external items are discoverable as metadata,
        # but their full text must not be fetched, cached, or reused in reasoning.
        if access_class == "restricted_external":
            return None

        if access_class == "open_access_full_text":
            text = str(candidate.get("oa_full_text") or candidate.get("abstract_text") or "").strip()
            if text:
                return {"source_id": source_id, "text": text, "field": "oa_full_text", "access_class": access_class}
            return None

        if access_class in {"abstract_only", "metadata_only"}:
            text = str(candidate.get("abstract_text") or "").strip()
            if text:
                return {"source_id": source_id, "text": text, "field": "abstract_text", "access_class": access_class}
            return None

        if access_class == "user_provided_document":
            text = str(candidate.get("oa_full_text") or candidate.get("abstract_text") or "").strip()
            if text:
                return {"source_id": source_id, "text": text, "field": "user_provided_document", "access_class": access_class}
            return None

        return None


class MetadataAPILiteratureProvider:
    """HTTP-client-ready metadata provider shell.

    Legal guardrail: this provider only returns provider-supplied metadata and any
    explicitly accessible text returned by the API. It must never crawl or retain
    closed/paywalled full text.
    """

    provider_id = "metadata_api_provider"
    provider_result_source = "metadata_api_search"

    def __init__(
        self,
        *,
        search_client: MetadataSearchClient | OpenAlexLikeClient | None = None,
    ) -> None:
        self._search_client = search_client
        self.last_request_id = ""
        self.last_query_status = ""
        self.last_error_message = ""

    def _request_payload(self, query: str, filters: dict[str, Any]) -> dict[str, Any]:
        return {
            "query": _clean_text(query),
            "filters": dict(filters or {}),
            "request_id": f"litreq_{self.provider_id}_{uuid.uuid4().hex[:12]}",
            "result_source": self.provider_result_source,
        }

    def search(self, query: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        payload = self._request_payload(query, dict(filters or {}))
        self.last_request_id = payload["request_id"]
        self.last_error_message = ""
        if self._search_client is None:
            self.last_query_status = "not_configured"
            return []

        try:
            raw_response = _invoke_search_client(self._search_client, query, dict(filters or {}))
        except Exception as exc:
            self.last_query_status = "provider_unavailable"
            self.last_error_message = _clean_text(exc) or exc.__class__.__name__
            return []
        result_source = payload["result_source"]
        request_id = payload["request_id"]
        query_status = "success"
        rows: list[dict[str, Any]] = []

        if isinstance(raw_response, Mapping):
            request_id = _clean_text(raw_response.get("request_id")) or request_id
            result_source = _clean_text(raw_response.get("result_source")) or result_source
            query_status = _clean_text(raw_response.get("query_status")).lower() or query_status
            if not query_status and _clean_text(raw_response.get("error")):
                query_status = "provider_unavailable"
            self.last_error_message = _clean_text(raw_response.get("error") or raw_response.get("detail"))
            rows = [dict(item) for item in (raw_response.get("results") or []) if isinstance(item, Mapping)]
        elif isinstance(raw_response, list):
            rows = [dict(item) for item in raw_response if isinstance(item, Mapping)]

        self.last_request_id = request_id
        if not rows and query_status == "success":
            query_status = "no_results"
        self.last_query_status = query_status
        return self._normalize_rows(rows, query=query, request_id=request_id, result_source=result_source)

    def _normalize_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        query: str,
        request_id: str,
        result_source: str,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in normalize_literature_sources(rows):
            provenance = dict(item.get("provenance") or {})
            normalized.append(
                {
                    **item,
                    "citation_text": item.get("citation_text") or format_citation_text(item),
                    "provenance": {
                        **provenance,
                        "provider_id": self.provider_id,
                        "request_id": request_id,
                        "result_source": result_source,
                        "query": query,
                        "provider_scope": [self.provider_id],
                        "provider_request_ids": [request_id],
                    },
                }
            )
        return normalized

    def fetch_accessible_text(self, candidate: dict[str, Any]) -> dict[str, Any] | None:
        access_class = _clean_text(candidate.get("access_class")).lower() or "metadata_only"
        source_id = _clean_text(candidate.get("source_id"))
        if access_class == "restricted_external":
            return None
        if access_class in {"open_access_full_text", "user_provided_document"}:
            text = _clean_text(candidate.get("oa_full_text") or candidate.get("abstract_text"))
            if text:
                field = "oa_full_text" if access_class == "open_access_full_text" else "user_provided_document"
                return {"source_id": source_id, "text": text, "field": field, "access_class": access_class}
            return None
        if access_class in {"abstract_only", "metadata_only"}:
            text = _clean_text(candidate.get("abstract_text") or _extract_accessible_abstract_text(candidate))
            if text:
                return {"source_id": source_id, "text": text, "field": "abstract_text", "access_class": access_class}
        return None


class OpenAlexLikeLiteratureProvider(MetadataAPILiteratureProvider):
    """OpenAlex-style metadata provider shell.

    Legal guardrail: this provider is metadata-first and only uses abstract or
    open-access text when the provider response already exposes it legally.

    Expected client behavior:
    - accepts `(query, filters)`
    - returns metadata rows plus optional `request_id`, `result_source`, `query_status`, and `error`
    - may expose abstract/open-access URL signals when legally available
    - must not scrape web pages or fetch closed/paywalled full text
    """

    provider_id = "openalex_like_provider"
    provider_result_source = "openalex_like_search"

    def __init__(
        self,
        *,
        client: OpenAlexLikeClient | MetadataSearchClient | None = None,
        search_client: OpenAlexLikeClient | MetadataSearchClient | None = None,
    ) -> None:
        super().__init__(search_client=client if client is not None else search_client)

    @classmethod
    def from_env(cls) -> OpenAlexLikeLiteratureProvider:
        return cls(client=build_openalex_like_client_from_env())

    def _normalize_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        query: str,
        request_id: str,
        result_source: str,
    ) -> list[dict[str, Any]]:
        normalized_rows: list[dict[str, Any]] = []
        for raw_row in rows:
            item = self._normalize_openalex_like_row(raw_row)
            if not item:
                continue
            provenance = dict(item.get("provenance") or {})
            normalized_rows.append(
                {
                    **item,
                    "citation_text": item.get("citation_text") or format_citation_text(item),
                    "provenance": {
                        **provenance,
                        "provider_id": self.provider_id,
                        "request_id": request_id,
                        "result_source": result_source,
                        "query": query,
                        "provider_scope": [self.provider_id],
                        "provider_request_ids": [request_id],
                    },
                }
            )
        return normalized_rows

    def _normalize_openalex_like_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        source = dict(row)
        title = _first_non_empty(source.get("title"), source.get("display_name"))
        if not title:
            return {}

        provenance = dict(source.get("provenance") or {}) if isinstance(source.get("provenance"), Mapping) else {}
        authors = _as_str_list(source.get("authors"))
        if not authors:
            authorships = source.get("authorships") or []
            if isinstance(authorships, list):
                for item in authorships:
                    if not isinstance(item, Mapping):
                        continue
                    author_name = _first_non_empty(
                        item.get("author_display_name"),
                        _nested_get(item, "author", "display_name"),
                    )
                    if author_name:
                        authors.append(author_name)

        abstract_text = _extract_accessible_abstract_text(source)
        oa_full_text = _extract_accessible_oa_text(source)
        access_class = _clean_text(source.get("access_class")).lower()
        if access_class not in ACCESS_CLASS_PRIORITY:
            access_class = "open_access_full_text" if oa_full_text else "abstract_only" if abstract_text else "metadata_only"
        elif access_class == "metadata_only" and abstract_text:
            access_class = "abstract_only"
        elif access_class == "abstract_only" and oa_full_text:
            access_class = "open_access_full_text"

        available_fields = _as_str_list(source.get("available_fields"))
        if not available_fields:
            available_fields = ["metadata"]
            if abstract_text:
                available_fields.append("abstract")
            if oa_full_text:
                available_fields.append("oa_full_text")
        else:
            if abstract_text and "abstract" not in available_fields:
                available_fields.append("abstract")
            if oa_full_text and "oa_full_text" not in available_fields:
                available_fields.append("oa_full_text")

        normalized = normalize_literature_sources(
            [
                {
                    "source_id": _first_non_empty(source.get("source_id"), source.get("id"), _nested_get(source, "ids", "openalex")),
                    "title": title,
                    "authors": authors,
                    "journal": _first_non_empty(
                        source.get("journal"),
                        _nested_get(source, "primary_location", "source", "display_name"),
                        _nested_get(source, "host_venue", "display_name"),
                    ),
                    "year": source.get("year") if source.get("year") not in (None, "") else source.get("publication_year"),
                    "doi": _clean_doi(source.get("doi") or _nested_get(source, "ids", "doi")),
                    "url": _first_non_empty(
                        source.get("url"),
                        _nested_get(source, "open_access", "oa_url"),
                        _nested_get(source, "best_oa_location", "landing_page_url"),
                        _nested_get(source, "best_oa_location", "pdf_url"),
                        _nested_get(source, "primary_location", "pdf_url"),
                        _nested_get(source, "primary_location", "landing_page_url"),
                        source.get("id"),
                    ),
                    "access_class": access_class,
                    "available_fields": available_fields,
                    "abstract_text": abstract_text,
                    "oa_full_text": oa_full_text,
                    "source_license_note": _first_non_empty(source.get("source_license_note"), "provider_metadata"),
                    "citation_text": _clean_text(source.get("citation_text")),
                    "provenance": provenance,
                }
            ]
        )
        return normalized[0] if normalized else {}


class MultiLiteratureProviderAggregator:
    provider_id = "multi_provider_aggregator"
    provider_result_source = "multi_provider_search"

    def __init__(self, providers: list[LiteratureProvider]) -> None:
        self.providers = list(providers)
        self.last_request_id = ""
        self.last_request_ids: list[str] = []
        self.last_query_status = ""
        self.last_error_message = ""

    def search(self, query: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        aggregated: dict[str, dict[str, Any]] = {}
        self.last_request_ids = []
        statuses: list[str] = []
        errors: list[str] = []
        for provider in self.providers:
            for candidate in provider.search(query, filters=filters):
                identity = citation_identity_key(candidate)
                if identity in aggregated:
                    aggregated[identity] = merge_literature_candidates(aggregated[identity], candidate)
                else:
                    aggregated[identity] = dict(candidate)
            request_id = _clean_text(getattr(provider, "last_request_id", ""))
            if request_id and request_id not in self.last_request_ids:
                self.last_request_ids.append(request_id)
            status = _clean_text(getattr(provider, "last_query_status", "")).lower()
            if status:
                statuses.append(status)
            error = _clean_text(getattr(provider, "last_error_message", ""))
            if error:
                errors.append(error)
        self.last_request_id = self.last_request_ids[-1] if self.last_request_ids else ""
        if aggregated:
            self.last_query_status = "success"
        elif statuses and all(status == "not_configured" for status in statuses):
            self.last_query_status = "not_configured"
        elif "provider_unavailable" in statuses:
            self.last_query_status = "provider_unavailable"
        elif "request_failed" in statuses:
            self.last_query_status = "request_failed"
        elif "query_too_narrow" in statuses and all(
            status in {"query_too_narrow", "no_results", "success"} for status in statuses
        ):
            self.last_query_status = "query_too_narrow"
        elif statuses:
            self.last_query_status = "no_results"
        else:
            self.last_query_status = ""
        self.last_error_message = "; ".join(errors)
        return list(aggregated.values())

    def fetch_accessible_text(self, candidate: dict[str, Any]) -> dict[str, Any] | None:
        provider_scope = _as_str_list((candidate.get("provenance") or {}).get("provider_scope"))
        provider_id = _clean_text((candidate.get("provenance") or {}).get("provider_id"))
        candidate_scope = provider_scope or ([provider_id] if provider_id else [])
        for provider in self.providers:
            if provider.provider_id not in candidate_scope:
                continue
            accessible = provider.fetch_accessible_text(candidate)
            if accessible is not None:
                return accessible
        return None


def default_literature_provider_registry() -> dict[str, Callable[[], LiteratureProvider]]:
    return {
        "fixture_provider": FixtureLiteratureProvider,
        "metadata_api_provider": MetadataAPILiteratureProvider,
        "openalex_like_provider": OpenAlexLikeLiteratureProvider.from_env,
    }


def available_literature_provider_ids(
    *,
    registry: Mapping[str, Callable[[], LiteratureProvider]] | None = None,
) -> list[str]:
    return sorted(str(provider_id).strip() for provider_id in (registry or default_literature_provider_registry()) if str(provider_id).strip())


def resolve_literature_provider(
    provider_ids: list[str] | None = None,
    *,
    registry: Mapping[str, Callable[[], LiteratureProvider]] | None = None,
) -> tuple[LiteratureProvider, list[str]]:
    providers, provider_scope = resolve_literature_providers(provider_ids, registry=registry)
    if len(providers) != 1:
        raise ValueError("Multiple literature providers were requested; use resolve_literature_providers instead.")
    return providers[0], provider_scope


def resolve_literature_providers(
    provider_ids: list[str] | None = None,
    *,
    registry: Mapping[str, Callable[[], LiteratureProvider]] | None = None,
) -> tuple[list[LiteratureProvider], list[str]]:
    registry_map = dict(registry or default_literature_provider_registry())
    requested_ids: list[str] = []
    for item in provider_ids or []:
        token = str(item).strip()
        if token and token not in requested_ids:
            requested_ids.append(token)

    selected_ids = requested_ids or ["fixture_provider"]
    providers: list[LiteratureProvider] = []
    for provider_id in selected_ids:
        factory = registry_map.get(provider_id)
        if factory is None:
            available = ", ".join(available_literature_provider_ids(registry=registry_map)) or "none"
            raise ValueError(f"Unknown literature provider '{provider_id}'. Available providers: {available}.")
        providers.append(factory())
    return providers, selected_ids
