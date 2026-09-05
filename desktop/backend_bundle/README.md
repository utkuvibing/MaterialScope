# Desktop Backend Bundle

This folder contains the Windows-focused backend freezing path used by the Electron desktop package.

This is an experimental backend-only bundle for `backend.main`; it does not include the Dash UI or the Streamlit Windows installer. For the combined Dash/FastAPI application, follow the [root README](../../README.md#run-locally).

## Goal

Build a local backend executable so the packaged Electron app does not require system Python.

## Build Command

From repository root:

```powershell
python .\desktop\backend_bundle\build_backend.py --clean
```

Expected output:

- `desktop/backend_bundle/dist/materialscope_backend/materialscope_backend.exe`

## Notes

- This bundle keeps backend API contracts unchanged; it only changes runtime distribution.
- Build machine must have PyInstaller installed in the active Python environment.
