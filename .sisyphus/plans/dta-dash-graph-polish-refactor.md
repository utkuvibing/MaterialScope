# DTA Dash Graph Polish & Refactor (Result vs Debug Modes)

## TL;DR
> **Summary**: Refactor Dash DTA plotting into explicit `result` and `debug` figure modes, defaulting all saved/exported/report figures to polished `result` mode while preserving rich analysis detail in `debug` mode.
> **Deliverables**:
> - Mode-aware DTA figure builder in `dash_app/pages/dta.py`
> - Clutter-reduced annotation/hover strategy with fixed label rendering
> - Updated page wiring so result surface is clean by default
> - Regression-safe capture/report behavior and expanded automated tests
> **Effort**: Medium
> **Parallel**: YES - 2 waves
> **Critical Path**: Task 1 → Task 2 → Task 5 → Task 6

## Context
### Original Request
- Deliver a focused Dash Plotly DTA graph polish/refactor that feels product-quality, reduces clutter, separates clean result vs detailed debug behavior, and preserves analysis/saving/literature/report stability.

### Interview Summary
- Scope selected: **Dash only**.
- Export/saved snapshot default: **Result mode**.
- Preserve existing analysis pipeline and contracts; improve presentation and interaction quality.

### Metis Review (gaps addressed)
- Added explicit guardrail to keep changes in Dash DTA surface (no Streamlit/DSC cross-modality abstraction).
- Added explicit requirement that capture/report path always enforces result mode.
- Added mandatory test matrix for mode behavior, annotation policy, and capture/report non-regression.

## Work Objectives
### Core Objective
Make Dash DTA figure output clearly product-quality by default while preserving deeper diagnostic detail via an explicit debug mode.

### Deliverables
- `dash_app/pages/dta.py` updated with mode-aware figure composition.
- Updated DTA result figure wiring and capture path.
- TR/EN i18n keys for any new mode labels/help text.
- Extended tests in `tests/test_dta_dash_page.py` (+ targeted related tests if needed).

### Definition of Done (verifiable conditions with commands)
- `python -m pytest tests/test_dta_dash_page.py -q` passes.
- `python -m pytest tests/test_dash_workflow_regression.py -q` passes.
- `python -m pytest tests/test_report_generator.py -k dta -q` passes.
- DTA result figure tests prove: result/debug mode behavior differs as defined; capture uses result mode.

### Must Have
- Explicit DTA figure mode contract: `result` and `debug`.
- A visible Dash mode control (`dta-figure-view-mode`) near the result figure, defaulting to `result`.
- Result mode defaults to corrected signal as hero when available.
- Minimal on-chart text in result mode; onset/endset detail moved to hover/table/debug.
- Broken placeholder/invalid annotation text removed.
- Capture/report registration path preserved, with result mode lock.

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- No edits to `ui/components/plot_builder.py` or `ui/dta_page.py` in this slice.
- No change to DTA analysis algorithms, result schema, literature compare semantics, or report artifact keys.
- No generic cross-modality plotting framework introduction.
- No broad visual experimentation outside requested hierarchy/readability goals.

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: **tests-after** (pytest).
- QA policy: Every task includes executable scenarios.
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
Wave 1: Figure architecture + UI wiring foundation
- Task 1 (mode contract)
- Task 2 (result mode composition)
- Task 3 (debug mode composition)
- Task 4 (mode routing in figure area/capture)

Wave 2: Stabilization + regression-proofing
- Task 5 (annotation/hover text hardening)
- Task 6 (tests for mode/annotation/capture)
- Task 7 (i18n + legend/UX polish)
- Task 8 (targeted non-regression run + evidence)

### Dependency Matrix (full, all tasks)
- 1 blocks 2,3,4,5,6,7
- 2 blocks 4,6
- 3 blocks 4,6
- 4 blocks 6,8
- 5 blocks 6
- 6 blocks 8
- 7 can run after 1 (independent) but should finish before 8
- 8 final implementation verification before review wave

### Agent Dispatch Summary (wave → task count → categories)
- Wave 1 → 4 tasks → unspecified-high, quick
- Wave 2 → 4 tasks → unspecified-high, quick

## TODOs

- [ ] 1. Define explicit DTA figure mode contract in Dash builder

  **What to do**:
  - Introduce a DTA-local `view_mode` contract (`"result" | "debug"`) in `dash_app/pages/dta.py` figure helpers.
  - Apply mode in `_build_dta_go_figure(...)` and downstream callers.
  - Keep default behavior for result surfaces as `result`.

  **Must NOT do**:
  - Do not change API payload schema from backend.
  - Do not edit Streamlit plot builders.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: Multi-surface behavior contract with regression risk.
  - Skills: `[]` - No special bundled skill required.
  - Omitted: `["reverse-engineer"]` - Not needed for focused refactor.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 2,3,4,5,6,7 | Blocked By: []

  **References**:
  - Pattern: `dash_app/pages/dta.py:1976-2133` - Current DTA figure composition.
  - Pattern: `dash_app/pages/dta.py:2136-2158` - Figure wrapper used by result panel.
  - Test: `tests/test_dta_dash_page.py:337-377` - Primary-trace expectation baseline.

  **Acceptance Criteria**:
  - [ ] Figure builder accepts explicit mode and defaults to `result` when omitted.
  - [ ] Existing result panel still renders without callback contract changes.

  **QA Scenarios**:
  ```
  Scenario: Mode default remains stable
    Tool: Bash
    Steps: python -m pytest tests/test_dta_dash_page.py -k "build_figure" -q
    Expected: Existing build_figure tests pass with new mode contract in place.
    Evidence: .sisyphus/evidence/task-1-mode-contract.txt

  Scenario: Invalid mode safely degrades
    Tool: Bash
    Steps: Add/execute unit test invoking builder with invalid mode token.
    Expected: Builder falls back to result behavior (no exception, deterministic output).
    Evidence: .sisyphus/evidence/task-1-mode-contract-error.txt
  ```

  **Commit**: YES | Message: `refactor(dta-dash): add explicit figure view mode contract` | Files: `dash_app/pages/dta.py`, `tests/test_dta_dash_page.py`

- [ ] 2. Implement polished Result mode hierarchy

  **What to do**:
  - In `result` mode, enforce visual hierarchy:
    - corrected (or best primary) = hero trace,
    - raw = faint background,
    - smoothed = medium support,
    - baseline = subtle dashed support,
    - event markers = restrained accent.
  - Ensure legend and hover prioritize primary readability.

  **Must NOT do**:
  - Do not remove scientifically relevant data from debug mode.
  - Do not hide primary signal from result mode.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: Visual hierarchy + data readability tradeoffs.
  - Skills: `[]`
  - Omitted: `["remotion-best-practices"]` - Unrelated domain.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 4,6 | Blocked By: 1

  **References**:
  - Pattern: `dash_app/pages/dta.py:2005-2063` - Current primary/secondary traces.
  - API/Type: `dash_app/pages/dta.py:1968-1973` - Primary name/color resolution.
  - Test: `tests/test_dta_dash_page.py:371-375` - Corrected hero + raw subordinate expectations.

  **Acceptance Criteria**:
  - [ ] Result mode consistently emphasizes corrected signal when available.
  - [ ] Raw/smoothed/baseline are visually subordinate with deterministic style rules.

  **QA Scenarios**:
  ```
  Scenario: Result mode trace hierarchy
    Tool: Bash
    Steps: python -m pytest tests/test_dta_dash_page.py -k "corrected_as_primary_trace" -q
    Expected: Corrected trace width/opacities and y-range assertions pass.
    Evidence: .sisyphus/evidence/task-2-result-hierarchy.txt

  Scenario: Missing corrected fallback
    Tool: Bash
    Steps: Add/execute test where corrected is absent and smoothed/raw fallback is used.
    Expected: Fallback primary is correct with subordinate support traces and no crash.
    Evidence: .sisyphus/evidence/task-2-result-hierarchy-error.txt
  ```

  **Commit**: YES | Message: `feat(dta-dash): polish result-mode trace hierarchy` | Files: `dash_app/pages/dta.py`, `tests/test_dta_dash_page.py`

- [ ] 3. Implement Debug mode with richer overlays

  **What to do**:
  - Add debug-specific composition policy that keeps richer overlays/guide lines and detailed contextual cues.
  - Preserve restraint: no excessive always-on text labels.
  - Add a UI mode selector in the result figure region with id `dta-figure-view-mode` (`result` default, `debug` optional).

  **Must NOT do**:
  - Do not make debug mode the default for saved/exported result surfaces.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: Additive behavior branch after contract is defined.
  - Skills: `[]`
  - Omitted: `["reverse-engineer"]`

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 4,6 | Blocked By: 1

  **References**:
  - Pattern: `dash_app/pages/dta.py:2065-2121` - Existing event guides + labels.
  - Pattern: `dash_app/pages/dta.py:1525-1658` - Result panel output wiring.
  - Pattern: `dash_app/pages/dta.py:1050-1123` - DTA tab/card layout mount points.

  **Acceptance Criteria**:
  - [ ] Debug mode renders richer overlays than result mode using same data.
  - [ ] Debug mode remains readable and theme-compatible.
  - [ ] `dta-figure-view-mode` renders with `result` default and switching to `debug` updates figure composition.

  **QA Scenarios**:
  ```
  Scenario: Mode behavior divergence
    Tool: Bash
    Steps: Add/execute tests that compare result vs debug trace/shape counts for same payload.
    Expected: Debug has >= detail overlays while result remains minimal.
    Evidence: .sisyphus/evidence/task-3-debug-mode.txt

  Scenario: Dense events in debug mode
    Tool: Bash
    Steps: Use synthetic dense-event test payload (>=6 peaks).
    Expected: No unreadable/broken label artifacts; figure still renders.
    Evidence: .sisyphus/evidence/task-3-debug-mode-error.txt
  ```

  **Commit**: YES | Message: `feat(dta-dash): add debug plotting mode overlays` | Files: `dash_app/pages/dta.py`, `tests/test_dta_dash_page.py`

- [ ] 4. Route result surfaces and capture/export to Result mode

  **What to do**:
  - Ensure `display_result` figure area uses `result` mode.
  - Ensure `_capture_dta_figure_png` / `capture_dta_figure` force `result` mode regardless of interactive debug state.
  - Keep existing figure label contract (`DTA Analysis - {dataset_key}`).
  - Remove duplicated curve fetch by passing already-fetched curves through builder wrappers where practical (no behavior change).

  **Must NOT do**:
  - Do not change register endpoint payload shape.
  - Do not alter result artifact key naming logic.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: report/capture regression risk.
  - Skills: `[]`
  - Omitted: `["git-master"]` - Not a git task.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 6,8 | Blocked By: 1,2,3

  **References**:
  - Pattern: `dash_app/pages/dta.py:1630-1633` - Result figure area.
  - Pattern: `dash_app/pages/dta.py:3226-3310` - Capture + registration flow.
  - Test: `tests/test_dta_dash_page.py:1312-1419` - Capture idempotence/failure behavior.

  **Acceptance Criteria**:
  - [ ] Saved/captured DTA PNG always generated from result mode figure.
  - [ ] Existing figure registration tests continue to pass.
  - [ ] Figure rendering path does not perform redundant double-fetch for the same result render cycle.

  **QA Scenarios**:
  ```
  Scenario: Capture enforces result mode
    Tool: Bash
    Steps: python -m pytest tests/test_dta_dash_page.py -k "capture_dta_figure" -q
    Expected: Capture tests pass; result mode path is explicitly asserted.
    Evidence: .sisyphus/evidence/task-4-capture-result-mode.txt

  Scenario: Kaleido missing still degrades safely
    Tool: Bash
    Steps: Run degrade test case in capture suite.
    Expected: Status=skipped and no register call when PNG generation fails.
    Evidence: .sisyphus/evidence/task-4-capture-result-mode-error.txt
  ```

  **Commit**: YES | Message: `fix(dta-dash): force result mode for capture and report figure` | Files: `dash_app/pages/dta.py`, `tests/test_dta_dash_page.py`

- [ ] 5. Harden annotation and hover text strategy

  **What to do**:
  - Remove/replace any direct annotation patterns that can emit placeholder/broken text.
  - Keep only essential default labels in result mode.
  - Move onset/endset and extra event detail into hover/table/debug path.
  - Ensure no overlapping annotation spam in dense regions.

  **Must NOT do**:
  - Do not suppress event details from table/cards.
  - Do not output unlabeled “new text” / placeholder artifacts.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: focused rendering-policy update.
  - Skills: `[]`
  - Omitted: `["frontend-ui-ux"]` - not required for this bounded technical pass.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 6 | Blocked By: 1

  **References**:
  - Pattern: `dash_app/pages/dta.py:2068-2089` - Guide annotation gating.
  - Pattern: `dash_app/pages/dta.py:2098-2120` - Peak text suppression logic.
  - Pattern: `dash_app/pages/dta.py:2161-2183` - Full event detail table.

  **Acceptance Criteria**:
  - [ ] Result mode contains minimal readable labels only.
  - [ ] Onset/endset details remain available via hover/table/debug.
  - [ ] No broken placeholder annotation text appears.

  **QA Scenarios**:
  ```
  Scenario: Dense-event annotation restraint
    Tool: Bash
    Steps: Run new dense-event test validating annotation/text count threshold.
    Expected: Text labels are capped and no placeholder strings are present.
    Evidence: .sisyphus/evidence/task-5-annotation-strategy.txt

  Scenario: Hover retains critical details
    Tool: Bash
    Steps: Validate hovertemplate/hover data content in tests for onset/endset visibility.
    Expected: Essential thermal event details exist in hover without chart text clutter.
    Evidence: .sisyphus/evidence/task-5-annotation-strategy-error.txt
  ```

  **Commit**: YES | Message: `fix(dta-dash): reduce annotation clutter and stabilize event text` | Files: `dash_app/pages/dta.py`, `tests/test_dta_dash_page.py`

- [ ] 6. Expand automated tests for mode, hierarchy, and non-regression

  **What to do**:
  - Extend `tests/test_dta_dash_page.py` with:
    - result vs debug figure-mode matrix tests,
    - annotation/label anti-clutter tests,
    - capture path result-mode enforcement tests.
  - Keep current tests intact; add targeted new ones only.

  **Must NOT do**:
  - Do not rewrite unrelated test modules.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: safety net quality gates.
  - Skills: `[]`
  - Omitted: `["playwright"]` - not needed for unit/integration pytest layer.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 8 | Blocked By: 2,3,4,5

  **References**:
  - Test: `tests/test_dta_dash_page.py:337-406` - existing figure behavior checks.
  - Test: `tests/test_dta_dash_page.py:1312-1419` - capture behavior baseline.
  - Test: `tests/test_dta_dash_page.py:423-537` - server integration baseline.

  **Acceptance Criteria**:
  - [ ] New tests cover both modes and dense-event behavior.
  - [ ] Existing DTA Dash test expectations remain green.

  **QA Scenarios**:
  ```
  Scenario: DTA Dash suite passes
    Tool: Bash
    Steps: python -m pytest tests/test_dta_dash_page.py -q
    Expected: 0 failed.
    Evidence: .sisyphus/evidence/task-6-dta-tests.txt

  Scenario: Workflow regression safety
    Tool: Bash
    Steps: python -m pytest tests/test_dash_workflow_regression.py -q
    Expected: 0 failed.
    Evidence: .sisyphus/evidence/task-6-dta-tests-error.txt
  ```

  **Commit**: YES | Message: `test(dta-dash): add mode and annotation regression coverage` | Files: `tests/test_dta_dash_page.py`, `tests/test_dash_workflow_regression.py` (if touched)

- [ ] 7. Add i18n and legend/interaction polish wiring for new mode UX

  **What to do**:
  - Add/update TR/EN keys for any new mode labels/help/captions.
  - Ensure legend behavior and hover mode remain clean and non-noisy in both themes.

  **Must NOT do**:
  - Do not add untranslated UI strings.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: localized UI text and minor wiring.
  - Skills: `[]`
  - Omitted: `["writing"]` - pure app i18n wiring, not docs.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 8 | Blocked By: 1

  **References**:
  - Pattern: `utils/i18n.py:874-876, 1032+` - existing DTA/Dash label keys.
  - Pattern: `dash_app/pages/dta.py:2224-2254, 2424-2493` - locale-render callbacks.

  **Acceptance Criteria**:
  - [ ] No new raw English fallback keys rendered in TR UI.
  - [ ] Mode labels are localized and consistent.

  **QA Scenarios**:
  ```
  Scenario: Locale-safe rendering
    Tool: Bash
    Steps: python -m pytest tests/test_dash_chrome_i18n.py -q
    Expected: 0 failed; no missing-key regressions.
    Evidence: .sisyphus/evidence/task-7-i18n.txt

  Scenario: Missing key guard
    Tool: Bash
    Steps: Add/execute targeted DTA key assertion test.
    Expected: New DTA mode keys resolve in both EN and TR.
    Evidence: .sisyphus/evidence/task-7-i18n-error.txt
  ```

  **Commit**: YES | Message: `chore(dta-dash): localize figure mode and polish labels` | Files: `utils/i18n.py`, `dash_app/pages/dta.py`, relevant tests

- [ ] 8. Run targeted non-regression verification + evidence collation

  **What to do**:
  - Run final targeted suite for DTA Dash + report paths.
  - Capture outputs into `.sisyphus/evidence/` paths referenced above.

  **Must NOT do**:
  - Do not broaden into full repository test sweep unless required by failures.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: deterministic command execution and evidence capture.
  - Skills: `[]`
  - Omitted: `["playwright"]` - optional for this slice unless UI E2E is requested.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: F1-F4 | Blocked By: 4,6,7

  **References**:
  - Test: `tests/test_dta_dash_page.py`
  - Test: `tests/test_report_generator.py`
  - Export path context: `dash_app/pages/dta.py:3226-3310`

  **Acceptance Criteria**:
  - [ ] All targeted commands return passing status.
  - [ ] Evidence files exist for each task scenario.

  **QA Scenarios**:
  ```
  Scenario: Report-path DTA regression
    Tool: Bash
    Steps: python -m pytest tests/test_report_generator.py -k dta -q
    Expected: 0 failed.
    Evidence: .sisyphus/evidence/task-8-report-regression.txt

  Scenario: Capture + result integration regression
    Tool: Bash
    Steps: python -m pytest tests/test_dta_dash_page.py -k "capture_dta_figure or import_and_run_via_server" -q
    Expected: 0 failed.
    Evidence: .sisyphus/evidence/task-8-report-regression-error.txt
  ```

  **Commit**: NO | Message: `n/a` | Files: `n/a`

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.
- [ ] F1. Plan Compliance Audit — oracle
- [ ] F2. Code Quality Review — unspecified-high
- [ ] F3. Real Manual QA — unspecified-high (+ playwright if UI)
- [ ] F4. Scope Fidelity Check — deep

## Commit Strategy
- Commit 1 (refactor core): Tasks 1-5
- Commit 2 (tests + i18n + verification artifacts): Tasks 6-8
- Keep commits scoped and avoid unrelated workspace drift.

## Success Criteria
- DTA Dash result chart is visibly cleaner with reduced annotation noise.
- Debug detail remains available without polluting result view.
- Corrected signal is the dominant trace when present.
- Save/capture/report path remains stable and uses result-mode figure.
- Targeted DTA Dash and report tests pass.
