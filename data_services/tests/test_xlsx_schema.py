"""The generic .xlsx -> column-CSV converter used by the ingest API."""

import csv
import datetime as dt

import openpyxl
import pytest

from src.schema_registry.parsers import xlsx_schema


def _workbook(path, sheets):
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(row)
    workbook.save(path)
    return path


def _read(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_preamble_rows_are_skipped_and_types_are_inferred(tmp_path):
    source = _workbook(tmp_path / "wb.xlsx", {"Data": [
        ["Financial Status"],                       # merged title, one filled cell
        ["Exported On 2026-01-01"],                 # another one-cell row
        ["Serial No", "Firm Name", "Total Cost"],   # header
        [1, "Alpha", 12.5],
        [2, "Beta", 7],
    ]})

    report = xlsx_schema.write_schema_csv(source, tmp_path / "cols.csv")

    assert report == {"sheet": "Data", "header_row": 3, "columns": 3, "rows_sampled": 2}
    assert [(row["name"], row["data_type"]) for row in _read(tmp_path / "cols.csv")] == [
        ("serial_no", "integer"),
        ("firm_name", "character varying"),
        ("total_cost", "double precision"),
    ]


def test_a_non_ascii_header_is_kept_as_the_hindi_label(tmp_path):
    source = _workbook(tmp_path / "wb.xlsx", {"Sheet1": [
        ["नाम", "आयु"],
        ["A", 30],
    ]})

    xlsx_schema.write_schema_csv(source, tmp_path / "cols.csv")

    assert _read(tmp_path / "cols.csv") == [
        {"name": "column_1", "name_Hindi": "नाम", "data_type": "character varying"},
        {"name": "column_2", "name_Hindi": "आयु", "data_type": "integer"},
    ]


def test_duplicate_headings_get_distinct_names(tmp_path):
    source = _workbook(tmp_path / "wb.xlsx", {"S": [
        ["Name", "name", "Name"],
        ["a", "b", "c"],
    ]})

    xlsx_schema.write_schema_csv(source, tmp_path / "cols.csv")

    assert [row["name"] for row in _read(tmp_path / "cols.csv")] == ["name", "name_2", "name_3"]


def test_the_widest_headered_sheet_is_chosen(tmp_path):
    source = _workbook(tmp_path / "wb.xlsx", {
        "Cover": [["Title"]],
        "Data": [["a", "b"], [1, 2]],
    })

    report = xlsx_schema.write_schema_csv(source, tmp_path / "cols.csv")

    assert report["sheet"] == "Data"


def test_a_sheet_can_be_named_explicitly(tmp_path):
    source = _workbook(tmp_path / "wb.xlsx", {
        "First": [["a", "b"], [1, 2]],
        "Second": [["c", "d"], [3, 4]],
    })

    report = xlsx_schema.write_schema_csv(source, tmp_path / "cols.csv", sheet="Second")

    assert report["sheet"] == "Second" and [row["name"] for row in _read(tmp_path / "cols.csv")] == ["c", "d"]


def test_a_missing_sheet_lists_the_sheets_that_exist(tmp_path):
    source = _workbook(tmp_path / "wb.xlsx", {"Data": [["a"], [1]]})

    with pytest.raises(ValueError, match=r"Data"):
        xlsx_schema.write_schema_csv(source, tmp_path / "cols.csv", sheet="Missing")


def test_a_header_without_data_rows_is_refused(tmp_path):
    source = _workbook(tmp_path / "wb.xlsx", {"S": [["a", "b"]]})

    with pytest.raises(ValueError, match="no data rows"):
        xlsx_schema.write_schema_csv(source, tmp_path / "cols.csv")


def test_a_sheet_without_a_header_is_refused(tmp_path):
    source = _workbook(tmp_path / "wb.xlsx", {"S": [["only one cell"]]})

    with pytest.raises(ValueError, match="usable header row"):
        xlsx_schema.write_schema_csv(source, tmp_path / "cols.csv")


def test_inference_handles_python_values_directly():
    assert xlsx_schema._infer_type([1, 2]) == "integer"
    assert xlsx_schema._infer_type([1, 2.5]) == "double precision"
    assert xlsx_schema._infer_type([True, False]) == "boolean"
    assert xlsx_schema._infer_type([dt.date(2026, 1, 1)]) == "date"
    assert xlsx_schema._infer_type([dt.datetime(2026, 1, 1, 10, 0)]) == "timestamp"
    assert xlsx_schema._infer_type([None, ""]) == "character varying"
    assert xlsx_schema._infer_type(["1", "2"]) == "character varying"
