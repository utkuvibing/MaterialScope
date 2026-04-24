"""Helpers for Dash import preview and column mapping."""

from __future__ import annotations

import base64
import io
import os
from typing import Any

import pandas as pd

from core.data_io import detect_file_format, guess_columns


def decode_base64_content(content_string: str) -> bytes:
    return base64.b64decode(content_string.encode("ascii"))


def load_raw_preview_dataframe(file_name: str, file_bytes: bytes) -> pd.DataFrame:
    source = io.BytesIO(file_bytes)
    source.name = file_name

    raw_ext = os.path.splitext(file_name)[1].lower()
    if raw_ext in (".xlsx", ".xls"):
        df = pd.read_excel(source)
        if all(isinstance(col, int) for col in df.columns):
            df.columns = [f"Column {index + 1}" for index in range(len(df.columns))]
        return df

    fmt = detect_file_format(source)
    source.seek(0)
    delimiter = fmt.get("delimiter", ",")
    sep = r"\s+" if delimiter == " " else delimiter
    header = fmt.get("header_row", 0)
    encoding = fmt.get("encoding", "utf-8")

    try:
        df = pd.read_csv(
            source,
            sep=sep,
            header=header,
            encoding=encoding,
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


def build_import_preview(file_name: str, content_string: str, modality: str | None = None) -> dict[str, Any]:
    file_bytes = decode_base64_content(content_string)
    frame = load_raw_preview_dataframe(file_name, file_bytes)
    guessed = guess_columns(frame, source_name=file_name, modality=modality)
    preview = frame.head(20).copy().where(pd.notna(frame.head(20)), None)
    return {
        "file_name": file_name,
        "file_base64": content_string,
        "columns": [str(column) for column in frame.columns],
        "preview_rows": preview.to_dict(orient="records"),
        "guessed_mapping": guessed,
        "row_count": len(frame),
    }
