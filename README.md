# MaterialScope

**[English](README.md) · [Türkçe](README.tr.md)**

MaterialScope is an open-source Python workbench for reproducible materials-characterization workflows. It brings DSC, TGA, DTA, FTIR, Raman, and XRD data into one place for import, processing, comparison, visualization, and report-ready export.

## What it does

- Imports common laboratory files: CSV, TXT, TSV, XLSX, and XLS.
- Helps review column mapping and data-quality warnings before analysis.
- Provides modality-aware workflows for thermal, spectral, and diffraction data.
- Lets you compare runs and export figures, data, and reports.

## How it works

1. Import one or more measurement files.
2. Review the detected format, columns, and metadata.
3. Select the relevant analysis workflow and inspect the interactive results.
4. Compare runs when needed, then export the data or a report.

MaterialScope is designed to keep source data, processing choices, visualizations, and exported results connected in a single project workflow.

## Run locally

**Prerequisites:** Python 3.11+ and `pip`.

```bash
git clone https://github.com/utkuvibing/MaterialScope.git
cd MaterialScope
python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Install the project and start the app:

```bash
pip install -e .
python -m dash_app.server
```

For development and testing, also install the tooling extra:

```bash
pip install -e ".[dev]"
```

Open [http://127.0.0.1:8050](http://127.0.0.1:8050) in your browser.

This command starts one process serving both Dash and the FastAPI API on the same port. You do not need to start a second backend for Dash.

For a sample-data walkthrough and feedback instructions, see the [early-tester guide](docs/early-tester-guide.md).

## Data and deployment

The local launch runs on your computer. Workspaces are held in memory: before stopping or restarting the server, download a `.scopezip` project archive from the Project page and keep it on disk. Saving an analysis result within the workspace is not a durable backup. Reopen the archive from Project to resume later; keep your original measurement files separately.

Local-first does not mean every feature is offline. Configured reference-library downloads, cloud library lookups, and literature services can make network requests. See [reference-library configuration](docs/reference_library_ingest.md) for those workflows.

API authentication is optional. To enable it for protected API routes, start the combined server with your own token:

```bash
python -m dash_app.server --token "YOUR_PRIVATE_TOKEN"
```

The bundled Dash client receives that token automatically. Setting `MATERIALSCOPE_API_TOKEN` alone configures the client; it does not enable server authentication. Binding to a non-loopback address without a token prints a warning but still starts the server. `/health` remains unauthenticated even when a token is enabled. This API token is not a browser login system.

## Other application surfaces

The [Windows installer](packaging/windows/README.md) retains the Streamlit application and prefers port 8501. The [Electron shell](desktop/electron/README.md) is a desktop experiment that launches a backend-only service; it does not package the Dash UI.

Streamlit still has library, license, kinetics, and deconvolution pages with no equivalent Dash pages; kinetics and deconvolution are preview features. Dash library features and backend endpoints do not imply page-level parity. Streamlit remains a dependency, including through shared translations. See the [Streamlit parity inventory](docs/streamlit-parity-inventory.md) for the gaps and migration prerequisites. Retirement requires a separate migration; no removal date is set.

Current documentation uses MaterialScope. Existing `ThermoAnalyzer` packaging filenames, environment aliases, and other compatibility identifiers remain unchanged.

## Note

MaterialScope is an evolving research and engineering project. Its analysis outputs support scientific workflows but do not replace expert validation, particularly for qualitative spectral and XRD interpretation.

## License

MaterialScope is licensed under the GNU Affero General Public License v3.0 only (AGPL-3.0-only) — see [LICENSE](LICENSE). Commercial use is permitted under the AGPL as long as its terms are followed. Organizations that want to use, modify, distribute, embed, or offer MaterialScope without the AGPL's copyleft and source-sharing obligations can ask the copyright holder about a separate proprietary/commercial license — see [COMMERCIAL-LICENSING.md](COMMERCIAL-LICENSING.md). Revisions released before the license transition were published under the MIT License and remain usable under the license that applied to those revisions — see [LICENSE_HISTORY.md](LICENSE_HISTORY.md). The MaterialScope name and logo are not licensed for uses that imply official status — see [TRADEMARKS.md](TRADEMARKS.md).

The software copyright license is a separate concept from the application's optional runtime license-key mechanism (`MATERIALSCOPE_LICENSE_SECRET`, HMAC-signed keys). That mechanism is a deployment feature flag only: it does not change, replace, or add to the copyright license, and setting the environment variable does not relicense the software in either direction.

The optional commercial-license gate is also separate from the API token. Its HMAC demo secret is public, so anyone with it can forge license keys. Commercial deployments must supply `MATERIALSCOPE_LICENSE_SECRET` externally; rotating it invalidates existing signed licenses and requires re-issuance. A client-held shared secret still cannot provide secure distributable licensing. Asymmetric signing is future work.
