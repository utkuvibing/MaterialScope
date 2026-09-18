"""
Multi-peak deconvolution using lmfit.

Supports Gaussian, Lorentzian, and pseudo-Voigt peak shapes.
Initial parameters can be supplied manually or estimated automatically
via scipy.signal.find_peaks.
"""

from __future__ import annotations

import numpy as np
from typing import Optional
from scipy.signal import find_peaks

try:
    from lmfit import CompositeModel, Model, Parameters
    from lmfit.models import GaussianModel, LorentzianModel, PseudoVoigtModel
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "lmfit is required for peak deconvolution. "
        "Install it with:  pip install lmfit"
    ) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def deconvolve_peaks(
    x: np.ndarray,
    y: np.ndarray,
    n_peaks: int,
    peak_shape: str = "gaussian",
    initial_params: Optional[list[dict]] = None,
) -> dict:
    """
    Fit *n_peaks* overlapping peaks to the data (x, y).

    Parameters
    ----------
    x : np.ndarray
        Independent axis (e.g., temperature, wavenumber, 2θ).
    y : np.ndarray
        Signal intensity / heat-flow values.
    n_peaks : int
        Number of peaks to fit.  Must be >= 1.
    peak_shape : {'gaussian', 'lorentzian', 'pseudo_voigt'}
        Functional form for every peak component.
    initial_params : list[dict], optional
        Per-peak initial guesses.  Each dict may contain any subset of:
        ``{'center': float, 'amplitude': float, 'sigma': float}``.
        Missing keys are filled by the auto-estimator.  If *None* the
        auto-estimator is used for all peaks.

    Returns
    -------
    dict with keys:

    ``'params'``
        dict – fitted lmfit Parameters values keyed by parameter name.
    ``'fitted'``
        np.ndarray – total fitted curve evaluated on *x*.
    ``'components'``
        list[np.ndarray] – individual peak contributions on *x*.
    ``'residual'``
        np.ndarray – y minus fitted (should be small / noise-like).
    ``'r_squared'``
        float – coefficient of determination for the total fit.
    ``'report'``
        str – full lmfit fit report.
    ``'initial_guesses'``
        list[dict] – the initial guess actually used per peak.  Every entry
        carries ``field_sources`` so a partially user-supplied peak is
        recorded honestly: ``source`` is ``'user'`` only when the caller
        supplied every field, ``'auto'`` when none, ``'mixed'`` otherwise.
    ``'residual_stats'`` / ``'fit_quality'``
        dict – agreement statistics.  ``sse_per_dof`` (alias
        ``unweighted_sse_per_dof``) is the unweighted residual sum of squares
        per degree of freedom; it is *not* a measurement-uncertainty-weighted
        reduced chi-square.  ``reduced_chi_squared`` is retained for
        backward compatibility and carries the same unweighted value.
    ``'auto_estimate'``
        dict – diagnostics from the automatic estimator (detected peak count,
        prominence threshold, whether even-spacing fallback was used, and
        whether the signal has usable positive structure).

    Raises
    ------
    ValueError
        If *n_peaks* < 1 or *peak_shape* is not recognised.
    RuntimeError
        If lmfit fails to converge.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if n_peaks < 1:
        raise ValueError("n_peaks must be >= 1.")

    valid_shapes = {"gaussian", "lorentzian", "pseudo_voigt"}
    if peak_shape.lower() not in valid_shapes:
        raise ValueError(
            f"peak_shape must be one of {valid_shapes!r}, got {peak_shape!r}."
        )

    # Build the composite model and set initial parameters
    composite_model, param_names_per_peak = _build_model(n_peaks, peak_shape)
    auto_estimate = auto_estimate_peaks(x, y, n_peaks, peak_shape=peak_shape)
    auto_estimates = auto_estimate["peaks"]

    params = composite_model.make_params()
    used_initial_guesses: list[dict] = []

    for peak_idx in range(n_peaks):
        auto = auto_estimates[peak_idx]
        user = (initial_params[peak_idx] if initial_params and peak_idx < len(initial_params)
                else {})
        if not isinstance(user, dict):
            user = {}

        # Per-field provenance: a peak is only "user" for the fields the
        # caller actually supplied.  Partial hints are recorded as "mixed"
        # instead of claiming the whole peak came from the user.
        field_sources = {
            key: ("user" if user.get(key) is not None else "auto")
            for key in ("center", "amplitude", "sigma")
        }
        supplied = {source for source in field_sources.values()}
        if supplied == {"user"}:
            source = "user"
        elif supplied == {"auto"}:
            source = "auto"
        else:
            source = "mixed"

        center = user.get("center", auto["center"])
        amplitude = user.get("amplitude", auto["amplitude"])
        sigma = user.get("sigma", auto["sigma"])
        used_initial_guesses.append(
            {
                "peak": peak_idx + 1,
                "center": float(center),
                "amplitude": float(amplitude),
                "sigma": float(sigma),
                "source": source,
                "field_sources": field_sources,
            }
        )

        prefix = f"p{peak_idx + 1}_"
        params[f"{prefix}center"].set(value=center, min=x.min(), max=x.max())
        params[f"{prefix}amplitude"].set(value=amplitude, min=0)
        params[f"{prefix}sigma"].set(value=sigma, min=1e-6)

        if peak_shape.lower() == "pseudo_voigt":
            params[f"{prefix}fraction"].set(value=0.5, min=0.0, max=1.0)

    # Perform the fit
    result = composite_model.fit(y, params, x=x)

    if not result.success and result.aborted:
        raise RuntimeError(
            "lmfit minimisation did not converge. "
            "Try providing better initial_params."
        )

    # Evaluate total fit and individual components
    fitted = result.eval(x=x)
    components = _eval_components(result, x, n_peaks, peak_shape)
    residual = y - fitted
    r_squared = _r_squared(y, fitted)
    rmse = float(np.sqrt(np.mean(residual ** 2)))
    mae = float(np.mean(np.abs(residual)))
    max_abs_residual = float(np.max(np.abs(residual)))
    # Degrees of freedom: only independently varied parameters reduce DoF.
    # lmfit derives ``height``/``fwhm`` from ``amplitude``/``sigma``, so
    # counting every entry in ``result.params`` understates DoF.
    n_data = int(getattr(result, "ndata", None) or len(y))
    nvarys = getattr(result, "nvarys", None)
    if nvarys is None:  # pragma: no cover - defensive for non-lmfit results
        free_param_count = sum(1 for p in result.params.values() if p.vary and p.expr is None)
    else:
        free_param_count = int(nvarys)
    dof = max(n_data - free_param_count, 1)
    # Unweighted residual sum of squares per DoF.  The fit carries no
    # measurement uncertainties, so this is NOT a reduced chi-square in the
    # metrological sense; the honest name is sse_per_dof.
    sse = float(np.sum(residual ** 2))
    sse_per_dof = float(sse / dof)

    # Collect fitted parameter values into a plain dict
    fitted_params = {name: result.params[name].value for name in result.params}

    return {
        "params": fitted_params,
        "fitted": fitted,
        "components": components,
        "residual": residual,
        "r_squared": r_squared,
        "report": result.fit_report(),
        "initial_guesses": used_initial_guesses,
        "auto_estimate": auto_estimate,
        "residual_stats": {
            "rmse": rmse,
            "mae": mae,
            "max_abs_residual": max_abs_residual,
            "sse_per_dof": sse_per_dof,
            "unweighted_sse_per_dof": sse_per_dof,
            # Legacy alias retained for compatibility; carries the same
            # unweighted value as sse_per_dof.
            "reduced_chi_squared": sse_per_dof,
            "dof": int(dof),
            "free_param_count": int(free_param_count),
            "n_data": int(n_data),
        },
        "fit_quality": {
            "r_squared": r_squared,
            "rmse": rmse,
            "sse_per_dof": sse_per_dof,
            "unweighted_sse_per_dof": sse_per_dof,
            "reduced_chi_squared": sse_per_dof,
            "dof": int(dof),
        },
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_model(
    n_peaks: int,
    peak_shape: str,
) -> tuple[CompositeModel, list[list[str]]]:
    """
    Build an lmfit CompositeModel for *n_peaks* peaks.

    Returns the composite model and a list of parameter-name lists,
    one sub-list per peak.
    """
    shape = peak_shape.lower()
    param_names_per_peak: list[list[str]] = []
    composite: Optional[CompositeModel] = None

    for i in range(n_peaks):
        prefix = f"p{i + 1}_"

        if shape == "gaussian":
            peak_model = GaussianModel(prefix=prefix)
        elif shape == "lorentzian":
            peak_model = LorentzianModel(prefix=prefix)
        else:  # pseudo_voigt
            peak_model = PseudoVoigtModel(prefix=prefix)

        param_names_per_peak.append(list(peak_model.param_names))

        if composite is None:
            composite = peak_model
        else:
            composite = composite + peak_model

    return composite, param_names_per_peak


# lmfit's ``amplitude`` is the integrated area of each (normalized) peak
# profile, not the peak height.  The automatic estimator therefore has to
# convert a sampled height into that area using each shape's own convention:
#
#   Gaussian     f(c) = A / (sqrt(2*pi) * sigma)   -> A = h * sigma * sqrt(2*pi)
#   Lorentzian   f(c) = A / (pi * sigma)           -> A = h * sigma * pi
#   pseudo-Voigt f(c) = A * [(1-f)/(sqrt(2*pi)*sigma) + f/(pi*sigma)]
#
GAUSSIAN_AREA_FACTOR = float(np.sqrt(2.0 * np.pi))
LORENTZIAN_AREA_FACTOR = float(np.pi)
PSEUDO_VOIGT_DEFAULT_FRACTION = 0.5


def shape_area_factor(peak_shape: str, *, fraction: float = PSEUDO_VOIGT_DEFAULT_FRACTION) -> float:
    """Return the multiplier that turns ``height * sigma`` into lmfit's amplitude.

    Each model uses its own ``sigma`` convention, taken from lmfit's own
    parameter definitions:

    - ``GaussianModel``:   ``height = A / (sigma * sqrt(2*pi))``
    - ``LorentzianModel``: ``height = A / (pi * sigma)``
    - ``PseudoVoigtModel``: the Gaussian term uses
      ``sigma_g = sigma / sqrt(2*ln 2)`` so every component — and the sum — has
      FWHM ``2*sigma``, giving
      ``height = A * ((1-f)/(sigma*sqrt(pi/log(2))) + f/(pi*sigma))``.
      Its ``sigma`` is therefore *not* a Gaussian standard deviation, and the
      conversion must not reuse the GaussianModel factor.
    """
    shape = str(peak_shape or "").strip().lower()
    if shape == "lorentzian":
        return LORENTZIAN_AREA_FACTOR
    if shape == "pseudo_voigt":
        clamped = min(max(float(fraction), 0.0), 1.0)
        mixing = (1.0 - clamped) / float(np.sqrt(np.pi / np.log(2.0))) + clamped / LORENTZIAN_AREA_FACTOR
        return 1.0 / max(mixing, 1e-12)
    return GAUSSIAN_AREA_FACTOR


def amplitude_from_height(
    height: float,
    sigma: float,
    peak_shape: str,
    *,
    fraction: float = PSEUDO_VOIGT_DEFAULT_FRACTION,
) -> float:
    """Convert a sampled peak height into lmfit's integrated-area amplitude."""
    return float(height) * max(float(sigma), 1e-12) * shape_area_factor(peak_shape, fraction=fraction)


def auto_estimate_peaks(
    x: np.ndarray,
    y: np.ndarray,
    n_peaks: int,
    peak_shape: str = "gaussian",
) -> dict:
    """
    Estimate initial center, amplitude, and sigma for each peak.

    Strategy
    --------
    1. Run scipy.signal.find_peaks on the positive-clipped signal.
    2. If fewer peaks are detected than requested, distribute the remaining
       centers evenly across the x-range.
    3. ``amplitude`` is lmfit's integrated-area parameter, so the sampled peak
       height is converted into an area with ``peak_shape``'s own convention
       (Gaussian, Lorentzian, or pseudo-Voigt).
    4. Sigma is set to one quarter of the average spacing between peaks
       (or a fraction of the x-range if only one peak).

    The estimation is *diagnostic*: callers can inspect the returned report
    to decide whether the signal actually carries usable positive structure
    for the non-negative component model instead of silently reshaping it.

    Returns
    -------
    dict with keys:

    ``'peaks'``
        list[dict] – ``{'center', 'amplitude', 'sigma', 'height'}`` per
        requested peak.  ``amplitude`` is an integrated area; ``height`` is
        the sampled height it was derived from.
    ``'detected_peak_count'``
        int – peaks found by find_peaks before any fallback spacing.
    ``'prominence_threshold'``
        float – prominence passed to find_peaks.
    ``'fallback_spacing_used'``
        bool – True when at least one center came from even spacing.
    ``'positive_point_fraction'``
        float – share of finite samples with a positive value.
    ``'positive_span'``
        float – range of the positive-clipped signal.
    ``'usable_positive_structure'``
        bool – True when at least one peak was detected on a signal with a
        non-zero positive span.
    ``'reason'``
        str | None – machine-readable reason when ``usable_positive_structure``
        is False (``'no_positive_structure'`` or ``'no_detectable_peaks'``).
    ``'amplitude_semantics'``
        str – always ``'integrated_area_parameter'``.
    ``'estimate_method'``
        str – the documented conversion used for the amplitude estimate.
    ``'shape_area_factor'``
        float – the multiplier applied to ``height * sigma``.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    y_pos = np.clip(y, 0, None)
    finite = np.isfinite(y_pos)
    if not np.any(finite):
        finite = np.ones_like(y_pos, dtype=bool)
    positive_point_fraction = float(np.mean(y_pos[finite] > 0)) if finite.any() else 0.0

    # Prominence threshold: 5% of the signal range
    prominence = 0.05 * (y_pos.max() - y_pos.min()) if y_pos.max() > y_pos.min() else 0.0

    detected_indices, _ = find_peaks(y_pos, prominence=prominence)

    # Sort by descending height and take up to n_peaks
    if len(detected_indices) > 0:
        order = np.argsort(y_pos[detected_indices])[::-1]
        detected_indices = detected_indices[order]

    detected_peak_count = int(len(detected_indices))
    centers_x = x[detected_indices].tolist() if len(detected_indices) > 0 else []

    # Pad with evenly spaced positions if we have fewer than n_peaks
    fallback_spacing_used = False
    if len(centers_x) < n_peaks:
        evenly_spaced = np.linspace(x.min(), x.max(), n_peaks + 2)[1:-1].tolist()
        existing = set(centers_x)
        for c in evenly_spaced:
            if len(centers_x) >= n_peaks:
                break
            # Avoid duplicating a center that is already close to an existing one
            if not any(abs(c - ex) < (x.max() - x.min()) / (n_peaks * 4) for ex in existing):
                centers_x.append(c)
                existing.add(c)
                fallback_spacing_used = True

    # If still not enough (very unlikely), just use evenly spaced
    if len(centers_x) < n_peaks:
        centers_x = np.linspace(x.min(), x.max(), n_peaks + 2)[1:-1].tolist()
        fallback_spacing_used = True

    centers_x = sorted(centers_x[:n_peaks])

    # Sigma: ~ quarter of average inter-peak spacing
    if n_peaks > 1:
        avg_spacing = (x.max() - x.min()) / (n_peaks - 1)
        sigma_default = avg_spacing / 4.0
    else:
        sigma_default = (x.max() - x.min()) / 6.0

    sigma_default = max(sigma_default, 1e-6)
    area_factor = shape_area_factor(peak_shape)

    estimates: list[dict] = []
    for c in centers_x:
        # Sampled height at the nearest grid point, converted into the
        # integrated-area amplitude the selected model actually expects.
        idx = int(np.argmin(np.abs(x - c)))
        height = float(y_pos[idx]) if y_pos[idx] > 0 else float(y_pos.max()) / n_peaks
        estimates.append(
            {
                "center": c,
                "amplitude": height * sigma_default * area_factor,
                "sigma": sigma_default,
                "height": height,
            }
        )

    positive_span = float(y_pos.max() - y_pos.min()) if y_pos.size else 0.0
    usable = bool(detected_peak_count >= 1 and positive_span > 0)
    if usable:
        reason = None
    elif positive_span <= 0:
        reason = "no_positive_structure"
    else:
        reason = "no_detectable_peaks"

    return {
        "peaks": estimates,
        "detected_peak_count": detected_peak_count,
        "prominence_threshold": float(prominence),
        "fallback_spacing_used": fallback_spacing_used,
        "positive_point_fraction": positive_point_fraction,
        "positive_span": positive_span,
        "usable_positive_structure": usable,
        "reason": reason,
        "amplitude_semantics": "integrated_area_parameter",
        "estimate_method": "height * sigma * shape_area_factor(peak_shape)",
        "peak_shape": str(peak_shape or "").strip().lower(),
        "shape_area_factor": float(area_factor),
    }


def _auto_estimate_params(
    x: np.ndarray,
    y: np.ndarray,
    n_peaks: int,
    peak_shape: str = "gaussian",
) -> list[dict]:
    """Backward-compatible wrapper returning only the per-peak guesses."""
    return auto_estimate_peaks(x, y, n_peaks, peak_shape=peak_shape)["peaks"]


def _eval_components(
    result,
    x: np.ndarray,
    n_peaks: int,
    peak_shape: str,
) -> list[np.ndarray]:
    """
    Evaluate each individual peak component from the fit result.

    lmfit's eval_components returns a dict keyed by prefix; we reorder
    to match the 1..n_peaks order used in _build_model.
    """
    comp_dict = result.eval_components(x=x)
    components: list[np.ndarray] = []

    for i in range(n_peaks):
        prefix = f"p{i + 1}_"
        if prefix in comp_dict:
            components.append(np.asarray(comp_dict[prefix], dtype=float))
        else:
            # Fallback: zero-filled array (should not happen in normal usage)
            components.append(np.zeros_like(x))

    return components


def _r_squared(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute coefficient of determination R²."""
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if np.isclose(ss_tot, 0.0):
        return 1.0 if np.isclose(ss_res, 0.0) else 0.0
    return float(1.0 - ss_res / ss_tot)
