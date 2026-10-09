"""Make storage and OpenMetadata match catalog.yaml -- one command that can
fill an empty server, and changes nothing when run again.

    python3 -m src.schema_registry.sync                 # do it
    python3 -m src.schema_registry.sync --dry-run       # only show what would happen
    python3 -m src.schema_registry.sync --publish-only  # quick restore: republish every
                                                        # table already in storage
    python3 -m src.schema_registry.sync --department pwd   # only one department

Steps, in order:
  1. OpenMetadata setup (custom properties) -- safe to repeat
  2. register every department in the catalog
  3. ingest each table whose file changed since its last run (same
     pipeline.run() as a single-table run); unchanged files are skipped
     by comparing SHA-256 with the archived copy
  4. set each dataset's fields (category, owner, ...) exactly as written
  5. publish every catalog table to OpenMetadata -- always, even unchanged
     ones, so a wiped server is refilled

One table failing never stops the others; the command exits non-zero if
anything failed, and prints a summary table either way.
"""

import argparse
import os
import sys
from dataclasses import dataclass

from metadata.ingestion.ometa.ometa_api import OpenMetadata

from src.schema_registry import inputs
from src.schema_registry.catalog import DatasetEntry, DepartmentEntry, load_catalog
from src.schema_registry.parsers.field_dictionary_ingest import run_field_dictionary
from src.schema_registry.pipeline import run
from src.schema_registry.registry import lookups, paths
from src.storage.base import ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Outcome:
    table_id: str
    ingest: str = "-"   # ingested | unchanged | would ingest | failed
    publish: str = "-"  # published | skipped | failed
    detail: str = ""


def _latest_archived_sha(storage: ObjectStorage, prefix: str, metadata: bool) -> str | None:
    files = sorted(
        p for p in storage.list(prefix)
        if p.endswith(".sha256") and ("__metadata__" in p) == metadata
    )
    return storage.read_bytes(files[-1]).decode().split()[0] if files else None


def _table_needs_ingest(storage: ObjectStorage, dept_id: str, ds_slug: str, table, table_id: str) -> str | None:
    """Why this table must be (re-)ingested, or None if nothing changed."""

    table_slug = lookups.slugify(table.name)
    source_bytes, _ = inputs.read_input(storage, table.source)  # first, so a dry run also catches a missing file
    registered = lookups.get_table(storage, table_id)
    if registered is None:
        return "new table"
    if (registered["table_name"], registered["schema_name"]) != (table.name, table.schema):
        return "table name or schema changed"
    prefix = paths.raw_source_prefix(dept_id, ds_slug, table_slug)
    if inputs.sha256(source_bytes) != _latest_archived_sha(storage, prefix, metadata=False):
        return "source file changed"
    if table.metadata:
        metadata_bytes, _ = inputs.read_input(storage, table.metadata)
        if inputs.sha256(metadata_bytes) != _latest_archived_sha(storage, prefix, metadata=True):
            return "metadata file changed"
    return None


def _ensure_department(storage: ObjectStorage, dept: DepartmentEntry, dry_run: bool) -> None:
    existing = next(
        (r for r in (storage.read_csv(lookups.DEPARTMENTS_PATH) if storage.exists(lookups.DEPARTMENTS_PATH) else [])
         if r["department_id"] == dept.id),
        None,
    )
    if existing and existing["department_name"] == dept.name:
        return
    if dry_run:
        logger.info(f"[dry run] would register department {dept.id} ({dept.name})")
        return
    lookups.register_department(storage, dept.id, dept.name)


def _ingest_dataset(storage: ObjectStorage, dept: DepartmentEntry, ds: DatasetEntry, dry_run: bool) -> list[Outcome]:
    ds_slug = lookups.slugify(ds.name)
    outcomes: list[Outcome] = []

    if ds.field_dictionary:
        label = f"{dept.id}.{ds_slug}.* (field dictionary)"
        try:
            data, _ = inputs.read_input(storage, ds.field_dictionary)
            previous = _latest_archived_sha(storage, paths.dataset_source_prefix(dept.id, ds_slug), metadata=False)
            if inputs.sha256(data) == previous:
                outcomes.append(Outcome(label, "unchanged"))
            elif dry_run:
                outcomes.append(Outcome(label, "would ingest", detail="field dictionary changed or new"))
            else:
                results = run_field_dictionary(department=dept.id, dataset=ds.name, source_file=ds.field_dictionary, storage=storage)
                outcomes.append(Outcome(label, "ingested", detail=f"{len(results)} table(s)"))
        except Exception as exc:  # noqa: BLE001 -- report and carry on with other tables
            outcomes.append(Outcome(label, "failed", detail=str(exc)))

    for table in ds.tables:
        table_id = f"{dept.id}.{ds_slug}.{lookups.slugify(table.name)}"
        try:
            reason = _table_needs_ingest(storage, dept.id, ds_slug, table, table_id)
            if reason is None:
                outcomes.append(Outcome(table_id, "unchanged"))
                continue
            if dry_run:
                outcomes.append(Outcome(table_id, "would ingest", detail=reason))
                continue
            result = run(
                department=dept.id, dataset=ds.name, table_name=table.name, source_file=table.source,
                storage=storage, source_format=table.format, schema_name=table.schema,
                business_metadata_file=table.metadata, allow_column_removal=table.allow_column_removal,
            )
            outcomes.append(Outcome(table_id, "ingested", detail=f"{reason}; {result['column_count']} columns"))
        except Exception as exc:  # noqa: BLE001
            outcomes.append(Outcome(table_id, "failed", detail=str(exc)))

    if not dry_run:
        lookups.set_dataset_fields(storage, f"{dept.id}.{ds_slug}", dept.id, ds.name, ds.fields)
    return outcomes


def _tables_to_publish(
    storage: ObjectStorage, departments: list[DepartmentEntry], publish_only: bool, only_department: str | None = None
) -> list[tuple[str, bool]]:
    """(table_id, allow_category_below_columns) for every table to publish."""

    registered = storage.read_csv(lookups.TABLES_PATH) if storage.exists(lookups.TABLES_PATH) else []
    if only_department:
        registered = [r for r in registered if r["dataset_id"].split(".")[0] == only_department]
    flags = {f"{d.id}.{lookups.slugify(ds.name)}": ds.allow_category_below_columns for d in departments for ds in d.datasets}
    if publish_only:  # restore: everything storage knows about
        return [(r["table_id"], flags.get(r["dataset_id"], False)) for r in registered]

    wanted: list[tuple[str, bool]] = []
    for dept in departments:
        for ds in dept.datasets:
            ds_id = f"{dept.id}.{lookups.slugify(ds.name)}"
            if ds.field_dictionary:  # its tables are whatever the file contained
                wanted += [(r["table_id"], ds.allow_category_below_columns) for r in registered if r["dataset_id"] == ds_id]
            wanted += [(f"{ds_id}.{lookups.slugify(t.name)}", ds.allow_category_below_columns) for t in ds.tables]
    return list(dict.fromkeys(wanted))


def sync(
    storage: ObjectStorage,
    departments: list[DepartmentEntry],
    client: OpenMetadata | None = None,
    setup=None,
    dry_run: bool = False,
    publish_only: bool = False,
    only_department: str | None = None,
) -> list[Outcome]:
    """Run the steps in the module docstring. `setup` is the OpenMetadata
    setup callable (custom properties); `client` None = storage only.
    `only_department` limits every step to that one department."""

    if only_department:
        if not publish_only and not any(d.id == only_department for d in departments):
            raise ValueError(f"Department '{only_department}' isn't in catalog.yaml")
        departments = [d for d in departments if d.id == only_department]

    from src.schema_registry.openmetadata.publish import publish_table

    if client is not None and setup is not None and not dry_run:
        setup()

    outcomes: dict[str, Outcome] = {}
    if not publish_only:
        for dept in departments:
            _ensure_department(storage, dept, dry_run)
            for ds in dept.datasets:
                for outcome in _ingest_dataset(storage, dept, ds, dry_run):
                    outcomes[outcome.table_id] = outcome

    targets = _tables_to_publish(storage, departments, publish_only, only_department)
    for table_id, allow_category in targets:
        outcome = outcomes.setdefault(table_id, Outcome(table_id))
        if outcome.ingest == "failed":
            outcome.publish = "skipped"
        elif client is None or dry_run:
            outcome.publish = "skipped" if client is None else "would publish"
        else:
            try:
                publish_table(client, storage, table_id, allow_category_below_columns=allow_category)
                outcome.publish = "published"
            except Exception as exc:  # noqa: BLE001
                outcome.publish = "failed"
                outcome.detail = f"{outcome.detail}; publish: {exc}".lstrip("; ")

    if not publish_only and not only_department:
        listed = {t for t, _ in targets}
        extra = sorted(r["table_id"] for r in (storage.read_csv(lookups.TABLES_PATH) if storage.exists(lookups.TABLES_PATH) else [])
                       if r["table_id"] not in listed)
        if extra:
            logger.warning(f"In storage but not in catalog.yaml (not published by sync): {', '.join(extra)}")
    return list(outcomes.values())


def print_summary(outcomes: list[Outcome]) -> None:
    width = max([len(o.table_id) for o in outcomes] + [5])
    print(f"\n{'TABLE':<{width}}  {'INGEST':<13} {'PUBLISH':<14} DETAIL")
    for o in outcomes:
        print(f"{o.table_id:<{width}}  {o.ingest:<13} {o.publish:<14} {o.detail}")
    failed = sum("failed" in (o.ingest, o.publish) for o in outcomes)
    print(f"\n{len(outcomes)} table(s), {failed} failed")


def _main(argv: list[str]) -> int:
    from src.schema_registry.openmetadata.publish import get_client
    from src.schema_registry.openmetadata.setup_custom_properties import setup as setup_custom_properties
    from src.storage import storage_from_env
    from src.storage.backup import backup_after_run
    from src.utils.cli import confirm_changes
    from src.utils.config import load_env

    parser = argparse.ArgumentParser(prog="python3 -m src.schema_registry.sync", description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalog", default=os.path.join(os.path.dirname(__file__), "..", "..", "catalog.yaml"))
    parser.add_argument("--dry-run", action="store_true", help="show what would happen, change nothing")
    parser.add_argument("--publish-only", action="store_true", help="republish every table already in storage")
    parser.add_argument("--department", help="only this department (e.g. pwd)")
    args = parser.parse_args(argv)

    load_env()
    storage = storage_from_env()
    departments = load_catalog(args.catalog)
    if not args.dry_run:
        which = f"department '{args.department}'" if args.department else "every department"
        confirm_changes(f"sync {which} in catalog.yaml -- "
                        + ("republish what's stored" if args.publish_only else "store in Wasabi and publish"))

    client = setup = None
    host, token = os.environ.get("OPENMETADATA_HOST_PORT"), os.environ.get("OPENMETADATA_JWT_TOKEN")
    if token:
        client = get_client(host_port=host, jwt_token=token)
        setup = lambda: setup_custom_properties(host_port=host, jwt_token=token)  # noqa: E731
    else:
        logger.warning("No OpenMetadata token for this ENVIRONMENT -- storage only, nothing published.")

    outcomes = sync(
        storage, departments, client=client, setup=setup,
        dry_run=args.dry_run, publish_only=args.publish_only, only_department=args.department,
    )
    print_summary(outcomes)
    failed = any("failed" in (o.ingest, o.publish) for o in outcomes)
    backed_up = args.dry_run or backup_after_run(storage)
    return 1 if failed or not backed_up else 0


if __name__ == "__main__":
    from src.utils.cli import run_cli

    sys.exit(run_cli("sync", _main, sys.argv[1:]))
