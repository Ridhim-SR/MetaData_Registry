from pathlib import Path
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)


class CSVExtractor:

    COLUMN_MAPPINGS = {
        "year": "year",
        "financial_year": "year",
        "fiscal_year": "year",
        "yr": "year",

        "industry_code_anzsic": "industry_code",
        "industry_code": "industry_code",
        "anzsic_code": "industry_code",

        "industry_name_anzsic": "industry_name",
        "industry_name": "industry_name",

        "rme_size_grp": "size_group",
        "size_group": "size_group",
        "size": "size_group",

        "variable": "variable",
        "metric": "variable",

        "value": "value",
        "amount": "value",

        "unit": "unit",
        "units": "unit",
    }

    def __init__(
        self,
        source_file: str,
        watermark_file: str,
        watermark_column: str = "year",
    ):
        self.source_file = Path(source_file)
        self.watermark_file = Path(watermark_file)
        self.watermark_column = watermark_column

    def get_watermark(self) -> int:
        """Get the last processed watermark."""

        if not self.watermark_file.exists():
            logger.info(f"No watermark file at {self.watermark_file} -- starting from 0")
            return 0

        value = self.watermark_file.read_text().strip()

        watermark = int(value) if value else 0
        logger.info(f"Loaded watermark: {watermark}")
        return watermark

    def save_watermark(self, value: int) -> None:
        """Save the latest watermark."""

        self.watermark_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.watermark_file.write_text(str(value))
        logger.info(f"Saved watermark: {value}")

    def map_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map source column names to standard column names."""

        df.columns = (
            df.columns
            .str.strip()
            .str.lower()
            .str.replace(r"[^\w]+", "_", regex=True)
            .str.strip("_")
        )

        df = df.rename(
            columns={
                column: self.COLUMN_MAPPINGS[column]
                for column in df.columns
                if column in self.COLUMN_MAPPINGS
            }
        )

        df = df.drop(columns=[c for c in df.columns if c.startswith("unnamed")])

        return df

    def extract(self) -> pd.DataFrame:
        """Extract records newer than the last watermark."""

        last_watermark = self.get_watermark()

        df = pd.read_csv(self.source_file)
        logger.info(f"Read {len(df)} row(s) from {self.source_file}")

        # Map source columns to standard names
        df = self.map_columns(df)

        # Check watermark column
        if self.watermark_column not in df.columns:
            raise ValueError(
                f"Watermark column '{self.watermark_column}' "
                f"not found. Available columns: "
                f"{list(df.columns)}"
            )

        # Convert watermark column
        df[self.watermark_column] = pd.to_numeric(
            df[self.watermark_column],
            errors="coerce",
        )

        # Remove invalid watermark values
        df = df.dropna(
            subset=[self.watermark_column]
        )

        df[self.watermark_column] = (
            df[self.watermark_column].astype(int)
        )

        # Extract only new records
        extracted = df[
            df[self.watermark_column] > last_watermark
        ].copy()

        logger.info(
            f"Extracted {len(extracted)} new row(s) "
            f"(year > {last_watermark})"
        )
        return extracted