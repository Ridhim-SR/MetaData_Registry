import json
from types import SimpleNamespace

import pytest

from src.schema_registry.openmetadata import publish as publish_module
from src.schema_registry.openmetadata.publish import (
    publish_table_fixing_display,
)
from src.schema_registry.registry import lookups, paths
from src.storage.local import LocalObjectStorage

_TABLE_ID = "pwd.vishwakarma.t1"
_TS = "20260101T000000000000Z"
_FQN = "pwd.vishwakarma.public.t1"


@pytest.fixture
def storage(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.upsert_table(storage, _TABLE_ID, "pwd.vishwakarma", "t1", "public")
    storage.write_csv(
        paths.curated_schema_path("pwd", "vishwakarma", "t1", _TS),
        [
            {
                "name": "total_cost", "data_type": "numeric", "length": "", "scale": "2",
                "nullable": "False", "default": "", "business_description": "Total cost",
                "tag": "Financial", "glossary_term": "", "active": "True",
                "classification": "Public", "readable_type": "Decimal Number", "unit": "INR",
            }
        ],
    )
    return storage


class _FakeTable:
    def __init__(self, display, *, description=None):
        self.id = "id-1"
        self.columns = [SimpleNamespace(name="total_cost", dataTypeDisplay=display)]
        self._json = {
            "id": self.id,
            "fullyQualifiedName": _FQN,
            "description": description,
            "owners": [],
            "tags": [],
            "tableType": "Regular",
            "retentionPeriod": None,
            "sourceUrl": None,
        }

    def model_dump(self, mode="json"):
        return self._json


def _fake_client():
    from unittest.mock import MagicMock

    return MagicMock()


def _backups(storage):
    prefix = f"{publish_module._RECREATE_BACKUP_PREFIX}/{_TABLE_ID}"
    return [p for p in storage.list(prefix) if p.endswith(".json")]


def test_stale_display_is_backed_up_deleted_and_recreated(storage, monkeypatch):
    stale = _FakeTable("numeric", description="Kept by hand")
    fixed = _FakeTable("decimal number (inr)", description="Kept by hand")
    published = []
    _tables = [stale, fixed, fixed]

    def _fake_publish(client, storage_arg, table_id, **kwargs):
        published.append(table_id)
        return {"table_id": table_id, "fully_qualified_name": _FQN}

    monkeypatch.setattr(publish_module, "publish_table", _fake_publish)
    monkeypatch.setattr(publish_module, "_get_or_none", lambda *a, **k: _tables.pop(0))
    client = _fake_client()

    result = publish_table_fixing_display(client, storage, _TABLE_ID)

    assert result["status"] == "recreated"
    assert result["columns"] == ["total_cost"]
    assert published == [_TABLE_ID]
    client.delete.assert_called_once()
    assert client.delete.call_args.kwargs["hard_delete"] is True
    assert client.delete.call_args.kwargs["recursive"] is True
    assert client.delete.call_args.kwargs["entity_id"] == "id-1"

    backups = _backups(storage)
    assert len(backups) == 1
    backup = json.loads(storage.read_bytes(backups[0]).decode())
    assert backup["table_id"] == _TABLE_ID
    assert backup["entity"]["description"] == "Kept by hand"


def test_matching_display_publishes_without_deleting(storage, monkeypatch):
    current = _FakeTable("decimal number (inr)")
    published = []

    def _fake_publish(client, storage_arg, table_id, **kwargs):
        published.append(table_id)
        return {"table_id": table_id, "fully_qualified_name": _FQN}

    monkeypatch.setattr(publish_module, "publish_table", _fake_publish)
    monkeypatch.setattr(publish_module, "_get_or_none", lambda *a, **k: current)
    client = _fake_client()

    result = publish_table_fixing_display(client, storage, _TABLE_ID)

    assert result["status"] == "published"
    assert published == [_TABLE_ID]
    client.delete.assert_not_called()
    assert _backups(storage) == []


def test_dry_run_reports_stale_display_without_changing_anything(storage, monkeypatch):
    stale = _FakeTable("numeric")
    published = []

    monkeypatch.setattr(
        publish_module, "publish_table", lambda *a, **k: published.append(a) or {}
    )
    monkeypatch.setattr(publish_module, "_get_or_none", lambda *a, **k: stale)
    client = _fake_client()

    result = publish_table_fixing_display(client, storage, _TABLE_ID, dry_run=True)

    assert result["status"] == "would recreate"
    assert result["columns"] == ["total_cost"]
    assert published == []
    client.delete.assert_not_called()
    assert _backups(storage) == []


def test_missing_table_is_published_normally(storage, monkeypatch):
    published = []

    def _fake_publish(client, storage_arg, table_id, **kwargs):
        published.append(table_id)
        return {"table_id": table_id, "fully_qualified_name": _FQN}

    monkeypatch.setattr(publish_module, "publish_table", _fake_publish)
    monkeypatch.setattr(publish_module, "_get_or_none", lambda *a, **k: None)
    client = _fake_client()

    result = publish_table_fixing_display(client, storage, _TABLE_ID)

    assert result["status"] == "created"
    assert published == [_TABLE_ID]
    client.delete.assert_not_called()


def test_refuses_a_soft_deleted_registry_row(storage, monkeypatch):
    lookups.soft_delete_table(storage, _TABLE_ID)
    client = _fake_client()

    with pytest.raises(ValueError, match="soft-deleted"):
        publish_table_fixing_display(client, storage, _TABLE_ID)

    client.delete.assert_not_called()
