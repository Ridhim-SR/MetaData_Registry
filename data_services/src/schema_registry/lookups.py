import os
import re

from filelock import FileLock

from src.storage.base import ObjectStorage
from src.storage.local import LocalObjectStorage

DEPARTMENTS_PATH = "_lookups/departments.csv"
DATASETS_PATH = "_lookups/datasets.csv"
TABLES_PATH = "_lookups/tables.csv"


def slugify(value: str) -> str:
    """Canonicalize a department/dataset/table name so "Amplify Data" and
    "amplify_data" resolve to the same id and folder instead of silently
    becoming two unrelated registry entries."""

    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _upsert(storage: ObjectStorage, path: str, key: str, row: dict) -> None:
    """Add `row` to the lookup CSV at `path` unless its key already exists.

    Locked per-path so concurrent callers (parallel ingestion runs writing
    to the same lookup file) can't race on the read-check-write and lose
    or corrupt rows."""

    with FileLock(storage.lock_path(path)):
        rows = storage.read_csv(path) if storage.exists(path) else []

        if any(r[key] == row[key] for r in rows):
            return

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


def upsert_dataset(storage: ObjectStorage, dataset_id: str, department_id: str, dataset_name: str) -> None:
    _upsert(
        storage,
        DATASETS_PATH,
        "dataset_id",
        {"dataset_id": dataset_id, "department_id": department_id, "dataset_name": dataset_name},
    )


def upsert_table(storage: ObjectStorage, table_id: str, dataset_id: str, table_name: str, schema_name: str) -> None:
    _upsert(
        storage,
        TABLES_PATH,
        "table_id",
        {"table_id": table_id, "dataset_id": dataset_id, "table_name": table_name, "schema_name": schema_name},
    )


if __name__ == "__main__":
    register_department(
        LocalObjectStorage(os.environ.get("STORAGE_ROOT", "storage")),
        slugify(os.environ["DEPARTMENT_ID"]),
        os.environ["DEPARTMENT_NAME"],
    )
