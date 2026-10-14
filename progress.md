# Project Progress: Agriculture Department Datasets

## Status: agri_dept — Complete (Storage + OpenMetadata, local **and** global migrated to `agri_dept` 2026-10-13); rural_development_department — local only; **local OpenMetadata reduced to just these two (13 tables) and local storage moved to a local MinIO, both local-only by enforcement (`LOCAL_ONLY=1`), on 2026-10-13** — **NEXT (2026-10-14, first task): `git pull`, merge `origin/main` (now `54679a2`, PR #23) locally, raise the PR `department/agriculture_department` → `main` — merge playbook in Future Work**

### Department
- **Department**: Agriculture Department — catalog id **`agri_dept`**
  (renamed from `agriculture_department` on 2026-10-09, see that section;
  display name unchanged)
- **Branch**: `department/agriculture_department`
  (all 3 datasets live on this one branch)
- **Also on this branch**: Rural Development Department — catalog id
  **`rural_development_department`**, dataset `mgnrega` (started
  2026-10-12, local-only; see that section)

---

### Merged origin/main (2026-10-13) + local storage now MinIO
- Merged `origin/main` (PRs #17-#22: confirm-before-changes, department
  displayName, Explore/TablePage work, connection-pool + user caching)
  into this branch; 2 conflicts resolved:
  - `catalog.yaml` kept ours (main never had the agri/mgnrega work;
    `pwd` stays commented out)
  - `registry.py /registry/tables/{id}`: main's anonymous-401 +
    `data_classification` merged with our `_dataset_info()` (OM custom
    properties) -- kept inside the client context so the OM lookup still
    has a client
- **Service display name**: `agri_dept` now shows **Agriculture Department**
  in OpenMetadata (local + global, JSON-Patch on `displayName` only --
  name/FQN/tags/tables untouched). Main's PR #21 does the same thing from
  `departments.csv` on every publish, so it stays in step from now on.
- **Local Wasabi stand-in = MinIO** (`infrastructure/minio/`): main's config
  routes feature branches to S3 (no local-filesystem storage), so
  `LOCAL_WASABI_*` in `data_services/.env` now point at a local MinIO
  container (`bitnamilegacy/minio`; Docker Hub's `minio/minio` was removed).
  The real boto3/S3 code path is exercised locally; validated with a
  write/read/lock/CSV round-trip. Buckets `sda-local`, `sda-local-backup`
  (`init_buckets.py`); the 736 existing storage files were copied in
  (`migrate_local_storage.py`), local `storage/` kept as a restore point.
  `sync --dry-run` is clean through MinIO (0 failed).
- **Tests**: 466 data_services + 47 apps/api passing. `test_batch` CLI tests
  now pass `--yes` (main's confirm prompt) and run against MinIO under a
  throwaway `WASABI_PREFIX`, so they can't touch real `local/` state; they
  also no longer publish `pwd.vishwakarma.t1` to live OM (empty token
  survives `load_env()`'s setdefault).
- `.gitignore`: MinIO data dirs + `*.tar` image exports can never be
  committed (the bucket holds registry state).
- **Where global Wasabi creds go**: `data_services/.env` section 3
  (`WASABI_BUCKET`/`WASABI_REGION`/`WASABI_ENDPOINT_URL`/
  `WASABI_ACCESS_KEY_ID`/`WASABI_SECRET_ACCESS_KEY`) -- read only when the
  branch is `main` (development) or `production`; feature branches refuse
  them by design.
- **Company Wasabi checked read-only (2026-10-13); upload paused at a safe
  point, zero writes**: the section-3 credentials were verified valid
  against `up-sda-schema-registry` (us-west-1). The bucket holds 8
  objects, **all PWD's** (the other team): the 3 shared `_lookups/*.csv`
  (with PWD's registry rows), 4 `department/pwd/...` snapshots, 1
  `inputs/pwd/...` file; no agri/mgnrega keys exist there. ETag/size
  snapshot saved so any later change is provable. A prepared one-off
  script -- `infrastructure/wasabi/push_agri_mgnrega.py`, dry-run by
  default -- would upload only our 4 namespaces (`dev/inputs/agri_dept/`,
  `dev/department/agri_dept/`, `dev/inputs/rural_development_department/`,
  `dev/department/rural_development_department/`), refuse any key that
  already exists, never touch `dev/_lookups/*` (overwriting those shared
  CSVs would wipe the other team's registry rows -- the server's own sync
  adds our rows later, merging them the way the code always has), and
  prove afterwards that every pre-existing object is unchanged. It was
  **not run** -- stopped at the user's request; next step is dry-run,
  review, then `--apply` (see Future Work). Also found: the backup bucket
  `up-sda-schema-registry-backup` really lives in `us-west-1`, not the
  `eu-central-1` of the old `.env.example` default -- fix
  `WASABI_BACKUP_REGION` server-side before any backup copy, or it fails
  with `AuthorizationHeaderMalformed`.
- **"Local stays local" is now enforced, not just promised**: new
  `LOCAL_ONLY=1` in `.env` (documented in `.env.example` 3b) makes
  `load_env()` refuse, in the local environment, any storage endpoint or
  OpenMetadata address that isn't this machine
  (localhost/127.0.0.1/host.docker.internal) -- a `PermissionError`
  before a single byte is written. Opt-in flag, so other devs' personal
  Wasabi setups (README 3b) keep working; on this machine it pins local
  storage to MinIO `localhost:9000` + local OM `localhost:8585`.
  4 new tests; data_services suite 470 passing.
- **Docs updated**: new `infrastructure/minio/README.md` (start/stop,
  ports, buckets, `.env` wiring, git-ignore rule, local-only guarantee);
  `data_services/README.md` environments/rules/troubleshooting/reference
  sections updated for MinIO + `LOCAL_ONLY`; root `README.md` repo-layout
  table fixed (`data_services` no longer "not used yet"; minio row added);
  the prepared push script committed under `infrastructure/wasabi/`.

### Merged origin/main (2026-10-05)
- Merged `origin/main` (PR #11, 23 commits) into this branch; 5 conflicts resolved
- **Classification decision**: field-level `classification` keeps this branch's
  MDSF levels (`Public`/`Internal`/`Confidential`/`Restricted`/`PII`/`Financial`/`Health`,
  default `Internal`), **not** main's `CAT-3`-or-blank `auto_classification()` —
  main's PII patterns (aadhaar, voter id, driving licence, vehicle registration)
  were folded into `AUTO_CLASSIFICATION_RULES` instead. Dataset-level `category`
  (CAT-1/2/3) still publishes as `DataSensitivity.*`.
- Adopted main's restructure: `lookups.py` → `registry/lookups.py`,
  `openmetadata_publish.py` → `openmetadata/publish.py`, parsers moved under
  `parsers/`. From our old module, `bytea` in `_TYPE_MAP` and the mutually
  exclusive `MDSF` classification (all 7 level tags) were ported into
  `openmetadata/publish.py`.
- Main's own doc comments still say `openmetadata_publish.py` (README,
  `storage/__init__.py`, `tests/test_pipeline.py`) — stale on main too.

---

### Dataset 1: Distribution Record Dataset
- **Dataset**: DISTRIBUTION RECORD DATASET (distribution_record_dataset)

#### Tables Published (5/5)

| Table | Columns | OpenMetadata FQN |
|-------|---------|------------------|
| crop_sales | 53 | agri_dept.distribution_record_dataset.public.crop_sales |
| current_booking | 55 | agri_dept.distribution_record_dataset.public.current_booking |
| current_booking_farmer_details | 19 | agri_dept.distribution_record_dataset.public.current_booking_farmer_details |
| online_booking | 13 | agri_dept.distribution_record_dataset.public.online_booking |
| online_booking_details | 19 | agri_dept.distribution_record_dataset.public.online_booking_details |

#### Source Files Added
- data_services/source/distribution_records/*.csv (5 files)
- data_services/configs/distribution_records_manifest.csv

#### Preprocessing (new, `src/schema_registry/parsers/dept/Agriculture/`)
Multi-table CSV sources are split/cleaned into per-table column-definition
files before the batch run:
```bash
python -m data_services.src.schema_registry.parsers.dept.Agriculture.preprocess_dataset --dataset <slug> --dry-run
python -m data_services.src.schema_registry.parsers.dept.Agriculture.preprocess_dataset --all
```
- `parsers/dept/Agriculture/preprocessors/base.py` — shared interface
- `parsers/dept/Agriculture/preprocessors/multi_table_csv.py` — header/section splitting
- `parsers/dept/Agriculture/preprocessors/registry.py` — per-dataset config + manifest generation
- Other departments get their own `parsers/dept/<Department>/` package
- `--all` covers **all 3 datasets** (distribution's manifest keeps its
  historical name `configs/distribution_records_manifest.csv` via the
  config's `manifest_file` key)
- A dataset's `business_metadata_file` config value is written into every
  row of its manifest (extra column), which `batch.py` passes to
  `pipeline.run()` — this is what keeps the field dictionary (descriptions /
  tags / MDSF classification) wired up on each ingest
- Regression tests: `data_services/tests/test_dept_agriculture_preprocess.py`
  (manifests regenerated by `--all` must stay byte-identical to committed)

---

### Dataset 2: Farmer Registration Master Dataset
- **Dataset**: FARMER REGISTRATION MASTER DATASET (farmer_registration_master_dataset)

#### Tables Published (1/1)

| Table | Columns | OpenMetadata FQN |
|-------|---------|------------------|
| farmers | 53 | agri_dept.farmer_registration_master_dataset.public.farmers |

#### Source Files Added
- data_services/source/farmer_registration/farmers.csv
- data_services/configs/farmer_registration_master_dataset_manifest.csv

---

### Dataset 3: Scheme Physical Financial Progress Dataset
- **Dataset**: SCHEME PHYSICAL FINANCIAL PROGRESS DATASET (scheme_physical_financial_progress_dataset)

#### Tables Published (3/3)

| Table | Columns | OpenMetadata FQN |
|-------|---------|------------------|
| target_allocation_v2 | 22 | agri_dept.scheme_physical_financial_progress_dataset.public.target_allocation_v2 |
| financial_budget_allocation | 18 | agri_dept.scheme_physical_financial_progress_dataset.public.financial_budget_allocation |
| grant_wise_bill_generation | 36 | agri_dept.scheme_physical_financial_progress_dataset.public.grant_wise_bill_generation |

#### Source Files Added
- data_services/source/scheme_progress/target_allocation_v2.csv
- data_services/source/scheme_progress/financial_budget_allocation.csv
- data_services/source/scheme_progress/grant_wise_bill_generation.csv
- data_services/configs/scheme_physical_financial_progress_dataset_manifest.csv

---

### Pipeline Commands

Register department:
```bash
DEPARTMENT_ID=agri_dept DEPARTMENT_NAME="Agriculture Department" python -m src.schema_registry.registry.lookups
```

Batch ingest (storage):
```bash
MANIFEST_FILE=configs/distribution_records_manifest.csv python -m src.schema_registry.batch
MANIFEST_FILE=configs/farmer_registration_master_dataset_manifest.csv python -m src.schema_registry.batch
MANIFEST_FILE=configs/scheme_physical_financial_progress_dataset_manifest.csv python -m src.schema_registry.batch
```

Batch ingest + OpenMetadata:
```bash
OPENMETADATA_JWT_TOKEN=<token> MANIFEST_FILE=configs/distribution_records_manifest.csv python -m src.schema_registry.batch
OPENMETADATA_JWT_TOKEN=<token> MANIFEST_FILE=configs/farmer_registration_master_dataset_manifest.csv python -m src.schema_registry.batch
OPENMETADATA_JWT_TOKEN=<token> MANIFEST_FILE=configs/scheme_physical_financial_progress_dataset_manifest.csv python -m src.schema_registry.batch
```

---

### Field-Level Classification (MDSF)
Per MDSF, classification is done **per field**, not per dataset — based on
potential risk of disclosure, re-identification or misuse.

- Levels: `Public`, `Internal`, `Confidential`, `Restricted`, `PII`, `Financial`, `Health`
- Auto-classified by rules in `src/schema_registry/curate.py` (`AUTO_CLASSIFICATION_RULES`)
- Manual override via field dictionary CSV (extra `classification` column), wired
  through the manifest's `business_metadata_file` field
- Priority: field dictionary > auto-classification > default (`Internal`)
- Sample field dictionary: `data_services/configs/field_dictionaries/farmer_registration_field_dictionary.csv`

Field Dictionary CSV format:
```csv
name,business_description,tag,glossary_term,active,classification
aadhar_no,"Unique Aadhaar number",PII,UIDAI_Aadhaar,true,PII
```

#### Published to OpenMetadata as column tags (done 2026-09-30)
Each curated column's `classification` is now applied as a tag on that column:

- Tag classification `MDSF` (mutually exclusive) auto-created by
  `openmetadata.publish._ensure_mdsf_levels()` with all 7 level tags —
  idempotent, runs once per publish
- `openmetadata.publish._to_column()` attaches a `TagLabel`
  (`source=Classification`, `labelType=Automated`, `state=Confirmed`) for the
  row's `classification`
- Verified: **288/288 columns tagged** across all 9 tables
  (`MDSF.Internal` 189, `MDSF.PII` 55, `MDSF.Financial` 41,
  `MDSF.Public` 2, `MDSF.Restricted` 1)

> **Gotcha:** OM 2.0.2 only populates `columns[].tags` when the request asks
> for **both** fields — `?fields=tags,columns`. `?fields=tags` alone returns
> an empty array (see `TableRepository` line ~210:
> `fields.contains(COLUMN_FIELD) && fields.contains(FIELD_TAGS)`).

---

### OpenMetadata Environment
- UI/API: http://localhost:8585 (Docker Compose: `infrastructure/openmetadata/`)
- Admin login: `admin@open-metadata.org` / `admin`
- JWT token for pipelines: **ingestion-bot** token (never expires) —
  Settings → Bots → ingestion-bot → Authentication Configuration, or decrypt
  from DB using `FERNET_KEY` in docker-compose
- 2026-09-30: MySQL volume was corrupted (InnoDB signal 6 crash loop) and reset;
  `docker-volume/db-data` wiped, migrations re-ran, all 9 tables re-published
- 2026-09-30: the reset left **5 orphaned Elasticsearch table docs** (old UUIDs
  that no longer existed in MySQL), so the Explore UI showed 14 tables instead
  of 9. Deleted them from `table_search_index`; API and UI both report 9 now.
  → If MySQL is ever wiped again, clean ES too (or re-run the search indexer).
- 2026-10-05: **second corruption** (340 restarts, `row_purge_step` InnoDB
  crash) → full local wipe + rebuild. Scope verified local-only before wiping
  (Docker Desktop npipe, compose project `openmetadata`, every OM URL in the
  repo is `http://localhost:8585`; no global/remote instance touched):
  1. `docker compose down` → deleted the corrupted bind mount
     `docker-volume/db-data` (the running container predated the compose file's
     switch to the `mysql-data` named volume, so `up -d` created a fresh
     named volume) → deleted `openmetadata_es-data` too, so **no orphan docs
     this time** (ES `table_search_index` = 9 right after republish)
  2. `execute_migrate_all` exit 0; server healthy; login OK
  3. Re-ran `setup_custom_properties` (the wipe also erased the 4 Database
     custom properties — `apiAvailable`/`datasetOwner`/`frequency`/`timeline`;
     any future wipe needs this before publishing)
  4. Re-published all 9 tables: 5/5 + 1/1 + 3/3; verified 288/288 columns
     MDSF-tagged with the documented distribution (Internal 189, PII 55,
     Financial 41, Public 2, Restricted 1)
  - **Gotcha hit during re-publish:** local
    `storage/_lookups/datasets.csv` still had the *pre-merge* header
    (`fiduciary,processor,risk_classification,retention_policy,lineage`) while
    merged code writes `category,api_available,owner,frequency,timeline,
    dataset_description` — `write_csv` derives fieldnames from `rows[0]`, so
    every row failed with `dict contains fields not in fieldnames`. Migrated
    the header in place (old values were all blank). Also: don't fix it with
    PowerShell `Export-Csv` — its UTF-8 **BOM** then breaks `csv.DictReader`
    (`'dataset_id'` KeyError); write with `UTF8Encoding($false)`.
- `bytea` type added to `_TYPE_MAP` (openmetadata/publish.py) and
  `KNOWN_POSTGRES_TYPES` (curate.py)

---

### Tests
- `python -m pytest tests/ -q` → **112 passed, 2 failed**
- Both failures are environmental (gitignored raw sample dumps, not in the
  repo), unrelated to this branch's changes:
  - `test_ddl_parser.py::test_real_vishwakarma_sample_parses_all_213_columns`
    needs `samples/pwd_vishwakarma_full_raw_columns.txt`
  - `test_field_dictionary_parser.py::test_real_sample_file_parses_into_seven_tables`
    needs `samples/kanya_sumangla_field_dictionary.csv`
- Requires main's new test dependency `moto[s3]` (in `requirements.txt`)

---

### Upload processed data to Neon (ingest API, 2026-10-05)
The curated snapshots no longer need to be mailed to the backend — `apps/api`
takes them over HTTP and stores them in the app DB (Neon in production,
`registry.*` schema):

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/registry/ingest` | logged-in user | upload a curated CSV snapshot (multipart `file`, optional `table_id`, `schema_name`) |
| GET | `/registry/ingest/tables` | public | list every ingested table |
| GET | `/registry/ingest/tables/{table_id}` | public | one table + its columns in snapshot order |

```bash
TOKEN=$(curl -s -X POST $API/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"...","password":"..."}' | jq -r .access_token)
curl -X POST $API/registry/ingest -H "Authorization: Bearer $TOKEN" \
  -F file=@storage/department/<dept>/<dataset>/<table>/curated/schemas/<ts>.csv
```
- Re-uploading the same table is idempotent (rows for that `table_id` are
  replaced, not appended); the snapshot's own `table_id` is trusted and a
  mismatched override is rejected, as is any file that isn't a curated
  snapshot (e.g. a raw source CSV).
- Tables: `registry.tables` / `registry.columns` (DDL in `apps/api/schema.sql`,
  created automatically at startup via `CREATE SCHEMA IF NOT EXISTS registry`).
- Endpoints and parsing covered by `apps/api/tests/test_registry_ingest.py`
  (18 passed); also verified live against a throwaway Postgres: upload,
  idempotent re-upload, 422 on wrong file, 401 without a token, 404 on an
  unknown `table_id`.

---

### Global push (2026-10-05)
All 3 Agriculture manifests also published to the **global** OpenMetadata at
`http://10.0.96.105:8585` (distinct instance — it already had `pwd.vishwakarma_T`
under service `pwd`; same `admin@open-metadata.org`/`admin` credentials,
version 2.0.2 identical to local):

```powershell
$env:OPENMETADATA_HOST_PORT = 'http://10.0.96.105:8585/api'
$env:OPENMETADATA_JWT_TOKEN = <global login accessToken>
# then the same 3 MANIFEST_FILE=... python -m src.schema_registry.batch runs
```
- Result: **9/9 tables** (5+1+3) → global now has 10 tables total
  (10 = 9 agriculture + the pre-existing pwd one); 288/288 MDSF-tagged
  columns, distribution identical to local; ES `table_search_index`=10
- Global already had the 4 Database custom properties
  (`apiAvailable`/`datasetOwner`/`frequency`/`timeline`), so
  `setup_custom_properties` wasn't needed there; MDSF classification was
  auto-created by `_ensure_mdsf_levels()` on first publish
- `OPENMETADATA_HOST_PORT` defaults to localhost — always set it explicitly
  when pushing global, and never wipe global (the local wipe procedure above
  applies only to the local Docker stack)

---

### Global server (8585) crash investigation (2026-10-05, ended mid-diagnosis)
Reported crashed shortly after the global push. Findings so far (all read-only):

- **Timeline (IST)**: push finished 17:02–17:05 → ~17:06 first probe:
  8585/8586 **dead**, but ES 9200, MySQL 3306, Airflow 8081, pm2 apps
  3100/4100, SSH 22 all alive → host was fine, only the `openmetadata_server`
  container was down → back up by 17:11; 4/4 `/system/version` samples OK
  over 75 s (17:16–17:17) = recovered, not flapping
- **Not a host reboot / not MySQL or ES**: MySQL uptime 7.4 h (started
  ~09:50), ES JVM same pid + 7.4 h uptime — neither restarted during the
  window; only the OM server (Java) died and came back
- DB forensics: server's boot side-effects (`change_event` bot-user updates
  by usage/governance/profiler-bot) stamped **17:10:03** = boot completing in
  the recovery window; `background_jobs` shows only 2 unrelated `CSV_EXPORT`
  jobs (admin, `pwd` service) completed 16:22 — nothing failing, no errors in
  `background_job_logs`
- **Root cause NOT confirmed**: needs `docker logs openmetadata_server` /
  `dmesg | grep -i oom` on the host. Leading hypothesis = **JVM OOM-kill**
  (server heap `-Xmx1G` + ES 1G) under the indexing load of the 9-table /
  501-column push; Docker `restart: always` brought it back in ~5 min.
  Correlation with the push is timing-only, not proven.
- **Blockers**: SSH to `bipp2@10.0.96.105` refused (`publickey,password` —
  no key on this machine); global's MySQL `root`/`password` from the compose
  file is **rejected** (different creds on global); use
  `openmetadata_user`/`openmetadata_password` (works). Port scans done with
  `Test-NetConnection`; MySQL probed via `pymysql`.
- Note: ES `_nodes/_local/jvm` in this image has **no `uptime_in_millis`** —
  use `start_time_in_millis` (or `pid`) instead.
- State at stop: global healthy again, 10 tables, data intact (205 tables in
  `openmetadata_db`); local stack also healthy (9 tables).

---

### Schema-registry loophole pass: subtasks 11–18 (2026-10-06)
Scope was P2 subtasks 11–16 + P3 subtasks 17–18 only (the P0/P1
personal-data classification items 1–10 were explicitly out of scope).

- **11 raw storage**: original submission copied verbatim to
  `<table>/raw/source/<ts>.<ext>` + `<ts>.sha256`, before parsing; new
  `write_bytes`/`read_bytes` on `ObjectStorage` (local + s3); result carries
  `source_path`/`source_hash_path`/`source_hash`.
- **12 run log + diff**: `_lookups/runs.csv` (run_id, table_id, ts, mode,
  source_hash, operator from `$OPERATOR`, added/removed/changed,
  publish_status, error) written in `finally` — **every** run gets a row,
  including failures; per-run `<table>/diffs/<ts>.csv` and an inferred mode
  (initial_load/append/update/full_refresh) computed *before* the removal
  guard so a rejected run still says what was missing.
- **13 storage/OM sync**: `publish_status` ∈ not_attempted/unpublished/
  published/failed; new `python -m src.schema_registry.republish` iterates
  `unpublished_runs()` (skips soft-deleted, continues past failures, updates
  run rows in place, exit 1 if any still fail); field-dictionary ingest is
  per-table isolated and reports status per table (non-zero exit).
- **14 restricted vocab**: `validate_category/tag/glossary_term` in curate.py
  (CAT-1..CAT-4, KNOWN_TAGS = AUTO_TAG_RULES ∪ {PII}, no "." in glossary
  terms), enforced in `run()` *and* in `publish_table()` (`_ensure_sensitivity_tag`,
  `_ensure_tags_and_terms`); CAT-4 description added; invalid values raise.
- **15 empty slugs + orphans**: `slugify()` raises on a name with no ASCII
  (no more `pwd..t1`); `deleted` column on `tables.csv` +
  `soft_delete_table()` + `python -m src.schema_registry.openmetadata.delete_table`
  (OM entity first, then registry mark); `publish_table()` refuses a
  soft-deleted row, `upsert_table()` clears the mark on re-ingest.
- **16 owners**: `_resolve_owner()` (User→Team, FQN or email local-part) →
  `owners` on `CreateDatabaseRequest` **and** in the JSON-Patch replace (always
  a list, `[]` when nothing resolves, so `/exists` for `replace`).
- **17 credentials**: compose no longer ships `MYSQL_ROOT_PASSWORD: password`
  (now `${MYSQL_ROOT_PASSWORD:?...}` → fails without `.env`,
  `.env.example` added, `.env` gitignored); 3306/9200/9300 bound to
  `127.0.0.1`; `AUTHENTICATION_ENABLE_SELF_SIGNUP` defaults to `false` in
  both places; infra README gained a hardening checklist + "change the
  bootstrap admin password" note; ingestion-bot JWT documented everywhere
  (admin session tokens explicitly called out as wrong).
- **18 smaller**: `batch.py` and field-dictionary ingest exit non-zero on
  failure (print FAILED rows); dataset-level fields now accepted in a
  manifest; `setup_custom_properties.py` requests have `(10,60)` timeouts +
  `raise_for_status()`; sample-dependent tests `skipif` their gitignored
  file; `latest_curated_snapshot_path()` only accepts `<ts>.csv` (stray
  README/backup can't become "the latest snapshot"); all CSV reads/writes
  now explicit UTF-8 (`utf-8-sig` reads) — Devanagari names/descriptions
  broke on Windows' locale encoding before.
- **Tests**: `python -m pytest tests/ -q` → **155 passed, 2 skipped** (the 2
  skips = gitignored `samples/` dumps). New: `test_run_log.py`,
  `test_republish.py`, `test_soft_delete.py`, `test_ownership.py`,
  `test_infrastructure.py` (+ additions to batch/field-dictionary/publish).
- **Live verification (local stack)**: 3 agriculture manifests → **9/9
  published**; runs.csv showed 9 `published` + 1 `not_attempted` (the
  rejected dictionary tag below) with modes/counts; `raw/source`+sha256+diffs
  present; `setup_custom_properties` idempotent (exit 0); `republish` 0/0;
  `category=CAT-2` + `owner=admin` published to the Database
  (`tags: DataSensitivity.CAT-2`, `owners: user:admin`), then cleared back to
  blank and re-published → `tags: [] owners: []` (JSON-Patch replace
  verified against a real server). Governance fields left blank as before.
- **Data fix found by item 14**: `configs/field_dictionaries/
  farmer_registration_field_dictionary.csv` had `tag=Internal` on 4 rows
  (`tag` was a copy of `classification` on all 18 rows; PII/Financial were
  valid FieldTags, Internal isn't) → `tag` blanked on those 4, `farmers`
  then ingested 9/9. OM still shows the stale `FieldTag.Internal` on those
  columns: **OpenMetadata merges `columns[].tags` on PUT** — the documented
  Known-limitation, now confirmed live. Fix agreed as follow-up (JSON-Patch
  replace on the table's columns/tags, same approach as the Database) but
  **not done** — session stopped there.
- **Pending DoD**: CMSVY + Vishwakarma re-ingest. Real CMSVY source is now
  at `Datasets/Kanya Sumangla Portal.xlsx` (Excel — still needs converting
  to the field-dictionary CSV shape before `field_dictionary_ingest` can
  run); `samples/kanya_sumangla_field_dictionary.csv` and
  `samples/pwd_vishwakarma_full_raw_columns.txt` remain absent from this
  machine, so neither was ingested. The 9-table agriculture re-ingest above
  was used as the live verification instead.
- **Local stack state at stop**: MySQL root password **rotated** off the old
  hardcoded `password` to a generated value stored in
  `infrastructure/openmetadata/.env` (gitignored; healthcheck healthy after
  `ALTER USER`), stack `docker compose down` (volumes kept) at end of
  session, Docker Desktop shut down.

---

### Column-tag JSON-Patch fix (2026-10-07)
Closes the known limitation left open at the end of the subtasks 11–18 pass:
OpenMetadata merges `columns[].tags` on PUT, so the `FieldTag.Internal` labels
that 4 `farmers` columns carried before `tag` was blanked in the field
dictionary stayed put no matter what `_to_column()` sent.

- `_patch_entity()` — the transport, extracted out of `_replace_entity_fields()`
- `_replace_column_tags(client, table_id, columns)` — called by `publish_table()`
  right after the table PUT; one op per column on `/columns/{i}/tags` with that
  column's full TagLabel list (`[]` clears a stale label). Per column rather
  than replacing `/columns` wholesale, so OpenMetadata's own per-column fields
  (`ordinalPosition`, `dataTypeDisplay`, `fullyQualifiedName`) survive; `add`
  rather than `replace` (RFC 6902 §4.1) so it works whether or not the stored
  column JSON has a `tags` key at all.
- Tests: `test_publish_table_patches_column_tags_right_after_the_put`,
  `test_publish_table_patches_an_empty_tag_list_to_clear_a_stale_label`. The
  Database-patch assertions in `test_openmetadata_publish.py` and
  `test_ownership.py` now pick their patch by `/databases/` path instead of
  `call_args` — the table patch is now the last one `publish_table()` sends.
- `python -m pytest tests/ -q` → **157 passed, 2 skipped** (was 155 + 2)
- README's Known-limitations bullet rewritten: the manual JSON-Patch `remove`
  workaround it told people to use is no longer needed.
- **Live verification (local stack, 2026-10-07)**: Docker Desktop was down, so
  started it and `docker compose up -d` (migrate exit 0, all 4 services
  healthy, no wipe). `python -m src.schema_registry.openmetadata.publish`
  with `TABLE_ID=agriculture_department.farmer_registration_master_dataset.
  farmers` exited 0 → the nested `/columns/{i}/tags` PATCH is accepted by a
  real OM 2.0.2 (the fallback of replacing `/columns` wholesale wasn't
  needed). Before/after diff of `?fields=tags,columns`: **exactly the 4 stale
  `FieldTag.Internal` labels gone** (`district_id`, `application_no`,
  `registration_no`, `block_id`), nothing else touched, 53/53 columns still
  tagged. Swept the other 8 tables (235 columns): 0 `FieldTag.Internal` left,
  so the whole local stack is clean.
- Local stack left **up** after the verification (it was `docker compose
  down` at the end of the previous session).

---

### Scope split + merge of origin/main (2026-10-08)

**Department scope (decided this session):**
- `agriculture_department` -- worked **locally and globally**.
- `public_works_department` (vishwakarma) and the Kanya Sumangla datasets --
  **local only**; someone else owns their global push, so nothing from this
  branch is ever published to `10.0.96.105` for those departments.

**Merged origin/main** (16 commits, `c12b473`), resolving all 19 conflicts:
tags -> main's shape (ingest writes only `name`/`business_description`; the
MDSF 7-level classification and curate's `auto_tag` untouched), `scale` ->
`None` everywhere, main's `validate_schema()` kept *alongside* our vocab
guards, main's atomic `_atomic_write`/`rows_to_csv`/`storage.lock` plus our
soft-delete/append-run lookups, main's by-name `_replace_column_tags` and
retrying `_patch_entity`. Installed `ruamel.yaml>=0.18` (main's
`add.py`/`catalog.py` need it). `python -m pytest tests/ -q` -> **397
passed** (301 before the merge; `reports/` left untracked).

**Dataset CATEGORY is now optional end-to-end.** `_check_category_covers_columns`
and its `_LEVEL_TO_MIN_CATEGORY` map (the "Under MDSF the highest category
applies" refusal, the blank-category warning) are gone from
`openmetadata/publish.py`, together with the whole `allow_category_below_columns`
knob threaded through `pipeline.run()`, `catalog.py`, `sync.py` and the
`ALLOW_CATEGORY_BELOW_COLUMNS` env var -- without that, every agriculture
publish warned (PII/Financial columns, blank CATEGORY). A `category` that
*is* set must still be CAT-1..CAT-4 (`_ensure_sensitivity_tag()`); blank
just means the Database entity carries no CAT tag. README bullet rewritten;
tests replaced with "CAT-1 + PII column publishes", "blank category
publishes without a warning", "non-CAT value still refused by run() and by
publish()".

**Agriculture's parser is wired into `pipeline.parse_source()` (2026-10-08).**
The `pass  # placeholder: agriculture's own parser goes here` in
`src/schema_registry/pipeline.py` now calls the department's own
`parsers/agriculture_parser.parse_table(text, table_name)`, which pulls the
requested table's block out of the multi-table submission (one CSV, several
tables side by side) by reusing `MultiTableCsvPreprocessor` -- the same code
preprocessing splits that file with, so the raw file and the preprocessed
per-table CSV parse to identical columns (locked by a test). Non-multi-table
input returns `None`, so the single-table CSVs preprocessing wrote and any
DDL dump still go through the shared parser; unknown table names fail with
the list of tables the submission does hold. That was the only placeholder
in the repo (repo-wide grep for placeholder/TODO/`goes here`/NotImplemented):
the web "hidden for now" nav blocks are deliberate UI scope, not missing
wiring. `python -m pytest tests/ -q` -> **405 passed** (8 new tests in
`tests/test_agriculture_parser.py`).

**Agriculture republished (local + global), 2026-10-08:**
- **Local**: the 3 manifests (`configs/distribution_records_manifest.csv`,
  `configs/farmer_registration_master_dataset_manifest.csv`,
  `configs/scheme_physical_financial_progress_dataset_manifest.csv`) ->
  **9/9 published**, no warnings; 288/288 columns tagged
  Internal 189 / PII 55 / Financial 41 / Public 2 / Restricted 1.
- **Global** (`http://10.0.96.105:8585/api`, same 3 manifests) -> **9/9
  published** with the identical 288-column tag distribution;
  `agriculture_department` = 9 tables, `public_works_department` still just
  its pre-existing `vishwakarma_T` (untouched, as scoped); server healthy
  (`2.0.2`) after the push.
- No category tag written on either side (CATEGORY left blank, see above).

---

### Catalog.yaml populated + audit-trail fixes (2026-10-09)

The department moved from manifest/`batch` runs to the documented
`add` → `sync` flow (README "Adding or updating a department's data"):

- 9 `add` runs (`ENVIRONMENT=local`) registered the 3 datasets in
  `data_services/catalog.yaml` under the id as it was then,
  `agriculture_department`: distribution 5 tables, farmers 1 (field
  dictionary passed as `--metadata`), scheme 3. Dataset details left blank —
  `category` is optional. The pre-existing `pwd` entry and the file's
  header comments kept as-is.
- `sync --department agriculture_department --dry-run`, then the real run:
  9/9 ingested through the agriculture parser (raw multi-table source) and
  published; a second run reports `unchanged / published` for all 9,
  0 failed, no "in storage but not in catalog" warnings for the department.
- **Audit-trail fix** (commit `dbf5ce9`): `sync()` ingests through
  `pipeline.run()` without an OpenMetadata client and publishes afterwards
  itself, so every run row was written `unpublished` and never updated — a
  successful sync looked unpublished in `runs.csv` and `republish` kept
  offering live tables. Added `lookups.latest_snapshot_run()` +
  `sync._record_publish()` (records `published`/`failed` + error on the
  snapshot-writing row; a broken log row is logged, never fails the sync);
  3 new tests in `tests/test_sync.py`.
- **`republish` env fix + Windows write retry** (commit `af7abb4`):
  `republish` called `load_dotenv()` and read a raw `OPENMETADATA_JWT_TOKEN`
  → KeyError on this repo's `LOCAL_*`-prefixed `.env`, and its hardcoded
  localhost default ignored `ENVIRONMENT` — now `load_env()` like every
  other CLI. `LocalObjectStorage` also retries the transient Windows
  `os.replace` PermissionError (antivirus/indexer; it was randomly failing
  `test_lookups`/`test_republish`); 2 new tests in
  `tests/test_local_storage.py`.
- `republish` run to align the log: **100 published / 1 not_attempted /
  0 unpublished** (the 1 = the rejected 2026-10-06 farmers dictionary run,
  excluded by design).
- `python -m pytest tests/ -q` → **425 passed**.
- Committed + pushed to this branch: `dbf5ce9` (sync fix), `af7abb4`
  (republish/local retry), `65c13a7` (catalog.yaml).

---

### Department id shortened: `agriculture_department` → `agri_dept` (2026-10-09)

Display name stays `Agriculture Department`; only the id changed — the
catalog key, table ids (`agri_dept.<dataset>.<table>`), storage paths and
the OpenMetadata service name.

- **Tracked files**: `catalog.yaml` (key + 10 `storage:inputs/...` source
  keys), the `pipeline.parse_source()` parser gate, agriculture
  `preprocessors/registry.py` (`department = ...`, drives manifest
  generation), the 3 `configs/*_manifest.csv`, `README.md`, and the id in
  `test_agriculture_parser.py` / `test_field_mapping.py` (fixture seeds).
- **Local storage (gitignored)**: byte-level replace across the tree —
  202 files / 6575 occurrences, **excluding `raw/source/**`** (212 files:
  the departments' original submissions must keep the bytes whose sha256
  runs.csv records) — then folder renames `storage/department/...` and
  `storage/inputs/...`; `_lookups/*.csv` backed up to temp first. runs.csv
  kept its 100 published / 1 not_attempted rows, now under `agri_dept.*`.
- **Local OpenMetadata**: `sync --department agri_dept` → 9 `unchanged` +
  `published` into the new service `agri_dept` (9 tables / 288 columns);
  the old `agriculture_department` service then hard-deleted via the SDK
  (`get_by_name` + `delete(id, recursive=True, hardDelete=True)`) — raw
  GET/DELETE by name 404s on this build, and the pydantic Uuid must be
  passed as the object (`str(id)` produces a `root=UUID('...')` URL).
- **Tag verification**: 9 tables / 288 columns / **365 tag assignments** —
  MDSF 288 (Internal 189 / PII 55 / Financial 41 / Public 2 / Restricted 1,
  exactly one per column) + FieldTag 59 (Date/Timestamp 27, PII 12,
  Financial 15, Status/Workflow 5) + BusinessGlossary 18 from the farmers
  field dictionary. Read with `?fields=columns,tags`: the `fields=tags`
  gotcha documented above cost a long detour — the writes had been fine all
  along (table-level tags do show with `fields=tags` alone, which made it
  look like only column tags were missing).
- `python -m pytest tests/ -q` → **425 passed** (twice).
- Global OpenMetadata untouched: it still holds the 9 tables under the old
  `agriculture_department` service — see Future Work.
- The rename edits were left uncommitted pending review.

---

### Rural Development (MGNREGA) onboarded, geo-name rule, `--reclassify` (2026-10-12)

Second department started on this branch. The catalog now lists two live
departments — `agri_dept` (local + global) and `rural_development_department`
(local only, global push later); `pwd` was commented out of it (below).
Everything today was **local** — no global push — and all code changes were
left uncommitted at end of day (14 modified + 3 new files; `reports/` still
untracked from 2026-10-07).

#### New: MGNREGA field dictionary + RuralDevelopment converter
- **Source**: `Datasets/Manreaga/` (gitignored) — 4 MGNREGA codebook
  workbooks downloaded 12:41, one per table, each holding a `codebook`
  sheet plus `metadata information` / `additional information`.
- **Converter**: new `src/schema_registry/parsers/dept/RuralDevelopment/`
  package — `mgnrega_codebook.py` (+ `__init__.py`) turns the workbooks
  into Field Dictionary CSVs, the exact shape `parse_field_dictionary`
  already consumes: one CSV per workbook (`--out-dir`) and one combined
  multi-table CSV (`--combined`, the file the catalog's `field_dictionary:`
  key takes). Table names come from each workbook's own "Resource" label:
  `category_wise_workers`, `employment_generated`, `women_joint_accounts`,
  `work_structure`.
  - Unit of measurement folded into the description ("Applied Job Cards" +
    "In Lakh" → "Applied Job Cards (In Lakh)"); Variable Type passes
    through to `FORMAT_TYPE_RULES`; Mandatory/Personal Data stay blank —
    gram-panchayat aggregates (job cards, workers, persondays,
    expenditure), never a person's record, so nothing is PII.
  - Guards: each workbook's metadata dataset name must start with
    `MGNREGA`, unknown workbook names are refused, a missing codebook
    fails loudly (a silent three-table ingest would be worse than an
    error).
  - CLI run wrote `configs/field_dictionaries/mgnrega/` (`*.csv`
    gitignored): 4 per-table CSVs + `mgnrega_field_dictionary.csv`.
- **New tests**: `tests/test_mgnrega_codebook.py` (per-table + combined
  conversion, guards, metadata/additional-info sheets).

#### Catalog changes (`catalog.yaml`)
- **New** `rural_development_department.mgnrega` described with the
  multi-table `field_dictionary:` key (no `tables:`), dataset details
  filled in: `frequency: yearly`, `timeline: 2014-15 to 2025-26`,
  `api_available: N`, plus a description of the 4 tables.
- **`pwd:` commented out** — PWD (vishwakarma) is scoped local-only and
  owned by another team, so it is kept out of the catalog to guarantee
  `sync` never touches it. Closes the long-standing "stale `pwd:` entry"
  Future-Work item (storage/OM use `public_works_department`; syncing
  `pwd` as-is would have duplicated it).
- `tests/test_catalog.py`: department list is now
  `[agri_dept, rural_development_department]`.

#### First ingest (local)
- `add` 14:19 (combined dictionary → `storage/inputs/
  rural_development_department/mgnrega/`), then `sync` 14:21–14:23 →
  **4/4 tables `initial_load` / `published`, 84 columns** (28 / 29 / 13 /
  14); `_lookups/*` and `storage/department/
  rural_development_department/mgnrega/` created.

#### Geo place-name classification rule (`curate.py`)
- New **first** rule in `AUTO_CLASSIFICATION_RULES`: administrative place
  names (`state|district|block|gp|gram_panchayat|village|tehsil|taluka|
  taluk|mandal|town|city|ward|sector|ulb|cluster|hobli|country` … `_name`,
  incl. compounds like `curr_district_name`) → **`Public`**. It must stay
  first: the PII rule matches any `*_name` column, so
  `state_name`/`district_name`/`gp_name` used to be tagged PII — a state
  or a Gram Panchayat is reference data, not a person. Covered in
  `tests/test_curate.py`.

#### `sync --reclassify` (re-derive auto answers on demand)
- **`sync.py`**: new `--reclassify` flag, **requires `--department`**
  (re-deriving classifications for every department would rewrite other
  teams' snapshots). It skips the "unchanged" short-circuit for both
  field-dictionary and per-table sources (outcome detail
  `reclassify requested`) and passes the flag down.
- **`pipeline.run(reclassify=True)`**: drops the stored auto-derived
  `classification`/`tag` before the merge so the *current*
  `AUTO_CLASSIFICATION_RULES`/`AUTO_TAG_RULES` re-derive them — without
  it a rule's first-run answer was frozen forever (a place-name
  classified PII under the old rule stayed PII). Answers re-submitted in
  this run's `business_metadata_file` still win through the same merge;
  a blank still never clears.
- **`field_dictionary_ingest.run_field_dictionary(..., reclassify=...)`**
  passes it through per table.
- New tests: 2 in `tests/test_sync.py`, 2 in `tests/test_pipeline.py`.

#### Publish fix: MDSF mutually-exclusive 400 (`openmetadata/publish.py`)
- The 15:51 `--reclassify` run (first run under the geo rule) **failed at
  publish ×4**: OpenMetadata 2.x's PUT merges the submitted column tags
  with the stored ones, so old `MDSF.PII` + new `MDSF.Public` arrived
  together → HTTP 400 `Tag labels MDSF.PII and MDSF.Public are mutually
  exclusive`; the `republish` at 16:00 failed the same way. A
  reclassify could therefore never land its new level.
- **Fix** `_columns_for_put()`: the `CreateTableRequest` now carries only
  the non-MDSF tags (FieldTag / glossary merge harmlessly); the
  JSON-Patch `_replace_column_tags()` sends right after the PUT (`add` on
  the exact `columns/N/tags` member) sets the full list, which *does* swap
  the old MDSF label for the new one (verified against local
  OpenMetadata 2.0.2 per the docstring).
- `tests/test_openmetadata_publish.py` asserts MDSF labels are absent
  from the PUT but present in the patch.
- ⚠️ `_lookups/runs.csv` still records those 4 mgnrega rows (15:51) as
  `failed` — the confirming republish after this 16:47 fix was **not**
  run today (see Future Work) → **done 2026-10-13**: 4/4 `published`,
  place-name columns now `MDSF.Public` (see that section).

#### apps/api: dataset docs served from OpenMetadata custom properties
- **`client.get_database_by_fqn()`** fetches the database with
  `fields=extension,owners` — the extension holds the dataset-level
  fields data_services publishes (frequency / timeline / apiAvailable /
  datasetOwner).
- **`routers/registry.py`**: `_info_from_extension()` maps extension keys
  to the sidecar's field names (`apiAvailable` free-text `Y`/`N` → bool,
  blank → `None`); `_dataset_info()` sources a table's `info` from the OM
  database extension and lets the local `table_info` sidecar — only ever
  written by the manual POST flow — override it **field by field**, so an
  admin edit beats a stale publish. `registry_table` now returns
  `info`/`facts` from it (lookup body moved inside the try that maps
  client errors to 404).
- **Tests**: `tests/test_registry_guest.py` gains fake OM databases with
  extensions and 2 new tests (docs served from OM extension; sidecar
  overrides it).

#### Test state at end of day
- `apps/api` (last run 15:42): 48 tests, `lastfailed` empty — green.
- `data_services` (last run 15:47): 457 tests collected; `lastfailed`
  holds 2 failures, both in `test_csv_schema_parser.py` (scale column) —
  files untouched today, not investigated (out of today's scope).

---

### Review, commits, and the confirming MGNREGA publish (2026-10-13)

Reviewed yesterday's 15 modified + 3 new files line by line (all coherent),
split them into 4 logical commits and pushed them, then closed the
⚠️ left open above.

- **Commits**: `4875f18` (MGNREGA converter + catalog entry, incl. the
  `pwd:` comment-out), `e3eed0d` (geo rule + `sync --reclassify`),
  `9948b89` (`_columns_for_put` MDSF fix), `a865413` (apps/api dataset
  docs from the OM database extension). `reports/` deliberately left
  untracked (field-mapping reports from 2026-10-07).
- **Docker Desktop was down** at session start, which is what made the 2
  `test_batch.py` CLI tests fail this morning: `batch`'s `load_env()`
  re-reads `OPENMETADATA_JWT_TOKEN` from `.env` (the test only unsets it
  in the subprocess env), so `get_client()` probed
  `localhost:8585/v1/system/version` → connection refused → exit 1 before
  any row ran. **Purely environmental** — they pass with the stack up.
  (`Invoke-WebRequest` to that URL times out on this machine; use
  `curl.exe` — a proxy setting swallows PowerShell's request.)
- **Stack up**: `docker compose up -d` → migrate exit 0, all 4 services
  healthy, server 2.0.2, no wipe.
- **Confirming sync** (the Future-Work item):
  `python -m src.schema_registry.sync --department rural_development_department`
  → field dictionary `unchanged`, **4/4 tables `published`, 0 failed** —
  the 10:22 `failed` rows in `_lookups/runs.csv` are now recorded
  `published` (`_record_publish` updates the snapshot-writing row), and a
  second run is a no-op.
- **Verified in OM**: all 4 tables (84 columns) carry **exactly one MDSF
  label per column** — `MDSF.Internal` 67 + `MDSF.Public` 17 = 84, no
  mutually-exclusive leftovers — and every place-name column
  (`state_name`, `district_name`, `block_name`, `gp_name` × 4 tables) is
  now `MDSF.Public`. So `_columns_for_put()` + the JSON-Patch really do
  swap the old label on a live 2.0.2 server.
- **Tests**: `data_services` → **445 passed** (was 443 + 2 environmental),
  `apps/api` → **47 passed**.

---

### Global OM phase 2: `agri_dept` migrated, old service deleted (2026-10-13)

The last "phase 2" item closed: global (`http://10.0.96.105:8585/api`)
now mirrors local, which had been on `agri_dept` since 2026-10-09.

- **Pre-flight**: global login is `POST /v1/users/login` with the
  password **base64-encoded** (`{"password":"YWRtaW4="}` — a plain
  `admin` gets `400 Password needs to be encoded in Base-64`).
  Inventory before: `agriculture_department` 9 tables (288 cols), `pwd` 1
  table (the other team's, untouched), 10 tables total.
- **Agri was reclassified first** (agreed scope call): the 9 snapshots
  predated the 2026-10-12 geo rule. Re-deriving under the current rules
  changes exactly **4 columns** — `current_booking.block_name`,
  `current_booking.district_name`, `farmers.block_name`,
  `farmers.bank_district_name`, `MDSF.PII → MDSF.Public` — everything
  else identical (the farmers field dictionary re-submits its answers,
  so `application_no`/`registration_no`/`rashan_card_no` keep their
  dictionary values rather than the auto answer).
  - `sync --reclassify --department agri_dept` (local) → **9/9 ingested
    + published, 0 failed**; local now `Internal 189 / PII 51 /
    Financial 41 / Public 6 / Restricted 1` = 288 (PII 55 → 51,
    Public 2 → 6), FieldTag 59 + BusinessGlossary 18 = 77 other labels.
- **Global push**: `OPENMETADATA_HOST_PORT=http://10.0.96.105:8585/api`
  + `OPENMETADATA_JWT_TOKEN=<login token>` then
  `sync --department agri_dept` → `unchanged / published` ×9, 0 failed.
  (`load_env()` uses `setdefault`, so shell-provided OM settings win.)
  Verified identical to local: 9 tables / 288 columns / 288 MDSF labels,
  same distribution, the 4 place-name columns `MDSF.Public`.
- **Old service deleted**: the SDK delete is
  `client.delete(DatabaseService, service.id, recursive=True,
  hard_delete=True)` — note the positional `entity_id` and snake_case
  `hard_delete` (an `id=`/`hardDelete=` call raises `TypeError` on this
  SDK build). Guard script refused to delete unless the new service
  already held 9 tables / 288 tagged columns.
- **After**: global = `agri_dept` 9 + `pwd` 1 = **10 tables**, ES
  `table_search_index` = **10** (no orphan docs), server healthy 2.0.2.

---

### Local cleanup: only Agri + MGNREGA left locally (2026-10-13)

Closing the original task ("add MGNREGA to OpenMetadata, then remove the
other departments locally so only Agri and MGNREGA remain"). Scope agreed:
**OM + registry, storage kept** — `storage/department/<other dept>/`
curated snapshots stay, so those departments can be re-published later;
`storage/inputs/` never held them anyway (only `agri_dept` + `rural_…`).

- **Local OpenMetadata**: hard-deleted 7 services (`recursive=True,
  hard_delete=True`, guarded script that refused unless `agri_dept`=9 and
  `rural_development_department`=4 tables were present):
  `basic_education_department` (5), `health_department` (4),
  `public_works_department` (1), `pwd` (1 — an orphan `t1` left by an old
  test, in no lookup), `revenue_department` (1),
  `social_welfare_department` (7),
  `women_and_child_development_department` (22) → **41 tables gone**.
  - Result: local OM = **`agri_dept` 9 + `rural_development_department` 4
    = 13 tables / 372 columns, all MDSF-tagged**; ES `table_search_index`
    = **13** (no orphans).
- **Registry lookups** (rows dropped, all 4 `_lookups/*.csv` backed up
  first to `storage/_lookups/backup_20261013/` — gitignored, but the
  restore point for this cleanup; a copy is also in the session temp
  folder):
  `departments.csv` → 2 rows (`agri_dept`,
  `rural_development_department`); `datasets.csv` → 4 rows (3 agri + the
  MGNREGA one); `tables.csv` → 13 rows (40 dropped).
  `runs.csv` deliberately **kept as-is**: it's the audit trail and all 73
  of those runs are `published`, so `republish` never offers them
  (verified: `republish` → `0/0 republished`, exit 0).
- `catalog.yaml` needed no change — it already listed only the two
  departments (`pwd` commented out on 2026-10-12).
- **Verified**: bare `sync --dry-run` → the 13 tables of the two
  departments only, `14 table(s), 0 failed` (14 = 13 tables + the
  field-dictionary line), no "in storage but not in catalog" noise.
  Tests: `data_services` **445 passed**, `apps/api` **47 passed**.
- Note for a reversal: bringing a department back = re-adding its catalog
  entry and `sync --publish-only` (its curated snapshots are still under
  `storage/department/`), or restoring `_lookups/*.csv` from the backup.

---

### Merge preview (dry-run, 2026-10-13): what `origin/main` (`54679a2`) conflicts on

Ran `git merge-tree` plus a real trial merge in a scratch worktree
(removed afterwards; the working tree was never touched). Result: **3
conflicted files, exactly one hunk each**; the other 9 overlapping files
auto-merge cleanly.

**1. `data_services/catalog.yaml`** (datasets block, ~line 42)
- Conflict: HEAD starts `agri_dept → distribution_record_dataset:` while
  main starts `vishwakarma: category: CAT-3` (PR #23 added a `steward:`
  key, filled `category: CAT-3` and the description on pwd's entry).
- Resolve: **keep ours** (pwd commented out; agri + mgnrega as-is). The
  hand-resolved file must NOT let main's pwd lines (`vishwakarma`,
  `CAT-3`, the long description) attach under our
  `distribution_record_dataset` -- the raw merge output does exactly that.
- Adopt from theirs: a blank `steward:` under each of our 4 dataset
  entries, and `steward` in the header's per-dataset field list.
- Preserve main's richer pwd metadata inside the commented pwd block
  (`category: CAT-3`, description, `steward:`) so nothing is lost when
  pwd is re-enabled.

**2. `data_services/src/schema_registry/openmetadata/publish.py`**
(insertion point after `_CUSTOM_PROPERTY_NAMES`, ~line 329)
- Conflict: we inserted `_resolve_owner()` there (ownership → OM
  User/Team); main inserted `EXTRA_METADATA_PROPERTY` +
  `_PUBLISHED_ELSEWHERE` + `_extra_metadata_json()` (both new in PR #23).
- Resolve: **keep both function blocks**, side by side.
- Already auto-merged, keep as-is: `"steward": "datasetSteward"` in
  `_CUSTOM_PROPERTY_NAMES`; `"steward": dataset_row.get("steward", "")`
  in `publish_table`'s dataset properties; the `_replace_entity_fields`
  call writing `extension.extraMetadata = _extra_metadata_json(...)`.
  Our extension builder (publish.py:386, iterates
  `_CUSTOM_PROPERTY_NAMES`) picks steward up automatically, so main's new
  steward assertions in `test_openmetadata_publish.py` (lines 225-264)
  pass without edits.

**3. `data_services/src/schema_registry/pipeline.py`** (~line 450)
- Conflict: HEAD has the expanded `result = {...}` dict (source_hash,
  archive paths, column_count, unmatched_metadata_names); main has its
  `lookups.upsert_dataset(... steward=steward ...)` + `upsert_table` at
  the old indentation.
- Resolve: **keep our `result` dict**, drop main's duplicate upsert
  block, and **add `steward=steward` to our `upsert_dataset` call** just
  above the conflict -- otherwise steward never reaches datasets.csv and
  `test_sync.py:79` (`assert row["steward"] == "PWD Data Cell"`) fails.
- Auto-merged already: `steward: str = ""` in `run()` (line 213), the
  docstring (246), and the `STEWARD` env read in `_main` (563).

**Auto-merging cleanly (review only, no hand-editing expected):**
`.env.example`, `README.md`, `catalog.py` (dataset `steward` field),
`setup_custom_properties.py` (creates the `datasetSteward` property),
`registry/lookups.py` (`upsert_dataset(..., steward=...)`), and the tests
`test_lookups.py`, `test_openmetadata_publish.py`, `test_sync.py` (new
steward assertions).

**After resolving:** `pip install -r requirements.txt` (main adds
`anthropic>=0.40` for the new standalone `ai_metadata.py` CLI -- nothing
imports it), run the full suites (data_services + apps/api), then
`sync --dry-run` through MinIO and confirm local OM still shows 2
services / 13 tables. Steward should then flow catalog → pipeline →
datasets.csv → the `datasetSteward` custom property end to end.

### Column descriptions + MDSF CAT for agri_dept (2026-10-14, done)

Delivered the 270 missing agri column descriptions, per-table metadata
files, and a dataset-level CAT-x classification per MDSF s5.1.

**What landed**
- `configs/field_dictionaries/<table>_metadata.csv` -- 8 new files
  (`name,business_description,tag`), one per distribution/scheme table:
  crop_sales 53, current_booking 55, current_booking_farmer_details 19,
  online_booking 13, online_booking_details 19, target_allocation_v2 22,
  financial_budget_allocation 18, grant_wise_bill_generation 36.
  Each is wired in `catalog.yaml` via `metadata: storage:inputs/agri_dept/...`.
- `farmer_registration_field_dictionary.csv` -- +35 rows appended (53
  total). The 18 department-answered rows are untouched byte for byte
  (only the missing final newline was added; without it the append
  glued onto `block_id`'s line and produced a 52-row file).
- `catalog.yaml` -- `category:` CAT-3 / CAT-3 / CAT-3 / CAT-1 and a
  dataset `description:` for each of the 4 datasets. MGNREGA is CAT-1
  (aggregated, no PII); the other three are CAT-3 (direct identifiers).
- `samples/cat_definitions.txt` -- the MeitY s5.1 text verbatim,
  force-added (`samples/` is gitignored); `_CAT_DESCRIPTIONS` in
  `publish.py` was rewritten to match it, CAT-4 = "Non-Shareable".
- `ai_metadata.py` -- replaced with the reviewed version; `DIRECT_ID`'s
  `ration` anchored to `(^|_)ration` (was matching `migration_status`).
  `Sensitive` added to `curate.KNOWN_TAGS` -- the pasted code emits it
  and `validate_tag("Sensitive")` was False, which would have failed at
  ingest. Auto-tagger switched off: only the `curate_schema()` fallback
  is commented out; `AUTO_TAG_RULES`/`auto_tag()` stay because
  `KNOWN_TAGS` derives from them. `--reclassify` now pops only
  `classification`, never `tag`.

**Result (verified against live OpenMetadata 2.0.2)**
- **372/372 columns described, 0 blank** (was 270 blank).
- **4/4 datasets carry `DataSensitivity.CAT-x`** and a description.
- **116 FieldTag labels** (was 59; 57 added, **0 removed, 0 overwritten**
  -- the department's answers are never overridden by the rules).
- **372/372 columns carry an MDSF level.** Tag values: Financial 39,
  PII 31, Date/Timestamp 27, Status/Workflow 14, Sensitive 5.
- Tests: data_services **478 passed**, apps/api **47 passed**.

**Gotcha for whoever verifies column tags next.** On this OM build
`GET /v1/tables/name/<fqn>?fields=tags` returns `tags: []` for *every*
column even though the labels are stored and indexed correctly -- do not
read that as data loss. The REST API's own log confirms it
(`storeUpdate: versionChanged=true, entityChanged=true ... Successfully
updated entity in ElasticSearch`), and the Elasticsearch
`table_search_index` shows the real values. Verify with
`/v1/search/query?index=table_search_index`, not the entity GET. Dataset
level is fine through GET (`fields=tags`).

**Known issue, not caused by this work.** `sync` exits 1 at the very end:
`Backup to 'sda-local-backup' failed (InvalidAccessKeyId)`. The data is
saved in `sda-local`; the backup bucket's key is invalid/absent in
`.env` (`LOCAL_WASABI_BACKUP_BUCKET`). No sync log before today mentions
"backup" at all, so this path had never succeeded locally. Fix by
creating the backup bucket and a key for it, or blank the variable.

### Future Work
- [x] **FIRST TASK (2026-10-14): `git pull`, merge `origin/main` locally,
      then raise the PR `department/agriculture_department` -> `main`**
      Done: merged as `eb13dbd` (main had moved `54679a2` -> `eee0696`).
      Exactly the 3 files the dry-run predicted, resolved as planned --
      `catalog.yaml` (ours + their `steward:`, pwd's richer metadata kept
      inside the commented block), `publish.py` (both function blocks),
      `pipeline.py` (our `result` dict + `steward=steward` on the
      upsert). Tests: **data_services 474 passed / 2 skipped, apps/api
      47 passed** (476 / 0 / 47 once MinIO was up -- the 2 skips were
      `requires_minio` in `test_batch`).** 6 failures found and fixed
      first: `test_ai_metadata`
      leaked the real `.env` into the session (`WASABI_BUCKET` made
      every later `storage_from_env()` build an S3 client -- stubbed
      `load_dotenv`, `draft()` is faked anyway); our
      `test_publish_table_patches_column_tags` counted table patches
      and main added a second one for `extraMetadata` (select on the
      column-tag ops); `latest_curated_snapshot_path()` returned
      backslashes on Windows, failing main's own
      `stores_unpublished_column_details` test (now returns forward
      slashes, not just matches on them).
      **`sync --dry-run` done 2026-10-14** (Docker up: `sda-minio` had
      exited 255, restarted it; `openmetadata_elasticsearch` was also
      down -- without it the `/api/v1/services/*` list hangs, since OM's
      search-index workers can't resolve). Result: **14 table(s),
      0 failed**, every row `unchanged` / `would publish`, exit 0. Local
      OM **untouched: 2 services / 13 tables**, with the service display
      name live (`Agriculture Department`). Steward chain verified
      separately: catalog.yaml parses `steward` for all 4 datasets and
      `set_dataset_fields()` writes it -- the column isn't in the live
      `_lookups/datasets.csv` yet only because a dry run writes nothing;
      the first real sync adds it (values blank until the governance
      meeting fills them in).
      **`pip install -r requirements.txt` done 2026-10-14** -- pulled
      `anthropic-1.13.0` + 6 deps, exit 0, no Anthropic account needed:
      installing is just downloading a PyPI package, and it asks for no
      login, key or payment. Re-ran both suites after: **476 / 0 / 47,
      still green** (it changed no behaviour -- `draft()` is faked in
      tests).
      What *does* need an account is **calling** the API, which
      `ai_metadata` is the only thing here that does: it needs
      `ANTHROPIC_API_KEY` (absent from `.env`). Two separate things to
      not conflate --
      - **Not** a Claude Pro/Max subscription (that's the claude.ai chat
        plan). The API is the Console at platform.claude.com, billed
        pay-as-you-go against prepaid credit with per-tier spend limits.
      - Verified failure mode with no key: `draft()` raises
        `KeyError: 'ANTHROPIC_API_KEY'` before any HTTP request, so
        nothing is sent and nothing is charged. The pipeline never calls
        `ai_metadata` (it's a manual step ahead of `add`), so the whole
        suite, `sync`, and everything else work with no key at all.
      Don't merge into `production` -- that's a separate, deliberate step
- [ ] **After the PR lands: push our 2 departments' files to the company
      Wasabi** (paused at a safe point 2026-10-13): run
      `python infrastructure/wasabi/push_agri_mgnrega.py` (dry-run -- it
      prints the upload set plus the 8 pre-existing PWD objects and checks
      nothing collides), review the output, then re-run with `--apply`.
      It writes only new keys under our 4 namespaces (agri_dept +
      rural_development_department, inputs + department), refuses to
      overwrite anything, and never touches the shared `dev/_lookups/*`
      CSVs or any PWD path. Do it after the merge lands so the dev
      server's next sync finds both the catalog entries and the files
- [ ] Server `.env` fix: `WASABI_BACKUP_REGION` is `eu-central-1` (the old
      `.env.example` default) but the backup bucket
      `up-sda-schema-registry-backup` lives in `us-west-1` -- backup
      copies fail with `AuthorizationHeaderMalformed` until corrected
- [ ] Add Field Dictionary (business metadata) for remaining tables
- [ ] Add dataset governance fields (owner, retention_policy, lineage)
- [ ] Add new tables as they arrive
- [ ] PWD (vishwakarma) + Kanya Sumangla (and the other 4 departments):
      their **local** OM services and registry rows were removed
      2026-10-13 to leave only Agri + MGNREGA locally — re-ingesting them
      means restoring `_lookups/*.csv` from the backup and
      `sync --publish-only` (their curated snapshots are still in
      `storage/department/`); their global push belongs to another team
- [x] Publish field-level classifications as OpenMetadata tags/taxonomy
- [x] Global OM: republish the department under `agri_dept` (phase 2) and
      delete its old `agriculture_department` service there — **done
      2026-10-13**: 9/9 published to global under `agri_dept` (after a
      4-column geo reclassify), old service hard-deleted, global = 10
      tables (`agri_dept` 9 + `pwd` 1), ES index consistent
- [x] `catalog.yaml`'s stale `pwd:` entry — commented out 2026-10-12 so
      sync can never touch it (storage/OM use `public_works_department`;
      PWD is the other team's, local-only)
- [x] Local OM: rerun `sync --department rural_development_department`
      (or `republish`) to clear the 4 `failed` mgnrega rows in runs.csv —
      they hit the MDSF mutually-exclusive 400 before `_columns_for_put`
      landed — and verify the place-name columns now show `MDSF.Public`
      (done 2026-10-13: 4/4 published, one MDSF label per column,
      `MDSF.Internal` 67 + `MDSF.Public` 17 = 84)
- [ ] `rural_development_department`: push to **global** OpenMetadata
      (the catalog comment scopes it local-only for now)