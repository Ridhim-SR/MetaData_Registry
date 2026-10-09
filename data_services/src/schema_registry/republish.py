"""Republish snapshots that never made it to OpenMetadata.

Every pipeline run records its publish outcome in `_lookups/runs.csv`
(pipeline.run), so "the publish failed and the snapshot is only in storage"
is now a state you can act on instead of something you discover in the UI.
This command finds those runs and re-publishes them through the exact same
publish_table() path a normal run uses -- re-running it is safe (everything
is create-or-update).

    python3 -m src.schema_registry.republish          # .env supplies ENVIRONMENT, host and token
    OPENMETADATA_JWT_TOKEN=<token> python3 -m src.schema_registry.republish   # or pass one

A table whose run wrote a snapshot but published it as `unpublished` (the
storage-only workflow: run() without a client) is included too -- that is
the documented "publish later" step, just done in bulk.

Exit code is 0 only if every republish succeeded, so CI/scripts can chain on
it (same convention as batch.py).
"""

import os
import sys

from src.schema_registry.openmetadata.publish import get_client, publish_table
from src.schema_registry.registry import lookups
from src.storage import storage_from_env
from src.storage.base import ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)


def republish_unpublished(storage: ObjectStorage, client) -> list[dict]:
    """Republish every table whose last snapshot-writing run never reached
    OpenMetadata. Returns one result dict per considered table:

        {"table_id", "run_id", "status": published|failed|skipped, ...}

    A successful republish updates that run's `publish_status`/`error` in
    place, so the next call only picks up what's still broken."""

    def _mark(run: dict, **fields) -> None:
        """Record the new outcome on the run row -- a broken log row must
        never take down the republish loop itself."""

        if not run.get("run_id"):
            logger.warning(f"No run_id on the log row for {run.get('table_id')} -- outcome not recorded.")
            return
        try:
            lookups.update_run(storage, run["run_id"], **fields)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Could not update run {run['run_id']} in {lookups.RUNS_PATH}: {exc}")

    results: list[dict] = []
    for table_id, run in lookups.unpublished_runs(storage).items():
        row = {"table_id": table_id, "run_id": run.get("run_id", ""), "was": run.get("publish_status", "")}

        table_row = lookups.get_table(storage, table_id)
        if table_row is None or table_row.get("deleted"):
            results.append({**row, "status": "skipped", "reason": "unknown or soft-deleted in the registry"})
            continue

        try:
            published = publish_table(client, storage, table_id)
        except Exception as exc:  # noqa: BLE001 -- one bad table must not stop the rest
            logger.error(f"Republish failed for {table_id}: {exc}")
            _mark(run, publish_status="failed", error=f"{type(exc).__name__}: {exc}")
            results.append({**row, "status": "failed", "error": str(exc)})
            continue

        _mark(run, publish_status="published", error="")
        results.append({**row, "status": "published", "fully_qualified_name": published["fully_qualified_name"]})

    return results


if __name__ == "__main__":
    from src.utils.config import load_env

    load_env()  # reads .env: ENVIRONMENT decides the storage and the LOCAL_/DEV_ token+host
    _client = get_client(
        host_port=os.environ.get("OPENMETADATA_HOST_PORT") or "http://localhost:8585/api",
        jwt_token=os.environ["OPENMETADATA_JWT_TOKEN"],
    )
    _results = republish_unpublished(storage_from_env(), _client)
    for _row in _results:
        detail = _row.get("fully_qualified_name") or _row.get("error") or _row.get("reason", "")
        print(f"{_row['status']:>10}  {_row['table_id']}  {detail}")
    _failed = [r for r in _results if r["status"] == "failed"]
    print(f"{len(_results) - len(_failed)}/{len(_results)} republished")
    sys.exit(1 if _failed else 0)
