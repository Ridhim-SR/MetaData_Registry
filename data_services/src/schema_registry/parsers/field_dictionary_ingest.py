import csv
import tempfile
from pathlib import Path

from metadata.ingestion.ometa.ometa_api import OpenMetadata

from src.schema_registry.parsers.field_dictionary_parser import parse_field_dictionary
from src.schema_registry.pipeline import run
from src.storage.base import ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)

_COLUMN_FIELDS = ["name", "data_type", "length", "nullable", "default"]
_METADATA_FIELDS = ["name", "business_description", "tag", "classification", "glossary_term", "active"]


def run_field_dictionary(
    department: str,
    dataset: str,
    source_file: str,
    storage: ObjectStorage,
    schema_name: str = "public",
    openmetadata_client: OpenMetadata | None = None,
    allow_column_removal: bool = False,
) -> dict[str, dict]:
    """Ingest a multi-table Field Dictionary CSV (see field_dictionary_parser.py
    for the expected shape) by splitting it into one temporary per-table
    columns file + business-metadata file per "Dataset Name" group, then
    calling pipeline.run() once per table -- exactly as if the department
    had submitted one CSV per table. Every existing guarantee (diff-based
    safety guard, locking, retry, auto-tag/auto-classification) applies
    unchanged, since run() itself isn't touched.

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

    tables = parse_field_dictionary(source_file)
    results: dict[str, dict] = {}

    with tempfile.TemporaryDirectory() as tmp_dir:
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
                            "tag": "",
                            "classification": "",
                            "glossary_term": "",
                            "active": "true",
                        }
                    )

            logger.info(f"Field dictionary: ingesting table '{table_name}' ({len(table['columns'])} column(s))")
            try:
                results[table_name] = {
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
                    ),
                }
            except Exception as exc:  # noqa: BLE001 -- keep going, report this table as failed
                logger.error(f"Field dictionary: table '{table_name}' failed: {exc}")
                results[table_name] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    ok = sum(1 for r in results.values() if r["status"] == "ok")
    logger.info(f"Field dictionary: {ok}/{len(results)} table(s) ingested")
    return results


if __name__ == "__main__":
    import os
    import sys

    from dotenv import load_dotenv

    from src.schema_registry.openmetadata.publish import get_client
    from src.storage import storage_from_env

    load_dotenv()
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
            print(f"{_table_name}: {_result['column_count']} column(s), {_result['warning_count']} warning(s)")
        else:
            print(f"{_table_name}: FAILED -- {_result['error']}")
    # Non-zero when any table failed: a caller that only checks the exit
    # code would otherwise treat "5 of 7 tables ingested" as success.
    sys.exit(1 if any(r["status"] == "failed" for r in _results.values()) else 0)
