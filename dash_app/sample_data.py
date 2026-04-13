"""Sample data helpers for the Dash UI."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DATA_FILES: dict[str, tuple[str, str]] = {
    "load-sample-dsc": ("dsc_polymer_melting.csv", "DSC"),
    "load-sample-tga": ("tga_calcium_oxalate.csv", "TGA"),
}


def resolve_sample_request(button_id: str) -> tuple[Path | None, str | None]:
    sample = SAMPLE_DATA_FILES.get(button_id)
    if sample is None:
        return None, None
    file_name, data_type = sample
    return REPO_ROOT / "sample_data" / file_name, data_type
