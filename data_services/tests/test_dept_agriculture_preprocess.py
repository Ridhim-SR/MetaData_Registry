"""Regression tests for the Agriculture Department preprocessing package
(src/schema_registry/parsers/dept/Agriculture).

These guard the two things a `--all` run must not break:
  * the field dictionary pointer (`business_metadata_file`) surviving in the
    generated manifest -- drop it and the next batch ingest loses every
    description / tag / MDSF classification;
  * the generated manifest of each dataset staying byte-identical to what is
    committed, so a preprocessing run doesn't dirty the working tree.
"""

from pathlib import Path

from src.schema_registry.parsers.dept.Agriculture.preprocessors import (
    PREPROCESSOR_CONFIG,
    generate_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS = REPO_ROOT / "data_services" / "configs"

EXPECTED_DATASETS = {
    "farmer_registration_master_dataset",
    "scheme_physical_financial_progress_dataset",
    "distribution_record_dataset",
}


def _committed(name: str) -> str:
    return (CONFIGS / name).read_text(encoding="utf-8").replace("\r\n", "\n")


def _generate(dataset: str, tables: list[str], monkeypatch, tmp_path) -> str:
    """Run generate_manifest() in an isolated cwd and return its output."""
    monkeypatch.chdir(tmp_path)
    output_dir = Path(PREPROCESSOR_CONFIG[dataset]["output_dir"])
    results = {table: str(output_dir / f"{table}.csv") for table in tables}
    path = generate_manifest(dataset, output_dir, results)
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_config_covers_all_three_datasets():
    assert EXPECTED_DATASETS == set(PREPROCESSOR_CONFIG)


def test_distribution_dataset_lists_all_five_tables():
    config = PREPROCESSOR_CONFIG["distribution_record_dataset"]
    assert config["tables"] == [
        "crop_sales",
        "current_booking",
        "current_booking_farmer_details",
        "online_booking",
        "online_booking_details",
    ]
    assert config["output_dir"] == "data_services/source/distribution_records"


def test_distribution_keeps_historical_manifest_name():
    config = PREPROCESSOR_CONFIG["distribution_record_dataset"]
    assert config["manifest_file"] == "data_services/configs/distribution_records_manifest.csv"


def test_farmer_config_carries_field_dictionary():
    config = PREPROCESSOR_CONFIG["farmer_registration_master_dataset"]
    assert config["business_metadata_file"] == (
        "configs/field_dictionaries/farmer_registration_field_dictionary.csv"
    )


def test_generate_manifest_writes_business_metadata_file(monkeypatch, tmp_path):
    text = _generate(
        "farmer_registration_master_dataset", ["farmers"], monkeypatch, tmp_path
    )

    header, *rows = text.strip().split("\n")
    assert header.split(",")[-1] == "business_metadata_file"
    assert len(rows) == 1
    assert rows[0].endswith(
        ",configs/field_dictionaries/farmer_registration_field_dictionary.csv"
    )


def test_generate_manifest_omits_column_without_config(monkeypatch, tmp_path):
    text = _generate(
        "scheme_physical_financial_progress_dataset",
        ["target_allocation_v2", "financial_budget_allocation", "grant_wise_bill_generation"],
        monkeypatch,
        tmp_path,
    )

    header = text.split("\n")[0]
    assert header == "department,dataset,table_name,source_file,source_format,schema_name"


def test_generated_farmer_manifest_matches_committed(monkeypatch, tmp_path):
    text = _generate("farmer_registration_master_dataset", ["farmers"], monkeypatch, tmp_path)
    assert text == _committed("farmer_registration_master_dataset_manifest.csv")


def test_generated_scheme_manifest_matches_committed(monkeypatch, tmp_path):
    text = _generate(
        "scheme_physical_financial_progress_dataset",
        ["target_allocation_v2", "financial_budget_allocation", "grant_wise_bill_generation"],
        monkeypatch,
        tmp_path,
    )
    assert text == _committed("scheme_physical_financial_progress_dataset_manifest.csv")


def test_generated_distribution_manifest_matches_committed(monkeypatch, tmp_path):
    text = _generate(
        "distribution_record_dataset",
        PREPROCESSOR_CONFIG["distribution_record_dataset"]["tables"],
        monkeypatch,
        tmp_path,
    )
    assert text == _committed("distribution_records_manifest.csv")
