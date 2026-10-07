import csv
import tempfile
from pathlib import Path

from metadata.ingestion.ometa.ometa_api import OpenMetadata

from src.schema_registry import inputs
from src.schema_registry.parsers.field_dictionary_parser import parse_field_dictionary_text
from src.schema_registry.pipeline import _timestamp, run
from src.schema_registry.registry import lookups, paths
from src.storage.base import ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)

_COLUMN_FIELDS = ["name", "data_type", "length", "nullable", "default"]
# Only what a Field Dictionary actually answers. Writing blank tag/
# classification/glossary_term or a hard-coded active=true here would
# overwrite answers set by hand on an earlier run every time it's re-ingested.
_METADATA_FIELDS = ["name", "business_description"]


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

    # `source_file` may be a local path or a storage:<key> (see inputs.py).
    # The original multi-table file is archived once at dataset level; each
    # table's run() then archives the per-table split it actually parsed.
    source_bytes, source_name = inputs.read_input(storage, source_file)
    tables = parse_field_dictionary_text(inputs.decode(source_bytes), label=source_file)
    archive_path = paths.dataset_source_path(
        lookups.slugify(department), lookups.slugify(dataset), _timestamp(), source_name
    )
    inputs.archive(storage, archive_path, source_bytes)
    logger.info(f"Field dictionary: archived original -> {archive_path}")
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
                    writer.writerow({"name": name, "business_description": meta.get("business_description", "")})

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

