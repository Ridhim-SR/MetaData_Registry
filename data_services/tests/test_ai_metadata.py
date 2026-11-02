import csv

import pytest

from src.schema_registry import ai_metadata


def test_ai_metadata_uses_the_curated_tag_vocabulary():
    from src.schema_registry.curate import KNOWN_TAGS

    assert set(ai_metadata.KNOWN_TAGS) == set(KNOWN_TAGS)
    assert {"Identifier", "Administrative-Unit", "Quantity", "Remarks"} <= set(ai_metadata.KNOWN_TAGS)


def test_apply_rules_tags_agriculture_welfare_and_rural_columns():
    columns = [
        {"name": "application_no"},
        {"name": "child_name_en"},
        {"name": "social_category"},
        {"name": "caste_application_no"},
        {"name": "women_active_workers"},
        {"name": "sc_active_workers"},
        {"name": "application_status"},
        {"name": "booking_amount"},
        {"name": "ifsc_code"},
        {"name": "district_code"},
        {"name": "year"},
        {"name": "login_id"},
        {"name": "active_jobcards"},
        {"name": "remarks"},
    ]

    drafted, _ = ai_metadata.apply_rules(columns, [])

    assert {column["name"]: column["tag"] for column in drafted} == {
        "application_no": "PII",
        "child_name_en": "PII",
        "social_category": "Sensitive",
        "caste_application_no": "Sensitive",
        "women_active_workers": "Sensitive",
        "sc_active_workers": "Sensitive",
        "application_status": "Status/Workflow",
        "booking_amount": "Financial",
        "ifsc_code": "Financial",
        "district_code": "Geospatial",
        "year": "Date/Timestamp",
        "login_id": "Identifier",
        "active_jobcards": "Quantity",
        "remarks": "Remarks",
    }


def test_apply_rules_generalizes_across_department_schema_patterns():
    columns = [
        {"name": "bride_name"},
        {"name": "teacher_name"},
        {"name": "hos_name"},
        {"name": "student_national_code"},
        {"name": "uploaded_by"},
        {"name": "doc_bride_age_proof"},
        {"name": "doc_id"},
        {"name": "registration_id"},
        {"name": "vendor_registration_id"},
        {"name": "mobile_verified"},
        {"name": "marital_status"},
        {"name": "is_cwsn"},
        {"name": "polio_birth_dose_flag"},
        {"name": "cumul_hh_jobcards_sc"},
        {"name": "central_subsidy"},
        {"name": "farmer_share"},
        {"name": "is_fee_paid"},
        {"name": "curr_mohalla_post"},
        {"name": "delivery_location_type"},
        {"name": "fam_completed_100_days"},
        {"name": "agri_land_area_hectares"},
        {"name": "is_permanent_same"},
        {"name": "school_name"},
        {"name": "district_name"},
    ]

    drafted, _ = ai_metadata.apply_rules(columns, [])

    assert {column["name"]: column["tag"] for column in drafted} == {
        "bride_name": "PII",
        "teacher_name": "PII",
        "hos_name": "PII",
        "student_national_code": "PII",
        "uploaded_by": "PII",
        "doc_bride_age_proof": "PII",
        "doc_id": "Identifier",
        "registration_id": "Identifier",
        "vendor_registration_id": "Identifier",
        "mobile_verified": "",
        "marital_status": "Sensitive",
        "is_cwsn": "Sensitive",
        "polio_birth_dose_flag": "Sensitive",
        "cumul_hh_jobcards_sc": "Sensitive",
        "central_subsidy": "Financial",
        "farmer_share": "Financial",
        "is_fee_paid": "Financial",
        "curr_mohalla_post": "Geospatial",
        "delivery_location_type": "Geospatial",
        "fam_completed_100_days": "Quantity",
        "agri_land_area_hectares": "Quantity",
        "is_permanent_same": "Status/Workflow",
        "school_name": "",
        "district_name": "Geospatial",
    }
    assert ai_metadata.category_floor(drafted, "CAT-1") == "CAT-3"


def test_apply_rules_preserves_explicit_approved_tags_but_rejects_unknown_tags():
    columns = [{"name": "free_text"}]
    drafted, _ = ai_metadata.apply_rules(columns, [{"name": "free_text", "tag": "Quantity"}])

    assert drafted[0]["tag"] == "Quantity"
    with pytest.raises(ValueError, match="unknown tag 'invented'"):
        ai_metadata.apply_rules(columns, [{"name": "free_text", "tag": "invented"}])


def test_writes_metadata_csv_next_to_raw_file(tmp_path, monkeypatch, capsys):
    raw = tmp_path / "t.txt"
    raw.write_text("sno integer NOT NULL, firm_name character varying(100), lat double precision")
    seen = {}

    def fake_draft(columns, definitions):
        seen["names"] = [c["name"] for c in columns]
        seen["definitions"] = definitions
        return {
            "columns": [{"name": "sno", "business_description": "Serial number", "tag": ""},
                        {"name": "lat", "business_description": "Latitude", "tag": "Geospatial"}],
            "dataset": {"description": "Works", "category": "CAT-3", "reason": "contractor data"},
        }

    monkeypatch.setattr(ai_metadata, "draft", fake_draft)
    # _main() calls load_dotenv() to find ANTHROPIC_API_KEY. Left alone that
    # reads the real .env into os.environ for the rest of the pytest session,
    # where its WASABI_BUCKET makes every later storage_from_env() build an
    # S3 client instead of the local storage these tests set up -- draft() is
    # faked above, so nothing here needs the real file.
    monkeypatch.setattr(ai_metadata, "load_dotenv", lambda *a, **k: None)
    defs = tmp_path / "cat.txt"
    defs.write_text("CAT-3: restricted")

    assert ai_metadata._main([str(raw), "--cat-definitions", str(defs)]) == 0

    rows = list(csv.DictReader(open(tmp_path / "t_metadata.csv")))
    assert [r["name"] for r in rows] == ["sno", "firm_name", "lat"]  # raw file's order
    assert rows[0]["business_description"] == "Serial number"
    assert rows[1]["business_description"] == ""  # a field the AI skipped stays blank
    assert rows[2]["tag"] == "Geospatial"
    assert seen["definitions"] == "CAT-3: restricted"
    out = capsys.readouterr().out
    assert "category:    CAT-3" in out and "catalog.yaml" in out
