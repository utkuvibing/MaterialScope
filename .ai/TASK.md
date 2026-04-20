# Task — MaterialScope

**Purpose:** One active migration slice — scope, goal, and acceptance only.

## Status: no active slice (2026-04-20)

The **Dash TGA Streamlit→Dash exploration / guidance parity** slice is **complete**. Start a new slice by replacing the status block above.

---

### Archived: Dash TGA exploration + guidance parity vs Streamlit (done, 2026-04-20)

**Goal:** Close high-value Streamlit TGA gaps (undo/redo/reset, raw-quality pre-run panel, per-step reference callouts, workflow guide) without replacing the workspace-backed Setup / Processing / Run architecture.

**In scope**

- [`dash_app/components/tga_explore.py`](dash_app/components/tga_explore.py): undo stack helpers, raw stats + Dash panel, step reference callout, local signal quality metrics (no Streamlit import).
- [`dash_app/pages/tga.py`](dash_app/pages/tga.py): new stores and callbacks; Setup (workflow guide + raw quality); Processing (history card); hydrate from `tga-history-hydrate`; extended sync + preset load for history; summary atmosphere when metadata present.
- [`utils/i18n.py`](utils/i18n.py): workflow guide, raw quality, processing history, step reference, atmosphere label (en/tr).
- Tests: [`tests/test_tga_explore.py`](tests/test_tga_explore.py), [`tests/test_tga_dash_page.py`](tests/test_tga_dash_page.py).

**Acceptance**

- Undo restores prior processing draft; redo forward; reset restores default draft; buttons disabled when stacks empty; preset load records prior draft on stack.
- Raw quality panel shows dataset-driven stats/warnings before run; full post-run validation unchanged.
- Each key step card shows compact reference line or neutral fallback.
- Workflow guide renders collapsible copy; atmosphere appears in summary when `metadata.atmosphere` exists.

**Verification**

- `rtk pytest tests/test_tga_explore.py tests/test_tga_dash_page.py -q` — 28 passed.
- `rtk pytest tests/test_dash_figure_capture_wiring.py tests/test_dsc_tga_parity.py -q` — 16 passed.

---

### Archived: Dash literature compare on all analysis pages (done, 2026-04-20)

**Goal:** Use the same TGA-style literature compare workflow (shared card, max claims + persist + Compare, compact output, status alert, `literature_compare` API) on every Dash analysis page, not only TGA.

**In scope**

- [`dash_app/components/literature_compare_ui.py`](dash_app/components/literature_compare_ui.py): reusable card builder, claim coercion, compact preview constants.
- [`dash_app/pages/tga.py`](dash_app/pages/tga.py), [`dsc.py`](dash_app/pages/dsc.py), [`dta.py`](dash_app/pages/dta.py), [`xrd.py`](dash_app/pages/xrd.py), [`ftir.py`](dash_app/pages/ftir.py), [`raman.py`](dash_app/pages/raman.py): layout slot + three callbacks each (`render_*_literature_chrome`, toggle, compare).
- [`utils/i18n.py`](utils/i18n.py): modality-specific hint keys for XRD / FTIR / Raman; shared TGA literature prefix for bulk output strings.
- [`backend/app.py`](backend/app.py): default provider when `provider_ids` omitted — include **RAMAN**.
- Tests: [`tests/test_xrd_dash_page.py`](tests/test_xrd_dash_page.py), [`tests/test_raman_dash_page.py`](tests/test_raman_dash_page.py), [`tests/test_backend_details.py`](tests/test_backend_details.py).

**Acceptance**

- Each listed analysis page exposes `{prefix}-literature-*` controls and runs compare against the latest result id when enabled.
- Compact evidence/alternative preview limits match the TGA-style Dash layout.
- RAMAN compare without explicit `provider_ids` resolves the same default live provider path as FTIR.

**Verification**

- `rtk pytest tests/test_xrd_dash_page.py tests/test_raman_dash_page.py tests/test_backend_details.py::test_result_literature_compare_endpoint_defaults_live_provider_for_raman_results tests/test_backend_details.py::test_result_literature_compare_endpoint_defaults_live_provider_for_ftir_results -q` — 28 passed.
- `rtk pytest tests/test_dash_figure_capture_wiring.py -q` — 10 passed.

---

### Archived: TGA Dash presets and presettable processing (done, 2026-04-20)

**Goal:** Bring save/load/delete preset workflow to the TGA Dash page in a reusable (TGA-first) way: preset chrome, `processing_overrides`-backed controls, hydrate on load, clear save/dirty UX, compatible with existing preset APIs.

**In scope**

- [`dash_app/pages/tga.py`](dash_app/pages/tga.py): preset card near workflow; processing controls; stores; callbacks; helpers for draft/snapshot/preset save body; `run_tga_analysis` passes `processing_overrides`.
- [`utils/i18n.py`](utils/i18n.py): TGA preset and processing strings (en/tr).
- [`tests/test_tga_dash_page.py`](tests/test_tga_dash_page.py).

**Acceptance**

- Presets list/load/save/delete use `list_analysis_presets` / `load_analysis_preset` / `save_analysis_preset` / `delete_analysis_preset` for analysis type `TGA`.
- Saved payload includes `workflow_template_id` (API field) plus `processing` with `smoothing`, `step_detection`, and `method_context` (`tga_unit_mode_*`) so unit mode round-trips.
- Run uses current UI: `workflow_template_id`, `unit_mode`, and `processing_overrides` from the draft store.
- Load hydrates template, unit, controls, draft, snapshot baseline; dirty indicator when UI diverges; empty preset list and API errors handled in UI copy.

**Verification**

- `rtk pytest tests/test_tga_dash_page.py -q` — 19 passed.
- `rtk pytest tests/test_backend_presets_api.py tests/test_preset_store.py -q` — 14 passed.

---

### Archived: Dash literature compare clickable DOI/URL (done, 2026-04-20)

**Goal:** Make literature references open in a new tab (Streamlit-like) across all Dash analysis pages by fixing the shared renderer only.

**In scope**

- [`dash_app/components/literature_compare_ui.py`](dash_app/components/literature_compare_ui.py): DOI/URL normalization, `href` on retained rows, linked titles and meta/rationale DOI text; preserve `evidence_preview_limit` / compact layout.
- [`tests/test_literature_compare_ui.py`](tests/test_literature_compare_ui.py).

**Acceptance**

- DOI variants normalize to `https://doi.org/...`; explicit `http(s)` URLs used when no resolvable DOI; linked citation DOI/URL used when comparison row has no direct link.
- Titles are anchors with `target="_blank"` and `rel="noopener noreferrer"` when a link exists; plain text otherwise.
- TGA preview “show more” path still renders multiple linked rows.

**Verification**

- `rtk pytest tests/test_literature_compare_ui.py tests/test_dsc_dash_page.py tests/test_tga_dash_page.py -q` — 50 passed.

---

### Archived: TGA Dash UX polish (done, 2026-04-20)

**Goal:** Improve TGA results UX without structural layout changes: validation easier to notice and more readable, fewer key-step cards for high-step datasets, denser literature compare, metrics/summary prioritization, lighter main figure; follow-up pass nested raw checks, clarified table authority, aligned figure markers with curated steps, and tightened compact literature.

**In scope**

- [`dash_app/pages/tga.py`](dash_app/pages/tga.py): quality (open + badges; checks under nested technical details); `_tga_curated_step_rows_for_ui` for cards + figure; step notes; metrics; figure caption + marker/vline rules; TGA literature preview kwargs.
- [`dash_app/components/literature_compare_ui.py`](dash_app/components/literature_compare_ui.py): optional preview limits; compact evidence and claims when TGA-style preview mode is active.
- [`utils/i18n.py`](utils/i18n.py): en/tr for validation technical title, step authority note, truncation copy, literature hints and compact claims.
- [`tests/test_tga_dash_page.py`](tests/test_tga_dash_page.py).

**Acceptance**

- Warnings/issues expand quality by default and show header badges; main panel is product-facing; full `validation.checks` behind nested “Technical validation details”.
- ≥7 steps → at most 6 ranked step cards + notes (truncation + table as source of truth); step table lists all rows.
- TGA literature: preview + show-more; compact rows; clearer expand affordance; long generated-claims lists collapsible.
- Metrics: steps, total loss, residue, unit mode, validation; summary has no duplicate unit rows.
- Main figure: caption (steps, loss, residue); first `dcc.Graph` extractable for capture; DTG separate; markers match curated step subset.

**Verification**

- `rtk pytest tests/test_tga_dash_page.py tests/test_dsc_dash_page.py -q` — 40 passed (or equivalent `.venv/bin/python -m pytest …`).

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
