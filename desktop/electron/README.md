# MaterialScope Electron Shell

This folder is a desktop packaging experiment for MaterialScope. It shows how the Python FastAPI backend can be launched from Electron and presented as a local desktop application shell.

## What It Demonstrates

- Electron main/preload/renderer process separation
- local backend startup and health probing
- randomized local backend port and token handling
- startup diagnostics for backend launch failures
- project archive open/save dialogs
- basic desktop workflow shell around the Python backend

## Development

From this directory:

```powershell
npm install
npm start
```

Useful scripts:

```powershell
npm run test:startup-paths
npm run test:startup-diagnostics
npm run build:backend
```

Generated installers, backend bundles, logs, and `node_modules/` are intentionally excluded from the public repository.
