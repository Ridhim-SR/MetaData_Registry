import csv
from collections import Counter
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

from src.schema_registry.curate import validate_schema
from src.schema_registry.parsers.field_dictionary_parser import parse_field_dictionary
from src.schema_registry.parsers.sericulture_xlsx import (
    OUTPUT_HEADERS,
    WORKBOOKS,
    convert_all,
    convert_workbook,
)

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "sericulture"
REAL_WORKBOOKS = {
    config.filename: next(SAMPLES.rglob(config.filename), None)
    for config in WORKBOOKS
}
HAS_REAL_WORKBOOKS = all(path is not None for path in REAL_WORKBOOKS.values())


def _write_workbook(path, sheet_name, headers, rows, merged=()):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    for cell_range in merged:
        sheet.merge_cells(cell_range)
    workbook.save(path)
    return path


def test_mpr_conversion_maps_fields_and_excludes_example_values(tmp_path):
    source = _write_workbook(
        tmp_path / "MPR.xlsx",
        "Sheet1",
        [
            "Dataset Field / Variable / Column",
            "Field Label (English)",
            "Field Label (Hindi)",
            "Data / Field / Column Description",
            "Units",
            "Format / Data Type",
            "Length",
            "Mandatory (Y/N)",
            "Personal Data (Y/N)",
            "Availability (Public/Internal)",
            "Sample Value / Example & Notes",
        ],
        [
            [
                "district_name",
                "District",
                "जनपद",
                "District name",
                "",
                "Text",
                "100",
                "Y",
                "N",
                "Internal",
                "SENSITIVE_EXAMPLE_MUST_NOT_BE_EXPORTED",
            ],
            ["target_amount", "Target", "", "Target amount", "INR", "Decimal", "12,2", "N", "N", "Internal", "999"],
        ],
    )
    output = convert_workbook(source, tmp_path / "out")

    with output.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        assert reader.fieldnames == list(OUTPUT_HEADERS)
    assert "Sample Value / Example & Notes" not in OUTPUT_HEADERS
    assert "SENSITIVE_EXAMPLE_MUST_NOT_BE_EXPORTED" not in output.read_text(encoding="utf-8-sig")
    assert rows[0]["Format"] == "Text (100)"
    assert rows[0]["name_hindi"] == "जनपद"
    assert rows[1]["Format"] == "Decimal (12,2)"
    parsed = parse_field_dictionary(str(output))["monthly_progress_report"]
    assert [column["name"] for column in parsed["columns"]] == ["district_name", "target_amount"]
    assert parsed["columns"][0]["name_hindi"] == "जनपद"
    assert parsed["business_metadata"]["target_amount"]["unit"] == "INR"
    validate_schema("sericulture.monthly_progress_report.monthly_progress_report", parsed["columns"])


def test_scheme_conversion_skips_section_rows_and_carries_merged_group(tmp_path):
    source = _write_workbook(
        tmp_path / "Mukhyamantri Resham Vikas Yojana.xlsx",
        "Sheet2",
        [
            "Section / Group",
            "Logical Field Name",
            "Field Label (Hindi/Regional Language)",
            "Field Label (English)",
            "Data Type",
            "Max Length / Format",
            "Mandatory (Yes/No)",
            "Allowed Values / Master Dropdown Options",
            "Description",
            "Sample Value(s)",
        ],
        [
            ["Personal Details", "", "", "", "", "", "", "", "", ""],
            ["Personal Details", "applicant_name", "आवेदक", "Applicant", "VARCHAR / FK", "100 chars", "Yes", "", "Name", "EXAMPLE"],
            [None, "age_years", "आयु", "Age", "INT / FK", "2–3 digits (18–100)", "No", "", "Age", "18"],
        ],
        merged=("A2:A3",),
    )
    output = convert_workbook(source, tmp_path / "out")
    parsed = parse_field_dictionary(str(output))["mukhyamantri_resham_vikas_yojana"]

    assert [column["name"] for column in parsed["columns"]] == ["applicant_name", "age_years"]
    assert parsed["columns"][0]["data_type"] == "character varying"
    assert parsed["columns"][1]["data_type"] == "integer"
    assert parsed["business_metadata"]["applicant_name"]["business_description"] == "Name"
    with output.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["Section"] for row in rows] == ["Personal Details", "Personal Details"]
    assert "EXAMPLE" not in output.read_text(encoding="utf-8-sig")
    validate_schema("sericulture.mrv.mrv", parsed["columns"])


def test_resham_conversion_skips_instruction_row_and_merges_prefilled_fields(tmp_path):
    source = _write_workbook(
        tmp_path / "Resham Mitra.xlsx",
        "Sheet1",
        [
            "Dataset Field /\nVariable/Column",
            "Field Label\n(Hindi/Regional Language)",
            "Field Label\n(English)",
            "Data/Field/Column\nDescription",
            "Format/Data\nType",
            "Length",
            "Mandatory\n(Y/N)",
            "Personal\nData (Y/N)",
            "Availability\n(Public/Internal)",
            "Sample\nValue/Example",
        ],
        [
            ["Exact\nfield/column\nname", "", "", "", "", "", "", "DO NOT INTERPRET", "", "EXAMPLE"],
            ["beneficiary_name (Inferred)", "लाभार्थी", "Beneficiary", "Registration name", "Text", "", "Y", "Y", "Internal", "EXAMPLE"],
            ["beneficiary_name (Inferred)", "लाभार्थी", "Beneficiary", "Pre-filled application name", "Text", "", "Y", "Y", "Internal", "EXAMPLE"],
        ],
    )
    output = convert_workbook(source, tmp_path / "out")
    parsed = parse_field_dictionary(str(output))["resham_mitra"]

    assert len(parsed["columns"]) == 1
    assert Counter(column["name"] for column in parsed["columns"]) == {"beneficiary_name (Inferred)": 1}
    assert parsed["columns"][0]["name_hindi"] == "लाभार्थी"
    assert parsed["business_metadata"]["beneficiary_name (Inferred)"]["business_description"] == (
        "Registration name / Pre-filled application name"
    )
    assert "EXAMPLE" not in output.read_text(encoding="utf-8-sig")
    validate_schema("sericulture.resham_mitra.resham_mitra", parsed["columns"])


@pytest.mark.skipif(not HAS_REAL_WORKBOOKS, reason="Sericulture workbooks are local and git-ignored")
def test_real_sericulture_workbooks_convert_to_registry_dictionaries(tmp_path):
    outputs = convert_all(SAMPLES, tmp_path)
    assert set(outputs) == {
        "monthly_progress_report",
        "mukhyamantri_resham_vikas_yojana",
        "resham_mitra",
    }

    expected_fields = {
        "monthly_progress_report": 50,
        "mukhyamantri_resham_vikas_yojana": 49,
        "resham_mitra": 51,
    }
    for dataset, output in outputs.items():
        with output.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
            assert "Sample Value" not in " ".join(reader.fieldnames or [])
            assert "Example" not in " ".join(reader.fieldnames or [])
        assert len(rows) == expected_fields[dataset]
        parsed = parse_field_dictionary(str(output))
        assert dataset in parsed
        validate_schema(f"sericulture.{dataset}.{dataset}", parsed[dataset]["columns"])
