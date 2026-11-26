import csv
import threading

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

    assert inputs._main(["upload-batch", str(manifest), "--workers", "2"]) == 0

    assert len(storage_factory_calls) == 1
    assert confirmations == [f"upload 2 file(s) listed in {manifest}"]
    assert storage.read_bytes("inputs/first/first.csv") == b"first"
    assert storage.read_bytes("inputs/second/second.csv") == b"second"


def test_upload_batch_uploads_files_concurrently(tmp_path):
    """A large manifest must not be one round trip after another. Two files
    are enough to prove the writes overlap: the barrier only releases when
    both workers are inside write_bytes at the same time."""

    class _OverlapStorage(LocalObjectStorage):
        def __init__(self, root):
            super().__init__(root)
            self.barrier = threading.Barrier(2)
            self.lock = threading.Lock()
            self.active = 0
            self.peak = 0

        def write_bytes(self, path, data):
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            try:
                self.barrier.wait(timeout=5)
                super().write_bytes(path, data)
            finally:
                with self.lock:
                    self.active -= 1

    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    uploads = []
    for name in ("first", "second"):
        source = source_dir / f"{name}.csv"
        source.write_bytes(name.encode())
        uploads.append((source, f"inputs/{name}.csv"))

    storage = _OverlapStorage(tmp_path / "storage")
    results = inputs.upload_batch(storage, uploads, workers=2)

    assert storage.peak == 2
    assert [key for key, _, _ in results] == ["inputs/first.csv", "inputs/second.csv"]
    assert storage.read_bytes("inputs/second.csv") == b"second"


def test_upload_batch_workers_one_stays_serial(tmp_path):
    source = tmp_path / "one.csv"
    source.write_bytes(b"one")
    storage = LocalObjectStorage(tmp_path / "storage")

    assert inputs.upload_batch(storage, [(source, "inputs/one.csv")], workers=1) == [
        ("inputs/one.csv", 3, inputs.sha256(b"one"))
    ]


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
