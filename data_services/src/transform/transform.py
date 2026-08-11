from pathlib import Path
import pandas as pd
import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)


class CSVTransformer:
    """
    Cleans and standardizes records produced by CSVExtractor.

    Expected input columns (after CSVExtractor.map_columns):
        year, industry_code, industry_name, size_group,
        variable, value, unit
    """

    REQUIRED_COLUMNS = [
        "year",
        "industry_code",
        "industry_name",
        "size_group",
        "variable",
        "value",
    ]

    # Columns that should be treated as text and stripped/normalized
    TEXT_COLUMNS = [
        "industry_code",
        "industry_name",
        "size_group",
        "variable",
        "unit",
    ]

    def __init__(self, dedupe_keys: list[str] | None = None):
        # Default natural key for a record in this dataset
        self.dedupe_keys = dedupe_keys or [
            "year",
            "industry_code",
            "size_group",
            "variable",
        ]

    def validate_columns(self, df: pd.DataFrame) -> None:
        """Ensure all required columns are present before transforming."""

        missing = [c for c in self.REQUIRED_COLUMNS if c not in df.columns]

        if missing:
            raise ValueError(
                f"Missing required column(s) for transform: {missing}. "
                f"Available columns: {list(df.columns)}"
            )

    def clean_text(self, df: pd.DataFrame) -> pd.DataFrame:
        """Strip whitespace, collapse internal spaces, and title/upper-case
        text columns consistently."""

        df = df.copy()

        for col in self.TEXT_COLUMNS:
            if col not in df.columns:
                continue

            df[col] = (
                df[col]
                .astype("string")
                .str.strip()
                .str.replace(r"\s+", " ", regex=True)
            )

        # Industry codes are typically short alpha codes (e.g. ANZSIC) -> uppercase
        if "industry_code" in df.columns:
            df["industry_code"] = df["industry_code"].str.upper()

        # Free-text names -> title case for consistency
        if "industry_name" in df.columns:
            df["industry_name"] = df["industry_name"].str.title()

        if "unit" in df.columns:
            df["unit"] = df["unit"].str.lower()

        return df

    def clean_value(self, df: pd.DataFrame) -> pd.DataFrame:
        """Coerce the value column to numeric, dropping rows that can't be
        parsed (e.g. 'n/a', '-', blanks)."""

        df = df.copy()

        # Strip common non-numeric artifacts before coercion (commas, $ signs)
        df["value"] = (
            df["value"]
            .astype("string")
            .str.replace(",", "", regex=False)
            .str.replace("$", "", regex=False)
            .str.strip()
        )

        df["value"] = pd.to_numeric(df["value"], errors="coerce")

        before = len(df)
        df = df.dropna(subset=["value"])
        dropped = before - len(df)

        if dropped:
            logger.info(f"Dropped {dropped} row(s) with non-numeric 'value'")

        return df

    def drop_incomplete_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """Drop rows missing any required identifying field."""

        key_cols = [c for c in self.REQUIRED_COLUMNS if c != "value"]

        before = len(df)
        df = df.dropna(subset=key_cols)
        df = df[(df[key_cols].astype("string") != "").all(axis=1)]
        dropped = before - len(df)

        if dropped:
            logger.info(f"Dropped {dropped} row(s) with missing key field(s)")

        return df

    def deduplicate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove duplicate records on the natural key, keeping the last
        occurrence (assumes later rows are more recent/authoritative)."""

        before = len(df)
        df = df.drop_duplicates(subset=self.dedupe_keys, keep="last")
        dropped = before - len(df)

        if dropped:
            logger.info(f"Dropped {dropped} duplicate row(s) on {self.dedupe_keys}")

        return df

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run the full transformation pipeline."""

        logger.info(f"Transforming {len(df)} row(s)")
        self.validate_columns(df)

        df = self.clean_text(df)
        df = self.clean_value(df)
        df = self.drop_incomplete_rows(df)
        df = self.deduplicate(df)

        logger.info(f"Transform complete: {len(df)} row(s) remain")
        return df.reset_index(drop=True)