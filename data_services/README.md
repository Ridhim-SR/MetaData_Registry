# Schema Registry (Department Metadata Cataloging)

Parses a department's raw column-definition submission (Postgres DDL dump
or CSV), validates/standardizes it, auto-tags sensitive fields, saves raw +
curated versions to object storage, and publishes the curated result into
OpenMetadata as a Table entity.

Code: `src/schema_registry/`, `src/storage/`.

## The pipeline

One `run()` call, three stages:

```
raw file --parse--> raw columns --curate_schema()--> curated columns --publish_table()--> OpenMetadata
             |                          |                                    |
       raw/schemas/<ts>.csv     curated/schemas/<ts>.csv          Service->Database->Schema->Table
```

- Pass an OpenMetadata client/token → all three stages run in one call (normal path).
- Omit it → stops after writing the curated CSV. Publish later with `openmetadata_publish.py` (below), no re-ingest needed.
- `batch.py` runs the same thing once per row of a manifest CSV, for many tables at once.
- Every run diffs the new source against the table's previous curated snapshot: additions/updates go through automatically; a column that existed before but is missing now raises an error (naming it) unless you pass `allow_column_removal=True` — this catches a partial/incremental submission before it silently deletes a column from OpenMetadata. Answers not resubmitted in `business_metadata_file` carry forward from the previous run instead of being blanked.

## Quickstart

```bash
# 1. Setup
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 2. Register a department (one-time)
DEPARTMENT_ID=pwd DEPARTMENT_NAME="Public Works Department" python3 -m src.schema_registry.lookups

# 3. Get a JWT token (skip if not publishing yet)
#    OpenMetadata running? see infrastructure/openmetadata/README.md
#    Log into http://localhost:8585 -- email admin@open-metadata.org / password admin
#    Settings -> Bots -> ingestion-bot -> generate a token

# 4. Run the full pipeline: ingest -> curate -> publish
OPENMETADATA_JWT_TOKEN=<token> \
DEPARTMENT=pwd DATASET=vishwakarma TABLE_NAME=TBD_confirm_with_pwd \
SOURCE_FILE=samples/pwd_vishwakarma_full_raw_columns.txt SOURCE_FORMAT=postgres_ddl \
python3 -m src.schema_registry.pipeline

# 5. Tests
python3 -m pytest tests/
```

## Command reference

| I want to... | Command |
|---|---|
| Register a department | `DEPARTMENT_ID=pwd DEPARTMENT_NAME="..." python3 -m src.schema_registry.lookups` |
| Ingest + curate, storage only | `DEPARTMENT=pwd DATASET=<ds> TABLE_NAME=<t> SOURCE_FILE=<path> SOURCE_FORMAT=postgres_ddl python3 -m src.schema_registry.pipeline` |
| Ingest + curate + publish, one call | same, plus `OPENMETADATA_JWT_TOKEN=<token>` |
| Register + ingest together | add `DEPARTMENT_NAME="..."` to the ingest command |
| Batch many tables from a manifest CSV | `MANIFEST_FILE=manifest.csv python3 -m src.schema_registry.batch` (+ `OPENMETADATA_JWT_TOKEN` to publish each) |
| (Re-)publish without re-ingesting | `OPENMETADATA_JWT_TOKEN=<token> TABLE_ID=<id> python3 -m src.schema_registry.openmetadata_publish` |
| Run all tests | `python3 -m pytest tests/` |
| Run one test | `python3 -m pytest tests/test_pipeline.py -v` |
| Start OpenMetadata | `cd ../infrastructure/openmetadata && docker compose up -d` |

Same calls work from Python: `from src.schema_registry.pipeline import run`,
passing `openmetadata_client=` (from `openmetadata_publish.get_client(...)`)
to publish, or omitting it to skip.

## Concepts

- **department → dataset → table**, e.g. `pwd` → `vishwakarma` → a table. IDs are slugified and hierarchical: `pwd.vishwakarma.<table>`.
- **Departments are a controlled vocabulary** — must be registered before ingesting (`run()` refuses to auto-create one). Datasets/tables auto-create on first use.
- **Source formats**: `postgres_ddl` (raw column-list dump) or `csv` (arbitrary headers, normalized via alias map — only `name`/`data_type` required).

## Storage layout

```
storage/
├── _lookups/{departments,datasets,tables}.csv   # registry + dataset-level governance fields (owner, fiduciary, retention, ...)
└── department/<dept>/<dataset>/<table>/
    ├── raw/schemas/<ts>.csv       # parsed structure only
    └── curated/schemas/<ts>.csv   # + business_description, tag, glossary_term, active, validation_warning
```

Every run adds a new timestamped snapshot (version history); re-running
doesn't duplicate lookups. `publish_table()` always uses the **latest**
curated snapshot. Fill in `business_description`/`tag`/`glossary_term`
later via a Field Dictionary CSV passed as `business_metadata_file`.

Dataset-level governance fields (`owner`, `fiduciary`, `processor`,
`risk_classification`, `retention_policy`, `lineage`) are optional kwargs
on `run()`, stored once per dataset — needed for OpenMetadata's Owner
field and custom properties.

## Object storage backend

Everything goes through `ObjectStorage` (`src/storage/base.py`) — the
backend is swappable without touching `schema_registry/`.

- **Now**: `LocalObjectStorage` — plain filesystem.
- **Target**: an S3-compatible backend (Wasabi, etc.) implementing the same
  4 methods (`write_csv`, `read_csv`, `exists`, `list`) + `lock_path`.
  Concurrency uses `filelock` locally; S3 will need conditional-PUT/ETag
  instead.

## Publish to OpenMetadata

`openmetadata_publish.py` pushes a table's latest curated snapshot as a
Table entity via the `openmetadata-ingestion` SDK (pin it to match the
running server's version). One function, `publish_table(client, storage,
table_id)`, does the Service → Database → Schema → Table create-or-update —
`pipeline.run()`/`batch.run_batch()` call it when given a client; the CLI
below calls it directly.

**Mapping**: department → service, dataset → database, `schema_name` →
schema, `table_name` → table. Columns from the curated CSV's `data_type`
(unrecognized types fail loudly, never guessed).

**Re-running is safe** — existing services/databases/schemas are reused;
the table is a create-or-update, so removed columns are actually removed
in OpenMetadata too, not left behind.

**Standalone republish** (no re-ingest):
```bash
OPENMETADATA_JWT_TOKEN=<token> OPENMETADATA_HOST_PORT=http://localhost:8585/api \
TABLE_ID=pwd.vishwakarma.tbd_confirm_with_pwd python3 -m src.schema_registry.openmetadata_publish
```

## Tests

```bash
python3 -m pytest tests/
```
Covers parsers, curation/tagging, lookup dedup, concurrency, and the full pipeline/batch/publish flow end to end.

## Known limitations

- `source_format="csv"` won't guess semantically-inverted columns (e.g. `Required` vs `Nullable`) — add a mapping in `csv_schema_parser.py` if needed.
- No mode is tracked explicitly (Initial Load/Append/Update/Full Refresh) — `run()` infers safety from a diff against the previous snapshot (see [The pipeline](#the-pipeline)) rather than the caller declaring which one this is, and nothing persists *which* decision was made for audit purposes.
- `publish_table()` ignores the curated `active` flag — a column marked inactive still gets published like any other.
- Renaming a column looks like a delete + an add to the diff — it requires `allow_column_removal=True`, and the old name's business metadata won't carry over to the new name (matching is by exact column name only).

---

# Appendix: CSV → OpenMetadata Pipeline

**Backend team's, not this project's scope** — kept for reference.
Watermark-based CSV extract/clean/push into OpenMetadata. Requires Docker.
Compose file: `docker-compose.yml` (default name, no `-f` needed).

| Service | Purpose | Port |
|---|---|---|
| mysql | OpenMetadata's DB | 3306 |
| elasticsearch | Search index | 9200 |
| openmetadata | Server / UI | 8585 |
| postgres | Sample source DB | 5432 |
| ingestion | Airflow | 8080 |
| csv-pipeline | ETL | — |

**Credentials** (local dev only): MySQL root `openmetadata`; MySQL app user
`openmetadata_user`/`openmetadata_password`; Postgres `postgres`/`postgres`;
OpenMetadata UI `admin@open-metadata.org`/`admin` (email, not username).
JWT token: **Settings → Bots → ingestion-bot** after first login, put in
`.env` as `OPENMETADATA_JWT_TOKEN=...`.

```bash
docker compose up -d                  # mysql, elasticsearch, openmetadata, postgres, ingestion
docker compose logs -f openmetadata   # wait for it to be ready

# then: log in, generate a token, put it in .env, and:
docker compose --profile pipeline run --rm csv-pipeline   # one-off run
docker compose --profile pipeline up -d --build csv-pipeline  # or as a persistent service

docker compose down       # stop, keep data
docker compose down -v    # stop, wipe volumes -- careful
```

`csv-pipeline` env vars: `SOURCE_FILE`, `OPENMETADATA_HOST_PORT`,
`OPENMETADATA_JWT_TOKEN`, `OM_SERVICE_NAME`/`OM_DATABASE_NAME`/
`OM_SCHEMA_NAME`/`OM_TABLE_NAME`.

---

## Run

```bash
cd ../infrastructure/openmetadata && docker compose up -d
cd ../../data_services && source .venv/bin/activate
OPENMETADATA_JWT_TOKEN=<token> \
DEPARTMENT=pwd DATASET=vishwakarma TABLE_NAME=TBD_confirm_with_pwd \
SOURCE_FILE=samples/pwd_vishwakarma_full_raw_columns.txt SOURCE_FORMAT=postgres_ddl \
python3 -m src.schema_registry.pipeline
```
