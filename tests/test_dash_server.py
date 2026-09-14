from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from dash_app.server import create_combined_app
from synthetic_samples import sample_for

# Broader import→run→workspace/export/compare coverage lives in
# tests/test_dash_workflow_regression.py


def test_combined_dash_app_startup_and_sample_import_smoke():
    app = create_combined_app()

    sample_path, sample_type = sample_for("DSC")
    assert sample_type == "DSC"
    assert sample_path.exists()

    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    root = client.get("/")
    assert root.status_code == 200
    assert "MaterialScope" in root.text

    workspace = client.post("/workspace/new")
    assert workspace.status_code == 200
    project_id = workspace.json()["project_id"]

    payload = base64.b64encode(sample_path.read_bytes()).decode("ascii")
    imported = client.post(
        "/dataset/import",
        json={
            "project_id": project_id,
            "file_name": sample_path.name,
            "file_base64": payload,
            "data_type": sample_type,
        },
    )
    assert imported.status_code == 200
    assert imported.json()["dataset"]["data_type"] == sample_type
