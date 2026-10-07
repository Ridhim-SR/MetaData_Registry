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


def test_auto_classifies_pii_fields_as_cat3():
    curated = curate_schema(
        [
            _col("aadhaar_number", "character varying"),
            _col("mobile_number", "character varying"),
            _col("email", "character varying"),
            _col("date_of_birth", "date"),
        ]
    )
    assert all(row["classification"] == "CAT-3" for row in curated)


def test_non_pii_field_gets_no_classification():
    curated = curate_schema([_col("total_cost", "double precision")])
    assert curated[0]["classification"] == ""


def test_business_metadata_overrides_auto_classification():
    business_metadata = {"mobile_number": {"classification": "CAT-2"}}
    curated = curate_schema([_col("mobile_number", "character varying")], business_metadata)
    assert curated[0]["classification"] == "CAT-2"
