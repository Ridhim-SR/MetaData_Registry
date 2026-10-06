import os
import re
from collections.abc import Callable

from src.utils.config import load_env
from filelock import FileLock

from src.schema_registry.registry import paths
from src.storage import storage_from_env
from src.storage.base import ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEPARTMENTS_PATH = "_lookups/departments.csv"
DATASETS_PATH = "_lookups/datasets.csv"
TABLES_PATH = "_lookups/tables.csv"


def slugify(value: str) -> str:
    """Canonicalize a department/dataset/table name so "Amplify Data" and
    "amplify_data" resolve to the same id and folder instead of silently
    becoming two unrelated registry entries."""

    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _upsert(
    storage: ObjectStorage,
    path: str,
    key: str,
    key_value: str,
    build_row: Callable[[dict | None], dict],
) -> dict | None:
    """Insert the row for `key_value` into the lookup CSV at `path`, or
    replace the existing one -- e.g. re-registering a dataset once its
    Owner/Retention/Lineage are confirmed updates that row instead of being
    silently ignored.

    `build_row(existing)` makes the new row from the current one (None if
    there isn't one), called while the lock is held -- so a row that
    carries fields forward from the old one (upsert_dataset) can't be built
    from a stale read and overwrite a concurrent run's changes. Returns the
    existing row, or None if this inserted a new one.

    Locked per-path so concurrent callers (parallel ingestion runs writing
    to the same lookup file) can't race on the read-modify-write and lose
    or corrupt rows."""

    with FileLock(storage.lock_path(path)):
        rows = storage.read_csv(path) if storage.exists(path) else []
        existing = next((r for r in rows if r[key] == key_value), None)
        rows = [r for r in rows if r[key] != key_value]
        rows.append(build_row(existing))
        storage.write_csv(path, rows)
        return existing


def register_department(storage: ObjectStorage, department_id: str, department_name: str) -> None:
    """Explicitly add a department to the controlled registry.

    This is a deliberate one-time action, not something pipeline.run()
    does automatically -- auto-creating departments from whatever text
    gets passed is exactly what let "Public Works Department"/"PWD Dept"/
    "pwd" fragment into unrelated entries (slugify only normalizes
    formatting, not synonyms/abbreviations of the same department).
    """

    existing = _upsert(
        storage,
        DEPARTMENTS_PATH,
        "department_id",
        department_id,
        lambda _: {"department_id": department_id, "department_name": department_name},
    )
    logger.info(f"Department {'re-registered' if existing else 'registered'}: {department_id} ({department_name})")


def department_exists(storage: ObjectStorage, department_id: str) -> bool:
    if not storage.exists(DEPARTMENTS_PATH):
        return False
    return any(r["department_id"] == department_id for r in storage.read_csv(DEPARTMENTS_PATH))


def _find(storage: ObjectStorage, path: str, key: str, value: str) -> dict | None:
    if not storage.exists(path):
        return None
    return next((r for r in storage.read_csv(path) if r[key] == value), None)


def get_dataset(storage: ObjectStorage, dataset_id: str) -> dict | None:
    return _find(storage, DATASETS_PATH, "dataset_id", dataset_id)


def get_table(storage: ObjectStorage, table_id: str) -> dict | None:
    return _find(storage, TABLES_PATH, "table_id", table_id)


def upsert_dataset(
    storage: ObjectStorage,
    dataset_id: str,
    department_id: str,
    dataset_name: str,
    category: str = "",
    api_available: str = "",
    owner: str = "",
    frequency: str = "",
    timeline: str = "",
    dataset_description: str = "",
) -> None:
    """Dataset-level fields (per the governance meeting): `category` (MDSF
    CAT-1/2/3/4 -- the dataset's overall classification, separate from
    curate.py's per-column `classification`), `api_available` (Y/N),
    `owner`, `frequency` (how often the data is refreshed/submitted), and
    `timeline` (the period/date range the dataset covers). These live here,
    once per dataset, rather than being repeated on every row of the
    curated schema CSV.

    A blank ("") argument means "not provided on this call" and carries
    forward whatever this dataset already has for that field, rather than
    wiping it -- same philosophy as business_metadata_file's carry-forward
    for column metadata. This matters because run() calls this once per
    table: without carry-forward, ingesting a dataset's 2nd/3rd/... table
    without re-typing its already-confirmed owner/category/etc. every time
    would silently blank them back out. To deliberately clear a field,
    edit `_lookups/datasets.csv` directly."""

    def _merged(existing: dict | None) -> dict:
        existing = existing or {}
        return {
            "dataset_id": dataset_id,
            "department_id": department_id,
            "dataset_name": dataset_name,
            "category": category or existing.get("category", ""),
            "api_available": api_available or existing.get("api_available", ""),
            "owner": owner or existing.get("owner", ""),
            "frequency": frequency or existing.get("frequency", ""),
            "timeline": timeline or existing.get("timeline", ""),
            "dataset_description": dataset_description or existing.get("dataset_description", ""),
        }

    # The carry-forward merge runs inside _upsert's lock -- reading the
    # existing row before taking the lock let two runs for tables in the
    # same dataset each overwrite the other's owner/category.
    existing = _upsert(storage, DATASETS_PATH, "dataset_id", dataset_id, _merged)
    logger.info(f"Dataset {'updated' if existing else 'created'}: {dataset_id}")


def latest_curated_snapshot_path(
    storage: ObjectStorage, department_id: str, dataset_slug: str, table_slug: str
) -> str:
    """Path of the most recently written curated schema snapshot for one
    table. Filenames are fixed-width UTC timestamps, so lexical order ==
    chronological order -- shared by openmetadata/publish.py (publish the
    latest) and pipeline.py (diff a new run against the latest)."""

    prefix = paths.curated_schemas_prefix(department_id, dataset_slug, table_slug)
    files = storage.list(prefix)
    if not files:
        raise FileNotFoundError(f"No curated schema under {prefix} -- run the pipeline for this table first.")
    return files[-1]


def upsert_table(storage: ObjectStorage, table_id: str, dataset_id: str, table_name: str, schema_name: str) -> None:
    existing = _upsert(
        storage,
        TABLES_PATH,
        "table_id",
        table_id,
        lambda _: {"table_id": table_id, "dataset_id": dataset_id, "table_name": table_name, "schema_name": schema_name},
    )
    logger.info(f"Table {'re-registered' if existing else 'registered'}: {table_id}")


if __name__ == "__main__":
    load_env()
    register_department(
        storage_from_env(),
        slugify(os.environ["DEPARTMENT_ID"]),
        os.environ["DEPARTMENT_NAME"],
    )
