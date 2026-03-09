# Electron Bootstrap (Tranche 1)

This directory contains a minimal desktop bootstrap shell for the first migration tranche.

What it does:
- launches local Python backend (`backend/main.py`)
- waits for `/health`
- opens an Electron window
- shows backend status + version
- provides `.thermozip` open/save smoke actions through backend `/project/load` and `/project/save`

What it does not do:
- does not migrate Streamlit pages
- does not change scientific algorithms
- does not replace current Windows packaging flow yet

## Run (development)

From repo root:

```powershell
cd desktop\electron
npm install
npm start
```

Optional environment variable:
- `TA_PYTHON` to override Python executable used for backend launch.

