# Task — MaterialScope

**Purpose:** One active migration slice — scope, goal, and acceptance only.

## Status: completed — Dash parity remediation + runtime/library stabilization (2026-04-24)

### Completed: P0-1 — Baseline method gap for DSC/DTA

**Done (2026-04-22).** DSC and DTA Dash pages now expose the full baseline method set already supported by core (`asls`, `airpls`, `modpoly`, `imodpoly`, `snip`, `rubberband`, `linear`, `spline`). DTA baseline callbacks now persist method-specific parameters for `airpls`, `modpoly`, `imodpoly`, `snip`, and `spline`; both modalities gained missing TR/EN i18n keys for extended baseline controls and targeted regression coverage.

### Completed: P0-2 + P0-3 — i18n key namespace leakage fix

**Done (2026-04-22).** DSC/DTA processing history labels and TGA quality/metadata/summary labels now use modality-native i18n keys instead of borrowing from TGA/DSC. 28 new keys, 32 reference swaps, 6 regression tests. Zero cross-namespace references remain.

### Completed: P0-4 — Similarity matching metric selector for FTIR/Raman

**Done (2026-04-22).** FTIR and Raman Dash pages now expose `cosine` / `pearson` similarity metric selectors and persist the chosen metric through processing drafts, presets, dirty tracking, undo/redo/reset, and run payload overrides. Metric defaults are template-first with `cosine` fallback, and backend local ranking plus cloud spectral search now honor the selected metric end-to-end. Focused verification passed: `pytest tests/test_ftir_dash_page.py tests/test_raman_dash_page.py tests/test_batch_runner.py -q` → 116 passed.

### Completed: P0-5 — DSC mass normalization control + backend honoring

**Done (2026-04-22).** DSC Dash now exposes a Setup-tab **Normalize by mass** control, persists it as a first-class `normalization` processing section through draft/default state, preset save/load, undo/redo/reset, and run payload overrides, and the backend DSC batch path explicitly honors `signal_pipeline.normalization.enabled` instead of always normalizing. The control defaults to **enabled** for backward compatibility. Focused verification passed: `python -m pytest -p no:cacheprovider tests/test_dsc_dash_page.py tests/test_batch_runner.py -q` → 67 passed.

### Completed: P1-1 — CSS class namespace cleanup

**Done (2026-04-22).** Shared structural result-role classes migrated from modality-specific `dsc-*`/`dta-*` prefixes to generic `ms-*` prefix across all 6 pages + CSS. Per-modality root page hooks (`{modality}-page`) added for future styling flexibility. TGA derivative class leakage fixed (`dsc-derivative-*` → `tga-derivative-*`). DTA-only debug classes preserved. 260/261 tests pass (1 pre-existing unrelated failure).

### Completed: P1-2 — Figure capture toolbar standardization

**Done (2026-04-23).** DSC, DTA, TGA, FTIR, and Raman now expose XRD-style manual **Snapshot** and **Report figure** controls while preserving existing `<modality>-result-figure` display/capture contracts and automatic capture callbacks. XRD was refactored onto shared pure artifact helpers without changing its toolbar IDs or overlay slot. Artifact panels refresh on latest-result changes and successful explicit figure actions only. Focused verification passed: `python -m pytest -p no:cacheprovider tests/test_analysis_page_components.py tests/test_xrd_dash_page.py tests/test_dsc_dash_page.py tests/test_dta_dash_page.py tests/test_tga_dash_page.py tests/test_ftir_dash_page.py tests/test_raman_dash_page.py -q` → 303 passed.

### Completed: P2 — Polish and remaining consistency

**Done (2026-04-24).** FTIR/Raman Dash pages now include setup-tab raw data quality panels and full UI-only spectral plot settings for legend, compact view, grid/crosshair, line/marker/export scale, trace visibility, reversed X axis, and locked X/Y ranges. TGA gained direct literature compare callback regression coverage. DSC gained loaded-preset dirty tracking and tests. Focused verification passed: `python -m pytest -p no:cacheprovider tests/test_analysis_page_components.py tests/test_ftir_dash_page.py tests/test_raman_dash_page.py tests/test_tga_dash_page.py tests/test_dsc_dash_page.py -q` → 189 passed.

### Completed: Post-parity stabilization — runtime/library test isolation

**Done (2026-04-24).** The remaining 6 full-suite failures after Dash parity closeout were traced to test-only runtime/library configuration leakage plus one under-provisioned FTIR fallback case, not to production behavior regressions. `tests/test_backend_api.py`, `tests/test_reference_library.py`, and `tests/test_backend_batch.py` now clear both primary and legacy library/runtime env vars, use tmp-path scoped `MATERIALSCOPE_HOME`, and reset the cloud client singleton where env changes must be re-read. The FTIR batch `no_match` regression now explicitly syncs fallback library state before asserting `spectral_no_match`. Verification passed: targeted 6-test slice green; `python -m pytest -p no:cacheprovider` → 1116 passed, 9 skipped.

---

### Remaining prioritized remediation backlog

Ordered by priority per the repo-wide parity audit:

#### P0 — user-facing parity / regression fixes

| # | Issue | Modalities | Effort | Key files |
|---|---|---|---|---|

**P0 backlog status:** cleared for the current parity remediation set.

#### P1 — maturity and consistency fixes

| # | Issue | Modalities | Effort | Key files |
|---|---|---|---|---|
| P1-3 | Shared boilerplate extraction UI/helper pass: history cards, preset cards, collapsible details, compatible quality/metadata helpers extracted; callback orchestration and incompatible modality-specific panels intentionally deferred | All | Done | `dash_app/components/analysis_boilerplate.py` |
| P1-4 | Exact duplicated coercion helpers extracted; DTA's non-negative helper variant with a `minimum` argument remains local because it is not an exact duplicate | All | Done | `dash_app/components/processing_inputs.py` |
| P1-7 | Regression tests for i18n leakage (done as part of P0-2+P0-3) | All | Done |  |

#### P2 — cleanup, naming, polish

| # | Issue | Modalities | Effort |
|---|---|---|---|
| P2-3 | Spectral modalities lack raw quality panel (intentional but inconsistent) | FTIR, Raman | Done |
| P2-4 | TGA missing literature compare callback test | TGA | Done |
| P2-5 | DSC missing preset dirty-flag test | DSC | Done |
| P2-6 | Streamlit spectral_page has 12+ plot setting toggles; Dash spectral pages have fewer | FTIR, Raman | Done |

### Recommended execution order

1. ~~P1-1 — CSS class namespace cleanup (done)~~
2. ~~P0-4 — Similarity metric selector (done)~~
3. ~~P0-5 — DSC mass normalization (done)~~
4. ~~P1-2 — Figure capture toolbar standardization (done)~~
5. ~~P1-3 + P1-4 — Shared boilerplate extraction UI/helper pass (done 2026-04-24)~~
6. ~~P2 items — polish and consistency (done 2026-04-24)~~

---

### Audit findings summary (2026-04-22)

| Modality | Streamlit lines | Dash lines | Parity | Key gaps |
|---|---|---|---|---|
| DSC | 818 | 2674 | Near | No remaining P0 gap |
| TGA | 886 | 2360 | Near | Was borrowing DSC i18n keys (fixed); CSS class leakage |
| DTA | 818 | 2973 | Near | Cleanest CSS scoping |
| FTIR | 12 (delegates) | 2625 | Near | Fewer spectral plot toggles than Streamlit |
| Raman | 12 (delegates) | 2630 | Near | Literature compare is Dash improvement; fewer spectral plot toggles than Streamlit |
| XRD | 2432 | 2697 | Near | Most complete figure toolbar; template for others |

**Cross-cutting issues:** Boilerplate duplication (~40% of each page).
