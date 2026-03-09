"""FastAPI app for the tranche-1 ThermoAnalyzer backend."""

from __future__ import annotations

import base64
import binascii
import io

from fastapi import FastAPI, Header, HTTPException

from backend import BACKEND_API_VERSION
from backend.models import (
    HealthResponse,
    ProjectLoadRequest,
    ProjectLoadResponse,
    ProjectSaveRequest,
    ProjectSaveResponse,
    ProjectSummary,
    VersionResponse,
)
from backend.store import ProjectStore
from core.project_io import PROJECT_EXTENSION, load_project_archive, save_project_archive
from utils.license_manager import APP_VERSION


def _require_token(expected_token: str | None, provided_token: str | None) -> None:
    if expected_token and provided_token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid or missing API token.")


def _decode_archive_b64(payload: str) -> bytes:
    try:
        return base64.b64decode(payload.encode("ascii"), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail=f"archive_base64 is not valid base64: {exc}") from exc


def _project_summary(project_state: dict) -> ProjectSummary:
    return ProjectSummary(
        active_dataset=project_state.get("active_dataset"),
        dataset_count=len(project_state.get("datasets", {}) or {}),
        result_count=len(project_state.get("results", {}) or {}),
        figure_count=len(project_state.get("figures", {}) or {}),
        analysis_history_count=len(project_state.get("analysis_history", []) or []),
    )


def create_app(*, api_token: str | None = None, store: ProjectStore | None = None) -> FastAPI:
    """Create a backend app instance with an in-memory project store."""
    app = FastAPI(title="ThermoAnalyzer Backend", version=BACKEND_API_VERSION)
    project_store = store or ProjectStore()

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(api_version=BACKEND_API_VERSION)

    @app.get("/version", response_model=VersionResponse)
    def version(x_ta_token: str | None = Header(default=None, alias="X-TA-Token")) -> VersionResponse:
        _require_token(api_token, x_ta_token)
        return VersionResponse(
            app_version=APP_VERSION,
            api_version=BACKEND_API_VERSION,
            project_extension=PROJECT_EXTENSION,
        )

    @app.post("/project/load", response_model=ProjectLoadResponse)
    def project_load(
        request: ProjectLoadRequest,
        x_ta_token: str | None = Header(default=None, alias="X-TA-Token"),
    ) -> ProjectLoadResponse:
        _require_token(api_token, x_ta_token)
        archive_bytes = _decode_archive_b64(request.archive_base64)

        try:
            project_state = load_project_archive(io.BytesIO(archive_bytes))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Project archive could not be loaded: {exc}") from exc

        project_id = project_store.put(project_state)
        return ProjectLoadResponse(
            project_id=project_id,
            project_extension=PROJECT_EXTENSION,
            summary=_project_summary(project_state),
        )

    @app.post("/project/save", response_model=ProjectSaveResponse)
    def project_save(
        request: ProjectSaveRequest,
        x_ta_token: str | None = Header(default=None, alias="X-TA-Token"),
    ) -> ProjectSaveResponse:
        _require_token(api_token, x_ta_token)

        project_state = project_store.get(request.project_id)
        if project_state is None:
            raise HTTPException(status_code=404, detail=f"Unknown project_id: {request.project_id}")

        try:
            archive_bytes = save_project_archive(project_state)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Project archive could not be saved: {exc}") from exc

        archive_base64 = base64.b64encode(archive_bytes).decode("ascii")
        return ProjectSaveResponse(
            project_id=request.project_id,
            file_name=f"thermoanalyzer_project{PROJECT_EXTENSION}",
            archive_base64=archive_base64,
        )

    return app

