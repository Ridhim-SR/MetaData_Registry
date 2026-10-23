# Data ingest API

One call takes a department's raw file and does the whole flow: draft descriptions and tags, store the file,
update `catalog.yaml`, publish to OpenMetadata, back up. It is the same as running `add` and then `sync` from
`data_services`, without the terminal.

## Run

```
cd apps/data-ingest
pip install -r requirements.txt
uvicorn main:app --port 4200
```

Docs and a try-it-out form: http://localhost:4200/docs (click **Try it out**).

Run exactly **one worker**. `catalog.yaml` is serialized across processes with a file lock, and every write is
atomic (temp file + replace), but a second worker would still queue behind a slow ingest.

## Which environment it uses

The git branch decides, same rule as the CLI: `main` is development, `production` is production, any other
branch is local. `GET /v1/status` shows the environment, bucket, folder, OpenMetadata host and whether the
configured token has expired. It needs `X-API-Key` when `INGEST_API_KEY` is set.

In `development` or `production`, an ingest that should publish is refused with `503` when
`OPENMETADATA_JWT_TOKEN` is missing: silently returning success while only writing to storage is not useful.
Use `run_sync=false` for a storage-only step. In `local`, a missing client is reported as `published: false`
and `publish: skipped`.

## The call

`POST /v1/ingest` (`multipart/form-data`)

| Field | Required | Example |
|---|---|---|
| `department` | yes | `pwd` |
| `dataset` | yes | `vishwakarma` |
| `table` | yes, unless `field_dictionary=true` | `vishwakarma_T` |
| `file` | yes | the department's raw file: `.csv`, `.xlsx`/`.xlsm`/`.xltx`, or Postgres DDL (`.txt`/`.sql`) |
| `field_dictionary` | no | `true`: the file describes several tables of the dataset (leave `table` out) |
| `department_name` | first time for a department only | `Public Works Department` |
| `category`, `description`, `owner`, `steward`, `frequency`, `timeline` | no | `CAT-3`, `Works managed by PWD` |
| `api_available` | no | `Y` or `N` |
| `schema` | no | database schema name (default `public`) |
| `allow_column_removal` | no | `true`: accept a new file that drops columns |
| `metadata` | no | the department's own metadata CSV (`name,business_description,tag`); replaces Claude drafting |
| `sheet` | no | worksheet name for an `.xlsx` upload (default: the widest sheet with a header) |
| `dry_run` | no | `true` parses and validates the file and shows what would change; writes nothing |
| `run_sync` | no | `false` = only upload and update `catalog.yaml` (the `add` command); default `true` |

Excel workbooks are reduced to the registry's column CSV. ASCII headings become snake_case names; a heading
with no ASCII spelling is kept as the column's Hindi label. The original workbook is kept under
`inputs/<department>/<dataset>/_original/`. A legacy `.xls` is refused with a message to save it as `.xlsx`.

Header on every call that changes data: `X-Confirm-Environment: <environment from /v1/status>`.
If `INGEST_API_KEY` is set, also send `X-API-Key`. Production refuses to start without it.
Uploads are capped at `INGEST_MAX_UPLOAD_BYTES` (default 25 MiB).

```
curl -X POST localhost:4200/v1/ingest \
  -H "X-Confirm-Environment: development" \
  -F department=pwd -F dataset=vishwakarma -F table=vishwakarma_T \
  -F category=CAT-3 -F file=@pwd_vishwakarma_full_raw_columns.txt
```

Same call for every case: a new table in an existing dataset, a new dataset in an existing department, a
new department (add `department_name`), or a changed file for an existing table.

## Add and sync as two steps (like the commands)

Send `run_sync=false` to only upload the file and update `catalog.yaml` (the `add` command). Review and
commit `catalog.yaml`, then publish with the second call:

`POST /v1/sync` (form fields, all optional)

| Field | Meaning |
|---|---|
| `department` | only this department (default: every department in `catalog.yaml`) |
| `dry_run` | `true` shows what would be stored and published, writes nothing |
| `publish_only` | `true` republishes what is already stored, ingests nothing |
| `reclassify` | `true` re-derives classification/tag from the current rules (needs `department`) |

Same `X-Confirm-Environment` header. The answer lists every table with `store` and `publish`.

```
curl -X POST localhost:4200/v1/ingest -H "X-Confirm-Environment: local" \
  -F department=pwd -F dataset=vishwakarma -F table=vishwakarma_T -F run_sync=false -F file=@raw.txt
curl -X POST localhost:4200/v1/sync -H "X-Confirm-Environment: local" -F department=pwd
```

## Answers

Every error uses the same top-level shape: `{"problem": "...", "fix": "...", ...}`. FastAPI's own validation
errors are flattened into it too, so a client needs one parser.

| Code | Meaning |
|---|---|
| 200 | done; `tables` shows `ingested` or `unchanged` per table, `published` says whether OpenMetadata was updated |
| 401 | missing or wrong `X-API-Key` (on `/v1/status` too) |
| 409 | environment header missing or wrong |
| 413 | the upload is larger than `INGEST_MAX_UPLOAD_BYTES`; nothing was stored |
| 422 | bad file, name or value; `catalog.yaml` and the previous input file are left as they were (`file_restored`) |
| 502 | stored but publishing failed (send the same call again), or drafting descriptions failed (nothing stored) |
| 503 | the API is not configured for this environment (for example no OpenMetadata token where one is required) |

A rejected update is transactional: the catalog, the stored input file and its metadata file are restored to
the last accepted version. A rejected *new* table can leave an unreferenced input object (storage has no
delete operation), but it never becomes part of `catalog.yaml`.

## Good to know

- One ingest runs at a time, because `catalog.yaml` is one file. Commit it afterwards.
- Descriptions are drafted by Claude only when `ANTHROPIC_API_KEY` is set; the MDSF s5.1 PII/Sensitive rules
  and the CAT-3 floor are applied after the model answers. An empty or malformed model reply is a `502`, not a
  silent empty metadata file.
- Dataset and table names may use letters, digits, `_`, `-` and spaces. Leading, trailing and repeated spaces
  are refused, as are two names that slugify to one id. Nothing is ever deleted.
- A multi-table file may be shared by several tables only when its bytes are unchanged (for example
  `agri_dept`'s one CSV that holds several tables). A different file with a colliding name is still refused.
- `/v1/status` decodes (but does not verify) the token to report `openmetadata_token_expires_at`. Refresh the
  token in `data_services/.env` and restart the API; the client is built once at startup.
- Tests: `pytest tests` from this folder (needs `requirements.txt` installed). CI runs this suite too.
