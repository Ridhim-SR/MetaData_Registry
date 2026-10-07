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
