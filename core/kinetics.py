"""
Kinetic analysis methods for thermal data.

Supports:
- Kissinger method
- Ozawa-Flynn-Wall (OFW) isoconversional method
- Friedman differential isoconversional method
- Conversion computation from DSC/TGA signals
"""

from __future__ import annotations

import math

import numpy as np
from dataclasses import dataclass, field
from typing import Any, Optional
from scipy import integrate, interpolate, stats

from core.scientific_sections import (
    build_equation,
    build_fit_quality,
    build_interpretation,
    build_scientific_context,
)
from core.scientific_reasoning import build_scientific_reasoning

GAS_CONSTANT_R = 8.314462  # J/(mol·K)

KINETICS_DEFAULT_CONFIDENCE_LEVEL = 0.95
KINETICS_CI_METHOD = (
    "two-sided Student-t interval on the OLS regression slope "
    "(slope +/- t_{n-2, 1-alpha/2} * stderr), propagated through the "
    "method's linear Ea transform"
)
KINETICS_OLS_ASSUMPTIONS = (
    "The fitted relationship is linear and correctly specified; observations "
    "are independent; residuals have zero mean, constant variance, and are "
    "approximately normal for finite-sample Student-t inference; predictor "
    "values are treated as fixed and measured without material error."
)
KINETICS_CI_SCOPE = (
    "Pointwise regression interval on the fitted Ea transform at each conversion "
    "level (or the single Kissinger fit), covering regression scatter only; it "
    "is not a simultaneous band or an instrument, preprocessing, sampling, or "
    "metrological uncertainty model."
)

# Explicit semantics of the fitted regression intercept per method. The
# intercept is NOT ln(A) on its own in any of these linearizations.
INTERCEPT_SEMANTICS = {
    "kissinger": (
        "regression intercept = ln(A * R / Ea); "
        "ln(A) with A in min^-1 is derived separately as intercept + ln(Ea / R)"
    ),
    "ofw": (
        "regression intercept = C, the Doyle-approximation constant term in "
        "log10(beta) = -0.4567 * Ea / (R * T_alpha) + C; it is not ln(A)"
    ),
    "friedman": (
        "regression intercept = ln(A * f(alpha)) at this conversion alpha; "
        "it is not ln(A) alone"
    ),
}


def _coerce_confidence_level(value: Any) -> float:
    """Return a confidence level in (0, 1), rejecting invalid input."""
    try:
        level = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"confidence_level must be a finite number in (0, 1), got {value!r}."
        ) from exc
    if not math.isfinite(level) or not 0.0 < level < 1.0:
        raise ValueError(
            f"confidence_level must be a finite number in (0, 1), got {value!r}."
        )
    return level


def _slope_ea_ci(
    *,
    slope: float,
    slope_stderr: float,
    n_points: int,
    confidence_level: float,
    slope_to_ea_factor: float,
) -> tuple[float | None, float | None, str, str]:
    """Map an OLS slope t-interval onto Ea (kJ/mol).

    ``slope_to_ea_factor`` is the signed factor such that
    ``Ea_kJ = -slope * factor`` (Kissinger/Friedman: R/1000; OFW:
    R/(0.4567*1000)). The sign flip means the slope interval maps onto Ea
    in reversed order.

    Returns ``(low, high, status, withheld_reason)``. The interval is
    withheld when fewer than 3 points were fitted (n-2 < 1 degree of
    freedom) or the slope standard error is non-finite.
    """
    if n_points < 3:
        return None, None, "withheld", "ea_ci_requires_at_least_3_points"
    if not math.isfinite(slope_stderr) or slope_stderr < 0.0:
        return None, None, "withheld", "ea_ci_slope_stderr_not_finite"
    dof = n_points - 2
    t_crit = float(stats.t.ppf(0.5 + confidence_level / 2.0, dof))
    slope_lo = slope - t_crit * slope_stderr
    slope_hi = slope + t_crit * slope_stderr
    ea_low = -slope_hi * slope_to_ea_factor
    ea_high = -slope_lo * slope_to_ea_factor
    low, high = min(ea_low, ea_high), max(ea_low, ea_high)
    if not (math.isfinite(low) and math.isfinite(high)):
        return None, None, "withheld", "ea_ci_not_finite"
    return float(low), float(high), "computed", ""


def _kissinger_ln_a_min_inv(regression_intercept: float | None, ea_kj_per_mol: float | None) -> float | None:
    """Derive ln(A) with A in min^-1 from the Kissinger intercept.

    intercept = ln(A * R / Ea)  =>  ln(A) = intercept + ln(Ea / R),
    with Ea in J/mol and R in J/(mol*K). Returns None when inputs are
    missing or non-positive (Ea <= 0 cannot produce a physical A here).
    """
    if regression_intercept is None or ea_kj_per_mol is None:
        return None
    ea_j = float(ea_kj_per_mol) * 1000.0
    if not math.isfinite(ea_j) or ea_j <= 0.0 or not math.isfinite(float(regression_intercept)):
        return None
    return float(regression_intercept + math.log(ea_j / GAS_CONSTANT_R))


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class KineticResult:
    """Container for a single kinetic analysis result."""

    method: str                            # 'kissinger', 'ozawa_flynn_wall', 'friedman'
    activation_energy: float               # kJ/mol
    pre_exponential: Optional[float] = None   # regression intercept (see intercept_semantics)
    r_squared: Optional[float] = None        # Regression quality (0–1)
    plot_data: Optional[dict] = field(default=None)  # Data for plotting
    # PR-20 statistics/provenance fields
    regression_slope: Optional[float] = None
    regression_intercept: Optional[float] = None
    slope_stderr: Optional[float] = None
    intercept_stderr: Optional[float] = None
    n_points: Optional[int] = None
    confidence_level: Optional[float] = None
    ea_ci_low_kj_mol: Optional[float] = None
    ea_ci_high_kj_mol: Optional[float] = None
    ea_ci_status: Optional[str] = None           # 'computed' | 'withheld'
    ea_ci_withheld_reason: Optional[str] = None
    intercept_semantics: Optional[str] = None    # explicit meaning of the intercept
    ln_a_min_inv: Optional[float] = None         # Kissinger only: ln(A), A in min^-1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def kissinger_analysis(
    heating_rates: list[float],
    peak_temperatures: list[float],
    confidence_level: float = KINETICS_DEFAULT_CONFIDENCE_LEVEL,
) -> KineticResult:
    """
    Kissinger kinetic analysis.

    Parameters
    ----------
    heating_rates : list[float]
        Heating rates β in K/min or °C/min (units cancel in the ratio).
    peak_temperatures : list[float]
        Peak temperatures Tp in °C (converted internally to K).

    Returns
    -------
    KineticResult
        Activation energy (kJ/mol), regression intercept, R², plot data,
        and a confidence interval on Ea at ``confidence_level``.

    Notes
    -----
    The Kissinger equation is:

        ln(β / Tp²) = -Ea / (R · Tp) + ln(A · R / Ea)

    A linear regression of ln(β/Tp²) vs 1/Tp gives:
        slope  = -Ea / R
        intercept = ln(A · R / Ea)

    The intercept is therefore *not* ln(A); it is ln(A·R/Ea). The result
    carries ``ln_a_min_inv = intercept + ln(Ea/R)`` as the derived ln(A)
    with A in min⁻¹, while ``pre_exponential``/``regression_intercept``
    retain the raw fitted intercept for backwards compatibility and for
    reconstructing the regression line.

    The Ea interval is a two-sided Student-t interval on the OLS slope
    (``n - 2`` degrees of freedom) propagated through ``Ea = -slope·R``.
    With fewer than three points the regression has no residual degrees
    of freedom and the interval is withheld. The interval is pointwise and
    covers regression scatter only under the OLS assumptions recorded in
    ``KINETICS_OLS_ASSUMPTIONS``; it is not a metrological uncertainty model.
    """
    beta = np.asarray(heating_rates, dtype=float)
    tp_celsius = np.asarray(peak_temperatures, dtype=float)
    tp_kelvin = tp_celsius + 273.15
    level = _coerce_confidence_level(confidence_level)

    if len(beta) < 2:
        raise ValueError("At least two data points are required for Kissinger analysis.")
    if len(beta) != len(tp_kelvin):
        raise ValueError("heating_rates and peak_temperatures must have the same length.")

    inv_tp = 1.0 / tp_kelvin
    ln_beta_tp2 = np.log(beta / tp_kelvin**2)

    fit = stats.linregress(inv_tp, ln_beta_tp2)
    slope, intercept, r_value = fit.slope, fit.intercept, fit.rvalue

    ea_j_per_mol = -slope * GAS_CONSTANT_R          # J/mol
    ea_kj_per_mol = ea_j_per_mol / 1000.0            # kJ/mol
    # The fitted intercept is ln(A·R/Ea), not ln(A); ln(A) is derived below.
    ln_a = intercept

    r_squared = r_value**2
    ci_low, ci_high, ci_status, ci_reason = _slope_ea_ci(
        slope=slope,
        slope_stderr=float(fit.stderr),
        n_points=len(beta),
        confidence_level=level,
        slope_to_ea_factor=GAS_CONSTANT_R / 1000.0,
    )
    ln_a_min_inv = _kissinger_ln_a_min_inv(intercept, ea_kj_per_mol)

    # Points along the fitted line for plotting
    x_fit = np.linspace(inv_tp.min(), inv_tp.max(), 200)
    y_fit = slope * x_fit + intercept

    plot_data = {
        "inv_tp": inv_tp.tolist(),
        "ln_beta_tp2": ln_beta_tp2.tolist(),
        "x_fit": x_fit.tolist(),
        "y_fit": y_fit.tolist(),
        "xlabel": "1/Tp  (K⁻¹)",
        "ylabel": "ln(β / Tp²)  (K⁻² min⁻¹)",
    }

    return KineticResult(
        method="kissinger",
        activation_energy=ea_kj_per_mol,
        pre_exponential=ln_a,
        r_squared=r_squared,
        plot_data=plot_data,
        regression_slope=float(slope),
        regression_intercept=float(intercept),
        slope_stderr=float(fit.stderr) if math.isfinite(fit.stderr) else None,
        intercept_stderr=float(fit.intercept_stderr) if math.isfinite(fit.intercept_stderr) else None,
        n_points=len(beta),
        confidence_level=level,
        ea_ci_low_kj_mol=ci_low,
        ea_ci_high_kj_mol=ci_high,
        ea_ci_status=ci_status,
        ea_ci_withheld_reason=ci_reason,
        intercept_semantics=INTERCEPT_SEMANTICS["kissinger"],
        ln_a_min_inv=ln_a_min_inv,
    )


def ozawa_flynn_wall_analysis(
    heating_rates: list[float],
    temperature_data: list[np.ndarray],
    conversion_data: list[np.ndarray],
    alpha_values: Optional[list[float]] = None,
    confidence_level: float = KINETICS_DEFAULT_CONFIDENCE_LEVEL,
) -> list[KineticResult]:
    """
    Ozawa-Flynn-Wall (OFW) isoconversional analysis.

    For each conversion level α the method fits:

        log(β) = -0.4567 · Ea / (R · T) + const

    using Doyle's approximation for the temperature integral.

    Parameters
    ----------
    heating_rates : list[float]
        List of heating rates β.
    temperature_data : list[np.ndarray]
        Temperature arrays (°C) – one array per heating rate.
    conversion_data : list[np.ndarray]
        Conversion arrays (0–1) – one array per heating rate, same length as
        the corresponding temperature array.
    alpha_values : list[float], optional
        Conversion levels at which Ea is evaluated.
        Default: np.arange(0.1, 0.95, 0.05).

    Returns
    -------
    list[KineticResult]
        One KineticResult per α value.  Results where fewer than two heating
        rates yield a valid temperature are silently skipped.
    """
    if alpha_values is None:
        alpha_values = np.arange(0.1, 0.95, 0.05).tolist()
    level = _coerce_confidence_level(confidence_level)

    beta = np.asarray(heating_rates, dtype=float)
    log_beta = np.log10(beta)

    if len(beta) != len(temperature_data) or len(beta) != len(conversion_data):
        raise ValueError(
            "heating_rates, temperature_data, and conversion_data must all "
            "have the same number of elements."
        )

    results: list[KineticResult] = []

    for alpha in alpha_values:
        temps_at_alpha: list[float] = []
        valid_log_beta: list[float] = []

        for i, (T_arr, alpha_arr) in enumerate(zip(temperature_data, conversion_data)):
            T_arr = np.asarray(T_arr, dtype=float)
            alpha_arr = np.asarray(alpha_arr, dtype=float)

            # Require the conversion range to span α
            if alpha_arr.min() >= alpha or alpha_arr.max() <= alpha:
                continue

            # Interpolate temperature at this α
            try:
                interp_func = interpolate.interp1d(
                    alpha_arr, T_arr, kind="linear", bounds_error=False,
                    fill_value="extrapolate"
                )
                t_at_alpha = float(interp_func(alpha))
            except Exception:
                continue

            temps_at_alpha.append(t_at_alpha + 273.15)  # convert to K
            valid_log_beta.append(log_beta[i])

        if len(temps_at_alpha) < 2:
            continue

        inv_t = np.array([1.0 / t for t in temps_at_alpha])
        log_b = np.array(valid_log_beta)

        fit = stats.linregress(inv_t, log_b)
        slope, intercept, r_value = fit.slope, fit.intercept, fit.rvalue

        # Doyle approximation: slope = -0.4567 * Ea / R
        ea_j_per_mol = -slope * GAS_CONSTANT_R / 0.4567
        ea_kj_per_mol = ea_j_per_mol / 1000.0
        ci_low, ci_high, ci_status, ci_reason = _slope_ea_ci(
            slope=slope,
            slope_stderr=float(fit.stderr),
            n_points=len(inv_t),
            confidence_level=level,
            slope_to_ea_factor=GAS_CONSTANT_R / (0.4567 * 1000.0),
        )

        x_fit = np.linspace(inv_t.min(), inv_t.max(), 200)
        y_fit = slope * x_fit + intercept

        plot_data = {
            "alpha": float(alpha),
            "inv_t": inv_t.tolist(),
            "log_beta": log_b.tolist(),
            "x_fit": x_fit.tolist(),
            "y_fit": y_fit.tolist(),
            "xlabel": "1/T  (K⁻¹)",
            "ylabel": "log(β)  (log K·min⁻¹)",
        }

        results.append(
            KineticResult(
                method="ozawa_flynn_wall",
                activation_energy=ea_kj_per_mol,
                pre_exponential=None,
                r_squared=r_value**2,
                plot_data=plot_data,
                regression_slope=float(slope),
                regression_intercept=float(intercept),
                slope_stderr=float(fit.stderr) if math.isfinite(fit.stderr) else None,
                intercept_stderr=float(fit.intercept_stderr) if math.isfinite(fit.intercept_stderr) else None,
                n_points=len(inv_t),
                confidence_level=level,
                ea_ci_low_kj_mol=ci_low,
                ea_ci_high_kj_mol=ci_high,
                ea_ci_status=ci_status,
                ea_ci_withheld_reason=ci_reason,
                intercept_semantics=INTERCEPT_SEMANTICS["ofw"],
            )
        )

    return results


def friedman_analysis(
    heating_rates: list[float],
    temperature_data: list[np.ndarray],
    conversion_data: list[np.ndarray],
    dalpha_dt_data: list[np.ndarray],
    alpha_values: Optional[list[float]] = None,
    confidence_level: float = KINETICS_DEFAULT_CONFIDENCE_LEVEL,
) -> list[KineticResult]:
    """
    Friedman differential isoconversional analysis.

    At each conversion α the method fits:

        ln(dα/dt) = -Ea / (R · T) + ln[A · f(α)]

    Parameters
    ----------
    heating_rates : list[float]
        List of heating rates β (used for labelling only in this method).
    temperature_data : list[np.ndarray]
        Temperature arrays (°C) – one per heating rate.
    conversion_data : list[np.ndarray]
        Conversion arrays (0–1) – one per heating rate.
    dalpha_dt_data : list[np.ndarray]
        Conversion-rate arrays dα/dt (s⁻¹ or min⁻¹) – one per heating rate,
        same length as the corresponding temperature and conversion arrays.
    alpha_values : list[float], optional
        Conversion levels at which Ea is evaluated.
        Default: np.arange(0.1, 0.95, 0.05).

    Returns
    -------
    list[KineticResult]
        One KineticResult per α value.
    """
    if alpha_values is None:
        alpha_values = np.arange(0.1, 0.95, 0.05).tolist()
    level = _coerce_confidence_level(confidence_level)

    n = len(heating_rates)
    if len(temperature_data) != n or len(conversion_data) != n or len(dalpha_dt_data) != n:
        raise ValueError(
            "heating_rates, temperature_data, conversion_data, and "
            "dalpha_dt_data must all have the same number of elements."
        )

    results: list[KineticResult] = []

    for alpha in alpha_values:
        inv_t_vals: list[float] = []
        ln_dalpha_dt_vals: list[float] = []

        for T_arr, alpha_arr, dalpha_arr in zip(
            temperature_data, conversion_data, dalpha_dt_data
        ):
            T_arr = np.asarray(T_arr, dtype=float)
            alpha_arr = np.asarray(alpha_arr, dtype=float)
            dalpha_arr = np.asarray(dalpha_arr, dtype=float)

            if alpha_arr.min() >= alpha or alpha_arr.max() <= alpha:
                continue

            try:
                interp_t = interpolate.interp1d(
                    alpha_arr, T_arr, kind="linear", bounds_error=False,
                    fill_value="extrapolate"
                )
                interp_dalpha = interpolate.interp1d(
                    alpha_arr, dalpha_arr, kind="linear", bounds_error=False,
                    fill_value="extrapolate"
                )
                t_at_alpha = float(interp_t(alpha)) + 273.15  # K
                da_at_alpha = float(interp_dalpha(alpha))
            except Exception:
                continue

            if da_at_alpha <= 0:
                continue

            inv_t_vals.append(1.0 / t_at_alpha)
            ln_dalpha_dt_vals.append(np.log(da_at_alpha))

        if len(inv_t_vals) < 2:
            continue

        inv_t = np.array(inv_t_vals)
        ln_da = np.array(ln_dalpha_dt_vals)

        fit = stats.linregress(inv_t, ln_da)
        slope, intercept, r_value = fit.slope, fit.intercept, fit.rvalue

        ea_j_per_mol = -slope * GAS_CONSTANT_R
        ea_kj_per_mol = ea_j_per_mol / 1000.0
        ci_low, ci_high, ci_status, ci_reason = _slope_ea_ci(
            slope=slope,
            slope_stderr=float(fit.stderr),
            n_points=len(inv_t),
            confidence_level=level,
            slope_to_ea_factor=GAS_CONSTANT_R / 1000.0,
        )

        x_fit = np.linspace(inv_t.min(), inv_t.max(), 200)
        y_fit = slope * x_fit + intercept

        plot_data = {
            "alpha": float(alpha),
            "inv_t": inv_t.tolist(),
            "ln_dalpha_dt": ln_da.tolist(),
            "x_fit": x_fit.tolist(),
            "y_fit": y_fit.tolist(),
            "xlabel": "1/T  (K⁻¹)",
            "ylabel": "ln(dα/dt)  (ln min⁻¹)",
        }

        results.append(
            KineticResult(
                method="friedman",
                activation_energy=ea_kj_per_mol,
                pre_exponential=intercept,   # ln[A·f(α)] — see intercept_semantics
                r_squared=r_value**2,
                plot_data=plot_data,
                regression_slope=float(slope),
                regression_intercept=float(intercept),
                slope_stderr=float(fit.stderr) if math.isfinite(fit.stderr) else None,
                intercept_stderr=float(fit.intercept_stderr) if math.isfinite(fit.intercept_stderr) else None,
                n_points=len(inv_t),
                confidence_level=level,
                ea_ci_low_kj_mol=ci_low,
                ea_ci_high_kj_mol=ci_high,
                ea_ci_status=ci_status,
                ea_ci_withheld_reason=ci_reason,
                intercept_semantics=INTERCEPT_SEMANTICS["friedman"],
            )
        )

    return results


def compute_conversion(
    temperature: np.ndarray,
    signal: np.ndarray,
    baseline: Optional[np.ndarray] = None,
    mode: str = "dsc",
) -> np.ndarray:
    """
    Convert a DSC or TGA signal to fractional conversion α (0–1).

    Parameters
    ----------
    temperature : np.ndarray
        Temperature axis (°C or K – only used as the integration variable).
    signal : np.ndarray
        For DSC: heat-flow signal (mW or mW/mg).
        For TGA: sample mass (mg or %).
    baseline : np.ndarray, optional
        Baseline signal to subtract before integration (DSC only).
        For TGA this parameter is ignored.
    mode : {'dsc', 'tga'}
        'dsc' uses cumulative integration of (signal − baseline).
        'tga' uses (m0 − m) / (m0 − mf).

    Returns
    -------
    np.ndarray
        Conversion array of the same length as *signal*, values in [0, 1].

    Raises
    ------
    ValueError
        If the total area/mass change is zero (degenerate signal).
    """
    temperature = np.asarray(temperature, dtype=float)
    signal = np.asarray(signal, dtype=float)

    if mode.lower() == "tga":
        m0 = signal[0]
        mf = signal[-1]
        delta = m0 - mf
        if np.isclose(delta, 0.0):
            raise ValueError(
                "TGA signal shows no mass change; cannot compute conversion."
            )
        alpha = (m0 - signal) / delta
        return np.clip(alpha, 0.0, 1.0)

    # DSC mode ----------------------------------------------------------------
    if baseline is None:
        # Linear baseline between first and last point
        baseline = np.linspace(signal[0], signal[-1], len(signal))
    else:
        baseline = np.asarray(baseline, dtype=float)

    corrected = signal - baseline

    # Cumulative trapezoid integration with respect to temperature
    cumulative = integrate.cumulative_trapezoid(corrected, temperature, initial=0.0)
    total_area = cumulative[-1]

    if np.isclose(total_area, 0.0):
        raise ValueError(
            "DSC signal area is zero after baseline subtraction; "
            "cannot compute conversion."
        )

    alpha = cumulative / total_area
    return np.clip(alpha, 0.0, 1.0)


def _resolve_kinetic_method(method: str) -> tuple[str, str]:
    token = str(method or "").strip().lower().replace("_", " ").replace("-", " ")
    if token in {"kissinger"}:
        return "kissinger", "Kissinger"
    if token in {"ofw", "ozawa flynn wall", "ozawa flynnwall"}:
        return "ofw", "Ozawa-Flynn-Wall"
    if token in {"friedman"}:
        return "friedman", "Friedman"
    raise ValueError(f"Unsupported kinetic method: {method}")


def _kinetics_rows(method_id: str, results: list[KineticResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in results:
        row: dict[str, Any] = {
            "activation_energy_kj_mol": float(item.activation_energy),
            "r_squared": float(item.r_squared) if item.r_squared is not None else None,
        }
        if item.pre_exponential is not None:
            row["pre_exponential"] = float(item.pre_exponential)
        alpha = (item.plot_data or {}).get("alpha")
        if alpha is not None:
            row["alpha"] = float(alpha)
        row["regression_intercept"] = (
            float(item.regression_intercept) if item.regression_intercept is not None else None
        )
        row["intercept_semantics"] = item.intercept_semantics
        row["n_points"] = int(item.n_points) if item.n_points is not None else None
        row["confidence_level"] = (
            float(item.confidence_level) if item.confidence_level is not None else None
        )
        row["ea_ci_method"] = KINETICS_CI_METHOD
        row["ea_ci_status"] = item.ea_ci_status
        row["activation_energy_ci_low_kj_mol"] = (
            float(item.ea_ci_low_kj_mol) if item.ea_ci_low_kj_mol is not None else None
        )
        row["activation_energy_ci_high_kj_mol"] = (
            float(item.ea_ci_high_kj_mol) if item.ea_ci_high_kj_mol is not None else None
        )
        if item.ea_ci_withheld_reason:
            row["ea_ci_withheld_reason"] = item.ea_ci_withheld_reason
        if method_id == "kissinger":
            row["regression_axis_x"] = "1/Tp"
            row["regression_axis_y"] = "ln(beta/Tp^2)"
            row["ln_a_min_inv"] = (
                float(item.ln_a_min_inv) if item.ln_a_min_inv is not None else None
            )
        rows.append(row)
    return rows


def _kinetics_summary(method_id: str, results: list[KineticResult]) -> dict[str, Any]:
    if method_id == "kissinger":
        result = results[0]
        return {
            "activation_energy_kj_mol": float(result.activation_energy),
            "pre_exponential": float(result.pre_exponential) if result.pre_exponential is not None else None,
            "r_squared": float(result.r_squared) if result.r_squared is not None else None,
            "regression_intercept": float(result.regression_intercept) if result.regression_intercept is not None else None,
            "intercept_semantics": result.intercept_semantics,
            "ln_a_min_inv": float(result.ln_a_min_inv) if result.ln_a_min_inv is not None else None,
            "n_points": int(result.n_points) if result.n_points is not None else None,
            "confidence_level": float(result.confidence_level) if result.confidence_level is not None else None,
            "ea_ci_method": KINETICS_CI_METHOD,
            "ea_ci_ols_assumptions": KINETICS_OLS_ASSUMPTIONS,
            "ea_ci_scope": KINETICS_CI_SCOPE,
            "ea_ci_status": result.ea_ci_status,
            "ea_ci_withheld_reason": result.ea_ci_withheld_reason or "",
            "activation_energy_ci_low_kj_mol": float(result.ea_ci_low_kj_mol) if result.ea_ci_low_kj_mol is not None else None,
            "activation_energy_ci_high_kj_mol": float(result.ea_ci_high_kj_mol) if result.ea_ci_high_kj_mol is not None else None,
        }

    ea = [float(item.activation_energy) for item in results]
    r2 = [float(item.r_squared) for item in results if item.r_squared is not None]
    ci_lows = [float(item.ea_ci_low_kj_mol) for item in results if item.ea_ci_low_kj_mol is not None]
    ci_highs = [float(item.ea_ci_high_kj_mol) for item in results if item.ea_ci_high_kj_mol is not None]
    levels = {float(item.confidence_level) for item in results if item.confidence_level is not None}
    return {
        "conversion_point_count": len(results),
        "activation_energy_min_kj_mol": min(ea) if ea else None,
        "activation_energy_max_kj_mol": max(ea) if ea else None,
        "activation_energy_mean_kj_mol": float(np.mean(ea)) if ea else None,
        "mean_r_squared": float(np.mean(r2)) if r2 else None,
        "confidence_level": levels.pop() if len(levels) == 1 else None,
        "ea_ci_method": KINETICS_CI_METHOD,
        "ea_ci_ols_assumptions": KINETICS_OLS_ASSUMPTIONS,
        "ea_ci_scope": KINETICS_CI_SCOPE,
        "ea_ci_computed_count": sum(1 for item in results if item.ea_ci_status == "computed"),
        "ea_ci_withheld_count": sum(1 for item in results if item.ea_ci_status == "withheld"),
        "activation_energy_ci_low_min_kj_mol": min(ci_lows) if ci_lows else None,
        "activation_energy_ci_high_max_kj_mol": max(ci_highs) if ci_highs else None,
    }


def _kinetics_scientific_context(method_id: str, label: str, results: list[KineticResult]) -> dict[str, Any]:
    equations: list[dict[str, Any]]
    if method_id == "kissinger":
        equations = [
            build_equation(
                "Kissinger Linearization",
                "ln(beta / Tp^2) = -Ea / (R * Tp) + ln(A * R / Ea)",
            )
        ]
    elif method_id == "ofw":
        equations = [
            build_equation(
                "OFW Approximation",
                "log(beta) = -0.4567 * Ea / (R * T_alpha) + C",
            )
        ]
    else:
        equations = [
            build_equation(
                "Friedman Differential Form",
                "ln(dalpha/dt) = -Ea / (R * T_alpha) + ln(A * f(alpha))",
            )
        ]

    interpretations = [
        build_interpretation(
            "Kinetic analysis finished successfully.",
            metric="result_count",
            value=len(results),
            unit="result rows",
        )
    ]
    if results:
        interpretations.append(
            build_interpretation(
                "Representative activation energy result.",
                metric="activation_energy_kj_mol",
                value=float(results[0].activation_energy),
                unit="kJ/mol",
            )
        )
        first = results[0]
        if first.ea_ci_status == "computed" and first.ea_ci_low_kj_mol is not None:
            interpretations.append(
                build_interpretation(
                    f"Ea {first.confidence_level:.0%} confidence interval "
                    f"[{first.ea_ci_low_kj_mol:.2f}, {first.ea_ci_high_kj_mol:.2f}] kJ/mol "
                    f"({KINETICS_CI_METHOD}).",
                    metric="activation_energy_ci",
                    value={"low": float(first.ea_ci_low_kj_mol), "high": float(first.ea_ci_high_kj_mol)},
                    unit="kJ/mol",
                )
            )
        elif first.ea_ci_status == "withheld":
            interpretations.append(
                build_interpretation(
                    f"Ea confidence interval withheld: {first.ea_ci_withheld_reason}.",
                    metric="activation_energy_ci",
                    value=None,
                    unit="kJ/mol",
                )
            )

    r2 = [float(item.r_squared) for item in results if item.r_squared is not None]
    fit_quality = build_fit_quality(
        {
            "evaluated_rows": len(results),
            "mean_r_squared": float(np.mean(r2)) if r2 else None,
            "min_r_squared": min(r2) if r2 else None,
            "max_r_squared": max(r2) if r2 else None,
        }
    )
    base_context = build_scientific_context(
        methodology={
            "analysis_family": "Kinetic Analysis",
            "method": label,
            "temperature_scale": "kelvin",
            "ea_ci_method": KINETICS_CI_METHOD,
            "ea_ci_ols_assumptions": KINETICS_OLS_ASSUMPTIONS,
            "ea_ci_scope": KINETICS_CI_SCOPE,
            "confidence_level": float(results[0].confidence_level) if results and results[0].confidence_level is not None else None,
            "intercept_semantics": INTERCEPT_SEMANTICS.get(method_id),
        },
        equations=equations,
        numerical_interpretation=interpretations,
        fit_quality=fit_quality,
        limitations=[
            "Interpretation quality depends on heating-rate spread and conversion interpolation quality.",
            KINETICS_OLS_ASSUMPTIONS,
            KINETICS_CI_SCOPE,
            "The regression intercept is not ln(A) on its own; see intercept_semantics for the method-specific meaning.",
        ],
    )
    reasoning = build_scientific_reasoning(
        analysis_type=label,
        summary=_kinetics_summary(method_id, results),
        rows=_kinetics_rows(method_id, results),
        metadata={},
        fit_quality=fit_quality,
        validation={},
    )
    merged = dict(base_context)
    merged.update(reasoning)
    return merged


def run_kinetic_analysis(
    method: str,
    *,
    heating_rates: list[float],
    peak_temperatures: list[float] | None = None,
    temperature_data: list[np.ndarray] | None = None,
    conversion_data: list[np.ndarray] | None = None,
    dalpha_dt_data: list[np.ndarray] | None = None,
    alpha_values: Optional[list[float]] = None,
    confidence_level: float = KINETICS_DEFAULT_CONFIDENCE_LEVEL,
) -> dict[str, Any]:
    """
    Unified kinetics runner with report-ready payloads.

    Returns a dict containing method metadata, raw KineticResult rows, summary,
    and scientific_context for normalized report serialization.
    """
    method_id, method_label = _resolve_kinetic_method(method)

    if method_id == "kissinger":
        if peak_temperatures is None:
            raise ValueError("peak_temperatures is required for Kissinger analysis.")
        result = kissinger_analysis(heating_rates, peak_temperatures, confidence_level=confidence_level)
        results = [result]
    elif method_id == "ofw":
        if temperature_data is None or conversion_data is None:
            raise ValueError("temperature_data and conversion_data are required for OFW analysis.")
        results = ozawa_flynn_wall_analysis(
            heating_rates,
            temperature_data,
            conversion_data,
            alpha_values=alpha_values,
            confidence_level=confidence_level,
        )
    else:
        if temperature_data is None or conversion_data is None or dalpha_dt_data is None:
            raise ValueError(
                "temperature_data, conversion_data, and dalpha_dt_data are required for Friedman analysis."
            )
        results = friedman_analysis(
            heating_rates,
            temperature_data,
            conversion_data,
            dalpha_dt_data,
            alpha_values=alpha_values,
            confidence_level=confidence_level,
        )

    rows = _kinetics_rows(method_id, results)
    summary = _kinetics_summary(method_id, results)
    scientific_context = _kinetics_scientific_context(method_id, method_label, results)

    return {
        "method_id": method_id,
        "method_label": method_label,
        "results": results,
        "rows": rows,
        "summary": summary,
        "scientific_context": scientific_context,
    }
