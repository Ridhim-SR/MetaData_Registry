# Schema Registry

This takes the column lists that departments send us (PWD, Samaj Kalyan, ...),
checks them, tags sensitive columns, keeps every version in storage, and puts
them into OpenMetadata.

Everything on the OpenMetadata server comes from scripts, never from clicking
in the UI. So if a server is wiped or a new one is set up, **one command
rebuilds it exactly**.

## How it works

```
Department's file ──upload──▶ Wasabi
                                │
catalog.yaml (in git) ──────────┤  "what should be in OpenMetadata"
                                ▼
                         sync command
             parse ─▶ check ─▶ store ─▶ publish to OpenMetadata
```

- **Wasabi** keeps the files: what departments sent, every processed version, and the list of departments and tables.
- **`catalog.yaml`** says what should be in OpenMetadata: departments, datasets, tables, and which file each table comes from. It's in git, so every change is reviewed.
- **`sync`** makes Wasabi and OpenMetadata match `catalog.yaml`. Running it again changes nothing.

## First-time setup

```bash
cd data_services
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # then fill in .env (see below)
```

Never commit `.env`. It holds passwords and keys.

## Choose where you work

One line in `.env` decides where everything goes:

```
ENVIRONMENT=local        # local | development | production
```

| `ENVIRONMENT` | Files go to | OpenMetadata used |
|---|---|---|
| `local` (default) | the `storage/` folder on your laptop. Never Wasabi | `LOCAL_OPENMETADATA_...` (your laptop) |
| `development` | Wasabi, folder `dev/` | `DEV_OPENMETADATA_...` (BIPP2, 10.0.96.105) |
| `production` | Wasabi, folder `prod/` | `PROD_OPENMETADATA_...` (not set up yet) |

- Use `local` to try things out. It can't change shared data.
- `development` and `production` stop with an error if `WASABI_BUCKET` is blank, so shared data never ends up on one laptop by mistake.
- To switch for one command only, put it in front: `ENVIRONMENT=development python3 -m src.schema_registry.sync`
- **Token:** in that server's OpenMetadata UI, go to Settings → Bots → ingestion-bot and copy the token into `.env`. Without a token, commands still save to storage but don't publish.

## Adding or updating a department's data

This is the normal way. Do it the same way every time.

**1. Run `add` with the department's file**
```bash
ENVIRONMENT=development python3 -m src.schema_registry.add samples/pwd_vishwakarma_full_raw_columns.txt \
    --department pwd --dataset vishwakarma --table vishwakarma_T
```
This does two things at once:
- uploads the file to Wasabi, at `dev/inputs/pwd/vishwakarma/<file name>`. You never pick or copy a path.
- adds the table to `catalog.yaml`, or points the existing entry at the new file.

It prints what it did:
```
  - uploaded samples/pwd_vishwakarma_full_raw_columns.txt -> inputs/pwd/vishwakarma/pwd_vishwakarma_full_raw_columns.txt
  - added table pwd/vishwakarma/vishwakarma_T
```

| Situation | Add to the command |
|---|---|
| First file of a **new department** | `--department-name "Full Department Name"` |
| A `.csv` file | nothing. The format is picked from the file name. Use `--format` to override |
| A file with descriptions/tags for the columns | `--metadata path/to/metadata.csv` |
| **One file describing several tables** (field dictionary) | `--field-dictionary` instead of `--table` |
| Table lives in another database schema | `--schema <name>` |

A department sends an **updated file**? Run the same `add` command again. Wasabi keeps the old version.

**2. Fill in the dataset's details** in `catalog.yaml` when you know them: `category` (CAT-1 to CAT-4), `owner`, `frequency`, ... `add` leaves them blank for a new dataset.

**3. Commit `catalog.yaml` and open a PR.** Get it reviewed and merged. If `add` says "catalog.yaml already up to date", there's nothing to commit.

**4. Run sync** (by hand, after the PR is merged. Nothing runs it automatically yet)
```bash
ENVIRONMENT=development python3 -m src.schema_registry.sync --dry-run          # see what would happen
ENVIRONMENT=development python3 -m src.schema_registry.sync                    # all departments
ENVIRONMENT=development python3 -m src.schema_registry.sync --department pwd   # just one
```
It prints a summary:
```
TABLE                          INGEST        PUBLISH        DETAIL
pwd.vishwakarma.vishwakarma_t  ingested      published      source file changed; 213 columns
```
- `unchanged`: the file is the same as last time, so it isn't processed again. It's still published, in case the server was wiped.
- `failed`: the reason is in DETAIL. Other tables carry on, and the command exits with an error so scripts notice.

Running all departments is fine: unchanged files are skipped, so only new work is done.

**5. Check it in OpenMetadata.**

**Going to production:** run the same `add` command with `ENVIRONMENT=production`. It uploads to `prod/`, and the catalog is already right. Then run `sync` with `ENVIRONMENT=production`.

## Rules

- **Don't change data in the OpenMetadata UI.** The next `sync` overwrites column tags and dataset details. Change the file or `catalog.yaml` instead.
- **Every change goes through `catalog.yaml` and a PR.** That's how we know what's on the server and who changed it.
- **Try things on `local` first.**
- **Departments' files stay out of git.** They're in Wasabi.

## Restoring a wiped server

```bash
ENVIRONMENT=development python3 -m src.schema_registry.sync                  # full: from catalog.yaml
ENVIRONMENT=development python3 -m src.schema_registry.sync --publish-only   # quick: republish everything already in Wasabi
```
Both are safe to run as often as you like.

## Other commands

| I want to... | Command |
|---|---|
| See uploaded files | `python3 -m src.schema_registry.inputs list` |
| Upload a file without touching the catalog | `python3 -m src.schema_registry.inputs upload <file> inputs/<dept>/<dataset>/<file>` |
| Try a single table without the catalog | `DEPARTMENT=pwd DATASET=vishwakarma TABLE_NAME=vishwakarma_T SOURCE_FILE=samples/x.txt SOURCE_FORMAT=postgres_ddl python3 -m src.schema_registry.pipeline` (add `DEPARTMENT_NAME="..."` the first time to register the department) |
| Republish one table | `TABLE_ID=pwd.vishwakarma.vishwakarma_t python3 -m src.schema_registry.openmetadata.publish` |
| Run all tests | `python3 -m pytest tests/` |
| Start OpenMetadata on your laptop | `cd ../infrastructure/openmetadata && docker compose up -d`, then log in at http://localhost:8585 |

`SOURCE_FILE` and metadata files can be a path on your laptop or `storage:<key>` for a file in Wasabi.

## What happens when you run again

- **Same file:** nothing changes in storage, and the same result goes to OpenMetadata.
- **New columns:** they're added.
- **Columns missing from the file:** the table stops with an error. This catches a department sending only part of the table. If they really removed columns, add `allow_column_removal: true` to that table in `catalog.yaml` for one sync, then remove it again.
- **Bad file** (unknown type, duplicate column name, a pasted `CREATE TABLE`): it's rejected and nothing is saved.
- **Descriptions and tags** come from a metadata file (`metadata:` in the catalog). A blank cell keeps the old answer; it never erases one.
- **Dataset category lower than its most sensitive column** (e.g. CAT-1 with a CAT-3 phone number column): publishing is refused. Raise the category. Only if those columns are removed before sharing, add `allow_category_below_columns: true` to the dataset.
- **Column tags** in OpenMetadata are set to exactly what the pipeline decided. Old ones are removed.

## When something fails

The error always names the exact problem. Fix the cause; don't bypass the check.

| Error says | What to do |
|---|---|
| `not found in storage -- upload it first` | Run `add` for that file in this ENVIRONMENT (e.g. it was added in development but not yet in production) |
| `isn't in catalog.yaml yet -- add --department-name` | First file of a new department: add `--department-name "..."` |
| `unknown key(s)` / `must be CAT-1 ... CAT-4` | Fix that line in `catalog.yaml` |
| `this run is missing N column(s)` | Partial file: ask the department for the full one. Real removal: `allow_column_removal: true` for one sync |
| `schema rejected ... unrecognized data type(s)` | If it's a real Postgres type, add it to `KNOWN_POSTGRES_TYPES` (`curate.py`) and `_TYPE_MAP` (`openmetadata/publish.py`); otherwise fix the file |
| `schema rejected ... duplicate column name(s)` / `have no name` | Fix the department's file |
| `full CREATE TABLE statement` / `table-level constraint` | Keep only the column lines, without `CREATE TABLE` or `CONSTRAINT` lines |
| `dataset category is CAT-x but column(s) ... are CAT-y` | Set `category:` to at least CAT-y in `catalog.yaml` |
| `name(s) matching no column` (warning) | Typo in the metadata file. Those rows were ignored |
| `Unrecognized Format value` (field dictionary) | Add one rule to `FORMAT_TYPE_RULES` in `field_dictionary_parser.py` |
| `Couldn't lock ... held by` | Someone else is running sync. Wait, or if their run died, it frees itself after 15 minutes |
| `401` from OpenMetadata | Token expired: get a new one into `.env` |
| Wasabi `AccessDenied` / `InvalidAccessKeyId` | Check the Wasabi keys in `.env` |

## Where files are stored

Same layout on your laptop (`storage/`) and in Wasabi (`dev/`, `prod/`):

```
inputs/<dept>/<dataset>/<file>              files uploaded with `add`
_lookups/departments.csv, datasets.csv, tables.csv   list of departments, datasets, tables
department/<dept>/<dataset>/<table>/
    raw/source/<time>__<file>               the exact file used, + .sha256
    raw/schemas/<time>.csv                  columns as read from the file
    curated/schemas/<time>.csv              + descriptions, tags, classification
department/<dept>/<dataset>/_source/        a multi-table field dictionary, once per dataset
_locks/                                     stops two people writing at the same time
```

Every run adds new files with a time in the name. Nothing is overwritten, so the full history stays. OpenMetadata always gets the newest version.

## How it looks in OpenMetadata

| Ours | In OpenMetadata |
|---|---|
| Department (`pwd`) | Database service. Created once |
| Dataset (`vishwakarma`) | Database: description, category tag, and owner / frequency / timeline / API as custom properties |
| `schema:` (default `public`) | Schema. Created once |
| Table | Table: columns, types, descriptions |
| Column tags | `FieldTag` (Financial, Geospatial, ...), `DataSensitivity` (CAT-1 to CAT-4), `BusinessGlossary` terms |

Columns whose names look like personal data (Aadhaar, PAN, mobile, email, ...) get CAT-3 automatically, unless the metadata file says otherwise.

`sync` also does the one-time OpenMetadata setup (the custom properties) on its own.

## Known limits

- Renaming or removing a table leaves the old one in OpenMetadata. Delete it there by hand.
- A renamed column counts as one removed plus one added, so it needs `allow_column_removal`, and its description doesn't carry over.
- Columns marked `active: false` are still published.
- Personal-data detection misses many names (e.g. `bride_name`, `groom_dob`, `account_no`). Check sensitive tables by hand.
- Each locked write to Wasabi takes about 3 seconds, so a big sync takes a few minutes.
- `vishwakarma_T` is a temporary table name. PWD's file had no table name. Change it in `catalog.yaml` once PWD confirms it.

## For developers

| Code | What it does |
|---|---|
| `src/schema_registry/add.py` | The `add` command: upload + catalog entry |
| `src/schema_registry/sync.py` | The `sync` command |
| `src/schema_registry/catalog.py` | Reads and checks `catalog.yaml` |
| `src/schema_registry/pipeline.py` | One table: parse → check → store (`run()`) |
| `src/schema_registry/inputs.py` | Upload/list files, read `storage:` files, archive originals |
| `src/schema_registry/parsers/` | Readers for Postgres column lists, CSV, field dictionaries |
| `src/schema_registry/curate.py` | Checks types and names, adds automatic tags and classification |
| `src/schema_registry/openmetadata/publish.py` | Sends one table to OpenMetadata |
| `src/schema_registry/registry/` | Department/dataset/table lists, and folder layout |
| `src/storage/` | Laptop folder or Wasabi, plus locking |
| `src/utils/config.py` | Reads `.env` and applies `ENVIRONMENT` |

**Which parser reads which file** is decided in one place: `parse_source()` in `pipeline.py`. Today every department uses the shared parser for its `format:` (`postgres_ddl` or `csv`).

**A department sends a file in a new layout?**
1. Write `parsers/<dept>_parser.py` with `parse_table(text, table_name)` returning the usual column fields (`name`, `data_type`, `length`, `scale`, `nullable`, `default`).
2. Add a branch for that department in `parse_source()` (there's an example in its docstring).
3. Add a test with a real example file.

If one file holds several tables, list each table in `catalog.yaml` with the **same** `source:`, and let the parser pick out each table by name.

## Step by step: putting a department's file into OpenMetadata

Follow the steps **in order**. In step 2 you run **only one** of the four commands: the one that matches your file.

**Step 1: Open the project** (every new terminal)
```bash
cd data_services
source .venv/bin/activate
```
First time on this machine? Do [First-time setup](#first-time-setup) before this.

**Step 2: Run `add`. Pick the ONE case that fits:**

| Your situation | Use |
|---|---|
| Department is already in `catalog.yaml` (e.g. PWD), one file = one table | Case A |
| Department is **not** in `catalog.yaml` yet | Case B |
| You also have a file with descriptions/tags for the columns | Case C |
| One file describes **several tables** (a field dictionary) | Case D |

Replace the file name, department, dataset and table with your own. The ones below are examples.

*Case A: existing department, one table* (also for an **updated** file: same command again)
```bash
ENVIRONMENT=development python3 -m src.schema_registry.add samples/pwd_vishwakarma_full_raw_columns.txt \
    --department pwd --dataset vishwakarma --table vishwakarma_T
```

*Case B: new department.* Same as A, plus its full name (only needed the first time):
```bash
ENVIRONMENT=development python3 -m src.schema_registry.add samples/cmsvy_applications.csv \
    --department samaj_kalyan --department-name "Department of Social Welfare" \
    --dataset cmsvy --table cmsvy_application
```

*Case C: with a descriptions/tags file.* Same as A or B, plus `--metadata`:
```bash
ENVIRONMENT=development python3 -m src.schema_registry.add samples/pwd_vishwakarma_full_raw_columns.txt \
    --department pwd --dataset vishwakarma --table vishwakarma_T \
    --metadata samples/pwd_vishwakarma_metadata.csv
```

*Case D: one file, many tables.* Use `--field-dictionary` instead of `--table`:
```bash
ENVIRONMENT=development python3 -m src.schema_registry.add samples/kanya_sumangla_field_dictionary.csv \
    --department samaj_kalyan --department-name "Department of Social Welfare" \
    --dataset cmsvy --field-dictionary
```

`add` prints what it did. If it says *"catalog.yaml already up to date"*, skip to step 4.

**Step 3: Fill in the dataset details** (new dataset, or when something changed)

Open `catalog.yaml`, find your dataset, and fill in what you know (leave the rest blank):
```yaml
      vishwakarma:
        category: CAT-3            # CAT-1 | CAT-2 | CAT-3 | CAT-4
        owner: PWD IT Cell
        frequency: monthly
        timeline: 2019-2026
        api_available: N           # Y or N
        description: Works and tenders managed by PWD
```

**Step 4: Check before you commit**
```bash
ENVIRONMENT=development python3 -m src.schema_registry.sync --dry-run
```
Every table should show `would ingest` or `unchanged`, with `0 failed`. If something shows `failed`, fix it first (see [When something fails](#when-something-fails)).

**Step 5: Commit `catalog.yaml` and open a PR**
```bash
git add catalog.yaml
git commit -m "PWD: new vishwakarma file"
git push
```
Then open the PR on GitHub and get it reviewed and merged.

**Step 6: After the PR is merged, run sync yourself** (nothing runs automatically on merge)
```bash
ENVIRONMENT=development python3 -m src.schema_registry.sync
```
You should see `ingested` (or `unchanged`) and `published`, with `0 failed`. To publish, you need the office network or VPN for BIPP2. Without it, PUBLISH shows `failed`.

**Step 7: Check in OpenMetadata.** Open http://10.0.96.105:8585 and find your table under the department's service.

For production: repeat **step 2 and step 6** with `ENVIRONMENT=production`.
