"""Combined FastAPI + Dash server entrypoint.

Run with: python -m dash_app.server
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

import uvicorn
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MaterialScope (Dash + FastAPI).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--token", default="")
    return parser.parse_args()


class _AbsoluteFormTargetMiddleware:
    """Translate absolute-form request targets to origin-form (RFC 9110 7.2).

    The deployment contract pins uvicorn's ``http="h11"`` parser because
    proxy-fronted runtimes (Vercel's container service) send request shapes
    such as ``POST https://<host>/_dash-update-component`` that httptools
    rejects with a parser-level ``400 Invalid HTTP request received.``. h11
    accepts those targets, but uvicorn forwards the full absolute URL as the
    ASGI ``path``, where it can never match a concrete route — callback POSTs
    fell through to Dash's GET-only index catch-all. RFC 9110 requires a
    server to translate absolute-form targets to origin-form; this middleware
    performs that translation and leaves origin-form targets untouched.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and b"://" in (scope.get("raw_path") or b""):
            target = scope["raw_path"].decode("ascii", "replace")
            parts = urlsplit(target)
            origin_path = parts.path or "/"
            scope["raw_path"] = origin_path.encode("ascii")
            scope["path"] = unquote(origin_path)
            if parts.query:
                scope["query_string"] = parts.query.encode("ascii")
        await self.app(scope, receive, send)


def _register_dash_catchall(dash_app) -> None:
    """Register Dash's client-side-routing catch-all at app creation time.

    Dash's FastAPI backend wires its ``{path:path}`` index catch-all only from
    ASGI lifespan (via ``DashMiddleware``), so deep links (``/dsc``, ``/tga``,
    ...) would 404 until a lifespan-aware server has started — and would never
    resolve under plain TestClient usage. Calling the same hook eagerly keeps
    page paths answering the Dash index from the very first request; the later
    lifespan call simply registers a duplicate that never wins route matching.
    """
    setup_catchall = getattr(dash_app.backend, "_setup_catchall", None)
    if not callable(setup_catchall):
        raise RuntimeError(
            "The installed Dash FastAPI backend does not expose "
            "_setup_catchall; page deep links would not resolve. "
            "Check the dash[fastapi] version contract (>=4.2,<5)."
        )
    setup_catchall()


def create_combined_app(*, api_token: str | None = None):
    """Create the MaterialScope FastAPI app with the native Dash FastAPI backend.

    One ASGI app serves both the REST API and the Dash UI: Dash (4.2+) registers
    its routes directly on the existing FastAPI instance, so no WSGI bridge is
    involved anywhere in the request path.
    """
    if api_token:
        # Explicit server token is authoritative: synchronize the co-located
        # Dash client's outbound token to the same value (explicit wins over
        # any stale MATERIALSCOPE_API_TOKEN). Server auth itself is still
        # controlled only by api_token; the env var is never read as auth.
        os.environ["MATERIALSCOPE_API_TOKEN"] = api_token
    from backend.app import create_app as create_backend
    from dash_app.app import create_dash_app

    api = create_backend(api_token=api_token)
    dash_app = create_dash_app(server=api)
    _register_dash_catchall(dash_app)
    api.state.dash_app = dash_app
    # Registered last so it is the outermost middleware: proxy-shaped targets
    # are normalized before Dash's middleware and FastAPI's router see them.
    api.add_middleware(_AbsoluteFormTargetMiddleware)
    return api


def main() -> None:
    load_dotenv(dotenv_path=REPO_ROOT / ".env", override=False)
    args = parse_args()

    from core.library_combined_bootstrap import (
        apply_combined_dash_server_library_env,
        sanitize_library_path_env_vars,
    )

    for line in sanitize_library_path_env_vars():
        print(line, flush=True)
    for line in apply_combined_dash_server_library_env(listen_host=args.host, listen_port=args.port):
        print(line, flush=True)
    # This entrypoint always serves Dash and the API in one process. Override
    # inherited values so callbacks cannot target a stale port from an earlier
    # desktop/backend launch and silently turn API failures into no-op 200s.
    os.environ["MATERIALSCOPE_API_URL"] = f"http://127.0.0.1:{args.port}"
    if args.token:
        os.environ["MATERIALSCOPE_API_TOKEN"] = args.token

    app = create_combined_app(api_token=args.token or None)
    print(f"MaterialScope (Dash) starting on http://{args.host}:{args.port}", flush=True)
    from backend.app import non_loopback_bind_warning

    warning = non_loopback_bind_warning(host=args.host, api_token=args.token or None)
    if warning:
        print(warning, flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info", http="h11")


if __name__ == "__main__":
    main()
