"""Normalize OpenSpecy spectra into tooling-only reference-library packages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.library_ingest.common import BUILD_ROOT, today_version_token, utcnow_iso
from tools.library_ingest.providers import emit_grouped_packages, load_openspecy_records, normalize_openspecy_record


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize OpenSpecy records into intermediate package_spec.json + entries.jsonl outputs.")
    parser.add_argument("--input-json", help="Recorded OpenSpecy JSON/JSONL fixture with axis/signal arrays.")
    parser.add_argument("--input-rds", help="Raw OpenSpecy RDS file. Requires pyreadr.")
    parser.add_argument("--analysis-type", action="append", default=[], help="Optional modality filter (FTIR and/or RAMAN).")
    parser.add_argument("--invert-signal", action="store_true", help="Invert spectral intensity before normalization.")
    parser.add_argument("--output-root", default=str(BUILD_ROOT), help="Normalized output root. Provider packages are written beneath this directory.")
    parser.add_argument("--generated-at", default=utcnow_iso(), help="ISO-8601 generation timestamp for emitted packages.")
    parser.add_argument("--provider-dataset-version", default=today_version_token(), help="Version token recorded in package_spec.json.")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Maximum entries per emitted normalized package.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    records = load_openspecy_records(input_json=args.input_json, input_rds=args.input_rds)
    if not records:
        raise SystemExit("Provide --input-json or --input-rds.")

    allowed_types = {token.strip().upper() for token in args.analysis_type if token.strip()}
    grouped: dict[str, list[dict]] = {}
    processed_count = 0
    for record in records:
        analysis_type, entry = normalize_openspecy_record(
            record,
            generated_at=args.generated_at,
            provider_dataset_version=args.provider_dataset_version,
            invert_signal=bool(args.invert_signal),
        )
        if allowed_types and analysis_type not in allowed_types:
            continue
        grouped.setdefault(analysis_type, []).append(entry)
        processed_count += 1
    if not grouped:
        raise SystemExit("No OpenSpecy records matched the requested analysis types.")

    package_ids = emit_grouped_packages(
        provider_id="openspecy",
        output_root=args.output_root,
        generated_at=args.generated_at,
        provider_dataset_version=args.provider_dataset_version,
        chunk_size=int(args.chunk_size),
        entries_by_analysis_type=grouped,
    )
    print(json.dumps({"provider": "openspecy", "package_ids": package_ids, "processed_count": processed_count}, indent=2))


if __name__ == "__main__":
    main()
