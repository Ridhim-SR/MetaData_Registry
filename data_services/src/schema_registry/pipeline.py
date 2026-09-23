import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from src.schema_registry import lookups
from src.schema_registry.csv_schema_parser import parse_csv_columns
from src.schema_registry.curate import curate_schema
from src.schema_registry.ddl_parser import parse_postgres_columns
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


def _load_business_metadata(path: str) -> dict[str, dict]:
    """Load a Field Dictionary export (CSV: name, business_description,
    tag, glossary_term, active) keyed by field name."""

    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))

    return {
        row["name"]: {
            "business_description": row.get("business_description", ""),
            "tag": row.get("tag", ""),
            "glossary_term": row.get("glossary_term", ""),
            "active": row.get("active", "").strip().lower() in _TRUE_VALUES,
        }
        for row in rows
    }


def run(
    department: str,
    dataset: str,
    table_name: str,
    source_file: str,
    storage: ObjectStorage,
    source_format: str = "postgres_ddl",
    schema_name: str = "public",
    business_metadata_file: str | None = None,
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

    Storage layout (each table gets its own folder, since tables in the
    same dataset can have unrelated structures):
        department/<department_id>/<dataset_slug>/<table_slug>/raw/schemas/<timestamp>.csv
        department/<department_id>/<dataset_slug>/<table_slug>/curated/schemas/<timestamp>.csv
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

    lookups.upsert_dataset(storage, dataset_id, department_id, dataset)
    lookups.upsert_table(storage, table_id, dataset_id, table_name, schema_name)

    parsed_columns = _PARSERS[source_format](source_file)
    raw_columns = [{"table_id": table_id, **col} for col in parsed_columns]
    logger.info(f"Parsed {len(raw_columns)} column(s) from {source_file}")

    ts = _timestamp()

    raw_path = f"department/{department_id}/{dataset_slug}/{table_slug}/raw/schemas/{ts}.csv"
    storage.write_csv(raw_path, raw_columns)
    logger.info(f"Stored raw schema -> {raw_path}")

    business_metadata = {}
    if business_metadata_file:
        business_metadata = _load_business_metadata(business_metadata_file)

    curated_columns = curate_schema(raw_columns, business_metadata)
    warning_count = sum(1 for c in curated_columns if c["validation_warning"])

    curated_path = f"department/{department_id}/{dataset_slug}/{table_slug}/curated/schemas/{ts}.csv"
    storage.write_csv(curated_path, curated_columns)
    logger.info(
        f"Stored curated schema -> {curated_path} "
        f"({len(curated_columns)} column(s), {warning_count} warning(s))"
    )

    return {
        "raw_path": raw_path,
        "curated_path": curated_path,
        "columns": curated_columns,
        "column_count": len(curated_columns),
        "warning_count": warning_count,
    }


if __name__ == "__main__":
    _storage = LocalObjectStorage(os.environ.get("STORAGE_ROOT", "storage"))

    # DEPARTMENT_NAME is optional -- set it to register a new department in
    # the same command; omit it once the department is already registered.
    if os.environ.get("DEPARTMENT_NAME"):
        lookups.register_department(_storage, lookups.slugify(os.environ["DEPARTMENT"]), os.environ["DEPARTMENT_NAME"])

    run(
        department=os.environ["DEPARTMENT"],
        dataset=os.environ["DATASET"],
        table_name=os.environ["TABLE_NAME"],
        source_file=os.environ["SOURCE_FILE"],
        storage=_storage,
        source_format=os.environ.get("SOURCE_FORMAT", "postgres_ddl"),
        schema_name=os.environ.get("SCHEMA_NAME", "public"),
        business_metadata_file=os.environ.get("BUSINESS_METADATA_FILE"),
    )
