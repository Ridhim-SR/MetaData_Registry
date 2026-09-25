from src.schema_registry import lookups
from src.storage.local import LocalObjectStorage


def test_register_department_creates_row(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    lookups.register_department(storage, "pwd", "PWD")
    rows = storage.read_csv(lookups.DEPARTMENTS_PATH)
    assert rows == [{"department_id": "pwd", "department_name": "PWD"}]


def test_register_department_is_deduped(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    lookups.register_department(storage, "pwd", "PWD")
    lookups.register_department(storage, "pwd", "PWD")
    rows = storage.read_csv(lookups.DEPARTMENTS_PATH)
    assert len(rows) == 1


def test_department_exists(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    assert lookups.department_exists(storage, "pwd") is False
    lookups.register_department(storage, "pwd", "PWD")
    assert lookups.department_exists(storage, "pwd") is True


def test_upsert_dataset_links_to_department(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    lookups.upsert_dataset(storage, "pwd.vishwakarma", "pwd", "vishwakarma")
    rows = storage.read_csv(lookups.DATASETS_PATH)
    assert rows == [
        {
            "dataset_id": "pwd.vishwakarma",
            "department_id": "pwd",
            "dataset_name": "vishwakarma",
            "owner": "",
            "fiduciary": "",
            "processor": "",
            "risk_classification": "",
            "retention_policy": "",
            "lineage": "",
        }
    ]


def test_upsert_dataset_governance_fields(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    lookups.upsert_dataset(
        storage, "pwd.vishwakarma", "pwd", "vishwakarma",
        fiduciary="Superintendent Engineer, I.D.S. Circle, Lucknow",
        processor="not defined",
        risk_classification="4/5",
    )
    rows = storage.read_csv(lookups.DATASETS_PATH)
    assert rows[0]["fiduciary"] == "Superintendent Engineer, I.D.S. Circle, Lucknow"
    assert rows[0]["processor"] == "not defined"
    assert rows[0]["risk_classification"] == "4/5"
    assert rows[0]["owner"] == ""


def test_upsert_table_links_to_dataset(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    lookups.upsert_table(storage, "pwd.vishwakarma.roads", "pwd.vishwakarma", "roads", "public")
    rows = storage.read_csv(lookups.TABLES_PATH)
    assert rows == [
        {"table_id": "pwd.vishwakarma.roads", "dataset_id": "pwd.vishwakarma", "table_name": "roads", "schema_name": "public"}
    ]


def test_two_datasets_same_department_both_kept(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    lookups.register_department(storage, "pwd", "PWD")
    lookups.upsert_dataset(storage, "pwd.vishwakarma", "pwd", "vishwakarma")
    lookups.upsert_dataset(storage, "pwd.srishti", "pwd", "srishti")

    departments = storage.read_csv(lookups.DEPARTMENTS_PATH)
    datasets = storage.read_csv(lookups.DATASETS_PATH)
    assert len(departments) == 1
    assert len(datasets) == 2
    assert {d["dataset_id"] for d in datasets} == {"pwd.vishwakarma", "pwd.srishti"}


def test_upsert_updates_existing_row_fields(tmp_path):
    """True upsert: re-registering an existing key with different field
    values replaces the row -- needed so a dataset's Owner/Retention/etc.
    can be filled in later once confirmed, without deleting/recreating it."""

    storage = LocalObjectStorage(tmp_path)
    lookups.upsert_table(storage, "pwd.vishwakarma.t1", "pwd.vishwakarma", "t1", "public")
    lookups.upsert_table(storage, "pwd.vishwakarma.t1", "pwd.vishwakarma", "t1", "reporting")

    rows = storage.read_csv(lookups.TABLES_PATH)
    assert len(rows) == 1
    assert rows[0]["schema_name"] == "reporting"


def test_upsert_dataset_update_does_not_disturb_other_datasets(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    lookups.upsert_dataset(storage, "pwd.vishwakarma", "pwd", "vishwakarma")
    lookups.upsert_dataset(storage, "pwd.srishti", "pwd", "srishti")

    lookups.upsert_dataset(storage, "pwd.vishwakarma", "pwd", "vishwakarma", owner="Someone")

    rows = storage.read_csv(lookups.DATASETS_PATH)
    assert len(rows) == 2
    vishwakarma = next(r for r in rows if r["dataset_id"] == "pwd.vishwakarma")
    srishti = next(r for r in rows if r["dataset_id"] == "pwd.srishti")
    assert vishwakarma["owner"] == "Someone"
    assert srishti["owner"] == ""
