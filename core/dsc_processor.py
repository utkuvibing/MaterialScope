"""
DSC (Differential Scanning Calorimetry) analysis pipeline.

Provides DSCProcessor, a fluent-interface class that chains signal smoothing,
mass normalisation, baseline correction, peak detection, and glass-transition
detection into a single, reproducible workflow.  The final state is exported
as a DSCResult dataclass.

Imports from sibling modules (run from the materialscope/ directory):
    core.preprocessing  - smooth_signal, compute_derivative, normalize_by_mass
    core.baseline       - correct_baseline
    core.peak_analysis  - find_thermal_peaks, characterize_peaks, ThermalPeak
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.preprocessing import smooth_signal, compute_derivative, normalize_by_mass
from core.baseline import correct_baseline
from core.peak_analysis import find_thermal_peaks, characterize_peaks, ThermalPeak
from core.sign_convention import CANONICAL, SignConvention, parse_declared
from core.units_dimensional import (
    UnitClass,
    canonical_signal_unit,
    heat_flow_step_to_delta_cp,
    peak_area_to_enthalpy,
    resolve_beta,
    resolve_working_unit,
)


# ---------------------------------------------------------------------------
# Glass-transition morphology gates
# ---------------------------------------------------------------------------
# A glass transition is a *persistent baseline step*: the signal settles on
# one level, transitions through an inflection, then settles on a different
# level.  Sharp peaks, decomposition spikes, edge artefacts and generic
# high-curvature features all produce large |d2| but fail the step
# morphology checks below.  Candidates are local maxima of the smoothed
# |first derivative| (the inflection of a step is where |d1| peaks); each is
# accepted only when every gate passes.

_TG_CANDIDATE_MAD = 1.5          # |d1| candidate floor = median + K*MAD (noise-relative)
_TG_ONSET_FRACTION = 0.15        # onset/endset walk threshold vs candidate |d1|
_TG_MIN_STEP_FRACTION = 0.60     # plateau shift vs total local excursion
_TG_MIN_PLATEAU_SNR = 3.0        # plateau shift vs detrended plateau roughness
_TG_MAX_PLATEAU_EXCURSION = 0.35  # plateau-window peak-to-peak vs shift
_TG_TRANSITION_RANGE = (0.5, 1.5)  # in-transition change vs plateau shift
_TG_PERSISTENCE_TOL = 0.50       # far-window step agreement tolerance


def _detrended_std(x: np.ndarray, y: np.ndarray) -> float:
    """Standard deviation of ``y`` after removing its best-fit line."""
    if y.size < 3 or np.ptp(x) <= 0:
        return float(np.std(y)) if y.size else 0.0
    coeffs = np.polyfit(x, y, 1)
    return float(np.std(y - np.polyval(coeffs, x)))


def _tg_step_evidence(
    t_full: np.ndarray,
    s_full: np.ndarray,
    infl: int,
    d1_smooth: np.ndarray,
    noise_level: float,
    flat_width: int,
    strict_context: bool,
) -> Optional[Tuple[int, int, float]]:
    """
    Evaluate whether the |d1| local maximum at ``infl`` is a baseline step.

    ``infl`` indexes the FULL signal, and ``d1_smooth`` is the smoothed
    |d1| of the full signal: the onset/endset walk and all plateau and
    persistence windows run on full-signal context so that a
    user-supplied region cannot hide context — a peak flank looks like a
    step inside a tight window, but the levels do not persist just
    outside it, and the walk must be able to descend past the transition
    foot even when the region boundary sits on it.

    Returns ``(onset_idx, endset_idx, heat_flow_step)`` when the candidate
    passes every morphology gate, else ``None``.  The gates are:

    * plateaus must exist on both sides (rejects edge artefacts);
    * the plateau level shift must dominate the local excursion
      (rejects features smaller than their own surroundings);
    * the shift must exceed detrended plateau roughness (SNR gate);
    * each plateau window must be flat relative to the shift
      (rejects peak flanks, which keep rising/falling through the window);
    * the signal change *within* [onset, endset] must match the plateau
      shift (rejects ramp/peak fragments whose apparent levels are set by
      windows far from a tiny transition);
    * the shift must persist: re-measuring it in far plateau windows must
      agree within tolerance (rejects broad-peak flanks and ramps that
      never settle).
    """
    n_full = len(t_full)
    threshold = max(_TG_ONSET_FRACTION * float(d1_smooth[infl]), noise_level)

    onset = infl
    for i in range(infl, -1, -1):
        if d1_smooth[i] <= threshold:
            onset = i
            break
    endset = infl
    for i in range(infl, n_full):
        if d1_smooth[i] <= threshold:
            endset = i
            break

    # Plateau windows in temperature space on the full signal.  The
    # derivative walk stops where the foot slope decays below the noise
    # floor, i.e. inside the true transition extent — so plateau windows
    # are pushed a half-transition-width clear of the measured
    # [onset, endset] to sit on genuinely flat signal.
    d_t = float(np.median(np.diff(t_full))) if n_full > 1 else 0.0
    flat_t = flat_width * abs(d_t) if d_t else 0.0
    if flat_t <= 0:
        return None

    def _plateau_levels(t_on: float, t_en: float):
        gap = max(0.5 * (t_en - t_on), 0.5 * flat_t)
        pre_edge, post_edge = t_on - gap, t_en + gap
        pre = (t_full >= pre_edge - flat_t) & (t_full < pre_edge)
        post = (t_full >= post_edge) & (t_full < post_edge + flat_t)
        if int(pre.sum()) < 3 or int(post.sum()) < 3:
            return None
        return pre_edge, post_edge, pre, post

    first = _plateau_levels(float(t_full[onset]), float(t_full[endset]))
    if first is None:
        return None
    pre_edge, post_edge, pre_mask, post_mask = first
    mean_before = float(np.mean(s_full[pre_mask]))
    mean_after = float(np.mean(s_full[post_mask]))
    step = mean_after - mean_before
    if not np.isfinite(step) or abs(step) < 1e-12:
        return None

    # Refine [onset, endset] by level crossing against the plateau means:
    # the transition edges are where the (lightly smoothed) signal leaves
    # the before level / reaches the after level — the analogue of the
    # tangent-intersection construction, and robust where the derivative
    # walk stalls inside the noise floor.
    s_sm = np.convolve(s_full, np.ones(5) / 5.0, mode='same')
    lev_lo = mean_before + 0.15 * step
    lev_hi = mean_after - 0.15 * step
    if step > 0:
        o2, e2 = onset, endset
        while o2 > 0 and s_sm[o2] > lev_lo:
            o2 -= 1
        while e2 < n_full - 1 and s_sm[e2] < lev_hi:
            e2 += 1
    else:
        o2, e2 = onset, endset
        while o2 > 0 and s_sm[o2] < lev_lo:
            o2 -= 1
        while e2 < n_full - 1 and s_sm[e2] > lev_hi:
            e2 += 1
    if e2 > o2 and (o2 != onset or e2 != endset):
        # The refined inflection must still sit inside the transition
        # body — a noise bump just ahead of a real step inherits the
        # step's plateau levels without being part of the transition.
        width = e2 - o2
        margin = 0.15 * width
        if not (o2 + margin < infl < e2 - margin):
            return None
        second = _plateau_levels(float(t_full[o2]), float(t_full[e2]))
        if second is None:
            return None
        onset, endset = o2, e2
        pre_edge, post_edge, pre_mask, post_mask = second
        mean_before = float(np.mean(s_full[pre_mask]))
        mean_after = float(np.mean(s_full[post_mask]))
        step = mean_after - mean_before
        if not np.isfinite(step) or abs(step) < 1e-12:
            return None

    pre_t, pre_s = t_full[pre_mask], s_full[pre_mask]
    post_t, post_s = t_full[post_mask], s_full[post_mask]
    t_onset, t_endset = float(t_full[onset]), float(t_full[endset])

    excursion = float(max(
        np.ptp(s_full[max(0, onset - flat_width): min(n_full, endset + flat_width)]),
        np.ptp(pre_s), np.ptp(post_s), abs(step),
    ))
    if abs(step) < _TG_MIN_STEP_FRACTION * excursion:
        return None

    roughness = max(_detrended_std(pre_t, pre_s), _detrended_std(post_t, post_s))
    if abs(step) < _TG_MIN_PLATEAU_SNR * max(roughness, 1e-12):
        return None

    plateau_excursion = max(float(np.ptp(pre_s)), float(np.ptp(post_s)))
    if plateau_excursion > _TG_MAX_PLATEAU_EXCURSION * abs(step):
        return None

    s_on = float(np.mean(s_full[max(0, onset - 2): onset + 3]))
    s_en = float(np.mean(s_full[max(0, endset - 2): endset + 3]))
    transition_ratio = (s_en - s_on) / step
    if not (_TG_TRANSITION_RANGE[0] <= transition_ratio <= _TG_TRANSITION_RANGE[1]):
        return None

    far_pre = (t_full >= pre_edge - 2 * flat_t) & (t_full < pre_edge - flat_t)
    far_post = (t_full >= post_edge + flat_t) & (t_full < post_edge + 2 * flat_t)
    if int(far_pre.sum()) >= 3 and int(far_post.sum()) >= 3:
        step_far = float(np.mean(s_full[far_post])) - float(np.mean(s_full[far_pre]))
        if abs(step_far - step) > _TG_PERSISTENCE_TOL * abs(step):
            return None

    # Deep persistence (constrained searches only): each plateau level must
    # still hold at a reach beyond the transition width itself.  This rejects
    # narrow-window framings of a peak flank, where the "before" level is
    # actually the peak shoulder.  Full-range searches skip it: adjacent
    # windows already see mid-range context, and a deep reach would
    # penalise a genuine Tg followed closely by a melting peak.
    if strict_context:
        reach = max(2.0 * flat_t, t_endset - t_onset)
        deep_pre = (t_full >= pre_edge - reach - flat_t) & (t_full < pre_edge - reach)
        deep_post = (t_full >= post_edge + reach) & (t_full < post_edge + reach + flat_t)
        if int(deep_pre.sum()) >= 3:
            if abs(float(np.mean(s_full[deep_pre])) - mean_before) > _TG_PERSISTENCE_TOL * abs(step):
                return None
        if int(deep_post.sum()) >= 3:
            if abs(float(np.mean(s_full[deep_post])) - mean_after) > _TG_PERSISTENCE_TOL * abs(step):
                return None

    return onset, endset, step


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GlassTransition:
    """Characterised glass-transition event detected in a DSC curve."""

    tg_midpoint: float    # Midpoint temperature [degrees C or K]
    tg_onset: float       # Onset temperature
    tg_endset: float      # Endset temperature
    # --- PR-9 dimensional honesty -------------------------------------
    # A raw heat-flow step is NOT ΔCp until it is β-corrected, so it must
    # never live in a field named delta_cp.
    heat_flow_step: float                   # Measured step in working signal units
    delta_cp_j_g_k: Optional[float] = None  # ΔCp [J/(g·K)]; ONLY set when beta-corrected
    delta_cp_basis: str = 'legacy_unknown'
    delta_cp_withheld_reason: Optional[str] = None


@dataclass
class DSCResult:
    """
    Full set of results produced by a DSCProcessor run.

    Attributes
    ----------
    peaks:
        List of ThermalPeak objects with onset, endset, area, FWHM, and
        height filled in.
    glass_transitions:
        List of GlassTransition objects detected in the curve.
    baseline:
        The computed (and optionally corrected) baseline array.
    smoothed_signal:
        The signal after smoothing (and optional mass normalisation).
    metadata:
        Dictionary of processing parameters used (method names, kwargs, etc.).
    """

    peaks: List[ThermalPeak] = field(default_factory=list)
    glass_transitions: List[GlassTransition] = field(default_factory=list)
    baseline: Optional[np.ndarray] = None
    smoothed_signal: Optional[np.ndarray] = None
    metadata: Dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# DSCProcessor
# ---------------------------------------------------------------------------

class DSCProcessor:
    """
    Fluent-interface DSC analysis pipeline.

    Usage example
    -------------
    result = (
        DSCProcessor(temperature, signal, sample_mass=5.2, heating_rate=10)
        .smooth(method='savgol', window_length=11, polyorder=3)
        .normalize()
        .correct_baseline(method='asls')
        .find_peaks(direction='both')
        .detect_glass_transition()
        .get_result()
    )

    Alternatively, call process() for the full default pipeline in one step:

        result = DSCProcessor(temperature, signal, sample_mass=5.2).process()
    """

    def __init__(
        self,
        temperature: np.ndarray,
        signal: np.ndarray,
        sample_mass: Optional[float] = None,
        heating_rate: Optional[float] = None,
        sign_convention: Optional[str] = None,
        signal_unit: Optional[str] = None,
        heating_rate_source: Optional[str] = None,
    ) -> None:
        """
        Initialise with raw experimental data.

        Parameters
        ----------
        temperature:
            1-D array of temperatures (monotonically increasing).
        signal:
            1-D DSC heat-flow signal array (same length as temperature).
            Typical units: mW, mW/mg, or W/g.
        sample_mass:
            Sample mass in milligrams.  Required for normalisation.
        heating_rate:
            Heating rate in K/min.
        sign_convention:
            Polarity frame of the passed signal (see
            ``core.sign_convention``).  ``None`` (default) means the
            canonical frame (exo-up); ``'unknown'`` withholds
            endo/exo labels instead of assuming polarity.
        signal_unit:
            Canonical unit of the incoming signal.  Drives dimensional
            conversion (PR-9): without it, ΔCp/enthalpy in corrected
            units are withheld rather than guessed.
        heating_rate_source:
            Provenance of ``heating_rate`` — ``'user'``, ``'parsed'``,
            or ``None``/unknown.  Only ``user``/``parsed`` rates are
            trusted for β-correction.
        """
        self._temperature: np.ndarray = np.asarray(temperature, dtype=float)
        self._raw_signal: np.ndarray = np.asarray(signal, dtype=float)
        self._signal: np.ndarray = self._raw_signal.copy()
        self._sample_mass: Optional[float] = sample_mass
        self._heating_rate: Optional[float] = heating_rate
        self._heating_rate_source: Optional[str] = heating_rate_source
        self._sign_convention: SignConvention = parse_declared(sign_convention, default=CANONICAL)

        self._source_signal_unit, source_class = canonical_signal_unit(signal_unit)
        self._working_signal_unit: str = self._source_signal_unit
        self._normalization_applied: bool = False
        self._normalization_skip_reason: Optional[str] = None
        self._signal_unit_class = source_class

        # Pipeline state
        self._baseline: Optional[np.ndarray] = None
        self._baseline_applied: bool = False
        self._peaks: List[ThermalPeak] = []
        self._glass_transitions: List[GlassTransition] = []
        self._metadata: Dict = {
            'sample_mass_mg': sample_mass,
            'heating_rate_K_min': heating_rate,
            'heating_rate_source': heating_rate_source,
            'signal_convention': self._sign_convention.value,
            'source_signal_unit': self._source_signal_unit,
            'working_signal_unit': self._working_signal_unit,
            'normalization_applied': self._normalization_applied,
            'normalization_skip_reason': None,
            'steps': [],
        }

    # ------------------------------------------------------------------
    # Unit provenance (PR-9)
    # ------------------------------------------------------------------

    @property
    def source_signal_unit(self) -> str:
        """Canonical unit of the signal as imported."""
        return self._source_signal_unit

    @property
    def working_signal_unit(self) -> str:
        """Canonical unit of the current working signal."""
        return self._working_signal_unit

    @property
    def normalization_applied(self) -> bool:
        """Whether ``normalize()`` actually divided the signal by mass."""
        return self._normalization_applied

    @property
    def normalization_skip_reason(self) -> Optional[str]:
        """Why ``normalize()`` left the signal unchanged, or ``None``."""
        return self._normalization_skip_reason

    def _resolved_beta(self) -> Tuple[Optional[float], Optional[str]]:
        """Validate the heating rate for dimensional conversion."""
        return resolve_beta(self._heating_rate, self._heating_rate_source)

    def _conversion_context(self) -> Dict[str, Optional[str]]:
        """Provenance block recorded alongside every converted quantity."""
        beta, reason = self._resolved_beta()
        return {
            'source_signal_unit': self._source_signal_unit,
            'working_signal_unit': self._working_signal_unit,
            'normalization_applied': self._normalization_applied,
            'heating_rate_K_min': beta,
            'heating_rate_source': self._heating_rate_source,
            'conversion_withheld_reason': reason,
        }

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def smooth(self, method: str = 'savgol', **kwargs) -> 'DSCProcessor':
        """
        Apply smoothing to the current signal in-place.

        Parameters
        ----------
        method:
            Smoothing method passed to core.preprocessing.smooth_signal.
            Common values: 'savgol', 'gaussian', 'moving_average'.
        **kwargs:
            Extra keyword arguments forwarded to smooth_signal.

        Returns
        -------
        self, for method chaining.
        """
        self._signal = smooth_signal(self._signal, method=method, **kwargs)
        self._metadata['steps'].append({'step': 'smooth', 'method': method, **kwargs})
        return self

    def normalize(self, force: bool = False) -> 'DSCProcessor':
        """
        Normalise the signal by sample mass (mW -> mW/mg or W -> W/g).

        Does nothing and emits a warning if sample_mass was not provided.
        Skips silently when the source signal is already in specific-power
        units unless ``force=True`` is passed as an explicit opt-in for a
        signal whose specific-unit label is believed to be wrong.

        Parameters
        ----------
        force:
            Opt-in re-normalization override.  When True, an
            already-specific source unit is treated as mislabeled raw power
            and divided by sample mass anyway.  Never divides a signal
            that was already normalized this session, and still requires a
            valid sample mass.

        Returns
        -------
        self, for method chaining.
        """
        # resolve_working_unit reads the *current* working unit and flag,
        # so a second normalize() can never divide by mass twice.
        working_unit, applied, reason = resolve_working_unit(
            self._source_signal_unit,
            self._sample_mass,
            True,
            working_unit=self._working_signal_unit,
            normalization_applied=self._normalization_applied,
            force_renormalize=force,
        )

        if not applied:
            # An already-specific signal needs no mass and no warning; for
            # anything else the reason normalization did not happen is the
            # missing mass, whatever the unit provenance says.
            already_specific = reason == "already_specific_power"
            if not already_specific and (
                reason in {"sample_mass_missing", "sample_mass_invalid"}
                or self._sample_mass is None
            ):
                warnings.warn(
                    "normalize() called but sample_mass was not provided.  "
                    "Skipping normalisation.",
                    RuntimeWarning,
                    stacklevel=2,
                )
            self._working_signal_unit = working_unit
            self._normalization_skip_reason = reason
            self._metadata['working_signal_unit'] = working_unit
            self._metadata['normalization_applied'] = False
            self._metadata['normalization_skip_reason'] = reason
            return self

        forced = force and self._signal_unit_class is UnitClass.SPECIFIC_POWER
        self._signal = normalize_by_mass(self._signal, sample_mass_mg=self._sample_mass)
        self._working_signal_unit = working_unit
        self._normalization_applied = True
        self._normalization_skip_reason = None
        self._metadata['working_signal_unit'] = working_unit
        self._metadata['normalization_applied'] = True
        self._metadata['normalization_skip_reason'] = None
        step = {
            'step': 'normalize',
            'mass_mg': self._sample_mass,
            'from_unit': self._source_signal_unit,
            'to_unit': working_unit,
        }
        if forced:
            step['forced'] = True
            step['overrode'] = 'already_specific_power'
        self._metadata['steps'].append(step)
        return self

    def correct_baseline(self, method: str = 'asls', **kwargs) -> 'DSCProcessor':
        """
        Compute and subtract a baseline from the current signal.

        The raw baseline array is stored and exposed in DSCResult.baseline.

        Parameters
        ----------
        method:
            Baseline method passed to core.baseline.correct_baseline.
            Common values: 'asls', 'linear', 'polynomial', 'rubberband'.
        **kwargs:
            Extra keyword arguments forwarded to correct_baseline.

        Returns
        -------
        self, for method chaining.
        """
        corrected, baseline = correct_baseline(
            self._temperature, self._signal, method=method, **kwargs
        )
        self._baseline = baseline
        self._signal = corrected
        self._baseline_applied = True
        self._metadata['steps'].append(
            {'step': 'correct_baseline', 'method': method, **kwargs}
        )
        return self

    def find_peaks(self, **kwargs) -> 'DSCProcessor':
        """
        Detect and characterise peaks in the current signal.

        Parameters
        ----------
        **kwargs:
            Keyword arguments forwarded to find_thermal_peaks (prominence,
            height, distance, width, direction).

        Returns
        -------
        self, for method chaining.
        """
        raw_peaks = find_thermal_peaks(
            self._temperature,
            self._signal,
            sign_convention=self._sign_convention,
            **kwargs,
        )
        # self._signal is already baseline-corrected when correct_baseline()
        # ran; passing the raw baseline here would subtract it a second time
        # and corrupt area, height, and FWHM alike.
        baseline_for_char = (
            np.zeros_like(self._signal) if self._baseline_applied else None
        )
        self._peaks = characterize_peaks(
            self._temperature,
            self._signal,
            raw_peaks,
            baseline=baseline_for_char,
        )
        self._apply_peak_enthalpies()
        self._metadata['steps'].append({'step': 'find_peaks', **kwargs})
        return self

    def _apply_peak_enthalpies(self) -> None:
        """Attach β-aware enthalpy J/g to every characterised peak.

        Reads the working unit only — never the sample mass — so a second
        division is impossible.  Withholds when provenance is missing.
        """
        beta, reason = self._resolved_beta()
        for peak in self._peaks:
            conversion = peak_area_to_enthalpy(
                peak.area,
                working_signal_unit=self._working_signal_unit,
                beta_k_min=beta,
            )
            peak.enthalpy_j_g = conversion.value
            peak.enthalpy_basis = conversion.basis
            # Root cause first: an unusable heating rate explains the
            # withholding better than the resulting missing value.
            peak.enthalpy_withheld_reason = (
                reason or conversion.withheld_reason
            )

    def detect_glass_transition(
        self,
        region: Optional[Tuple[float, float]] = None,
    ) -> 'DSCProcessor':
        """
        Detect glass transitions (Tg) from the step change in the DSC baseline.

        Algorithm
        ---------
        1. If a temperature region (T_low, T_high) is given, restrict analysis
           to that window; otherwise use the full temperature range.
        2. Compute the first derivative of the (smoothed/corrected) signal and
           lightly smooth its magnitude.
        3. Every local maximum of smoothed |d1| above a small floor is a Tg
           *candidate* - the inflection of a genuine baseline step sits at a
           |d1| maximum, while the largest |d2| feature alone is not
           evidence of a step (sharp peaks and decomposition spikes have
           higher curvature than any Tg).
        4. Each candidate must pass the morphology gates in
           ``_tg_step_evidence``: bounded flat plateaus on both sides, a
           persistent plateau level shift that dominates the local
           excursion, and an in-transition signal change consistent with
           that shift.  Candidates that fail - peaks, edge artefacts,
           ramp-like features - are not Tg; a user-supplied region does not
           bypass the gates.
        5. Among passing candidates the sharpest inflection (largest
           smoothed |d1|) wins.  Onset/endset are where smoothed |d1| falls
           to a fraction of the candidate peak or to the noise level.
        6. Compute delta_cp from the difference in the mean signal level in
           flat regions just outside [onset, endset].

        Parameters
        ----------
        region:
            Optional (T_start, T_end) tuple to restrict the search.

        Returns
        -------
        self, for method chaining.
        """
        temperature = self._temperature
        signal = self._signal
        n = len(temperature)

        # --- restrict to region if requested ---------------------------------
        if region is not None:
            t_lo, t_hi = float(region[0]), float(region[1])
            mask = (temperature >= t_lo) & (temperature <= t_hi)
            if mask.sum() < 10:
                warnings.warn(
                    f"detect_glass_transition: fewer than 10 points in region "
                    f"[{t_lo}, {t_hi}].  Skipping Tg detection.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                return self
            idxs = np.where(mask)[0]
            t_work = temperature[idxs]
            s_work = signal[idxs]
            offset = int(idxs[0])
        else:
            t_work = temperature
            s_work = signal
            offset = 0

        m = len(t_work)
        if m < 10:
            return self

        # --- smoothed |d1|: step inflections are its local maxima -------------
        d1_abs = np.abs(np.gradient(s_work, t_work))
        smooth_w = max(3, int(round(m * 0.005)) | 1)
        kernel = np.ones(smooth_w) / smooth_w
        d1_smooth = np.convolve(d1_abs, kernel, mode='same')

        # Candidate floor is noise-relative, not global-max-relative: a sharp
        # unrelated peak elsewhere must not price a legitimate small step out
        # of candidacy.  Median + 1.5*MAD is a robust "above noise" bar that
        # ignores large outlier excursions.
        noise_level = float(np.median(d1_smooth))
        noise_mad = 1.4826 * float(np.median(np.abs(d1_smooth - noise_level)))
        cand_floor = noise_level + _TG_CANDIDATE_MAD * noise_mad
        flat_width = max(5, m // 10)

        # Candidate *selection* stays region-restricted, but morphology is
        # judged on full-signal context: a constrained window must not be
        # able to hide what lies just outside it.
        if region is not None:
            d1_ctx = np.convolve(
                np.abs(np.gradient(signal, temperature)),
                np.ones(max(3, int(round(n * 0.005)) | 1))
                / max(3, int(round(n * 0.005)) | 1),
                mode='same',
            )
            noise_ctx = float(np.median(d1_ctx))
        else:
            d1_ctx, noise_ctx = d1_smooth, noise_level

        best = None  # (d1_smooth value, infl, onset, endset, step)
        for infl in range(1, m - 1):
            if d1_smooth[infl] < cand_floor:
                continue
            if not (
                d1_smooth[infl] >= d1_smooth[infl - 1]
                and d1_smooth[infl] > d1_smooth[infl + 1]
            ):
                continue
            evidence = _tg_step_evidence(
                temperature, signal,
                infl + offset, d1_ctx, noise_ctx, flat_width,
                strict_context=region is not None,
            )
            if evidence is None:
                continue
            if best is None or d1_smooth[infl] > best[0]:
                best = (float(d1_smooth[infl]), infl) + evidence

        if best is None:
            # No candidate showed baseline-step morphology.  Reporting no Tg
            # is the honest outcome - do not fabricate one from curvature.
            self._metadata['steps'].append(
                {
                    'step': 'detect_glass_transition',
                    'region': region,
                    'tg_midpoint': None,
                    'outcome': 'no_step_morphology',
                }
            )
            return self

        _, infl_local, onset, endset, heat_flow_step = best
        # onset/endset are full-signal indices (the morphology gates run on
        # full context); infl_local indexes the working arrays.
        tg_onset = float(temperature[onset])
        tg_endset = float(temperature[endset])
        tg_midpoint = float(t_work[infl_local])

        # β-corrected ΔCp only when the working unit and β are trustworthy.
        beta, beta_reason = self._resolved_beta()
        conversion = heat_flow_step_to_delta_cp(
            heat_flow_step,
            working_signal_unit=self._working_signal_unit,
            beta_k_min=beta,
        )

        tg = GlassTransition(
            tg_midpoint=tg_midpoint,
            tg_onset=tg_onset,
            tg_endset=tg_endset,
            heat_flow_step=heat_flow_step,
            delta_cp_j_g_k=conversion.value,
            delta_cp_basis=conversion.basis,
            delta_cp_withheld_reason=beta_reason or conversion.withheld_reason,
        )
        self._glass_transitions.append(tg)
        self._metadata['steps'].append(
            {
                'step': 'detect_glass_transition',
                'region': region,
                'tg_midpoint': tg_midpoint,
            }
        )
        return self

    # ------------------------------------------------------------------
    # Terminal methods
    # ------------------------------------------------------------------

    def process(
        self,
        smooth_method: str = 'savgol',
        baseline_method: str = 'asls',
        *,
        normalize_force: bool = False,
        **kwargs,
    ) -> DSCResult:
        """
        Execute the full default DSC pipeline in a single call.

        Pipeline order
        --------------
        1. smooth   - using smooth_method (default 'savgol')
        2. normalize - skipped silently if sample_mass is None or the
           source signal is already specific power (unless normalize_force)
        3. correct_baseline - using baseline_method (default 'asls')
        4. find_peaks - direction='both' unless overridden in kwargs
        5. detect_glass_transition - full temperature range

        Parameters
        ----------
        smooth_method:
            Smoothing algorithm passed to smooth().
        baseline_method:
            Baseline algorithm passed to correct_baseline().
        normalize_force:
            Opt-in re-normalization override forwarded to normalize()
            (see its docstring).  Off by default: an already-specific
            signal is never silently divided by mass.
        **kwargs:
            Optional overrides forwarded to find_peaks()
            (e.g. prominence, distance, direction).

        Returns
        -------
        DSCResult with all fields populated.
        """
        return (
            self
            .smooth(method=smooth_method)
            .normalize(force=normalize_force)
            .correct_baseline(method=baseline_method)
            .find_peaks(**kwargs)
            .detect_glass_transition()
            .get_result()
        )

    def get_result(self) -> DSCResult:
        """
        Package the current pipeline state into a DSCResult and return it.

        Returns
        -------
        DSCResult containing peaks, glass_transitions, baseline,
        smoothed_signal, and metadata.
        """
        return DSCResult(
            peaks=list(self._peaks),
            glass_transitions=list(self._glass_transitions),
            baseline=self._baseline.copy() if self._baseline is not None else None,
            smoothed_signal=self._signal.copy(),
            metadata=dict(self._metadata),
        )
