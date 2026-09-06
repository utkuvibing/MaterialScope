# MaterialScope Roadmap — living execution plan

**Created:** 2026-08-26 · **Baseline:** `ee0325b` · **Current:** PR-8 delivered as [PR #35](https://github.com/utkuvibing/MaterialScope/pull/35) (2026-09-06), closing its Phase 1 work package. Phase 1 planned as PR-8…PR-14, one PR per work package; PR-9 plan below. **Branch note:** the Dash runtime stability fix `1e1a705` is unmerged and precedes PR-9, which touches `dash_app/pages/home.py`; PR-9 branches from the updated main, not `72e734e`
**Current evidence:** [Streamlit parity inventory](streamlit-parity-inventory.md) plus current source for runtime claims. The original scout is a local, untracked historical snapshot and is not a published prerequisite.
**Working agreements:** every work package = one reviewable PR · no feature lands on red main · RAG merges only by separate approval · Streamlit removal is a migration (separately approved), not cleanup.

---

<a id="phase-0--stabilize-truth-in-progress"></a>

## Phase 0 — Stabilize truth *(complete with PR #34)*

Objective: green main protected by CI, honest packaging, dead weight gone, legacy stack inventoried. No science changes.

| WP | Scope | Status | Notes |
|---|---|---|---|
| **PR-1** | Restore green main: preserve RAG changeset on `codex/rag-lab-docs` @ `1aee3b8` (pushed); diagnose + root-cause-fix all 8 pre-existing failures; one production robustness fix in `coverage()`; hermetic job-state sandboxing; fixture-contract realignment | ✅ Done — PR #22 (head `0d2a7f3`, suite 1171 passed / 10 skipped) | Review-hardened: tolerance narrowed to `FileNotFoundError` with two regression proofs; unused bindings removed. Stash `codex-temp-before-cleanup-push` intentionally untouched (two latent test fixes: license date-bomb, XRD `.xy` import path) |
| **PR-2** | Real CI: pytest matrix (3.11/3.12) + ruff on push/PR; branch protection requiring checks where permissions allow; verify a deliberate probe fails AND blocks merge, then revert probe; defang the dep-less always-green pytest inside `cursor-agent.yml` | ✅ Done — PR #23 (main @ `a5197cf`); ruleset `main-requires-authoritative-ci` active with zero bypass actors; 1175 passed / 6 skipped per Python on clean runners | Ratchet contract: existing violations frozen per-file in `ruff.toml`; files without frozen ignores are fully enforced; ignored rules must be burned down when those files are cleaned. Probe verified red→blocking→reverted. Also fixed a real py311 SyntaxError (`ui/dta_page.py`) and machine-local masking in the build-corpus autodetection test |
| **PR-3** | Packaging truth: `pyproject.toml` (`requires-python>=3.11`), `[dev]` extra, move `pytest` out of runtime deps; kaleido pin **chosen from evidence** (inspect Plotly/Kaleido/Docker export path, run PNG export tests in fresh env before selecting major); drop `rdata`; document `httpx<0.29` pin; update `test_deployment_contract.py`; README Python-version truth; `.gitignore += output/` | ✅ Done — PR #24 (merged 2026-08-30; main @ `50b16c4`) | `pyproject.toml` consumes `requirements.txt` dynamically (single runtime source; Docker path unchanged) and mirrors `utils/license_manager.APP_VERSION` (dist reports `2.0`); `[dev]` = pytest+ruff; `rdata` dropped after zero-importer verification (`pyreadr` kept — `tools/library_ingest/providers.py`); kaleido evidence-based: `plotly>=6.1.1,<8` + `kaleido>=1,<2` validated in fresh 3.11/3.12 venvs, CI, and Docker chromium; `httpx<0.29` documented as intentional tested ceiling (no historical rationale; 0.29 nonexistent upstream); deprecated `engine="kaleido"` removed from both call sites; `test_deployment_contract.py` rewritten to packaging truth (`tomllib`-based); READMEs → Python 3.11+ (TR parity); CI installs `pip install -e ".[dev]"` + `pip check`, job names unchanged; bonus `.gitattributes` LF pin for `*.sh` fixed a Windows CRLF Docker blocker. Fresh envs: 1171 passed / 15 skipped per Python; Docker `/health` 200 + genuine Kaleido PNG in-container. `.gitignore += output/` deferred to PR-4 (tracked `output/playwright` png deletion already lives there) |
| **PR-4** | Dead code & hygiene: delete `core/online_providers/` (687 LOC, zero importers), tracked `output/playwright/*.png`; stale-branch deletion list for owner sign-off | ✅ Done — PR #25 (merged 2026-08-30; main @ `166a083`; 12 files +3/−879; suite 1171 passed / 15 skipped; `ruff` clean) | Branch deletion owner-gated follow-up, none run in PR |
| **PR-5** | Security trio, three independent commits: (a) archive extraction hardening — shared `core/archive_safety.py` (OS-independent traversal/link/device rejection, 3.11-safe manual validation) + failure-atomic `_install_package` (stage→backup→promote→restore); install `ValueError` still aborts `sync()`; (b) HMAC secret resolution centralized with byte-identical precedence, documented as demo-forgeable hygiene only (asymmetric signing deferred); (c) unauthenticated non-loopback bind warning, open-by-default preserved, explicit `--token`/`api_token` synchronized to bundled Dash client | ✅ Done — PR #31 (merged 2026-09-04; main @ `17ee101`; suite 1221 passed / 10 skipped; `ruff` clean; CI matrix 3.11/3.12 green) | Rotation note: secret change ⇒ re-issue keys; no enforcement added |
| **PR-6** | Streamlit parity/deprecation inventory (**read-only doc**, no deletions): Streamlit-only functionality ↔ Dash equivalents, packaging dependencies, tests, docs; removal itself becomes an independently approved later WP | ✅ Done — [PR #33](https://github.com/utkuvibing/MaterialScope/pull/33) (merged 2026-09-05; main @ `42e9641`) | Added `docs/streamlit-parity-inventory.md`; no runtime/dependency/packaging changes. PR reports 86 targeted tests passed and Ruff clean. Removal remains separately approved |
| **PR-7** | README/docs truth pass: local-first Dash single-process story; correct stale launch guidance; refresh early-tester-guide pointers; document retained ThermoAnalyzer compatibility names | ✅ Done — [PR #34](https://github.com/utkuvibing/MaterialScope/pull/34) (2026-09-06) | EN/TR READMEs, tester walkthrough, Windows help/build caveats, and Electron/backend-only distinctions updated. Source/link/whitespace checks; no runtime changes or tests |

### PR-7 — implementation plan (2026-09-06)

**Execution record:** implemented against main `42e9641`; the plan below is retained as the work-package record. Documentation now covers the combined launch, explicit archive downloads, network features, optional API auth and HMAC limitations, legacy page gaps, and retained compatibility names. Windows help now correctly keeps DTA outside the preview-only list. Installer builds remain unverified and missing guide/library inputs remain packaging follow-up work. The scout stays untracked; the current-evidence link above points to the merged inventory.

**Outcome:** a new user can choose the current Dash launch path, reach the tester guide, and understand the legacy desktop paths and limitations without inferring that Streamlit has already been retired.

**Evidence and starting point:** GitHub PR #33 is merged at `42e9641`. The plan used `docs/streamlit-parity-inventory.md`, especially sections 1, 3, 8, 10, and 12. The planning checkout was at `17ee101`; implementation fast-forwarded it to `42e9641` while preserving local planning/site files. The original scout is a historical snapshot: its WSGI architecture description predates PR #28; current Dash uses the shared FastAPI app natively.

Both READMEs already use `python -m dash_app.server` and Python 3.11+. There are no dual-run instructions in those quickstarts to delete. PR-7 should clarify the existing path and correct only stale guidance actually found. The Windows packaging README still says Python 3.10+ and describes itself as the primary Windows distribution; the tester guide lacks a setup pointer.

#### Deliverables and edit scope

| Files | Planned change | Source of truth |
|---|---|---|
| `README.md`, `README.tr.md` | Keep installation/launch instructions aligned. Explain local-first operation: one process and port serve Dash and FastAPI at `127.0.0.1:8050`, with no second backend command needed for Dash. Add links to the tester guide and PR-6 inventory; distinguish the retained Streamlit installer and experimental Electron shell. State that library/network features may make external requests and in-memory workspaces require explicit project export before restart; avoid blanket offline/privacy or autosave guarantees | `dash_app/server.py`, `dash_app/api_client.py`, `backend/store.py`, `backend/workspace.py`, `core/library_combined_bootstrap.py`, PR-6 inventory |
| `README.md`, `README.tr.md` | Add concise, matching operational notes: server auth is opt-in via `--token`; non-loopback startup warning does not enforce auth; `/health` remains unauthenticated; `MATERIALSCOPE_API_TOKEN` alone does not enable server auth. Explain that the public HMAC demo secret is forgeable, external `MATERIALSCOPE_LICENSE_SECRET` is needed for commercial deployments, and rotation requires re-issuing licenses; asymmetric licensing remains future work | `dash_app/server.py`, `backend/app.py`, `utils/license_manager.py`; PR #31 documentation handoff |
| `docs/early-tester-guide.md` | Add a relative link to README setup and identify the Dash testing surface. Make the existing ten-minute flow concrete using an existing sample, analysis, comparison, and export. Retain the feedback-form destination. State the relevant beta limits and link to the inventory instead of claiming full Streamlit parity | Current Dash pages, `sample_data/`, PR-6 inventory |
| `packaging/windows/README.md`, `packaging/windows/RELEASE_PREP_LOCAL.md`, `packaging/windows/end_user_docs/README.txt`, `packaging/windows/end_user_docs/HELP.html` | Correct stale product/setup claims where present: identify the retained Streamlit installer (preferred port 8501), align the Python prerequisite with 3.11+, and distinguish it from the Dash quickstart. Explain known missing guide/build inputs from PR-6 without claiming a verified installer build or repairing manifests | `pyproject.toml`, `packaging/windows/launcher.py`, existing spec/build scripts, PR-6 sections 8 and 10 |
| `desktop/electron/README.md`, `desktop/backend_bundle/README.md` | Review for launch ambiguity; edit only if needed. Preserve truthful experimental/backend-only instructions, including legitimate `backend.main` usage. Electron is not a packaged Dash UI | Electron startup code and backend bundle entrypoint; PR-6 section 3 |
| `docs/roadmap.md` | Record PR-7 completion and final compatibility-name decisions once implemented and verified. Resolve the existing `scout-report.md` pointer against the tracked documentation set; the scout is currently local/untracked, so do not silently publish it or count it as a tracked deliverable | Actual tracked tree at implementation time |

#### Boundaries and decisions

- Retain Streamlit and its dependency: PR-6 found no Dash page counterpart for library, license, kinetics, or deconvolution, and shared translations still import Streamlit. Describe retirement as a planned, separately approved migration; do not announce a removal date or full parity.
- Use MaterialScope in current documentation prose. Accept existing `ThermoAnalyzer` filenames, environment aliases, installer identifiers, and any runtime response strings as compatibility details for this PR. Keep literal commands and paths accurate; runtime/installer renaming belongs to Phase 4.
- Review PR-6 section 10 references with an explicit disposition: historical source/test comments may remain as provenance; embedded Dash/Electron UI wording remains with later UI/migration work. Do not expand this docs pass into callback, renderer, or test edits.
- Preserve the PR-6 inventory and scout as dated evidence. Do not rewrite their historical observations to describe the new documentation state.
- No runtime changes, dependency changes, packaging-manifest repairs, generated PDFs, UI changes, deployment changes, science fixes, or Streamlit removal. Existing untracked `docs/index.html`, `docs/scout-report.md`, and `website/` are outside this PR.

#### Implementation order and acceptance

1. Start from current main and inspect only the cited sources and PR-6 documentation rows. Confirm tracked link targets, launch commands, retained names, and actual sample workflow before editing.
2. Update the English README and tester flow, mirror the README changes in Turkish, then reconcile the affected Windows/desktop prose. Remove obsolete dual-run guidance only where it incorrectly describes Dash; retain valid backend-only and legacy commands.
3. Verify that a reader can install and launch Dash using one command, follow the tester-guide links, and identify which capabilities/distribution paths are legacy or experimental. EN/TR claims and commands must agree. No text may imply complete parity, durable autosave, mandatory auth, or completed Streamlit retirement.
4. Check relative links against tracked files; preserve the feedback URL; inspect remaining `ThermoAnalyzer`, `streamlit`, `backend.main`, `8000`, `8050`, `8501`, and missing professor-guide references in touched documentation. Each retained occurrence must match its actual context; zero matches is not the goal.
5. Inspect the final diff, run `git diff --check`, and verify `git status --short` / `git diff --name-only` show only intended documentation edits. No runtime suite, browser/E2E run, installer build, or new tests are required for prose-only changes. Any discovered runtime defect becomes a separate work package.

**Completion gate:** deliver the documentation diff with source/link validation and any remaining installer limitations recorded; mark PR-7 done only after implementation, not on the strength of this plan.

### Parallel track — monetization (no code)
Deep revenue conversation grounded in scout facts: local-first privacy as wedge; existing signed-license + `commercial_mode_enabled()` gate; BYO-key RAG demo value; open-core split options (cloud sync / hosted compute / pro analysis modules); who realistically pays (industry QC labs, grant-funded universities). Output: chosen revenue thesis + which feature goes behind the commercial gate first.

**Explicitly out of scope for Phase 0:** all P0/P1 scientific fixes, dependency upgrades beyond pins, UI changes, any deletions of `app.py`/`ui/`.

---

<a id="phase-1--core-workflow-correctness"></a>

## Phase 1 — Core-workflow correctness

Objective: make the core thermal workflows scientifically trustworthy — one sign convention, honest units and labels, guarded imports, a safe store. No UI redesign, no Phase 2 scientific depth, no Streamlit changes.

| WP | Scope | Status | Notes |
|---|---|---|---|
| **PR-8** | Sign-convention canon: one enum applied at ingest; labels derived post-inversion; resolves internal contradiction (`peak_analysis.py`) | ✅ Done — [PR #35](https://github.com/utkuvibing/MaterialScope/pull/35) (2026-09-06; main @ `72e734e`; 1269 passed / 10 skipped) | Acceptance: both-convention golden test end-to-end ✅ (+ unknown-polarity gate). Evidence: four contradictory conventions coexist — `peak_analysis.find_thermal_peaks` hardcodes up=exotherm; `integrate_peak` docstring claims positive=endotherm; `ui/dsc_page.py` offers "up (endotherm)"; `processing_schema.py` declares display-only `dsc.endotherm_up` vs `dta.exotherm_up`. Canonical decision: exo-up |
| **PR-9** | Dimensional honesty: ΔCp either β-corrected or relabeled; peak area β-aware J/g path or honest relabeling | 🔨 Planned — [plan](pr-9-plan.md) (2026-09-06); branches **after** the Dash runtime stability fix `1e1a705` | Acceptance: known-β conversion golden test. Builds on the PR-8 canonical frame for area sign semantics. **Feed from PR-8:** fix the `DSCProcessor.find_peaks` corrected-signal/raw-baseline double-subtraction before the β conversion (see PR-8 execution record) |
| **PR-10** | Temperature-scale gate: K-vs-°C plausibility check at import (`validation.py`); unit propagated into reasoning prose | ⬜ Planned | Acceptance: K fixture blocked; °C fixture labeled correctly throughout reports |
| **PR-11** | DTA characterization: reuse `characterize_peaks`; fix documented-kwarg crash; align docstring | ⬜ Planned | Scheduled after PR-8 so peak labeling does not churn twice |
| **PR-12** | Normalization & confidence guards: detect already-specific heat flow (opt-in re-normalization); fit-quality band defaults "low" without statistics | ⬜ Planned | Already-specific detection must respect the PR-8 canonical frame so normalized-unit fixtures are not double-inverted or double-normalized |
| **PR-13** | Import honesty pack: dropped-row/bad-line counts surfaced in metadata; ±Inf rejected at import; thousands-separator handling; encoding-mojibake warning; Excel sheet picker | ⬜ Planned | Shares the PR-8 import-declaration surface; do not reopen that surface twice |
| **PR-14** | Store hygiene: copy-on-read + per-project locks; disk autosave journal (crash-safe workspace restore) | ⬜ Planned | No science changes; unlocks crash-safe multi-dataset sessions |

Dependencies: Phase 0 CI protecting all of this.

### PR-8 — implementation plan (2026-09-06)

**Merge record (2026-09-06):** merged as [PR #35](https://github.com/utkuvibing/MaterialScope/pull/35); main @ `72e734e`. Suite 1269 passed / 10 skipped, ruff clean. The plan below is retained as the work-package record.

**Execution record:** implemented on branch `pr8/sign-convention-canon` (2026-09-06) against main `dca974d`; the plan below is retained as the work-package record. Implementation: `core/sign_convention.py` (enum, strict `parse_declared`, evidence-only `inspect_header_hints`, `apply_canonicalization` + provenance records, `label_from_direction`); declaration + canonicalization + raw-provenance recording in `read_thermal_data` (hash stays on the pre-canonicalization frame); `/dataset/import` + Dash import wizard declare `sign_convention` (recorded `sign_convention_declared_by`); detector labels derived from the canon; DTA single-signal direction passes (fixed the historical duplicate/contradictory-tag bug — each event detected once); TGA DTG events labeled `'step'`; enforced canonical method-context id replaced the contradictory display-only defaults; result records/dataset summaries carry the `sign_convention` provenance block; project archives restore the resolved frame. Golden gates green end-to-end (endo-up + exo-up melting event → both `endotherm`, matching temps/areas; mirrored DTA → single `exo` event; unknown → labels withheld + warnings). Suite 1269 passed / 10 skipped, ruff clean.

**Merge-blocker fix (pre-merge review):** DTAProcessor's serialized ``direction`` tags were previously hardcoded per pass ('exo' for the positive-direction pass, 'endo' for the negative pass) and could contradict the convention-derived ``peak_type`` when DTAProcessor was used directly with ``sign_convention='endo_up'``. Event-family passes now select a convention-aware search direction (exo events point down in an endo-up frame) and the tag is derived from the SAME canon label as ``peak_type`` via ``core.sign_convention.direction_tag_from_label`` — the two fields are structurally incapable of disagreeing. Canonical-ingest behavior and ``'exo'``/``'endo'`` serialization compatibility unchanged; regression tests cover direct endo-up use (up + down events), event-family gating under the convention, and the tag helper.

**Discovered during implementation (handed to PR-9):** `DSCProcessor.find_peaks` passes the corrected signal together with the RAW baseline array to `characterize_peaks`, so peak areas integrate ∫(corrected − raw_baseline) — the baseline is subtracted twice and the error scales with the baseline level × window width. This is an area-semantics defect, not a sign-convention defect (labels/provenance are unaffected); the both-convention golden uses a zero-baseline fixture so it tests the canon rather than baseline math. PR-9 owns the area fix alongside the β-aware J/g path.

**Pre-implementation clarifications (2026-09-06 review, binding):** (1) `UNKNOWN` polarity is preserved as unresolved — it is never silently handled or described as canonical exo-up; the only permitted unknown-as-exo-up handling is an explicitly recorded backward-compatibility assumption in metadata, and this PR implements none. (2) Explicit convention parsing and header-hint inspection are separate code paths: header tokens may produce warnings and contradiction evidence, and must never choose or flip the convention. (3) Raw/source provenance survives canonicalization: serialized/exported metadata must unambiguously state the originally declared convention and whether the working signal was inverted.

**Outcome:** an endothermic event encoded in either vendor convention produces the same event label and honest derived metrics end to end — ingest → analysis → serialized record — and the codebase carries exactly one documented, enforced sign convention.

**Evidence and starting point (contradiction inventory):**

- `core/peak_analysis.py::find_thermal_peaks` hard-tags upward peaks `'exotherm'` and downward peaks `'endotherm'` (exo-up assumption baked into the shared detector); its docstring repeats "up - exotherms in heat-flow convention".
- `core/peak_analysis.py::integrate_peak` docstring claims positive area means "endotherm in a heat-flow-up convention" — contradicting the same file's detector.
- `ui/dsc_page.py` labels the direction picker "up (endotherm)" / "down (exotherm)" (endo-up assumption), so a user selecting "up (endotherm)" receives peaks tagged `exotherm` in the results table.
- `core/processing_schema.py` method context declares display-only strings `dsc.endotherm_up` (DSC) and `dta.exotherm_up` (DTA) — declared conventions with no enforcement, and they contradict each other.
- `core/baseline.py` documents exotherm-up; `core/dta_processor.py` is physically exo-up (positive ΔT = exothermic).
- `core/dta_processor.py` calls `find_thermal_peaks` without `direction` in both its exo and endo passes (the parameter defaults to `'both'`), so a single event can be found in both passes and tagged `'exo'` then `'endo'`; `core/result_serialization.py` counts exotherms/endotherms from these tags, so summary counts can double-count.
- `core/tga_processor.py` negates DTG so mass-loss events surface as upward peaks, inheriting the nonsensical `'exotherm'` label for mass-loss steps.
- Ingest (`ThermalDataset`, `core/data_io.py`) carries no sign-convention field; modality `y_aliases` already detect `endo`/`exo` header tokens but nothing uses them for convention.
- `sample_data/dta_tnaa_10c_mendeley.csv` is exo-up in practice (the decomposition event is a positive excursion); the DSC samples carry no convention evidence — so the convention must be declared, not inferred from data shape.

#### Deliverables and edit scope

| Files | Planned change | Source of truth |
|---|---|---|
| `core/sign_convention.py` (new) | Single deep module with two strictly separated surfaces. Declaration surface: `SignConvention` enum (`EXO_UP`, `ENDO_UP`, `UNKNOWN`), canonical constant `EXO_UP`, `parse_declared()` accepting only explicitly declared values, `apply_canonicalization()` (returns signal + inversion record), `label_from_direction()` deriving `'endotherm'`/`'exotherm'`/`'unknown'`. Evidence surface: `inspect_header_hints()` returns read-only endo/exo header evidence for warnings and provenance; it can never set, choose, or flip a convention. No I/O, no pipeline imports | Contradiction inventory above |
| `core/data_io.py`, `backend/models.py`, `backend/app.py`, `dash_app/pages/home.py`, `dash_app/api_client.py` | Convention declared at ingest through the import wizard/API: new `ThermalDataset.signal_convention` (resolved working frame); `/dataset/import` accepts `sign_convention` (default `exo_up`, recorded as `sign_convention_declared_by: import_default` when not user-set); canonicalize once at ingest (declared endo-up inputs inverted once); raw/source provenance preserved — metadata records `raw_signal_convention`, `signal_inverted_at_import`, `canonical_signal_convention`, and `source_data_hash` keeps hashing the pre-canonicalization frame; header-token contradictions become warnings only (never a flip). Streamlit legacy import untouched | `/dataset/import` handler; existing `endo`/`exo` y-aliases |
| `core/peak_analysis.py` | `find_thermal_peaks` gains a `sign_convention` parameter (default canonical) and derives `peak_type` from it instead of hardcoding up=exotherm; rewrite `find_thermal_peaks` and `integrate_peak` docstrings to canonical semantics | Contradiction items 1–2 |
| `core/dsc_processor.py` | Forward the canonical frame; record the convention in result metadata/method context | DSC pipeline path |
| `core/dta_processor.py` | Both passes operate on one working signal (`direction='up'` exo pass, `direction='down'` endo pass); remove the inverted+`'both'` re-find; tags derived from canonical labels; `direction` attribute values stay `exo`/`endo` for serialization compatibility | Contradiction items 4–5; documented-kwarg crash stays PR-11 |
| `core/tga_processor.py` | DTG-derived peaks labeled `'step'` (mass-loss events), not `'exotherm'` | Contradiction item 6 |
| `core/processing_schema.py`, `core/result_serialization.py` | Method context: replace the display-only `dsc.endotherm_up`/`dta.exotherm_up` strings with one enforced canonical id; result records surface an unambiguous `sign_convention` provenance block (declared raw convention, canonical frame, whether the working signal was inverted) so exports can never be misread as "unknown polarity handled as exo-up"; summary counts read canon labels and never claim unknown-polarity events | Method-context evidence item |
| `ui/dsc_page.py`, `dash_app` import-preview UI | Direction picker relabeled to canonical truth ("up = exothermic deviation" / "down = endothermic deviation") with help text naming the canon; convention declaration added to the Dash import flow. Streamlit legacy pages untouched | Contradiction item 3; PR-6 inventory |
| `tests/test_sign_convention.py` (new), `tests/test_peak_analysis.py`, `tests/test_data_io.py`, `tests/test_backend_batch.py`, `tests/test_dsc_tga_parity.py` | Unit tests for the enum module; both-convention golden test through the backend API; DTA no-double-tag regression; TGA step-label test; ingest inversion and unknown-fallback tests | Acceptance gate |

#### Boundaries and decisions

- Canonical convention = **exo-up** (positive deviation above baseline = exothermic): matches `core/baseline.py`'s documented contract, DTA's physical ΔT direction, and the existing detector hardcode, so existing synthetic fixtures and result labels remain valid. An endo-up canonical would flip labels, Tg step signs, and serialization counts app-wide for zero correctness gain.
- The convention is **declared, not inferred**, and the surfaces stay separated: `parse_declared()` handles only user/API-declared values; `inspect_header_hints()` reads `endo`/`exo` header tokens and returns evidence used exclusively for warnings and provenance. Hints can never set, choose, or flip the convention — a contradiction between the declared convention and header evidence surfaces as a review warning, nothing more.
- `UNKNOWN` is a first-class unresolved state, never silently mapped onto canonical exo-up: no inversion, no polarity assumption, `peak_type='unknown'`, and exo/endo summary counts do not claim unknown-polarity events. Datasets imported without an explicit declaration default to a *recorded* `exo_up` declaration (`sign_convention_declared_by: import_default`) — that is a recorded default, not an unknown-as-known mapping. Legacy project archives restore with polarity unresolved plus an analysis-time warning prompting re-declaration. If backward compatibility ever requires assuming exo-up for unknown-polarity data, that assumption must be recorded explicitly in metadata; this PR implements no such assumption.
- Labels derived post-inversion with raw provenance preserved: canonicalization at ingest never destroys the source picture — `raw_signal_convention` (what was declared), `signal_inverted_at_import` (whether the working signal is a sign-flip of the imported frame), and `canonical_signal_convention` travel into dataset metadata, result records, and project archives. Every `'endotherm'`/`'exotherm'` label in the codebase traces to `label_from_direction` on the canonical frame; one derivation site, no per-module assumptions.
- In scope: the DTA duplicate/double-tag fix (it *is* the labeling contradiction), `peak_type` derivation, sign-semantics docstrings, the Dash convention-declaration surface. Out of scope: ΔCp/β math (PR-9), K/°C gate (PR-10), DTA `characterize_peaks` reuse and documented-kwarg crash (PR-11), broader import validation (PR-13), store changes (PR-14), Streamlit pages, report-template work beyond label rendering, plot styling.
- No dependency changes; EN/TR UI strings via the existing `tx()` mechanism.

#### Implementation order and acceptance

1. Branch from main; add `core/sign_convention.py` (enum, parser, canonicalizer, label derivation) with unit tests. Pure addition; full suite stays green.
2. Wire ingest: extend `ThermalDataset`, the `/dataset/import` parameter, and the Dash import preview; canonicalization + metadata recording + contradiction warnings; tests for both conventions and the unknown fallback.
3. Derive labels post-inversion: `sign_convention` parameter on `find_thermal_peaks`; `peak_type` from the canon; fix the `integrate_peak`/`find_thermal_peaks` docstrings; run direction unit tests under both conventions.
4. Align processors and serialization: DSC pass-through; DTA single-signal direction passes without duplicate or conflicting tags; TGA `'step'` labels; enforced method-context ids; counts from canon labels.
5. Dash UI truth pass: relabel the DSC direction picker and help text; surface the declared convention in the import preview. Verify EN/TR strings agree.
6. Golden gate: import the same melting event as an endo-up CSV and as an exo-up CSV through the backend API; both must produce peaks labeled `endotherm` with matching temperatures and areas. Mirror a DTA fixture in both conventions: identical labels, no duplicate peaks. TGA steps labeled `'step'`. An `unknown`-declared import of the same event yields peaks without endo/exo attribution (labels withheld, counts unclaimed), proving no silent polarity assumption.
7. Run the full pytest suite and `ruff check`; run `git diff --check`; verify `git status --short` shows only intended files. Any discovered adjacent defect (e.g., area unit handling) becomes its own work package — PR-9/PR-11 feed on findings.

**Completion gate:** deliver the implementation with the both-convention golden test green end-to-end and every inventory item above either fixed or explicitly dispositioned; mark PR-8 done only after implementation and CI, not on the strength of this plan.

## Phase 2 — Scientific depth

- DSC enthalpy: configurable bounds (snap-to-onset/endset), β-aware J/g, ± estimate.
- ISO-style Tg construction option (two-tangent, Cp offsets) alongside existing detector; multi-transition scan.
- TGA residual-mass-at-temperature; DTG %/min toggle; smoothing window in °C not points.
- FTIR/Raman region integration; transmittance→absorbance; nm↔cm⁻¹ conversion; annotated peak-table export.
- XRD: wavelength enforcement *before* matching; implement-or-remove fake baselines; optional Scherrer with explicit caveats.
- Kinetics: Ea confidence intervals; intercept semantics fixed.

Out of scope: Rietveld, Kα2 stripping (documented limitation instead).

## Phase 3 — Reproducibility & reporting

- **Archive v2**: raw bytes + SHA-256 verification on load + `app_version` gate + migration hooks; curve-in-CSV option.
- **Analysis recipes**: ordered parameterized pipeline recorded per result; replay; run-diff view.
- **Report overhaul**: significant-figure policy per unit; UTC+local timestamps; software version on cover.
- **Portable presets**: JSON export/import; travel inside project archives.

## Phase 4 — Productization

- Execute Streamlit retirement per PR-6 inventory (port kinetics/deconvolution to Dash or formally cut).
- One desktop channel decision (Electron vs installer-Dash); build reproduced in CI.
- Page decomposition: extract shared processing panels from 2–3k-line pages; slim i18n monolith.
- Browser E2E smoke (Playwright; chromium already in Docker image) covering import→analysis→export per modality.
- Deployment guide + branding cleanup (ThermoAnalyzer → MaterialScope in health payload/installer names).

---

## Top 10 next moves (post-PR-1 order)

1. ~~Commit working tree properly~~ ✔ (RAG parked on branch)
2. ~~PR-2: real CI~~ ✔ (PR #23)
3. ~~Fix P0-1…P0-5 scientific integrity pack~~ → Phase 1 correctness pack PR-8…PR-12; ~~PR-8 (sign-convention canon)~~ ✔ (PR #35); PR-9 (dimensional honesty) planned next
4. Import honesty pack
5. ~~pyproject + dependency pins (PR-3)~~ ✔ (PR #24)
6. ~~Security trio (PR-5)~~ ✔ (PR #31)
7. Disk autosave + copy-on-read store
8. ~~Delete dead weight (PR-4)~~ ✔ (PR #25); ~~PR-6 Streamlit inventory~~ ✔ (PR #33); ~~PR-7 docs truth pass~~ ✔ (PR #34)
9. DSC enthalpy done right
10. PR-7 legacy-status documentation implemented; approve the actual Streamlit migration separately in Phase 4

## Standing decisions log

| Date | Decision |
|---|---|
| 2026-08-26 | RAG preserved on `codex/rag-lab-docs`; merge requires explicit approval; not auto-committed to main |
| 2026-08-26 | First batch = Phase 0 stabilization only; no science changes yet |
| 2026-08-26 | Streamlit removal pulled out of Phase 0 → inventory first (PR-6), removal later as approved migration |
| 2026-08-26 | Monetization conversation runs in parallel with Phase 0 |
| 2026-08-26 | Kaleido pin must be evidence-based, not assumed `<1.0` |
| 2026-08-26 | PR-5 security items handled independently; container auth must not break documented local-first contract |
| 2026-08-26 | Lint ratchet (PR-2): existing violations frozen per-file in `ruff.toml`; files without frozen ignores are fully enforced; ignored rules must be burned down when those files are cleaned |
| 2026-08-27 | PR-3 packaging architecture: `requirements.txt` stays the single runtime dependency source (pyproject consumes it dynamically; Docker unchanged); dist version mirrors `utils/license_manager.APP_VERSION`; Kaleido v1 line (`plotly>=6.1.1,<8` / `kaleido>=1,<2`) chosen from fresh-env + Docker evidence; `httpx<0.29` kept as a documented tested ceiling; `.gitattributes` pins `*.sh` to LF |
| 2026-09-04 | PR-5 merged as #31 (squash `17ee101`): open-by-default preserved with startup warning instead of enforcement; explicit server token wins over stale client env; install failures keep the working package via backup/restore |
| 2026-09-05 | PR-6 merged as #33 (`42e9641`): read-only Streamlit parity inventory complete; four Streamlit routes lack Dash pages, shared translations still depend on Streamlit, and the Windows installer remains a Streamlit path. No removal authorized |
| 2026-09-06 | PR-7 planned as a documentation-only truth pass. Keep EN/TR aligned, explain the combined native FastAPI/Dash launch and PR-5 operational limits, link tester guidance, and retain runtime/installer compatibility names until Phase 4 |
| 2026-09-06 | PR-7 delivered in [PR #34](https://github.com/utkuvibing/MaterialScope/pull/34), based on `42e9641`: docs only; current evidence links to the merged parity inventory, with the scout left untracked. Compatibility names retained; historical source/test wording and embedded UI text deferred. No installer validation or Streamlit retirement claimed. This delivery closes the seven Phase 0 work packages; deferred follow-ups retain their original scope |
| 2026-09-06 | Phase 1 renumbered one-PR-per-WP: PR-8 sign-convention canon → PR-14 store hygiene; the bare list is replaced by a Phase-0-style table |
| 2026-09-06 | PR-8 planned: canonical sign convention = exo-up (positive deviation above baseline = exothermic), matching `core/baseline.py`, DTA physics, and the existing detector so existing fixtures stay valid; convention declared at ingest (endo-up inputs inverted once, recorded in metadata/provenance); all event labels derived post-inversion from the canon; DTA double-tag fix included; both-convention golden test is the acceptance gate |
| 2026-09-06 | PR-8 implemented on branch `pr8/sign-convention-canon` against `dca974d`: canon module + ingest declaration + canonicalization + provenance, DTA duplicate-tag fix, TGA step labels, enforced canonical method-context id, both-convention golden tests green (1269 passed / 10 skipped, ruff clean). UNKNOWN polarity stays unresolved (labels withheld; no backward-compat assumption implemented). Discovered and deferred to PR-9: DSC area double-subtraction (corrected signal integrated against the raw baseline) |
| 2026-09-06 | PR-8 merged as [PR #35](https://github.com/utkuvibing/MaterialScope/pull/35) — main @ `72e734e`. Work package complete; the implementation plan above is retained as the execution record |
| 2026-09-06 | PR-9 branches **after** the Dash runtime stability fix `1e1a705` (unmerged at planning time). PR-9 edits `dash_app/pages/home.py`, the same file as the stability fix, so `72e734e` is not a valid PR-9 base |
| 2026-09-06 | PR-9 dimensional decisions: (a) conversion to J/(g·K) and J/g is **gated** — β must be present, finite, > 0 *and* traceable to `user`/`parsed` provenance; otherwise the measured quantity is kept under an honest name with a recorded withheld reason. No fallback heating rate, ever. (b) `UnitClass` alone is insufficient: `normalize_by_mass` divides by milligrams, so `mW`→`mW/mg` (1.0) but `W`→`W/mg` (1000.0); conversion consumes an exact canonical unit via a `UNIT_TO_W_PER_G` factor table. (c) `source_signal_unit` / `working_signal_unit` / `normalization_applied` are tracked separately; conversion reads the working unit only and takes no mass argument, so a double division is structurally impossible and a second `normalize()` is a no-op. (d) Legacy payloads: missing basis ⇒ `legacy_unknown`; a legacy `delta_cp` is never displayed as corrected J/(g·K) and a legacy peak `area` is never J/g. (e) Nothing renders unitless — temperature-domain area uses working unit × K, step height uses the dynamic working unit. (f) The fabricated 10 °C/min UI default is removed so an untouched control yields `None`; datasets imported before PR-9 lose their borrowed β and withhold corrected units. (g) DTA receives the double-subtraction fix only, not the J/g conversion |
