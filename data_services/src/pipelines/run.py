import os
import sys

from src.utils.logger import get_logger
from src.extract.extract import CSVExtractor
from src.transform.transform import CSVTransformer
from src.load.load import OpenMetadataLoader

logger = get_logger(__name__)


def run() -> None:
    logger.info("Pipeline run started")
    extractor = CSVExtractor(
        source_file=os.environ["SOURCE_FILE"],
        watermark_file=os.environ.get("WATERMARK_FILE", "state/watermark.txt"),
        watermark_column="year",
    )

    raw = extractor.extract()

    if raw.empty:
        logger.info("No new rows since last watermark -- nothing to do.")
        return

    transformer = CSVTransformer()
    clean = transformer.transform(raw)

    if clean.empty:
        logger.info("All new rows were dropped during cleaning -- nothing to load.")
        return

    loader = OpenMetadataLoader(
        host_port=os.environ["OPENMETADATA_HOST_PORT"],
        jwt_token=os.environ["OPENMETADATA_JWT_TOKEN"],
        service_name=os.environ["OM_SERVICE_NAME"],
        database_name=os.environ["OM_DATABASE_NAME"],
        schema_name=os.environ["OM_SCHEMA_NAME"],
        table_name=os.environ["OM_TABLE_NAME"],
        dedupe_keys=["year", "industry_code", "size_group", "variable"],
    )

    loader.append(clean)

    extractor.save_watermark(int(clean["year"].max()))
    logger.info(f"Pipeline complete. New watermark: {extractor.get_watermark()}")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        logger.error(f"Pipeline failed: {exc}", exc_info=True)
        sys.exit(1)