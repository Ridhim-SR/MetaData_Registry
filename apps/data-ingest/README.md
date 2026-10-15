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

## Which environment it uses

The git branch decides, same rule as the CLI: `main` is development, `production` is production, any other
branch is local. `GET /v1/status` shows the environment, bucket, folder and OpenMetadata host.

## The call

`POST /v1/ingest` (`multipart/form-data`)

| Field | Required | Example |
|---|---|---|
| `department` | yes | `pwd` |
| `dataset` | yes | `vishwakarma` |
| `table` | yes | `vishwakarma_T` |
| `file` | yes | the department's raw file |
| `department_name` | first time for a department only | `Public Works Department` |
| `category`, `description`, `owner`, `steward`, `frequency`, `timeline` | no | `CAT-3`, `Works managed by PWD` |
| `api_available` | no | `Y` or `N` |
| `dry_run` | no | `true` shows what would change and writes nothing |
| `run_sync` | no | `false` = only upload and update `catalog.yaml` (the `add` command); default `true` |

Header on every call that changes data: `X-Confirm-Environment: <environment from /v1/status>`.
If `INGEST_API_KEY` is set, also send `X-API-Key`. Production refuses to start without it.

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

Same `X-Confirm-Environment` header. The answer lists every table with `store` and `publish`.

```
curl -X POST localhost:4200/v1/ingest -H "X-Confirm-Environment: local" \
  -F department=pwd -F dataset=vishwakarma -F table=vishwakarma_T -F run_sync=false -F file=@raw.txt
curl -X POST localhost:4200/v1/sync -H "X-Confirm-Environment: local" -F department=pwd
```

## Answers

| Code | Meaning |
|---|---|
| 200 | done; `tables` shows `ingested` or `unchanged` per table |
| 401 | missing or wrong `X-API-Key` |
| 409 | environment header missing or wrong |
| 422 | bad file, name or value; the body has `problem` and `fix`, and `catalog.yaml` is left as it was |
| 502 | stored but publishing failed (send the same call again), or drafting descriptions failed (nothing stored) |

## Good to know

- One ingest runs at a time, because `catalog.yaml` is one file. Commit it afterwards.
- Descriptions are drafted by Claude only when `ANTHROPIC_API_KEY` is set. Otherwise columns are stored without them.
- Dataset and table names may use letters, digits, `_`, `-` and spaces. Nothing is ever deleted.
- Tests: `pytest tests` from this folder (needs `requirements.txt` installed).
