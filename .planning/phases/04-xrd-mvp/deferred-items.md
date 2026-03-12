# Deferred Items

## 2026-03-12

1. `pytest -q` full-suite gate is blocked by environment-level tmpdir permission errors in unrelated tests:
   - `tests/test_diagnostics.py` (tmp_path fixture setup)
   - `tests/test_license_manager.py` (tmp_path fixture setup)
   - `tests/test_windows_launcher.py` (tmp_path fixture setup)
   - Error pattern: `PermissionError: [WinError 5] Access denied` under pytest temp roots.

2. One unrelated assertion mismatch exists outside 04-04 scope:
   - `tests/test_backend_batch.py::test_batch_run_xrd_preprocessing_path_returns_saved_with_peak_summary`
   - Expected `match_status == "not_run"`, actual `"no_match"`.