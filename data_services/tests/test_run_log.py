"""Items 11-13: the original submission is preserved, every run (even a
failed one) leaves an audit row with its diff, and an unpublished/failed
publish is recorded so it can be republished."""

import hashlib
from unittest.mock import MagicMock

import pytest

from src.schema_registry.openmetadata.publish import _unwrap
from src.schema_registry.pipeline import run
from src.schema_registry.registry import lookups
from src.storage.local import LocalObjectStorage


def _storage_with_department(tmp_path, department_id="pwd"):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, department_id, department_id.upper())
    return storage


def _write(tmp_path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def _runs(storage) -> list[dict]:
    return storage.read_csv(lookups.RUNS_PATH)


def test_original_submission_is_stored_with_its_sha256(tmp_path):
    """Item 11: raw/schemas/ only holds the parser's output, so a parser bug
    used to destroy the only evidence of what the department sent."""

    source = _write(tmp_path, "raw.txt", "sno integer NOT NULL, total_cost double precision")
    storage = _storage_with_department(tmp_path)

    result = run(
        department="pwd", dataset="vishwakarma", table_name="t1",
        source_file=source, storage=storage, source_format="postgres_ddl",
    )

    raw_bytes = open(source, "rb").read()
    digest = hashlib.sha256(raw_bytes).hexdigest()

    assert storage.exists(result["source_path"])
    assert result["source_path"].startswith("department/pwd/vishwakarma/t1/raw/source/")
    assert result["source_path"].endswith(".txt")
    assert storage.read_bytes(result["source_path"]) == raw_bytes

    # the hash is written next to the bytes, and both agree with each other
    assert storage.exists(result["source_hash_path"])
    assert storage.read_bytes(result["source_hash_path"]).decode().strip() == digest
    assert result["source_hash"] == digest


def test_submission_is_the_original_bytes_not_a_reparse(tmp_path):
    source = _write(tmp_path, "raw.txt", "col with, \"quotes\", and\ttabs\n")
    storage = _storage_with_department(tmp_path)

    result = run(
        department="pwd", dataset="vishwakarma", table_name="t1",
        source_file=source, storage=storage, source_format="postgres_ddl",
    )

    assert storage.read_bytes(result["source_path"]) == open(source, "rb").read()


def test_run_log_row_on_success(tmp_path, monkeypatch):
    """Item 12: who ran it, what changed, and whether it was published."""

    monkeypatch.setenv("OPERATOR", "ci-bot")
    source = _write(tmp_path, "raw.txt", "sno integer NOT NULL, total_cost double precision")
    storage = _storage_with_department(tmp_path)

    result = run(
        department="pwd", dataset="vishwakarma", table_name="t1",
        source_file=source, storage=storage, source_format="postgres_ddl",
    )

    rows = _runs(storage)
    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == result["run_id"]
    assert row["table_id"] == "pwd.vishwakarma.t1"
    assert row["ts"]
    assert row["mode"] == "initial_load"
    assert row["source_hash"] == result["source_hash"]
    assert row["operator"] == "ci-bot"
    assert row["added"] == "2"
    assert row["removed"] == "0"
    assert row["changed"] == "0"
    assert row["publish_status"] == "unpublished"  # storage-only run
    assert row["error"] == ""


def test_run_log_row_written_even_when_the_run_fails(tmp_path):
    """The whole point of the audit row: a rejected partial submission must
    still say what it was missing instead of vanishing."""

    storage = _storage_with_department(tmp_path)
    v1 = _write(tmp_path, "v1.txt", "col_a integer NOT NULL, col_b character varying(50)")
    run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=v1, storage=storage)

    v2 = _write(tmp_path, "v2.txt", "col_a integer NOT NULL")  # col_b missing
    with pytest.raises(ValueError, match="col_b"):
        run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=v2, storage=storage)

    rows = _runs(storage)
    assert len(rows) == 2
    failed = rows[1]
    assert "col_b" in failed["error"]
    assert failed["publish_status"] == "not_attempted"  # no snapshot was written
    assert failed["mode"] == "full_refresh"  # diff computed before the guard
    assert failed["removed"] == "1"


def test_run_log_records_the_processing_mode(tmp_path):
    """README used to list "no mode is tracked explicitly" as a known
    limitation: initial_load / append / update / full_refresh now show up in
    the log."""

    storage = _storage_with_department(tmp_path)

    run(department="pwd", dataset="d", table_name="t1",
        source_file=_write(tmp_path, "v1.txt", "col_a integer NOT NULL"), storage=storage)
    run(department="pwd", dataset="d", table_name="t1",
        source_file=_write(tmp_path, "v2.txt", "col_a integer NOT NULL, col_b character varying(50)"), storage=storage)
    run(department="pwd", dataset="d", table_name="t1",
        source_file=_write(tmp_path, "v3.txt", "col_a bigint NOT NULL, col_b character varying(50)"), storage=storage)
    run(department="pwd", dataset="d", table_name="t1",
        source_file=_write(tmp_path, "v4.txt", "col_a bigint NOT NULL"), storage=storage,
        allow_column_removal=True)

    rows = _runs(storage)
    assert [r["mode"] for r in rows] == ["initial_load", "append", "update", "full_refresh"]
    assert [(r["added"], r["removed"], r["changed"]) for r in rows] == [
        ("1", "0", "0"),
        ("1", "0", "0"),
        ("0", "0", "1"),
        ("0", "1", "0"),
    ]


def test_per_run_diff_file_names_what_changed(tmp_path):
    """Type and nullability changes used to pass unnoticed on their way to
    OpenMetadata -- the diff is where they show up."""

    storage = _storage_with_department(tmp_path)
    run(department="pwd", dataset="d", table_name="t1",
        source_file=_write(tmp_path, "v1.txt", "col_a integer NOT NULL"), storage=storage)

    result = run(
        department="pwd", dataset="d", table_name="t1",
        source_file=_write(tmp_path, "v2.txt", "col_a character varying(50)"), storage=storage,
    )

    diff = storage.read_csv(result["diff_path"])
    by_field = {row["field"]: row for row in diff if row["change"] == "changed"}
    assert by_field["data_type"]["before"] == "integer"
    assert by_field["data_type"]["after"] == "character varying"
    assert by_field["nullable"]["before"] == "False"
    assert by_field["nullable"]["after"] == "True"


def test_diff_marks_added_and_removed_columns(tmp_path):
    storage = _storage_with_department(tmp_path)
    run(department="pwd", dataset="d", table_name="t1",
        source_file=_write(tmp_path, "v1.txt", "col_a integer NOT NULL, col_b integer NOT NULL"), storage=storage)

    result = run(
        department="pwd", dataset="d", table_name="t1",
        source_file=_write(tmp_path, "v2.txt", "col_a integer NOT NULL, col_c integer NOT NULL"),
        storage=storage, allow_column_removal=True,
    )

    diff = storage.read_csv(result["diff_path"])
    assert {(row["change"], row["column"]) for row in diff} == {
        ("added", "col_c"),
        ("removed", "col_b"),
    }


def test_failed_publish_is_recorded_so_it_can_be_republished(tmp_path):
    """Item 13: the snapshot is already in storage when publish runs, so a
    failure there used to leave storage and OpenMetadata silently out of
    sync with nothing recording it."""

    source = _write(tmp_path, "raw.txt", "sno integer NOT NULL")
    storage = _storage_with_department(tmp_path)
    client = MagicMock()
    client.get_by_name.side_effect = Exception("Entity not found")
    client.create_or_update.side_effect = RuntimeError("server said no")

    with pytest.raises(RuntimeError, match="server said no"):
        run(department="pwd", dataset="vishwakarma", table_name="t1",
            source_file=source, storage=storage, openmetadata_client=client)

    row = _runs(storage)[0]
    assert row["publish_status"] == "failed"
    assert "RuntimeError: server said no" in row["error"]
    # ...and the snapshot it failed to publish is still there for republish
    assert storage.exists(lookups.latest_curated_snapshot_path(storage, "pwd", "vishwakarma", "t1"))


def test_published_run_is_marked_published(tmp_path):
    source = _write(tmp_path, "raw.txt", "sno integer NOT NULL")
    storage = _storage_with_department(tmp_path)
    client = MagicMock()
    client.get_by_name.side_effect = Exception("Entity not found")

    def _create(request):
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

    client.create_or_update.side_effect = _create

    run(department="pwd", dataset="vishwakarma", table_name="t1",
        source_file=source, storage=storage, openmetadata_client=client)

    assert _runs(storage)[0]["publish_status"] == "published"


def test_invalid_category_never_reaches_the_registry(tmp_path):
    """Item 14 (dataset level): "cat3" used to be stored as-is and published
    as a brand-new tag next to the real CAT-3."""

    source = _write(tmp_path, "raw.txt", "sno integer NOT NULL")
    storage = _storage_with_department(tmp_path)

    with pytest.raises(ValueError, match="unknown category 'cat3'"):
        run(department="pwd", dataset="vishwakarma", table_name="t1",
            source_file=source, storage=storage, category="cat3")

    assert lookups.get_dataset(storage, "pwd.vishwakarma") is None
    # ...and the rejected run still left its audit row
    assert _runs(storage)[0]["publish_status"] == "not_attempted"
    assert "unknown category" in _runs(storage)[0]["error"]
