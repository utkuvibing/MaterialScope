"""Workspace-backed peak deconvolution coverage (preview module).

Covers the scientific and honesty contract of
``backend.deconvolution_service`` plus the ``/deconvolution`` HTTP surface:
basis resolution (never a silent fallback), effective axis semantics, explicit
inversion, honest fit-quality naming, persistence/hydration identifiers,
``.scopezip`` round-trip, and generic export/report compatibility.
"""

from __future__ import annotations

import base64
import math
from typing import Any

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("lmfit")

from backend.deconvolution_service import (  # noqa: E402
    DeconvolutionValidationError,
    describe_options,
    run_deconvolution_workflow,
)
from backend.analysis_state import resolve_analysis_state  # noqa: E402
from backend.models import (  # noqa: E402
    DeconvolutionInitialGuess,
    DeconvolutionRunRequest,
)
from backend.workspace import summarize_result  # noqa: E402

PREVIEW_ENV = "MATERIALSCOPE_ENABLE_PREVIEW_MODULES"
DATASET_KEY = "synthetic_scan"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _Dataset:
    """Minimal stand-in for the workspace's imported dataset object."""

    def __init__(
        self,
        x: np.ndarray,
        y: np.ndarray,
        *,
        data_type: str = "DSC",
        units: dict | None = None,
        metadata: dict | None = None,
        original_columns: dict | None = None,
    ) -> None:
        self.data = pd.DataFrame({"temperature": x, "signal": y})
        self.units = units if units is not None else {"temperature": "°C", "signal": "mW"}
        self.metadata = metadata if metadata is not None else {"sample_name": "Synthetic"}
        self.data_type = data_type
        self.original_columns = original_columns if original_columns is not None else {
            "temperature": "temperature",
            "signal": "signal",
        }
        self.file_path = None
        self.signal_convention = "unknown"


def _two_gaussians(x: np.ndarray) -> np.ndarray:
    return 2.0 * np.exp(-0.5 * ((x - 120.0) / 8.0) ** 2) + 1.5 * np.exp(-0.5 * ((x - 170.0) / 10.0) ** 2)


def _thermal_dataset(**kwargs) -> _Dataset:
    x = np.linspace(50.0, 250.0, 500)
    return _Dataset(x, _two_gaussians(x), **kwargs)


def _state(dataset: _Dataset, *, analysis_type: str | None = None, analysis_state: dict | None = None) -> dict:
    state: dict = {
        "datasets": {DATASET_KEY: dataset},
        "results": {},
        "analysis_history": [],
        "figures": {},
    }
    if analysis_type is not None:
        state[f"{analysis_type.lower()}_state_{DATASET_KEY}"] = analysis_state or {}
    return state


def _request(**overrides) -> DeconvolutionRunRequest:
    payload = {
        "dataset_key": DATASET_KEY,
        "signal_basis": "raw",
        "n_peaks": 2,
        "peak_shape": "gaussian",
        "initial_params": [
            DeconvolutionInitialGuess(center=120.0, amplitude=2.0, sigma=8.0),
            DeconvolutionInitialGuess(center=170.0, amplitude=1.5, sigma=10.0),
        ],
        "invert_signal_for_fit": False,
    }
    payload.update(overrides)
    return DeconvolutionRunRequest(**payload)


def _run(state: dict, **overrides):
    return run_deconvolution_workflow(state=state, request=_request(**overrides))


def _centers(record: dict) -> list[float]:
    return [float(row["center"]) for row in record["rows"]]


def _guesses(*entries: tuple[float, float, float]) -> list[DeconvolutionInitialGuess]:
    """Build full initial guesses from (center, amplitude, sigma) triples."""
    return [
        DeconvolutionInitialGuess(center=center, amplitude=amplitude, sigma=sigma)
        for center, amplitude, sigma in entries
    ]


# ---------------------------------------------------------------------------
# Fit paths
# ---------------------------------------------------------------------------


def test_two_overlapping_gaussians_recover_centers():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state)

    centers = _centers(outcome["record"])
    assert centers[0] == pytest.approx(120.0, abs=0.5)
    assert centers[1] == pytest.approx(170.0, abs=0.5)
    assert outcome["record"]["summary"]["r_squared"] > 0.99


def test_lorentzian_fit_path():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state, peak_shape="lorentzian")

    assert outcome["record"]["summary"]["peak_shape"] == "lorentzian"
    assert all(row["fwhm"] is not None for row in outcome["record"]["rows"])


def test_pseudo_voigt_fit_path_reports_fraction():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state, peak_shape="pseudo_voigt")

    rows = outcome["record"]["rows"]
    assert outcome["record"]["summary"]["peak_shape"] == "pseudo_voigt"
    assert all(row.get("fraction") is not None for row in rows)


def test_single_peak_fit():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(
        state,
        n_peaks=1,
        initial_params=[DeconvolutionInitialGuess(center=120.0, amplitude=2.0, sigma=8.0)],
    )

    assert outcome["record"]["summary"]["peak_count"] == 1
    assert len(outcome["record"]["rows"]) == 1


def test_ten_peaks_accepted_at_the_boundary():
    x = np.linspace(50.0, 250.0, 800)
    y = np.zeros_like(x)
    for index in range(10):
        center = 70.0 + index * 12.0
        y = y + np.exp(-0.5 * ((x - center) / 2.0) ** 2)
    state = _state(_Dataset(x, y), analysis_type="DSC")

    outcome = _run(
        state,
        n_peaks=10,
        initial_params=[
            DeconvolutionInitialGuess(center=70.0 + index * 12.0, amplitude=1.0, sigma=2.0)
            for index in range(10)
        ],
    )

    assert len(outcome["record"]["rows"]) == 10


def test_more_than_ten_peaks_rejected_by_the_request_model():
    with pytest.raises(Exception) as excinfo:
        _request(n_peaks=11)
    assert "n_peaks" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Initial guesses + provenance
# ---------------------------------------------------------------------------


def test_automatic_guesses_are_recorded_as_auto():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state, initial_params=[])

    processing = outcome["record"]["processing"]
    assert processing["initial_guess_provenance"] == ["auto"]
    assert processing["auto_estimate"]["detected_peak_count"] == 2
    assert processing["auto_estimate"]["fallback_spacing_used"] is False


def test_full_user_guesses_recorded_as_user():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state)

    assert outcome["record"]["processing"]["initial_guess_provenance"] == ["user"]


def test_partial_guesses_record_mixed_field_provenance():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(
        state,
        initial_params=[DeconvolutionInitialGuess(center=120.0)],
    )

    guesses = outcome["record"]["processing"]["initial_guesses"]
    assert guesses[0]["source"] == "mixed"
    assert guesses[0]["field_sources"]["center"] == "user"
    assert guesses[0]["field_sources"]["sigma"] == "auto"


def test_more_guesses_than_components_is_rejected():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    with pytest.raises(DeconvolutionValidationError) as excinfo:
        _run(
            state,
            n_peaks=1,
            initial_params=[
                DeconvolutionInitialGuess(center=120.0, sigma=8.0, amplitude=2.0),
                DeconvolutionInitialGuess(center=170.0, sigma=10.0, amplitude=1.5),
            ],
        )
    assert "silently ignored" in str(excinfo.value)


def test_non_finite_and_invalid_guesses_are_rejected():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    with pytest.raises(DeconvolutionValidationError):
        _run(state, initial_params=[DeconvolutionInitialGuess(center=float("nan"))])
    with pytest.raises(DeconvolutionValidationError):
        _run(state, initial_params=[DeconvolutionInitialGuess(sigma=0.0)])
    with pytest.raises(DeconvolutionValidationError):
        _run(state, initial_params=[DeconvolutionInitialGuess(amplitude=-1.0)])
    with pytest.raises(DeconvolutionValidationError):
        _run(state, initial_params=[DeconvolutionInitialGuess(center=999.0)])


# ---------------------------------------------------------------------------
# Range restriction + input validation
# ---------------------------------------------------------------------------


def test_range_restriction_narrows_the_fitted_domain():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state, range_min=100.0, range_max=200.0)

    payload = outcome["record"]["report_payload"]
    assert min(payload["x"]) >= 100.0
    assert max(payload["x"]) <= 200.0
    assert outcome["record"]["processing"]["selected_range"] == [min(payload["x"]), max(payload["x"])]


def test_range_with_too_few_points_is_blocked():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    with pytest.raises(DeconvolutionValidationError) as excinfo:
        _run(state, range_min=100.0, range_max=100.5)
    assert "usable points" in str(excinfo.value)


def test_range_outside_the_domain_is_blocked():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    with pytest.raises(DeconvolutionValidationError) as excinfo:
        _run(state, range_min=500.0, range_max=600.0)
    assert "does not intersect" in str(excinfo.value)


def test_inverted_range_bounds_are_blocked():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    with pytest.raises(DeconvolutionValidationError) as excinfo:
        _run(state, range_min=200.0, range_max=100.0)
    assert "less than" in str(excinfo.value)


def test_empty_and_non_finite_signals_are_blocked():
    x = np.linspace(50.0, 250.0, 100)
    empty_state = _state(_Dataset(x, np.zeros_like(x)), analysis_type="DSC")
    empty_state[f"dsc_state_{DATASET_KEY}"] = {}

    with pytest.raises(DeconvolutionValidationError):
        _run(empty_state)

    flat = _state(_Dataset(x, np.full_like(x, np.nan)), analysis_type="DSC")
    with pytest.raises(DeconvolutionValidationError) as excinfo:
        _run(flat)
    assert "no finite axis/signal samples" in str(excinfo.value)


def test_unsupported_modality_is_blocked():
    dataset = _thermal_dataset(data_type="UNKNOWN")
    state = _state(dataset)

    with pytest.raises(DeconvolutionValidationError) as excinfo:
        _run(state)
    assert "Unsupported modality" in str(excinfo.value)


def test_unknown_dataset_raises_key_error():
    state = {"datasets": {}, "results": {}, "analysis_history": []}

    with pytest.raises(KeyError):
        _run(state)


# ---------------------------------------------------------------------------
# Signal bases
# ---------------------------------------------------------------------------


def test_raw_basis_works_without_saved_analysis_state():
    """A freshly imported dataset can be fitted on raw before any stable run."""
    dataset = _thermal_dataset()
    state = _state(dataset)

    resolved = resolve_analysis_state(state, "DSC", DATASET_KEY)
    assert resolved.has_analysis_state is False
    assert resolved.bases["raw"].available is True
    assert resolved.bases["raw"].source == "dataset_import"
    assert resolved.bases["smoothed"].available is False
    assert resolved.bases["smoothed"].reason == "no_saved_analysis_state"

    outcome = _run(state, signal_basis="raw")

    assert outcome["record"]["summary"]["signal_basis"] == "raw"
    assert outcome["record"]["processing"]["signal_basis_source"] == "dataset_import"


@pytest.mark.parametrize("basis", ["smoothed", "corrected", "normalized"])
def test_saved_processed_bases_are_usable(basis):
    x = np.linspace(50.0, 250.0, 500)
    dataset = _thermal_dataset()
    state = _state(
        dataset,
        analysis_type="DSC",
        analysis_state={"axis": x.tolist(), basis: _two_gaussians(x).tolist()},
    )

    outcome = _run(state, signal_basis=basis)

    assert outcome["record"]["processing"]["signal_basis"] == basis
    assert outcome["record"]["processing"]["signal_basis_source"] == "analysis_state"


def test_unavailable_basis_blocks_and_never_falls_back_to_raw():
    state = _state(_thermal_dataset(), analysis_type="DSC", analysis_state={})

    with pytest.raises(DeconvolutionValidationError) as excinfo:
        _run(state, signal_basis="corrected")

    message = str(excinfo.value)
    assert "corrected" in message
    assert "No fallback basis is substituted" in message
    assert "no_saved_corrected_curve" in message
    assert state["results"] == {}


def test_raw_basis_unavailable_when_the_effective_axis_was_converted():
    x = np.linspace(4000.0, 400.0, 200)
    dataset = _Dataset(
        x,
        np.linspace(0.2, 0.9, 200),
        data_type="FTIR",
        units={"temperature": "cm^-1", "signal": "absorbance"},
    )
    state = _state(
        dataset,
        analysis_type="FTIR",
        analysis_state={
            "axis": np.linspace(400.0, 4000.0, 200).tolist(),
            "axis_unit": "nm",
            "axis_role": "wavelength",
            "smoothed": np.linspace(0.3, 0.8, 200).tolist(),
            "diagnostics": {"axis_conversion": {"basis": "converted"}},
        },
    )

    resolved = resolve_analysis_state(state, "FTIR", DATASET_KEY)
    assert resolved.bases["raw"].available is False
    assert resolved.bases["raw"].reason == "raw_signal_not_aligned_with_effective_axis"
    assert resolved.bases["smoothed"].available is True

    with pytest.raises(DeconvolutionValidationError) as excinfo:
        _run(state, signal_basis="raw")
    assert "raw_signal_not_aligned_with_effective_axis" not in str(excinfo.value)
    assert "original imported axis" in str(excinfo.value)


def test_unsupported_basis_name_is_blocked():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    with pytest.raises(DeconvolutionValidationError) as excinfo:
        _run(state, signal_basis="dtg")
    assert "signal_basis must be one of" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Polarity / inversion honesty
# ---------------------------------------------------------------------------


def test_inversion_is_recorded_when_explicitly_requested():
    x = np.linspace(50.0, 250.0, 500)
    dataset = _Dataset(x, -_two_gaussians(x))
    state = _state(dataset, analysis_type="DSC")

    outcome = _run(state, invert_signal_for_fit=True)

    processing = outcome["record"]["processing"]
    payload = outcome["record"]["report_payload"]
    assert processing["inversion_applied"] is True
    assert "multiplied by -1" in processing["inversion_semantics"]
    assert payload["inversion_applied"] is True
    assert "negated for fit" in payload["ylabel"]
    assert outcome["record"]["provenance"]["inversion_applied"] is True
    assert outcome["record"]["summary"]["inversion_applied"] is True
    # The fitted input is the negated signal.
    assert max(payload["y"]) > 0


def test_no_automatic_inversion_for_negative_signals():
    x = np.linspace(50.0, 250.0, 500)
    dataset = _Dataset(x, -_two_gaussians(x))
    state = _state(dataset)

    with pytest.raises(DeconvolutionValidationError) as excinfo:
        _run(state)

    message = str(excinfo.value)
    assert "no positive structure" in message
    assert "never modified automatically" in message
    assert state["results"] == {}


def test_positive_signals_are_never_marked_as_inverted():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state)

    assert outcome["record"]["processing"]["inversion_applied"] is False
    assert outcome["record"]["summary"]["inversion_applied"] is False
    assert outcome["record"]["report_payload"]["inversion_applied"] is False
    assert "as stored" in outcome["record"]["processing"]["inversion_semantics"]


# ---------------------------------------------------------------------------
# Axis / unit semantics
# ---------------------------------------------------------------------------


def test_thermal_axis_reports_temperature_units():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state)

    assert outcome["axis_role"] == "temperature"
    assert outcome["axis_unit"] == "°C"
    assert "Temperature" in outcome["record"]["report_payload"]["xlabel"]


def test_ftir_axis_is_not_labelled_as_temperature():
    x = np.linspace(4000.0, 400.0, 300)
    y = 1.0 * np.exp(-0.5 * ((x - 1700.0) / 30.0) ** 2) + 0.6 * np.exp(-0.5 * ((x - 1600.0) / 25.0) ** 2)
    dataset = _Dataset(x, y, data_type="FTIR", units={"temperature": "cm^-1", "signal": "absorbance"})
    state = _state(
        dataset,
        analysis_type="FTIR",
        analysis_state={
            "axis": x.tolist(),
            "axis_role": "wavenumber",
            "axis_unit": "cm^-1",
            "signal_role": "absorbance",
            "signal_unit": "absorbance",
        },
    )

    outcome = _run(state, initial_params=_guesses((1700.0, 1.0, 30.0), (1600.0, 0.6, 25.0)))

    payload = outcome["record"]["report_payload"]
    assert outcome["axis_role"] == "wavenumber"
    assert outcome["axis_unit"] == "cm^-1"
    assert "Wavenumber" in payload["xlabel"]
    assert "°C" not in payload["xlabel"]
    assert "temperature" not in payload["xlabel"].lower()


def test_raman_converted_axis_keeps_effective_role_and_unit():
    x = np.linspace(500.0, 3500.0, 300)
    y = np.exp(-0.5 * ((x - 1000.0) / 50.0) ** 2)
    dataset = _Dataset(x, y, data_type="RAMAN", units={"temperature": "nm", "signal": "counts"})
    state = _state(
        dataset,
        analysis_type="RAMAN",
        analysis_state={
            "axis": x.tolist(),
            "axis_role": "wavelength",
            "axis_unit": "nm",
            "signal_role": "intensity",
            "signal_unit": "counts",
        },
    )

    outcome = _run(state, n_peaks=1, initial_params=_guesses((1000.0, 1.0, 50.0)))

    assert outcome["axis_role"] == "wavelength"
    assert outcome["axis_unit"] == "nm"
    assert "Wavelength" in outcome["record"]["report_payload"]["xlabel"]
    assert "nm" in outcome["record"]["report_payload"]["xlabel"]


def test_xrd_two_theta_axis_semantics():
    x = np.linspace(10.0, 80.0, 400)
    y = np.exp(-0.5 * ((x - 30.0) / 0.4) ** 2) + 0.7 * np.exp(-0.5 * ((x - 32.0) / 0.5) ** 2)
    dataset = _Dataset(
        x,
        y,
        data_type="XRD",
        units={"temperature": "degree_2theta", "signal": "counts"},
        metadata={"xrd_axis_role": "two_theta", "xrd_axis_unit": "degree_2theta"},
    )
    state = _state(dataset, analysis_type="XRD", analysis_state={"axis": x.tolist()})

    outcome = _run(state, initial_params=_guesses((30.0, 1.0, 0.4), (32.0, 0.7, 0.5)))

    assert outcome["axis_role"] == "two_theta"
    payload = outcome["record"]["report_payload"]
    assert "2θ" in payload["xlabel"]
    assert "°C" not in payload["xlabel"]


def test_describe_options_reports_domain_and_basis_reasons():
    dataset = _thermal_dataset()
    state = _state(dataset)

    options = describe_options(resolve_analysis_state(state, "DSC", DATASET_KEY))

    assert options["has_analysis_state"] is False
    assert options["axis_domain"][0] == pytest.approx(50.0)
    assert options["axis_domain"][1] == pytest.approx(250.0)
    reasons = {entry["name"]: entry["reason"] for entry in options["bases"]}
    assert reasons["raw"] is None
    assert reasons["corrected"] == "no_saved_analysis_state"


# ---------------------------------------------------------------------------
# lmfit parameter semantics + fit quality
# ---------------------------------------------------------------------------


def test_amplitude_is_not_presented_as_peak_height():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state)

    record = outcome["record"]
    assert record["summary"]["amplitude_semantics"] == "integrated_area_parameter"
    assert "not a peak height" in record["processing"]["component_parameter_semantics"]
    first = record["rows"][0]
    assert first["amplitude"] > first["height"]
    assert record["rows"][0]["fwhm"] is not None


def test_fit_quality_uses_honest_naming():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state)

    summary = outcome["record"]["summary"]
    assert summary["sse_per_dof"] is not None
    assert summary["dof"] == 494
    assert summary["rmse"] is not None
    assert summary["mae"] is not None
    assert summary["max_abs_residual"] is not None
    limitations = " ".join(outcome["record"]["scientific_context"]["limitations"])
    assert "unweighted" in limitations.lower()
    assert "not a metrologically interpretable reduced chi-square" in limitations.lower()
    assert "user/model choice" in limitations


def test_ftir_transmittance_warns_without_blocking_or_inverting():
    """The %T advisory is role-based: it fires and the run still completes."""
    x = np.linspace(4000.0, 400.0, 300)
    y = 0.1 + 0.5 * np.exp(-0.5 * ((x - 1700.0) / 30.0) ** 2)
    dataset = _Dataset(x, y, data_type="FTIR", units={"temperature": "cm^-1", "signal": "%T"})
    state = _state(
        dataset,
        analysis_type="FTIR",
        analysis_state={
            "axis": x.tolist(),
            "axis_unit": "cm^-1",
            "axis_role": "wavenumber",
            "signal_role": "transmittance",
            "signal_unit": "%T",
        },
    )

    outcome = _run(state, n_peaks=1, initial_params=_guesses((1700.0, 0.5, 30.0)))

    warnings = outcome["warnings"]
    assert any("transmittance" in item.lower() for item in warnings)
    assert outcome["record"]["validation"]["status"] == "warn"
    assert outcome["record"]["processing"]["inversion_applied"] is False
    assert outcome["record"]["summary"]["inversion_applied"] is False


def test_ftir_transmittance_dip_failure_carries_the_guidance():
    """A real %T dip cannot be represented by non-negative components.

    The run stays allowed by policy, but the numerical failure must explain the
    likely cause and persist nothing rather than inventing a result.
    """
    x = np.linspace(4000.0, 400.0, 300)
    y = 1.0 - 0.4 * np.exp(-0.5 * ((x - 1700.0) / 30.0) ** 2)
    dataset = _Dataset(x, y, data_type="FTIR", units={"temperature": "cm^-1", "signal": "%T"})
    state = _state(
        dataset,
        analysis_type="FTIR",
        analysis_state={
            "axis": x.tolist(),
            "axis_unit": "cm^-1",
            "axis_role": "wavenumber",
            "signal_role": "transmittance",
            "signal_unit": "%T",
        },
    )

    with pytest.raises(DeconvolutionValidationError) as excinfo:
        _run(state, n_peaks=1, initial_params=_guesses((1700.0, 0.5, 30.0)))

    message = str(excinfo.value)
    assert "Peak fit failed" in message
    assert "transmittance" in message.lower()
    assert state["results"] == {}


def test_no_transmittance_warning_once_inverted():
    """A baseline-relative %T band: inversion is the honest, user-declared path."""
    x = np.linspace(4000.0, 400.0, 300)
    y = 0.2 - 0.6 * np.exp(-0.5 * ((x - 1700.0) / 30.0) ** 2)
    dataset = _Dataset(x, y, data_type="FTIR", units={"temperature": "cm^-1", "signal": "%T"})
    state = _state(
        dataset,
        analysis_type="FTIR",
        analysis_state={
            "axis": x.tolist(),
            "axis_unit": "cm^-1",
            "axis_role": "wavenumber",
            "signal_role": "transmittance",
            "signal_unit": "%T",
        },
    )

    outcome = _run(
        state,
        n_peaks=1,
        initial_params=_guesses((1700.0, 0.6, 30.0)),
        invert_signal_for_fit=True,
    )

    assert not any("transmittance" in item.lower() for item in outcome["warnings"])
    assert outcome["record"]["processing"]["inversion_applied"] is True
    assert max(outcome["record"]["report_payload"]["y"]) > 0


# ---------------------------------------------------------------------------
# Persistence, ids, hydration identifiers
# ---------------------------------------------------------------------------


def test_repeat_runs_get_unique_result_ids():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    first = _run(state)
    second = _run(state)
    third = _run(state)

    assert first["result_id"] == f"deconv_{DATASET_KEY}"
    assert second["result_id"] == f"deconv_{DATASET_KEY}_2"
    assert third["result_id"] == f"deconv_{DATASET_KEY}_3"
    assert set(state["results"]) == {first["result_id"], second["result_id"], third["result_id"]}


def test_result_carries_the_preview_analysis_scope():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state)

    record = state["results"][outcome["result_id"]]
    assert record["provenance"]["analysis_scope"] == "preview_deconvolution"
    assert record["status"] == "experimental"
    summary = summarize_result(record)
    assert summary.analysis_scope == "preview_deconvolution"
    assert summary.dataset_key == DATASET_KEY


def test_successful_run_appends_a_history_event():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state)

    history = state["analysis_history"]
    assert history[-1]["action"] == "Peak Deconvolution"
    assert history[-1]["page"] == "Deconvolution"
    assert history[-1]["result_id"] == outcome["result_id"]
    assert history[-1]["dataset_key"] == DATASET_KEY


def test_report_payload_is_renderable_without_refitting():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state)

    payload = outcome["record"]["report_payload"]
    assert len(payload["x"]) == len(payload["y"]) == len(payload["fitted"]) == len(payload["residual"])
    assert len(payload["components"]) == 2
    assert all(len(component) == len(payload["x"]) for component in payload["components"])
    assert payload["xlabel"] and payload["ylabel"]
    assert all(isinstance(float(value), float) for value in payload["x"][:5])


def test_all_arrays_are_json_safe():
    import json

    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state)

    json.dumps(outcome["record"]["report_payload"])
    json.dumps(outcome["record"]["summary"])
    json.dumps(outcome["record"]["rows"])


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from backend.app import create_app

    return TestClient(create_app())


def _import_dataset(
    client,
    project_id: str,
    csv_text: str,
    *,
    data_type: str,
    name: str,
    metadata: dict | None = None,
) -> str:
    payload: dict[str, Any] = {
        "project_id": project_id,
        "file_name": name,
        "file_base64": base64.b64encode(csv_text.encode("utf-8")).decode("ascii"),
        "data_type": data_type,
    }
    if metadata:
        payload["metadata"] = metadata
    response = client.post("/dataset/import", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["dataset"]["key"]


def _run_stable_analysis(
    client,
    project_id: str,
    dataset_key: str,
    analysis_type: str,
    *,
    workflow_template_id: str,
    processing_overrides: dict | None = None,
) -> dict:
    payload: dict[str, Any] = {
        "project_id": project_id,
        "dataset_key": dataset_key,
        "analysis_type": analysis_type,
        "workflow_template_id": workflow_template_id,
    }
    if processing_overrides:
        payload["processing_overrides"] = processing_overrides
    run = client.post("/analysis/run", json=payload)
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["execution_status"] == "saved", body
    return body


def _thermal_csv() -> str:
    x = np.linspace(50.0, 250.0, 500)
    y = _two_gaussians(x)
    rows = "\n".join(f"{t:.4f},{v:.6f}" for t, v in zip(x, y))
    return f"Temperature,HeatFlow\n{rows}\n"


def test_endpoint_blocked_when_preview_disabled(client, monkeypatch):
    monkeypatch.delenv(PREVIEW_ENV, raising=False)
    project_id = client.post("/workspace/new").json()["project_id"]

    response = client.post(
        f"/workspace/{project_id}/deconvolution/run",
        json={"dataset_key": "anything", "n_peaks": 2},
    )

    assert response.status_code == 403


def test_options_endpoint_blocked_when_preview_disabled(client, monkeypatch):
    monkeypatch.delenv(PREVIEW_ENV, raising=False)
    project_id = client.post("/workspace/new").json()["project_id"]

    response = client.get(f"/workspace/{project_id}/deconvolution/options/anything")

    assert response.status_code == 403


def test_endpoint_success_path_persists_a_workspace_result(client, monkeypatch):
    monkeypatch.setenv(PREVIEW_ENV, "1")
    project_id = client.post("/workspace/new").json()["project_id"]
    dataset_key = _import_dataset(client, project_id, _thermal_csv(), data_type="DSC", name="thermal.csv")

    options = client.get(f"/workspace/{project_id}/deconvolution/options/{dataset_key}")
    assert options.status_code == 200
    assert options.json()["bases"][0]["name"] == "raw"
    assert options.json()["bases"][0]["available"] is True

    response = client.post(
        f"/workspace/{project_id}/deconvolution/run",
        json={
            "dataset_key": dataset_key,
            "signal_basis": "raw",
            "n_peaks": 2,
            "peak_shape": "gaussian",
            "initial_params": [
                {"center": 120.0, "amplitude": 2.0, "sigma": 8.0},
                {"center": 170.0, "amplitude": 1.5, "sigma": 10.0},
            ],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["execution_status"] == "saved"
    assert body["result_id"]
    assert body["axis_role"] == "temperature"
    assert body["inversion_applied"] is False
    assert body["report_payload"]["x"]
    assert body["validation"]["status"] in {"pass", "warn"}

    results = client.get(f"/workspace/{project_id}/results").json()
    ids = [item["id"] for item in results.get("results", [])]
    assert body["result_id"] in ids
    scopes = {item["id"]: item["analysis_scope"] for item in results.get("results", [])}
    assert scopes[body["result_id"]] == "preview_deconvolution"


def test_endpoint_result_detail_is_compatible(client, monkeypatch):
    monkeypatch.setenv(PREVIEW_ENV, "1")
    project_id = client.post("/workspace/new").json()["project_id"]
    dataset_key = _import_dataset(client, project_id, _thermal_csv(), data_type="DSC", name="thermal.csv")

    run = client.post(
        f"/workspace/{project_id}/deconvolution/run",
        json={
            "dataset_key": dataset_key,
            "signal_basis": "raw",
            "n_peaks": 2,
            "peak_shape": "gaussian",
            "initial_params": [
                {"center": 120.0, "amplitude": 2.0, "sigma": 8.0},
                {"center": 170.0, "amplitude": 1.5, "sigma": 10.0},
            ],
        },
    ).json()

    detail = client.get(f"/workspace/{project_id}/results/{run['result_id']}")

    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["summary"]["amplitude_semantics"] == "integrated_area_parameter"
    assert payload["processing"]["signal_basis"] == "raw"
    assert payload["provenance"]["analysis_scope"] == "preview_deconvolution"
    assert payload["report_payload"]["x"]
    assert payload["rows"]
    assert payload["scientific_context"]["limitations"]


def test_endpoint_blocks_unavailable_basis_with_400(client, monkeypatch):
    monkeypatch.setenv(PREVIEW_ENV, "1")
    project_id = client.post("/workspace/new").json()["project_id"]
    dataset_key = _import_dataset(client, project_id, _thermal_csv(), data_type="DSC", name="thermal.csv")

    response = client.post(
        f"/workspace/{project_id}/deconvolution/run",
        json={"dataset_key": dataset_key, "signal_basis": "corrected", "n_peaks": 2},
    )

    assert response.status_code == 400
    assert "No fallback basis is substituted" in response.json()["detail"]


def test_endpoint_unknown_dataset_returns_404(client, monkeypatch):
    monkeypatch.setenv(PREVIEW_ENV, "1")
    project_id = client.post("/workspace/new").json()["project_id"]

    response = client.post(
        f"/workspace/{project_id}/deconvolution/run",
        json={"dataset_key": "missing", "n_peaks": 2},
    )

    assert response.status_code == 404


def test_endpoint_rejects_out_of_range_peak_count(client, monkeypatch):
    monkeypatch.setenv(PREVIEW_ENV, "1")
    project_id = client.post("/workspace/new").json()["project_id"]

    response = client.post(
        f"/workspace/{project_id}/deconvolution/run",
        json={"dataset_key": "missing", "n_peaks": 11},
    )

    assert response.status_code == 422


def test_scopezip_round_trip_preserves_result_and_payload(tmp_path, monkeypatch):
    from core.project_io import deserialize_project, serialize_project

    state = _state(_thermal_dataset(), analysis_type="DSC")
    outcome = _run(state)

    payload = serialize_project(state)
    archive = {
        **payload["datasets"],
        **payload["figures"],
        **payload["branding_assets"],
    }
    restored = deserialize_project(
        payload["manifest"],
        archive,
        results_payload=payload["results"],
        history_payload=payload["history"],
    )

    restored_record = restored["results"][outcome["result_id"]]
    assert restored_record["provenance"]["analysis_scope"] == "preview_deconvolution"
    assert restored_record["report_payload"]["x"]
    assert len(restored_record["report_payload"]["components"]) == 2
    assert summarize_result(restored_record).analysis_scope == "preview_deconvolution"


def test_generic_exports_and_reports_accept_the_result(tmp_path):
    from backend.exports import (
        build_export_preparation,
        generate_report_docx_artifact,
        generate_report_pdf_artifact,
        generate_results_csv_artifact,
        generate_results_xlsx_artifact,
    )

    state = _state(_thermal_dataset(), analysis_type="DSC")
    outcome = _run(state)

    preparation = build_export_preparation(state)
    assert any(item.id == outcome["result_id"] for item in preparation["exportable_results"])
    assert not preparation["skipped_record_issues"]

    csv_artifact = generate_results_csv_artifact(state, selected_result_ids=[outcome["result_id"]])
    assert csv_artifact["included_result_ids"] == [outcome["result_id"]]
    assert csv_artifact["artifact_base64"]

    xlsx_artifact = generate_results_xlsx_artifact(state, selected_result_ids=[outcome["result_id"]])
    assert xlsx_artifact["included_result_ids"] == [outcome["result_id"]]
    assert xlsx_artifact["artifact_base64"]

    docx_artifact = generate_report_docx_artifact(
        state, selected_result_ids=[outcome["result_id"]], include_figures=False
    )
    assert docx_artifact["included_result_ids"] == [outcome["result_id"]]

    pdf_artifact = generate_report_pdf_artifact(
        state, selected_result_ids=[outcome["result_id"]], include_figures=False
    )
    assert pdf_artifact["included_result_ids"] == [outcome["result_id"]]


def test_figure_registration_path_accepts_the_result(client, monkeypatch):
    monkeypatch.setenv(PREVIEW_ENV, "1")
    project_id = client.post("/workspace/new").json()["project_id"]
    dataset_key = _import_dataset(client, project_id, _thermal_csv(), data_type="DSC", name="thermal.csv")

    run = client.post(
        f"/workspace/{project_id}/deconvolution/run",
        json={
            "dataset_key": dataset_key,
            "signal_basis": "raw",
            "n_peaks": 2,
            "peak_shape": "gaussian",
            "initial_params": [
                {"center": 120.0, "amplitude": 2.0, "sigma": 8.0},
                {"center": 170.0, "amplitude": 1.5, "sigma": 10.0},
            ],
        },
    ).json()

    png = base64.b64encode(b"\x89PNG\r\n\x1a\n fake").decode("ascii")
    register = client.post(
        f"/workspace/{project_id}/results/{run['result_id']}/figure",
        json={
            "figure_png_base64": png,
            "figure_label": "Peak Deconvolution Analysis - synthetic.csv",
        },
    )

    assert register.status_code == 200, register.text
    detail = client.get(f"/workspace/{project_id}/results/{run['result_id']}").json()
    assert detail["figure_artifacts"]["report_figure_key"]
    assert detail["figure_artifacts"]["figure_keys"]


def test_analysis_state_curves_contract_is_unchanged_for_fresh_datasets(client, monkeypatch):
    """The shared resolver must not change the existing curves endpoint."""
    monkeypatch.setenv(PREVIEW_ENV, "1")
    project_id = client.post("/workspace/new").json()["project_id"]
    dataset_key = _import_dataset(client, project_id, _thermal_csv(), data_type="DSC", name="thermal.csv")

    curves = client.get(f"/workspace/{project_id}/analysis-state/DSC/{dataset_key}")

    assert curves.status_code == 200
    body = curves.json()
    # Unchanged backward-compatible empty surface when no analysis state exists.
    assert body["temperature"] == []
    assert body["raw_signal"] == []
    assert body["has_smoothed"] is False
    assert body["axis_role"] is None


def test_nan_inputs_never_reach_the_fit():
    x = np.linspace(50.0, 250.0, 500)
    y = _two_gaussians(x)
    y[::7] = np.nan
    state = _state(_Dataset(x, y), analysis_type="DSC")

    outcome = _run(state)

    payload = outcome["record"]["report_payload"]
    # Non-finite samples are dropped before fitting, so the persisted fitted
    # input contains no holes and no nulls.
    assert all(value is not None and math.isfinite(float(value)) for value in payload["y"])
    assert len(payload["x"]) == len(payload["y"]) == len(payload["fitted"])


# ---------------------------------------------------------------------------
# Basis-specific signal semantics (%T raw + converted absorbance working state)
# ---------------------------------------------------------------------------

_FTIR_WN = np.linspace(4000.0, 400.0, 300)


def _ftir_transmittance_dip() -> np.ndarray:
    """A realistic %T spectrum: a downward absorption band on a flat baseline."""
    return 1.0 - 0.4 * np.exp(-0.5 * ((_FTIR_WN - 1700.0) / 30.0) ** 2)


def _ftir_transmittance_bump() -> np.ndarray:
    """A baseline-relative %T spectrum with positive-going structure."""
    return 0.1 + 0.5 * np.exp(-0.5 * ((_FTIR_WN - 1700.0) / 30.0) ** 2)


def _ftir_dataset(signal: np.ndarray) -> _Dataset:
    return _Dataset(
        _FTIR_WN,
        signal,
        data_type="FTIR",
        units={"temperature": "cm^-1", "signal": "%T"},
        metadata={"sample_name": "ir"},
        original_columns={"temperature": "Wavenumber (cm-1)", "signal": "Transmittance (%T)"},
    )


def _absorbed_state(signal: np.ndarray) -> dict:
    """Saved FTIR state *after* the stable %T -> absorbance conversion."""
    absorbance = -np.log10(np.clip(signal, 1e-9, None))
    return {
        "axis": _FTIR_WN.tolist(),
        "axis_unit": "cm^-1",
        "axis_role": "wavenumber",
        "signal_role": "absorbance",
        "signal_unit": "absorbance",
        "smoothed": absorbance.tolist(),
        "corrected": absorbance.tolist(),
        "normalized": (absorbance / float(np.max(absorbance))).tolist(),
        "diagnostics": {"signal_role": "absorbance"},
        "processing": {"method_context": {"ftir_signal_role": "absorbance"}},
    }


def test_resolver_signal_semantics_are_basis_specific():
    """A %T import whose working state was converted must not leak semantics."""
    dataset = _ftir_dataset(_ftir_transmittance_dip())
    state = _state(dataset, analysis_type="FTIR", analysis_state=_absorbed_state(_ftir_transmittance_dip()))

    resolved = resolve_analysis_state(state, "FTIR", DATASET_KEY)
    bases = resolved.bases

    # Raw is the imported curve, not the saved working signal.
    assert bases["raw"].signal_role == "transmittance"
    assert bases["raw"].signal_unit == "%T"
    assert bases["raw"].dimensional_basis == "physical"
    assert bases["raw"].role_provenance == "declared_unit"

    for name in ("smoothed", "corrected"):
        assert bases[name].signal_role == "absorbance"
        assert bases[name].signal_unit == "absorbance"

    # Normalized keeps the useful role but claims no physical unit.
    assert bases["normalized"].signal_role == "absorbance"
    assert bases["normalized"].signal_unit is None
    assert bases["normalized"].dimensional_basis == "normalized"

    # The endpoint-level effective semantics stay the saved working signal.
    assert resolved.signal_role == "absorbance"
    assert resolved.signal_unit == "absorbance"


def test_resolver_keeps_raw_transmittance_for_a_fresh_import():
    dataset = _ftir_dataset(_ftir_transmittance_dip())
    state = _state(dataset)

    resolved = resolve_analysis_state(state, "FTIR", DATASET_KEY)

    assert resolved.has_analysis_state is False
    assert resolved.bases["raw"].available is True
    assert resolved.bases["raw"].signal_role == "transmittance"
    assert resolved.bases["raw"].signal_unit == "%T"
    assert resolved.bases["corrected"].available is False


def test_raw_semantics_do_not_claim_absorbance_when_provenance_is_generic():
    """A generic unit leaves the raw role unresolved instead of guessing."""
    dataset = _Dataset(
        _FTIR_WN,
        _ftir_transmittance_dip(),
        data_type="FTIR",
        units={"temperature": "cm^-1", "signal": "a.u."},
        original_columns={"temperature": "Wavenumber (cm-1)", "signal": "Signal"},
    )
    state = _state(dataset)

    resolved = resolve_analysis_state(state, "FTIR", DATASET_KEY)

    assert resolved.bases["raw"].signal_role is None
    assert resolved.bases["raw"].signal_unit == "a.u."
    assert resolved.bases["raw"].role_provenance == "unresolved"


def test_raw_semantics_use_the_column_header_when_the_unit_is_generic():
    dataset = _Dataset(
        _FTIR_WN,
        _ftir_transmittance_dip(),
        data_type="FTIR",
        units={"temperature": "cm^-1", "signal": "%"},
        original_columns={"temperature": "Wavenumber (cm-1)", "signal": "Transmittance (%T)"},
    )
    state = _state(dataset)

    resolved = resolve_analysis_state(state, "FTIR", DATASET_KEY)

    assert resolved.bases["raw"].signal_role == "transmittance"
    assert resolved.bases["raw"].role_provenance == "column_header"


def test_basis_labels_follow_the_selected_basis():
    dataset = _ftir_dataset(_ftir_transmittance_dip())
    state = _state(dataset, analysis_type="FTIR", analysis_state=_absorbed_state(_ftir_transmittance_dip()))

    options = describe_options(resolve_analysis_state(state, "FTIR", DATASET_KEY))
    by_name = {entry["name"]: entry for entry in options["bases"]}

    assert "Transmittance" in by_name["raw"]["signal_label"]
    assert "Absorbance" in by_name["corrected"]["signal_label"]
    # Normalized bases use an explicit path that cannot pick up a default
    # physical unit.
    assert by_name["normalized"]["signal_label"] == "Normalized absorbance"


def test_run_on_raw_records_transmittance_semantics_and_warns():
    """Raw keeps %T semantics, so the transmittance advisory must fire."""
    dataset = _ftir_dataset(_ftir_transmittance_bump())
    state = _state(dataset, analysis_type="FTIR", analysis_state=_absorbed_state(_ftir_transmittance_bump()))

    outcome = _run(state, n_peaks=1, initial_params=_guesses((1700.0, 0.5, 30.0)))

    processing = outcome["record"]["processing"]
    provenance = outcome["record"]["provenance"]
    summary = outcome["record"]["summary"]
    assert processing["signal_role"] == "transmittance"
    assert processing["signal_unit"] == "%T"
    assert processing["signal_dimensional_basis"] == "physical"
    assert provenance["fit_signal_role"] == "transmittance"
    assert provenance["fit_signal_unit"] == "%T"
    assert summary["signal_unit"] == "%T"
    assert any("transmittance" in item.lower() for item in outcome["warnings"])
    assert "Transmittance" in outcome["record"]["report_payload"]["ylabel"]


def test_run_on_corrected_uses_absorbance_semantics_without_the_advisory():
    dataset = _ftir_dataset(_ftir_transmittance_dip())
    state = _state(dataset, analysis_type="FTIR", analysis_state=_absorbed_state(_ftir_transmittance_dip()))

    outcome = _run(
        state,
        signal_basis="corrected",
        n_peaks=1,
        initial_params=_guesses((1700.0, 30.0, 30.0)),
    )

    processing = outcome["record"]["processing"]
    summary = outcome["record"]["summary"]
    assert processing["signal_role"] == "absorbance"
    assert processing["signal_unit"] == "absorbance"
    assert processing["signal_basis_source"] == "analysis_state"
    assert not any("transmittance" in item.lower() for item in outcome["warnings"])
    assert summary["signal_unit"] == "absorbance"
    assert summary["sse_per_dof_unit"] == "absorbance²"
    assert summary["amplitude_unit"] == "absorbance·cm^-1"
    assert "Absorbance" in outcome["record"]["report_payload"]["ylabel"]


def test_run_on_normalized_does_not_claim_a_physical_unit():
    dataset = _ftir_dataset(_ftir_transmittance_dip())
    state = _state(dataset, analysis_type="FTIR", analysis_state=_absorbed_state(_ftir_transmittance_dip()))

    outcome = _run(
        state,
        signal_basis="normalized",
        n_peaks=1,
        initial_params=_guesses((1700.0, 0.5, 30.0)),
    )

    processing = outcome["record"]["processing"]
    summary = outcome["record"]["summary"]
    assert processing["signal_role"] == "absorbance"
    assert processing["signal_unit"] is None
    assert processing["signal_dimensional_basis"] == "normalized"
    assert summary["signal_unit"] is None
    assert summary["sse_per_dof_unit"] is None
    assert "amplitude_unit" not in summary
    # No physical unit may leak into the persisted figure label.
    assert outcome["record"]["report_payload"]["ylabel"] == "Normalized absorbance"


def test_sse_per_dof_unit_is_squared_signal_units_when_known():
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state)

    summary = outcome["record"]["summary"]
    assert summary["sse_per_dof_unit"] == "mW²"
    assert summary["signal_dimensional_basis"] == "physical"


def test_sse_per_dof_unit_is_unspecified_when_the_unit_is_unknown():
    x = np.linspace(50.0, 250.0, 500)
    dataset = _Dataset(x, _two_gaussians(x), units={"temperature": "°C", "signal": ""})
    state = _state(dataset, analysis_type="DSC")

    outcome = _run(state)

    summary = outcome["record"]["summary"]
    assert summary["signal_unit"] is None
    assert summary["sse_per_dof_unit"] is None


# ---------------------------------------------------------------------------
# Production path: real FTIR %T -> absorbance analysis
# ---------------------------------------------------------------------------


def _ftir_pct_csv() -> str:
    rows = "\n".join(f"{wn:.4f},{value:.8f}" for wn, value in zip(_FTIR_WN, _ftir_transmittance_dip()))
    return f"Wavenumber (cm-1),Transmittance (%T)\n{rows}\n"


def test_ftir_transmittance_to_absorbance_production_path(client, monkeypatch):
    """Real stable FTIR conversion: options and runs must follow the basis."""
    monkeypatch.setenv(PREVIEW_ENV, "1")
    project_id = client.post("/workspace/new").json()["project_id"]
    dataset_key = _import_dataset(client, project_id, _ftir_pct_csv(), data_type="FTIR", name="ir_pct.csv")

    # A. the imported dataset really is %T
    detail = client.get(f"/workspace/{project_id}/datasets/{dataset_key}").json()
    assert detail["units"]["signal"] == "%T"

    # B. the REAL stable FTIR path, with %T -> absorbance enabled
    run = client.post(
        "/analysis/run",
        json={
            "project_id": project_id,
            "dataset_key": dataset_key,
            "analysis_type": "FTIR",
            "workflow_template_id": "ftir.general",
            "processing_overrides": {"signal_conversion": {"enabled": True}},
        },
    )
    assert run.status_code == 200, run.text
    run_body = run.json()
    assert run_body["execution_status"] == "saved"
    stable = client.get(f"/workspace/{project_id}/results/{run_body['result_id']}").json()
    assert stable["summary"]["converted_to_absorbance"] is True

    # C. deconvolution options follow the saved conversion per basis
    options = client.get(f"/workspace/{project_id}/deconvolution/options/{dataset_key}")
    assert options.status_code == 200, options.text
    by_name = {entry["name"]: entry for entry in options.json()["bases"]}

    assert by_name["raw"]["available"] is True
    assert by_name["raw"]["signal_role"] == "transmittance"
    assert by_name["raw"]["signal_unit"] == "%T"
    assert "Transmittance" in by_name["raw"]["signal_label"]

    for name in ("smoothed", "corrected"):
        assert by_name[name]["available"] is True
        assert by_name[name]["signal_role"] == "absorbance"
        assert by_name[name]["signal_unit"] == "absorbance"

    assert by_name["normalized"]["signal_role"] == "absorbance"
    assert by_name["normalized"]["signal_unit"] is None
    assert by_name["normalized"]["dimensional_basis"] == "normalized"
    assert by_name["normalized"]["signal_label"] == "Normalized absorbance"

    # D. corrected fits the real absorbance bands with absorbance semantics
    corrected = client.post(
        f"/workspace/{project_id}/deconvolution/run",
        json={
            "dataset_key": dataset_key,
            "signal_basis": "corrected",
            "n_peaks": 1,
            "peak_shape": "gaussian",
            "initial_params": [{"center": 1700.0, "sigma": 30.0, "amplitude": 30.0}],
        },
    )
    assert corrected.status_code == 200, corrected.text
    corrected_body = corrected.json()
    assert corrected_body["signal_role"] == "absorbance"
    assert corrected_body["signal_unit"] == "absorbance"
    assert corrected_body["result_summary"]["sse_per_dof_unit"] == "absorbance²"
    assert not any("transmittance" in item.lower() for item in corrected_body["warnings"])

    corrected_detail = client.get(f"/workspace/{project_id}/results/{corrected_body['result_id']}").json()
    assert corrected_detail["processing"]["signal_role"] == "absorbance"
    assert corrected_detail["provenance"]["fit_signal_role"] == "absorbance"

    # E. normalized fits with no physical unit claimed anywhere
    normalized = client.post(
        f"/workspace/{project_id}/deconvolution/run",
        json={
            "dataset_key": dataset_key,
            "signal_basis": "normalized",
            "n_peaks": 1,
            "peak_shape": "gaussian",
            "initial_params": [{"center": 1700.0, "sigma": 30.0, "amplitude": 0.5}],
        },
    )
    assert normalized.status_code == 200, normalized.text
    normalized_body = normalized.json()
    assert normalized_body["signal_unit"] is None
    assert normalized_body["signal_dimensional_basis"] == "normalized"
    assert normalized_body["result_summary"]["signal_unit"] is None
    assert normalized_body["result_summary"]["sse_per_dof_unit"] is None


def test_ftir_raw_basis_run_keeps_transmittance_provenance(client, monkeypatch):
    """Selecting raw on a converted dataset must not borrow absorbance."""
    monkeypatch.setenv(PREVIEW_ENV, "1")
    project_id = client.post("/workspace/new").json()["project_id"]
    bump_rows = "\n".join(f"{wn:.4f},{value:.8f}" for wn, value in zip(_FTIR_WN, _ftir_transmittance_bump()))
    dataset_key = _import_dataset(
        client, project_id, f"Wavenumber (cm-1),Transmittance (%T)\n{bump_rows}\n", data_type="FTIR", name="ir_bump.csv"
    )

    run = client.post(
        "/analysis/run",
        json={
            "project_id": project_id,
            "dataset_key": dataset_key,
            "analysis_type": "FTIR",
            "workflow_template_id": "ftir.general",
            "processing_overrides": {"signal_conversion": {"enabled": True}},
        },
    )
    assert run.status_code == 200, run.text

    response = client.post(
        f"/workspace/{project_id}/deconvolution/run",
        json={
            "dataset_key": dataset_key,
            "signal_basis": "raw",
            "n_peaks": 1,
            "peak_shape": "gaussian",
            "initial_params": [{"center": 1700.0, "sigma": 30.0, "amplitude": 0.5}],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["signal_role"] == "transmittance"
    assert body["signal_unit"] == "%T"
    assert any("transmittance" in item.lower() for item in body["warnings"])

    detail = client.get(f"/workspace/{project_id}/results/{body['result_id']}").json()
    assert detail["processing"]["signal_role"] == "transmittance"
    assert detail["processing"]["signal_unit"] == "%T"
    assert detail["provenance"]["fit_signal_role"] == "transmittance"
    assert detail["summary"]["signal_unit"] == "%T"
    assert "Transmittance" in detail["report_payload"]["ylabel"]


# ---------------------------------------------------------------------------
# Production units for thermal processed bases (DSC mW/mg, TGA mass-%)
# ---------------------------------------------------------------------------


def _thermal_unit_csv(header: str, x: np.ndarray, y: np.ndarray) -> str:
    rows = "\n".join(f"{xi:.4f},{yi:.6f}" for xi, yi in zip(x, y))
    return f"{header}\n{rows}\n"


def test_dsc_mass_normalized_working_bases_report_mw_per_mg(client, monkeypatch):
    """A mass-normalized DSC working signal must not be labelled mW."""
    monkeypatch.setenv(PREVIEW_ENV, "1")
    x = np.linspace(50.0, 250.0, 400)
    csv_text = _thermal_unit_csv("Temperature (°C),Heat Flow (mW)", x, _two_gaussians(x))
    project_id = client.post("/workspace/new").json()["project_id"]
    dataset_key = _import_dataset(
        client,
        project_id,
        csv_text,
        data_type="DSC",
        name="dsc_mw.csv",
        metadata={"sample_mass": 5.0, "heating_rate": 10.0},
    )

    imported = client.get(f"/workspace/{project_id}/datasets/{dataset_key}").json()
    assert imported["units"]["signal"] == "mW"

    _run_stable_analysis(
        client, project_id, dataset_key, "DSC", workflow_template_id="dsc.general"
    )

    options = client.get(f"/workspace/{project_id}/deconvolution/options/{dataset_key}")
    assert options.status_code == 200, options.text
    by_name = {entry["name"]: entry for entry in options.json()["bases"]}
    # The saved working signal is the mass-normalized one.
    assert by_name["smoothed"]["signal_unit"] == "mW/mg"
    assert by_name["corrected"]["signal_unit"] == "mW/mg"
    # Raw stays the imported mW signal.
    assert by_name["raw"]["signal_unit"] == "mW"

    run = client.post(
        f"/workspace/{project_id}/deconvolution/run",
        json={
            "dataset_key": dataset_key,
            "signal_basis": "corrected",
            "n_peaks": 2,
            "peak_shape": "gaussian",
        },
    )
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["signal_unit"] == "mW/mg"
    assert body["result_summary"]["signal_unit"] == "mW/mg"
    assert body["result_summary"]["sse_per_dof_unit"] == "(mW/mg)²"
    assert body["result_summary"]["amplitude_unit"] == "mW/mg·°C"

    detail = client.get(f"/workspace/{project_id}/results/{body['result_id']}").json()
    assert detail["processing"]["signal_unit"] == "mW/mg"
    assert detail["processing"]["signal_dimensional_basis"] == "physical"
    assert detail["provenance"]["fit_signal_unit"] == "mW/mg"
    # build_axis_title renders mW/mg with a superscript: mW mg⁻¹.
    assert "mW" in detail["report_payload"]["ylabel"]
    assert "mg" in detail["report_payload"]["ylabel"]


def test_tga_absolute_mass_input_reports_percent_working_basis(client, monkeypatch):
    """TGAProcessor saves a mass-% working curve even for an mg input."""
    monkeypatch.setenv(PREVIEW_ENV, "1")
    temperature = np.linspace(30.0, 600.0, 300)
    # mg-scale input with a mid-step oxidation-like mass-gain bump so the
    # working curve keeps positive structure for the fit.
    mass_mg = 10.0 - 4.0 / (1.0 + np.exp(-(temperature - 350.0) / 40.0)) + 0.6 * np.exp(
        -0.5 * ((temperature - 450.0) / 20.0) ** 2
    )
    csv_text = _thermal_unit_csv("Temperature (°C),Mass (mg)", temperature, mass_mg)
    project_id = client.post("/workspace/new").json()["project_id"]
    dataset_key = _import_dataset(
        client,
        project_id,
        csv_text,
        data_type="TGA",
        name="tga_mg.csv",
        metadata={"sample_mass": 10.0, "heating_rate": 10.0},
    )

    imported = client.get(f"/workspace/{project_id}/datasets/{dataset_key}").json()
    assert imported["units"]["signal"] == "mg"

    _run_stable_analysis(
        client, project_id, dataset_key, "TGA", workflow_template_id="tga.general"
    )

    options = client.get(f"/workspace/{project_id}/deconvolution/options/{dataset_key}")
    assert options.status_code == 200, options.text
    by_name = {entry["name"]: entry for entry in options.json()["bases"]}
    assert by_name["smoothed"]["available"] is True
    assert by_name["smoothed"]["signal_unit"] == "%"
    assert by_name["raw"]["signal_unit"] == "mg"

    run = client.post(
        f"/workspace/{project_id}/deconvolution/run",
        json={
            "dataset_key": dataset_key,
            "signal_basis": "smoothed",
            "n_peaks": 1,
            "peak_shape": "gaussian",
        },
    )
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["signal_unit"] == "%"
    assert body["result_summary"]["signal_unit"] == "%"
    assert body["result_summary"]["sse_per_dof_unit"] == "%²"

    detail = client.get(f"/workspace/{project_id}/results/{body['result_id']}").json()
    assert detail["processing"]["signal_unit"] == "%"
    assert detail["provenance"]["fit_signal_unit"] == "%"
    assert "%" in detail["report_payload"]["ylabel"]
    # Value-scale evidence that the working curve really is mass-%.
    assert max(detail["report_payload"]["y"]) <= 100.0 + 10.0


def test_xrd_normalized_basis_never_acquires_the_counts_unit():
    """``build_axis_title`` defaults XRD to counts; a normalized curve must not."""
    x = np.linspace(10.0, 80.0, 400)
    y = np.exp(-0.5 * ((x - 30.0) / 0.4) ** 2)
    dataset = _Dataset(
        x,
        y,
        data_type="XRD",
        units={"temperature": "degree_2theta", "signal": "counts"},
        metadata={"xrd_axis_role": "two_theta", "xrd_axis_unit": "degree_2theta"},
    )
    state = _state(
        dataset,
        analysis_type="XRD",
        analysis_state={
            "axis": x.tolist(),
            "smoothed": y.tolist(),
            "corrected": y.tolist(),
            "normalized": (y / float(np.max(y))).tolist(),
        },
    )

    options = describe_options(resolve_analysis_state(state, "XRD", DATASET_KEY))
    by_name = {entry["name"]: entry for entry in options["bases"]}
    assert by_name["normalized"]["available"] is True
    assert by_name["normalized"]["signal_unit"] is None
    assert by_name["normalized"]["signal_label"] == "Normalized intensity"

    outcome = _run(
        state,
        signal_basis="normalized",
        n_peaks=1,
        initial_params=_guesses((30.0, 0.5, 0.4)),
    )

    payload = outcome["record"]["report_payload"]
    assert payload["ylabel"] == "Normalized intensity"
    assert "counts" not in payload["ylabel"].lower()
    assert outcome["record"]["summary"]["signal_unit"] is None
    assert outcome["record"]["summary"]["sse_per_dof_unit"] is None
    assert outcome["record"]["processing"]["signal_dimensional_basis"] == "normalized"


def test_non_gaussian_runs_record_their_own_shape_factor():
    """Auto-estimate diagnostics must follow the fitted shape, not Gaussian."""
    state = _state(_thermal_dataset(), analysis_type="DSC")

    outcome = _run(state, peak_shape="lorentzian")

    auto_estimate = outcome["record"]["processing"]["auto_estimate"]
    assert auto_estimate["peak_shape"] == "lorentzian"
    assert auto_estimate["shape_area_factor"] == pytest.approx(float(np.pi))
