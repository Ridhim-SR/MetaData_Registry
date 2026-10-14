"""Dataset preprocessor configuration registry."""

from pathlib import Path
from typing import Any

from .base import BasePreprocessor
from .multi_table_csv import MultiTableCsvPreprocessor

PREPROCESSOR_MAP = {
    "multi_table_csv": MultiTableCsvPreprocessor,
}

PREPROCESSOR_CONFIG = {
    "farmer_registration_master_dataset": {
        "preprocessor": "multi_table_csv",
        "input_file": "datasets/Farmer_Registration_Master_Dataset-12_9_15.csv",
        "output_dir": "data_services/source/farmer_registration",
        "tables": ["farmers"],
        # Passed through to every row of the generated manifest, so batch.py
        # hands it to pipeline.run() as business_metadata_file. Without it the
        # field dictionary (descriptions / tags / MDSF classification) is
        # silently dropped on the next ingest.
        "business_metadata_file": "configs/field_dictionaries/farmer_registration_field_dictionary.csv",
    },
    "scheme_physical_financial_progress_dataset": {
        "preprocessor": "multi_table_csv",
        "input_file": "datasets/Scheme_Physical__Financial_Progress_Dataset-12_30_34.csv",
        "output_dir": "data_services/source/scheme_progress",
        "tables": [
            "target_allocation_v2",
            "financial_budget_allocation",
            "grant_wise_bill_generation",
        ],
    },
    "distribution_record_dataset": {
        "preprocessor": "multi_table_csv",
        "input_file": "datasets/Distribution_Records_Dataset-12_13_52.csv",
        "output_dir": "data_services/source/distribution_records",
        "tables": [
            "crop_sales",
            "current_booking",
            "current_booking_farmer_details",
            "online_booking",
            "online_booking_details",
        ],
        # This dataset's manifest was named before the "<dataset>_manifest.csv"
        # convention; keep the historical name so existing batch commands
        # (MANIFEST_FILE=configs/distribution_records_manifest.csv) keep working.
        "manifest_file": "data_services/configs/distribution_records_manifest.csv",
    },
}


def get_preprocessor(dataset_name: str) -> BasePreprocessor:
    """Get preprocessor instance for a dataset by name."""
    if dataset_name not in PREPROCESSOR_CONFIG:
        raise ValueError(f"Unknown dataset: {dataset_name}. Available: {list(PREPROCESSOR_CONFIG.keys())}")

    config = PREPROCESSOR_CONFIG[dataset_name]
    preprocessor_type = config["preprocessor"]

    if preprocessor_type not in PREPROCESSOR_MAP:
        raise ValueError(f"Unknown preprocessor type: {preprocessor_type}")

    return PREPROCESSOR_MAP[preprocessor_type]()


def get_dataset_config(dataset_name: str) -> dict[str, Any]:
    """Get full configuration for a dataset."""
    if dataset_name not in PREPROCESSOR_CONFIG:
        raise ValueError(f"Unknown dataset: {dataset_name}")
    return PREPROCESSOR_CONFIG[dataset_name]


def generate_manifest(dataset_name: str, output_dir: Path, table_results: dict[str, str]) -> Path:
    """Generate manifest CSV for the processed dataset.

    The `business_metadata_file` / `manifest_file` keys in PREPROCESSOR_CONFIG
    are carried through: the former becomes an extra manifest column (consumed
    by batch.py as pipeline.run()'s business_metadata_file), the latter
    overrides the default ``data_services/configs/<dataset>_manifest.csv``
    path. The extra column is only written when a dataset actually configures
    it, so manifests of datasets without a field dictionary stay byte-identical.
    """
    config = get_dataset_config(dataset_name)
    department = "agri_dept"
    dataset_slug = dataset_name
    schema_name = "public"

    business_metadata_file = config.get("business_metadata_file", "")
    manifest_path = Path(
        config.get("manifest_file") or f"data_services/configs/{dataset_slug}_manifest.csv"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    header = "department,dataset,table_name,source_file,source_format,schema_name"
    if business_metadata_file:
        header += ",business_metadata_file"

    with manifest_path.open("w", encoding="utf-8", newline="") as f:
        f.write(header + "\n")
        for table_name, output_path in table_results.items():
            source_file = output_path.replace("data_services/", "").replace("\\", "/")
            if source_file.startswith("data_services/"):
                source_file = source_file[len("data_services/"):]
            row = f"{department},{dataset_slug},{table_name},{source_file},csv,{schema_name}"
            if business_metadata_file:
                row += f",{business_metadata_file}"
            f.write(row + "\n")

    return manifest_path