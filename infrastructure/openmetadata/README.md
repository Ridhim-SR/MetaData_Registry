# OpenMetadata Infrastructure

Docker Compose setup for a local **OpenMetadata** instance used as the metadata
source of truth by the monorepo (`apps/api` FastAPI service and `apps/web` UI).

This directory is infrastructure only. It is **not** part of the `apps/*`
workspaces and does not contain application code.

## What it runs

The compose file is the official OpenMetadata quickstart stack, pinned to
**2.0.2** (copied verbatim from
`open-metadata/OpenMetadata` -> `docker/docker-compose-quickstart/docker-compose.yml`).

| Service                | Image                                              | Purpose                                        |
| ---------------------- | -------------------------------------------------- | ---------------------------------------------- |
| `openmetadata_mysql`   | `docker.getcollate.io/openmetadata/db:2.0.2`      | MySQL database storing OpenMetadata metadata   |
| `openmetadata_elasticsearch` | `docker.elastic.co/elasticsearch/elasticsearch:9.3.0` | Search backend (Elasticsearch)            |
| `execute_migrate_all`  | `docker.getcollate.io/openmetadata/server:2.0.2`  | One-shot DB migration bootstrap               |
| `openmetadata_server`  | `docker.getcollate.io/openmetadata/server:2.0.2`  | OpenMetadata server (UI + REST API, port 8585) |
| `openmetadata_ingestion` | `docker.getcollate.io/openmetadata/ingestion:2.0.2` | Airflow-based ingestion engine (port 8080)  |

> Note: the current official OpenMetadata compose uses **Elasticsearch** as the
> search backend (OpenMetadata migrated away from OpenSearch). This is an
> internal detail of OpenMetadata and does not affect the FastAPI integration,
> which only talks to the REST API on port 8585.

## Start

```bash
# from the repo root, or:
docker compose -f infrastructure/openmetadata/docker-compose.yml up -d --wait
```

`--wait` blocks until all services report healthy, so the server is actually
ready to accept API requests before `npm run dev` proceeds.

To start the whole dev environment (OpenMetadata + apps):

```bash
npm run dev
```

## Ports

| Port | Service                                |
| ---- | -------------------------------------- |
| 8585 | OpenMetadata UI and REST API (`/api/v1`) |
| 8586 | OpenMetadata admin/healthcheck port     |
| 8080 | Airflow / ingestion webserver          |
| 9200 | Elasticsearch                          |
| 3306 | MySQL (OpenMetadata metadata DB)       |

## Access

- OpenMetadata UI: <http://localhost:8585>
- REST API: <http://localhost:8585/api/v1>
- Default admin user: `admin@open-metadata.org` / `admin`

The FastAPI backend (`apps/api`) reads these settings from environment
variables (see `apps/api/src/openmetadata/config.py`), defaulting to
`OPENMETADATA_HOST=http://localhost:8585`, `OPENMETADATA_USERNAME=admin@open-metadata.org`,
`OPENMETADATA_PASSWORD=admin` — so the defaults line up with this local stack.

## Configuration

All OpenMetadata settings in the compose file can be overridden via environment
variables (e.g. `DB_USER`, `DB_USER_PASSWORD`, `ELASTICSEARCH_HOST`,
`OPENMETADATA_SERVER_IMAGE`). No secrets are hardcoded in this repository.

## Data persistence

- MySQL data is stored under `./docker-volume/db-data` (git-ignored).
- Elasticsearch data is stored in the named volume `es-data`.

## Stop / teardown

```bash
docker compose -f infrastructure/openmetadata/docker-compose.yml down
# remove data volumes too:
docker compose -f infrastructure/openmetadata/docker-compose.yml down -v
```
