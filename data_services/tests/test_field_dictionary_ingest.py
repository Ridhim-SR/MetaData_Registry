from src.schema_registry.registry import lookups
from src.schema_registry.parsers.field_dictionary_ingest import run_field_dictionary
from src.storage.local import LocalObjectStorage


def _write_dictionary(tmp_path, rows):
    path = tmp_path / "field_dictionary.csv"
    header = "Dataset Name,Dataset Field,Data Description,Format,Mandatory (Y/N)"
    lines = [header] + [",".join(row) for row in rows]
    path.write_text("\n".join(lines), encoding="utf-8")
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
    assert column["classification"] == "PII"


def test_mandatory_n_means_nullable_true(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "welfare", "Social Welfare Department")
    source = _write_dictionary(tmp_path, [("t1", "optional_field", "desc", "Text", "N")])

    results = run_field_dictionary(department="welfare", dataset="cmsvy", source_file=source, storage=storage)

    assert results["t1"]["columns"][0]["nullable"] is True


def test_one_bad_table_does_not_stop_the_rest_of_the_file(tmp_path):
    """The whole file used to be one all-or-nothing operation: a single
    table the pipeline rejects (here: a name with no ASCII to slugify)
    must not throw away the tables that were fine."""

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "welfare", "Social Welfare Department")
    source = _write_dictionary(
        tmp_path,
        [
            ("cmsvy_application", "application_no", "Registration ID", "Text (Alphanumeric)", "Y"),
            ("सड़क", "road_name", "Name of the road", "Text", "Y"),
        ],
    )

    results = run_field_dictionary(department="welfare", dataset="cmsvy", source_file=source, storage=storage)

    assert results["cmsvy_application"]["status"] == "ok"
    assert results["सड़क"]["status"] == "failed"
    assert "explicit ASCII id" in results["सड़क"]["error"]
    # the good table really made it into the registry
    assert lookups.get_table(storage, "welfare.cmsvy.cmsvy_application") is not None


def test_publish_failure_is_reported_per_table_and_the_loop_continues(tmp_path):
    """Item 13: a publish error on one table must be captured on that table's
    row (so republish can fix it) instead of aborting the ingest."""

    class _FailingClient:
        def __init__(self):
            from unittest.mock import MagicMock
            from src.schema_registry.openmetadata.publish import _unwrap

            self.client = MagicMock()
            self.get_by_name = MagicMock(side_effect=Exception("Entity not found"))

            def _create_or_update(request):
                if type(request).__name__ == "CreateTableRequest" and _unwrap(request.name) == "cmsvy_bride_details":
                    raise RuntimeError("server said no")
                entity = MagicMock()
                name = _unwrap(getattr(request, "name", None))
                parent = _unwrap(
                    getattr(request, "service", None)
                    or getattr(request, "database", None)
                    or getattr(request, "databaseSchema", None)
                    or getattr(request, "classification", None)
                    or getattr(request, "glossary", None)
                )
                entity.fullyQualifiedName = f"{parent}.{name}" if parent else str(name)
                entity.name = name
                entity.id = "11111111-1111-1111-1111-111111111111"
                # _replace_column_tags() matches the sent columns against the
                # ones the "server" echoes back, so it needs a real list here
                entity.columns = getattr(request, "columns", None)
                return entity

            self.create_or_update = MagicMock(side_effect=_create_or_update)

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "welfare", "Social Welfare Department")
    source = _write_dictionary(
        tmp_path,
        [
            ("cmsvy_application", "application_no", "Registration ID", "Text (Alphanumeric)", "Y"),
            ("cmsvy_bride_details", "bride_aadhaar_no", "Aadhaar of the bride", "Numeric (12 Digits)", "Y"),
        ],
    )

    results = run_field_dictionary(
        department="welfare", dataset="cmsvy", source_file=source,
        storage=storage, openmetadata_client=_FailingClient(),
    )

    assert results["cmsvy_application"]["status"] == "ok"
    assert results["cmsvy_bride_details"]["status"] == "failed"
    assert "server said no" in results["cmsvy_bride_details"]["error"]

    # the failed one still has its snapshot in storage, and its run row says
    # so -- that's what republish picks up
    from src.schema_registry.registry import lookups as _lookups
    rows = {r["table_id"]: r for r in storage.read_csv(_lookups.RUNS_PATH)}
    assert rows["welfare.cmsvy.cmsvy_application"]["publish_status"] == "published"
    assert rows["welfare.cmsvy.cmsvy_bride_details"]["publish_status"] == "failed"
    assert "server said no" in rows["welfare.cmsvy.cmsvy_bride_details"]["error"]


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
    # `classification` is an MDSF level here (the dataset categories CAT-n are
    # the dataset-level axis), anything else is auto-classified again.
    manual.write_text("name,classification,glossary_term,active\nbride_mobile_no,Confidential,Mobile Number,false\n")
    run(
        department="welfare", dataset="cmsvy", table_name="t1", source_file=str(columns_file),
        storage=storage, source_format="csv", business_metadata_file=str(manual),
    )

    results = run_field_dictionary(department="welfare", dataset="cmsvy", source_file=source, storage=storage)

    column = results["t1"]["columns"][0]
    assert (column["classification"], column["glossary_term"], column["active"]) == (
        "Confidential",
        "Mobile Number",
        False,
    )
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


def _write_dictionary_with_personal(tmp_path, rows):
    import csv as _csv

    path = tmp_path / "field_dictionary_personal.csv"
    header = ["Dataset Name", "Dataset Field", "Data Description", "Format", "Mandatory (Y/N)", "Personal Data (Y/N)"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = _csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return str(path)


def test_personal_data_column_is_classified_but_not_tagged_by_ingest(tmp_path):
    """The ingest step writes only name + business_description: the file's
    `Personal Data (Y/N)` answer must not land as a column tag. Classification
    still comes from curate.py's own PII rules, and the tag from its auto-tag
    rules (which have no rule for an aadhaar number)."""

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "welfare", "Social Welfare Department")
    source = _write_dictionary_with_personal(
        tmp_path,
        [("t1", "bride_aadhaar_no", "Aadhaar of the bride", "Numeric (12 Digits)", "Y", "Y")],
    )

    results = run_field_dictionary(department="welfare", dataset="cmsvy", source_file=source, storage=storage)

    assert results["t1"]["columns"][0]["tag"] == ""
    assert results["t1"]["columns"][0]["classification"] == "PII"


def test_personal_data_no_leaves_auto_tagging_in_charge(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "welfare", "Social Welfare Department")
    source = _write_dictionary_with_personal(
        tmp_path,
        [("t1", "tender_cost", "Cost of the tender", "Numeric (12 Digits)", "N", "N")],
    )

    results = run_field_dictionary(department="welfare", dataset="cmsvy", source_file=source, storage=storage)

    assert results["t1"]["columns"][0]["tag"] == "Financial"


def test_unrecognised_format_row_is_still_ingested(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "welfare", "Social Welfare Department")
    source = _write_dictionary(tmp_path, [("t1", "weird_col", "Mystery field", "[Aadhaar Redacted]", "N")])

    results = run_field_dictionary(department="welfare", dataset="cmsvy", source_file=source, storage=storage)

    assert results["t1"]["status"] == "ok"
    assert results["t1"]["columns"][0]["data_type"] == "character varying"
