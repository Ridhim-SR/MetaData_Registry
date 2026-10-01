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

    Returns {table_name: run()'s own result dict}, one entry per table found
    in the file. `department` must already be registered, same precondition
    as run() itself.
    """

    tables = parse_field_dictionary(source_file)
    results: dict[str, dict] = {}

    with tempfile.TemporaryDirectory() as tmp_dir:
        for table_name, table in tables.items():
            columns_path = Path(tmp_dir) / f"{table_name}_columns.csv"
            with columns_path.open("w", newline="") as f:
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
            with metadata_path.open("w", newline="") as f:
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
            results[table_name] = run(
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
            )

    return results


if __name__ == "__main__":
    import os

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
        print(f"{_table_name}: {_result['column_count']} column(s), {_result['warning_count']} warning(s)")
