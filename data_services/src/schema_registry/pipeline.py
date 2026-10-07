import csv
import io
import os
from datetime import datetime, timezone

from src.utils.config import load_env
from metadata.ingestion.ometa.ometa_api import OpenMetadata

from src.schema_registry import inputs
from src.schema_registry.registry import lookups, paths
from src.schema_registry.curate import curate_schema, validate_schema
from src.schema_registry.openmetadata.publish import get_client, publish_table
from src.schema_registry.parsers.csv_schema_parser import parse_csv_text
from src.schema_registry.parsers.ddl_parser import parse_postgres_columns
from src.storage import storage_from_env
from src.storage.base import ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)

_TRUE_VALUES = {"y", "yes", "true", "1"}

# source_format -> parser over the submission's text (see inputs.read_input
# for where that text comes from: a local path or a storage:<key>)
_PARSERS = {
    "postgres_ddl": parse_postgres_columns,
    "csv": parse_csv_text,
}


def _timestamp() -> str:
    # microsecond resolution -- second resolution collides on back-to-back
    # runs (e.g. a batch loop) and silently overwrites the previous snapshot
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


_METADATA_TEXT_FIELDS = ("business_description", "tag", "classification", "glossary_term")


def _business_metadata_from_rows(rows: list[dict]) -> dict[str, dict]:
    """Shape a list of CSV rows (a Field Dictionary export, or a previous
    curated snapshot) into the {name: {business_description, tag,
    classification, glossary_term, active}} form curate_schema() expects.

    Only fields with a non-blank value are included -- a blank cell (or a
    column the file doesn't have at all) means "not answered in this file",
    not "clear this answer". That's what lets _merge_business_metadata()
    keep a previous answer instead of a blank silently overwriting it, and
    keeps a file with no `active` column from marking every column it
    mentions as inactive."""

    metadata: dict[str, dict] = {}
    for row in rows:
        meta = {field: row[field].strip() for field in _METADATA_TEXT_FIELDS if (row.get(field) or "").strip()}
        active = (row.get("active") or "").strip().lower()
        if active:
            meta["active"] = active in _TRUE_VALUES
        metadata[row["name"]] = meta
    return metadata


def _merge_business_metadata(previous: dict[str, dict], new: dict[str, dict]) -> dict[str, dict]:
    """Field-by-field merge: a value answered in `new` wins, anything it
    leaves out keeps `previous`'s answer. A whole-dict replace here is what
    let a description-only Field Dictionary re-run reset a hand-set
    classification back to the auto one and wipe the glossary term."""

    merged = {name: dict(meta) for name, meta in previous.items()}
    for name, meta in new.items():
        merged.setdefault(name, {}).update(meta)
    return merged


def _parse_business_metadata(text: str) -> dict[str, dict]:
    """A Field Dictionary export (CSV: name, business_description, tag,
    classification, glossary_term, active), keyed by field name."""

    return _business_metadata_from_rows(list(csv.DictReader(io.StringIO(text))))


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
    category: str = "",
    api_available: str = "",
    owner: str = "",
    frequency: str = "",
    timeline: str = "",
    dataset_description: str = "",
    openmetadata_client: OpenMetadata | None = None,
    allow_column_removal: bool = False,
    allow_category_below_columns: bool = False,
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

    category/api_available/owner/frequency/timeline/dataset_description are
    dataset-level fields (decided in the governance meeting) stored once
    per dataset in `_lookups/datasets.csv`, not repeated per column row --
    `category` (MDSF CAT-1/2/3/4) and `dataset_description` are also pushed
    to OpenMetadata as the Database entity's tag/description by
    publish_table(). Left blank if not yet confirmed -- re-run with the
    answer once it comes in to update the existing entry.

    Storage layout (each table gets its own folder, since tables in the
    same dataset can have unrelated structures) -- defined once in
    paths.py, not repeated as an f-string in every function that needs it:
        department/<department_id>/<dataset_slug>/<table_slug>/raw/schemas/<timestamp>.csv
        department/<department_id>/<dataset_slug>/<table_slug>/curated/schemas/<timestamp>.csv

    `openmetadata_client`: if given, the freshly curated snapshot is also
    published to OpenMetadata (via openmetadata.publish.publish_table) as
    the last step of this same call, so ingest -> curate -> publish is one
    pipeline run instead of two separate manual steps. Omit it to keep
    this call to storage only.

    `allow_category_below_columns`: passed through to publish_table() --
    see its check that the dataset's category is at least as high as its
    most sensitive column's classification.

    Re-running for a table that's already been curated before diffs the new
    source against the *previous* curated snapshot instead of blindly
    trusting this run's input as the complete truth:
      - Columns present before but missing from this run raise a ValueError
        naming them, unless `allow_column_removal=True` -- this is what
        catches a partial/incremental submission (e.g. a department sends
        only its 2 new columns, expecting an "append") before it silently
        drops every other previously-published column from OpenMetadata.
      - `business_description`/`tag`/`classification`/`glossary_term`/
        `active` are merged field by field: any field this run's
        `business_metadata_file` leaves blank (or doesn't have as a column,
        or no file at all) is carried forward from the previous snapshot
        rather than reset -- so a description-only file doesn't erase a
        hand-set classification or glossary term. To change an answer,
        send the new value; a blank never clears one.
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

    # Everything that can reject this submission runs before anything is
    # written -- parse, schema checks, the metadata file, and (inside the
    # lock) the column-removal guard. The registry (_lookups/) is only
    # updated once the new snapshots are stored, so a rejected run leaves
    # tables.csv/datasets.csv exactly as they were.
    ts = _timestamp()

    source_bytes, source_name = inputs.read_input(storage, source_file)
    parsed_columns = _PARSERS[source_format](inputs.decode(source_bytes))
    validate_schema(table_id, parsed_columns)
    raw_columns = [{"table_id": table_id, "ingestion_timestamp": ts, **col} for col in parsed_columns]
    logger.info(f"Parsed {len(raw_columns)} column(s) from {source_file}")

    metadata_bytes, metadata_name, submitted_metadata = None, None, {}
    if business_metadata_file:
        metadata_bytes, metadata_name = inputs.read_input(storage, business_metadata_file)
        submitted_metadata = _parse_business_metadata(inputs.decode(metadata_bytes))
    column_names = {col["name"] for col in raw_columns}
    unmatched_metadata_names = sorted(set(submitted_metadata) - column_names)
    if unmatched_metadata_names:
        logger.warning(
            f"{table_id}: business_metadata_file has {len(unmatched_metadata_names)} name(s) matching no "
            f"column, ignored -- check for typos: {', '.join(unmatched_metadata_names)}"
        )

    # Locked per table: reading the previous snapshot, deciding whether a
    # removal is allowed, and writing the new raw+curated snapshot must be
    # one atomic step, or two concurrent runs for the same table (e.g. a
    # double-triggered CLI call, two batch jobs targeting the same row)
    # could both read the same "previous" state and both proceed on stale
    # information.
    with storage.lock(paths.pipeline_lock_path(department_id, dataset_slug, table_slug)):
        previous_curated = _previous_curated_columns(storage, department_id, dataset_slug, table_slug)

        if previous_curated is not None:
            removed = {row["name"] for row in previous_curated} - column_names
            if removed and not allow_column_removal:
                raise ValueError(
                    f"{table_id}: this run is missing {len(removed)} column(s) that exist in the "
                    f"previous curated snapshot ({', '.join(sorted(removed))}). If this is an "
                    f"intentional full refresh, pass allow_column_removal=True; if not, this source "
                    f"file is likely a partial/incremental submission, not the full current schema."
                )

        business_metadata = _business_metadata_from_rows(previous_curated) if previous_curated else {}
        business_metadata = _merge_business_metadata(business_metadata, submitted_metadata)

        curated_columns = curate_schema(raw_columns, business_metadata)
        warning_count = sum(1 for c in curated_columns if c["validation_warning"])

        # The exact files this run parsed, byte for byte, beside the raw
        # schema they produced -- evidence for every snapshot, and what lets
        # a rebuild work from storage alone.
        source_archive = paths.raw_source_path(department_id, dataset_slug, table_slug, ts, source_name)
        source_sha256 = inputs.archive(storage, source_archive, source_bytes)
        metadata_archive = None
        if metadata_bytes is not None:
            metadata_archive = paths.raw_source_path(
                department_id, dataset_slug, table_slug, ts, f"metadata__{metadata_name}"
            )
            inputs.archive(storage, metadata_archive, metadata_bytes)
        logger.info(f"Archived source -> {source_archive} (sha256 {source_sha256[:12]}...)")

        raw_path = paths.raw_schema_path(department_id, dataset_slug, table_slug, ts)
        storage.write_csv(raw_path, raw_columns)
        logger.info(f"Stored raw schema -> {raw_path}")

        curated_path = paths.curated_schema_path(department_id, dataset_slug, table_slug, ts)
        storage.write_csv(curated_path, curated_columns)
        logger.info(
            f"Stored curated schema -> {curated_path} "
            f"({len(curated_columns)} column(s), {warning_count} warning(s))"
        )

    lookups.upsert_dataset(
        storage, dataset_id, department_id, dataset,
        category=category, api_available=api_available, owner=owner,
        frequency=frequency, timeline=timeline, dataset_description=dataset_description,
    )
    lookups.upsert_table(storage, table_id, dataset_id, table_name, schema_name)

    result = {
        "raw_path": raw_path,
        "curated_path": curated_path,
        "columns": curated_columns,
        "column_count": len(curated_columns),
        "warning_count": warning_count,
        "unmatched_metadata_names": unmatched_metadata_names,
        "source_archive_path": source_archive,
        "source_sha256": source_sha256,
        "metadata_archive_path": metadata_archive,
    }

    if openmetadata_client is not None:
        result["openmetadata"] = publish_table(
            openmetadata_client, storage, table_id, allow_category_below_columns=allow_category_below_columns
        )

    return result


if __name__ == "__main__":
    load_env()
    _storage = storage_from_env()

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
        # Dataset-level fields -- optional, only needed once per dataset
        # (upsert_dataset() carries forward whatever's already set, so a
        # later run for a different table in the same dataset can omit these).
        category=os.environ.get("CATEGORY", ""),
        api_available=os.environ.get("API_AVAILABLE", ""),
        owner=os.environ.get("OWNER", ""),
        frequency=os.environ.get("FREQUENCY", ""),
        timeline=os.environ.get("TIMELINE", ""),
        dataset_description=os.environ.get("DATASET_DESCRIPTION", ""),
        openmetadata_client=_client,
        allow_column_removal=os.environ.get("ALLOW_COLUMN_REMOVAL", "").strip().lower() in _TRUE_VALUES,
        allow_category_below_columns=os.environ.get("ALLOW_CATEGORY_BELOW_COLUMNS", "").strip().lower()
        in _TRUE_VALUES,
    )
