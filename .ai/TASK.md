# Task — MaterialScope

**Purpose:** One active migration slice — scope, goal, and acceptance only.

## Status (2026-04-19): DSC Dash P0/P1 maturity — implemented

**Goal:** Bring Dash DSC to DTA-level maturity: literature compare, reliable figure capture path, pre-run dataset info, baseline temperature window + derivative preview, interpretation polish.

**In scope (done)**

- Literature compare panel + callbacks + i18n (`dash.analysis.dsc.literature.*`); shared `literature_compare_ui` with DTA refactor.
- DSC `dtg` in analysis state from `core/batch_runner.py` (`compute_derivative` on corrected signal); optional derivative helper card (not a second “hero” figure).
- Setup tab: prerun dataset card from `workspace_dataset_detail` + validation `checks`.
- Processing: baseline region controls threaded into draft overrides (`baseline.region`).
- Event cards: concise Tg one-liner + lighter section chrome; primary peaks unchanged.

**Verification**

- `.venv/bin/python -m pytest tests/test_dsc_dash_page.py tests/test_batch_runner.py::test_execute_dsc_batch_template_saves_normalized_record -q` — passed (19 tests in DSC file + 1 batch).
- `tests/test_dta_dash_page.py` — passed (DTA unaffected by literature refactor).
