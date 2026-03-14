"""Checkpoint helpers for resumable provider ingest."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .common import read_json, write_json


def checkpoint_path(output_root: Path, provider_id: str) -> Path:
    return Path(output_root) / "_checkpoints" / f"{provider_id}.json"


def load_checkpoint(output_root: Path, provider_id: str) -> dict[str, Any]:
    payload = read_json(
        checkpoint_path(output_root, provider_id),
        {
            "provider": provider_id,
            "completed": False,
            "last_source_id": "",
            "next_chunk_index": 1,
            "processed_count": 0,
            "emitted_package_ids": [],
            "errors": [],
        },
    )
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("provider", provider_id)
    payload.setdefault("completed", False)
    payload.setdefault("last_source_id", "")
    payload.setdefault("next_chunk_index", 1)
    payload.setdefault("processed_count", 0)
    payload.setdefault("emitted_package_ids", [])
    payload.setdefault("errors", [])
    return payload


def save_checkpoint(output_root: Path, provider_id: str, checkpoint: dict[str, Any]) -> None:
    write_json(checkpoint_path(output_root, provider_id), checkpoint)


def append_error(checkpoint: dict[str, Any], *, source_id: str, message: str, limit: int = 200) -> None:
    errors = list(checkpoint.get("errors") or [])
    errors.append({"source_id": str(source_id), "message": str(message)})
    checkpoint["errors"] = errors[-limit:]


def checkpoint_copy(checkpoint: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(checkpoint)
