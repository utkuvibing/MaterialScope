"""Opt-in live checks for the preview Kinetics Dash page.

Two layers, both against the real combined Dash/FastAPI server started with
``MATERIALSCOPE_ENABLE_PREVIEW_MODULES=1``:

1. ``test_kinetics_run_callback_dispatch_*`` dispatch the registered
   ``run_kinetics`` callback through ``/_dash-update-component`` — the same
   transport the browser uses — and verify the workspace result persists.
2. ``test_kinetics_page_real_browser_run`` drives a real browser via
   ``playwright-cli run-code`` and verifies the rendered Plotly surface.

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


def _tga_csv(name: str, step_center: float) -> Path:
    """Deterministic TGA-like CSV (temperature/signal columns) under pytest_temp."""
    out_dir = REPO_ROOT / "pytest_temp" / "kinetics_browser"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    temperature = np.linspace(30.0, 800.0, 300)
    mass = 100.0 - 60.0 / (1.0 + np.exp(-(temperature - step_center) / 45.0))
    frame = pd.DataFrame({"temperature": temperature, "signal": np.round(mass, 4)})
    path.write_text(frame.to_csv(index=False), encoding="utf-8")
    return path


def _dsc_csv(name: str, peak_center: float) -> Path:
    """Deterministic DSC-like CSV (single positive peak) under pytest_temp."""
    out_dir = REPO_ROOT / "pytest_temp" / "kinetics_browser"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    temperature = np.linspace(50.0, 350.0, 300)
    signal = np.exp(-0.5 * ((temperature - peak_center) / 12.0) ** 2)
    frame = pd.DataFrame({"temperature": temperature, "signal": np.round(signal, 6)})
    path.write_text(frame.to_csv(index=False), encoding="utf-8")
    return path


def _import_dataset(client, project_id: str, path: Path, data_type: str = "TGA") -> str:
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


def _seed_three_tga(client, project_id: str) -> list[str]:
    keys = []
    for idx, center in enumerate((400.0, 430.0, 460.0)):
        keys.append(_import_dataset(client, project_id, _tga_csv(f"kinetics_tga_{idx}.csv", center)))
    return keys


def _seed_three_dsc_with_analysis(client, project_id: str) -> list[str]:
    """Import 3 DSC datasets and run REAL ``/analysis/run`` DSC execution on each.

    The saved ``dsc_state_*`` payloads then carry genuine ndarray curves —
    the production shape that crashed the unfixed kinetics service.
    """
    keys = []
    for idx, center in enumerate((195.0, 212.0, 228.0)):
        key = _import_dataset(
            client, project_id, _dsc_csv(f"kinetics_dsc_{idx}.csv", center), "DSC"
        )
        response = client.post(
            "/analysis/run",
            json={
                "project_id": project_id,
                "dataset_key": key,
                "analysis_type": "DSC",
            },
        )
        response.raise_for_status()
        keys.append(key)
    return keys


def _dispatch_run_kinetics(client, project_id: str, keys: list[str], rates: list[float]):
    """Invoke the registered run_kinetics callback the way the renderer does."""
    spec = next(
        item
        for item in client.get("/_dash-dependencies").json()
        if "kinetics-run-status" in item["output"]
    )
    # Pattern-matching (ALL) state ids arrive JSON-encoded in the dependency
    # spec; the renderer sends lists of per-component values under them.
    rate_wildcard = json.dumps({"index": ["ALL"], "type": "kinetics-rate-input"}, separators=(",", ":"))
    tp_wildcard = json.dumps({"index": ["ALL"], "type": "kinetics-tp-input"}, separators=(",", ":"))
    rate_ids = [{"type": "kinetics-rate-input", "index": key} for key in keys]
    tp_ids = [{"type": "kinetics-tp-input", "index": key} for key in keys]

    states: list[dict] = []
    for item in spec["state"]:
        cid = item["id"]
        prop = item["property"]
        if cid == "project-id":
            value = project_id
        elif cid == "kinetics-method":
            value = "ofw"
        elif cid == "kinetics-input-mode":
            value = "datasets"
        elif cid == "kinetics-dataset-select":
            value = keys
        elif cid == rate_wildcard:
            value = rates if prop == "value" else rate_ids
        elif cid == tp_wildcard:
            value = [None] * len(keys) if prop == "value" else tp_ids
        elif cid == "kinetics-manual-table":
            value = []
        elif cid == "kinetics-alpha-min":
            value = 0.1
        elif cid == "kinetics-alpha-max":
            value = 0.9
        elif cid == "kinetics-alpha-step":
            value = 0.1
        elif cid == "kinetics-confidence":
            value = 0.95
        elif cid in {"kinetics-refresh", "workspace-refresh"}:
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
            "inputs": [{"id": "kinetics-run-btn", "property": "n_clicks", "value": 1}],
            "state": states,
            "changedPropIds": ["kinetics-run-btn.n_clicks"],
        },
    )
    response.raise_for_status()
    return response.json()


def test_kinetics_run_callback_dispatch_saves_workspace_result(live_dash_preview):
    """Live callback dispatch: browser transport -> backend endpoint -> saved result."""
    client = live_dash_preview
    project_id = client.post("/workspace/new").json()["project_id"]
    keys = _seed_three_tga(client, project_id)

    body = _dispatch_run_kinetics(client, project_id, keys, [5.0, 10.0, 20.0])
    response = body.get("response") or {}

    status_children = json.dumps(response.get("kinetics-run-status", {}))
    assert "kinetics" in status_children.lower() or "saved" in status_children.lower(), status_children
    result_id = (response.get("kinetics-latest-result-id") or {}).get("data")
    assert result_id, response

    results = client.get(f"/workspace/{project_id}/results").json()
    ids = [item["id"] for item in results.get("results", [])]
    assert result_id in ids

    detail = client.get(f"/workspace/{project_id}/results/{result_id}").json()
    assert detail["processing"]["kinetics_method"] == "ofw"
    assert detail["rows"], "OFW run should persist per-alpha rows"


def test_kinetics_run_callback_dispatch_blocks_untraceable_rate(live_dash_preview):
    """Missing heating-rate provenance blocks through the live transport too."""
    client = live_dash_preview
    project_id = client.post("/workspace/new").json()["project_id"]
    keys = _seed_three_tga(client, project_id)

    body = _dispatch_run_kinetics(client, project_id, keys, [5.0, None, 20.0])
    status_children = json.dumps((body.get("response") or {}).get("kinetics-run-status", {}))
    assert "danger" in status_children or "block" in status_children.lower(), status_children


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
        timeout=180,
        check=True,
    )
    return completed.stdout.strip()


_BROWSER_JS_TEMPLATE = """
async (page) => {
  const BASE = %(base)r;
  const PROJECT_ID = %(project)r;
  const NAMES = %(names)s;
  await page.goto(BASE + '/kinetics', {waitUntil: 'domcontentloaded'});
  await page.evaluate((pid) => {
    sessionStorage.setItem('project-id', JSON.stringify(pid));
    sessionStorage.setItem('project-id-timestamp', String(Date.now()));
  }, PROJECT_ID);
  await page.reload({waitUntil: 'domcontentloaded'});
  await page.locator('#kinetics-method').waitFor({state: 'visible', timeout: 30000});
  await page.locator('#kinetics-method input[value="ofw"]').click();
  for (const name of NAMES) {
    await page.locator('#kinetics-dataset-select').click();
    const option = page.locator('.dash-dropdown-option', {hasText: name}).first();
    await option.waitFor({state: 'visible', timeout: 10000});
    await option.click();
    await page.waitForTimeout(400);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);
  }
  await page.waitForFunction(
    (n) => document.querySelectorAll('#kinetics-dataset-inputs input[type="number"]').length >= n,
    NAMES.length,
    {timeout: 20000}
  );
  const rates = ['5', '10', '20'];
  const inputs = page.locator('#kinetics-dataset-inputs input[type="number"]');
  for (let i = 0; i < NAMES.length; i++) { await inputs.nth(i).fill(rates[i]); }
  await page.locator('#kinetics-run-btn').click();
  await page.waitForSelector('#kinetics-result-figure .js-plotly-plot', {state: 'visible', timeout: 90000});
  await page.waitForTimeout(1500);
  const collect = async () => page.evaluate(() => {
    const box = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {width: r.width, height: r.height};
    };
    return {
      plot: box('#kinetics-result-figure .js-plotly-plot'),
      svg: box('#kinetics-result-figure svg.main-svg'),
      plotCount: document.querySelectorAll('#kinetics-result-figure .js-plotly-plot').length,
      svgCount: document.querySelectorAll('#kinetics-result-figure svg.main-svg').length,
      status: (document.querySelector('#kinetics-run-status') || {}).innerText || '',
      tableRows: document.querySelectorAll('#kinetics-result-table tbody tr').length,
    };
  });
  const first = await collect();
  // Hydration regression: a full reload must reopen the saved workspace
  // result (kinetics-latest-result-id hydration), not just the in-page store.
  await page.reload({waitUntil: 'domcontentloaded'});
  await page.waitForSelector('#kinetics-result-figure .js-plotly-plot', {state: 'visible', timeout: 60000});
  await page.waitForTimeout(1000);
  const second = await collect();
  await page.evaluate((r) => { window.__kineticsReport = r; }, {first, second});
}
"""


@pytest.mark.skipif(
    os.environ.get("MATERIALSCOPE_RUN_BROWSER_TESTS") != "1",
    reason="Set MATERIALSCOPE_RUN_BROWSER_TESTS=1 to run live browser rendering checks.",
)
def test_kinetics_page_real_browser_run(live_dash_preview):
    client = live_dash_preview
    base_url = str(client.base_url).rstrip("/")
    project_id = client.post("/workspace/new").json()["project_id"]
    keys = _seed_three_tga(client, project_id)
    names = [f"{key} (TGA)" for key in keys]

    script_path = REPO_ROOT / "pytest_temp" / "kinetics_browser" / "kinetics_browser.js"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        _BROWSER_JS_TEMPLATE
        % {
            "base": base_url,
            "project": project_id,
            "names": json.dumps(names),
        },
        encoding="utf-8",
    )

    session = f"kinetics-{os.getpid()}"
    try:
        _pw_session(session, "open", base_url)
        _pw_session(session, "run-code", "--filename", str(script_path))
        output = _pw_session(session, "eval", "() => window.__kineticsReport")
    finally:
        npx = shutil.which("npx") or shutil.which("npx.cmd")
        if npx:
            subprocess.run(
                [npx, "--yes", "--package", "@playwright/cli", "playwright-cli", f"-s={session}", "close"],
                cwd=REPO_ROOT,
                capture_output=True,
                timeout=30,
            )

    # playwright-cli wraps eval output as "### Result\n<json>\n### ..."
    marker = "### Result\n"
    assert marker in output, output
    payload = output.split(marker, 1)[1].split("\n### ", 1)[0].strip()
    report = json.loads(payload)
    assert isinstance(report, dict), output

    first = report["first"]
    assert first["plotCount"] >= 1
    assert first["svgCount"] >= 1
    assert first["plot"]["width"] > 300
    assert first["plot"]["height"] > 300
    assert first["tableRows"] >= 1

    # After a full reload the page rehydrates kinetics-latest-result-id from
    # the workspace results list and re-renders the same saved result.
    second = report["second"]
    assert second["plotCount"] >= 1
    assert second["svgCount"] >= 1
    assert second["tableRows"] >= 1


@pytest.mark.skipif(
    os.environ.get("MATERIALSCOPE_RUN_BROWSER_TESTS") != "1",
    reason="Set MATERIALSCOPE_RUN_BROWSER_TESTS=1 to run live browser rendering checks.",
)
def test_kinetics_page_real_browser_dsc_ofw(live_dash_preview):
    """Real DSC /analysis/run state -> browser OFW -> reload re-render."""
    client = live_dash_preview
    base_url = str(client.base_url).rstrip("/")
    project_id = client.post("/workspace/new").json()["project_id"]
    keys = _seed_three_dsc_with_analysis(client, project_id)
    names = [f"{key} (DSC)" for key in keys]

    script_path = REPO_ROOT / "pytest_temp" / "kinetics_browser" / "kinetics_browser_dsc.js"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        _BROWSER_JS_TEMPLATE
        % {
            "base": base_url,
            "project": project_id,
            "names": json.dumps(names),
        },
        encoding="utf-8",
    )

    session = f"kinetics-dsc-{os.getpid()}"
    try:
        _pw_session(session, "open", base_url)
        _pw_session(session, "run-code", "--filename", str(script_path))
        output = _pw_session(session, "eval", "() => window.__kineticsReport")
    finally:
        npx = shutil.which("npx") or shutil.which("npx.cmd")
        if npx:
            subprocess.run(
                [npx, "--yes", "--package", "@playwright/cli", "playwright-cli", f"-s={session}", "close"],
                cwd=REPO_ROOT,
                capture_output=True,
                timeout=30,
            )

    marker = "### Result\n"
    assert marker in output, output
    payload = output.split(marker, 1)[1].split("\n### ", 1)[0].strip()
    report = json.loads(payload)
    assert isinstance(report, dict), output

    first = report["first"]
    assert first["plotCount"] >= 1
    assert first["tableRows"] >= 1

    # Saved DSC-based kinetics result rehydrates after reload.
    second = report["second"]
    assert second["plotCount"] >= 1
    assert second["tableRows"] >= 1
