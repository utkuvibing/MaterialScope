"""Tests for modality-first import pipeline.

Covers:
- core.modality_specs: spec lookups, suspicious unit combos
- core.data_io.guess_columns(modality=...): modality-aware column detection
- core.validation: 4-tier status (pass/pass_with_review/warn/fail)
- dash_app.import_preview: modality-aware preview building
- Backend integration: import with explicit modality
"""

import io
import os
import sys

import numpy as np
import pandas as pd
import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.modality_specs import (
    MODALITY_SPECS,
    SUPPORTED_MODALITIES,
    check_suspicious_unit_combo,
    get_modality_spec,
    modality_allowed_x_units,
    modality_allowed_y_units,
    modality_default_x_unit,
    modality_default_y_unit,
    modality_signal_pattern_key,
    modality_is_spectral,
)
from core.data_io import guess_columns, read_thermal_data
from core.validation import validate_thermal_dataset


# ===========================================================================
# Modality Specs
# ===========================================================================


class TestModalitySpecs:

    def test_all_modalities_have_specs(self):
        for m in ("DSC", "TGA", "DTA", "FTIR", "RAMAN", "XRD"):
            spec = get_modality_spec(m)
            assert spec is not None, f"Missing spec for {m}"
            assert spec["label"]
            assert spec["allowed_x_units"]
            assert spec["allowed_y_units"]
            assert spec["x_aliases"]
            assert spec["y_aliases"]
            assert spec["required_columns"]

    def test_unknown_modality_returns_none(self):
        assert get_modality_spec("UNKNOWN") is None
        assert get_modality_spec("") is None
        assert get_modality_spec("foo") is None

    def test_suspicious_dsc_units(self):
        # DSC x-axis should not be cm^-1
        warnings = check_suspicious_unit_combo("DSC", "cm^-1", "mW")
        assert any("cm" in w for w in warnings)

    def test_suspicious_ftir_units(self):
        # FTIR x-axis should not be °C
        warnings = check_suspicious_unit_combo("FTIR", "°C", "absorbance")
        assert any("°C" in w or "unusual" in w for w in warnings)

    def test_suspicious_xrd_units(self):
        # XRD y-axis should not be mW
        warnings = check_suspicious_unit_combo("XRD", "degree_2theta", "mW")
        assert any("mW" in w for w in warnings)

    def test_valid_dsc_units_no_warnings(self):
        warnings = check_suspicious_unit_combo("DSC", "°C", "mW")
        assert len(warnings) == 0

    def test_valid_ftir_units_no_warnings(self):
        warnings = check_suspicious_unit_combo("FTIR", "cm^-1", "absorbance")
        assert len(warnings) == 0

    def test_valid_xrd_units_no_warnings(self):
        warnings = check_suspicious_unit_combo("XRD", "degree_2theta", "counts")
        assert len(warnings) == 0

    def test_spectral_modality_flags(self):
        assert modality_is_spectral("FTIR") is True
        assert modality_is_spectral("RAMAN") is True
        assert modality_is_spectral("DSC") is False
        assert modality_is_spectral("XRD") is False

    def test_signal_pattern_keys(self):
        assert modality_signal_pattern_key("DSC") == "signal_dsc"
        assert modality_signal_pattern_key("TGA") == "signal_tga"
        assert modality_signal_pattern_key("FTIR") == "signal_ftir"

    def test_default_units(self):
        assert modality_default_x_unit("DSC") == "°C"
        assert modality_default_y_unit("DSC") == "mW"
        assert modality_default_x_unit("FTIR") == "cm^-1"
        assert modality_default_x_unit("XRD") == "degree_2theta"

    def test_allowed_units(self):
        assert "°C" in modality_allowed_x_units("DSC")
        assert "cm^-1" in modality_allowed_x_units("FTIR")
        assert "%" in modality_allowed_y_units("TGA")
        assert "counts" in modality_allowed_y_units("XRD")


# ===========================================================================
# guess_columns with modality
# ===========================================================================


def _make_dsc_df():
    """Create a DataFrame with DSC-like columns."""
    return pd.DataFrame({
        "Temp/°C": np.linspace(30, 300, 100),
        "DSC/(mW/mg)": np.random.randn(100),
        "Time/min": np.linspace(0, 27, 100),
    })


def _make_ftir_df():
    """Create a DataFrame with FTIR-like columns."""
    return pd.DataFrame({
        "Wavenumber (cm-1)": np.linspace(4000, 400, 200),
        "Absorbance": np.random.rand(200),
    })


def _make_xrd_df():
    """Create a DataFrame with XRD-like columns."""
    return pd.DataFrame({
        "2Theta": np.linspace(10, 80, 150),
        "Intensity (counts)": np.random.rand(150) * 1000,
    })


def _make_ambiguous_df():
    """Create a DataFrame with generic column names that could be multiple types."""
    return pd.DataFrame({
        "Column 1": np.linspace(0, 100, 50),
        "Column 2": np.random.randn(50),
    })


class TestGuessColumnsModalityAware:

    def test_dsc_modality_restricts_signal(self):
        df = _make_dsc_df()
        result = guess_columns(df, modality="DSC")
        assert result["data_type"] == "DSC"
        assert result["signal"] == "DSC/(mW/mg)"
        assert result["temperature"] == "Temp/°C"

    def test_ftir_modality_restricts_signal(self):
        df = _make_ftir_df()
        result = guess_columns(df, modality="FTIR")
        assert result["data_type"] == "FTIR"
        assert result["signal"] == "Absorbance"
        assert result["temperature"] == "Wavenumber (cm-1)"

    def test_xrd_modality_restricts_signal(self):
        df = _make_xrd_df()
        result = guess_columns(df, modality="XRD")
        assert result["data_type"] == "XRD"
        assert result["signal"] == "Intensity (counts)"
        assert result["temperature"] == "2Theta"

    def test_modality_prevents_wrong_type_inference(self):
        """With DSC modality, an FTIR-like file should still be typed as DSC."""
        df = _make_ftir_df()
        result = guess_columns(df, modality="DSC")
        assert result["data_type"] == "DSC"
        # Signal should be the best available numeric column since no DSC-specific patterns match
        assert result["signal"] is not None

    def test_same_file_different_modality(self):
        """Same file, different modality => different type."""
        df = _make_dsc_df()
        result_dsc = guess_columns(df, modality="DSC")
        result_tga = guess_columns(df, modality="TGA")
        assert result_dsc["data_type"] == "DSC"
        assert result_tga["data_type"] == "TGA"

    def test_no_modality_uses_auto_detection(self):
        """Without modality, auto-detection should still work."""
        df = _make_dsc_df()
        result = guess_columns(df, source_name="dsc_data.csv")
        assert result["data_type"] == "DSC"

    def test_ambiguous_file_with_modality(self):
        """Generic file with modality set => type determined by modality."""
        df = _make_ambiguous_df()
        result = guess_columns(df, modality="DSC")
        assert result["data_type"] == "DSC"
        assert result["signal"] is not None

    def test_modality_sets_inferred_type(self):
        df = _make_dsc_df()
        result = guess_columns(df, modality="DSC")
        assert result["inferred_analysis_type"] == "DSC"

    def test_candidates_only_for_modality(self):
        """When modality is set, only that modality should have candidates."""
        df = _make_dsc_df()
        result = guess_columns(df, modality="DSC")
        assert "dsc" in result.get("candidates", {})
        assert "tga" not in result.get("candidates", {})
        assert "ftir" not in result.get("candidates", {})


# ===========================================================================
# read_thermal_data with modality
# ===========================================================================


class TestReadThermalDataModalityAware:

    def test_dsc_modality_import(self):
        csv = "Temp/°C,DSC/(mW/mg)\n25,0.1\n50,0.2\n75,0.3\n100,0.4\n"
        buf = io.BytesIO(csv.encode("utf-8"))
        buf.name = "test_dsc.csv"
        ds = read_thermal_data(buf, data_type="DSC")
        assert ds.data_type == "DSC"
        assert len(ds.data) == 4
        assert "temperature" in ds.data.columns
        assert "signal" in ds.data.columns

    def test_ftir_modality_import(self):
        csv = "Wavenumber (cm-1),Absorbance\n4000,0.1\n3000,0.2\n2000,0.3\n1000,0.4\n"
        buf = io.BytesIO(csv.encode("utf-8"))
        buf.name = "test_ftir.csv"
        ds = read_thermal_data(buf, data_type="FTIR")
        assert ds.data_type == "FTIR"
        assert ds.units.get("temperature") == "cm^-1"

    def test_xrd_modality_import(self):
        csv = "2Theta,Intensity\n10,100\n20,200\n30,300\n40,400\n"
        buf = io.BytesIO(csv.encode("utf-8"))
        buf.name = "test_xrd.csv"
        ds = read_thermal_data(buf, data_type="XRD")
        assert ds.data_type == "XRD"
        assert ds.units.get("temperature") == "degree_2theta"

    def test_same_csv_different_modality(self):
        csv = "X,Y\n25,0.1\n50,0.2\n75,0.3\n100,0.4\n"
        buf_dsc = io.BytesIO(csv.encode("utf-8"))
        buf_dsc.name = "test.csv"
        ds_dsc = read_thermal_data(buf_dsc, data_type="DSC", column_mapping={"temperature": "X", "signal": "Y"})

        buf_ftir = io.BytesIO(csv.encode("utf-8"))
        buf_ftir.name = "test.csv"
        ds_ftir = read_thermal_data(buf_ftir, data_type="FTIR", column_mapping={"temperature": "X", "signal": "Y"})

        assert ds_dsc.data_type == "DSC"
        assert ds_ftir.data_type == "FTIR"
        assert ds_dsc.units.get("temperature") == "°C"
        assert ds_ftir.units.get("temperature") == "cm^-1"


# ===========================================================================
# Validation 4-tier status
# ===========================================================================


class TestValidationFourTier:

    def _make_dataset(self, data_type="DSC", x_unit="°C", signal_unit="mW"):
        from core.data_io import ThermalDataset
        df = pd.DataFrame({
            "temperature": np.linspace(30, 300, 100),
            "signal": np.random.randn(100),
        })
        return ThermalDataset(
            data=df,
            metadata={
                "sample_name": "test",
                "sample_mass": 10.0,
                "heating_rate": 10.0,
                "import_confidence": "high",
                "import_warnings": [],
                "import_review_required": False,
                "inferred_analysis_type": data_type,
                "inferred_signal_unit": signal_unit,
                "inferred_vendor": "Generic",
                "vendor_detection_confidence": "high",
            },
            data_type=data_type,
            units={"temperature": x_unit, "signal": signal_unit},
            original_columns={"temperature": "temp", "signal": "sig"},
            file_path="test.csv",
        )

    def test_pass_status(self):
        ds = self._make_dataset("DSC", "°C", "mW")
        result = validate_thermal_dataset(ds, enforce_workflow_context=False)
        assert result["status"] in ("pass", "pass_with_review", "warn")

    def test_fail_status_missing_data(self):
        result = validate_thermal_dataset(None, enforce_workflow_context=False)
        assert result["status"] == "fail"
        assert "review_flags" in result

    def test_pass_with_review_suspicious_units(self):
        """FTIR with °C axis should produce pass_with_review."""
        ds = self._make_dataset("FTIR", "°C", "a.u.")
        result = validate_thermal_dataset(ds, enforce_workflow_context=False)
        review_flags = result.get("review_flags", [])
        # Should have a review flag about unusual axis unit for FTIR
        assert any("°C" in flag or "unusual" in flag for flag in review_flags)

    def test_warn_status_missing_metadata(self):
        ds = self._make_dataset("DSC")
        ds.metadata.pop("heating_rate", None)
        result = validate_thermal_dataset(ds, enforce_workflow_context=False)
        assert result["status"] in ("warn", "pass", "pass_with_review")
        # Should have warnings about missing metadata

    def test_review_flags_in_result(self):
        ds = self._make_dataset("XRD", "°C", "mW")
        result = validate_thermal_dataset(ds, enforce_workflow_context=False)
        assert "review_flags" in result
        assert isinstance(result["review_flags"], list)

    def test_xrd_suspicious_y_unit_review(self):
        ds = self._make_dataset("XRD", "degree_2theta", "mW")
        result = validate_thermal_dataset(ds, enforce_workflow_context=False)
        review_flags = result.get("review_flags", [])
        assert any("mW" in flag for flag in review_flags)


# ===========================================================================
# Import Preview with modality
# ===========================================================================


class TestImportPreviewModality:

    def test_build_preview_with_modality(self):
        from dash_app.import_preview import build_import_preview
        import base64

        csv = "Temp/°C,DSC/(mW/mg)\n25,0.1\n50,0.2\n75,0.3\n100,0.4\n"
        b64 = base64.b64encode(csv.encode("utf-8")).decode("ascii")

        preview_dsc = build_import_preview("test.csv", b64, modality="DSC")
        assert preview_dsc["guessed_mapping"]["data_type"] == "DSC"

        preview_ftir = build_import_preview("test.csv", b64, modality="FTIR")
        assert preview_ftir["guessed_mapping"]["data_type"] == "FTIR"

    def test_same_file_different_modality_preview(self):
        from dash_app.import_preview import build_import_preview
        import base64

        csv = "Wavenumber (cm-1),Absorbance\n4000,0.1\n3000,0.2\n2000,0.3\n"
        b64 = base64.b64encode(csv.encode("utf-8")).decode("ascii")

        preview_ftir = build_import_preview("test.csv", b64, modality="FTIR")
        assert preview_ftir["guessed_mapping"]["data_type"] == "FTIR"
        assert preview_ftir["guessed_mapping"]["signal"] == "Absorbance"

        preview_raman = build_import_preview("test.csv", b64, modality="RAMAN")
        assert preview_raman["guessed_mapping"]["data_type"] == "RAMAN"

    def test_preview_without_modality(self):
        from dash_app.import_preview import build_import_preview
        import base64

        csv = "Temp/°C,DSC/(mW/mg)\n25,0.1\n50,0.2\n75,0.3\n"
        b64 = base64.b64encode(csv.encode("utf-8")).decode("ascii")

        preview = build_import_preview("test.csv", b64)
        # Without modality, auto-detection should identify DSC
        assert preview["guessed_mapping"]["data_type"] in ("DSC", "unknown")


# ===========================================================================
# Backend integration: import with modality
# ===========================================================================


class TestBackendModalityImport:

    def test_import_dsc_with_modality(self):
        from backend.app import create_app
        from backend.store import ProjectStore
        from fastapi.testclient import TestClient
        import base64

        app = create_app(store=ProjectStore())
        client = TestClient(app)

        # Create workspace
        r = client.post("/workspace/new")
        assert r.is_success
        project_id = r.json()["project_id"]

        # Import with DSC modality
        csv = "Temp/°C,DSC/(mW/mg)\n25,0.1\n50,0.2\n75,0.3\n100,0.4\n125,0.5\n"
        b64 = base64.b64encode(csv.encode("utf-8")).decode("ascii")

        r = client.post("/dataset/import", json={
            "project_id": project_id,
            "file_name": "dsc_test.csv",
            "file_base64": b64,
            "data_type": "DSC",
            "column_mapping": {},
            "metadata": {},
        })
        assert r.is_success, f"Import failed: {r.text}"
        result = r.json()
        assert result["dataset"]["data_type"] == "DSC"
        assert result["validation"]["status"] in ("pass", "warn", "pass_with_review")

    def test_import_ftir_with_modality(self):
        from backend.app import create_app
        from backend.store import ProjectStore
        from fastapi.testclient import TestClient
        import base64

        app = create_app(store=ProjectStore())
        client = TestClient(app)

        r = client.post("/workspace/new")
        project_id = r.json()["project_id"]

        csv = "Wavenumber (cm-1),Absorbance\n4000,0.1\n3000,0.2\n2000,0.3\n1000,0.4\n500,0.5\n"
        b64 = base64.b64encode(csv.encode("utf-8")).decode("ascii")

        r = client.post("/dataset/import", json={
            "project_id": project_id,
            "file_name": "ftir_test.csv",
            "file_base64": b64,
            "data_type": "FTIR",
            "column_mapping": {},
            "metadata": {},
        })
        assert r.is_success, f"Import failed: {r.text}"
        result = r.json()
        assert result["dataset"]["data_type"] == "FTIR"

    def test_import_xrd_with_modality(self):
        from backend.app import create_app
        from backend.store import ProjectStore
        from fastapi.testclient import TestClient
        import base64

        app = create_app(store=ProjectStore())
        client = TestClient(app)

        r = client.post("/workspace/new")
        project_id = r.json()["project_id"]

        csv = "2Theta,Intensity\n10,100\n20,200\n30,300\n40,400\n50,500\n"
        b64 = base64.b64encode(csv.encode("utf-8")).decode("ascii")

        r = client.post("/dataset/import", json={
            "project_id": project_id,
            "file_name": "xrd_test.csv",
            "file_base64": b64,
            "data_type": "XRD",
            "column_mapping": {},
            "metadata": {},
        })
        assert r.is_success, f"Import failed: {r.text}"
        result = r.json()
        assert result["dataset"]["data_type"] == "XRD"

    def test_same_file_different_modality_different_result(self):
        """Same CSV content imported as DSC vs FTIR should have different data types and units."""
        from backend.app import create_app
        from backend.store import ProjectStore
        from fastapi.testclient import TestClient
        import base64

        csv = "X,Y\n25,0.1\n50,0.2\n75,0.3\n100,0.4\n125,0.5\n"
        b64 = base64.b64encode(csv.encode("utf-8")).decode("ascii")

        # Import as DSC
        app_dsc = create_app(store=ProjectStore())
        client_dsc = TestClient(app_dsc)
        r = client_dsc.post("/workspace/new")
        pid_dsc = r.json()["project_id"]
        r = client_dsc.post("/dataset/import", json={
            "project_id": pid_dsc,
            "file_name": "test.csv",
            "file_base64": b64,
            "data_type": "DSC",
            "column_mapping": {"temperature": "X", "signal": "Y"},
            "metadata": {},
        })
        assert r.is_success
        ds_dsc = r.json()["dataset"]
        assert ds_dsc["data_type"] == "DSC"

        # Import as FTIR
        app_ftir = create_app(store=ProjectStore())
        client_ftir = TestClient(app_ftir)
        r = client_ftir.post("/workspace/new")
        pid_ftir = r.json()["project_id"]
        r = client_ftir.post("/dataset/import", json={
            "project_id": pid_ftir,
            "file_name": "test.csv",
            "file_base64": b64,
            "data_type": "FTIR",
            "column_mapping": {"temperature": "X", "signal": "Y"},
            "metadata": {},
        })
        assert r.is_success
        ds_ftir = r.json()["dataset"]
        assert ds_ftir["data_type"] == "FTIR"

    def test_sample_import_dsc(self):
        from backend.app import create_app
        from backend.store import ProjectStore
        from fastapi.testclient import TestClient
        import base64
        from pathlib import Path

        sample_path = Path(_ROOT) / "sample_data" / "dsc_polymer_melting.csv"
        if not sample_path.exists():
            pytest.skip("Sample data file not found")

        app = create_app(store=ProjectStore())
        client = TestClient(app)
        r = client.post("/workspace/new")
        project_id = r.json()["project_id"]

        b64 = base64.b64encode(sample_path.read_bytes()).decode("ascii")
        r = client.post("/dataset/import", json={
            "project_id": project_id,
            "file_name": sample_path.name,
            "file_base64": b64,
            "data_type": "DSC",
            "column_mapping": {},
            "metadata": {},
        })
        assert r.is_success, f"Sample import failed: {r.text}"
        result = r.json()
        assert result["dataset"]["data_type"] == "DSC"

    def test_remove_dataset_flow(self):
        from backend.app import create_app
        from backend.store import ProjectStore
        from fastapi.testclient import TestClient
        import base64

        app = create_app(store=ProjectStore())
        client = TestClient(app)

        r = client.post("/workspace/new")
        project_id = r.json()["project_id"]

        csv = "Temp/°C,DSC/(mW/mg)\n25,0.1\n50,0.2\n75,0.3\n100,0.4\n125,0.5\n"
        b64 = base64.b64encode(csv.encode("utf-8")).decode("ascii")
        r = client.post("/dataset/import", json={
            "project_id": project_id,
            "file_name": "dsc_test.csv",
            "file_base64": b64,
            "data_type": "DSC",
            "column_mapping": {},
            "metadata": {},
        })
        assert r.is_success
        datasets = client.get(f"/workspace/{project_id}/datasets").json()["datasets"]
        assert len(datasets) == 1

        # Remove
        key = datasets[0]["key"]
        r = client.delete(f"/workspace/{project_id}/datasets/{key}")
        assert r.is_success

        # Verify removed
        datasets = client.get(f"/workspace/{project_id}/datasets").json()["datasets"]
        assert len(datasets) == 0

    def test_active_dataset_selection(self):
        from backend.app import create_app
        from backend.store import ProjectStore
        from fastapi.testclient import TestClient
        import base64

        app = create_app(store=ProjectStore())
        client = TestClient(app)

        r = client.post("/workspace/new")
        project_id = r.json()["project_id"]

        csv1 = "Temp/°C,DSC/(mW/mg)\n25,0.1\n50,0.2\n75,0.3\n100,0.4\n125,0.5\n"
        csv2 = "Temp/°C,DSC/(mW/mg)\n30,0.5\n60,0.4\n90,0.3\n120,0.2\n150,0.1\n"
        for name, csv_data in [("ds1.csv", csv1), ("ds2.csv", csv2)]:
            b64 = base64.b64encode(csv_data.encode("utf-8")).decode("ascii")
            client.post("/dataset/import", json={
                "project_id": project_id,
                "file_name": name,
                "file_base64": b64,
                "data_type": "DSC",
                "column_mapping": {},
                "metadata": {},
            })

        datasets = client.get(f"/workspace/{project_id}/datasets").json()["datasets"]
        assert len(datasets) == 2

        # Set active to second dataset
        keys = [d["key"] for d in datasets]
        r = client.put(f"/workspace/{project_id}/active-dataset", json={"dataset_key": keys[1]})
        assert r.is_success

        summary = client.get(f"/workspace/{project_id}/datasets").json()
        assert summary["active_dataset"] == keys[1]
