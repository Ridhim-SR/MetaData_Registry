"""Abstract base class for dataset preprocessors."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class BasePreprocessor(ABC):
    """Abstract base class for all dataset preprocessors."""

    @abstractmethod
    def process(
        self,
        input_path: Path,
        output_dir: Path,
        tables: list[str],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Process input file and write clean table CSVs to output directory.

        Args:
            input_path: Path to the raw input CSV file
            output_dir: Directory to write clean table CSVs
            tables: List of expected table names
            dry_run: If True, only preview what would be done without writing

        Returns:
            Dictionary with processing results:
            - "tables": dict mapping table_name -> output_path (or expected path if dry_run)
            - "skipped_rows": list of skipped row info (for logging)
            - "stats": dict with row counts per table
        """
        pass