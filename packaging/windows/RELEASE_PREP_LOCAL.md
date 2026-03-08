# Local Windows Release Prep

This is the primary release process for ThermoAnalyzer beta distribution.

## 1. Build on local Windows machine

From repo root:

```powershell
pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File packaging\windows\build_beta_installer.ps1
```

Expected installer output:

```text
release\ThermoAnalyzer_Setup_<APP_VERSION>.exe
```

Default naming pattern:

```text
ThermoAnalyzer_Setup_<APP_VERSION>.exe
```

## 2. Quick validation before publish

- Confirm installer file exists under `release\`.
- Install once on a clean/secondary Windows machine if available.
- Validate launch path: Start Menu shortcut opens app in browser.
- Verify stable beta scope flows still run (DSC, TGA, Compare Workspace, Batch Template Runner, export, `.thermozip` save/load).

## 3. Publish to GitHub Releases

1. Open repository -> **Releases** -> **Draft a new release**.
2. Set release tag/version (for example `v2.0.0-beta1`).
3. Upload `release\ThermoAnalyzer_Setup_<APP_VERSION>.exe` as asset.
4. Publish release.

## 4. What to send to professors

Share only:

- GitHub Release URL
- One-line instruction: "Download `ThermoAnalyzer_Setup_<APP_VERSION>.exe`, run Setup, then click Next -> Install -> Finish."

No Python/pip/terminal instructions should be sent to end users.
