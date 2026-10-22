from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

from src.schema_registry.parsers import mla_lads_xlsx

WORKBOOK = (
    Path(__file__).resolve().parents[2]
    / "Datasets"
    / "MLA LADS"
    / "MLA_LADS_UP_Financial_Status_English.xlsx"
)
REAL = pytest.mark.skipif(not WORKBOOK.exists(), reason=f"{WORKBOOK} is gitignored and not present")

HEADERS = [header for header, _, _, _ in mla_lads_xlsx.COLUMNS]
EXPECTED_NAMES = [name for _, name, _, _ in mla_lads_xlsx.COLUMNS]
EXPECTED_TYPES = [data_type for _, _, data_type, _ in mla_lads_xlsx.COLUMNS]
EXPECTED_HINDI = [name_hindi for _, _, _, name_hindi in mla_lads_xlsx.COLUMNS]

DATA_ROW = [
    1,
    "श्री उमर अली खान (1 विo सo बेहट)",
    "2024-25",
    "सहारनपुर",
    136.47,
    500,
    636.47,
    455.34,
    181.13,
    391.93,
    244.54,
    63.41,
]


def _write_workbook(tmp_path, headers=HEADERS, rows=None, preamble=True, sheet="Sheet1"):
    """A workbook shaped like the portal export: title, timestamp, headers, rows."""

    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = sheet
    start = 1
    if preamble:
        worksheet.cell(1, 1, "विधान मण्डल क्षेत्र विकास निधि योजना ,ग्राम्य विकास विभाग, उत्तर प्रदेश")
        worksheet.cell(
            2, 1, "Exported On Wed Oct 21 2026 11:34:19 GMT+0530 (India Standard Time)"
        )
        start = 3
    for column, header in enumerate(headers, start=1):
        worksheet.cell(start, column, header)
    for offset, row in enumerate(rows if rows is not None else [DATA_ROW], start=1):
        for column, value in enumerate(row, start=1):
            worksheet.cell(start + offset, column, value)

    path = tmp_path / "export.xlsx"
    workbook.save(path)
    workbook.close()
    return path


def test_skips_title_and_timestamp_and_keeps_the_twelve_columns(tmp_path):
    columns = mla_lads_xlsx.schema_columns(_write_workbook(tmp_path))

    assert [column["name"] for column in columns] == EXPECTED_NAMES
    assert [column["name_hindi"] for column in columns] == EXPECTED_HINDI
    assert [column["data_type"] for column in columns] == EXPECTED_TYPES
    assert all(column["nullable"] is True for column in columns)
    assert columns[0]["name_hindi"] == "क्रमसं०"


def test_header_is_found_even_when_spacing_and_case_differ(tmp_path):
    headers = list(HEADERS)
    headers[6] = "TOTAL (REMAINDER + ALLOCATED) (in lakh)"  # export has a run of spaces
    headers[3] = "NODAL DISTRICT"

    columns = mla_lads_xlsx.schema_columns(_write_workbook(tmp_path, headers=headers))

    assert len(columns) == 12
    assert columns[6]["name"] == "total_remainder_allocated_lakhs"


def test_hindi_values_survive_the_read(tmp_path):
    names, rows = mla_lads_xlsx.read_rows(_write_workbook(tmp_path))

    assert rows[0][names.index("mla_name_and_constituency")] == DATA_ROW[1]
    assert rows[0][names.index("nodal_district")] == DATA_ROW[3]


def test_write_schema_csv_is_the_shared_parser_shape(tmp_path):
    out = tmp_path / "mla_lads_schema.csv"
    mla_lads_xlsx.write_schema_csv(_write_workbook(tmp_path), out)

    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "name,name_Hindi,data_type"
    assert len(lines) == 1 + len(EXPECTED_NAMES)
    assert lines[1].split(",") == ["serial_number", "क्रमसं०", "integer"]


def test_a_missing_column_is_refused(tmp_path):
    with pytest.raises(ValueError, match="no MLA LADS header row"):
        mla_lads_xlsx.schema_columns(_write_workbook(tmp_path, headers=HEADERS[:-1]))


def test_a_workbook_without_the_report_shape_is_refused(tmp_path):
    path = tmp_path / "other.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active.append(["something", "else"])
    workbook.save(path)
    workbook.close()

    with pytest.raises(ValueError, match="not an MLA LADS financial-status export"):
        mla_lads_xlsx.schema_columns(path)


def test_a_text_value_in_an_amount_column_is_refused(tmp_path):
    row = list(DATA_ROW)
    row[5] = "not a number"

    with pytest.raises(ValueError, match="not a number"):
        mla_lads_xlsx.schema_columns(_write_workbook(tmp_path, rows=[row]))


@REAL
def test_real_export_has_twelve_columns_and_403_rows():
    names, rows = mla_lads_xlsx.read_rows(WORKBOOK)

    assert names == EXPECTED_NAMES
    assert len(rows) == 403
    assert rows[0][0] == 1
