"""Data ingest API: one call takes a department's raw file and runs the whole flow --
descriptions drafted, file stored, catalog.yaml updated, stored, published, backed up.

    cd apps/data-ingest && pip install -r requirements.txt
    uvicorn main:app --port 4200

The environment (development / production / local) is the one the checked-out git
branch selects -- exactly the rule the CLI uses (data_services/src/utils/config.py).
Every call that changes data must send  X-Confirm-Environment: <that environment>.

Run exactly one worker. catalog.yaml is serialized across processes with a file
lock, but a slow ingest would still queue behind the others.
"""

import base64
import hmac
import json
import os
import shutil
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

DATA_SERVICES = Path(__file__).resolve().parents[2] / "data_services"
sys.path.insert(0, str(DATA_SERVICES))

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.schema_registry import ai_metadata, inputs
from src.schema_registry.add import (
    DEFAULT_CATALOG,
    add,
    catalog_lock,
    guess_format,
    input_key,
    update_catalog_text,
    write_catalog_text,
)
from src.schema_registry.catalog import load_catalog, parse_catalog
from src.schema_registry.curate import KNOWN_TAGS, validate_schema
from src.schema_registry.parsers import mla_lads_xlsx, xlsx_schema
from src.schema_registry.parsers.field_dictionary_parser import parse_field_dictionary_text
from src.schema_registry.pipeline import parse_source
from src.schema_registry.registry import lookups
from src.schema_registry.sync import sync
from src.storage.backup import backup_after_run
from src.utils import config
from src.utils.logger import get_logger

DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
XLSX_SUFFIXES = {".xlsx", ".xlsm", ".xltx"}

logger = get_logger(__name__)

app = FastAPI(title="Data ingest API", version="1.1")

_lock = threading.Lock()  # catalog.yaml is one file: one ingest at a time in this process
_state: dict = {}


@app.middleware("http")
async def refuse_oversized_bodies(request, call_next):
    """Reject an obviously oversized multipart body before Starlette spools it.

    save_upload() enforces the exact cap per file; this stops a hostile or
    mistaken multi-gigabyte POST from filling the temp folder first. The margin
    covers multipart headers and the optional metadata file.
    """

    if request.method == "POST":
        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                if int(raw_length) > _max_upload_bytes() + 2 * 1024 * 1024:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "problem": "the request body is larger than the upload limit",
                            "fix": "raise INGEST_MAX_UPLOAD_BYTES or send a smaller file",
                        },
                    )
            except ValueError:
                pass
    return await call_next(request)


# --- errors: one shape for everything -----------------------------------------------------------

@app.exception_handler(StarletteHTTPException)
async def http_error(_request, exc: StarletteHTTPException) -> JSONResponse:
    """Always answer {"problem", "fix", ...} -- the shape the README documents.

    FastAPI would otherwise nest a dict detail under "detail" while its own
    validation errors return a list, so a client needed two parsers.
    """

    detail = exc.detail
    body = dict(detail) if isinstance(detail, dict) else {"problem": str(detail), "fix": ""}
    body.setdefault("problem", "request failed")
    body.setdefault("fix", "")
    return JSONResponse(status_code=exc.status_code, content=body, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_error(_request, exc: RequestValidationError) -> JSONResponse:
    parts = []
    for error in exc.errors():
        where = ".".join(str(part) for part in error["loc"] if part != "body")
        parts.append(f"{where}: {error['msg']}" if where else error["msg"])
    return JSONResponse(
        status_code=422,
        content={
            "problem": "invalid request -- " + "; ".join(parts),
            "fix": "send every required form field and the file (see /docs)",
        },
    )


@app.exception_handler(Exception)
async def unexpected_error(_request, exc: Exception) -> JSONResponse:
    logger.exception(f"unhandled error in the ingest API: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "problem": f"unexpected server error ({type(exc).__name__})",
            "fix": "check the API logs; the request may not have been stored",
        },
    )


# --- runtime / configuration -------------------------------------------------------------------

def runtime() -> dict:
    """Environment, storage and OpenMetadata client, built once from .env + the git branch."""

    if not _state:
        try:
            from src.schema_registry.openmetadata.publish import get_client
            from src.schema_registry.openmetadata.setup_custom_properties import setup
            from src.storage import storage_from_env

            env = config.load_env()  # refuses an environment this branch may not run
            if env == "production" and not os.environ.get("INGEST_API_KEY"):
                raise PermissionError(
                    "INGEST_API_KEY is not set -- production needs it, so only callers with the key can write"
                )
            host, token = os.environ.get("OPENMETADATA_HOST_PORT"), os.environ.get("OPENMETADATA_JWT_TOKEN")
            _state.update(
                env=env,
                branch=config._current_branch(),
                storage=storage_from_env(),
                catalog=DEFAULT_CATALOG,
                client=get_client(host, token) if token else None,
                setup=(lambda: setup(host_port=host, jwt_token=token)) if token else None,
            )
        except Exception as exc:  # noqa: BLE001 -- configuration/storage/OM client setup only
            problem, _, fix = str(exc).partition(" -- ")
            raise HTTPException(
                503,
                {
                    "problem": f"the API is not configured: {problem or type(exc).__name__}",
                    "fix": fix or "fill in data_services/.env (see .env.example) and restart the API",
                },
            )
    return _state


def _token_expiry() -> datetime | None:
    """exp of the OpenMetadata JWT, without verifying it -- for /v1/status."""

    token = os.environ.get("OPENMETADATA_JWT_TOKEN") or ""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload)).get("exp")
        return datetime.fromtimestamp(int(exp), tz=timezone.utc) if exp else None
    except Exception:  # noqa: BLE001 -- an unreadable token is reported as "no expiry", not a 500
        return None


def _max_upload_bytes() -> int:
    try:
        return int(os.environ.get("INGEST_MAX_UPLOAD_BYTES") or DEFAULT_MAX_UPLOAD_BYTES)
    except ValueError:
        return DEFAULT_MAX_UPLOAD_BYTES


def form_flag(value: str | None, *, default: bool) -> bool:
    """Read a form flag that defaults to true.

    FastAPI 0.161 (with Pydantic 2.14) coerces an *omitted* bool form field to
    False even when the declared default is True, so `run_sync: bool =
    Form(True)` silently skipped sync after the upgrade. Taking the raw string
    keeps the default explicit and independent of the installed version.
    """

    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"false", "0", "no", "off"}


def check_api_key(x_api_key: str | None) -> None:
    expected = os.environ.get("INGEST_API_KEY")
    if expected and not hmac.compare_digest(x_api_key or "", expected):
        raise HTTPException(401, {"problem": "missing or wrong API key", "fix": "send the header X-API-Key"})


def check_access(rt: dict, dry_run: bool, x_confirm_environment: str | None, x_api_key: str | None) -> None:
    check_api_key(x_api_key)
    if not dry_run and x_confirm_environment != rt["env"]:
        raise HTTPException(
            409,
            {
                "problem": "environment not confirmed",
                "fix": f"send the header X-Confirm-Environment: {rt['env']}",
            },
        )


def check_publish_available(rt: dict, dry_run: bool) -> None:
    """A shared environment without a token must not report success: nothing would be published."""

    if not dry_run and rt["client"] is None and rt["env"] in ("development", "production"):
        raise HTTPException(
            503,
            {
                "problem": f"OpenMetadata is not configured, so nothing would be published ({rt['env']})",
                "fix": "set OPENMETADATA_JWT_TOKEN in data_services/.env and restart, "
                       "or send run_sync=false to store without publishing",
            },
        )


# --- files -------------------------------------------------------------------------------------

def safe_upload_name(filename: str | None) -> str:
    """The file's base name, with both '/' and '\\' treated as separators.

    Path(...).name already does that on Windows; on Linux a browser-supplied
    '..\\..\\evil' would otherwise keep its backslashes and land as one odd
    file name."""

    name = Path(str(filename or "").replace("\\", "/")).name
    if name in ("", ".", ".."):
        raise HTTPException(422, {"problem": "the uploaded file has no usable name",
                                  "fix": "send the file with its original file name"})
    return name


def save_upload(upload: UploadFile, dest: Path, what: str) -> None:
    limit = _max_upload_bytes()
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            413,
            {
                "problem": f"{what} is larger than the {limit}-byte upload limit",
                "fix": "raise INGEST_MAX_UPLOAD_BYTES or send a smaller file",
            },
        )
    dest.write_bytes(data)


def prepare_source(raw: Path, work: Path, dataset: str, sheet: str | None) -> tuple[Path, dict | None]:
    """The file the registry should parse: the upload itself, or an .xlsx converted to CSV."""

    suffix = raw.suffix.lower()
    if suffix in XLSX_SUFFIXES:
        converted = work / f"{raw.stem}.csv"
        try:
            if lookups.slugify(dataset) == "mla_lads":
                columns = mla_lads_xlsx.write_schema_csv(raw, converted)
                report = {"converter": "mla_lads_xlsx", "columns": len(columns)}
            else:
                report = {"converter": "xlsx_schema", **xlsx_schema.write_schema_csv(raw, converted, sheet=sheet)}
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001 -- openpyxl/zipfile errors for a corrupt upload
            raise ValueError(
                f"could not read '{raw.name}' as an Excel workbook ({type(exc).__name__}) -- "
                "save it as .xlsx and send it again; nothing was stored"
            )
        return converted, {"from": raw.name, **report}
    if suffix == ".xls":
        raise ValueError(
            "legacy .xls isn't supported -- save the workbook as .xlsx and send it again; nothing was stored"
        )
    if sheet:
        raise ValueError("sheet only applies to an .xlsx upload")
    return raw, None


def validate_uploaded_source(source: Path, department: str, dataset: str, table: str | None, field_dictionary: bool) -> None:
    text = inputs.decode(source.read_bytes())
    if field_dictionary:
        tables = parse_field_dictionary_text(text, label=source.name)
        if not tables:
            raise ValueError(f"{source.name}: no table/field rows found; nothing was stored")
        return
    columns = parse_source(department, table or source.stem, guess_format(source.name), text)
    validate_schema(f"{department}.{dataset}.{table}", columns)


# --- catalog / rollback helpers ----------------------------------------------------------------

def previous_inputs(rt: dict, catalog_text: str, department: str, dataset: str,
                    table: str | None, field_dictionary: bool) -> dict[str, bytes]:
    """Bytes of the files this call may overwrite, keyed by storage path.

    add() uploads before sync validates. On a sync-stage rejection the catalog
    is restored; these bytes let us restore the input and metadata files too,
    so the published snapshot and its registered source do not diverge.
    """

    saved: dict[str, bytes] = {}
    try:
        entries = parse_catalog(catalog_text)
    except Exception:  # noqa: BLE001 -- a broken catalog is add()'s problem to report
        return saved
    department_entry = next((entry for entry in entries if entry.id == department), None)
    if department_entry is None:
        return saved
    dataset_entry = next(
        (entry for entry in department_entry.datasets if lookups.slugify(entry.name) == lookups.slugify(dataset)),
        None,
    )
    if dataset_entry is None:
        return saved

    refs: list[str | None] = []
    if field_dictionary:
        refs.append(dataset_entry.field_dictionary)
    else:
        table_entry = next((entry for entry in dataset_entry.tables if lookups.slugify(entry.name) == lookups.slugify(table or "")), None)
        if table_entry is not None:
            refs.extend([table_entry.source, table_entry.metadata])
    for ref in refs:
        if ref and ref.startswith(inputs.STORAGE_SCHEME):
            key = ref[len(inputs.STORAGE_SCHEME):].lstrip("/")
            if rt["storage"].exists(key):
                saved[key] = rt["storage"].read_bytes(key)
    return saved


def restore_inputs(rt: dict, saved: dict[str, bytes]) -> bool:
    restored = False
    for key, data in saved.items():
        rt["storage"].write_bytes(key, data)
        restored = True
    return restored


def rollback_inputs(rt: dict, before: str, saved: dict[str, bytes], locked: bool = False) -> bool:
    """Put the catalog and any overwritten input/metadata files back. Returns
    whether at least one file was restored (False for a brand-new table).

    `locked=True` means the caller already holds catalog_lock() (a rejected
    update rolls back before it leaves the guard)."""

    if not before:
        return False
    if locked:
        write_catalog_text(rt["catalog"], before)
        return restore_inputs(rt, saved)
    with catalog_lock(rt["catalog"]):
        write_catalog_text(rt["catalog"], before)
        return restore_inputs(rt, saved)


# --- drafting ----------------------------------------------------------------------------------

def draft_descriptions(raw: Path, workdir: Path) -> tuple[Path | None, str, dict, list[str]]:
    """Column descriptions and tags drafted by Claude: (csv path, source, dataset suggestion, rule changes).
    Without ANTHROPIC_API_KEY nothing is drafted and the columns just have no descriptions."""

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None, "none (ANTHROPIC_API_KEY not set)", {}, []
    columns = parse_source("", raw.stem, guess_format(raw.name), inputs.decode(raw.read_bytes()))
    definitions = ai_metadata.DEFAULT_DEFINITIONS
    result = ai_metadata.draft(columns, definitions.read_text() if definitions.is_file() else None)

    # The CLI's ai_metadata path applies the MDSF s5.1 rules and the CAT floor;
    # this path must not trust the model for either.
    drafted, changed = ai_metadata.apply_rules(columns, result.get("columns", []))
    drafted = [{**column, "tag": column.get("tag") if column.get("tag") in KNOWN_TAGS else ""} for column in drafted]
    if not any((column.get("business_description") or "").strip() for column in drafted):
        raise RuntimeError(
            "the AI returned no usable column descriptions -- nothing was stored; "
            "try again, or send your own metadata CSV as `metadata`"
        )

    out = workdir / f"{raw.stem}_metadata.csv"
    ai_metadata.write_csv(out, columns, drafted)

    suggestion = dict(result.get("dataset") or {})
    if suggestion:
        suggestion["category"] = ai_metadata.category_floor(drafted, suggestion.get("category"))
    return out, "claude", suggestion, changed


# --- routes ------------------------------------------------------------------------------------

@app.get("/v1/status")
def status(x_api_key: str | None = Header(None)) -> dict:
    """Where this API is pointed -- check before sending a file."""

    check_api_key(x_api_key)
    rt = runtime()
    expiry = _token_expiry()
    return {
        "environment": rt["env"],
        "branch": rt["branch"],
        "bucket": os.environ.get("WASABI_BUCKET"),
        "folder": os.environ.get("WASABI_PREFIX"),
        "openmetadata": os.environ.get("OPENMETADATA_HOST_PORT") if rt["client"] else None,
        "openmetadata_token_expires_at": expiry.isoformat() if expiry else None,
        "openmetadata_token_expired": bool(expiry and expiry <= datetime.now(timezone.utc)),
        "descriptions_drafted_by_claude": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "upload_limit_bytes": _max_upload_bytes(),
    }


@app.post("/v1/ingest")
def ingest(
    department: str = Form(..., description="department id, for example pwd"),
    dataset: str = Form(..., description="for example vishwakarma"),
    table: str | None = Form(None, description="for example vishwakarma_T (required unless field_dictionary=true)"),
    file: UploadFile = File(..., description="the department's raw file (.csv, .xlsx or Postgres DDL)"),
    department_name: str | None = Form(None, description="full name -- only the first time a department is added"),
    category: str | None = Form(None, description="CAT-1 | CAT-2 | CAT-3 | CAT-4"),
    description: str | None = Form(None, description="what the dataset holds"),
    owner: str | None = Form(None),
    steward: str | None = Form(None),
    frequency: str | None = Form(None, description="how often the data is refreshed"),
    timeline: str | None = Form(None, description="period the data covers"),
    api_available: str | None = Form(None, description="Y or N"),
    schema_name: str | None = Form(None, alias="schema", description="database schema name (default public)"),
    field_dictionary: bool = Form(False, description="true: the file describes several tables of the dataset"),
    allow_column_removal: bool = Form(False, description="true: accept a file that drops columns"),
    metadata: UploadFile | None = File(None, description="the department's own metadata CSV (name,business_description,tag)"),
    sheet: str | None = Form(None, description="worksheet name, for an .xlsx upload"),
    dry_run: bool = Form(False, description="true: show what would change, change nothing"),
    run_sync: str | None = Form(None, description="true|false (default true): false only uploads and updates catalog.yaml, like the add command"),
    x_confirm_environment: str | None = Header(None),
    x_api_key: str | None = Header(None),
) -> dict:
    rt = runtime()
    check_access(rt, dry_run, x_confirm_environment, x_api_key)
    sync_requested = form_flag(run_sync, default=True)
    if field_dictionary and table:
        raise HTTPException(
            422,
            {
                "problem": "send either table or field_dictionary=true, not both",
                "fix": "a field dictionary describes several tables, so leave table out",
            },
        )
    if not field_dictionary and not table:
        raise HTTPException(
            422,
            {
                "problem": "table is required unless field_dictionary=true",
                "fix": "name the table, or send field_dictionary=true for a multi-table field dictionary",
            },
        )
    if not dry_run and sync_requested:
        check_publish_available(rt, dry_run)
    if not file.filename:
        raise HTTPException(422, {"problem": "the file has no name", "fix": "upload the department's file with its file name"})

    fields = {"category": category, "description": description, "owner": owner, "steward": steward,
              "frequency": frequency, "timeline": timeline, "api_available": api_available}
    fields = {key: value.strip() for key, value in fields.items() if value and value.strip()}
    work = Path(tempfile.mkdtemp())
    before = ""
    saved: dict[str, bytes] = {}
    keep = False
    rolled_back = False
    try:
        raw = work / safe_upload_name(file.filename)
        save_upload(file, raw, "the uploaded file")
        department_metadata: Path | None = None
        if metadata is not None:
            if not metadata.filename:
                raise ValueError("the metadata file has no name; nothing was stored")
            department_metadata = work / f"department_{safe_upload_name(metadata.filename)}"
            save_upload(metadata, department_metadata, "the metadata file")
            inputs.decode(department_metadata.read_bytes())  # refuse a binary "CSV" before anything is written

        source, conversion = prepare_source(raw, work, dataset, sheet)

        # Syntax/schema checks first: a bad file must not reach storage.
        validate_uploaded_source(source, department, dataset, table, field_dictionary)

        with _lock, catalog_lock(rt["catalog"]):
            before = rt["catalog"].read_text(encoding="utf-8") if rt["catalog"].exists() else ""
            saved = previous_inputs(rt, before, department, dataset, table, field_dictionary)

            if dry_run:
                metadata_key = input_key(department, dataset, department_metadata.name) if department_metadata else None
                _, changes = update_catalog_text(
                    before, department, dataset,
                    f"{inputs.STORAGE_SCHEME}{input_key(department, dataset, raw.name)}",
                    department_name=department_name, table=None if field_dictionary else table,
                    file_format=guess_format(source.name),
                    schema=schema_name, metadata_ref=f"{inputs.STORAGE_SCHEME}{metadata_key}" if metadata_key else None,
                    dataset_fields=fields, allow_column_removal=allow_column_removal,
                )
                keep = True  # dry run never wrote the catalog or the files
                return {
                    "environment": rt["env"],
                    "dry_run": True,
                    "validated": True,
                    "conversion": conversion,
                    "catalog_changes": changes,
                }

            drafted: Path | None = None
            source_name = "department" if department_metadata else "none (ANTHROPIC_API_KEY not set)"
            suggestion: dict = {}
            rule_changes: list[str] = []
            if department_metadata is None:
                try:
                    drafted, source_name, suggestion, rule_changes = draft_descriptions(source, work)
                except (ValueError, FileNotFoundError, PermissionError):
                    raise
                except Exception as exc:  # noqa: BLE001 -- AI service down, rate-limited, or bad JSON
                    problem, _, fix = str(exc).partition(" -- ")
                    raise HTTPException(
                        502,
                        {
                            "problem": f"drafting descriptions failed: {problem}",
                            "fix": fix or "nothing was stored; try again, or send your own metadata CSV as `metadata`",
                        },
                    )
            metadata_file = str(department_metadata or drafted) if (department_metadata or drafted) else None
            # A supplied category may not be lower than the floor the rules derive
            # from the drafted columns (a PII column means CAT-3 at least).
            proposed = (suggestion or {}).get("category")
            if fields.get("category") in ai_metadata.CATEGORY_ORDER and proposed in ai_metadata.CATEGORY_ORDER:
                fields["category"] = max(fields["category"], proposed, key=ai_metadata.CATEGORY_ORDER.index)

            changes = add(
                rt["storage"], rt["catalog"], str(source), department, dataset,
                table=None if field_dictionary else table, department_name=department_name,
                schema=schema_name, metadata_file=metadata_file, dataset_fields=fields,
                allow_column_removal=allow_column_removal, lock=False,
            )
            original_key = None
            if conversion is not None:
                original_key = input_key(department, dataset, f"_original/{raw.name}")
                rt["storage"].write_bytes(original_key, raw.read_bytes())
                changes.insert(0, f"kept the original workbook as {original_key}")

            if not sync_requested:
                keep = True
                backed_up = backup_after_run(rt["storage"])
                return {
                    "environment": rt["env"],
                    "descriptions": {"source": source_name, "file": Path(metadata_file).name if metadata_file else None,
                                     "dataset_suggestion": suggestion or None, "rules_changed": rule_changes},
                    "conversion": conversion,
                    "original": original_key,
                    "catalog_changes": [change.replace(str(work) + "/", "") for change in changes],
                    "backup_ok": backed_up,
                    "published": False,
                    "next": "commit catalog.yaml, then call POST /v1/sync (or run the sync command)",
                }

            outcomes = sync(rt["storage"], load_catalog(str(rt["catalog"])), client=rt["client"],
                            setup=rt["setup"], only_department=department)
            if field_dictionary:
                mine = next((outcome for outcome in outcomes if "(field dictionary)" in outcome.table_id), None)
            else:
                mine = next(
                    (outcome for outcome in outcomes
                     if outcome.table_id == f"{department}.{lookups.slugify(dataset)}.{lookups.slugify(table)}"),
                    None,
                )
            if mine is None:
                raise HTTPException(
                    502,
                    {
                        "problem": "the file was stored but sync did not report this table",
                        "fix": "the catalog may not match the request; nothing was published",
                    },
                )
            if mine.ingest == "failed":
                problem, _, fix = mine.detail.partition(" -- ")
                try:
                    restored = rollback_inputs(rt, before, saved, locked=True)
                    rolled_back = True
                except Exception:  # noqa: BLE001 -- report the original rejection; log the restore failure
                    logger.exception("could not restore the catalog/input after a rejected update")
                    restored = False
                raise HTTPException(
                    422,
                    {
                        "problem": problem,
                        "fix": fix or "correct the file and send it again",
                        "catalog": "unchanged",
                        "file_restored": restored,
                    },
                )

            keep = True  # stored and accepted: a publish failure must keep the files for a retry
            backed_up = backup_after_run(rt["storage"])
            if mine.publish == "failed":
                raise HTTPException(
                    502,
                    {
                        "problem": f"stored, but publishing to OpenMetadata failed: {mine.detail}",
                        "fix": "the files are stored; send the same call again to retry the publish",
                        "stored": True,
                    },
                )
    except (ValueError, FileNotFoundError, PermissionError) as exc:
        problem, _, fix = str(exc).partition(" -- ")
        raise HTTPException(422, {"problem": problem, "fix": fix or "correct the file and send it again"})
    finally:
        if before and not keep and not rolled_back:
            try:
                rollback_inputs(rt, before, saved)
            except Exception:  # noqa: BLE001 -- never hide the original error
                logger.exception("could not restore the catalog/input while handling a failed ingest")
        shutil.rmtree(work, ignore_errors=True)

    return {
        "environment": rt["env"],
        "descriptions": {"source": source_name, "file": Path(metadata_file).name if metadata_file else None,
                         "dataset_suggestion": suggestion or None, "rules_changed": rule_changes},
        "conversion": conversion,
        "original": original_key,
        "catalog_changes": [change.replace(str(work) + "/", "") for change in changes],
        "tables": [{"id": outcome.table_id, "store": outcome.ingest, "publish": outcome.publish,
                    "detail": outcome.detail} for outcome in outcomes],
        "backup_ok": backed_up,
        "published": rt["client"] is not None and any(outcome.publish == "published" for outcome in outcomes),
        "next": "commit catalog.yaml so the repository matches what was stored",
    }


@app.post("/v1/sync")
def run_sync_endpoint(
    department: str | None = Form(None, description="only this department (default: every department in catalog.yaml)"),
    dry_run: bool = Form(False, description="true: show what would happen, change nothing"),
    publish_only: bool = Form(False, description="true: republish what is already stored, ingest nothing"),
    reclassify: bool = Form(False, description="true: re-derive classification/tag from the current rules (needs department)"),
    x_confirm_environment: str | None = Header(None),
    x_api_key: str | None = Header(None),
) -> dict:
    """Same as the sync command: store what changed, publish, back up."""

    rt = runtime()
    check_access(rt, dry_run, x_confirm_environment, x_api_key)
    if not dry_run:
        check_publish_available(rt, dry_run)
    try:
        with _lock:
            outcomes = sync(rt["storage"], load_catalog(str(rt["catalog"])), client=rt["client"], setup=rt["setup"],
                            dry_run=dry_run, publish_only=publish_only, only_department=department or None,
                            reclassify=reclassify)
            backed_up = True if dry_run else backup_after_run(rt["storage"])
    except (ValueError, FileNotFoundError, PermissionError) as exc:
        problem, _, fix = str(exc).partition(" -- ")
        raise HTTPException(422, {"problem": problem, "fix": fix or "see the sync command output"})
    except Exception as exc:  # noqa: BLE001 -- storage/OpenMetadata failure outside the per-table guard
        logger.exception("sync failed")
        raise HTTPException(
            502,
            {
                "problem": f"sync failed ({type(exc).__name__})",
                "fix": "check the API logs and storage/OpenMetadata access; the run may be partial",
            },
        )
    tables = [{"id": outcome.table_id, "store": outcome.ingest, "publish": outcome.publish,
               "detail": outcome.detail} for outcome in outcomes]
    if any(outcome.publish == "failed" for outcome in outcomes) and not dry_run:
        raise HTTPException(502, {"problem": "some tables were stored but could not be published",
                                  "fix": "send the same call again to retry", "tables": tables})
    if any(outcome.ingest == "failed" for outcome in outcomes) and not dry_run:
        raise HTTPException(422, {"problem": "some tables were rejected", "fix": "see detail per table", "tables": tables})
    return {"environment": rt["env"], "dry_run": dry_run, "tables": tables,
            "published": rt["client"] is not None and any(o.publish == "published" for o in outcomes),
            "backup_ok": backed_up}
