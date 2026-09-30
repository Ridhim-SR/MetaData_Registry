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
    """Generate manifest CSV for the processed dataset."""
    config = get_dataset_config(dataset_name)
    department = "agriculture_department"
    dataset_slug = dataset_name
    schema_name = "public"

    manifest_path = Path("data_services/configs") / f"{dataset_slug}_manifest.csv"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    with manifest_path.open("w", encoding="utf-8", newline="") as f:
        f.write("department,dataset,table_name,source_file,source_format,schema_name\n")
        for table_name, output_path in table_results.items():
            source_file = output_path.replace("data_services/", "").replace("\\", "/")
            if source_file.startswith("data_services/"):
                source_file = source_file[len("data_services/"):]
            f.write(f"{department},{dataset_slug},{table_name},{source_file},csv,{schema_name}\n")

    return manifest_path