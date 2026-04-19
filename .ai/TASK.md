# Task — MaterialScope

**Purpose:** One active migration slice — scope, goal, and acceptance only.

## Status: no active slice (2026-04-19)

The **TGA Dash DSC-parity layout** slice is **complete** (pending merge verification: full `pytest` if desired).

When starting new work, replace this file with the new slice goal, in/out of scope, and acceptance criteria.

---

### Archived: TGA Dash DSC-parity layout (done)

**Goal:** Bring the TGA Dash analysis page to near DSC-level layout and feature parity: ordered sections, analysis summary, validation/quality, raw metadata (DSC UX), literature compare, DTG card + cleaner main figure, export/report tests for TGA.

**In scope**

- [`dash_app/pages/tga.py`](dash_app/pages/tga.py): `dsc-results-surface`, section order, `workspace_dataset_detail`, builders, literature callbacks, figure/DTG split.
- [`utils/i18n.py`](utils/i18n.py): TGA summary, quality, DTG, literature strings (en/tr).
- Tests: [`tests/test_tga_dash_page.py`](tests/test_tga_dash_page.py), TGA workflow DOCX + export warning coverage.

**Acceptance**

- Section order matches plan; analysis summary shows dataset, sample, mass, heating rate, resolved unit mode, inference basis.
- Validation/quality shows status, counts, warnings, calibration/reference, `validation.checks` when present.
- Raw metadata: user-facing keys + collapsible technical block (DSC pattern).
- Literature compare: max claims, persist, compare, output + status (shared UI).
- Main figure without DTG overlay; DTG in dedicated card; figure capture still finds nested `dcc.Graph`.
- TGA run with mocked PNG: DOCX includes `word/media/` when `include_figures=True`; `collect_figure_export_warnings` covers TGA failed/missing bytes.

**Verification (at completion)**

- `uv run pytest tests/test_tga_dash_page.py` — 8 passed.
- `uv run pytest tests/test_backend_workflow.py::test_analysis_run_auto_registers_figure_for_tga_and_persists_into_exports_and_project` — pass.
- `uv run pytest tests/test_backend_exports.py` (collect warning tests used for TGA) — pass.
- `uv run pytest tests/test_dash_figure_capture_wiring.py` — 10 passed.

---

### Archived: DSC stabilization & literature recall + mini-patch (done)

**Goal:** Tighten DSC peak detection defaults, rebalance result layout, reduce metadata noise, improve thermal literature compare recall for weak metadata, surface no-result diagnostics, and fix follow-up issues (missing i18n key, legacy distance=1).

**Delivered**

- Peak detection defaults raised to `None` (auto-derive prominence/distance); batch_runner guard for DSC parity with DTA; legacy `distance=1` also normalized to `None`.
- Layout reorder: main DSC figure above raw metadata.
- Raw metadata split into user-facing keys + collapsible technical details subsection (with proper en/tr i18n labels).
- DSC behavior-first fallback queries expanded with broader vocabulary (differential scanning calorimetry, direction-specific, Tg-window variants).
- Literature compare technical diagnostics now show `search_mode`, `subject_trust`, `display_terms`, and executed fallback queries.
- `LiteratureContext.executed_queries` field added for UI diagnostic display.

**Verification (at completion)**

- 899 passed, 0 failures, 9 skipped across full suite.
- DSC, DTA, TGA, literature compare, and batch runner test files all green.
- i18n key leak confirmed fixed in both en and tr locales.

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
