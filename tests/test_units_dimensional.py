"""Unit tests for core.units_dimensional (PR-9 dimensional honesty)."""

from __future__ import annotations

import math

import pytest

from core.units_dimensional import (
    BASIS_BETA_CORRECTED,
    BASIS_LEGACY_UNKNOWN,
    BASIS_RAW_SIGNAL_STEP,
    BASIS_TEMPERATURE_DOMAIN_AREA,
    SECONDS_PER_MINUTE,
    UnitClass,
    area_units_label,
    canonical_signal_unit,
    classify_signal_unit,
    factor_to_w_per_g,
    heat_flow_step_to_delta_cp,
    peak_area_to_enthalpy,
    resolve_beta,
    resolve_working_unit,
)


class TestCanonicalSignalUnit:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("mW", "mW"),
            ("W", "W"),
            ("mW/mg", "mW/mg"),
            ("W/g", "W/g"),
            ("W/mg", "W/mg"),
            ("mW/g", "mW/g"),
        ],
    )
    def test_recognized_units(self, raw, expected):
        assert canonical_signal_unit(raw) == (expected, classify_signal_unit(raw))

    def test_longest_token_wins(self):
        """W/mg and mW/g must not be mis-hit by W or mW."""
        assert canonical_signal_unit("W/mg") == ("W/mg", UnitClass.SPECIFIC_POWER)
        assert canonical_signal_unit("mW/g") == ("mW/g", UnitClass.SPECIFIC_POWER)

    def test_classes(self):
        assert classify_signal_unit("mW") is UnitClass.RAW_POWER
        assert classify_signal_unit("W") is UnitClass.RAW_POWER
        assert classify_signal_unit("mW/mg") is UnitClass.SPECIFIC_POWER
        assert classify_signal_unit("W/g") is UnitClass.SPECIFIC_POWER

    @pytest.mark.parametrize("raw", ["a.u.", "µV", "mV", "", None, "unknown"])
    def test_unusable(self, raw):
        assert classify_signal_unit(raw) is UnitClass.UNUSABLE


class TestFactorTable:
    @pytest.mark.parametrize(
        "unit,expected",
        [
            ("mW/mg", 1.0),
            ("W/g", 1.0),
            ("W/mg", 1000.0),
            ("mW/g", 1e-3),
        ],
    )
    def test_factors(self, unit, expected):
        assert factor_to_w_per_g(unit) == pytest.approx(expected)

    @pytest.mark.parametrize("unit", ["mW", "W", "a.u.", "", None])
    def test_no_factor_for_non_specific(self, unit):
        assert factor_to_w_per_g(unit) is None


class TestResolveBeta:
    def test_user_beta_accepted(self):
        beta, reason = resolve_beta(10.0, "user")
        assert beta == pytest.approx(10.0)
        assert reason is None

    def test_parsed_beta_accepted(self):
        beta, reason = resolve_beta(20.0, "parsed")
        assert beta == pytest.approx(20.0)
        assert reason is None

    @pytest.mark.parametrize("value", [0.0, -5.0, float("nan"), float("inf")])
    def test_invalid_beta_withheld(self, value):
        beta, reason = resolve_beta(value, "user")
        assert beta is None
        assert reason == "heating_rate_invalid"

    def test_missing_beta_withheld(self):
        beta, reason = resolve_beta(None, "user")
        assert beta is None
        assert reason == "heating_rate_missing"

    @pytest.mark.parametrize("source", [None, "", "ui_default", "legacy_unknown"])
    def test_unverified_source_withheld(self, source):
        beta, reason = resolve_beta(10.0, source)
        assert beta is None
        assert reason is not None


class TestResolveWorkingUnit:
    def test_raw_mw_normalizes_to_mw_per_mg(self):
        unit, applied, reason = resolve_working_unit("mW", 5.0, True)
        assert (unit, applied, reason) == ("mW/mg", True, None)

    def test_raw_w_normalizes_to_w_per_mg(self):
        """W divided by mg is W/mg — not mW/mg."""
        unit, applied, reason = resolve_working_unit("W", 5.0, True)
        assert (unit, applied, reason) == ("W/mg", True, None)

    @pytest.mark.parametrize("unit", ["W/g", "mW/mg"])
    def test_already_specific_is_skipped(self, unit):
        resolved, applied, reason = resolve_working_unit(unit, 5.0, True)
        assert resolved == unit
        assert applied is False
        assert reason == "already_specific_power"

    def test_second_normalize_is_noop(self):
        """A second call must not divide again: structural idempotence.

        The working unit is unchanged and ``applied`` is False so the
        caller performs no further division.
        """
        first_unit, first_applied, _ = resolve_working_unit("mW", 5.0, True)
        assert (first_unit, first_applied) == ("mW/mg", True)

        second_unit, second_applied, reason = resolve_working_unit(
            "mW", 5.0, True, working_unit=first_unit, normalization_applied=first_applied
        )
        assert second_unit == first_unit, "working unit must not change"
        assert second_applied is False, "must not divide by mass a second time"
        assert reason == "already_normalized"

    def test_missing_mass_skips(self):
        unit, applied, reason = resolve_working_unit("mW", None, True)
        assert applied is False
        assert reason == "sample_mass_missing"

    @pytest.mark.parametrize("mass", [0.0, -1.0, float("nan")])
    def test_invalid_mass_skips(self, mass):
        unit, applied, reason = resolve_working_unit("mW", mass, True)
        assert applied is False
        assert reason == "sample_mass_invalid"

    def test_unusable_unit_skips(self):
        unit, applied, reason = resolve_working_unit("a.u.", 5.0, True)
        assert applied is False
        assert reason == "signal_unit_unusable"

    def test_not_requested_skips(self):
        unit, applied, reason = resolve_working_unit("mW", 5.0, False)
        assert (unit, applied, reason) == ("mW", False, "normalization_not_requested")


class TestStepToDeltaCp:
    def test_converts_with_specific_power_and_beta(self):
        result = heat_flow_step_to_delta_cp(
            0.08, working_signal_unit="W/g", beta_k_min=10.0
        )
        assert result.corrected
        assert result.value == pytest.approx(0.08 * SECONDS_PER_MINUTE / 10.0)
        assert result.basis == BASIS_BETA_CORRECTED
        assert result.withheld_reason is None

    def test_scales_inversely_with_beta(self):
        slow = heat_flow_step_to_delta_cp(0.08, working_signal_unit="W/g", beta_k_min=10.0)
        fast = heat_flow_step_to_delta_cp(0.08, working_signal_unit="W/g", beta_k_min=20.0)
        assert slow.value == pytest.approx(2.0 * fast.value)

    def test_w_per_mg_applies_thousand_factor(self):
        """W/mg carries a 1000x factor that the class alone would miss."""
        w_per_mg = heat_flow_step_to_delta_cp(
            0.08, working_signal_unit="W/mg", beta_k_min=10.0
        )
        mw_per_mg = heat_flow_step_to_delta_cp(
            0.08, working_signal_unit="mW/mg", beta_k_min=10.0
        )
        assert w_per_mg.value == pytest.approx(1000.0 * mw_per_mg.value)

    def test_raw_power_withheld(self):
        result = heat_flow_step_to_delta_cp(
            0.08, working_signal_unit="mW", beta_k_min=10.0
        )
        assert result.value is None
        assert result.withheld_reason == "signal_not_mass_normalized"
        assert result.basis == BASIS_RAW_SIGNAL_STEP

    def test_unusable_unit_withheld(self):
        result = heat_flow_step_to_delta_cp(
            0.08, working_signal_unit="a.u.", beta_k_min=10.0
        )
        assert result.value is None
        assert result.withheld_reason == "signal_unit_unusable"

    @pytest.mark.parametrize("beta", [None, 0.0, -1.0, float("nan")])
    def test_bad_beta_withheld(self, beta):
        result = heat_flow_step_to_delta_cp(
            0.08, working_signal_unit="W/g", beta_k_min=beta
        )
        assert result.value is None
        assert result.withheld_reason is not None


class TestAreaToEnthalpy:
    def test_converts(self):
        result = peak_area_to_enthalpy(2.5, working_signal_unit="W/g", beta_k_min=10.0)
        assert result.corrected
        assert result.value == pytest.approx(2.5 * SECONDS_PER_MINUTE / 10.0)

    def test_scales_inversely_with_beta(self):
        slow = peak_area_to_enthalpy(2.5, working_signal_unit="W/g", beta_k_min=10.0)
        fast = peak_area_to_enthalpy(2.5, working_signal_unit="W/g", beta_k_min=20.0)
        assert slow.value == pytest.approx(2.0 * fast.value)

    def test_raw_power_withheld(self):
        result = peak_area_to_enthalpy(2.5, working_signal_unit="mW", beta_k_min=10.0)
        assert result.value is None
        assert result.withheld_reason == "signal_not_mass_normalized"
        assert result.basis == BASIS_TEMPERATURE_DOMAIN_AREA

    def test_missing_beta_withheld(self):
        result = peak_area_to_enthalpy(2.5, working_signal_unit="W/g", beta_k_min=None)
        assert result.value is None
        assert result.withheld_reason == "heating_rate_missing"


class TestUnitEquivalenceVsNumericEquality:
    """Two distinct cases; either alone would pass a broken factor table."""

    def test_equivalent_physical_power_identical(self):
        """1 W and 1000 mW are the same power: results must match exactly."""
        mass = 5.0
        as_w = resolve_working_unit("W", mass, True)
        as_mw = resolve_working_unit("mW", mass, True)

        # Same physical power: the mW curve carries 1000x the numbers.
        step_w = 0.001
        step_mw = 1.0

        cp_w = heat_flow_step_to_delta_cp(
            step_w / mass, working_signal_unit=as_w[0], beta_k_min=10.0
        )
        cp_mw = heat_flow_step_to_delta_cp(
            step_mw / mass, working_signal_unit=as_mw[0], beta_k_min=10.0
        )
        assert cp_w.value == pytest.approx(cp_mw.value, rel=1e-9)

    def test_identical_numbers_differ_by_unit_factor(self):
        """A value of 1 labelled W vs 1 labelled mW differs by 1000x."""
        mass = 5.0
        as_w = resolve_working_unit("W", mass, True)
        as_mw = resolve_working_unit("mW", mass, True)

        cp_w = heat_flow_step_to_delta_cp(
            1.0 / mass, working_signal_unit=as_w[0], beta_k_min=10.0
        )
        cp_mw = heat_flow_step_to_delta_cp(
            1.0 / mass, working_signal_unit=as_mw[0], beta_k_min=10.0
        )
        assert cp_w.value == pytest.approx(1000.0 * cp_mw.value, rel=1e-9)


class TestAreaUnitsLabel:
    @pytest.mark.parametrize(
        "unit,expected",
        [
            ("mW/mg", "mW/mg·K"),
            ("W/g", "W/g·K"),
            ("W/mg", "W/mg·K"),
        ],
    )
    def test_labels(self, unit, expected):
        assert area_units_label(unit) == expected

    def test_unknown_unit(self):
        assert area_units_label("a.u.") == "unknown units·K"
        assert area_units_label(None) == "unknown units·K"


class TestConversionSerialization:
    def test_to_dict_roundtrip(self):
        result = heat_flow_step_to_delta_cp(
            0.08, working_signal_unit="W/g", beta_k_min=10.0
        )
        payload = result.to_dict()
        assert set(payload) == {
            "value",
            "basis",
            "withheld_reason",
            "beta_k_min",
            "signal_unit",
            "factor_to_w_per_g",
        }
        assert payload["basis"] == BASIS_BETA_CORRECTED
        assert math.isfinite(payload["value"])

    def test_legacy_basis_constant(self):
        assert BASIS_LEGACY_UNKNOWN == "legacy_unknown"
