"""Deterministic synthetic measurement files for the test suite.

Replaces the retired ``sample_data/`` and ``test_data/`` directories. Every
file is generated with a fixed seed and materialized under
``pytest_temp/synthetic_samples/`` (already covered by ``.gitignore``), so
the suite no longer depends on tracked dataset files.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "pytest_temp" / "synthetic_samples"


def _gaussian(x: np.ndarray, center: float, sigma: float, amplitude: float) -> np.ndarray:
    return amplitude * np.exp(-0.5 * ((x - center) / sigma) ** 2)


def _sigmoid(x: np.ndarray, center: float, width: float) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-(x - center) / width))


def _write_csv(name: str, frame: pd.DataFrame, *, sep: str = ",") -> Path:
    _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    path = _OUTPUT_ROOT / name
    content = frame.to_csv(index=False, sep=sep)
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8", newline="")
    return path


def _dsc_polymer_melting_frame() -> pd.DataFrame:
    """Polymer-like DSC trace: Tg step, cold crystallization, melting endotherm."""
    rng = np.random.default_rng(20240914)
    temperature = np.arange(30.0, 300.01, 0.5)
    baseline = -0.42 + 0.00035 * (temperature - 30.0)
    tg_step = 0.10 * _sigmoid(temperature, 78.0, 3.5)
    cold_crystallization = -_gaussian(temperature, 130.0, 7.0, 0.55)
    melting = _gaussian(temperature, 250.0, 6.0, 0.9)
    signal = baseline + tg_step + cold_crystallization + melting
    signal += rng.normal(0.0, 0.008, len(temperature))
    return pd.DataFrame(
        {
            "Temperature (°C)": temperature,
            "Time (min)": np.round((temperature - 30.0) / 10.0, 4),
            "Heat Flow (mW/mg)": np.round(signal, 5),
        }
    )


def _tga_calcium_oxalate_frame() -> pd.DataFrame:
    """Three-step decomposition trace (oxalate-like) in mass percent."""
    rng = np.random.default_rng(20240915)
    temperature = np.arange(30.0, 850.01, 0.5)
    mass = (
        100.0
        - 12.0 * _sigmoid(temperature, 200.0, 6.0)
        - 19.0 * _sigmoid(temperature, 480.0, 9.0)
        - 45.0 * _sigmoid(temperature, 700.0, 22.0)
    )
    mass += rng.normal(0.0, 0.05, len(temperature))
    return pd.DataFrame(
        {
            "Temperature (°C)": temperature,
            "Time (min)": np.round((temperature - 30.0) / 10.0, 4),
            "Mass (%)": np.round(mass, 3),
        }
    )


def _dta_events_frame(variant: str) -> pd.DataFrame:
    """DTA trace with strong exo events plus sub-threshold shoulder ripples.

    The ``5c`` variant carries six resolved exothermic events; the ``10c``
    variant carries five.  Small dips (~0.004 a.u.) sit between events to
    exercise the automatic detection floor: they must not be reported.
    """
    rng = np.random.default_rng(20240916 if variant == "5c" else 20240917)
    temperature = np.arange(27.0, 620.01, 0.25)
    baseline = -0.21 + 0.00004 * (temperature - 27.0)
    if variant == "5c":
        centers = [80.0, 150.0, 240.0, 330.0, 430.0, 520.0]
        amplitudes = [0.10, 0.06, 0.12, 0.05, 0.09, 0.04]
        sigmas = [5.0, 4.0, 6.0, 5.0, 7.0, 5.0]
    else:
        centers = [90.0, 170.0, 280.0, 400.0, 500.0]
        amplitudes = [0.12, 0.07, 0.15, 0.08, 0.05]
        sigmas = [5.0, 4.0, 6.0, 6.0, 5.0]
    signal = baseline.copy()
    for center, amplitude, sigma in zip(centers, amplitudes, sigmas):
        signal += _gaussian(temperature, center, sigma, amplitude)
    for ripple_center in (115.0, 285.0, 470.0):
        signal -= _gaussian(temperature, ripple_center, 3.0, 0.004)
    signal += rng.normal(0.0, 0.0008, len(temperature))
    return pd.DataFrame({"temperature": temperature, "signal": np.round(signal, 6)})


def _ftir_absorbance_frame() -> pd.DataFrame:
    """FTIR absorbance-like spectrum over 400-4000 cm^-1."""
    rng = np.random.default_rng(20240918)
    axis = np.arange(400.0, 4000.01, 2.0)
    signal = 0.05 + 0.00001 * (axis - 400.0)
    for center, amplitude, sigma in (
        (1050.0, 0.8, 15.0),
        (1450.0, 0.35, 8.0),
        (1600.0, 0.5, 10.0),
        (2900.0, 0.3, 12.0),
        (3400.0, 0.4, 60.0),
    ):
        signal += _gaussian(axis, center, sigma, amplitude)
    signal += rng.normal(0.0, 0.003, len(axis))
    return pd.DataFrame({"temperature": axis, "signal": np.round(signal, 5)})


def _raman_bands_frame() -> pd.DataFrame:
    """Raman shift spectrum with D/G/2D-like bands over 100-3200 cm^-1."""
    rng = np.random.default_rng(20240919)
    axis = np.arange(100.0, 3200.01, 2.0)
    signal = 0.02 + 0.000008 * (axis - 100.0)
    for center, amplitude, sigma in (
        (1350.0, 0.6, 10.0),
        (1580.0, 1.0, 8.0),
        (2700.0, 0.4, 12.0),
    ):
        signal += _gaussian(axis, center, sigma, amplitude)
    signal += rng.normal(0.0, 0.002, len(axis))
    return pd.DataFrame({"temperature": axis, "signal": np.round(signal, 5)})


def _xrd_powder_frame() -> pd.DataFrame:
    """Powder XRD pattern (counts vs 2-theta) over 5-90 degrees."""
    rng = np.random.default_rng(20240920)
    axis = np.arange(5.0, 90.001, 0.03)
    signal = 800.0 + 2.0 * (axis - 5.0)
    for center, amplitude, sigma in (
        (20.8, 2500.0, 0.10),
        (26.6, 9000.0, 0.08),
        (36.5, 1800.0, 0.12),
        (39.4, 1200.0, 0.10),
        (45.8, 2200.0, 0.10),
        (50.1, 900.0, 0.12),
        (60.0, 1400.0, 0.12),
        (68.1, 1000.0, 0.12),
    ):
        signal += _gaussian(axis, center, sigma, amplitude)
    signal += rng.normal(0.0, 25.0, len(axis))
    return pd.DataFrame({"temperature": np.round(axis, 4), "signal": np.round(signal, 1)})


_SAMPLE_BUILDERS = {
    "DSC": ("synthetic_dsc_polymer_melting.csv", _dsc_polymer_melting_frame),
    "TGA": ("synthetic_tga_calcium_oxalate.csv", _tga_calcium_oxalate_frame),
    "DTA": ("synthetic_dta_events_5c.csv", lambda: _dta_events_frame("5c")),
    "FTIR": ("synthetic_ftir_absorbance.csv", _ftir_absorbance_frame),
    "RAMAN": ("synthetic_raman_bands.csv", _raman_bands_frame),
    "XRD": ("synthetic_xrd_powder.csv", _xrd_powder_frame),
}


def sample_for(modality: str) -> tuple[Path, str]:
    """Return ``(path, data_type)`` for a generated per-modality CSV."""
    token = str(modality or "").strip().upper()
    spec = _SAMPLE_BUILDERS.get(token)
    if spec is None:
        raise KeyError(f"No synthetic sample for modality {modality!r}")
    file_name, builder = spec
    return _write_csv(file_name, builder()), token


def dta_events_path(variant: str) -> Path:
    """Return the generated multi-event DTA trace (``5c`` or ``10c`` variant)."""
    if variant not in {"5c", "10c"}:
        raise KeyError(f"Unknown DTA variant {variant!r}")
    return _write_csv(f"synthetic_dta_events_{variant}.csv", _dta_events_frame(variant))


def ensure_all_samples() -> dict[str, Path]:
    """Materialize every per-modality sample file; returns modality -> path."""
    return {modality: sample_for(modality)[0] for modality in _SAMPLE_BUILDERS}
