# Session — MaterialScope

**Purpose:** **Current working state**, **carryover**, and **next step** only.

## Carryover

- **Project:** MaterialScope
- **Branch:** `web-dash-plotly-migration`

## What was done this session

- **Repo-wide Dash vs Streamlit parity audit** — compared all 6 analysis modalities (DSC, TGA, DTA, FTIR, Raman, XRD) across 18 dimensions. All modalities reached **near parity**; several Dash-only improvements identified (undo/redo, presets with dirty tracking, figure toolbar, literature for spectral types).
- **P0-1 — Baseline method gap for DSC/DTA (completed 2026-04-22):**
  - Confirmed core already supported the full baseline method set; the unfinished gap was in Dash page wiring, especially DTA baseline callbacks.
  - Fixed DTA baseline parameter-group visibility, `airpls` lambda enablement, apply/sync callbacks, and status text so `airpls`, `modpoly`, `imodpoly`, `snip`, and `spline` persist correctly.
  - Added missing TR + EN baseline i18n keys and help text for extended method parameters in `utils/i18n.py` for both DSC and DTA.
  - Added targeted regression tests covering extended baseline normalization, callback wiring, and baseline chrome output.
- **P0-2 + P0-3 i18n key leakage fix (completed):**
  - Added 28 new i18n keys to `utils/i18n.py` (7 DSC processing history, 7 DTA processing history, 14 TGA quality/metadata/summary), all with TR + EN.
  - Swapped 32 cross-namespace key references: 7 in `dash_app/pages/dsc.py`, 7 in `dash_app/pages/dta.py`, 18 in `dash_app/pages/tga.py`.
  - Added 6 regression tests (3 source-grep guards + 3 monkeypatch callback tests) across `tests/test_dsc_dash_page.py`, `tests/test_dta_dash_page.py`, `tests/test_tga_dash_page.py`.
  - Verified: zero cross-namespace i18n refs remain; 152/153 tests pass (1 pre-existing unrelated failure).
- **P1-1 — CSS class namespace cleanup (completed 2026-04-22):**
  - Renamed shared structural/result-role classes from modality-specific `dsc-*`/`dta-*` prefixes to generic `ms-*` prefix across all 6 pages + CSS: `ms-results-surface`, `ms-result-section`, `ms-result-{context,hero,support,secondary}`, `ms-result-figure-shell`, `ms-result-graph`, `ms-meta-{term,def,value}`.
  - Added per-modality root page hooks (`dsc-page`, `dta-page`, `tga-page`, `ftir-page`, `raman-page`, `xrd-page`) for future per-modality styling flexibility.
  - Fixed TGA derivative class leakage: `dsc-derivative-graph` → `tga-derivative-graph`, `dsc-derivative-helper` → `tga-derivative-helper`.
  - Preserved DTA-only debug classes (`dta-figure-stack`, `dta-result-debug`, `dta-debug-shell`, `dta-debug-graph`) untouched.
  - Merged duplicate DSC CSS section into shared generic section in `style.css`.
  - Updated 6 test files to assert new generic class names.
  - Files touched: `dash_app/assets/style.css`, `dash_app/pages/{dsc,dta,tga,ftir,raman,xrd}.py`, `tests/test_{dsc,dta,tga,ftir,raman,xrd}_dash_page.py`.

## What was verified

- `pytest tests/test_dsc_dash_page.py tests/test_dta_dash_page.py tests/test_tga_dash_page.py tests/test_ftir_dash_page.py tests/test_raman_dash_page.py tests/test_xrd_dash_page.py -q` — 260 passed, 1 pre-existing failure (`test_backend_register_figure_writes_state_and_artifacts` — 409 duplicate figure, unrelated).
- `pytest tests/test_dta_dash_page.py::test_normalize_baseline_values_gates_asls_params tests/test_dta_dash_page.py::test_toggle_dta_baseline_parameter_groups_and_inputs_cover_extended_methods tests/test_dta_dash_page.py::test_apply_and_sync_dta_baseline_controls_cover_extended_methods tests/test_dta_dash_page.py::test_render_dta_baseline_chrome_emits_help_hints_tr_and_en tests/test_dsc_dash_page.py::test_render_dsc_baseline_chrome_emits_extended_parameter_hints -q` — 5 passed.
- Grep confirmed zero `dsc-result-section`, `dsc-result-context`, `dsc-result-hero`, `dsc-result-support`, `dsc-result-secondary`, `dsc-result-figure-shell`, `dsc-result-graph`, `dsc-results-surface`, `dsc-meta-term`, `dsc-meta-def`, `dsc-meta-value` in all touched pages, CSS, and tests.
- Grep confirmed zero `dta-result-section`, `dta-result-context`, `dta-result-hero`, `dta-result-support`, `dta-result-secondary`, `dta-result-figure-shell`, `dta-result-graph`, `dta-results-surface`, `dta-meta-term`, `dta-meta-def`, `dta-meta-value` in all touched pages, CSS, and tests.
- Negative check confirmed DTA-only debug classes (`dta-figure-stack`, `dta-result-debug`, `dta-debug-shell`, `dta-debug-graph`) still present in `dta.py` and `style.css`.

## Next step

- **P0-4** — Similarity matching metric selector for FTIR/Raman.

**Process defaults:** **`00-workflow.mdc`**.
