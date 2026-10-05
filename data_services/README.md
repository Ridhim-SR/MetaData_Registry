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

- Pass an OpenMetadata client/token → all three stages run in one call.
- Omit it → stops after writing the curated CSV. Publish later with `openmetadata_publish.py`, no re-ingest needed.
- `batch.py` runs the same thing once per row of a manifest CSV, for many tables at once.
- Every run diffs the new source against the table's previous curated snapshot: additions/updates go through automatically; a column that existed before but is missing now raises an error unless you pass `allow_column_removal=True` — this catches a partial/incremental submission before it silently deletes a column from OpenMetadata. Answers not resubmitted in `business_metadata_file` carry forward instead of being blanked.

## Concepts

- **department → dataset → table → columns.** IDs are slugified and hierarchical: `pwd.vishwakarma.<table>`.
- **Departments are a controlled vocabulary** — must be registered before ingesting (`run()` refuses to auto-create one). Datasets/tables auto-create on first use.
- **Source formats**: `postgres_ddl` (raw column-list dump) or `csv` (arbitrary headers, normalized via alias map — only `name`/`data_type` required). A multi-table Field Dictionary CSV (one file, many tables) goes through `parsers/field_dictionary_ingest.py` instead, which splits it and calls `run()` once per table.
- **Dataset-level fields** — set once per dataset (not per column), optional kwargs on `run()`:

  | Field | Meaning |
  |---|---|
  | `category` | MDSF CAT-1/2/3/4 — the dataset's overall classification (separate from each column's own `classification`) |
  | `api_available` | Y/N — exposed via an API? |
  | `owner` | who's accountable for this dataset |
  | `frequency` | how often the data is refreshed/submitted |
  | `timeline` | the period/date range the dataset covers |
  | `dataset_description` | what the dataset is |

  A blank value carries forward whatever's already set, rather than wiping it — so only mention a field when you're setting or changing it. `category`/`dataset_description` also get pushed onto OpenMetadata's Database entity; the rest live in `_lookups/datasets.csv` only (see [Known limitations](#known-limitations)).

## Quickstart

```bash
# 1. Setup
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 2. Register a department (one-time)
DEPARTMENT_ID=pwd DEPARTMENT_NAME="Public Works Department" python3 -m src.schema_registry.registry.lookups

# 3. Get a JWT token (skip if not publishing yet)
#    OpenMetadata running? see infrastructure/openmetadata/README.md
#    Log into http://localhost:8585 -- email admin@open-metadata.org / password admin
#    Settings -> Bots -> ingestion-bot -> generate a token

# 4. Run the full pipeline: ingest -> curate -> publish
OPENMETADATA_JWT_TOKEN=<token> \
DEPARTMENT=pwd DATASET=vishwakarma TABLE_NAME=vishwakarma_T \
SOURCE_FILE=samples/pwd_vishwakarma_full_raw_columns.txt SOURCE_FORMAT=postgres_ddl \
python3 -m src.schema_registry.pipeline

# 5. Tests
python3 -m pytest tests/
```

**Config**: every CLI command above loads `.env` automatically (via
`python-dotenv`) — copy `.env.example` to `.env` and fill in
`OPENMETADATA_JWT_TOKEN` / Wasabi credentials there instead of exporting
them each time. `.env` is gitignored; never commit it.

**`vishwakarma_T` is a provisional table name**, not a confirmed one — PWD's
raw submission was only a column-list dump with no `CREATE TABLE <name>`,
so the real Postgres table/schema/database name is still unknown. Rename it
(re-run with a different `TABLE_NAME`, then delete the old one) once PWD
confirms the actual name.

## Command reference

| I want to... | Command |
|---|---|
| Register a department | `DEPARTMENT_ID=pwd DEPARTMENT_NAME="..." python3 -m src.schema_registry.registry.lookups` |
| Ingest + curate, storage only | `DEPARTMENT=pwd DATASET=<ds> TABLE_NAME=<t> SOURCE_FILE=<path> SOURCE_FORMAT=postgres_ddl python3 -m src.schema_registry.pipeline` |
| Ingest + curate + publish, one call | same, plus `OPENMETADATA_JWT_TOKEN=<token>` |
| Register + ingest together | add `DEPARTMENT_NAME="..."` to the ingest command |
| Set a dataset's fields (see [Concepts](#concepts)) | add any of `CATEGORY`/`API_AVAILABLE`/`OWNER`/`FREQUENCY`/`TIMELINE`/`DATASET_DESCRIPTION` to the ingest command |
| Batch many tables from a manifest CSV | `MANIFEST_FILE=manifest.csv python3 -m src.schema_registry.batch` (+ `OPENMETADATA_JWT_TOKEN` to publish each) |
| (Re-)publish without re-ingesting | `OPENMETADATA_JWT_TOKEN=<token> TABLE_ID=<id> python3 -m src.schema_registry.openmetadata.publish` |
| Run all tests | `python3 -m pytest tests/` |
| Run one test | `python3 -m pytest tests/test_pipeline.py -v` |
| Start OpenMetadata | `cd ../infrastructure/openmetadata && docker compose up -d` |

Same calls work from Python: `from src.schema_registry.pipeline import run`,
passing `openmetadata_client=` (from `openmetadata_publish.get_client(...)`)
to publish, or omitting it to skip.

## Storage layout

```
storage/
├── _lookups/{departments,datasets,tables}.csv   # registry + dataset-level fields
└── department/<dept>/<dataset>/<table>/
    ├── raw/schemas/<ts>.csv       # parsed structure only
    └── curated/schemas/<ts>.csv   # + business_description, tag, classification, glossary_term, active, validation_warning
```

Every run adds a new timestamped snapshot (version history); re-running
doesn't duplicate lookups. `publish_table()` always uses the **latest**
curated snapshot. Fill in `business_description`/`tag`/`glossary_term`
later via a Field Dictionary CSV passed as `business_metadata_file`.

**Backend**: everything goes through `ObjectStorage` (`src/storage/base.py`), swappable without touching `schema_registry/`:

- **`LocalObjectStorage`** — plain filesystem, default for local dev.
- **`S3ObjectStorage`** — Wasabi or any S3-compatible provider via `boto3`. `storage_from_env()` picks between the two: set `WASABI_BUCKET` (+ `WASABI_ENDPOINT_URL`/`WASABI_ACCESS_KEY_ID`/`WASABI_SECRET_ACCESS_KEY`, optionally `WASABI_PREFIX`/`WASABI_REGION`) in `.env` to switch to Wasabi; leave it unset to keep using Local.
- **Concurrency**: `filelock`, local-filesystem-only for both backends — fine for single-machine runs, not yet safe for multiple machines writing to the same bucket concurrently (would need conditional-PUT/ETag locking).

## Publish to OpenMetadata

`openmetadata_publish.py` pushes a table's latest curated snapshot as a
Table entity via the `openmetadata-ingestion` SDK (pin it to match the
running server's version). One function, `publish_table(client, storage,
table_id)`, does the Service → Database → Schema → Table create-or-update.

**Mapping**: department → service, dataset → database, `schema_name` →
schema, `table_name` → table. Columns come from the curated CSV's
`data_type` (unrecognized types fail loudly, never guessed). Each column's
`tag`/`classification`/`glossary_term` are pushed as TagLabels — `tag`
under a `FieldTag` Classification, `classification` (MDSF CAT-1/2/3) under
`DataSensitivity`, `glossary_term` under a `BusinessGlossary` — created on
first use, reused after. The dataset's own `category`/`dataset_description`
are pushed the same way, one level up, onto the Database entity.

**Re-running is safe** — the service and schema are reused; the database
and table are always create-or-update, so a later-confirmed `category`/
`dataset_description` actually lands, and removed columns are actually
removed in OpenMetadata too.

**Standalone republish** (no re-ingest):
```bash
OPENMETADATA_JWT_TOKEN=<token> OPENMETADATA_HOST_PORT=http://localhost:8585/api \
TABLE_ID=pwd.vishwakarma.vishwakarma_t python3 -m src.schema_registry.openmetadata.publish
```

**One-time per OpenMetadata instance**: `api_available`/`owner`/`frequency`/`timeline` ride on OpenMetadata Custom Properties, which must be registered before they'll show up:
```bash
OPENMETADATA_JWT_TOKEN=<token> python3 -m src.schema_registry.openmetadata.setup_custom_properties
```

## Tests

```bash
python3 -m pytest tests/
```
Covers parsers, curation/tagging, lookup dedup, concurrency, and the full pipeline/batch/publish flow end to end.

## A new department's data fails the pipeline — what to do

It's built to fail loudly, never guess — the error names the exact bad value. Match it to one of these; don't bypass it:

| Error says... | Means | Fix |
|---|---|---|
| `Unknown department` | Not registered | `lookups.register_department(...)`, rerun — no code change |
| Parser can't make sense of the file at all | A genuinely new raw file *shape* | Write `parsers/<name>_parser.py` producing the same column-dict shape (`name`/`data_type`/`length`/`scale`/`nullable`/`default`), add a test against the real sample file, wire it in (see `field_dictionary_parser.py` for a template) |
| `Unrecognized Format value`, `missing required field`, or similar, on a *known* format | One value the parser's rule table doesn't cover yet | Small targeted addition — one line in `FORMAT_TYPE_RULES`, the CSV alias map, or the DDL regex. Don't rewrite the parser |
| `No OpenMetadata mapping for Postgres type` | A type never seen before | Add it to `KNOWN_POSTGRES_TYPES` (curate.py) and `_TYPE_MAP` (openmetadata_publish.py) |
| `this run is missing N column(s)...` | Column-removal guard | Real full resubmission → `allow_column_removal=True`. Accidental partial file → fix the source file instead, the guard just did its job |
| OpenMetadata/Wasabi error | Could be code or credentials/network | Verify independently (curl, AWS CLI) before touching code |

Then: add a test that reproduces it, confirm the full suite passes, and verify the actual published result via the OpenMetadata API — not just "no exception was thrown."

## Known limitations

- `source_format="csv"` won't guess semantically-inverted columns (e.g. `Required` vs `Nullable`) — add a mapping in `parsers/csv_schema_parser.py` if needed.
- No mode is tracked explicitly (Initial Load/Append/Update/Full Refresh) — `run()` infers safety from a diff against the previous snapshot rather than the caller declaring which one this is, and nothing persists *which* decision was made for audit purposes.
- `publish_table()` ignores the curated `active` flag — a column marked inactive still gets published like any other.
- Renaming a column looks like a delete + an add to the diff — it requires `allow_column_removal=True`, and the old name's business metadata won't carry over (matching is by exact column name only).
- OpenMetadata's PUT merges tags/extension rather than replacing them by default — `_ensure_database()` works around this with an explicit JSON-Patch replace so a cleared `category`/custom property actually clears; column-level tags on the Table entity don't have this fix yet, so clearing a stale column `tag`/`classification` still needs a manual JSON-Patch `remove`.

## Just run it

Every option lives in `.env` — copy `.env.example`, fill it in once, then
the command itself never changes:

```bash
cd /Users/adityaoffice/Desktop/UP_SDA/MetaData_Registry/data_services
source .venv/bin/activate
python3 -m src.schema_registry.pipeline
```

`.env.example` documents every key, required and optional, with what each
one does — nothing hidden in `pipeline.py` that you'd have to go read
source code to discover:

| Key | Required? | Notes |
|---|---|---|
| `OPENMETADATA_JWT_TOKEN` | yes | Settings → Bots → ingestion-bot in the OpenMetadata UI. An admin session token expires in ~1hr — refresh it if a run fails with 401 (see `.env`'s comment for the exact `curl`) |
| `DEPARTMENT` | yes | must already be registered (see Quickstart) |
| `DATASET` | yes | auto-creates on first use |
| `TABLE_NAME` | yes | |
| `SOURCE_FILE` | yes | |
| `SOURCE_FORMAT` | yes | `postgres_ddl` or `csv` |
| `WASABI_BUCKET` | no | leave blank for local storage; fill in once Wasabi is confirmed clean (see [Storage layout](#storage-layout)) |
| `CATEGORY`/`API_AVAILABLE`/`OWNER`/`FREQUENCY`/`TIMELINE`/`DATASET_DESCRIPTION` | no | dataset-level fields (see [Concepts](#concepts)) — type a real value only once you have it; blank/omitted carries forward whatever was last set, so these rarely need touching after the first time |

To run a different table, just edit `.env` and run the same command again.
