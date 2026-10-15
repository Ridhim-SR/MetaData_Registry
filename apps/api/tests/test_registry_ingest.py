"""Unit tests for the curated-snapshot ingest endpoint (no DB required)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.routers.registry_ingest import parse_curated_snapshot  # noqa: E402

VALID_SNAPSHOT = (
    "table_id,ingestion_timestamp,name,data_type,length,scale,nullable,default,"
    "business_description,tag,glossary_term,active,classification,validation_warning\n"
    "agriculture_department.distribution_record_dataset.crop_sales,"
    "20260930T083920804959Z,id,character varying,,,True,,,,,True,Internal,\n"
    "agriculture_department.distribution_record_dataset.crop_sales,"
    "20260930T083920804959Z,quantity,numeric,10,2,False,0,"
    "Quintals sold,Financial,Sale Volume,true,Financial,some warning\n"
)

# pre-classification snapshots simply omit that column
OLD_SNAPSHOT = (
    "table_id,ingestion_timestamp,name,data_type,length,scale,nullable,default,"
    "business_description,tag,glossary_term,active,validation_warning\n"
    "agriculture_department.distribution_record_dataset.crop_sales,"
    "20260928T044715078090Z,id,character varying,,,True,,,,,True,\n"
)


def test_parses_meta_and_columns():
    meta, columns = parse_curated_snapshot(VALID_SNAPSHOT)

    assert meta["table_id"] == "agriculture_department.distribution_record_dataset.crop_sales"
    assert meta["department"] == "agriculture_department"
    assert meta["dataset"] == "distribution_record_dataset"
    assert meta["table_name"] == "crop_sales"
    assert meta["schema_name"] == "public"
    assert meta["column_count"] == 2
    assert meta["source_timestamp"] == "20260930T083920804959Z"

    first, second = columns
    assert first["position"] == 1
    assert first["name"] == "id"
    assert first["data_type"] == "character varying"
    assert first["nullable"] is True
    assert first["active"] is True
    assert first["classification"] == "Internal"
    assert first["tag"] is None

    assert second["position"] == 2
    assert second["length"] == 10
    assert second["scale"] == 2
    assert second["nullable"] is False
    assert second["default_value"] == "0"
    assert second["business_description"] == "Quintals sold"
    assert second["tag"] == "Financial"
    assert second["glossary_term"] == "Sale Volume"
    assert second["classification"] == "Financial"
    assert second["validation_warning"] == "some warning"


def test_tolerates_snapshot_without_classification_column():
    meta, columns = parse_curated_snapshot(OLD_SNAPSHOT)
    assert meta["column_count"] == 1
    assert meta["source_timestamp"] == "20260928T044715078090Z"
    assert columns[0]["classification"] is None
    assert columns[0]["active"] is True


def test_snapshot_table_id_wins_when_request_does_not_send_one():
    snapshot = VALID_SNAPSHOT.replace(
        "agriculture_department.distribution_record_dataset.crop_sales,", ","
    )
    meta, _ = parse_curated_snapshot(
        snapshot, table_id="agriculture_department.distribution_record_dataset.crop_sales"
    )
    assert meta["table_id"] == "agriculture_department.distribution_record_dataset.crop_sales"
    assert meta["table_name"] == "crop_sales"


def test_mismatched_table_id_override_rejected():
    with pytest.raises(ValueError, match="belongs to"):
        parse_curated_snapshot(
            VALID_SNAPSHOT,
            table_id="agriculture_department.distribution_record_dataset.online_booking",
        )


def test_rejects_non_curated_csv():
    with pytest.raises(ValueError, match="Not a curated schema snapshot"):
        parse_curated_snapshot("column_name,data_type\nid,character varying\n")


def test_rejects_empty_file():
    with pytest.raises(ValueError, match="empty"):
        parse_curated_snapshot("")


def test_rejects_header_only_snapshot():
    with pytest.raises(ValueError, match="no column rows"):
        parse_curated_snapshot("table_id,name,data_type\n")


def test_rejects_row_without_name():
    snapshot = VALID_SNAPSHOT.splitlines()[0] + "\nagriculture_department.a.b,ts,,integer,,,\n"
    with pytest.raises(ValueError, match="missing column name"):
        parse_curated_snapshot(snapshot)


def test_rejects_malformed_table_id():
    snapshot = VALID_SNAPSHOT.replace(
        "agriculture_department.distribution_record_dataset.crop_sales", "just_one_part"
    )
    with pytest.raises(ValueError, match="department.dataset.table"):
        parse_curated_snapshot(snapshot)


def test_schema_name_defaults_and_overrides():
    assert parse_curated_snapshot(VALID_SNAPSHOT)[0]["schema_name"] == "public"
    assert parse_curated_snapshot(VALID_SNAPSHOT, schema_name="staging")[0]["schema_name"] == "staging"
