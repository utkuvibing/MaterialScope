"""Environment bootstrap for ``python -m dash_app.server`` (combined FastAPI + Dash).

The FastAPI app and spectral batch runner call the managed cloud-library HTTP client against
``MATERIALSCOPE_LIBRARY_CLOUD_URL``. Docker-style defaults use port **8000**, while the combined
dev server listens on **8050** by default, which previously required manual shell fixes on WSL.

This module runs **before** ``backend.app.create_app`` so ``ManagedLibraryCloudService`` reads
corrected environment variables on first startup.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from core.library_cloud_client import (
    CLOUD_URL_ENV,
    CLOUD_URL_ENV_LEGACY,
    DEV_CLOUD_AUTH_ENV,
    DEV_CLOUD_AUTH_ENV_LEGACY,
    reset_library_cloud_client,
)
from core.path_env import library_filesystem_env_looks_like_windows_leak

# Keep literal names here so this module stays lightweight (no numpy via core.hosted_library).
_ENV_HOSTED_ROOT = ("MATERIALSCOPE_LIBRARY_HOSTED_ROOT", "THERMOANALYZER_LIBRARY_HOSTED_ROOT")
_ENV_MIRROR_ROOT = ("MATERIALSCOPE_LIBRARY_MIRROR_ROOT", "THERMOANALYZER_LIBRARY_MIRROR_ROOT")


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _loopback_hostname(hostname: str) -> bool:
    return hostname.strip().lower() in {"", "127.0.0.1", "localhost", "::1"}


def _bind_host_for_client(listen_host: str) -> str:
    token = str(listen_host or "").strip()
    if token in {"0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    return token or "127.0.0.1"


def sanitize_library_path_env_vars() -> list[str]:
    """Clear obviously broken Windows-derived library path env vars on POSIX hosts."""
    lines: list[str] = []
    pairs: list[tuple[str, str]] = [
        (_ENV_HOSTED_ROOT[0], "hosted library catalog"),
        (_ENV_HOSTED_ROOT[1], "hosted library catalog (legacy)"),
        (_ENV_MIRROR_ROOT[0], "library mirror"),
        (_ENV_MIRROR_ROOT[1], "library mirror (legacy)"),
    ]
    for env_name, label in pairs:
        raw = os.getenv(env_name, "")
        if not str(raw).strip():
            continue
        if library_filesystem_env_looks_like_windows_leak(str(raw)):
            os.environ.pop(env_name, None)
            lines.append(
                f"[library-env] Ignored {env_name} ({label}): value looks like a Windows path on "
                f"{sys.platform!r} ({raw!r}). Using repo defaults instead. Fix or remove this line in .env."
            )
    return lines


def apply_combined_dash_server_library_env(*, listen_host: str, listen_port: int) -> list[str]:
    """Align cloud-library client URL with this combined server's listen port when appropriate."""
    lines: list[str] = []
    if _truthy(os.getenv("MATERIALSCOPE_LIBRARY_DISABLE_COMBINED_BOOTSTRAP", "")):
        lines.append(
            "[library-env] Combined Dash bootstrap disabled via MATERIALSCOPE_LIBRARY_DISABLE_COMBINED_BOOTSTRAP."
        )
        return lines

    bind = _bind_host_for_client(listen_host)
    desired = f"http://{bind}:{int(listen_port)}".rstrip("/")

    primary = str(os.getenv(CLOUD_URL_ENV, "") or "").strip()
    legacy = str(os.getenv(CLOUD_URL_ENV_LEGACY, "") or "").strip()
    raw = primary or legacy

    if not raw:
        os.environ[CLOUD_URL_ENV] = desired
        reset_library_cloud_client()
        lines.append(
            f"[library-env] MATERIALSCOPE_LIBRARY_CLOUD_URL was unset; defaulting to {desired!r} for "
            "this combined Dash + FastAPI process."
        )
        if not _truthy(os.getenv(DEV_CLOUD_AUTH_ENV, "") or os.getenv(DEV_CLOUD_AUTH_ENV_LEGACY, "")):
            lines.append(
                f"[library-env] Tip: set {DEV_CLOUD_AUTH_ENV}=1 in .env for local trial-token cloud auth "
                "(unless you already use a stored trial/activated license)."
            )
        return lines

    try:
        parsed = urlparse(raw)
    except Exception:
        lines.append(f"[library-env] MATERIALSCOPE_LIBRARY_CLOUD_URL is not a valid URL: {raw!r}")
        return lines

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        lines.append(f"[library-env] MATERIALSCOPE_LIBRARY_CLOUD_URL must be http(s): {raw!r}")
        return lines

    url_port = parsed.port
    if url_port is None:
        url_port = 443 if parsed.scheme == "https" else 80

    # Typical docker/.env.example default while this process listens elsewhere.
    if (
        _loopback_hostname(str(parsed.hostname or ""))
        and url_port == 8000
        and int(listen_port) != 8000
    ):
        os.environ[CLOUD_URL_ENV] = desired
        os.environ.pop(CLOUD_URL_ENV_LEGACY, None)
        reset_library_cloud_client()
        lines.append(
            f"[library-env] Cloud URL pointed to loopback port 8000 ({raw!r}) but this combined server "
            f"listens on {int(listen_port)}; updated MATERIALSCOPE_LIBRARY_CLOUD_URL to {desired!r}. "
            "Use a standalone backend on 8000 (``python -m backend.main``) if you need that layout."
        )
        return lines

    if _loopback_hostname(str(parsed.hostname or "")) and url_port != int(listen_port):
        lines.append(
            f"[library-env] Warning: MATERIALSCOPE_LIBRARY_CLOUD_URL uses port {url_port} ({raw!r}) but "
            f"this combined server listens on {int(listen_port)}. Cloud library calls may fail with "
            "connection_refused unless a separate backend is running on that port."
        )

    return lines
