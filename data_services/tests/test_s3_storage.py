import boto3
import pytest
from moto import mock_aws

from src.schema_registry import lookups
from src.schema_registry.pipeline import run
from src.storage.s3 import S3ObjectStorage


@pytest.fixture
def bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="test-bucket")
        yield "test-bucket"


def _storage(bucket, prefix="", **kwargs):
    return S3ObjectStorage(bucket=bucket, prefix=prefix, region_name="us-east-1", **kwargs)


def test_write_then_read_csv_roundtrips(bucket):
    storage = _storage(bucket)
    rows = [{"name": "col_a", "data_type": "integer"}, {"name": "col_b", "data_type": "text"}]
    storage.write_csv("dept/dataset/table/curated/schemas/ts.csv", rows)

    assert storage.read_csv("dept/dataset/table/curated/schemas/ts.csv") == rows


def test_exists_true_and_false(bucket):
    storage = _storage(bucket)
    storage.write_csv("a.csv", [{"x": "1"}])

    assert storage.exists("a.csv") is True
    assert storage.exists("missing.csv") is False


def test_list_returns_sorted_relative_paths_under_prefix(bucket):
    storage = _storage(bucket)
    storage.write_csv("dept/table/curated/schemas/20260101T000000Z.csv", [{"x": "1"}])
    storage.write_csv("dept/table/curated/schemas/20260102T000000Z.csv", [{"x": "1"}])
    storage.write_csv("dept/table/raw/schemas/20260101T000000Z.csv", [{"x": "1"}])

    files = storage.list("dept/table/curated/schemas/")

    assert files == [
        "dept/table/curated/schemas/20260101T000000Z.csv",
        "dept/table/curated/schemas/20260102T000000Z.csv",
    ]


def test_list_empty_prefix_returns_empty_list(bucket):
    storage = _storage(bucket)
    assert storage.list("nothing/here/") == []


def test_write_empty_rows_produces_empty_object(bucket):
    storage = _storage(bucket)
    storage.write_csv("empty.csv", [])

    assert storage.exists("empty.csv") is True
    assert storage.read_csv("empty.csv") == []


def test_prefix_is_applied_to_the_real_key_but_stripped_back_off_for_callers(bucket):
    storage = _storage(bucket, prefix="myprefix")
    storage.write_csv("a/b.csv", [{"x": "1"}])

    raw = boto3.client("s3", region_name="us-east-1").get_object(Bucket=bucket, Key="myprefix/a/b.csv")
    content = raw["Body"].read().decode()
    assert "x" in content and "1" in content

    assert storage.list("a/") == ["a/b.csv"]
    assert storage.exists("a/b.csv") is True


def test_lock_path_is_stable_and_local(bucket, tmp_path):
    """Same input -> same lock file (so FileLock actually serializes
    concurrent access to it), different inputs -> different files, and it's
    a real local filesystem path, not an S3 key -- see the class docstring
    for why locking stays local-only for now."""

    storage = _storage(bucket, lock_dir=tmp_path / "locks")

    path1 = storage.lock_path("dept/table/pipeline")
    path2 = storage.lock_path("dept/table/pipeline")
    path3 = storage.lock_path("other/table/pipeline")

    assert path1 == path2
    assert path1 != path3
    assert path1.startswith(str(tmp_path / "locks"))


def test_full_pipeline_run_works_against_s3_backed_storage(bucket, tmp_path, tmp_path_factory):
    """The whole point of the ObjectStorage abstraction: pipeline.run()
    shouldn't need to know or care that it's writing to S3 instead of the
    local filesystem -- same registration, ingest, curate, and column-
    removal-guard behavior either way."""

    storage = _storage(bucket, lock_dir=tmp_path_factory.mktemp("locks"))
    lookups.register_department(storage, "pwd", "Public Works Department")

    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("sno integer NOT NULL, firm_name character varying(100)")

    result = run(
        department="pwd", dataset="vishwakarma", table_name="t1",
        source_file=str(ddl_file), storage=storage, source_format="postgres_ddl",
    )

    assert result["column_count"] == 2
    assert storage.exists(result["raw_path"])
    assert storage.exists(result["curated_path"])
    assert storage.read_csv("_lookups/tables.csv")[0]["table_id"] == "pwd.vishwakarma.t1"
