"""Ingest the pipeline's processed output into Neon (the app database).

`data_services` produces one curated CSV snapshot per table:

    storage/department/<dept>/<dataset>/<table>/curated/schemas/<ts>.csv
    table_id,ingestion_timestamp,name,data_type,...,classification,...

POST /registry/ingest takes that file as an upload and stores its rows in
``registry.tables`` / ``registry.columns``, replacing the previous snapshot
for the same ``table_id`` (re-uploading is idempotent). No more mailing CSVs
-- the backend queries Neon directly, and the GET endpoints below are a
read-only view for verification/showcase.

OpenMetadata remains the catalogue of record; this is the shared, queryable
copy of our pipeline's output.
"""

import csv
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_session as db_get_session
from database.models import RegistryColumn, RegistryTable, User
from src.middleware.auth import get_current_user
from src.schemas.registry_ingest import (
    IngestResponse,
    IngestedColumn,
    IngestedTable,
    IngestedTableDetail,
)

router = APIRouter(prefix="/registry/ingest", tags=["registry"])

# The only two headers without which the file cannot be a curated snapshot
# (anything else -- a raw source dump, a manifest -- is rejected up front).
REQUIRED_HEADERS = ("name", "data_type")


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"true", "1", "yes", "y"}


def _as_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _as_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def parse_curated_snapshot(
    text: str, table_id: str | None = None, schema_name: str = "public"
) -> tuple[dict, list[dict]]:
    """Parse a curated CSV snapshot into (table_meta, column_rows).

    Pure function (no DB) so it can be unit-tested. Raises ``ValueError``
    with a message safe to return to the uploader as a 422.
    """

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("The uploaded file is empty")

    missing = [header for header in REQUIRED_HEADERS if header not in reader.fieldnames]
    if missing:
        raise ValueError(
            f"Not a curated schema snapshot: missing column(s) {', '.join(missing)}. "
            "Expected the pipeline's curated CSV (table_id, ingestion_timestamp, name, "
            "data_type, ...)."
        )

    rows = list(reader)
    if not rows:
        raise ValueError("The snapshot contains no column rows")

    csv_table_id = _as_text(rows[0].get("table_id"))
    resolved = _as_text(table_id) or csv_table_id
    if not resolved:
        raise ValueError(
            "No table_id: pass one with the upload, or use a snapshot that carries one"
        )

    csv_table_ids = {t for t in (_as_text(row.get("table_id")) for row in rows) if t}
    if csv_table_ids and resolved not in csv_table_ids:
        raise ValueError(
            f"Snapshot belongs to {', '.join(sorted(csv_table_ids))}, not to '{resolved}'"
        )

    parts = resolved.split(".")
    if len(parts) < 3 or not all(part.strip() for part in parts[:3]):
        raise ValueError(f"table_id '{resolved}' must look like department.dataset.table")

    columns: list[dict] = []
    for position, row in enumerate(rows, start=1):
        name = _as_text(row.get("name"))
        data_type = _as_text(row.get("data_type"))
        if not name:
            raise ValueError(f"Row {position}: missing column name")
        if not data_type:
            raise ValueError(f"Row {position} ({name}): missing data_type")
        if len(name) > 200:
            raise ValueError(f"Row {position}: column name longer than 200 characters")
        if len(data_type) > 50:
            raise ValueError(f"Row {position} ({name}): data_type longer than 50 characters")

        columns.append(
            {
                "position": position,
                "name": name,
                "data_type": data_type,
                "length": _as_int(row.get("length")),
                "scale": _as_int(row.get("scale")),
                "nullable": _as_bool(row.get("nullable"), default=True),
                "default_value": _as_text(row.get("default")),
                "business_description": _as_text(row.get("business_description")),
                "tag": _as_text(row.get("tag")),
                "classification": _as_text(row.get("classification")),
                "glossary_term": _as_text(row.get("glossary_term")),
                "active": _as_bool(row.get("active"), default=True),
                "validation_warning": _as_text(row.get("validation_warning")),
            }
        )

    source_timestamp = next(
        (t for t in (_as_text(row.get("ingestion_timestamp")) for row in rows) if t), None
    )
    meta = {
        "table_id": resolved,
        "department": parts[0].strip(),
        "dataset": parts[1].strip(),
        "table_name": ".".join(part.strip() for part in parts[2:]),
        "schema_name": (_as_text(schema_name) or "public"),
        "column_count": len(columns),
        "source_timestamp": source_timestamp,
    }
    return meta, columns


@router.post("", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_curated_snapshot(
    file: UploadFile = File(..., description="Curated CSV snapshot from data_services"),
    table_id: str | None = Form(None, description="Overrides the snapshot's own table_id"),
    schema_name: str = Form("public"),
    session: AsyncSession = Depends(db_get_session),
    user: User = Depends(get_current_user),
):
    """Upload a curated snapshot; replaces any previous copy of that table."""

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="The uploaded file is empty")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="The snapshot must be UTF-8 encoded CSV")

    try:
        meta, columns = parse_curated_snapshot(text, table_id=table_id, schema_name=schema_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    existing = await session.scalar(
        select(RegistryTable).where(RegistryTable.table_id == meta["table_id"])
    )
    if existing is None:
        existing = RegistryTable(**meta, uploaded_by=user.email)
        session.add(existing)
    else:
        for key, value in {**meta, "uploaded_by": user.email}.items():
            setattr(existing, key, value)
    # flush so a brand-new registry.tables row exists before the FK'd columns
    await session.flush()

    await session.execute(
        delete(RegistryColumn).where(RegistryColumn.table_id == meta["table_id"])
    )
    await session.execute(
        insert(RegistryColumn),
        [{**column, "table_id": meta["table_id"]} for column in columns],
    )
    await session.commit()
    await session.refresh(existing)

    return IngestResponse(
        table_id=existing.table_id,
        department=existing.department,
        dataset=existing.dataset,
        schema_name=existing.schema_name,
        table_name=existing.table_name,
        column_count=existing.column_count,
        source_timestamp=existing.source_timestamp,
        uploaded_by=existing.uploaded_by,
    )


@router.get("/tables", response_model=list[IngestedTable])
async def list_ingested_tables(session: AsyncSession = Depends(db_get_session)):
    """Every ingested table (metadata only -- safe to expose publicly)."""

    rows = (
        (await session.execute(select(RegistryTable).order_by(RegistryTable.table_id)))
        .scalars()
        .all()
    )
    return [IngestedTable.model_validate(row, from_attributes=True) for row in rows]


@router.get("/tables/{table_id}", response_model=IngestedTableDetail)
async def get_ingested_table(table_id: str, session: AsyncSession = Depends(db_get_session)):
    """One ingested table with its columns, in snapshot order."""

    table = await session.scalar(
        select(RegistryTable).where(RegistryTable.table_id == table_id)
    )
    if table is None:
        raise HTTPException(status_code=404, detail=f"No ingested table '{table_id}'")

    columns = (
        (
            await session.execute(
                select(RegistryColumn)
                .where(RegistryColumn.table_id == table_id)
                .order_by(RegistryColumn.position)
            )
        )
        .scalars()
        .all()
    )
    detail = IngestedTableDetail.model_validate(table, from_attributes=True)
    detail.columns = [IngestedColumn.model_validate(column, from_attributes=True) for column in columns]
    return detail
