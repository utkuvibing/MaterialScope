"""Contract tests for the landing-page waitlist service (landing/ package)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from landing.server import create_landing_app
from landing.store import WaitlistStore, is_valid_email, normalize_email


@pytest.fixture()
def client(tmp_path):
    store = WaitlistStore(tmp_path / "waitlist.jsonl")
    app = create_landing_app(store=store)
    with TestClient(app) as test_client:
        yield test_client, store, tmp_path / "waitlist.jsonl"


def test_waitlist_join_persists_email_and_role(client):
    test_client, _, path = client
    response = test_client.post("/api/waitlist", json={"email": "  Dana@Lab.ORG ", "role": "research"})
    assert response.status_code == 201
    assert response.json() == {"status": "joined"}
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["email"] == "dana@lab.org"
    assert record["role"] == "research"
    assert record["joined_at"]


def test_waitlist_duplicate_is_idempotent(client):
    test_client, _, path = client
    assert test_client.post("/api/waitlist", json={"email": "a@b.io"}).status_code == 201
    second = test_client.post("/api/waitlist", json={"email": "A@B.IO"})
    assert second.status_code == 200
    assert second.json() == {"status": "already"}
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 1


@pytest.mark.parametrize(
    "bad_email",
    ["", "not-an-email", "a@b", "a@-b.com", "a b@c.com", "a@b..com", "x" * 300 + "@y.io"],
)
def test_waitlist_rejects_invalid_emails(client, bad_email):
    test_client, _, _ = client
    response = test_client.post("/api/waitlist", json={"email": bad_email})
    assert response.status_code == 422


def test_waitlist_honeypot_is_accepted_but_discarded(client):
    test_client, _, path = client
    response = test_client.post("/api/waitlist", json={"email": "bot@spam.test", "company": "ClickMe LLC"})
    assert response.status_code == 200
    assert response.json() == {"status": "discarded"}
    assert not path.exists()


def test_waitlist_rate_limited(client):
    test_client, _, _ = client
    statuses = [
        test_client.post("/api/waitlist", json={"email": f"user{i}@lab.org"}).status_code for i in range(8)
    ]
    assert statuses.count(429) >= 1
    assert statuses[-1] == 429


def test_waitlist_unknown_role_is_dropped(tmp_path):
    store = WaitlistStore(tmp_path / "waitlist.jsonl")
    assert store.join("ok@lab.org", "supervillain") == "joined"
    record = json.loads((tmp_path / "waitlist.jsonl").read_text(encoding="utf-8"))
    assert record["role"] == ""


def test_store_survives_reload(tmp_path):
    path = tmp_path / "waitlist.jsonl"
    WaitlistStore(path).join("keep@lab.org")
    reloaded = WaitlistStore(path)
    assert reloaded.join("keep@lab.org") == "already"
    assert reloaded.count == 1


def test_email_validation_helpers():
    assert is_valid_email(normalize_email("  U.T+tag@Sub.Example.COM "))
    assert not is_valid_email("a@b")
    assert not is_valid_email("@nope.io")


def test_form_encoded_fallback(client):
    test_client, store, _ = client
    ok = test_client.post(
        "/api/waitlist/form",
        data={"email": "dana@lab.org", "role": "graduate", "company": ""},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert ok.status_code == 200
    assert "on the list." in ok.text
    assert store.count == 1

    bad = test_client.post(
        "/api/waitlist/form",
        data={"email": "nope", "company": ""},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert bad.status_code == 422
    assert "look right" in bad.text


def test_health_and_static_serving(client):
    test_client, _, _ = client
    health = test_client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    page = test_client.get("/")
    assert page.status_code == 200
    assert "MaterialScope" in page.text
    assert page.headers["content-type"].startswith("text/html")

    css = test_client.get("/static/landing.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]

    traces = test_client.get("/static/traces.js")
    assert traces.status_code == 200
    assert "MS_TRACES" in traces.text


def test_page_structure_basics(client):
    test_client, _, _ = client
    html = test_client.get("/").text
    for required in (
        '<form id="waitlist-form"',
        'aria-live="polite"',
        'id="waitlist-email"',
        "prefers-reduced-motion",
    ):
        assert required in html or required in test_client.get("/static/landing.css").text, required
