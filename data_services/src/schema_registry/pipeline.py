import csv
import io
import os
import uuid
from datetime import datetime, timezone

from src.utils.config import load_env
from metadata.ingestion.ometa.ometa_api import OpenMetadata

from src.schema_registry import inputs
from src.schema_registry.registry import lookups, paths
from src.schema_registry.curate import CATEGORY_LEVELS, curate_schema, validate_category, validate_schema
from src.schema_registry.openmetadata.publish import get_client, publish_table
from src.schema_registry.parsers import agriculture_parser
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

# Fields the per-run diff compares between the previous curated snapshot and
# this run's. The structural ones are the whole reason the diff exists: a
# data_type or nullability change used to pass unnoticed on its way to
# OpenMetadata. The governance ones catch a column being reclassified.
_DIFF_FIELDS = ("data_type", "nullable", "length", "scale", "classification", "tag", "glossary_term")


def parse_source(department_id: str, table_name: str, source_format: str, text: str) -> list[dict]:
    """Pick the parser for this file: a department's own parser if it has
    one, otherwise the shared parser for the file's format.

    To give a department its own parser: write parsers/<dept>_parser.py with
    parse_table(text, table_name) -> columns (or None when the file isn't
    that department's layout), import it above, and replace that
    department's `pass` below with
        return <dept>_parser.parse_table(text, table_name)
    """

    if department_id == "agri_dept":
        # One CSV holding several tables side by side, which the shared
        # per-format parser can't read -- its own parser picks out this
        # table's block. None means "not that layout", so the per-table
        # CSVs preprocessing wrote (and any DDL dump) still go through the
        # shared parser below.
        block = agriculture_parser.parse_table(text, table_name)
        if block is not None:
            return block
    # elif department_id == "<next_department>":
    #     pass

    return _PARSERS[source_format](text)


def _timestamp() -> str:
    # microsecond resolution -- second resolution collides on back-to-back
    # runs (e.g. a batch loop) and silently overwrites the previous snapshot
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _operator(explicit: str = "") -> str:
    """Who ran this: an explicit argument wins, else the environment
    (OPERATOR, then the login name) -- the run log is only useful if it says
    whose machine/CI job produced the change."""

    if explicit:
        return explicit
    return os.environ.get("OPERATOR") or os.environ.get("USER") or os.environ.get("USERNAME") or ""


def _norm(value) -> str:
    """CSV round-trips everything to text, while the current run still has
    real bools/ints (nullable=True vs the previous row's "True") -- compare
    them as text or every field would look changed on every run."""

    return "" if value is None else str(value)


def _diff_columns(previous: list[dict] | None, current: list[dict]) -> list[dict]:
    """Rows for the per-run diff file: `change` is added/removed/changed,
    one row per changed field (not per column) so "data_type: integer ->
    bigint" is visible as exactly that.

    `previous` is None on a table's first-ever run, so every column counts
    as added -- that run did add them, and the log should say so."""

    previous_by_name = {row["name"]: row for row in previous or []}
    current_by_name = {row["name"]: row for row in current}
    rows: list[dict] = []

    for name, row in current_by_name.items():
        if name not in previous_by_name:
            rows.append({"change": "added", "column": name, "field": "column", "before": "", "after": _norm(row.get("data_type"))})
            continue
        before_row = previous_by_name[name]
        for field in _DIFF_FIELDS:
            before, after = _norm(before_row.get(field)), _norm(row.get(field))
            if before != after:
                rows.append({"change": "changed", "column": name, "field": field, "before": before, "after": after})

    for name, row in previous_by_name.items():
        if name not in current_by_name:
            rows.append({"change": "removed", "column": name, "field": "column", "before": _norm(row.get("data_type")), "after": ""})

    return rows


def _summarize_diff(diff_rows: list[dict], has_previous: bool) -> tuple[str, int, int, int]:
    """(processing mode, added, removed, changed) for the run log.

    mode is what the README's Known limitations used to say was never
    recorded: how this run related to what was there before.
      initial_load  -- nothing to compare against (first run)
      append        -- only new columns
      full_refresh  -- columns were removed (allow_column_removal=True)
      update        -- columns changed in place, or nothing structural changed
    """

    added = sum(1 for row in diff_rows if row["change"] == "added")
    removed = sum(1 for row in diff_rows if row["change"] == "removed")
    changed = len({row["column"] for row in diff_rows if row["change"] == "changed"})

    if not has_previous:
        mode = "initial_load"
    elif removed:
        mode = "full_refresh"
    elif added:
        mode = "append"
    else:
        mode = "update"
    return mode, added, removed, changed


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
    operator: str = "",
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
        department/<department_id>/<dataset_slug>/<table_slug>/raw/source/<ts><name>    original submission + <ts><name>.sha256
        department/<department_id>/<dataset_slug>/<table_slug>/raw/schemas/<ts>.csv    parser's output
        department/<department_id>/<dataset_slug>/<table_slug>/curated/schemas/<ts>.csv
        department/<department_id>/<dataset_slug>/<table_slug>/diffs/<ts>.csv          what this run changed
        _lookups/runs.csv                                                              one audit row per run

    Every run appends one row to `_lookups/runs.csv` -- including runs that
    fail -- recording run_id, table_id, ts, mode (initial_load / append /
    update / full_refresh), source_hash, operator, the added/removed/
    changed counts, publish_status and the error if there was one. That row
    is written from a `finally`, so a parser error, a bad tag value or a
    rejected partial submission all still leave a record.

    `openmetadata_client`: if given, the freshly curated snapshot is also
    published to OpenMetadata (via openmetadata.publish.publish_table) as
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

    ts = _timestamp()
    run_id = uuid.uuid4().hex
    operator = _operator(operator)

    # Everything the run log row needs, defaulted before anything can fail:
    # `finally` writes it whatever happens, so these must always be bound.
    #
    # publish_status vocabulary (what happened to *this run's* snapshot):
    #   not_attempted  failed before a curated snapshot was written
    #   unpublished    snapshot in storage, not in OpenMetadata yet (a
    #                  storage-only run, or a failure before the publish step)
    #   published      snapshot is live in OpenMetadata
    #   failed         publish attempted and raised -- republish fixes these
    table_id = ""
    mode = ""
    added = removed = changed = 0
    source_hash = ""
    publish_status = "not_attempted"
    error = ""

    try:
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

        # Rejected here, before the value reaches _lookups/datasets.csv --
        # an unvalidated category used to be stored as-is and then turned
        # into a brand-new tag in OpenMetadata by publish_table().
        if category and not validate_category(category):
            raise ValueError(
                f"{dataset_id}: unknown category '{category}' -- allowed: "
                f"{', '.join(CATEGORY_LEVELS)} (MDSF CAT levels, exactly as written)."
            )

        logger.info(f"Schema ingestion started: {table_id} (format: {source_format})")

        # Everything that can reject this submission runs before anything is
        # written -- parse, schema checks, the metadata file, and (inside the
        # lock) the column-removal guard. The registry (_lookups/) is only
        # updated once the new snapshots are stored, so a rejected run leaves
        # tables.csv/datasets.csv exactly as they were.
        source_bytes, source_name = inputs.read_input(storage, source_file)
        parsed_columns = parse_source(department_id, table_name, source_format, inputs.decode(source_bytes))
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

            business_metadata = _business_metadata_from_rows(previous_curated) if previous_curated else {}
            business_metadata = _merge_business_metadata(business_metadata, submitted_metadata)

            curated_columns = curate_schema(raw_columns, business_metadata)

            # Diff (and therefore mode/counts) before the removal guard, so a
            # rejected partial submission still logs what it was missing.
            diff_rows = _diff_columns(previous_curated, curated_columns)
            mode, added, removed, changed = _summarize_diff(diff_rows, previous_curated is not None)

            if previous_curated is not None:
                removed_names = {row["name"] for row in previous_curated} - column_names
                if removed_names and not allow_column_removal:
                    raise ValueError(
                        f"{table_id}: this run is missing {len(removed_names)} column(s) that exist in the "
                        f"previous curated snapshot ({', '.join(sorted(removed_names))}). If this is an "
                        f"intentional full refresh, pass allow_column_removal=True; if not, this source "
                        f"file is likely a partial/incremental submission, not the full current schema."
                    )

            # The exact files this run parsed, byte for byte, beside the raw
            # schema they produced -- evidence for every snapshot, and what lets
            # a rebuild work from storage alone.
            source_archive = paths.raw_source_path(department_id, dataset_slug, table_slug, ts, source_name)
            source_hash = inputs.archive(storage, source_archive, source_bytes)
            metadata_archive = None
            if metadata_bytes is not None:
                metadata_archive = paths.raw_source_path(
                    department_id, dataset_slug, table_slug, ts, f"metadata__{metadata_name}"
                )
                inputs.archive(storage, metadata_archive, metadata_bytes)
            logger.info(f"Archived source -> {source_archive} (sha256 {source_hash[:12]}...)")

            raw_path = paths.raw_schema_path(department_id, dataset_slug, table_slug, ts)
            storage.write_csv(raw_path, raw_columns)
            logger.info(f"Stored raw schema -> {raw_path}")

            curated_path = paths.curated_schema_path(department_id, dataset_slug, table_slug, ts)
            storage.write_csv(curated_path, curated_columns)
            logger.info(
                f"Stored curated schema -> {curated_path} "
                f"({len(curated_columns)} column(s))"
            )

            diff_file = paths.diff_path(department_id, dataset_slug, table_slug, ts)
            storage.write_csv(diff_file, diff_rows)

            # Snapshot exists now: from here on the run's log row must offer
            # it for (re)publishing even if the next line blows up.
            publish_status = "unpublished"

        lookups.upsert_dataset(
            storage, dataset_id, department_id, dataset,
            category=category, api_available=api_available, owner=owner,
            frequency=frequency, timeline=timeline, dataset_description=dataset_description,
        )
        lookups.upsert_table(storage, table_id, dataset_id, table_name, schema_name)

        result = {
            "run_id": run_id,
            "raw_path": raw_path,
            "curated_path": curated_path,
            "diff_path": diff_file,
            "source_path": source_archive,
            "source_hash_path": f"{source_archive}.sha256",
            "source_hash": source_hash,
            "source_archive_path": source_archive,
            "source_sha256": source_hash,
            "metadata_archive_path": metadata_archive,
            "mode": mode,
            "added": added,
            "removed": removed,
            "changed": changed,
            "columns": curated_columns,
            "column_count": len(curated_columns),
            "unmatched_metadata_names": unmatched_metadata_names,
        }

        if openmetadata_client is not None:
            try:
                result["openmetadata"] = publish_table(
                    openmetadata_client,
                    storage,
                    table_id,
                )
            except Exception as exc:  # noqa: BLE001 -- recorded, then re-raised
                publish_status = "failed"
                error = f"{type(exc).__name__}: {exc}"
                logger.error(f"Publish failed for {table_id} ({run_id}): {exc} -- republish with "
                             f"`python3 -m src.schema_registry.republish`")
                raise
            publish_status = "published"

        return result
    except BaseException as exc:
        if not error:
            error = f"{type(exc).__name__}: {exc}"
        if not table_id:
            # slugify() itself failed -- still log the run against something
            # the operator will recognize.
            table_id = f"{department}.{dataset}.{table_name}"
        raise
    finally:
        try:
            lookups.append_run(
                storage,
                {
                    "run_id": run_id,
                    "table_id": table_id,
                    "ts": ts,
                    "mode": mode,
                    "source_hash": source_hash,
                    "operator": operator,
                    "added": added,
                    "removed": removed,
                    "changed": changed,
                    "publish_status": publish_status,
                    "error": error,
                },
            )
        except Exception:  # noqa: BLE001 -- never mask the run's own error
            logger.exception(f"Could not write the run-log row for {run_id} ({table_id})")


def _main(argv: list[str]) -> int:
    """Command line entry point (settings come from .env / the shell)."""

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
    )
    return 0


if __name__ == "__main__":
    import sys

    from src.utils.cli import run_cli

    sys.exit(run_cli("pipeline", _main, sys.argv[1:]))
