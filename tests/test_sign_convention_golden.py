"""
test_sign_convention_golden.py
------------------------------
PR-8 acceptance gate: both-convention golden tests end to end through the
backend API (import -> analysis -> serialized record).

The same physical melting event is encoded as an endo-up CSV and as an
exo-up CSV.  After ingest canonicalization both imports must produce the
same analysis outcome: peaks labeled ``endotherm`` with matching
temperatures and areas.  Mirrored DTA fixtures must produce a single,
correctly tagged event (no duplicate/contradictory tags).  An
``unknown``-declared import must keep polarity unresolved: no endo/exo
attribution, counts unclaimed, explicit warnings.
"""

from __future__ import annotations

import base64

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


_TOKEN = {"X-MaterialScope-Token": "sign-canon-token"}

_TEMPERATURE = np.linspace(50.0, 250.0, 401)

# The same endothermic melting event in the two vendor encodings.
# Baseline is zero so the golden exercises the sign canon (labels and
# provenance), not baseline-correction behavior.
_MELT_CENTER = 150.0
_PEAK = 1.2
_EXO_UP_SIGNAL = -_PEAK * np.exp(-0.5 * ((_TEMPERATURE - _MELT_CENTER) / 4.0) ** 2)
_ENDO_UP_SIGNAL = _PEAK * np.exp(-0.5 * ((_TEMPERATURE - _MELT_CENTER) / 4.0) ** 2)

# The same exothermic decomposition event, mirrored across conventions.
_DECOMPOSITION_CENTER = 180.0
_DTA_EXO_UP_SIGNAL = 0.2 + 2.0 * np.exp(-0.5 * ((_TEMPERATURE - _DECOMPOSITION_CENTER) / 5.0) ** 2)
_DTA_ENDO_UP_MIRROR = 0.2 - 2.0 * np.exp(-0.5 * ((_TEMPERATURE - _DECOMPOSITION_CENTER) / 5.0) ** 2)


def _csv(signal: np.ndarray, header: str = "Temperature (degC),Heat Flow (mW/mg)") -> bytes:
    rows = "\n".join(f"{t:.2f},{s:.6f}" for t, s in zip(_TEMPERATURE, signal))
    return f"{header}\n{rows}\n".encode("utf-8")


def _post_import(client: TestClient, project_id: str, name: str, csv_bytes: bytes, data_type: str, sign_convention: str) -> dict:
    response = client.post(
        "/dataset/import",
        headers=_TOKEN,
        json={
            "project_id": project_id,
            "file_name": f"{name}.csv",
            "file_base64": base64.b64encode(csv_bytes).decode("ascii"),
            "data_type": data_type,
            "sign_convention": sign_convention,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _new_project(client: TestClient) -> str:
    response = client.post("/workspace/new", headers=_TOKEN)
    assert response.status_code == 200
    return response.json()["project_id"]


def _run_analysis(client: TestClient, project_id: str, dataset_key: str, analysis_type: str, workflow_template_id: str, processing_overrides: dict | None = None) -> dict:
    response = client.post(
        "/analysis/run",
        headers=_TOKEN,
        json={
            "project_id": project_id,
            "dataset_key": dataset_key,
            "analysis_type": analysis_type,
            "workflow_template_id": workflow_template_id,
            "processing_overrides": processing_overrides or {},
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["execution_status"] == "saved", payload.get("failure_reason")
    detail = client.get(f"/workspace/{project_id}/results/{payload['result_id']}", headers=_TOKEN)
    assert detail.status_code == 200
    # The detail endpoint exposes rows/summary/validation at the top level.
    return detail.json()


@pytest.fixture()
def client():
    return TestClient(create_app(api_token="sign-canon-token"))


def test_melting_event_labels_endotherm_under_both_conventions(client):
    """Golden: endo-up and exo-up encodings of one event agree after canon."""
    project_id = _new_project(client)

    imported_endo = _post_import(client, project_id, "melt_endo_up", _csv(_ENDO_UP_SIGNAL), "DSC", "endo_up")
    imported_exo = _post_import(client, project_id, "melt_exo_up", _csv(_EXO_UP_SIGNAL), "DSC", "exo_up")

    # Import provenance is unambiguous on both paths.
    assert imported_endo["dataset"]["signal_convention"] == "exo_up"
    assert imported_endo["dataset"]["raw_signal_convention"] == "endo_up"
    assert imported_endo["dataset"]["signal_inverted_at_import"] is True
    assert imported_exo["dataset"]["signal_inverted_at_import"] is False

    record_endo = _run_analysis(
        client, project_id, imported_endo["dataset"]["key"], "DSC", "dsc.general",
        processing_overrides={"baseline": {"method": "linear"}},
    )
    record_exo = _run_analysis(
        client, project_id, imported_exo["dataset"]["key"], "DSC", "dsc.general",
        processing_overrides={"baseline": {"method": "linear"}},
    )

    endo_rows = [row for row in record_endo["rows"] if row["peak_type"] == "endotherm"]
    exo_rows = [row for row in record_exo["rows"] if row["peak_type"] == "endotherm"]
    assert len(endo_rows) == 1, record_endo["rows"]
    assert len(exo_rows) == 1, record_exo["rows"]

    # The event is labeled endotherm regardless of the vendor encoding.
    assert abs(endo_rows[0]["peak_temperature"] - _MELT_CENTER) < 2.0
    assert abs(exo_rows[0]["peak_temperature"] - _MELT_CENTER) < 2.0
    assert abs(endo_rows[0]["peak_temperature"] - exo_rows[0]["peak_temperature"]) < 1.0
    assert abs(abs(endo_rows[0]["area"]) - abs(exo_rows[0]["area"])) < 1e-3

    # Provenance travels into the serialized record.
    assert record_endo["summary"]["sign_convention"]["declared"] == "endo_up"
    assert record_endo["summary"]["sign_convention"]["canonical"] == "exo_up"
    assert record_endo["summary"]["sign_convention"]["inverted_at_import"] is True
    assert record_exo["summary"]["sign_convention"]["declared"] == "exo_up"
    assert record_exo["summary"]["sign_convention"]["inverted_at_import"] is False


def test_dta_mirrored_fixture_single_correctly_tagged_event(client):
    """Golden: both DTA encodings give ONE exotherm-tagged event (no dupes)."""
    project_id = _new_project(client)

    imported_exo = _post_import(
        client, project_id, "dta_exo_up",
        _csv(_DTA_EXO_UP_SIGNAL, "Temperature (degC),DeltaT (uV)"), "DTA", "exo_up",
    )
    imported_endo = _post_import(
        client, project_id, "dta_endo_up_mirror",
        _csv(_DTA_ENDO_UP_MIRROR, "Temperature (degC),DeltaT (uV)"), "DTA", "endo_up",
    )

    record_exo = _run_analysis(client, project_id, imported_exo["dataset"]["key"], "DTA", "dta.general")
    record_endo = _run_analysis(client, project_id, imported_endo["dataset"]["key"], "DTA", "dta.general")

    for record in (record_exo, record_endo):
        assert record["summary"]["exotherm_count"] == 1
        assert record["summary"]["endotherm_count"] == 0
        rows = record["rows"]
        assert len(rows) == 1, rows  # historical bug produced duplicates
        assert rows[0]["direction"] == "exo"
        assert rows[0]["peak_type"] == "exotherm"
        assert abs(rows[0]["peak_temperature"] - _DECOMPOSITION_CENTER) < 2.0

    assert record_endo["summary"]["sign_convention"]["declared"] == "endo_up"
    assert record_endo["summary"]["sign_convention"]["inverted_at_import"] is True


def test_unknown_polarity_withheld_end_to_end(client):
    """Golden: an undeclared polarity yields no endo/exo attribution."""
    project_id = _new_project(client)
    imported = _post_import(client, project_id, "melt_unknown", _csv(_ENDO_UP_SIGNAL), "DSC", "unknown")

    assert imported["dataset"]["signal_convention"] == "unknown"
    assert imported["dataset"]["raw_signal_convention"] == "unknown"

    record = _run_analysis(client, project_id, imported["dataset"]["key"], "DSC", "dsc.general")

    assert record["rows"], "peaks are still detected on unknown-polarity data"
    assert {row["peak_type"] for row in record["rows"]} == {"unknown"}
    provenance = record["summary"]["sign_convention"]
    assert provenance["declared"] == "unknown"
    assert provenance["canonical"] is None
    assert provenance["inverted_at_import"] is False
    warnings_text = " ".join(str(item) for item in record["validation"].get("warnings") or [])
    assert "polarity" in warnings_text.lower()
