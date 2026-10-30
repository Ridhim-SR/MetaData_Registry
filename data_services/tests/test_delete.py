from pathlib import Path
from unittest.mock import MagicMock

from src.schema_registry.delete import Target, purge, restore, soft_delete
from src.schema_registry.registry import lookups
from src.storage.local import LocalObjectStorage
from src.storage import storage_from_env


def _storage(tmp_path: Path) -> LocalObjectStorage:
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    lookups.upsert_dataset(storage, "pwd.ds", "pwd", "Dataset")
    lookups.upsert_table(storage, "pwd.ds.t", "pwd.ds", "t", "public")
    storage.write_bytes("department/pwd/ds/t/curated/schemas/1.csv", b"schema")
    storage.write_bytes("inputs/pwd/ds/source.csv", b"source")
    return storage


def test_table_purge_removes_derived_data_but_keeps_shared_input(tmp_path):
    storage = _storage(tmp_path)

    result = purge(storage, Target("table", "pwd.ds.t"))

    assert result["storage_objects"] == 1
    assert not storage.exists("department/pwd/ds/t/curated/schemas/1.csv")
    assert storage.exists("inputs/pwd/ds/source.csv")
    assert lookups.get_table(storage, "pwd.ds.t") is None


def test_dataset_dry_run_does_not_change_storage_or_registry(tmp_path):
    storage = _storage(tmp_path)

    result = purge(storage, Target("dataset", "pwd.ds"), dry_run=True)

    assert result["tables"] == 1
    assert result["storage_objects"] == 2
    assert storage.exists("department/pwd/ds/t/curated/schemas/1.csv")
    assert storage.exists("inputs/pwd/ds/source.csv")
    assert lookups.get_table(storage, "pwd.ds.t") is not None


def test_unknown_dataset_scope_is_rejected(tmp_path):
    storage = _storage(tmp_path)

    import pytest
    with pytest.raises(ValueError, match="No registered tables matched"):
        purge(storage, Target("dataset", "pwd.missing"))


def test_soft_delete_retains_storage_and_restore_clears_marker(tmp_path):
    storage = _storage(tmp_path)
    client = MagicMock()

    result = soft_delete(storage, Target("table", "pwd.ds.t"), client=client)

    assert result["status"] == "soft_deleted"
    assert storage.exists("department/pwd/ds/t/curated/schemas/1.csv")
    assert lookups.get_table(storage, "pwd.ds.t")["deleted"]

    restored = restore(storage, Target("table", "pwd.ds.t"))

    assert restored["status"] == "restored"
    assert not lookups.get_table(storage, "pwd.ds.t")["deleted"]


def test_s3_deletion_requires_dedicated_credentials(monkeypatch):
    monkeypatch.setenv("WASABI_BUCKET", "bucket")
    monkeypatch.setenv("WASABI_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.delenv("WASABI_DELETE_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("WASABI_DELETE_SECRET_ACCESS_KEY", raising=False)

    import pytest
    with pytest.raises(ValueError, match="dedicated S3 credentials"):
        storage_from_env(delete_credentials=True)
