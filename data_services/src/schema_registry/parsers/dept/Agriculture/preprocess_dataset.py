"""CLI for preprocessing a department's multi-table dataset CSV into one CSV per table.

Wired for dev-time use: it cuts the department's raw submission into the
per-table files under ``data_services/source/`` and writes the manifest
``batch.py`` reads. ``sync`` does **not** use any of that -- ``sync`` reads
``catalog.yaml`` and pulls each table out of the submission itself (see
parsers/agriculture_parser.py). See the "Two ways in" section of the README.

    python3 -m src.schema_registry.parsers.dept.Agriculture.preprocess_dataset --dataset farmer_registration_master_dataset
    python3 -m src.schema_registry.parsers.dept.Agriculture.preprocess_dataset --all --dry-run
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.logger import LOG_DIR, get_logger

from .preprocessors import (
    PREPROCESSOR_CONFIG,
    get_dataset_config,
    get_preprocessor,
    generate_manifest,
)

# get_logger() rather than logging.basicConfig(): a library module must not
# reconfigure the root logger, and the console format belongs to the project.
logger = get_logger(__name__)


def process_dataset(dataset_name: str, dry_run: bool = False) -> dict[str, Any]:
    """Process a single dataset."""
    logger.info(f"Processing dataset: {dataset_name} (dry_run={dry_run})")

    config = get_dataset_config(dataset_name)
    preprocessor = get_preprocessor(dataset_name)

    input_path = Path(config["input_file"])
    output_dir = Path(config["output_dir"])
    tables = config.get("tables", [])

    if not input_path.exists():
        raise FileNotFoundError(
            f"Input file not found: {input_path} -- it is the department's raw submission, "
            f"which is not committed (see README, 'Two ways in'). Put it there and re-run."
        )

    results = preprocessor.process(
        input_path=input_path,
        output_dir=output_dir,
        tables=tables,
        dry_run=dry_run,
    )

    if not dry_run:
        manifest_path = generate_manifest(dataset_name, output_dir, results["tables"])
        logger.info(f"Generated manifest: {manifest_path}")
        results["manifest"] = str(manifest_path)

    if results["skipped_rows"]:
        # LOG_DIR is resolved from this package's location, so the log lands in
        # data_services/logs whatever directory the command was run from.
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        skipped_log = LOG_DIR / f"skipped_{dataset_name}_{datetime.now().strftime('%Y%m%dT%H%M%S')}.log"
        with skipped_log.open("w", encoding="utf-8") as f:
            for row in results["skipped_rows"]:
                f.write(f"Table: {row['table']}, Row: {row['row_index']}, Error: {row['error']}, Raw: {row['raw_row']}\n")
        logger.warning(f"Skipped {len(results['skipped_rows'])} row(s), logged to {skipped_log}")
    else:
        logger.info("No rows skipped")

    return results


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Preprocess dataset CSV files for schema registry ingestion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 -m src.schema_registry.parsers.dept.Agriculture.preprocess_dataset --dataset farmer_registration_master_dataset
  python3 -m src.schema_registry.parsers.dept.Agriculture.preprocess_dataset --dataset scheme_physical_financial_progress_dataset --dry-run
  python3 -m src.schema_registry.parsers.dept.Agriculture.preprocess_dataset --all
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dataset",
        help="Name of dataset to process (must be in registry)",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Process all configured datasets",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be processed without writing files",
    )

    args = parser.parse_args(argv)

    if args.dataset:
        datasets = [args.dataset]
    else:
        datasets = list(PREPROCESSOR_CONFIG.keys())

    logger.info(f"Starting preprocessing for: {datasets}")
    if args.dry_run:
        logger.info("DRY RUN MODE - no files will be written")

    all_results = {}
    for dataset_name in datasets:
        try:
            result = process_dataset(dataset_name, dry_run=args.dry_run)
            all_results[dataset_name] = result
        except Exception as e:
            logger.error(f"Failed to process {dataset_name}: {e}")
            all_results[dataset_name] = {"error": str(e)}
            return 1

    logger.info("=" * 60)
    logger.info("PREPROCESSING SUMMARY")
    logger.info("=" * 60)

    for dataset_name, result in all_results.items():
        if "error" in result:
            logger.error(f"  {dataset_name}: FAILED - {result['error']}")
        else:
            logger.info(f"  {dataset_name}: OK")
            for table_name, stats in result.get("stats", {}).items():
                logger.info(
                    f"    {table_name}: {stats['columns']} columns, "
                    f"{stats['rows_written']} rows written, "
                    f"{stats['rows_skipped']} rows skipped"
                )
            if not args.dry_run and "manifest" in result:
                logger.info(f"    Manifest: {result['manifest']}")

    if args.dry_run:
        logger.info("\nDRY RUN COMPLETE - no files were written")
    else:
        logger.info("\nPREPROCESSING COMPLETE")

    return 1 if any("error" in r for r in all_results.values()) else 0


if __name__ == "__main__":
    from src.utils.cli import run_cli

    sys.exit(run_cli("preprocess", _main, sys.argv[1:]))
