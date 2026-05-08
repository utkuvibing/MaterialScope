from __future__ import annotations

import math

from dash_app.compare_academic_utils import (
    AcademicCompareOptions,
    AcademicCurve,
    apply_vertical_offsets,
    build_academic_compare_figure,
    candidate_from_dataset_summary,
    filter_candidates,
    group_candidates_by_sample,
    normalize_trace,
    render_compare_label,
    select_curve_from_analysis_state,
    select_raw_curve,
)


def _candidate(
    key: str,
    *,
    data_type: str = "FTIR",
    sample_id: str | None = None,
    temp: float | None = None,
    unit: str = "°C",
    tags: list[str] | None = None,
    material_type: str = "",
    composition: str = "",
) -> dict:
    return {
        "dataset_key": key,
        "display_name": f"{key}.csv",
        "data_type": data_type,
        "sample_id": sample_id or key,
        "sample_name": f"Sample {sample_id or key}",
        "processing_temperature_value": temp,
        "processing_temperature_unit": unit,
        "tags": tags or [],
        "material_type": material_type,
        "composition": composition,
    }


def test_candidate_from_dataset_summary_merges_sample_metadata_and_fallbacks():
    candidate = candidate_from_dataset_summary(
        {"key": "ftir_a1.csv", "display_name": "FTIR A1", "data_type": "FTIR", "points": 3},
        {
            "sample_id": "A1",
            "sample_name": "Alpha one",
            "processing_temperature_value": 1050,
            "composition": "Al2O3-SiO2",
            "tags": ["ceramic", "sintered"],
        },
    )

    assert candidate["dataset_key"] == "ftir_a1.csv"
    assert candidate["sample_id"] == "A1"
    assert candidate["sample_name"] == "Alpha one"
    assert candidate["processing_temperature_value"] == 1050
    assert candidate["processing_temperature_unit"] == "°C"
    assert candidate["composition"] == "Al2O3-SiO2"
    assert candidate["tags"] == ["ceramic", "sintered"]

    fallback = candidate_from_dataset_summary({"key": "B3_run.csv", "data_type": "RAMAN"})
    assert fallback["sample_id"] == "B3_run"
    assert fallback["sample_name"] == "B3_run.csv"


def test_group_candidates_by_sample_uses_sample_id():
    grouped = group_candidates_by_sample(
        [
            _candidate("a1_ftir", sample_id="A1"),
            _candidate("a1_tga", data_type="TGA", sample_id="A1"),
            _candidate("b3_ftir", sample_id="B3"),
        ]
    )

    assert set(grouped) == {"A1", "B3"}
    assert [item["dataset_key"] for item in grouped["A1"]] == ["a1_ftir", "a1_tga"]


def test_filter_candidates_supports_technique_series_temperature_tags_and_composition():
    candidates = [
        _candidate("a1_950", sample_id="A1", temp=950, tags=["sintered"], material_type="ceramic", composition="Al2O3"),
        _candidate("a1_1050", sample_id="A1", temp=1050, tags=["sintered"], material_type="ceramic", composition="SiO2"),
        _candidate("b3_1050", sample_id="B3", temp=1050, tags=["pressed"], material_type="ceramic", composition="Al2O3"),
        _candidate("a1_tga", data_type="TGA", sample_id="A1", temp=1050, tags=["sintered"]),
    ]

    by_series = filter_candidates(candidates, analysis_type="FTIR", series_filter="A")
    assert [item["dataset_key"] for item in by_series] == ["a1_950", "a1_1050"]

    by_temp = filter_candidates(candidates, analysis_type="FTIR", temperature_filter_value=1050, temperature_filter_unit="degC")
    assert [item["dataset_key"] for item in by_temp] == ["a1_1050", "b3_1050"]

    by_tag_and_composition = filter_candidates(
        candidates,
        analysis_type="FTIR",
        tag_filters=["sintered"],
        composition_filter="sio",
        material_type_filter="ceram",
    )
    assert [item["dataset_key"] for item in by_tag_and_composition] == ["a1_1050"]


def test_render_compare_label_supports_temperature_and_cleanup():
    candidate = _candidate("a1_1050", sample_id="A1", temp=1050, composition="Al2O3")

    assert render_compare_label(candidate, "{sample_id} at {temperature}") == "A1 at 1050°C"
    assert render_compare_label(candidate, "{sample_id} ({composition})") == "A1 (Al2O3)"

    missing_temperature = _candidate("b3", sample_id="B3")
    assert render_compare_label(missing_temperature, "{sample_id} at {temperature}") == "B3"

    empty_label = {"dataset_key": "raw_file.csv", "display_name": "Raw File"}
    assert render_compare_label(empty_label, "{sample_id} at {temperature}") == "Raw File"


def test_select_curve_from_analysis_state_respects_signal_mode_and_smoothing():
    curves = {
        "temperature": [400, 500, 600],
        "corrected": [1, 2, 3],
        "smoothed": [2, 3, 4],
        "normalized": [0, 0.5, 1],
        "raw_signal": [10, 20, 30],
        "x_unit": "cm^-1",
        "y_unit": "absorbance",
        "signal_role": "absorbance",
    }

    assert select_curve_from_analysis_state(curves, "best")[2] == "corrected"
    assert select_curve_from_analysis_state(curves, "processed")[2] == "corrected"
    assert select_curve_from_analysis_state(curves, "raw")[2] == "raw"

    no_corrected = dict(curves, corrected=[])
    assert select_curve_from_analysis_state(no_corrected, "best", smoothing_enabled=True)[2] == "smoothed"
    assert select_curve_from_analysis_state(no_corrected, "best", smoothing_enabled=False)[2] == "raw"


def test_select_raw_curve_prefers_canonical_columns_then_aliases_then_numeric_fallback():
    canonical = select_raw_curve(
        [{"temperature": 100, "signal": 1}, {"temperature": 200, "signal": 2}],
        ["temperature", "signal"],
        "FTIR",
    )
    assert canonical is not None
    assert canonical[2:] == ("temperature", "signal")

    alias = select_raw_curve(
        [{"Wavenumber": 1000, "Absorbance": 0.1}, {"Wavenumber": 900, "Absorbance": 0.2}],
        ["Wavenumber", "Absorbance"],
        "FTIR",
    )
    assert alias is not None
    assert alias[2:] == ("Wavenumber", "Absorbance")

    fallback = select_raw_curve(
        [{"a": 1, "b": 2, "name": "x"}, {"a": 3, "b": 4, "name": "y"}],
        ["name", "a", "b"],
        "DSC",
    )
    assert fallback is not None
    assert fallback[2:] == ("a", "b")


def test_normalize_trace_modes_are_deterministic():
    assert normalize_trace([2, -4], "max") == [0.5, -1.0]
    assert normalize_trace([10, 20, 30], "minmax") == [0.0, 0.5, 1.0]

    area = normalize_trace([1, 1, 1], "area", x=[0, 1, 2])
    assert area == [0.5, 0.5, 0.5]

    assert normalize_trace([5, 5], "minmax") == [5.0, 5.0]


def test_apply_vertical_offsets_stacks_by_median_range():
    traces = [
        AcademicCurve("a", "A", [1, 2], [0, 1], "raw"),
        AcademicCurve("b", "B", [1, 2], [0, 1], "raw"),
        AcademicCurve("c", "C", [1, 2], [0, 1], "raw"),
    ]

    stacked = apply_vertical_offsets(traces, "stacked")
    assert stacked[0].y == [0, 1]
    assert stacked[1].y == [1.1, 2.1]
    assert stacked[2].y == [2.2, 3.2]


def test_build_academic_compare_figure_sets_ftir_axes_reverse_and_labels():
    candidates = [
        _candidate("a1", sample_id="A1", temp=1050),
        _candidate("b3", sample_id="B3", temp=1050),
    ]
    curve_payloads = {
        "a1": {
            "temperature": [4000, 3000, 2000],
            "raw_signal": [90, 85, 80],
            "x_unit": "cm^-1",
            "y_unit": "%",
            "signal_role": "transmittance",
        },
        "b3": {
            "temperature": [4000, 3000, 2000],
            "raw_signal": [88, 82, 78],
            "x_unit": "cm^-1",
            "y_unit": "%",
            "signal_role": "transmittance",
        },
    }

    result = build_academic_compare_figure(
        analysis_type="FTIR",
        candidates=candidates,
        selected_dataset_keys=["a1", "b3"],
        curve_payloads=curve_payloads,
        options=AcademicCompareOptions(analysis_type="FTIR", selected_dataset_keys=["a1", "b3"], signal_mode="raw"),
    )

    assert len(result.figure.data) == 2
    assert [trace.name for trace in result.figure.data] == ["A1 at 1050°C", "B3 at 1050°C"]
    assert "Wavenumber" in result.figure.layout.xaxis.title.text
    assert "Transmittance" in result.figure.layout.yaxis.title.text
    assert result.figure.layout.xaxis.autorange == "reversed"


def test_build_academic_compare_figure_warns_on_mixed_units_and_raw_fallback():
    candidates = [
        _candidate("a1", sample_id="A1", data_type="RAMAN"),
        _candidate("a2", sample_id="A2", data_type="RAMAN"),
    ]
    curve_payloads = {
        "a1": {
            "temperature": [100, 200],
            "raw_signal": [1, 2],
            "x_unit": "cm^-1",
            "y_unit": "counts",
            "signal_role": "intensity",
        }
    }
    raw_payloads = {
        "a2": {
            "columns": ["shift", "intensity"],
            "rows": [{"shift": 100, "intensity": 2}, {"shift": 200, "intensity": 3}],
        }
    }

    result = build_academic_compare_figure(
        analysis_type="RAMAN",
        candidates=candidates,
        selected_dataset_keys=["a1", "a2"],
        curve_payloads=curve_payloads,
        raw_payloads=raw_payloads,
        options=AcademicCompareOptions(analysis_type="RAMAN", selected_dataset_keys=["a1", "a2"], signal_mode="raw"),
    )

    assert len(result.figure.data) == 2
    assert "Raman Shift" in result.figure.layout.xaxis.title.text
    assert any("Raw fallback" in warning for warning in result.warnings)

    mixed = build_academic_compare_figure(
        analysis_type="RAMAN",
        candidates=candidates,
        selected_dataset_keys=["a1", "a2"],
        curve_payloads={
            "a1": dict(curve_payloads["a1"], y_unit="counts"),
            "a2": {
                "temperature": [100, 200],
                "raw_signal": [1, 2],
                "x_unit": "cm^-1",
                "y_unit": "a.u.",
                "signal_role": "intensity",
            },
        },
        options=AcademicCompareOptions(analysis_type="RAMAN", selected_dataset_keys=["a1", "a2"], signal_mode="raw"),
    )
    assert any("mixed y-axis units" in warning for warning in mixed.warnings)


def test_build_academic_compare_figure_normalized_stacked_title_and_values():
    candidates = [
        _candidate("x1", data_type="XRD", sample_id="X1"),
        _candidate("x2", data_type="XRD", sample_id="X2"),
    ]
    payload = {
        "temperature": [10, 20],
        "raw_signal": [10, 20],
        "x_unit": "degree_2theta",
        "y_unit": "counts",
        "signal_role": "intensity",
    }

    result = build_academic_compare_figure(
        analysis_type="XRD",
        candidates=candidates,
        selected_dataset_keys=["x1", "x2"],
        curve_payloads={"x1": payload, "x2": payload},
        options=AcademicCompareOptions(
            analysis_type="XRD",
            selected_dataset_keys=["x1", "x2"],
            signal_mode="raw",
            normalize_mode="max",
            offset_mode="stacked",
            reverse_x_axis=False,
        ),
    )

    assert "2θ" in result.figure.layout.xaxis.title.text
    assert "normalized=max" in result.figure.layout.title.text
    assert "stacked" in result.figure.layout.title.text
    assert math.isclose(result.figure.data[0].y[1], 1.0)
    assert result.figure.data[1].y[0] > result.figure.data[0].y[1]
