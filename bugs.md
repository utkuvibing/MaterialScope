# Bugs

Use this file as a lightweight bug worklog. Add a new section whenever a bug is reproduced, investigated, or fixed.

---

## Bug Entry Template

### Title
Short bug summary.

### Date
YYYY-MM-DD

### Repro
1. Step one
2. Step two
3. Observed failure

### Suspected Cause
Brief hypothesis before the fix.

### Attempted Fix
What was tried first, if anything.

### Actual Fix
What changed in the final patch.

### Verification
- Tests run
- Manual verification
- Residual risk

---

### Title
Legacy report-generator CSV contract drifted from normalized result exports

### Date
2026-03-07

### Repro
1. Run `pytest -q`.
2. Observe failures in `tests/test_report_generator.py`.
3. See header/content assertions expecting the old kinetics-only CSV schema instead of the normalized flat record export currently produced by `core/report_generator.generate_csv_summary()`.

### Suspected Cause
The repo migrated report/export flows to normalized result records, but `tests/test_report_generator.py` remained on the old pre-normalization CSV contract.

### Attempted Fix
Brownfield hardening pass aligns tests and report/export helpers to the normalized record contract instead of restoring the deprecated CSV format.

### Actual Fix
Update report/export tests to validate normalized flat record output and extend exports to carry optional processing/provenance/validation metadata in a backward-compatible way.

### Verification
- Run `pytest -q`
- Confirm `tests/test_export_report.py` and `tests/test_project_io.py` still pass with normalized records
- Residual risk: downstream external tooling that assumed the old CSV layout would need an explicit legacy export helper

### Title
Legacy tuple validator drifted away from the current ThermalDataset model

### Date
2026-03-07

### Repro
1. Open `utils/validators.py`.
2. Inspect `validate_thermal_dataset()`.
3. See it expecting legacy attributes like `temperature_column`, `heat_flow_column`, and `sample_mass_mg` that the current `core.data_io.ThermalDataset` no longer uses.

### Suspected Cause
The repo kept the old tuple-based validator API for compatibility, but its dataset-level implementation was never updated after the standardized `temperature` / `signal` DataFrame contract and the new structured validator were introduced.

### Attempted Fix
Do not delete the public helper outright; keep its scalar validation helpers and replace only the stale dataset-level path.

### Actual Fix
Rewrite `utils/validators.py` as a compatibility layer that preserves the `(is_valid, message)` return type while delegating dataset-level checks to `core.validation.validate_thermal_dataset()`.

### Verification
- Run `pytest tests/test_validation.py -q`
- Confirm legacy wrapper returns `True` for valid current datasets and surfaces structured failure messages for invalid ones
- Residual risk: any third-party caller that relied on the old verbose message wording may observe text differences, but the public tuple shape is preserved

### Title
Saved workflow templates lacked stable internal IDs and DSC/TGA reports hid method context

### Date
2026-03-07

### Repro
1. Save a DSC or TGA result.
2. Inspect the normalized record `processing` payload and generated report.
3. Observe that the saved payload carried only a user-facing workflow label, and the report showed mostly generic key/value blocks rather than DSC/TGA-specific method context such as calibration, sign convention, atmosphere, and reference visibility.

### Suspected Cause
The first hardening tranche standardized payload structure but did not introduce stable template identifiers or domain-specific report rendering, so brownfield compatibility was preserved at the cost of method traceability.

### Attempted Fix
Avoid changing the normalized record contract or archive format; add stable template IDs inside the existing `processing` dict and derive richer report summaries from existing record metadata plus validation checks.

### Actual Fix
Extend `core.processing_schema` to backfill `workflow_template_id` / `workflow_template_label`, harden `core.validation` with DSC/TGA-specific checks, and teach `core.report_generator` to render domain-specific method summaries for DSC/TGA while keeping flat CSV export unchanged.

### Verification
- Run `pytest tests/test_validation.py tests/test_report_generator.py tests/test_export_report.py tests/test_project_io.py -q`
- Run `pytest -q`
- Confirm old label-only payloads still normalize correctly and project archives round-trip with the richer processing dict
- Residual risk: template labels remain user-facing strings, so multilingual labels can still differ even when the stable internal ID is identical

### Title
TGA reference matching could incorrectly fall back to DSC melting standards

### Date
2026-03-07

### Repro
1. Build a TGA processing payload with a reference temperature near 155 °C.
2. Call `build_calibration_reference_context(..., analysis_type="TGA", reference_temperature_c=155.0)`.
3. Observe that the reference state becomes `reference_checked` against `Indium (In)` instead of remaining unmatched for TGA.

### Suspected Cause
`utils.reference_data.find_nearest_reference()` searched TGA decomposition standards first but then also considered DSC melting standards, so a TGA midpoint could be matched to an unrelated DSC calibrant if it was numerically closer.

### Attempted Fix
Keep the helper brownfield and local; restrict the reference pool by analysis modality instead of introducing a new calibration engine or archive schema.

### Actual Fix
Limit `find_nearest_reference()` to DSC/DTA melting standards for DSC/DTA analyses and TGA decomposition standards for TGA analyses, then add a regression test that asserts a 155 °C TGA event remains `reference_out_of_window`.

### Verification
- Run `pytest tests/test_validation.py tests/test_project_io.py -q`
- Run `pytest -q`
- Confirm TGA project round-trip keeps `reference_out_of_window` for the 155 °C synthetic step while 200 °C still matches `CaC₂O₄·H₂O  Step 1`
