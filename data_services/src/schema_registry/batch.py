import csv
import os

from src.schema_registry import lookups
from src.schema_registry.pipeline import run
from src.storage.base import ObjectStorage
from src.storage.local import LocalObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)


def run_batch(manifest_file: str, storage: ObjectStorage) -> list[dict]:
    """Run the schema-registry pipeline once per row of a manifest CSV, so
    onboarding many departments/datasets/tables is one command instead of
    one Python call per submission.

    Manifest columns: department, dataset, table_name, source_file,
    source_format ("postgres_ddl" or "csv"), schema_name (optional,
    default "public"), business_metadata_file (optional), department_name
    (optional -- a manifest is something you deliberately write, so a row
    naming a not-yet-registered department here explicitly registers it,
    unlike pipeline.run() which refuses to auto-create departments from
    arbitrary text).

    One row failing doesn't stop the rest -- each result records its own
    status so a bad submission can be fixed and rerun without redoing
    everything else.
    """

    with open(manifest_file, newline="") as f:
        rows = list(csv.DictReader(f))

    results = []
    for row in rows:
        table_id = f"{row['department']}.{row['dataset']}.{row['table_name']}"
        try:
            if row.get("department_name"):
                lookups.register_department(storage, lookups.slugify(row["department"]), row["department_name"])

            result = run(
                department=row["department"],
                dataset=row["dataset"],
                table_name=row["table_name"],
                source_file=row["source_file"],
                storage=storage,
                source_format=row.get("source_format") or "postgres_ddl",
                schema_name=row.get("schema_name") or "public",
                business_metadata_file=row.get("business_metadata_file") or None,
            )
            results.append({"table_id": table_id, "status": "ok", **result})
        except Exception as exc:
            logger.error(f"Failed for {table_id}: {exc}")
            results.append({"table_id": table_id, "status": "failed", "error": str(exc)})

    ok = sum(1 for r in results if r["status"] == "ok")
    logger.info(f"Batch complete: {ok}/{len(results)} succeeded")
    return results


if __name__ == "__main__":
    run_batch(
        manifest_file=os.environ["MANIFEST_FILE"],
        storage=LocalObjectStorage(os.environ.get("STORAGE_ROOT", "storage")),
    )
