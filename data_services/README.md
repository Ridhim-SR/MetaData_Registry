# CSV → OpenMetadata Pipeline

Extracts new rows from a CSV (watermark-based), cleans/dedupes them, and
pushes them into OpenMetadata as table metadata + sample data.

## Services

| Service      | Purpose                          | Port |
|--------------|-----------------------------------|------|
| mysql        | OpenMetadata's backend DB         | 3306 |
| elasticsearch| OpenMetadata's search index       | 9200 |
| openmetadata | OpenMetadata server / UI          | 8585 |
| postgres     | Sample data source DB             | 5432 |
| ingestion    | Airflow (OpenMetadata ingestion)  | 8080 |
| csv-pipeline | This project — extract/transform/load | — |

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