"""Normalize ROD spectral records into tooling-only reference-library packages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.library_ingest.common import BUILD_ROOT, read_json_records, today_version_token, utcnow_iso
from tools.library_ingest.providers import emit_grouped_packages, normalize_rod_record


def _read_ids(path: str | Path | None) -> list[str]:
    if not path:
        return []
    return [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize ROD records into intermediate package_spec.json + entries.jsonl outputs.")
    parser.add_argument("--manifest", help="JSON/JSONL file containing ROD records with source_id and optional jcamp_path/jcamp_url/jcamp.")
    parser.add_argument("--source-id", action="append", default=[], help="ROD source id to fetch via the default JCAMP URL template.")
    parser.add_argument("--source-ids-file", help="Text file containing one ROD source id per line.")
    parser.add_argument("--analysis-type", default="RAMAN", help="Spectral modality recorded in emitted package specs.")
    parser.add_argument("--invert-signal", action="store_true", help="Invert spectral intensity before normalization.")
    parser.add_argument("--output-root", default=str(BUILD_ROOT), help="Normalized output root. Provider packages are written beneath this directory.")
    parser.add_argument("--generated-at", default=utcnow_iso(), help="ISO-8601 generation timestamp for emitted packages.")
    parser.add_argument("--provider-dataset-version", default=today_version_token(), help="Version token recorded in package_spec.json.")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Maximum entries per emitted normalized package.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    records: list[dict] = []
    if args.manifest:
        records.extend(read_json_records(args.manifest))
    records.extend({"source_id": source_id} for source_id in [*args.source_id, *_read_ids(args.source_ids_file)])
    if not records:
        raise SystemExit("Provide --manifest or at least one --source-id.")

    grouped: dict[str, list[dict]] = {}
    for record in sorted(records, key=lambda item: str(item.get("source_id") or item.get("id") or "")):
        analysis_type, entry = normalize_rod_record(
            record,
            generated_at=args.generated_at,
            provider_dataset_version=args.provider_dataset_version,
            default_analysis_type=args.analysis_type,
            invert_signal=bool(args.invert_signal),
        )
        grouped.setdefault(analysis_type, []).append(entry)

    package_ids = emit_grouped_packages(
        provider_id="rod",
        output_root=args.output_root,
        generated_at=args.generated_at,
        provider_dataset_version=args.provider_dataset_version,
        chunk_size=int(args.chunk_size),
        entries_by_analysis_type=grouped,
    )
    print(json.dumps({"provider": "rod", "package_ids": package_ids, "processed_count": sum(len(value) for value in grouped.values())}, indent=2))


if __name__ == "__main__":
    main()
