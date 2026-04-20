# Decisions — MaterialScope

**This file is the only durable log for design, architecture, and workflow commitments.** Session notes belong in **`.ai/SESSION.md`**; slice completion in **`.ai/TASK.md`**; defects in **`.ai/BUGS.md`**. Process details: **`.cursor/rules/00-workflow.mdc`**.

---

## 2026-04-20 — Thermal Dash pages: Processing history card + neutral Reset styling

**Decision:** DSC and DTA expose a **Processing history** card on the Processing tab (before presets) with Undo, Redo, and Reset to defaults, mirroring TGA: one merged callback per page driven by `dash.callback_context.triggered_id`, updating `processing-draft`, undo/redo stacks, and a small `*-history-status` line. Smoothing (and other section) chrome callbacks no longer own undo/redo/reset **button label** outputs—those live in dedicated `render_*_processing_history_chrome` callbacks. **Reset to defaults** uses Bootstrap **`secondary` outline** (same as Undo/Redo), not **`warning`**, so reset is not confused with validation severity.

**Reason:** Parity across TGA/DSC/DTA; yellow/warning is reserved for validation and alerts.

**Consequence / future:** Any new analysis page with a processing draft + undo stack should reuse this card + merged handler pattern for predictable wiring and theming.

---

## 2026-04-20 — TGA Dash presets: unit mode inside `processing.method_context`; overrides-only run

**Decision:** On the TGA Dash page, persist **declared unit mode** in preset `processing.method_context` (`tga_unit_mode_declared` / `tga_unit_mode_label`) together with `smoothing` and `step_detection`, because the SQLite preset envelope only stores `workflow_template_id` + `processing` (no separate `unit_mode` column). On **Run**, continue sending `unit_mode` as the existing `/analysis/run` field when not `auto`, and send **`processing_overrides`** built only from smoothing + step_detection (normalized from the UI draft store).

**Reason:** Matches the backend preset store contract and `processing_overrides` merge rules (`update_processing_step` / `method_context`); avoids a backend migration while still making presets meaningful for TGA.

**Consequence / future:** DSC/DTA preset pages can follow the same pattern for any “run-time” field not in the preset envelope. Reuse `_apply_processing_overrides` semantics: Dash should only emit override sections the backend accepts for that modality.

---

## 2026-04-20 — TGA processing draft sync: `prevent_initial_call="initial_duplicate"`

**Decision:** The callback that writes `tga-processing-draft` from control `Input`s uses `Output(..., allow_duplicate=True)` with `prevent_initial_call="initial_duplicate"` so it can coexist with layout-provided initial store data and preset-load writers without `DuplicateCallback` registration errors on Dash ≥2.18.

**Reason:** Dash requires either `prevent_initial_call=True` or `initial_duplicate` when combining `allow_duplicate` with an initial fire; we need the first client pass to align store + controls without ordering races.

**Consequence / future:** Other pages adding a similar “controls → draft store” mirror should use the same pattern when the store is also written by load/reset callbacks.

---

## 2026-04-20 — Dash literature compare: shared DOI/URL resolution and linked titles

**Decision:** Implement DOI normalization (`https://doi.org/...`), optional HTTP URL fallback, and `resolve_literature_href` (direct DOI → direct URL → first linked citation DOI → first linked citation URL) inside `dash_app/components/literature_compare_ui.py`. Render retained evidence titles as `html.A` when a URL exists; link DOI text in citation meta and linkify bare DOI tokens in comparison rationale strings. No per-modality Dash page changes.

**Reason:** DSC/DTA/TGA all use `render_literature_output`; centralizing avoids drift and restores Streamlit-like “open paper in new tab” behavior.

**Consequence / future:** Any new analysis page that reuses this renderer gets links automatically; edge cases (non-DOI URLs in free-text rationale) remain plain unless matched as DOI tokens.

---

## 2026-04-20 — TGA quality panel: `validation.checks` under nested technical details

**Decision:** Keep status, warning/issue counts, warning/issue lists, and calibration/reference in the main TGA quality alert; render `validation.checks` only inside a collapsed “Technical validation details” `<details>` block.

**Reason:** The flat checks list read like a backend inspection dump and obscured user-meaningful validation content.

**Consequence / future:** Power users expand one nested section for import/inference keys; empty checks omit the block.

---

## 2026-04-20 — TGA figure markers use the same curated step rows as key-step cards

**Decision:** Add `_tga_curated_step_rows_for_ui` and use it for both `_build_step_cards` midpoint/card data and `_build_figure` midpoint marker traces so the annotated set always matches the curated ranked subset (including ordering by significance when all steps fit the cap).

**Reason:** Cards and plot could diverge (e.g. raw row order vs ranked cap), which confused interpretation on high-step datasets.

**Consequence / future:** Any change to capping or ranking logic should touch this helper once.

---

## 2026-04-20 — TGA literature compare uses optional preview limits on shared `render_literature_output`

**Decision:** Add optional `evidence_preview_limit` and `alternative_preview_limit` to `dash_app/components/literature_compare_ui.py::render_literature_output` (defaults `None` = unchanged full layout). TGA passes small limits (2 / 1) so retained references collapse behind a `<details>` “show N more” block with lighter row chrome; DSC/DTA call sites unchanged.

**Reason:** TGA literature output was visually heavy on the page; other modalities did not request a denser default.

**Consequence / future:** Any page may opt in with the same kwargs; keep defaults `None` so existing tests and layouts stay stable.

---

## 2026-04-19 — Literature: opt-in fixture fallback when OpenAlex env is missing

**Decision:** When the default provider list is only `openalex_like_provider` and `build_openalex_like_client_from_env()` would return `None`, optionally expand to `["openalex_like_provider", "fixture_provider"]` if `MATERIALSCOPE_LITERATURE_FIXTURE_FALLBACK` (or `THERMOANALYZER_LITERATURE_FIXTURE_FALLBACK`) is truthy (`1`/`true`/`yes`/`on`), and set `filters["allow_fixture_fallback"] = True` for traceability.

**Reason:** Recall/query improvements do not help if the live HTTP client is never configured; local dev and demos need an explicit, safe path without silently pretending fixture data is live OpenAlex.

**Consequence / future:** Production should set `MATERIALSCOPE_OPENALEX_EMAIL` or API key; fixture mode remains dev/demo-only and must stay opt-in.

---

## 2026-04-19 — DSC peak detection defaults use auto-derivation (None) instead of explicit 0.0/1

**Decision:** Set `_DSC_PEAK_DETECTION_DEFAULTS` to `prominence=None, distance=None` and convert user-input 0.0/1 to `None` in `_normalize_peak_detection_values`. Add a batch_runner guard for the DSC path (same pattern as DTA at lines 624-627).

**Reason:** Explicit `prominence=0.0` bypassed the auto-derivation in `find_thermal_peaks` (which only activates when prominence is `None`), causing every tiny signal fluctuation to register as a peak on simple single-event DSC traces.

**Consequence / future:** DTA already uses this pattern. TGA migration should follow the same approach. The `peak_analysis.py` auto-derivation (10% of signal range, n//20 distance) becomes the effective floor for all thermal modalities.

---

## 2026-04-19 — DSC result layout promotes analysis figure above raw metadata

**Decision:** Reorder DSC right-column layout so the main figure appears immediately after quality/validation, with raw metadata demoted to the second-to-last position before literature compare.

**Reason:** The main DSC figure is the primary analysis artifact; burying it below raw metadata made the results surface feel debug-centric rather than analysis-first.

**Consequence / future:** Other modalities (TGA, XRD, FTIR, Raman) should follow the same analysis-first ordering when they get full Dash surfaces.

---

## 2026-04-19 — Raw metadata split into user-facing and technical subsections

**Decision:** Define `_DSC_USER_FACING_METADATA_KEYS` (sample_name, display_name, sample_mass, heating_rate, instrument, vendor, file_name, source_data_hash). Show those directly; demote all other keys into a nested collapsible "Technical details" section.

**Reason:** All-metadata-equal rendering exposed internal/debug fields alongside user-relevant ones, making the panel noisy without adding analytical value.

**Consequence / future:** Same pattern can be applied to DTA, TGA, and other modality pages. The key set should be reviewed when new metadata fields are added.

---

## 2026-04-19 — DSC behavior-first literature fallback queries expanded with broader vocabulary

**Decision:** Expand DSC behavior-first fallback queries from 2-3 to 4+ variants, including "differential scanning calorimetry", direction-specific terms ("endotherm/endothermic", "exotherm/exothermic/crystallization"), and Tg-window variants ("DSC glass transition X C polymer").

**Reason:** When sample_name is absent/generic, the original 2-3 fallback queries had narrow vocabulary and poor recall. `_thermal_search_queries` caps at 5, so ordering by relevance matters.

**Consequence / future:** The 5-query cap means the most relevant queries are used automatically. Future modalities should define similarly broad fallback sets.

---

## 2026-04-19 — Literature compare technical diagnostics include search_mode, subject_trust, and executed queries

**Decision:** Add `search_mode`, `subject_trust`, `query_display_terms`, and `executed_queries` to the collapsible technical details section in `literature_compare_ui.py`. Add `executed_queries: list[str]` field to `LiteratureContext` dataclass.

**Reason:** "No literature found" was a dead end without diagnostic context. Showing which queries were executed and why (search_mode, subject_trust) makes no-result cases actionable instead of opaque.

**Consequence / future:** All modalities using `render_literature_output` benefit automatically. No per-page changes needed.

---

## 2026-04-18 — Figure persistence moved to shared backend save path

**Decision:** Register a result snapshot figure in shared backend state during saved `/analysis/run` and batch save flows, instead of relying solely on page-specific Dash capture callbacks.

**Reason:** Real app behavior showed visible graphs could still fail to persist for export/project flows when UI capture callbacks were skipped or failed at runtime.

**Consequence / future:** Figure persistence is now modality-agnostic and resilient for saved results. Page-level capture remains useful for richer figure overrides but is no longer the single point of failure.

---

## 2026-04-18 — Shared figure rendering helper with fallback

**Decision:** Introduce `core/figure_render.py` and route Dash capture paths through `render_plotly_figure_png`, with fallback rendering when primary Plotly static export fails.

**Reason:** Runtime renderer availability differs across environments; hard dependency on one render path caused missed registrations.

**Consequence / future:** Capture reliability improves across environments. Future work can tune fallback quality without touching every modality page.

---

## 2026-04-18 — Branding upload gets explicit pre-save pending state

**Decision:** Add a dedicated Dash callback that renders pending logo feedback (`branding-logo-selection`) immediately from upload contents, independent of saved branding state.

**Reason:** Previously the UI only showed backend-persisted logo; users received no confirmation after file selection before clicking Save Branding.

**Consequence / future:** UX now clearly distinguishes "selected but not saved yet" from "currently saved logo". Save flow remains unchanged.

---

## 2026-04-18 — DTA Dash figure view_mode contract

**Decision:** Introduce an explicit `view_mode` parameter (`"result" | "debug"`) on `_build_dta_go_figure` and `_build_figure` in `dash_app/pages/dta.py`, defaulting to `"result"`. The mode controls trace hierarchy, annotation density, and hover detail. Capture/report paths always force `"result"` regardless of interactive state.

**Reason:** The current DTA figure builder has no mode concept — all overlays render identically whether the user is inspecting analysis or exporting a publication figure. This makes result charts cluttered and debug charts no richer than necessary. An explicit mode contract separates concerns cleanly without touching the analysis pipeline.

**Consequence / future:** Other modalities (DSC, TGA) can adopt the same `view_mode` pattern when they migrate to Dash. The `dta-figure-view-mode` selector pattern should be reused.

---

## 2026-04-18 — Result mode as default for all saved/exported figures

**Decision:** All figure capture (`_capture_dta_figure_png`, `capture_dta_figure`) and report registration paths use `view_mode="result"` unconditionally. The interactive `dta-figure-view-mode` selector only affects the live `dcc.Graph` in the result panel.

**Reason:** Report Center exports and PNG captures must be publication-quality by default. Debug overlays should never leak into saved artifacts unless explicitly requested in a future slice.

**Consequence / future:** If a future slice adds a "debug export" button, it can pass `view_mode="debug"` to the builder, but the default capture path remains result-only.

---

## 2026-04-18 — Annotation strategy: result mode minimal, debug mode rich

**Decision:** In `result` mode, onset/endset vertical guide lines and their text annotations are suppressed; only primary-event peak temperature labels appear on-chart. All onset/endset/area/height detail moves to `hovertemplate` on peak markers and remains in the event detail table/cards. In `debug` mode, the current annotation richness (guide lines with labels, all peak text) is preserved.

**Reason:** Overlapping onset/endset labels are the primary source of chart clutter in dense DTA results. Hover and table already carry this information. Result mode should be clean enough for publication export.

**Consequence / future:** The `_ANNOTATION_MIN_SEP` and `_PRIMARY_EVENT_LIMIT` constants remain relevant for debug mode. Result mode uses a simpler threshold (primary events only, no onset/endset vlines).

---

## 2026-04-19 — Shared Dash literature compare rendering

**Decision:** Move literature compare output + status alert rendering into `dash_app/components/literature_compare_ui.py`, parameterized by an `i18n_prefix` (e.g. `dash.analysis.dta.literature` / `dash.analysis.dsc.literature`). DTA page delegates to the shared module; DSC uses the same contract with DSC-specific keys.

**Reason:** Avoid duplicating large rendering trees and keep DTA/DSC behavior aligned.

**Consequence / future:** New modalities can reuse the helper by supplying a matching key namespace in `utils/i18n.py`.

---

## 2026-04-19 — DSC analysis state includes `dtg` (derivative) curve

**Decision:** After baseline correction in `_execute_dsc_batch`, compute a first-derivative curve vs temperature with `core.preprocessing.compute_derivative` and store it in modality state as `dtg`, exposed via existing `analysis_state_curves`.

**Reason:** Enables a compact derivative helper in Dash without a second full “debug” surface; aligns with backend-driven curves contract.

**Consequence / future:** Downstream UIs should treat `dtg` as optional (may be empty if insufficient points).
