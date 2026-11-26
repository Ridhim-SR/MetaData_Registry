import csv
import os
import tempfile
import time
from concurrent.futures import Executor, ThreadPoolExecutor
from pathlib import Path

from metadata.ingestion.ometa.ometa_api import OpenMetadata

from src.schema_registry import inputs
from src.schema_registry.parsers.field_dictionary_parser import parse_field_dictionary_text
from src.schema_registry.parsers.irrigation_parser import parse_irrigation_field_dictionary
from src.schema_registry.pipeline import _timestamp, run
from src.schema_registry.registry import lookups, paths
from src.storage.base import ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)

# `name_hindi` is a column attribute (OpenMetadata's Column.displayName), so
# it travels in the split columns CSV rather than business metadata. It is
# optional: a parser that doesn't answer it writes the column blank, and the
# CSV parser then leaves the previous label alone.
_COLUMN_FIELDS = ["name", "data_type", "length", "nullable", "default", "name_hindi"]
# `tag` is included so a Field Dictionary that answers it (an optional `tag`
# column) actually reaches curate_schema() -- the parser used to compute it
# and then drop it here, so a department's answer silently never landed.
# `Personal Data (Y/N)` is deliberately not a source of tags (see the parser).
# Parsers can provide reviewed tags and classifications. Blank answers are
# filtered out by _business_metadata_from_rows(), so they do not erase
# existing values. `glossary_term` and `active` are not source fields.
_METADATA_FIELDS = ["name", "business_description", "tag", "unit", "classification"]

DEFAULT_TABLE_WORKERS = 4


def _worker_count(variable: str, default: int) -> int:
    """Positive integer from the environment, or `default` when unset."""

    raw = os.environ.get(variable, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{variable} must be a positive integer") from exc
    if value < 1:
        raise ValueError(f"{variable} must be a positive integer")
    return value


def run_field_dictionary(
    department: str,
    dataset: str,
    source_file: str,
    storage: ObjectStorage,
    schema_name: str = "public",
    openmetadata_client: OpenMetadata | None = None,
    allow_column_removal: bool = False,
    reclassify: bool = False,
    workers: int | None = None,
    executor: Executor | None = None,
) -> dict[str, dict]:
    """Ingest a Field Dictionary CSV by splitting it into one temporary per-table
    columns file + business-metadata file per "Dataset Name" group, then
    calling pipeline.run() once per table -- exactly as if the department
    had submitted one CSV per table. Every existing guarantee (diff-based
    safety guard, locking, retry, auto-tag/auto-classification) applies
    unchanged, since run() itself isn't touched.

    Tables inside one dictionary are independent (their own lock, snapshot
    and run-log row), so they are ingested through a bounded pool. `executor`
    lets a caller (sync) share its table pool instead of nesting another one;
    otherwise `workers` -- FIELD_DICTIONARY_TABLE_WORKERS, default 4 -- sets
    the pool size. 1 keeps the old strictly serial order.

    One bad table doesn't stop the rest: each run() call is isolated, its
    exception is captured, and the result dict records status/error for it
    (`{"status": "failed", "error": ...}` instead of run()'s own keys).
    Tables ingested before the failure already exist in storage/OpenMetadata,
    so a partial file gets as far as it can rather than throwing away the
    tables that were fine.

    Returns {table_name: run()'s own result dict (+ "status": "ok")}, one
    entry per table found in the file. `department` must already be
    registered, same precondition as run() itself.
    """

    # `source_file` may be a local path or a storage:<key> (see inputs.py).
    # The original multi-table file is archived once at dataset level; each
    # table's run() then archives the per-table split it actually parsed.
    source_bytes, source_name = inputs.read_input(storage, source_file)
    text = inputs.decode(source_bytes)
    parse_started = time.perf_counter()
    if department == "irrigation_dept":
        tables = parse_irrigation_field_dictionary(
            text,
            label=source_file,
            default_table_name=dataset,
        )
    else:
        tables = parse_field_dictionary_text(text, label=source_file)
    logger.info(
        f"Stage timing: stage=parse dataset_id={lookups.slugify(department)}."
        f"{lookups.slugify(dataset)} tables={len(tables)} "
        f"elapsed_ms={(time.perf_counter() - parse_started) * 1000:.1f}"
    )
    archive_path = paths.dataset_source_path(
        lookups.slugify(department), lookups.slugify(dataset), _timestamp(), source_name
    )
    inputs.archive(storage, archive_path, source_bytes)
    logger.info(f"Field dictionary: archived original -> {archive_path}")
    results: dict[str, dict] = {}

    def _ingest_one(table_name: str, table: dict, columns_path: Path, metadata_path: Path) -> tuple[str, dict]:
        logger.info(f"Field dictionary: ingesting table '{table_name}' ({len(table['columns'])} column(s))")
        try:
            return table_name, {
                "status": "ok",
                **run(
                    department=department,
                    dataset=dataset,
                    table_name=table_name,
                    source_file=str(columns_path),
                    storage=storage,
                    source_format="csv",
                    schema_name=schema_name,
                    business_metadata_file=str(metadata_path),
                    openmetadata_client=openmetadata_client,
                    allow_column_removal=allow_column_removal,
                    reclassify=reclassify,
                ),
            }
        except Exception as exc:  # noqa: BLE001 -- keep going, report this table as failed
            logger.error(f"Field dictionary: table '{table_name}' failed: {exc}")
            return table_name, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    with tempfile.TemporaryDirectory() as tmp_dir:
        jobs: list[tuple[str, dict, Path, Path]] = []
        for table_name, table in tables.items():
            columns_path = Path(tmp_dir) / f"{table_name}_columns.csv"
            with columns_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=_COLUMN_FIELDS)
                writer.writeheader()
                for c in table["columns"]:
                    writer.writerow(
                        {
                            "name": c["name"],
                            "data_type": c["data_type"],
                            "length": c["length"] if c["length"] is not None else "",
                            "nullable": str(c["nullable"]),
                            "default": c["default"] if c["default"] is not None else "",
                            "name_hindi": c.get("name_hindi", ""),
                        }
                    )

            metadata_path = Path(tmp_dir) / f"{table_name}_metadata.csv"
            with metadata_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=_METADATA_FIELDS)
                writer.writeheader()
                for name, meta in table["business_metadata"].items():
                    writer.writerow(
                        {
                            "name": name,
                            "business_description": meta.get("business_description", ""),
                            "tag": meta.get("tag", ""),
                            "unit": meta.get("unit", ""),
                            "classification": meta.get("classification", ""),
                        }
                    )
            jobs.append((table_name, table, columns_path, metadata_path))

        if executor is not None:
            completed = list(executor.map(lambda job: _ingest_one(*job), jobs))
        else:
            if workers is None:
                workers = _worker_count("FIELD_DICTIONARY_TABLE_WORKERS", DEFAULT_TABLE_WORKERS)
            if workers < 1:
                raise ValueError("workers must be a positive integer")
            pool_size = min(workers, len(jobs))
            if pool_size <= 1:
                completed = [_ingest_one(*job) for job in jobs]
            else:
                with ThreadPoolExecutor(max_workers=pool_size) as pool:
                    completed = list(pool.map(lambda job: _ingest_one(*job), jobs))
        results = dict(completed)

    ok = sum(1 for r in results.values() if r["status"] == "ok")
    logger.info(f"Field dictionary: {ok}/{len(results)} table(s) ingested")
    return results


if __name__ == "__main__":
    import os
    import sys

    from src.schema_registry.openmetadata.publish import get_client
    from src.storage import storage_from_env
    from src.utils.config import load_env

    load_env()
    _storage = storage_from_env()

    _client = None
    if os.environ.get("OPENMETADATA_JWT_TOKEN"):
        _client = get_client(
            host_port=os.environ.get("OPENMETADATA_HOST_PORT", "http://localhost:8585/api"),
            jwt_token=os.environ["OPENMETADATA_JWT_TOKEN"],
        )

    _results = run_field_dictionary(
        department=os.environ["DEPARTMENT"],
        dataset=os.environ["DATASET"],
        source_file=os.environ["SOURCE_FILE"],
        storage=_storage,
        schema_name=os.environ.get("SCHEMA_NAME", "public"),
        openmetadata_client=_client,
    )
    for _table_name, _result in _results.items():
        if _result["status"] == "ok":
            print(f"{_table_name}: {_result['column_count']} column(s)")
        else:
            print(f"{_table_name}: FAILED -- {_result['error']}")
    # Non-zero when any table failed: a caller that only checks the exit
    # code would otherwise treat "5 of 7 tables ingested" as success.
    sys.exit(1 if any(r["status"] == "failed" for r in _results.values()) else 0)
