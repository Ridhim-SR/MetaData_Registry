from concurrent.futures import ThreadPoolExecutor

from src.schema_registry import lookups
from src.storage.local import LocalObjectStorage


def test_concurrent_department_registrations_do_not_lose_rows(tmp_path):
    """20 threads each register a distinct department at the same time.
    All 20 must survive -- a read-then-write race would silently drop some."""

    storage = LocalObjectStorage(tmp_path)
    department_ids = [f"dept_{i}" for i in range(20)]

    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(lambda d: lookups.register_department(storage, d, d), department_ids))

    rows = storage.read_csv(lookups.DEPARTMENTS_PATH)
    assert {r["department_id"] for r in rows} == set(department_ids), (
        f"expected 20 departments, found {len(rows)}: lost rows under concurrent writes"
    )
