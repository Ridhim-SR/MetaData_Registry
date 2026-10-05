from src.storage import storage_from_env
from src.storage.local import LocalObjectStorage
from src.storage.s3 import S3ObjectStorage


def test_defaults_to_local_storage(tmp_path, monkeypatch):
    monkeypatch.delenv("WASABI_BUCKET", raising=False)
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))

    storage = storage_from_env()

    assert isinstance(storage, LocalObjectStorage)
    assert storage.root == tmp_path


def test_switches_to_s3_when_wasabi_bucket_is_set(monkeypatch):
    monkeypatch.setenv("WASABI_BUCKET", "my-bucket")
    monkeypatch.setenv("WASABI_PREFIX", "schema-registry")
    monkeypatch.setenv("WASABI_ENDPOINT_URL", "https://s3.us-east-1.wasabisys.com")

    storage = storage_from_env()

    assert isinstance(storage, S3ObjectStorage)
    assert storage.bucket == "my-bucket"
    assert storage.prefix == "schema-registry"
