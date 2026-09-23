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
    assert rows == [{"dataset_id": "pwd.vishwakarma", "department_id": "pwd", "dataset_name": "vishwakarma"}]


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


def test_upsert_does_not_update_existing_row_fields(tmp_path):
    """Known limitation: this is insert-if-missing, not a true upsert --
    re-registering an existing key with different field values is ignored."""

    storage = LocalObjectStorage(tmp_path)
    lookups.upsert_table(storage, "pwd.vishwakarma.t1", "pwd.vishwakarma", "t1", "public")
    lookups.upsert_table(storage, "pwd.vishwakarma.t1", "pwd.vishwakarma", "t1", "reporting")

    rows = storage.read_csv(lookups.TABLES_PATH)
    assert len(rows) == 1
    assert rows[0]["schema_name"] == "public"
