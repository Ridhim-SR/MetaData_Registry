import hashlib

import pytest
from unittest.mock import MagicMock

from src.schema_registry import gdrive_mirror
from src.schema_registry.gdrive_mirror import (
    dataset_details_text,
    mirror_after_run,
    mirror_all,
)
from src.schema_registry.pipeline import run
from src.schema_registry.registry import lookups, paths
from src.storage.gdrive import GoogleDriveConfigError, GoogleDriveMirror, mirror_from_env
from src.storage.local import LocalObjectStorage


class FakeMirror:
    def __init__(self, fail: bool = False):
        self.uploads: dict[str, tuple[bytes, str]] = {}
        self.fail = fail

    def upload_bytes(self, path, data, mimetype="text/csv", skip_if_unchanged=False,
                     compare_latest=False):
        if self.fail:
            raise RuntimeError("drive is down")
        self.uploads[path] = (data, mimetype)
        return f"id-{len(self.uploads)}"

    def upload_text(self, path, text, mimetype="text/plain", skip_if_unchanged=False):
        return self.upload_bytes(
            path, text.encode("utf-8"), mimetype=mimetype,
            skip_if_unchanged=skip_if_unchanged,
        )


def _storage_with_department(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    return storage


def _run_table(tmp_path, storage, name="t1"):
    source = tmp_path / f"{name}.txt"
    source.write_text("sno integer NOT NULL, total_cost double precision")
    return run(
        department="pwd",
        dataset="vishwakarma",
        table_name=name,
        source_file=str(source),
        storage=storage,
        category="CAT-3",
        owner="Public Works Department",
        dataset_description="Financial management of sanctioned projects.",
    )


def test_dataset_details_text_is_deterministic_and_complete():
    text = dataset_details_text(
        "pwd", "Public Works Department", "vishwakarma",
        {
            "category": "CAT-3",
            "dataset_type": "Administrative",
            "schema_source": "Department Provided",
            "owner": "PWD",
            "steward": "",
            "frequency": "Daily",
            "timeline": "2019 - ongoing",
            "api_available": "N",
            "dataset_description": "Line one.\nLine two.",
        },
    )
    assert text == dataset_details_text(
        "pwd", "Public Works Department", "vishwakarma",
        {
            "category": "CAT-3",
            "dataset_type": "Administrative",
            "schema_source": "Department Provided",
            "owner": "PWD",
            "steward": "",
            "frequency": "Daily",
            "timeline": "2019 - ongoing",
            "api_available": "N",
            "dataset_description": "Line one.\nLine two.",
        },
    )
    assert "Dataset ID:    pwd.vishwakarma" in text
    assert "Category: CAT-3" in text
    assert "Dataset Type: Administrative" in text
    assert "Description:\n  Line one.\n  Line two." in text


def test_mirror_after_run_uploads_curated_and_dataset_details(tmp_path, monkeypatch):
    storage = _storage_with_department(tmp_path)
    result = _run_table(tmp_path, storage)
    fake = FakeMirror()
    monkeypatch.setattr(gdrive_mirror, "mirror_from_env", lambda: fake)

    mirror_after_run(
        storage,
        department_id="pwd",
        department_name="Public Works Department",
        dataset_name="vishwakarma",
        dataset_slug="vishwakarma",
        table_slug="t1",
        timestamp=result["timestamp"],
    )

    curated = paths.curated_schema_path(
        "pwd", "vishwakarma", "t1", result["timestamp"]
    )
    assert curated in fake.uploads
    assert fake.uploads[curated][0] == storage.read_bytes(curated)
    details = paths.dataset_details_path("pwd", "vishwakarma")
    assert details in fake.uploads
    assert "Dataset Type:" in fake.uploads[details][0].decode()
    assert "CAT-3" in fake.uploads[details][0].decode()


def test_mirror_after_run_never_raises_when_drive_fails(tmp_path, monkeypatch):
    storage = _storage_with_department(tmp_path)
    result = _run_table(tmp_path, storage)
    monkeypatch.setattr(gdrive_mirror, "mirror_from_env", lambda: FakeMirror(fail=True))

    mirror_after_run(
        storage,
        department_id="pwd",
        department_name="PWD",
        dataset_name="vishwakarma",
        dataset_slug="vishwakarma",
        table_slug="t1",
        timestamp=result["timestamp"],
    )


def test_mirror_all_backfills_every_table_and_details(tmp_path):
    storage = _storage_with_department(tmp_path)
    _run_table(tmp_path, storage, "t1")
    _run_table(tmp_path, storage, "t2")

    from src.schema_registry.catalog import parse_catalog

    departments = parse_catalog(
        """
departments:
  pwd:
    name: Public Works Department
    datasets:
      vishwakarma:
        category: CAT-3
        dataset_type: Administrative
        tables:
          t1:
            source: storage:inputs/pwd/t1.txt
          t2:
            source: storage:inputs/pwd/t2.txt
"""
    )
    fake = FakeMirror()
    done = mirror_all(storage, departments, mirror=fake)

    assert paths.dataset_details_path("pwd", "vishwakarma") in fake.uploads
    for table in ("t1", "t2"):
        latest = lookups.latest_curated_snapshot_path(storage, "pwd", "vishwakarma", table)
        assert latest in fake.uploads
        assert fake.uploads[latest][0] == storage.read_bytes(latest)
    assert paths.dataset_details_path("pwd", "vishwakarma") in done


def test_mirror_from_env_is_off_when_folder_is_blank(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("GOOGLE_DRIVE_FOLDER_ID", raising=False)
    for name in ("LOCAL", "DEV", "PROD"):
        monkeypatch.delenv(f"{name}_GOOGLE_DRIVE_FOLDER_ID", raising=False)

    from src.storage.gdrive import reset_cache

    reset_cache()
    assert mirror_from_env() is None


def test_mirror_from_env_needs_credentials_when_folder_is_set(monkeypatch):
    from src.storage.gdrive import reset_cache

    reset_cache()
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "folder-123")
    monkeypatch.delenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE", raising=False)
    monkeypatch.delenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", raising=False)

    with pytest.raises(GoogleDriveConfigError, match="no service account"):
        mirror_from_env()


def test_upload_updates_an_existing_file_instead_of_creating_a_duplicate():
    pytest.importorskip("googleapiclient.http")

    mirror = GoogleDriveMirror("root")
    mirror._folder_cache[("department",)] = "dept-folder"
    mirror._folder_cache[("department", "pwd")] = "pwd-folder"
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": "existing-file"}]
    }
    mirror._service = service

    mirror.upload_bytes("department/pwd/details.txt", b"hello", mimetype="text/plain")

    service.files.return_value.update.assert_called_once()
    assert service.files.return_value.update.call_args.kwargs["fileId"] == "existing-file"
    service.files.return_value.create.assert_not_called()


def test_timestamped_snapshot_is_skipped_when_content_is_unchanged():
    pytest.importorskip("googleapiclient.http")

    mirror = GoogleDriveMirror("root")
    for index in range(1, 7):
        mirror._folder_cache[
            ("department", "pwd", "ds", "t1", "curated", "schemas")[:index]
        ] = f"folder-{index}"
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": "old", "name": "20260101T000000000000Z.csv",
                   "md5Checksum": hashlib.md5(b"same").hexdigest()}]
    }
    mirror._service = service

    result = mirror.upload_bytes(
        "department/pwd/ds/t1/curated/schemas/20260202T000000000000Z.csv",
        b"same", compare_latest=True,
    )

    assert result is None
    service.files.return_value.create.assert_not_called()
    service.files.return_value.update.assert_not_called()


def test_upload_skips_rewriting_an_identical_dataset_details_file():
    pytest.importorskip("googleapiclient.http")

    mirror = GoogleDriveMirror("root")
    mirror._folder_cache[("department",)] = "dept-folder"
    mirror._folder_cache[("department", "pwd")] = "pwd-folder"
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": "details", "name": "dataset_details.txt",
                   "md5Checksum": hashlib.md5(b"same details").hexdigest()}]
    }
    mirror._service = service

    result = mirror.upload_text(
        "department/pwd/dataset_details.txt", "same details", skip_if_unchanged=True
    )

    assert result is None
    service.files.return_value.update.assert_not_called()
    service.files.return_value.create.assert_not_called()


def test_timestamped_snapshot_is_uploaded_when_content_changed():
    pytest.importorskip("googleapiclient.http")

    def _result(payload):
        call = MagicMock()
        call.execute.return_value = payload
        return call

    mirror = GoogleDriveMirror("root")
    for index in range(1, 7):
        mirror._folder_cache[
            ("department", "pwd", "ds", "t1", "curated", "schemas")[:index]
        ] = f"folder-{index}"
    service = MagicMock()
    service.files.return_value.list.side_effect = lambda **kwargs: _result(
        {"files": [{"id": "old", "name": "20260101T000000000000Z.csv",
                    "md5Checksum": hashlib.md5(b"old").hexdigest()}]}
        if kwargs["q"].startswith("'") else {"files": []}
    )
    service.files.return_value.create.return_value.execute.return_value = {"id": "new"}
    mirror._service = service

    result = mirror.upload_bytes(
        "department/pwd/ds/t1/curated/schemas/20260202T000000000000Z.csv",
        b"new", compare_latest=True,
    )

    assert result == "new"
    service.files.return_value.create.assert_called_once()


def test_pipeline_run_survives_a_broken_drive_configuration(tmp_path, monkeypatch):
    """The Wasabi write already happened; a bad Drive key must not fail it."""

    from src.storage.gdrive import reset_cache

    reset_cache()
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "folder-123")
    monkeypatch.setenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE", str(tmp_path / "missing.json"))
    monkeypatch.delenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", raising=False)

    storage = _storage_with_department(tmp_path)
    result = _run_table(tmp_path, storage, "t1")

    assert storage.exists(result["curated_path"])
    reset_cache()
