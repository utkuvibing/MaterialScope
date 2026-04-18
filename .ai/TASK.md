# Task — MaterialScope

**Purpose:** One active migration slice — scope, goal, and acceptance only.

## Status (2026-04-18): DTA Dash Graph Polish & Refactor — in progress

**Goal:** Refactor Dash DTA plotting into explicit `result` and `debug` figure modes, defaulting all saved/exported/report figures to polished `result` mode while preserving rich analysis detail in `debug` mode.

**In scope**

- `dash_app/pages/dta.py`: add `view_mode` contract to `_build_dta_go_figure` and `_build_figure`; implement result-mode trace hierarchy; implement debug-mode overlays; add `dta-figure-view-mode` UI selector; force result mode in capture path; reduce annotation clutter in result mode; add hover detail.
- `tests/test_dta_dash_page.py`: add mode matrix tests, annotation anti-clutter tests, capture result-mode enforcement tests.
- `utils/i18n.py`: add TR/EN keys for figure view mode labels.

**Out of scope**

- `ui/components/plot_builder.py`, `ui/dta_page.py` (Streamlit surface).
- DTA analysis algorithms, result schema, literature compare semantics, report artifact keys.
- Generic cross-modality plotting framework.
- Broad visual experimentation outside hierarchy/readability goals.

**Acceptance**

- `python -m pytest tests/test_dta_dash_page.py -q` passes.
- `python -m pytest tests/test_dash_workflow_regression.py -q` passes.
- `python -m pytest tests/test_report_generator.py -k dta -q` passes.
- DTA result figure tests prove: result/debug mode behavior differs as defined; capture uses result mode.