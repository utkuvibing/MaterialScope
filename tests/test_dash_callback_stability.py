"""Real callback dispatch against one live event loop and its co-located API."""

import base64
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

import httpx
import pytest

from dash_app.sample_data import resolve_sample_request


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


def _invoke_registered(client, input_id, values):
    """Use the actual registered graph, including duplicate-output hashes."""
    dependencies = client.get("/_dash-dependencies").json()
    spec = next(item for item in dependencies if any(i["id"] == input_id for i in item["inputs"]))
    output = spec["output"]
    outputs = []
    for target in output.strip(".").split("..."):
        component, prop = target.split("@", 1)[0].rsplit(".", 1)
        outputs.append({"id": component, "property": prop})
    inputs = [(i["id"], i["property"], values.get(i["id"])) for i in spec["inputs"]]
    states = [(i["id"], i["property"], values.get(i["id"])) for i in spec["state"]]
    return _callback(client, output, inputs, states, outputs).json()["response"]


@pytest.mark.parametrize("modality", ["DSC", "TGA", "DTA", "FTIR", "RAMAN", "XRD"])
def test_confirm_import_creates_dataset_through_live_callback(live_dash, modality):
    project = live_dash.post("/workspace/new").json()["project_id"]
    path, _ = resolve_sample_request(f"load-sample-{modality.lower()}")
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
