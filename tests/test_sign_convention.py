"""
test_sign_convention.py
-----------------------
Unit tests for the PR-8 sign-convention canon.

Covers:
- core.sign_convention helpers (strict parsing, evidence-only header
  hints, canonicalization, label derivation, provenance records)
- find_thermal_peaks label derivation under both conventions + UNKNOWN
- DTAProcessor single-pass direction detection (no duplicate or
  contradictory tags)
- TGAProcessor DTG peaks labeled as step events (mass axis, not heat)
- DSCProcessor convention recording, including the unknown-withheld path
- ingest canonicalization + raw provenance in core.data_io
"""

from __future__ import annotations

import io

import numpy as np
import pytest

from core.data_io import read_thermal_data
from core.dsc_processor import DSCProcessor
from core.dta_processor import DTAProcessor
from core.sign_convention import (
    CANONICAL_SIGNAL_CONVENTION,
    SignConvention,
    apply_canonicalization,
    direction_tag_from_label,
    inspect_header_hints,
    is_declared,
    label_from_direction,
    parse_declared,
    provenance_record,
    summarize_provenance,
)
from core.peak_analysis import find_thermal_peaks
from core.tga_processor import TGAProcessor


# ---------------------------------------------------------------------------
# Shared synthetic signals
# ---------------------------------------------------------------------------

T = np.linspace(30.0, 300.0, 900)
TWO_EVENT_SIGNAL = (
    2.0 * np.exp(-0.5 * ((T - 120.0) / 5.0) ** 2)
    - 1.5 * np.exp(-0.5 * ((T - 220.0) / 6.0) ** 2)
)


# ---------------------------------------------------------------------------
# parse_declared — explicit declarations only
# ---------------------------------------------------------------------------


class TestParseDeclared:
    def test_accepts_declared_tokens_case_insensitive(self):
        assert parse_declared("exo_up") is SignConvention.EXO_UP
        assert parse_declared("ENDO_UP") is SignConvention.ENDO_UP
        assert parse_declared(" Unknown ") is SignConvention.UNKNOWN

    def test_accepts_enum_instance(self):
        assert parse_declared(SignConvention.ENDO_UP) is SignConvention.ENDO_UP

    def test_default_used_when_nothing_declared(self):
        assert parse_declared(None, default=SignConvention.EXO_UP) is SignConvention.EXO_UP
        assert parse_declared("  ", default=SignConvention.ENDO_UP) is SignConvention.ENDO_UP

    def test_raises_without_default(self):
        with pytest.raises(ValueError):
            parse_declared(None)

    def test_rejects_hint_tokens_and_free_text(self):
        # Header-style hints must never parse as a declared convention.
        for token in ("endo", "exo up", "endothermic up", "Endo Down", "ta.instruments"):
            with pytest.raises(ValueError):
                parse_declared(token)


class TestIsDeclared:
    def test_resolving_conventions(self):
        assert is_declared(SignConvention.EXO_UP)
        assert is_declared(SignConvention.ENDO_UP)

    def test_unknown_is_not_declared(self):
        assert not is_declared(SignConvention.UNKNOWN)


# ---------------------------------------------------------------------------
# inspect_header_hints — evidence only, never a decision
# ---------------------------------------------------------------------------


class TestInspectHeaderHints:
    def test_no_tokens(self):
        evidence = inspect_header_hints("Heat Flow (mW/mg)")
        assert evidence == {"endo_token": False, "exo_token": False, "implied": None}

    def test_endo_up_implied(self):
        evidence = inspect_header_hints("Temperature (°C),Heat Flow (endo up) (mW/mg)")
        assert evidence["endo_token"] is True
        assert evidence["implied"] == "endo_up"

    def test_endo_down_implies_exo_up_frame(self):
        evidence = inspect_header_hints("Heat Flow (Endo Down)")
        assert evidence["implied"] == "exo_up"

    def test_exo_down_implies_endo_up_frame(self):
        evidence = inspect_header_hints("Heat Flow (exo down)")
        assert evidence["implied"] == "endo_up"

    def test_ambiguous_family_tokens_give_no_implied_frame(self):
        evidence = inspect_header_hints("Endo / Exo events")
        assert evidence["endo_token"] and evidence["exo_token"]
        assert evidence["implied"] is None


# ---------------------------------------------------------------------------
# apply_canonicalization — raw provenance preserved
# ---------------------------------------------------------------------------


class TestApplyCanonicalization:
    def test_canonical_input_copied_not_inverted(self):
        signal = np.array([1.0, -2.0, 3.0])
        canonical, record = apply_canonicalization(signal, SignConvention.EXO_UP)
        np.testing.assert_array_equal(canonical, signal)
        assert canonical is not signal
        assert record["raw_signal_convention"] == "exo_up"
        assert record["canonical_signal_convention"] == CANONICAL_SIGNAL_CONVENTION
        assert record["signal_inverted_at_import"] is False

    def test_endo_up_inverted_exactly_once(self):
        signal = np.array([1.0, -2.0, 3.0])
        canonical, record = apply_canonicalization(signal, SignConvention.ENDO_UP)
        np.testing.assert_array_equal(canonical, -signal)
        assert record["raw_signal_convention"] == "endo_up"
        assert record["signal_inverted_at_import"] is True
        assert record["canonical_signal_convention"] == CANONICAL_SIGNAL_CONVENTION

    def test_unknown_preserves_uncertainty(self):
        signal = np.array([1.0, -2.0, 3.0])
        canonical, record = apply_canonicalization(signal, SignConvention.UNKNOWN)
        np.testing.assert_array_equal(canonical, signal)
        assert record["raw_signal_convention"] == "unknown"
        assert record["canonical_signal_convention"] is None
        assert record["signal_inverted_at_import"] is False


class TestProvenanceRecords:
    def test_provenance_record_declared(self):
        record = provenance_record(SignConvention.ENDO_UP, declared_by="user")
        assert record == {
            "raw_signal_convention": "endo_up",
            "canonical_signal_convention": "exo_up",
            "signal_inverted_at_import": True,
            "sign_convention_declared_by": "user",
        }

    def test_summarize_provenance_declared(self):
        meta = provenance_record(SignConvention.EXO_UP, declared_by="import_default")
        summary = summarize_provenance(meta)
        assert summary == {
            "declared": "exo_up",
            "canonical": "exo_up",
            "inverted_at_import": False,
            "declared_by": "import_default",
        }

    def test_summarize_provenance_backward_safe(self):
        # Datasets predating the canon resolve to an explicit unresolved
        # state, never to a silently assumed canonical frame.
        summary = summarize_provenance({})
        assert summary == {
            "declared": "unknown",
            "canonical": None,
            "inverted_at_import": False,
            "declared_by": "not_recorded",
        }


# ---------------------------------------------------------------------------
# label_from_direction
# ---------------------------------------------------------------------------


class TestLabelFromDirection:
    def test_canonical_frame(self):
        assert label_from_direction("up") == "exotherm"
        assert label_from_direction("down") == "endotherm"

    def test_endo_up_frame(self):
        assert label_from_direction("up", SignConvention.ENDO_UP) == "endotherm"
        assert label_from_direction("down", SignConvention.ENDO_UP) == "exotherm"

    def test_unknown_frame_withholds_labels(self):
        assert label_from_direction("up", SignConvention.UNKNOWN) == "unknown"
        assert label_from_direction("down", SignConvention.UNKNOWN) == "unknown"

    def test_alias_tokens(self):
        assert label_from_direction("exo") == "exotherm"
        assert label_from_direction("endo") == "endotherm"

    def test_unrecognized_direction(self):
        assert label_from_direction("sideways") == "unknown"


# ---------------------------------------------------------------------------
# find_thermal_peaks — labels derived from the convention
# ---------------------------------------------------------------------------


class TestFindThermalPeaksConvention:
    def test_canonical_labels(self):
        peaks = find_thermal_peaks(T, TWO_EVENT_SIGNAL)
        by_temp = {round(p.peak_temperature): p.peak_type for p in peaks}
        assert by_temp[120] == "exotherm"
        assert by_temp[220] == "endotherm"

    def test_endo_up_frame_relabeled(self):
        peaks = find_thermal_peaks(T, TWO_EVENT_SIGNAL, sign_convention="endo_up")
        by_temp = {round(p.peak_temperature): p.peak_type for p in peaks}
        assert by_temp[120] == "endotherm"
        assert by_temp[220] == "exotherm"

    def test_unknown_frame_withholds_all_labels(self):
        peaks = find_thermal_peaks(T, TWO_EVENT_SIGNAL, sign_convention="unknown")
        assert len(peaks) == 2
        assert {p.peak_type for p in peaks} == {"unknown"}

    def test_invalid_convention_rejected(self):
        with pytest.raises(ValueError):
            find_thermal_peaks(T, TWO_EVENT_SIGNAL, sign_convention="endo")


# ---------------------------------------------------------------------------
# DTAProcessor — single pass per direction, no duplicate tags
# ---------------------------------------------------------------------------


class TestDTAProcessorDirection:
    def _processor(self, sign_convention=None) -> DTAProcessor:
        processor = DTAProcessor(T, TWO_EVENT_SIGNAL, sign_convention=sign_convention)
        processor.smooth(method="savgol", window_length=11, polyorder=2)
        return processor

    def test_each_event_detected_once_with_correct_tag(self):
        processor = self._processor(None)
        processor.find_peaks()
        peaks = processor._peaks
        assert len(peaks) == 2  # historical bug produced 4 (each event twice)
        by_temp = {round(p.peak_temperature): p for p in peaks}
        # Canonical exo-up frame: up event = exotherm, down event = endotherm.
        assert by_temp[120].peak_type == "exotherm"
        assert by_temp[120].direction == "exo"
        assert by_temp[220].peak_type == "endotherm"
        assert by_temp[220].direction == "endo"

    def test_endo_up_convention_direction_matches_peak_type(self):
        """Regression: direct DTAProcessor(sign_convention='endo_up') use.

        In an endo-up frame the endothermic event points UP and the
        exothermic event points DOWN.  The serialized ``direction`` tag is
        derived from the same canon label as ``peak_type`` and must never
        contradict it.
        """
        endo_up_signal = (
            0.2
            + 2.0 * np.exp(-0.5 * ((T - 120.0) / 5.0) ** 2)
            - 1.5 * np.exp(-0.5 * ((T - 220.0) / 6.0) ** 2)
        )
        processor = DTAProcessor(T, endo_up_signal, sign_convention="endo_up")
        processor.smooth(method="savgol", window_length=11, polyorder=2)
        processor.find_peaks()

        peaks = processor._peaks
        assert len(peaks) == 2
        by_temp = {round(p.peak_temperature): p for p in peaks}
        up_peak = by_temp[120]
        down_peak = by_temp[220]

        # Upward event in an endo-up frame is endothermic.
        assert up_peak.peak_type == "endotherm"
        assert up_peak.direction == "endo"
        # Downward event in an endo-up frame is exothermic.
        assert down_peak.peak_type == "exotherm"
        assert down_peak.direction == "exo"

    def test_event_family_gating_follows_convention(self):
        """detect_exothermic-only on endo-up data finds the DOWN event."""
        endo_up_signal = (
            0.2
            + 2.0 * np.exp(-0.5 * ((T - 120.0) / 5.0) ** 2)  # endothermic in endo-up
            - 1.5 * np.exp(-0.5 * ((T - 220.0) / 6.0) ** 2)  # exothermic in endo-up
        )
        processor = DTAProcessor(T, endo_up_signal, sign_convention="endo_up")
        processor.smooth(method="savgol", window_length=11, polyorder=2)
        processor.find_peaks(detect_exothermic=True, detect_endothermic=False)

        assert len(processor._peaks) == 1
        found = processor._peaks[0]
        assert round(found.peak_temperature) == 220  # the exothermic (down) event
        assert found.peak_type == "exotherm"
        assert found.direction == "exo"

    def test_unknown_polarity_never_attributed(self):
        processor = self._processor("unknown")
        processor.find_peaks()
        assert {p.direction for p in processor._peaks} == {"unknown"}
        assert {p.peak_type for p in processor._peaks} == {"unknown"}

    def test_detection_gating_unchanged(self):
        processor = self._processor(None)
        processor.find_peaks(detect_exothermic=True, detect_endothermic=False)
        assert [p.direction for p in processor._peaks] == ["exo"]


class TestDirectionTagFromLabel:
    def test_compact_tags_from_canon_labels(self):
        assert direction_tag_from_label("exotherm") == "exo"
        assert direction_tag_from_label("endotherm") == "endo"

    def test_unknown_and_unknowable_labels(self):
        assert direction_tag_from_label("unknown") == "unknown"
        assert direction_tag_from_label("") == "unknown"
        assert direction_tag_from_label("step") == "unknown"


# ---------------------------------------------------------------------------
# TGAProcessor — DTG events are steps, not thermal endo/exo labels
# ---------------------------------------------------------------------------


class TestTGAStepLabels:
    def test_dtg_peaks_labeled_step(self):
        temperature = np.linspace(50.0, 300.0, 400)
        mass = 100.0 - 12.0 / (1.0 + np.exp(-(temperature - 150.0) / 5.0))
        processor = TGAProcessor(temperature, mass)
        processor.smooth(method="savgol", window_length=11, polyorder=2)
        processor.compute_dtg()
        processor.detect_steps()
        assert processor._dtg_peaks, "expected at least one DTG mass-loss event"
        assert {peak.peak_type for peak in processor._dtg_peaks} == {"step"}


# ---------------------------------------------------------------------------
# DSCProcessor — convention recorded, unknown withheld
# ---------------------------------------------------------------------------


class TestDSCProcessorConvention:
    def test_metadata_records_convention(self):
        processor = DSCProcessor(T, TWO_EVENT_SIGNAL, sign_convention="endo_up")
        processor.find_peaks()
        assert processor._metadata["signal_convention"] == "endo_up"
        by_temp = {round(p.peak_temperature): p.peak_type for p in processor._peaks}
        assert by_temp[120] == "endotherm"

    def test_unknown_convention_withholds_labels(self):
        processor = DSCProcessor(T, TWO_EVENT_SIGNAL, sign_convention="unknown")
        processor.find_peaks()
        assert {p.peak_type for p in processor._peaks} == {"unknown"}


# ---------------------------------------------------------------------------
# Ingest — declaration, canonicalization, warnings
# ---------------------------------------------------------------------------


def _csv_bytes(temperature: np.ndarray, signal: np.ndarray, header: str) -> io.StringIO:
    rows = "\n".join(f"{t:.2f},{s:.6f}" for t, s in zip(temperature, signal))
    return io.StringIO(f"{header}\n{rows}\n")


class TestIngestSignConvention:
    TEMPERATURE = np.linspace(50.0, 250.0, 201)

    @classmethod
    def _endotherm_up_signal(cls) -> np.ndarray:
        # Melting event as an endo-up file: positive excursion.
        return 0.5 + 1.2 * np.exp(-0.5 * ((cls.TEMPERATURE - 150.0) / 4.0) ** 2)

    @classmethod
    def _exotherm_up_same_event(cls) -> np.ndarray:
        # The same physical event in an exo-up file: negative excursion.
        return 0.5 - 1.2 * np.exp(-0.5 * ((cls.TEMPERATURE - 150.0) / 4.0) ** 2)

    def test_declared_endo_up_inverted_with_provenance(self):
        dataset = read_thermal_data(
            _csv_bytes(self.TEMPERATURE, self._endotherm_up_signal(), "Temperature (degC),Heat Flow (mW/mg)"),
            data_type="DSC",
            sign_convention="endo_up",
        )
        assert dataset.signal_convention == "exo_up"
        assert dataset.metadata["raw_signal_convention"] == "endo_up"
        assert dataset.metadata["signal_inverted_at_import"] is True
        assert dataset.metadata["canonical_signal_convention"] == "exo_up"
        assert dataset.metadata["sign_convention_declared_by"] == "user"
        # The endo-up excursion (positive) was inverted into the canonical frame.
        assert bool((dataset.data["signal"].values < 0).any())

    def test_declared_exo_up_not_inverted(self):
        dataset = read_thermal_data(
            _csv_bytes(self.TEMPERATURE, self._exotherm_up_same_event(), "Temperature (degC),Heat Flow (mW/mg)"),
            data_type="DSC",
            sign_convention="exo_up",
        )
        assert dataset.signal_convention == "exo_up"
        assert dataset.metadata["signal_inverted_at_import"] is False

    def test_default_declaration_recorded_as_import_default(self):
        dataset = read_thermal_data(
            _csv_bytes(self.TEMPERATURE, self._exotherm_up_same_event(), "Temperature (degC),Heat Flow (mW/mg)"),
            data_type="DSC",
        )
        assert dataset.metadata["raw_signal_convention"] == "exo_up"
        assert dataset.metadata["sign_convention_declared_by"] == "import_default"

    def test_unknown_keeps_polarity_unresolved(self):
        dataset = read_thermal_data(
            _csv_bytes(self.TEMPERATURE, self._endotherm_up_signal(), "Temperature (degC),Heat Flow (mW/mg)"),
            data_type="DSC",
            sign_convention="unknown",
        )
        assert dataset.signal_convention == "unknown"
        assert dataset.metadata["canonical_signal_convention"] is None
        assert dataset.metadata["signal_inverted_at_import"] is False
        # No inversion: the raw frame is preserved untouched.
        assert bool((dataset.data["signal"].values > 0).all())
        assert any("withheld" in warning for warning in dataset.metadata["import_warnings"])

    def test_header_contradiction_warns_without_flipping(self):
        dataset = read_thermal_data(
            _csv_bytes(self.TEMPERATURE, self._exotherm_up_same_event(), "Temperature (degC),Heat Flow (endo up) (mW/mg)"),
            data_type="DSC",
            sign_convention="exo_up",
        )
        evidence = dataset.metadata["sign_convention_header_evidence"]
        assert evidence["endo_token"] is True
        assert evidence["implied"] == "endo_up"
        assert any("header evidence" in warning for warning in dataset.metadata["import_warnings"])
        # Declared convention wins: data applied unchanged, never flipped.
        assert bool((dataset.data["signal"].values < 0).any())

    def test_invalid_declaration_rejected(self):
            with pytest.raises(ValueError):
                read_thermal_data(
                    _csv_bytes(self.TEMPERATURE, self._exotherm_up_same_event(), "Temperature (degC),Heat Flow (mW/mg)"),
                data_type="DSC",
                sign_convention="endothermic",
            )

    def test_spectral_imports_unaffected(self):
        dataset = read_thermal_data(
            _csv_bytes(np.linspace(500.0, 4000.0, 50), np.linspace(0.1, 0.9, 50), "Wavenumber (cm-1),Absorbance"),
            data_type="FTIR",
        )
        assert dataset.signal_convention == "unknown"
        assert "raw_signal_convention" not in dataset.metadata


class TestArchiveRoundTrip:
    def test_archive_round_trip_preserves_sign_convention_provenance(self):
        from core.project_io import load_project_archive, save_project_archive

        temperature = np.linspace(50.0, 250.0, 201)
        signal = 0.5 + 1.2 * np.exp(-0.5 * ((temperature - 150.0) / 4.0) ** 2)
        dataset = read_thermal_data(
            _csv_bytes(temperature, signal, "Temperature (degC),Heat Flow (mW/mg)"),
            data_type="DSC",
            sign_convention="endo_up",
        )
        session_state = {
            "datasets": {"run": dataset},
            "active_dataset": "run",
            "results": {},
            "figures": {},
            "analysis_history": [],
        }
        archive_bytes = save_project_archive(session_state)
        restored = load_project_archive(io.BytesIO(archive_bytes))

        restored_dataset = restored["datasets"]["run"]
        # The declared endo-up dataset was canonicalized at import, so the
        # restored working signal is in the canonical frame while the raw
        # provenance survives untouched.
        assert restored_dataset.signal_convention == "exo_up"
        assert restored_dataset.metadata["raw_signal_convention"] == "endo_up"
        assert restored_dataset.metadata["signal_inverted_at_import"] is True
        assert restored_dataset.metadata["canonical_signal_convention"] == "exo_up"
