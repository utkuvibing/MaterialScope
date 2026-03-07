# Plans

Use this file for large features, cross-cutting refactors, or work that should stay visible across multiple Codex sessions.

---

## Plan Template

### Title
Short name for the work item.

### Objective
What is changing and why?

### Definition Of Done
- Concrete acceptance criteria
- User-visible outcome
- Verification outcome

### Constraints
- What must not change?
- Compatibility constraints
- Scope boundaries

### Impact Analysis
- Affected modules/files
- Data shape or API implications
- User workflow implications

### Risks
- Regression risks
- Migration risks
- Test gaps

### Migration / Rollout Strategy
- Backward compatibility notes
- Order of implementation
- Rollback approach if needed

### Test Strategy
- Unit/integration/manual checks to run
- Commands to execute

### Progress Log
- [ ] Step 1
- [ ] Step 2
- [ ] Step 3

### Notes
Open questions, decisions, follow-ups.

---

## Title
Brownfield Product Hardening - Export, Validation, and Provenance

### Objective
Stabilize the normalized export/report contract, replace the stale dataset validator path with a real validation gate, and add backward-compatible provenance fields so DSC/TGA workflows become more reproducible and defensible without rewriting the repo.

### Definition Of Done
- `pytest -q` passes with the report/export contract aligned to normalized result records.
- Imported datasets are validated before entering the stable analysis workflow.
- Saved result records can optionally carry processing, provenance, validation, and review data.
- DOCX/PDF/CSV exports surface the new record metadata without breaking current DSC/TGA workflows.

### Constraints
- Keep the existing Streamlit shell and normalized result record shape backward-compatible.
- Do not rewrite analysis engines or change core dataset/session flows.
- Preserve `.thermozip` loading for older archives.

### Impact Analysis
- Affected modules: `core/report_generator.py`, `core/result_serialization.py`, `core/data_io.py`, `core/project_io.py`, `ui/home.py`, `ui/dsc_page.py`, `ui/tga_page.py`, `ui/kinetics_page.py`, `ui/components/history_tracker.py`.
- Tests to update/add: `tests/test_report_generator.py`, `tests/test_export_report.py`, `tests/test_project_io.py`, plus new validation coverage.
- User workflow impact: import will show validation feedback earlier; reports will include method/provenance context.

### Risks
- CSV export row counts will change once processing/provenance/validation sections are flattened.
- Extra record fields must remain optional to avoid breaking older saved results.
- UI pages may expose additional warnings for datasets that previously loaded silently.

### Migration / Rollout Strategy
- Implement optional fields first in result serialization.
- Align report/export consumers and tests to the normalized contract.
- Add validation gate in a warnings-first manner, only blocking clearly invalid datasets.
- Keep preview modules marked as preview; only harden shared normalized export paths this round.

### Test Strategy
- Run `pytest -q`.
- Run focused suites for report/export/project IO during development.
- Verify old records without optional fields still pass `split_valid_results`.

### Progress Log
- [x] Add repo worklog entries
- [x] Stabilize normalized report/export contract
- [x] Add validation gate and provenance fields
- [x] Update UI save flows for DSC/TGA/kinetics
- [x] Verify with tests

### Notes
- This is the first hardening tranche from the broader brownfield productization roadmap, not the full 6-month scope.

---

## Title
Report/Test Coverage Recovery and Processing Schema Standardization

### Objective
Recover report/export regression coverage on the normalized result contract, replace the stale legacy validator implementation with a compatibility wrapper, and standardize DSC/TGA processing payloads without changing the normalized record schema or analysis architecture.

### Definition Of Done
- Report/export tests cover DOCX target writes, normalized CSV rows, and XLSX summary visibility without restoring the deprecated CSV contract.
- `utils/validators.py` delegates dataset-level validation to `core.validation` while preserving the legacy tuple API.
- DSC/TGA pages save a versioned, standardized processing payload that remains backward-compatible for exports and project round-trips.
- Reports expose method summary plus clearer validation/provenance tables.

### Constraints
- Keep the normalized result contract unchanged.
- No batch runner, calibration engine, or architecture migration in this tranche.
- Preserve existing project/archive compatibility.

### Impact Analysis
- Runtime files: `core/report_generator.py`, `core/processing_schema.py`, `ui/dsc_page.py`, `ui/tga_page.py`, `utils/validators.py`.
- Tests: `tests/test_report_generator.py`, `tests/test_export_report.py`, `tests/test_validation.py`.
- User workflow impact: saved DSC/TGA results now carry a consistent processing schema; reports show clearer method/validation/provenance context.

### Risks
- Added processing aliases must stay compatible with older saved records and flat exports.
- Localized TGA workflow labels remain user-facing strings; the schema standardizes structure, not label canonicalization.
- Report wording changes can affect brittle string assertions if new downstream tests are added carelessly.

### Migration / Rollout Strategy
- Add the processing helper first.
- Update DSC/TGA pages to write the standardized payload while preserving legacy top-level keys.
- Improve report section rendering and expand tests against the normalized contract.
- Replace the stale validator implementation last with a compatibility wrapper and regression tests.

### Test Strategy
- Run `pytest tests/test_report_generator.py tests/test_export_report.py tests/test_validation.py -q`.
- Run `pytest -q`.
- Run `pytest --collect-only -q` to compare test count.

### Progress Log
- [x] Add `core.processing_schema` helper and wire DSC/TGA pages to it
- [x] Improve DOCX/PDF method, validation, and provenance rendering
- [x] Restore report/export regression coverage on the normalized contract
- [x] Replace stale `utils.validators` dataset path with compatibility wrapper
- [ ] Verify final pytest totals and residual risk

### Notes
- This tranche intentionally does not resurrect the deprecated kinetics-only CSV export contract.

---

## Title
DSC/TGA Validation Hardening and Domain-Specific Report Visibility

### Objective
Strengthen DSC/TGA-specific validation around calibration, sign convention, atmosphere, unit plausibility, and step-analysis context; move workflow templates onto stable internal IDs with preserved labels; and make reports show domain-specific method summaries without changing the normalized export contract.

### Definition Of Done
- DSC/TGA validation checks include method-context details when processing metadata is available.
- Saved `processing` payloads carry stable template IDs plus user-facing labels, while still preserving the legacy `workflow_template` field.
- DOCX/PDF reports render DSC/TGA method summaries with calibration/reference visibility instead of only generic processing tables.
- Existing `.thermozip` archives and legacy label-only processing payloads remain readable.

### Constraints
- No rewrite, no architecture migration, no batch runner, no calibration engine.
- Keep normalized CSV/XLSX/DOCX record contracts unchanged.
- Stay within existing `core/`, `ui/`, and `tests/` structure.

### Impact Analysis
- Runtime files: `core/processing_schema.py`, `core/validation.py`, `ui/dsc_page.py`, `ui/tga_page.py`, `core/report_generator.py`.
- Regression files: `tests/test_validation.py`, `tests/test_report_generator.py`, `tests/test_export_report.py`, `tests/test_project_io.py`.
- User-visible change: reports and validation warnings become more scientifically specific for DSC/TGA.

### Risks
- Template IDs must backfill correctly from legacy label-only payloads.
- New validation warnings must not incorrectly block existing datasets that only lack optional lab metadata.
- Domain-specific report wording increases string-sensitivity in tests.

### Migration / Rollout Strategy
- Extend `core.processing_schema` first so old payloads backfill IDs/labels.
- Feed standardized processing into validation and saved results.
- Render domain-specific report summaries from existing normalized records plus validation metadata.
- Verify project round-trip with richer `processing` payloads.

### Test Strategy
- Run `pytest tests/test_validation.py tests/test_report_generator.py tests/test_export_report.py tests/test_project_io.py -q`.
- Run `pytest -q`.
- Run `pytest --collect-only -q`.

### Progress Log
- [x] Add stable workflow template IDs with label backfill
- [x] Harden DSC/TGA validation checks
- [x] Render domain-specific DSC/TGA method summaries in reports
- [x] Update regression coverage and project round-trip assertions
- [ ] Verify final collect-count delta and residual risk

### Notes
- Compatibility is preserved by keeping `workflow_template` as a label alias while adding `workflow_template_id` and `workflow_template_label`.

---

## Title
Calibration/Reference Hardening and Support Diagnostics

### Objective
Promote calibration/reference status to first-class saved context for DSC/TGA results, add structured logging with stable error IDs, and expose a support snapshot download path without changing the normalized result/export contract or `.thermozip` format.

### Definition Of Done
- DSC/TGA saved `processing` / `provenance` payloads carry explicit calibration/reference state.
- Reports show calibration/reference state clearly for DSC/TGA.
- Import, project load, DSC analysis, TGA analysis, and export/report generation errors emit stable error IDs and land in a structured diagnostics log.
- Users can download a serialized support snapshot from the report center.

### Constraints
- No rewrite, no architecture migration, no batch runner, no archive schema change.
- Keep normalized CSV/XLSX flat export headers unchanged.
- Do not persist diagnostics/support state inside `.thermozip` archives.

### Impact Analysis
- Runtime files: `app.py`, `ui/home.py`, `ui/dsc_page.py`, `ui/tga_page.py`, `ui/export_page.py`, `core/provenance.py`, `core/validation.py`, `core/report_generator.py`, `utils/reference_data.py`, `utils/session_state.py`, plus new `utils/diagnostics.py`.
- Tests: existing report/export/project/validation tests plus new diagnostics coverage.
- User workflow impact: richer DSC/TGA saved context and a new support snapshot download in the report center.

### Risks
- Support logs are local filesystem artifacts; path handling must stay resilient in Streamlit runs.
- Calibration/reference state must remain additive so old results still render as “not recorded” rather than failing validation.
- Error IDs should be shown only on actual failures, not on normal warnings.

### Migration / Rollout Strategy
- Add diagnostics helper and session keys first.
- Thread calibration/reference context into DSC/TGA save flows.
- Improve report rendering and add export-center support snapshot.
- Verify no archive contract changes by keeping project round-trip tests green.

### Test Strategy
- Run `pytest tests/test_diagnostics.py tests/test_report_generator.py tests/test_export_report.py tests/test_project_io.py tests/test_validation.py -q`.
- Run `pytest -q`.
- Run `pytest --collect-only -q`.

### Progress Log
- [x] Add diagnostics helper and support snapshot serializer
- [x] Add calibration/reference context to DSC/TGA save flows
- [x] Render calibration/reference status in reports
- [x] Add structured error IDs to import/project/analysis/export/report failures
- [x] Verify final collect-count delta and residual risk

### Notes
- Support diagnostics remain session-local and downloadable; they are intentionally not embedded into project archives in this tranche.
- `pytest --collect-only -q` increased from 162 to 165 after adding diagnostics coverage and a modality-specific TGA reference regression.

---

## Title
Compare Workspace Batch Template Runner MVP

### Objective
Add a brownfield batchable template runner for DSC/TGA on top of the existing compare workspace so the same stable workflow template can be applied to multiple compatible datasets while reusing the current processing schema, validation, provenance, and export/report flows.

### Definition Of Done
- Users can select multiple compatible DSC or TGA datasets in the compare workspace and apply one workflow template to all selected runs.
- Each successful dataset saves a normal stable result record with the existing processing/provenance/validation structure and stable template ID.
- Per-dataset validation failures and analysis exceptions are surfaced in a batch summary with stable diagnostics instead of aborting the full batch.
- Compare workspace stores a batch summary that round-trips through existing project archives and appears in generated reports.

### Constraints
- No rewrite, no architecture migration, no normalized result/export contract changes, no archive schema changes.
- Stay limited to DSC/TGA and the existing compare workspace.
- Reuse existing validation, provenance, diagnostics, and report/export flows.

### Impact Analysis
- Runtime files: `core/batch_runner.py`, `ui/compare_page.py`, `core/report_generator.py`.
- Regression files: `tests/test_batch_runner.py`, `tests/test_report_generator.py`, `tests/test_project_io.py`.
- User-visible change: compare workspace gains a batch template runner plus a saved batch summary that existing report/export flows can reuse.

### Risks
- Batch defaults must be conservative so they do not imply richer per-template method control than the repo currently has.
- Per-dataset failures must remain isolated so one bad dataset does not prevent other selected runs from saving.
- Stored batch summary data must remain additive inside `comparison_workspace` to preserve old archive compatibility.

### Migration / Rollout Strategy
- Add a small UI-independent batch helper first.
- Wire compare workspace to run the helper per selected dataset and collect stable diagnostics.
- Render saved batch summary in reports using the existing comparison workspace payload.
- Verify project round-trip without touching `core.project_io`.

### Test Strategy
- Run `pytest tests/test_batch_runner.py tests/test_report_generator.py tests/test_project_io.py -q`.
- Run `pytest -q`.
- Run `pytest --collect-only -q`.

### Progress Log
- [x] Add core batch helper for DSC/TGA template execution
- [x] Wire compare workspace batch UI and saved summary
- [x] Render compare-workspace batch summary in reports
- [x] Add regression coverage and verify collect-count delta

### Notes
- Batch summary will be stored inside `comparison_workspace` so old archives stay readable and new archives round-trip without a manifest change.
- `pytest --collect-only -q` increased from 165 to 168 after adding dedicated batch-runner coverage.

---

## Title
Batch Runner Outcome Hardening and Summary Clarity

### Objective
Harden the compare-workspace batch runner UX by standardizing per-dataset outcomes (`saved` / `blocked` / `failed`), improving batch summary visibility and filtering, and making reports/export preview show batch totals plus failure reasons and error IDs more clearly.

### Definition Of Done
- Batch summary rows consistently use `saved`, `blocked`, or `failed`.
- Compare workspace shows clearer batch totals and lets the user filter batch rows by outcome.
- Report/export preview surfaces batch totals, failure reasons, and error IDs from the saved compare workspace state.
- Existing result/provenance/validation/export flows remain unchanged.

### Constraints
- No rewrite, no architecture migration, no `.thermozip` compatibility break, no flat export schema change.
- Keep using the current processing/provenance/validation/result flows.
- Stay within DSC/TGA batch MVP usability only.

### Impact Analysis
- Runtime files: `core/batch_runner.py`, `ui/compare_page.py`, `core/report_generator.py`, `ui/export_page.py`.
- Regression files: `tests/test_batch_runner.py`, `tests/test_report_generator.py`, `tests/test_export_report.py`.
- User-visible change: clearer batch outcome categories, filters, totals, and failure diagnostics in compare/report/export views.

### Risks
- Older saved batch summaries may still contain legacy `error` labels and must normalize safely to `failed`.
- Failure reasons should remain concise enough to display in tables without breaking report readability.
- No new result/export schema should leak out of the compare workspace state.

### Migration / Rollout Strategy
- Normalize batch summary rows in one place first.
- Reuse the normalized rows in compare workspace, report generation, and export preview.
- Keep saved summary data additive inside `comparison_workspace`.

### Test Strategy
- Run `pytest tests/test_batch_runner.py tests/test_report_generator.py tests/test_export_report.py -q`.
- Run `pytest -q`.
- Run `pytest --collect-only -q`.

### Progress Log
- [x] Normalize batch outcome categories and failure metadata
- [x] Improve compare workspace visibility and filtering
- [x] Improve report/export preview batch clarity
- [x] Add regression coverage and verify collect-count delta

### Notes
- Legacy `execution_status="error"` rows will be displayed as `failed` without mutating archive structure.
- `pytest --collect-only -q` increased from 168 to 170 after adding batch outcome normalization and export-preview coverage.
