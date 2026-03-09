"""Minimal DTOs for the tranche-1 backend surface."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "thermoanalyzer-backend"
    api_version: str


class VersionResponse(BaseModel):
    app_version: str
    api_version: str
    project_extension: str


class ProjectSummary(BaseModel):
    active_dataset: str | None = None
    dataset_count: int = 0
    result_count: int = 0
    figure_count: int = 0
    analysis_history_count: int = 0


class ProjectLoadRequest(BaseModel):
    archive_base64: str = Field(..., min_length=1)


class ProjectLoadResponse(BaseModel):
    project_id: str
    project_extension: str
    summary: ProjectSummary


class ProjectSaveRequest(BaseModel):
    project_id: str = Field(..., min_length=1)


class ProjectSaveResponse(BaseModel):
    project_id: str
    file_name: str
    archive_base64: str

