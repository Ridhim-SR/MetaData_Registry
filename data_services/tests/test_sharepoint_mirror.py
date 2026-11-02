import pytest

from src.schema_registry import sharepoint_mirror
from src.schema_registry.sharepoint_mirror import (
    dataset_details_text,
    mirror_after_run,
    mirror_all,
)
from src.schema_registry.pipeline import run
from src.schema_registry.registry import lookups, paths
from src.storage.sharepoint import SharePointConfigError, SharePointMirror, mirror_from_env, reset_cache
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
    monkeypatch.setattr(sharepoint_mirror, "mirror_from_env", lambda: fake)

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
    monkeypatch.setattr(sharepoint_mirror, "mirror_from_env", lambda: FakeMirror(fail=True))

    mirror_after_run(
        storage,
        department_id="pwd",
        department_name="PWD",
        dataset_name="vishwakarma",
        dataset_slug="vishwakarma",
        table_slug="t1",
        timestamp=result["timestamp"],
    )


def test_mirror_all_backfills_every_table_and_details(tmp_path, monkeypatch):
    monkeypatch.setattr(sharepoint_mirror, "_current_branch", lambda: "main")
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


def test_mirror_all_rejects_non_main_branch(tmp_path, monkeypatch):
    monkeypatch.setattr(sharepoint_mirror, "_current_branch", lambda: "feature/test")
    with pytest.raises(PermissionError, match="only on the 'main' branch"):
        mirror_all(_storage_with_department(tmp_path), [], mirror=FakeMirror())


def test_mirror_from_env_is_off_when_sharepoint_is_blank(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    for setting in ("LOCAL_MIRROR_FOLDER",):
        monkeypatch.delenv(f"SHAREPOINT_{setting}", raising=False)

    reset_cache()
    assert mirror_from_env() is None


def test_mirror_from_env_requires_all_settings(monkeypatch):
    reset_cache()
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("SHAREPOINT_LOCAL_MIRROR_FOLDER", "")

    assert mirror_from_env() is None


def test_local_mirror_copies_and_skips_identical_files(tmp_path):
    mirror = SharePointMirror(str(tmp_path / "sharepoint"))
    relative = "department/pwd/dataset/details.txt"
    destination = mirror.upload_bytes(relative, b"metadata", skip_if_unchanged=True)

    assert destination is not None
    assert (tmp_path / "sharepoint" / relative).read_bytes() == b"metadata"
    assert mirror.upload_bytes(relative, b"metadata", skip_if_unchanged=True) is None

def test_pipeline_run_survives_a_broken_sharepoint_configuration(tmp_path, monkeypatch):
    """The Wasabi write already happened; an unconfigured mirror must not fail it."""

    reset_cache()
    monkeypatch.delenv("SHAREPOINT_LOCAL_MIRROR_FOLDER", raising=False)
    storage = _storage_with_department(tmp_path)
    result = _run_table(tmp_path, storage, "t1")

    assert storage.exists(result["curated_path"])
    reset_cache()
