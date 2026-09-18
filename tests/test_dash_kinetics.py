"""Tests for the preview Kinetics Dash page and workspace-backed endpoint.

Covers the backend kinetics service (validation, persistence, scientific
honesty), the ``POST /workspace/{project_id}/kinetics/run`` endpoint
(including preview gating), project-archive round-trip, and the Dash page
module (registration, nav gating, EN/TR chrome).
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import dash
import numpy as np
import pandas as pd
import pytest

from backend.kinetics_service import (
    KineticsValidationError,
    _resolve_alpha_grid,
    run_kinetics_workflow,
)
from backend.models import (
    KineticsDatasetSelection,
    KineticsManualPoint,
    KineticsRunRequest,
    ResultSummary,
)
from backend.workspace import summarize_result
from core.data_io import ThermalDataset
from core.result_serialization import split_valid_results


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _tga_dataset(metadata: dict | None = None, *, step_center: float = 420.0) -> ThermalDataset:
    """Deterministic TGA-like mass-loss curve (one sigmoidal step).

    ``step_center`` shifts the degradation step, mimicking the rate-dependent
    displacement real multi-rate series exhibit.
    """
    temperature = np.linspace(30.0, 800.0, 400)
    mass = 100.0 - 60.0 / (1.0 + np.exp(-(temperature - step_center) / 45.0))
    frame = pd.DataFrame({"temperature": temperature, "signal": np.round(mass, 4)})
    return ThermalDataset(
        data=frame,
        metadata=dict(metadata or {}),
        data_type="TGA",
        units={"temperature": "°C", "signal": "%"},
        original_columns={"temperature": "temperature", "signal": "signal"},
    )


def _dsc_dataset(metadata: dict | None = None, *, peak_center: float = 210.0) -> ThermalDataset:
    """Deterministic DSC-like trace with a single positive peak."""
    temperature = np.linspace(50.0, 350.0, 300)
    signal = np.exp(-0.5 * ((temperature - peak_center) / 12.0) ** 2)
    frame = pd.DataFrame({"temperature": temperature, "signal": np.round(signal, 6)})
    return ThermalDataset(
        data=frame,
        metadata=dict(metadata or {}),
        data_type="DSC",
        units={"temperature": "°C", "signal": "mW/mg"},
        original_columns={"temperature": "temperature", "signal": "signal"},
    )


def _ftir_dataset() -> ThermalDataset:
    axis = np.linspace(400.0, 4000.0, 200)
    signal = np.exp(-0.5 * ((axis - 1600.0) / 20.0) ** 2)
    frame = pd.DataFrame({"temperature": axis, "signal": signal})
    return ThermalDataset(
        data=frame,
        metadata={},
        data_type="FTIR",
        units={"temperature": "cm^-1", "signal": "a.u."},
        original_columns={"temperature": "temperature", "signal": "signal"},
    )


def _dsc_corrected_state(dataset: ThermalDataset) -> dict:
    temperature = np.asarray(dataset.data["temperature"], dtype=float)
    corrected = np.asarray(dataset.data["signal"], dtype=float)
    return {
        "axis": temperature.tolist(),
        "temperature": temperature.tolist(),
        "corrected": corrected.tolist(),
        "peaks": [],
    }


def _state(datasets: dict[str, ThermalDataset], extra: dict | None = None) -> dict:
    state = {
        "datasets": datasets,
        "results": {},
        "figures": {},
        "analysis_history": [],
        "branding": {},
        "comparison_workspace": {},
        "active_dataset": None,
    }
    state.update(extra or {})
    return state


def _request(**kwargs) -> KineticsRunRequest:
    return KineticsRunRequest(**kwargs)


# ---------------------------------------------------------------------------
# Service: manual Kissinger
# ---------------------------------------------------------------------------


def test_manual_kissinger_persists_normalized_workspace_result():
    state = _state({})
    request = _request(
        method="kissinger",
        input_mode="manual",
        manual_points=[
            KineticsManualPoint(heating_rate=5.0, peak_temperature=210.0),
            KineticsManualPoint(heating_rate=10.0, peak_temperature=220.0),
            KineticsManualPoint(heating_rate=20.0, peak_temperature=232.0),
        ],
    )

    outcome = run_kinetics_workflow(state=state, request=request, app_version="test")

    result_id = outcome["result_id"]
    assert result_id in state["results"]
    record = state["results"][result_id]
    assert record["analysis_type"] == "Kissinger"
    assert record["summary"]["activation_energy_kj_mol"] is not None
    assert "ln(A * R / Ea)" in (record["summary"]["intercept_semantics"] or "")
    assert record["summary"]["ln_a_min_inv"] is not None
    assert record["summary"]["ea_ci_status"] == "computed"
    assert record["report_payload"]["plots"]
    assert record["processing"]["input_mode"] == "manual"
    sources = {entry["heating_rate_source"] for entry in record["processing"]["inputs"]}
    assert sources == {"user"}
    # History event recorded.
    assert state["analysis_history"]
    assert state["analysis_history"][-1]["result_id"] == result_id


def test_manual_kissinger_two_points_withholds_ci():
    state = _state({})
    request = _request(
        method="kissinger",
        input_mode="manual",
        manual_points=[
            KineticsManualPoint(heating_rate=5.0, peak_temperature=210.0),
            KineticsManualPoint(heating_rate=10.0, peak_temperature=220.0),
        ],
    )
    outcome = run_kinetics_workflow(state=state, request=request)
    record = state["results"][outcome["result_id"]]
    assert record["summary"]["ea_ci_status"] == "withheld"
    assert record["summary"]["ea_ci_withheld_reason"]
    assert record["summary"]["activation_energy_kj_mol"] is not None


def test_manual_kissinger_requires_two_distinct_rates():
    state = _state({})
    request = _request(
        method="kissinger",
        input_mode="manual",
        manual_points=[
            KineticsManualPoint(heating_rate=10.0, peak_temperature=210.0),
            KineticsManualPoint(heating_rate=10.0, peak_temperature=220.0),
        ],
    )
    with pytest.raises(KineticsValidationError, match="distinct"):
        run_kinetics_workflow(state=state, request=request)


def test_manual_kissinger_requires_two_points():
    state = _state({})
    request = _request(
        method="kissinger",
        input_mode="manual",
        manual_points=[KineticsManualPoint(heating_rate=5.0, peak_temperature=210.0)],
    )
    with pytest.raises(KineticsValidationError, match="at least two"):
        run_kinetics_workflow(state=state, request=request)


# ---------------------------------------------------------------------------
# Service: dataset-backed Kissinger
# ---------------------------------------------------------------------------


def test_dataset_kissinger_happy_path_records_provenance():
    datasets = {
        "dsc_a": _dsc_dataset(peak_center=210.0),
        "dsc_b": _dsc_dataset(peak_center=220.0),
        "dsc_c": _dsc_dataset(peak_center=232.0),
    }
    state = _state(datasets)
    request = _request(
        method="kissinger",
        dataset_selections=[
            KineticsDatasetSelection(dataset_key="dsc_a", heating_rate=5.0, peak_temperature=210.0),
            KineticsDatasetSelection(dataset_key="dsc_b", heating_rate=10.0, peak_temperature=220.0),
            KineticsDatasetSelection(dataset_key="dsc_c", heating_rate=20.0, peak_temperature=232.0),
        ],
    )
    outcome = run_kinetics_workflow(state=state, request=request)
    record = state["results"][outcome["result_id"]]
    assert record["metadata"]["dataset_keys"] == ["dsc_a", "dsc_b", "dsc_c"]
    assert record["summary"]["activation_energy_kj_mol"] is not None


def test_missing_heating_rate_blocks_no_fabricated_default():
    """No metadata rate and no user-declared rate must block the run."""
    datasets = {"tga_a": _tga_dataset(), "tga_b": _tga_dataset()}
    state = _state(datasets)
    request = _request(
        method="ofw",
        dataset_selections=[
            KineticsDatasetSelection(dataset_key="tga_a"),
            KineticsDatasetSelection(dataset_key="tga_b", heating_rate=10.0),
        ],
    )
    with pytest.raises(KineticsValidationError, match="heating rate"):
        run_kinetics_workflow(state=state, request=request)
    assert state["results"] == {}


def test_untraceable_metadata_heating_rate_blocks():
    """A metadata heating rate without user/parsed provenance is not trusted."""
    datasets = {
        "tga_a": _tga_dataset(metadata={"heating_rate": 10.0, "heating_rate_source": "legacy_unknown"}),
        "tga_b": _tga_dataset(),
    }
    state = _state(datasets)
    request = _request(
        method="ofw",
        dataset_selections=[
            KineticsDatasetSelection(dataset_key="tga_a"),
            KineticsDatasetSelection(dataset_key="tga_b", heating_rate=20.0),
        ],
    )
    with pytest.raises(KineticsValidationError, match="traceable heating rate"):
        run_kinetics_workflow(state=state, request=request)


def test_parsed_metadata_heating_rate_is_usable():
    datasets = {
        "tga_a": _tga_dataset(
            metadata={"heating_rate": 5.0, "heating_rate_source": "parsed"}, step_center=400.0
        ),
        "tga_b": _tga_dataset(
            metadata={"heating_rate": 10.0, "heating_rate_source": "parsed"}, step_center=430.0
        ),
        "tga_c": _tga_dataset(
            metadata={"heating_rate": 20.0, "heating_rate_source": "parsed"}, step_center=460.0
        ),
    }
    state = _state(datasets)
    request = _request(
        method="ofw",
        dataset_selections=[
            KineticsDatasetSelection(dataset_key="tga_a"),
            KineticsDatasetSelection(dataset_key="tga_b"),
            KineticsDatasetSelection(dataset_key="tga_c"),
        ],
    )
    outcome = run_kinetics_workflow(state=state, request=request)
    record = state["results"][outcome["result_id"]]
    assert record["analysis_type"] == "Ozawa-Flynn-Wall"
    assert len(record["rows"]) > 0


def test_duplicate_dataset_selection_blocked():
    datasets = {"tga_a": _tga_dataset(), "tga_b": _tga_dataset()}
    state = _state(datasets)
    request = _request(
        method="ofw",
        dataset_selections=[
            KineticsDatasetSelection(dataset_key="tga_a", heating_rate=5.0),
            KineticsDatasetSelection(dataset_key="tga_a", heating_rate=10.0),
        ],
    )
    with pytest.raises(KineticsValidationError, match="only once"):
        run_kinetics_workflow(state=state, request=request)


def test_mixed_modality_selection_blocked():
    datasets = {"dsc_a": _dsc_dataset(), "tga_a": _tga_dataset()}
    state = _state(datasets)
    request = _request(
        method="ofw",
        dataset_selections=[
            KineticsDatasetSelection(dataset_key="dsc_a", heating_rate=5.0),
            KineticsDatasetSelection(dataset_key="tga_a", heating_rate=10.0),
        ],
    )
    with pytest.raises(KineticsValidationError, match="same analysis type"):
        run_kinetics_workflow(state=state, request=request)


def test_ineligible_modality_blocked():
    datasets = {"ftir_a": _ftir_dataset(), "tga_a": _tga_dataset()}
    state = _state(datasets)
    request = _request(
        method="ofw",
        dataset_selections=[
            KineticsDatasetSelection(dataset_key="ftir_a", heating_rate=5.0),
            KineticsDatasetSelection(dataset_key="tga_a", heating_rate=10.0),
        ],
    )
    with pytest.raises(KineticsValidationError, match="DSC and TGA"):
        run_kinetics_workflow(state=state, request=request)


def test_distinct_rate_requirement_for_datasets():
    datasets = {"tga_a": _tga_dataset(), "tga_b": _tga_dataset()}
    state = _state(datasets)
    request = _request(
        method="ofw",
        dataset_selections=[
            KineticsDatasetSelection(dataset_key="tga_a", heating_rate=10.0),
            KineticsDatasetSelection(dataset_key="tga_b", heating_rate=10.0),
        ],
    )
    with pytest.raises(KineticsValidationError, match="distinct"):
        run_kinetics_workflow(state=state, request=request)


# ---------------------------------------------------------------------------
# Service: OFW / Friedman conversion bases
# ---------------------------------------------------------------------------


def test_dsc_ofw_without_corrected_state_blocks_with_prerequisite_reason():
    datasets = {
        "dsc_a": _dsc_dataset(peak_center=200.0),
        "dsc_b": _dsc_dataset(peak_center=210.0),
        "dsc_c": _dsc_dataset(peak_center=220.0),
    }
    state = _state(datasets)  # no dsc_state_* entries
    request = _request(
        method="ofw",
        dataset_selections=[
            KineticsDatasetSelection(dataset_key="dsc_a", heating_rate=5.0),
            KineticsDatasetSelection(dataset_key="dsc_b", heating_rate=10.0),
            KineticsDatasetSelection(dataset_key="dsc_c", heating_rate=20.0),
        ],
    )
    with pytest.raises(KineticsValidationError, match="baseline-corrected DSC"):
        run_kinetics_workflow(state=state, request=request)


def test_dsc_ofw_with_corrected_state_succeeds():
    datasets = {
        "dsc_a": _dsc_dataset(peak_center=200.0),
        "dsc_b": _dsc_dataset(peak_center=212.0),
        "dsc_c": _dsc_dataset(peak_center=225.0),
    }
    state = _state(
        datasets,
        extra={f"dsc_state_{key}": _dsc_corrected_state(ds) for key, ds in datasets.items()},
    )
    request = _request(
        method="ofw",
        dataset_selections=[
            KineticsDatasetSelection(dataset_key="dsc_a", heating_rate=5.0),
            KineticsDatasetSelection(dataset_key="dsc_b", heating_rate=10.0),
            KineticsDatasetSelection(dataset_key="dsc_c", heating_rate=20.0),
        ],
    )
    outcome = run_kinetics_workflow(state=state, request=request)
    record = state["results"][outcome["result_id"]]
    assert record["analysis_type"] == "Ozawa-Flynn-Wall"
    assert all(r["activation_energy_kj_mol"] is not None for r in record["rows"])
    bases = {entry["signal_basis"] for entry in record["processing"]["inputs"]}
    assert bases == {"dsc_corrected_signal"}


def test_tga_friedman_records_dalpha_dt_derivation():
    datasets = {
        "tga_a": _tga_dataset(step_center=400.0),
        "tga_b": _tga_dataset(step_center=430.0),
        "tga_c": _tga_dataset(step_center=460.0),
    }
    state = _state(datasets)
    request = _request(
        method="friedman",
        alpha_min=0.2,
        alpha_max=0.8,
        alpha_step=0.2,
        dataset_selections=[
            KineticsDatasetSelection(dataset_key="tga_a", heating_rate=5.0),
            KineticsDatasetSelection(dataset_key="tga_b", heating_rate=10.0),
            KineticsDatasetSelection(dataset_key="tga_c", heating_rate=20.0),
        ],
    )
    outcome = run_kinetics_workflow(state=state, request=request)
    record = state["results"][outcome["result_id"]]
    assert record["analysis_type"] == "Friedman"
    assert "gradient(alpha, temperature)" in record["processing"]["dalpha_dt_derivation"]
    assert all("ln(A * f(alpha))" in (r["intercept_semantics"] or "") for r in record["rows"])


def test_isoconversional_ci_withheld_with_two_rates():
    datasets = {"tga_a": _tga_dataset(step_center=400.0), "tga_b": _tga_dataset(step_center=440.0)}
    state = _state(datasets)
    request = _request(
        method="ofw",
        alpha_min=0.3,
        alpha_max=0.6,
        alpha_step=0.3,
        dataset_selections=[
            KineticsDatasetSelection(dataset_key="tga_a", heating_rate=5.0),
            KineticsDatasetSelection(dataset_key="tga_b", heating_rate=10.0),
        ],
    )
    outcome = run_kinetics_workflow(state=state, request=request)
    record = state["results"][outcome["result_id"]]
    assert record["rows"], "expected per-alpha rows"
    assert all(r["ea_ci_status"] == "withheld" for r in record["rows"])


def test_saved_record_passes_result_validation():
    state = _state({})
    request = _request(
        method="kissinger",
        input_mode="manual",
        manual_points=[
            KineticsManualPoint(heating_rate=5.0, peak_temperature=210.0),
            KineticsManualPoint(heating_rate=10.0, peak_temperature=220.0),
            KineticsManualPoint(heating_rate=20.0, peak_temperature=232.0),
        ],
    )
    run_kinetics_workflow(state=state, request=request)
    valid, issues = split_valid_results(state["results"])
    assert issues == []
    assert len(valid) == 1


def test_scopezip_round_trip_retains_kinetics_result():
    from core.project_io import deserialize_project, serialize_project

    state = _state({})
    request = _request(
        method="kissinger",
        input_mode="manual",
        manual_points=[
            KineticsManualPoint(heating_rate=5.0, peak_temperature=210.0),
            KineticsManualPoint(heating_rate=10.0, peak_temperature=220.0),
            KineticsManualPoint(heating_rate=20.0, peak_temperature=232.0),
        ],
    )
    outcome = run_kinetics_workflow(state=state, request=request)
    payload = serialize_project(state)
    restored = deserialize_project(
        payload["manifest"],
        {**payload["datasets"], **payload["figures"], **payload["branding_assets"]},
        results_payload=payload["results"],
        history_payload=payload["history"],
    )
    assert outcome["result_id"] in restored["results"]
    restored_record = restored["results"][outcome["result_id"]]
    assert restored_record["analysis_type"] == "Kissinger"
    assert restored_record["scientific_context"]
    assert restored_record["report_payload"]["plots"]
    assert restored["analysis_history"]


# ---------------------------------------------------------------------------
# Endpoint: preview gating + API contract
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from backend.app import create_app

    return TestClient(create_app())


def test_kinetics_endpoint_blocked_when_preview_disabled(client, monkeypatch):
    monkeypatch.delenv("MATERIALSCOPE_ENABLE_PREVIEW_MODULES", raising=False)
    project_id = client.post("/workspace/new").json()["project_id"]
    response = client.post(
        f"/workspace/{project_id}/kinetics/run",
        json={
            "method": "kissinger",
            "input_mode": "manual",
            "manual_points": [
                {"heating_rate": 5.0, "peak_temperature": 210.0},
                {"heating_rate": 10.0, "peak_temperature": 220.0},
            ],
        },
    )
    assert response.status_code == 403


def test_kinetics_endpoint_manual_kissinger_round_trip(client, monkeypatch):
    monkeypatch.setenv("MATERIALSCOPE_ENABLE_PREVIEW_MODULES", "1")
    project_id = client.post("/workspace/new").json()["project_id"]
    response = client.post(
        f"/workspace/{project_id}/kinetics/run",
        json={
            "method": "kissinger",
            "input_mode": "manual",
            "manual_points": [
                {"heating_rate": 5.0, "peak_temperature": 210.0},
                {"heating_rate": 10.0, "peak_temperature": 220.0},
                {"heating_rate": 20.0, "peak_temperature": 232.0},
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result_id"]
    assert body["method_id"] == "kissinger"
    assert body["execution_status"] == "saved"

    # Workspace results list includes the saved record.
    results = client.get(f"/workspace/{project_id}/results").json()
    ids = [item["id"] for item in results.get("results", [])]
    assert body["result_id"] in ids

    # ResultDetail exposes summary + report_payload for re-rendering.
    detail = client.get(f"/workspace/{project_id}/results/{body['result_id']}").json()
    assert detail["summary"]["activation_energy_kj_mol"] is not None
    assert detail["report_payload"]["plots"]
    assert detail["processing"]["kinetics_method"] == "kissinger"


def test_kinetics_endpoint_validation_error_is_400(client, monkeypatch):
    monkeypatch.setenv("MATERIALSCOPE_ENABLE_PREVIEW_MODULES", "1")
    project_id = client.post("/workspace/new").json()["project_id"]
    response = client.post(
        f"/workspace/{project_id}/kinetics/run",
        json={"method": "kissinger", "input_mode": "manual", "manual_points": []},
    )
    assert response.status_code == 400
    assert "at least two" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Dash page: registration, gating, chrome
# ---------------------------------------------------------------------------


@pytest.fixture()
def _dash_app():
    import dash
    from dash import html

    try:
        dash.get_app()
    except Exception:
        app = dash.Dash(
            __name__,
            use_pages=True,
            pages_folder="",
            suppress_callback_exceptions=True,
        )
        app.layout = html.Div(dash.page_container)
    yield


def _import_page():
    import dash_app.pages.kinetics as mod

    return mod


def test_kinetics_page_registered(_dash_app):
    import dash

    _import_page()
    paths = {page.get("path") for page in dash.page_registry.values()}
    assert "/kinetics" in paths


def test_kinetics_nav_hidden_when_preview_disabled(_dash_app, monkeypatch):
    monkeypatch.delenv("MATERIALSCOPE_ENABLE_PREVIEW_MODULES", raising=False)
    from dash_app.layout import build_sidebar_inner

    sidebar = build_sidebar_inner("en", "light")
    assert "/kinetics" not in str(sidebar)


def test_kinetics_nav_visible_when_preview_enabled(_dash_app, monkeypatch):
    monkeypatch.setenv("MATERIALSCOPE_ENABLE_PREVIEW_MODULES", "1")
    from dash_app.layout import build_sidebar_inner

    sidebar = build_sidebar_inner("en", "light")
    assert "/kinetics" in str(sidebar)


def test_kinetics_page_blocks_workflow_when_preview_disabled(_dash_app, monkeypatch):
    monkeypatch.delenv("MATERIALSCOPE_ENABLE_PREVIEW_MODULES", raising=False)
    mod = _import_page()
    style, disabled = mod.gate_kinetics_page("en")
    assert style.get("display") == "none"
    assert disabled


def test_kinetics_page_enabled_when_preview_on(_dash_app, monkeypatch):
    monkeypatch.setenv("MATERIALSCOPE_ENABLE_PREVIEW_MODULES", "1")
    mod = _import_page()
    style, disabled = mod.gate_kinetics_page("en")
    assert style == {}
    assert disabled == ""


@pytest.mark.parametrize("locale", ["en", "tr"])
def test_kinetics_chrome_renders_in_en_and_tr(_dash_app, monkeypatch, locale):
    monkeypatch.setenv("MATERIALSCOPE_ENABLE_PREVIEW_MODULES", "1")
    mod = _import_page()
    outputs = mod.render_kinetics_chrome(locale)
    # method options localized, run button non-empty
    assert outputs[4][0]["label"]
    assert outputs[16]  # run button label


# ---------------------------------------------------------------------------
# Regression: real DSC analysis state uses ndarrays (PR #62 review, blocker)
# ---------------------------------------------------------------------------


def _dsc_csv(path: Path, peak_center: float) -> Path:
    temperature = np.linspace(50.0, 350.0, 300)
    signal = np.exp(-0.5 * ((temperature - peak_center) / 12.0) ** 2)
    path.write_text(
        pd.DataFrame({"temperature": temperature, "signal": np.round(signal, 6)}).to_csv(
            index=False
        ),
        encoding="utf-8",
    )
    return path


def _import_dataset(client, project_id: str, path: Path, data_type: str) -> str:
    response = client.post(
        "/dataset/import",
        json={
            "project_id": project_id,
            "file_name": path.name,
            "file_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
            "data_type": data_type,
        },
    )
    response.raise_for_status()
    return response.json()["dataset"]["key"]


def _run_analysis(client, project_id: str, dataset_key: str, analysis_type: str) -> None:
    response = client.post(
        "/analysis/run",
        json={
            "project_id": project_id,
            "dataset_key": dataset_key,
            "analysis_type": analysis_type,
        },
    )
    assert response.status_code == 200, response.text


def test_dsc_ofw_and_friedman_use_real_saved_analysis_state(tmp_path, monkeypatch):
    """Real ``/analysis/run`` DSC execution stores ndarray payloads.

    The prior implementation boolean-coerced ``dsc_state.get("corrected") or []``
    which raises ``ValueError`` on multi-element ndarrays. This test drives the
    genuine backend/core DSC execution path and would fail on the unfixed code.
    """
    from fastapi.testclient import TestClient

    from backend.app import create_app
    from backend.store import ProjectStore

    monkeypatch.setenv("MATERIALSCOPE_ENABLE_PREVIEW_MODULES", "1")
    store = ProjectStore(autosave=False)
    client = TestClient(create_app(store=store))
    project_id = client.post("/workspace/new").json()["project_id"]

    keys = [
        _import_dataset(
            client,
            project_id,
            _dsc_csv(tmp_path / f"dsc_{idx}.csv", center),
            "DSC",
        )
        for idx, center in enumerate((195.0, 212.0, 228.0))
    ]
    for key in keys:
        _run_analysis(client, project_id, key, "DSC")

    state = store.get(project_id)
    for key in keys:
        dsc_state = state[f"dsc_state_{key}"]
        # Production shape: ndarray payloads, not lists.
        assert isinstance(dsc_state["corrected"], np.ndarray)
        assert dsc_state["corrected"].size > 1

    selections = [
        {"dataset_key": key, "heating_rate": rate}
        for key, rate in zip(keys, (5.0, 10.0, 20.0), strict=True)
    ]
    for method in ("ofw", "friedman"):
        response = client.post(
            f"/workspace/{project_id}/kinetics/run",
            json={
                "method": method,
                "alpha_min": 0.2,
                "alpha_max": 0.8,
                "alpha_step": 0.2,
                "dataset_selections": selections,
            },
        )
        assert response.status_code == 200, response.text
        result_id = response.json()["result_id"]
        detail = client.get(f"/workspace/{project_id}/results/{result_id}").json()
        bases = {
            entry["signal_basis"] for entry in detail["processing"]["inputs"]
        }
        assert bases == {"dsc_corrected_signal"}


# ---------------------------------------------------------------------------
# Regression: alpha grid must never exceed alpha_max (PR #62 review)
# ---------------------------------------------------------------------------


def test_alpha_grid_evenly_divisible_range_reaches_alpha_max():
    request = _request(method="ofw", alpha_min=0.1, alpha_max=0.9, alpha_step=0.2)
    values, _ = _resolve_alpha_grid(request)
    assert values == pytest.approx([0.1, 0.3, 0.5, 0.7, 0.9])


def test_alpha_grid_non_even_range_never_exceeds_alpha_max():
    request = _request(method="ofw", alpha_min=0.1, alpha_max=0.85, alpha_step=0.2)
    values, _ = _resolve_alpha_grid(request)
    assert values == pytest.approx([0.1, 0.3, 0.5, 0.7])
    assert max(values) <= 0.85


def test_alpha_grid_float_edge_keeps_endpoint_within_bounds():
    request = _request(method="ofw", alpha_min=0.1, alpha_max=0.3, alpha_step=0.1)
    values, _ = _resolve_alpha_grid(request)
    assert values == pytest.approx([0.1, 0.2, 0.3])
    assert min(values) >= 0.1
    assert max(values) <= 0.3 + 1e-9


# ---------------------------------------------------------------------------
# Regression: hydrate kinetics-latest-result-id from workspace (PR #62 review)
# ---------------------------------------------------------------------------


def _results_payload(*items: dict[str, Any]) -> dict[str, Any]:
    return {"results": list(items)}


def _kinetics_summary(result_id: str, saved_at: str) -> dict[str, Any]:
    return {
        "id": result_id,
        "analysis_scope": "preview_kinetics",
        "saved_at_utc": saved_at,
    }


def test_hydration_selects_newest_kinetics_result(_dash_app, monkeypatch):
    mod = _import_page()
    payload = _results_payload(
        _kinetics_summary("k1", "2026-01-01T10:00:00+00:00"),
        _kinetics_summary("k2", "2026-01-02T10:00:00+00:00"),
        {"id": "dsc1", "analysis_scope": None, "saved_at_utc": "2026-01-03T00:00:00+00:00"},
    )
    monkeypatch.setattr("dash_app.api_client.workspace_results", lambda _pid: payload)
    assert (
        mod.hydrate_latest_kinetics_result("/kinetics", "proj", 0, None) == "k2"
    )


def test_hydration_deterministic_tiebreak_on_equal_timestamps(_dash_app, monkeypatch):
    mod = _import_page()
    payload = _results_payload(
        _kinetics_summary("k-b", "2026-01-01T10:00:00+00:00"),
        _kinetics_summary("k-a", "2026-01-01T10:00:00+00:00"),
    )
    monkeypatch.setattr("dash_app.api_client.workspace_results", lambda _pid: payload)
    first = mod.hydrate_latest_kinetics_result("/kinetics", "proj", 0, None)
    payload["results"].reverse()
    monkeypatch.setattr("dash_app.api_client.workspace_results", lambda _pid: payload)
    second = mod.hydrate_latest_kinetics_result("/kinetics", "proj", 0, None)
    assert first == second == "k-b"


def test_hydration_keeps_valid_current_selection(_dash_app, monkeypatch):
    mod = _import_page()
    payload = _results_payload(
        _kinetics_summary("k1", "2026-01-01T10:00:00+00:00"),
        _kinetics_summary("k2", "2026-01-02T10:00:00+00:00"),
    )
    monkeypatch.setattr("dash_app.api_client.workspace_results", lambda _pid: payload)
    with pytest.raises(dash.exceptions.PreventUpdate):
        mod.hydrate_latest_kinetics_result("/kinetics", "proj", 0, "k1")


def test_hydration_replaces_stale_selection_with_newest(_dash_app, monkeypatch):
    mod = _import_page()
    payload = _results_payload(
        _kinetics_summary("k2", "2026-01-02T10:00:00+00:00"),
    )
    monkeypatch.setattr("dash_app.api_client.workspace_results", lambda _pid: payload)
    assert (
        mod.hydrate_latest_kinetics_result("/kinetics", "proj", 0, "gone")
        == "k2"
    )


def test_hydration_empty_when_no_kinetics_results(_dash_app, monkeypatch):
    mod = _import_page()
    payload = _results_payload(
        {"id": "dsc1", "analysis_scope": None, "saved_at_utc": "2026-01-01T00:00:00+00:00"},
    )
    monkeypatch.setattr("dash_app.api_client.workspace_results", lambda _pid: payload)
    with pytest.raises(dash.exceptions.PreventUpdate):
        mod.hydrate_latest_kinetics_result("/kinetics", "proj", 0, None)
    assert mod.hydrate_latest_kinetics_result("/kinetics", "proj", 0, "stale") is None


def test_hydration_requires_project_and_route(_dash_app):
    mod = _import_page()
    with pytest.raises(dash.exceptions.PreventUpdate):
        mod.hydrate_latest_kinetics_result("/kinetics", "", 0, None)
    with pytest.raises(dash.exceptions.PreventUpdate):
        mod.hydrate_latest_kinetics_result("/dsc", "proj", 0, None)


def test_scopezip_restored_kinetics_result_rehydrates():
    """A kinetics record survives .scopezip round-trip and stays identifiable."""
    from core.project_io import deserialize_project, serialize_project

    state = _state({})
    request = _request(
        method="kissinger",
        input_mode="manual",
        manual_points=[
            KineticsManualPoint(heating_rate=5.0, peak_temperature=210.0),
            KineticsManualPoint(heating_rate=10.0, peak_temperature=220.0),
            KineticsManualPoint(heating_rate=20.0, peak_temperature=232.0),
        ],
    )
    outcome = run_kinetics_workflow(state=state, request=request)
    payload = serialize_project(state)
    restored = deserialize_project(
        payload["manifest"],
        {**payload["datasets"], **payload["figures"], **payload["branding_assets"]},
        results_payload=payload["results"],
        history_payload=payload["history"],
    )
    restored_record = restored["results"][outcome["result_id"]]
    assert restored_record["provenance"]["analysis_scope"] == "preview_kinetics"

    # The workspace summary the Dash page hydrates from stays identifiable.
    summary = summarize_result(restored_record)
    assert isinstance(summary, ResultSummary)
    assert summary.analysis_scope == "preview_kinetics"
