"""Opt-in browser regression test for the XRD Plotly result surface."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("MATERIALSCOPE_BROWSER_TEST_URL", "http://127.0.0.1:8050")


def _post_json(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload or {}).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _put_json(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload or {}).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _server_available() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/xrd", timeout=5) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def _pw(*args: str) -> str:
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        pytest.skip("npx is required for Playwright CLI browser checks.")
    completed = subprocess.run(
        [npx, "--yes", "--package", "@playwright/cli", "playwright-cli", "--raw", *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=90,
        check=True,
    )
    return completed.stdout.strip()


def test_xrd_result_plotly_graph_has_visible_browser_box():
    if os.environ.get("MATERIALSCOPE_RUN_BROWSER_TESTS") != "1":
        pytest.skip("Set MATERIALSCOPE_RUN_BROWSER_TESTS=1 to run live browser rendering checks.")
    if not (shutil.which("npx") or shutil.which("npx.cmd")):
        pytest.skip("npx is required for Playwright CLI browser checks.")
    if not _server_available():
        pytest.skip(f"MaterialScope server is not reachable at {BASE_URL}.")

    project = _post_json("/workspace/new")["project_id"]
    sample = REPO_ROOT / "sample_data" / "xrd_2024_0304_zenodo.csv"
    imported = _post_json(
        "/dataset/import",
        {
            "project_id": project,
            "file_name": sample.name,
            "file_base64": base64.b64encode(sample.read_bytes()).decode("ascii"),
            "data_type": "XRD",
        },
    )
    dataset_key = (imported.get("dataset") or {}).get("key") or imported.get("dataset_key") or sample.name
    _put_json(f"/workspace/{project}/active-dataset", {"dataset_key": dataset_key})

    _pw("close-all")
    _pw("open", f"{BASE_URL}/xrd")
    _pw(
        "eval",
        f"() => {{ sessionStorage.setItem('project-id', JSON.stringify('{project}')); sessionStorage.setItem('project-id-timestamp', String(Date.now())); }}",
    )
    _pw("reload")
    time.sleep(2)
    _pw("eval", "() => document.querySelector('#xrd-left-tabs-tab-run')?.click()")
    time.sleep(1)
    _pw("eval", "() => document.querySelector('#xrd-run-btn')?.click()")
    time.sleep(8)
    payload = _pw(
        "eval",
        "() => { const box = (sel) => { const el = document.querySelector(sel); if (!el) return null; const r = el.getBoundingClientRect(); return {width: r.width, height: r.height}; }; return { plot: box('#xrd-result-figure .js-plotly-plot'), svg: box('#xrd-result-figure svg.main-svg'), plotCount: document.querySelectorAll('#xrd-result-figure .js-plotly-plot').length, svgCount: document.querySelectorAll('#xrd-result-figure svg.main-svg').length }; }",
    )
    result = json.loads(payload)

    assert result["plotCount"] >= 1
    assert result["svgCount"] >= 1
    assert result["plot"]["width"] > 300
    assert result["plot"]["height"] > 300
    assert result["svg"]["width"] > 300
    assert result["svg"]["height"] > 300
