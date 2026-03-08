# Windows Setup Packaging (Local-First)

This folder defines the primary Windows distribution flow for ThermoAnalyzer:

1. Build locally on Windows.
2. Produce one installer: `ThermoAnalyzer_Setup_<APP_VERSION>.exe`.
3. Upload that `.exe` to GitHub Releases.
4. End users only download and run `Setup.exe`.

For the short release checklist, see [RELEASE_PREP_LOCAL.md](RELEASE_PREP_LOCAL.md).

## Packaging model (kept intentionally stable)

- Runtime packaging: PyInstaller `onedir`
- Installer: Inno Setup 6
- Launch model: local launcher that starts Streamlit and opens the default browser

No architecture rewrite, no framework migration, and no data-contract changes are required.

## Prerequisites (build machine only)

- Windows machine
- Python 3.10+ available on PATH
- Repository checked out locally
- Dependencies installed with `pip install -r requirements.txt`
- Inno Setup 6 installed (`ISCC.exe`)
- Internet access during build to download official Microsoft `vc_redist.x64.exe` (unless `-VcRedistPath` is provided)

## Primary build commands (local Windows)

From repo root:

```powershell
pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File packaging\windows\build_beta_installer.ps1
```

Shortcut alternative:

```powershell
packaging\windows\build_beta_installer.bat
```

Optional flags:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build_beta_installer.ps1 -IsccPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
powershell -ExecutionPolicy Bypass -File packaging\windows\build_beta_installer.ps1 -VcRedistPath "C:\installers\vc_redist.x64.exe"
powershell -ExecutionPolicy Bypass -File packaging\windows\build_beta_installer.ps1 -SetupBaseName "ThermoAnalyzer_Setup"
```

## Expected output

Final installer:

```text
release\ThermoAnalyzer_Setup_<APP_VERSION>.exe
```

Example:

```text
release\ThermoAnalyzer_Setup_2.0.exe
```

Intermediate build folders:

```text
packaging\windows\dist\
packaging\windows\build\
```

## GitHub Release publish (manual, no Actions required)

1. Open GitHub repository -> **Releases** -> **Draft a new release**.
2. Tag/version the release (for example `v2.0.0-beta1`).
3. Upload `release\ThermoAnalyzer_Setup_<APP_VERSION>.exe` as asset.
4. Publish release.

Professor/end user path is then:

- Release page
- Download `ThermoAnalyzer_Setup_<APP_VERSION>.exe`
- Double-click -> `Next` -> `Install` -> `Finish`

## Optional: Actions path (secondary only)

The repo still includes `.github/workflows/windows-beta-installer.yml` as an optional automation path. It is not required for the primary release model above.

## End-user behavior

- No Python, pip, PATH edits, terminal, or PowerShell needed on end-user machines.
- Installer can auto-attempt Microsoft VC++ runtime compatibility install when missing.
- Application runs locally and opens in browser (accepted beta behavior).

## Known limitations

- UI still opens in a browser tab (not a native desktop shell).
- Some systems may show one-time Windows prompts (browser/firewall/runtime).
- Installer size remains larger due to `onedir` reliability choice.
