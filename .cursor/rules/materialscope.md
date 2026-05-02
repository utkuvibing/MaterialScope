---
description: MaterialScope architecture and contribution constraints
alwaysApply: true
---

# MaterialScope Project Rules

- Treat MaterialScope as a Python-first scientific application. Keep Node/TypeScript limited to automation or desktop packaging unless a task explicitly says otherwise.
- Preserve the current app shape: `dash_app/` is the primary Dash + Plotly interface, `backend/` is FastAPI, `core/` owns analysis/reporting logic, and `ui/` is the legacy Streamlit surface.
- Prefer small, focused fixes that follow existing local patterns. Do not restructure the app, rename major directories, or introduce broad framework changes for issue-level work.
- Keep secrets and local artifacts out of commits. Never commit `.env`, credentials, generated reference libraries, build output, cache directories, or private paths.
- Use `pytest` for validation when dependencies are available. If optional scientific dependencies are unavailable, report the limitation clearly instead of masking test failures.
