from pathlib import Path

import pytest

from src.schema_registry.parsers import agriculture_parser
from src.schema_registry.parsers.csv_schema_parser import parse_csv_text
from src.schema_registry.pipeline import parse_source

# The real agriculture submission (one CSV, several tables side by side) is
# gitignored (root .gitignore: *.csv), so it only exists on machines where
# someone dropped it locally -- the suite has to be green either way.
SAMPLE = Path("../Datasets/Distribution_Records_Dataset-12_13_52.csv")
PREPROCESSED = Path("source/distribution_records/crop_sales.csv")

MULTI_TABLE = """Table Name,crop_sales,,,,Table Name,current_booking,,
,,,,
column_name,data_type,,,,column_name,data_type,,
id,character varying,,,,id,character varying
status,integer,,,,status,integer
"""


def test_multi_table_submission_returns_only_the_requested_table():
    columns = agriculture_parser.parse_table(MULTI_TABLE, "current_booking")

    assert [c["name"] for c in columns] == ["id", "status"]
    assert columns[0] == {
        "name": "id",
        "data_type": "character varying",
        "length": None,
        "scale": None,
        "nullable": True,
        "default": None,
    }


def test_single_table_submission_is_left_to_the_shared_parser():
    assert agriculture_parser.parse_table("column_name,data_type\nid,integer\n", "t1") is None
    assert agriculture_parser.parse_table("sno integer NOT NULL", "t1") is None
    assert agriculture_parser.parse_table("too short\n", "t1") is None


def test_unknown_table_lists_what_the_submission_holds():
    with pytest.raises(ValueError, match="isn't in this submission -- it holds: crop_sales, current_booking"):
        agriculture_parser.parse_table(MULTI_TABLE, "nope")


def test_parse_source_routes_agriculture_through_its_own_parser():
    columns = parse_source("agriculture_department", "current_booking", "csv", MULTI_TABLE)

    assert [c["name"] for c in columns] == ["id", "status"]


def test_parse_source_falls_back_to_the_shared_parser_for_a_single_table_csv():
    text = "column_name,data_type\nid,integer\n"

    assert parse_source("agriculture_department", "crop_sales", "csv", text) == parse_csv_text(text)


def test_parse_source_falls_back_to_the_shared_parser_for_a_ddl_dump():
    assert parse_source("agriculture_department", "crop_sales", "postgres_ddl", "sno integer NOT NULL") == [
        {"name": "sno", "data_type": "integer", "length": None, "scale": None, "nullable": False, "default": None}
    ]


@pytest.mark.skipif(not SAMPLE.exists(), reason="the real agriculture submission is gitignored")
def test_real_submission_parses_every_table_it_holds():
    text = SAMPLE.read_text(encoding="utf-8")

    counts = {
        table: len(agriculture_parser.parse_table(text, table))
        for table in [
            "crop_sales",
            "current_booking",
            "current_booking_farmer_details",
            "online_booking",
            "online_booking_details",
        ]
    }

    assert counts == {
        "crop_sales": 53,
        "current_booking": 55,
        "current_booking_farmer_details": 19,
        "online_booking": 13,
        "online_booking_details": 19,
    }


@pytest.mark.skipif(
    not (SAMPLE.exists() and PREPROCESSED.exists()),
    reason="needs the gitignored submission and the CSV preprocessing wrote from it",
)
def test_raw_and_preprocessed_routes_produce_identical_columns():
    """Ingesting the raw multi-table file or the per-table CSV preprocessing
    split out of it must land on the same columns -- otherwise the source
    of an ingest would show up as a schema change on the next run."""

    raw = agriculture_parser.parse_table(SAMPLE.read_text(encoding="utf-8"), "crop_sales")
    split = parse_csv_text(PREPROCESSED.read_text(encoding="utf-8"))

    assert raw == split
