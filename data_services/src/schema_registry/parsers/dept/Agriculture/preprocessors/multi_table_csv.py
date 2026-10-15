"""Preprocessor for multi-table CSV format with metadata header rows.

The input files contain COLUMN DEFINITIONS (schema), not data records.
Each row after the header is a column definition: column_name,data_type
"""

import logging
from pathlib import Path
from typing import Any

from .base import BasePreprocessor

logger = logging.getLogger(__name__)


class MultiTableCsvPreprocessor(BasePreprocessor):
    """Preprocessor for CSV files containing column definitions for multiple tables.

    Input format:
    - Row 0: Table Name,<table1>,,Table Name,<table2>,...
    - Row 1: (empty)
    - Row 2: column_name,data_type,,column_name,data_type,...
    - Row 3+: Column definitions (one per row): col_name,data_type,,col_name,data_type,...
    """

    ROW_TABLE_NAMES = 0
    ROW_EMPTY = 1
    ROW_COLUMN_HEADERS = 2
    ROW_FIRST_COL_DEF = 3

    def process(
        self,
        input_path: Path,
        output_dir: Path,
        tables: list[str],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        logger.info(f"Processing {input_path}")

        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        raw_lines = input_path.read_text(encoding="utf-8").splitlines()

        if len(raw_lines) < self.ROW_FIRST_COL_DEF + 1:
            raise ValueError(f"Input file too short, expected at least {self.ROW_FIRST_COL_DEF + 1} rows")

        table_blocks = self._detect_tables(raw_lines[self.ROW_COLUMN_HEADERS])
        table_names = self._parse_table_names(raw_lines[self.ROW_TABLE_NAMES], table_blocks)

        logger.debug(f"Detected blocks: {table_blocks}")
        logger.debug(f"Mapped names: {table_names}")

        # Collect column definitions from all data rows
        col_def_rows = raw_lines[self.ROW_FIRST_COL_DEF:]
        table_columns = self._collect_column_definitions(col_def_rows, table_blocks)

        # Update blocks with collected columns
        for table_name, columns in table_columns.items():
            if table_name in table_blocks:
                table_blocks[table_name]["columns"] = columns

        if tables:
            table_blocks = {name: block for name, block in table_blocks.items() if name in tables}
            table_columns = {name: cols for name, cols in table_columns.items() if name in tables}

        logger.info(f"Found {len(table_blocks)} table(s), {len(col_def_rows)} column definition row(s)")

        results = {
            "tables": {},
            "skipped_rows": [],
            "stats": {},
        }

        for table_name, block in table_blocks.items():
            columns = block.get("columns", [])

            if not dry_run:
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / f"{table_name}.csv"
                self._write_clean_csv(output_path, columns)
                results["tables"][table_name] = str(output_path)
                logger.info(f"Wrote {len(columns)} column(s) to {output_path}")
            else:
                results["tables"][table_name] = str(output_dir / f"{table_name}.csv")
                logger.info(f"[DRY RUN] Would write {len(columns)} column(s) to {output_dir / f'{table_name}.csv'}")

            results["stats"][table_name] = {
                "columns": len(columns),
                "rows_written": len(columns),
                "rows_skipped": 0,
            }

        return results

    def _detect_tables(self, header_line: str) -> dict[str, dict]:
        """Detect table column blocks from the column header row (row 2)."""
        parts = header_line.split(",")
        blocks = {}
        block_idx = 0
        i = 0

        while i < len(parts):
            part = parts[i].strip().lower()
            if part == "column_name":
                block_idx += 1
                block_key = f"table_{block_idx}"
                start_col = i

                if i + 1 < len(parts) and parts[i + 1].strip().lower() == "data_type":
                    end_col = i + 1
                    blocks[block_key] = {
                        "start_col": start_col,
                        "end_col": end_col,
                        "columns": [],
                    }
                    i = end_col + 1
                    continue
            i += 1

        logger.debug(f"Detected {len(blocks)} table block(s)")
        return blocks

    def _collect_column_definitions(self, col_def_rows: list[str], blocks: dict) -> dict[str, list[tuple[str, str]]]:
        """Collect all column definitions (name, type) for each table from the data rows."""
        table_columns = {name: [] for name in blocks.keys()}

        for row_idx, row in enumerate(col_def_rows):
            parts = row.split(",")
            for block_key, block_info in blocks.items():
                start_col = block_info["start_col"]

                if len(parts) > start_col:
                    col_name = parts[start_col].strip()
                    data_type = parts[start_col + 1].strip() if start_col + 1 < len(parts) else ""

                    if col_name and col_name.lower() != "column_name":
                        table_columns[block_key].append((col_name, data_type))

        logger.debug(f"Collected columns: {table_columns}")
        return table_columns

    def _parse_table_names(self, names_line: str, blocks: dict) -> dict[str, str]:
        """Parse row 0 to get table names for each detected block."""
        parts = names_line.split(",")
        table_names = {}
        block_list = list(blocks.items())

        for i, (block_key, block_info) in enumerate(block_list):
            name_col = block_info["start_col"]
            table_name = None

            if name_col < len(parts):
                candidate = parts[name_col].strip()
                if candidate and candidate != "Table Name":
                    table_name = candidate

            if not table_name and i + 1 < len(parts):
                for j in range(name_col + 1, min(len(parts), name_col + 5)):
                    candidate = parts[j].strip()
                    if candidate and candidate != "Table Name":
                        table_name = candidate
                        break

            if not table_name:
                table_name = f"table_{i + 1}"

            table_names[table_name] = table_name
            if block_key in blocks:
                blocks[table_name] = blocks.pop(block_key)

        return table_names

    def _write_clean_csv(self, output_path: Path, columns: list[tuple[str, str]]) -> None:
        """Write clean CSV with column_name,data_type header and column definitions."""
        with output_path.open("w", encoding="utf-8", newline="") as f:
            f.write("column_name,data_type\n")
            for col_name, data_type in columns:
                f.write(f"{col_name},{data_type}\n")