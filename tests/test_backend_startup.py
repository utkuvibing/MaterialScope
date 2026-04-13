from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_get_json(url: str, *, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(request, timeout=2) as response:  # nosec B310
        return json.loads(response.read().decode("utf-8"))


def _wait_for_health(url: str, timeout_s: float = 15.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            payload = _http_get_json(f"{url}/health")
            if payload.get("status") == "ok":
                return
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
        time.sleep(0.2)
    raise AssertionError("Backend health endpoint did not become ready in time.")


def test_backend_process_startup_smoke():
    if sys.platform == "win32":
        pytest.skip("Backend subprocess startup smoke is not supported in this Windows local test harness.")
    repo_root = Path(__file__).resolve().parents[1]
    port = _free_port()
    token = "startup-smoke-token"
    base_url = f"http://127.0.0.1:{port}"

    process = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "backend.main",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--token",
            token,
        ],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        _wait_for_health(base_url)
        version = _http_get_json(
            f"{base_url}/version",
            headers={"X-TA-Token": token},
        )
        assert "app_version" in version
        assert version["project_extension"] == ".thermozip"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

