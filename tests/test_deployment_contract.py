from __future__ import annotations

import ast
import json
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _repo_text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _pyproject() -> dict:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _requirement_lines(path: str) -> list[str]:
    lines = []
    for raw_line in _repo_text(path).splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


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
    # Docker must keep consuming the same requirements.txt that pyproject
    # declares as its dynamic runtime dependency source.
    assert "COPY requirements.txt ." in dockerfile
    assert "pip install -r requirements.txt" in dockerfile


def test_container_entrypoint_runs_combined_dash_server_only():
    start_script = _repo_text("docker/start.sh")

    assert 'exec python -m dash_app.server --host 0.0.0.0 --port "${PORT:-8050}"' in start_script
    assert 'MATERIALSCOPE_API_URL:-http://127.0.0.1:${PORT:-8050}' in start_script
    assert "python -m backend.main" not in start_script
    assert "streamlit run app.py" not in start_script
    assert "&" not in start_script


def _uvicorn_run_kwargs() -> dict[str, str | int | None]:
    """Extract the keyword arguments of the ``uvicorn.run(...)`` call in the
    combined Dash server entrypoint. Non-literal arguments (e.g. ``args.host``)
    evaluate to None — the contract only pins literal choices like ``http``."""
    tree = ast.parse(_repo_text("dash_app/server.py"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "run"
            and isinstance(func.value, ast.Name)
            and func.value.id == "uvicorn"
        ):
            kwargs: dict[str, str | int | None] = {}
            for kw in node.keywords:
                if kw.arg is None:
                    continue
                try:
                    kwargs[kw.arg] = ast.literal_eval(kw.value)
                except ValueError:
                    kwargs[kw.arg] = None
            return kwargs
    raise AssertionError("dash_app/server.py does not call uvicorn.run(...)")


def test_combined_server_pins_h11_http_parser():
    """The deployed server must pin uvicorn's HTTP parser to h11.

    requirements.txt depends on plain ``uvicorn`` (no [standard] extra), so
    httptools only ever reaches container images transitively. With
    ``http="auto"`` uvicorn silently selects the httptools parser whenever it
    is importable, and current uvicorn/httptools releases reject valid
    proxy-generated request shapes (e.g. absolute-form targets) with
    ``400 Invalid HTTP request received.`` where h11 accepts them — on Vercel
    that 400s every POST /_dash-update-component and the Dash shell never
    populates. h11 is uvicorn's own hard dependency and accepts those shapes.
    """
    kwargs = _uvicorn_run_kwargs()
    assert kwargs.get("http") == "h11"


def test_h11_pin_resolves_to_h11_protocol_even_when_httptools_is_importable():
    """Runtime half of the parser contract: with httptools importable (the
    transitive-install scenario behind the Vercel 400s), the server's pinned
    configuration must still resolve uvicorn's protocol to H11Protocol."""
    import unittest.mock

    import uvicorn
    from uvicorn.protocols.http.h11_impl import H11Protocol

    async def asgi_app(scope, receive, send):  # pragma: no cover - never run
        return

    with unittest.mock.patch.dict(sys.modules, {"httptools": unittest.mock.MagicMock()}):
        config = uvicorn.Config(asgi_app, http="h11", lifespan="off")
        config.load()
        assert config.http_protocol_class is H11Protocol


def test_vercel_seam_reuses_docker_contract():
    """Vercel deploys the existing Dockerfile as a container service — no
    duplicated Docker contract (no Dockerfile.vercel, no copied steps)."""
    vercel = json.loads(_repo_text("vercel.json"))

    # Exactly one service, built by the container runtime from the real
    # Dockerfile at the repository root.
    assert list(vercel["services"]) == ["materialscope"]
    service = vercel["services"]["materialscope"]
    assert service["root"] == "."
    assert service["runtime"] == "container"
    assert service["entrypoint"] == "Dockerfile"

    # The seam must point at the real Docker contract, not a copy.
    assert (REPO_ROOT / service["entrypoint"]).is_file()
    assert not (REPO_ROOT / "Dockerfile.vercel").exists()

    # A single catch-all rewrite exposes the service publicly.
    assert vercel["rewrites"] == [
        {"source": "/(.*)", "destination": {"service": "materialscope"}}
    ]


def _requirement_name(line: str) -> str:
    """Extract the lowercase distribution name from a PEP 508-style line."""
    spec = line.split(";")[0]
    for token in (">", "<", "=", " ", "[", "!"):
        spec = spec.split(token)[0]
    return spec.strip().lower()


def test_packaging_contract_declares_project_truth():
    """pyproject.toml must be the packaging contract; requirements.txt is the
    single runtime source it consumes dynamically (PR-3)."""
    pyproject = _pyproject()
    project = pyproject["project"]

    assert project["name"] == "MaterialScope"
    assert project["requires-python"] == ">=3.11"
    assert {"dependencies", "version"}.issubset(project["dynamic"])

    build_system = pyproject["build-system"]
    assert build_system["build-backend"] == "setuptools.build_meta"
    assert any(str(spec).startswith("setuptools") for spec in build_system["requires"])

    # Single runtime dependency source: pyproject consumes requirements.txt,
    # which Docker installs directly.
    assert pyproject["tool"]["setuptools"]["dynamic"]["dependencies"]["file"] == ["requirements.txt"]
    # Version mirrors the existing app-version constant; no parallel scheme.
    assert pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"] == "utils.license_manager.APP_VERSION"


def test_dev_extra_isolates_test_tooling_from_runtime():
    dev_names = {_requirement_name(entry) for entry in _pyproject()["project"]["optional-dependencies"]["dev"]}
    assert {"pytest", "ruff"} <= dev_names

    # Nothing declared as development tooling may also sit in runtime deps.
    runtime_names = {_requirement_name(line) for line in _requirement_lines("requirements.txt")}
    assert not dev_names & runtime_names


def test_requirements_keep_runtime_and_ingest_dependencies_without_test_tooling():
    requirements = "\n".join(_requirement_lines("requirements.txt"))

    # Combined Dash/FastAPI runtime contract stays intact. Dash must declare
    # the native FastAPI backend contract ([fastapi] extra, 4.2+) because the
    # combined server passes the existing FastAPI app into Dash directly; the
    # a2wsgi WSGI bridge was removed with that migration.
    assert "dash[fastapi]>=4.2,<5" in requirements
    assert "fastapi>=0.115.0" in requirements

    # Ingest dependencies stay represented (tools/library_ingest/providers.py).
    assert "pymatgen>=2025.1" in requirements
    assert "mp-api>=0.45" in requirements
    assert "pyreadr>=0.5" in requirements

    # Plotly/Kaleido compatibility range validated on Python 3.11/3.12 and in
    # Docker against a real Chrome/Chromium: Plotly 6+ requires Kaleido v1.
    assert "plotly>=6.1.1,<8" in requirements
    assert "kaleido>=1,<2" in requirements

    # pytest is development infrastructure (moved to the `dev` extra), rdata
    # has zero importers anywhere in the repository, and the a2wsgi WSGI
    # bridge was removed with the native Dash FastAPI backend migration.
    names = {_requirement_name(line) for line in _requirement_lines("requirements.txt")}
    assert "pytest" not in names
    assert "rdata" not in names
    assert "a2wsgi" not in names


def test_readme_documents_preview_and_dash_container_runtime_flags():
    readme = _repo_text("README.md")

    # Runtime contract: the README must document the combined Dash server entrypoint.
    assert "python -m dash_app.server" in readme
    assert "http://127.0.0.1:8050" in readme
    # Marketing copy is intentionally not asserted here; wording evolves
    # independently of runtime behavior (see ee0325b).
    assert "MATERIALSCOPE_ENABLE_PREVIEW_MODULES=false" not in readme
    assert "DEV_CLOUD_AUTH" not in readme


def test_dash_assets_keep_result_plotly_resize_contract():
    css = _repo_text("dash_app/assets/style.css")
    resize_js = _repo_text("dash_app/assets/result_figure_resize.js")

    assert ".ms-figure-host" in css
    assert "height: 560px" in css
    assert ".ms-figure-host .plot-container" in css
    assert ".ms-figure-host .svg-container" in css
    assert ".ms-figure-host .main-svg" in css
    assert "Plotly.Plots.resize" in resize_js
    assert ".ms-figure-host .js-plotly-plot" in resize_js
