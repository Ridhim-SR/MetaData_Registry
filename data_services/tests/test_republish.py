"""Item 13: the republish command that closes the storage/OpenMetadata gap.

A run whose snapshot reached storage but not OpenMetadata (`unpublished`)
or was published and failed (`failed`) is now a state you can act on, one
command at a time, without re-ingesting anything."""

from unittest.mock import MagicMock

from src.schema_registry.openmetadata.publish import _unwrap
from src.schema_registry.pipeline import run
from src.schema_registry.registry import lookups
from src.schema_registry.republish import republish_unpublished
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
        entity.columns = getattr(request, "columns", None)
        return entity

    client.create_or_update.side_effect = _create_or_update
    return client


def _client_failing_on_table(table_name: str):
    """A fake server that rejects one specific table's CreateTableRequest
    and answers everything else normally."""

    client = _fake_client()
    inner = client.create_or_update.side_effect

    def _side_effect(request):
        if type(request).__name__ == "CreateTableRequest" and _unwrap(request.name) == table_name:
            raise RuntimeError("server said no")
        return inner(request)

    client.create_or_update.side_effect = _side_effect
    return client


def _ingest(storage, tmp_path, table_name: str, ddl: str = "col_a integer NOT NULL", **kwargs) -> None:
    if not lookups.department_exists(storage, "pwd"):
        lookups.register_department(storage, "pwd", "Public Works Department")
    source = tmp_path / f"{table_name}.txt"
    source.write_text(ddl)
    run(
        department="pwd", dataset="vishwakarma", table_name=table_name,
        source_file=str(source), storage=storage, source_format="postgres_ddl", **kwargs,
    )


def _runs_by_table(storage) -> dict:
    return {row["table_id"]: row for row in storage.read_csv(lookups.RUNS_PATH)}


def test_republish_publishes_storage_only_runs_and_marks_them(tmp_path):
    """The documented "publish later" workflow, done in bulk: run() without a
    client leaves the snapshot unpublished, republish() is the step that
    catches storage up with OpenMetadata."""

    storage = LocalObjectStorage(tmp_path / "storage")
    _ingest(storage, tmp_path, "t1")
    assert _runs_by_table(storage)["pwd.vishwakarma.t1"]["publish_status"] == "unpublished"

    results = republish_unpublished(storage, _fake_client())

    assert [r["status"] for r in results] == ["published"]
    assert results[0]["table_id"] == "pwd.vishwakarma.t1"
    assert results[0]["fully_qualified_name"].endswith(".t1")

    row = _runs_by_table(storage)["pwd.vishwakarma.t1"]
    assert row["publish_status"] == "published"
    assert row["error"] == ""
    # second call finds nothing left to do
    assert republish_unpublished(storage, _fake_client()) == []


def test_republish_fixes_a_run_whose_publish_failed(tmp_path):
    """run() with a client that errors leaves `failed` + the error text on
    the row; republishing the same snapshot must clear both."""

    storage = LocalObjectStorage(tmp_path / "storage")
    _ingest(storage, tmp_path, "t1")
    rows = _runs_by_table(storage)
    # simulate what run() recorded when publish_table() raised
    rows["pwd.vishwakarma.t1"]["publish_status"] = "failed"
    rows["pwd.vishwakarma.t1"]["error"] = "RuntimeError: server said no"
    storage.write_csv(lookups.RUNS_PATH, list(rows.values()))

    results = republish_unpublished(storage, _fake_client())

    assert [r["status"] for r in results] == ["published"]
    row = _runs_by_table(storage)["pwd.vishwakarma.t1"]
    assert row["publish_status"] == "published"
    assert row["error"] == ""


def test_republish_continues_after_one_table_fails(tmp_path):
    """One broken table must not stop the loop -- and its failure must be
    recorded on its own row while the others publish."""

    storage = LocalObjectStorage(tmp_path / "storage")
    _ingest(storage, tmp_path, "t1")
    _ingest(storage, tmp_path, "t2")

    results = republish_unpublished(storage, _client_failing_on_table("t2"))

    by_table = {r["table_id"]: r for r in results}
    assert by_table["pwd.vishwakarma.t1"]["status"] == "published"
    assert by_table["pwd.vishwakarma.t2"]["status"] == "failed"
    assert "server said no" in by_table["pwd.vishwakarma.t2"]["error"]

    rows = _runs_by_table(storage)
    assert rows["pwd.vishwakarma.t1"]["publish_status"] == "published"
    assert rows["pwd.vishwakarma.t2"]["publish_status"] == "failed"
    assert "server said no" in rows["pwd.vishwakarma.t2"]["error"]

    # the failed one is picked up again next time, the published one isn't
    assert [r["table_id"] for r in republish_unpublished(storage, _fake_client())] == ["pwd.vishwakarma.t2"]


def test_republish_skips_soft_deleted_tables(tmp_path):
    """A table the operator removed on purpose must never be re-published by
    a bulk republish."""

    storage = LocalObjectStorage(tmp_path / "storage")
    _ingest(storage, tmp_path, "t1")
    lookups.soft_delete_table(storage, "pwd.vishwakarma.t1")

    results = republish_unpublished(storage, _fake_client())

    assert [r["status"] for r in results] == ["skipped"]
    assert "soft-deleted" in results[0]["reason"]
