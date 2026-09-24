from unittest.mock import MagicMock

import pytest

from src.schema_registry import lookups
from src.schema_registry.openmetadata_publish import _unwrap
from src.schema_registry.pipeline import run
from src.storage.local import LocalObjectStorage


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
