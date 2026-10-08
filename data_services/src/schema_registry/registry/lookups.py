import re
from collections.abc import Callable
from datetime import datetime, timezone


from src.schema_registry.registry import paths
from src.storage.base import ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEPARTMENTS_PATH = "_lookups/departments.csv"
DATASETS_PATH = "_lookups/datasets.csv"
TABLES_PATH = "_lookups/tables.csv"
RUNS_PATH = "_lookups/runs.csv"

# One row per pipeline run (see pipeline.run): the audit trail for "what was
# submitted, what changed, who ran it, and whether it reached OpenMetadata".
RUN_FIELDS = [
    "run_id",
    "table_id",
    "ts",
    "mode",
    "source_hash",
    "operator",
    "added",
    "removed",
    "changed",
    "publish_status",
    "error",
]

# Filenames count as timestamped snapshots only if they match what
# pipeline._timestamp() writes -- anything else in the folder (a stray
# README, an editor backup, a manually dropped CSV) must never be picked
# as "the latest snapshot" to diff against or publish.
_SNAPSHOT_NAME = re.compile(r"^\d{8}T\d+Z\.csv$")


def slugify(value: str) -> str:
    """Canonicalize a department/dataset/table name so "Amplify Data" and
    "amplify_data" resolve to the same id and folder instead of silently
    becoming two unrelated registry entries.

    Raises ValueError when the result would be empty: a name made entirely
    of non-ASCII characters (a Hindi name typed in Devanagari, say) slugifies
    to "", which used to silently build ids like "pwd..t1" and folders named
    after nothing. Such a name needs an explicit ASCII id instead.
    """

    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if not slug:
        raise ValueError(
            f"Cannot build an id from {value!r}: it contains no ASCII letters or digits. "
            f"Names like this must be given an explicit ASCII id by the caller "
            f"(e.g. pass 'dept_1' for a department whose name is written only in Devanagari)."
        )
    return slug


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

    Locked per-path (storage.lock -- across machines on Wasabi) so
    concurrent callers writing to the same lookup file can't race on the
    read-modify-write and lose or corrupt rows."""

    with storage.lock(path):
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


DATASET_FIELDS = ("category", "api_available", "owner", "frequency", "timeline", "dataset_description")


def set_dataset_fields(storage: ObjectStorage, dataset_id: str, department_id: str, dataset_name: str, fields: dict) -> bool:
    """Set a dataset's fields to exactly `fields` -- a blank value clears
    it. Unlike upsert_dataset() (which keeps old values for blanks), this
    is for sync: catalog.yaml is reviewed in git and is the truth, so a
    field removed there must be removed here too. Returns True if anything
    changed."""

    new_row = {"dataset_id": dataset_id, "department_id": department_id, "dataset_name": dataset_name}
    new_row.update({field: (fields.get(field) or "") for field in DATASET_FIELDS})
    existing = _upsert(storage, DATASETS_PATH, "dataset_id", dataset_id, lambda _: new_row)
    changed = existing is None or any((existing.get(k) or "") != v for k, v in new_row.items())
    if changed:
        logger.info(f"Dataset fields set from catalog: {dataset_id}")
    return changed


def latest_curated_snapshot_path(
    storage: ObjectStorage, department_id: str, dataset_slug: str, table_slug: str
) -> str:
    """Path of the most recently written curated schema snapshot for one
    table. Filenames are fixed-width UTC timestamps, so lexical order ==
    chronological order -- shared by openmetadata/publish.py (publish the
    latest) and pipeline.py (diff a new run against the latest).

    Only files named like pipeline._timestamp()'s output count: a stray
    non-snapshot file dropped in the folder (a README, a ~backup, a CSV
    with a different name) must never be mistaken for the latest snapshot."""

    prefix = paths.curated_schemas_prefix(department_id, dataset_slug, table_slug)
    # Local storage on Windows returns backslash-separated paths, S3 returns
    # forward slashes -- normalize before taking the filename.
    files = [f for f in storage.list(prefix) if _SNAPSHOT_NAME.match(f.replace("\\", "/").rsplit("/", 1)[-1])]
    if not files:
        raise FileNotFoundError(f"No curated schema under {prefix} -- run the pipeline for this table first.")
    return files[-1]


def upsert_table(storage: ObjectStorage, table_id: str, dataset_id: str, table_name: str, schema_name: str) -> None:
    existing = _upsert(
        storage,
        TABLES_PATH,
        "table_id",
        table_id,
        # `deleted` reset to "": re-ingesting a table that was previously
        # soft-deleted is an explicit "this table is back" action, so the
        # mark must not survive a fresh run().
        lambda _: {
            "table_id": table_id,
            "dataset_id": dataset_id,
            "table_name": table_name,
            "schema_name": schema_name,
            "deleted": "",
        },
    )
    logger.info(f"Table {'re-registered' if existing else 'registered'}: {table_id}")


def soft_delete_table(storage: ObjectStorage, table_id: str) -> dict:
    """Mark a table as deleted in the registry without dropping its row --
    the snapshot history and the run log stay readable, but publish_table()
    refuses to push a soft-deleted table to OpenMetadata anymore.

    This is the registry half of "renaming a table leaves the old one
    orphaned in OpenMetadata": soft-delete here, then delete the OpenMetadata
    entity (see openmetadata.publish.delete_table)."""

    with storage.lock(TABLES_PATH):
        rows = storage.read_csv(TABLES_PATH) if storage.exists(TABLES_PATH) else []
        row = next((r for r in rows if r["table_id"] == table_id), None)
        if row is None:
            raise ValueError(f"Unknown table_id '{table_id}' -- not found in {TABLES_PATH}")
        if row.get("deleted"):
            logger.info(f"Table already soft-deleted: {table_id}")
            return row
        row["deleted"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        storage.write_csv(TABLES_PATH, rows)
    logger.info(f"Table soft-deleted from the registry: {table_id} ({row['deleted']})")
    return row


def append_run(storage: ObjectStorage, row: dict) -> None:
    """Append one row to the run log (`_lookups/runs.csv`), filling any
    missing field with "" so a partial row (a run that failed early) still
    writes a complete, well-formed line."""

    _upsert(
        storage,
        RUNS_PATH,
        "run_id",
        str(row.get("run_id", "")),
        lambda _: {field: str(row.get(field, "")) for field in RUN_FIELDS},
    )


def update_run(storage: ObjectStorage, run_id: str, **fields) -> None:
    """Update fields of an existing run row (e.g. record that its publish
    finally succeeded). Unknown field names are rejected rather than silently
    dropped -- a typo'd column here would quietly lose audit data."""

    unknown = set(fields) - set(RUN_FIELDS)
    if unknown:
        raise ValueError(f"Unknown run field(s) {sorted(unknown)}; allowed: {RUN_FIELDS}")

    with storage.lock(RUNS_PATH):
        rows = storage.read_csv(RUNS_PATH) if storage.exists(RUNS_PATH) else []
        row = next((r for r in rows if r["run_id"] == run_id), None)
        if row is None:
            raise ValueError(f"Unknown run_id '{run_id}' -- not found in {RUNS_PATH}")
        row.update({k: str(v) for k, v in fields.items()})
        storage.write_csv(RUNS_PATH, rows)


def unpublished_runs(storage: ObjectStorage) -> dict[str, dict]:
    """{table_id: newest run row that wrote a snapshot but is not in
    OpenMetadata yet} -- what the republish command iterates over.

    Only rows whose run actually wrote a snapshot count (`publish_status`
    != "not_attempted"), and the newest such row wins per table, so a later
    failed run doesn't hide the snapshot an earlier run left unpublished."""

    if not storage.exists(RUNS_PATH):
        return {}
    with_snapshot: dict[str, dict] = {}
    for row in storage.read_csv(RUNS_PATH):  # append-ordered: last wins
        if row.get("publish_status") != "not_attempted":
            with_snapshot[row["table_id"]] = row
    return {table_id: row for table_id, row in with_snapshot.items() if row.get("publish_status") != "published"}
