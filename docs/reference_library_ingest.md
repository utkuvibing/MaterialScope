# Reference Library Ingest

Local ingest tooling writes provider-normalized packages under `build/reference_library_ingest/<provider>/<package_id>/` and then turns those packages into the runtime mirror format under `build/reference_library_mirror/`.

## Install

```bash
python -m pip install -r requirements.txt
```

`pymatgen` is only needed for COD and Materials Project XRD generation. `mp-api` is only needed when you fetch Materials Project records live. `pyreadr` and `rdata` are only needed when you ingest raw OpenSpecy bundle formats.

## Provider CLIs

### COD

Recorded/local fixtures:

```bash
python tools/ingest_cod.py \
  --manifest tests/fixtures/reference_library_ingest/cod_records.json \
  --output-root build/reference_library_ingest \
  --generated-at 2026-03-14T00:00:00Z \
  --provider-dataset-version 2026.03.fixture
```

Live by COD id:

```bash
python tools/ingest_cod.py --source-id 1001 --source-id 1002
```

### Materials Project

Recorded/local fixtures:

```bash
python tools/ingest_materials_project.py \
  --input-json tests/fixtures/reference_library_ingest/materials_project_records.json \
  --output-root build/reference_library_ingest \
  --generated-at 2026-03-14T00:00:00Z \
  --provider-dataset-version 2026.03.fixture
```

Live by material id:

```bash
set MP_API_KEY=...
python tools/ingest_materials_project.py --material-id mp-149 --material-id mp-22862
```

### OpenSpecy

Recorded/local JSON export:

```bash
python tools/ingest_openspecy.py \
  --input-json tests/fixtures/reference_library_ingest/openspecy/records.json \
  --output-root build/reference_library_ingest
```

Raw RDS bundle:

```bash
python tools/ingest_openspecy.py --input-rds path/to/openspecy_library.rds
```

### ROD

Recorded/local fixtures:

```bash
python tools/ingest_rod.py \
  --manifest tests/fixtures/reference_library_ingest/rod_records.json \
  --output-root build/reference_library_ingest
```

Live by ROD id:

```bash
python tools/ingest_rod.py --source-id 2001 --source-id 2002
```

## Build Mirror

Normalized packages are now the primary input:

```bash
python tools/build_reference_library_mirror.py \
  --normalized-root build/reference_library_ingest \
  --output build/reference_library_mirror
```

The legacy seed path still works when the normalized root is empty:

```bash
python tools/build_reference_library_mirror.py \
  --source sample_data/reference_library_seed.json \
  --output build/reference_library_mirror
```

## Test Fixtures

`tests/test_reference_library_ingest.py` uses tiny recorded CIF, JSON, and JCAMP fixtures under `tests/fixtures/reference_library_ingest/`. The tests do not call live network endpoints.
