"""Dash application factory for MaterialScope."""

from __future__ import annotations

import asyncio
import inspect

import dash
import dash_bootstrap_components as dbc
from fastapi import FastAPI


class MaterialScopeDash(dash.Dash):
    def _execute_callback(self, func, args, outputs_list, g):
        """Keep synchronous work off the co-located API's event loop.

        Dash's native FastAPI HTTP dispatcher calls synchronous callbacks inline.
        Our callbacks use a synchronous HTTP client to that same server, so inline
        execution blocks the API until the client times out. Offload the complete
        callback wrapper (including serialization); to_thread preserves request
        and Dash ContextVars. Async callbacks, including Pages routing, stay on
        the event loop. This private Dash seam is covered by live dispatch tests.
        """
        invoke = super()._execute_callback(func, args, outputs_list, g)
        if not isinstance(self.server, FastAPI) or inspect.iscoroutinefunction(func):
            return invoke
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # WebSocket dispatch already runs sync callbacks in its own executor.
            return invoke

        async def invoke_in_thread():
            return await asyncio.to_thread(invoke)

        return invoke_in_thread


def create_dash_app(
    *,
    requests_pathname_prefix: str = "/",
    server: FastAPI | None = None,
) -> dash.Dash:
    """Create and return the Dash application instance.

    ``server`` may be an existing FastAPI app so Dash registers its routes on
    that same ASGI app (Dash 4.2+ native FastAPI backend) instead of creating
    its own Flask server behind a WSGI bridge.
    """
    # Unit tests may ``import dash_app.pages.*`` with a throwaway Dash app, which registers
    # pages under ``dash_app.pages.<name>``. The real app loads the same files via
    # ``pages_folder`` as ``pages.<name>``, which would duplicate routes — clear stale entries.
    import dash._pages as _dash_pages

    for _key in list(_dash_pages.PAGE_REGISTRY.keys()):
        if isinstance(_key, str) and _key.startswith("dash_app.pages."):
            del _dash_pages.PAGE_REGISTRY[_key]

    app = MaterialScopeDash(
        __name__,
        server=server if server is not None else True,
        use_pages=True,
        pages_folder="pages",
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap",
        ],
        suppress_callback_exceptions=True,
        requests_pathname_prefix=requests_pathname_prefix,
        title="MaterialScope",
        update_title="MaterialScope ...",
    )

    from dash_app.layout import build_layout, register_clientside_theme

    app.layout = build_layout()
    register_clientside_theme(app)
    return app
