"""
dta_processor.py
----------------
Differential Thermal Analysis (DTA) processing pipeline.

DTA measures the temperature difference (delta-T) between a sample and an
inert reference material as both are subjected to a controlled temperature
program.  Exothermic reactions produce a positive delta-T signal (sample
warmer than reference); endothermic reactions produce a negative delta-T
signal.

Unlike DSC, the raw DTA signal is expressed as a temperature difference (degC
or microvolts from a thermocouple differential) and is *not* calibrated to
absolute heat-flow units (mW or J/g).  Qualitative peak identification is
therefore the main goal of DTA analysis.

Pipeline
--------
    raw data
        -> smooth()             : noise reduction (Savitzky-Golay by default)
        -> correct_baseline()   : remove instrumental drift / curvature
        -> find_peaks()         : locate thermal events
        -> DTAResult            : structured output dataclass

Usage example
-------------
    import numpy as np
    from core.dta_processor import DTAProcessor

    temperature = np.linspace(25, 1000, 3000)
    delta_T = ...   # experimental DTA signal

    result = DTAProcessor(temperature, delta_T).process()
    for peak in result.peaks:
        print(peak.peak_temperature, peak.direction)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional

from core.preprocessing import smooth_signal
from core.baseline import correct_baseline
from core.peak_analysis import find_thermal_peaks, ThermalPeak
from core.sign_convention import CANONICAL, SignConvention, direction_tag_from_label, parse_declared


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DTAResult:
    """
    Full results of a DTA processing run.

    Attributes
    ----------
    peaks : list of ThermalPeak
        Detected thermal events (both exothermic and endothermic), ordered
        by peak temperature.  Each :class:`~core.peak_analysis.ThermalPeak`
        carries temperature, height, area, and a ``direction`` flag
        (``'exo'`` or ``'endo'``).
    baseline : np.ndarray
        Estimated baseline signal as returned by
        :func:`~core.baseline.correct_baseline`.  Same length as the
        input temperature array.
    smoothed_signal : np.ndarray
        DTA delta-T signal after smoothing and baseline correction.
    metadata : dict
        Arbitrary key-value pairs (sample name, heating rate, atmosphere, …)
        passed through from the processor.
    """

    peaks: List[ThermalPeak]
    baseline: np.ndarray
    smoothed_signal: np.ndarray
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# DTAProcessor
# ---------------------------------------------------------------------------

class DTAProcessor:
    """
    Fluent-interface processing pipeline for DTA data.

    Each method returns ``self`` so calls can be chained:

        result = DTAProcessor(T, dT).smooth().correct_baseline().find_peaks().get_result()

    Or use the convenience :meth:`process` method which runs the full
    pipeline in one call.

    Parameters
    ----------
    temperature : array-like
        Temperature axis in degrees Celsius (or Kelvin).  Must be
        monotonically increasing and match the length of ``signal``.
    signal : array-like
        Raw DTA differential-temperature signal (delta-T, in degC or
        microvolts).  Positive values conventionally indicate exothermic
        events; negative values indicate endothermic events (instrument
        and convention dependent – verify with your instrument manual).
    metadata : dict, optional
        Arbitrary metadata forwarded into :class:`DTAResult`.
    """

    def __init__(
        self,
        temperature,
        signal,
        metadata: Optional[dict] = None,
        sign_convention: Optional[str] = None,
    ):
        self._temperature = np.asarray(temperature, dtype=float)
        self._raw_signal = np.asarray(signal, dtype=float)
        self._sign_convention: SignConvention = parse_declared(sign_convention, default=CANONICAL)

        if self._temperature.shape != self._raw_signal.shape:
            raise ValueError(
                f"temperature and signal must have the same length, "
                f"got {len(self._temperature)} and {len(self._raw_signal)}."
            )

        self._metadata = metadata or {}

        # Internal state populated by each pipeline stage
        self._smoothed: Optional[np.ndarray] = None
        self._baseline: Optional[np.ndarray] = None
        self._baseline_corrected: Optional[np.ndarray] = None
        self._peaks: Optional[List[ThermalPeak]] = None
        self._result: Optional[DTAResult] = None

    # ------------------------------------------------------------------
    # Pipeline stages
    # ------------------------------------------------------------------

    def smooth(self, method: str = "savgol", **kwargs) -> "DTAProcessor":
        """
        Smooth the raw DTA signal.

        DTA signals are typically noisier than DSC because the temperature-
        difference measurement is more sensitive to vibration and furnace
        fluctuations.  A Savitzky-Golay filter with a moderate window is a
        good starting point.

        Parameters
        ----------
        method : str, default 'savgol'
            Smoothing algorithm forwarded to
            :func:`~core.preprocessing.smooth_signal`.
            Options: ``'savgol'``, ``'moving_average'``, ``'gaussian'``.
        **kwargs
            Additional keyword arguments forwarded to the smoothing function.
            Savitzky-Golay defaults: ``window_length=11``, ``polyorder=3``.
            Gaussian default: ``sigma=2``.

        Returns
        -------
        DTAProcessor
            ``self`` for method chaining.
        """
        source = (
            self._baseline_corrected
            if self._baseline_corrected is not None
            else self._raw_signal
        )
        self._smoothed = smooth_signal(source, method=method, **kwargs)
        return self

    def correct_baseline(self, method: str = "asls", **kwargs) -> "DTAProcessor":
        """
        Remove the slowly varying instrumental baseline from the DTA signal.

        DTA baselines exhibit curvature caused by:
          - Asymmetric heat capacities of sample vs. reference.
          - Temperature-dependent thermocouple sensitivity.
          - Furnace geometry drift.

        This method applies baseline correction *before* smoothing when called
        in the recommended order (correct_baseline -> smooth -> find_peaks).
        If :meth:`smooth` has already been called, the smoothed signal is
        corrected instead.

        Parameters
        ----------
        method : str, default 'asls'
            Baseline estimation algorithm forwarded to
            :func:`~core.baseline.correct_baseline`.
            Common options: ``'asls'`` (asymmetric least squares),
            ``'polynomial'``, ``'linear'``.
        **kwargs
            Algorithm-specific keyword arguments (e.g., ``lam``, ``p`` for
            AsLS; ``degree`` for polynomial).

        Returns
        -------
        DTAProcessor
            ``self`` for method chaining.
        """
        source = (
            self._smoothed
            if self._smoothed is not None
            else self._raw_signal
        )

        corrected, baseline = correct_baseline(
            self._temperature,
            source,
            method=method,
            **kwargs,
        )

        self._baseline = baseline
        self._baseline_corrected = corrected

        # If smooth has already been applied, re-smooth the corrected signal
        # so that self._smoothed reflects the baseline-corrected data.
        if self._smoothed is not None:
            self._smoothed = corrected

        return self

    def find_peaks(
        self,
        prominence: Optional[float] = None,
        detect_endothermic: bool = True,
        detect_exothermic: bool = True,
        min_peak_height: Optional[float] = None,
        **kwargs,
    ) -> "DTAProcessor":
        """
        Locate thermal events (endothermic and exothermic peaks) in the DTA
        signal.

        Unlike DSC processing, no enthalpy calibration is performed.  The
        peak area in the DTA signal is proportional to the enthalpy change
        but the proportionality constant is instrument- and temperature-
        dependent.

        Algorithm
        ---------
        1. Use the baseline-corrected and smoothed signal (falling back to
           the raw signal if neither pre-processing step has been applied).
           Both passes operate on the SAME working signal — no inverted
           re-find — so each event is detected exactly once (PR-8 fix for
           the historical duplicate/contradictory-tag behaviour).
        2. Detect exothermic events with a convention-aware search
           direction: in the canonical exo-up frame they point up
           (``direction='up'``); in an endo-up frame they point down
           (``direction='down'``).
        3. Detect endothermic events with the mirrored search direction
           for the recorded convention.
        4. Tag each peak with a ``direction`` attribute derived from the
           SAME canon label as ``peak_type`` (``'exo'``/``'endo'``), so the
           two fields cannot disagree; for ``'unknown'`` polarity frames
           every event is tagged ``'unknown'`` instead of being silently
           attributed.  Merge both lists, sorting by temperature.

        Parameters
        ----------
        prominence : float, optional
            Minimum peak prominence in delta-T units.  If ``None``, an
            adaptive default of 5 % of the signal's peak-to-peak range is
            used.
        detect_endothermic : bool, default True
            Whether to detect endothermic events.  The search direction
            follows the recorded sign convention (endothermic peaks point
            down in the canonical exo-up frame, up in an endo-up frame).
        detect_exothermic : bool, default True
            Whether to detect exothermic events.  The search direction
            follows the recorded sign convention.
        min_peak_height : float, optional
            Absolute minimum peak height (positive value for exo, absolute
            value for endo).  Peaks smaller than this are filtered out.
        **kwargs
            Additional keyword arguments forwarded to
            :func:`~core.peak_analysis.find_thermal_peaks`
            (e.g., ``min_width``, ``rel_height``).

        Returns
        -------
        DTAProcessor
            ``self`` for method chaining.
        """
        # Determine which signal to use for peak finding
        if self._baseline_corrected is not None:
            working_signal = self._baseline_corrected
        elif self._smoothed is not None:
            working_signal = self._smoothed
        else:
            working_signal = self._raw_signal

        # Adaptive prominence
        signal_range = working_signal.max() - working_signal.min()
        if prominence is None:
            prominence = max(0.05 * signal_range, 1e-6)

        all_peaks: List[ThermalPeak] = []

        # PR-8: event-family passes are convention-aware.  In the canonical
        # exo-up frame exothermic events point up and endothermic events
        # point down; in an endo-up frame the directions mirror.  UNKNOWN
        # polarity has no physical mapping, so the passes stay mechanical
        # sign-direction scans with tags withheld.
        if self._sign_convention is SignConvention.ENDO_UP:
            exo_search_direction = 'down'
            endo_search_direction = 'up'
        else:  # canonical exo-up frame, or UNKNOWN polarity (mechanical scan)
            exo_search_direction = 'up'
            endo_search_direction = 'down'

        # --- Exothermic-event pass (convention-aware search direction) ---
        if detect_exothermic:
            exo_peaks: List[ThermalPeak] = find_thermal_peaks(
                self._temperature,
                working_signal,
                prominence=prominence,
                direction=exo_search_direction,
                sign_convention=self._sign_convention,
                **kwargs,
            )
            for peak in exo_peaks:
                if min_peak_height is not None and peak.height < min_peak_height:
                    continue
                # Tag derived from the same canon label as peak_type, so
                # direction and peak_type cannot disagree.
                _tag_peak_direction(peak, direction_tag_from_label(peak.peak_type))
                all_peaks.append(peak)

        # --- Endothermic-event pass (mirrored search direction) ---
        if detect_endothermic:
            endo_peaks: List[ThermalPeak] = find_thermal_peaks(
                self._temperature,
                working_signal,
                prominence=prominence,
                direction=endo_search_direction,
                sign_convention=self._sign_convention,
                **kwargs,
            )
            for peak in endo_peaks:
                if min_peak_height is not None and peak.height < min_peak_height:
                    continue
                _tag_peak_direction(peak, direction_tag_from_label(peak.peak_type))
                all_peaks.append(peak)

        # Sort by temperature (ascending)
        all_peaks.sort(key=lambda p: p.peak_temperature)
        self._peaks = all_peaks
        return self

    def process(
        self,
        smooth_method: str = "savgol",
        baseline_method: str = "asls",
        prominence: Optional[float] = None,
        detect_endothermic: bool = True,
        detect_exothermic: bool = True,
        **kwargs,
    ) -> DTAResult:
        """
        Run the complete DTA processing pipeline in a single call.

        Order of operations:
          1. :meth:`smooth`             - noise reduction
          2. :meth:`correct_baseline`   - baseline subtraction
          3. :meth:`find_peaks`         - thermal event detection

        Parameters
        ----------
        smooth_method : str, default 'savgol'
            Smoothing algorithm forwarded to :meth:`smooth`.
        baseline_method : str, default 'asls'
            Baseline algorithm forwarded to :meth:`correct_baseline`.
        prominence : float, optional
            Peak prominence threshold forwarded to :meth:`find_peaks`.
        detect_endothermic : bool, default True
            Whether to detect endothermic peaks.
        detect_exothermic : bool, default True
            Whether to detect exothermic peaks.
        **kwargs
            Additional keyword arguments forwarded to each stage.  Keys that
            are relevant only to a specific stage (e.g., ``window_length``,
            ``polyorder``, ``lam``, ``p``) are passed transparently.

        Returns
        -------
        DTAResult
            Fully populated result dataclass.
        """
        self.smooth(method=smooth_method, **kwargs)
        self.correct_baseline(method=baseline_method, **kwargs)
        self.find_peaks(
            prominence=prominence,
            detect_endothermic=detect_endothermic,
            detect_exothermic=detect_exothermic,
            **kwargs,
        )
        return self.get_result()

    def get_result(self) -> DTAResult:
        """
        Assemble and return the :class:`DTAResult` from the current pipeline
        state.

        Falls back gracefully when optional stages have been skipped:
          - If baseline correction was skipped, ``baseline`` is a zero array.
          - If smoothing was skipped, ``smoothed_signal`` is the raw signal.

        Returns
        -------
        DTAResult

        Raises
        ------
        RuntimeError
            If :meth:`find_peaks` has not been called yet.
        """
        if self._peaks is None:
            raise RuntimeError(
                "Peak detection has not been run.  Call process() or the individual "
                "stage methods (smooth -> correct_baseline -> find_peaks) first."
            )

        # Graceful fallbacks for skipped stages
        smoothed = (
            self._smoothed
            if self._smoothed is not None
            else self._raw_signal.copy()
        )
        baseline = (
            self._baseline
            if self._baseline is not None
            else np.zeros_like(self._temperature)
        )

        self._result = DTAResult(
            peaks=self._peaks,
            baseline=baseline,
            smoothed_signal=smoothed,
            metadata=self._metadata,
        )
        return self._result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tag_peak_direction(peak: ThermalPeak, direction: str) -> None:
    """
    Attach a ``direction`` attribute to a ThermalPeak instance.

    :class:`~core.peak_analysis.ThermalPeak` may not have a ``direction``
    field by default.  This helper attaches it dynamically so that DTA
    callers can distinguish exothermic from endothermic events without
    requiring a subclass.

    Parameters
    ----------
    peak : ThermalPeak
        The peak object to annotate.
    direction : str
        Either ``'exo'`` or ``'endo'``.
    """
    try:
        object.__setattr__(peak, "direction", direction)
    except (AttributeError, TypeError):
        # Dataclass with frozen=True or a class that doesn't support
        # __setattr__ – store on __dict__ directly as a best-effort approach.
        try:
            peak.__dict__["direction"] = direction
        except AttributeError:
            pass  # Silently skip if truly immutable; caller can infer direction from sign.
