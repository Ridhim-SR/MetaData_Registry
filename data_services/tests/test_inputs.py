import csv

import pytest

from src.schema_registry import inputs
from src.storage.local import LocalObjectStorage


def _write_manifest(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["local_path", "storage_key"])
        writer.writerows(rows)


def test_upload_batch_resolves_relative_paths_and_uploads_through_one_client(tmp_path, monkeypatch):
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    (source_dir / "first.csv").write_bytes(b"first")
    (source_dir / "second.csv").write_bytes(b"second")
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, [
        ["sources/first.csv", "inputs/first/first.csv"],
        ["sources/second.csv", "inputs/second/second.csv"],
    ])
    storage = LocalObjectStorage(tmp_path / "storage")
    storage_factory_calls = []

    import src.storage as storage_module
    import src.utils.cli as cli_module
    import src.utils.config as config_module

    monkeypatch.setattr(config_module, "load_env", lambda: None)
    monkeypatch.setattr(storage_module, "storage_from_env", lambda: storage_factory_calls.append(True) or storage)
    confirmations = []
    monkeypatch.setattr(cli_module, "confirm_changes", confirmations.append)

    assert inputs._main(["upload-batch", str(manifest)]) == 0

    assert len(storage_factory_calls) == 1
    assert confirmations == [f"upload 2 file(s) listed in {manifest}"]
    assert storage.read_bytes("inputs/first/first.csv") == b"first"
    assert storage.read_bytes("inputs/second/second.csv") == b"second"


def test_upload_manifest_validates_all_sources_before_writing(tmp_path):
    (tmp_path / "present.csv").write_bytes(b"present")
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, [
        ["present.csv", "inputs/present.csv"],
        ["missing.csv", "inputs/missing.csv"],
    ])
    storage = LocalObjectStorage(tmp_path / "storage")

    with pytest.raises(FileNotFoundError, match="missing.csv"):
        inputs.upload_batch(storage, inputs.read_upload_manifest(manifest))

    assert storage.list("inputs/") == []


def test_upload_manifest_rejects_duplicate_and_escaping_storage_keys(tmp_path):
    (tmp_path / "one.csv").write_bytes(b"one")
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, [
        ["one.csv", "inputs/one.csv"],
        ["one.csv", "inputs/one.csv"],
    ])

    with pytest.raises(ValueError, match="duplicate storage key"):
        inputs.read_upload_manifest(manifest)

    _write_manifest(manifest, [["one.csv", "../outside.csv"]])
    with pytest.raises(ValueError, match="invalid storage key"):
        inputs.read_upload_manifest(manifest)
