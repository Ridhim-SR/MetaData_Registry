import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from src.schema_registry.registry import lookups
from src.schema_registry.batch import run_batch
from src.storage.local import LocalObjectStorage


def test_batch_runs_multiple_departments(tmp_path):
    ddl_file = tmp_path / "pwd.txt"
    ddl_file.write_text("sno integer NOT NULL")
    csv_file = tmp_path / "health.csv"
    csv_file.write_text("Field Name,Data Type\npatient_id,integer\n")

    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "department,dataset,table_name,source_file,source_format\n"
        f"pwd,vishwakarma,t1,{ddl_file},postgres_ddl\n"
        f"health,patient_registry,patients,{csv_file},csv\n"
    )

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "PWD")
    lookups.register_department(storage, "health", "Health")

    results = run_batch(str(manifest), storage)

    assert len(results) == 2
    assert all(r["status"] == "ok" for r in results)


def test_batch_one_bad_row_does_not_block_others(tmp_path):
    ddl_file = tmp_path / "pwd.txt"
    ddl_file.write_text("sno integer NOT NULL")
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("Description,Category\nsome text,finance\n")

    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "department,dataset,table_name,source_file,source_format\n"
        f"pwd,vishwakarma,t1,{ddl_file},postgres_ddl\n"
        f"irrigation,scheme_tracker,schemes,{bad_csv},csv\n"
    )

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "PWD")
    lookups.register_department(storage, "irrigation", "Irrigation")

    results = run_batch(str(manifest), storage)

    statuses = {r["table_id"]: r["status"] for r in results}
    assert statuses["pwd.vishwakarma.t1"] == "ok"
    assert statuses["irrigation.scheme_tracker.schemes"] == "failed"


def test_batch_registers_new_department_from_manifest(tmp_path):
    """A manifest is something you deliberately write, so a row naming a
    department_name for a not-yet-registered department registers it
    inline -- unlike a bare pipeline.run() call, which refuses to."""

    csv_file = tmp_path / "x.csv"
    csv_file.write_text("Field Name,Data Type\ncol_a,integer\n")

    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "department,department_name,dataset,table_name,source_file,source_format\n"
        f"PWD,Public Works Department,vishwakarma,t1,{csv_file},csv\n"
    )

    storage = LocalObjectStorage(tmp_path / "storage")
    results = run_batch(str(manifest), storage)

    assert results[0]["status"] == "ok"
    departments = storage.read_csv("_lookups/departments.csv")
    assert departments == [{"department_id": "pwd", "department_name": "Public Works Department"}]


def test_batch_row_for_unregistered_department_fails_gracefully(tmp_path):
    csv_file = tmp_path / "x.csv"
    csv_file.write_text("Field Name,Data Type\ncol_a,integer\n")

    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "department,dataset,table_name,source_file,source_format\n"
        f"never_registered,d1,t1,{csv_file},csv\n"
    )

    results = run_batch(str(manifest), LocalObjectStorage(tmp_path / "storage"))

    assert results[0]["status"] == "failed"
    assert "Unknown department" in results[0]["error"]


def test_batch_row_dropping_a_column_fails_without_allow_column_removal(tmp_path):
    """Same guard as pipeline.run() -- a manifest row whose source is
    missing a column from that table's previous curated snapshot fails
    that row instead of silently publishing fewer columns."""

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "PWD")

    csv_v1 = tmp_path / "v1.csv"
    csv_v1.write_text("Field Name,Data Type\ncol_a,integer\ncol_b,varchar\n")
    manifest_v1 = tmp_path / "manifest_v1.csv"
    manifest_v1.write_text(
        "department,dataset,table_name,source_file,source_format\n"
        f"pwd,vishwakarma,t1,{csv_v1},csv\n"
    )
    run_batch(str(manifest_v1), storage)

    csv_v2 = tmp_path / "v2.csv"
    csv_v2.write_text("Field Name,Data Type\ncol_a,integer\n")  # col_b missing
    manifest_v2 = tmp_path / "manifest_v2.csv"
    manifest_v2.write_text(
        "department,dataset,table_name,source_file,source_format\n"
        f"pwd,vishwakarma,t1,{csv_v2},csv\n"
    )
    results = run_batch(str(manifest_v2), storage)

    assert results[0]["status"] == "failed"
    assert "col_b" in results[0]["error"]


def test_batch_row_dropping_a_column_succeeds_with_allow_column_removal(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "PWD")

    csv_v1 = tmp_path / "v1.csv"
    csv_v1.write_text("Field Name,Data Type\ncol_a,integer\ncol_b,varchar\n")
    manifest_v1 = tmp_path / "manifest_v1.csv"
    manifest_v1.write_text(
        "department,dataset,table_name,source_file,source_format\n"
        f"pwd,vishwakarma,t1,{csv_v1},csv\n"
    )
    run_batch(str(manifest_v1), storage)

    csv_v2 = tmp_path / "v2.csv"
    csv_v2.write_text("Field Name,Data Type\ncol_a,integer\n")
    manifest_v2 = tmp_path / "manifest_v2.csv"
    manifest_v2.write_text(
        "department,dataset,table_name,source_file,source_format,allow_column_removal\n"
        f"pwd,vishwakarma,t1,{csv_v2},csv,true\n"
    )
    results = run_batch(str(manifest_v2), storage)

    assert results[0]["status"] == "ok"
    assert results[0]["column_count"] == 1


def test_manifest_row_can_set_the_dataset_level_fields(tmp_path):
    """category/owner/etc. used to be silently dropped by the manifest path
    -- a batch onboarding was the only way to register a dataset, and it
    never set its governance fields."""

    csv_file = tmp_path / "x.csv"
    csv_file.write_text("Field Name,Data Type\ncol_a,integer\n")

    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "department,department_name,dataset,table_name,source_file,source_format,"
        "category,api_available,owner,frequency,timeline,dataset_description\n"
        f"pwd,Public Works Department,vishwakarma,t1,{csv_file},csv,"
        "CAT-2,N,PWD Data Office,Annual,2024-25,PWD's master works dataset.\n"
    )

    storage = LocalObjectStorage(tmp_path / "storage")
    results = run_batch(str(manifest), storage)

    assert results[0]["status"] == "ok"
    row = lookups.get_dataset(storage, "pwd.vishwakarma")
    assert row["category"] == "CAT-2"
    assert row["api_available"] == "N"
    assert row["owner"] == "PWD Data Office"
    assert row["frequency"] == "Annual"
    assert row["timeline"] == "2024-25"
    assert row["dataset_description"] == "PWD's master works dataset."


_MINIO_ENDPOINT = "http://localhost:9000"


def _minio_up() -> bool:
    try:
        with socket.create_connection(("localhost", 9000), timeout=2):
            return True
    except OSError:
        return False


requires_minio = pytest.mark.skipif(
    not _minio_up(),
    reason="MinIO not running -- docker compose -f infrastructure/minio/docker-compose.yml up -d",
)


def _run_cli(tmp_path, manifest) -> "subprocess.CompletedProcess":
    env = {**os.environ, "MANIFEST_FILE": str(manifest)}
    # Main's config routes feature-branch runs to S3 (no local-filesystem
    # storage anymore), so point the CLI at the local MinIO stand-in
    # (infrastructure/minio) under a throwaway prefix: the run exercises the
    # real S3 code path but can never touch the real local/ registry state.
    env.update({
        "LOCAL_WASABI_ENDPOINT_URL": _MINIO_ENDPOINT,
        "LOCAL_WASABI_REGION": "us-east-1",
        "LOCAL_WASABI_BUCKET": "sda-local",
        "LOCAL_WASABI_ACCESS_KEY_ID": "minioadmin",
        "LOCAL_WASABI_SECRET_ACCESS_KEY": "minioadmin",
        "WASABI_PREFIX": f"tests/{uuid.uuid4().hex}",
    })
    # Storage-only run. Popping the token is NOT enough: load_env() re-reads
    # it from .env, so the CLI would build a real client and this test would
    # publish `pwd.vishwakarma.t1` into whatever local OpenMetadata is up
    # (it did -- a stray `pwd` service kept reappearing after every suite
    # run). An empty value survives load_env()'s setdefault and keeps the
    # client None.
    env["OPENMETADATA_JWT_TOKEN"] = ""
    # Main's confirm_changes() refuses a non-tty run without --yes.
    return subprocess.run(
        [sys.executable, "-m", "src.schema_registry.batch", "--yes"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


@requires_minio
def test_batch_cli_exits_non_zero_when_a_row_fails(tmp_path):
    """cron/CI used to see exit 0 for a half-failed batch."""

    ddl_file = tmp_path / "pwd.txt"
    ddl_file.write_text("sno integer NOT NULL")
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "department,dataset,table_name,source_file,source_format\n"
        f"never_registered,d1,t1,{ddl_file},postgres_ddl\n"
    )

    proc = _run_cli(tmp_path, manifest)

    assert proc.returncode == 1
    assert "FAILED never_registered.d1.t1" in proc.stdout
    assert "Unknown department" in proc.stdout


@requires_minio
def test_batch_cli_exits_zero_when_every_row_succeeds(tmp_path):
    csv_file = tmp_path / "x.csv"
    csv_file.write_text("Field Name,Data Type\ncol_a,integer\n")
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "department,department_name,dataset,table_name,source_file,source_format\n"
        f"pwd,Public Works Department,vishwakarma,t1,{csv_file},csv\n"
    )

    proc = _run_cli(tmp_path, manifest)

    assert proc.returncode == 0
    assert "FAILED" not in proc.stdout
