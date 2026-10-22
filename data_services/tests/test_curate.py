import pytest

from src.schema_registry.curate import KNOWN_TAGS, auto_classify, curate_schema


def _col(name, data_type="integer", **overrides):
    col = {"name": name, "data_type": data_type, "length": None, "scale": None, "nullable": True, "default": None}
    col.update(overrides)
    return col


def test_curate_schema_no_longer_tags_from_the_column_name():
    """Auto-tagging is switched off: a tag is a reviewed decision, not a
    guess at the column name, so a column the submitted metadata does not
    answer stays blank. Nothing is derived behind the reviewer's back."""

    curated = curate_schema(
        [
            _col("total_cost", "double precision"),
            _col("firm_pannumber", "character varying"),
            _col("lat", "double precision"),
            _col("demand_status"),
            _col("tender_date", "date"),
        ]
    )
    assert [row["tag"] for row in curated] == ["", "", "", "", ""]


def test_auto_tag_rules_still_cover_their_original_cases():
    """Only curate_schema()'s *use* of AUTO_TAG_RULES is off -- the rules
    themselves stay, because KNOWN_TAGS is derived from them (so every tag
    already published still validates) and ai_metadata drafts against the
    same list."""

    from src.schema_registry.curate import auto_tag

    assert auto_tag("total_cost") == "Financial"
    assert auto_tag("firm_pannumber") == "Firm/Contractor-Identifier"
    assert auto_tag("lat") == "Geospatial"
    assert auto_tag("longs") == "Geospatial"
    assert auto_tag("demand_status") == "Status/Workflow"
    assert auto_tag("tender_date") == "Date/Timestamp"
    assert auto_tag("comment") is None


def test_untagged_field_gets_empty_string_not_none():
    curated = curate_schema([_col("comment", "character varying")])
    assert curated[0]["tag"] == ""


def test_submitted_tag_is_taken_as_written():
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


def test_a_field_no_rule_recognises_is_left_blank_not_guessed_internal():
    curated = curate_schema([_col("sno", "integer")])
    assert curated[0]["classification"] == ""


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


def test_name_hindi_is_carried_beside_the_column():
    curated = curate_schema([_col("serial_number", name_hindi="क्रमसं०")])
    assert curated[0]["name_hindi"] == "क्रमसं०"


def test_name_hindi_from_business_metadata_fills_a_missing_column_answer():
    curated = curate_schema(
        [_col("serial_number")],
        {"serial_number": {"name_hindi": "क्रमसं०"}},
    )
    assert curated[0]["name_hindi"] == "क्रमसं०"


def test_the_schema_csv_answer_wins_over_a_carried_forward_label():
    """An edited label in the submitted schema CSV must take effect instead of
    the previous snapshot's label being carried forward forever."""

    curated = curate_schema(
        [_col("serial_number", name_hindi="क्रमसंख्या")],
        {"serial_number": {"name_hindi": "क्रमसं०"}},
    )
    assert curated[0]["name_hindi"] == "क्रमसंख्या"


def test_a_column_without_a_hindi_name_does_not_gain_the_key():
    curated = curate_schema([_col("amount", "numeric")])
    assert "name_hindi" not in curated[0]


# --- auto_classify: whole-token matching for the short, ambiguous words ----------------------------

@pytest.mark.parametrize("name,level", [
    # a trigger word that only sits INSIDE a longer word must not fire (no rule left -> blank)
    ("cancel_by_logic", ""),      # log in "logic"
    ("catalog_no", ""),           # log in "catalog"
    ("hotmix_plant", ""),         # plan in "plant"
    ("company_code", "Internal"),         # pan in "company"
    ("expansion_date", ""),       # pan in "expansion"
    ("author", ""),               # auth in "author"
    ("monkey", ""),               # key in "monkey"
    ("migrant_count", ""),        # grant in "migrant"
    ("capacity", ""),             # city in "capacity" -- must not become Public
    ("statement_date", ""),       # state in "statement" -- must not become Public
    ("name_of_work", "Internal"),         # a title, not a person
    ("name_of_scheme", "Internal"),
    ("crop_noncrop_name_id", "Internal"),  # an id, "name" is in the middle
])
def test_a_word_inside_a_longer_word_does_not_trigger_a_rule(name, level):
    assert auto_classify(name) == level


@pytest.mark.parametrize("name,level", [
    ("audit_log", "Restricted"), ("change_log", "Restricted"), ("access_logs", "Restricted"),
    ("api_key", "Restricted"), ("auth_token", "Restricted"), ("password", "Restricted"),
    ("forecast_plan", "Confidential"), ("plan", "Confidential"),
    ("aadhaar", "PII"), ("aadhaar_no", "PII"), ("aadhaarnumber", "PII"), ("pan", "PII"),
    ("pan_number", "PII"), ("firm_pannumber", "PII"), ("pancard", "PII"),
    ("name", "PII"), ("full_name", "PII"), ("farmername", "PII"), ("sansthaname", "PII"),
    ("name_of_applicant", "PII"), ("mobile_no", "PII"), ("email", "PII"), ("dob", "PII"),
    ("total_cost", "Financial"), ("v19_20extraamount", "Financial"), ("v20_21surrenderamount", "Financial"),
    ("emi", "Financial"), ("grant_amount", "Financial"),
    ("state", "Public"), ("states", "Public"), ("emp_avail_states_persondays", "Public"),
    ("district", "Internal"), ("latitude", "Public"),  # district: the Internal rule is first -- unchanged
    ("change_mainschemeid", "Internal"), ("sno", ""), ("tender_date", ""),
])
def test_the_real_cases_still_match(name, level):
    assert auto_classify(name) == level
