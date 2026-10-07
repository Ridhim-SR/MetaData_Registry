import pytest

import os

import pytest

from src.schema_registry.parsers.field_dictionary_parser import parse_field_dictionary_text, parse_format


def parse_field_dictionary(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return parse_field_dictionary_text(f.read(), label=str(path))


def test_parse_format_numeric():
    assert parse_format("Numeric (12 Digits)") == ("numeric", 12)


def test_parse_format_numeric_no_length():
    assert parse_format("Numeric (Currency in Rs.)") == ("numeric", None)


def test_parse_format_date():
    assert parse_format("Date (DD/MM/YYYY)") == ("date", None)


def test_parse_format_text_variants_map_to_varchar():
    assert parse_format("Text (Alphanumeric)")[0] == "character varying"
    assert parse_format("Text / Dropdown")[0] == "character varying"
    assert parse_format("Option: Bride, Guardian/Parent")[0] == "character varying"
    assert parse_format("Alphanumeric (11 Characters)") == ("character varying", 11)


def test_parse_format_image_and_file_map_to_varchar():
    assert parse_format("Image (JPG/PNG, 20-50 KB)")[0] == "character varying"
    assert parse_format("File (PDF, 50-100 KB)")[0] == "character varying"


def test_parse_format_unrecognized_raises():
    with pytest.raises(ValueError, match="Unrecognized Format value"):
        parse_format("Blob")


def _write_dictionary(tmp_path, rows):
    path = tmp_path / "field_dictionary.csv"
    header = "Dataset Name,Dataset Field,Data Description,Format,Mandatory (Y/N)"
    lines = [header] + [",".join(row) for row in rows]
    path.write_text("\n".join(lines))
    return str(path)


def test_groups_rows_by_dataset_name(tmp_path):
    source = _write_dictionary(
        tmp_path,
        [
            ("t1", "col_a", "First column", "Text", "Y"),
            ("t1", "col_b", "Second column", "Numeric (10 Digits)", "N"),
            ("t2", "col_c", "Other table's column", "Date (DD/MM/YYYY)", "Y"),
        ],
    )

    tables = parse_field_dictionary(source)

    assert set(tables.keys()) == {"t1", "t2"}
    assert [c["name"] for c in tables["t1"]["columns"]] == ["col_a", "col_b"]
    assert [c["name"] for c in tables["t2"]["columns"]] == ["col_c"]


def test_mandatory_y_means_not_nullable(tmp_path):
    source = _write_dictionary(
        tmp_path,
        [
            ("t1", "required_col", "desc", "Text", "Y"),
            ("t1", "optional_col", "desc", "Text", "N"),
        ],
    )

    columns = parse_field_dictionary(source)["t1"]["columns"]

    assert columns[0]["nullable"] is False
    assert columns[1]["nullable"] is True


def test_data_description_becomes_business_metadata(tmp_path):
    source = _write_dictionary(tmp_path, [("t1", "col_a", "What this field means", "Text", "Y")])

    business_metadata = parse_field_dictionary(source)["t1"]["business_metadata"]

    assert business_metadata["col_a"]["business_description"] == "What this field means"


@pytest.mark.skipif(not os.path.exists("samples/kanya_sumangla_field_dictionary.csv"),
                    reason="real sample file is gitignored; not on this machine")
def test_real_sample_file_parses_into_seven_tables():
    tables = parse_field_dictionary("samples/kanya_sumangla_field_dictionary.csv")

    assert set(tables.keys()) == {
        "cmsvy_application",
        "cmsvy_bride_details",
        "cmsvy_groom_details",
        "cmsvy_eligibility",
        "cmsvy_bank_details",
        "cmsvy_uploaded_docs",
        "cmsvy_workflow",
    }
    assert len(tables["cmsvy_bride_details"]["columns"]) == 7
