# Schema Registry

Departments (PWD, Samaj Kalyan, ...) send us lists of their table columns.
This project checks those lists, tags sensitive columns, keeps every version
in storage, and publishes them to OpenMetadata.

Everything in OpenMetadata comes from these scripts, never from clicking in
the UI. If a server is wiped or a new one is set up, **one command rebuilds it**.

**Contents:**
[At a glance](#at-a-glance) ·
[How it works](#how-it-works) ·
[First-time setup](#first-time-setup) ·
[Environments](#environments-local-development-production) ·
[Adding a department's file](#adding-a-departments-file) ·
[Changing data later](#changing-data-later) ·
[Blank fields in catalog.yaml are cleared, not kept](#blank-fields-in-catalogyaml-are-cleared-not-kept) ·
[Publish to OpenMetadata](#publish-to-open-metadata) ·
[Tests](#tests) ·
[Backups](#backups) ·
[Restoring](#restoring) ·
[When something fails](#when-something-fails) ·
[Reference](#reference) ·
[For developers](#for-developers)

---

## At a glance

**One time**

| What | How |
|---|---|
| Set up your machine | [First-time setup](#first-time-setup) |
| Turn on backups (only for a new Wasabi account) | [Backups → One-time setup](#one-time-setup) |

**Every time a department sends a new or updated file**

| Step | Command |
|---|---|
| 1. Upload the file and update the catalog | `python3 -m src.schema_registry.add <file> --department <dept> --dataset <dataset> --table <table>` |
| 2. Fill in dataset details, commit `catalog.yaml`, open a PR, merge | git |
| 3. Store and publish | `python3 -m src.schema_registry.sync` |

The backup runs on its own at the end of steps 1 and 3.

**Once a month:** `python3 -m src.storage.backup verify` to check the backup is complete.

### Deleting and purging catalog entities

The default deletion is a reversible soft-delete. It hides the selected
OpenMetadata entities, marks registry tables as deleted, and retains storage
and history. Use `--list` to review soft-deleted tables and `--restore` to
reactivate a scope.

```bash
python3 -m src.schema_registry.delete --table pwd.vishwakarma.works
python3 -m src.schema_registry.delete --list
python3 -m src.schema_registry.delete --table pwd.vishwakarma.works --restore
```

Permanent deletion is a separate, explicit purge. The target must already be
soft-deleted; `--purge` permanently removes OpenMetadata, storage, and registry
rows. Review a dry run before approving it:

```bash
python3 -m src.schema_registry.delete --table pwd.vishwakarma.works --purge --dry-run
python3 -m src.schema_registry.delete --table pwd.vishwakarma.works --purge --yes
```

Both operations require the environment-specific dedicated
`<ENV>_OPENMETADATA_ADMIN_JWT_TOKEN` (for example,
`DEV_OPENMETADATA_ADMIN_JWT_TOKEN`).
The regular ingestion token is intentionally rejected. For S3/Wasabi,
`<ENV>_WASABI_DELETE_ACCESS_KEY_ID` and
`<ENV>_WASABI_DELETE_SECRET_ACCESS_KEY` are also required; they must belong
to a key permitted to delete the selected environment's objects. Local
filesystem storage does not need S3 credentials.

The command asks for environment confirmation before making changes. `--yes`
bypasses the prompt for approved automation. Every lifecycle operation is
recorded in `_lookups/deletions.csv` with the operator, environment, target,
counts, and status. Dedicated S3 deletion credentials are required only for
`--purge`.

---

## How it works

```
Department's file ──add──▶ Wasabi ──────────┐
                                            │
catalog.yaml (in git) ──────────────────────┤  "what should be in OpenMetadata"
                                            ▼
                                      sync command
                      read ─▶ check ─▶ store ─▶ publish to OpenMetadata
                                            │
                                            └──▶ backup bucket (automatic)
```

- **Wasabi** stores the files: what departments sent, every processed version, and the lists of departments, datasets and tables.
- **`catalog.yaml`** lists what should be in OpenMetadata and which file each table comes from. It's in git, so every change is reviewed.
- **`add`** uploads a file and writes its entry in `catalog.yaml`.
- **`sync`** makes Wasabi and OpenMetadata match `catalog.yaml`. Running it twice changes nothing.
- **Every run leaves an audit trail**: the submitted file is copied verbatim to `raw/source/<ts>.<ext>` (with its SHA-256 next to it), the diff goes to `<table>/diffs/<ts>.csv`, and a row lands in `_lookups/runs.csv` — including runs that failed, with the error and how far they got (`publish_status`: `not_attempted` / `unpublished` / `published` / `failed`).

---

## Two ways in (only one reaches OpenMetadata)

Agriculture submits **one CSV holding several tables side by side**, so there
are two ways to turn it into one CSV per table. They deliberately coexist, but
they are not interchangeable:

| | `sync` + **`catalog.yaml`** | `preprocess_dataset` + **manifests** |
|---|---|---|
| What it reads | the department's submission in storage (`storage:inputs/...`) | the submission on disk at `datasets/<file>.csv` |
| Splits it with | `parsers/agriculture_parser.py`, at ingest time | `parsers/dept/Agriculture/preprocessors/` |
| Writes | storage + OpenMetadata | per-table CSVs under `data_services/source/` and a manifest in `configs/` |
| Read by | **`sync`** — the path that reaches OpenMetadata | `batch` (`MANIFEST_FILE=configs/<dataset>_manifest.csv python3 -m src.schema_registry.batch`) |

**`catalog.yaml` is the source of truth.** `sync` reads only it, so any table
that is not listed there is invisible to `sync` and to a rebuild — a manifest
row on its own does nothing for the catalog. The preprocessed CSVs under
`data_services/source/` and the `configs/*_manifest.csv` files are the dev-time
convenience for running many tables through `batch` without uploading anything;
they are committed so the pipeline can be exercised from a clone.

**The raw submissions are not committed.** `preprocess_dataset` points at
`datasets/*.csv` — the department's original multi-table workbooks — which are
deliberately left out of the repo (raw department data, and large). To run it,
drop the file at the path named in
`src/schema_registry/parsers/dept/Agriculture/preprocessors/registry.py`
(`PREPROCESSOR_CONFIG[<dataset>]["input_file"]`) and re-run. `sync` needs no
local copy at all: it reads the submission from storage.

---

## First-time setup

```bash
cd data_services
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in .env -- each setting has a comment
```

- **Never commit `.env`.** It holds keys and tokens.
- **OpenMetadata token:** in that server's UI, go to Settings → Bots → ingestion-bot and copy the token into `.env`. Without a token, commands still save files but don't publish.
- **Every new terminal:** `cd data_services && source .venv/bin/activate`

---

## Environments (local, development, production)

**The git branch you're on decides where everything goes.** Leave `ENVIRONMENT=` blank in `.env`.

| Git branch | Environment | Files go to (Wasabi) | OpenMetadata |
|---|---|---|---|
| any feature branch | `local` | your own Wasabi, folder `local/` | `LOCAL_OPENMETADATA_...` (your laptop) |
| `main` | `development` | company Wasabi, folder `dev/` | `DEV_OPENMETADATA_...` (BIPP2, 10.0.96.105; needs office network or VPN) |
| `production` | `production` | company Wasabi, folder `prod/` | `PROD_OPENMETADATA_...` (not set up yet) |

- Each branch can only use its own environment. Anything else is refused, so dev and production data only come from reviewed code.
- **`sync` enforces this a second time, at the point of the write.** Every command gets the rule from `load_env()`, but `sync()` also checks the branch it is running on before it reads anything: company Wasabi (`dev/` or `prod/`) only from the branch that owns it — `main` for `dev/`, `production` for `prod/`. That covers a direct `sync()` call built from `WASABI_BUCKET`/`WASABI_PREFIX` left over in the shell by an earlier `main` session, which nothing else would notice. `local/` is unrestricted: it is this branch's own account.
- If git can't tell the branch, it counts as a feature branch (`local`).
- Try things on a feature branch first. It writes only to `local/` and your laptop's OpenMetadata.
- `main` and `production` use the company Wasabi (`WASABI_...` in `.env`). **Feature branches never do:** they use your own Wasabi account from the `LOCAL_WASABI_...` lines (section 3b of `.env`), and stop with an error if those are blank.
- **In this project that "own account" is a local MinIO server** (`infrastructure/minio/`, buckets `sda-local` / `sda-local-backup`), so feature branches run the real S3 code path with zero company credentials in play — see `infrastructure/minio/README.md`. `LOCAL_ONLY=1` (`.env` section 3b) enforces it: local runs refuse any storage or OpenMetadata address that isn't this machine, so local data can never reach a shared server by a mistyped or copied host.
- **Going live:** merge `main` into `production`, check out `production`, then run `add`/`sync` there.
- **Every command that changes data asks first.** `add`, `sync`, `backup setup/copy/restore`, `inputs upload` and the other writing commands show where they will write (environment, branch, Wasabi folder, OpenMetadata) and ask twice: type `yes`, then the environment's name. Anything else cancels with nothing changed. Read-only commands (`--dry-run`, `verify`, `inputs list`) don't ask. For scripts, add `--yes` to skip the questions.

---

## Adding a department's file

Do it the same way every time. Examples use PWD; replace the file, department, dataset and table with your own.

### Step 1: Run `add`, picking the one case that fits

| Your situation | Case |
|---|---|
| Department is already in `catalog.yaml`, one file = one table (also for an **updated** file) | A |
| Department is **not** in `catalog.yaml` yet | B |
| You also have a file with column descriptions/tags | C |
| One file describes **several tables** (field dictionary) | D |

**A: existing department**
```bash
python3 -m src.schema_registry.add samples/pwd_vishwakarma_full_raw_columns.txt \
    --department pwd --dataset vishwakarma --table vishwakarma_T
```

**B: new department.** Add its full name (first time only):
```bash
python3 -m src.schema_registry.add samples/cmsvy_applications.csv \
    --department samaj_kalyan --department-name "Department of Social Welfare" \
    --dataset cmsvy --table cmsvy_application
```

**C: with descriptions/tags.** Same as A or B, plus `--metadata`:
```bash
python3 -m src.schema_registry.add samples/pwd_vishwakarma_full_raw_columns.txt \
    --department pwd --dataset vishwakarma --table vishwakarma_T \
    --metadata samples/pwd_vishwakarma_metadata.csv
```

**D: one file, many tables.** `--field-dictionary` instead of `--table`:
```bash
python3 -m src.schema_registry.add samples/kanya_sumangla_field_dictionary.csv \
    --department samaj_kalyan --dataset cmsvy --field-dictionary
```

Other options: `--format csv|postgres_ddl` (normally guessed from the file name: `.csv` → csv, anything else → postgres_ddl), and `--schema <name>` if the table isn't in the `public` schema.

`add` uploads the file to Wasabi (`dev/inputs/<dept>/<dataset>/<file>`) and updates `catalog.yaml`. It prints what it did:
```
  - uploaded samples/pwd_vishwakarma_full_raw_columns.txt -> inputs/pwd/vishwakarma/pwd_vishwakarma_full_raw_columns.txt
  - added table pwd/vishwakarma/vishwakarma_T
```
If it says *"catalog.yaml already up to date"*, skip to step 4.

### Step 2: Fill in the dataset details

For a new dataset, `add` leaves these blank. Fill in what you know in `catalog.yaml`:
```yaml
      vishwakarma:
        category: CAT-3            # CAT-1 | CAT-2 | CAT-3 | CAT-4
        owner: PWD IT Cell
        steward: PWD data steward
        frequency: monthly
        timeline: 2019-2026
        api_available: N           # Y or N
        description: Works and tenders managed by PWD
```

### Step 3: Check, then commit and open a PR

```bash
python3 -m src.schema_registry.sync --dry-run
```
Every table should show `would ingest` or `unchanged`, with `0 failed`. Fix anything that `failed` first (see [When something fails](#when-something-fails)).

```bash
git add catalog.yaml
git commit -m "PWD: new vishwakarma file"
git push
```
Open the PR on GitHub and get it reviewed and merged.

### Step 4: After the merge, run sync

Nothing runs it automatically yet.
```bash
python3 -m src.schema_registry.sync                    # all departments
python3 -m src.schema_registry.sync --department pwd   # just one
```
Tables are ingested in parallel with a bounded worker pool (8 workers by
default). Change the limit for a large or rate-limited environment with
`--workers`, or set `SYNC_MAX_WORKERS` for automation:
```bash
python3 -m src.schema_registry.sync --department pwd --workers 4
```
Each table still has its own storage lock and audit row, and publishing stays
ordered after ingestion so a partial worker failure cannot publish an
incomplete snapshot. Use a lower worker count if Wasabi or the OpenMetadata
server is rate-limited.
It prints a summary:
```
TABLE                          INGEST        PUBLISH        DETAIL
pwd.vishwakarma.vishwakarma_t  ingested      published      source file changed; 213 columns
```
- `unchanged`: same file as last time, so it isn't processed again. It's still published, in case the server was wiped.
- `failed`: the reason is in DETAIL. Other tables carry on, and the command exits with an error.
- Running all departments is fine: unchanged files are skipped.

### Step 5: Check in OpenMetadata

Open http://10.0.96.105:8585 and find the table under the department's service.

**For production:** merge `main` into the `production` branch, check it out, and repeat step 1 and step 4 there. The catalog is already right.

---

## Changing data later

### Columns

The department sends an updated file. Run `add` with the same names as before, then `sync`.

| Change in the file | What happens | Anything extra? |
|---|---|---|
| Same file again | Nothing changes in storage; it's republished as is | No |
| **New column** | Added, with automatic tags and classification | No |
| **Type, length or nullable changed** | Updated in OpenMetadata | No (check the dry run) |
| **Column removed** | `sync` **stops** for that table: `missing N column(s)`. This catches a partial file | If it's a real removal: add `allow_column_removal: true` to the table in `catalog.yaml` for **one** sync, then remove it |
| **Column renamed** | Counts as one removed plus one added | Same as removed. Its description and tags **don't** carry over |
| **Bad file** (unknown type, duplicate or empty column name, pasted `CREATE TABLE`) | Rejected, nothing saved | Fix the file |

### Column descriptions and tags

They come from a metadata file: `add … --metadata <file>`, then `sync`.
- A new value replaces the old one. The old sensitivity tag is removed in OpenMetadata.
- A **blank cell keeps** the old value; it never erases one.
- Column tags in OpenMetadata are set to exactly what the pipeline decided.

### Dataset details (category, owner, steward, frequency, timeline, api_available, description)

Edit them in `catalog.yaml` → PR → merge → `sync`. No new file or `add` needed.
- **Deleting a value in `catalog.yaml` clears it** in OpenMetadata. The catalog is the truth — but read [Blank fields in `catalog.yaml` are cleared, not kept](#blank-fields-in-catalogyaml-are-cleared-not-kept) first: a blank also wipes a value that only exists in storage.
- **`category` is optional.** Leave it blank until the governance meeting answers: a blank value just means the Database entity carries no CAT tag. When it is set, only `CAT-1`..`CAT-4` are accepted — an unknown value is rejected rather than published as a new tag.
- **`category` must be at least as high as the most sensitive column** (e.g. not CAT-1 when a phone-number column is CAT-3), or publishing is refused. Only if those columns are removed before sharing, add `allow_category_below_columns: true` to the dataset.

### Rules

- **Don't edit data in the OpenMetadata UI.** The next `sync` overwrites it. Change the file or `catalog.yaml` instead.
- **Every change goes through `catalog.yaml` and a PR**, so we know what's on the server and who changed it.
- **Departments' files stay out of git.** They live in storage: the company Wasabi on `main`/`production`, your local MinIO on feature branches (`infrastructure/minio/`). The git-ignored `data_services/storage/` folder is only a restore point.
- Old versions are never lost: Wasabi keeps every snapshot, and OpenMetadata keeps its own version history.

---

## Blank fields in `catalog.yaml` are cleared, not kept

**This is the one thing here that can destroy another team's data and exit `0` doing it.** Read this before deleting a line from `catalog.yaml`, and before running `sync` without `--department`.

### The issue

Two functions write a dataset's fields into `_lookups/datasets.csv`, and they read a blank in exactly opposite ways:

| Called by | Function | A blank field means |
|---|---|---|
| `add`, `batch`, `pipeline` | `upsert_dataset()` | **"not supplied"** — keep whatever is already stored |
| **`sync`** | `set_dataset_fields()` | **"cleared"** — empty the stored value |

`sync` uses the second one deliberately: `catalog.yaml` is reviewed in git, so it *is* the truth, and a field deleted there should disappear from storage too. That reasoning holds **only as long as the catalog is the sole place a value can come from.**

It isn't. Storage can hold values the catalog has never recorded — an `owner` another team set out of band, or one written by a `batch` CSV from before the dataset had a catalog entry. In that case the catalog's blank does not mean *"we decided to clear this"*, it means *"nobody wrote this down yet"* — and `sync` cannot tell the two apart.

### What `sync` does with a blank

`set_dataset_fields()` rebuilds the row from the catalog and replaces the stored one. It never merges:

```python
new_row.update({field: (fields.get(field) or "") for field in DATASET_FIELDS})
_upsert(storage, DATASETS_PATH, "dataset_id", dataset_id, lambda _: new_row)
```

That `lambda _: new_row` is the whole problem: the existing row is discarded, not consulted. Compare `upsert_dataset()`, which keeps it — `"owner": owner or existing.get("owner", "")`.

All seven dataset fields behave this way:

```
category   api_available   owner   steward   frequency   timeline   dataset_description
```

### The implications

Measured against a throwaway local store, so this is observed rather than inferred:

```
1. after their write   owner=[Public Works Department (PWD)]
2. after a bare sync   owner=[]
```

Nothing in that run looks wrong. `sync` exits `0`, the summary says `0 failed`, and the audit row is normal. The only trace is one log line — `Dataset fields set from catalog: pwd.vishwakarma` — identical in form to a legitimate update.

### What breaks as a result

| Issue | Why |
|---|---|
| **Ownership silently vanishes** | The Database's built-in **Owners** field is filled from `owner`. Once cleared, ownership-based access rules, "my assets" filters and ownership reports stop applying to that dataset. |
| **Another team's work is lost** | An out-of-band value existed only in storage. `catalog.yaml` never recorded it, so there is nothing in git to restore from. |
| **The damage stays invisible** | `sync` reports success. You learn about it from a user who lost access, or from a diff of `_lookups/datasets.csv` — never from the run itself. |
| **The obvious repair doesn't hold** | Retyping the value in the OpenMetadata UI is undone by the next `sync`. The catalog is the only durable place for it. |
| **It recurs** | Every later sync clears it again, until the value is written into `catalog.yaml`. |

Wasabi keeps every version for 90 days and the backup bucket keeps the newest copy forever, so the old `_lookups/datasets.csv` can be brought back. That is a rescue, not a workflow.

### How to avoid it

- **Scope every `sync`.** The department filter is applied before anything is written, so other departments are never in scope:
  ```
  sync --department agri_dept   ✅ never reaches pwd
  sync                          ⚠️ every dataset in the catalog
  ```
- **Never set a dataset field out of band.** If a value must change, change it in `catalog.yaml` through a PR. A value living only in storage has a countdown on it.
- **Reconcile before the first bare `sync` in a new environment.** Diff storage against the catalog, and record any value storage holds that the catalog does not — as a deliberate entry, not a blank.
- **A dry run will not warn you.** Dataset fields are written only `if not dry_run` (`sync.py`), so `--dry-run` always looks clean here. It says nothing about a wipe that a real run would perform.
- **If you didn't put a value in the catalog, assume it isn't there.** The catalog's blank is authoritative — that is the design, and it is also the hazard.

---

## Backups

Three protections, so a mistake, a leaked key, or a lost bucket can't destroy the departments' files:

| Protection | What it does |
|---|---|
| **Version history** (main bucket) | An overwritten or deleted file can be brought back for 90 days |
| **Pipeline user** (the key in `.env`) | Can read, write and delete normally, but **never permanently delete**: no erasing old versions, no deleting buckets |
| **Backup bucket** (another region, `eu-central-1`, with Object Lock) | A second copy. **Nobody can delete** a file in it for 90 days, not even the admin. The newest copy of every file is kept forever |

**It's automatic.** With `WASABI_BACKUP_BUCKET` set in `.env`, every `add` and `sync` copies its new or changed files to the backup at the end. Nothing in the backup is ever deleted. If the copy fails, your data is still saved, the error says so, and the next run catches up.

### One-time setup

Only once per Wasabi account, by whoever has the admin key. Takes 1–3 minutes, because Wasabi answers slowly.

```bash
# 1. In .env:  WASABI_BACKUP_BUCKET=pwd-schema-registry-backup   WASABI_BACKUP_REGION=eu-central-1
# 2. See what it will do (changes nothing):
python3 -m src.storage.backup setup --pipeline-user sda-pipeline --dry-run
# 3. Do it, and make a key for the pipeline user:
python3 -m src.storage.backup setup --pipeline-user sda-pipeline --create-key
# 4. Put the printed key in .env (WASABI_ACCESS_KEY_ID / WASABI_SECRET_ACCESS_KEY).
#    It's shown only once. Keep the admin key out of .env.
# 5. First full copy, then check it:
python3 -m src.storage.backup copy --all
python3 -m src.storage.backup verify --all
```
- Running `setup` again is safe: it only does what's missing and prints `already` for the rest.
- If the admin key isn't in `.env`, put it in front: `WASABI_ADMIN_ACCESS_KEY_ID=... WASABI_ADMIN_SECRET_ACCESS_KEY=... python3 -m src.storage.backup setup ...`
- Wasabi's own "bucket replication" isn't used: trial accounts can't turn it on, and this works on every plan.

### Backup commands

| I want to... | Command |
|---|---|
| Check the backup is complete and identical (monthly) | `python3 -m src.storage.backup verify` |
| Catch up after a failed backup | `python3 -m src.storage.backup copy` |
| See what a restore would bring back | `python3 -m src.storage.backup restore --dry-run` |
| Bring back missing files | `python3 -m src.storage.backup restore`, then `sync` |
| Also replace files that differ | `python3 -m src.storage.backup restore --overwrite` |

These cover this environment's folder (`local/`, `dev/` or `prod/`). Add `--all` for the whole bucket.

In the Wasabi console, the backup is its own bucket (`pwd-schema-registry-backup`, Frankfurt), with the same folders as the main one.

---

## Restoring

| What was lost | What to do |
|---|---|
| **OpenMetadata** (server wiped or new) | `python3 -m src.schema_registry.sync --publish-only` (quick: republish what's in Wasabi), or plain `sync` (full: from `catalog.yaml`) |
| **One file** deleted or overwritten by mistake | Wasabi console → the bucket → turn on "Show Versions" → restore the older version |
| **Many files or a whole folder** in Wasabi | `python3 -m src.storage.backup restore`, then `sync` |

All of these are safe to run more than once.

---

## Publish to OpenMetadata

`openmetadata/publish.py` pushes a table's latest curated snapshot as a
Table entity via the `openmetadata-ingestion` SDK (pin it to match the
running server's version). One function, `publish_table(client, storage,
table_id)`, does the Service → Database → Schema → Table create-or-update.

**Mapping**: department → service, dataset → database, `schema_name` →
schema, `table_name` → table. Columns come from the curated CSV's
`data_type` (unrecognized types fail loudly, never guessed), and gets a
`readable_type` label derived from it (Whole Number / Decimal Number / Text /
Date & Time) so the catalog reads plainly to non-technical users. Each
column's `tag`/`classification`/`glossary_term` are pushed as TagLabels — `tag`
under a `FieldTag` Classification, the column's MDSF `classification`
level under `MDSF`, `glossary_term` under a `BusinessGlossary` — created on
first use, reused after. `readable_type`, plus `unit` when a department
answered one (`₹`/`Rs` → `INR`, `$` → `USD`), becomes the column's built-in
`dataTypeDisplay` (`Decimal Number (INR)`); `unit` also stays in
`extraMetadata` for machine use. Units are only accepted on numeric columns.
The dataset's own `category` (CAT-1..CAT-4,
validated against the MDSF vocabulary — an unknown one is rejected rather
than published as a new tag) and `dataset_description` are pushed the same
way, one level up, onto the Database entity. A resolved `owner` (an
OpenMetadata user or team, matched by name or email) also lands in the
Database's built-in **Owners** field, so ownership-based access rules and
"my assets" filters apply; an unresolvable one is a warning, not a failure.
A matching team must be of type **Group**: OpenMetadata rejects
Department/Division/BusinessUnit teams as owners, so those are skipped with a
warning instead of failing the publish.

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
---

## When something fails

Every command ends with either `Finished (ok)` or a short box like this:
```
------------------------------------------------------------------------------
ERROR: Can't reach the OpenMetadata server (http://10.0.96.105:8585/api).
What to do: ... For BIPP2 (development) you need the office network or VPN ...
Log file: logs/sync_20261007_164556.log
------------------------------------------------------------------------------
```
- Every run writes a log file in `data_services/logs/` (not in git), with the full technical details if it failed. **To get help, send that file.**
- Fix the cause; don't bypass the check.

| Error says | What to do |
|---|---|
| `not found in storage -- upload it first` | Run `add` for that file on this branch (e.g. added on `main` but not yet on `production`) |
| `isn't in catalog.yaml yet -- add --department-name` | New department: add `--department-name "..."` |
| `unknown key(s)` / `must be CAT-1 ... CAT-4` | Fix that line in `catalog.yaml` |
| `this run is missing N column(s)` | Partial file: ask for the full one. Real removal: `allow_column_removal: true` for one sync |
| `schema rejected ... unrecognized data type(s)` | If it's a real Postgres type, add it to `KNOWN_POSTGRES_TYPES` (`curate.py`) and `_TYPE_MAP` (`openmetadata/publish.py`); otherwise fix the file |
| `schema rejected ... duplicate column name(s)` / `have no name` | Fix the department's file |
| `full CREATE TABLE statement` / `table-level constraint` | Keep only the column lines |
| `Unknown category '...'` | `category:` must be `CAT-1`..`CAT-4`, or left blank — fix that line in `catalog.yaml` |
| `name(s) matching no column` (warning) | Typo in the metadata file; those rows were ignored |
| `Unrecognized Format value` (field dictionary) | Add a rule to `FORMAT_TYPE_RULES` in `field_dictionary_parser.py` |
| `ENVIRONMENT=... isn't allowed on branch '...'` | Each branch runs one environment: feature → local, `main` → development, `production` → production. Leave `ENVIRONMENT` blank in `.env`, or switch branch |
| `LOCAL_ONLY=1 refuses ...` | A `LOCAL_WASABI_...` / `LOCAL_OPENMETADATA_...` address points off this machine. Fix the address (local = MinIO on `localhost:9000` + local OpenMetadata), or delete `LOCAL_ONLY=1` from `.env` if you really mean to send local data to a remote server |
| `Couldn't lock ... held by` | Someone else is running sync. Wait; a dead run's lock frees itself after 15 minutes |
| `Can't reach the OpenMetadata server` | BIPP2 needs the office network or VPN; local needs `docker compose up -d` |
| `401` from OpenMetadata | Token expired: put a new one in `.env` |
| Wasabi `AccessDenied` / `InvalidAccessKeyId` | Check the Wasabi keys in `.env` |
| `Backup to '...' failed` | Your data is saved; run `python3 -m src.storage.backup copy` later |
| `No backup bucket set` (warning) | Set `WASABI_BACKUP_BUCKET` in `.env` (see [Backups](#backups)) |
| `already exists without Object Lock` | Use a new name for `WASABI_BACKUP_BUCKET` and run `setup` again |

---

## Reference

### Other commands

| I want to... | Command |
|---|---|
| See uploaded files | `python3 -m src.schema_registry.inputs list` |
| Upload a file without touching the catalog | `python3 -m src.schema_registry.inputs upload <file> inputs/<dept>/<dataset>/<file>` |
| Try one table without the catalog | `DEPARTMENT=pwd DATASET=vishwakarma TABLE_NAME=vishwakarma_T SOURCE_FILE=samples/x.txt SOURCE_FORMAT=postgres_ddl python3 -m src.schema_registry.pipeline` (add `DEPARTMENT_NAME="..."` the first time) |
| Republish one table | `TABLE_ID=pwd.vishwakarma.vishwakarma_t python3 -m src.schema_registry.openmetadata.publish` |
| Batch many tables from a manifest CSV | `MANIFEST_FILE=manifest.csv python3 -m src.schema_registry.batch` (add `OPENMETADATA_JWT_TOKEN` to publish each) |
| Republish everything that never reached OpenMetadata | `python3 -m src.schema_registry.republish` (reads `_lookups/runs.csv`; exit 1 if any still fail) |
| Backfill readable types into existing curated snapshots | `python3 -m src.schema_registry.backfill_readable [--dry-run] [--department <id>] [--exclude <table_id>] [--publish]` |
| Readable type not showing in OpenMetadata | Add `--recreate` (with `--publish`): backs the entity up under `_lookups/om_recreate_backups/`, hard-deletes and republishes only tables whose stored `dataTypeDisplay` is stale |
| Remove a (renamed/orphaned) table from OpenMetadata + the registry | `TABLE_ID=<id> python3 -m src.schema_registry.openmetadata.delete_table` (re-ingesting the id later brings it back) |
| See who ran what, and whether it published | `storage/_lookups/runs.csv` (one row per run, including failed ones) |
| Run all tests | `python3 -m pytest tests/` |
| Start OpenMetadata on your laptop | `cd ../infrastructure/openmetadata && docker compose up -d`, then http://localhost:8585 |

`SOURCE_FILE` and metadata files can be a path on your laptop or `storage:<key>` for a file in storage.

### Environment variables for the direct commands

The `pipeline` / `batch` / `publish` / `republish` commands read their
arguments from the environment (the `add` + `sync` flow above doesn't need
these):

| Key | Required? | Notes |
|---|---|---|
| `OPENMETADATA_JWT_TOKEN` | only when publishing | Settings → Bots → ingestion-bot → generate a token (never an admin session token: those expire in ~1hr and carry full admin rights) |
| `DEPARTMENT` | yes | must already be registered |
| `DATASET` | yes | auto-creates on first use |
| `TABLE_NAME` | yes | |
| `SOURCE_FILE` | yes | |
| `SOURCE_FORMAT` | yes | `postgres_ddl` or `csv` |
| `WASABI_BUCKET` | no | filled automatically: `LOCAL_WASABI_BUCKET` (local MinIO on feature branches), the company bucket on `main`/`production` (which needs it in `.env`) |
| `CATEGORY`/`API_AVAILABLE`/`OWNER`/`FREQUENCY`/`TIMELINE`/`DATASET_DESCRIPTION` | no | dataset-level fields — type a real value only once you have it; blank/omitted carries forward whatever was last set, so these rarely need touching after the first time |
### Where files are stored

Same layout in each Wasabi folder (`local/`, `dev/`, `prod/`) and in the backup bucket (without `_locks/`):

```
inputs/<dept>/<dataset>/<file>                      files uploaded with `add`
_lookups/departments.csv, datasets.csv, tables.csv   lists of departments, datasets, tables; runs.csv = one row per run (with publish_status)
department/<dept>/<dataset>/<table>/
    raw/source/<time>__<file>                        the exact file used, + .sha256
    raw/schemas/<time>.csv                           columns as read from the file
    curated/schemas/<time>.csv                       + descriptions, tags, classification, readable type, unit
    diffs/<time>.csv                                 what this run added/removed/changed vs the previous snapshot
department/<dept>/<dataset>/_source/                 a multi-table field dictionary
_locks/                                              stops two people writing at once
```

Every run adds new files with the time in the name, so the full history stays. OpenMetadata always gets the newest.

### How it looks in OpenMetadata

| Ours | In OpenMetadata |
|---|---|
| Department (`pwd`) | Database service. Its name is the id (`pwd`); the full department name from the catalog is shown as its display name |
| Dataset (`vishwakarma`) | Database: description, category tag, and owner / steward / frequency / timeline / API as custom properties |
| `schema:` (default `public`) | Schema |
| Table | Table: columns with a plain-language type (`dataTypeDisplay`, e.g. `Decimal Number (INR)`), descriptions, plus an `extraMetadata` custom property: JSON with the column details not shown elsewhere (nullable, default, scale, unit, ...) and the curated file it came from, kept for later use |
| Column tags | `FieldTag` (Financial, Geospatial, ...), `DataSensitivity` (CAT-1 to CAT-4), `BusinessGlossary` terms |

- Columns whose names look like personal data (Aadhaar, PAN, mobile, email, ...) get CAT-3 automatically, unless the metadata file says otherwise.
- `sync` also does the one-time OpenMetadata setup (custom properties) on its own.

### Known limits

- Renaming or removing a table leaves the old one in OpenMetadata: `TABLE_ID=<id> python3 -m src.schema_registry.openmetadata.delete_table` removes it there and marks the registry row deleted (re-ingesting the id brings it back).
- A renamed column needs `allow_column_removal`, and its description doesn't carry over.
- OpenMetadata 2.0.2 ignores a changed `dataTypeDisplay` on an existing column whose type is unchanged; `backfill_readable --publish --recreate` hard-deletes and republishes the table (with a backup in storage) to make a later readable type visible.
- Columns marked `active: false` are still published.
- Personal-data detection misses many names (e.g. `bride_name`, `groom_dob`, `account_no`). Check sensitive tables by hand.
- Numeric precision/scale (e.g. `numeric(10,2)`) is kept in the curated file for Postgres column lists only, and isn't sent to OpenMetadata.
- Each locked write to Wasabi takes about 3 seconds, so a big sync takes a few minutes.
- `vishwakarma_T` is a temporary table name (PWD's file had none). Change it in `catalog.yaml` once PWD confirms it.
- `source_format="csv"` won't guess semantically-inverted columns (e.g. `Required` vs `Nullable`) — add a mapping in `parsers/csv_schema_parser.py` if needed.
- `publish_table()` ignores the curated `active` flag — a column marked inactive still gets published like any other.
- OpenMetadata's PUT merges tags/extension instead of replacing them by default — so does a Table's PUT, one level down, for each column's tags. Both are patched explicitly right after the PUT (JSON-Patch `replace` on the Database's `tags`/`extension`/`owners`, `add` on every `/columns/{i}/tags`), which is what makes a cleared `category`, custom property or column `tag`/`classification` actually clear instead of staying stuck.
- The run log (`_lookups/runs.csv`) is a flat CSV, not a queryable store — one row per run is enough for "what happened and is it in OpenMetadata?", but cross-run analytics would want a real table (and `_lookups/*.csv`'s file locking only covers single-machine runs).

---

## For developers

| Code | What it does |
|---|---|
| `src/schema_registry/add.py` | `add`: upload + catalog entry |
| `src/schema_registry/sync.py` | `sync` |
| `src/schema_registry/catalog.py` | Reads and checks `catalog.yaml` |
| `src/schema_registry/pipeline.py` | One table: read → check → store (`run()`) |
| `src/schema_registry/inputs.py` | Upload/list files, read `storage:` files, archive originals |
| `src/schema_registry/parsers/` | Readers for Postgres column lists, CSV, field dictionaries |
| `src/schema_registry/curate.py` | Checks types and names, adds automatic tags and classification |
| `src/schema_registry/openmetadata/publish.py` | Sends one table to OpenMetadata |
| `src/schema_registry/registry/` | Department/dataset/table lists, and folder layout |
| `src/storage/` | Wasabi storage, plus locking |
| `src/storage/backup.py` | Backup bucket: setup, copy, verify, restore |
| `src/utils/config.py` | Reads `.env`, picks the environment from the git branch |
| `src/utils/cli.py` | The error box and log file for every command |

**Which parser reads which file** is decided in one place: `parse_source()` in `pipeline.py`. Most departments use the shared parser for their `format:` (`postgres_ddl` or `csv`); `agri_dept` has its own (`parsers/agriculture_parser.py`), which picks its table's block out of a one-file-many-tables submission and falls back to the shared parser for anything else.

**A department sends a file in a new layout?**
1. Write `parsers/<dept>_parser.py` with `parse_table(text, table_name)` returning the usual column fields (`name`, `data_type`, `length`, `scale`, `nullable`, `default`).
2. Add a branch for that department in `parse_source()` (see its docstring).
3. Add a test with a real example file.

If one file holds several tables, list each table in `catalog.yaml` with the **same** `source:`, and let the parser pick out each table by name.
