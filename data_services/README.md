# Schema Registry (Department Metadata Cataloging)

Takes a department's raw column-definition submission (a Postgres DDL dump,
or a CSV with arbitrary headers), validates and standardizes it, auto-tags
sensitive fields, and saves both the raw and curated version to
**S3-compatible object storage** (Wasabi, etc.). Used to build the
department schema catalog for the State Data Authority submission (Field
Dictionary style output). Publishing the curated data into OpenMetadata is
a separate, later step owned by the backend team — out of scope here.

Code lives in `src/schema_registry/` and `src/storage/`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Concepts

- **department / dataset / table**: a hierarchy, e.g. PWD (department) →
  VISHWAKARMA (dataset) → its underlying Postgres table.
- **Departments are a controlled vocabulary.** They must be explicitly
  registered before you can ingest data for them — `run()` refuses to
  auto-create one from arbitrary text, because normalizing spelling
  (`slugify`) can't tell that "Public Works Department" and "PWD Dept" are
  the same department. Datasets and tables *are* auto-created on first use.
- **IDs** are hierarchical and slugified (lowercased, non-alphanumeric →
  `_`): `pwd` → `pwd.vishwakarma` → `pwd.vishwakarma.<table>`.
- **Source formats**: `postgres_ddl` (a raw Postgres column-list dump) or
  `csv` (any header names — auto-normalized via an alias map; only `name`
  and `data_type` are required, unrecognized required fields raise loudly
  instead of guessing).

## How to run

**1. Register a department** (one-time, before its first ingestion):
```bash
DEPARTMENT_ID=pwd DEPARTMENT_NAME="Public Works Department" python3 -m src.schema_registry.lookups
```

**2. Ingest one table** — CLI (env-var driven):
```bash
DEPARTMENT=pwd DATASET=vishwakarma TABLE_NAME=TBD_confirm_with_pwd \
SOURCE_FILE=samples/pwd_vishwakarma_full_raw_columns.txt SOURCE_FORMAT=postgres_ddl \
python3 -m src.schema_registry.pipeline
```
or in one command (registers + runs together via `DEPARTMENT_NAME`):
```bash
DEPARTMENT=pwd DEPARTMENT_NAME="Public Works Department" DATASET=vishwakarma TABLE_NAME=TBD_confirm_with_pwd \
SOURCE_FILE=samples/pwd_vishwakarma_full_raw_columns.txt SOURCE_FORMAT=postgres_ddl \
python3 -m src.schema_registry.pipeline
```
or from Python directly:
```python
from src.schema_registry.pipeline import run
from src.storage.local import LocalObjectStorage

run(
    department="pwd", dataset="vishwakarma", table_name="TBD_confirm_with_pwd",
    source_file="samples/pwd_vishwakarma_full_raw_columns.txt",
    storage=LocalObjectStorage("storage"), source_format="postgres_ddl",
)
```

**3. Ingest many tables/departments at once** — write a manifest CSV:
```csv
department,department_name,dataset,table_name,source_file,source_format
pwd,Public Works Department,vishwakarma,TBD_confirm_with_pwd,samples/pwd_vishwakarma_full_raw_columns.txt,postgres_ddl
irrigation,Irrigation Department,scheme_tracker,schemes,submissions/irrigation.csv,csv
```
(`department_name` is optional — only needed the first time a department appears; `schema_name` and `business_metadata_file` are also optional per row.)
```bash
MANIFEST_FILE=manifest.csv python3 -m src.schema_registry.batch
```
One bad row logs an error and fails gracefully — it doesn't block the rest of the batch.

## Output — object storage layout

```
storage/
├── _lookups/
│   ├── departments.csv   # department_id, department_name
│   ├── datasets.csv      # dataset_id, department_id, dataset_name
│   └── tables.csv        # table_id, dataset_id, table_name, schema_name
└── department/<dept_id>/<dataset>/<table>/
    ├── raw/schemas/<timestamp>.csv       # parsed structure only
    └── curated/schemas/<timestamp>.csv   # + business_description, tag, glossary_term, active, validation_warning
```

Every run adds a new timestamped snapshot rather than overwriting the last one (version history). Re-running for an already-registered dataset/table is safe — lookups don't duplicate.

To later fill in `business_description`/`tag`/`glossary_term` once a department answers your Field Dictionary questions, export their answers to a CSV (`name, business_description, tag, glossary_term, active`) and pass it as `business_metadata_file`.

## Object storage backend

All reads/writes go through the `ObjectStorage` interface (`src/storage/base.py`), not directly through file APIs — so the actual backend is swappable without touching `schema_registry/` at all.

- **Now**: `LocalObjectStorage` (`src/storage/local.py`) — plain filesystem, rooted at whatever path you pass (`storage/` by default). Used for local development while the folder/lookup structure was being worked out.
- **Target**: an S3-compatible backend (Wasabi, etc.) implementing the same four methods — `write_csv`, `read_csv`, `exists`, `list`, plus `lock_path` for concurrency safety. Swapping in `S3ObjectStorage(bucket=..., prefix=...)` in place of `LocalObjectStorage(...)` is the only change needed anywhere in `pipeline.py`/`batch.py`/`lookups.py` — none of them know or care which backend they're talking to.
- Concurrency: local backend uses `filelock` (file-based locks) to make concurrent department/dataset/table registrations safe. An S3 backend will need a different mechanism (e.g. conditional PUT / ETag checks), not file locks — this is the one piece of `lookups._upsert` that will need backend-specific handling once S3 is wired in.

## Tests

```bash
python3 -m pytest tests/
```

Covers the DDL/CSV parsers, curation/tagging rules, lookup dedup behavior, concurrent-write safety, and the full pipeline/batch flow end to end.

## Known limitations

- `lookups._upsert` is insert-if-missing, not a true upsert — re-registering an existing id with different field values doesn't update it.
- `source_format="csv"` deliberately does not guess on semantically-inverted columns like `Required` (the opposite of `Nullable`) — add an explicit mapping in `csv_schema_parser.py` if a department's CSV needs it.

---

# CSV → OpenMetadata Pipeline

**Not part of this project's scope** — owned by the backend team, kept here
for reference only. Extracts new rows from a CSV (watermark-based),
cleans/dedupes them, and pushes them into OpenMetadata as table metadata +
sample data. Requires Docker.

## Services

| Service      | Purpose                          | Port |
|--------------|-----------------------------------|------|
| mysql        | OpenMetadata's backend DB         | 3306 |
| elasticsearch| OpenMetadata's search index       | 9200 |
| openmetadata | OpenMetadata server / UI          | 8585 |
| postgres     | Sample data source DB             | 5432 |
| ingestion    | Airflow (OpenMetadata ingestion)  | 8080 |
| csv-pipeline | extract/transform/load            | — |

## Credentials (local dev only — change before any real deployment)

| What                     | Value                          |
|---------------------------|--------------------------------|
| MySQL root password       | `openmetadata`                 |
| MySQL app user            | `openmetadata_user` / `openmetadata_password` |
| Postgres user              | `postgres` / `postgres`        |
| OpenMetadata UI login      | `admin` / `admin`              |
| OpenMetadata JWT token     | Generate after first login: **Settings → Bots → ingestion-bot** (or a personal access token), then put it in `.env` as `OPENMETADATA_JWT_TOKEN=...` |

`.env` (create this file, don't commit it):
```
OPENMETADATA_JWT_TOKEN=<paste token here>
```

## Run everything

`csv-pipeline` is behind a `pipeline` profile, so it does **not** start
automatically — it needs a JWT token that only exists after you've logged
into the OpenMetadata UI once, so it can't come up at the same time as
everything else.

```bash
docker compose up -d
```

This starts mysql, elasticsearch, openmetadata, postgres, and ingestion only.

Check logs / wait for it to be ready:
```bash
docker compose logs -f openmetadata
```

Then:
1. Open http://localhost:8585, log in as `admin` / `admin`
2. **Settings → Bots → ingestion-bot** → generate a token
3. Put it in `.env` as `OPENMETADATA_JWT_TOKEN=...`

## Run the pipeline manually

Only after the token is in `.env`:

```bash
docker compose --profile pipeline up -d --build csv-pipeline   # start/restart the service
docker compose --profile pipeline run --rm csv-pipeline        # one-off run, no persistent container
```

Re-run either command any time you want to process new rows from the
source CSV (the watermark ensures already-processed rows are skipped).

The watermark (last processed `year`) is stored in the `pipeline_state`
volume, so re-runs only process new rows.

## Filename note

Your compose file is named `docker_compose.yml` (underscore), not the
default `docker-compose.yml`/`compose.yaml` Docker looks for automatically.
Either rename it, or pass `-f` on every command:
```bash
docker compose -f docker_compose.yml up -d
```
(examples below assume you've renamed it to the default; add `-f docker_compose.yml` if not)

## Stop everything

```bash
docker compose down          # keeps data
docker compose down -v       # wipes all volumes (mysql/ES/postgres/watermark) — careful
```

## Config (env vars on `csv-pipeline`)

| Var | Meaning |
|---|---|
| `SOURCE_FILE` | Path to source CSV inside the container |
| `OPENMETADATA_HOST_PORT` | `http://openmetadata:8585/api` |
| `OPENMETADATA_JWT_TOKEN` | From `.env` |
| `OM_SERVICE_NAME` / `OM_DATABASE_NAME` / `OM_SCHEMA_NAME` / `OM_TABLE_NAME` | Where the table is registered in OpenMetadata's catalog |
