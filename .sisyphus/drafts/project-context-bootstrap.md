# Draft: Project Context Bootstrap

## Requirements (confirmed)
- before writing code, read and understand `.ai` files
- be ready to execute using repo instructions and project knowledge

## Technical Decisions
- context source of truth is repository files (`.ai/*`, `README.md`, `.cursor/rules/*`), not chat memory
- work should proceed in small, verifiable slices with explicit scope boundaries

## Research Findings
- `.ai/AGENTS.md`: context-first workflow, pre-change checklist, and update discipline for SESSION/DECISIONS
- `.ai/SESSION.md`: latest completed slice is thermal literature semantics backend update; next suggested slice is wiring semantics into Dash/report explanations
- `.ai/TASK.md`: active slice status is marked implemented for backend thermal semantics, with verification commands recorded
- `.ai/DECISIONS.md`: durable decisions reinforce modality-by-modality Dash migration and behavior-first thermal comparison semantics
- `.ai/BUGS.md`: one standing suspected parity-gap meta-bug (BUG-001), no newly confirmed open bug from this pass

## Open Questions
- what is the next slice to plan: Dash/report-facing thermal semantics UI wiring, or another priority?

## Scope Boundaries
- INCLUDE: context loading, constraints extraction, and planning readiness
- EXCLUDE: code implementation and source-file mutation
