"""Build a curated reference-library mirror from normalized source specs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.reference_library import build_reference_library_package
from tools.library_ingest.common import iter_normalized_packages, normalized_package_dirs


DEFAULT_LEGACY_SOURCE = Path("sample_data") / "reference_library_seed.json"
DEFAULT_NORMALIZED_ROOT = Path("build") / "reference_library_ingest"
DEFAULT_OUTPUT_ROOT = Path("build") / "reference_library_mirror"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build MaterialScope reference-library mirror packages.")
    parser.add_argument(
        "--normalized-root",
        default=str(DEFAULT_NORMALIZED_ROOT),
        help="Primary input root containing provider package_spec.json + entries.jsonl directories.",
    )
    parser.add_argument(
        "--source",
        default=str(DEFAULT_LEGACY_SOURCE),
        help="Legacy normalized seed/source JSON file. Used when --normalized-root has no package outputs.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Destination directory for the generated mirror.",
    )
    return parser.parse_args(argv)


def _manifest_etag(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _seed_from_normalized_root(normalized_root: Path) -> dict[str, Any]:
    packages: list[dict[str, Any]] = []
    generated_at_values: list[str] = []
    for spec, entries in iter_normalized_packages(normalized_root):
        generated_at_values.append(spec.generated_at)
        packages.append(
            {
                **spec.to_dict(),
                "entries": entries,
            }
        )
    packages.sort(
        key=lambda item: (
            str(item.get("provider") or "").lower(),
            str(item.get("analysis_type") or "").upper(),
            str(item.get("package_id") or "").lower(),
        )
    )
    generated_at = max((value for value in generated_at_values if value), default="")
    return {"generated_at": generated_at, "packages": packages}


def _load_seed(args: argparse.Namespace) -> dict[str, Any]:
    normalized_root = Path(args.normalized_root).resolve()
    if normalized_package_dirs(normalized_root):
        return _seed_from_normalized_root(normalized_root)

    source_path = Path(args.source).resolve()
    return json.loads(source_path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    output_root = Path(args.output).resolve()
    seed = _load_seed(args)

    output_root.mkdir(parents=True, exist_ok=True)
    packages_root = output_root / "packages"
    packages_root.mkdir(parents=True, exist_ok=True)

    provider_rows: dict[str, dict] = {}
    manifest_packages: list[dict] = []
    for package in seed.get("packages") or []:
        package_id = str(package.get("package_id") or "").strip()
        version = str(package.get("version") or "").strip()
        archive_name = f"{package_id}-{version}.zip"
        archive_path = packages_root / archive_name
        sha256 = build_reference_library_package(
            output_path=archive_path,
            package_metadata={
                "package_id": package_id,
                "analysis_type": package.get("analysis_type"),
                "provider": package.get("provider"),
                "version": version,
                "source_url": package.get("source_url") or "",
                "license_name": package.get("license_name") or "",
                "license_text": package.get("license_text") or "",
                "attribution": package.get("attribution") or "",
                "priority": package.get("priority") or 0,
                "published_at": package.get("published_at") or seed.get("generated_at") or "",
                "generated_at": package.get("generated_at") or seed.get("generated_at") or "",
                "provider_dataset_version": package.get("provider_dataset_version") or "",
                "builder_version": package.get("builder_version") or "",
                "normalized_schema_version": package.get("normalized_schema_version") or 1,
            },
            entries=package.get("entries") or [],
        )
        provider_name = str(package.get("provider") or "").strip()
        provider_key = provider_name.lower().replace(" ", "_")
        provider = provider_rows.setdefault(
            provider_key,
            {
                "provider_id": provider_key,
                "name": provider_name,
                "modalities": [],
                "source_url": package.get("source_url") or "",
                "license_name": package.get("license_name") or "",
                "license_text": package.get("license_text") or "",
                "attribution": package.get("attribution") or "",
            },
        )
        analysis_type = str(package.get("analysis_type") or "").upper()
        if analysis_type and analysis_type not in provider["modalities"]:
            provider["modalities"].append(analysis_type)
        manifest_packages.append(
            {
                "package_id": package_id,
                "analysis_type": package.get("analysis_type"),
                "provider": package.get("provider"),
                "version": version,
                "archive_name": archive_name,
                "sha256": sha256,
                "entry_count": len(package.get("entries") or []),
                "source_url": package.get("source_url") or "",
                "license_name": package.get("license_name") or "",
                "license_text": package.get("license_text") or "",
                "attribution": package.get("attribution") or "",
                "priority": package.get("priority") or 0,
                "published_at": package.get("published_at") or seed.get("generated_at") or "",
                "generated_at": package.get("generated_at") or seed.get("generated_at") or "",
                "provider_dataset_version": package.get("provider_dataset_version") or "",
                "builder_version": package.get("builder_version") or "",
                "normalized_schema_version": package.get("normalized_schema_version") or 1,
            }
        )

    manifest = {
        "schema_version": 1,
        "generated_at": seed.get("generated_at"),
        "providers": sorted(provider_rows.values(), key=lambda item: item["name"].lower()),
        "packages": manifest_packages,
    }
    manifest["etag"] = _manifest_etag(manifest)
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
