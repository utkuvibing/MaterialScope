"""Helpers for Dash import preview and column mapping."""

from __future__ import annotations

import base64
import io
import os
from typing import Any

import pandas as pd

from core.data_io import (
    detect_file_format,
    guess_columns,
    list_excel_sheets,
    load_xrd_measured_preview,
)


def decode_base64_content(content_string: str) -> bytes:
    return base64.b64decode(content_string.encode("ascii"))


def load_raw_preview_dataframe(
    file_name: str,
    file_bytes: bytes,
    sheet_name: str | None = None,
    modality: str | None = None,
) -> pd.DataFrame:
    # Measured XRD patterns (e.g. .xy) carry comment/metadata lines that the
    # generic header-sniffer mistakes for a header row; use the XRD-aware
    # parser so the mapping step sees the real numeric columns.
    xrd_preview = load_xrd_measured_preview(file_name, file_bytes, data_type=modality)
    if xrd_preview is not None:
        return xrd_preview[0]

    source = io.BytesIO(file_bytes)
    source.name = file_name

    raw_ext = os.path.splitext(file_name)[1].lower()
    if raw_ext in (".xlsx", ".xls"):
        selected: str | int = sheet_name if sheet_name else 0
        df = pd.read_excel(source, sheet_name=selected)
        if all(isinstance(col, int) for col in df.columns):
            df.columns = [f"Column {index + 1}" for index in range(len(df.columns))]
        return df

    fmt = detect_file_format(source)
    source.seek(0)
    delimiter = fmt.get("delimiter", ",")
    sep = r"\s+" if delimiter == " " else delimiter
    header = fmt.get("header_row", 0)
    encoding = str(fmt.get("encoding") or "utf-8")
    # The fallback decode is annotated ("utf-8 (with replacements)") which
    # is not a real codec name; read_csv needs the plain codec.
    if "(" in encoding:
        encoding = encoding.split("(", 1)[0].strip() or "utf-8"
    thousands = fmt.get("thousands_sep")

    try:
        df = pd.read_csv(
            source,
            sep=sep,
            header=header,
            encoding=encoding,
            thousands=thousands,
            engine="python",
            skip_blank_lines=True,
        )
    except Exception:
        source.seek(0)
        df = pd.read_csv(
            source,
            sep=r"\s+",
            header=None,
            encoding=encoding,
            engine="python",
            skip_blank_lines=True,
        )
    else:
        numeric_headers = sum(
            1 for col in df.columns
            if pd.to_numeric(pd.Series([col]), errors="coerce").notna().all()
        )
        if len(df.columns) <= 3 and numeric_headers == len(df.columns):
            source.seek(0)
            df = pd.read_csv(
                source,
                sep=r"\s+",
                header=None,
                encoding=encoding,
                engine="python",
                skip_blank_lines=True,
            )

    if all(isinstance(col, int) for col in df.columns):
        df.columns = [f"Column {index + 1}" for index in range(len(df.columns))]
    return df


def build_import_preview(
    file_name: str,
    content_string: str,
    modality: str | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    file_bytes = decode_base64_content(content_string)

    # For workbooks, enumerate sheets so the wizard can offer a picker.
    sheet_names: list[str] = []
    raw_ext = os.path.splitext(file_name)[1].lower()
    if raw_ext in (".xlsx", ".xls"):
        source = io.BytesIO(file_bytes)
        source.name = file_name
        try:
            sheet_names = list_excel_sheets(source)
        except Exception:
            sheet_names = []
        if sheet_name not in sheet_names:
            sheet_name = sheet_names[0] if sheet_names else None

    xrd_preview = load_xrd_measured_preview(file_name, file_bytes, data_type=modality)
    if xrd_preview is not None:
        frame, xrd_wavelength = xrd_preview
    else:
        frame = load_raw_preview_dataframe(file_name, file_bytes, sheet_name=sheet_name, modality=modality)
        xrd_wavelength = None
    guessed = guess_columns(frame, source_name=file_name, modality=modality)
    preview = frame.head(20).copy().where(pd.notna(frame.head(20)), None)
    payload: dict[str, Any] = {
        "file_name": file_name,
        "file_base64": content_string,
        "columns": [str(column) for column in frame.columns],
        "preview_rows": preview.to_dict(orient="records"),
        "guessed_mapping": guessed,
        "row_count": len(frame),
        "sheet_names": sheet_names,
        "sheet_name": sheet_name,
    }
    if xrd_preview is not None:
        payload["xrd_wavelength_angstrom"] = xrd_wavelength
        payload["xrd_wavelength_source"] = "parsed" if xrd_wavelength is not None else None
    return payload
