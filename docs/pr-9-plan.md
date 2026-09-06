# PR-9 — Dimensional honesty: ΔCp and peak area

*Work-package plan (2026-09-06). Phase 1 of [roadmap.md](roadmap.md). Status: **planned, not implemented**.*

**Branch:** `pr9/dimensional-honesty`
**Base:** NOT `72e734e` — see Branching below
**Roadmap row:** Phase 1 → PR-9
**Baseline evidence:** current source; the PR-8 execution record in `roadmap.md` (baseline double-subtraction handoff)

## Deliverables

1. **Roadmap truth update** — PR-8 is merged; the roadmap still says "PR pending".
2. **PR-9 implementation** — gated β-correction with honest fallback, plus the PR-8 handoff (baseline double-subtraction).

---

## Branching — do NOT branch from `72e734e`

`main` is at `72e734e`. The Dash runtime stability fix `1e1a705` ("fix: stabilize Dash runtime and import workflow") is **unmerged** and lives on the current checkout `fix/dash-runtime-stability`. PR-9 edits `dash_app/pages/home.py:357,1313` — the same file the stability fix touches. Branching from `72e734e` guarantees a conflict and would land PR-9 on a main whose Dash import path is broken.

**Order of operations:**

1. Land the stability fix first — merge `fix/dash-runtime-stability` (`1e1a705`) into main, or rebase and fast-forward. Confirm main has moved past `72e734e` and CI is green.
2. `git checkout main && git pull` — main must contain `1e1a705`.
3. Branch `pr9/dimensional-honesty` from **that** main.
4. Record the new base commit in the PR description and in the roadmap row.

The roadmap Part-1 edit is independent and may land first, on its own, from `72e734e` — it touches only `docs/roadmap.md`.

---

## Part 1 — Roadmap: mark PR-8 done

PR-8 merged as **[PR #35](https://github.com/utkuvibing/MaterialScope/pull/35)** at `72e734e`. Branch `origin/pr8/sign-convention-canon` exists.

Edits to `docs/roadmap.md`:

| Location | Change |
|---|---|
| Line 3 (header `**Current:**`) | Phase 0 closed by PR #34; PR-8 delivered as #35; PR-9 planned below; Dash stability fix `1e1a705` precedes PR-9 |
| Line 79 (PR-8 row) | `🔨 Implemented` → `✅ Done — PR #35 (head `72e734e`, 1269 passed / 10 skipped)`. Keep the exo-up canon rationale + the PR-9 feed note |
| Line 80 (PR-9 row) | `⬜ Planned` → `🔨 Planned — implementation below`; note it branches *after* the Dash stability fix |
| Line 91 (PR-8 execution record) | Prefix: merged as #35 at `72e734e`; plan retained as record |
| Standing decisions log | Add 2026-09-06 rows: PR-8 merged as #35; Dash stability fix gates PR-9's branch point; PR-9 decisions (gated conversion, exact-unit factor table, source-vs-working unit split, legacy-payload rules, dynamic unit rendering, field naming, fabricated β default removed, DTA included) |

Reconcile the two conflicting suite counts in the file (1269 at line 91 vs 1264 at line 207) — keep one, sourced from the PR #35 CI run.

---

## Part 2 — PR-9 design

### The defects

**D1 — ΔCp is not ΔCp.** `core/dsc_processor.py:349` computes `delta_cp = mean_after - mean_before`. After `normalize()` (`core/preprocessing.py:195`) that is **W/g**, not J/(g·K). `self._heating_rate` has **zero read sites** (`core/dsc_processor.py:128`). Docstring at `:40` claims `[J/(g * degrees C)]`. Too small by β/60 (×6 at β=10 K/min).

**D2 — peak area is not J/g.** `core/peak_analysis.py:340` returns `∫(signal−baseline)dT` → **W·K/g**. `core/peak_analysis.py:41` calls it "enthalpy for DSC"; three UI sites hardcode `J/g`. `core/result_serialization.py:200` documents `"DeltaH = integral(...) / beta"` — **the code never divides by β**.

**D3 — baseline double-subtraction (PR-8 handoff).** `core/dsc_processor.py:239-244` passes the corrected signal with the raw baseline → `∫(S − 2B)dT`. Corrupts **three** fields: `area` (`:574`), `height` (`:580`), `fwhm` (`:533`), and `fwhm` drives the integration window (`:547-549`). Same defect at `core/batch_runner.py:728-733` and `ui/dta_page.py:645-650`. `ui/dsc_page.py:669` already has the correct pattern — copy it.

**D4 — fabricated β.** `ui/components/column_mapper.py:168` seeds `value=10.0`; `dash_app/pages/home.py:357` seeds `value=10`. Most datasets carry a β nobody entered.

### Decision: gated conversion, never a silent guess

```
ΔCp [J/(g·K)] = step[W/g] × 60 / β
ΔH  [J/g]     = area[W·K/g] × 60 / β
```

Both operate on the **working** signal unit; neither ever divides by mass again.

Gate — all must hold:

1. β present, finite, > 0
2. `heating_rate_source` ∈ {`user`, `parsed`} (`ui_default` / `legacy_unknown` → withhold)
3. `working_signal_unit` resolves to a known specific-power unit with a finite `W/g` factor
4. `normalization_applied` is consistent with that unit (raw power + `True`, specific + `False`)

Withheld-reason vocabulary: `heating_rate_missing` · `heating_rate_invalid` · `heating_rate_unverified` · `signal_unit_unusable` · `signal_not_mass_normalized` · `legacy_unknown`.

### New module: `core/units_dimensional.py`

Pure, no I/O, no pipeline imports — mirrors `core/sign_convention.py` from PR-8.

#### Unit class is NOT sufficient — the exact unit is required

`normalize_by_mass` (`core/preprocessing.py:195`) divides by **milligrams**, so one `RAW_POWER` class yields two different working units:

| source | after `normalize()` | working unit | factor → W/g |
|---|---|---|---|
| `mW` | `mW / mg` | `mW/mg` | **1.0** |
| `W`  | `W / mg`  | `W/mg`  | **1000.0** |

A class-only design returns the `W` case 1000× too small. Conversion takes the **exact canonical unit** (or its factor), never a class.

```python
UNIT_TO_W_PER_G = {
    "mW/mg": 1.0,      # 1e-3 W / 1e-3 g
    "W/g":   1.0,
    "W/mg":  1000.0,   # 1 W / 1e-3 g
    "mW/g":  1e-3,
}
RAW_POWER_TO_WORKING = {"mW": "mW/mg", "W": "W/mg"}

class UnitClass(str, Enum):
    SPECIFIC_POWER = "specific_power"
    RAW_POWER      = "raw_power"
    UNUSABLE       = "unusable"      # a.u., µV, mV, unknown, ""

@dataclass(frozen=True)
class Conversion:
    value: Optional[float]           # None when withheld
    basis: str                       # 'beta_corrected' | 'raw_signal_step' | 'temperature_domain_area' | 'legacy_unknown'
    withheld_reason: Optional[str]
    beta_k_min: Optional[float]
    signal_unit: Optional[str]       # exact working unit the factor came from
    factor_to_w_per_g: Optional[float]

def canonical_signal_unit(unit: str | None) -> tuple[str, UnitClass]
def factor_to_w_per_g(unit: str) -> Optional[float]
def resolve_working_unit(source_unit, sample_mass_mg, normalize_requested,
                         *, working_unit=None, normalization_applied=False)
    -> tuple[str, bool, Optional[str]]   # (working_unit, normalization_applied, reason)
def resolve_beta(heating_rate, heating_rate_source) -> tuple[float | None, str | None]
def heat_flow_step_to_delta_cp(step, *, working_signal_unit, beta_k_min) -> Conversion
def peak_area_to_enthalpy(area, *, working_signal_unit, beta_k_min) -> Conversion
def area_units_label(working_signal_unit) -> str    # e.g. "mW/mg·K", "W/mg·K"
```

**Mass is consumed in exactly one place.** The conversion functions take **no** `sample_mass` — only `working_signal_unit`. If raw power reaches conversion, it withholds (`signal_not_mass_normalized`) rather than dividing again, so a double division is structurally impossible.

`canonical_signal_unit` matches longest-token-first (`core/data_io.py:1195` uses insertion-order substring matching and is wrong for `W/mg` / `mW/g` — leave it, out of scope; this module is the authority for dimensional work).

Add `SECONDS_PER_MINUTE = 60.0` and `UNIT_TO_W_PER_G` to `utils/constants.py`; add `"J/g"` and `"J/(g·K)"` to `core/axis_labels.py`.

#### Source unit vs working unit — and idempotent normalize

| Field | Meaning |
|---|---|
| `source_signal_unit` | canonical unit as imported |
| `working_signal_unit` | canonical unit of `self._signal` **right now** |
| `normalization_applied` | whether `normalize()` actually divided by mass |

Transitions — `resolve_working_unit()` decides, `normalize()` performs:

| source | mass | `normalization_applied` | `working_signal_unit` |
|---|---|---|---|
| `W/g`, `mW/mg` | any | `False` (skip + warning) | unchanged, factor 1.0 / per table |
| `mW` | > 0 | `True` | `mW/mg` (1.0) |
| `W` | > 0 | `True` | `W/mg` (1000.0) |
| `mW` / `W` | missing | `False` (skip + warning) | unchanged, raw → withhold |
| `a.u.` / unknown | any | `False` | `UNUSABLE` → withhold |

**Idempotence is structural, not incidental.** `normalize()` must read the *current* `working_signal_unit` / `normalization_applied` — never the source unit alone — and short-circuit when the working unit is already specific power (or `normalization_applied is True`). `resolve_working_unit()` therefore takes `working_unit` and `normalization_applied` as explicit inputs (above). A second `normalize()` call is a no-op: same working unit, same every downstream number, step not recorded twice. Today `core/batch_runner.py:415-416` calls it unconditionally, so a `W/g` import is divided by mass twice — this is the guard that stops it.

### Legacy-result handling

Any payload written before PR-9 lacks the basis fields. Rules — absence is **not** permission to assume:

- **No `delta_cp_basis`** ⇒ basis = `legacy_unknown`; `delta_cp_j_g_k` stays `None`; reason `legacy_unknown`.
- A legacy **`delta_cp` value must never be interpreted or displayed as corrected J/(g·K)**. It is an unlabeled raw signal step of unknown provenance. Render it as `ΔCp (unknown basis — legacy result)`, never with a J/(g·K) suffix.
- **No `enthalpy_basis`** ⇒ a legacy peak `area` is temperature-domain area, **never J/g**. `enthalpy_j_g` stays `None`.
- Deserialization is the re-entry point: `glass_transition_from_dict` / `thermal_peak_from_dict` (`core/result_serialization.py:850,882`), which `core/project_io.py:256-260` uses to restore project archives. They must default basis to `legacy_unknown` and leave corrected fields `None` rather than coercing.
- Re-analysis of a legacy dataset re-derives everything; the legacy flag applies only to stored results carried forward.

### Field naming

`GlassTransition` (`core/dsc_processor.py:33-40`):

```python
heat_flow_step: float                        # measured step, working signal units
delta_cp_j_g_k: Optional[float] = None       # ONLY when beta-corrected
delta_cp_basis: str = 'legacy_unknown'
delta_cp_withheld_reason: Optional[str] = None
```

`delta_cp` is **renamed** — ~10 call sites (`result_serialization.py:878,888`, `report_generator.py:1648`, `ui/dsc_page.py:616,760`, `dash_app/pages/dsc.py:2721+`, `tests/test_dsc_processor.py:281`).

`ThermalPeak` (`core/peak_analysis.py:41`) — `area` keeps its name (churning ~15 sites buys no honesty); comment corrected, three fields added:

```python
enthalpy_j_g: Optional[float] = None
enthalpy_basis: str = 'legacy_unknown'
enthalpy_withheld_reason: Optional[str] = None
```

**Serialization:** `*_to_dict` emit `delta_cp` / `enthalpy_j_g` only when `basis == 'beta_corrected'`, and always emit `heat_flow_step` / `area` plus basis, withheld reason, and `source_signal_unit` / `working_signal_unit` / `normalization_applied`. New payloads are self-describing; old ones degrade to `legacy_unknown`.

### Threading

| Site | Change |
|---|---|
| `core/dsc_processor.py:95-140` | `__init__` gains `signal_unit` → `self._source_signal_unit`; init `working_signal_unit`, `normalization_applied = False` (TGA precedent: `core/tga_processor.py:364-384`, `core/batch_runner.py:542`) |
| `core/dsc_processor.py:166-189` `normalize()` | Rewrite around `resolve_working_unit()` reading current `working_signal_unit` / `normalization_applied`; skip + warn when already specific or mass missing; on apply set working unit + flag + record transition |
| `core/batch_runner.py:405-411` | pass `signal_unit=(dataset.units or {}).get("signal")` |
| `ui/dsc_page.py:552-557` | pass `signal_unit=dataset.units.get("signal")` (also pass `sign_convention`, missing here unlike batch) |
| `core/dsc_processor.py:346-358`, `:239-244` | conversions read `self._working_signal_unit`; never `self._sample_mass` |

`ui/dsc_page.py:305` discards `normalize_by_mass`'s return — pre-existing no-op, logged, not fixed here.

### Remove the fabricated β default

| Site | Change |
|---|---|
| `ui/components/column_mapper.py:167-170` | `value=None`; example moves to label/help. `st.number_input` returns `None` until typed — that *is* the provenance signal |
| `ui/components/column_mapper.py:210` | add `"heating_rate_source": "user" if heating_rate else "missing"` |
| `dash_app/pages/home.py:357` | `value=None, placeholder="e.g. 10"` — **only after the stability fix is merged** |
| `dash_app/pages/home.py:1313` | keep the `None` guard; add `heating_rate_source` |
| `backend/models.py:231` | add `heating_rate_source: str | None = None` |
| `core/data_io.py:620,1609,1992` | carry `heating_rate_source` through the three parsers |

`parsed` is reserved; no parser sets it yet. **Absent source ⇒ `legacy_unknown` ⇒ withhold** — pre-PR-9 datasets lose their borrowed β. Honest outcome; state it in the PR description.

### Fix the double-subtraction (D3)

```python
# core/dsc_processor.py find_peaks — track the frame, don't guess it
self._baseline_applied = True          # set in correct_baseline() (:209-213)
...
baseline_for_char = (
    np.zeros_like(self._signal) if self._baseline_applied else None
)
self._peaks = characterize_peaks(T, self._signal, raw_peaks,
                                 baseline=baseline_for_char)
```

Identical one-liner at `core/batch_runner.py:728` and `ui/dta_page.py:645`. No `characterize_peaks` signature change.

### Labels, equations, reports, UI — no hardcoded or unitless units

**Nothing is rendered as unitless.** Temperature-domain area renders with `area_units_label(working_signal_unit)` — working signal unit × K (`mW/mg·K`, `W/mg·K`, …). Step height renders with the dynamic working unit, **not** a hardcoded `W/g`. Legacy payloads render `unknown basis` instead of a unit.

| Site | Change |
|---|---|
| `core/result_serialization.py:197-203` | Replace the lying equation. Always emit `event_area = ∫(signal − baseline) dT` with its real unit; emit `ΔH[J/g] = area × 60 / β` only when `enthalpy_basis == 'beta_corrected'` |
| `core/result_serialization.py:228-231` | Add a dimensional limitation (copy the DTA precedent at `:337-341,352-356`) |
| `core/result_serialization.py:831-889, 933-964` | Carry `heat_flow_step` / `delta_cp_j_g_k` / basis / withheld reason / `source_signal_unit` / `working_signal_unit` / `normalization_applied` / `heating_rate_source` through rows and summary |
| `core/result_serialization.py:850,882` | `*_from_dict` default basis to `legacy_unknown`; never coerce |
| `core/report_generator.py:1648` | Dynamic label from basis + working unit: `ΔCp (J/(g·K))` when corrected, `Step height (<working_signal_unit>)` otherwise, `ΔCp (unknown basis — legacy result)` for legacy; append the withheld reason when present |
| `ui/dsc_page.py:616,760` | ΔCp metric driven by basis; never a bare `ΔCp` |
| `ui/dsc_page.py:728,770`, `ui/components/plot_builder.py:402` | Drop hardcoded `J/g`; render area with `area_units_label(working_signal_unit)`; show `enthalpy_j_g` only when corrected |
| `dash_app/pages/dsc.py:965,2711,2806` | Area column gets a real unit (it was effectively unitless); enthalpy column appears only when corrected |
| `utils/i18n.py` | Add `ΔCp` / `step height` / `enthalpy` / `J/(g·K)` / `J/g` / `unknown basis` keys in EN+TR. Reuse the unused `dash.analysis.label.dcp` (`:1702`) for ΔCp; separate key for step height |

**DTA stays out of the J/g conversion** — `core/dta_processor.py:240-243` documents its area has no calibration constant. DTA gets the double-subtraction fix only.

---

## Implementation order

1. Land the Dash stability fix; confirm main moved; branch from updated main.
2. Roadmap PR-8 update (may land independently, docs-only).
3. `core/units_dimensional.py` + `tests/test_units_dimensional.py`. Pure addition; suite stays green.
4. Thread source/working unit + `normalization_applied`; rewrite `normalize()` around `resolve_working_unit()`.
5. Fix double-subtraction at three sites; non-zero-baseline regression (DSC + DTA).
6. Rename `delta_cp` → `heat_flow_step`; add conversion fields; update ~10 sites.
7. Add `enthalpy_*` to `ThermalPeak`; wire `find_peaks`; serialize + legacy deserialization defaults.
8. Remove β defaults; add `heating_rate_source`.
9. Dynamic labels, equations, reports, i18n (EN+TR).
10. Golden gates + full suite + ruff.

## Acceptance / verification

New `tests/test_dimensional_honesty_golden.py`:

- **Known-β ΔH** — Gaussian from `generate_test_data.py`'s relation (`A = H·β/60 / (σ√(2π))`, `H=25 J/g`, `σ=7`) at **β=10 and β=20**; `enthalpy_j_g` ≈ 25 both. A missing β conversion cannot pass both.
- **Known-β ΔCp** — tanh step (fixture amplitude 0.08) at β=10 and β=20; matches the 60/β relation.
- **Normalized-once equivalence.** Two datasets describing the same physics — raw `mW` + `sample_mass` vs already-specific `W/g` (raw divided through by mass) — must yield **identical** `delta_cp_j_g_k`, `enthalpy_j_g`, and `working_signal_unit` after `process()`. `normalization_applied` True for the raw pair, False for the specific pair.
- **Normalize idempotence** — calling `normalize()` twice leaves `working_signal_unit`, the signal, and all derived numbers unchanged; the step is not recorded twice.
- **Factor table** — `factor_to_w_per_g`: `mW/mg = 1.0`, `W/g = 1.0`, `W/mg = 1000.0`, `mW/g = 1e-3`.
- **Unit-equivalence vs numeric-equality — two distinct cases, both required:**
  - *Equivalent physical power* — the same power expressed as `1 W` and as `1000 mW`, each with the same sample mass, must produce **identical** specific-power results and identical corrected ΔCp/ΔH.
  - *Identical numeric values with different units* — a numeric value of `1` labelled `W` vs `1` labelled `mW`, with the same mass, must produce specific-power results differing by exactly **1000×**.

  Testing only the first would pass while the factor table is inverted; testing only the second would pass while conflating unit conversion with physical equivalence.
- **Legacy payload regression** — feed pre-PR-9 serialized dicts (bare `delta_cp`, bare peak `area`, no basis keys) through `glass_transition_from_dict` / `thermal_peak_from_dict` and through `core/project_io.py:_deserialize_dsc_state`. Assert: basis == `legacy_unknown`, `delta_cp_j_g_k is None`, `enthalpy_j_g is None`, legacy `delta_cp` is **not** surfaced with a J/(g·K) label, legacy `area` is **not** surfaced as J/g. Include a full archive round-trip.
- **Gate** — β missing / 0 / negative / non-finite / `ui_default` / `legacy_unknown` ⇒ corrected fields `None` **and** non-null `withheld_reason`; raw quantity still present and correct.
- **Unit class** — `W/g` and `mW/mg` convert without mass; `mW` without mass withholds (`signal_not_mass_normalized`); `mW` with mass converts; `a.u.` withholds.
- **No double subtraction** — peak on a non-zero sloped baseline; `area` within 10% of analytical, `height` ≈ amplitude, `fwhm` ≈ `2.3548σ`, for DSC and DTA. (`tests/test_peak_analysis.py:349` uses a zero baseline and cannot catch this.)

Existing tests to watch:

- `tests/test_dsc_processor.py:281` — `tg.delta_cp > 0.0` → field rename
- `tests/test_dsc_processor.py:427-479` — area sign assertions; magnitudes change, signs must not
- `tests/test_dsc_processor.py:253-263` — `"normalize" not in step_names` when mass missing; must survive the new skip logic
- `tests/test_sign_convention_golden.py:129` — cross-encoding magnitude equality; must still hold

Also: `ruff check`, `git diff --check`, and a manual Dash import confirming an untouched rate control yields `heating_rate=None` plus a visible "units unavailable" reason rather than a number. Re-run this after the stability fix merges, since it touches the same import path.

## Boundaries

- **In scope:** the four defects; DSC dimensional honesty; DTA double-subtraction only.
- **Out of scope:** K/°C gate (PR-10), DTA `characterize_peaks` reuse (PR-11), broader already-specific re-normalization UI (PR-12 — PR-9 takes only the guard it needs), import validation (PR-13), store (PR-14). No `characterize_peaks` signature change. No dependency changes. No Streamlit page work beyond the two files named.
- **Follow-up logged, not fixed:** `ui/dsc_page.py:305` discards `normalize_by_mass`'s return (pre-existing no-op).
- Any newly discovered defect becomes its own work package, per the Phase 1 one-PR-per-WP rule.
