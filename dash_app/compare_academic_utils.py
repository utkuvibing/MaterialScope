"""Pure helpers for academic-style same-technique comparison overlays."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
import re
from statistics import median
from typing import Any

import plotly.graph_objects as go

from core.axis_labels import build_axis_title, canonical_unit_token
from core.modality_specs import get_modality_spec


@dataclass(frozen=True)
class AcademicCompareOptions:
    analysis_type: str
    selected_dataset_keys: list[str] = field(default_factory=list)
    signal_mode: str = "best"
    normalize_mode: str = "none"
    offset_mode: str = "none"
    reverse_x_axis: bool | None = None
    label_template: str = "{sample_id} at {temperature}"
    smoothing_enabled: bool = True


@dataclass(frozen=True)
class AcademicCurve:
    dataset_key: str
    label: str
    x: list[float | None]
    y: list[float | None]
    source: str
    x_unit: str | None = None
    y_unit: str | None = None
    signal_role: str | None = None
    axis_role: str | None = None


@dataclass(frozen=True)
class AcademicCompareResult:
    figure: go.Figure
    warnings: list[str] = field(default_factory=list)
    trace_summaries: list[dict[str, Any]] = field(default_factory=list)


_TEMPLATE_FIELDS = {
    "sample_id",
    "sample_name",
    "temperature",
    "composition",
    "material_type",
    "dataset_key",
    "display_name",
}


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return dict(value.model_dump())
    if hasattr(value, "dict"):
        return dict(value.dict())
    return {key: getattr(value, key) for key in dir(value) if not key.startswith("_") and not callable(getattr(value, key))}


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clean_stem(value: str) -> str:
    text = str(value or "").strip()
    if "." in text:
        return text.rsplit(".", 1)[0]
    return text


def _tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = re.split(r"[,;|]", value)
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = [value]
    return [str(item).strip() for item in raw if str(item).strip()]


def _format_temperature(value: Any, unit: Any = "°C") -> str:
    number = _as_float(value)
    if number is None:
        return ""
    unit_text = str(unit or "°C").strip() or "°C"
    display = str(int(number)) if float(number).is_integer() else f"{number:g}"
    return f"{display}{unit_text}"


def candidate_from_dataset_summary(dataset_summary: Any, sample_record: Any = None) -> dict[str, Any]:
    """Build a compare candidate from dataset summary plus optional sample metadata."""
    dataset = _as_dict(dataset_summary)
    sample = _as_dict(sample_record)
    dataset_key = _first_text(dataset.get("dataset_key"), dataset.get("key"), sample.get("dataset_key"))
    display_name = _first_text(dataset.get("display_name"), dataset.get("file_name"), dataset_key)
    sample_id = _first_text(sample.get("sample_id"), dataset.get("sample_id"), _clean_stem(dataset_key))
    sample_name = _first_text(sample.get("sample_name"), dataset.get("sample_name"), display_name)
    temp_value = sample.get("processing_temperature_value", dataset.get("processing_temperature_value"))
    temp_unit = _first_text(sample.get("processing_temperature_unit"), dataset.get("processing_temperature_unit"), "°C")
    return {
        "dataset_key": dataset_key,
        "display_name": display_name,
        "data_type": _first_text(dataset.get("data_type"), sample.get("data_type")).upper(),
        "points": dataset.get("points"),
        "sample_id": sample_id,
        "sample_name": sample_name,
        "material_type": _first_text(sample.get("material_type"), dataset.get("material_type")),
        "processing_temperature_value": _as_float(temp_value),
        "processing_temperature_unit": temp_unit,
        "composition": _first_text(sample.get("composition"), dataset.get("composition")),
        "tags": _tags(sample.get("tags", dataset.get("tags"))),
        "linked_dataset_keys": list(sample.get("linked_dataset_keys") or []),
        "linked_result_ids": list(sample.get("linked_result_ids") or []),
        "has_analysis_state": bool(dataset.get("has_analysis_state", sample.get("has_analysis_state", False))),
        "has_processed_result": bool(dataset.get("has_processed_result", sample.get("has_processed_result", False))),
        "x_unit": dataset.get("x_unit") or sample.get("x_unit"),
        "y_unit": dataset.get("y_unit") or sample.get("y_unit"),
        "signal_role": dataset.get("signal_role") or sample.get("signal_role"),
    }


def group_candidates_by_sample(candidates: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        key = _first_text(candidate.get("sample_id"), candidate.get("dataset_key"), "unknown")
        grouped.setdefault(key, []).append(candidate)
    return grouped


def filter_candidates(
    candidates: list[dict[str, Any]],
    *,
    analysis_type: str,
    group_mode: str = "manual",
    series_filter: str = "",
    temperature_filter_value: float | None = None,
    temperature_filter_unit: str = "°C",
    material_type_filter: str = "",
    tag_filters: list[str] | None = None,
    composition_filter: str = "",
) -> list[dict[str, Any]]:
    """Filter same-technique academic comparison candidates."""
    del group_mode  # The UI mode selects which filters are active; filtering itself is composable.
    modality = str(analysis_type or "").upper()
    series = str(series_filter or "").strip().upper()
    material = str(material_type_filter or "").strip().lower()
    composition = str(composition_filter or "").strip().lower()
    requested_tags = {str(tag).strip().lower() for tag in (tag_filters or []) if str(tag).strip()}
    requested_temp = _as_float(temperature_filter_value)
    requested_unit = canonical_unit_token(temperature_filter_unit or "°C")

    filtered: list[dict[str, Any]] = []
    for candidate in candidates:
        if modality and str(candidate.get("data_type") or "").upper() != modality:
            continue
        sample_id = str(candidate.get("sample_id") or "").upper()
        if series and not sample_id.startswith(series):
            continue
        if requested_temp is not None:
            candidate_temp = _as_float(candidate.get("processing_temperature_value"))
            candidate_unit = canonical_unit_token(candidate.get("processing_temperature_unit") or "°C")
            if candidate_temp is None or not math.isclose(candidate_temp, requested_temp, rel_tol=0.0, abs_tol=1e-9):
                continue
            if candidate_unit != requested_unit:
                continue
        if material and material not in str(candidate.get("material_type") or "").lower():
            continue
        if composition and composition not in str(candidate.get("composition") or "").lower():
            continue
        candidate_tags = {tag.lower() for tag in _tags(candidate.get("tags"))}
        if requested_tags and not requested_tags.issubset(candidate_tags):
            continue
        filtered.append(candidate)
    return filtered


def render_compare_label(candidate: dict[str, Any], template: str) -> str:
    """Render a sample-aware trace label from a constrained template."""
    values = {
        "sample_id": _first_text(candidate.get("sample_id")),
        "sample_name": _first_text(candidate.get("sample_name")),
        "temperature": _format_temperature(
            candidate.get("processing_temperature_value"),
            candidate.get("processing_temperature_unit"),
        ),
        "composition": _first_text(candidate.get("composition")),
        "material_type": _first_text(candidate.get("material_type")),
        "dataset_key": _first_text(candidate.get("dataset_key")),
        "display_name": _first_text(candidate.get("display_name")),
    }
    text = str(template or "{sample_id} at {temperature}")
    for field_name in _TEMPLATE_FIELDS:
        text = text.replace("{" + field_name + "}", values[field_name])
    text = re.sub(r"\s+at\s*$", "", text).strip()
    text = re.sub(r"\(\s*\)", "", text).strip()
    text = re.sub(r"\s+[—-]\s*$", "", text).strip()
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text or values["display_name"] or values["dataset_key"] or "Dataset"


def _numeric_pair_series(x_values: list[Any], y_values: list[Any]) -> tuple[list[float | None], list[float | None]]:
    n = min(len(x_values), len(y_values))
    x_out: list[float | None] = []
    y_out: list[float | None] = []
    for idx in range(n):
        x = _as_float(x_values[idx])
        y = _as_float(y_values[idx])
        x_out.append(x)
        y_out.append(y)
    return x_out, y_out


def select_curve_from_analysis_state(
    curves: dict[str, Any],
    signal_mode: str = "best",
    smoothing_enabled: bool = True,
) -> tuple[list[float | None], list[float | None], str, dict[str, Any]] | None:
    """Pick a same-length curve from an analysis-state payload."""
    x_values = list((curves or {}).get("temperature") or [])
    if not x_values:
        return None

    mode = str(signal_mode or "best").lower()
    if mode == "raw":
        priority = [("raw_signal", "raw")]
    elif mode == "processed":
        priority = [("corrected", "corrected"), ("smoothed", "smoothed"), ("normalized", "normalized"), ("raw_signal", "raw")]
    else:
        priority = [("corrected", "corrected")]
        if smoothing_enabled:
            priority.append(("smoothed", "smoothed"))
        priority.append(("raw_signal", "raw"))

    for key, source in priority:
        y_values = list((curves or {}).get(key) or [])
        if len(y_values) == len(x_values):
            x, y = _numeric_pair_series(x_values, y_values)
            meta = {
                "x_unit": (curves or {}).get("x_unit"),
                "y_unit": (curves or {}).get("y_unit"),
                "signal_role": (curves or {}).get("signal_role"),
                "axis_role": (curves or {}).get("axis_role"),
            }
            return x, y, source, meta
    return None


def _column_values(rows: list[dict[str, Any]], column: str) -> list[Any]:
    return [row.get(column) for row in rows]


def _is_numeric_column(rows: list[dict[str, Any]], column: str) -> bool:
    values = [_as_float(row.get(column)) for row in rows[:25]]
    return any(value is not None for value in values)


def _match_alias_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    for pattern in aliases:
        rx = re.compile(pattern, re.IGNORECASE)
        for column in columns:
            if rx.search(str(column)):
                return column
    return None


def select_raw_curve(
    rows: list[dict[str, Any]],
    columns: list[str],
    analysis_type: str,
) -> tuple[list[float | None], list[float | None], str, str] | None:
    """Select x/y data columns for a raw imported dataset payload."""
    if not rows or not columns:
        return None
    x_column = "temperature" if "temperature" in columns else None
    y_column = "signal" if "signal" in columns else None
    spec = get_modality_spec(analysis_type)
    if spec:
        x_column = x_column or _match_alias_column(columns, tuple(spec.get("x_aliases") or ()))
        y_column = y_column or _match_alias_column(columns, tuple(spec.get("y_aliases") or ()))
    numeric_columns = [column for column in columns if _is_numeric_column(rows, column)]
    x_column = x_column or (numeric_columns[0] if numeric_columns else None)
    y_column = y_column or next((column for column in numeric_columns if column != x_column), None)
    if not x_column or not y_column:
        return None
    x, y = _numeric_pair_series(_column_values(rows, x_column), _column_values(rows, y_column))
    return x, y, x_column, y_column


def normalize_trace(y: list[Any], mode: str = "none", x: list[Any] | None = None) -> list[float | None]:
    """Normalize y values for academic overlays."""
    values = [_as_float(item) for item in y]
    finite = [item for item in values if item is not None]
    token = str(mode or "none").lower()
    if token == "none" or not finite:
        return values
    if token == "max":
        scale = max(abs(item) for item in finite)
        return values if scale == 0 else [None if item is None else item / scale for item in values]
    if token == "minmax":
        lo = min(finite)
        hi = max(finite)
        span = hi - lo
        return values if span == 0 else [None if item is None else (item - lo) / span for item in values]
    if token == "area":
        xs = [_as_float(item) for item in (x or list(range(len(values))))]
        area = 0.0
        for idx in range(1, min(len(xs), len(values))):
            x0, x1 = xs[idx - 1], xs[idx]
            y0, y1 = values[idx - 1], values[idx]
            if None not in (x0, x1, y0, y1):
                area += ((y0 + y1) / 2.0) * (x1 - x0)
        scale = abs(area)
        return values if scale == 0 else [None if item is None else item / scale for item in values]
    return values


def apply_vertical_offsets(traces: list[AcademicCurve], offset_mode: str = "none") -> list[AcademicCurve]:
    """Apply deterministic stacked offsets to curve y values."""
    if str(offset_mode or "none").lower() != "stacked":
        return traces
    ranges: list[float] = []
    for trace in traces:
        finite = [value for value in trace.y if value is not None and math.isfinite(value)]
        if finite:
            ranges.append(max(finite) - min(finite))
    positive_ranges = [value for value in ranges if value > 0]
    offset_step = 1.1 * median(positive_ranges) if positive_ranges else 1.0
    offset_traces: list[AcademicCurve] = []
    for index, trace in enumerate(traces):
        offset = index * offset_step
        y = [None if value is None else value + offset for value in trace.y]
        offset_traces.append(replace(trace, y=y))
    return offset_traces


def _first_non_empty(values: list[Any]) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _dedupe_labels(traces: list[AcademicCurve], warnings: list[str]) -> list[AcademicCurve]:
    counts: dict[str, int] = {}
    for trace in traces:
        counts[trace.label] = counts.get(trace.label, 0) + 1
    if not any(count > 1 for count in counts.values()):
        return traces
    warnings.append("Duplicate academic trace labels were disambiguated with dataset keys.")
    seen: dict[str, int] = {}
    deduped: list[AcademicCurve] = []
    for trace in traces:
        seen[trace.label] = seen.get(trace.label, 0) + 1
        if counts[trace.label] > 1:
            suffix = trace.dataset_key[-12:] if trace.dataset_key else str(seen[trace.label])
            deduped.append(replace(trace, label=f"{trace.label} [{suffix}]"))
        else:
            deduped.append(trace)
    return deduped


def build_academic_compare_figure(
    *,
    analysis_type: str,
    candidates: list[dict[str, Any]],
    selected_dataset_keys: list[str],
    curve_payloads: dict[str, dict[str, Any]] | None = None,
    raw_payloads: dict[str, dict[str, Any]] | None = None,
    options: AcademicCompareOptions | None = None,
    theme: str | None = None,
) -> AcademicCompareResult:
    """Build an academic-style Plotly overlay from prepared candidate and curve payloads."""
    del theme  # The Dash page applies its shared theme after figure construction.
    modality = str(analysis_type or "").upper()
    opts = options or AcademicCompareOptions(analysis_type=modality, selected_dataset_keys=selected_dataset_keys)
    candidate_by_key = {str(candidate.get("dataset_key")): candidate for candidate in candidates}
    warnings: list[str] = []
    traces: list[AcademicCurve] = []
    curve_payloads = curve_payloads or {}
    raw_payloads = raw_payloads or {}

    for dataset_key in selected_dataset_keys:
        candidate = candidate_by_key.get(dataset_key)
        if candidate is None:
            warnings.append(f"Selected dataset '{dataset_key}' is not available for {modality}.")
            continue
        if not candidate.get("sample_id"):
            warnings.append(f"Dataset '{dataset_key}' has no sample_id; display name fallback was used.")
        label = render_compare_label(candidate, opts.label_template)
        picked = select_curve_from_analysis_state(
            curve_payloads.get(dataset_key) or {},
            signal_mode=opts.signal_mode,
            smoothing_enabled=opts.smoothing_enabled,
        )
        if picked is not None:
            x, y, source, meta = picked
        else:
            raw = raw_payloads.get(dataset_key) or {}
            selected_raw = select_raw_curve(raw.get("rows") or [], raw.get("columns") or [], modality)
            if selected_raw is None:
                warnings.append(f"No plottable curve was found for dataset '{dataset_key}'.")
                continue
            x, y, x_column, y_column = selected_raw
            source = "raw"
            meta = {
                "x_unit": candidate.get("x_unit"),
                "y_unit": candidate.get("y_unit"),
                "signal_role": candidate.get("signal_role"),
                "axis_role": None,
            }
            if (x_column, y_column) != ("temperature", "signal"):
                warnings.append(f"Raw fallback for '{dataset_key}' used columns '{x_column}' and '{y_column}'.")
        y = normalize_trace(y, opts.normalize_mode, x)
        traces.append(
            AcademicCurve(
                dataset_key=dataset_key,
                label=label,
                x=x,
                y=y,
                source=source,
                x_unit=meta.get("x_unit"),
                y_unit=meta.get("y_unit"),
                signal_role=meta.get("signal_role"),
                axis_role=meta.get("axis_role"),
            )
        )

    traces = _dedupe_labels(apply_vertical_offsets(traces, opts.offset_mode), warnings)
    x_units = [trace.x_unit for trace in traces if trace.x_unit]
    y_units = [trace.y_unit for trace in traces if trace.y_unit]
    signal_roles = [trace.signal_role for trace in traces if trace.signal_role]
    if len({canonical_unit_token(unit) for unit in y_units}) > 1:
        warnings.append("Selected curves have mixed y-axis units; the first available unit is used for the axis title.")
    if len({str(role).lower() for role in signal_roles}) > 1:
        warnings.append("Selected curves have mixed signal roles; verify that the overlay is scientifically comparable.")

    x_title = build_axis_title(modality, "x", detected_unit=_first_non_empty(x_units), plotly_html=True)
    y_title = build_axis_title(
        modality,
        "y",
        detected_unit=_first_non_empty(y_units),
        signal_kind=_first_non_empty(signal_roles),
        plotly_html=True,
    )
    if str(opts.normalize_mode or "none").lower() != "none":
        y_title = f"{y_title} (normalized: {opts.normalize_mode})"
    if str(opts.offset_mode or "none").lower() == "stacked":
        y_title = f"{y_title} + offset"

    fig = go.Figure()
    trace_summaries: list[dict[str, Any]] = []
    for trace in traces:
        fig.add_trace(
            go.Scatter(
                x=trace.x,
                y=trace.y,
                mode="lines",
                name=trace.label,
                hovertemplate=(
                    f"{trace.label}<br>"
                    "%{x}<br>%{y}<br>"
                    f"dataset: {trace.dataset_key}<br>"
                    f"source: {trace.source}<extra></extra>"
                ),
            )
        )
        trace_summaries.append(
            {
                "dataset_key": trace.dataset_key,
                "label": trace.label,
                "source": trace.source,
                "points": len(trace.x),
            }
        )

    title_bits = [f"{modality} Academic Compare"]
    if str(opts.normalize_mode or "none").lower() != "none":
        title_bits.append(f"normalized={opts.normalize_mode}")
    if str(opts.offset_mode or "none").lower() == "stacked":
        title_bits.append("stacked")
    fig.update_layout(
        title=" · ".join(title_bits),
        xaxis_title=x_title,
        yaxis_title=y_title,
        margin=dict(l=56, r=24, t=64, b=52),
        height=460,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    reverse_x = opts.reverse_x_axis if opts.reverse_x_axis is not None else modality == "FTIR"
    if reverse_x:
        fig.update_xaxes(autorange="reversed")
    return AcademicCompareResult(figure=fig, warnings=warnings, trace_summaries=trace_summaries)
