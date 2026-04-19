# Task — MaterialScope

**Purpose:** One active migration slice — scope, goal, and acceptance only.

## Status: no active slice (2026-04-19)

The **DSC Dash P0/P1 maturity** slice is **complete** and **pushed** (`0ff062c` on `web-dash-plotly-migration`).

When starting new work, replace this file with the new slice goal, in/out of scope, and acceptance criteria.

---

### Archived: DSC Dash P0/P1 maturity (done)

**Goal:** Bring Dash DSC to DTA-level maturity: literature compare, reliable figure capture path, pre-run dataset info, baseline temperature window + derivative preview, interpretation polish.

**Delivered**

- Literature compare + i18n; shared `literature_compare_ui` with DTA refactor.  
- DSC `dtg` in analysis state; optional derivative helper card.  
- Setup: prerun dataset card from `workspace_dataset_detail` + validation `checks`.  
- Processing: baseline region in draft → `processing_overrides`.  
- Event area: concise Tg one-liner; peaks/table unchanged.

**Verification (at completion)**

- `pytest tests/test_dsc_dash_page.py` and targeted `test_batch_runner` DSC test passed locally.  
- `pytest tests/test_dta_dash_page.py` passed after DTA literature refactor.
