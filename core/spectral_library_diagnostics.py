"""Single entry point for spectral reference-library runtime diagnostics (FTIR/Raman/XRD client path)."""

from __future__ import annotations

import os
from typing import Any, Mapping

from core.hosted_library import HostedLibraryCatalog, resolve_hosted_root
from core.library_cloud_client import (
    CLOUD_URL_ENV,
    CLOUD_URL_ENV_LEGACY,
    get_library_cloud_client,
)
from core.reference_library import get_reference_library_manager


def collect_spectral_library_runtime_diagnostics(
    *,
    analysis_type: str = "FTIR",
    include_health_probe: bool = True,
) -> dict[str, Any]:
    """Return a JSON-serializable snapshot for dev tools and logging.

    Spectral batch runs try the managed cloud HTTP client first; if that returns no payload,
    ``core.batch_runner`` falls back to installed mirror candidates, then dataset-embedded refs.
    This helper surfaces those branches without executing a search.
    """
    modality = str(analysis_type or "").strip().upper() or "FTIR"
    client = get_library_cloud_client()
    mgr = get_reference_library_manager()
    ctx = mgr.library_context(modality)
    status = mgr.status()
    hosted = HostedLibraryCatalog()
    probe: dict[str, Any]
    if include_health_probe:
        probe = dict(client.health_probe())
    else:
        probe = {"state": "skipped", "message": "health probe skipped"}

    health_state = str(probe.get("state") or "")
    installed_n = int(mgr.count_installed_candidates(modality))
    env_url = str(os.getenv(CLOUD_URL_ENV, "") or os.getenv(CLOUD_URL_ENV_LEGACY, "") or "").strip()

    resolution_order: list[dict[str, Any]] = [
        {
            "step": "cloud_search",
            "eligible": bool(client.configured and client.enabled_by_env),
            "health_probe_state": health_state,
            "summary": (
                "Batch calls /v1/library/search/* with a bearer token when configured and enabled."
            ),
        },
        {
            "step": "limited_fallback_cache",
            "eligible": installed_n > 0,
            "installed_candidate_count": installed_n,
            "summary": "Used when cloud search is not used or returns no usable payload but mirror packages exist.",
        },
        {
            "step": "dataset_embedded",
            "eligible": False,
            "summary": "Used when dataset metadata carries embedded spectral references (see batch_runner).",
        },
        {
            "step": "unavailable",
            "eligible": not client.configured,
            "summary": "No cloud client and no offline candidates → library_result_source may be unavailable.",
        },
    ]

    return {
        "modality": modality,
        "effective_cloud_url": str(client.base_url or ""),
        "raw_cloud_url_env": env_url,
        "cloud_client_configured": bool(client.configured),
        "cloud_client_enabled_by_env": bool(client.enabled_by_env),
        "cloud_health_probe": probe,
        "cloud_last_error": (client.last_error or "")[:500],
        "cloud_last_error_kind": getattr(client, "last_error_kind", "") or "",
        "cloud_last_auth_mode": getattr(client, "last_auth_mode", "") or "",
        "effective_hosted_root": str(resolve_hosted_root()),
        "hosted_catalog_root_used": str(hosted.root),
        "hosted_manifest_exists": bool(hosted.manifest_path.exists()),
        "hosted_live_provider_count": int(hosted.live_provider_count(modality=modality)),
        "hosted_load_entries_count": len(hosted.load_entries(modality)),
        "hosted_missing_modalities": hosted.missing_modalities(("FTIR", "RAMAN", "XRD")),
        "reference_library_status": dict(status) if isinstance(status, Mapping) else status,
        "library_context": dict(ctx) if isinstance(ctx, Mapping) else ctx,
        "installed_candidate_count": installed_n,
        "batch_resolution_order": resolution_order,
        "library_result_source_vocabulary": [
            "cloud_search",
            "limited_fallback_cache",
            "dataset_embedded",
            "unavailable",
            "not_configured",
        ],
    }
