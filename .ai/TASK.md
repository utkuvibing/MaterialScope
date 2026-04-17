# Active task — MaterialScope

**Purpose:** One active migration slice — scope, goal, and acceptance only.

## Status (2026-04-17): Phase 4 — DTA polish (shipped in working tree; commit pending)

**Goal:** Close remaining DTA parity gaps from the Phase 4 plan: quality/validation visibility, dedicated raw-metadata card, expanded applied-processing summary, preset apply/save tab auto-advance to Run, keyboard shortcuts (undo/redo/run), and DTA i18n polish.

**In scope**

- `[dash_app/pages/dta.py](dash_app/pages/dta.py)`: results column — `dta-result-quality`, `dta-result-raw-metadata`; extend `display_result` to consume `detail["validation"]` and `result` summary fields; wrap processing details in expandable UI with per-step parameter blocks; preset callbacks output `dta-left-tabs` → `dta-tab-run` on successful apply/save; Run tab shortcut hints.
- `[utils/i18n.py](utils/i18n.py)`: `dash.analysis.dta.quality.`*, `dash.analysis.dta.raw_metadata.*`, `dash.analysis.dta.processing.*` (expand + blocks), `dash.analysis.dta.shortcuts.*`.
- `[dash_app/assets/dta_shortcuts.js](dash_app/assets/dta_shortcuts.js)`: global keydown → click `dta-undo-btn` / `dta-redo-btn` / `dta-run-btn` when not in editable fields; support Ctrl or Meta.
- `[tests/test_dta_dash_page.py](tests/test_dta_dash_page.py)`: layout ids/order, eight-way `display_result`, preset tab outputs, optional helper tests.

**Out of scope**

- Non-DTA modalities; preset import/export; backend API contract changes unless strictly required; browser E2E (Playwright) for shortcuts — manual smoke noted.

**Acceptance**

- Layout includes `dta-result-quality` and `dta-result-raw-metadata` between metrics and figure; `display_result` returns eight outputs with consistent empty/error/success behavior.
- Quality card shows validation status and warning/issue counts (from `validation` + `result` fallback).
- Raw metadata card lists full `dataset.metadata` (sorted keys) or localized empty state.
- Processing section is expandable with JSON detail blocks for smoothing/baseline/peak steps when data exists.
- Successful preset apply/save sets left tabs active to Run; failures leave tab unchanged.
- Shortcut script present; Run tab shows localized shortcut hints.
- `pytest tests/test_dta_dash_page.py -x -q` and backend preset/API tests pass.

**Verification (recorded)**

- `python -m pytest tests/test_dta_dash_page.py -x -q` → **88 passed**
- `python -m pytest tests/test_backend_api.py tests/test_backend_details.py tests/test_backend_presets_api.py -x -q` → **49 passed, 1 skipped**