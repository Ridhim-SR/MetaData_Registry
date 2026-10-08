"""Agriculture's own submission parser (wired in by pipeline.parse_source).

The department submits ONE CSV holding several tables side by side::

    Table Name,crop_sales,,,,Table Name,current_booking,,
    ,,,,,
    column_name,data_type,,,,column_name,data_type,,
    id,character varying,,,,id,character varying,,

The shared csv parser expects a single table's `column_name,data_type`
header, so it cannot read that layout. `parse_table()` pulls out the block
for the table being ingested and returns the same canonical column shape
the shared parser produces, so nothing downstream (validate_schema,
curate_schema, the diff, publish) can tell which parser saw the file.

The block-splitting itself is the existing MultiTableCsvPreprocessor -- the
code preprocessing already uses to cut the same file into per-table CSVs --
so the two paths can't drift apart.

Anything that isn't that layout returns None, which tells
pipeline.parse_source() to fall back to the shared parser for the file's
format (the single-table CSVs preprocessing wrote, a DDL dump, ...).
"""

from src.schema_registry.parsers.dept.Agriculture.preprocessors import MultiTableCsvPreprocessor
from src.utils.logger import get_logger

logger = get_logger(__name__)

_MARKER = "table name"


def _multi_table_lines(text: str) -> list[str] | None:
    """The submission's lines when it is the multi-table layout, else None."""

    lines = text.splitlines()
    if len(lines) < MultiTableCsvPreprocessor.ROW_FIRST_COL_DEF + 1:
        return None
    if not lines[MultiTableCsvPreprocessor.ROW_TABLE_NAMES].lower().startswith(_MARKER):
        return None
    if "column_name" not in lines[MultiTableCsvPreprocessor.ROW_COLUMN_HEADERS].lower():
        return None
    return lines


def parse_table(text: str, table_name: str) -> list[dict] | None:
    """Columns of `table_name` from a multi-table agriculture submission.

    Returns None when `text` isn't that layout, so the caller can hand the
    file to the shared parser instead.
    """

    lines = _multi_table_lines(text)
    if lines is None:
        return None

    preprocessor = MultiTableCsvPreprocessor()
    blocks = preprocessor._detect_tables(lines[MultiTableCsvPreprocessor.ROW_COLUMN_HEADERS])
    # renames the table_1..table_n block keys to the names in row 0
    preprocessor._parse_table_names(lines[MultiTableCsvPreprocessor.ROW_TABLE_NAMES], blocks)
    table_columns = preprocessor._collect_column_definitions(
        lines[MultiTableCsvPreprocessor.ROW_FIRST_COL_DEF:], blocks
    )

    if table_name not in table_columns:
        available = ", ".join(sorted(name for name, cols in table_columns.items() if cols)) or "(none)"
        raise ValueError(f"'{table_name}' isn't in this submission -- it holds: {available}")

    columns = [
        {
            "name": name,
            "data_type": data_type,
            # same defaults the shared csv parser gives the per-table CSVs
            # preprocessing writes from this same block, so ingesting the
            # raw file or the split one produces an identical snapshot
            "length": None,
            "scale": None,
            "nullable": True,
            "default": None,
        }
        for name, data_type in table_columns[table_name]
    ]
    logger.info(f"agriculture_parser: parsed {len(columns)} column(s) for '{table_name}'")
    return columns


__all__ = ["parse_table"]
