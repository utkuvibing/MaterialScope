from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from backend.app import create_app


def _headers() -> dict[str, str]:
    return {"X-MaterialScope-Token": "workspace-token"}


def _as_b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _import_dataset(client: TestClient, project_id: str, thermal_dataset, file_name: str) -> str:
    csv_bytes = thermal_dataset.data.to_csv(index=False).encode("utf-8")
    imported = client.post(
        "/dataset/import",
        headers=_headers(),
        json={
            "project_id": project_id,
            "file_name": file_name,
            "file_base64": _as_b64(csv_bytes),
            "data_type": "DSC",
        },
    )
    assert imported.status_code == 200
    return imported.json()["dataset"]["key"]


def test_workspace_context_and_active_dataset_update(thermal_dataset):
    app = create_app(api_token="workspace-token")
    client = TestClient(app)
    project_id = client.post("/workspace/new", headers=_headers()).json()["project_id"]

    first_key = _import_dataset(client, project_id, thermal_dataset, "first.csv")
    second_key = _import_dataset(client, project_id, thermal_dataset, "second.csv")

    context = client.get(f"/workspace/{project_id}/context", headers=_headers())
    assert context.status_code == 200
    body = context.json()
    assert body["active_dataset_key"] == second_key
    assert body["active_dataset"]["key"] == second_key
    assert "compare_workspace" in body
    assert "recent_history" in body

    set_active = client.put(
        f"/workspace/{project_id}/active-dataset",
        headers=_headers(),
        json={"dataset_key": first_key},
    )
    assert set_active.status_code == 200
    assert set_active.json()["active_dataset_key"] == first_key

    refreshed = client.get(f"/workspace/{project_id}/context", headers=_headers())
    assert refreshed.status_code == 200
    refreshed_body = refreshed.json()
    assert refreshed_body["active_dataset_key"] == first_key
    assert refreshed_body["active_dataset"]["key"] == first_key


def test_compare_selection_roundtrip_survives_save_load(thermal_dataset):
    app = create_app(api_token="workspace-token")
    client = TestClient(app)
    project_id = client.post("/workspace/new", headers=_headers()).json()["project_id"]

    first_key = _import_dataset(client, project_id, thermal_dataset, "cmp_first.csv")
    second_key = _import_dataset(client, project_id, thermal_dataset, "cmp_second.csv")

    replace_response = client.post(
        f"/workspace/{project_id}/compare/selection",
        headers=_headers(),
        json={"operation": "replace", "dataset_keys": [first_key, second_key]},
    )
    assert replace_response.status_code == 200
    compare_payload = replace_response.json()["compare_workspace"]
    assert compare_payload["selected_datasets"] == [first_key, second_key]

    compare_notes = client.put(
        f"/workspace/{project_id}/compare",
        headers=_headers(),
        json={
            "analysis_type": "DSC",
            "selected_datasets": [first_key, second_key],
            "notes": "Workspace compare persistence check",
        },
    )
    assert compare_notes.status_code == 200

    saved = client.post(
        "/project/save",
        headers=_headers(),
        json={"project_id": project_id},
    )
    assert saved.status_code == 200
    archive_base64 = saved.json()["archive_base64"]

    loaded = client.post(
        "/project/load",
        headers=_headers(),
        json={"archive_base64": archive_base64},
    )
    assert loaded.status_code == 200
    loaded_project_id = loaded.json()["project_id"]

    loaded_compare = client.get(f"/workspace/{loaded_project_id}/compare", headers=_headers())
    assert loaded_compare.status_code == 200
    loaded_payload = loaded_compare.json()["compare_workspace"]
    assert loaded_payload["selected_datasets"] == [first_key, second_key]
    assert loaded_payload["notes"] == "Workspace compare persistence check"


def test_compare_selection_and_active_dataset_validation(thermal_dataset):
    app = create_app(api_token="workspace-token")
    client = TestClient(app)
    project_id = client.post("/workspace/new", headers=_headers()).json()["project_id"]
    _import_dataset(client, project_id, thermal_dataset, "validation_seed.csv")

    invalid_op = client.post(
        f"/workspace/{project_id}/compare/selection",
        headers=_headers(),
        json={"operation": "invalid"},
    )
    assert invalid_op.status_code == 400
    assert "operation must be one of" in invalid_op.json()["detail"]

    unknown_active = client.put(
        f"/workspace/{project_id}/active-dataset",
        headers=_headers(),
        json={"dataset_key": "missing_dataset"},
    )
    assert unknown_active.status_code == 404
    assert "Unknown dataset_key" in unknown_active.json()["detail"]


def test_compare_workspace_academic_fields_roundtrip_and_candidate_endpoint(thermal_dataset):
    app = create_app(api_token="workspace-token")
    client = TestClient(app)
    project_id = client.post("/workspace/new", headers=_headers()).json()["project_id"]

    dataset_key = _import_dataset(client, project_id, thermal_dataset, "A1_1050.csv")

    update = client.put(
        f"/workspace/{project_id}/compare",
        headers=_headers(),
        json={
            "analysis_type": "DSC",
            "selected_datasets": [dataset_key],
            "compare_display_mode": "academic",
            "compare_group_mode": "sample_series",
            "series_filter": "A",
            "temperature_filter_value": 1050,
            "temperature_filter_unit": "°C",
            "material_type_filter": "ceramic",
            "tag_filters": ["sintered"],
            "composition_filter": "Al2O3",
            "label_template": "{sample_id} at {temperature}",
            "signal_mode": "raw",
            "normalize_mode": "max",
            "offset_mode": "stacked",
            "reverse_x_axis": True,
            "smoothing_enabled": False,
            "notes": "academic compare",
        },
    )
    assert update.status_code == 200
    payload = update.json()["compare_workspace"]
    assert payload["compare_display_mode"] == "academic"
    assert payload["compare_group_mode"] == "sample_series"
    assert payload["series_filter"] == "A"
    assert payload["temperature_filter_value"] == 1050
    assert payload["tag_filters"] == ["sintered"]
    assert payload["signal_mode"] == "raw"
    assert payload["normalize_mode"] == "max"
    assert payload["offset_mode"] == "stacked"
    assert payload["reverse_x_axis"] is True
    assert payload["smoothing_enabled"] is False

    candidates = client.get(
        f"/workspace/{project_id}/compare/candidates",
        headers=_headers(),
        params={"analysis_type": "DSC"},
    )
    assert candidates.status_code == 200
    body = candidates.json()
    assert body["analysis_type"] == "DSC"
    assert len(body["candidates"]) == 1
    candidate = body["candidates"][0]
    assert candidate["dataset_key"] == dataset_key
    assert candidate["sample_id"] == "A1_1050"
    assert candidate["sample_name"]
    assert candidate["data_type"] == "DSC"

    saved = client.post("/project/save", headers=_headers(), json={"project_id": project_id})
    loaded = client.post("/project/load", headers=_headers(), json={"archive_base64": saved.json()["archive_base64"]})
    loaded_project_id = loaded.json()["project_id"]
    loaded_payload = client.get(f"/workspace/{loaded_project_id}/compare", headers=_headers()).json()["compare_workspace"]
    assert loaded_payload["compare_display_mode"] == "academic"
    assert loaded_payload["label_template"] == "{sample_id} at {temperature}"
    assert loaded_payload["selected_datasets"] == [dataset_key]
