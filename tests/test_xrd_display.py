from core import xrd_display


def test_format_scientific_formula_text_subscripts_simple_formulas():
    assert xrd_display.format_scientific_formula_text("MgB2", target="unicode") == "MgB₂"
    assert xrd_display.format_scientific_formula_text("CaCO3", target="unicode") == "CaCO₃"


def test_format_scientific_formula_text_preserves_hydrates_and_decimals():
    assert xrd_display.format_scientific_formula_text("CuSO4·5H2O", target="unicode") == "CuSO₄·5H₂O"
    assert xrd_display.format_scientific_formula_text("LiNi0.5Mn1.5O4", target="unicode") == "LiNi₀.₅Mn₁.₅O₄"


def test_format_scientific_formula_text_does_not_subscript_provider_or_candidate_ids():
    assert xrd_display.format_scientific_formula_text("COD #1000026", target="unicode") == "COD #1000026"
    assert xrd_display.format_scientific_formula_text("mp-1234", target="unicode") == "mp-1234"
    assert xrd_display.format_scientific_formula_text("cod_1000026", target="unicode") == "cod_1000026"


def test_xrd_candidate_display_variants_apply_scientific_formatting_after_name_resolution():
    variants = xrd_display.xrd_candidate_display_variants(
        {
            "candidate_name": "COD 1000026",
            "candidate_id": "cod_1000026",
            "source_id": "1000026",
            "library_provider": "COD",
            "formula": "MgB2",
        }
    )

    assert variants["raw_display_name"] == "MgB2"
    assert variants["plain_display_name"] == "MgB2"
    assert variants["unicode_display_name"] == "MgB₂"
