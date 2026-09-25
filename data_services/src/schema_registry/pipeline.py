import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock
from metadata.ingestion.ometa.ometa_api import OpenMetadata

from src.schema_registry import lookups
from src.schema_registry.csv_schema_parser import parse_csv_columns
from src.schema_registry.curate import curate_schema
from src.schema_registry.ddl_parser import parse_postgres_columns
from src.schema_registry.openmetadata_publish import get_client, publish_table
from src.storage.base import ObjectStorage
from src.storage.local import LocalObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)

_TRUE_VALUES = {"y", "yes", "true", "1"}

_PARSERS = {
    "postgres_ddl": lambda path: parse_postgres_columns(Path(path).read_text()),
    "csv": parse_csv_columns,
}


def _timestamp() -> str:
    # microsecond resolution -- second resolution collides on back-to-back
    # runs (e.g. a batch loop) and silently overwrites the previous snapshot
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _business_metadata_from_rows(rows: list[dict]) -> dict[str, dict]:
    """Shape a list of CSV rows (a Field Dictionary export, or a previous
    curated snapshot) into the {name: {business_description, tag,
    glossary_term, active}} form curate_schema() expects."""

    return {
        row["name"]: {
            "business_description": row.get("business_description", ""),
            "tag": row.get("tag", ""),
            "glossary_term": row.get("glossary_term", ""),
            "active": row.get("active", "").strip().lower() in _TRUE_VALUES,
        }
        for row in rows
    }


def _load_business_metadata(path: str) -> dict[str, dict]:
    """Load a Field Dictionary export (CSV: name, business_description,
    tag, glossary_term, active) keyed by field name."""

    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return _business_metadata_from_rows(rows)


def _previous_curated_columns(
    storage: ObjectStorage, department_id: str, dataset_slug: str, table_slug: str
) -> list[dict] | None:
    """The last curated snapshot for this table, or None if this is its
    first-ever run (nothing to diff or carry forward against)."""

    try:
        path = lookups.latest_curated_snapshot_path(storage, department_id, dataset_slug, table_slug)
    except FileNotFoundError:
        return None
    return storage.read_csv(path)


def run(
    department: str,
    dataset: str,
    table_name: str,
    source_file: str,
    storage: ObjectStorage,
    source_format: str = "postgres_ddl",
    schema_name: str = "public",
    business_metadata_file: str | None = None,
    owner: str = "",
    fiduciary: str = "",
    processor: str = "",
    risk_classification: str = "",
    retention_policy: str = "",
    lineage: str = "",
    openmetadata_client: OpenMetadata | None = None,
    allow_column_removal: bool = False,
) -> dict:
    """Parse a department's raw column-definition submission, validate/
    standardize it, and store both the raw and curated schema versions
    as CSV.

    `source_format` picks the parser for the submission format a
    department actually used (departments won't all submit the same
    way): "postgres_ddl" for a raw Postgres column-list dump (like PWD's),
    "csv" for a column-definition CSV with arbitrary header names.

    department/dataset/table names are slugified (lowercased, non-alphanumeric
    collapsed to "_") before building ids/paths, so "Amplify Data" and
    "amplify_data" resolve to the same registry entry and folder instead of
    silently becoming two unrelated ones. Original display names are kept
    in `_lookups/*.csv` (deduped, keyed by hierarchical id:
    "pwd", "pwd.vishwakarma", "pwd.vishwakarma.<table>") rather than
    repeated as text on every column row -- each column row only carries
    `table_id`, which joins back to the lookups.

    `department` must already be a registered department (see
    lookups.register_department) -- slugify only normalizes formatting, it
    can't tell that "Public Works Department"/"PWD Dept" are the same
    department, so departments are a deliberately controlled vocabulary
    rather than auto-created from whatever text a caller passes.

    owner/fiduciary/processor/risk_classification/retention_policy/lineage
    are dataset-level governance fields (needed for OpenMetadata's Owner
    field and custom properties) stored once per dataset in
    `_lookups/datasets.csv`, not repeated per column row. Left blank if
    not yet confirmed -- re-run with the answer once it comes in to update
    the existing entry.

    Storage layout (each table gets its own folder, since tables in the
    same dataset can have unrelated structures):
        department/<department_id>/<dataset_slug>/<table_slug>/raw/schemas/<timestamp>.csv
        department/<department_id>/<dataset_slug>/<table_slug>/curated/schemas/<timestamp>.csv

    `openmetadata_client`: if given, the freshly curated snapshot is also
    published to OpenMetadata (via openmetadata_publish.publish_table) as
    the last step of this same call, so ingest -> curate -> publish is one
    pipeline run instead of two separate manual steps. Omit it to keep
    this call to storage only.

    Re-running for a table that's already been curated before diffs the new
    source against the *previous* curated snapshot instead of blindly
    trusting this run's input as the complete truth:
      - Columns present before but missing from this run raise a ValueError
        naming them, unless `allow_column_removal=True` -- this is what
        catches a partial/incremental submission (e.g. a department sends
        only its 2 new columns, expecting an "append") before it silently
        drops every other previously-published column from OpenMetadata.
      - `business_description`/`tag`/`glossary_term`/`active` for any
        column not mentioned in this run's `business_metadata_file` (or
        given no file at all) are carried forward from the previous
        snapshot rather than reset to blank -- so answering one column's
        Field Dictionary question doesn't erase everyone else's answers.
      - A table's first-ever run has no previous snapshot to diff or carry
        forward against, so it always succeeds (this is "initial load").
    """

    if source_format not in _PARSERS:
        raise ValueError(f"Unknown source_format '{source_format}'. Options: {list(_PARSERS)}")

    department_id = lookups.slugify(department)
    dataset_slug = lookups.slugify(dataset)
    table_slug = lookups.slugify(table_name)
    dataset_id = f"{department_id}.{dataset_slug}"
    table_id = f"{dataset_id}.{table_slug}"

    if not lookups.department_exists(storage, department_id):
        raise ValueError(
            f"Unknown department '{department_id}'. Register it first with "
            f"lookups.register_department(storage, '{department_id}', '<display name>') "
            f"before ingesting data for it."
        )

    logger.info(f"Schema ingestion started: {table_id} (format: {source_format})")

    lookups.upsert_dataset(
        storage, dataset_id, department_id, dataset,
        owner=owner, fiduciary=fiduciary, processor=processor,
        risk_classification=risk_classification, retention_policy=retention_policy, lineage=lineage,
    )
    lookups.upsert_table(storage, table_id, dataset_id, table_name, schema_name)

    ts = _timestamp()

    parsed_columns = _PARSERS[source_format](source_file)
    raw_columns = [{"table_id": table_id, "ingestion_timestamp": ts, **col} for col in parsed_columns]
    logger.info(f"Parsed {len(raw_columns)} column(s) from {source_file}")

    # Locked per table: reading the previous snapshot, deciding whether a
    # removal is allowed, and writing the new raw+curated snapshot must be
    # one atomic step, or two concurrent runs for the same table (e.g. a
    # double-triggered CLI call, two batch jobs targeting the same row)
    # could both read the same "previous" state and both proceed on stale
    # information.
    lock_path = storage.lock_path(f"department/{department_id}/{dataset_slug}/{table_slug}/pipeline")
    with FileLock(lock_path):
        previous_curated = _previous_curated_columns(storage, department_id, dataset_slug, table_slug)

        if previous_curated is not None:
            removed = {row["name"] for row in previous_curated} - {col["name"] for col in raw_columns}
            if removed and not allow_column_removal:
                raise ValueError(
                    f"{table_id}: this run is missing {len(removed)} column(s) that exist in the "
                    f"previous curated snapshot ({', '.join(sorted(removed))}). If this is an "
                    f"intentional full refresh, pass allow_column_removal=True; if not, this source "
                    f"file is likely a partial/incremental submission, not the full current schema."
                )

        raw_path = f"department/{department_id}/{dataset_slug}/{table_slug}/raw/schemas/{ts}.csv"
        storage.write_csv(raw_path, raw_columns)
        logger.info(f"Stored raw schema -> {raw_path}")

        business_metadata = _business_metadata_from_rows(previous_curated) if previous_curated else {}
        if business_metadata_file:
            business_metadata.update(_load_business_metadata(business_metadata_file))

        curated_columns = curate_schema(raw_columns, business_metadata)
        warning_count = sum(1 for c in curated_columns if c["validation_warning"])

        curated_path = f"department/{department_id}/{dataset_slug}/{table_slug}/curated/schemas/{ts}.csv"
        storage.write_csv(curated_path, curated_columns)
        logger.info(
            f"Stored curated schema -> {curated_path} "
            f"({len(curated_columns)} column(s), {warning_count} warning(s))"
        )

    result = {
        "raw_path": raw_path,
        "curated_path": curated_path,
        "columns": curated_columns,
        "column_count": len(curated_columns),
        "warning_count": warning_count,
    }

    if openmetadata_client is not None:
        result["openmetadata"] = publish_table(openmetadata_client, storage, table_id)

    return result


if __name__ == "__main__":
    _storage = LocalObjectStorage(os.environ.get("STORAGE_ROOT", "storage"))

    # DEPARTMENT_NAME is optional -- set it to register a new department in
    # the same command; omit it once the department is already registered.
    if os.environ.get("DEPARTMENT_NAME"):
        lookups.register_department(_storage, lookups.slugify(os.environ["DEPARTMENT"]), os.environ["DEPARTMENT_NAME"])

    # OPENMETADATA_JWT_TOKEN is optional -- set it to publish to OpenMetadata
    # as part of this same run; omit it to only write raw/curated to storage.
    _client = None
    if os.environ.get("OPENMETADATA_JWT_TOKEN"):
        _client = get_client(
            host_port=os.environ.get("OPENMETADATA_HOST_PORT", "http://localhost:8585/api"),
            jwt_token=os.environ["OPENMETADATA_JWT_TOKEN"],
        )

    run(
        department=os.environ["DEPARTMENT"],
        dataset=os.environ["DATASET"],
        table_name=os.environ["TABLE_NAME"],
        source_file=os.environ["SOURCE_FILE"],
        storage=_storage,
        source_format=os.environ.get("SOURCE_FORMAT", "postgres_ddl"),
        schema_name=os.environ.get("SCHEMA_NAME", "public"),
        business_metadata_file=os.environ.get("BUSINESS_METADATA_FILE"),
        openmetadata_client=_client,
        allow_column_removal=os.environ.get("ALLOW_COLUMN_REMOVAL", "").strip().lower() in _TRUE_VALUES,
    )
