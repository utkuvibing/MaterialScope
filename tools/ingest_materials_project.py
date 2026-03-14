"""Normalize Materials Project structures into tooling-only reference-library packages."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.library_ingest.common import BUILD_ROOT, read_json_records, today_version_token, utcnow_iso
from tools.library_ingest.providers import (
    XRDPatternOptions,
    emit_grouped_packages,
    fetch_materials_project_records,
    normalize_materials_project_record,
)


def _read_ids(path: str | Path | None) -> list[str]:
    if not path:
        return []
    return [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize Materials Project structures into intermediate package_spec.json + entries.jsonl outputs.")
    parser.add_argument("--input-json", help="Recorded Materials Project JSON fixture with material_id plus structure or structure_cif fields.")
    parser.add_argument("--material-id", action="append", default=[], help="Materials Project material id to fetch live via the mp-api client.")
    parser.add_argument("--material-ids-file", help="Text file containing one Materials Project material id per line.")
    parser.add_argument("--api-key", help="Materials Project API key. Falls back to MP_API_KEY if omitted.")
    parser.add_argument("--output-root", default=str(BUILD_ROOT), help="Normalized output root. Provider packages are written beneath this directory.")
    parser.add_argument("--generated-at", default=utcnow_iso(), help="ISO-8601 generation timestamp for emitted packages.")
    parser.add_argument("--provider-dataset-version", default=today_version_token(), help="Version token recorded in package_spec.json.")
    parser.add_argument("--chunk-size", type=int, default=500, help="Maximum entries per emitted normalized package.")
    parser.add_argument("--wavelength-angstrom", type=float, default=1.5406, help="X-ray wavelength used to calculate powder patterns.")
    parser.add_argument("--two-theta-min", type=float, default=5.0, help="Lower two-theta bound for emitted peaks.")
    parser.add_argument("--two-theta-max", type=float, default=90.0, help="Upper two-theta bound for emitted peaks.")
    parser.add_argument("--min-relative-intensity", type=float, default=0.01, help="Discard peaks below this normalized intensity threshold.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    records: list[dict] = []
    if args.input_json:
        records.extend(read_json_records(args.input_json))

    requested_ids = [*args.material_id, *_read_ids(args.material_ids_file)]
    api_key = (args.api_key or os.getenv("MP_API_KEY") or "").strip()
    if requested_ids:
        if not api_key:
            raise SystemExit("Materials Project live ingest requires --api-key or MP_API_KEY.")
        records.extend(fetch_materials_project_records(api_key=api_key, material_ids=requested_ids))

    if not records:
        raise SystemExit("Provide --input-json or at least one --material-id.")

    options = XRDPatternOptions(
        wavelength_angstrom=float(args.wavelength_angstrom),
        two_theta_min=float(args.two_theta_min),
        two_theta_max=float(args.two_theta_max),
        min_relative_intensity=float(args.min_relative_intensity),
    )
    normalized_entries = [
        normalize_materials_project_record(
            record,
            generated_at=args.generated_at,
            provider_dataset_version=args.provider_dataset_version,
            options=options,
        )
        for record in sorted(records, key=lambda item: str(item.get("material_id") or item.get("source_id") or item.get("id") or ""))
    ]
    package_ids = emit_grouped_packages(
        provider_id="materials_project",
        output_root=args.output_root,
        generated_at=args.generated_at,
        provider_dataset_version=args.provider_dataset_version,
        chunk_size=int(args.chunk_size),
        entries_by_analysis_type={"XRD": normalized_entries},
    )
    print(json.dumps({"provider": "materials_project", "package_ids": package_ids, "processed_count": len(normalized_entries)}, indent=2))


if __name__ == "__main__":
    main()
