# Local Windows Release Prep

This checklist describes the retained Streamlit Windows installer. It is separate from the [Dash setup](../../README.md#run-locally) and does not establish that an installer has been built or validated.

Before building, use Python 3.11+ and reconcile the missing guide/library inputs listed in [packaging limitations](README.md#known-limitations). Keep the existing `ThermoAnalyzer` spec and installer filenames; packaging migration is separate work.

## 1. Build on local Windows machine

From repo root:

```powershell
pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File packaging\windows\build_beta_installer.ps1
```

Expected installer output:

```text
release\MaterialScope_Setup_<APP_VERSION>.exe
```

Default naming pattern:

```text
MaterialScope_Setup_<APP_VERSION>.exe
```

## 2. Quick validation before publish

- Confirm installer file exists under `release\`.
- Install once on a clean/secondary Windows machine if available.
- Validate launch path: Start Menu shortcut opens the Streamlit app in a browser, preferring port 8501 (with an available-port fallback), rather than the Dash app on 8050.
- Check that the intended help files and library resources are actually installed; missing spec inputs may be silently omitted.
- Verify stable beta scope flows still run (DSC, TGA, Compare Workspace, Batch Template Runner, export, `.scopezip` save/load with legacy `.thermozip` open support).

## 3. Publish to GitHub Releases

1. Open repository -> **Releases** -> **Draft a new release**.
2. Set release tag/version (for example `v2.0.0-beta1`).
3. Upload `release\MaterialScope_Setup_<APP_VERSION>.exe` as asset.
4. Publish release.

## 4. What to send to professors

Share only:

- GitHub Release URL
- One-line instruction: "Download `MaterialScope_Setup_<APP_VERSION>.exe`, run Setup, then click Next -> Install -> Finish."

No Python/pip/terminal instructions should be sent to end users.
