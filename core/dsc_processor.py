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
    canonical_signal_unit,
    heat_flow_step_to_delta_cp,
    peak_area_to_enthalpy,
    resolve_beta,
    resolve_working_unit,
)


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

    def normalize(self) -> 'DSCProcessor':
        """
        Normalise the signal by sample mass (mW -> mW/mg or W -> W/g).

        Does nothing and emits a warning if sample_mass was not provided.

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
            self._metadata['working_signal_unit'] = working_unit
            self._metadata['normalization_applied'] = False
            return self

        self._signal = normalize_by_mass(self._signal, sample_mass_mg=self._sample_mass)
        self._working_signal_unit = working_unit
        self._normalization_applied = True
        self._metadata['working_signal_unit'] = working_unit
        self._metadata['normalization_applied'] = True
        self._metadata['steps'].append(
            {
                'step': 'normalize',
                'mass_mg': self._sample_mass,
                'from_unit': self._source_signal_unit,
                'to_unit': working_unit,
            }
        )
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
        2. Compute the second derivative of the (smoothed/corrected) signal.
        3. Locate the index where the magnitude of the second derivative is
           maximum - this is the inflection of the step.
        4. Define onset and endset as the points on either side of the
           inflection where the first derivative drops to 10 % of its
           maximum magnitude.
        5. Compute delta_cp from the difference in the mean signal level in
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

        # --- first and second derivatives ------------------------------------
        d1 = np.gradient(s_work, t_work)
        d2 = np.gradient(d1, t_work)

        # Smooth derivatives lightly with a simple moving average (3-point)
        kernel = np.ones(3) / 3.0
        d2_smooth = np.convolve(np.abs(d2), kernel, mode='same')

        # --- locate inflection (max |d2|) ------------------------------------
        infl_local = int(np.argmax(d2_smooth))

        # --- onset: where |d1| drops to 10 % of max on the left -------------
        d1_abs = np.abs(d1)
        d1_max = float(np.max(d1_abs[max(0, infl_local - m // 4): infl_local + 1]))
        threshold = 0.10 * d1_max if d1_max > 0 else 0.0

        onset_local = infl_local
        for i in range(infl_local, -1, -1):
            if d1_abs[i] <= threshold:
                onset_local = i
                break

        endset_local = infl_local
        for i in range(infl_local, m):
            if d1_abs[i] <= threshold:
                endset_local = i
                break

        tg_onset = float(t_work[onset_local])
        tg_endset = float(t_work[endset_local])
        tg_midpoint = float(t_work[infl_local])

        # --- heat-flow step from flat regions outside [onset, endset] -------
        flat_width = max(5, m // 10)

        bl_start = max(0, onset_local - flat_width)
        bl_end = onset_local
        ar_start = endset_local
        ar_end = min(m - 1, endset_local + flat_width)

        if bl_end > bl_start and ar_end > ar_start:
            mean_before = float(np.mean(s_work[bl_start:bl_end]))
            mean_after = float(np.mean(s_work[ar_start:ar_end]))
            heat_flow_step = mean_after - mean_before
        else:
            heat_flow_step = 0.0

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
        **kwargs,
    ) -> DSCResult:
        """
        Execute the full default DSC pipeline in a single call.

        Pipeline order
        --------------
        1. smooth   - using smooth_method (default 'savgol')
        2. normalize - skipped silently if sample_mass is None
        3. correct_baseline - using baseline_method (default 'asls')
        4. find_peaks - direction='both' unless overridden in kwargs
        5. detect_glass_transition - full temperature range

        Parameters
        ----------
        smooth_method:
            Smoothing algorithm passed to smooth().
        baseline_method:
            Baseline algorithm passed to correct_baseline().
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
            .normalize()
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
