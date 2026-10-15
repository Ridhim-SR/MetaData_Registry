from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

from src.schema_registry.parsers.field_dictionary_parser import parse_field_dictionary
from src.schema_registry.parsers.dept.RuralDevelopment import mgnrega_codebook as codebook

REAL_DIR = Path(__file__).resolve().parents[2] / "Datasets" / "Manreaga"
REAL = pytest.mark.skipif(not REAL_DIR.is_dir(), reason=f"{REAL_DIR} is gitignored and not present")

CODEBOOK_HEADER = ["Variable Name", "Variable Description", "Variable Type", "Unit Of Measurement", "Unit Type"]


def _workbook(path, variables, metadata=None, additional=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = codebook.CODEBOOK_SHEET
    ws.append(["Dataset Variables & Formulas Used"])
    ws.append(CODEBOOK_HEADER)
    for row in variables:
        ws.append(row)

    meta = wb.create_sheet(codebook.METADATA_SHEET)
    meta.append(["Metadata Information"])
    for key, value in (metadata or {"Dataset Name": "MGNREGA (Mahatma Gandhi National Rural Employment Guarantee Act)"}).items():
        meta.append([key, value])

    add = wb.create_sheet(codebook.ADDITIONAL_SHEET)
    add.append(["Additional Information"])
    for key, value in (additional or {"Years Covered": "2014-2015 to 2025-2026"}).items():
        add.append([key, value])

    wb.save(str(path))
    return path


def _variable(name="year", description="Year", vtype="text", unit="", unit_type="Categorical"):
    return [name, description, vtype, unit, unit_type]


def test_tables_have_unique_slugs_and_files():
    tables = [config.table for config in codebook.TABLES]
    files = [config.file for config in codebook.TABLES]
    assert len(tables) == len(set(tables)) == 4
    assert len(files) == len(set(files))
    assert all(table == table.lower() for table in tables)
    assert all(config.file.endswith(".xlsx") for config in codebook.TABLES)


def test_every_table_belongs_to_the_mgnrega_dataset():
    assert codebook.DATASET == "mgnrega"
    assert codebook.DEPARTMENT_ID == "rural_development_department"
    for config in codebook.TABLES:
        assert config.resource


def test_read_codebook_maps_variables_to_dictionary_rows(tmp_path):
    path = _workbook(
        tmp_path / "category_wise_codebook.xlsx",
        [
            _variable(),
            _variable("applied_jobcards", "Applied Job Cards", "integer", "In Lakh", "Count"),
            _variable("expenditure", "Spend", "numeric", "Rupees In Lakh", "Number"),
        ],
    )

    records = codebook.read_codebook(path, "category_wise_workers")

    assert list(records[0].keys()) == codebook.OUTPUT_HEADERS
    assert records[0] == {
        "Dataset Name": "category_wise_workers",
        "Dataset Field": "year",
        "Data Description": "Year",
        "Format": "text",
        "Mandatory (Y/N)": "",
        "Personal Data (Y/N)": "",
    }
    assert records[1]["Data Description"] == "Applied Job Cards (In Lakh)"
    assert records[1]["Format"] == "integer"
    assert records[2]["Data Description"] == "Spend (Rupees In Lakh)"
    assert records[2]["Format"] == "numeric"


def test_read_codebook_rejects_an_unknown_variable_type(tmp_path):
    path = _workbook(tmp_path / "c.xlsx", [_variable("x", "X", "double precision")])

    with pytest.raises(ValueError, match="unknown Variable Type 'double precision'"):
        codebook.read_codebook(path, "t")


def test_read_codebook_rejects_a_missing_codebook_sheet(tmp_path):
    path = _workbook(tmp_path / "c.xlsx", [_variable()])
    wb = openpyxl.load_workbook(str(path))
    del wb[codebook.CODEBOOK_SHEET]
    wb.save(str(path))

    with pytest.raises(ValueError, match="No 'codebook' sheet"):
        codebook.read_codebook(path, "t")


def test_read_codebook_rejects_another_datasets_metadata(tmp_path):
    path = _workbook(
        tmp_path / "c.xlsx",
        [_variable()],
        metadata={"Dataset Name": "Some Other Scheme"},
    )

    with pytest.raises(ValueError, match="expected it to start with 'MGNREGA'"):
        codebook.read_codebook(path, "t")


def test_convert_all_writes_one_csv_per_codebook(tmp_path):
    src = tmp_path / "Manreaga"
    src.mkdir()
    for config in codebook.TABLES:
        _workbook(src / config.file, [_variable("gp_code", "Gram Panchayat Code"), _variable("mandays", "Persondays", "integer", "Number", "Count")])

    written = codebook.convert_all(src, tmp_path / "out")

    assert set(written) == {config.table for config in codebook.TABLES}
    for table, path in written.items():
        assert path == tmp_path / "out" / f"{table}.csv"
        parsed = parse_field_dictionary(str(path))
        assert list(parsed) == [table]
        columns = parsed[table]["columns"]
        assert [c["name"] for c in columns] == ["gp_code", "mandays"]
        assert [c["data_type"] for c in columns] == ["character varying", "integer"]
        assert all(c["nullable"] for c in columns)


def test_convert_all_fails_loudly_when_a_codebook_is_missing(tmp_path):
    src = tmp_path / "Manreaga"
    src.mkdir()
    for config in codebook.TABLES[1:]:
        _workbook(src / config.file, [_variable()])

    with pytest.raises(FileNotFoundError, match=codebook.TABLES[0].file):
        codebook.convert_all(src, tmp_path / "out")


def test_metadata_and_additional_info_are_read(tmp_path):
    path = _workbook(
        tmp_path / "c.xlsx",
        [_variable()],
        metadata={"Dataset Name": "MGNREGA", "Frequency": "Yearly", "Source Name": "Ministry of Rural Development"},
        additional={"Years Covered": "2020-2021 to 2025-2026", "Number Of District(S)": "742"},
    )

    assert codebook.read_metadata(path) == {
        "Dataset Name": "MGNREGA",
        "Frequency": "Yearly",
        "Source Name": "Ministry of Rural Development",
    }
    assert codebook.read_additional_info(path) == {
        "Years Covered": "2020-2021 to 2025-2026",
        "Number Of District(S)": "742",
    }


def test_unknown_workbook_name_is_refused(tmp_path):
    with pytest.raises(ValueError, match="not a known MGNREGA codebook"):
        codebook._config_for(tmp_path / "random.xlsx")


def test_write_combined_dictionary_makes_one_multi_table_csv(tmp_path):
    src = tmp_path / "Manreaga"
    src.mkdir()
    for i, config in enumerate(codebook.TABLES):
        _workbook(src / config.file, [_variable(f"col_{i}", f"Column {i}", "integer", "Number", "Count")])

    combined = codebook.write_combined_dictionary(src, tmp_path / "mgnrega_field_dictionary.csv")

    parsed = parse_field_dictionary(str(combined))
    assert set(parsed) == {config.table for config in codebook.TABLES}
    for i, config in enumerate(codebook.TABLES):
        assert [c["name"] for c in parsed[config.table]["columns"]] == [f"col_{i}"]


def test_combined_flag_needs_the_folder(tmp_path):
    src = tmp_path / "one.xlsx"
    _workbook(src, [_variable()])

    with pytest.raises(SystemExit):
        codebook.main(["--input", str(src), "--out-dir", str(tmp_path / "out"), "--combined", str(tmp_path / "c.csv")])


@REAL
def test_real_codebooks_convert_and_round_trip(tmp_path):
    written = codebook.convert_all(REAL_DIR, tmp_path)

    expected_counts = {
        "category_wise_workers": 28,
        "employment_generated": 29,
        "women_joint_accounts": 13,
        "work_structure": 14,
    }
    assert {table: len(parse_field_dictionary(str(path))[table]["columns"]) for table, path in written.items()} == expected_counts

    work_structure = parse_field_dictionary(str(written["work_structure"]))["work_structure"]
    by_name = {c["name"]: c for c in work_structure["columns"]}
    assert by_name["expenditure_lakhs"]["data_type"] == "numeric"
    assert by_name["mandays"]["data_type"] == "integer"
    assert by_name["work_type"]["data_type"] == "character varying"
    assert work_structure["business_metadata"]["expenditure_lakhs"] == {
        "business_description": "Expenditure on works in the year (Rupees In Lakh)",
        "tag": "",
    }
