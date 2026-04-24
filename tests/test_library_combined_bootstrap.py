from __future__ import annotations

import os
import sys

import pytest

from core.library_cloud_client import CLOUD_URL_ENV, CLOUD_URL_ENV_LEGACY, reset_library_cloud_client
from core.library_combined_bootstrap import (
    apply_combined_dash_server_library_env,
    sanitize_library_path_env_vars,
)


@pytest.fixture(autouse=True)
def _reset_cloud_client():
    reset_library_cloud_client()
    yield
    reset_library_cloud_client()


@pytest.mark.skipif(sys.platform == "win32", reason="sanitize targets POSIX Windows-path leaks")
def test_sanitize_drops_windows_hosted_root_on_posix(monkeypatch):
    monkeypatch.setenv("MATERIALSCOPE_LIBRARY_HOSTED_ROOT", r"C:\build\reference_library_hosted")
    lines = sanitize_library_path_env_vars()
    assert "MATERIALSCOPE_LIBRARY_HOSTED_ROOT" not in os.environ
    assert any("Ignored MATERIALSCOPE_LIBRARY_HOSTED_ROOT" in line for line in lines)


def test_apply_combined_sets_cloud_url_when_unset(monkeypatch):
    monkeypatch.delenv(CLOUD_URL_ENV, raising=False)
    monkeypatch.delenv(CLOUD_URL_ENV_LEGACY, raising=False)
    monkeypatch.delenv("MATERIALSCOPE_LIBRARY_DISABLE_COMBINED_BOOTSTRAP", raising=False)
    lines = apply_combined_dash_server_library_env(listen_host="127.0.0.1", listen_port=8050)
    assert os.environ[CLOUD_URL_ENV] == "http://127.0.0.1:8050"
    assert any("was unset" in line for line in lines)


def test_apply_combined_rewrites_loopback_8000_when_server_not_8000(monkeypatch):
    monkeypatch.setenv(CLOUD_URL_ENV, "http://127.0.0.1:8000")
    monkeypatch.delenv(CLOUD_URL_ENV_LEGACY, raising=False)
    monkeypatch.delenv("MATERIALSCOPE_LIBRARY_DISABLE_COMBINED_BOOTSTRAP", raising=False)
    lines = apply_combined_dash_server_library_env(listen_host="127.0.0.1", listen_port=8050)
    assert os.environ[CLOUD_URL_ENV] == "http://127.0.0.1:8050"
    assert os.getenv(CLOUD_URL_ENV_LEGACY) is None
    assert any("port 8000" in line for line in lines)


def test_apply_combined_respects_explicit_matching_port(monkeypatch):
    monkeypatch.setenv(CLOUD_URL_ENV, "http://127.0.0.1:8050")
    monkeypatch.delenv("MATERIALSCOPE_LIBRARY_DISABLE_COMBINED_BOOTSTRAP", raising=False)
    lines = apply_combined_dash_server_library_env(listen_host="127.0.0.1", listen_port=8050)
    assert os.environ[CLOUD_URL_ENV] == "http://127.0.0.1:8050"
    assert not any("Warning" in line for line in lines)


def test_apply_combined_warns_on_loopback_port_mismatch(monkeypatch):
    monkeypatch.setenv(CLOUD_URL_ENV, "http://127.0.0.1:9000")
    monkeypatch.delenv("MATERIALSCOPE_LIBRARY_DISABLE_COMBINED_BOOTSTRAP", raising=False)
    lines = apply_combined_dash_server_library_env(listen_host="127.0.0.1", listen_port=8050)
    assert os.environ[CLOUD_URL_ENV] == "http://127.0.0.1:9000"
    assert any("Warning" in line for line in lines)
