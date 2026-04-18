# Session — MaterialScope

**Purpose:** **Current working state**, **carryover**, and **next step** only. Not an inventory of the repo, not a durable decision log—use **`DECISIONS.md`** for the latter; **`TASK.md`** for the active slice.

## Carryover

- **Project:** MaterialScope
- **Direction (context):** incremental Streamlit → Dash + Plotly; DTA parity plan in `c:\Users\Utku ŞAHİN\.cursor\plans\dash_dta_parity_audit_292c7597.plan.md` (audit + phased approach + first safe slice).
- **Branch:** `web-dash-plotly-migration`.
- **WIP / cautions:** Large set of **unrelated modified** tracked files remains locally from prior sessions (see `git status`); **do not mix** with the next slice unless intentional. Also one deleted file staged in the working tree: `.cursor/rules/materialscope-dash-migration.mdc` (deletion not committed — unrelated). Next slice should start from a clean checkout-equivalent mental model and touch only files scoped to that slice's TASK.md.
- **Active slice (2026-04-18 — DTA Dash Graph Polish & Refactor):** Plan at `.sisyphus/plans/dta-dash-graph-polish-refactor.md`. Scope: Dash-only DTA figure mode contract (`result`/`debug`), annotation clutter reduction, trace hierarchy polish, capture/report result-mode lock, i18n, expanded tests. Files: `dash_app/pages/dta.py`, `tests/test_dta_dash_page.py`, `utils/i18n.py`. No Streamlit or cross-modality changes.

## Next step

1. **Execute Task 1:** Add `view_mode` contract to `_build_dta_go_figure` and `_build_figure` in `dash_app/pages/dta.py`.
2. Continue through Tasks 2–8 per plan dependency order.
3. Run Final Verification Wave (F1–F4) after all implementation tasks complete.

**Process defaults:** single thread, **no PM/architect/QA roleplay**, small safe diffs, explicit verification—full detail in **`00-workflow.mdc`**.