import os
import re

from filelock import FileLock

from src.storage import storage_from_env
from src.storage.base import ObjectStorage

DEPARTMENTS_PATH = "_lookups/departments.csv"
DATASETS_PATH = "_lookups/datasets.csv"
TABLES_PATH = "_lookups/tables.csv"


def slugify(value: str) -> str:
    """Canonicalize a department/dataset/table name so "Amplify Data" and
    "amplify_data" resolve to the same id and folder instead of silently
    becoming two unrelated registry entries."""

    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _upsert(storage: ObjectStorage, path: str, key: str, row: dict) -> None:
    """Insert `row` into the lookup CSV at `path`, or replace the existing
    row with the same key -- e.g. re-registering a dataset once its Owner/
    Retention/Lineage are confirmed updates that row instead of being
    silently ignored.

    Locked per-path so concurrent callers (parallel ingestion runs writing
    to the same lookup file) can't race on the read-modify-write and lose
    or corrupt rows."""

    with FileLock(storage.lock_path(path)):
        rows = storage.read_csv(path) if storage.exists(path) else []
        rows = [r for r in rows if r[key] != row[key]]
        rows.append(row)
        storage.write_csv(path, rows)


def register_department(storage: ObjectStorage, department_id: str, department_name: str) -> None:
    """Explicitly add a department to the controlled registry.

    This is a deliberate one-time action, not something pipeline.run()
    does automatically -- auto-creating departments from whatever text
    gets passed is exactly what let "Public Works Department"/"PWD Dept"/
    "pwd" fragment into unrelated entries (slugify only normalizes
    formatting, not synonyms/abbreviations of the same department).
    """

    _upsert(
        storage,
        DEPARTMENTS_PATH,
        "department_id",
        {"department_id": department_id, "department_name": department_name},
    )


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
    owner: str = "",
    fiduciary: str = "",
    processor: str = "",
    risk_classification: str = "",
    retention_policy: str = "",
    lineage: str = "",
) -> None:
    """Governance fields (owner/fiduciary/processor/risk/retention/lineage)
    are dataset-level, not per-column, so they live here rather than being
    repeated on every row of the curated schema CSV. Left blank ("") when
    not yet confirmed -- call again once an answer comes in to update it,
    same as unanswered Field Dictionary columns."""

    _upsert(
        storage,
        DATASETS_PATH,
        "dataset_id",
        {
            "dataset_id": dataset_id,
            "department_id": department_id,
            "dataset_name": dataset_name,
            "owner": owner,
            "fiduciary": fiduciary,
            "processor": processor,
            "risk_classification": risk_classification,
            "retention_policy": retention_policy,
            "lineage": lineage,
        },
    )


def latest_curated_snapshot_path(
    storage: ObjectStorage, department_id: str, dataset_slug: str, table_slug: str
) -> str:
    """Path of the most recently written curated schema snapshot for one
    table. Filenames are fixed-width UTC timestamps, so lexical order ==
    chronological order -- shared by openmetadata_publish.py (publish the
    latest) and pipeline.py (diff a new run against the latest)."""

    prefix = f"department/{department_id}/{dataset_slug}/{table_slug}/curated/schemas/"
    files = storage.list(prefix)
    if not files:
        raise FileNotFoundError(f"No curated schema under {prefix} -- run the pipeline for this table first.")
    return files[-1]


def upsert_table(storage: ObjectStorage, table_id: str, dataset_id: str, table_name: str, schema_name: str) -> None:
    _upsert(
        storage,
        TABLES_PATH,
        "table_id",
        {"table_id": table_id, "dataset_id": dataset_id, "table_name": table_name, "schema_name": schema_name},
    )


if __name__ == "__main__":
    register_department(
        storage_from_env(),
        slugify(os.environ["DEPARTMENT_ID"]),
        os.environ["DEPARTMENT_NAME"],
    )
