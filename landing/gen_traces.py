"""Generate ``landing/web/traces.js`` from the repository's sample datasets.

The landing page renders real characterization traces (DSC, TGA, DTA, FTIR,
Raman, XRD) so the hero visualization shows actual MaterialScope data rather
than decorative mock-ups.  This module is the single source for that asset:

    python -m landing.gen_traces

It reads CSVs from ``sample_data/`` and writes a plain script that assigns a
``window.MS_TRACES`` object with, per modality: normalized polyline points,
axis domains/units, tick positions in data units, and a few peak/step
annotations.  Values are rounded aggressively to keep the file small.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO_ROOT / "sample_data"
OUTPUT_PATH = Path(__file__).resolve().parent / "web" / "traces.js"

CU_K_ALPHA_ANGSTROM = 1.5406
TARGET_POINTS = 260


def _read_xy(path: Path, x_name: str, y_name: str) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                x = float(row[x_name])
                y = float(row[y_name])
            except (TypeError, ValueError, KeyError):
                continue
            if math.isfinite(x) and math.isfinite(y):
                xs.append(x)
                ys.append(y)
    if not xs:
        raise SystemExit(f"No numeric rows parsed from {path}")
    return xs, ys


def _resample(xs: list[float], ys: list[float], n: int = TARGET_POINTS) -> tuple[list[float], list[float]]:
    """Bucket downsample that keeps the min/max of each bucket (preserves peaks)."""
    count = len(xs)
    if count <= n:
        return xs, ys
    out_x: list[float] = []
    out_y: list[float] = []
    for i in range(n):
        lo = (i * count) // n
        hi = ((i + 1) * count) // n
        hi = max(hi, lo + 1)
        seg = [(xs[j], ys[j]) for j in range(lo, min(hi, count))]
        lo_y = min(seg, key=lambda p: p[1])
        hi_y = max(seg, key=lambda p: p[1])
        if lo_y[1] <= hi_y[1]:
            out_x.extend((lo_y[0], hi_y[0]))
            out_y.extend((lo_y[1], hi_y[1]))
        else:
            out_x.extend((hi_y[0], lo_y[0]))
            out_y.extend((hi_y[1], lo_y[1]))
    return out_x, out_y


def _find_prominent_peaks(xs: list[float], ys: list[float], invert: bool, k: int, min_sep_frac: float = 0.08) -> list[int]:
    """Index list of up to ``k`` prominent local maxima (sign adjusted if inverted)."""
    if invert:
        ys = [-y for y in ys]
    n = len(ys)
    win = max(3, n // 40)
    candidates: list[tuple[float, int]] = []
    med = statistics.median(ys)
    for i in range(win, n - win):
        y = ys[i]
        if y <= med:
            continue
        window = ys[i - win : i + win + 1]
        if y >= max(window) and y - min(window) > 1e-9:
            candidates.append((y - min(window), i))
    candidates.sort(reverse=True)
    picks: list[int] = []
    min_sep = int(n * min_sep_frac)
    for _, idx in candidates:
        if all(abs(idx - p) >= min_sep for p in picks):
            picks.append(idx)
        if len(picks) >= k:
            break
    return sorted(picks)


def _nice_ticks(lo: float, hi: float, n: int = 6) -> list[float]:
    span = hi - lo
    if span <= 0:
        return [lo]
    raw = span / max(n - 1, 2)
    mag = 10.0 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if step >= raw:
            break
    first = math.ceil(lo / step) * step
    ticks: list[float] = []
    value = first
    while value <= hi + step * 1e-6 and len(ticks) < 12:
        ticks.append(round(value, 6))
        value += step
    return ticks


def _smooth(ys: list[float], win: int) -> list[float]:
    half = max(1, win // 2)
    n = len(ys)
    out = []
    prefix = [0.0]
    for y in ys:
        prefix.append(prefix[-1] + y)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n - 1, i + half)
        out.append((prefix[hi + 1] - prefix[lo]) / (hi - lo + 1))
    return out


def _dominant_extremum(xs: list[float], ys: list[float], prefer: str, win_frac: float = 1 / 40) -> int:
    """Index of the smoothed curve's dominant extremum (largest deviation from the median)."""
    sw = _smooth(ys, max(3, int(len(ys) * win_frac)))
    med = statistics.median(sw)
    if prefer == "max":
        return sw.index(max(sw))
    if prefer == "min":
        return sw.index(min(sw))
    hi = max(sw) - med
    lo = med - min(sw)
    return sw.index(max(sw) if hi >= lo else min(sw))


def _fmt(v: float) -> float:
    return round(v, 4)


def _series(fname: str, x_name: str, y_name: str, *, sort_key: bool = True) -> tuple[list[float], list[float]]:
    xs, ys = _read_xy(SAMPLE_DIR / fname, x_name, y_name)
    if sort_key:
        pairs = sorted(zip(xs, ys))
        xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
    return _resample(xs, ys)


def build_dsc() -> dict:
    xs, ys = _series("dsc_polymer_melting.csv", "Temperature (°C)", "Heat Flow (mW/mg)")
    # Endotherm direction: whichever side of the median deviates further.
    med = statistics.median(ys)
    prefer = "max" if (max(ys) - med) >= (med - min(ys)) else "min"
    idx = _dominant_extremum(xs, ys, prefer)
    kind = "endothermic" if prefer == "max" else "exothermic"
    annotations = [{"x": _fmt(xs[idx]), "y": _fmt(ys[idx]), "label": f"{kind} peak · {xs[idx]:.0f} °C"}]
    return _pack(
        key="dsc",
        title="DSC",
        full="Differential Scanning Calorimetry",
        file="dsc_polymer_melting.csv",
        xs=xs,
        ys=ys,
        x_label="Temperature",
        x_unit="°C",
        y_label="Heat flow",
        y_unit="mW/mg",
        annotations=annotations,
        meta="Polymer melting run · 541 pts",
    )


def build_tga() -> dict:
    xs, ys = _series("tga_calcium_oxalate.csv", "Temperature (°C)", "Mass (%)")
    # Step temperatures: strongest mass-loss rate inside each temperature window.
    rate_at = [(xs[i], (ys[i + 1] - ys[i]) / max(xs[i + 1] - xs[i], 1e-9)) for i in range(len(xs) - 1)]
    annotations = []
    for lo_t, hi_t in ((80.0, 290.0), (290.0, 540.0), (540.0, 900.0)):
        seg = [(x, r) for x, r in rate_at if lo_t <= x < hi_t]
        if not seg:
            continue
        x0, r0 = min(seg, key=lambda p: p[1])
        idx = min(range(len(xs)), key=lambda i: abs(xs[i] - x0))
        annotations.append(
            {
                "x": _fmt(xs[idx]),
                "y": _fmt(ys[idx]),
                "label": f"mass-loss step · {xs[idx]:.0f} °C",
            }
        )
    out = _pack(
        key="tga",
        title="TGA",
        full="Thermogravimetric Analysis",
        file="tga_calcium_oxalate.csv",
        xs=xs,
        ys=ys,
        x_label="Temperature",
        x_unit="°C",
        y_label="Mass",
        y_unit="%",
        annotations=annotations,
        meta="Calcium oxalate · 3 decomposition steps",
    )
    return out


def build_dta() -> dict:
    xs, ys = _series("dta_tnaa_5c_mendeley.csv", "temperature", "signal")
    idx = _dominant_extremum(xs, ys, "max")
    annotations = [{"x": _fmt(xs[idx]), "y": _fmt(ys[idx]), "label": f"decomposition peak · {xs[idx]:.0f} °C"}]
    return _pack(
        key="dta",
        title="DTA",
        full="Differential Thermal Analysis",
        file="dta_tnaa_5c_mendeley.csv",
        xs=xs,
        ys=ys,
        x_label="Temperature",
        x_unit="°C",
        y_label="DTA signal",
        y_unit="a.u.",
        annotations=annotations,
        meta="TNAA decomposition · 5 °C/min",
    )


def build_ftir() -> dict:
    # x column carries wavenumber (cm^-1); signal is transmittance-like.
    xs, ys = _series("ftir_particleboard_50g_figshare.csv", "temperature", "signal", sort_key=False)
    xs = list(reversed(xs))
    ys = list(reversed(ys))
    picks = _find_prominent_peaks(xs, ys, invert=True, k=2, min_sep_frac=0.05)
    annotations = [
        {"x": _fmt(xs[i]), "y": _fmt(ys[i]), "label": f"absorption band · {xs[i]:.0f} cm⁻¹"} for i in picks
    ]
    out = _pack(
        key="ftir",
        title="FTIR",
        full="Fourier-Transform Infrared Spectroscopy",
        file="ftir_particleboard_50g_figshare.csv",
        xs=xs,
        ys=ys,
        x_label="Wavenumber",
        x_unit="cm⁻¹",
        y_label="Intensity",
        y_unit="a.u.",
        annotations=annotations,
        meta="Particleboard sample · decreasing ν̃",
    )
    out["xReversed"] = True
    return out


def build_raman() -> dict:
    xs, ys = _series("raman_cnt_figshare.csv", "temperature", "signal")
    picks = _find_prominent_peaks(xs, ys, invert=False, k=2)
    annotations = [
        {"x": _fmt(xs[i]), "y": _fmt(ys[i]), "label": f"graphitic band · {xs[i]:.0f} cm⁻¹"} for i in picks
    ]
    return _pack(
        key="raman",
        title="Raman",
        full="Raman spectroscopy",
        file="raman_cnt_figshare.csv",
        xs=xs,
        ys=ys,
        x_label="Raman shift",
        x_unit="cm⁻¹",
        y_label="Intensity",
        y_unit="a.u.",
        annotations=annotations,
        meta="Carbon nanotube sample",
    )


def build_xrd() -> dict:
    xs, ys = _series("xrd_2024_0304_zenodo.csv", "temperature", "signal")
    picks = _find_prominent_peaks(xs, ys, invert=False, k=3)
    annotations = []
    for i in picks:
        two_theta = xs[i]
        d = CU_K_ALPHA_ANGSTROM / (2.0 * math.sin(math.radians(two_theta / 2.0)))
        annotations.append(
            {
                "x": _fmt(two_theta),
                "y": _fmt(ys[i]),
                "label": f"{two_theta:.2f}° 2θ · d = {d:.3f} Å",
            }
        )
    return _pack(
        key="xrd",
        title="XRD",
        full="X-Ray Diffraction",
        file="xrd_2024_0304_zenodo.csv",
        xs=xs,
        ys=ys,
        x_label="2θ",
        x_unit="°",
        y_label="Intensity",
        y_unit="counts",
        annotations=annotations,
        meta="Cu Kα λ = 1.5406 Å",
    )


def _pack(
    *,
    key: str,
    title: str,
    full: str,
    file: str,
    xs: list[float],
    ys: list[float],
    x_label: str,
    x_unit: str,
    y_label: str,
    y_unit: str,
    annotations: list[dict],
    meta: str,
    ) -> dict:
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    x_pad = (x_hi - x_lo) * 0.02 or 1.0
    y_pad = (y_hi - y_lo) * 0.10 or 1.0
    x_lo -= x_pad
    x_hi += x_pad
    y_lo -= y_pad
    y_hi += y_pad
    span_x = x_hi - x_lo or 1.0
    span_y = y_hi - y_lo or 1.0
    pts = [[(x - x_lo) / span_x, 1.0 - (y - y_lo) / span_y] for x, y in zip(xs, ys)]
    pts = [[round(px, 4), round(py, 4)] for px, py in pts]
    return {
        "key": key,
        "title": title,
        "full": full,
        "file": file,
        "meta": meta,
        "xLabel": x_label,
        "xUnit": x_unit,
        "yLabel": y_label,
        "yUnit": y_unit,
        "xDomain": [_fmt(x_lo), _fmt(x_hi)],
        "yDomain": [_fmt(y_lo), _fmt(y_hi)],
        "xTicks": [_fmt(t) for t in _nice_ticks(x_lo, x_hi)],
        "yTicks": [_fmt(t) for t in _nice_ticks(y_lo, y_hi, 5)],
        "xTicksLabel": [_strip_zero(t) for t in _nice_ticks(x_lo, x_hi)],
        "yTicksLabel": [_strip_zero(t) for t in _nice_ticks(y_lo, y_hi, 5)],
        "xReversed": False,
        "points": pts,
        "annotations": annotations,
    }


def _strip_zero(v: float) -> str:
    if abs(v) >= 100:
        return str(int(round(v)))
    text = f"{v:.1f}"
    if text.endswith(".0"):
        text = text[:-2]
    return text


def main() -> None:
    builders = [build_xrd, build_dsc, build_tga, build_dta, build_ftir, build_raman]
    data = {}
    for build in builders:
        entry = build()
        data[entry["key"]] = entry
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, separators=(",", ":"))
    OUTPUT_PATH.write_text(
        "// Generated by `python -m landing.gen_traces` — do not edit by hand.\n"
        "// Real sample traces from sample_data/, normalized into unit box (y flipped, screen space).\n"
        f"window.MS_TRACES = {body};\n",
        encoding="utf-8",
    )
    total_pts = sum(len(entry["points"]) for entry in data.values())
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)} · {len(data)} modalities · {total_pts} points · {OUTPUT_PATH.stat().st_size/1024:.1f} KiB")


if __name__ == "__main__":
    main()
