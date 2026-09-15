"""
test_tga_depth.py
-----------------
PR-17 — TGA scientific depth.

Covers:
- Residual mass at declared target temperatures (interpolated on the
  smoothed curve; out-of-range / non-finite targets withheld explicitly).
- DTG expressed in %/min — emitted only when a traceable heating rate
  exists (resolve_beta provenance gate); otherwise withheld with a reason.
- Smoothing windows expressed in degC converted to points via the real
  temperature-axis spacing.
- Batch-runner, serialization, and archive round-trip plumbing.
"""

import numpy as np
import pytest

from core.tga_processor import (
    TGAProcessor,
    TGAResult,
    _celsius_to_points,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _step(t, center, width):
    return 1.0 / (1.0 + np.exp(-(t - center) / width))


def _two_step_mass(t):
    """Two clean decomposition steps: -30% @ ~300 degC, -50% @ ~600 degC."""
    return 100.0 - 30.0 * _step(t, 300.0, 8.0) - 50.0 * _step(t, 600.0, 10.0)


@pytest.fixture
def temperature_axis():
    # 0.5 degC spacing — matches a 10 K/min ramp sampled at 1.2 s intervals.
    return np.linspace(30.0, 800.0, 1541)


@pytest.fixture
def mass_signal(temperature_axis):
    return _two_step_mass(temperature_axis)


def _make_processor(temperature_axis, mass_signal, **metadata):
    return TGAProcessor(temperature_axis, mass_signal, metadata=metadata)


# ---------------------------------------------------------------------------
# _celsius_to_points
# ---------------------------------------------------------------------------

class TestCelsiusToPoints:
    def test_half_degree_spacing(self, temperature_axis):
        # 5 degC / 0.5 degC-per-sample = 10 points
        assert _celsius_to_points(temperature_axis, 5.0) == 10

    def test_result_never_exceeds_data_length(self):
        t = np.linspace(0.0, 100.0, 21)  # 5 degC spacing
        assert _celsius_to_points(t, 500.0) <= 21

    def test_degenerate_axis_raises(self):
        with pytest.raises(ValueError, match="temperature axis"):
            _celsius_to_points(np.array([50.0, 50.0, 50.0]), 5.0)


# ---------------------------------------------------------------------------
# Temperature-domain smoothing windows
# ---------------------------------------------------------------------------

class TestCelsiusSmoothing:
    def test_window_celsius_converted_and_recorded(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        p.smooth(window_celsius=5.0).compute_dtg()
        result = p.get_result()
        step = result.metadata["steps"][0]
        assert step["step"] == "smooth"
        assert step["window_celsius"] == pytest.approx(5.0)
        # 5 degC / 0.5 degC = 10 -> forced odd -> 11
        assert step["window_length_effective"] == 11

    def test_window_celsius_overrides_point_window(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        p.smooth(window_celsius=5.0, window_length=51).compute_dtg()
        step = p.get_result().metadata["steps"][0]
        assert step["window_length_effective"] == 11

    def test_sigma_celsius_for_gaussian(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        p.smooth(method="gaussian", sigma_celsius=2.5).compute_dtg()
        step = p.get_result().metadata["steps"][0]
        assert step["sigma_celsius"] == pytest.approx(2.5)
        # 2.5 degC / 0.5 degC-per-sample = sigma of 5 samples
        assert step["sigma_effective"] == pytest.approx(5.0)

    def test_window_celsius_rejected_for_gaussian(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        with pytest.raises(ValueError, match="sigma_celsius"):
            p.smooth(method="gaussian", window_celsius=5.0)

    def test_point_window_still_works(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        p.smooth(window_length=15, polyorder=3).compute_dtg()
        result = p.get_result()
        assert result.smoothed_signal is not None
        step = result.metadata["steps"][0]
        assert "window_celsius" not in step

    def test_dtg_window_celsius_applies(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        p.smooth().compute_dtg(window_celsius=5.0)
        assert p.get_result().dtg_signal is not None


# ---------------------------------------------------------------------------
# Residual mass at target temperature
# ---------------------------------------------------------------------------

class TestResidualMass:
    def test_known_fixture(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        p.smooth().compute_dtg().measure_residual_mass([350.0, 700.0])
        points = p.get_result().residual_mass_points
        assert len(points) == 2
        # After the -30% step at 300 degC the residual is ~70%.
        assert points[0].target_temperature == pytest.approx(350.0)
        assert points[0].residual_mass_percent == pytest.approx(70.0, abs=0.5)
        # After both steps only the 20% residue remains.
        assert points[1].residual_mass_percent == pytest.approx(20.0, abs=0.5)

    def test_before_any_step(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        p.smooth().compute_dtg().measure_residual_mass([100.0])
        assert p.get_result().residual_mass_points[0].residual_mass_percent == pytest.approx(100.0, abs=0.5)

    def test_out_of_range_withheld(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        p.smooth().compute_dtg().measure_residual_mass([10.0, 900.0])
        points = p.get_result().residual_mass_points
        assert all(pt.residual_mass_percent is None for pt in points)
        assert all(pt.withheld_reason == "target_outside_measured_range" for pt in points)

    def test_non_finite_target_withheld(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        p.smooth().compute_dtg().measure_residual_mass([float("nan"), float("inf"), "not-a-number"])
        points = p.get_result().residual_mass_points
        assert len(points) == 3
        assert all(pt.withheld_reason == "target_not_finite" for pt in points)
        assert all(pt.residual_mass_percent is None for pt in points)

    def test_residual_mass_mg_requires_initial_mass(self, temperature_axis, mass_signal):
        p = TGAProcessor(temperature_axis, mass_signal, initial_mass_mg=12.5)
        p.smooth().compute_dtg().measure_residual_mass([700.0])
        point = p.get_result().residual_mass_points[0]
        assert point.residual_mass_mg == pytest.approx(
            point.residual_mass_percent / 100.0 * 12.5, rel=1e-6
        )

    def test_residual_mass_mg_none_without_initial_mass(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        p.smooth().compute_dtg().measure_residual_mass([700.0])
        assert p.get_result().residual_mass_points[0].residual_mass_mg is None

    def test_requires_smooth_first(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        with pytest.raises(RuntimeError, match="smooth"):
            p.measure_residual_mass([350.0])

    def test_pipeline_step_recorded(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        p.smooth().compute_dtg().measure_residual_mass([350.0, 900.0])
        steps = p.get_result().metadata["steps"]
        record = next(s for s in steps if s["step"] == "measure_residual_mass")
        assert record["evaluated"] == 1
        assert record["withheld"] == 1


# ---------------------------------------------------------------------------
# DTG %/min honesty gate
# ---------------------------------------------------------------------------

class TestDtGPerMin:
    def test_traceable_beta_produces_per_min(self, temperature_axis, mass_signal):
        p = _make_processor(
            temperature_axis, mass_signal,
            heating_rate=10.0, heating_rate_source="parsed",
        )
        p.smooth().compute_dtg().compute_dtg_per_min()
        result = p.get_result()
        assert result.dtg_per_min_basis == "beta_traceable"
        assert result.dtg_per_min_withheld_reason is None
        np.testing.assert_allclose(result.dtg_per_min, result.dtg_signal * 10.0)

    def test_user_source_accepted(self, temperature_axis, mass_signal):
        p = _make_processor(
            temperature_axis, mass_signal,
            heating_rate=20.0, heating_rate_source="user",
        )
        p.smooth().compute_dtg().compute_dtg_per_min()
        assert p.get_result().dtg_per_min_basis == "beta_traceable"

    def test_missing_heating_rate_withheld(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        p.smooth().compute_dtg().compute_dtg_per_min()
        result = p.get_result()
        assert result.dtg_per_min is None
        assert result.dtg_per_min_basis == "withheld"
        assert result.dtg_per_min_withheld_reason == "heating_rate_missing"

    def test_rate_without_provenance_withheld(self, temperature_axis, mass_signal):
        # A bare heating rate with no source is legacy — never trusted.
        p = _make_processor(temperature_axis, mass_signal, heating_rate=10.0)
        p.smooth().compute_dtg().compute_dtg_per_min()
        result = p.get_result()
        assert result.dtg_per_min is None
        assert result.dtg_per_min_withheld_reason == "legacy_unknown"

    def test_unverified_source_withheld(self, temperature_axis, mass_signal):
        p = _make_processor(
            temperature_axis, mass_signal,
            heating_rate=10.0, heating_rate_source="inferred_from_spacing",
        )
        p.smooth().compute_dtg().compute_dtg_per_min()
        result = p.get_result()
        assert result.dtg_per_min is None
        assert result.dtg_per_min_withheld_reason == "heating_rate_unverified"

    def test_invalid_rate_withheld(self, temperature_axis, mass_signal):
        p = _make_processor(
            temperature_axis, mass_signal,
            heating_rate=-5.0, heating_rate_source="parsed",
        )
        p.smooth().compute_dtg().compute_dtg_per_min()
        result = p.get_result()
        assert result.dtg_per_min is None
        assert result.dtg_per_min_withheld_reason == "heating_rate_invalid"

    def test_not_computed_by_default(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        p.smooth().compute_dtg()
        result = p.get_result()
        assert result.dtg_per_min_basis == "not_computed"
        assert result.dtg_per_min is None

    def test_requires_dtg_first(self, temperature_axis, mass_signal):
        p = _make_processor(
            temperature_axis, mass_signal,
            heating_rate=10.0, heating_rate_source="parsed",
        )
        p.smooth()
        with pytest.raises(RuntimeError, match="compute_dtg"):
            p.compute_dtg_per_min()

    def test_metadata_step_records_basis(self, temperature_axis, mass_signal):
        p = _make_processor(temperature_axis, mass_signal)
        p.smooth().compute_dtg().compute_dtg_per_min()
        record = next(
            s for s in p.get_result().metadata["steps"] if s["step"] == "compute_dtg_per_min"
        )
        assert record["basis"] == "withheld"
        assert record["withheld_reason"] == "heating_rate_missing"
        assert record["heating_rate_k_min"] is None


# ---------------------------------------------------------------------------
# Batch-runner plumbing
# ---------------------------------------------------------------------------

class TestBatchRunnerPlumbing:
    def _dataset(self, temperature_axis, mass_signal, **extra_metadata):
        import pandas as pd
        from core.data_io import ThermalDataset

        metadata = {
            "sample_name": "DepthTGA",
            "sample_mass": 10.0,
            "display_name": "Depth TGA",
        }
        metadata.update(extra_metadata)
        return ThermalDataset(
            data=pd.DataFrame({"temperature": temperature_axis, "signal": mass_signal}),
            metadata=metadata,
            data_type="TGA",
            units={"temperature": "degC", "signal": "%"},
            original_columns={"temperature": "temperature", "signal": "signal"},
            file_path="",
        )

    def test_residual_mass_flows_to_record(self, temperature_axis, mass_signal):
        from core.batch_runner import execute_batch_template

        dataset = self._dataset(temperature_axis, mass_signal)
        outcome = execute_batch_template(
            dataset_key="depth_tga",
            dataset=dataset,
            analysis_type="TGA",
            workflow_template_id="tga.general",
            existing_processing={
                "analysis_steps": {
                    "residual_mass": {"enabled": True, "targets": [350.0, 900.0]}
                }
            },
        )
        assert outcome["status"] == "saved"
        points = outcome["record"]["summary"]["residual_mass_points"]
        assert len(points) == 2
        assert points[0]["residual_mass_percent"] == pytest.approx(70.0, abs=0.5)
        assert points[1]["withheld_reason"] == "target_outside_measured_range"

    def test_dtg_per_min_traceable_in_state(self, temperature_axis, mass_signal):
        from core.batch_runner import execute_batch_template

        dataset = self._dataset(
            temperature_axis, mass_signal,
            heating_rate=10.0, heating_rate_source="parsed",
        )
        outcome = execute_batch_template(
            dataset_key="depth_tga",
            dataset=dataset,
            analysis_type="TGA",
            workflow_template_id="tga.general",
        )
        assert outcome["status"] == "saved"
        summary = outcome["record"]["summary"]
        assert summary["dtg_per_min_basis"] == "beta_traceable"
        assert summary["dtg_per_min_withheld_reason"] is None
        state_pm = np.asarray(outcome["state"]["dtg_per_min"], dtype=float)
        np.testing.assert_allclose(
            state_pm, np.asarray(outcome["state"]["dtg"], dtype=float) * 10.0
        )

    def test_dtg_per_min_withheld_without_rate(self, temperature_axis, mass_signal):
        from core.batch_runner import execute_batch_template

        dataset = self._dataset(temperature_axis, mass_signal)
        outcome = execute_batch_template(
            dataset_key="depth_tga",
            dataset=dataset,
            analysis_type="TGA",
            workflow_template_id="tga.general",
        )
        assert outcome["status"] == "saved"
        summary = outcome["record"]["summary"]
        assert summary["dtg_per_min_basis"] == "withheld"
        assert summary["dtg_per_min_withheld_reason"] == "heating_rate_missing"
        assert outcome["state"]["dtg_per_min"] is None

    def test_dtg_per_min_disabled(self, temperature_axis, mass_signal):
        from core.batch_runner import execute_batch_template

        dataset = self._dataset(
            temperature_axis, mass_signal,
            heating_rate=10.0, heating_rate_source="parsed",
        )
        outcome = execute_batch_template(
            dataset_key="depth_tga",
            dataset=dataset,
            analysis_type="TGA",
            workflow_template_id="tga.general",
            existing_processing={
                "analysis_steps": {"dtg_per_min": {"enabled": False}}
            },
        )
        assert outcome["status"] == "saved"
        assert outcome["record"]["summary"]["dtg_per_min_basis"] == "not_computed"
        assert outcome["state"]["dtg_per_min"] is None

    def test_window_celsius_via_processing(self, temperature_axis, mass_signal):
        from core.batch_runner import execute_batch_template

        dataset = self._dataset(temperature_axis, mass_signal)
        outcome = execute_batch_template(
            dataset_key="depth_tga",
            dataset=dataset,
            analysis_type="TGA",
            workflow_template_id="tga.general",
            existing_processing={
                "signal_pipeline": {"smoothing": {"window_celsius": 5.0}}
            },
        )
        assert outcome["status"] == "saved"
        steps = outcome["state"]["tga_result"].metadata["steps"]
        smooth_step = next(s for s in steps if s["step"] == "smooth")
        assert smooth_step["window_celsius"] == pytest.approx(5.0)
        assert smooth_step["window_length_effective"] == 11
        # The °C section must be recorded for reproducibility.
        assert (
            outcome["record"]["processing"]["signal_pipeline"]["smoothing"]["window_celsius"]
            == pytest.approx(5.0)
        )


# ---------------------------------------------------------------------------
# Serialization / archive round-trip
# ---------------------------------------------------------------------------

class TestSerialization:
    def _result(self, temperature_axis, mass_signal, **metadata):
        p = TGAProcessor(temperature_axis, mass_signal, metadata=metadata, initial_mass_mg=10.0)
        p.smooth().compute_dtg().measure_residual_mass([350.0, 900.0]).detect_steps().compute_dtg_per_min()
        return p.get_result()

    def test_summary_carries_pr17_fields(self, temperature_axis, mass_signal):
        from core.result_serialization import serialize_tga_result
        import pandas as pd
        from core.data_io import ThermalDataset

        result = self._result(
            temperature_axis, mass_signal,
            heating_rate=10.0, heating_rate_source="user",
        )
        dataset = ThermalDataset(
            data=pd.DataFrame({"temperature": temperature_axis, "signal": mass_signal}),
            metadata={"sample_name": "DepthTGA"},
            data_type="TGA",
            units={"temperature": "degC", "signal": "%"},
            original_columns={},
            file_path="",
        )
        record = serialize_tga_result("k", dataset, result)
        summary = record["summary"]
        assert summary["dtg_per_min_basis"] == "beta_traceable"
        assert len(summary["residual_mass_points"]) == 2
        assert summary["residual_mass_points"][0]["residual_mass_percent"] == pytest.approx(70.0, abs=0.5)
        assert summary["residual_mass_points"][1]["withheld_reason"] == "target_outside_measured_range"
        # Scientific context must mention the new equations.
        ctx = record.get("scientific_context") or {}
        eq_names = [e.get("name") for e in ctx.get("equations") or []]
        assert "DTG per Minute" in eq_names
        assert "Residual Mass at Target" in eq_names

    def test_legacy_result_serializes_with_defaults(self, temperature_axis, mass_signal):
        # A TGAResult built without PR-17 fields (old archive) must still
        # serialize — additive defaults only.
        from core.result_serialization import serialize_tga_result
        import pandas as pd
        from core.data_io import ThermalDataset

        legacy = TGAResult(
            steps=[],
            dtg_peaks=[],
            dtg_signal=np.gradient(mass_signal, temperature_axis),
            smoothed_signal=mass_signal,
            total_mass_loss_percent=80.0,
            residue_percent=20.0,
            metadata={},
        )
        dataset = ThermalDataset(
            data=pd.DataFrame({"temperature": temperature_axis, "signal": mass_signal}),
            metadata={},
            data_type="TGA",
            units={"temperature": "degC", "signal": "%"},
            original_columns={},
            file_path="",
        )
        record = serialize_tga_result("k", dataset, legacy)
        assert record["summary"]["dtg_per_min_basis"] == "not_computed"
        assert record["summary"]["residual_mass_points"] == []

    def test_state_round_trip(self, temperature_axis, mass_signal):
        from core.project_io import _deserialize_tga_state, _serialize_tga_state

        result = self._result(
            temperature_axis, mass_signal,
            heating_rate=10.0, heating_rate_source="parsed",
        )
        state = {
            "smoothed": result.smoothed_signal,
            "dtg": result.dtg_signal,
            "tga_result": result,
            "processing": {"analysis_steps": {"residual_mass": {"enabled": True, "targets": [350.0, 900.0]}}},
        }
        payload = _serialize_tga_state(state)
        assert payload["dtg_per_min"] is not None
        assert payload["dtg_per_min_basis"] == "beta_traceable"
        assert len(payload["residual_mass_points"]) == 2

        restored = _deserialize_tga_state(payload)
        np.testing.assert_allclose(restored["dtg_per_min"], result.dtg_per_min)
        r = restored["tga_result"]
        assert r.dtg_per_min_basis == "beta_traceable"
        np.testing.assert_allclose(r.dtg_per_min, result.dtg_per_min)
        assert r.residual_mass_points[0].residual_mass_percent == pytest.approx(70.0, abs=0.5)
        assert r.residual_mass_points[1].withheld_reason == "target_outside_measured_range"

    def test_legacy_state_payload_deserializes(self, temperature_axis, mass_signal):
        # Payloads written before PR-17 lack the new keys entirely.
        from core.project_io import _deserialize_tga_state

        legacy_payload = {
            "smoothed": mass_signal.tolist(),
            "dtg": np.gradient(mass_signal, temperature_axis).tolist(),
            "steps": [],
            "summary": {"total_mass_loss_percent": 80.0, "residue_percent": 20.0},
            "processing": {},
        }
        restored = _deserialize_tga_state(legacy_payload)
        r = restored["tga_result"]
        assert r is not None
        assert r.dtg_per_min is None
        assert r.dtg_per_min_basis == "not_computed"
        assert r.residual_mass_points == []
        assert restored["dtg_per_min"] is None


# ---------------------------------------------------------------------------
# Dash page plumbing
# ---------------------------------------------------------------------------

@pytest.fixture
def _dash_app():
    import dash
    from dash import html

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


@pytest.mark.usefixtures("_dash_app")
class TestDashPlumbing:
    def test_draft_from_control_values(self):
        import dash_app.pages.tga as tga_page

        draft = tga_page._tga_draft_from_control_values(
            "savgol", 11, 3, 2.0, "", 0.5, 80,
            smooth_window_c=5.0,
            depth_dtg_per_min=["enabled"],
            depth_residual_enabled=["enabled"],
            depth_residual_targets="350, 700; 900",
        )
        assert draft["smoothing"]["window_celsius"] == pytest.approx(5.0)
        assert draft["residual_mass"] == {"enabled": True, "targets": [350.0, 700.0, 900.0]}
        assert draft["dtg_per_min"] == {"enabled": True}

    def test_draft_defaults_are_safe(self):
        import dash_app.pages.tga as tga_page

        draft = tga_page._tga_draft_from_control_values("savgol", 11, 3, 2.0, "", 0.5, 80)
        assert "window_celsius" not in draft["smoothing"]
        assert draft["residual_mass"] == {"enabled": False, "targets": []}
        assert draft["dtg_per_min"] == {"enabled": True}

    def test_gaussian_maps_to_sigma_celsius(self):
        import dash_app.pages.tga as tga_page

        draft = tga_page._tga_draft_from_control_values(
            "gaussian", 11, 3, 2.0, "", 0.5, 80,
            smooth_window_c=2.5,
        )
        assert draft["smoothing"]["sigma_celsius"] == pytest.approx(2.5)
        assert "window_celsius" not in draft["smoothing"]

    def test_residual_targets_parsing(self):
        import dash_app.pages.tga as tga_page

        assert tga_page._parse_tga_residual_targets("350, 700") == [350.0, 700.0]
        assert tga_page._parse_tga_residual_targets("") == []
        assert tga_page._parse_tga_residual_targets("abc, nan, 400") == [400.0]

    def test_overrides_and_snapshot(self):
        import dash_app.pages.tga as tga_page

        draft = {
            "smoothing": {"method": "savgol", "window_length": 11, "polyorder": 3, "window_celsius": 5.0},
            "step_detection": {"method": "dtg_peaks", "prominence": None, "min_mass_loss": 0.5, "search_half_width": 80},
            "residual_mass": {"enabled": True, "targets": [350.0]},
            "dtg_per_min": {"enabled": False},
        }
        overrides = tga_page._tga_overrides_from_draft(draft)
        assert overrides["residual_mass"]["enabled"] is True
        assert overrides["residual_mass"]["targets"] == [350.0]
        assert overrides["dtg_per_min"]["enabled"] is False
        assert overrides["smoothing"]["window_celsius"] == pytest.approx(5.0)

        snapshot = tga_page._tga_ui_snapshot_dict("tga.general", "auto", draft)
        assert snapshot["residual_mass"]["targets"] == [350.0]
        assert snapshot["dtg_per_min"]["enabled"] is False

    def test_draft_roundtrip_from_loaded_processing(self):
        import dash_app.pages.tga as tga_page

        processing = {
            "signal_pipeline": {"smoothing": {"method": "savgol", "window_length": 15, "polyorder": 3, "window_celsius": 7.5}},
            "analysis_steps": {
                "step_detection": {"method": "dtg_peaks", "prominence": 0.2, "min_mass_loss": 0.4, "search_half_width": 90},
                "residual_mass": {"enabled": True, "targets": [200.0, 500.0]},
                "dtg_per_min": {"enabled": False},
            },
            "method_context": {"tga_unit_mode_declared": "percent"},
        }
        draft, unit = tga_page._tga_draft_and_unit_from_loaded_processing(processing)
        assert unit == "percent"
        assert draft["residual_mass"]["targets"] == [200.0, 500.0]
        assert draft["dtg_per_min"]["enabled"] is False
        assert draft["smoothing"]["window_celsius"] == pytest.approx(7.5)
