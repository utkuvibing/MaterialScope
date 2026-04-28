from __future__ import annotations

from core.spectral_demo_references import load_demo_spectral_references


def test_demo_ftir_reference_seed_is_bundled_and_loadable():
    references = load_demo_spectral_references("FTIR")

    assert references
    assert all(row["analysis_type"] == "FTIR" for row in references)
    assert all(len(row["axis"]) == len(row["signal"]) for row in references)


def test_demo_raman_reference_seed_is_bundled_and_loadable():
    references = load_demo_spectral_references("RAMAN")

    assert references
    assert all(row["analysis_type"] == "RAMAN" for row in references)
    assert all(len(row["axis"]) == len(row["signal"]) for row in references)
