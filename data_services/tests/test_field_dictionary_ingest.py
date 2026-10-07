from src.schema_registry.registry import lookups
from src.schema_registry.parsers.field_dictionary_ingest import run_field_dictionary
from src.storage.local import LocalObjectStorage


def _write_dictionary(tmp_path, rows):
    path = tmp_path / "field_dictionary.csv"
    header = "Dataset Name,Dataset Field,Data Description,Format,Mandatory (Y/N)"
    lines = [header] + [",".join(row) for row in rows]
    path.write_text("\n".join(lines))
    return str(path)


def test_splits_one_file_into_multiple_published_tables(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "welfare", "Social Welfare Department")
    source = _write_dictionary(
        tmp_path,
        [
            ("cmsvy_application", "application_no", "Registration ID", "Text (Alphanumeric)", "Y"),
            ("cmsvy_bride_details", "bride_aadhaar_no", "Aadhaar of the bride", "Numeric (12 Digits)", "Y"),
            ("cmsvy_bride_details", "bride_mobile_no", "Contact number", "Numeric (10 Digits)", "Y"),
        ],
    )

    results = run_field_dictionary(
        department="welfare",
        dataset="cmsvy",
        source_file=source,
        storage=storage,
    )

    assert set(results.keys()) == {"cmsvy_application", "cmsvy_bride_details"}
    assert results["cmsvy_application"]["column_count"] == 1
    assert results["cmsvy_bride_details"]["column_count"] == 2

    # each table actually landed under its own table_id, independently
    # curated and stored -- not merged into one
    assert lookups.get_table(storage, "welfare.cmsvy.cmsvy_application") is not None
    assert lookups.get_table(storage, "welfare.cmsvy.cmsvy_bride_details") is not None


def test_business_description_carries_through_and_pii_still_auto_classifies(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "welfare", "Social Welfare Department")
    source = _write_dictionary(
        tmp_path,
        [("t1", "bride_aadhaar_no", "Aadhaar of the bride", "Numeric (12 Digits)", "Y")],
    )

    results = run_field_dictionary(department="welfare", dataset="cmsvy", source_file=source, storage=storage)

    column = results["t1"]["columns"][0]
    assert column["business_description"] == "Aadhaar of the bride"
    # untouched by this new ingest path -- curate.py's existing PII regex
    # still fires on its own, independent of anything in the source file
    assert column["classification"] == "CAT-3"


def test_mandatory_n_means_nullable_true(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "welfare", "Social Welfare Department")
    source = _write_dictionary(tmp_path, [("t1", "optional_field", "desc", "Text", "N")])

    results = run_field_dictionary(department="welfare", dataset="cmsvy", source_file=source, storage=storage)

    assert results["t1"]["columns"][0]["nullable"] is True


def test_reingesting_dictionary_keeps_answers_set_by_hand(tmp_path):
    """The dictionary only answers business_description -- re-ingesting it
    must not blank a classification/glossary term/active flag someone set
    on this table in between."""

    from src.schema_registry.pipeline import run

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "welfare", "Social Welfare Department")
    source = _write_dictionary(tmp_path, [("t1", "bride_mobile_no", "Contact number", "Numeric (10 Digits)", "Y")])
    run_field_dictionary(department="welfare", dataset="cmsvy", source_file=source, storage=storage)

    columns_file = tmp_path / "cols.csv"
    columns_file.write_text("name,data_type\nbride_mobile_no,numeric\n")
    manual = tmp_path / "manual.csv"
    manual.write_text("name,classification,glossary_term,active\nbride_mobile_no,CAT-2,Mobile Number,false\n")
    run(
        department="welfare", dataset="cmsvy", table_name="t1", source_file=str(columns_file),
        storage=storage, source_format="csv", business_metadata_file=str(manual),
    )

    results = run_field_dictionary(department="welfare", dataset="cmsvy", source_file=source, storage=storage)

    column = results["t1"]["columns"][0]
    assert (column["classification"], column["glossary_term"], column["active"]) == ("CAT-2", "Mobile Number", False)
    assert column["business_description"] == "Contact number"


def test_dictionary_from_storage_is_archived_once_at_dataset_level(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "welfare", "Social Welfare Department")
    local = _write_dictionary(tmp_path, [("t1", "bride_name", "Name of the bride", "Text", "Y")])
    storage.write_bytes("inputs/welfare/dict.csv", open(local, "rb").read())

    results = run_field_dictionary(
        department="welfare", dataset="cmsvy", source_file="storage:inputs/welfare/dict.csv", storage=storage
    )

    assert results["t1"]["column_count"] == 1
    archived = [p for p in storage.list("department/welfare/cmsvy/_source/") if not p.endswith(".sha256")]
    assert len(archived) == 1 and archived[0].endswith("__dict.csv")
    assert storage.read_bytes(archived[0]) == open(local, "rb").read()
