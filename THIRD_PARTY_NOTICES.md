# Third-Party Notices

MaterialScope is distributed under AGPL-3.0-only. The items below are
third-party material bundled with, referenced by, or fetched through the
project. They are **not** covered by the project's AGPL grant and remain
under their own licenses or terms where applicable.

## Runtime-fetched reference libraries

`tools/library_ingest/` and the reference-library features fetch data at
runtime from external providers. Provider metadata and declared license
identifiers live in `tools/library_ingest/provider_sources.json`:

| Provider | Content | Declared license |
|---|---|---|
| COD (Crystallography Open Database) | XRD crystal-structure CIFs | CC0-1.0 |
| Materials Project | XRD structures | Materials Project Terms of Use |
| OpenSpecy | FTIR/Raman spectra | CC-BY-4.0 |
| ROD (Raman Open Database) | Raman/JCAMP-DX records | CC0-1.0 |

These records are fetched on demand; their own terms follow the data.
`sample_data/reference_library_seed.json` is a starter seed of
normalized reference entries that declares per-package license labels
from the same providers.

## Test fixtures

`tests/fixtures/reference_library_ingest/` contains small hand-written
fixture files (minimal CIF/JCAMP-style records and JSON records pointing
at `example.invalid`) authored for tests. They are not redistributed
provider data.

## Sample and test datasets

Files under `sample_data/` and `test_data/` fall into two groups:

- **Project-generated synthetic data.** Most `test_data/` files are
  produced by `generate_test_data.py` from literature-typical values
  (for example `dsc_PET_amorphous_10Kmin.csv`,
  `dsc_Nylon6_PA6_NETZSCH.txt`, `tga_polymers_comparison.xlsx`).
  `sample_data/dsc_polymer_melting.csv`,
  `sample_data/dsc_multirate_kissinger.csv`, and
  `sample_data/tga_calcium_oxalate.csv` are likewise synthetic fixtures
  authored for the project.

- **Externally sourced datasets (filename-indicated, unverified).** The
  following tracked files are named after public data repositories
  (Mendeley Data, Figshare, Zenodo), but this repository does not record
  their exact source records, authors, or license terms. No
  redistribution permission is asserted for the unverified files listed
  below until their source license is confirmed:

  - `sample_data/dta_tnaa_5c_mendeley.csv`,
    `sample_data/dta_tnaa_10c_mendeley.csv`
  - `test_data/dta_tnaa_2p5c_mendeley.csv`,
    `test_data/dta_tnaa_7p5c_mendeley.csv`
  - `sample_data/ftir_particleboard_50g_figshare.csv`,
    `test_data/ftir_particleboard_100g_figshare.csv`
  - `sample_data/raman_cnt_figshare.csv`,
    `test_data/raman_cnt_figshare_sparse.csv`
  - `sample_data/xrd_2024_0304_zenodo.csv`,
    `sample_data/xrd_2024_1613_zenodo.csv`
  - `test_data/xrd_2024_0303_zenodo.csv`,
    `test_data/xrd_2024_1784_zenodo.csv`,
    `test_data/xrd_2024_2097_zenodo.csv`

  These files are **not** relicensed under the AGPL. Their redistribution
  terms are unverified inside this repository and must be confirmed
  against the original source records; this is a current
  public-repository cleanup blocker and a release blocker. Their
  presence in Git history does not make them safely redistributable.
  Until then they are treated as third-party material retained for
  test/sample use, not as project-owned content.

- `test_data/CaCO3 decomposition.csv` is not produced by
  `generate_test_data.py`; its provenance is likewise unrecorded and is
  grouped with the unverified items above.

## Other third-party material

- `desktop/electron/assets/` — MaterialScope icon/logo artwork
  (project branding; see [TRADEMARKS.md](TRADEMARKS.md)).
- No vendored source code or bundled third-party binaries are tracked in
  the repository.
