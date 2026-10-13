# MinIO Infrastructure

A local **S3-compatible server (MinIO)** standing in for the company Wasabi
account during feature-branch work. It is infrastructure only -- not part of
the `apps/*` workspaces and not application code.

## Why it exists

Feature branches must never touch company storage, and main's config
(`data_services/src/utils/config.py`) routes them to an S3 account of their
own (`LOCAL_WASABI_...`, README section 3b). Rather than handing everyone a
real Wasabi account, this stack provides one on `localhost`: the exact same
boto3/S3 code path (`S3ObjectStorage`) runs against it, with the same bucket
layout Wasabi uses. Whatever passes here is what runs on the company bucket
later -- including the lock (`_locks/`), snapshot and lookup-CSV behaviour.

## Local-only guarantee

Local data never leaves this machine:

- `data_services/.env` points `LOCAL_WASABI_*` at `http://localhost:9000`,
  buckets `sda-local` / `sda-local-backup` -- never at a Wasabi address.
- `LOCAL_ONLY=1` in `data_services/.env` turns that into an **enforced**
  rule: `load_env()` refuses any local-environment address that isn't
  `localhost` / `127.0.0.1` / `host.docker.internal`, for storage *and* for
  the OpenMetadata server. A copied company host or a typo'd endpoint stops
  the command before anything is written.
- The company bucket (`WASABI_...`) is only reachable from `main`
  (development) or `production`, by the branch rule in `config.py`.
- The MinIO image and its data volume are **git-ignored** (`.gitignore`:
  `infrastructure/minio/data/`, `minio-data/`, `*.minio*`, `*.tar`) and are
  never uploaded to git or any global service.

## What it runs

| Service  | Image                   | Purpose                              |
| -------- | ----------------------- | ------------------------------------ |
| `minio`  | `bitnamilegacy/minio`   | S3 server + web console              |

The image is `bitnamilegacy/minio`: Docker Hub's `minio/minio` was removed
when MinIO went closed-source (2025); the bitnami legacy org keeps the last
open build available.

## Start / stop

```bash
# start (detached)
docker compose -f infrastructure/minio/docker-compose.yml up -d

# stop -- data survives in the named volume
docker compose -f infrastructure/minio/docker-compose.yml down

# stop AND wipe the buckets (only to rebuild from scratch)
docker compose -f infrastructure/minio/docker-compose.yml down -v
```

| Port | What                    | Bound to        |
| ---- | ----------------------- | --------------- |
| 9000 | S3 API (`LOCAL_WASABI_ENDPOINT_URL`) | all interfaces |
| 9001 | Web console (<http://localhost:9001>, `minioadmin` / `minioadmin`) | all interfaces |

## First-time setup (already done on this machine)

```bash
# 1. create the two buckets
python infrastructure/minio/init_buckets.py

# 2. one-time: copy an existing data_services/storage/ tree into MinIO
python infrastructure/minio/migrate_local_storage.py
```

`migrate_local_storage.py` is reusable (it copies whatever is in
`storage/`), but after the first run the buckets are the real storage:
new files go through the S3 path (`add`/`sync`/`batch`), not the local
`storage/` folder, which is kept only as a restore point.

## Wiring into data_services/.env (section 3b)

```dotenv
LOCAL_WASABI_ENDPOINT_URL=http://localhost:9000
LOCAL_WASABI_BUCKET=sda-local
LOCAL_WASABI_REGION=us-east-1
LOCAL_WASABI_ACCESS_KEY_ID=minioadmin
LOCAL_WASABI_SECRET_ACCESS_KEY=minioadmin
LOCAL_WASABI_BACKUP_BUCKET=sda-local-backup
LOCAL_WASABI_BACKUP_REGION=us-east-1
LOCAL_ONLY=1
```

`LOCAL_ONLY=1` is the safety rail described above; keep it.

## Data persistence

- Buckets live in the named Docker volume `minio-data` (same reasoning as
  the OpenMetadata MySQL volume: a bind-mount of registry state invites
  accidental edits and permission drift).
- The buckets hold the same layout as the company bucket
  (`inputs/`, `department/`, `_lookups/`, `_locks/` under a `local/`
  prefix) -- see "Where files are stored" in `data_services/README.md`.
- Never commit, export or upload this volume: it is a developer's local
  registry state, and `.gitignore` exists to keep it that way.
