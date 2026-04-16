# Active task — MaterialScope

**Purpose:** **One active migration slice**—scope, goal, and **acceptance** only. Workflow philosophy: **`.cursor/rules/00-workflow.mdc`**. Durable design decisions: **`.ai/DECISIONS.md`** only.

**Status (2026-04-16):** **No active slice.** Phase 3 (3a + 3b + 3c) shipped as commit `279604b` on `origin/web-dash-plotly-migration`. Awaiting user decision on the next slice — see `.ai/SESSION.md` → Next step for the two candidate directions (Phase 4 DTA polish vs. first non-DTA modality migration).

When the next slice starts, this file should be **rewritten** with: title, goal, approach summary, in-scope files, explicit out-of-scope items, acceptance criteria, and a quick checklist — following the shape of the previous (now-closed) slice archived below.

---

## Last shipped slice (archive, for pattern reference)

**Title:** Dash DTA — Phase 3 batch (3a stepwise tabs + 3b processing preset CRUD + 3c richer results summary)

**Shipped:** commit `279604b` on `web-dash-plotly-migration`, pushed to origin on 2026-04-16.

**Goal (met):** reach near-full DTA parity with the Streamlit `ui/dta_page.py` page by (1) mirroring the stepwise Setup/Processing/Run UX, (2) exposing `core.preset_store` through the backend and wiring a preset panel into the Processing tab, (3) rendering the dataset-metadata header block at the top of the results column.

**Delivered (10 files, +2035 / -79):**

- `backend/models.py` — 6 new pydantic preset models (`PresetSummary`, `PresetListResponse`, `PresetSaveRequest`, `PresetSaveResponse`, `PresetLoadResponse`, `PresetDeleteResponse`).
- `backend/app.py` — 4 new modality-agnostic routes `GET/POST /presets/{analysis_type}` and `GET/DELETE /presets/{analysis_type}/{preset_name}`, all guarded by `_require_token` via `X-TA-Token`; `PresetLimitError` → 409, `PresetStoreError` → 400, missing → 404.
- `dash_app/api_client.py` — 4 helpers (`list_analysis_presets`, `save_analysis_preset`, `load_analysis_preset`, `delete_analysis_preset`).
- `dash_app/pages/dta.py`:
  - 3a: `_dta_left_column_tabs()` wraps the 6 left-column cards in a `dbc.Tabs` (Setup / Processing / Run) with stable shell ids `dta-tab-{setup,processing,run}-shell`. New `render_dta_tab_chrome` callback flips labels per locale.
  - 3b: `_preset_controls_card()` mounted as the first child of the Processing tab (shares the step's undo/redo stack); `dcc.Store("dta-preset-refresh", data=0)` added to `_processing_draft_stores`; 6 new callbacks (`render_dta_preset_chrome`, `refresh_dta_preset_options`, `toggle_dta_preset_action_buttons`, `apply_dta_preset`, `save_dta_preset`, `delete_dta_preset`). Apply pushes current draft onto the undo stack and restores `workflow_template_id` on `dta-template-select.value` when still valid (dash.no_update otherwise). Inline `html.Small` help hints with stable DOM ids added under every tunable smoothing / baseline / peak-detection control + a preset overview hint; existing per-card chrome callbacks extended with extra outputs to populate them.
  - 3c: new `_format_dataset_metadata_value` + `_build_dta_dataset_summary` helpers rendering an `html.Dl` definition-list (dataset filename / sample / mass mg / heating rate °C/min, with graceful fallbacks and conditional rows). New `result_placeholder_card("dta-result-dataset-summary")` mounted **above** `dta-result-metrics`; `display_result` callback extended to 6 outputs; empty-state and backend-error paths preserve the summary panel with a localized empty message.
- `utils/i18n.py` — **~40 new TR/EN bundle entries**: `dash.analysis.dta.tab.{setup,processing,run}` (3); `dash.analysis.dta.presets.*` (19, including `{error}` placeholder variants); `dash.analysis.dta.{smoothing,baseline,peaks}.help.*` and `dash.analysis.dta.presets.help.overview` (13); `dash.analysis.dta.summary.*` (8).
- `tests/test_backend_presets_api.py` **(new)** — 10 endpoint tests isolating storage via `monkeypatch.setenv("MATERIALSCOPE_HOME", tmp_path)`.
- `tests/test_dta_dash_page.py` — **+29** Phase-3 regression tests (tab structure, preset panel IDs in Processing tab, api_client forwarding, apply/save/delete callback bodies, hint rendering TR/EN, dataset-summary helper edge cases, `display_result` 6-panel empty/success/error paths).
- `.ai/SESSION.md`, `.ai/TASK.md`, `.ai/DECISIONS.md` — documentation updates including 2 new entries in DECISIONS.md.

**Out-of-scope (deferred to Phase 4 or later):**

- Quality dashboard / validation-warnings card.
- Raw-tab metadata panel.
- Applied-processing-summary expansion (per-step detail lines beyond current `processing_details_section`).
- Translation polish sweep (remaining EN-only literals across non-DTA pages).
- Keyboard shortcuts (Ctrl+Z / Ctrl+Shift+Z / Ctrl+Enter).
- Auto-advancing tabs after preset apply/save.
- Preset export/import across machines.
- Other modalities (DSC, TGA, FTIR, Raman, XRD) — the backend routes are modality-agnostic and will serve future slices without rework.

**Verification (pre-push):**

- `python -m pytest tests/test_dta_dash_page.py -x -q` → **86 passed** in 6.80s.
- `python -m pytest tests/test_backend_presets_api.py -x -q` → **10 passed** in 3.67s.
- `python -m pytest tests/test_backend_api.py tests/test_backend_details.py tests/test_backend_presets_api.py -x -q` → **49 passed, 1 skipped** in 14.32s.
- No regressions.

**Durable decisions recorded in `.ai/DECISIONS.md`:**

1. *Dash results summary: dataset metadata as a dedicated card above the metrics row* — definition-list format, `html.Dl` above `metrics_row`, single owner (`display_result`), reused by future modality pages.
2. *(Preset CRUD decision was scoped inside this slice and is captured by the commit message + Phase 3 section of SESSION.md; the modality-agnostic routing pattern is the reusable contract.)*
