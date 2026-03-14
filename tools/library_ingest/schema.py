"""Tooling-only normalized schema helpers for provider ingest."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PackageSpec:
    package_id: str
    analysis_type: str
    provider: str
    version: str
    source_url: str
    license_name: str
    license_text: str
    attribution: str
    priority: int
    published_at: str
    generated_at: str
    provider_dataset_version: str
    builder_version: str
    normalized_schema_version: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PackageSpec":
        return cls(
            package_id=str(payload.get("package_id") or "").strip(),
            analysis_type=str(payload.get("analysis_type") or "").strip().upper(),
            provider=str(payload.get("provider") or "").strip(),
            version=str(payload.get("version") or "").strip(),
            source_url=str(payload.get("source_url") or "").strip(),
            license_name=str(payload.get("license_name") or "").strip(),
            license_text=str(payload.get("license_text") or "").strip(),
            attribution=str(payload.get("attribution") or "").strip(),
            priority=int(payload.get("priority") or 0),
            published_at=str(payload.get("published_at") or "").strip(),
            generated_at=str(payload.get("generated_at") or "").strip(),
            provider_dataset_version=str(payload.get("provider_dataset_version") or "").strip(),
            builder_version=str(payload.get("builder_version") or "").strip(),
            normalized_schema_version=int(payload.get("normalized_schema_version") or 1),
        )


def normalized_xrd_entry(
    *,
    candidate_id: str,
    candidate_name: str,
    provider: str,
    source_id: str,
    source_url: str,
    peaks: list[dict[str, float]],
    generated_at: str,
    provider_dataset_version: str,
    builder_version: str,
    normalized_schema_version: int,
) -> dict[str, Any]:
    return {
        "candidate_id": str(candidate_id),
        "candidate_name": str(candidate_name),
        "provider": str(provider),
        "source_id": str(source_id),
        "source_url": str(source_url),
        "peaks": peaks,
        "generated_at": str(generated_at),
        "provider_dataset_version": str(provider_dataset_version),
        "builder_version": str(builder_version),
        "normalized_schema_version": int(normalized_schema_version),
    }


def normalized_spectral_entry(
    *,
    candidate_id: str,
    candidate_name: str,
    provider: str,
    source_id: str,
    source_url: str,
    axis: list[float],
    signal: list[float],
    generated_at: str,
    provider_dataset_version: str,
    builder_version: str,
    normalized_schema_version: int,
) -> dict[str, Any]:
    return {
        "candidate_id": str(candidate_id),
        "candidate_name": str(candidate_name),
        "provider": str(provider),
        "source_id": str(source_id),
        "source_url": str(source_url),
        "axis": axis,
        "signal": signal,
        "generated_at": str(generated_at),
        "provider_dataset_version": str(provider_dataset_version),
        "builder_version": str(builder_version),
        "normalized_schema_version": int(normalized_schema_version),
    }
