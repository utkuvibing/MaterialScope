"""GET /workspace/{pid}/results/{rid}/figure — authorized PNG fetch for previews (Slice 5–6)."""

from __future__ import annotations

import base64
import io

import pytest
from fastapi.testclient import TestClient

from dash_app.sample_data import resolve_sample_request
from dash_app.server import create_combined_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_combined_app())


def test_get_result_figure_png_returns_bytes_after_register(client: TestClient):
    project_id = client.post("/workspace/new").json()["project_id"]
    sample_path, _ = resolve_sample_request("load-sample-dsc")
    payload = base64.b64encode(sample_path.read_bytes()).decode("ascii")
    imported = client.post(
        "/dataset/import",
        json={
            "project_id": project_id,
            "file_name": sample_path.name,
            "file_base64": payload,
            "data_type": "DTA",
        },
    )
    assert imported.status_code == 200
    dataset_key = imported.json()["dataset"]["key"]
    run = client.post(
        "/analysis/run",
        json={
            "project_id": project_id,
            "dataset_key": dataset_key,
            "analysis_type": "DTA",
            "workflow_template_id": "dta.general",
        },
    )
    assert run.status_code == 200
    result_id = run.json()["result_id"]
    label = f"DTA Analysis - {dataset_key}"
    png = b"\x89PNG\r\n\x1a\nTEST-GET-BYTES"
    reg = client.post(
        f"/workspace/{project_id}/results/{result_id}/figure",
        json={
            "figure_png_base64": base64.b64encode(png).decode("ascii"),
            "figure_label": label,
            "replace": True,
        },
    )
    assert reg.status_code == 200

    got = client.get(
        f"/workspace/{project_id}/results/{result_id}/figure",
        params={"figure_key": label},
    )
    assert got.status_code == 200, got.text
    assert got.headers.get("content-type", "").startswith("image/png")
    assert got.content == png


def test_get_result_figure_png_downscales_with_max_edge(client: TestClient):
    from PIL import Image

    project_id = client.post("/workspace/new").json()["project_id"]
    sample_path, _ = resolve_sample_request("load-sample-dsc")
    payload = base64.b64encode(sample_path.read_bytes()).decode("ascii")
    imported = client.post(
        "/dataset/import",
        json={
            "project_id": project_id,
            "file_name": sample_path.name,
            "file_base64": payload,
            "data_type": "DTA",
        },
    )
    assert imported.status_code == 200
    dataset_key = imported.json()["dataset"]["key"]
    run = client.post(
        "/analysis/run",
        json={
            "project_id": project_id,
            "dataset_key": dataset_key,
            "analysis_type": "DTA",
            "workflow_template_id": "dta.general",
        },
    )
    assert run.status_code == 200
    result_id = run.json()["result_id"]
    label = "large-preview-figure"
    buf = io.BytesIO()
    Image.new("RGB", (400, 100), color=(10, 20, 30)).save(buf, format="PNG")
    large_png = buf.getvalue()
    reg = client.post(
        f"/workspace/{project_id}/results/{result_id}/figure",
        json={
            "figure_png_base64": base64.b64encode(large_png).decode("ascii"),
            "figure_label": label,
            "replace": True,
        },
    )
    assert reg.status_code == 200

    full = client.get(
        f"/workspace/{project_id}/results/{result_id}/figure",
        params={"figure_key": label},
    )
    assert full.status_code == 200
    thumb = client.get(
        f"/workspace/{project_id}/results/{result_id}/figure",
        params={"figure_key": label, "max_edge": 80},
    )
    assert thumb.status_code == 200, thumb.text
    assert thumb.headers.get("content-type", "").startswith("image/png")
    assert len(thumb.content) < len(full.content)

    im_thumb = Image.open(io.BytesIO(thumb.content))
    im_thumb.load()
    assert max(im_thumb.size) <= 80


def test_get_result_figure_png_rejects_unknown_key(client: TestClient):
    project_id = client.post("/workspace/new").json()["project_id"]
    sample_path, _ = resolve_sample_request("load-sample-dsc")
    payload = base64.b64encode(sample_path.read_bytes()).decode("ascii")
    imported = client.post(
        "/dataset/import",
        json={
            "project_id": project_id,
            "file_name": sample_path.name,
            "file_base64": payload,
            "data_type": "DTA",
        },
    )
    dataset_key = imported.json()["dataset"]["key"]
    run = client.post(
        "/analysis/run",
        json={
            "project_id": project_id,
            "dataset_key": dataset_key,
            "analysis_type": "DTA",
            "workflow_template_id": "dta.general",
        },
    )
    result_id = run.json()["result_id"]
    bad = client.get(
        f"/workspace/{project_id}/results/{result_id}/figure",
        params={"figure_key": "not-a-registered-label"},
    )
    assert bad.status_code == 404
