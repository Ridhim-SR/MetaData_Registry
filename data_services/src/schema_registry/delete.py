"""Soft-delete or permanently purge a department, dataset, or table.

Examples (run from ``data_services``):

    python3 -m src.schema_registry.delete --table pwd.vishwakarma.works
    python3 -m src.schema_registry.delete --list
    python3 -m src.schema_registry.delete --table pwd.vishwakarma.works --restore
    python3 -m src.schema_registry.delete --table pwd.vishwakarma.works --purge
    python3 -m src.schema_registry.delete --dataset pwd.vishwakarma
    python3 -m src.schema_registry.delete --department pwd

Normal deletion is reversible: it hides the OpenMetadata entities and marks
the registry rows while retaining storage and history. ``--purge`` is the
explicit permanent operation that removes OpenMetadata, storage, and registry
rows. Use ``--list`` to review soft-deleted targets and ``--restore`` to bring
one back.
"""

import argparse
import os
import socket
from datetime import datetime, timezone
from dataclasses import dataclass

from metadata.generated.schema.entity.data.database import Database
from metadata.generated.schema.entity.data.table import Table
from metadata.generated.schema.entity.services.databaseService import DatabaseService

from src.schema_registry.openmetadata.publish import _get_or_none, _unwrap
from src.schema_registry.registry import lookups
from src.storage import storage_from_env
from src.storage.base import ObjectStorage
from src.utils.cli import confirm_changes, run_cli
from src.utils.config import load_env

DELETION_LOG = "_lookups/deletions.csv"
DELETION_FIELDS = (
    "deletion_id", "target", "operator", "environment", "branch",
    "started_at", "finished_at", "status", "tables", "openmetadata",
    "storage_objects", "error",
)


@dataclass(frozen=True)
class Target:
    kind: str
    value: str


def _get_deleted_or_none(client, entity, fqn: str):
    """Find active or soft-deleted entities so purge can hard-delete both."""

    try:
        return client.get_by_name(entity=entity, fqn=fqn, include="deleted")
    except Exception as exc:
        if "not found" in str(exc).lower() or "404" in str(exc):
            return None
        raise


def _validate_target(value: str, parts: int, kind: str) -> str:
    pieces = value.split(".")
    if len(pieces) != parts or any(not piece for piece in pieces):
        raise ValueError(f"--{kind} must be a dot-separated id with {parts} parts, e.g. "
                         f"{'pwd.vishwakarma.works' if parts == 3 else 'pwd.vishwakarma' if parts == 2 else 'pwd'}")
    return value


def _matching_rows(storage: ObjectStorage, target: Target) -> list[dict]:
    rows = storage.read_csv(lookups.TABLES_PATH) if storage.exists(lookups.TABLES_PATH) else []
    if target.kind == "table":
        return [row for row in rows if row["table_id"] == target.value]
    if target.kind == "dataset":
        return [row for row in rows if row["dataset_id"] == target.value]
    return [row for row in rows if row["dataset_id"].startswith(f"{target.value}.")]


def _validate_scope(rows: list[dict], target: Target) -> None:
    if not rows:
        raise ValueError(
            f"No registered tables matched {target.kind} '{target.value}' -- "
            "refusing to delete an empty or unknown scope"
        )


def _storage_prefixes(target: Target) -> list[str]:
    if target.kind == "table":
        department, dataset, table = target.value.split(".")
        return [
            f"department/{department}/{dataset}/{table}/",
        ]
    department, dataset = (target.value.split(".") if target.kind == "dataset" else (target.value, ""))
    suffix = f"{department}/{dataset}/" if dataset else f"{department}/"
    return [f"department/{suffix}", f"inputs/{suffix}"]


def _remove_lookup_rows(storage: ObjectStorage, target: Target) -> dict[str, int]:
    removed = {}
    table_rows = storage.read_csv(lookups.TABLES_PATH) if storage.exists(lookups.TABLES_PATH) else []
    selected_ids = {row["table_id"] for row in _matching_rows(storage, target)}
    for path, key, predicate in [
        (lookups.TABLES_PATH, "table_id", lambda row: row["table_id"] in selected_ids),
        (lookups.RUNS_PATH, "table_id", lambda row: row.get("table_id") in selected_ids),
    ]:
        if not storage.exists(path):
            continue
        rows = storage.read_csv(path)
        kept = [row for row in rows if not predicate(row)]
        if len(kept) != len(rows):
            storage.write_csv(path, kept)
        removed[path] = len(rows) - len(kept)

    if target.kind == "table":
        return removed
    dataset_ids = {row["dataset_id"] for row in table_rows if row["table_id"] in selected_ids}
    if target.kind == "dataset":
        dataset_ids.add(target.value)
    for path, key in [(lookups.DATASETS_PATH, "dataset_id"), (lookups.DEPARTMENTS_PATH, "department_id")]:
        if not storage.exists(path):
            continue
        rows = storage.read_csv(path)
        if target.kind == "dataset":
            predicate = lambda row: row.get(key) in dataset_ids if key == "dataset_id" else False
        else:
            predicate = lambda row: row.get("department_id") == target.value if key == "department_id" else row.get("dataset_id", "").startswith(f"{target.value}.")
        kept = [row for row in rows if not predicate(row)]
        if len(kept) != len(rows):
            storage.write_csv(path, kept)
        removed[path] = len(rows) - len(kept)
    return removed


def _delete_openmetadata(client, storage: ObjectStorage, target: Target) -> int:
    return _delete_openmetadata_with_mode(client, storage, target, hard_delete=True)


def _delete_openmetadata_with_mode(client, storage: ObjectStorage, target: Target, hard_delete: bool) -> int:
    deleted = 0
    for row in _matching_rows(storage, target):
        fqn = f"{row['dataset_id'].replace('.', '.', 1)}.{row['schema_name']}.{row['table_name']}"
        entity = _get_deleted_or_none(client, Table, fqn) if hard_delete else _get_or_none(client, Table, fqn)
        if entity is not None:
            client.delete(
                entity=Table, entity_id=str(_unwrap(entity.id)), recursive=hard_delete,
                **({"hard_delete": True} if hard_delete else {}),
            )
            deleted += 1

    if target.kind == "table":
        return deleted
    department, dataset = (target.value.split(".") if target.kind == "dataset" else (target.value, ""))
    if dataset:
        fqn = f"{department}.{dataset}"
        entity = _get_deleted_or_none(client, Database, fqn) if hard_delete else _get_or_none(client, Database, fqn)
        if entity is not None:
            client.delete(
                entity=Database, entity_id=str(_unwrap(entity.id)), recursive=hard_delete,
                **({"hard_delete": True} if hard_delete else {}),
            )
            deleted += 1
    else:
        service = _get_deleted_or_none(client, DatabaseService, department) if hard_delete else _get_or_none(client, DatabaseService, department)
        if service is not None:
            client.delete(
                entity=DatabaseService, entity_id=str(_unwrap(service.id)), recursive=hard_delete,
                **({"hard_delete": True} if hard_delete else {}),
            )
            deleted += 1
    return deleted


def soft_delete(storage: ObjectStorage, target: Target, client=None, dry_run: bool = False) -> dict:
    """Hide entities and mark registry rows without deleting storage."""

    rows = _matching_rows(storage, target)
    _validate_scope(rows, target)
    if not dry_run and client is None:
        raise ValueError("OpenMetadata admin client is required for a soft delete")
    if not dry_run and client is not None:
        om_deleted = _delete_openmetadata_with_mode(client, storage, target, hard_delete=False)
        for row in rows:
            lookups.soft_delete_table(storage, row["table_id"])
    else:
        om_deleted = 0
    return {
        "target": f"{target.kind} {target.value}",
        "status": "would_soft_delete" if dry_run else "soft_deleted",
        "tables": len(rows),
        "openmetadata": om_deleted,
        "storage_objects_retained": sum(len(storage.list(p)) for p in _storage_prefixes(target)),
    }


def _soft_deleted_targets(storage: ObjectStorage) -> list[str]:
    rows = storage.read_csv(lookups.TABLES_PATH) if storage.exists(lookups.TABLES_PATH) else []
    return sorted(row["table_id"] for row in rows if row.get("deleted"))


def restore(storage: ObjectStorage, target: Target, client=None, dry_run: bool = False) -> dict:
    rows = _matching_rows(storage, target)
    rows = [row for row in rows if row.get("deleted")]
    if not rows:
        raise ValueError(f"No soft-deleted tables matched {target.kind} '{target.value}'")
    if not dry_run:
        for row in rows:
            lookups.restore_table(storage, row["table_id"])
        if client is not None:
            from src.schema_registry.openmetadata.publish import publish_table
            for row in rows:
                publish_table(client, storage, row["table_id"])
    return {
        "target": f"{target.kind} {target.value}",
        "status": "would_restore" if dry_run else "restored",
        "tables": len(rows),
    }


def _require_soft_deleted(storage: ObjectStorage, target: Target) -> None:
    rows = _matching_rows(storage, target)
    _validate_scope(rows, target)
    if any(not row.get("deleted") for row in rows):
        raise ValueError(
            f"{target.kind} '{target.value}' is not fully soft-deleted -- "
            "run the default delete first and review --list before using --purge"
        )


def purge(storage: ObjectStorage, target: Target, client=None, dry_run: bool = False) -> dict:
    rows = _matching_rows(storage, target)
    _validate_scope(rows, target)
    prefixes = _storage_prefixes(target)
    # Listing is deliberately done before any OpenMetadata mutation. This
    # catches missing storage access and gives the operator the exact scope
    # before the first destructive call.
    planned_objects = sum(len(storage.list(prefix)) for prefix in prefixes)
    if not dry_run and client is not None:
        om_deleted = _delete_openmetadata(client, storage, target)
    else:
        om_deleted = 0
    objects = planned_objects
    if not dry_run:
        objects = sum(storage.delete_prefix(prefix) for prefix in prefixes)
        lookup_rows = _remove_lookup_rows(storage, target)
    else:
        lookup_rows = {}
    return {"target": f"{target.kind} {target.value}", "tables": len(rows),
            "openmetadata": om_deleted, "storage_objects": objects, "lookup_rows": lookup_rows}


def _audit(storage: ObjectStorage, row: dict) -> None:
    with storage.lock(DELETION_LOG):
        rows = storage.read_csv(DELETION_LOG) if storage.exists(DELETION_LOG) else []
        rows.append({field: str(row.get(field, "")) for field in DELETION_FIELDS})
        storage.write_csv(DELETION_LOG, rows)


def _update_audit(storage: ObjectStorage, deletion_id: str, **fields: object) -> None:
    with storage.lock(DELETION_LOG):
        rows = storage.read_csv(DELETION_LOG) if storage.exists(DELETION_LOG) else []
        row = next((item for item in rows if item.get("deletion_id") == deletion_id), None)
        if row is None:
            raise ValueError(f"Deletion audit row '{deletion_id}' was not found")
        row.update({key: str(value) for key, value in fields.items()})
        storage.write_csv(DELETION_LOG, rows)


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--department")
    group.add_argument("--dataset")
    group.add_argument("--table")
    group.add_argument("--list", action="store_true", dest="list_deleted")
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--purge", action="store_true", help="permanently remove a previously soft-deleted scope")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.list_deleted:
        load_env()
        storage = storage_from_env()
        print("\n".join(_soft_deleted_targets(storage)) or "No soft-deleted tables.")
        return 0
    if not any((args.department, args.dataset, args.table)):
        parser.error("one of --department, --dataset, or --table is required")
    if args.restore and args.purge:
        parser.error("--restore and --purge cannot be combined")
    if args.department:
        target = Target("department", _validate_target(args.department, 1, "department"))
    elif args.dataset:
        target = Target("dataset", _validate_target(args.dataset, 2, "dataset"))
    else:
        target = Target("table", _validate_target(args.table, 3, "table"))

    load_env()
    storage = storage_from_env() if args.dry_run or args.restore or not args.purge else storage_from_env(delete_credentials=True)
    if args.dry_run:
        if args.purge:
            _require_soft_deleted(storage, target)
        action = restore if args.restore else purge if args.purge else soft_delete
        print(action(storage, target, dry_run=True))
        return 0
    token = os.environ.get("OPENMETADATA_ADMIN_JWT_TOKEN")
    if not token:
        raise ValueError(
            "OPENMETADATA_ADMIN_JWT_TOKEN is required -- refusing lifecycle change. "
            "A normal ingestion token is not accepted."
        )
    action_name = "PERMANENTLY purge" if args.purge else "restore" if args.restore else "soft-delete"
    if args.purge:
        _require_soft_deleted(storage, target)
    confirm_changes(f"{action_name} {target.kind} '{target.value}'")
    from src.schema_registry.openmetadata.publish import get_client
    client = get_client(os.environ.get("OPENMETADATA_HOST_PORT", "http://localhost:8585/api"), token)
    started = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    deletion_id = f"{started}-{socket.gethostname()}"
    from src.utils.config import _current_branch
    operator = os.environ.get("OPERATOR") or os.environ.get("USERNAME") or ""
    _audit(storage, {
        "deletion_id": deletion_id,
        "target": f"{target.kind} {target.value}",
        "operator": operator,
        "environment": os.environ.get("ENVIRONMENT", ""),
        "branch": _current_branch() or "",
        "started_at": started,
        "status": "started",
    })
    try:
        if args.restore:
            result = restore(storage, target, client=client)
        elif args.purge:
            result = purge(storage, target, client=client)
        else:
            result = soft_delete(storage, target, client=client)
    except Exception as exc:
        _update_audit(
            storage, deletion_id, finished_at=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),
            status="failed", error=f"{type(exc).__name__}: {exc}",
        )
        raise
    _update_audit(
        storage, deletion_id, finished_at=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),
        status=result["status"], tables=result["tables"],
        openmetadata=result.get("openmetadata", 0),
        storage_objects=result.get("storage_objects", 0),
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli("delete", _main, __import__("sys").argv[1:]))
