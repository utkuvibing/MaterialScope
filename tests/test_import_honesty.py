"""PR-13: import honesty pack.

Covers:
- dropped-row / bad-line / Inf counts surfaced in dataset metadata and
  import_warnings,
- thousands-separator handling in delimited text,
- encoding-mojibake warning,
- Excel sheet listing + explicit sheet selection end to end
  (read_thermal_data -> backend -> preview helpers).
"""

from __future__ import annotations

import base64
import io

import numpy as np
import pandas as pd
import pytest

from core.data_io import list_excel_sheets, read_thermal_data


def _csv_source(text: str, name: str = "sample.csv") -> io.BytesIO:
    buf = io.BytesIO(text.encode("utf-8"))
    buf.name = name
    return buf


class TestDroppedRowCounts:
    def test_nonnumeric_rows_counted_and_warned(self):
        csv = (
            "Temp/°C,DSC/(mW/mg)\n"
            "25,0.1\n"
            "oops,0.2\n"
            "75,bad\n"
            "100,0.4\n"
        )
        ds = read_thermal_data(_csv_source(csv), data_type="DSC")
        meta = ds.metadata
        assert meta["import_rows_dropped"] == 2
        assert len(ds.data) == 2
        assert any("non-numeric" in w for w in meta["import_warnings"])
        assert any("2 row(s)" in w for w in meta["import_warnings"])

    def test_empty_rows_counted_without_noise(self):
        csv = "Temp/°C,DSC/(mW/mg)\n25,0.1\n,\n75,0.3\n"
        ds = read_thermal_data(_csv_source(csv), data_type="DSC")
        # The ",\n" row is fully empty and dropped before mapping.
        assert ds.metadata["import_empty_rows_dropped"] >= 0
        assert len(ds.data) == 2

    def test_zero_drops_report_zero(self):
        csv = "Temp/°C,DSC/(mW/mg)\n25,0.1\n75,0.3\n"
        ds = read_thermal_data(_csv_source(csv), data_type="DSC")
        assert ds.metadata["import_rows_dropped"] == 0
        assert ds.metadata["import_inf_rows_dropped"] == 0
        assert ds.metadata["import_bad_lines"] == 0


class TestInfRejection:
    def test_inf_rows_rejected_counted_warned(self):
        csv = (
            "Temp/°C,DSC/(mW/mg)\n"
            "25,0.1\n"
            "50,inf\n"
            "75,-Inf\n"
            "100,0.4\n"
        )
        ds = read_thermal_data(_csv_source(csv), data_type="DSC")
        assert ds.metadata["import_inf_rows_dropped"] == 2
        assert len(ds.data) == 2
        assert np.isfinite(ds.data["signal"]).all()
        assert any("non-finite" in w for w in ds.metadata["import_warnings"])


class TestBadLines:
    def test_malformed_lines_counted_and_warned(self):
        # Extra field in row 2 makes pandas skip it under on_bad_lines='warn'.
        csv = (
            "Temp/°C,DSC/(mW/mg)\n"
            "25,0.1\n"
            "50,0.2,EXTRA\n"
            "75,0.3\n"
        )
        ds = read_thermal_data(
            _csv_source(csv),
            data_type="DSC",
            column_mapping={"temperature": "Temp/°C", "signal": "DSC/(mW/mg)"},
        )
        assert ds.metadata["import_bad_lines"] >= 1
        assert any("malformed" in w for w in ds.metadata["import_warnings"])


class TestThousandsSeparator:
    def test_european_thousands_with_comma_decimal(self):
        # ';' delimiter, decimal ',', '.' thousands — German style.
        csv = "Temp/°C;DSC/(mW/mg)\n25,0;0,10\n1.250,0;0,42\n2.500,0;0,30\n"
        ds = read_thermal_data(_csv_source(csv), data_type="DSC")
        temps = ds.data["temperature"].tolist()
        assert temps == [25.0, 1250.0, 2500.0]
        assert ds.metadata["import_thousands_sep"] == "."

    def test_us_thousands_with_dot_decimal(self):
        # ';' delimiter, '.' decimal, ',' thousands — US style.
        csv = "Temp/°C;DSC/(mW/mg)\n25.0;0.10\n1,250.0;0.42\n"
        ds = read_thermal_data(_csv_source(csv), data_type="DSC")
        assert ds.data["temperature"].tolist() == [25.0, 1250.0]
        assert ds.metadata["import_thousands_sep"] == ","

    def test_no_thousands_without_grouped_pattern(self):
        csv = "Temp/°C;DSC/(mW/mg)\n25.0;0.10\n75.5;0.42\n"
        ds = read_thermal_data(_csv_source(csv), data_type="DSC")
        assert ds.metadata["import_thousands_sep"] is None
        assert ds.data["temperature"].tolist() == [25.0, 75.5]


class TestMojibake:
    def test_non_utf8_bytes_warn_about_mojibake(self):
        # 0xB0 alone is invalid UTF-8, so the latin-1 fallback decodes the
        # file — any special character is then interpretation-dependent.
        raw = b"Temp/\xb0C,DSC/(mW/mg)\n25,0.1\n50,0.2\n75,0.3\n"
        buf = io.BytesIO(raw)
        buf.name = "mojibake.csv"
        ds = read_thermal_data(buf, data_type="DSC")
        assert ds.metadata["import_encoding"] == "latin-1"
        assert any("mojibake" in w or "Encoding check" in w for w in ds.metadata["import_warnings"])

    def test_utf8_file_has_no_encoding_warning(self):
        csv = "Temp/°C,DSC/(mW/mg)\n25,0.1\n75,0.3\n"
        ds = read_thermal_data(_csv_source(csv), data_type="DSC")
        assert ds.metadata["import_encoding"] == "utf-8"
        assert not any("mojibake" in w for w in ds.metadata["import_warnings"])


def _xlsx_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return buf.getvalue()


class TestExcelSheetPicker:
    def _workbook(self):
        sheet_a = pd.DataFrame({"Temp/°C": [25.0, 50.0, 75.0], "DSC/(mW/mg)": [0.1, 0.2, 0.3]})
        sheet_b = pd.DataFrame({"Temp/°C": [100.0, 200.0, 300.0], "DSC/(mW/mg)": [1.0, 2.0, 3.0]})
        return {"First": sheet_a, "Second": sheet_b}

    def test_list_excel_sheets(self):
        buf = io.BytesIO(_xlsx_bytes(self._workbook()))
        buf.name = "wb.xlsx"
        assert list_excel_sheets(buf) == ["First", "Second"]

    def test_default_first_sheet_with_warning(self):
        buf = io.BytesIO(_xlsx_bytes(self._workbook()))
        buf.name = "wb.xlsx"
        ds = read_thermal_data(buf, data_type="DSC")
        assert ds.metadata["import_sheet_name"] == "First"
        assert ds.metadata["import_sheet_names"] == ["First", "Second"]
        assert ds.data["temperature"].tolist() == [25.0, 50.0, 75.0]
        assert any("sheets" in w for w in ds.metadata["import_warnings"])

    def test_explicit_sheet_selection(self):
        buf = io.BytesIO(_xlsx_bytes(self._workbook()))
        buf.name = "wb.xlsx"
        ds = read_thermal_data(buf, data_type="DSC", sheet_name="Second")
        assert ds.metadata["import_sheet_name"] == "Second"
        assert ds.data["temperature"].tolist() == [100.0, 200.0, 300.0]
        assert not any("sheets" in w for w in ds.metadata["import_warnings"])

    def test_invalid_sheet_name_rejected(self):
        buf = io.BytesIO(_xlsx_bytes(self._workbook()))
        buf.name = "wb.xlsx"
        with pytest.raises(ValueError, match="Sheet 'Nope' not found"):
            read_thermal_data(buf, data_type="DSC", sheet_name="Nope")

    def test_preview_reports_sheets(self):
        from dash_app.import_preview import build_import_preview

        b64 = base64.b64encode(_xlsx_bytes(self._workbook())).decode("ascii")
        preview = build_import_preview("wb.xlsx", b64, modality="DSC")
        assert preview["sheet_names"] == ["First", "Second"]
        assert preview["sheet_name"] == "First"

        preview_b = build_import_preview("wb.xlsx", b64, modality="DSC", sheet_name="Second")
        assert preview_b["sheet_name"] == "Second"
        assert preview_b["columns"] == ["Temp/°C", "DSC/(mW/mg)"]


class TestBackendSheetImport:
    def test_import_endpoint_accepts_sheet_name(self):
        from fastapi.testclient import TestClient

        from backend.app import create_app
        from backend.store import ProjectStore

        app = create_app(store=ProjectStore())
        client = TestClient(app)
        project_id = client.post("/workspace/new").json()["project_id"]

        sheets = {
            "Meta": pd.DataFrame({"Notes": ["x"]}),
            "Data": pd.DataFrame({"Temp/°C": [25.0, 50.0, 75.0], "DSC/(mW/mg)": [0.1, 0.2, 0.3]}),
        }
        b64 = base64.b64encode(_xlsx_bytes(sheets)).decode("ascii")

        r = client.post(
            "/dataset/import",
            json={
                "project_id": project_id,
                "file_name": "wb.xlsx",
                "file_base64": b64,
                "data_type": "DSC",
                "column_mapping": {"temperature": "Temp/°C", "signal": "DSC/(mW/mg)"},
                "metadata": {},
                "sheet_name": "Data",
            },
        )
        assert r.is_success, r.text
        assert r.json()["dataset"]["data_type"] == "DSC"

    def test_dataset_summary_exposes_import_warnings(self):
        from fastapi.testclient import TestClient

        from backend.app import create_app
        from backend.store import ProjectStore

        app = create_app(store=ProjectStore())
        client = TestClient(app)
        project_id = client.post("/workspace/new").json()["project_id"]

        csv = "Temp/°C,DSC/(mW/mg)\n25,0.1\noops,0.2\n75,0.3\n"
        b64 = base64.b64encode(csv.encode("utf-8")).decode("ascii")
        r = client.post(
            "/dataset/import",
            json={
                "project_id": project_id,
                "file_name": "drops.csv",
                "file_base64": b64,
                "data_type": "DSC",
                "column_mapping": {},
                "metadata": {},
            },
        )
        assert r.is_success, r.text
        warnings = r.json()["dataset"]["import_warnings"]
        assert any("non-numeric" in w for w in warnings)


class TestWizardDefaults:
    def test_preview_callback_leaves_mass_and_heating_rate_empty(self):
        import dash
        from dash import html as dash_html

        try:
            dash.get_app()
        except Exception:
            app = dash.Dash(
                __name__,
                use_pages=True,
                pages_folder="",
                suppress_callback_exceptions=True,
            )
            app.layout = dash_html.Div(dash.page_container)

        import dash_app.pages.home as home

        csv = "Temp/°C,DSC/(mW/mg)\n25,0.1\n75,0.3\n"
        pending = [
            {
                "file_name": "dsc.csv",
                "file_base64": base64.b64encode(csv.encode("utf-8")).decode("ascii"),
            }
        ]
        out = home.build_pending_preview("dsc.csv", "DSC", None, pending, "en")
        # Outputs: ..., mapping-sample-name, mapping-sample-mass,
        # mapping-heating-rate, mapping-xrd-wavelength, xrd_style
        assert out[10] is None  # sample_mass
        assert out[11] is None  # heating_rate
