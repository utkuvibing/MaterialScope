from __future__ import annotations

import base64
from pathlib import Path

import numpy as np
import pytest

from fastapi.testclient import TestClient

from backend.app import create_app
from core.library_cloud_client import reset_library_cloud_client


_LIBRARY_RUNTIME_ENV_KEYS = (
    "MATERIALSCOPE_LIBRARY_FEED_URL",
    "THERMOANALYZER_LIBRARY_FEED_URL",
    "MATERIALSCOPE_LIBRARY_MIRROR_ROOT",
    "THERMOANALYZER_LIBRARY_MIRROR_ROOT",
    "MATERIALSCOPE_LIBRARY_CLOUD_URL",
    "THERMOANALYZER_LIBRARY_CLOUD_URL",
    "MATERIALSCOPE_LIBRARY_CLOUD_ENABLED",
    "THERMOANALYZER_LIBRARY_CLOUD_ENABLED",
    "MATERIALSCOPE_LIBRARY_DEV_CLOUD_AUTH",
    "THERMOANALYZER_LIBRARY_DEV_CLOUD_AUTH",
    "MATERIALSCOPE_LIBRARY_HOSTED_ROOT",
    "THERMOANALYZER_LIBRARY_HOSTED_ROOT",
    "MATERIALSCOPE_LIBRARY_ALLOW_FULL_PROVIDER_SYNC",
    "THERMOANALYZER_LIBRARY_ALLOW_FULL_PROVIDER_SYNC",
    "MATERIALSCOPE_HOME",
    "THERMOANALYZER_HOME",
)


@pytest.fixture(autouse=True)
def _isolate_library_runtime_env(monkeypatch, tmp_path):
    for key in _LIBRARY_RUNTIME_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    home_root = tmp_path / "home"
    home_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MATERIALSCOPE_HOME", str(home_root))
    reset_library_cloud_client()
    yield
    reset_library_cloud_client()


def _headers() -> dict[str, str]:
    return {"X-MaterialScope-Token": "batch-token"}


def _as_b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _import_metadata(thermal_dataset) -> dict[str, object]:
    return {
        "sample_name": thermal_dataset.metadata.get("sample_name"),
        "sample_mass": thermal_dataset.metadata.get("sample_mass"),
        "heating_rate": thermal_dataset.metadata.get("heating_rate"),
        "instrument": thermal_dataset.metadata.get("instrument"),
    }


def _import_dataset(client: TestClient, project_id: str, thermal_dataset, file_name: str, data_type: str) -> str:
    csv_bytes = thermal_dataset.data.to_csv(index=False).encode("utf-8")
    imported = client.post(
        "/dataset/import",
        headers=_headers(),
        json={
            "project_id": project_id,
            "file_name": file_name,
            "file_base64": _as_b64(csv_bytes),
            "data_type": data_type,
            "metadata": _import_metadata(thermal_dataset),
        },
    )
    assert imported.status_code == 200
    return imported.json()["dataset"]["key"]


def test_batch_run_saves_results_for_compare_selected_datasets(thermal_dataset):
    app = create_app(api_token="batch-token")
    client = TestClient(app)
    project_id = client.post("/workspace/new", headers=_headers()).json()["project_id"]

    first = _import_dataset(client, project_id, thermal_dataset, "batch_a.csv", "DSC")
    second = _import_dataset(client, project_id, thermal_dataset, "batch_b.csv", "DSC")

    compare_set = client.post(
        f"/workspace/{project_id}/compare/selection",
        headers=_headers(),
        json={"operation": "replace", "dataset_keys": [first, second]},
    )
    assert compare_set.status_code == 200

    batch_run = client.post(
        f"/workspace/{project_id}/batch/run",
        headers=_headers(),
        json={"analysis_type": "DSC", "workflow_template_id": "dsc.general"},
    )
    assert batch_run.status_code == 200
    payload = batch_run.json()
    assert payload["analysis_type"] == "DSC"
    assert payload["outcomes"]["total"] == 2
    assert payload["outcomes"]["saved"] == 2
    assert payload["outcomes"]["blocked"] == 0
    assert payload["outcomes"]["failed"] == 0
    assert len(payload["saved_result_ids"]) == 2
    assert len(payload["batch_summary"]) == 2

    results = client.get(f"/workspace/{project_id}/results", headers=_headers())
    assert results.status_code == 200
    assert len(results.json()["results"]) == 2


def test_batch_run_blocks_incompatible_datasets_without_aborting(thermal_dataset):
    app = create_app(api_token="batch-token")
    client = TestClient(app)
    project_id = client.post("/workspace/new", headers=_headers()).json()["project_id"]

    dsc_key = _import_dataset(client, project_id, thermal_dataset, "batch_dsc.csv", "DSC")
    tga_key = _import_dataset(client, project_id, thermal_dataset, "batch_tga.csv", "TGA")

    compare_set = client.post(
        f"/workspace/{project_id}/compare/selection",
        headers=_headers(),
        json={"operation": "replace", "dataset_keys": [dsc_key, tga_key]},
    )
    assert compare_set.status_code == 200

    batch_run = client.post(
        f"/workspace/{project_id}/batch/run",
        headers=_headers(),
        json={"analysis_type": "DSC", "workflow_template_id": "dsc.general"},
    )
    assert batch_run.status_code == 200
    payload = batch_run.json()
    assert payload["outcomes"]["total"] == 2
    assert payload["outcomes"]["saved"] == 1
    assert payload["outcomes"]["blocked"] == 1
    assert payload["outcomes"]["failed"] == 0
    blocked = [row for row in payload["batch_summary"] if row["execution_status"] == "blocked"]
    assert blocked
    assert blocked[0]["dataset_key"] == tga_key


def test_batch_summary_persists_in_project_roundtrip(thermal_dataset):
    app = create_app(api_token="batch-token")
    client = TestClient(app)
    project_id = client.post("/workspace/new", headers=_headers()).json()["project_id"]

    first = _import_dataset(client, project_id, thermal_dataset, "persist_a.csv", "DSC")
    second = _import_dataset(client, project_id, thermal_dataset, "persist_b.csv", "DSC")
    client.post(
        f"/workspace/{project_id}/compare/selection",
        headers=_headers(),
        json={"operation": "replace", "dataset_keys": [first, second]},
    )

    batch_run = client.post(
        f"/workspace/{project_id}/batch/run",
        headers=_headers(),
        json={"analysis_type": "DSC", "workflow_template_id": "dsc.general"},
    )
    assert batch_run.status_code == 200
    run_payload = batch_run.json()
    assert run_payload["batch_run_id"]

    save_response = client.post(
        "/project/save",
        headers=_headers(),
        json={"project_id": project_id},
    )
    assert save_response.status_code == 200
    archive_base64 = save_response.json()["archive_base64"]

    load_response = client.post(
        "/project/load",
        headers=_headers(),
        json={"archive_base64": archive_base64},
    )
    assert load_response.status_code == 200
    loaded_project_id = load_response.json()["project_id"]

    compare_response = client.get(f"/workspace/{loaded_project_id}/compare", headers=_headers())
    assert compare_response.status_code == 200
    compare_payload = compare_response.json()["compare_workspace"]
    assert compare_payload["batch_run_id"] == run_payload["batch_run_id"]
    assert len(compare_payload["batch_summary"]) == 2
    assert len(compare_payload["batch_result_ids"]) == 2


def test_batch_run_ftir_similarity_path_returns_no_match_as_saved(thermal_dataset, monkeypatch):
    mirror_root = Path(__file__).resolve().parents[1] / "sample_data" / "reference_library_mirror"
    monkeypatch.setenv("MATERIALSCOPE_LIBRARY_MIRROR_ROOT", str(mirror_root))
    app = create_app(api_token="batch-token")
    client = TestClient(app)
    sync_response = client.post(
        "/library/sync",
        headers=_headers(),
        json={"force": True},
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["status"]["fallback_package_count"] >= 1
    project_id = client.post("/workspace/new", headers=_headers()).json()["project_id"]

    spectral_dataset = thermal_dataset.copy()
    axis = np.linspace(400.0, 2900.0, len(spectral_dataset.data))
    spectral_dataset.data["temperature"] = axis
    spectral_dataset.data["signal"] = -(
        np.exp(-0.5 * ((axis - 1200.0) / 120.0) ** 2)
        + 0.6 * np.exp(-0.5 * ((axis - 2000.0) / 150.0) ** 2)
    )

    ftir_key = _import_dataset(client, project_id, spectral_dataset, "batch_ftir.csv", "FTIR")
    compare_set = client.post(
        f"/workspace/{project_id}/compare/selection",
        headers=_headers(),
        json={"operation": "replace", "dataset_keys": [ftir_key]},
    )
    assert compare_set.status_code == 200

    batch_run = client.post(
        f"/workspace/{project_id}/batch/run",
        headers=_headers(),
        json={"analysis_type": "FTIR", "workflow_template_id": "ftir.general"},
    )
    assert batch_run.status_code == 200
    payload = batch_run.json()

    assert payload["analysis_type"] == "FTIR"
    assert payload["outcomes"]["total"] == 1
    assert payload["outcomes"]["saved"] == 1
    assert payload["outcomes"]["blocked"] == 0
    assert payload["outcomes"]["failed"] == 0
    assert len(payload["saved_result_ids"]) == 1
    assert len(payload["batch_summary"]) == 1
    assert payload["batch_summary"][0]["match_status"] == "no_match"
    assert payload["batch_summary"][0]["caution_code"] == "spectral_no_match"


def test_batch_run_xrd_preprocessing_path_returns_saved_with_peak_summary(thermal_dataset):
    app = create_app(api_token="batch-token")
    client = TestClient(app)
    project_id = client.post("/workspace/new", headers=_headers()).json()["project_id"]

    xrd_dataset = thermal_dataset.copy()
    axis = np.linspace(8.0, 88.0, len(xrd_dataset.data))
    signal = (
        18.0
        + 0.02 * axis
        + 70.0 * np.exp(-0.5 * ((axis - 21.2) / 0.35) ** 2)
        + 120.0 * np.exp(-0.5 * ((axis - 35.7) / 0.42) ** 2)
        + 85.0 * np.exp(-0.5 * ((axis - 52.4) / 0.38) ** 2)
    )
    xy_lines = ["# wavelength 1.5406", "2theta intensity"]
    xy_lines.extend(f"{theta:.4f} {intensity:.6f}" for theta, intensity in zip(axis, signal))
    imported = client.post(
        "/dataset/import",
        headers=_headers(),
        json={
            "project_id": project_id,
            "file_name": "batch_xrd.xy",
            "file_base64": _as_b64("\n".join(xy_lines).encode("utf-8")),
            "data_type": "XRD",
        },
    )
    assert imported.status_code == 200
    xrd_key = imported.json()["dataset"]["key"]
    compare_set = client.post(
        f"/workspace/{project_id}/compare/selection",
        headers=_headers(),
        json={"operation": "replace", "dataset_keys": [xrd_key]},
    )
    assert compare_set.status_code == 200

    batch_run = client.post(
        f"/workspace/{project_id}/batch/run",
        headers=_headers(),
        json={"analysis_type": "XRD", "workflow_template_id": "xrd.general"},
    )
    assert batch_run.status_code == 200
    payload = batch_run.json()

    assert payload["analysis_type"] == "XRD"
    assert payload["outcomes"]["total"] == 1
    assert payload["outcomes"]["saved"] == 1
    assert payload["outcomes"]["blocked"] == 0
    assert payload["outcomes"]["failed"] == 0
    assert len(payload["saved_result_ids"]) == 1
    assert len(payload["batch_summary"]) == 1
    assert payload["batch_summary"][0]["peak_count"] >= 1
    assert payload["batch_summary"][0]["match_status"] == "not_run"
