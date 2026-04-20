# Session — MaterialScope

**Purpose:** **Current working state**, **carryover**, and **next step** only.

## Carryover

- **Project:** MaterialScope
- **Branch:** `web-dash-plotly-migration`
- **Last slice:** Dash literature compare — same card + callbacks on all analysis pages (TGA parity).

## What was done this session

1. **Shared UI** [`dash_app/components/literature_compare_ui.py`](dash_app/components/literature_compare_ui.py): `build_literature_compare_card`, `coerce_literature_max_claims`, compact preview limits; imports consolidated.
2. **Pages wired** (literature chrome + toggle + compare → `literature_compare` + compact `render_literature_output` + status alert): **TGA, DSC, DTA, XRD, FTIR, RAMAN** under `dash_app/pages/*.py`.
3. **i18n** [`utils/i18n.py`](utils/i18n.py): short hints per modality `dash.analysis.{xrd,ftir,raman}.literature.{ready,empty,missing_result}` (en/tr); rendered output reuses `dash.analysis.tga.literature` tree where applicable.
4. **Backend** [`backend/app.py`](backend/app.py): default `provider_ids` for empty compare requests now includes **RAMAN** (same live provider default as FTIR/XRD/thermal).
5. **Tests**: XRD/Raman layout ids + ordering; `test_result_literature_compare_endpoint_defaults_live_provider_for_raman_results` in [`tests/test_backend_details.py`](tests/test_backend_details.py).

## What was verified

- `rtk pytest tests/test_xrd_dash_page.py tests/test_raman_dash_page.py tests/test_backend_details.py::test_result_literature_compare_endpoint_defaults_live_provider_for_raman_results tests/test_backend_details.py::test_result_literature_compare_endpoint_defaults_live_provider_for_ftir_results -q` — **28 passed**.
- `rtk pytest tests/test_dash_figure_capture_wiring.py -q` — **10 passed**.

## Next step

- None required for this slice; optional: add `tests/test_ftir_dash_page.py` layout assertions if we want parity with XRD/Raman tests.

**Process defaults:** **`00-workflow.mdc`**.
