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
| 1. Upload the file and update the catalog | `ENVIRONMENT=development python3 -m src.schema_registry.add <file> --department <dept> --dataset <dataset> --table <table>` |
| 2. Fill in dataset details, commit `catalog.yaml`, open a PR, merge | git |
| 3. Store and publish | `ENVIRONMENT=development python3 -m src.schema_registry.sync` |

The backup runs on its own at the end of steps 1 and 3.

**Once a month:** `python3 -m src.storage.backup verify` to check the backup is complete.

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

One line in `.env` decides where everything goes:

```
ENVIRONMENT=local        # local | development | production
```

| `ENVIRONMENT` | Files go to | OpenMetadata |
|---|---|---|
| `local` (default) | `storage/` folder on your laptop (never Wasabi) | `LOCAL_OPENMETADATA_...` (your laptop) |
| `development` | Wasabi, folder `dev/` | `DEV_OPENMETADATA_...` (BIPP2, 10.0.96.105; needs office network or VPN) |
| `production` | Wasabi, folder `prod/` | `PROD_OPENMETADATA_...` (not set up yet) |

**Which branch may use which environment** (enforced: the command stops otherwise):

| Git branch | Allowed | Blocked |
|---|---|---|
| `main` | `development`, `production` | `local` |
| any other branch | `local`, `development` | `production` |

- Production data only comes from reviewed code on `main`. If git can't tell the branch, production is blocked.
- Try things on `local` first (on a feature branch). It can't change shared data.
- `development` and `production` refuse to run if `WASABI_BUCKET` is blank, so shared data never lands on one laptop by mistake.
- For one command only, put it in front: `ENVIRONMENT=local python3 -m src.schema_registry.sync`

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
ENVIRONMENT=development python3 -m src.schema_registry.add samples/pwd_vishwakarma_full_raw_columns.txt \
    --department pwd --dataset vishwakarma --table vishwakarma_T
```

**B: new department.** Add its full name (first time only):
```bash
ENVIRONMENT=development python3 -m src.schema_registry.add samples/cmsvy_applications.csv \
    --department samaj_kalyan --department-name "Department of Social Welfare" \
    --dataset cmsvy --table cmsvy_application
```

**C: with descriptions/tags.** Same as A or B, plus `--metadata`:
```bash
ENVIRONMENT=development python3 -m src.schema_registry.add samples/pwd_vishwakarma_full_raw_columns.txt \
    --department pwd --dataset vishwakarma --table vishwakarma_T \
    --metadata samples/pwd_vishwakarma_metadata.csv
```

**D: one file, many tables.** `--field-dictionary` instead of `--table`:
```bash
ENVIRONMENT=development python3 -m src.schema_registry.add samples/kanya_sumangla_field_dictionary.csv \
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
        frequency: monthly
        timeline: 2019-2026
        api_available: N           # Y or N
        description: Works and tenders managed by PWD
```

### Step 3: Check, then commit and open a PR

```bash
ENVIRONMENT=development python3 -m src.schema_registry.sync --dry-run
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
ENVIRONMENT=development python3 -m src.schema_registry.sync                    # all departments
ENVIRONMENT=development python3 -m src.schema_registry.sync --department pwd   # just one
```
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

**For production:** repeat step 1 and step 4 with `ENVIRONMENT=production` (on `main`). The catalog is already right.

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

### Dataset details (category, owner, frequency, timeline, api_available, description)

Edit them in `catalog.yaml` → PR → merge → `sync`. No new file or `add` needed.
- **Deleting a value in `catalog.yaml` clears it** in OpenMetadata. The catalog is the truth.
- **`category` must be at least as high as the most sensitive column** (e.g. not CAT-1 when a phone-number column is CAT-3), or publishing is refused. Only if those columns are removed before sharing, add `allow_category_below_columns: true` to the dataset.

### Rules

- **Don't edit data in the OpenMetadata UI.** The next `sync` overwrites it. Change the file or `catalog.yaml` instead.
- **Every change goes through `catalog.yaml` and a PR**, so we know what's on the server and who changed it.
- **Departments' files stay out of git.** They live in Wasabi.
- Old versions are never lost: Wasabi keeps every snapshot, and OpenMetadata keeps its own version history.

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
ENVIRONMENT=development python3 -m src.storage.backup setup --pipeline-user sda-pipeline --dry-run
# 3. Do it, and make a key for the pipeline user:
ENVIRONMENT=development python3 -m src.storage.backup setup --pipeline-user sda-pipeline --create-key
# 4. Put the printed key in .env (WASABI_ACCESS_KEY_ID / WASABI_SECRET_ACCESS_KEY).
#    It's shown only once. Keep the admin key out of .env.
# 5. First full copy, then check it:
ENVIRONMENT=development python3 -m src.storage.backup copy --all
ENVIRONMENT=development python3 -m src.storage.backup verify --all
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

These cover this `ENVIRONMENT`'s folder (`dev/` or `prod/`). Add `--all` for the whole bucket.

In the Wasabi console, the backup is its own bucket (`pwd-schema-registry-backup`, Frankfurt), with the same folders as the main one.

---

## Restoring

| What was lost | What to do |
|---|---|
| **OpenMetadata** (server wiped or new) | `ENVIRONMENT=development python3 -m src.schema_registry.sync --publish-only` (quick: republish what's in Wasabi), or plain `sync` (full: from `catalog.yaml`) |
| **One file** deleted or overwritten by mistake | Wasabi console → the bucket → turn on "Show Versions" → restore the older version |
| **Many files or a whole folder** in Wasabi | `python3 -m src.storage.backup restore`, then `sync` |

All of these are safe to run more than once.

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
| `not found in storage -- upload it first` | Run `add` for that file in this ENVIRONMENT (e.g. added in development but not yet in production) |
| `isn't in catalog.yaml yet -- add --department-name` | New department: add `--department-name "..."` |
| `unknown key(s)` / `must be CAT-1 ... CAT-4` | Fix that line in `catalog.yaml` |
| `this run is missing N column(s)` | Partial file: ask for the full one. Real removal: `allow_column_removal: true` for one sync |
| `schema rejected ... unrecognized data type(s)` | If it's a real Postgres type, add it to `KNOWN_POSTGRES_TYPES` (`curate.py`) and `_TYPE_MAP` (`openmetadata/publish.py`); otherwise fix the file |
| `schema rejected ... duplicate column name(s)` / `have no name` | Fix the department's file |
| `full CREATE TABLE statement` / `table-level constraint` | Keep only the column lines |
| `dataset category is CAT-x but column(s) ... are CAT-y` | Set `category:` to at least CAT-y in `catalog.yaml` |
| `name(s) matching no column` (warning) | Typo in the metadata file; those rows were ignored |
| `Unrecognized Format value` (field dictionary) | Add a rule to `FORMAT_TYPE_RULES` in `field_dictionary_parser.py` |
| `ENVIRONMENT=production isn't allowed on branch '...'` | Merge your PR, `git checkout main && git pull`, then run it |
| `ENVIRONMENT=local isn't allowed on branch 'main'` | On `main` use `development` or `production` |
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
| Run all tests | `python3 -m pytest tests/` |
| Start OpenMetadata on your laptop | `cd ../infrastructure/openmetadata && docker compose up -d`, then http://localhost:8585 |

`SOURCE_FILE` and metadata files can be a path on your laptop or `storage:<key>` for a file in storage.

### Where files are stored

Same layout in `storage/` (local), in Wasabi (`dev/`, `prod/`) and in the backup bucket (without `_locks/`):

```
inputs/<dept>/<dataset>/<file>                      files uploaded with `add`
_lookups/departments.csv, datasets.csv, tables.csv   lists of departments, datasets, tables
department/<dept>/<dataset>/<table>/
    raw/source/<time>__<file>                        the exact file used, + .sha256
    raw/schemas/<time>.csv                           columns as read from the file
    curated/schemas/<time>.csv                       + descriptions, tags, classification
department/<dept>/<dataset>/_source/                 a multi-table field dictionary
_locks/                                              stops two people writing at once
```

Every run adds new files with the time in the name, so the full history stays. OpenMetadata always gets the newest.

### How it looks in OpenMetadata

| Ours | In OpenMetadata |
|---|---|
| Department (`pwd`) | Database service |
| Dataset (`vishwakarma`) | Database: description, category tag, and owner / frequency / timeline / API as custom properties |
| `schema:` (default `public`) | Schema |
| Table | Table: columns, types, descriptions |
| Column tags | `FieldTag` (Financial, Geospatial, ...), `DataSensitivity` (CAT-1 to CAT-4), `BusinessGlossary` terms |

- Columns whose names look like personal data (Aadhaar, PAN, mobile, email, ...) get CAT-3 automatically, unless the metadata file says otherwise.
- `sync` also does the one-time OpenMetadata setup (custom properties) on its own.

### Known limits

- Renaming or removing a table leaves the old one in OpenMetadata. Delete it there by hand.
- A renamed column needs `allow_column_removal`, and its description doesn't carry over.
- Columns marked `active: false` are still published.
- Personal-data detection misses many names (e.g. `bride_name`, `groom_dob`, `account_no`). Check sensitive tables by hand.
- Numeric precision/scale (e.g. `numeric(10,2)`) is kept in the curated file for Postgres column lists only, and isn't sent to OpenMetadata.
- Each locked write to Wasabi takes about 3 seconds, so a big sync takes a few minutes.
- `vishwakarma_T` is a temporary table name (PWD's file had none). Change it in `catalog.yaml` once PWD confirms it.

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
| `src/storage/` | Local folder or Wasabi, plus locking |
| `src/storage/backup.py` | Backup bucket: setup, copy, verify, restore |
| `src/utils/config.py` | Reads `.env`, applies `ENVIRONMENT` and the branch rule |
| `src/utils/cli.py` | The error box and log file for every command |

**Which parser reads which file** is decided in one place: `parse_source()` in `pipeline.py`. Today every department uses the shared parser for its `format:` (`postgres_ddl` or `csv`).

**A department sends a file in a new layout?**
1. Write `parsers/<dept>_parser.py` with `parse_table(text, table_name)` returning the usual column fields (`name`, `data_type`, `length`, `scale`, `nullable`, `default`).
2. Add a branch for that department in `parse_source()` (see its docstring).
3. Add a test with a real example file.

If one file holds several tables, list each table in `catalog.yaml` with the **same** `source:`, and let the parser pick out each table by name.
