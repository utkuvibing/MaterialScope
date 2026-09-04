# MaterialScope Roadmap — living execution plan

**Created:** 2026-08-26 · **Baseline:** `ee0325b` · **Current:** post PR-5 (PR #31 merged 2026-09-04 → main @ `17ee101`)
**Ground truth:** [`scout-report.md`](scout-report.md) — read it before changing plan assumptions.
**Working agreements:** every work package = one reviewable PR · no feature lands on red main · RAG merges only by separate approval · Streamlit removal is a migration (separately approved), not cleanup.

---

## Phase 0 — Stabilize truth *(in progress)*

Objective: green main protected by CI, honest packaging, dead weight gone, legacy stack inventoried. No science changes.

| WP | Scope | Status | Notes |
|---|---|---|---|
| **PR-1** | Restore green main: preserve RAG changeset on `codex/rag-lab-docs` @ `1aee3b8` (pushed); diagnose + root-cause-fix all 8 pre-existing failures; one production robustness fix in `coverage()`; hermetic job-state sandboxing; fixture-contract realignment | ✅ Done — PR #22 (head `0d2a7f3`, suite 1171 passed / 10 skipped) | Review-hardened: tolerance narrowed to `FileNotFoundError` with two regression proofs; unused bindings removed. Stash `codex-temp-before-cleanup-push` intentionally untouched (two latent test fixes: license date-bomb, XRD `.xy` import path) |
| **PR-2** | Real CI: pytest matrix (3.11/3.12) + ruff on push/PR; branch protection requiring checks where permissions allow; verify a deliberate probe fails AND blocks merge, then revert probe; defang the dep-less always-green pytest inside `cursor-agent.yml` | ✅ Done — PR #23 (main @ `a5197cf`); ruleset `main-requires-authoritative-ci` active with zero bypass actors; 1175 passed / 6 skipped per Python on clean runners | Ratchet contract: existing violations frozen per-file in `ruff.toml`; files without frozen ignores are fully enforced; ignored rules must be burned down when those files are cleaned. Probe verified red→blocking→reverted. Also fixed a real py311 SyntaxError (`ui/dta_page.py`) and machine-local masking in the build-corpus autodetection test |
| **PR-3** | Packaging truth: `pyproject.toml` (`requires-python>=3.11`), `[dev]` extra, move `pytest` out of runtime deps; kaleido pin **chosen from evidence** (inspect Plotly/Kaleido/Docker export path, run PNG export tests in fresh env before selecting major); drop `rdata`; document `httpx<0.29` pin; update `test_deployment_contract.py`; README Python-version truth; `.gitignore += output/` | ✅ Done — PR #24 (merged 2026-08-30; main @ `50b16c4`) | `pyproject.toml` consumes `requirements.txt` dynamically (single runtime source; Docker path unchanged) and mirrors `utils/license_manager.APP_VERSION` (dist reports `2.0`); `[dev]` = pytest+ruff; `rdata` dropped after zero-importer verification (`pyreadr` kept — `tools/library_ingest/providers.py`); kaleido evidence-based: `plotly>=6.1.1,<8` + `kaleido>=1,<2` validated in fresh 3.11/3.12 venvs, CI, and Docker chromium; `httpx<0.29` documented as intentional tested ceiling (no historical rationale; 0.29 nonexistent upstream); deprecated `engine="kaleido"` removed from both call sites; `test_deployment_contract.py` rewritten to packaging truth (`tomllib`-based); READMEs → Python 3.11+ (TR parity); CI installs `pip install -e ".[dev]"` + `pip check`, job names unchanged; bonus `.gitattributes` LF pin for `*.sh` fixed a Windows CRLF Docker blocker. Fresh envs: 1171 passed / 15 skipped per Python; Docker `/health` 200 + genuine Kaleido PNG in-container. `.gitignore += output/` deferred to PR-4 (tracked `output/playwright` png deletion already lives there) |
| **PR-4** | Dead code & hygiene: delete `core/online_providers/` (687 LOC, zero importers), tracked `output/playwright/*.png`; stale-branch deletion list for owner sign-off | ✅ Done — PR #25 (merged 2026-08-30; main @ `166a083`; 12 files +3/−879; suite 1171 passed / 15 skipped; `ruff` clean) | Branch deletion owner-gated follow-up, none run in PR |
| **PR-5** | Security trio, three independent commits: (a) archive extraction hardening — shared `core/archive_safety.py` (OS-independent traversal/link/device rejection, 3.11-safe manual validation) + failure-atomic `_install_package` (stage→backup→promote→restore); install `ValueError` still aborts `sync()`; (b) HMAC secret resolution centralized with byte-identical precedence, documented as demo-forgeable hygiene only (asymmetric signing deferred); (c) unauthenticated non-loopback bind warning, open-by-default preserved, explicit `--token`/`api_token` synchronized to bundled Dash client | ✅ Done — PR #31 (merged 2026-09-04; main @ `17ee101`; suite 1221 passed / 10 skipped; `ruff` clean; CI matrix 3.11/3.12 green) | Rotation note: secret change ⇒ re-issue keys; no enforcement added |
| **PR-6** | Streamlit parity/deprecation inventory (**read-only doc**, no deletions): Streamlit-only functionality ↔ Dash equivalents, packaging dependencies, tests, docs; removal itself becomes an independently approved later WP | ⬜ | Supersedes original "remove Streamlit in Phase 0" after review |
| **PR-7** | README/docs truth pass: local-first Dash single-process story; remove dual-run instructions; refresh early-tester-guide pointers; rename ThermoAnalyzer remnants or accept them | ⬜ | |

### Parallel track — monetization (no code)
Deep revenue conversation grounded in scout facts: local-first privacy as wedge; existing signed-license + `commercial_mode_enabled()` gate; BYO-key RAG demo value; open-core split options (cloud sync / hosted compute / pro analysis modules); who realistically pays (industry QC labs, grant-funded universities). Output: chosen revenue thesis + which feature goes behind the commercial gate first.

**Explicitly out of scope for Phase 0:** all P0/P1 scientific fixes, dependency upgrades beyond pins, UI changes, any deletions of `app.py`/`ui/`.

---

## Phase 1 — Core-workflow correctness

Work packages (each independently reviewable; golden/property tests required):

1. **Sign-convention canon** — one enum applied at ingest; labels derived post-inversion; resolves internal contradiction (`peak_analysis.py`). Acceptance: both-convention golden test end-to-end.
2. **Dimensional honesty** — ΔCp either β-corrected or relabeled; peak area β-aware J/g path or honest relabeling. Acceptance: known-β conversion golden test.
3. **Temperature-scale gate** — K-vs-°C plausibility check at import (`validation.py`); unit propagated into reasoning prose. Acceptance: K fixture blocked; °C fixture labeled correctly throughout reports.
4. **DTA characterization** — reuse `characterize_peaks`; fix documented-kwarg crash; align docstring.
5. **Normalization & confidence guards** — detect already-specific heat flow (opt-in re-normalization); fit-quality band defaults "low" without statistics.
6. **Import honesty pack** — dropped-row/bad-line counts surfaced in metadata; ±Inf rejected at import; thousands-separator handling; encoding-mojibake warning; Excel sheet picker.
7. **Store hygiene** — copy-on-read + per-project locks; disk autosave journal (crash-safe workspace restore).

Dependencies: Phase 0 CI protecting all of this.

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
3. Fix P0-1…P0-5 scientific integrity pack
4. Import honesty pack
5. ~~pyproject + dependency pins (PR-3)~~ ✔ (PR #24)
6. ~~Security trio (PR-5)~~ ✔ (PR #31)
7. Disk autosave + copy-on-read store
8. ~~Delete dead weight (PR-4)~~ ✔ (PR #25) ← done; next: PR-6 Streamlit inventory (read-only)
9. DSC enthalpy done right
10. Decide Streamlit fate via PR-6 inventory → write deprecation paragraph

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
