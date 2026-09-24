from unittest.mock import MagicMock

import pytest

from src.schema_registry import lookups
from src.schema_registry.openmetadata_publish import _unwrap, publish_table
from src.schema_registry.pipeline import run
from src.storage.local import LocalObjectStorage


def _ingested_storage(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    run(
        department="pwd",
        dataset="vishwakarma",
        table_name="TBD_confirm_with_pwd",
        source_file=_write_ddl(tmp_path),
        storage=storage,
        source_format="postgres_ddl",
    )
    return storage


def _write_ddl(tmp_path) -> str:
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text(
        "sno integer NOT NULL, firm_name character varying(100), total_cost double precision DEFAULT 0"
    )
    return str(ddl_file)


def _fake_client():
    """A minimal stand-in for OpenMetadata's SDK client: get_by_name always
    reports "not found" (nothing exists yet), create_or_update just echoes
    back something with a name/fullyQualifiedName so _fqn() can chain calls
    the same way the real SDK's response objects do."""

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
        fqn = f"{parent}.{name}" if parent else str(name)
        entity.fullyQualifiedName = fqn
        entity.name = name
        return entity

    client.create_or_update.side_effect = _create_or_update
    return client


def test_publish_table_builds_full_entity_chain(tmp_path):
    storage = _ingested_storage(tmp_path)
    client = _fake_client()

    result = publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    assert result["table_id"] == "pwd.vishwakarma.tbd_confirm_with_pwd"
    assert result["column_count"] == 3
    assert result["fully_qualified_name"] == "pwd.vishwakarma.public.TBD_confirm_with_pwd"

    created = [call.args[0] for call in client.create_or_update.call_args_list]
    assert _unwrap(created[0].name) == "pwd"  # service defaults to department_id
    assert _unwrap(created[1].name) == "vishwakarma"  # database == dataset slug
    assert _unwrap(created[2].name) == "public"  # schema_name from tables.csv
    table_request = created[3]
    assert _unwrap(table_request.name) == "TBD_confirm_with_pwd"
    assert [_unwrap(c.name) for c in table_request.columns] == ["sno", "firm_name", "total_cost"]


def test_publish_table_reuses_existing_entities_instead_of_recreating(tmp_path):
    storage = _ingested_storage(tmp_path)
    client = _fake_client()
    existing_service = MagicMock(fullyQualifiedName="pwd", name="pwd")
    client.get_by_name.side_effect = None
    client.get_by_name.return_value = existing_service

    publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    # every level found an existing entity, so create_or_update was only
    # called once -- for the table itself, which is always created/updated
    assert client.create_or_update.call_count == 1


def test_publish_table_unknown_table_id_raises(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    client = _fake_client()

    with pytest.raises(ValueError, match="Unknown table_id"):
        publish_table(client, storage, "pwd.vishwakarma.does_not_exist")


def test_publish_table_no_curated_snapshot_raises(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    lookups.upsert_dataset(storage, "pwd.vishwakarma", "pwd", "vishwakarma")
    lookups.upsert_table(storage, "pwd.vishwakarma.t1", "pwd.vishwakarma", "t1", "public")
    client = _fake_client()

    with pytest.raises(FileNotFoundError, match="No curated schema"):
        publish_table(client, storage, "pwd.vishwakarma.t1")


def test_publish_table_unmapped_data_type_raises(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    run(
        department="pwd",
        dataset="vishwakarma",
        table_name="t1",
        source_file=_write_ddl(tmp_path),
        storage=storage,
        source_format="postgres_ddl",
    )
    # tamper with the curated snapshot to simulate a type this pipeline
    # never validated (should never happen via curate.py, but publish
    # should fail loudly rather than silently mis-typing a column in OM)
    curated_path = storage.list("department/pwd/vishwakarma/t1/curated/schemas/")[-1]
    rows = storage.read_csv(curated_path)
    rows[0]["data_type"] = "money"
    storage.write_csv(curated_path, rows)

    client = _fake_client()
    with pytest.raises(ValueError, match="No OpenMetadata mapping"):
        publish_table(client, storage, "pwd.vishwakarma.t1")


def test_publish_table_picks_latest_curated_snapshot(tmp_path):
    storage = _ingested_storage(tmp_path)
    # re-run with a different column set -- should produce a newer snapshot
    ddl_file = tmp_path / "raw2.txt"
    ddl_file.write_text("only_col integer NOT NULL")
    run(
        department="pwd",
        dataset="vishwakarma",
        table_name="TBD_confirm_with_pwd",
        source_file=str(ddl_file),
        storage=storage,
        source_format="postgres_ddl",
    )

    client = _fake_client()
    result = publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    assert result["column_count"] == 1
    table_request = client.create_or_update.call_args_list[-1].args[0]
    assert [_unwrap(c.name) for c in table_request.columns] == ["only_col"]
