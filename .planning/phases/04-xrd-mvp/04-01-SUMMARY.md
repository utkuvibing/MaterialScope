---
phase: 04-xrd-mvp
plan: 01
subsystem: api
tags: [xrd, import, cif, fastapi, streamlit]
requires:
  - phase: 01-foundation-contracts-and-execution-path
    provides: registry-driven stable modality execution and state-key conventions
provides:
  - XRD stable modality registration with deterministic xrd_state_* keys
  - Normalized XRD import contract for .xy/.dat/.cif with bounded CIF scope
  - Backend/API dispatch coverage proving XRD onboarding path and unknown-type guardrails
affects: [04-02-PLAN.md, xrd-processing, backend-dispatch, import-workflow]
tech-stack:
  added: []
  patterns:
    - registry-driven stable modality onboarding
    - bounded parser policy with explicit unsupported error messaging
key-files:
  created: []
  modified:
    - core/modalities/adapters.py
    - core/modalities/registry.py
    - core/modalities/state_keys.py
    - core/data_io.py
    - ui/components/column_mapper.py
    - backend/app.py
    - tests/test_modality_registry.py
    - tests/test_data_io.py
    - tests/test_backend_modality_dispatch.py
    - tests/test_backend_api.py
key-decisions:
  - "XRD import normalizes to two-theta axis + intensity with explicit xrd_* provenance fields, regardless of source format."
  - "CIF MVP support is restricted to single-block powder-pattern loops with _pd_meas_2theta_scan/intensity tags; structural-only and d-spacing-only variants fail explicitly."
  - "Backend dataset import treats XRD as warning-summary flow (similar to spectral onboarding) to preserve stable API contracts while XRD execution kernels are phased in later plans."
patterns-established:
  - "Stable modality contract-first onboarding: adapter + registry + state key + dispatch tests in the first task."
  - "Import parser boundaries are enforced with deterministic, user-readable unsupported messages."
requirements-completed: [XRD-01]
duration: 13min
completed: 2026-03-12
---

# Phase 4 Plan 01: XRD Contract and Import Foundation Summary

**XRD is now a stable registered modality with deterministic state keys and normalized `.xy/.dat/.cif` import contracts carrying axis and wavelength provenance.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-03-12T10:09:46Z
- **Completed:** 2026-03-12T10:23:18Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments
- Added XRD to the stable modality registry/adapter/state-key contract surface without regressing unknown analysis-type errors.
- Implemented XRD import normalization for measured-pattern `.xy/.dat` files and bounded `.cif` parsing with explicit unsupported-scope failures.
- Wired backend import/dispatch and API coverage so XRD flows through stable onboarding paths and exposes import metadata contract fields.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add XRD stable modality contracts and deterministic state keys** - `070da04` (feat)
2. **Task 2: Implement normalized `.xy/.dat/.cif` XRD import with bounded CIF scope** - `bff23b8` (feat)
3. **Task 3: Wire backend import/dispatch surfaces for XRD onboarding** - `e0d77a8` (feat)

## Files Created/Modified
- `core/modalities/adapters.py` - Added `XRDAdapter` stable contract binding.
- `core/modalities/registry.py` - Registered XRD as stable with default template `xrd.general`.
- `core/modalities/state_keys.py` - Added deterministic `xrd_state_<dataset_key>` mapping.
- `core/data_io.py` - Added XRD measured/CIF parsing, normalization, and provenance metadata fields.
- `ui/components/column_mapper.py` - Added XRD data-type option and axis/signal labels for mapping UI.
- `backend/app.py` - Routed XRD imports through warning-summary validation flow.
- `tests/test_modality_registry.py` - Updated stable registry and state-key expectations for XRD.
- `tests/test_data_io.py` - Added XRD `.xy/.dat/.cif` normalization and CIF boundary/error tests.
- `tests/test_backend_modality_dispatch.py` - Added XRD dispatch-path coverage and unknown-type guard checks.
- `tests/test_backend_api.py` - Added backend API contract assertions for XRD import metadata.

## Decisions Made
- XRD onboarding is contract-first: registry/adapter/state-key and backend dispatch acceptance precede full XRD processing kernels.
- CIF support is intentionally bounded in MVP: only powder-pattern loops are accepted, with explicit unsupported messaging for structural-only or multi-block inputs.
- XRD metadata contract always carries `xrd_axis_role`, `xrd_axis_unit`, and `xrd_wavelength_angstrom` fields (where available) to preserve downstream traceability.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] StringIO source names were not propagated for extension-based parser routing**
- **Found during:** Task 2
- **Issue:** `.cif`/`.xy` tests using in-memory `StringIO` could not trigger extension-gated XRD parser paths because source names were dropped.
- **Fix:** Updated `_to_readable_buffer` to preserve `source.name` for `io.StringIO` sources.
- **Files modified:** `core/data_io.py`
- **Verification:** `pytest -q tests/test_data_io.py -k "xrd or cif or xy or dat"`
- **Committed in:** `bff23b8`

**2. [Rule 1 - Bug] Guess-column ambiguity over/under-claiming on mixed unit headers**
- **Found during:** Task 2 verification
- **Issue:** Existing ambiguity threshold logic produced false unknowns for clear DSC/TGA headers and over-claimed misleading mixed headers after parser integration checks.
- **Fix:** Tuned ambiguity threshold to preserve existing expected behavior across DSC/TGA ambiguity edge cases while keeping misleading-header caution semantics.
- **Files modified:** `core/data_io.py`
- **Verification:** `pytest -q tests/test_data_io.py -k "xrd or cif or xy or dat"`
- **Committed in:** `bff23b8`

---

**Total deviations:** 2 auto-fixed (2 bug fixes)
**Impact on plan:** Both fixes were required to keep import/heuristic behavior correct and to satisfy the plan’s automated verification gate without scope creep.

## Issues Encountered
- `apply_patch` was unavailable in this sandbox session; file updates were applied via direct PowerShell edits with immediate compile/test validation.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- XRD-01 foundation is complete and validated; Phase 04-02 can build preprocessing and peak-detection kernels on the normalized import contract.
- Backend dispatch paths already recognize XRD as stable, so subsequent processing/serialization work can layer without changing import/API envelope contracts.

---
*Phase: 04-xrd-mvp*
*Completed: 2026-03-12*

## Self-Check: PASSED
- FOUND: .planning/phases/04-xrd-mvp/04-01-SUMMARY.md
- FOUND: commit 070da04
- FOUND: commit bff23b8
- FOUND: commit e0d77a8

