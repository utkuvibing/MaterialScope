"""Deterministic bundled FTIR/Raman reference fallback."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED_LIBRARY_PATH = PROJECT_ROOT / "sample_data" / "reference_library_seed.json"


def _float_array(values: Any) -> np.ndarray | None:
    try:
        arr = np.asarray(values or [], dtype=float)
    except (TypeError, ValueError):
        return None
    if arr.ndim != 1 or arr.size < 3:
        return None
    return arr


@lru_cache(maxsize=2)
def load_demo_spectral_references(analysis_type: str) -> list[dict[str, Any]]:
    token = str(analysis_type or "").strip().upper()
    if token not in {"FTIR", "RAMAN"} or not SEED_LIBRARY_PATH.exists():
        return []
    try:
        payload = json.loads(SEED_LIBRARY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    references: list[dict[str, Any]] = []
    for package in payload.get("packages") or []:
        if not isinstance(package, Mapping):
            continue
        if str(package.get("analysis_type") or "").strip().upper() != token:
            continue
        provider = str(package.get("provider") or "Demo Spectral").strip()
        package_id = str(package.get("package_id") or f"demo_{token.lower()}_seed").strip()
        package_version = str(package.get("version") or "demo").strip()
        for entry in package.get("entries") or []:
            if not isinstance(entry, Mapping):
                continue
            axis = _float_array(entry.get("axis"))
            signal = _float_array(entry.get("signal"))
            if axis is None or signal is None or axis.size != signal.size:
                continue
            candidate_id = str(entry.get("candidate_id") or entry.get("id") or "").strip()
            if not candidate_id:
                continue
            references.append(
                {
                    **dict(entry),
                    "candidate_id": candidate_id,
                    "candidate_name": str(entry.get("candidate_name") or entry.get("name") or candidate_id),
                    "analysis_type": token,
                    "provider": provider,
                    "package_id": package_id,
                    "package_version": package_version,
                    "library_provider": provider,
                    "library_package": package_id,
                    "library_version": package_version,
                    "priority": int(package.get("priority") or entry.get("priority") or 0),
                    "source_url": str(entry.get("source_url") or package.get("source_url") or "").strip(),
                    "attribution": str(entry.get("attribution") or package.get("attribution") or "").strip(),
                    "license_name": str(entry.get("license_name") or package.get("license_name") or "").strip(),
                    "axis": axis,
                    "signal": signal,
                    "demo_reference": True,
                }
            )
    references.sort(
        key=lambda item: (
            -int(item.get("priority") or 0),
            str(item.get("provider") or ""),
            str(item.get("candidate_id") or ""),
        )
    )
    return references
