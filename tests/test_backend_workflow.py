from __future__ import annotations

import base64
import io

from fastapi.testclient import TestClient

from backend.app import create_app
from core.project_io import load_project_archive


def _headers() -> dict[str, str]:
    return {"X-TA-Token": "workflow-token"}


def _to_base64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def test_workspace_import_run_analysis_and_save_roundtrip(thermal_dataset):
    app = create_app(api_token="workflow-token")
    client = TestClient(app)

    create_response = client.post("/workspace/new", headers=_headers())
    assert create_response.status_code == 200
    project_id = create_response.json()["project_id"]

    csv_bytes = thermal_dataset.data.to_csv(index=False).encode("utf-8")
    import_response = client.post(
        "/dataset/import",
        headers=_headers(),
        json={
            "project_id": project_id,
            "file_name": "synthetic_dsc.csv",
            "file_base64": _to_base64(csv_bytes),
            "data_type": "DSC",
        },
    )
    assert import_response.status_code == 200
    imported = import_response.json()
    dataset_key = imported["dataset"]["key"]
    assert imported["summary"]["dataset_count"] == 1
    assert imported["dataset"]["data_type"] == "DSC"

    datasets_response = client.get(f"/workspace/{project_id}/datasets", headers=_headers())
    assert datasets_response.status_code == 200
    datasets = datasets_response.json()["datasets"]
    assert len(datasets) == 1
    assert datasets[0]["key"] == dataset_key

    run_response = client.post(
        "/analysis/run",
        headers=_headers(),
        json={
            "project_id": project_id,
            "dataset_key": dataset_key,
            "analysis_type": "DSC",
            "workflow_template_id": "dsc.general",
        },
    )
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["execution_status"] == "saved"
    assert run_payload["result_id"].startswith("dsc_")

    results_response = client.get(f"/workspace/{project_id}/results", headers=_headers())
    assert results_response.status_code == 200
    results = results_response.json()["results"]
    assert len(results) == 1
    assert results[0]["id"] == run_payload["result_id"]
    assert results[0]["analysis_type"] == "DSC"

    save_response = client.post(
        "/project/save",
        headers=_headers(),
        json={"project_id": project_id},
    )
    assert save_response.status_code == 200
    archive_base64 = save_response.json()["archive_base64"]
    restored = load_project_archive(io.BytesIO(base64.b64decode(archive_base64.encode("ascii"))))
    assert dataset_key in restored["datasets"]
    assert run_payload["result_id"] in restored["results"]
