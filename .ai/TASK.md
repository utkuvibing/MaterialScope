# Task — MaterialScope

**Purpose:** One active migration slice — scope, goal, and acceptance only.

## Status: active — Dash parity audit remediation backlog (2026-04-22)

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
| P1-2 | Figure capture inconsistency: only XRD has snapshot/report toolbar; others have auto-capture only | DSC, DTA, TGA, FTIR, Raman | L | Port XRD toolbar pattern to each page |
| P1-3 | Shared boilerplate extraction: coercion helpers, preset card, quality card, metadata panel, history card all duplicated across 6 pages | All | L | New shared module(s) |
| P1-4 | Duplicated coercion helpers (`_coerce_int_positive`, `_coerce_float_positive`, `_coerce_float_non_negative`) in DSC, DTA, FTIR, Raman | All | S | Extract to shared module |
| P1-7 | Regression tests for i18n leakage (done as part of P0-2+P0-3) | All | S | Done |

#### P2 — cleanup, naming, polish

| # | Issue | Modalities | Effort |
|---|---|---|---|
| P2-3 | Spectral modalities lack raw quality panel (intentional but inconsistent) | FTIR, Raman | M |
| P2-4 | TGA missing literature compare callback test | TGA | S |
| P2-5 | DSC missing preset dirty-flag test | DSC | S |
| P2-6 | Streamlit spectral_page has 12+ plot setting toggles; Dash spectral pages have fewer | FTIR, Raman | M |

### Recommended execution order

1. ~~P1-1 — CSS class namespace cleanup (done)~~
2. ~~P0-4 — Similarity metric selector (done)~~
3. ~~P0-5 — DSC mass normalization (done)~~
4. P1-2 — Figure capture toolbar standardization (large, high UX value, use XRD as template)
5. P1-3 + P1-4 — Shared boilerplate extraction (large, maintenance burden reduction)
6. P2 items — polish and consistency

---

### Audit findings summary (2026-04-22)

| Modality | Streamlit lines | Dash lines | Parity | Key gaps |
|---|---|---|---|---|
| DSC | 818 | 2674 | Near | No remaining P0 gap; figure toolbar standardization still pending |
| TGA | 886 | 2360 | Near | Was borrowing DSC i18n keys (fixed); CSS class leakage |
| DTA | 818 | 2973 | Near | Cleanest CSS scoping |
| FTIR | 12 (delegates) | 2625 | Near | Figure capture toolbar inconsistency; fewer spectral plot toggles than Streamlit |
| Raman | 12 (delegates) | 2630 | Near | Same as FTIR; literature compare is Dash improvement |
| XRD | 2432 | 2697 | Near | Most complete figure toolbar; template for others |

**Cross-cutting issues:** Boilerplate duplication (~40% of each page), figure capture inconsistency.
