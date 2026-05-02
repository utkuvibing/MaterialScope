---
description: Scientific safety expectations for MaterialScope changes
globs: **/*.py
alwaysApply: false
---

# Scientific Safety

- Do not present DSC, TGA, DTA, FTIR, Raman, XRD, kinetics, deconvolution, or matching output as definitive scientific identification unless the code already has validated expert-grade evidence.
- Preserve cautionary language for prototype and screening workflows. Prefer terms such as "screening aid", "qualitative comparison", "candidate", and "requires expert validation".
- Keep raw data, processing choices, validation warnings, figures, and exports traceable when changing analysis or reporting paths.
- Add focused tests for parser behavior, numerical edge cases, validation warnings, and export contracts when a change affects scientific outputs.
- Avoid silent fallbacks that change scientific meaning. If data cannot be parsed or validated, surface a clear warning or error using the existing project patterns.
