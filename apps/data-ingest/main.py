"""Data ingest API: one call takes a department's raw file and runs the whole flow --
descriptions drafted, file stored, catalog.yaml updated, stored, published, backed up.

    cd apps/data-ingest && pip install -r requirements.txt
    uvicorn main:app --port 4200

The environment (development / production / local) is the one the checked-out git
branch selects -- exactly the rule the CLI uses (data_services/src/utils/config.py).
Every call that changes data must send  X-Confirm-Environment: <that environment>.
"""

import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

DATA_SERVICES = Path(__file__).resolve().parents[2] / "data_services"
sys.path.insert(0, str(DATA_SERVICES))

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

from src.schema_registry import ai_metadata
from src.schema_registry.add import DEFAULT_CATALOG, add, guess_format, update_catalog_text
from src.schema_registry.catalog import load_catalog
from src.schema_registry.curate import KNOWN_TAGS
from src.schema_registry.pipeline import parse_source
from src.schema_registry.registry import lookups
from src.schema_registry.sync import sync
from src.storage.backup import backup_after_run
from src.utils import config

app = FastAPI(title="Data ingest API", version="1.0")

_lock = threading.Lock()  # catalog.yaml is one file: one ingest at a time
_state: dict = {}


def runtime() -> dict:
    """Environment, storage and OpenMetadata client, built once from .env + the git branch."""

    if not _state:
        from src.schema_registry.openmetadata.publish import get_client
        from src.schema_registry.openmetadata.setup_custom_properties import setup
        from src.storage import storage_from_env

        env = config.load_env()  # refuses an environment this branch may not run
        if env == "production" and not os.environ.get("INGEST_API_KEY"):
            raise PermissionError("INGEST_API_KEY is not set -- production needs it, so only callers with the key can write")
        host, token = os.environ.get("OPENMETADATA_HOST_PORT"), os.environ.get("OPENMETADATA_JWT_TOKEN")
        _state.update(
            env=env,
            branch=config._current_branch(),
            storage=storage_from_env(),
            catalog=DEFAULT_CATALOG,
            client=get_client(host, token) if token else None,
            setup=(lambda: setup(host_port=host, jwt_token=token)) if token else None,
        )
    return _state


def draft_descriptions(raw: Path, workdir: Path) -> tuple[Path | None, str, dict]:
    """Column descriptions and tags drafted by Claude: (csv path, source, dataset suggestion).
    Without ANTHROPIC_API_KEY nothing is drafted and the columns just have no descriptions."""

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None, "none (ANTHROPIC_API_KEY not set)", {}
    columns = parse_source("", raw.stem, guess_format(raw.name), raw.read_text(encoding="utf-8-sig"))
    definitions = ai_metadata.DEFAULT_DEFINITIONS
    result = ai_metadata.draft(columns, definitions.read_text() if definitions.is_file() else None)
    drafted = [{**d, "tag": d.get("tag") if d.get("tag") in KNOWN_TAGS else ""} for d in result.get("columns", [])]
    out = workdir / f"{raw.stem}_metadata.csv"
    ai_metadata.write_csv(out, columns, drafted)
    return out, "claude", result.get("dataset", {})


def check_access(rt: dict, dry_run: bool, x_confirm_environment: str | None, x_api_key: str | None) -> None:
    expected_key = os.environ.get("INGEST_API_KEY")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(401, {"problem": "missing or wrong API key", "fix": "send the header X-API-Key"})
    if not dry_run and x_confirm_environment != rt["env"]:
        raise HTTPException(409, {"problem": "environment not confirmed",
                                  "fix": f"send the header X-Confirm-Environment: {rt['env']}"})


@app.get("/v1/status")
def status() -> dict:
    """Where this API is pointed -- check before sending a file."""

    rt = runtime()
    return {
        "environment": rt["env"],
        "branch": rt["branch"],
        "bucket": os.environ.get("WASABI_BUCKET"),
        "folder": os.environ.get("WASABI_PREFIX"),
        "openmetadata": os.environ.get("OPENMETADATA_HOST_PORT") if rt["client"] else None,
        "descriptions_drafted_by_claude": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


@app.post("/v1/ingest")
def ingest(
    department: str = Form(..., description="department id, for example pwd"),
    dataset: str = Form(..., description="for example vishwakarma"),
    table: str = Form(..., description="for example vishwakarma_T"),
    file: UploadFile = File(..., description="the department's raw file"),
    department_name: str | None = Form(None, description="full name -- only the first time a department is added"),
    category: str | None = Form(None, description="CAT-1 | CAT-2 | CAT-3 | CAT-4"),
    description: str | None = Form(None, description="what the dataset holds"),
    owner: str | None = Form(None),
    steward: str | None = Form(None),
    frequency: str | None = Form(None, description="how often the data is refreshed"),
    timeline: str | None = Form(None, description="period the data covers"),
    api_available: str | None = Form(None, description="Y or N"),
    dry_run: bool = Form(False, description="true: show what would change, change nothing"),
    run_sync: bool = Form(True, description="false: only upload and update catalog.yaml (like the add command); sync later"),
    x_confirm_environment: str | None = Header(None),
    x_api_key: str | None = Header(None),
) -> dict:
    rt = runtime()
    check_access(rt, dry_run, x_confirm_environment, x_api_key)

    if not file.filename:
        raise HTTPException(422, {"problem": "the file has no name", "fix": "upload the department's file with its file name"})
    fields = {"category": category, "description": description, "owner": owner, "steward": steward,
              "frequency": frequency, "timeline": timeline, "api_available": api_available}
    fields = {k: v.strip() for k, v in fields.items() if v and v.strip()}
    work = Path(tempfile.mkdtemp())
    try:
        raw = work / Path(file.filename).name
        raw.write_bytes(file.file.read())
        with _lock:
            if dry_run:
                from src.schema_registry import inputs
                from src.schema_registry.add import input_key

                _, changes = update_catalog_text(
                    rt["catalog"].read_text(), department, dataset,
                    f"{inputs.STORAGE_SCHEME}{input_key(department, dataset, raw.name)}",
                    department_name=department_name, table=table, file_format=guess_format(raw.name),
                    dataset_fields=fields,
                )
                return {"environment": rt["env"], "dry_run": True, "catalog_changes": changes}

            before = rt["catalog"].read_text()
            try:
                metadata, source, suggestion = draft_descriptions(raw, work)
            except (ValueError, FileNotFoundError, PermissionError):
                raise
            except Exception as exc:  # noqa: BLE001 -- the AI service is down, rate-limited, or sent bad JSON
                raise HTTPException(502, {"problem": f"drafting descriptions failed ({type(exc).__name__})",
                                          "fix": "nothing was stored; try again, or unset ANTHROPIC_API_KEY to skip drafting"})
            changes = add(rt["storage"], rt["catalog"], str(raw), department, dataset, table=table,
                          department_name=department_name, metadata_file=str(metadata) if metadata else None,
                          dataset_fields=fields)
            if not run_sync:
                backed_up = backup_after_run(rt["storage"])
                return {
                    "environment": rt["env"],
                    "descriptions": {"source": source, "file": metadata.name if metadata else None,
                                     "dataset_suggestion": suggestion or None},
                    "catalog_changes": [c.replace(str(work) + "/", "") for c in changes],
                    "backup_ok": backed_up,
                    "next": "commit catalog.yaml, then call POST /v1/sync (or run the sync command)",
                }
            outcomes = sync(rt["storage"], load_catalog(str(rt["catalog"])), client=rt["client"],
                            setup=rt["setup"], only_department=department)
            mine = next((o for o in outcomes if o.table_id == f"{department}.{lookups.slugify(dataset)}.{lookups.slugify(table)}"), None)
            if mine is not None and mine.ingest == "failed":
                rt["catalog"].write_text(before)  # a rejected file must not leave its catalog entry behind
                problem, _, fix = mine.detail.partition(" -- ")
                raise HTTPException(422, {"problem": problem, "fix": fix or "correct the file and send it again",
                                          "catalog": "unchanged"})
            backed_up = backup_after_run(rt["storage"])
            if mine is not None and mine.publish == "failed":
                raise HTTPException(502, {"problem": f"stored, but publishing to OpenMetadata failed: {mine.detail}",
                                          "fix": "the files are stored; send the same call again to retry the publish",
                                          "stored": True})
    except (ValueError, FileNotFoundError, PermissionError) as exc:
        problem, _, fix = str(exc).partition(" -- ")
        raise HTTPException(422, {"problem": problem, "fix": fix})
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return {
        "environment": rt["env"],
        "descriptions": {"source": source, "file": metadata.name if metadata else None,
                         "dataset_suggestion": suggestion or None},
        "catalog_changes": [c.replace(str(work) + "/", "") for c in changes],
        "tables": [{"id": o.table_id, "store": o.ingest, "publish": o.publish, "detail": o.detail} for o in outcomes],
        "backup_ok": backed_up,
        "next": "commit catalog.yaml so the repository matches what was stored",
    }


@app.post("/v1/sync")
def run_sync_endpoint(
    department: str | None = Form(None, description="only this department (default: every department in catalog.yaml)"),
    dry_run: bool = Form(False, description="true: show what would happen, change nothing"),
    publish_only: bool = Form(False, description="true: republish what is already stored, ingest nothing"),
    x_confirm_environment: str | None = Header(None),
    x_api_key: str | None = Header(None),
) -> dict:
    """Same as the sync command: store what changed, publish, back up."""

    rt = runtime()
    check_access(rt, dry_run, x_confirm_environment, x_api_key)
    try:
        with _lock:
            outcomes = sync(rt["storage"], load_catalog(str(rt["catalog"])), client=rt["client"], setup=rt["setup"],
                            dry_run=dry_run, publish_only=publish_only, only_department=department or None)
            backed_up = True if dry_run else backup_after_run(rt["storage"])
    except (ValueError, FileNotFoundError, PermissionError) as exc:
        problem, _, fix = str(exc).partition(" -- ")
        raise HTTPException(422, {"problem": problem, "fix": fix})
    tables = [{"id": o.table_id, "store": o.ingest, "publish": o.publish, "detail": o.detail} for o in outcomes]
    if any(o.publish == "failed" for o in outcomes) and not dry_run:
        raise HTTPException(502, {"problem": "some tables were stored but could not be published",
                                  "fix": "send the same call again to retry", "tables": tables})
    if any(o.ingest == "failed" for o in outcomes) and not dry_run:
        raise HTTPException(422, {"problem": "some tables were rejected", "fix": "see detail per table", "tables": tables})
    return {"environment": rt["env"], "dry_run": dry_run, "tables": tables, "backup_ok": backed_up}
