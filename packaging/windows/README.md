# Windows Setup Packaging (Local-First)

This folder contains the retained Windows installer for the Streamlit application. For the current Dash application, use the [root README setup](../../README.md#run-locally). This installer does not launch Dash.

The intended release flow, after build inputs and the resulting installer have been validated, is:

1. Build locally on Windows.
2. Produce one installer: `MaterialScope_Setup_<APP_VERSION>.exe`.
3. Upload that `.exe` to GitHub Releases.
4. End users only download and run `Setup.exe`.

For the short release checklist, see [RELEASE_PREP_LOCAL.md](RELEASE_PREP_LOCAL.md).

## Packaging model (kept intentionally stable)

- Runtime packaging: PyInstaller `onedir`
- Installer: Inno Setup 6
- Launch model: local launcher that starts Streamlit and opens the default browser

The launcher prefers port 8501 and chooses another available port if needed. Dash defaults to 8050. Streamlit retirement and installer migration require separate work; see the [parity inventory](../../docs/streamlit-parity-inventory.md).

## Prerequisites (build machine only)

- Windows machine
- Python 3.11+ available on PATH
- Repository checked out locally
- Dependencies installed with `pip install -r requirements.txt`
- Inno Setup 6 installed (`ISCC.exe`)
- Internet access during build to download official Microsoft `vc_redist.x64.exe` (unless `-VcRedistPath` is provided)

## Primary build commands (local Windows)

These are the existing build commands, not evidence of a verified installer build. Review the missing inputs under Known limitations first. From repo root:

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
powershell -ExecutionPolicy Bypass -File packaging\windows\build_beta_installer.ps1 -SetupBaseName "MaterialScope_Setup"
```

## Expected output

Final installer:

```text
release\MaterialScope_Setup_<APP_VERSION>.exe
```

Example:

```text
release\MaterialScope_Setup_2.0.exe
```

Intermediate build folders:

```text
packaging\windows\dist\
packaging\windows\build\
```

## GitHub Release publish (manual, no Actions required)

1. Open GitHub repository -> **Releases** -> **Draft a new release**.
2. Tag/version the release (for example `v2.0.0-beta1`).
3. Upload `release\MaterialScope_Setup_<APP_VERSION>.exe` as asset.
4. Publish release.

Professor/end user path is then:

- Release page
- Download `MaterialScope_Setup_<APP_VERSION>.exe`
- Double-click -> `Next` -> `Install` -> `Finish`

## Optional: Actions path (secondary only)

The primary release model is local Windows packaging. Add repository automation separately if you need hosted installer builds.

## End-user behavior

- No Python, pip, PATH edits, terminal, or PowerShell needed on end-user machines.
- Installer can auto-attempt Microsoft VC++ runtime compatibility install when missing.
- Application runs locally and opens in browser (accepted beta behavior).

## Known limitations

- The spec references untracked/absent inputs: `build/reference_library_hosted`, `build/reference_library_mirror_live`, `PROFESOR_KURULUM_VE_KULLANIM_KILAVUZU.md`, `PROFESSOR_SETUP_AND_USAGE_GUIDE.md`, and `PROFESSOR_BETA_GUIDE.md`. Its collection helper can omit missing paths, so a completed build alone does not prove those resources were bundled. Reconcile inputs and validate the installed contents in a separate packaging change before release.
- This documentation pass does not verify an installer build. The Dash [early-tester guide](../../docs/early-tester-guide.md) is current guidance for Dash, not a replacement installer manifest input.
- `ThermoAnalyzerLauncher.spec`, `ThermoAnalyzer_Beta.iss`, and legacy environment aliases retain their compatibility names. Use the exact existing filenames in build commands.
- UI still opens in a browser tab (not a native desktop shell).
- Some systems may show one-time Windows prompts (browser/firewall/runtime).
- Installer size remains larger due to `onedir` reliability choice.
