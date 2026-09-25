import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from src.schema_registry import lookups
from src.schema_registry.pipeline import run
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


def test_concurrent_runs_block_on_the_same_table_lock(tmp_path):
    """Thread 1 legitimately adds col_b while paused mid-critical-section
    (inside run()'s per-table lock, right after reading the previous
    snapshot). Thread 2 concurrently submits a source that only has col_a
    -- unaware col_b is being added right now.

    If the lock works, thread 2 cannot even start reading the previous
    snapshot until thread 1 finishes and releases the lock -- so thread 2
    is guaranteed to see col_b in the "previous" state, correctly detect it
    as missing from its own submission, and raise. Without the lock, thread
    2 would race ahead, read the stale pre-col_b snapshot, see nothing
    missing, and silently publish a snapshot that drops col_b the moment
    it becomes "latest"."""

    storage = LocalObjectStorage(tmp_path)
    lookups.register_department(storage, "pwd", "PWD")

    seed_ddl = tmp_path / "seed.txt"
    seed_ddl.write_text("col_a integer NOT NULL")
    run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(seed_ddl), storage=storage)

    import src.schema_registry.pipeline as pipeline_module

    thread1_reading = threading.Event()
    let_thread1_proceed = threading.Event()
    original_previous_curated = pipeline_module._previous_curated_columns

    def _paused_read(*args, **kwargs):
        result = original_previous_curated(*args, **kwargs)
        thread1_reading.set()
        assert let_thread1_proceed.wait(timeout=5), "test deadlocked waiting to be released"
        return result

    ddl_with_b = tmp_path / "with_b.txt"
    ddl_with_b.write_text("col_a integer NOT NULL, col_b character varying(50)")

    def _thread1():
        with patch.object(pipeline_module, "_previous_curated_columns", side_effect=_paused_read):
            run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_with_b), storage=storage)

    t1 = threading.Thread(target=_thread1)
    t1.start()
    assert thread1_reading.wait(timeout=5), "thread 1 never reached its paused read"

    ddl_a_only = tmp_path / "a_only.txt"
    ddl_a_only.write_text("col_a integer NOT NULL")
    outcome = {}

    def _thread2():
        try:
            run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_a_only), storage=storage)
            outcome["result"] = "ok"
        except ValueError as exc:
            outcome["result"] = "raised"
            outcome["error"] = str(exc)

    t2 = threading.Thread(target=_thread2)
    t2.start()

    # Give thread 2 a moment: it should be blocked acquiring the lock, not
    # racing ahead to read a stale previous snapshot.
    t2.join(timeout=0.3)
    assert "result" not in outcome, "thread 2 proceeded past the lock while thread 1 was mid-write"

    let_thread1_proceed.set()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert outcome["result"] == "raised", "thread 2 should have detected col_b as missing, not silently succeeded"
    assert "col_b" in outcome["error"]
