"""Focused regression: the combined app serves Dash natively on one FastAPI server.

The legacy topology created a FastAPI backend plus a separate Flask-backed
Dash server and bridged it with ``WSGIMiddleware(dash.server)`` at ``/``. On
the Vercel container runtime that bridge degraded every
``POST /_dash-update-component`` into an application-level 400 (the request
body never reached Dash's callback dispatcher intact). Dash 4.2+ supports a
native FastAPI backend instead: the existing FastAPI app is passed in as
``Dash(server=...)`` and Dash registers ``/_dash-*`` routes on that same ASGI
app. These tests pin that contract.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from dash_app.server import create_combined_app


@pytest.fixture()
def combined() -> tuple[FastAPI, TestClient]:
    app = create_combined_app()
    return app, TestClient(app)


def test_combined_app_uses_one_fastapi_server_for_api_and_dash(combined: tuple[FastAPI, TestClient]):
    app, _client = combined

    # The combined app IS the FastAPI backend app, and Dash registered itself
    # on that same instance instead of building a parallel Flask server.
    assert isinstance(app, FastAPI)
    dash_app = app.state.dash_app
    assert dash_app.server is app
    assert type(dash_app.backend).__name__ == "FastAPIDashServer"

    # The legacy WSGI bridge mount is gone: the only mounts left are Dash's
    # own asset/websocket mounts, nothing bridging a second server at "/".
    mounts = [route for route in app.router.routes if isinstance(route, Mount)]
    assert all(route.path != "/" for route in mounts)


def test_rest_api_and_dash_served_by_the_same_app(combined: tuple[FastAPI, TestClient]):
    app, client = combined

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    workspace = client.post("/workspace/new")
    assert workspace.status_code == 200
    assert workspace.json()["project_id"]

    # Dash endpoints answer on the very same app instance.
    index = client.get("/")
    assert index.status_code == 200
    assert "MaterialScope" in index.text

    layout = client.get("/_dash-layout")
    assert layout.status_code == 200
    assert "MaterialScope" in json.dumps(layout.json())

    dependencies = client.get("/_dash-dependencies")
    assert dependencies.status_code == 200
    assert isinstance(dependencies.json(), list)
    assert len(dependencies.json()) > 0


def test_dash_assets_and_page_deep_links_served(combined: tuple[FastAPI, TestClient]):
    _app, client = combined

    style = client.get("/assets/style.css")
    assert style.status_code == 200
    assert "css" in style.headers.get("content-type", "")

    # Client-side-routing deep links must render the Dash index shell.
    deep_link = client.get("/dsc")
    assert deep_link.status_code == 200
    assert "DSC Analysis - MaterialScope" in deep_link.text


def test_real_dash_callback_post_reaches_dash_without_400(combined: tuple[FastAPI, TestClient]):
    """The Vercel failure signature: POST /_dash-update-component returning 400.

    Registers a genuine callback on the combined app's Dash instance and drives
    the full native dispatch path (DashMiddleware -> callback dispatcher ->
    JSON response) with a real browser-shaped payload.
    """
    app, client = combined
    dash_app = app.state.dash_app

    from dash import Input, Output

    @dash_app.callback(
        Output("fastapi-backend-probe-output", "children"),
        Input("fastapi-backend-probe-input", "value"),
    )
    def _probe(value: str | None) -> str:
        return f"echo:{value}"

    assert "fastapi-backend-probe-output.children" in dash_app.callback_map

    payload = {
        "output": "fastapi-backend-probe-output.children",
        "outputs": {"id": "fastapi-backend-probe-output", "property": "children"},
        "inputs": [
            {
                "id": "fastapi-backend-probe-input",
                "property": "value",
                "value": "native-fastapi",
            }
        ],
        "changedPropIds": ["fastapi-backend-probe-input.value"],
    }
    response = client.post("/_dash-update-component", json=payload)

    assert response.status_code != 400
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["response"]["fastapi-backend-probe-output"]["children"] == "echo:native-fastapi"


def test_proxy_absolute_form_callback_post_reaches_dash(combined: tuple[FastAPI, TestClient]):
    """Vercel's proxy sends absolute-form targets (POST https://host/...).

    httptools rejected those with a parser-level 400 (why ``http="h11"`` is
    pinned); h11 accepts them but leaves the absolute URL in the ASGI path.
    The combined server must translate them to origin-form so the callback
    POST reaches Dash's dispatcher instead of the GET-only catch-all.
    """
    import asyncio
    import json as jsonlib

    app, _client = combined
    dash_app = app.state.dash_app

    from dash import Input, Output

    @dash_app.callback(
        Output("proxy-probe-output", "children"),
        Input("proxy-probe-input", "value"),
    )
    def _probe(value: str | None) -> str:
        return f"echo:{value}"

    payload = jsonlib.dumps(
        {
            "output": "proxy-probe-output.children",
            "outputs": {"id": "proxy-probe-output", "property": "children"},
            "inputs": [
                {
                    "id": "proxy-probe-input",
                    "property": "value",
                    "value": "absolute-form",
                }
            ],
            "changedPropIds": ["proxy-probe-input.value"],
        }
    ).encode()
    raw_target = b"https://materialscope-preview.vercel.app/_dash-update-component"
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        # uvicorn's h11 parser forwards absolute-form targets verbatim.
        "path": raw_target.decode("ascii"),
        "raw_path": raw_target,
        "query_string": b"",
        "headers": [
            (b"host", b"materialscope-preview.vercel.app"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode("ascii")),
        ],
        "client": ("10.0.0.1", 54321),
        "server": ("0.0.0.0", 8050),
    }
    response: dict = {}

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            response["status"] = message["status"]
        elif message["type"] == "http.response.body":
            response.setdefault("body", b"")
            response["body"] += message.get("body", b"")
            response["complete"] = not message.get("more_body", False)

    asyncio.run(app(scope, receive, send))

    assert response.get("status") != 400
    assert response.get("status") == 200, response.get("body")
    assert response.get("complete")
    body = jsonlib.loads(response["body"])
    assert body["response"]["proxy-probe-output"]["children"] == "echo:absolute-form"
