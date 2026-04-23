# Decisions — MaterialScope
 
**This file is the only durable log for design, architecture, and workflow commitments.** Session notes belong in **`.ai/SESSION.md`**; slice completion in **`.ai/TASK.md`**; defects in **`.ai/BUGS.md`**. Process details: **`.cursor/rules/00-workflow.mdc`**.
 
---

## 2026-04-23 — P1-2 completed: figure artifact toolbar is shared UI while result slots remain stable

**Decision:**

1. Manual figure artifact controls are standardized across all six Dash modalities as **Snapshot** and **Report figure** actions.
2. The existing `<modality>-result-figure` slot remains the stable display/capture contract; toolbar surfaces wrap the slot instead of renaming or replacing it.
3. Shared code for figure artifacts lives in `dash_app/components/figure_artifacts.py` and is limited to pure UI/metadata helpers. Page modules keep Dash callbacks, API calls, and result-specific orchestration.
4. Artifact panels refresh only on latest-result changes and successful explicit snapshot/report actions; failed/skipped explicit actions update inline status without refetching artifacts.
5. Figure extraction from Dash component trees now follows visual order (parent before descendants, children left-to-right/top-to-bottom) so primary result graphs are captured before later debug/secondary graphs.

**Reason:** XRD had the clearest user-facing figure artifact controls, but other modalities only had background auto-capture. Standardizing the toolbar improves report UX while preserving existing auto-capture resilience and avoiding a backend API/schema change.

**Consequence / future:** New analysis pages should use the shared figure artifact surface and keep their result figure slot stable. Any future debug-export feature should be explicit; default report figures remain primary/result-oriented.

---

## 2026-04-22 — P0-5 completed: DSC mass normalization is a first-class processing step with default-ON backward compatibility

**Decision:**

1. DSC mass normalization is implemented as a first-class **`normalization`** processing section, not as ad-hoc UI state or `method_context`.
2. The Dash DSC page exposes the control in the **Setup** tab, but the selected value persists end-to-end through **processing draft defaults, hydration, preset save/load, undo/redo/reset history, and `/analysis/run` processing overrides**.
3. Backend DSC batch execution in `core/batch_runner.py` honors **`signal_pipeline.normalization.enabled`** explicitly and records the resolved normalization state in saved processing payloads.
4. The default remains **enabled / on** so that introducing the control does not silently change existing scientific behavior for current templates and saved flows.

**Reason:** The missing Dash control was a real parity gap, but the pre-existing backend behavior already normalized DSC by mass whenever sample mass was available. Making normalization explicit while preserving the old effective default closes the parity gap without introducing silent output drift.

**Consequence / future:** Any future DSC UX/report/export work should treat normalization state as part of the authoritative processing trace. If product later wants to change the default, that must be treated as an intentional behavior change and called out separately.

---

## 2026-04-22 — P0-5 planning: DSC mass normalization will be user-controlled but default ON

**Decision:**

1. DSC Dash will gain an explicit **Normalize by mass** control, exposed in the **Setup** flow, but the effective normalization state must persist end-to-end through **draft/default state, preset save/load, undo/redo/reset history, run payloads, and backend execution**.
2. The default for the new control is **enabled / on** unless an existing saved draft, preset, or other persisted processing payload explicitly records a different value.
3. Backend DSC execution must **honor the selected value explicitly** instead of always normalizing whenever sample mass exists.
4. This slice is intended to **close the Dash control gap without introducing a silent scientific behavior regression** for existing datasets and saved flows that already depend on today's effective always-normalized behavior.

**Reason:** Users requested the missing Dash control parity, but switching the default to opt-in would silently change current DSC results for datasets with recorded sample mass. Preserving the current effective default while making the behavior explicit is the smallest safe P0 fix.

**Consequence / future:** DSC processing and saved-result traces should record whether mass normalization was enabled so later UX/reporting work can surface the basis clearly. A future product decision may still change the default, but that would be a deliberate behavior change rather than an incidental side-effect of adding the control.

---

## 2026-04-22 — P0-4 completed: FTIR/Raman similarity metric is template-first and backend-honored end-to-end

**Decision:**

1. FTIR and Raman Dash pages expose a similarity metric selector with exactly **`cosine`** and **`pearson`** options; no additional spectral matching metrics are introduced in this slice.
2. Metric defaults are **template-first**, with **`cosine`** as the fallback when a template does not specify one. Raman template defaults may intentionally differ by workflow (for example, polymorph-oriented Raman templates may default to `pearson`).
3. The selected metric is part of the persisted processing state and must flow through **processing drafts, hydration, dirty tracking, preset save/load, undo/redo/reset, and `/analysis/run` processing overrides**.
4. Backend spectral matching must honor the selected metric in **both** local ranking (`core/batch_runner.py::_rank_spectral_matches`) and cloud spectral search (`backend/library_cloud_service.py::search_spectral` + `backend/models.py::SpectralLibrarySearchRequest`). UI exposure without backend propagation is not considered complete.

**Reason:** Streamlit already exposed cosine/pearson selection for spectral matching, while Dash FTIR/Raman lacked that control and previously relied on backend behavior that effectively hardcoded the metric path. End-to-end parity required both UI persistence and backend enforcement.

**Consequence / future:** Future spectral-matching work must treat `metric` as a first-class processing parameter for FTIR/Raman. If new metrics are added later, they must be reflected consistently in templates, preset payloads, batch/cloud ranking paths, and targeted regression tests.

---

## 2026-04-22 — Repo-wide Dash vs Streamlit parity audit: remediation backlog agreed

**Decision:**

1. All 6 analysis modalities (DSC, TGA, DTA, FTIR, Raman, XRD) are at **near parity** vs Streamlit. No modality is regressed or first-slice only.
2. Prioritized remediation backlog agreed in execution order:
   - **P0-2 + P0-3 (done):** i18n key namespace leakage — DSC/DTA borrowing TGA processing history keys; TGA borrowing DSC quality/metadata/summary keys. 28 new keys, 32 reference swaps, 6 regression tests.
   - **P1-1 (done):** CSS class namespace cleanup — 5 modalities use `dsc-result-*` CSS classes; only DTA uses own-prefixed classes. Prerequisite for per-modality styling.
   - **P0-1 (done):** Baseline method gap — DSC/DTA now expose the full core-supported baseline set; DTA callback wiring and DSC/DTA baseline i18n were completed.
   - **P0-4 (done):** Similarity metric selector — FTIR/Raman now expose cosine/pearson metric selection with template-first defaults and backend-honored local/cloud matching.
   - **P0-5:** DSC mass normalization — missing "Normalize by mass" control present in Streamlit.
   - **P1-2:** Figure capture toolbar — only XRD has snapshot/report toolbar; port to other modalities.
   - **P1-3 + P1-4:** Shared boilerplate extraction — duplicated coercion helpers, preset cards, quality cards, metadata panels across 6 pages.
   - **P2 items:** Polish, naming, and remaining consistency.

**Reason:** Systematic modality-by-modality audit across 18 dimensions (page shell, processing controls, presets, undo/redo, run gating, results, quality, figure, literature, i18n, CSS) revealed no blocking gaps but several high-visibility consistency issues, especially for TR locale users seeing wrong-modality labels.

**Consequence / future:** P0-2+P0-3, P1-1, and P0-1 are landed; remaining items follow the agreed order. CSS cleanup (P1-1) unblocks per-modality styling work, and the baseline parity fix establishes the full thermal baseline-method surface as the Dash default.

---

## 2026-04-21 — Raman Dash page promoted to full product-grade analysis shell

**Decision:**

1. Raman Dash page is now structured to match the mature modality pages (FTIR/DSC/TGA/DTA): explicit **Setup / Processing / Run** tabs on the left, and standardized results surface ordering on the right (summary → metrics → quality → figure → top-match → peak cards → table → processing → raw metadata → literature).
2. Raman processing state follows the shared draft lifecycle pattern: normalized draft store, control hydration, undo/redo/reset history, preset load/save/save-as/delete, and `processing_overrides` forwarding through `/analysis/run`.
3. Raman page strings are sourced from **`dash.analysis.raman.*`** namespace so modality-specific UX text does not depend on TGA/FTIR copy.

**Reason:** Raman had a first-slice page shape and incomplete parity versus the product-grade analysis pages, creating UX inconsistency and feature gaps during the Streamlit → Dash migration.

**Consequence / future:** Raman now shares the same operational model as other mature pages, so future enhancements (new controls, richer cards, capture/export polish) can follow the established cross-modality callback/store patterns.

---

## 2026-04-21 — Raman-specific literature + scientific reasoning paths (no generic fallback in normal Raman flow)

**Decision:**

1. Add deterministic Raman query payload builder in [`core/raman_literature_query_builder.py`](core/raman_literature_query_builder.py), including modality-first Raman terminology, evidence snapshot, display terms, and “query-too-narrow” guard.
2. Route `analysis_type == "RAMAN"` to dedicated `_compare_raman_result_to_literature` in [`core/literature_compare.py`](core/literature_compare.py), mirroring FTIR-level traceability (`executed_queries`, provider state, surfaced comparison ranking) with Raman-specific relevance/posture/evidence-scope logic.
3. Add `_build_raman_reasoning` and dispatcher branch in [`core/scientific_reasoning.py`](core/scientific_reasoning.py) so Raman records avoid generic “not specialized” reasoning output.
4. In shared spectral batch flow ([`core/batch_runner.py`](core/batch_runner.py)), warning strings are modality-aware (`FTIR` vs `RAMAN`) and Raman method-context signal flags are persisted to prevent cross-modality labeling leakage.

**Reason:** Raman previously inherited generic literature/reasoning behavior and could surface FTIR wording in shared spectral warnings, reducing interpretability and modality trust.

**Consequence / future:** Raman literature/reasoning semantics now evolve independently of generic fallback paths; FTIR and Raman can share architecture while preserving modality-specific language and scoring behavior.

---

## 2026-04-21 — Combined Dash server: library cloud URL bootstrap + POSIX Windows-path env sanitation

**Decision:**

1. **`python -m dash_app.server`** runs **`sanitize_library_path_env_vars`** then **`apply_combined_dash_server_library_env`** (see [`core/library_combined_bootstrap.py`](core/library_combined_bootstrap.py)) **before** importing [`backend/app.py`](backend/app.py), so the first `ManagedLibraryCloudService` sees corrected `MATERIALSCOPE_LIBRARY_CLOUD_URL`. Opt out with **`MATERIALSCOPE_LIBRARY_DISABLE_COMBINED_BOOTSTRAP=1`**.
2. **Defaults:** unset cloud URL → `http://<bind>:<port>` (loopback when listening on `0.0.0.0`); loopback URL stuck on **port 8000** while the combined server listens on another port → rewrite to the listen port (Docker `.env` vs Dash dev mismatch).
3. **POSIX safety:** hosted/mirror env values that look like pasted Windows paths are **removed at startup** (sanitize) and **ignored in resolution** ([`core/path_env.py`](core/path_env.py), [`core/hosted_library.py`](core/hosted_library.py), [`core/reference_library.py`](core/reference_library.py)) with logging.
4. **Diagnostics:** [`core/spectral_library_diagnostics.py`](core/spectral_library_diagnostics.py) is the shared snapshot builder; [`tools/ftir_library_diagnostics.py`](tools/ftir_library_diagnostics.py) wraps it for CLI/NDJSON.

**Reason:** WSL/Linux dev failed FTIR matching with `library_unavailable` due to cloud client pointing at **8000** while the combined app served on **8050**, plus malformed **Windows-derived hosted root** paths; fixes belonged in startup and path resolution, not the FTIR UI.

**Consequence / future:** Standalone **`python -m backend.main`** on 8000 is unchanged. Split-process / production layouts should set **`MATERIALSCOPE_LIBRARY_CLOUD_URL`** explicitly to the real API origin.

---

## 2026-04-21 — Dash: validation warning counts from list payloads; FTIR page i18n under `dash.analysis.ftir.*`

**Decision:**

1. **Counts:** UI warning and issue **counts** (saved-run banner from `interpret_run_result`, FTIR validation/quality panel badges and numeric lines) use **`len(validation["warnings"])`** and **`len(validation["issues"])`** via **`finalized_validation_warning_issue_counts`** in [`dash_app/components/analysis_page.py`](dash_app/components/analysis_page.py). Stale **`warning_count`** / **`issue_count`** integers must not override the lists when they disagree.
2. **FTIR Dash copy:** All user-visible FTIR processing/preset/quality/raw-metadata/baseline chrome on [`dash_app/pages/ftir.py`](dash_app/pages/ftir.py) reads **`dash.analysis.ftir.*`** keys in [`utils/i18n.py`](utils/i18n.py), not **`dash.analysis.tga.*`** or DSC thermal baseline strings, so the page stays modality-correct without scattering one-off string edits.

**Reason:** Users saw TGA/thermal wording and °C on FTIR; run banner and quality panel could disagree on warning totals; library-off states read like chemistry failures.

**Consequence / future:** Other modality pages can reuse **`finalized_validation_warning_issue_counts`** in their quality builders for the same guarantee. Raman (or others) still borrowing TGA preset keys should get their own **`dash.analysis.raman.*`** (or shared neutral) namespace when touched.

---

## 2026-04-21 — FTIR literature compare: dedicated query builder + thermal-style compare path

**Decision:**

1. **Routing:** `analysis_type == "FTIR"` uses **`_compare_ftir_result_to_literature`**, not the generic per-claim path — same structural guarantees as DSC/DTA/TGA (single search pool, ranked surfacing, merged surfaced comparisons, rich `LiteratureContext` including **`executed_queries`**).
2. **Queries:** **`core/ftir_literature_query_builder.build_ftir_literature_query`** builds modality-first text from real summary/row evidence (including **`matched_peak_pairs`** → wavenumber display terms when present). When **`match_status == library_unavailable`**, queries target **FTIR methodology / library practice**, not a fabricated top identification.
3. **Relevance:** FTIR uses explicit **modality** phrases plus **distractor penalties** (off-topic domains) so irrelevant hits are less likely to dominate; **no IR modality mention in source text → non_validating** posture.
4. **Scientific reasoning:** **`_build_ftir_reasoning`** supplies FTIR-native claims (library unavailable vs matched vs no_match); the generic “not specialized for this analysis type yet” branch is **not** used for FTIR.
5. **Context normalization:** **`LiteratureContext.executed_queries`** is passed through **`normalize_literature_context`** and normalized in **`to_dict`** so technical-details UI stays truthful for all modalities using executed query lists.

**Reason:** FTIR previously fell through generic literature + generic reasoning, producing placeholder copy and weak retention semantics. End-to-end FTIR-specific inputs restore product trust without a new FTIR literature card layout.

**Consequence / future:** **RAMAN** still uses the generic literature path today; a small follow-up can reuse the FTIR builder/compare with modality strings swapped. Raw-quality exploration was removed from the FTIR page; undo/redo helpers remain in `ftir_explore.py`.

---

## 2026-04-21 — FTIR follow-up: adaptive prominence, normalized plot gating, `library_unavailable` match status

**Decision:**

1. **Spectral peak prominence** (`_detect_spectral_peaks`): combine the configured absolute prominence with a **data-driven floor** from `ptp(signal)` so the same nominal threshold does not over-filter when the working Y scale is smaller (e.g. normalized basis). If the first `find_peaks` pass returns nothing, a **second pass** uses a lowered prominence derived from `min(effective×fraction, ptp×fraction, cfg×fraction)` so visible features can still be retained without unbounded sensitivity on the first pass.
2. **Normalized on the main figure:** The batch runner records **`normalized_axis_ratio_vs_corrected`** and **`plot_normalized_primary_axis`** (true only if normalization is informative *and* normalized peak-to-peak is at least ~**2.2%** of corrected peak-to-peak). The Dash FTIR figure **omits** the normalized trace when the flag is explicitly false; peak marker Y positions use the **corrected** (display) trace at the nearest wavenumber index, not the detection-basis intensity alone.
3. **Match status vocabulary:** Add **`library_unavailable`** when **`ranked_matches` is empty** and library **source/mode** indicates the reference corpus was **not configured or unavailable** — distinct from **`no_match`**, which means candidates were ranked but none met the acceptance threshold. Serialization and validation emit **`spectral_library_unavailable`** caution semantics for the former.
4. **Default overlays:** When **corrected** exists, **hide smoothed** on the FTIR figure (intermediate only if corrected is absent); show **baseline** only alongside corrected; keep imported + query as the primary interpretive traces.
5. **Literature technical headings:** Collapsible section titles use **`literature_t`** with a human fallback so missing per-modality keys cannot render as raw key strings; FTIR gains explicit **`dash.analysis.ftir.literature.technical_*`** strings.

**Reason:** Users saw under-detection, a flat normalized line dominating scale/marker logic, crowded overlays, “No match” read as chemistry when the library was missing, and leaked i18n keys in FTIR literature technical blocks. Backend remains source of truth; UI reflects diagnostics and summary semantics.

**Consequence / future:** Raman shares `_execute_spectral_batch` and inherits prominence + normalized diagnostics; only the FTIR Dash figure policy was specialized. Reports or exports that branch on `match_status` should treat **`library_unavailable`** as a **provenance/tooling** outcome, not a spectral similarity failure.

---

## 2026-04-21 — FTIR science chain: signal-role-aware pipeline with baseline validation and normalization guards

**Decision:** The spectral batch runner (`core/batch_runner.py::_execute_spectral_batch`) now:
1. Infers FTIR signal role from `dataset.units["signal"]` / `dataset.metadata["inferred_signal_unit"]` (*absorbance* / *transmittance* / *unknown*).
2. Inverts transmittance signals (`max – signal`) before smoothing/baseline so troughs become peaks; records `ftir_inverted_for_transmittance` in processing context.
3. Uses real `pybaselines` ASLS/rubberband with optional region weights instead of the previous fake linear-through-endpoints implementation.
4. Validates the baseline fit: rejects it if variance increases >50% or corrected range collapses to <2% of original range; falls back to zero baseline and suppresses the trace.
5. Guards normalization: skips it when signal has zero range, zero norm, or the result would be near-flat; falls back to showing the corrected spectrum.
6. Replaces the hand-rolled peak scanner with `scipy.signal.find_peaks`; auto-fallback to 20% prominence when strict threshold yields nothing.
7. Surfaces all failure modes as FTIR-specific warnings in validation + a `diagnostics` dict in analysis state (exposed via `AnalysisStateCurvesResponse`).
8. The Dash page reads diagnostics and suppresses invalid traces instead of plotting them; legend labels append “(inverted)” when applicable.

**Reason:** The previous pipeline produced visibly absurd baselines, misleading flat normalized traces, and zero peaks with no explanation. Signal-role ignorance caused transmittance troughs to be discarded. Fixing the backend chain and making the frontend reflect backend truth is more robust than client-side rescue logic.

**Consequence / future:** Raman shares the same `_execute_spectral_batch` path and benefits automatically. Future peak controls (width, SNR) should extend the new `find_peaks`-based detector. Cloud search endpoint (`backend/library_cloud_service.py`) was updated to call the new signatures.

---

## 2026-04-20 — FTIR analysis page: backend-truth peaks via `analysis_state_curves`; deferred overlay preview

**Decision:** Extend `AnalysisStateCurvesResponse` and `analysis_state_curves` endpoint to return `normalized` signal and `peaks` for FTIR, with safe `_peak_to_dict` conversion so DSC/DTA `ThermalPeak` dataclass objects do not cause Pydantic serialization errors. The Dash page renders backend-truth peaks directly from this endpoint instead of re-detecting client-side. The top-match overlay preview graph (candidate signal plotted over sample signal) is explicitly deferred because the backend does not expose a candidate/reference signal endpoint today; the Dash page ships a strong text hero summary instead.

**Reason:** Keeps peak display consistent with backend analysis; avoids client/server drift. Overlay preview requires a new backend API for candidate spectral signals — out of scope for this slice.

**Consequence / future:** When a candidate signal endpoint exists, the overlay preview can be added with minimal frontend-only changes. Other spectral modalities (Raman, XRD) should follow the same backend-truth curves contract.

---

## 2026-04-20 — FTIR preset payload: workflow template + full processing draft

**Decision:** FTIR preset save/load stores both `workflow_template_id` and the complete FTIR processing draft (baseline, normalization, smoothing, peak detection, similarity matching) inside the `processing` envelope, matching the existing preset API contract. On load, the page hydrates template, controls, draft, snapshot baseline, and dirty state. On run, `processing_overrides` is built only from the UI draft store.

**Reason:** Presets must be meaningful for FTIR; storing only the workflow template would lose all processing context. Reuses the TGA pattern (unit mode in `method_context`) but applies it to the full FTIR draft.

**Consequence / future:** Any new analysis page with a processing draft should follow the same preset envelope pattern: template id + full draft in `processing`.

---

## 2026-04-20 — FTIR controls scope: only expose backend-supported parameters

**Decision:** The FTIR Dash page exposes only `prominence`, `distance`, `max_peaks` for peak detection and `top_n`, `minimum_score` for similarity matching — the exact parameters the backend `processing_schema` and batch runner support today. Width, threshold, and other advanced peak controls are omitted until the backend detector is extended.

**Reason:** Prevents user confusion from controls that would be ignored or would fail validation on the backend. Keeps the UI honest about backend capability.

**Consequence / future:** When the backend adds new processing parameters (e.g., peak width, SNR threshold), the Dash page can expand its controls and preset draft model incrementally.

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
