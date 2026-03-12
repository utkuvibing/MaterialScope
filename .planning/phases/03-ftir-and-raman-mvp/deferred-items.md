# Deferred Items

## 2026-03-12

- Verification command `pytest -q tests/test_validation.py tests/test_result_serialization.py` has one pre-existing failure in `tests/test_validation.py::test_validate_thermal_dataset_surfaces_import_review_context`:
  - Expected `summary["checks"]["inferred_analysis_type"] == "TGA"`
  - Actual value is `"unknown"`
  - This issue is outside Task 3 spectral serialization/caution scope and was not auto-fixed in this execution.
