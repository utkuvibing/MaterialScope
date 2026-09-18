from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("lmfit")

from core.peak_deconvolution import auto_estimate_peaks, deconvolve_peaks, shape_area_factor
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


@pytest.mark.parametrize(
    ("shape", "factor"),
    [
        ("gaussian", float(np.sqrt(2.0 * np.pi))),
        ("lorentzian", float(np.pi)),
        (
            "pseudo_voigt",
            1.0
            / (
                0.5 / float(np.sqrt(np.pi / np.log(2.0)))
                + 0.5 / float(np.pi)
            ),
        ),
    ],
)
def test_auto_amplitude_guess_has_integrated_area_semantics(shape, factor):
    """lmfit's amplitude is an area, so the auto guess must not be the height."""
    x, y = _synthetic_signal()

    estimate = auto_estimate_peaks(x, y, 2, peak_shape=shape)
    peak = estimate["peaks"][0]

    assert estimate["amplitude_semantics"] == "integrated_area_parameter"
    assert estimate["shape_area_factor"] == pytest.approx(factor)
    assert estimate["peak_shape"] == shape
    assert "shape_area_factor" in estimate["estimate_method"]

    # A sampled height is the starting point, but the submitted amplitude is
    # the integrated area that the selected model parameterizes.
    assert peak["height"] > 0
    assert peak["amplitude"] == pytest.approx(peak["height"] * peak["sigma"] * factor)
    assert peak["amplitude"] != pytest.approx(peak["height"])


def test_auto_amplitude_reproduces_the_height_inside_the_real_lmfit_models():
    """Ground truth: evaluate the actual lmfit models, not the helper's formula.

    lmfit's PseudoVoigtModel uses ``sigma_g = sigma / sqrt(2 ln 2)`` (every
    component has FWHM ``2 * sigma``), so its conversion differs from the
    GaussianModel convention.
    """
    from lmfit.models import GaussianModel, LorentzianModel, PseudoVoigtModel

    x, y = _synthetic_signal()
    models = {
        "gaussian": GaussianModel(prefix="p1_"),
        "lorentzian": LorentzianModel(prefix="p1_"),
        "pseudo_voigt": PseudoVoigtModel(prefix="p1_"),
    }

    for shape, model in models.items():
        estimate = auto_estimate_peaks(x, y, 1, peak_shape=shape)
        peak = estimate["peaks"][0]

        kwargs: dict[str, float] = {
            "amplitude": peak["amplitude"],
            "center": peak["center"],
            "sigma": peak["sigma"],
        }
        if shape == "pseudo_voigt":
            # The estimator seeds the same fraction the fit starts from.
            kwargs["fraction"] = 0.5

        evaluated = model.eval(x=np.asarray([peak["center"]]), **kwargs)

        assert float(evaluated[0]) == pytest.approx(peak["height"], rel=1e-6), shape


def test_pseudo_voigt_factor_differs_from_the_gaussian_convention():
    """The PV ``sigma`` is not a Gaussian standard deviation (FWHM is 2*sigma)."""
    assert shape_area_factor("pseudo_voigt") != pytest.approx(shape_area_factor("gaussian"))
    # At f = 0 the mixed profile is a Gaussian of width sigma_g = sigma/sqrt(2 ln 2).
    assert shape_area_factor("pseudo_voigt", fraction=0.0) == pytest.approx(
        float(np.sqrt(2.0 * np.pi)) / float(np.sqrt(2.0 * np.log(2.0)))
    )

    # Sanity: the Gaussian factor is the lightest, the Lorentzian the heaviest.
    assert shape_area_factor("lorentzian") > shape_area_factor("pseudo_voigt") > shape_area_factor("gaussian")


def test_auto_estimate_without_shape_argument_stays_backwards_compatible():
    x, y = _synthetic_signal()

    estimate = auto_estimate_peaks(x, y, 2)

    assert estimate["peak_shape"] == "gaussian"
    assert len(estimate["peaks"]) == 2
    assert set(estimate["peaks"][0]) == {"center", "amplitude", "sigma", "height"}


def test_auto_estimated_amplitude_is_a_usable_fit_start():
    """Correct area scaling must keep the automatic path converging."""
    x, y = _synthetic_signal()

    result = deconvolve_peaks(x, y, n_peaks=2, peak_shape="gaussian")

    assert result["r_squared"] > 0.99
    assert [row["center"] for row in result["initial_guesses"]] == pytest.approx([120.0, 170.0], abs=5.0)


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
