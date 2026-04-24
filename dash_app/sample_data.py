"""Sample data helpers for the Dash UI."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DATA_FILES: dict[str, dict[str, str]] = {
    "load-sample-dsc": {
        "label": "DSC - Polymer Melting",
        "file_name": "dsc_polymer_melting.csv",
        "data_type": "DSC",
    },
    "load-sample-tga": {
        "label": "TGA - Calcium Oxalate",
        "file_name": "tga_calcium_oxalate.csv",
        "data_type": "TGA",
    },
    "load-sample-dsc-kissinger": {
        "label": "DSC - Multi-Rate Kissinger",
        "file_name": "dsc_multirate_kissinger.csv",
        "data_type": "DSC",
    },
    "load-sample-dta": {
        "label": "DTA - TNAA (5 °C/min)",
        "file_name": "dta_tnaa_5c_mendeley.csv",
        "data_type": "DTA",
    },
    "load-sample-ftir": {
        "label": "FTIR - Particleboard",
        "file_name": "ftir_particleboard_50g_figshare.csv",
        "data_type": "FTIR",
    },
    "load-sample-raman": {
        "label": "RAMAN - CNT Spectrum",
        "file_name": "raman_cnt_figshare.csv",
        "data_type": "RAMAN",
    },
    "load-sample-xrd": {
        "label": "XRD - 2024-0304",
        "file_name": "xrd_2024_0304_zenodo.csv",
        "data_type": "XRD",
    },
}


def list_sample_specs() -> list[dict[str, str]]:
    return [{"id": key, **value} for key, value in SAMPLE_DATA_FILES.items()]


def resolve_sample_request(button_id: str) -> tuple[Path | None, str | None]:
    sample = SAMPLE_DATA_FILES.get(button_id)
    if sample is None:
        return None, None
    file_name = sample["file_name"]
    data_type = sample["data_type"]
    return REPO_ROOT / "sample_data" / file_name, data_type
