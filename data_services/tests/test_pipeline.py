import csv
from unittest.mock import MagicMock

import pytest

from src.schema_registry import lookups
from src.schema_registry.openmetadata_publish import _unwrap
from src.schema_registry.pipeline import run
from src.storage.local import LocalObjectStorage


def _write_business_metadata(tmp_path, filename: str, rows: list[dict]) -> str:
    path = tmp_path / filename
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "business_description", "tag", "glossary_term", "active"])
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def _storage_with_department(tmp_path, department_id="pwd", department_name="PWD"):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, department_id, department_name)
    return storage


def _fake_om_client():
    """Same minimal SDK stand-in as test_openmetadata_publish.py's
    _fake_client(): get_by_name always reports "not found", create_or_update
    echoes back a name/fullyQualifiedName so _fqn() can chain calls."""

    client = MagicMock()
    client.get_by_name.side_effect = Exception("Entity not found")

    def _create_or_update(request):
        entity = MagicMock()
        name = _unwrap(getattr(request, "name", None))
        parent = _unwrap(
            getattr(request, "service", None)
            or getattr(request, "database", None)
            or getattr(request, "databaseSchema", None)
        )
        entity.fullyQualifiedName = f"{parent}.{name}" if parent else str(name)
        entity.name = name
        return entity

    client.create_or_update.side_effect = _create_or_update
    return client


def test_run_with_postgres_ddl_format(tmp_path):
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text('sno integer NOT NULL, total_cost double precision DEFAULT 0')
    storage = _storage_with_department(tmp_path)

    result = run(
        department="pwd",
        dataset="vishwakarma",
        table_name="TBD_confirm_with_pwd",
        source_file=str(ddl_file),
        storage=storage,
        source_format="postgres_ddl",
    )

    assert result["column_count"] == 2
    assert result["warning_count"] == 0
    assert storage.exists(result["raw_path"])
    assert storage.exists(result["curated_path"])

    curated = storage.read_csv(result["curated_path"])
    assert curated[0]["table_id"] == "pwd.vishwakarma.tbd_confirm_with_pwd"
    assert curated[1]["tag"] == "Financial"


def test_run_with_openmetadata_client_publishes_in_the_same_call(tmp_path):
    """The whole point of wiring publish into run(): passing a client makes
    ingest -> curate -> publish one pipeline call instead of a separate
    manual openmetadata_publish.publish_table() step afterward."""

    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("sno integer NOT NULL, firm_name character varying(100)")
    storage = _storage_with_department(tmp_path)
    client = _fake_om_client()

    result = run(
        department="pwd",
        dataset="vishwakarma",
        table_name="t1",
        source_file=str(ddl_file),
        storage=storage,
        openmetadata_client=client,
    )

    assert result["openmetadata"]["fully_qualified_name"] == "pwd.vishwakarma.public.t1"
    assert result["openmetadata"]["column_count"] == 2
    assert client.create_or_update.call_count == 4  # service, database, schema, table


def test_run_without_openmetadata_client_skips_publish(tmp_path):
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("sno integer NOT NULL")
    storage = _storage_with_department(tmp_path)

    result = run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)

    assert "openmetadata" not in result


def test_curated_rows_carry_ingestion_timestamp(tmp_path):
    """Audit requirement: ingestion timestamp must travel with the row data
    itself, not only live in the filename -- otherwise it's lost if the CSV
    is ever copied/extracted from its file path."""

    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("sno integer NOT NULL")
    storage = _storage_with_department(tmp_path)

    result = run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)

    curated = storage.read_csv(result["curated_path"])
    assert curated[0]["ingestion_timestamp"]
    raw = storage.read_csv(result["raw_path"])
    assert raw[0]["ingestion_timestamp"] == curated[0]["ingestion_timestamp"]


def test_run_with_csv_format(tmp_path):
    csv_file = tmp_path / "raw.csv"
    csv_file.write_text("Field Name,Data Type\nroad_id,integer\nroad_name,varchar\n")
    storage = _storage_with_department(tmp_path)

    result = run(
        department="pwd",
        dataset="srishti",
        table_name="roads",
        source_file=str(csv_file),
        storage=storage,
        source_format="csv",
    )

    assert result["column_count"] == 2
    curated = storage.read_csv(result["curated_path"])
    assert curated[0]["name"] == "road_id"


def test_run_registers_dataset_and_table_lookups(tmp_path):
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("sno integer NOT NULL")
    storage = _storage_with_department(tmp_path)

    run(
        department="pwd",
        dataset="vishwakarma",
        table_name="t1",
        source_file=str(ddl_file),
        storage=storage,
        source_format="postgres_ddl",
    )

    assert storage.read_csv("_lookups/departments.csv") == [{"department_id": "pwd", "department_name": "PWD"}]
    assert storage.read_csv("_lookups/datasets.csv")[0]["dataset_id"] == "pwd.vishwakarma"
    assert storage.read_csv("_lookups/tables.csv")[0]["table_id"] == "pwd.vishwakarma.t1"


def test_unregistered_department_raises(tmp_path):
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("sno integer NOT NULL")
    storage = LocalObjectStorage(tmp_path / "storage")  # no register_department call

    with pytest.raises(ValueError, match="Unknown department"):
        run(
            department="unknown_dept",
            dataset="vishwakarma",
            table_name="t1",
            source_file=str(ddl_file),
            storage=storage,
        )


def test_two_tables_same_dataset_get_separate_folders(tmp_path):
    storage = _storage_with_department(tmp_path)
    file_a = tmp_path / "a.txt"
    file_a.write_text("col_a integer")
    file_b = tmp_path / "b.txt"
    file_b.write_text("col_b integer")

    result_a = run(department="pwd", dataset="d1", table_name="table_a", source_file=str(file_a), storage=storage)
    result_b = run(department="pwd", dataset="d1", table_name="table_b", source_file=str(file_b), storage=storage)

    assert result_a["raw_path"] != result_b["raw_path"]
    assert "table_a" in result_a["raw_path"]
    assert "table_b" in result_b["raw_path"]


def test_rerun_does_not_duplicate_lookup_but_adds_new_snapshot(tmp_path):
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("sno integer NOT NULL")
    storage = _storage_with_department(tmp_path)

    run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)
    run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)

    assert len(storage.read_csv("_lookups/tables.csv")) == 1
    raw_files = storage.list("department/pwd/vishwakarma/t1/raw/schemas")
    assert len(raw_files) == 2


def test_differently_spelled_department_resolves_to_registered_entry(tmp_path):
    """slugify normalizes formatting of an already-registered department,
    it doesn't let you register a new one by typing it differently."""

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "amplify_data", "Amplify Data")

    file_a = tmp_path / "a.csv"
    file_a.write_text("Field Name,Data Type\ncol_a,integer\n")

    run(department="Amplify Data", dataset="usage", table_name="events", source_file=str(file_a), storage=storage, source_format="csv")

    departments = storage.read_csv("_lookups/departments.csv")
    assert len(departments) == 1
    assert departments[0]["department_id"] == "amplify_data"


def test_unknown_source_format_raises(tmp_path):
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("sno integer")
    storage = _storage_with_department(tmp_path)

    with pytest.raises(ValueError, match="Unknown source_format"):
        run(
            department="pwd",
            dataset="vishwakarma",
            table_name="t1",
            source_file=str(ddl_file),
            storage=storage,
            source_format="excel",
        )


def test_first_run_never_blocked_by_column_removal_guard(tmp_path):
    """A table's first-ever run has no previous snapshot to diff against,
    so it always succeeds regardless of allow_column_removal (this is
    "initial load")."""

    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("col_a integer NOT NULL")
    storage = _storage_with_department(tmp_path)

    result = run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)

    assert result["column_count"] == 1


def test_rerun_with_only_additions_succeeds_without_allow_column_removal(tmp_path):
    storage = _storage_with_department(tmp_path)
    ddl_v1 = tmp_path / "v1.txt"
    ddl_v1.write_text("col_a integer NOT NULL")
    run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v1), storage=storage)

    ddl_v2 = tmp_path / "v2.txt"
    ddl_v2.write_text("col_a integer NOT NULL, col_b character varying(50)")
    result = run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v2), storage=storage)

    assert result["column_count"] == 2


def test_rerun_dropping_a_column_raises_without_allow_column_removal(tmp_path):
    """The core guard: a source file missing a column that exists in the
    previous curated snapshot is treated as a likely partial/incremental
    submission, not an intentional removal -- it must fail loudly instead
    of silently publishing a table with fewer columns."""

    storage = _storage_with_department(tmp_path)
    ddl_v1 = tmp_path / "v1.txt"
    ddl_v1.write_text("col_a integer NOT NULL, col_b character varying(50)")
    run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v1), storage=storage)

    ddl_v2 = tmp_path / "v2.txt"
    ddl_v2.write_text("col_a integer NOT NULL")  # col_b missing

    with pytest.raises(ValueError, match="col_b"):
        run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v2), storage=storage)

    # the rejected run must not have written a new snapshot
    assert len(storage.list("department/pwd/vishwakarma/t1/curated/schemas")) == 1


def test_rerun_dropping_a_column_succeeds_with_allow_column_removal(tmp_path):
    storage = _storage_with_department(tmp_path)
    ddl_v1 = tmp_path / "v1.txt"
    ddl_v1.write_text("col_a integer NOT NULL, col_b character varying(50)")
    run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v1), storage=storage)

    ddl_v2 = tmp_path / "v2.txt"
    ddl_v2.write_text("col_a integer NOT NULL")

    result = run(
        department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v2), storage=storage,
        allow_column_removal=True,
    )

    assert result["column_count"] == 1
    assert [c["name"] for c in result["columns"]] == ["col_a"]


def test_rerun_carries_forward_business_metadata_not_resubmitted(tmp_path):
    """A department answering one column's Field Dictionary question
    shouldn't erase another column's previously-recorded answer just
    because this run's business_metadata_file doesn't mention it."""

    storage = _storage_with_department(tmp_path)
    ddl_v1 = tmp_path / "v1.txt"
    ddl_v1.write_text("col_a integer NOT NULL, col_b character varying(50)")
    meta_v1 = _write_business_metadata(tmp_path, "meta_v1.csv", [
        {"name": "col_a", "business_description": "First column", "tag": "", "glossary_term": "", "active": "true"},
        {"name": "col_b", "business_description": "Second column", "tag": "", "glossary_term": "", "active": "true"},
    ])
    run(
        department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v1), storage=storage,
        business_metadata_file=meta_v1,
    )

    # v2 only answers col_b, and adds col_c -- col_a's description should
    # still be there, not blanked out
    ddl_v2 = tmp_path / "v2.txt"
    ddl_v2.write_text("col_a integer NOT NULL, col_b character varying(50), col_c double precision")
    meta_v2 = _write_business_metadata(tmp_path, "meta_v2.csv", [
        {"name": "col_b", "business_description": "Updated second column", "tag": "", "glossary_term": "", "active": "true"},
    ])
    result = run(
        department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v2), storage=storage,
        business_metadata_file=meta_v2,
    )

    by_name = {c["name"]: c for c in result["columns"]}
    assert by_name["col_a"]["business_description"] == "First column"  # carried forward, not blanked
    assert by_name["col_b"]["business_description"] == "Updated second column"  # file overlay wins
    assert by_name["col_c"]["business_description"] == ""  # brand new column, nothing to carry forward


def test_rerun_with_no_metadata_file_still_carries_forward_previous_answers(tmp_path):
    storage = _storage_with_department(tmp_path)
    ddl_v1 = tmp_path / "v1.txt"
    ddl_v1.write_text("col_a integer NOT NULL")
    meta_v1 = _write_business_metadata(tmp_path, "meta_v1.csv", [
        {"name": "col_a", "business_description": "Only column", "tag": "PII", "glossary_term": "", "active": "true"},
    ])
    run(
        department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v1), storage=storage,
        business_metadata_file=meta_v1,
    )

    # v2: same column, no business_metadata_file at all
    ddl_v2 = tmp_path / "v2.txt"
    ddl_v2.write_text("col_a integer NOT NULL")
    result = run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v2), storage=storage)

    assert result["columns"][0]["business_description"] == "Only column"
    assert result["columns"][0]["tag"] == "PII"
