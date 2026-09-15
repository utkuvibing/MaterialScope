"""PR-16 tests: ISO-11357-2-style two-tangent Tg construction.

Covers:
- detect_glass_transition_iso on a controlled reference fixture: logistic
  blend of two known linear tangents, so Tig/Teg/Tmg and the Cp offset are
  analytically constrained
- multi-transition reporting from a single scan
- candidate gating: sharp peaks are not Tg; degenerate tangent geometry is
  skipped, not fabricated
- the existing step-morphology detector is unchanged (single best result)
- delta_cp honesty: beta-gated through heat_flow_step_to_delta_cp
- serialization round-trip of construction + construction_details
- batch-runner plumbing: glass_transition.method dispatch + transitions list
- Dash draft normalization for the method selector
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from core.dsc_processor import DSCProcessor
from core.result_serialization import (
    glass_transition_from_dict,
    glass_transition_to_dict,
    serialize_dsc_result,
)
from core.units_dimensional import BASIS_BETA_CORRECTED

TEMPERATURES = np.arange(40.0, 240.5, 0.5)


def _two_tangent_step(t, t0, width, m1, b1, m2, b2):
    """Logistic blend of two lines: pre-tangent below t0, post above."""
    w = 1.0 / (1.0 + np.exp(-(t - t0) / width))
    return (1.0 - w) * (m1 * t + b1) + w * (m2 * t + b2)


def _single_step_signal(t0=130.0, width=3.0, step=0.15):
    """One Tg-like step: flat-ish tangents, smooth transition at t0."""
    return _two_tangent_step(TEMPERATURES, t0, width, m1=0.002, b1=1.0, m2=0.004, b2=1.0 + step)


def _double_step_signal():
    sig = _two_tangent_step(TEMPERATURES, 105.0, 2.5, 0.002, 1.0, 0.004, 1.12)
    # second step stacked on the first's post-tangent
    w = 1.0 / (1.0 + np.exp(-(TEMPERATURES - 185.0) / 2.5))
    sig = sig + w * (0.002 * TEMPERATURES + 0.15)
    return sig


def _peak_only_signal():
    """Sharp Gaussian peak — peak morphology, not a baseline step."""
    return 1.0 + 0.002 * TEMPERATURES + 0.8 * np.exp(-0.5 * ((TEMPERATURES - 140.0) / 4.0) ** 2)


def _processor(signal, *, beta=10.0, mass=5.0, unit="mW", normalize=True):
    p = DSCProcessor(
        TEMPERATURES,
        signal,
        sample_mass=mass,
        heating_rate=beta,
        signal_unit=unit,
        heating_rate_source="user",
    )
    if normalize and mass:
        p.normalize()
    return p


class TestIsoTgReferenceFixture:
    def test_single_step_recovers_known_construction(self):
        t0, width, step_offset = 130.0, 3.0, 0.15
        signal = _single_step_signal(t0, width, step_offset)
        proc = _processor(signal)
        proc.detect_glass_transition_iso()
        tgs = proc.get_result().glass_transitions
        assert len(tgs) == 1
        tg = tgs[0]
        assert tg.construction == "iso_two_tangent"
        # The logistic midline crossing is exactly t0 for a symmetric blend.
        assert tg.tg_midpoint == pytest.approx(t0, abs=1.5)
        # ISO geometry: extrapolated onset below the transition, endset above.
        assert tg.tg_onset < tg.tg_midpoint < tg.tg_endset
        assert t0 - 8 * width < tg.tg_onset < t0
        assert t0 < tg.tg_endset < t0 + 8 * width
        # The reported step is the vertical Cp offset between the tangents
        # at Tmg: (m2-m1)*Tmg + (b2-b1).  The processor mass-normalised the
        # mW signal (5 mg -> W/g), so the working-unit step is /5.
        expected_offset = ((0.004 - 0.002) * tg.tg_midpoint + step_offset) / 5.0
        assert tg.heat_flow_step == pytest.approx(expected_offset, rel=0.10)

    def test_construction_details_record_tangent_geometry(self):
        proc = _processor(_single_step_signal(), normalize=False)
        proc.detect_glass_transition_iso()
        tg = proc.get_result().glass_transitions[0]
        details = tg.construction_details
        assert details is not None
        for key in (
            "inflection_temperature",
            "inflection_signal",
            "inflection_slope",
            "pre_tangent",
            "post_tangent",
            "plateau_windows",
        ):
            assert key in details
        assert details["pre_tangent"]["slope"] == pytest.approx(0.002, rel=0.5)
        assert details["post_tangent"]["slope"] == pytest.approx(0.004, rel=0.5)
        assert tg.tg_onset == pytest.approx(
            (details["inflection_signal"] - details["inflection_slope"] * details["inflection_temperature"]
             - details["pre_tangent"]["intercept"])
            / (details["pre_tangent"]["slope"] - details["inflection_slope"]),
            rel=1e-9,
        )

    def test_delta_cp_beta_corrected_through_pr9_path(self):
        proc = _processor(_single_step_signal(), beta=20.0)
        proc.detect_glass_transition_iso()
        tg = proc.get_result().glass_transitions[0]
        assert tg.delta_cp_basis == BASIS_BETA_CORRECTED
        # mW / (mg-normalized→mW/mg) -> W/g via unit resolution; ΔCp = step/β.
        assert tg.delta_cp_j_g_k is not None
        assert tg.delta_cp_j_g_k > 0

    def test_delta_cp_withheld_without_beta(self):
        proc = _processor(_single_step_signal(), beta=None)
        proc.detect_glass_transition_iso()
        tg = proc.get_result().glass_transitions[0]
        assert tg.delta_cp_j_g_k is None
        assert tg.delta_cp_basis != BASIS_BETA_CORRECTED
        assert tg.delta_cp_withheld_reason

    def test_existing_detector_unchanged_reports_single_best(self):
        proc = _processor(_double_step_signal())
        proc.detect_glass_transition()
        tgs = proc.get_result().glass_transitions
        assert len(tgs) == 1
        assert tgs[0].construction == "step_morphology"


class TestIsoTgMultiTransition:
    def test_two_steps_reported_from_one_scan(self):
        proc = _processor(_double_step_signal())
        proc.detect_glass_transition_iso()
        tgs = proc.get_result().glass_transitions
        assert len(tgs) == 2, (
            "ISO construction must report both qualifying transitions "
            f"from a single scan, got {[t.tg_midpoint for t in tgs]}"
        )
        mids = sorted(t.tg_midpoint for t in tgs)
        assert mids[0] == pytest.approx(105.0, abs=3.0)
        assert mids[1] == pytest.approx(185.0, abs=3.0)
        assert all(t.construction == "iso_two_tangent" for t in tgs)

    def test_peak_does_not_produce_iso_tg(self):
        proc = _processor(_peak_only_signal())
        proc.detect_glass_transition_iso()
        tgs = proc.get_result().glass_transitions
        assert tgs == [], "a sharp peak is not a baseline step — must not fabricate a Tg"

    def test_region_restricts_candidate_search(self):
        proc = _processor(_double_step_signal())
        proc.detect_glass_transition_iso(region=(80.0, 140.0))
        tgs = proc.get_result().glass_transitions
        assert len(tgs) == 1
        assert tgs[0].tg_midpoint == pytest.approx(105.0, abs=3.0)


class TestIsoTgSerialization:
    def test_construction_roundtrip(self):
        proc = _processor(_single_step_signal(), normalize=False)
        proc.detect_glass_transition_iso()
        tg = proc.get_result().glass_transitions[0]
        payload = glass_transition_to_dict(tg)
        assert payload["construction"] == "iso_two_tangent"
        assert payload["construction_details"]["pre_tangent"]["slope"] == pytest.approx(0.002, rel=0.5)
        restored = glass_transition_from_dict(payload)
        assert restored.construction == "iso_two_tangent"
        assert restored.construction_details["post_tangent"]["intercept"] == pytest.approx(
            tg.construction_details["post_tangent"]["intercept"]
        )

    def test_legacy_payload_has_no_construction(self):
        tg = glass_transition_from_dict(
            {"tg_midpoint": 120.0, "tg_onset": 115.0, "tg_endset": 125.0, "delta_cp": 0.12}
        )
        assert tg.construction is None
        assert "construction" not in glass_transition_to_dict(tg)

    def test_serialized_record_lists_all_transitions(self):
        proc = _processor(_double_step_signal())
        proc.detect_glass_transition_iso()
        dataset = SimpleNamespace(
            metadata={"sample_mass": 5.0, "heating_rate": 10.0},
            units={"temperature": "°C", "signal": "W/g"},
        )
        record = serialize_dsc_result(
            "ds1", dataset, peaks=[], glass_transitions=proc.get_result().glass_transitions
        )
        summary = record["summary"]
        assert summary["glass_transition_count"] == 2
        assert len(summary["transitions"]) == 2
        assert summary["tg_construction"] == "iso_two_tangent"
        mids = sorted(t["tg_midpoint"] for t in summary["transitions"])
        assert mids[0] == pytest.approx(105.0, abs=3.0)
        assert mids[1] == pytest.approx(185.0, abs=3.0)


# ---------------------------------------------------------------------------
# Batch-runner plumbing
# ---------------------------------------------------------------------------


def _dataset(signal, *, beta=10.0, unit="mW", mass=5.0):
    import pandas as pd

    return SimpleNamespace(
        data=pd.DataFrame({"temperature": TEMPERATURES, "signal": signal}),
        metadata={
            "sample_mass": mass,
            "heating_rate": beta,
            "heating_rate_source": "user",
            "sample_name": "iso-tg-sample",
        },
        units={"temperature": "°C", "signal": unit},
        data_type="DSC",
    )


def _run_batch(dataset, *, glass_transition):
    from core.batch_runner import execute_batch_template
    from core.processing_schema import (
        ensure_processing_payload,
        update_processing_step,
    )

    processing = ensure_processing_payload(
        {"workflow_template_id": "dsc.general"}, analysis_type="DSC"
    )
    processing = update_processing_step(
        processing, "glass_transition", glass_transition, analysis_type="DSC"
    )
    return execute_batch_template(
        dataset_key="ds1",
        dataset=dataset,
        analysis_type="DSC",
        workflow_template_id="dsc.general",
        existing_processing=processing,
    )


class TestBatchRunnerIsoTg:
    def test_iso_method_reports_multiple_transitions(self):
        execution = _run_batch(
            _dataset(_double_step_signal()),
            glass_transition={"mode": "auto", "region": None, "method": "iso"},
        )
        assert execution["status"] == "saved"
        section = execution["processing"]["analysis_steps"]["glass_transition"]
        assert section["method"] == "iso"
        assert section["method_requested"] == "iso"
        assert section["event_count"] == 2
        summary = execution["record"]["summary"]
        assert summary["glass_transition_count"] == 2
        assert len(summary["transitions"]) == 2
        assert all(t["construction"] == "iso_two_tangent" for t in summary["transitions"])

    def test_step_method_is_default_single_best(self):
        execution = _run_batch(
            _dataset(_double_step_signal()),
            glass_transition={"mode": "auto", "region": None},
        )
        assert execution["status"] == "saved"
        section = execution["processing"]["analysis_steps"]["glass_transition"]
        assert section["method"] == "step"
        assert section["event_count"] <= 1

    def test_unknown_method_falls_back_to_step_recorded(self):
        execution = _run_batch(
            _dataset(_single_step_signal()),
            glass_transition={"method": "bogus"},
        )
        section = execution["processing"]["analysis_steps"]["glass_transition"]
        assert section["method"] == "step"
        assert section["method_requested"] == "bogus"


@pytest.fixture()
def _dash_app():
    """Create a minimal Dash app so dash.register_page() works."""
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
class TestDashDraftNormalization:
    def test_method_normalizes_to_known_values(self):
        from dash_app.pages.dsc import _normalize_tg_method

        assert _normalize_tg_method("iso") == "iso"
        assert _normalize_tg_method("ISO") == "iso"
        assert _normalize_tg_method("step") == "step"
        assert _normalize_tg_method(None) == "step"
        assert _normalize_tg_method("nonsense") == "step"

    def test_glass_transition_section_carries_method(self):
        from dash_app.pages.dsc import _normalize_glass_transition_values

        values = _normalize_glass_transition_values(True, 80.0, 160.0, "iso")
        assert values == {"mode": "auto", "region": [80.0, 160.0], "method": "iso"}
        values = _normalize_glass_transition_values(False, None, None, "iso")
        assert values == {"mode": "auto", "region": None, "method": "iso"}

    def test_draft_roundtrip_preserves_iso_method(self):
        from dash_app.pages.dsc import (
            _normalize_dsc_processing_draft,
            _overrides_from_draft,
        )

        draft = _normalize_dsc_processing_draft(
            {"glass_transition": {"mode": "auto", "region": None, "method": "iso"}}
        )
        overrides = _overrides_from_draft(draft)
        assert overrides["glass_transition"]["method"] == "iso"
