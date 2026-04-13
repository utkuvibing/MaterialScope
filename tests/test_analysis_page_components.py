"""Tests for shared analysis-page primitives (dash_app.components.analysis_page)."""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

from dash_app.components.analysis_page import (
    dataset_options,
    dataset_selector_block,
    eligible_datasets,
    empty_result_msg,
    interpret_run_result,
    metric_card,
    metrics_row,
    no_data_figure_msg,
    processing_details_section,
    resolve_sample_name,
)


# ---------------------------------------------------------------------------
# metric_card / metrics_row
# ---------------------------------------------------------------------------

def test_metric_card_renders_label_and_value():
    card = metric_card("Peaks", "3")
    assert isinstance(card, dbc.Card)
    body = card.children
    small = body.children[0]
    h4 = body.children[1]
    assert "Peaks" in small.children
    assert h4.children == "3"


def test_metrics_row_contains_heading_and_card_columns():
    row = metrics_row([("A", "1"), ("B", "2")])
    children = row.children
    assert children[0].children == "Result Summary"
    assert isinstance(children[1], dbc.Row)
    cols = children[1].children
    assert len(cols) == 2


# ---------------------------------------------------------------------------
# eligible_datasets / dataset_options
# ---------------------------------------------------------------------------

def test_eligible_datasets_filters_by_uppercase_type():
    datasets = [
        {"key": "a", "data_type": "DSC"},
        {"key": "b", "data_type": "tga"},
        {"key": "c", "data_type": "UNKNOWN"},
        {"key": "d", "data_type": "FTIR"},
    ]
    result = eligible_datasets(datasets, {"DSC", "UNKNOWN"})
    assert [d["key"] for d in result] == ["a", "c"]


def test_eligible_datasets_handles_missing_type():
    datasets = [{"key": "x", "data_type": None}, {"key": "y"}]
    # None -> "NONE", missing key -> "" -- neither matches {"UNKNOWN"}
    result = eligible_datasets(datasets, {"UNKNOWN"})
    assert result == []

    # With UNKNOWN data_type explicitly set, it matches
    datasets2 = [{"key": "z", "data_type": "UNKNOWN"}]
    result2 = eligible_datasets(datasets2, {"UNKNOWN"})
    assert [d["key"] for d in result2] == ["z"]


def test_dataset_options_builds_select_options():
    datasets = [
        {"key": "a.csv", "display_name": "Sample A", "data_type": "DSC"},
        {"key": "b.csv", "display_name": "Sample B", "data_type": "TGA"},
    ]
    opts = dataset_options(datasets)
    assert len(opts) == 2
    assert opts[0]["value"] == "a.csv"
    assert "Sample A" in opts[0]["label"]
    assert "DSC" in opts[0]["label"]


# ---------------------------------------------------------------------------
# dataset_selector_block
# ---------------------------------------------------------------------------

def test_dataset_selector_block_returns_disabled_when_empty():
    children, disabled = dataset_selector_block(
        selector_id="test-select",
        empty_msg="Import a file first.",
        eligible=[],
        all_datasets=[{"key": "x", "data_type": "FTIR"}],
        eligible_types={"DSC"},
    )
    assert disabled is True
    assert "Import a file first" in children.children


def test_dataset_selector_block_returns_enabled_when_eligible():
    eligible = [{"key": "a.csv", "display_name": "A", "data_type": "DSC"}]
    children, disabled = dataset_selector_block(
        selector_id="test-select",
        empty_msg="No data.",
        eligible=eligible,
        all_datasets=eligible,
        eligible_types={"DSC"},
    )
    assert disabled is False
    assert isinstance(children, html.Div)
    # First child should be the selector
    selector = children.children[0]
    assert isinstance(selector, dbc.Select)
    assert selector.id == "test-select"


def test_dataset_selector_block_prefers_active_dataset():
    eligible = [
        {"key": "a.csv", "display_name": "A", "data_type": "DSC"},
        {"key": "b.csv", "display_name": "B", "data_type": "DSC"},
    ]
    children, disabled = dataset_selector_block(
        selector_id="test-select",
        empty_msg="No data.",
        eligible=eligible,
        all_datasets=eligible,
        eligible_types={"DSC"},
        active_dataset="b.csv",
    )
    selector = children.children[0]
    assert selector.value == "b.csv"


# ---------------------------------------------------------------------------
# interpret_run_result
# ---------------------------------------------------------------------------

def test_interpret_run_result_saved():
    result = {
        "execution_status": "saved",
        "result_id": "dsc_test",
        "failure_reason": None,
        "validation": {"status": "pass", "warning_count": 0},
    }
    alert, saved, result_id = interpret_run_result(result)
    assert saved is True
    assert result_id == "dsc_test"
    assert isinstance(alert, dbc.Alert)
    assert alert.color == "success"


def test_interpret_run_result_blocked():
    result = {
        "execution_status": "blocked",
        "result_id": None,
        "failure_reason": "Not eligible",
        "validation": {"status": "fail", "warning_count": 0},
    }
    alert, saved, result_id = interpret_run_result(result)
    assert saved is False
    assert result_id is None
    assert alert.color == "warning"


def test_interpret_run_result_failed():
    result = {
        "execution_status": "failed",
        "result_id": None,
        "failure_reason": "Crash",
        "validation": {"status": "error", "warning_count": 0},
    }
    alert, saved, result_id = interpret_run_result(result)
    assert saved is False
    assert result_id is None
    assert alert.color == "danger"


def test_interpret_run_result_unknown_status():
    result = {
        "execution_status": "garbage",
        "result_id": None,
        "failure_reason": None,
        "validation": {},
    }
    alert, saved, result_id = interpret_run_result(result)
    assert saved is False
    assert result_id is None
    assert alert.color == "danger"


# ---------------------------------------------------------------------------
# processing_details_section
# ---------------------------------------------------------------------------

def test_processing_details_section_shows_shared_fields():
    processing = {
        "workflow_template_label": "General DSC",
        "workflow_template_version": 1,
        "signal_pipeline": {"smoothing": {"method": "savgol"}},
    }
    section = processing_details_section(processing)
    children = section.children
    texts = [c.children for c in children if isinstance(c, html.P)]
    joined = " ".join(str(t) for t in texts)
    assert "General DSC" in joined
    assert "savgol" in joined


def test_processing_details_section_appends_extra_lines():
    processing = {
        "workflow_template_label": "General TGA",
        "workflow_template_version": 1,
        "signal_pipeline": {"smoothing": {"method": "savgol"}},
    }
    extra = [html.P("Step Detection: dtg_peaks")]
    section = processing_details_section(processing, extra_lines=extra)
    children = section.children
    texts = [c.children for c in children if isinstance(c, html.P)]
    joined = " ".join(str(t) for t in texts)
    assert "dtg_peaks" in joined


# ---------------------------------------------------------------------------
# empty state helpers
# ---------------------------------------------------------------------------

def test_empty_result_msg():
    msg = empty_result_msg()
    assert isinstance(msg, html.P)
    assert "Run an analysis" in msg.children


def test_no_data_figure_msg():
    msg = no_data_figure_msg()
    assert isinstance(msg, html.P)
    assert "No data available" in msg.children


# ---------------------------------------------------------------------------
# resolve_sample_name
# ---------------------------------------------------------------------------

def test_resolve_sample_name_prefers_summary_name():
    name = resolve_sample_name({"sample_name": "Polymer A"}, {"dataset_key": "polymer_a.csv"})
    assert name == "Polymer A"


def test_resolve_sample_name_uses_fallback_when_summary_empty():
    name = resolve_sample_name({"sample_name": None}, {"dataset_key": "polymer_a.csv"},
                               fallback_display_name="Polymer A Display")
    assert name == "Polymer A Display"


def test_resolve_sample_name_strips_extension_from_key():
    name = resolve_sample_name({"sample_name": None}, {"dataset_key": "polymer_a.csv"})
    assert name == "polymer_a"


def test_resolve_sample_name_strips_various_extensions():
    for ext in (".csv", ".txt", ".dat", ".xls", ".xlsx"):
        name = resolve_sample_name({}, {"dataset_key": f"sample{ext}"})
        assert name == "sample", f"Failed for extension {ext}"


def test_resolve_sample_name_na_fallback():
    name = resolve_sample_name({}, {})
    assert name == "N/A"


def test_resolve_sample_name_ignores_blank_sample_name():
    name = resolve_sample_name({"sample_name": "  "}, {"dataset_key": "test.csv"})
    assert name == "test"


def test_resolve_sample_name_prefers_display_name_over_key():
    name = resolve_sample_name({"sample_name": ""},
                               {"dataset_key": "raw_data.csv"},
                               fallback_display_name="Calcium Oxalate")
    assert name == "Calcium Oxalate"
