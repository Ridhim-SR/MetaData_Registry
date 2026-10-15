import csv
from pathlib import Path

import pytest

from src.schema_registry.parsers.field_dictionary_parser import (
    parse_field_dictionary,
    parse_format,
    parse_format_full,
)

# Real CMSVY dictionary, gitignored like the other sample dumps (root
# .gitignore: samples/) -- skipped where it isn't present so the suite stays
# green in a clean checkout.
SAMPLE = Path("samples/kanya_sumangla_field_dictionary.csv")


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


@pytest.mark.skipif(not SAMPLE.exists(), reason=f"{SAMPLE} is gitignored and not present")
def test_real_sample_file_parses_into_seven_tables():
    tables = parse_field_dictionary(str(SAMPLE))

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


BASE_HEADERS = ["Dataset Name", "Dataset Field", "Data Description", "Format", "Mandatory (Y/N)"]


def _write_csv(tmp_path, headers, rows, name="field_dictionary.csv", encoding="utf-8"):
    path = tmp_path / name
    with path.open("w", newline="", encoding=encoding) as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return str(path)


def _single(tmp_path, field, description, fmt, mandatory="Y", table="t1"):
    return _write_csv(tmp_path, BASE_HEADERS, [[table, field, description, fmt, mandatory]])


# --- parse_format: existing rules under edge cases ---------------------


def test_numeric_lowercase_still_maps():
    assert parse_format("numeric (12 digits)") == ("numeric", 12)


def test_numeric_bare_has_no_length():
    assert parse_format("Numeric") == ("numeric", None)


def test_numeric_parenthesised_count_without_unit_takes_length():
    assert parse_format("Numeric (10)") == ("numeric", 10)


def test_date_bare_has_no_length():
    assert parse_format("date") == ("date", None)


def test_date_is_case_insensitive_and_ignores_its_own_mask():
    assert parse_format("DATE (DD-MM-YYYY)") == ("date", None)


def test_format_text_is_stripped_before_matching():
    assert parse_format("   Text (Alphanumeric)   ") == ("character varying", None)


def test_option_with_colon_and_comma_maps_to_varchar():
    assert parse_format("Option: Bride, Guardian/Parent")[0] == "character varying"


def test_image_size_hint_does_not_become_a_length():
    assert parse_format("Image (JPG/PNG, 20-50 KB)") == ("character varying", None)


def test_file_size_hint_does_not_become_a_length():
    assert parse_format("File (PDF, 50-100 KB)") == ("character varying", None)


def test_unknown_format_still_points_at_the_rule_table():
    with pytest.raises(ValueError, match="FORMAT_TYPE_RULES"):
        parse_format("Checkbox")


def test_rule_must_be_anchored_at_the_start_of_the_text():
    with pytest.raises(ValueError, match="Unrecognized Format value"):
        parse_format("Is Boolean (True/False)")


# --- parse_format: department-supplied DB-ish types --------------------


def test_varchar_with_length():
    assert parse_format("VARCHAR(30)") == ("character varying", 30)


def test_varchar_mixed_case_with_length():
    assert parse_format("Varchar(50)") == ("character varying", 50)


def test_varchar_bare_has_no_length():
    assert parse_format("Varchar") == ("character varying", None)


def test_varchar_with_space_before_paren():
    assert parse_format("VARCHAR (255)") == ("character varying", 255)


def test_string_wrapping_varchar_keeps_varchar_meaning():
    assert parse_format("String (Varchar)") == ("character varying", None)


def test_string_with_character_count():
    assert parse_format("String (20-character)") == ("character varying", 20)


def test_string_with_digit_count():
    assert parse_format("String (12-digit)") == ("character varying", 12)


def test_char_with_length_is_fixed_width_character():
    assert parse_format("CHAR(1)") == ("character", 1)


def test_character_varying_literal_does_not_collapse_to_char():
    assert parse_format("character varying(100)") == ("character varying", 100)


def test_integer_variants():
    assert parse_format("INTEGER") == ("integer", None)
    assert parse_format("Integer") == ("integer", None)


def test_bigint_maps_to_bigint_not_integer():
    assert parse_format("BIGINT") == ("bigint", None)


def test_boolean_variants():
    assert parse_format("Boolean (True/False)") == ("boolean", None)
    assert parse_format("BOOLEAN") == ("boolean", None)


def test_year_maps_to_integer():
    assert parse_format("Year") == ("integer", None)


def test_decimal_bare_maps_to_numeric():
    assert parse_format("Decimal") == ("numeric", None)


# --- parse_format_full: precision and scale ----------------------------


def test_decimal_with_scale():
    spec = parse_format_full("Decimal (18,2)")
    assert (spec.data_type, spec.length, spec.scale) == ("numeric", 18, 2)


def test_decimal_uppercase_with_scale():
    spec = parse_format_full("DECIMAL(10,2)")
    assert (spec.data_type, spec.length, spec.scale) == ("numeric", 10, 2)


def test_numeric_with_scale_keeps_scale():
    spec = parse_format_full("numeric(10,2)")
    assert (spec.data_type, spec.length, spec.scale) == ("numeric", 10, 2)


def test_scale_is_none_for_plain_numeric():
    assert parse_format_full("Numeric (12 Digits)").scale is None


def test_scale_is_none_for_varchar():
    assert parse_format_full("VARCHAR(30)").scale is None


def test_parse_format_stays_a_two_tuple():
    assert parse_format("Decimal (18,2)") == ("numeric", 18)


def test_parse_format_agrees_with_parse_format_full():
    for text in ["Text", "Numeric (12 Digits)", "Date (DD/MM/YYYY)", "VARCHAR(30)", "Enum('A','BB')"]:
        spec = parse_format_full(text)
        assert parse_format(text) == (spec.data_type, spec.length)


def test_formatspec_unpacks_into_three_values():
    data_type, length, scale = parse_format_full("Decimal (18,2)")
    assert (data_type, length, scale) == ("numeric", 18, 2)


def test_bad_format_raises_from_parse_format_full_too():
    with pytest.raises(ValueError, match="Unrecognized Format value"):
        parse_format_full("Blob")


# --- parse_format: enum / dropdown free text ---------------------------


def test_enum_bare_is_varchar():
    assert parse_format("Enum") == ("character varying", None)


def test_enum_literals_set_length_to_the_longest_value():
    assert parse_format("ENUM('Rural','Urban')") == ("character varying", 5)


def test_enum_literals_with_spaces_set_length_to_the_longest_value():
    assert parse_format("Enum('Yes','Not Applicable')") == ("character varying", 14)


def test_dropdown_bare_is_varchar():
    assert parse_format("Dropdown") == ("character varying", None)


def test_dropdown_with_yes_no_choices_has_no_length():
    assert parse_format("Dropdown (Yes/No)") == ("character varying", None)


def test_dropdown_with_character_count():
    assert parse_format("Dropdown (20)") == ("character varying", 20)


def test_dropdown_with_enum_is_varchar():
    assert parse_format("Dropdown / Enum")[0] == "character varying"


def test_dropdown_with_string_is_varchar():
    assert parse_format("Dropdown / String")[0] == "character varying"


def test_enum_with_varchar_is_varchar():
    assert parse_format("Enum / Varchar")[0] == "character varying"


# --- parse_format: date-style pattern codes ----------------------------


def test_pattern_code_wryydd_is_full_width_varchar():
    code = "WRYYDDnnnnnnn"
    assert parse_format(code) == ("character varying", len(code))


def test_pattern_code_wuyydd_with_trailing_flag_is_full_width_varchar():
    code = "WUYYDDnnnnnnnN"
    assert parse_format(code) == ("character varying", len(code))


def test_pattern_code_yyddt_is_full_width_varchar():
    code = "YYDDTnnnnnnn"
    assert parse_format(code) == ("character varying", len(code))


def test_pattern_code_does_not_swallow_ordinary_words():
    with pytest.raises(ValueError, match="Unrecognized Format value"):
        parse_format("Monetary")


# --- parse_field_dictionary: structure ---------------------------------


def test_rows_group_in_file_order_across_three_tables(tmp_path):
    source = _write_csv(
        tmp_path,
        BASE_HEADERS,
        [
            ("a", "one", "d", "Text", "Y"),
            ("b", "two", "d", "Text", "Y"),
            ("a", "three", "d", "Text", "Y"),
            ("c", "four", "d", "Text", "Y"),
        ],
    )
    tables = parse_field_dictionary(source)
    assert list(tables.keys()) == ["a", "b", "c"]
    assert [c["name"] for c in tables["a"]["columns"]] == ["one", "three"]
    assert [c["name"] for c in tables["b"]["columns"]] == ["two"]
    assert [c["name"] for c in tables["c"]["columns"]] == ["four"]


def test_utf8_bom_on_the_header_is_tolerated(tmp_path):
    source = _write_csv(tmp_path, BASE_HEADERS, [("t1", "col", "d", "Text", "Y")], encoding="utf-8-sig")
    assert [c["name"] for c in parse_field_dictionary(source)["t1"]["columns"]] == ["col"]


def test_crlf_line_endings_are_tolerated(tmp_path):
    path = tmp_path / "field_dictionary.csv"
    path.write_bytes(b"Dataset Name,Dataset Field,Data Description,Format,Mandatory (Y/N)\r\nt1,col,d,Text,Y\r\n")
    assert [c["name"] for c in parse_field_dictionary(str(path))["t1"]["columns"]] == ["col"]


def test_extra_workbook_columns_are_ignored(tmp_path):
    headers = BASE_HEADERS + ["Field Label Hindi", "Sample Value", "Notes"]
    source = _write_csv(
        tmp_path,
        headers,
        [("t1", "col", "d", "Text", "Y", "hindi label", "SAMPLE-1", "n")],
    )
    assert [c["name"] for c in parse_field_dictionary(source)["t1"]["columns"]] == ["col"]


def test_description_containing_a_comma_survives(tmp_path):
    source = _single(tmp_path, "col", "District name, as on 1 April", "Text")
    assert parse_field_dictionary(source)["t1"]["business_metadata"]["col"]["business_description"] == (
        "District name, as on 1 April"
    )


def test_description_containing_quotes_survives(tmp_path):
    source = _single(tmp_path, "col", 'He said "yes" then left', "Text")
    assert parse_field_dictionary(source)["t1"]["business_metadata"]["col"]["business_description"] == (
        'He said "yes" then left'
    )


def test_empty_description_becomes_empty_string(tmp_path):
    source = _single(tmp_path, "col", "", "Text")
    assert parse_field_dictionary(source)["t1"]["business_metadata"]["col"]["business_description"] == ""


def test_missing_description_column_is_tolerated(tmp_path):
    source = _write_csv(
        tmp_path,
        ["Dataset Name", "Dataset Field", "Format", "Mandatory (Y/N)"],
        [("t1", "col", "Text", "Y")],
    )
    assert parse_field_dictionary(source)["t1"]["business_metadata"]["col"]["business_description"] == ""


def test_missing_mandatory_column_treats_every_field_as_nullable(tmp_path):
    source = _write_csv(
        tmp_path,
        ["Dataset Name", "Dataset Field", "Data Description", "Format"],
        [("t1", "col", "d", "Text")],
    )
    assert parse_field_dictionary(source)["t1"]["columns"][0]["nullable"] is True


def test_dataset_name_is_stripped_before_grouping(tmp_path):
    source = _write_csv(tmp_path, BASE_HEADERS, [("  t1  ", "col", "d", "Text", "Y")])
    assert list(parse_field_dictionary(source).keys()) == ["t1"]


def test_rows_without_a_dataset_name_are_skipped(tmp_path):
    source = _write_csv(tmp_path, BASE_HEADERS, [("", "col", "d", "Text", "Y"), ("t1", "keep", "d", "Text", "Y")])
    tables = parse_field_dictionary(source)
    assert list(tables.keys()) == ["t1"]


def test_rows_without_a_field_name_are_skipped(tmp_path):
    source = _write_csv(tmp_path, BASE_HEADERS, [("t1", "  ", "d", "Text", "Y"), ("t1", "keep", "d", "Text", "Y")])
    assert [c["name"] for c in parse_field_dictionary(source)["t1"]["columns"]] == ["keep"]


def test_field_name_is_stripped_but_keeps_its_original_case(tmp_path):
    source = _single(tmp_path, "  Application_No  ", "d", "Text")
    table = parse_field_dictionary(source)["t1"]
    assert table["columns"][0]["name"] == "Application_No"
    assert "Application_No" in table["business_metadata"]


def test_repeated_field_name_in_one_table_keeps_both_columns(tmp_path):
    source = _write_csv(
        tmp_path,
        BASE_HEADERS,
        [("t1", "col", "first", "Text", "Y"), ("t1", "col", "second", "Text", "Y")],
    )
    table = parse_field_dictionary(source)["t1"]
    assert len(table["columns"]) == 2
    assert table["business_metadata"]["col"]["business_description"] == "second"


def test_default_is_always_none_because_dictionaries_carry_no_default(tmp_path):
    source = _single(tmp_path, "col", "d", "Text")
    assert parse_field_dictionary(source)["t1"]["columns"][0]["default"] is None


def test_scale_is_none_for_a_text_field(tmp_path):
    source = _single(tmp_path, "col", "d", "Text (Alphanumeric)")
    assert parse_field_dictionary(source)["t1"]["columns"][0]["scale"] is None


def test_scale_is_carried_for_a_decimal_field(tmp_path):
    source = _single(tmp_path, "amt", "d", "Decimal (18,2)")
    column = parse_field_dictionary(source)["t1"]["columns"][0]
    assert (column["data_type"], column["length"], column["scale"]) == ("numeric", 18, 2)


def test_dataset_names_differing_only_by_case_stay_separate_tables(tmp_path):
    source = _write_csv(tmp_path, BASE_HEADERS, [("t1", "col", "d", "Text", "Y"), ("T1", "col2", "d", "Text", "Y")])
    tables = parse_field_dictionary(source)
    assert sorted(tables.keys()) == ["T1", "t1"]


# --- parse_field_dictionary: mandatory / nullable edge cases ------------


def test_mandatory_y_rural_is_not_nullable(tmp_path):
    source = _single(tmp_path, "col", "d", "Text", mandatory="Y (Rural)")
    assert parse_field_dictionary(source)["t1"]["columns"][0]["nullable"] is False


def test_mandatory_y_urban_is_not_nullable(tmp_path):
    source = _single(tmp_path, "col", "d", "Text", mandatory="Y (Urban)")
    assert parse_field_dictionary(source)["t1"]["columns"][0]["nullable"] is False


def test_lowercase_y_is_not_nullable(tmp_path):
    source = _single(tmp_path, "col", "d", "Text", mandatory="y")
    assert parse_field_dictionary(source)["t1"]["columns"][0]["nullable"] is False


def test_y_with_padding_is_not_nullable(tmp_path):
    source = _single(tmp_path, "col", "d", "Text", mandatory="  Y  ")
    assert parse_field_dictionary(source)["t1"]["columns"][0]["nullable"] is False


def test_n_with_padding_is_nullable(tmp_path):
    source = _single(tmp_path, "col", "d", "Text", mandatory=" N ")
    assert parse_field_dictionary(source)["t1"]["columns"][0]["nullable"] is True


def test_blank_mandatory_is_nullable(tmp_path):
    source = _single(tmp_path, "col", "d", "Text", mandatory="")
    assert parse_field_dictionary(source)["t1"]["columns"][0]["nullable"] is True


# --- parse_field_dictionary: Personal Data (Y/N) becomes the tag -------


def _with_personal(tmp_path, personal):
    headers = BASE_HEADERS + ["Personal Data (Y/N)"]
    return _write_csv(tmp_path, headers, [("t1", "col", "d", "Text", "Y", personal)])


def test_personal_data_yes_becomes_pii_tag(tmp_path):
    meta = parse_field_dictionary(_with_personal(tmp_path, "Y"))["t1"]["business_metadata"]["col"]
    assert meta["tag"] == "PII"


def test_personal_data_lowercase_yes_becomes_pii_tag(tmp_path):
    meta = parse_field_dictionary(_with_personal(tmp_path, "y"))["t1"]["business_metadata"]["col"]
    assert meta["tag"] == "PII"


def test_personal_data_no_leaves_the_tag_empty(tmp_path):
    meta = parse_field_dictionary(_with_personal(tmp_path, "N"))["t1"]["business_metadata"]["col"]
    assert meta["tag"] == ""


def test_blank_personal_data_leaves_the_tag_empty(tmp_path):
    meta = parse_field_dictionary(_with_personal(tmp_path, ""))["t1"]["business_metadata"]["col"]
    assert meta["tag"] == ""


def test_absent_personal_data_column_leaves_the_tag_empty(tmp_path):
    meta = parse_field_dictionary(_single(tmp_path, "col", "d", "Text"))["t1"]["business_metadata"]["col"]
    assert meta["tag"] == ""


# --- parse_field_dictionary: unrecognised Format inside a real file ----


def test_unrecognised_format_does_not_kill_the_whole_file(tmp_path):
    source = _write_csv(
        tmp_path,
        BASE_HEADERS,
        [
            ("t1", "good", "d", "Text", "Y"),
            ("t1", "weird", "d", "[Aadhaar Redacted]", "Y"),
            ("t1", "also_good", "d", "Numeric (12 Digits)", "Y"),
        ],
    )
    table = parse_field_dictionary(source)["t1"]
    assert [c["name"] for c in table["columns"]] == ["good", "weird", "also_good"]


def test_unrecognised_format_falls_back_to_varchar_and_is_recorded(tmp_path):
    source = _single(tmp_path, "weird", "d", "[Aadhaar Redacted]")
    table = parse_field_dictionary(source)["t1"]
    assert table["columns"][0]["data_type"] == "character varying"
    assert table["columns"][0]["length"] is None
    assert "[Aadhaar Redacted]" in table["business_metadata"]["weird"]["format_note"]


def test_unrecognised_format_neighbours_keep_their_real_type(tmp_path):
    source = _single(tmp_path, "amt", "d", "Decimal")
    column = parse_field_dictionary(source)["t1"]["columns"][0]
    assert (column["data_type"], column["length"], column["scale"]) == ("numeric", None, None)


def test_recognised_format_records_no_format_note(tmp_path):
    source = _single(tmp_path, "col", "d", "Text")
    assert "format_note" not in parse_field_dictionary(source)["t1"]["business_metadata"]["col"]


def test_unrecognised_format_row_still_gets_its_pii_tag(tmp_path):
    headers = BASE_HEADERS + ["Personal Data (Y/N)"]
    source = _write_csv(tmp_path, headers, [("t1", "weird", "d", "Blob", "Y", "Y")])
    meta = parse_field_dictionary(source)["t1"]["business_metadata"]["weird"]
    assert meta["tag"] == "PII"
    assert "format_note" in meta
