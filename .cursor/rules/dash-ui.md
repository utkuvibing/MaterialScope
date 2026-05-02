---
description: Dash and Plotly UI conventions for MaterialScope
globs: dash_app/**/*.py
alwaysApply: false
---

# Dash UI Rules

- Keep Dash callbacks explicit and local to the feature area when possible. Avoid broad callback rewrites for narrow UI fixes.
- Preserve Plotly figure readability for laboratory workflows: clear axis labels, units where available, useful legends, and cautious annotations.
- Do not move primary Dash behavior back into the legacy Streamlit `ui/` surface unless the task explicitly targets legacy UI.
- Keep expensive parsing, fitting, and report generation out of hot UI paths where possible. Use existing backend or core helpers rather than duplicating analysis logic in callbacks.
- When changing interactive state, check empty data, malformed uploads, and multi-file comparison cases.
