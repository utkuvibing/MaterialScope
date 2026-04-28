"""Deterministic demo XRD reference fallback bundled with the app."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED_LIBRARY_PATH = PROJECT_ROOT / "sample_data" / "reference_library_seed.json"


def _normalize_peak_rows(peaks: Any) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    if not isinstance(peaks, list):
        return rows
    for item in peaks:
        if not isinstance(item, Mapping):
            continue
        try:
            position = float(item.get("position"))
            intensity = float(item.get("intensity", 1.0))
        except (TypeError, ValueError):
            continue
        peak = {"position": position, "intensity": intensity}
        if item.get("d_spacing") not in (None, ""):
            try:
                peak["d_spacing"] = float(item.get("d_spacing"))
            except (TypeError, ValueError):
                pass
        rows.append(peak)
    return rows


@lru_cache(maxsize=1)
def load_demo_xrd_references() -> list[dict[str, Any]]:
    """Load bundled seed XRD references without requiring a synced library."""
    if not SEED_LIBRARY_PATH.exists():
        return []
    try:
        payload = json.loads(SEED_LIBRARY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    references: list[dict[str, Any]] = []
    for package in payload.get("packages") or []:
        if not isinstance(package, Mapping):
            continue
        if str(package.get("analysis_type") or "").strip().upper() != "XRD":
            continue
        provider = str(package.get("provider") or "Demo XRD").strip()
        package_id = str(package.get("package_id") or "demo_xrd_seed").strip()
        package_version = str(package.get("version") or "demo").strip()
        for entry in package.get("entries") or []:
            if not isinstance(entry, Mapping):
                continue
            peaks = _normalize_peak_rows(entry.get("peaks"))
            if not peaks:
                continue
            candidate_id = str(entry.get("candidate_id") or entry.get("id") or "").strip()
            if not candidate_id:
                continue
            references.append(
                {
                    **dict(entry),
                    "candidate_id": candidate_id,
                    "candidate_name": str(entry.get("candidate_name") or entry.get("name") or candidate_id),
                    "analysis_type": "XRD",
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
                    "peaks": peaks,
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
