from unittest.mock import MagicMock

import pytest
import requests
from metadata.ingestion.ometa.client import APIError

from src.schema_registry import lookups
from src.schema_registry.openmetadata_publish import _create_or_update, _get_by_name, _unwrap, publish_table
from src.schema_registry.pipeline import run
from src.storage.local import LocalObjectStorage


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """The retry tests below deliberately trigger tenacity's backoff --
    skip the actual wait so the suite doesn't slow down."""
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


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
    # re-run with a different (shrunk) column set -- should produce a newer
    # snapshot; allow_column_removal=True since this deliberately drops
    # columns from the previous run (see test_pipeline.py for the guard
    # that rejects this without it).
    ddl_file = tmp_path / "raw2.txt"
    ddl_file.write_text("only_col integer NOT NULL")
    run(
        department="pwd",
        dataset="vishwakarma",
        table_name="TBD_confirm_with_pwd",
        source_file=str(ddl_file),
        storage=storage,
        source_format="postgres_ddl",
        allow_column_removal=True,
    )

    client = _fake_client()
    result = publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    assert result["column_count"] == 1
    table_request = client.create_or_update.call_args_list[-1].args[0]
    assert [_unwrap(c.name) for c in table_request.columns] == ["only_col"]


def _api_error(status_code: int) -> APIError:
    error = APIError({"code": status_code, "message": "boom"})
    error._http_error = MagicMock(response=MagicMock(status_code=status_code))
    return error


def test_create_or_update_retries_on_connection_error_then_succeeds():
    client = MagicMock()
    client.create_or_update.side_effect = [
        requests.exceptions.ConnectionError("server unreachable"),
        requests.exceptions.ConnectionError("still unreachable"),
        "created",
    ]

    result = _create_or_update(client, MagicMock())

    assert result == "created"
    assert client.create_or_update.call_count == 3


def test_create_or_update_retries_on_5xx_then_succeeds():
    client = MagicMock()
    client.create_or_update.side_effect = [_api_error(503), "created"]

    result = _create_or_update(client, MagicMock())

    assert result == "created"
    assert client.create_or_update.call_count == 2


def test_create_or_update_does_not_retry_on_4xx():
    """A 4xx means the request itself is wrong (e.g. bad payload) --
    retrying it just fails the same way every time, slower."""

    client = MagicMock()
    client.create_or_update.side_effect = _api_error(400)

    with pytest.raises(APIError):
        _create_or_update(client, MagicMock())

    assert client.create_or_update.call_count == 1


def test_create_or_update_gives_up_after_max_attempts():
    client = MagicMock()
    client.create_or_update.side_effect = requests.exceptions.ConnectionError("down")

    with pytest.raises(requests.exceptions.ConnectionError):
        _create_or_update(client, MagicMock())

    assert client.create_or_update.call_count == 4  # stop_after_attempt(4)


def test_get_by_name_retries_on_connection_error():
    client = MagicMock()
    client.get_by_name.side_effect = [requests.exceptions.ConnectionError("blip"), "found"]

    result = _get_by_name(client, MagicMock(), "some.fqn")

    assert result == "found"
    assert client.get_by_name.call_count == 2
