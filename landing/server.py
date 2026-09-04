"""Public landing page + waitlist endpoint for MaterialScope.

Run with: ``python -m landing.server --port 8090``

Serves the static site in ``landing/web/`` and exposes one write path —
``POST /api/waitlist`` — backed by :class:`landing.store.WaitlistStore`.
Deliberately standalone: it never imports the product (Dash UI or analysis
core), so marketing infrastructure can move to its own deployment without
touching the app.  Replace ``WaitlistStore`` with a database or CRM client
to persist submissions elsewhere; the HTTP contract stays the same.
"""

from __future__ import annotations

import argparse
import html
import mimetypes
import os
import time
from collections import deque
from pathlib import Path
from urllib.parse import parse_qs

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from landing.store import WaitlistStore, is_valid_email, normalize_email

mimetypes.add_type("font/woff2", ".woff2")

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = Path(__file__).resolve().parent / "web"
DEFAULT_DATA_DIR = REPO_ROOT / "landing" / "data"

LANDING_API_VERSION = "0.1"
RATE_LIMIT_WINDOW_SECONDS = 60.0
RATE_LIMIT_MAX_REQUESTS = 6

# Paths handled by the API; everything else falls through to the static site.
_STATIC_CACHE_CONTROL = {
    ".css": "public, max-age=3600",
    ".js": "public, max-age=3600",
    ".svg": "public, max-age=86400",
    ".png": "public, max-age=86400",
    ".woff2": "public, max-age=31536000, immutable",
}


class WaitlistJoinRequest(BaseModel):
    """Payload for ``POST /api/waitlist``.

    ``company`` is a honeypot field: real visitors never fill it, bots do.
    """

    email: str = Field(default="", max_length=320)
    role: str = Field(default="", max_length=128)
    company: str = Field(default="", max_length=128)


class WaitlistJoinResponse(BaseModel):
    status: str  # "joined" | "already" | "discarded"


class LandingHealthResponse(BaseModel):
    status: str = "ok"
    service: str = "materialscope-landing"
    api_version: str


class _RateLimiter:
    """Small sliding-window limiter (per client host) for a public endpoint."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._hits.setdefault(key, deque())
        while bucket and now - bucket[0] > self._window:
            bucket.popleft()
        if len(bucket) >= self._max:
            return False
        bucket.append(now)
        return True


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def create_landing_app(
    *,
    store: WaitlistStore | None = None,
    web_dir: Path | None = None,
) -> FastAPI:
    """Create the landing app.  ``store`` is injectable for tests/swap-outs."""
    site_dir = Path(web_dir or WEB_DIR)
    waitlist = store or WaitlistStore(DEFAULT_DATA_DIR / "waitlist.jsonl")
    limiter = _RateLimiter(RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECONDS)

    app = FastAPI(title="MaterialScope Landing", version=LANDING_API_VERSION)

    @app.get("/api/health", response_model=LandingHealthResponse)
    def health() -> LandingHealthResponse:
        return LandingHealthResponse(api_version=LANDING_API_VERSION)

    @app.post("/api/waitlist", response_model=WaitlistJoinResponse)
    def join_waitlist(
        payload: WaitlistJoinRequest,
        request: Request,
        response: Response,
    ) -> WaitlistJoinResponse:
        if payload.company.strip():
            # Honeypot triggered: pretend success, record nothing.
            return WaitlistJoinResponse(status="discarded")
        if not limiter.allow(_client_key(request)):
            raise HTTPException(
                status_code=429,
                detail="Too many attempts from this address — wait a minute and try again.",
            )
        email = normalize_email(payload.email)
        if not is_valid_email(email):
            raise HTTPException(status_code=422, detail="Please enter a valid email address.")
        try:
            status = waitlist.join(email, payload.role)
        except OSError as exc:  # storage failure surfaces as retryable error
            raise HTTPException(status_code=503, detail="Could not save your email — please try again.") from exc
        if status == "joined":
            response.status_code = 201
        return WaitlistJoinResponse(status=status)

    @app.post("/api/waitlist/form", include_in_schema=False, response_class=HTMLResponse)
    async def join_waitlist_form(request: Request) -> HTMLResponse:
        """Form-encoded fallback for browsers without JavaScript.

        Mirrors the JSON contract; renders a minimal result page instead of
        requiring the client-side success state.
        """
        body = (await request.body()).decode("utf-8", "replace")
        fields = {key: (values[0] if values else "") for key, values in parse_qs(body).items()}
        if fields.get("company", "").strip():
            return _form_page("You're on the list.", saved=True)
        if not limiter.allow(_client_key(request)):
            return _form_page("Too many attempts — please wait a minute and try again.", ok=False)
        email = normalize_email(fields.get("email", ""))
        if not is_valid_email(email):
            return _form_page("That email address doesn't look right.", ok=False)
        try:
            status = waitlist.join(email, fields.get("role", ""))
        except OSError:
            return _form_page("Could not save your email — please try again.", ok=False)
        message = "You're already on the list." if status == "already" else "You're on the list."
        return _form_page(message, saved=True)

    def _form_page(message: str, *, ok: bool = True, saved: bool = False) -> HTMLResponse:
        note = (
            "We'll email you when early access opens."
            if saved
            else "Return to the page and try again."
        )
        page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MaterialScope — waitlist</title>
<style>
  body {{ font-family: 'IBM Plex Sans', -apple-system, sans-serif; margin: 0; min-height: 100svh;
         display: grid; place-items: center; background: #121110; color: #EEEDEA; padding: 24px; }}
  main {{ max-width: 420px; text-align: center; border: 1px solid #3D3B38; background: #1A1917;
         border-radius: 16px; padding: 40px 32px; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 10px; }}
  p {{ color: #C6C0B6; margin: 0 0 22px; }}
  a {{ color: #CBB896; font-weight: 600; }}
  svg {{ margin-bottom: 14px; }}
</style></head>
<body><main>
{'<svg width="40" height="40" viewBox="0 0 44 44" fill="none"><circle cx="22" cy="22" r="19" stroke="#CBB896" stroke-width="2"/><path d="M14 22.5l5.5 5.5L30.5 17" stroke="#CBB896" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>' if saved else ''}
<h1>{html.escape(message)}</h1>
<p>{html.escape(note)}</p>
<a href="/">Back to MaterialScope</a>
</main></body></html>"""
        return HTMLResponse(page, status_code=200 if ok else 422)

    # Static site last so /api/* always wins route matching.
    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return _static_response("index.html")

    def _static_response(name: str) -> FileResponse:
        target = site_dir / name
        suffix = target.suffix.lower()
        headers = {}
        if suffix in _STATIC_CACHE_CONTROL:
            headers["Cache-Control"] = _STATIC_CACHE_CONTROL[suffix]
        else:
            headers["Cache-Control"] = "no-cache"
        return FileResponse(target, headers=headers)

    app.mount("/static", StaticFiles(directory=site_dir), name="landing-static")
    app.state.waitlist_store = waitlist
    return app


def default_data_dir() -> Path:
    return Path(os.environ.get("MATERIALSCOPE_LANDING_DATA", DEFAULT_DATA_DIR))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MaterialScope landing page server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()

    app = create_landing_app(store=WaitlistStore(default_data_dir() / "waitlist.jsonl"))
    print(f"MaterialScope landing starting on http://{args.host}:{args.port}", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
