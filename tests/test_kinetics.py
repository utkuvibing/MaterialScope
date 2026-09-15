import numpy as np
import pytest
from scipy.optimize import brentq

from core.kinetics import (
    GAS_CONSTANT_R,
    KINETICS_CI_METHOD,
    compute_conversion,
    kissinger_analysis,
    run_kinetic_analysis,
)


def _kissinger_fixture(ea_j_mol: float = 150_000.0, ln_a: float = np.log(1e10), rates=None):
    """Generate peak temperatures consistent with a known Ea/A pair.

    Solves ln(beta/Tp^2) = -Ea/(R*Tp) + ln(A*R/Ea) for Tp per heating rate,
    so the regression must recover the injected kinetics.
    """
    rates = rates or [5.0, 10.0, 20.0, 40.0]
    intercept = ln_a + np.log(GAS_CONSTANT_R / ea_j_mol)
    temps = []
    for beta in rates:
        f = lambda T: np.log(beta / T**2) + ea_j_mol / (GAS_CONSTANT_R * T) - intercept  # noqa: E731
        temps.append(float(brentq(f, 300.0, 2000.0)) - 273.15)
    return list(rates), temps, ea_j_mol / 1000.0, ln_a


def test_compute_conversion_tga_mode_uses_mass_drop_fraction():
    temperature = np.array([25.0, 100.0, 200.0, 300.0])
    mass = np.array([100.0, 95.0, 70.0, 60.0])

    alpha = compute_conversion(temperature, mass, mode="tga")

    np.testing.assert_allclose(alpha, [0.0, 0.125, 0.75, 1.0], atol=1e-8)


def test_run_kinetic_analysis_returns_report_ready_kissinger_payload():
    payload = run_kinetic_analysis(
        "kissinger",
        heating_rates=[5.0, 10.0, 20.0],
        peak_temperatures=[210.0, 220.0, 232.0],
    )

    assert payload["method_id"] == "kissinger"
    assert payload["summary"]["activation_energy_kj_mol"] is not None
    assert len(payload["rows"]) == 1
    assert payload["scientific_context"]["equations"]
    assert payload["scientific_context"]["numerical_interpretation"]
    assert payload["scientific_context"]["scientific_claims"]
    assert payload["scientific_context"]["evidence_map"]
    assert payload["scientific_context"]["uncertainty_assessment"]
    assert payload["scientific_context"]["next_experiments"]


def test_run_kinetic_analysis_returns_report_ready_ofw_payload():
    heating_rates = [5.0, 10.0, 20.0]
    temperature_data = [
        np.array([100.0, 120.0, 140.0, 160.0]),
        np.array([105.0, 125.0, 145.0, 165.0]),
        np.array([110.0, 130.0, 150.0, 170.0]),
    ]
    conversion_data = [
        np.array([0.0, 0.3, 0.7, 1.0]),
        np.array([0.0, 0.32, 0.72, 1.0]),
        np.array([0.0, 0.34, 0.74, 1.0]),
    ]

    payload = run_kinetic_analysis(
        "ofw",
        heating_rates=heating_rates,
        temperature_data=temperature_data,
        conversion_data=conversion_data,
        alpha_values=[0.2, 0.4, 0.6],
    )

    assert payload["method_id"] == "ofw"
    assert payload["summary"]["conversion_point_count"] >= 2
    assert payload["rows"]
    assert payload["scientific_context"]["fit_quality"]["evaluated_rows"] == len(payload["rows"])
    assert payload["scientific_context"]["scientific_claims"]
    assert payload["scientific_context"]["alternative_hypotheses"]


def test_run_kinetic_analysis_returns_report_ready_friedman_payload():
    heating_rates = [5.0, 10.0, 20.0]
    temperature_data = [
        np.array([100.0, 120.0, 140.0, 160.0]),
        np.array([105.0, 125.0, 145.0, 165.0]),
        np.array([110.0, 130.0, 150.0, 170.0]),
    ]
    conversion_data = [
        np.array([0.0, 0.3, 0.7, 1.0]),
        np.array([0.0, 0.32, 0.72, 1.0]),
        np.array([0.0, 0.34, 0.74, 1.0]),
    ]
    dalpha_dt_data = [
        np.array([0.01, 0.03, 0.04, 0.02]),
        np.array([0.015, 0.028, 0.038, 0.022]),
        np.array([0.02, 0.03, 0.042, 0.025]),
    ]

    payload = run_kinetic_analysis(
        "friedman",
        heating_rates=heating_rates,
        temperature_data=temperature_data,
        conversion_data=conversion_data,
        dalpha_dt_data=dalpha_dt_data,
        alpha_values=[0.2, 0.4, 0.6],
    )

    assert payload["method_id"] == "friedman"
    assert payload["summary"]["conversion_point_count"] >= 2
    assert payload["scientific_context"]["equations"]
    assert payload["scientific_context"]["scientific_claims"]
    assert payload["scientific_context"]["next_experiments"]


# ---------------------------------------------------------------------------
# PR-20: Ea confidence intervals + intercept semantics
# ---------------------------------------------------------------------------


def test_kissinger_recovers_known_ea_and_ln_a_with_ci():
    rates, temps, ea_true_kj, ln_a_true = _kissinger_fixture()

    result = kissinger_analysis(rates, temps)

    assert result.activation_energy == pytest.approx(ea_true_kj, rel=1e-6)
    assert result.ln_a_min_inv == pytest.approx(ln_a_true, abs=1e-4)
    assert result.ea_ci_status == "computed"
    assert result.confidence_level == pytest.approx(0.95)
    # Exact fixture -> zero-width interval at the point estimate.
    assert result.ea_ci_low_kj_mol == pytest.approx(ea_true_kj, rel=1e-6)
    assert result.ea_ci_high_kj_mol == pytest.approx(ea_true_kj, rel=1e-6)


def test_kissinger_intercept_is_ln_a_r_over_ea_not_ln_a():
    """The fitted intercept must not be presented as ln(A)."""
    rates, temps, ea_true_kj, ln_a_true = _kissinger_fixture()

    result = kissinger_analysis(rates, temps)

    expected_intercept = ln_a_true + np.log(GAS_CONSTANT_R / (ea_true_kj * 1000.0))
    assert result.regression_intercept == pytest.approx(expected_intercept, abs=1e-6)
    assert result.pre_exponential == pytest.approx(result.regression_intercept)
    assert "ln(A * R / Ea)" in result.intercept_semantics
    # Guard against regression to the old "intercept ≈ ln(A)" assumption.
    assert abs(result.regression_intercept - result.ln_a_min_inv) > 1.0


def test_kissinger_ci_widens_with_scatter_and_contains_true_ea():
    rates, temps, ea_true_kj, _ = _kissinger_fixture()
    rng = np.random.default_rng(7)
    noisy_temps = np.asarray(temps) + rng.normal(0.0, 0.8, size=len(temps))

    result = kissinger_analysis(rates, noisy_temps.tolist())

    assert result.ea_ci_status == "computed"
    assert result.ea_ci_low_kj_mol < result.activation_energy < result.ea_ci_high_kj_mol
    # Scatter is small; the true Ea should still sit inside the interval.
    assert result.ea_ci_low_kj_mol <= ea_true_kj <= result.ea_ci_high_kj_mol
    assert (result.ea_ci_high_kj_mol - result.ea_ci_low_kj_mol) > 0.0


def test_kissinger_ci_withheld_with_two_points():
    rates, temps, _, _ = _kissinger_fixture()

    result = kissinger_analysis(rates[:2], temps[:2])

    assert result.ea_ci_status == "withheld"
    assert result.ea_ci_withheld_reason == "ea_ci_requires_at_least_3_points"
    assert result.ea_ci_low_kj_mol is None and result.ea_ci_high_kj_mol is None
    # Point estimate still reported — only the interval is withheld.
    assert result.activation_energy == pytest.approx(150.0, rel=1e-6)


def test_kissinger_confidence_level_is_explicit_and_affects_width():
    rates, temps, _, _ = _kissinger_fixture()
    rng = np.random.default_rng(3)
    noisy = np.asarray(temps) + rng.normal(0.0, 1.2, size=len(temps))

    r95 = kissinger_analysis(rates, noisy.tolist(), confidence_level=0.95)
    r50 = kissinger_analysis(rates, noisy.tolist(), confidence_level=0.50)

    assert r95.confidence_level == pytest.approx(0.95)
    assert r50.confidence_level == pytest.approx(0.50)
    w95 = r95.ea_ci_high_kj_mol - r95.ea_ci_low_kj_mol
    w50 = r50.ea_ci_high_kj_mol - r50.ea_ci_low_kj_mol
    assert w95 > w50 > 0.0


def test_kissinger_invalid_confidence_level_falls_back_to_default():
    rates, temps, _, _ = _kissinger_fixture()
    result = kissinger_analysis(rates, temps, confidence_level=1.5)
    assert result.confidence_level == pytest.approx(0.95)


def test_ofw_rows_carry_ci_and_intercept_semantics():
    heating_rates = [5.0, 10.0, 20.0, 40.0]
    temperature_data = [
        np.array([100.0, 120.0, 140.0, 160.0]),
        np.array([105.0, 125.0, 145.0, 165.0]),
        np.array([110.0, 130.0, 150.0, 170.0]),
        np.array([115.0, 135.0, 155.0, 175.0]),
    ]
    conversion_data = [
        np.array([0.0, 0.3, 0.7, 1.0]),
        np.array([0.0, 0.32, 0.72, 1.0]),
        np.array([0.0, 0.34, 0.74, 1.0]),
        np.array([0.0, 0.33, 0.71, 1.0]),
    ]

    payload = run_kinetic_analysis(
        "ofw",
        heating_rates=heating_rates,
        temperature_data=temperature_data,
        conversion_data=conversion_data,
        alpha_values=[0.3, 0.5],
    )

    assert payload["summary"]["ea_ci_method"] == KINETICS_CI_METHOD
    assert payload["summary"]["confidence_level"] == pytest.approx(0.95)
    assert payload["summary"]["ea_ci_computed_count"] == len(payload["rows"])
    for row in payload["rows"]:
        assert row["ea_ci_status"] == "computed"
        assert row["activation_energy_ci_low_kj_mol"] <= row["activation_energy_kj_mol"]
        assert row["activation_energy_kj_mol"] <= row["activation_energy_ci_high_kj_mol"]
        assert "Doyle" in row["intercept_semantics"]
        assert row["n_points"] == 4


def test_friedman_rows_carry_ci_and_intercept_semantics():
    heating_rates = [5.0, 10.0, 20.0, 40.0]
    temperature_data = [
        np.array([100.0, 120.0, 140.0, 160.0]),
        np.array([105.0, 125.0, 145.0, 165.0]),
        np.array([110.0, 130.0, 150.0, 170.0]),
        np.array([115.0, 135.0, 155.0, 175.0]),
    ]
    conversion_data = [
        np.array([0.0, 0.3, 0.7, 1.0]),
        np.array([0.0, 0.32, 0.72, 1.0]),
        np.array([0.0, 0.34, 0.74, 1.0]),
        np.array([0.0, 0.33, 0.71, 1.0]),
    ]
    dalpha_dt_data = [
        np.array([0.01, 0.03, 0.04, 0.02]),
        np.array([0.015, 0.028, 0.038, 0.022]),
        np.array([0.02, 0.03, 0.042, 0.025]),
        np.array([0.017, 0.031, 0.040, 0.023]),
    ]

    payload = run_kinetic_analysis(
        "friedman",
        heating_rates=heating_rates,
        temperature_data=temperature_data,
        conversion_data=conversion_data,
        dalpha_dt_data=dalpha_dt_data,
        alpha_values=[0.3, 0.5],
    )

    assert payload["summary"]["ea_ci_computed_count"] == len(payload["rows"])
    for row in payload["rows"]:
        assert row["ea_ci_status"] == "computed"
        assert row["activation_energy_ci_low_kj_mol"] <= row["activation_energy_kj_mol"]
        assert row["activation_energy_kj_mol"] <= row["activation_energy_ci_high_kj_mol"]
        assert "ln(A * f(alpha))" in row["intercept_semantics"]


def test_ofw_ci_withheld_when_fewer_than_three_rates():
    heating_rates = [5.0, 10.0]
    temperature_data = [
        np.array([100.0, 120.0, 140.0, 160.0]),
        np.array([105.0, 125.0, 145.0, 165.0]),
    ]
    conversion_data = [
        np.array([0.0, 0.3, 0.7, 1.0]),
        np.array([0.0, 0.32, 0.72, 1.0]),
    ]

    payload = run_kinetic_analysis(
        "ofw",
        heating_rates=heating_rates,
        temperature_data=temperature_data,
        conversion_data=conversion_data,
        alpha_values=[0.5],
    )

    row = payload["rows"][0]
    assert row["ea_ci_status"] == "withheld"
    assert row["ea_ci_withheld_reason"] == "ea_ci_requires_at_least_3_points"
    assert row["activation_energy_ci_low_kj_mol"] is None


def test_kissinger_serialization_carries_ci_and_semantics():
    from core.result_serialization import serialize_kissinger_result

    rates, temps, ea_true_kj, _ = _kissinger_fixture()
    result = kissinger_analysis(rates, temps)
    record = serialize_kissinger_result(result)

    summary = record["summary"]
    assert summary["activation_energy_ci_low_kj_mol"] == pytest.approx(ea_true_kj, rel=1e-6)
    assert summary["ea_ci_status"] == "computed"
    assert summary["confidence_level"] == pytest.approx(0.95)
    assert "ln(A * R / Ea)" in summary["intercept_semantics"]
    assert summary["ln_a_min_inv"] is not None
    ctx = record["scientific_context"]
    assert "slope" in ctx["methodology"]["ea_ci_method"]
    assert ctx["methodology"]["intercept_semantics"]


def test_isoconversional_serialization_carries_ci_fields():
    from core.result_serialization import serialize_friedman_results, serialize_ofw_results

    heating_rates = [5.0, 10.0, 20.0]
    temperature_data = [
        np.array([100.0, 120.0, 140.0, 160.0]),
        np.array([105.0, 125.0, 145.0, 165.0]),
        np.array([110.0, 130.0, 150.0, 170.0]),
    ]
    conversion_data = [
        np.array([0.0, 0.3, 0.7, 1.0]),
        np.array([0.0, 0.32, 0.72, 1.0]),
        np.array([0.0, 0.34, 0.74, 1.0]),
    ]
    dalpha_dt_data = [
        np.array([0.01, 0.03, 0.04, 0.02]),
        np.array([0.015, 0.028, 0.038, 0.022]),
        np.array([0.02, 0.03, 0.042, 0.025]),
    ]

    ofw_payload = run_kinetic_analysis(
        "ofw",
        heating_rates=heating_rates,
        temperature_data=temperature_data,
        conversion_data=conversion_data,
        alpha_values=[0.5],
    )
    record = serialize_ofw_results(ofw_payload["results"])
    row = record["rows"][0]
    assert row["ea_ci_status"] in {"computed", "withheld"}
    assert "intercept_semantics" in row
    assert "confidence_level" in row
    assert record["scientific_context"]["methodology"]["ea_ci_method"]

    friedman_payload = run_kinetic_analysis(
        "friedman",
        heating_rates=heating_rates,
        temperature_data=temperature_data,
        conversion_data=conversion_data,
        dalpha_dt_data=dalpha_dt_data,
        alpha_values=[0.5],
    )
    record = serialize_friedman_results(friedman_payload["results"])
    row = record["rows"][0]
    assert row["ea_ci_status"] == "computed"
    assert row["activation_energy_ci_low_kj_mol"] <= row["activation_energy_kj_mol"]
    assert "ln(A * f(alpha))" in row["intercept_semantics"]


def test_scientific_context_documents_ci_method_and_intercept_semantics():
    rates, temps, _, _ = _kissinger_fixture()
    payload = run_kinetic_analysis("kissinger", heating_rates=rates, peak_temperatures=temps)

    ctx = payload["scientific_context"]
    assert ctx["methodology"]["ea_ci_method"] == KINETICS_CI_METHOD
    assert ctx["methodology"]["confidence_level"] == pytest.approx(0.95)
    assert "ln(A * R / Ea)" in ctx["methodology"]["intercept_semantics"]
    assert any(
        "confidence interval" in str(item.get("statement", "")).lower()
        for item in ctx["numerical_interpretation"]
    )
