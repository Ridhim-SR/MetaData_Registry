# Government Data Catalog

Monorepo for a department-wise **metadata catalog**: government departments POST
dataset *metadata* (name, description, columns — never raw data) through our
FastAPI backend, which stores it in **OpenMetadata** via the official Python SDK.
The frontend never talks to OpenMetadata directly.

```
apps/web (React + Vite) ──► apps/api (FastAPI, :8000) ──► OpenMetadata (:8585)
                                                             ├─ MySQL (metadata store)
                                                             └─ Elasticsearch (search index)
```

One service per department (e.g. `gov_agriculture`, `gov_health` — ~12 total),
one database inside each, datasets as schemas → tables:

```
gov_agriculture.agriculture.farmer_register.farmer_register
│               │           │                │
│               │           │                └── Table (= dataset)
│               │           └── Schema (= dataset grouping)
│               └── Database (= department)
└── Service (= department bucket)
```

## Repo layout

| Path | What it is |
|---|---|
| `apps/api` | FastAPI backend (Python, venv at `apps/api/.venv`). Routers in `src/routers/`, OM code in `src/openmetadata/` |
| `apps/web` | React 19 + Vite + Tailwind frontend |
| `data_services/` | Reserved for future data pipelines (Airflow DAGs). Not used yet |
| `infrastructure/openmetadata/` | Docker Compose stack for local OpenMetadata (server **2.0.2**, MySQL, Elasticsearch). See its own `README.md` |
| `package.json` / `turbo.json` | Monorepo orchestration (`apps/*` workspaces) |

## The metadata pipeline (current scope)

Single endpoint, metadata-only:

```
POST /openmetadata/metadata/tables
```

Flow: Pydantic validation → official SDK (`service.py`) → find-or-create
Service → Database → Schema → create-or-update Table → returns
`{success, message, data: {name, fully_qualified_name, id}}`.
Repeating the same payload updates instead of duplicating (same `id` back).

Example body:

```json
{
  "name": "crop_production",
  "display_name": "Crop Production Statistics",
  "description": "District-wise crop production statistics",
  "database_service": "government_data",
  "database": "agriculture",
  "database_schema": "public",
  "columns": [
    {"name": "district", "data_type": "VARCHAR", "description": "Name of the district"},
    {"name": "crop", "data_type": "VARCHAR", "description": "Name of the crop"},
    {"name": "year", "data_type": "INT", "description": "Year of production"},
    {"name": "production", "data_type": "DECIMAL", "description": "Total crop production"}
  ]
}
```

## Prerequisites

- Node.js + npm 11, Python with venv at `apps/api/.venv` (deps installed)
- Docker Desktop running
- Free ports: `8000` (API), `8585` (OM), `9200` (ES), `3306` (MySQL)

## Run the project

From the repo root:

```powershell
npm run dev
```

This starts OpenMetadata (`--wait` until healthy) plus all apps via turbo.
Individual pieces:

```powershell
# OpenMetadata only
npm run dev:openmetadata

# Apps only (from root)
npm run dev:apps

# Backend only (from apps/api) — token required, see below
npm run dev     # with --reload
npm start       # without reload
```

### Backend token (required)

The backend authenticates to OpenMetadata with a JWT — get one, then start the backend **in the same terminal**:

```powershell
# 1. Log in (returns accessToken, valid ~1h)
curl.exe -X POST http://localhost:8585/api/v1/users/login `
  -H "Content-Type: application/json" `
  -d '{"email":"admin@open-metadata.org","password":"YWRtaW4="}'

# 2. Export + start (from apps/api)
$env:OPENMETADATA_JWT_TOKEN="paste-accessToken-here"
.\.venv\Scripts\python.exe -m uvicorn src.main:app --port 8000
```

For a long-lived token use the UI: `http://localhost:8585` → Settings → Bots → `ingestion-bot`.

### Health checks

```powershell
docker ps --format "{{.Names}} {{.Status}}"          # all OM containers (healthy)
curl.exe http://localhost:8585/api/v1/system/version  # {"version":"2.0.2",...}
```

- OpenMetadata UI: http://localhost:8585 (admin / admin)
- API docs (Swagger): http://localhost:8000/docs

### Test the pipeline

```bash
curl -X POST http://localhost:8000/openmetadata/metadata/tables \
  -H "Content-Type: application/json" \
  -d '{ ...crop_production JSON above... }'
```

Expect `201` with the table's `fully_qualified_name`, then find it in the OM UI
under Explore. POSTing twice returns the same `id` (upsert, no duplicates).

## Versions (must match)

| Component | Version |
|---|---|
| OpenMetadata server (Docker) | `2.0.2` |
| `openmetadata-ingestion` (pip, `apps/api/requirements.txt`) | `2.0.2.0` |

The SDK refuses to run against a mismatched server (`Major and minor versions
should match`), so keep these in lockstep when upgrading.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `"OPENMETADATA_JWT_TOKEN is not set"` from the API | Backend started in a terminal without the token, or a stale server holds `:8000`. Kill all (`Get-Process python \| Stop-Process`), set token + start fresh in one window |
| `Server version is X vs. Client version Y` | Wrong OM stack running (e.g. an old 1.12.6 copy from outside this repo). `docker compose -f infrastructure/openmetadata/docker-compose.yml down`, remove stray OM containers/networks, `up` again from this repo |
| `http://localhost:8585` not loading | Server starts only after MySQL is healthy; first boot + migration takes minutes. Wait for `(healthy)` on all containers, then check the version endpoint |
| `Pool overlaps` network error on compose up | Orphan network from a duplicate stack. `docker network rm <name>`, retry |
| Port `8000` busy / two uvicorns | Old `--reload` instances survive. Stop all python processes, start exactly one server |

## Deliberately out of scope (for now)

Portal login / multi-admin per-department rules, tags & glossary terms, search
endpoint, real data ingestion, hosting move. The pipeline above is the complete
current backend surface — everything else comes later.
