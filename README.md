# MaterialScope

MaterialScope is an open-source scientific software project for reproducible materials-characterization workflows across DSC, TGA, DTA, FTIR, Raman, and XRD data. It is a Python workbench for importing, processing, comparing, and reporting common laboratory analysis data, and demonstrates a full-stack scientific application: data ingestion, modality-specific processing, interactive Plotly views, a FastAPI backend, report generation, and regression-tested workflows.

The current primary interface is a Dash + Plotly app mounted on FastAPI. A legacy Streamlit interface remains in the repository for comparison and transition work.

**Project home:** [github.com/utkuvibing/MaterialScope](https://github.com/utkuvibing/MaterialScope).

## Why This Project Matters

Materials labs often move between vendor exports, spreadsheets, plotting tools, and handwritten report notes. MaterialScope explores a more reproducible workflow where raw data, processing choices, validation warnings, figures, and report artifacts stay connected in one project archive.

For portfolio review, this repository is intended to show:

- scientific data parsing and validation across multiple file formats
- reproducible analysis pipelines for thermal, spectral, and diffraction-style workflows
- interactive Dash/Plotly UI design for technical users
- FastAPI endpoints for analysis, project state, export, and diagnostics
- automated tests around import behavior, backend contracts, plotting, and reporting

## Feature Status

| Area | Status | Notes |
| --- | --- | --- |
| DSC, TGA, DTA | Stable prototype | Thermal import, preprocessing, peak/step analysis, summaries, and export paths. |
| FTIR, Raman | Prototype | Spectral import, preprocessing, and qualitative comparison workflows. |
| XRD | Prototype | Qualitative phase-screening workflow; not a substitute for expert confirmation. |
| Compare workspace | Stable prototype | Cross-run review and project-level comparison. |
| DOCX/PDF/XLSX/CSV export | Stable prototype | Report and data export paths with validation context. |
| Kinetics and deconvolution | Experimental | Present for exploration; not presented as production-ready. |
| Streamlit UI | Legacy | Kept as a transition/reference surface while Dash is the primary app. |

## Tech Stack

- Python
- Dash and Plotly
- FastAPI
- Pandas, NumPy, SciPy, scikit-learn
- Streamlit legacy UI
- Pytest
- Docker-ready server entrypoint
- Electron packaging experiments for desktop delivery

## Screenshots And Demo

Screenshots and a short demo walkthrough should be added before sharing this repository widely.

Suggested screenshots:

- import and column-mapping workflow
- thermal analysis result page
- spectral or XRD qualitative comparison page
- compare workspace
- export/report generation screen

## Installation

### Prerequisites

- Python 3.10 or newer
- `pip`

### Setup

```bash
git clone https://github.com/utkuvibing/MaterialScope.git
cd MaterialScope

python -m venv venv
```

Activate the virtual environment:

```bash
# Linux/macOS
source venv/bin/activate

# Windows PowerShell
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Running The App

Start the primary Dash + FastAPI app:

```bash
python -m dash_app.server
```

Default local URL:

```text
http://127.0.0.1:8050
```

Start the backend API only:

```bash
python -m backend.main
```

Run the legacy Streamlit UI:

```bash
streamlit run app.py
```

## Sample Data

The repository includes small sample and test datasets for local development and automated tests.

Before publishing or redistributing this repository, review the contents of `sample_data/` and `test_data/` to confirm that every included file is permitted for public redistribution under its source license.

## Repository Layout

```text
MaterialScope/
├── app.py                 # legacy Streamlit entrypoint
├── dash_app/              # primary Dash + Plotly app and combined server
├── backend/               # FastAPI backend and API models
├── core/                  # analysis, validation, plotting, and reporting logic
├── ui/                    # legacy Streamlit pages/components
├── tools/                 # local ingest, diagnostics, and utility scripts
├── tests/                 # pytest suite
├── sample_data/           # documented sample datasets and fixtures
├── test_data/             # test fixtures
├── desktop/               # desktop packaging experiments
├── packaging/windows/     # Windows packaging scripts and notes
└── requirements.txt
```

## Development Notes

Run tests with:

```bash
pytest
```

Optional environment variables can be placed in a local `.env` file when needed. Do not commit real API keys, tokens, private paths, generated libraries, build outputs, or local packaging artifacts.

## Contributing

Issues, bug reports, documentation improvements, and small feature PRs are welcome.

Scientific results must be validated carefully. XRD, spectral matching, and experimental modules are screening/prototype aids, not definitive expert confirmation.

## Limitations

- Qualitative spectral and XRD matches are screening aids, not definitive identification.
- Experimental modules may change without backward compatibility.
- Bundled sample data is for testing and demonstration, not scientific benchmarking.
- This repository may contain packaging and migration work that is useful for engineering review but not intended as polished end-user documentation.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
