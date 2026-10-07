import boto3
import pytest
from moto import mock_aws

from src.schema_registry.registry import lookups
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


def test_lock_is_exclusive_across_storage_instances(bucket):
    """Two S3ObjectStorage objects stand in for two machines: while one
    holds the lock, the other can't take it, and gets it once released."""

    machine_a = _storage(bucket, prefix="dev")
    machine_b = _storage(bucket, prefix="dev", lock_timeout_seconds=0.2, lock_poll_seconds=0.05)

    with machine_a.lock("_lookups/tables.csv"):
        with pytest.raises(TimeoutError, match="held by"):
            with machine_b.lock("_lookups/tables.csv"):
                pass
    with machine_b.lock("_lookups/tables.csv"):
        pass
    assert machine_a.list("_locks/") == []  # released, nothing left behind


def test_expired_lock_is_taken_over(bucket):
    """A run that died holding the lock mustn't block everyone forever."""

    dead_run = _storage(bucket, lock_ttl_seconds=-1)  # its lock is born expired
    held = dead_run.lock("dept/table/pipeline")
    held.__enter__()  # never released

    with _storage(bucket, lock_timeout_seconds=1, lock_poll_seconds=0.05).lock("dept/table/pipeline"):
        pass


def test_different_paths_lock_independently(bucket):
    storage = _storage(bucket, lock_timeout_seconds=0.2, lock_poll_seconds=0.05)
    with storage.lock("a"):
        with storage.lock("b"):
            pass


def test_concurrent_registrations_from_two_machines_lose_no_rows(bucket):
    """The real risk the cross-machine lock exists for: many writers doing
    read-modify-write on one shared lookup file in the same bucket."""

    from concurrent.futures import ThreadPoolExecutor

    machines = [_storage(bucket, prefix="dev", lock_poll_seconds=0.01) for _ in range(4)]
    departments = [f"dept_{i}" for i in range(12)]
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda i: lookups.register_department(machines[i % 4], departments[i], departments[i]), range(12)))

    rows = machines[0].read_csv(lookups.DEPARTMENTS_PATH)
    assert sorted(r["department_id"] for r in rows) == sorted(departments)


def test_bytes_roundtrip_exactly(bucket):
    storage = _storage(bucket)
    data = "\ufeffname,data_type\r\nरजिस्टर,text\r\n".encode("utf-8")
    storage.write_bytes("inputs/x.csv", data)
    assert storage.read_bytes("inputs/x.csv") == data


def test_full_pipeline_run_works_against_s3_backed_storage(bucket, tmp_path, tmp_path_factory):
    """The whole point of the ObjectStorage abstraction: pipeline.run()
    shouldn't need to know or care that it's writing to S3 instead of the
    local filesystem -- same registration, ingest, curate, and column-
    removal-guard behavior either way."""

    storage = _storage(bucket)
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
