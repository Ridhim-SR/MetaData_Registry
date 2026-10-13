import pytest

from src.schema_registry.curate import KNOWN_TAGS, curate_schema


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
            "tag": "PII",
            "glossary_term": "Sanctioned Cost",
            "active": True,
        }
    }
    curated = curate_schema([_col("total_cost", "double precision")], business_metadata)
    assert curated[0]["tag"] == "PII"
    assert curated[0]["business_description"] == "Total sanctioned project cost"
    assert curated[0]["glossary_term"] == "Sanctioned Cost"


def test_unknown_tag_is_rejected():
    """A tag outside KNOWN_TAGS must not be accepted: publishing it would
    auto-create a new tag in OpenMetadata's FieldTag Classification."""

    business_metadata = {"total_cost": {"tag": "Custom Tag"}}

    with pytest.raises(ValueError, match="unknown tag 'Custom Tag'"):
        curate_schema([_col("total_cost", "double precision")], business_metadata)
    assert "Custom Tag" not in KNOWN_TAGS


def test_glossary_term_with_dot_is_rejected():
    """A "." inside a glossary term breaks OpenMetadata's dot-separated
    FQN (BusinessGlossary.<term>), so the term would silently never resolve."""

    business_metadata = {"total_cost": {"glossary_term": "Cost.Total"}}

    with pytest.raises(ValueError, match="contains '.'"):
        curate_schema([_col("total_cost", "double precision")], business_metadata)


def test_field_without_business_metadata_stays_blank():
    curated = curate_schema([_col("yojanacode", "character varying")], {"other_field": {}})
    assert curated[0]["business_description"] == ""
    assert curated[0]["glossary_term"] == ""
    assert curated[0]["active"] is True


def test_auto_classifies_pii_fields_as_pii():
    curated = curate_schema(
        [
            _col("aadhaar_number", "character varying"),
            _col("mobile_number", "character varying"),
            _col("email", "character varying"),
            _col("date_of_birth", "date"),
        ]
    )
    assert all(row["classification"] == "PII" for row in curated)


def test_non_pii_field_defaults_to_internal():
    curated = curate_schema([_col("sno", "integer")])
    assert curated[0]["classification"] == "Internal"


def test_geographic_place_names_are_public_not_pii():
    """A place is not a person: state/district/block/Gram-Panchayat name
    columns are reference data, so the generic PII "name" rule must not
    reach them (the geo rule runs first)."""

    curated = curate_schema(
        [
            _col("state_name", "character varying"),
            _col("district_name", "character varying"),
            _col("block_name", "character varying"),
            _col("gp_name", "character varying"),
            _col("curr_district_name", "character varying"),  # compound prefix
            _col("project_block_name", "character varying"),
        ]
    )
    assert all(row["classification"] == "Public" for row in curated)


def test_personal_names_still_classify_as_pii():
    curated = curate_schema(
        [
            _col("father_name", "character varying"),
            _col("applicant_first_name", "character varying"),
            _col("name", "character varying"),
        ]
    )
    assert all(row["classification"] == "PII" for row in curated)


def test_geo_rule_only_matches_name_columns():
    """state_code keeps its existing Internal classification, and a column
    merely containing a place word stays on the later rules."""

    curated = curate_schema(
        [
            _col("state_code", "character varying"),
            _col("emp_avail_states_persondays", "integer"),
        ]
    )
    assert curated[0]["classification"] == "Internal"
    assert curated[1]["classification"] == "Public"  # existing geo rule, unchanged


def test_business_metadata_overrides_auto_classification():
    business_metadata = {"mobile_number": {"classification": "Confidential"}}
    curated = curate_schema([_col("mobile_number", "character varying")], business_metadata)
    assert curated[0]["classification"] == "Confidential"


def test_unknown_classification_override_falls_back_to_rules():
    business_metadata = {"mobile_number": {"classification": "CAT-2"}}
    curated = curate_schema([_col("mobile_number", "character varying")], business_metadata)
    assert curated[0]["classification"] == "PII"
