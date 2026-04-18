# Decisions — MaterialScope

**This file is the only durable log for design, architecture, and workflow commitments.** Session notes belong in **`.ai/SESSION.md`**; slice completion in **`.ai/TASK.md`**; defects in **`.ai/BUGS.md`**. Process details: **`.cursor/rules/00-workflow.mdc`**.

---

## 2026-04-18 — DTA Dash figure view_mode contract

**Decision:** Introduce an explicit `view_mode` parameter (`"result" | "debug"`) on `_build_dta_go_figure` and `_build_figure` in `dash_app/pages/dta.py`, defaulting to `"result"`. The mode controls trace hierarchy, annotation density, and hover detail. Capture/report paths always force `"result"` regardless of interactive state.

**Reason:** The current DTA figure builder has no mode concept — all overlays render identically whether the user is inspecting analysis or exporting a publication figure. This makes result charts cluttered and debug charts no richer than necessary. An explicit mode contract separates concerns cleanly without touching the analysis pipeline.

**Consequence / future:** Other modalities (DSC, TGA) can adopt the same `view_mode` pattern when they migrate to Dash. The `dta-figure-view-mode` selector pattern should be reused.

---

## 2026-04-18 — Result mode as default for all saved/exported figures

**Decision:** All figure capture (`_capture_dta_figure_png`, `capture_dta_figure`) and report registration paths use `view_mode="result"` unconditionally. The interactive `dta-figure-view-mode` selector only affects the live `dcc.Graph` in the result panel.

**Reason:** Report Center exports and PNG captures must be publication-quality by default. Debug overlays should never leak into saved artifacts unless explicitly requested in a future slice.

**Consequence / future:** If a future slice adds a "debug export" button, it can pass `view_mode="debug"` to the builder, but the default capture path remains result-only.

---

## 2026-04-18 — Annotation strategy: result mode minimal, debug mode rich

**Decision:** In `result` mode, onset/endset vertical guide lines and their text annotations are suppressed; only primary-event peak temperature labels appear on-chart. All onset/endset/area/height detail moves to `hovertemplate` on peak markers and remains in the event detail table/cards. In `debug` mode, the current annotation richness (guide lines with labels, all peak text) is preserved.

**Reason:** Overlapping onset/endset labels are the primary source of chart clutter in dense DTA results. Hover and table already carry this information. Result mode should be clean enough for publication export.

**Consequence / future:** The `_ANNOTATION_MIN_SEP` and `_PRIMARY_EVENT_LIMIT` constants remain relevant for debug mode. Result mode uses a simpler threshold (primary events only, no onset/endset vlines).