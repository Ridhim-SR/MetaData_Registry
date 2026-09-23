from src.schema_registry import lookups
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
