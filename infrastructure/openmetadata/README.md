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
# one-time: create the local secrets file and set MYSQL_ROOT_PASSWORD
#   (compose refuses to start without it -- there is no default password)
cp infrastructure/openmetadata/.env.example infrastructure/openmetadata/.env

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

| Port | Service                                | Bound to |
| ---- | -------------------------------------- | -------- |
| 8585 | OpenMetadata UI and REST API (`/api/v1`) | all interfaces |
| 8586 | OpenMetadata admin/healthcheck port     | all interfaces |
| 8080 | Airflow / ingestion webserver          | all interfaces |
| 9200 | Elasticsearch                          | **127.0.0.1 only** |
| 9300 | Elasticsearch transport                | **127.0.0.1 only** |
| 3306 | MySQL (OpenMetadata metadata DB)       | **127.0.0.1 only** |

MySQL and Elasticsearch hold the same catalogue data as the API and must not be
reachable from other machines: only the OpenMetadata server (inside the compose
network) talks to them. Everything else goes through 8585.

## Access

- OpenMetadata UI: <http://localhost:8585>
- REST API: <http://localhost:8585/api/v1>
- Bootstrap admin user: `admin@open-metadata.org` / `admin` -- **change this
  password on first login** (Settings -> Users -> Admin -> Edit -> Password).
  It is how every OpenMetadata install boots; leaving it in place is what makes
  a stack with published ports trivially accessible.

The FastAPI backend (`apps/api`) reads these settings from environment
variables (see `apps/api/src/openmetadata/config.py`), defaulting to
`OPENMETADATA_HOST=http://localhost:8585`, `OPENMETADATA_USERNAME=admin@open-metadata.org`,
`OPENMETADATA_PASSWORD=admin` -- after changing the admin password above, put
the new one in `apps/api/.env` (or point the backend at a bot JWT instead).

### Hardening checklist (deployed stacks)

1. `cp .env.example .env` and set a generated `MYSQL_ROOT_PASSWORD`; compose
   will not start without it.
2. Change the bootstrap admin password immediately after the first login, and
   update `OPENMETADATA_PASSWORD` wherever it is consumed.
3. Self-signup is disabled (`AUTHENTICATION_ENABLE_SELF_SIGNUP=false`), so
   user accounts are created by an admin only.
4. MySQL/Elasticsearch stay bound to `127.0.0.1`; do not publish them on a
   public interface.
5. Pipelines authenticate with an **ingestion-bot JWT** (Settings -> Bots ->
   ingestion-bot -> Generate JWT), never with an admin session token or the
   admin password: `OPENMETADATA_JWT_TOKEN` in `data_services/.env`.

## Configuration

All OpenMetadata settings in the compose file can be overridden via environment
variables (e.g. `DB_USER`, `DB_USER_PASSWORD`, `ELASTICSEARCH_HOST`,
`OPENMETADATA_SERVER_IMAGE`). The one required variable is
`MYSQL_ROOT_PASSWORD`, set in this folder's `.env` (copy `.env.example`) --
compose aborts with a clear error if it is missing. No secrets are hardcoded
in this repository.

## Data persistence

- MySQL data is stored in the named volume `mysql-data` (not a Windows
  bind-mount — bind-mounting `./docker-volume/db-data` corrupts InnoDB on
  case-insensitive filesystems, crash-looping MySQL and failing
  `execute-migrate-all` on every run).
- Elasticsearch data is stored in the named volume `es-data`.
- Legacy `./docker-volume/db-data*` dirs (including `.bak-corrupt-*` /
  `.corrupt-*`) are local-only backups, git-ignored, and no longer mounted.

## Stop / teardown

```bash
docker compose -f infrastructure/openmetadata/docker-compose.yml down
# remove data volumes too:
docker compose -f infrastructure/openmetadata/docker-compose.yml down -v
```
