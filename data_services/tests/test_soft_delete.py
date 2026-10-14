"""Item 15 (and the orphaned-table half of it): empty slugs are rejected,
and a soft-deleted table is dropped from OpenMetadata and refused by the
publisher until it is re-ingested."""

from unittest.mock import MagicMock

import pytest

from src.schema_registry.openmetadata.publish import _unwrap, delete_table, publish_table
from src.schema_registry.pipeline import run
from src.schema_registry.registry import lookups
from src.storage.local import LocalObjectStorage


def _fake_client():
    client = MagicMock()
    client.get_by_name.side_effect = Exception("Entity not found")

    def _create_or_update(request):
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
        entity.columns = getattr(request, "columns", None)
        return entity

    client.create_or_update.side_effect = _create_or_update
    return client


def _ingested_storage(tmp_path) -> LocalObjectStorage:
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    source = tmp_path / "raw.txt"
    source.write_text("col_a integer NOT NULL")
    run(
        department="pwd", dataset="vishwakarma", table_name="t1",
        source_file=str(source), storage=storage, source_format="postgres_ddl",
    )
    return storage


def test_slugify_rejects_a_name_with_no_ascii(tmp_path):
    """'pwd..t1' and empty folder names are what this used to produce."""

    with pytest.raises(ValueError, match="explicit ASCII id"):
        lookups.slugify("सड़क")

    with pytest.raises(ValueError, match="explicit ASCII id"):
        lookups.slugify("  ---  ")


def test_slugify_still_normalizes_ordinary_names():
    assert lookups.slugify("Amplify Data") == "amplify_data"
    assert lookups.slugify("Vishwakarma 2.0") == "vishwakarma_2_0"


def test_delete_table_removes_it_from_openmetadata_and_marks_the_registry(tmp_path):
    storage = _ingested_storage(tmp_path)
    client = _fake_client()
    client.get_by_name.side_effect = lambda entity, fqn: (
        MagicMock(id="22222222-2222-2222-2222-222222222222", fullyQualifiedName=fqn)
        if fqn == "pwd.vishwakarma.public.t1"
        else (_ for _ in ()).throw(Exception("Entity not found"))
    )

    result = delete_table(client, storage, "pwd.vishwakarma.t1")

    assert result["openmetadata"] == "deleted"
    client.delete.assert_called_once()
    assert result["fully_qualified_name"] == "pwd.vishwakarma.public.t1"

    row = lookups.get_table(storage, "pwd.vishwakarma.t1")
    assert row["deleted"]  # timestamped, but the row itself is kept

    # ...and the publisher now refuses to push it back
    with pytest.raises(ValueError, match="soft-deleted"):
        publish_table(_fake_client(), storage, "pwd.vishwakarma.t1")


def test_delete_table_tolerates_an_entity_already_gone_from_openmetadata(tmp_path):
    """Retrying the command (or deleting after someone removed it in the
    OM UI) must still mark the registry -- that's the whole point."""

    storage = _ingested_storage(tmp_path)
    client = _fake_client()

    result = delete_table(client, storage, "pwd.vishwakarma.t1")

    assert result["openmetadata"] == "not-found"
    client.delete.assert_not_called()
    assert lookups.get_table(storage, "pwd.vishwakarma.t1")["deleted"]


def test_delete_table_unknown_id_raises(tmp_path):
    storage = _ingested_storage(tmp_path)

    with pytest.raises(ValueError, match="Unknown table_id"):
        delete_table(_fake_client(), storage, "pwd.vishwakarma.nope")


def test_reingesting_a_soft_deleted_table_brings_it_back(tmp_path):
    """The mark in tables.csv is per-run state, not a tombstone: an
    explicit re-ingest clears it and the next publish works again."""

    storage = _ingested_storage(tmp_path)
    lookups.soft_delete_table(storage, "pwd.vishwakarma.t1")

    source = tmp_path / "raw.txt"
    source.write_text("col_a integer NOT NULL, col_b integer NOT NULL")
    run(
        department="pwd", dataset="vishwakarma", table_name="t1",
        source_file=str(source), storage=storage, source_format="postgres_ddl",
    )

    assert lookups.get_table(storage, "pwd.vishwakarma.t1")["deleted"] == ""
    result = publish_table(_fake_client(), storage, "pwd.vishwakarma.t1")
    assert result["table_id"] == "pwd.vishwakarma.t1"


def test_pipeline_rejects_an_empty_slug_before_writing_anything(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    source = tmp_path / "raw.txt"
    source.write_text("col_a integer NOT NULL")

    with pytest.raises(ValueError, match="explicit ASCII id"):
        run(
            department="pwd", dataset="vishwakarma", table_name="सड़क",
            source_file=str(source), storage=storage, source_format="postgres_ddl",
        )

    # rejected before any lookup row was written -- no "pwd.vishwakarma."
    # table, no empty dataset id
    assert not storage.exists(lookups.TABLES_PATH)
    assert not storage.exists(lookups.DATASETS_PATH)

    # ...but the rejected run still left its audit row, keyed on the raw
    # name the operator typed
    row = storage.read_csv(lookups.RUNS_PATH)[0]
    assert row["table_id"] == "pwd.vishwakarma.सड़क"
    assert row["publish_status"] == "not_attempted"
    assert "explicit ASCII id" in row["error"]
