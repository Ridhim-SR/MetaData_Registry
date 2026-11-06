"""Real-MinIO integration tests for the S3 storage/lock code path.

These are opt-in. They are skipped (with the reason in pytest's -rs output)
unless the caller explicitly provides a MinIO/S3 endpoint:

    SDA_MINIO_INTEGRATION=1
    SDA_MINIO_ENDPOINT=http://localhost:9000
    SDA_MINIO_BUCKET=sda-local
    SDA_MINIO_REGION=us-east-1                  # optional, defaults to us-east-1
    SDA_MINIO_ACCESS_KEY_ID=minioadmin
    SDA_MINIO_SECRET_ACCESS_KEY=minioadmin

The Moto tests in test_s3_storage.py stay in place: they are fast, run
everywhere, and cover the same API surface. These tests add the thing Moto
cannot prove -- that a real S3-compatible server enforces the conditional
writes the cross-machine lock depends on, and that concurrent read-modify-write
updates lose no rows against it.

Every object lives under a unique ``tests/minio-integration/<label>-<uuid>``
prefix and is deleted in a ``finally`` block, so a failed run does not
contaminate later runs.

For a bounded stress run (not part of normal PR CI), set
``SDA_MINIO_STRESS_ROUNDS`` to repeat the concurrency case:

    SDA_MINIO_STRESS_ROUNDS=50 python -m pytest tests/test_s3_minio_integration.py -q -rs
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import pytest

from src.schema_registry.registry import lookups
from src.storage.s3 import S3ObjectStorage

_ENDPOINT = os.environ.get("SDA_MINIO_ENDPOINT", "").strip()
_BUCKET = os.environ.get("SDA_MINIO_BUCKET", "").strip()
_ACCESS_KEY_ID = os.environ.get("SDA_MINIO_ACCESS_KEY_ID", "").strip()
_SECRET_ACCESS_KEY = os.environ.get("SDA_MINIO_SECRET_ACCESS_KEY", "").strip()
_REGION = os.environ.get("SDA_MINIO_REGION", "").strip() or "us-east-1"
_STRESS_ROUNDS = int(os.environ.get("SDA_MINIO_STRESS_ROUNDS", "1"))


def _configuration_problem() -> str | None:
    if os.environ.get("SDA_MINIO_INTEGRATION", "").strip() != "1":
        return (
            "real-MinIO integration tests are opt-in: set SDA_MINIO_INTEGRATION=1 "
            "and SDA_MINIO_ENDPOINT/BUCKET/ACCESS_KEY_ID/SECRET_ACCESS_KEY "
            "(see data_services/README.md)"
        )
    missing = [
        name
        for name, value in {
            "SDA_MINIO_ENDPOINT": _ENDPOINT,
            "SDA_MINIO_BUCKET": _BUCKET,
            "SDA_MINIO_ACCESS_KEY_ID": _ACCESS_KEY_ID,
            "SDA_MINIO_SECRET_ACCESS_KEY": _SECRET_ACCESS_KEY,
        }.items()
        if not value
    ]
    if missing:
        return (
            "SDA_MINIO_INTEGRATION=1 but the MinIO connection settings are "
            f"incomplete: {', '.join(missing)}"
        )
    return None


_PROBLEM = _configuration_problem()
requires_minio_integration = pytest.mark.skipif(_PROBLEM is not None, reason=_PROBLEM or "")


def _storage(prefix: str, **kwargs) -> S3ObjectStorage:
    return S3ObjectStorage(
        bucket=_BUCKET,
        prefix=prefix,
        endpoint_url=_ENDPOINT,
        aws_access_key_id=_ACCESS_KEY_ID,
        aws_secret_access_key=_SECRET_ACCESS_KEY,
        region_name=_REGION,
        lock_timeout_seconds=kwargs.pop("lock_timeout_seconds", 30),
        lock_poll_seconds=kwargs.pop("lock_poll_seconds", 0.02),
        **kwargs,
    )


def _prefix(label: str) -> str:
    return f"tests/minio-integration/{label}-{uuid.uuid4().hex}"


@requires_minio_integration
def test_real_minio_enforces_the_conditional_lock_writes():
    """If-None-Match must be honored, or two machines can hold one lock."""

    prefix = _prefix("lock")
    holder = _storage(prefix)
    contender = _storage(prefix, lock_timeout_seconds=0.5, lock_poll_seconds=0.05)
    try:
        with holder.lock(lookups.DEPARTMENTS_PATH):
            with pytest.raises(TimeoutError, match="held by"):
                with contender.lock(lookups.DEPARTMENTS_PATH):
                    pass
        with contender.lock(lookups.DEPARTMENTS_PATH):
            pass
        assert holder.list("_locks/") == []
    finally:
        holder.delete_prefix("")


@requires_minio_integration
def test_real_minio_concurrent_registrations_keep_every_row():
    """The Moto scenario, against a real S3 server: 4 storage instances are
    4 machines doing read-modify-write on one shared lookup CSV. Every unique
    department row must survive, and no lock may be left behind."""

    assert _STRESS_ROUNDS >= 1, "SDA_MINIO_STRESS_ROUNDS must be at least 1"

    for round_number in range(_STRESS_ROUNDS):
        _concurrent_registration_round(round_number)


def _concurrent_registration_round(round_number: int) -> None:
    prefix = _prefix(f"round-{round_number}")
    machines = [_storage(prefix) for _ in range(4)]
    departments = [f"round_{round_number}_dept_{i}" for i in range(16)]
    try:
        with ThreadPoolExecutor(max_workers=len(departments)) as pool:
            list(
                pool.map(
                    lambda i: lookups.register_department(
                        machines[i % len(machines)], departments[i], f"Department {i}"
                    ),
                    range(len(departments)),
                )
            )

        rows = machines[0].read_csv(lookups.DEPARTMENTS_PATH)
        assert sorted(row["department_id"] for row in rows) == sorted(departments)
        assert machines[0].list("_locks/") == [], "a lock object survived a successful run"
    finally:
        machines[0].delete_prefix("")
