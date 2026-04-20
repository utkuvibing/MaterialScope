# Task — MaterialScope

**Purpose:** One active migration slice — scope, goal, and acceptance only.

## Status: no active slice (2026-04-21)

The **FTIR literature + Setup cleanup** slice is **complete**. Start a new slice by replacing the status block above.

---

### Archived: FTIR literature compare + Raw Data Quality removal (done, 2026-04-21)

**Goal:** Remove the low-value FTIR Raw Data Quality block from Setup; bring FTIR literature compare to **TGA-level** traceability and FTIR-specific queries/claims (no generic placeholder path), without redesigning the FTIR page or breaking shared literature UI.

**In scope**

- [`dash_app/pages/ftir.py`](dash_app/pages/ftir.py): remove raw-quality card and callbacks; keep Setup / Processing / Run and DSC/TGA/DTA alignment.
- [`dash_app/components/ftir_explore.py`](dash_app/components/ftir_explore.py): remove raw-quality stats/panel; keep undo/redo + `downsample_rows`.
- [`core/ftir_literature_query_builder.py`](core/ftir_literature_query_builder.py): traceable query payload (modality, match status, peaks, wavenumber terms from evidence, library-unavailable vs matched vs no_match semantics).
- [`core/literature_compare.py`](core/literature_compare.py): `_compare_ftir_result_to_literature` + FTIR relevance/distractor penalties; `compare_result_to_literature` branches **FTIR**.
- [`core/scientific_reasoning.py`](core/scientific_reasoning.py): `_build_ftir_reasoning` + dispatch.
- [`core/literature_models.py`](core/literature_models.py): `executed_queries` through `normalize_literature_context` / `to_dict`.
- [`core/experiment_recommender.py`](core/experiment_recommender.py): FTIR follow-up recommendations.
- Tests: [`tests/test_literature_compare.py`](tests/test_literature_compare.py), [`tests/test_ftir_dash_page.py`](tests/test_ftir_dash_page.py), [`tests/test_result_serialization.py`](tests/test_result_serialization.py).

**Acceptance**

- FTIR Setup tab no longer shows Raw Data Quality; layout IDs/tests updated.
- FTIR literature uses dedicated compare path; provider **not_configured** vs **no_real_results** remain distinct; no generic “not specialized” string on normal FTIR paths.
- Shared literature renderer and FTIR figure/preset/export wiring unchanged by intent.

**Verification**

- `rtk pytest tests/test_literature_compare.py tests/test_ftir_dash_page.py tests/test_result_serialization.py::test_serialize_ftir_result_persists_no_match_caution_and_evidence -q` — **111 passed**.

---

### Archived: FTIR follow-up pass — peaks, figure, library diagnostics, i18n (done, 2026-04-21)

**Goal:** After science-chain stabilization, improve FTIR peak retention, normalized-trace and overlay clarity, library-vs-chemistry messaging, and FTIR literature technical i18n — without redesigning the FTIR page or bypassing backend truth.

**In scope**

- [`core/batch_runner.py`](core/batch_runner.py): adaptive spectral prominence + two-pass fallback; `ftir.general` peak defaults; analysis-state diagnostics `plot_normalized_primary_axis` / `normalized_axis_ratio_vs_corrected`; `match_status` **`library_unavailable`** when no ranked rows and library path is missing/unconfigured (vs real **`no_match`**); matching caution payload.
- [`core/validation.py`](core/validation.py), [`core/result_serialization.py`](core/result_serialization.py): spectral validation and caution serialization for **`library_unavailable`**.
- [`dash_app/pages/ftir.py`](dash_app/pages/ftir.py): aligned UI peak defaults; figure trace policy (hide smoothed when corrected; baseline when helpful; conditional normalized); peak marker Y from displayed query path; empty match panels use library-unavailable copy when applicable.
- [`dash_app/components/literature_compare_ui.py`](dash_app/components/literature_compare_ui.py): collapsible titles use **`literature_t`** + fallback.
- [`utils/i18n.py`](utils/i18n.py): `match_status.library_unavailable`, FTIR match body, FTIR literature `technical_details_title` + `technical.*` keys.
- Tests: [`tests/test_batch_runner.py`](tests/test_batch_runner.py), [`tests/test_ftir_dash_page.py`](tests/test_ftir_dash_page.py), [`tests/test_validation.py`](tests/test_validation.py).

**Acceptance**

- Wide multi-feature synthetic FTIR retains multiple detected peaks (regression test).
- Normalized trace suppressed on the main figure when backend flags shared-axis ratio too low; figure still renders with primary traces.
- Empty library UI distinguishes **`library_unavailable`** from inconclusive chemistry **`no_match`**.
- FTIR literature technical-details heading never shows a raw i18n key in the UI.
- Presets, export, literature compare, and figure capture wiring unchanged by intent.

**Verification**

- `rtk pytest tests/test_batch_runner.py tests/test_ftir_dash_page.py tests/test_validation.py::test_enrich_ftir_result_validation_adds_library_unavailable_semantics -q` — **71 passed**.
- Targeted: `tests/test_result_serialization.py`, `tests/test_literature_compare_panel.py`, `tests/test_literature_compare.py`, `tests/test_raman_dash_page.py`.

---

### Archived: FTIR science chain stabilization (done, 2026-04-21)

**Goal:** Fix the FTIR preprocessing / peak-detection / matching science chain so results are scientifically honest and diagnostically transparent, without redesigning the FTIR page.

**In scope**

- [`core/batch_runner.py`](core/batch_runner.py): signal-role inference (`_infer_spectral_signal_role`), transmittance inversion (`_maybe_invert_spectral_signal`), real baseline estimation with `pybaselines` (`_estimate_spectral_baseline`), baseline validation (`_validate_spectral_baseline`), guarded normalization (`_normalize_spectral_signal`), robust peak detection with `scipy.signal.find_peaks` + fallback (`_detect_spectral_peaks`), matching basis alignment (`_rank_spectral_matches` uses `query_signal`).
- [`backend/library_cloud_service.py`](backend/library_cloud_service.py): updated to call new spectral helper signatures.
- [`backend/models.py`](backend/models.py): `AnalysisStateCurvesResponse` extended with `diagnostics`.
- [`backend/app.py`](backend/app.py): `analysis_state_curves` endpoint returns `diagnostics` from analysis state.
- [`dash_app/pages/ftir.py`](dash_app/pages/ftir.py): figure rendering suppresses invalid traces; legend labels “(inverted)” for transmittance; diagnostic notes render below figure.
- Tests: [`tests/test_batch_runner.py`](tests/test_batch_runner.py) (8 new tests), [`tests/test_ftir_dash_page.py`](tests/test_ftir_dash_page.py) (1 new test).

**Acceptance**

- Baseline is validated and suppressed when implausible; corrected trace falls back to smoothed; warning explains why.
- Normalization is skipped when it would produce a near-flat or non-informative result; warning explains why.
- Transmittance data is inverted before peak detection so troughs become peaks; inversion is recorded in diagnostics and legend.
- Peak detection uses `scipy.signal.find_peaks` with auto-fallback prominence; zero peaks surface a concrete reason.
- Similarity matching runs on the best available processed signal (normalized if informative, else corrected).
- Dash figure does not show silently invalid overlay traces; diagnostics appear as notes below the plot.
- All existing FTIR page flows (presets, literature compare, figure export) continue to work.

**Verification**

- `rtk pytest tests/test_batch_runner.py -q` — **29 passed**.
- `rtk pytest tests/test_ftir_dash_page.py -q` — **36 passed**.
- `rtk pytest tests/test_dash_workflow_regression.py -q` — **76 passed**.
- FTIR end-to-end regression (`load-sample-ftir`) passes.

---

### Archived: Dash FTIR full product-grade page (done, 2026-04-20)

**Goal:** Bring the FTIR Dash analysis page from a first-slice implementation to a full product-grade page aligned with the existing DSC/TGA/DTA standard.

**In scope**

- [`dash_app/pages/ftir.py`](dash_app/pages/ftir.py): complete rewrite to standard left-column tabs (Setup / Processing / Run) + right-column result surface (summary, metrics, quality, figure, top-match, peak cards, match table, processing, raw metadata, literature compare); processing draft store + controls; preset workflow; undo/redo/reset; figure overlays.
- [`dash_app/components/ftir_explore.py`](dash_app/components/ftir_explore.py): raw-quality stats, spacing/irregularity hints, undo/redo helpers, panel builder.
- [`backend/models.py`](backend/models.py): `AnalysisStateCurvesResponse` extended with `normalized`, `peaks`, `has_normalized`, `has_peaks`.
- [`backend/app.py`](backend/app.py): `analysis_state_curves` endpoint returns new fields + safe `_peak_to_dict` conversion for DSC/DTA dataclass peaks.
- [`utils/i18n.py`](utils/i18n.py): ~45 FTIR-specific keys (en/tr).
- Tests: [`tests/test_ftir_dash_page.py`](tests/test_ftir_dash_page.py).

**Acceptance**

- FTIR page matches DSC/TGA/DTA section order and design language exactly.
- Processing controls (baseline, normalization, smoothing, peak detection, similarity matching) map into `processing_overrides` for `analysis_run`.
- Preset payload saves and loads both `workflow_template_id` and full FTIR processing draft.
- Backend exposes `normalized` signal and `peaks` via `analysis_state_curves`; Dash page shows backend-truth peaks without client-side re-detection.
- Figure shows raw/smoothed/corrected/baseline/normalized overlays with reversed x-axis and limited peak labels (top 8).
- Top-match hero summary panel renders candidate name, score, confidence badge, and overlap explanation (overlay preview deferred).
- Literature compare uses FTIR-specific i18n prefix and shared renderer unchanged.
- Undo/redo/reset work with dirty-state tracking on the Processing tab.

**Verification**

- `rtk pytest tests/test_ftir_dash_page.py -q` — **35 passed**.
- `rtk pytest tests/test_dash_workflow_regression.py tests/test_dash_figure_capture_wiring.py tests/test_analysis_page_components.py tests/test_preset_store.py tests/test_tga_dash_page.py tests/test_dsc_dash_page.py -q` — **142 passed**.
- `rtk pytest tests/test_backend_workflow.py -q` — **13 passed**.

---

### Archived: DSC/DTA Dash Processing history parity + TGA reset styling (done, 2026-04-20)

**Goal:** Match the TGA Processing tab “Processing history” UX on DSC and DTA (Undo / Redo / Reset to defaults, draft-only hint, status line). Align **Reset to defaults** with the neutral secondary outline palette (not warning).

**In scope**

- [`dash_app/pages/dsc.py`](dash_app/pages/dsc.py): history card, `render_dsc_processing_history_chrome`, merged `dsc_processing_history_actions`; smoothing chrome without undo/redo/reset children.
- [`dash_app/pages/dta.py`](dash_app/pages/dta.py): same pattern (`render_dta_processing_history_chrome`, `dta_processing_history_actions`).
- [`dash_app/pages/tga.py`](dash_app/pages/tga.py): `tga-processing-reset-btn` → `color="secondary"`.
- [`utils/i18n.py`](utils/i18n.py): DSC/DTA `processing.history_hint` keys (en/tr).
- [`tests/test_dta_dash_page.py`](tests/test_dta_dash_page.py): smoothing chrome tuple length / hint indices.

**Acceptance**

- Processing tab shows history card before presets (DSC/DTA); undo/redo/reset update draft + stacks and show localized history status where implemented.
- Reset uses secondary outline like Undo/Redo on TGA/DSC/DTA history controls.
- No duplicate conflicting callbacks for the same outputs.

**Verification**

- `rtk pytest tests/test_dta_dash_page.py tests/test_dsc_dash_page.py -q` — 127 passed.

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
