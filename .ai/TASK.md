# Active task — MaterialScope

**Purpose:** One active migration slice — scope, goal, and acceptance only.

## Status (2026-04-17): Thermal literature search semantics (backend) — implemented

**Goal:** Introduce explicit thermal search semantics for DSC/DTA/TGA with `known_material` vs `behavior_first` mode branching, conservative subject trust inference, and explainable evidence-scope metadata for UI/report layers.

**In scope**

- `[core/thermal_literature_query_builder.py](core/thermal_literature_query_builder.py)`: add `_infer_subject_trust` (`trusted|low_trust|absent`) + `_infer_search_mode` (`known_material|behavior_first`); branch DSC/DTA/TGA query construction by mode; include `search_mode` + `subject_trust` in payload and `evidence_snapshot`.
- `[core/literature_compare.py](core/literature_compare.py)`: propagate `search_mode`/`subject_trust` into `literature_context`; classify per-comparison thermal evidence scope (`material_specific|behavior_level|generic_context`) and emit `evidence_scope_summary` at context level.
- `[core/literature_models.py](core/literature_models.py)`: extend normalized models with `search_mode`, `subject_trust`, `evidence_scope_summary`, and per-row `evidence_scope`.
- `[tests/test_literature_compare.py](tests/test_literature_compare.py)`: focused coverage for mode/trust inference, behavior-first query anchoring, known-material anchoring, and metadata exposure.

**Out of scope**

- Provider/env registry refactors; broad score/threshold retuning; non-thermal modalities (XRD/generic); Dash layout changes.

**Acceptance**

- DSC/DTA/TGA query payload exposes `search_mode` and `subject_trust`.
- `behavior_first` mode does not use low-trust labels as primary query anchors.
- `known_material` mode preserves trusted subject/material anchoring.
- `literature_context` includes `search_mode`, `subject_trust`, `evidence_scope_summary`.
- Thermal `literature_comparisons` include per-row `evidence_scope`.
- Thermal-focused tests pass without broad scoring rewrites.

**Verification (recorded)**

- `python -m pytest tests/test_literature_compare.py -q` → **63 passed**
- `python -m pytest tests/test_backend_details.py tests/test_literature_compare_panel.py -q` → **47 passed** (3 warnings)
