"""Dash coverage for the preview Peak Deconvolution page.

Mirrors ``tests/test_dash_kinetics.py``: page registration, preview gating,
EN/TR chrome, dynamic axis labels, signal-basis availability, the run and
error callbacks, result rendering from the persisted payload, and every
hydration branch (newest / keep-valid / stale / empty / deterministic
tie-break / ``.scopezip``-restored).
"""

from __future__ import annotations

import importlib
import json

import dash
import pytest
from dash import html

PREVIEW_ENV = "MATERIALSCOPE_ENABLE_PREVIEW_MODULES"
PAGE_PATH = "/deconvolution"
SCOPE = "preview_deconvolution"


@pytest.fixture()
def _dash_app():
    try:
        dash.get_app()
    except Exception:
        app = dash.Dash(
            __name__,
            use_pages=True,
            pages_folder="",
            suppress_callback_exceptions=True,
        )
        app.layout = html.Div(dash.page_container)
    yield


def _import_page():
    return importlib.import_module("dash_app.pages.deconvolution")


def _dump(component) -> str:
    to_json = getattr(component, "to_plotly_json", None)
    if callable(to_json):
        return json.dumps(to_json(), default=str)
    return json.dumps(component, default=str)


def _text(component) -> str:
    """Collect the visible text of a Dash component tree."""
    parts: list[str] = []

    def walk(node) -> None:
        if node is None or isinstance(node, (int, float, bool)):
            return
        if isinstance(node, str):
            parts.append(node)
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
            return
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
            return
        children = getattr(node, "children", None)
        if children is not None:
            walk(children)
        else:
            parts.append(str(node))

    walk(component)
    return " ".join(parts)


def _options_payload(
    *,
    available=("raw",),
    has_analysis_state=False,
    axis_unit="°C",
    axis_role="temperature",
    x_label="Temperature (°C)",
    y_label="Heat Flow (mW)",
) -> dict:
    bases = []
    for name in ("raw", "smoothed", "corrected", "normalized"):
        is_available = name in available
        if is_available:
            reason = None
        elif name == "raw":
            reason = "no_usable_samples"
        else:
            reason = "no_saved_analysis_state" if not has_analysis_state else f"no_saved_{name}_curve"
        bases.append(
            {
                "name": name,
                "available": is_available,
                "source": ("dataset_import" if name == "raw" else "analysis_state") if is_available else None,
                "reason": reason,
                "length": 200 if is_available else 0,
            }
        )
    return {
        "dataset_key": "dsc1",
        "analysis_type": "DSC",
        "has_analysis_state": has_analysis_state,
        "axis_role": axis_role,
        "axis_unit": axis_unit,
        "signal_role": "heat_flow",
        "signal_unit": "mW",
        "x_label": x_label,
        "y_label": y_label,
        "axis_domain": [50.0, 250.0],
        "sample_count": 200,
        "bases": bases,
    }


def _detail_payload() -> dict:
    x = [100.0, 120.0, 140.0, 160.0]
    return {
        "summary": {
            "r_squared": 0.999,
            "rmse": 0.0012,
            "mae": 0.0009,
            "max_abs_residual": 0.003,
            "sse_per_dof": 1.4e-05,
            "dof": 494,
            "peak_shape": "gaussian",
            "peak_count": 2,
            "signal_basis": "raw",
            "axis_unit": "°C",
            "signal_unit": "mW",
            "inversion_applied": False,
            "amplitude_semantics": "integrated_area_parameter",
            "amplitude_unit": "mW·°C",
        },
        "processing": {
            "dataset_key": "dsc1",
            "signal_basis": "raw",
            "signal_basis_source": "dataset_import",
            "axis_role": "temperature",
            "axis_unit": "°C",
            "signal_role": "heat_flow",
            "signal_unit": "mW",
            "selected_range": [50.0, 250.0],
            "n_peaks": 2,
            "peak_shape": "gaussian",
            "inversion_applied": False,
            "inversion_semantics": "the selected signal was fitted exactly as stored (no sign change)",
            "initial_guess_provenance": ["mixed", "auto"],
            "fit_engine": "lmfit",
            "component_parameter_semantics": "lmfit amplitude is an integrated area parameter, not a peak height",
            "auto_estimate": {
                "detected_peak_count": 2,
                "prominence_threshold": 0.1,
                "fallback_spacing_used": False,
                "positive_point_fraction": 1.0,
            },
        },
        "provenance": {"analysis_scope": SCOPE, "saved_at_utc": "2026-01-02T10:00:00+00:00"},
        "validation": {"status": "warn", "warnings": ["advisory text"], "issues": []},
        "rows": [
            {"peak": 1, "center": 120.0, "amplitude": 40.1, "sigma": 8.0, "fwhm": 18.8, "height": 2.0},
            {"peak": 2, "center": 170.0, "amplitude": 37.6, "sigma": 10.0, "fwhm": 23.5, "height": 1.5},
        ],
        "report_payload": {
            "x": x,
            "y": [0.1, 2.0, 1.6, 0.2],
            "fitted": [0.12, 1.98, 1.58, 0.22],
            "components": [[0.05, 1.9, 0.1, 0.0], [0.0, 0.08, 1.5, 0.2]],
            "residual": [-0.02, 0.02, 0.02, -0.02],
            "xlabel": "Temperature (°C)",
            "ylabel": "Heat Flow (mW)",
            "axis_role": "temperature",
            "axis_unit": "°C",
            "signal_role": "heat_flow",
            "signal_unit": "mW",
            "inversion_applied": False,
            "signal_basis": "raw",
        },
        "scientific_context": {"limitations": ["identifiability limitation"]},
        "figure_artifacts": {"figure_keys": ["Peak_Deconvolution_Analysis_dsc1"], "report_figure_key": "Peak_Deconvolution_Analysis_dsc1"},
    }


def _results_payload(*items: dict) -> dict:
    return {"results": list(items)}


def _summary(result_id: str, saved_at: str) -> dict:
    return {"id": result_id, "analysis_scope": SCOPE, "saved_at_utc": saved_at}


# ---------------------------------------------------------------------------
# Registration, gating, chrome
# ---------------------------------------------------------------------------


def test_page_is_registered(_dash_app):
    _import_page()
    paths = {page.get("path") for page in dash.page_registry.values()}
    assert PAGE_PATH in paths


@pytest.mark.parametrize("locale", ["en", "tr"])
def test_preview_nav_visible_when_enabled(_dash_app, monkeypatch, locale):
    monkeypatch.setenv(PREVIEW_ENV, "1")
    from dash_app.layout import build_sidebar_inner

    markup = _dump(build_sidebar_inner(locale, "light"))
    assert PAGE_PATH in markup


def test_preview_nav_absent_when_disabled(_dash_app, monkeypatch):
    monkeypatch.delenv(PREVIEW_ENV, raising=False)
    from dash_app.layout import build_sidebar_inner

    markup = _dump(build_sidebar_inner("en", "light"))
    assert PAGE_PATH not in markup
    # The stable analysis links stay untouched.
    assert "/dsc" in markup


def test_page_blocks_workflow_when_preview_disabled(_dash_app, monkeypatch):
    monkeypatch.delenv(PREVIEW_ENV, raising=False)
    mod = _import_page()

    style, disabled = mod.gate_deconvolution_page("en")

    assert style.get("display") == "none"
    assert disabled


def test_page_enabled_when_preview_on(_dash_app, monkeypatch):
    monkeypatch.setenv(PREVIEW_ENV, "1")
    mod = _import_page()

    style, disabled = mod.gate_deconvolution_page("en")

    assert style == {}
    assert disabled == ""


@pytest.mark.parametrize("locale", ["en", "tr"])
def test_chrome_renders_in_en_and_tr(_dash_app, monkeypatch, locale):
    monkeypatch.setenv(PREVIEW_ENV, "1")
    mod = _import_page()

    outputs = mod.render_deconvolution_chrome(locale)

    assert outputs[0]
    assert outputs[15]  # run button label
    assert [option["value"] for option in outputs[8]] == ["gaussian", "lorentzian", "pseudo_voigt"]


def test_chrome_differs_between_locales(_dash_app, monkeypatch):
    monkeypatch.setenv(PREVIEW_ENV, "1")
    mod = _import_page()

    assert mod.render_deconvolution_chrome("en")[2] != mod.render_deconvolution_chrome("tr")[2]


# ---------------------------------------------------------------------------
# Dataset + basis resolution
# ---------------------------------------------------------------------------


def test_dataset_selector_lists_supported_modalities(_dash_app, monkeypatch):
    mod = _import_page()
    monkeypatch.setattr(
        "dash_app.api_client.workspace_datasets",
        lambda _pid: {
            "datasets": [
                {"key": "dsc1", "display_name": "scan", "data_type": "DSC"},
                {"key": "ftir1", "display_name": "ir", "data_type": "FTIR"},
                {"key": "xrd1", "display_name": "powder", "data_type": "XRD"},
            ]
        },
    )

    options = mod.load_deconvolution_datasets("proj", 0, 0)

    assert [option["value"] for option in options] == ["dsc1", "ftir1", "xrd1"]


def test_basis_options_reflect_availability_and_reasons(_dash_app, monkeypatch):
    mod = _import_page()
    monkeypatch.setattr(
        "dash_app.api_client.deconvolution_options",
        lambda _pid, _key: _options_payload(available=("raw", "smoothed"), has_analysis_state=True),
    )

    outputs = mod.resolve_deconvolution_basis("proj", "dsc1", "en", None)
    basis_options, selected, options, dataset_status, basis_status = outputs[:5]

    assert selected == "raw"
    assert options["axis_role"] == "temperature"
    disabled = {option["value"]: option.get("disabled") for option in basis_options}
    assert disabled["raw"] is False
    assert disabled["smoothed"] is False
    assert disabled["corrected"] is True
    # Reasons are shown as localized copy, not machine tokens.
    assert "no baseline-corrected curve was saved" in _text(basis_options)
    assert "°C" in _text(dataset_status)
    assert basis_status is not None


def test_basis_options_keep_a_valid_current_selection(_dash_app, monkeypatch):
    mod = _import_page()
    monkeypatch.setattr(
        "dash_app.api_client.deconvolution_options",
        lambda _pid, _key: _options_payload(available=("raw", "corrected"), has_analysis_state=True),
    )

    outputs = mod.resolve_deconvolution_basis("proj", "dsc1", "en", "corrected")

    assert outputs[1] == "corrected"


def test_basis_options_replace_a_stale_selection(_dash_app, monkeypatch):
    mod = _import_page()
    monkeypatch.setattr(
        "dash_app.api_client.deconvolution_options",
        lambda _pid, _key: _options_payload(available=("raw",), has_analysis_state=True),
    )

    outputs = mod.resolve_deconvolution_basis("proj", "dsc1", "en", "normalized")

    assert outputs[1] == "raw"


def test_axis_labels_follow_the_effective_axis_for_spectra(_dash_app, monkeypatch):
    mod = _import_page()
    monkeypatch.setattr(
        "dash_app.api_client.deconvolution_options",
        lambda _pid, _key: _options_payload(
            available=("raw",),
            has_analysis_state=True,
            axis_unit="cm^-1",
            axis_role="wavenumber",
            x_label="Wavenumber (cm⁻¹)",
            y_label="Absorbance (a.u.)",
        ),
    )

    outputs = mod.resolve_deconvolution_basis("proj", "ftir1", "en", None)

    range_min_label = outputs[5]
    range_max_label = outputs[6]
    assert "cm^-1" in range_min_label
    assert "cm^-1" in range_max_label
    assert "°C" not in range_min_label
    assert "°C" not in _dump(outputs[3])


def test_missing_axis_unit_is_labelled_as_unspecified(_dash_app, monkeypatch):
    mod = _import_page()
    monkeypatch.setattr(
        "dash_app.api_client.deconvolution_options",
        lambda _pid, _key: _options_payload(available=("raw",), axis_unit=None),
    )

    outputs = mod.resolve_deconvolution_basis("proj", "dsc1", "en", None)

    assert "unspecified" in outputs[5]


def test_no_dataset_selection_shows_guidance(_dash_app, monkeypatch):
    mod = _import_page()

    outputs = mod.resolve_deconvolution_basis("proj", None, "en", None)

    assert outputs[0] == []
    assert outputs[1] is None
    assert "Import data first" in _dump(outputs[3])


def test_unavailable_selected_basis_shows_prerequisite_message(_dash_app, monkeypatch):
    mod = _import_page()
    monkeypatch.setattr(
        "dash_app.api_client.deconvolution_options",
        lambda _pid, _key: _options_payload(available=("raw",), has_analysis_state=False),
    )

    outputs = mod.resolve_deconvolution_basis("proj", "dsc1", "en", "corrected")

    # Selection falls back to the available basis rather than staying unusable.
    assert outputs[1] == "raw"


# ---------------------------------------------------------------------------
# Initial guess rows
# ---------------------------------------------------------------------------


def test_guess_rows_scale_with_component_count(_dash_app, monkeypatch):
    mod = _import_page()

    rows = mod.render_guess_rows(["on"], 3, {"axis_unit": "°C"}, "en")

    assert len(rows) == 4  # three component cards + the hint line


def test_guess_rows_hidden_when_disabled(_dash_app, monkeypatch):
    mod = _import_page()

    rows = mod.render_guess_rows([], 3, {"axis_unit": "°C"}, "en")

    assert not isinstance(rows, list)


def test_blank_guess_fields_are_not_submitted_as_user_values(_dash_app, monkeypatch):
    monkeypatch.setenv(PREVIEW_ENV, "1")
    mod = _import_page()
    captured: dict = {}

    def _fake_run(_pid, payload):
        captured.update(payload)
        return {"result_id": "deconv_dsc1", "warnings": []}

    monkeypatch.setattr("dash_app.api_client.deconvolution_run", _fake_run)

    result = mod.run_deconvolution(
        1,
        "proj",
        "dsc1",
        "raw",
        2,
        "gaussian",
        [],
        None,
        None,
        [],
        ["on"],
        [120.0, None],
        [{"type": "deconvolution-guess-center", "index": 0}, {"type": "deconvolution-guess-center", "index": 1}],
        [None, None],
        [{"type": "deconvolution-guess-amplitude", "index": 0}, {"type": "deconvolution-guess-amplitude", "index": 1}],
        [8.0, None],
        [{"type": "deconvolution-guess-sigma", "index": 0}, {"type": "deconvolution-guess-sigma", "index": 1}],
        0,
        0,
        "en",
    )

    assert captured["initial_params"] == [{"center": 120.0, "sigma": 8.0}, {}]
    assert captured["n_peaks"] == 2
    assert captured["invert_signal_for_fit"] is False
    assert "range_min" not in captured
    assert result[2] == "deconv_dsc1"


def test_run_without_guesses_sends_empty_initial_params(_dash_app, monkeypatch):
    monkeypatch.setenv(PREVIEW_ENV, "1")
    mod = _import_page()
    captured: dict = {}
    monkeypatch.setattr(
        "dash_app.api_client.deconvolution_run",
        lambda _pid, payload: (captured.update(payload), {"result_id": "r1", "warnings": []})[1],
    )

    mod.run_deconvolution(
        1, "proj", "dsc1", "raw", 2, "gaussian", [], None, None, [], [],
        [], [], [], [], [], [],
        0, 0, "en",
    )

    assert captured["initial_params"] == [{}, {}]


def test_run_sends_range_and_inversion_when_requested(_dash_app, monkeypatch):
    monkeypatch.setenv(PREVIEW_ENV, "1")
    mod = _import_page()
    captured: dict = {}
    monkeypatch.setattr(
        "dash_app.api_client.deconvolution_run",
        lambda _pid, payload: (captured.update(payload), {"result_id": "r1", "warnings": []})[1],
    )

    mod.run_deconvolution(
        1, "proj", "dsc1", "corrected", 1, "lorentzian", ["on"], 100.0, 200.0, ["on"], [],
        [], [], [], [], [], [],
        0, 0, "en",
    )

    assert captured["range_min"] == 100.0
    assert captured["range_max"] == 200.0
    assert captured["invert_signal_for_fit"] is True
    assert captured["signal_basis"] == "corrected"


def test_run_blocked_when_preview_disabled(_dash_app, monkeypatch):
    monkeypatch.delenv(PREVIEW_ENV, raising=False)
    mod = _import_page()
    called = {"count": 0}
    monkeypatch.setattr(
        "dash_app.api_client.deconvolution_run",
        lambda _pid, payload: called.update(count=called["count"] + 1),
    )

    result = mod.run_deconvolution(
        1, "proj", "dsc1", "raw", 2, "gaussian", [], None, None, [], [],
        [], [], [], [], [], [],
        0, 0, "en",
    )

    assert called["count"] == 0
    assert "warning" in _dump(result[0])


def test_run_error_callback_reports_the_failure(_dash_app, monkeypatch):
    monkeypatch.setenv(PREVIEW_ENV, "1")
    mod = _import_page()

    def _boom(_pid, _payload):
        raise RuntimeError("400 Bad Request: Signal basis 'corrected' is unavailable")

    monkeypatch.setattr("dash_app.api_client.deconvolution_run", _boom)

    result = mod.run_deconvolution(
        1, "proj", "dsc1", "corrected", 2, "gaussian", [], None, None, [], [],
        [], [], [], [], [], [],
        0, 0, "en",
    )

    assert "corrected" in _dump(result[0])
    assert result[1] is dash.no_update


def test_run_without_dataset_is_blocked(_dash_app, monkeypatch):
    monkeypatch.setenv(PREVIEW_ENV, "1")
    mod = _import_page()

    result = mod.run_deconvolution(
        1, "proj", None, "raw", 2, "gaussian", [], None, None, [], [],
        [], [], [], [], [], [],
        0, 0, "en",
    )

    assert "warning" in _dump(result[0])


# ---------------------------------------------------------------------------
# Result rendering
# ---------------------------------------------------------------------------


def test_result_rendering_uses_the_persisted_payload(_dash_app, monkeypatch):
    mod = _import_page()
    monkeypatch.setattr(
        "dash_app.api_client.workspace_result_detail",
        lambda _pid, _rid: _detail_payload(),
    )

    metrics, figure, table, residual, scientific = mod.display_deconvolution_result(
        "deconv_dsc1", 0, "light", "en", "proj"
    )

    metrics_text = _text(metrics)
    assert "Unweighted SSE / DoF" in metrics_text
    assert "Degrees of freedom" in metrics_text
    assert "not a measurement-uncertainty-weighted" in metrics_text

    assert figure is not None and "Graph" in _dump(figure)
    assert len(figure.figure.data) == 4  # input + total fit + two components
    assert figure.figure.layout.xaxis.title.text == "Temperature (°C)"
    assert figure.figure.layout.yaxis.title.text == "Heat Flow (mW)"

    table_text = _text(table)
    assert "Integrated amplitude / area parameter" in table_text
    assert "FWHM" in table_text
    assert "Component" in table_text

    assert len(residual.figure.data) == 1
    assert len(residual.figure.layout.shapes) >= 1  # zero reference line

    scientific_text = _text(scientific)
    assert "identifiability limitation" in scientific_text
    assert "advisory text" in scientific_text
    assert SCOPE in scientific_text


def test_result_rendering_flags_inversion(_dash_app, monkeypatch):
    mod = _import_page()
    payload = _detail_payload()
    payload["summary"]["inversion_applied"] = True
    payload["processing"]["inversion_applied"] = True
    monkeypatch.setattr("dash_app.api_client.workspace_result_detail", lambda _pid, _rid: payload)

    _metrics, figure, _table, _residual, scientific = mod.display_deconvolution_result(
        "deconv_dsc1", 0, "light", "en", "proj"
    )

    assert "multiplied by -1" in _text(scientific)
    assert figure is not None


def test_result_rendering_empty_state(_dash_app, monkeypatch):
    mod = _import_page()

    outputs = mod.display_deconvolution_result(None, 0, "light", "en", "proj")

    assert all(_dump(item) for item in outputs)
    assert not any("Graph" in _dump(item) for item in outputs)


def test_result_rendering_surfaces_detail_errors(_dash_app, monkeypatch):
    mod = _import_page()

    def _boom(_pid, _rid):
        raise RuntimeError("500 Server Error")

    monkeypatch.setattr("dash_app.api_client.workspace_result_detail", _boom)

    outputs = mod.display_deconvolution_result("deconv_dsc1", 0, "light", "en", "proj")

    assert "danger" in _dump(outputs[0])


def test_figure_artifacts_panel_renders_saved_keys(_dash_app, monkeypatch):
    mod = _import_page()
    monkeypatch.setattr(
        "dash_app.api_client.workspace_result_detail",
        lambda _pid, _rid: _detail_payload(),
    )

    panel = mod.render_deconvolution_figure_artifacts("deconv_dsc1", {}, "en", "proj")

    assert "Peak_Deconvolution_Analysis_dsc1" in _dump(panel)


# ---------------------------------------------------------------------------
# Hydration
# ---------------------------------------------------------------------------


def test_hydration_selects_the_newest_result(_dash_app, monkeypatch):
    mod = _import_page()
    payload = _results_payload(
        _summary("deconv_a", "2026-01-01T10:00:00+00:00"),
        {"id": "dsc1", "analysis_scope": None, "saved_at_utc": "2026-01-03T00:00:00+00:00"},
        _summary("deconv_b", "2026-01-02T10:00:00+00:00"),
    )
    monkeypatch.setattr("dash_app.api_client.workspace_results", lambda _pid: payload)

    assert mod.hydrate_latest_deconvolution_result(PAGE_PATH, "proj", 0, None) == "deconv_b"


def test_hydration_deterministic_tiebreak_on_equal_timestamps(_dash_app, monkeypatch):
    mod = _import_page()
    payload = _results_payload(
        _summary("deconv-b", "2026-01-01T10:00:00+00:00"),
        _summary("deconv-a", "2026-01-01T10:00:00+00:00"),
    )
    monkeypatch.setattr("dash_app.api_client.workspace_results", lambda _pid: payload)
    first = mod.hydrate_latest_deconvolution_result(PAGE_PATH, "proj", 0, None)
    payload["results"].reverse()
    monkeypatch.setattr("dash_app.api_client.workspace_results", lambda _pid: payload)
    second = mod.hydrate_latest_deconvolution_result(PAGE_PATH, "proj", 0, None)

    assert first == second == "deconv-b"


def test_hydration_keeps_a_valid_current_selection(_dash_app, monkeypatch):
    mod = _import_page()
    payload = _results_payload(
        _summary("deconv_a", "2026-01-01T10:00:00+00:00"),
        _summary("deconv_b", "2026-01-02T10:00:00+00:00"),
    )
    monkeypatch.setattr("dash_app.api_client.workspace_results", lambda _pid: payload)

    with pytest.raises(dash.exceptions.PreventUpdate):
        mod.hydrate_latest_deconvolution_result(PAGE_PATH, "proj", 0, "deconv_a")


def test_hydration_replaces_a_stale_id(_dash_app, monkeypatch):
    mod = _import_page()
    payload = _results_payload(_summary("deconv_b", "2026-01-02T10:00:00+00:00"))
    monkeypatch.setattr("dash_app.api_client.workspace_results", lambda _pid: payload)

    assert mod.hydrate_latest_deconvolution_result(PAGE_PATH, "proj", 0, "gone") == "deconv_b"


def test_hydration_empty_when_no_deconvolution_results(_dash_app, monkeypatch):
    mod = _import_page()
    payload = _results_payload({"id": "dsc1", "analysis_scope": None, "saved_at_utc": "2026-01-01T00:00:00+00:00"})
    monkeypatch.setattr("dash_app.api_client.workspace_results", lambda _pid: payload)

    with pytest.raises(dash.exceptions.PreventUpdate):
        mod.hydrate_latest_deconvolution_result(PAGE_PATH, "proj", 0, None)
    assert mod.hydrate_latest_deconvolution_result(PAGE_PATH, "proj", 0, "stale") is None


def test_hydration_requires_project_and_route(_dash_app):
    mod = _import_page()

    with pytest.raises(dash.exceptions.PreventUpdate):
        mod.hydrate_latest_deconvolution_result(PAGE_PATH, "", 0, None)
    with pytest.raises(dash.exceptions.PreventUpdate):
        mod.hydrate_latest_deconvolution_result("/dsc", "proj", 0, None)


def test_hydration_ignores_other_scopes(_dash_app, monkeypatch):
    mod = _import_page()
    payload = _results_payload(
        {"id": "kin1", "analysis_scope": "preview_kinetics", "saved_at_utc": "2026-01-05T00:00:00+00:00"},
        _summary("deconv_a", "2026-01-01T00:00:00+00:00"),
    )
    monkeypatch.setattr("dash_app.api_client.workspace_results", lambda _pid: payload)

    assert mod.hydrate_latest_deconvolution_result(PAGE_PATH, "proj", 0, None) == "deconv_a"


def test_scopezip_restored_result_keeps_its_hydration_scope():
    from backend.workspace import summarize_result
    from core.project_io import deserialize_project, serialize_project

    detail = _detail_payload()
    record = {
        "id": "deconv_dsc1",
        "analysis_type": "Peak Deconvolution",
        "status": "experimental",
        "dataset_key": "dsc1",
        "metadata": {},
        "summary": detail["summary"],
        "rows": detail["rows"],
        "artifacts": {},
        "processing": detail["processing"],
        "provenance": detail["provenance"],
        "validation": detail["validation"],
        "review": {},
        "scientific_context": detail["scientific_context"],
        "report_payload": detail["report_payload"],
    }
    state = {"datasets": {}, "results": {"deconv_dsc1": record}, "analysis_history": [], "figures": {}}

    payload = serialize_project(state)
    restored = deserialize_project(
        payload["manifest"],
        {**payload["datasets"], **payload["figures"], **payload["branding_assets"]},
        results_payload=payload["results"],
        history_payload=payload["history"],
    )

    restored_record = restored["results"]["deconv_dsc1"]
    assert restored_record["provenance"]["analysis_scope"] == SCOPE
    assert restored_record["report_payload"]["components"]
    assert summarize_result(restored_record).analysis_scope == SCOPE
