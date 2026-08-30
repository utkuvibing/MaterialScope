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

## Note

MaterialScope is an evolving research and engineering project. Its analysis outputs support scientific workflows but do not replace expert validation, particularly for qualitative spectral and XRD interpretation.

## License

MIT — see [LICENSE](LICENSE).
