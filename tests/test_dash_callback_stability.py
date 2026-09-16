"""Real callback dispatch against one live event loop and its co-located API."""

import base64
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

import httpx
import pytest

from synthetic_samples import ensure_all_samples, sample_for


@pytest.fixture(scope="module")
def live_dash():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, MATERIALSCOPE_API_URL=f"http://127.0.0.1:{port}")
    script = """
import sys, uvicorn
from dash_app.server import create_combined_app
from dash_app import api_client
api_client._TIMEOUT = 1.0
app = create_combined_app()
uvicorn.run(app, host='127.0.0.1', port=int(sys.argv[1]), log_level='error')
"""
    process = subprocess.Popen([sys.executable, "-c", script, str(port)], env=env)
    try:
        with httpx.Client(base_url=env["MATERIALSCOPE_API_URL"], timeout=5, trust_env=False) as client:
            for _ in range(100):
                try:
                    if client.get("/health").is_success:
                        break
                except httpx.TransportError:
                    pass
                assert process.poll() is None, "Dash server exited during startup"
                time.sleep(0.1)
            else:
                pytest.fail("Dash server did not start")
            client.get("/_dash-layout").raise_for_status()
            yield client
    finally:
        process.terminate()
        process.wait(timeout=10)


def _callback(client, output, inputs, states=(), outputs=None):
    response = client.post("/_dash-update-component", json={
        "output": output,
        "outputs": outputs or {"id": output.split(".")[0], "property": output.split(".")[1]},
        "inputs": [{"id": key, "property": prop, "value": value} for key, prop, value in inputs],
        "state": [{"id": key, "property": prop, "value": value} for key, prop, value in states],
        "changedPropIds": [f"{inputs[0][0]}.{inputs[0][1]}"],
    })
    response.raise_for_status()
    return response


def test_workspace_hydration_and_stale_session_recovery(live_dash):
    for current in (None, "workspace-from-previous-server"):
        response = _callback(live_dash, "project-id.data", [("project-id", "data", current)])
        project_id = response.json()["response"]["project-id"]["data"]
        assert project_id, "Hydration returned HTTP 200 but failed to create a workspace"
        assert live_dash.get(f"/workspace/{project_id}").json()["project_id"] == project_id
        unchanged = _callback(live_dash, "project-id.data", [("project-id", "data", project_id)])
        assert unchanged.status_code == 204 or unchanged.json()["response"] == {}, unchanged.text


def _spec(client, *, input_id=None, output_contains=None):
    """Find a registered callback spec by input component and/or output fragment."""
    for item in client.get("/_dash-dependencies").json():
        if input_id and not any(i["id"] == input_id for i in item["inputs"]):
            continue
        if output_contains and output_contains not in item["output"]:
            continue
        return item
    raise AssertionError(f"callback spec not found: input={input_id} output~{output_contains}")


def _invoke_spec(client, spec, values):
    """Invoke one registered callback spec the way the renderer would."""
    output = spec["output"]
    outputs = []
    for target in output.strip(".").split("..."):
        component, prop = target.split("@", 1)[0].rsplit(".", 1)
        outputs.append({"id": component, "property": prop})
    # The renderer sends `outputs` as an object for single-output callbacks.
    outputs_payload = outputs[0] if len(outputs) == 1 else outputs
    inputs = [(i["id"], i["property"], values.get(i["id"])) for i in spec["inputs"]]
    states = [(i["id"], i["property"], values.get(i["id"])) for i in spec["state"]]
    response = _callback(client, output, inputs, states, outputs_payload)
    if response.status_code == 204:  # PreventUpdate
        return {}
    return response.json()["response"]


def _invoke_registered(client, input_id, values):
    """Use the actual registered graph, including duplicate-output hashes."""
    return _invoke_spec(client, _spec(client, input_id=input_id), values)


@pytest.mark.parametrize("modality", ["DSC", "TGA", "DTA", "FTIR", "RAMAN", "XRD"])
def test_confirm_import_creates_dataset_through_live_callback(live_dash, modality):
    project = live_dash.post("/workspace/new").json()["project_id"]
    path, _ = sample_for(modality)
    pending = [{"file_name": path.name, "file_base64": base64.b64encode(path.read_bytes()).decode("ascii")}]
    values = {
        "project-id": project, "ui-locale": "en", "home-refresh": 0,
        "pending-file-select": path.name, "pending-upload-files": pending,
        "import-selected-modality": modality, "import-mapped-btn": 1,
    }
    preview = _invoke_registered(live_dash, "pending-file-select", values)
    values.update({key: item.get("value", item.get("data")) for key, item in preview.items()})
    result = _invoke_registered(live_dash, "import-mapped-btn", values)
    assert result.get("home-refresh", {}).get("data") == 1, result
    assert result["import-wizard-step"]["data"] == 0
    assert result["pending-upload-files"]["data"] == []
    datasets = live_dash.get(f"/workspace/{project}/datasets").json()["datasets"]
    assert len(datasets) == 1
    assert datasets[0]["data_type"] == modality
    assert datasets[0]["key"]


@pytest.mark.parametrize("missing", ["project-id", "pending-import-preview"])
def test_confirm_prerequisite_error_is_visible_on_final_step(live_dash, missing):
    values = {"ui-locale": "en", "import-mapped-btn": 1, "project-id": "unused", "pending-import-preview": {"columns": []}}
    values[missing] = None
    result = _invoke_registered(live_dash, "import-mapped-btn", values)
    assert result.get("validation-summary-status", {}).get("children"), result


def _import_via_api(client, project_id, modality, file_name=None):
    """Seed a dataset through the real import endpoint (what the wizard calls)."""
    path, data_type = sample_for(modality)
    response = client.post(
        "/dataset/import",
        json={
            "project_id": project_id,
            "file_name": file_name or path.name,
            "file_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
            "data_type": data_type,
        },
    )
    response.raise_for_status()
    return response.json()["dataset"]["key"]


def _remove_values(project_id, dataset_key, *, clicks=1, refresh=0):
    """State the browser holds when Remove is clicked on the Loaded Datasets panel."""
    return {
        "project-id": project_id,
        "ui-locale": "en",
        "home-refresh": refresh,
        "active-dataset-select": dataset_key,
        "remove-dataset-btn": clicks,
    }


def _invoke_remove(client, project_id, dataset_key, *, clicks=1, refresh=0):
    """Click Remove once: dispatch the registered remove_dataset callback."""
    spec = _spec(client, input_id="remove-dataset-btn", output_contains="dataset-action-status")
    return _invoke_spec(client, spec, _remove_values(project_id, dataset_key, clicks=clicks, refresh=refresh))


def _loaded_datasets_view(client, project_id, refresh):
    """Dispatch load_workspace_datasets the way the renderer does after home-refresh bumps."""
    spec = _spec(client, output_contains="datasets-table.children")
    values = {"project-id": project_id, "home-refresh": refresh, "ui-theme": "light", "ui-locale": "en"}
    return _invoke_spec(client, spec, values)


def _detail_panel(client, project_id, dataset_key, refresh):
    spec = _spec(client, output_contains="dataset-detail-panel.children")
    values = {
        "project-id": project_id,
        "active-dataset-select": dataset_key,
        "home-refresh": refresh,
        "ui-theme": "light",
        "ui-locale": "en",
    }
    return _invoke_spec(client, spec, values)


def test_remove_dataset_single_click_refreshes_workspace(live_dash):
    """Manual-QA regression: one Remove click must delete AND refresh — no stale UI."""
    project = live_dash.post("/workspace/new").json()["project_id"]
    key = _import_via_api(live_dash, project, "DSC")

    # First click: success alert + home-refresh bump. Pre-fix this POST 500'd
    # (TypeError on the {key} placeholder) after the delete already committed,
    # leaving the stale row on screen until a browser reload.
    result = _invoke_remove(live_dash, project, key)
    assert result["home-refresh"]["data"] == 1, result
    assert "Removed dataset" in json.dumps(result["dataset-action-status"]["children"])

    payload = live_dash.get(f"/workspace/{project}/datasets").json()
    assert payload["datasets"] == []
    assert payload["active_dataset"] is None

    # The refresh the bumped store triggers must empty the table, options and select.
    view = _loaded_datasets_view(live_dash, project, result["home-refresh"]["data"])
    assert view["active-dataset-select"]["options"] == []
    assert view["active-dataset-select"]["value"] is None
    assert key not in json.dumps(view["datasets-table"]["children"])
    assert key not in json.dumps(view["import-metrics"]["children"])

    # The detail panel follows the cleared selection to the empty state.
    detail = _detail_panel(live_dash, project, None, result["home-refresh"]["data"])
    assert key not in json.dumps(detail["dataset-detail-panel"]["children"])


def test_remove_active_dataset_clears_selection_with_multiple_datasets(live_dash):
    """Removing the active dataset must deterministically clear the active selection."""
    project = live_dash.post("/workspace/new").json()["project_id"]
    first = _import_via_api(live_dash, project, "DSC")
    second = _import_via_api(live_dash, project, "DSC")
    assert live_dash.get(f"/workspace/{project}/datasets").json()["active_dataset"] == second

    result = _invoke_remove(live_dash, project, second)
    assert result["home-refresh"]["data"] == 1, result

    payload = live_dash.get(f"/workspace/{project}/datasets").json()
    assert [item["key"] for item in payload["datasets"]] == [first]
    assert payload["active_dataset"] is None

    view = _loaded_datasets_view(live_dash, project, result["home-refresh"]["data"])
    assert [opt["value"] for opt in view["active-dataset-select"]["options"]] == [first]
    assert view["active-dataset-select"]["value"] is None
    assert second not in json.dumps(view["datasets-table"]["children"])
    assert first in json.dumps(view["datasets-table"]["children"])


def test_remove_non_active_dataset_preserves_active(live_dash):
    """A removal aimed at a non-active key must not disturb the active dataset."""
    project = live_dash.post("/workspace/new").json()["project_id"]
    first = _import_via_api(live_dash, project, "DSC")
    second = _import_via_api(live_dash, project, "DSC")
    assert live_dash.get(f"/workspace/{project}/datasets").json()["active_dataset"] == second

    result = _invoke_remove(live_dash, project, first)
    assert result["home-refresh"]["data"] == 1, result

    payload = live_dash.get(f"/workspace/{project}/datasets").json()
    assert [item["key"] for item in payload["datasets"]] == [second]
    assert payload["active_dataset"] == second

    view = _loaded_datasets_view(live_dash, project, result["home-refresh"]["data"])
    assert view["active-dataset-select"]["value"] == second
    assert [opt["value"] for opt in view["active-dataset-select"]["options"]] == [second]


def test_remove_dataset_stale_second_click_fails_without_corrupting_state(live_dash):
    """A repeated Remove against a stale selection shows an error but changes nothing."""
    project = live_dash.post("/workspace/new").json()["project_id"]
    key = _import_via_api(live_dash, project, "DSC")
    first = _invoke_remove(live_dash, project, key)
    assert first["home-refresh"]["data"] == 1

    # The second click the QA flow needed: with the fix the select clears so this
    # cannot fire against the stale key — but if it ever does (double dispatch),
    # it must surface the failure alert without touching home-refresh.
    second = _invoke_remove(live_dash, project, key, clicks=2, refresh=first["home-refresh"]["data"])
    assert "Remove failed" in json.dumps(second["dataset-action-status"]["children"])
    assert "home-refresh" not in second, second

    view = _loaded_datasets_view(live_dash, project, 1)
    assert view["active-dataset-select"]["options"] == []
    assert view["active-dataset-select"]["value"] is None

    # The renderer prevents this outright: no selection -> the callback does not run.
    blocked = _invoke_remove(live_dash, project, None, clicks=3, refresh=1)
    assert blocked == {}, blocked


def test_workspace_transport_failure_preserves_session_and_logs(monkeypatch, caplog):
    import dash
    from dash_app import api_client
    from dash_app.layout import ensure_project

    def unavailable(_project):
        raise httpx.ReadTimeout("backend unavailable")

    def must_not_replace():
        pytest.fail("A transient API failure must not replace the user's workspace")

    monkeypatch.setattr(api_client, "workspace_summary", unavailable)
    monkeypatch.setattr(api_client, "workspace_new", must_not_replace)
    assert ensure_project("existing-project") is dash.no_update
    assert "Workspace validation failed" in caplog.text


@pytest.mark.skipif(os.environ.get("MATERIALSCOPE_RUN_BROWSER_TESTS") != "1", reason="Opt-in Playwright browser check")
def test_browser_navigation_and_confirm_import(live_dash):
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        pytest.skip("npx is required for Playwright CLI")
    session = f"stability-{os.getpid()}"
    command = [npx, "--yes", "--package", "@playwright/cli", "playwright-cli", f"-s={session}"]
    root = Path(__file__).resolve().parents[1]
    ensure_all_samples()

    def run(*args):
        result = subprocess.run(command + list(args), cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "### Error" not in result.stdout, result.stdout
        return result.stdout

    try:
        run("open", str(live_dash.base_url))
        output = run("run-code", "--filename", "tests/dash_stability_browser.js")
        assert '"idleCallbacks":0' in output, output
    finally:
        subprocess.run(command + ["close"], cwd=root, capture_output=True, timeout=30)
