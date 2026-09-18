from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("lmfit")

from core.peak_deconvolution import auto_estimate_peaks, deconvolve_peaks
from core.result_serialization import serialize_deconvolution_result


def _synthetic_signal():
    x = np.linspace(50.0, 250.0, 500)
    y = (
        2.0 * np.exp(-0.5 * ((x - 120.0) / 8.0) ** 2)
        + 1.5 * np.exp(-0.5 * ((x - 170.0) / 10.0) ** 2)
    )
    return x, y


def test_deconvolve_peaks_returns_residual_stats_and_fit_quality():
    x, y = _synthetic_signal()

    result = deconvolve_peaks(x, y, n_peaks=2, peak_shape="gaussian")

    assert "initial_guesses" in result
    assert "residual_stats" in result
    assert "fit_quality" in result
    assert result["residual_stats"]["rmse"] >= 0.0
    assert result["fit_quality"]["dof"] > 0


def test_serialize_deconvolution_result_populates_scientific_context():
    x, y = _synthetic_signal()
    result = deconvolve_peaks(x, y, n_peaks=2, peak_shape="gaussian")
    result["x"] = x
    result["y"] = y
    dataset = SimpleNamespace(metadata={"sample_name": "Synthetic Deconv"})

    record = serialize_deconvolution_result(
        "synthetic_deconv",
        dataset,
        result,
        peak_shape="gaussian",
    )

    assert record["analysis_type"] == "Peak Deconvolution"
    assert record["scientific_context"]["fit_quality"]["r_squared"] is not None
    assert record["scientific_context"]["methodology"]["peak_shape"] == "gaussian"
    assert record["scientific_context"]["methodology"]["initial_guesses"]
    assert record["scientific_context"]["scientific_claims"]
    assert record["scientific_context"]["uncertainty_assessment"]
    assert record["scientific_context"]["next_experiments"]


def _full_guesses():
    return [
        {"center": 120.0, "amplitude": 2.0, "sigma": 8.0},
        {"center": 170.0, "amplitude": 1.5, "sigma": 10.0},
    ]


def test_initial_guess_provenance_is_recorded_per_field():
    """A partial hint must not label the whole peak as user-supplied."""
    x, y = _synthetic_signal()

    result = deconvolve_peaks(
        x,
        y,
        n_peaks=2,
        peak_shape="gaussian",
        initial_params=[{"center": 120.0}, {}],
    )

    first, second = result["initial_guesses"]
    assert first["source"] == "mixed"
    assert first["field_sources"] == {"center": "user", "amplitude": "auto", "sigma": "auto"}
    assert second["source"] == "auto"
    assert set(second["field_sources"].values()) == {"auto"}


def test_initial_guess_provenance_all_user_and_all_auto():
    x, y = _synthetic_signal()

    auto_only = deconvolve_peaks(x, y, n_peaks=2, peak_shape="gaussian")
    assert {entry["source"] for entry in auto_only["initial_guesses"]} == {"auto"}

    user_only = deconvolve_peaks(
        x, y, n_peaks=2, peak_shape="gaussian", initial_params=_full_guesses()
    )
    assert {entry["source"] for entry in user_only["initial_guesses"]} == {"user"}
    assert {
        value for entry in user_only["initial_guesses"] for value in entry["field_sources"].values()
    } == {"user"}


def test_derived_lmfit_parameters_do_not_reduce_dof():
    """height/fwhm are derived, so they must not be counted as free parameters."""
    x, y = _synthetic_signal()

    result = deconvolve_peaks(
        x, y, n_peaks=2, peak_shape="gaussian", initial_params=_full_guesses()
    )
    stats = result["residual_stats"]

    # Two Gaussian components contribute exactly center/amplitude/sigma each.
    assert stats["free_param_count"] == 6
    assert stats["n_data"] == len(y)
    assert stats["dof"] == len(y) - 6
    # The derived parameters still exist in the fitted parameter map.
    assert "p1_height" in result["params"]
    assert "p1_fwhm" in result["params"]


def test_sse_per_dof_is_the_canonical_name_and_stays_unweighted():
    x, y = _synthetic_signal()

    result = deconvolve_peaks(
        x, y, n_peaks=2, peak_shape="gaussian", initial_params=_full_guesses()
    )
    stats = result["residual_stats"]
    expected = float(np.sum((y - result["fitted"]) ** 2) / stats["dof"])

    assert stats["sse_per_dof"] == pytest.approx(expected)
    assert stats["unweighted_sse_per_dof"] == pytest.approx(stats["sse_per_dof"])
    # Legacy alias survives with the corrected value.
    assert stats["reduced_chi_squared"] == pytest.approx(stats["sse_per_dof"])
    assert result["fit_quality"]["sse_per_dof"] == pytest.approx(stats["sse_per_dof"])


@pytest.mark.parametrize("shape", ["gaussian", "lorentzian", "pseudo_voigt"])
def test_derived_height_and_fwhm_exist_for_every_shape(shape):
    x, y = _synthetic_signal()

    result = deconvolve_peaks(x, y, n_peaks=1, peak_shape=shape, initial_params=[_full_guesses()[0]])

    assert "p1_height" in result["params"]
    assert "p1_fwhm" in result["params"]


def test_auto_estimate_reports_missing_positive_structure():
    x, y = _synthetic_signal()

    estimate = auto_estimate_peaks(x, -y, 2)

    assert estimate["usable_positive_structure"] is False
    assert estimate["reason"] == "no_positive_structure"
    assert estimate["positive_point_fraction"] == pytest.approx(0.0)
    assert estimate["detected_peak_count"] == 0
    assert estimate["fallback_spacing_used"] is True
    assert len(estimate["peaks"]) == 2


def test_auto_estimate_detects_positive_peaks():
    x, y = _synthetic_signal()

    estimate = auto_estimate_peaks(x, y, 2)

    assert estimate["usable_positive_structure"] is True
    assert estimate["reason"] is None
    assert estimate["detected_peak_count"] == 2
    assert estimate["fallback_spacing_used"] is False
    assert estimate["positive_point_fraction"] == pytest.approx(1.0)


def test_serializer_persists_report_payload_and_derived_rows():
    x, y = _synthetic_signal()
    result = deconvolve_peaks(
        x, y, n_peaks=2, peak_shape="gaussian", initial_params=_full_guesses()
    )
    dataset = SimpleNamespace(metadata={"sample_name": "Synthetic Deconv"})
    report_payload = {"x": x.tolist(), "fitted": result["fitted"].tolist(), "residual": result["residual"].tolist()}

    record = serialize_deconvolution_result(
        "synthetic_deconv",
        dataset,
        result,
        peak_shape="gaussian",
        processing={
            "signal_basis": "raw",
            "axis_role": "temperature",
            "axis_unit": "°C",
            "signal_unit": "mW",
            "inversion_applied": False,
        },
        report_payload=report_payload,
    )

    assert record["report_payload"] == report_payload
    first_row = record["rows"][0]
    assert first_row["fwhm"] is not None
    assert first_row["height"] is not None
    # The integrated area parameter must not be presented as a height.
    assert first_row["amplitude"] != pytest.approx(first_row["height"])
    summary = record["summary"]
    assert summary["amplitude_semantics"] == "integrated_area_parameter"
    assert summary["amplitude_unit"] == "mW·°C"
    assert summary["sse_per_dof"] is not None
    assert summary["signal_basis"] == "raw"
    assert summary["axis_unit"] == "°C"
    assert summary["inversion_applied"] is False
    limitations = " ".join(record["scientific_context"]["limitations"])
    assert "unweighted" in limitations.lower()
    assert "not peak height" in limitations.lower()


def test_serializer_omits_amplitude_unit_when_a_dimension_is_unknown():
    x, y = _synthetic_signal()
    result = deconvolve_peaks(
        x, y, n_peaks=1, peak_shape="gaussian", initial_params=[_full_guesses()[0]]
    )
    dataset = SimpleNamespace(metadata={})

    record = serialize_deconvolution_result(
        "synthetic_deconv",
        dataset,
        result,
        peak_shape="gaussian",
        processing={"signal_basis": "raw", "axis_unit": None, "signal_unit": "mW"},
    )

    assert "amplitude_unit" not in record["summary"]
