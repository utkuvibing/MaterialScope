"""Opt-in live checks for the preview Peak Deconvolution Dash page.

Two layers, both against the real combined Dash/FastAPI server started with
``MATERIALSCOPE_ENABLE_PREVIEW_MODULES=1``:

1. ``test_deconvolution_run_callback_dispatch_*`` dispatch the registered
   ``run_deconvolution`` callback through ``/_dash-update-component`` — the
   same transport the browser uses — and verify the workspace result persists.
2. ``test_deconvolution_page_real_browser_*`` drive a real browser via
   ``playwright-cli run-code`` and verify the required acceptance flows:
   a thermal fit on a processed basis (plus hydration after a hard reload) and
   a non-temperature axis whose labels never claim °C.

Set ``MATERIALSCOPE_RUN_BROWSER_TESTS=1`` to enable the browser portion.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = REPO_ROOT / "pytest_temp" / "deconvolution_browser"


@pytest.fixture(scope="module")
def live_dash_preview():
    """Combined server on a free port with the preview flag enabled."""
    import httpx

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(
        os.environ,
        MATERIALSCOPE_API_URL=f"http://127.0.0.1:{port}",
        MATERIALSCOPE_ENABLE_PREVIEW_MODULES="1",
    )
    script = """
import sys, uvicorn
from dash_app.server import create_combined_app
app = create_combined_app()
uvicorn.run(app, host='127.0.0.1', port=int(sys.argv[1]), log_level='error')
"""
    process = subprocess.Popen([sys.executable, "-c", script, str(port)], env=env)
    try:
        with httpx.Client(base_url=env["MATERIALSCOPE_API_URL"], timeout=5, trust_env=False) as client:
            for _ in range(150):
                try:
                    if client.get("/health").is_success:
                        break
                except httpx.TransportError:
                    pass
                assert process.poll() is None, "Preview Dash server exited during startup"
                time.sleep(0.1)
            else:
                pytest.fail("Preview Dash server did not start")
            client.get("/_dash-layout").raise_for_status()
            yield client
    finally:
        process.terminate()
        process.wait(timeout=10)


def _write_csv(name: str, frame: pd.DataFrame) -> Path:
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORK_ROOT / name
    path.write_text(frame.to_csv(index=False), encoding="utf-8")
    return path


def _thermal_csv(name: str) -> Path:
    """Deterministic DSC-like CSV with two overlapping peaks."""
    temperature = np.linspace(50.0, 250.0, 400)
    signal = 2.0 * np.exp(-0.5 * ((temperature - 120.0) / 8.0) ** 2) + 1.5 * np.exp(
        -0.5 * ((temperature - 170.0) / 10.0) ** 2
    )
    return _write_csv(
        name,
        pd.DataFrame({"temperature": np.round(temperature, 4), "signal": np.round(signal, 6)}),
    )


def _spectral_csv(name: str) -> Path:
    """Deterministic FTIR-like CSV (wavenumber cm^-1 / absorbance)."""
    wavenumber = np.linspace(4000.0, 400.0, 400)
    signal = 1.0 * np.exp(-0.5 * ((wavenumber - 1700.0) / 30.0) ** 2) + 0.6 * np.exp(
        -0.5 * ((wavenumber - 1600.0) / 25.0) ** 2
    )
    return _write_csv(
        name,
        pd.DataFrame(
            {
                "Wavenumber (cm-1)": np.round(wavenumber, 4),
                "Absorbance": np.round(signal, 6),
            }
        ),
    )


def _import_dataset(client, project_id: str, path: Path, data_type: str) -> str:
    response = client.post(
        "/dataset/import",
        json={
            "project_id": project_id,
            "file_name": path.name,
            "file_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
            "data_type": data_type,
        },
    )
    response.raise_for_status()
    return response.json()["dataset"]["key"]


def _run_stable_dsc_analysis(client, project_id: str, dataset_key: str) -> None:
    response = client.post(
        "/analysis/run",
        json={"project_id": project_id, "dataset_key": dataset_key, "analysis_type": "DSC"},
    )
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Live callback dispatch (browser transport)
# ---------------------------------------------------------------------------


def _dispatch_run_deconvolution(client, project_id: str, dataset_key: str, basis: str):
    spec = next(
        item
        for item in client.get("/_dash-dependencies").json()
        if "deconvolution-run-status" in item["output"]
    )
    center_wildcard = json.dumps(
        {"index": ["ALL"], "type": "deconvolution-guess-center"}, separators=(",", ":")
    )
    amplitude_wildcard = json.dumps(
        {"index": ["ALL"], "type": "deconvolution-guess-amplitude"}, separators=(",", ":")
    )
    sigma_wildcard = json.dumps(
        {"index": ["ALL"], "type": "deconvolution-guess-sigma"}, separators=(",", ":")
    )
    center_ids = [
        {"type": "deconvolution-guess-center", "index": 0},
        {"type": "deconvolution-guess-center", "index": 1},
    ]
    amplitude_ids = [
        {"type": "deconvolution-guess-amplitude", "index": 0},
        {"type": "deconvolution-guess-amplitude", "index": 1},
    ]
    sigma_ids = [
        {"type": "deconvolution-guess-sigma", "index": 0},
        {"type": "deconvolution-guess-sigma", "index": 1},
    ]

    states: list[dict] = []
    for item in spec["state"]:
        cid = item["id"]
        prop = item["property"]
        if cid == "project-id":
            value = project_id
        elif cid == "deconvolution-dataset-select":
            value = dataset_key
        elif cid == "deconvolution-basis-select":
            value = basis
        elif cid == "deconvolution-n-peaks":
            value = 2
        elif cid == "deconvolution-peak-shape":
            value = "gaussian"
        elif cid == "deconvolution-use-range":
            value = []
        elif cid == "deconvolution-range-min":
            value = None
        elif cid == "deconvolution-range-max":
            value = None
        elif cid == "deconvolution-invert":
            value = []
        elif cid == "deconvolution-use-guesses":
            value = ["on"]
        elif cid in {center_wildcard, amplitude_wildcard, sigma_wildcard}:
            if prop == "id":
                value = {
                    center_wildcard: center_ids,
                    amplitude_wildcard: amplitude_ids,
                    sigma_wildcard: sigma_ids,
                }[cid]
            elif cid == center_wildcard:
                value = [120.0, 170.0]
            elif cid == amplitude_wildcard:
                value = [2.0, 1.5]
            else:
                value = [8.0, 10.0]
        elif cid in {"deconvolution-refresh", "workspace-refresh"}:
            value = 0
        elif cid == "ui-locale":
            value = "en"
        else:
            value = None
        states.append({"id": cid, "property": prop, "value": value})

    response = client.post(
        "/_dash-update-component",
        json={
            "output": spec["output"],
            "outputs": [
                {
                    "id": t.split("@", 1)[0].rsplit(".", 1)[0],
                    "property": t.split("@", 1)[0].rsplit(".", 1)[1],
                }
                for t in spec["output"].strip(".").split("...")
            ],
            "inputs": [{"id": "deconvolution-run-btn", "property": "n_clicks", "value": 1}],
            "state": states,
            "changedPropIds": ["deconvolution-run-btn.n_clicks"],
        },
    )
    response.raise_for_status()
    return response.json()


def test_deconvolution_run_callback_dispatch_saves_workspace_result(live_dash_preview):
    """Live callback dispatch: browser transport -> backend endpoint -> saved result."""
    client = live_dash_preview
    project_id = client.post("/workspace/new").json()["project_id"]
    dataset_key = _import_dataset(client, project_id, _thermal_csv("dispatch_dsc.csv"), "DSC")

    body = _dispatch_run_deconvolution(client, project_id, dataset_key, "raw")
    response = body.get("response") or {}

    status_children = json.dumps(response.get("deconvolution-run-status", {}))
    assert "saved" in status_children.lower(), status_children
    result_id = (response.get("deconvolution-latest-result-id") or {}).get("data")
    assert result_id, response

    results = client.get(f"/workspace/{project_id}/results").json()
    assert result_id in [item["id"] for item in results.get("results", [])]

    detail = client.get(f"/workspace/{project_id}/results/{result_id}").json()
    assert detail["provenance"]["analysis_scope"] == "preview_deconvolution"
    assert detail["processing"]["signal_basis"] == "raw"
    assert len(detail["rows"]) == 2
    assert detail["report_payload"]["components"]
    assert detail["summary"]["amplitude_semantics"] == "integrated_area_parameter"


def test_deconvolution_dispatch_blocks_missing_basis(live_dash_preview):
    """An unavailable basis is refused through the live transport too."""
    client = live_dash_preview
    project_id = client.post("/workspace/new").json()["project_id"]
    dataset_key = _import_dataset(client, project_id, _thermal_csv("dispatch_block.csv"), "DSC")

    body = _dispatch_run_deconvolution(client, project_id, dataset_key, "corrected")
    response = body.get("response") or {}

    status_children = json.dumps(response.get("deconvolution-run-status", {}))
    assert "danger" in status_children or "unavailable" in status_children.lower(), status_children
    results = client.get(f"/workspace/{project_id}/results").json()
    assert results.get("results") == []


# ---------------------------------------------------------------------------
# Real-browser rendering via playwright-cli run-code
# ---------------------------------------------------------------------------


def _pw_session(session: str, *args: str) -> str:
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        pytest.skip("npx is required for Playwright CLI browser checks.")
    completed = subprocess.run(
        [npx, "--yes", "--package", "@playwright/cli", "playwright-cli", f"-s={session}", *args],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=300,
        check=True,
    )
    return completed.stdout.strip()


def _run_browser_script(template: str, params: dict, session_name: str) -> dict:
    base_url = params["base"]
    script_path = WORK_ROOT / f"{session_name}.js"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(template % params, encoding="utf-8")

    session = f"{session_name}-{os.getpid()}"
    try:
        _pw_session(session, "open", base_url)
        _pw_session(session, "run-code", "--filename", str(script_path))
        output = _pw_session(session, "eval", "() => window.__deconvolutionReport")
    finally:
        npx = shutil.which("npx") or shutil.which("npx.cmd")
        if npx:
            subprocess.run(
                [npx, "--yes", "--package", "@playwright/cli", "playwright-cli", f"-s={session}", "close"],
                cwd=REPO_ROOT,
                capture_output=True,
                timeout=60,
            )

    marker = "### Result\n"
    assert marker in output, output
    payload = output.split(marker, 1)[1].split("\n### ", 1)[0].strip()
    report = json.loads(payload)
    assert isinstance(report, dict), output
    return report


_THERMAL_BROWSER_JS = """
async (page) => {
  const BASE = %(base)r;
  const PROJECT_ID = %(project)r;
  const DATASET = %(dataset)r;
  const textOf = (sel) => page.evaluate((s) => {
    const el = document.querySelector(s);
    return el ? (el.innerText || el.textContent || '') : '';
  }, sel);
  await page.goto(BASE + '/deconvolution', {waitUntil: 'domcontentloaded'});
  await page.evaluate((pid) => {
    sessionStorage.setItem('project-id', JSON.stringify(pid));
    sessionStorage.setItem('project-id-timestamp', String(Date.now()));
  }, PROJECT_ID);
  await page.reload({waitUntil: 'domcontentloaded'});
  await page.locator('#deconvolution-dataset-select').waitFor({state: 'visible', timeout: 30000});

  await page.locator('#deconvolution-dataset-select').click();
  const option = page.locator('.dash-dropdown-option', {hasText: DATASET}).first();
  await option.waitFor({state: 'visible', timeout: 15000});
  await option.click();
  await page.keyboard.press('Escape');

  // Wait for the backend options to resolve the dataset (status text appears).
  await page.waitForFunction(
    () => ((document.querySelector('#deconvolution-dataset-status') || {}).innerText || '').length > 0,
    null,
    {timeout: 20000}
  );
  await page.waitForTimeout(1200);
  const datasetStatus = await textOf('#deconvolution-dataset-status');

  await page.locator('#deconvolution-basis-select').click();
  const basisOption = page.locator('.dash-dropdown-option', {hasText: 'Baseline-corrected'}).first();
  await basisOption.waitFor({state: 'visible', timeout: 15000});
  await basisOption.click();
  await page.keyboard.press('Escape');
  await page.waitForTimeout(800);

  await page.locator('#deconvolution-n-peaks').fill('2');
  await page.keyboard.press('Tab');
  await page.locator('#deconvolution-use-guesses input').click();
  await page.waitForTimeout(800);

  const centers = page.locator('input[id*="deconvolution-guess-center"]');
  const sigmas = page.locator('input[id*="deconvolution-guess-sigma"]');
  await centers.nth(0).fill('120');
  await sigmas.nth(0).fill('8');
  await centers.nth(1).fill('170');
  await sigmas.nth(1).fill('10');

  await page.locator('#deconvolution-run-btn').click();
  await page.waitForSelector('#deconvolution-result-figure .js-plotly-plot', {state: 'visible', timeout: 120000});
  await page.waitForTimeout(2000);

  const collect = async () => page.evaluate(() => {
    const box = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {width: r.width, height: r.height};
    };
    const tableHeader = (document.querySelector('#deconvolution-result-table thead') || {}).innerText || '';
    const metricText = (document.querySelector('#deconvolution-result-metrics') || {}).innerText || '';
    // Limitations live inside a collapsed <details>, so read textContent.
    const scientificText = (document.querySelector('#deconvolution-result-scientific') || {}).textContent || '';
    return {
      plot: box('#deconvolution-result-figure .js-plotly-plot'),
      svg: box('#deconvolution-result-figure svg.main-svg'),
      plotCount: document.querySelectorAll('#deconvolution-result-figure .js-plotly-plot').length,
      residualPlots: document.querySelectorAll('#deconvolution-result-residual .js-plotly-plot').length,
      tableRows: document.querySelectorAll('#deconvolution-result-table tbody tr').length,
      tableHeader,
      metricText,
      scientificText,
      status: (document.querySelector('#deconvolution-run-status') || {}).innerText || '',
    };
  });
  const first = await collect();
  await page.reload({waitUntil: 'domcontentloaded'});
  await page.waitForSelector('#deconvolution-result-figure .js-plotly-plot', {state: 'visible', timeout: 90000});
  await page.waitForTimeout(1500);
  const second = await collect();
  await page.evaluate((r) => { window.__deconvolutionReport = r; }, {datasetStatus, first, second});
}
"""

_SPECTRAL_BROWSER_JS = """
async (page) => {
  const BASE = %(base)r;
  const PROJECT_ID = %(project)r;
  const DATASET = %(dataset)r;
  const textOf = (sel) => page.evaluate((s) => {
    const el = document.querySelector(s);
    return el ? (el.innerText || el.textContent || '') : '';
  }, sel);
  await page.goto(BASE + '/deconvolution', {waitUntil: 'domcontentloaded'});
  await page.evaluate((pid) => {
    sessionStorage.setItem('project-id', JSON.stringify(pid));
    sessionStorage.setItem('project-id-timestamp', String(Date.now()));
  }, PROJECT_ID);
  await page.reload({waitUntil: 'domcontentloaded'});
  await page.locator('#deconvolution-dataset-select').waitFor({state: 'visible', timeout: 30000});

  await page.locator('#deconvolution-dataset-select').click();
  const option = page.locator('.dash-dropdown-option', {hasText: DATASET}).first();
  await option.waitFor({state: 'visible', timeout: 15000});
  await option.click();
  await page.keyboard.press('Escape');
  await page.waitForTimeout(1500);

  const datasetStatus = await textOf('#deconvolution-dataset-status');

  await page.locator('#deconvolution-n-peaks').fill('2');
  await page.keyboard.press('Tab');
  await page.locator('#deconvolution-use-guesses input').click();
  await page.waitForTimeout(800);
  const centers = page.locator('input[id*="deconvolution-guess-center"]');
  const sigmas = page.locator('input[id*="deconvolution-guess-sigma"]');
  await centers.nth(0).fill('1700');
  await sigmas.nth(0).fill('30');
  await centers.nth(1).fill('1600');
  await sigmas.nth(1).fill('25');

  await page.locator('#deconvolution-run-btn').click();
  await page.waitForSelector('#deconvolution-result-figure .js-plotly-plot', {state: 'visible', timeout: 120000});
  await page.waitForTimeout(2000);

  const report = await page.evaluate(() => {
    const table = document.querySelector('#deconvolution-result-table');
    const figure = document.querySelector('#deconvolution-result-figure .js-plotly-plot');
    const rangeLabel = (document.querySelector('#deconvolution-lbl-range-min') || {}).innerText || '';
    return {
      tableHeader: (table || {}).innerText || '',
      rangeLabel,
      yAxisTitle: (((figure || {}).layout || {}).yaxis || {}).title ? figure.layout.yaxis.title.text : '',
      plotVisible: !!figure,
    };
  });
  await page.evaluate((r) => { window.__deconvolutionReport = r; }, {datasetStatus, ...report});
}
"""


@pytest.mark.skipif(
    os.environ.get("MATERIALSCOPE_RUN_BROWSER_TESTS") != "1",
    reason="Set MATERIALSCOPE_RUN_BROWSER_TESTS=1 to run live browser rendering checks.",
)
def test_deconvolution_page_real_browser_thermal_flow(live_dash_preview):
    """FLOW 1 + FLOW 3: thermal fit on a processed basis, then hard-reload hydration."""
    client = live_dash_preview
    base_url = str(client.base_url).rstrip("/")
    project_id = client.post("/workspace/new").json()["project_id"]
    dataset_key = _import_dataset(client, project_id, _thermal_csv("thermal_flow_dsc.csv"), "DSC")
    _run_stable_dsc_analysis(client, project_id, dataset_key)

    report = _run_browser_script(
        _THERMAL_BROWSER_JS,
        {"base": base_url, "project": project_id, "dataset": dataset_key},
        "deconvolution-thermal",
    )

    assert "°C" in report["datasetStatus"]

    first = report["first"]
    assert first["plot"] and first["plot"]["width"] > 200 and first["plot"]["height"] > 200
    assert first["svg"] and first["svg"]["height"] > 100
    assert first["plotCount"] == 1
    assert first["residualPlots"] == 1
    assert first["tableRows"] == 2
    assert "integrated amplitude" in first["tableHeader"].lower()
    assert "fwhm" in first["tableHeader"].lower()
    # Bootstrap uppercases metric labels, so compare case-insensitively.
    assert "unweighted sse / dof" in first["metricText"].lower()
    assert "not a measurement-uncertainty-weighted" in first["scientificText"].lower()

    # Hydration: the reload must re-render the saved result (no re-fit needed).
    second = report["second"]
    assert second["plot"] and second["plot"]["height"] > 200
    assert second["tableRows"] == 2
    assert second["plotCount"] == 1


@pytest.mark.skipif(
    os.environ.get("MATERIALSCOPE_RUN_BROWSER_TESTS") != "1",
    reason="Set MATERIALSCOPE_RUN_BROWSER_TESTS=1 to run live browser rendering checks.",
)
def test_deconvolution_page_real_browser_spectral_flow(live_dash_preview):
    """FLOW 2: a non-temperature axis must never be labelled as °C."""
    client = live_dash_preview
    base_url = str(client.base_url).rstrip("/")
    project_id = client.post("/workspace/new").json()["project_id"]
    dataset_key = _import_dataset(client, project_id, _spectral_csv("spectral_flow_ftir.csv"), "FTIR")

    report = _run_browser_script(
        _SPECTRAL_BROWSER_JS,
        {"base": base_url, "project": project_id, "dataset": dataset_key},
        "deconvolution-spectral",
    )

    assert report["plotVisible"] is True
    assert "°C" not in report["datasetStatus"]
    assert "cm" in report["datasetStatus"]
    assert "°C" not in report["rangeLabel"]
    assert "cm" in report["rangeLabel"]
    assert "°C" not in report["tableHeader"]
    assert "cm" in report["tableHeader"]
    assert "Integrated amplitude" in report["tableHeader"]
