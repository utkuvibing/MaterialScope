"""Tests for shared analysis-page primitives (dash_app.components.analysis_page)."""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html
import plotly.graph_objects as go

import dash_app.components.analysis_page as analysis_page_mod
from dash_app.components.analysis_boilerplate import (
    build_apply_preset_card,
    build_collapsible_section,
    build_load_saveas_preset_card,
    build_processing_history_card,
    build_split_raw_metadata_panel,
    build_validation_quality_card,
)
from dash_app.components.analysis_page import (
    finalized_validation_warning_issue_counts,
    capture_result_figure_from_layout,
    register_result_figure_from_layout_children,
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
from dash_app.components.figure_artifacts import (
    build_figure_artifacts_panel,
    figure_action_metadata,
    figure_artifact_button_labels,
    figure_artifact_count,
    ordered_figure_preview_keys,
    primary_report_figure_label,
)
from dash_app.components.processing_inputs import (
    coerce_float_non_negative,
    coerce_float_positive,
    coerce_int_positive,
)


# ---------------------------------------------------------------------------
# shared boilerplate extraction
# ---------------------------------------------------------------------------

def test_processing_input_coercion_helpers_preserve_duplicate_page_semantics():
    assert coerce_int_positive(None, default=4, minimum=2) == 4
    assert coerce_int_positive("", default=1, minimum=3) == 3
    assert coerce_int_positive("6.7", default=1, minimum=3) == 6
    assert coerce_int_positive("bad", default=1, minimum=3) == 3

    assert coerce_float_positive(None, default=2.0, minimum=0.5) == 2.0
    assert coerce_float_positive("-1", default=2.0, minimum=0.5) == 0.5
    assert coerce_float_positive("nan", default=2.0, minimum=0.5) == 2.0
    assert coerce_float_positive("1.25", default=2.0, minimum=0.5) == 1.25

    assert coerce_float_non_negative(None, default=-1.0) == 0.0
    assert coerce_float_non_negative("-0.2", default=1.0) == 1.0
    assert coerce_float_non_negative("nan", default=1.0) == 1.0
    assert coerce_float_non_negative("0.2", default=1.0) == 0.2


def test_processing_history_card_uses_supplied_contract_ids():
    card = build_processing_history_card(
        title_id="abc-processing-history-title",
        hint_id="abc-processing-history-hint",
        undo_button_id="abc-processing-undo-btn",
        redo_button_id="abc-processing-redo-btn",
        reset_button_id="abc-processing-reset-btn",
        status_id="abc-history-status",
    )
    rendered = str(card)
    for expected in (
        "abc-processing-history-title",
        "abc-processing-history-hint",
        "abc-processing-undo-btn",
        "abc-processing-redo-btn",
        "abc-processing-reset-btn",
        "abc-history-status",
    ):
        assert expected in rendered


def test_preset_card_variants_use_supplied_prefix_ids():
    apply_card = build_apply_preset_card(id_prefix="abc")
    apply_rendered = str(apply_card)
    for expected in (
        "abc-preset-card-title",
        "abc-preset-select",
        "abc-preset-apply-btn",
        "abc-preset-delete-btn",
        "abc-preset-save-name",
        "abc-preset-save-btn",
        "abc-preset-status",
    ):
        assert expected in apply_rendered

    load_card = build_load_saveas_preset_card(id_prefix="xyz")
    load_rendered = str(load_card)
    for expected in (
        "xyz-preset-card-title",
        "xyz-preset-loaded-line",
        "xyz-preset-dirty-flag",
        "xyz-preset-select",
        "xyz-preset-load-btn",
        "xyz-preset-delete-btn",
        "xyz-preset-save-name",
        "xyz-preset-save-btn",
        "xyz-preset-saveas-btn",
        "xyz-preset-status",
    ):
        assert expected in load_rendered


def test_collapsible_section_preserves_details_contract_and_suffix():
    suffix = [dbc.Badge("2 warnings", color="warning", className="ms-2", pill=True)]
    details = build_collapsible_section("en", "dash.analysis.dsc.quality.card_title", html.Div("body"), open=True, summary_suffix=suffix)
    rendered = str(details)
    assert "ta-ms-details mb-0" in rendered
    assert "ta-details-summary" in rendered
    assert "ta-details-body mt-2" in rendered
    assert "ta-details-chevron" in rendered
    assert "Validation and quality" in rendered
    assert "2 warnings" in rendered
    assert details.open is True


def test_validation_quality_card_accepts_modality_prefix_and_count_policy():
    detail = {
        "validation": {
            "status": "ok",
            "warning_count": 4,
            "issue_count": 3,
            "warnings": ["one"],
            "issues": [],
        }
    }
    legacy_counts = build_validation_quality_card(
        detail,
        {},
        "en",
        i18n_prefix="dash.analysis.dsc.quality",
        derive_counts_from_lists=False,
    )
    assert " 4" in str(legacy_counts)
    assert " 3" in str(legacy_counts)

    list_counts = build_validation_quality_card(
        detail,
        {},
        "en",
        i18n_prefix="dash.analysis.ftir.quality",
        derive_counts_from_lists=True,
        include_attention_badges=True,
        open_when_attention=True,
    )
    rendered = str(list_counts)
    assert "1 warning" in rendered
    assert "0" in rendered
    assert list_counts.open is True


def test_split_raw_metadata_panel_accepts_key_set_and_formatter():
    panel = build_split_raw_metadata_panel(
        {"sample_name": "A", "technical": {"x": 1}},
        "en",
        i18n_prefix="dash.analysis.dsc.raw_metadata",
        user_facing_keys=frozenset({"sample_name"}),
        value_formatter=lambda value: str(value).strip() if value is not None else None,
    )
    rendered = str(panel)
    assert "sample_name" in rendered
    assert "technical" in rendered
    assert "Technical details" in rendered


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
        "validation": {"status": "pass", "warning_count": 0, "warnings": []},
    }
    alert, saved, result_id = interpret_run_result(result)
    assert saved is True
    assert result_id == "dsc_test"
    assert isinstance(alert, dbc.Alert)
    assert alert.color == "success"


def test_finalized_validation_warning_issue_counts_prefers_lists():
    assert finalized_validation_warning_issue_counts(
        {"warnings": ["a", "b"], "issues": ["x"], "warning_count": 99, "issue_count": 99}
    ) == (2, 1)


def test_interpret_run_result_saved_ignores_stale_warning_count():
    result = {
        "execution_status": "saved",
        "result_id": "ftir_test",
        "failure_reason": None,
        "validation": {"status": "warn", "warning_count": 11, "warnings": ["w"] * 10, "issues": []},
    }
    alert, saved, result_id = interpret_run_result(result, locale_data="en")
    assert saved is True
    assert result_id == "ftir_test"
    body = str(alert)
    assert "warnings: 10" in body
    assert "warnings: 11" not in body


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


# ---------------------------------------------------------------------------
# figure capture helper
# ---------------------------------------------------------------------------

def test_extract_graph_figure_payload_preserves_visual_order():
    result_fig = go.Figure(data=[go.Scatter(x=[1], y=[1], name="result")])
    debug_fig = go.Figure(data=[go.Scatter(x=[1], y=[2], name="debug")])
    children = html.Div(
        [
            html.Div(dcc.Graph(figure=result_fig), id="result-slot"),
            html.Details([html.Summary("Debug"), html.Div(dcc.Graph(figure=debug_fig))]),
        ]
    )

    payload = analysis_page_mod._extract_graph_figure_payload(children)
    assert payload is result_fig


def test_capture_result_figure_from_layout_registers_primary_figure(monkeypatch):
    import dash_app.api_client as api_client

    register_calls: list[dict] = []

    monkeypatch.setattr(
        analysis_page_mod,
        "render_plotly_figure_png",
        lambda _fig, **_k: (b"\x89PNG\r\n\x1a\nFAKE", None),
    )
    monkeypatch.setattr(
        api_client,
        "workspace_result_detail",
        lambda *_a, **_k: {"result": {"dataset_key": "synthetic_dsc"}},
    )
    monkeypatch.setattr(
        api_client,
        "register_result_figure",
        lambda pid, rid, png_bytes, *, label, replace=False: register_calls.append(
            {"pid": pid, "rid": rid, "bytes": bytes(png_bytes), "label": label, "replace": replace}
        )
        or {"figure_key": label, "figure_keys": [label]},
    )

    children = html.Div(
        dcc.Graph(
            figure=go.Figure(
                data=[go.Scatter(x=[100.0, 200.0], y=[0.1, -0.2], mode="lines", name="Corrected")]
            )
        )
    )
    captured = capture_result_figure_from_layout(
        result_id="dsc_result_1",
        project_id="proj-1",
        figure_children=children,
        captured={},
        analysis_type="DSC",
    )

    assert captured["dsc_result_1"]["status"] == "ok"
    assert captured["dsc_result_1"]["label"] == "DSC Analysis - synthetic_dsc"
    assert register_calls == [
        {
            "pid": "proj-1",
            "rid": "dsc_result_1",
            "bytes": b"\x89PNG\r\n\x1a\nFAKE",
            "label": "DSC Analysis - synthetic_dsc",
            "replace": True,
        }
    ]


def test_capture_result_figure_from_layout_reads_serialized_children(monkeypatch):
    import dash_app.api_client as api_client

    monkeypatch.setattr(analysis_page_mod, "render_plotly_figure_png", lambda _fig, **_k: (b"PNG", None))
    monkeypatch.setattr(
        api_client,
        "workspace_result_detail",
        lambda *_a, **_k: {"result": {"dataset_key": "serialized_source"}},
    )
    monkeypatch.setattr(
        api_client,
        "register_result_figure",
        lambda _pid, _rid, _png_bytes, *, label, replace=False: {"figure_key": label, "figure_keys": [label]},
    )

    serialized_children = {
        "props": {
            "children": [
                {
                    "props": {
                        "figure": {
                            "data": [{"type": "scatter", "mode": "lines", "x": [1, 2], "y": [3, 4]}],
                            "layout": {},
                        }
                    }
                }
            ]
        }
    }
    captured = capture_result_figure_from_layout(
        result_id="ftir_result_1",
        project_id="proj-2",
        figure_children=serialized_children,
        captured={},
        analysis_type="FTIR",
    )
    assert captured["ftir_result_1"]["status"] == "ok"
    assert captured["ftir_result_1"]["label"] == "FTIR Analysis - serialized_source"


def test_register_result_figure_from_layout_children_honors_replace_flag(monkeypatch):
    import dash_app.api_client as api_client

    register_calls: list[dict] = []

    monkeypatch.setattr(
        analysis_page_mod,
        "render_plotly_figure_png",
        lambda _fig, **_k: (b"\x89PNG\r\n\x1a\nFAKE", None),
    )
    monkeypatch.setattr(
        api_client,
        "register_result_figure",
        lambda pid, rid, png_bytes, *, label, replace=False: register_calls.append(
            {"pid": pid, "rid": rid, "label": label, "replace": replace}
        )
        or {"figure_key": label, "figure_keys": [label]},
    )

    children = html.Div(
        dcc.Graph(
            figure=go.Figure(
                data=[go.Scatter(x=[1.0, 2.0], y=[1.0, 2.0], mode="lines", name="X")]
            )
        )
    )
    snap = register_result_figure_from_layout_children(
        figure_children=children,
        project_id="p1",
        result_id="r1",
        label="XRD Snapshot - ds - 20260101T000000Z",
        replace=False,
    )
    assert snap["status"] == "ok"
    assert register_calls[-1]["replace"] is False

    rep = register_result_figure_from_layout_children(
        figure_children=children,
        project_id="p1",
        result_id="r1",
        label="XRD Analysis - ds",
        replace=True,
    )
    assert rep["status"] == "ok"
    assert register_calls[-1]["replace"] is True


def test_register_result_figure_from_layout_children_skips_without_graph():
    out = register_result_figure_from_layout_children(
        figure_children=html.Div("no graph"),
        project_id="p",
        result_id="r",
        label="L",
        replace=False,
    )
    assert out["status"] == "skipped"
    assert out["reason"] == "no_graph_in_layout"


# ---------------------------------------------------------------------------
# figure artifact pure helpers
# ---------------------------------------------------------------------------

def test_figure_artifact_helpers_order_labels_and_actions():
    artifacts = {
        "figure_keys": ["DSC Snapshot - ds - t1", "DSC Analysis - ds", "DSC Snapshot - ds - t1"],
        "report_figure_key": "DSC Analysis - ds",
    }
    assert ordered_figure_preview_keys(artifacts) == ["DSC Analysis - ds", "DSC Snapshot - ds - t1"]
    assert figure_artifact_count(artifacts) == 2
    assert primary_report_figure_label("dsc", "ds", "rid") == "DSC Analysis - ds"

    snapshot = figure_action_metadata(
        "snapshot",
        analysis_type="DSC",
        dataset_key="ds",
        result_id="rid",
        snapshot_stamp="20260423T000000Z",
    )
    assert snapshot["label"] == "DSC Snapshot - ds - 20260423T000000Z"
    assert snapshot["replace"] is False

    report = figure_action_metadata("report", analysis_type="DSC", dataset_key="ds", result_id="rid")
    assert report["label"] == "DSC Analysis - ds"
    assert report["replace"] is True


def test_figure_artifact_panel_and_labels_render():
    snap_label, report_label, details_label = figure_artifact_button_labels("en")
    assert snap_label == "Snapshot"
    assert report_label == "Report figure"
    assert "Saved figures" in details_label

    empty = build_figure_artifacts_panel({}, "en")
    assert "No saved figures" in str(empty)

    panel = build_figure_artifacts_panel(
        {
            "figure_keys": ["DSC Analysis - ds", "DSC Snapshot - ds - t"],
            "report_figure_key": "DSC Analysis - ds",
            "report_figure_status": "captured",
        },
        "en",
        previews={"DSC Analysis - ds": "data:image/png;base64,AAA"},
    )
    s = str(panel)
    assert "DSC Analysis - ds" in s
    assert "Show registry keys" in s
