from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _repo_text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_dockerfile_keeps_dash_runtime_contract():
    dockerfile = _repo_text("Dockerfile")

    assert "FROM python:3.12-slim" in dockerfile
    assert "chromium" in dockerfile
    assert "curl" in dockerfile
    assert "BROWSER_PATH=/usr/bin/chromium" in dockerfile
    assert "CHROME_BIN=/usr/bin/chromium" in dockerfile
    assert "MATERIALSCOPE_HOME=/data/materialscope" in dockerfile
    assert "mkdir -p /data/materialscope" in dockerfile
    assert "EXPOSE 8050" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert 'http://127.0.0.1:${PORT:-8050}/health' in dockerfile
    assert "_stcore/health" not in dockerfile
    assert 'CMD ["/app/docker/start.sh"]' in dockerfile


def test_container_entrypoint_runs_combined_dash_server_only():
    start_script = _repo_text("docker/start.sh")

    assert 'exec python -m dash_app.server --host 0.0.0.0 --port "${PORT:-8050}"' in start_script
    assert 'MATERIALSCOPE_API_URL:-http://127.0.0.1:${PORT:-8050}' in start_script
    assert "python -m backend.main" not in start_script
    assert "streamlit run app.py" not in start_script
    assert "&" not in start_script


def test_requirements_include_runtime_and_ingest_dependencies():
    requirements = _repo_text("requirements.txt")

    assert "dash>=2.18.0" in requirements
    assert "fastapi>=0.115.0" in requirements
    assert "pymatgen>=2025.1" in requirements
    assert "mp-api>=0.45" in requirements
    assert "pyreadr>=0.5" in requirements
    assert "rdata>=0.11" in requirements


def test_readme_documents_preview_and_dash_container_runtime_flags():
    readme = _repo_text("README.md")

    assert "python -m dash_app.server" in readme
    assert "Stable prototype" in readme
    assert "Experimental" in readme
    assert "MATERIALSCOPE_ENABLE_PREVIEW_MODULES=false" not in readme
    assert "DEV_CLOUD_AUTH" not in readme
