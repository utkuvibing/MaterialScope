"""PR-10: temperature-scale gate — K-vs-°C plausibility at import/validation.

A Kelvin-shaped axis silently labelled °C (or a °C axis mislabeled K) is a
scale bug, not a thermal event.  These tests cover:

- unit provenance at import (declared in header vs silently defaulted °C)
- validation blocking a Kelvin-shaped axis recorded as °C
- the explicit scale-confirmation escape hatch
- Kelvin-labelled data flowing through labelled as K (never rewritten)
- temperature-unit propagation into scientific-reasoning prose
"""

from __future__ import annotations

import base64
import io

import numpy as np
import pandas as pd

from core.data_io import ThermalDataset, read_thermal_data
from core.result_serialization import serialize_dsc_result
from core.scientific_reasoning import build_scientific_reasoning
from core.validation import validate_thermal_dataset
from core.dsc_processor import GlassTransition


def _thermal_csv(temp_header: str, signal_header: str, temps: np.ndarray, signal: np.ndarray) -> io.StringIO:
    frame = pd.DataFrame({temp_header: temps, signal_header: signal})
    return io.StringIO(frame.to_csv(index=False))


def _kelvin_axis() -> np.ndarray:
    return np.linspace(300.0, 900.0, 200)


def _celsius_axis() -> np.ndarray:
    return np.linspace(30.0, 300.0, 200)


def _flat_signal(n: int = 200) -> np.ndarray:
    return np.linspace(0.5, 0.55, n)


class TestImportScaleProvenance:
    def test_kelvin_declared_axis_is_recorded_and_plausible(self):
        dataset = read_thermal_data(
            _thermal_csv("Temperature (K)", "Heat Flow (mW)", _kelvin_axis(), _flat_signal()),
            data_type="DSC",
            sign_convention="exo_up",
        )

        assert dataset.units["temperature"] == "K"
        assert dataset.metadata["temperature_unit_source"] == "header"
        assert dataset.metadata["temperature_scale_plausibility"] == "kelvin_declared_plausible"
        assert dataset.metadata["temperature_scale_review_required"] is False

    def test_unlabeled_kelvin_shaped_axis_defaults_celsius_and_flags_review(self):
        dataset = read_thermal_data(
            _thermal_csv("Temperature", "Heat Flow (mW)", _kelvin_axis(), _flat_signal()),
            data_type="DSC",
            sign_convention="exo_up",
        )

        assert dataset.units["temperature"] == "°C"
        assert dataset.metadata["temperature_unit_source"] == "defaulted_celsius"
        assert dataset.metadata["temperature_scale_plausibility"] == "kelvin_axis_recorded_as_celsius"
        assert dataset.metadata["temperature_scale_review_required"] is True
        assert any("Kelvin" in warning for warning in dataset.metadata["import_warnings"])

    def test_declared_celsius_axis_is_plausible(self):
        dataset = read_thermal_data(
            _thermal_csv("Temperature (°C)", "Heat Flow (mW)", _celsius_axis(), _flat_signal()),
            data_type="DSC",
            sign_convention="exo_up",
        )

        assert dataset.units["temperature"] == "°C"
        assert dataset.metadata["temperature_unit_source"] == "header"
        assert dataset.metadata["temperature_scale_plausibility"] == "scale_plausible"

    def test_declared_kelvin_implausibly_low_axis_flags_review_not_block(self):
        # Cryogenic data exists; a sub-100 K start is suspect but not
        # physically impossible, so import flags it for review only.
        temps = np.linspace(50.0, 400.0, 200)
        dataset = read_thermal_data(
            _thermal_csv("Temperature (K)", "Heat Flow (mW)", temps, _flat_signal()),
            data_type="DSC",
            sign_convention="exo_up",
        )

        assert dataset.units["temperature"] == "K"
        assert dataset.metadata["temperature_scale_plausibility"] == "kelvin_declared_implausible"
        assert dataset.metadata["temperature_scale_review_required"] is True


class TestValidationScaleGate:
    def _dataset(self, temps: np.ndarray, unit: str, *, confirmed: bool = False) -> ThermalDataset:
        metadata = {"sample_name": "gate-fixture"}
        if confirmed:
            metadata["temperature_scale_confirmed"] = True
        return ThermalDataset(
            data=pd.DataFrame({"temperature": temps, "signal": _flat_signal(len(temps))}),
            metadata=metadata,
            data_type="DSC",
            units={"temperature": unit, "signal": "mW"},
            original_columns={"temperature": "temperature", "signal": "signal"},
            file_path="",
        )

    def test_kelvin_shaped_axis_recorded_as_celsius_is_blocked(self):
        summary = validate_thermal_dataset(self._dataset(_kelvin_axis(), "°C"))

        assert summary["status"] == "fail"
        assert summary["checks"]["temperature_scale_plausibility"] == "kelvin_axis_recorded_as_celsius"
        assert any("Kelvin" in issue for issue in summary["issues"])

    def test_kelvin_shaped_axis_recorded_as_degc_is_blocked(self):
        summary = validate_thermal_dataset(self._dataset(_kelvin_axis(), "degC"))

        assert summary["status"] == "fail"
        assert any("Kelvin" in issue for issue in summary["issues"])

    def test_confirmed_scale_releases_the_gate_to_a_warning(self):
        summary = validate_thermal_dataset(self._dataset(_kelvin_axis(), "°C", confirmed=True))

        assert summary["status"] != "fail"
        assert summary["checks"]["temperature_scale_plausibility"] == "scale_confirmed_despite_kelvin_shape"
        assert any("Kelvin" in warning for warning in summary["warnings"])
        assert summary["checks"]["temperature_scale_confirmed"] is True

    def test_kelvin_declared_axis_passes_with_kelvin_label(self):
        summary = validate_thermal_dataset(self._dataset(_kelvin_axis(), "K"))

        assert summary["checks"]["temperature_scale_plausibility"] == "kelvin_declared_plausible"
        assert not any("Kelvin" in issue for issue in summary["issues"])
        assert summary["checks"]["temperature_unit"] == "K"

    def test_celsius_axis_passes(self):
        summary = validate_thermal_dataset(self._dataset(_celsius_axis(), "°C"))

        assert summary["checks"]["temperature_scale_plausibility"] == "scale_plausible"
        assert not any("Kelvin" in issue for issue in summary["issues"])

    def test_spectral_axes_are_not_gated(self):
        dataset = ThermalDataset(
            data=pd.DataFrame(
                {"temperature": np.linspace(4000.0, 400.0, 100), "signal": _flat_signal(100)}
            ),
            metadata={"sample_name": "ftir-fixture"},
            data_type="FTIR",
            units={"temperature": "cm^-1", "signal": "absorbance"},
            original_columns={"temperature": "wavenumber", "signal": "signal"},
            file_path="",
        )
        summary = validate_thermal_dataset(dataset)

        assert summary["checks"]["temperature_scale_plausibility"] == "not_evaluated"
        assert not any("Kelvin" in issue for issue in summary["issues"])


class TestReasoningUnitProvenance:
    def test_dsc_reasoning_uses_recorded_kelvin_unit(self):
        payload = build_scientific_reasoning(
            analysis_type="DSC",
            summary={"peak_count": 1, "tg_midpoint": 350.0},
            rows=[{"peak_temperature": 600.0}],
            metadata={"temperature_unit": "K"},
            fit_quality={"r_squared": 0.99},
            validation={"status": "pass", "warnings": []},
        )

        evidence = [item for values in payload["evidence_map"].values() for item in values]
        assert any("350.00 K" in item for item in evidence)
        assert not any("°C" in item for item in evidence)

    def test_dsc_reasoning_defaults_to_celsius_without_recorded_unit(self):
        payload = build_scientific_reasoning(
            analysis_type="DSC",
            summary={"peak_count": 1, "tg_midpoint": 120.0},
            rows=[{"peak_temperature": 250.0}],
            metadata={},
            fit_quality={"r_squared": 0.99},
            validation={"status": "pass", "warnings": []},
        )

        evidence = [item for values in payload["evidence_map"].values() for item in values]
        assert any("120.00 °C" in item for item in evidence)

    def test_tga_reasoning_uses_recorded_kelvin_unit(self):
        payload = build_scientific_reasoning(
            analysis_type="TGA",
            summary={"step_count": 2, "total_mass_loss_percent": 80.0, "residue_percent": 20.0},
            rows=[
                {"midpoint_temperature": 400.0, "mass_loss_percent": 50.0},
                {"midpoint_temperature": 700.0, "mass_loss_percent": 30.0},
            ],
            metadata={"temperature_unit": "K", "sample_mass": 10.0, "heating_rate": 10.0, "instrument": "TA", "atmosphere": "N2"},
            fit_quality={"r_squared": 0.99},
            validation={"status": "pass", "warnings": []},
        )

        evidence = [item for values in payload["evidence_map"].values() for item in values]
        assert any(" K." in item or item.endswith(" K") for item in evidence)
        assert not any("°C" in item for item in evidence)


class TestSerializedRecordUnitProvenance:
    def test_serialize_dsc_result_labels_tg_in_kelvin(self):
        temps = _kelvin_axis()
        dataset = ThermalDataset(
            data=pd.DataFrame({"temperature": temps, "signal": _flat_signal(len(temps))}),
            metadata={
                "sample_name": "KelvinDSC",
                "sample_mass": 5.0,
                "heating_rate": 10.0,
                "instrument": "TestInstrument",
            },
            data_type="DSC",
            units={"temperature": "K", "signal": "mW/mg"},
            original_columns={"temperature": "Temperature (K)", "signal": "Heat Flow (mW)"},
            file_path="",
        )
        tg = GlassTransition(tg_midpoint=350.0, tg_onset=340.0, tg_endset=360.0, heat_flow_step=0.1)

        record = serialize_dsc_result("k_dataset", dataset, [], glass_transitions=[tg])

        evidence = [
            item
            for values in (record["scientific_context"].get("evidence_map") or {}).values()
            for item in values
        ]
        assert any("350.00 K" in item for item in evidence)


class TestImportApiBlocksKelvinSuspect:
    def test_dataset_import_rejects_unconfirmed_kelvin_shaped_celsius(self):
        from fastapi.testclient import TestClient

        from backend.app import create_app

        client = TestClient(create_app(api_token="workspace-token"))
        headers = {"X-MaterialScope-Token": "workspace-token"}
        project_id = client.post("/workspace/new", headers=headers).json()["project_id"]

        frame = pd.DataFrame(
            {"Temperature": _kelvin_axis(), "Heat Flow (mW)": _flat_signal()}
        )
        payload = {
            "project_id": project_id,
            "file_name": "kelvin_shaped.csv",
            "file_base64": base64.b64encode(frame.to_csv(index=False).encode("utf-8")).decode("ascii"),
            "data_type": "DSC",
            "column_mapping": {"temperature": "Temperature", "signal": "Heat Flow (mW)"},
            "sign_convention": "exo_up",
        }
        response = client.post("/dataset/import", headers=headers, json=payload)

        assert response.status_code == 400
        assert "Kelvin" in response.json()["detail"]

    def test_dataset_import_accepts_confirmed_scale(self):
        from fastapi.testclient import TestClient

        from backend.app import create_app

        client = TestClient(create_app(api_token="workspace-token"))
        headers = {"X-MaterialScope-Token": "workspace-token"}
        project_id = client.post("/workspace/new", headers=headers).json()["project_id"]

        frame = pd.DataFrame(
            {"Temperature": _kelvin_axis(), "Heat Flow (mW)": _flat_signal()}
        )
        payload = {
            "project_id": project_id,
            "file_name": "kelvin_shaped_confirmed.csv",
            "file_base64": base64.b64encode(frame.to_csv(index=False).encode("utf-8")).decode("ascii"),
            "data_type": "DSC",
            "column_mapping": {"temperature": "Temperature", "signal": "Heat Flow (mW)"},
            "sign_convention": "exo_up",
            "metadata": {"temperature_scale_confirmed": True},
        }
        response = client.post("/dataset/import", headers=headers, json=payload)

        assert response.status_code == 200
