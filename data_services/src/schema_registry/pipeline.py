import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from src.schema_registry.curate import curate_schema
from src.schema_registry.ddl_parser import parse_postgres_columns
from src.storage.base import ObjectStorage
from src.storage.local import LocalObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)

_TRUE_VALUES = {"y", "yes", "true", "1"}


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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
    raw_ddl_file: str,
    storage: ObjectStorage,
    business_metadata_file: str | None = None,
) -> dict:
    """Parse a raw Postgres column-list dump, validate/standardize it,
    and store both the raw and curated schema versions as CSV.

    Storage layout:
        <department>/<dataset>/raw/schemas/<timestamp>.csv
        <department>/<dataset>/curated/schemas/<timestamp>.csv
    """

    logger.info(f"Schema ingestion started: {department}/{dataset}")

    ddl_text = Path(raw_ddl_file).read_text()
    raw_columns = parse_postgres_columns(ddl_text)
    logger.info(f"Parsed {len(raw_columns)} column(s) from {raw_ddl_file}")

    ts = _timestamp()

    raw_path = f"{department}/{dataset}/raw/schemas/{ts}.csv"
    storage.write_csv(raw_path, raw_columns)
    logger.info(f"Stored raw schema -> {raw_path}")

    business_metadata = {}
    if business_metadata_file:
        business_metadata = _load_business_metadata(business_metadata_file)

    curated_columns = curate_schema(raw_columns, business_metadata)
    warning_count = sum(1 for c in curated_columns if c["validation_warning"])

    curated_path = f"{department}/{dataset}/curated/schemas/{ts}.csv"
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
    run(
        department=os.environ["DEPARTMENT"],
        dataset=os.environ["DATASET"],
        raw_ddl_file=os.environ["RAW_DDL_FILE"],
        storage=LocalObjectStorage(os.environ.get("STORAGE_ROOT", "storage")),
        business_metadata_file=os.environ.get("BUSINESS_METADATA_FILE"),
    )
