from src.schema_registry.curate import curate_schema


def _col(name, data_type="integer", **overrides):
    col = {"name": name, "data_type": data_type, "length": None, "scale": None, "nullable": True, "default": None}
    col.update(overrides)
    return col


def test_auto_tags_financial_field():
    curated = curate_schema([_col("total_cost", "double precision")])
    assert curated[0]["tag"] == "Financial"


def test_auto_tags_firm_identifier():
    curated = curate_schema([_col("firm_pannumber", "character varying")])
    assert curated[0]["tag"] == "Firm/Contractor-Identifier"


def test_auto_tags_geospatial():
    curated = curate_schema([_col("lat", "double precision"), _col("longs", "double precision")])
    assert curated[0]["tag"] == "Geospatial"
    assert curated[1]["tag"] == "Geospatial"


def test_auto_tags_status_and_date():
    curated = curate_schema([_col("demand_status"), _col("tender_date", "date")])
    assert curated[0]["tag"] == "Status/Workflow"
    assert curated[1]["tag"] == "Date/Timestamp"


def test_untagged_field_gets_empty_string_not_none():
    curated = curate_schema([_col("comment", "character varying")])
    assert curated[0]["tag"] == ""


def test_unknown_postgres_type_produces_validation_warning():
    curated = curate_schema([_col("weird_col", "some_made_up_type")])
    assert "Unrecognized Postgres type" in curated[0]["validation_warning"]


def test_known_type_has_no_warning():
    curated = curate_schema([_col("sno", "integer")])
    assert curated[0]["validation_warning"] == ""


def test_business_metadata_overrides_auto_tag():
    business_metadata = {
        "total_cost": {
            "business_description": "Total sanctioned project cost",
            "tag": "Custom Tag",
            "glossary_term": "Sanctioned Cost",
            "active": True,
        }
    }
    curated = curate_schema([_col("total_cost", "double precision")], business_metadata)
    assert curated[0]["tag"] == "Custom Tag"
    assert curated[0]["business_description"] == "Total sanctioned project cost"
    assert curated[0]["glossary_term"] == "Sanctioned Cost"


def test_field_without_business_metadata_stays_blank():
    curated = curate_schema([_col("yojanacode", "character varying")], {"other_field": {}})
    assert curated[0]["business_description"] == ""
    assert curated[0]["glossary_term"] == ""
    assert curated[0]["active"] is True
