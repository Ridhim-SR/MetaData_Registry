from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

from src.schema_registry.parsers.field_dictionary_parser import parse_field_dictionary
from src.schema_registry.parsers import kanya_xlsx

WORKBOOK = Path(__file__).resolve().parents[2] / "Datasets" / "Kanya Sumangla Portal.xlsx"
REAL = pytest.mark.skipif(not WORKBOOK.exists(), reason=f"{WORKBOOK} is gitignored and not present")

# What the department actually ships: the six columns we keep plus the four
# we drop (labels, availability, sample value, notes) and a trailing cell
# some sheets have and some don't.
FULL_HEADER = [
    "Dataset Name",
    "Dataset Field",
    "Field Label Hindi",
    "Field Label English",
    "Data Description",
    "Format",
    "Mandatory (Y/N)",
    "Personal Data (Y/N)",
    "Availability (Public/Internal)",
    "Sample Value",
    "Notes",
]


def _row(table="t1", field="col_a", description="What it means", fmt="Text", mandatory="Y", personal="N"):
    return [table, field, "hindi", "english", description, fmt, mandatory, personal, "Public", "9999999999", "note"]


def _workbook(path, sheets, note_rows=None):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    if note_rows is not None:
        ws = wb.create_sheet("Note")
        for row in note_rows:
            ws.append(row)
    wb.save(str(path))
    return path


def _roster_workbook(path, row):
    """A workbook containing every sheet in SHEETS, each with one data row
    produced by `row(config)`."""

    sheets = {config.sheet: [FULL_HEADER, row(config)] for config in kanya_xlsx.SHEETS}
    return _workbook(path, sheets)


CMSVY = next(config for config in kanya_xlsx.SHEETS if config.sheet == kanya_xlsx.CMSVY_SHEET)


def test_sheets_use_a_unique_dataset_slug_per_entry():
    slugs = [config.dataset for config in kanya_xlsx.SHEETS]
    assert len(slugs) == len(set(slugs))
    assert all(slug == slug.lower() for slug in slugs)


def test_every_sheet_names_a_department():
    for config in kanya_xlsx.SHEETS:
        assert config.department_id and config.department_id.islower()
        assert config.department_name


def test_read_sheet_keeps_only_the_six_parser_columns(tmp_path):
    path = _workbook(tmp_path / "wb.xlsx", {"t": [FULL_HEADER, _row()]})

    records = kanya_xlsx.read_sheet(path, "t")

    assert list(records[0].keys()) == kanya_xlsx.OUTPUT_HEADERS
    assert "Sample Value" not in records[0]
    assert "Field Label Hindi" not in records[0]


def test_columns_are_read_by_header_name_not_position(tmp_path):
    shuffled = [
        "Format",
        "Dataset Name",
        "Data Description",
        "Dataset Field",
        "Mandatory (Y/N)",
        "Personal Data (Y/N)",
    ]
    path = _workbook(tmp_path / "wb.xlsx", {"t": [shuffled, ["Text", "t1", "desc", "col_a", "Y", "N"]]})

    records = kanya_xlsx.read_sheet(path, "t")

    assert records == [
        {
            "Dataset Name": "t1",
            "Dataset Field": "col_a",
            "Data Description": "desc",
            "Format": "Text",
            "Mandatory (Y/N)": "Y",
            "Personal Data (Y/N)": "N",
        }
    ]


def test_sample_value_and_labels_never_reach_the_output(tmp_path):
    path = _roster_workbook(tmp_path / "wb.xlsx", lambda config: _row(table=config.dataset, personal="Y"))

    written = kanya_xlsx.convert_workbook(path, tmp_path / "out")
    body = "".join(p.read_text(encoding="utf-8") for p in written.values())

    assert "9999999999" not in body
    assert "hindi" not in body
    assert "english" not in body
    assert "Availability" not in body
    assert "Sample Value" not in body
    assert "Notes" not in body


def test_rows_without_a_field_name_are_skipped(tmp_path):
    path = _workbook(tmp_path / "wb.xlsx", {"t": [FULL_HEADER, _row(field="  "), _row(field="col_b")]})

    records = kanya_xlsx.read_sheet(path, "t")

    assert [r["Dataset Field"] for r in records] == ["col_b"]


def test_rows_without_a_dataset_name_are_skipped(tmp_path):
    path = _workbook(tmp_path / "wb.xlsx", {"t": [FULL_HEADER, _row(table=""), _row(table="t2")]})

    records = kanya_xlsx.read_sheet(path, "t")

    assert [r["Dataset Name"] for r in records] == ["t2"]


def test_cell_values_are_stripped(tmp_path):
    path = _workbook(tmp_path / "wb.xlsx", {"t": [FULL_HEADER, _row(field="  col_a  ")]})

    assert kanya_xlsx.read_sheet(path, "t")[0]["Dataset Field"] == "col_a"


def test_convert_workbook_writes_one_csv_per_roster_entry(tmp_path):
    sheets = {config.sheet: [FULL_HEADER, _row(table=f"{config.dataset}_t")] for config in kanya_xlsx.SHEETS}
    path = _workbook(tmp_path / "wb.xlsx", sheets)

    written = kanya_xlsx.convert_workbook(path, tmp_path / "out")

    assert set(written) == {config.dataset for config in kanya_xlsx.SHEETS}
    for config in kanya_xlsx.SHEETS:
        assert written[config.dataset].name == f"{config.dataset}.csv"


def test_converted_csvs_parse_into_the_expected_tables(tmp_path):
    sheets = {config.sheet: [FULL_HEADER, _row(table="t_one"), _row(table="t_two")] for config in kanya_xlsx.SHEETS}
    path = _workbook(tmp_path / "wb.xlsx", sheets)

    written = kanya_xlsx.convert_workbook(path, tmp_path / "out")

    for dataset, csv_path in written.items():
        tables = parse_field_dictionary(str(csv_path))
        assert set(tables) == {"t_one", "t_two"}, dataset


def test_personal_data_survives_conversion_into_a_pii_tag(tmp_path):
    path = _roster_workbook(
        tmp_path / "wb.xlsx",
        lambda config: _row(table=config.dataset, field="aadhaar_no", personal="Y"),
    )

    written = kanya_xlsx.convert_workbook(path, tmp_path / "out")

    for config in kanya_xlsx.SHEETS:
        table = parse_field_dictionary(str(written[config.dataset]))[config.dataset]
        assert table["business_metadata"]["aadhaar_no"]["tag"] == "PII", config.sheet


def test_cmsvy_sample_is_the_converted_cmsvy_sheet(tmp_path):
    sheets = {config.sheet: [FULL_HEADER, _row(table="t")] for config in kanya_xlsx.SHEETS}
    path = _workbook(tmp_path / "wb.xlsx", sheets)

    written = kanya_xlsx.convert_workbook(path, tmp_path / "out")
    sample = kanya_xlsx.write_cmsvy_sample(path, tmp_path / "samples" / "kanya_sumangla_field_dictionary.csv")

    assert sample.read_bytes() == written[CMSVY.dataset].read_bytes()


def test_missing_sheet_raises(tmp_path):
    path = _workbook(tmp_path / "wb.xlsx", {"other": [FULL_HEADER, _row()]})

    with pytest.raises(ValueError, match="No sheet"):
        kanya_xlsx.read_sheet(path, kanya_xlsx.SHEETS[0].sheet)


def test_sheet_missing_a_required_column_raises(tmp_path):
    path = _workbook(tmp_path / "wb.xlsx", {"t": [["Dataset Name", "Dataset Field"], ["t1", "col"]]})

    with pytest.raises(ValueError, match="missing column"):
        kanya_xlsx.read_sheet(path, "t")


def test_empty_sheet_raises(tmp_path):
    path = _workbook(tmp_path / "wb.xlsx", {"t": []})

    with pytest.raises(ValueError, match="empty"):
        kanya_xlsx.read_sheet(path, "t")


def test_read_note_sheet_returns_scheme_department_and_identifiers(tmp_path):
    note = [
        [None, None, "Scheme/Schema", "Deptt.", "Identifiers"],
        [None, None, "UDISE+", "Basic Education + SSA", "PEN"],
        [None, None, None, None, None],
    ]
    path = _workbook(tmp_path / "wb.xlsx", {"t": [FULL_HEADER, _row()]}, note_rows=note)

    assert kanya_xlsx.read_note_sheet(path) == {
        "UDISE+": {"department": "Basic Education + SSA", "identifiers": "PEN"}
    }


@REAL
def test_every_note_sheet_scheme_is_covered_by_the_roster():
    roster = kanya_xlsx.read_note_sheet(WORKBOOK)
    schemes = {config.scheme for config in kanya_xlsx.SHEETS}

    assert set(roster) <= schemes


@REAL
def test_note_sheet_departments_match_the_roster():
    roster = kanya_xlsx.read_note_sheet(WORKBOOK)
    by_scheme = {config.scheme: config for config in kanya_xlsx.SHEETS}

    assert "Revenue" in roster["Income Certificate"]["department"]
    assert by_scheme["Income Certificate"].department_id == "revenue_department"
    assert roster["PM Matru Vandana Yojana"]["department"] == "WCD"
    assert by_scheme["PM Matru Vandana Yojana"].department_id == "women_and_child_development_department"
    assert roster["UDISE+"]["department"] == "Basic Education + SSA"
    assert by_scheme["UDISE+"].department_id == "basic_education_department"
    assert roster["Immunisation"]["department"] == "Health"
    assert by_scheme["Immunisation"].department_id == "health_department"
    assert roster["Samuhik Vivah"]["department"] == "Social Welfare"
    assert by_scheme["Samuhik Vivah"].department_id == "social_welfare_department"


@REAL
def test_real_workbook_converts_every_row_and_the_counts_agree(tmp_path):
    workbook = openpyxl.load_workbook(str(WORKBOOK), read_only=True, data_only=True)
    try:
        expected: dict[str, set[str]] = {}
        expected_columns: dict[str, int] = {}
        for config in kanya_xlsx.SHEETS:
            rows = workbook[config.sheet].iter_rows(values_only=True)
            index = kanya_xlsx._header_index(next(rows))
            names = set()
            count = 0
            for row in rows:
                if kanya_xlsx._cell(row, index["Dataset Name"]) and kanya_xlsx._cell(row, index["Dataset Field"]):
                    names.add(kanya_xlsx._cell(row, index["Dataset Name"]))
                    count += 1
            expected[config.dataset] = names
            expected_columns[config.dataset] = count
    finally:
        workbook.close()

    written = kanya_xlsx.convert_workbook(WORKBOOK, tmp_path)

    total_columns = 0
    notes = 0
    for config in kanya_xlsx.SHEETS:
        tables = parse_field_dictionary(str(written[config.dataset]))
        assert set(tables) == expected[config.dataset], config.sheet
        total_columns += sum(len(t["columns"]) for t in tables.values())
        notes += sum(
            "format_note" in meta for t in tables.values() for meta in t["business_metadata"].values()
        )

    assert total_columns == sum(expected_columns.values())
    assert notes <= 5, "unexpectedly many unrecognised Format values"


@REAL
def test_real_cmsvy_sample_parses_into_seven_tables(tmp_path):
    sample = kanya_xlsx.write_cmsvy_sample(WORKBOOK, tmp_path / "kanya_sumangla_field_dictionary.csv")

    tables = parse_field_dictionary(str(sample))

    assert set(tables) == {
        "cmsvy_application",
        "cmsvy_bride_details",
        "cmsvy_groom_details",
        "cmsvy_eligibility",
        "cmsvy_bank_details",
        "cmsvy_uploaded_docs",
        "cmsvy_workflow",
    }
    assert len(tables["cmsvy_bride_details"]["columns"]) == 7
