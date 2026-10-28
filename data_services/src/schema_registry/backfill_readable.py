"""Backfill `readable_type` (and normalise `unit`) into curated snapshots
that were written before those columns existed.

New runs get both automatically: `curate_schema()` derives `readable_type`
from `data_type` and validates/normalises `unit`. Tables ingested earlier
only have `data_type` in their latest curated snapshot, and `sync` skips them
because their source file has not changed.

The safe way to fill them in is to rewrite each table's latest curated
snapshot in place, adding the two derived columns and changing nothing else.
That is exactly what this command does -- it does not re-read the original
submission, it does not re-run the auto-classifier, and it does not
re-derive `classification`/`tag` the way `sync --reclassify` does, so
reviewed governance answers (including deliberately blank ones) are left
alone.

    python -m src.schema_registry.backfill_readable --dry-run
    python -m src.schema_registry.backfill_readable --department pwd
    python -m src.schema_registry.backfill_readable --department pwd --publish

A table whose latest snapshot already has `readable_type` is reported as
`unchanged` and no new snapshot is written, so the command is idempotent.
`unit` can only be backfilled where a previous snapshot or metadata answer
already carries one -- nothing guesses a unit from a column name. Run without
`--publish` to fill storage only; the new snapshot then shows up as
`unpublished` and `republish` (or this command with `--publish`) can push it.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from dataclasses import dataclass

from src.schema_registry.curate import readable_data_type, validate_unit
from src.schema_registry.pipeline import _timestamp
from src.schema_registry.registry import lookups, paths
from src.storage.base import ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)

_BACKFILL_OPERATOR = "backfill_readable"


@dataclass
class Outcome:
    table_id: str
    status: str  # backfilled | unchanged | would backfill | failed
    publish: str = "-"  # "-" | published | failed
    detail: str = ""


def _split_table_id(table_id: str) -> tuple[str, str, str]:
    parts = table_id.split(".")
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"table_id {table_id!r} must look like department.dataset.table")
    return parts[0], parts[1], parts[2]


def _needs_backfill(previous: list[dict], curated: list[dict]) -> bool:
    """True unless every row already agrees on the two fields this command
    owns. Comparing only those keeps a second run a no-op even though the
    CSV round-trip turns booleans/ints into strings."""

    if len(previous) != len(curated):
        return True
    for old, new in zip(previous, curated):
        if (old.get("name") or "") != (new.get("name") or ""):
            return True
        if (old.get("readable_type") or "") != new["readable_type"]:
            return True
        if (old.get("unit") or "") != (new.get("unit") or ""):
            return True
    return False


def _backfill_table(
    storage: ObjectStorage,
    table_id: str,
    *,
    dry_run: bool,
    client=None,
) -> Outcome:
    department_id, dataset_slug, table_slug = _split_table_id(table_id)
    lock_path = paths.pipeline_lock_path(department_id, dataset_slug, table_slug)

    # Same lock a pipeline run takes, so a backfill can never interleave with
    # an in-flight ingest and leave the "latest" snapshot half-replaced.
    with storage.lock(lock_path):
        raw_path = lookups.latest_raw_snapshot_path(storage, department_id, dataset_slug, table_slug)
        curated_path = lookups.latest_curated_snapshot_path(storage, department_id, dataset_slug, table_slug)
        raw_columns = storage.read_csv(raw_path)
        previous = storage.read_csv(curated_path)

        # The raw snapshot is only a consistency check: deriving from the
        # curated row's own data_type is what guarantees the only change is
        # the two new columns. If the two snapshots disagree on the column
        # list, one of them is stale and re-running curate would guess.
        raw_names = {row.get("name") for row in raw_columns}
        curated_names = {row.get("name") for row in previous}
        if raw_names != curated_names:
            raise ValueError(
                f"{table_id}: raw and curated snapshots disagree on columns "
                f"(raw-only={sorted(raw_names - curated_names)}, "
                f"curated-only={sorted(curated_names - raw_names)}) -- run the pipeline first."
            )

        # Copy every reviewed answer verbatim; overwrite only the two
        # derived columns. Re-running curate_schema() here would also
        # re-apply the auto-classifier, silently turning a deliberately
        # blank classification into Internal/Financial.
        curated = []
        for row in previous:
            updated = dict(row)
            updated["readable_type"] = readable_data_type(updated["data_type"])
            updated["unit"] = validate_unit(updated.get("unit", ""), updated["data_type"])
            curated.append(updated)

        if not _needs_backfill(previous, curated):
            return Outcome(table_id, "unchanged", detail="latest curated snapshot already has readable_type")

        ts = _timestamp()
        # The snapshot is new, so its rows should say when it was produced
        # rather than repeating the ingestion timestamp of the raw snapshot.
        curated = [{**row, "ingestion_timestamp": ts} for row in curated]
        readable = sum(1 for row in curated if row.get("readable_type"))
        units = sorted({row["unit"] for row in curated if row.get("unit")})
        detail = f"{len(curated)} column(s), {readable} readable_type, unit={units or '[]'}"

        if dry_run:
            return Outcome(table_id, "would backfill", detail=detail)

        new_path = paths.curated_schema_path(department_id, dataset_slug, table_slug, ts)
        storage.write_csv(new_path, curated)

        run_id = uuid.uuid4().hex
        lookups.append_run(
            storage,
            {
                "run_id": run_id,
                "table_id": table_id,
                "ts": ts,
                "mode": "backfill",
                "operator": _BACKFILL_OPERATOR,
                "publish_status": "unpublished",
            },
        )
        logger.info(f"Backfilled readable_type for {table_id} -> {new_path}")

        if client is None:
            return Outcome(table_id, "backfilled", detail=detail)

        from src.schema_registry.openmetadata.publish import publish_table

        try:
            publish_table(client, storage, table_id)
        except Exception as exc:  # noqa: BLE001 -- one bad table must not stop the rest
            lookups.update_run(storage, run_id, publish_status="failed", error=f"{type(exc).__name__}: {exc}")
            logger.error(f"Publish failed for {table_id}: {exc}")
            return Outcome(table_id, "backfilled", publish="failed", detail=f"{detail}; publish: {exc}")

        lookups.update_run(storage, run_id, publish_status="published")
        return Outcome(table_id, "backfilled", publish="published", detail=detail)


def backfill(
    storage: ObjectStorage,
    *,
    department: str | None = None,
    dry_run: bool = False,
    client=None,
) -> list[Outcome]:
    """Backfill every registered table (or one department's tables).

    One failing table never stops the others -- its error is recorded in the
    returned Outcome, exactly like `sync`."""

    if not storage.exists(lookups.TABLES_PATH):
        raise ValueError(f"{lookups.TABLES_PATH} not found -- nothing registered in this storage")

    rows = storage.read_csv(lookups.TABLES_PATH)
    if department:
        rows = [row for row in rows if row["table_id"].split(".")[0] == department]

    outcomes: list[Outcome] = []
    for row in rows:
        table_id = row.get("table_id", "")
        if row.get("deleted"):
            outcomes.append(Outcome(table_id, "skipped", detail="soft-deleted in the registry"))
            continue
        try:
            outcomes.append(_backfill_table(storage, table_id, dry_run=dry_run, client=client))
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Backfill failed for {table_id}: {exc}")
            outcomes.append(Outcome(table_id, "failed", detail=str(exc)))
    return outcomes


def print_summary(outcomes: list[Outcome]) -> None:
    width = max([len(o.table_id) for o in outcomes] + [5])
    print(f"\n{'TABLE':<{width}}  {'BACKFILL':<15} {'PUBLISH':<10} DETAIL")
    for outcome in outcomes:
        print(f"{outcome.table_id:<{width}}  {outcome.status:<15} {outcome.publish:<10} {outcome.detail}")
    failed = sum(o.status == "failed" or o.publish == "failed" for o in outcomes)
    print(f"\n{len(outcomes)} table(s), {failed} failed")


def _main(argv: list[str]) -> int:
    from src.schema_registry.openmetadata.publish import get_client
    from src.storage import storage_from_env
    from src.utils.config import load_env

    parser = argparse.ArgumentParser(
        prog="python -m src.schema_registry.backfill_readable",
        description="Backfill readable_type/unit into existing curated snapshots.",
    )
    parser.add_argument("--department", default="", help="only this department id (e.g. pwd)")
    parser.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    parser.add_argument("--publish", action="store_true", help="also republish each backfilled table")
    args = parser.parse_args(argv)

    load_env()
    storage = storage_from_env()

    client = None
    if args.publish:
        host = os.environ.get("OPENMETADATA_HOST_PORT")
        token = os.environ.get("OPENMETADATA_JWT_TOKEN")
        if not token:
            parser.error("--publish needs OPENMETADATA_JWT_TOKEN for this ENVIRONMENT (see .env)")
        client = get_client(host_port=host, jwt_token=token)

    outcomes = backfill(
        storage, department=args.department or None, dry_run=args.dry_run, client=client
    )
    print_summary(outcomes)
    return 1 if any(o.status == "failed" or o.publish == "failed" for o in outcomes) else 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
