import pytest

from src.schema_registry.backfill_readable import backfill
from src.schema_registry.registry import lookups, paths
from src.storage.local import LocalObjectStorage

_RAW_TS = "20260101T000000000000Z"


@pytest.fixture
def storage(tmp_path):
    return LocalObjectStorage(tmp_path / "storage")


def _seed(
    storage,
    table_id="pwd.vishwakarma.t1",
    table="t1",
    raw_types=None,
    curated=None,
):
    department_id, dataset_slug, table_slug = table_id.split(".")
    lookups.upsert_table(storage, table_id, f"{department_id}.{dataset_slug}", table, "public")

    raw_types = raw_types or [("sno", "integer", "", ""), ("total_cost", "numeric", "", "2")]
    raw = [
        {
            "table_id": table_id,
            "ingestion_timestamp": _RAW_TS,
            "name": name,
            "data_type": data_type,
            "length": length,
            "scale": scale,
            "nullable": "False",
            "default": "",
        }
        for name, data_type, length, scale in raw_types
    ]
    storage.write_csv(paths.raw_schema_path(department_id, dataset_slug, table_slug, _RAW_TS), raw)

    curated = curated or [
        {
            "name": "sno", "data_type": "integer", "length": "", "scale": "", "nullable": "False",
            "default": "", "business_description": "Serial number", "tag": "",
            "classification": "Public", "glossary_term": "", "active": "True",
        },
        {
            "name": "total_cost", "data_type": "numeric", "length": "", "scale": "2", "nullable": "False",
            "default": "", "business_description": "Total cost", "tag": "Financial",
            "classification": "Financial", "glossary_term": "Cost", "active": "True", "unit": "₹",
        },
    ]
    storage.write_csv(paths.curated_schema_path(department_id, dataset_slug, table_slug, _RAW_TS), curated)


def _latest(storage, table_id="pwd.vishwakarma.t1"):
    department_id, dataset_slug, table_slug = table_id.split(".")
    return storage.read_csv(lookups.latest_curated_snapshot_path(storage, department_id, dataset_slug, table_slug))


def _snapshot_count(storage, table_id="pwd.vishwakarma.t1"):
    department_id, dataset_slug, table_slug = table_id.split(".")
    return len([
        f for f in storage.list(paths.curated_schemas_prefix(department_id, dataset_slug, table_slug))
        if f.endswith(".csv")
    ])


def _run_rows(storage):
    return storage.read_csv(lookups.RUNS_PATH) if storage.exists(lookups.RUNS_PATH) else []


def test_backfill_adds_readable_type_while_keeping_data_type_and_answers(storage):
    _seed(storage)

    outcomes = backfill(storage)

    assert [(o.table_id, o.status) for o in outcomes] == [("pwd.vishwakarma.t1", "backfilled")]
    by_name = {row["name"]: row for row in _latest(storage)}
    assert by_name["sno"]["data_type"] == "integer"
    assert by_name["sno"]["readable_type"] == "Whole Number"
    assert by_name["sno"]["business_description"] == "Serial number"
    assert by_name["sno"]["classification"] == "Public"
    assert by_name["sno"]["unit"] == ""
    assert by_name["total_cost"]["data_type"] == "numeric"
    assert by_name["total_cost"]["readable_type"] == "Decimal Number"
    assert by_name["total_cost"]["unit"] == "INR"
    assert by_name["total_cost"]["tag"] == "Financial"
    assert by_name["total_cost"]["glossary_term"] == "Cost"


def test_backfill_preserves_blank_and_reviewed_classifications(storage):
    _seed(
        storage,
        curated=[
            {
                "name": "sno", "data_type": "integer", "length": "", "scale": "",
                "nullable": "False", "default": "", "business_description": "",
                "tag": "", "classification": "", "glossary_term": "", "active": "True",
            },
            {
                "name": "total_cost", "data_type": "numeric", "length": "", "scale": "2",
                "nullable": "False", "default": "", "business_description": "Cost",
                "tag": "Financial", "classification": "Financial",
                "glossary_term": "Cost", "active": "True", "unit": "INR",
            },
        ],
    )

    backfill(storage)

    by_name = {row["name"]: row for row in _latest(storage)}
    assert by_name["sno"]["classification"] == ""
    assert by_name["total_cost"]["classification"] == "Financial"
    assert by_name["sno"]["business_description"] == ""


def test_raw_and_curated_name_mismatch_fails_that_table(storage):
    _seed(storage)
    curated_path = paths.curated_schema_path("pwd", "vishwakarma", "t1", _RAW_TS)
    rows = storage.read_csv(curated_path)
    rows[0]["name"] = "renamed_sno"
    storage.write_csv(curated_path, rows)

    outcomes = backfill(storage)

    assert [o.status for o in outcomes] == ["failed"]
    assert "disagree on columns" in outcomes[0].detail


def test_backfill_does_not_modify_the_previous_snapshot(storage):
    _seed(storage)
    old_path = paths.curated_schema_path("pwd", "vishwakarma", "t1", _RAW_TS)

    backfill(storage)

    old = storage.read_csv(old_path)
    assert "readable_type" not in old[0]
    assert _snapshot_count(storage) == 2


def test_running_backfill_twice_is_a_no_op(storage):
    _seed(storage)

    backfill(storage)
    outcomes = backfill(storage)

    assert [o.status for o in outcomes] == ["unchanged"]
    assert _snapshot_count(storage) == 2
    assert len(_run_rows(storage)) == 1


def test_dry_run_writes_nothing(storage):
    _seed(storage)

    outcomes = backfill(storage, dry_run=True)

    assert [o.status for o in outcomes] == ["would backfill"]
    assert _snapshot_count(storage) == 1
    assert _run_rows(storage) == []


def test_department_filter_only_touches_that_department(storage):
    _seed(storage, table_id="pwd.vishwakarma.t1", table="t1")
    _seed(storage, table_id="welfare.cmsvy.t1", table="t1")

    outcomes = backfill(storage, department="pwd")

    assert [o.table_id for o in outcomes] == ["pwd.vishwakarma.t1"]
    assert _snapshot_count(storage, "welfare.cmsvy.t1") == 1


def test_one_bad_type_fails_only_that_table(storage):
    _seed(storage, table_id="pwd.vishwakarma.good", table="good")
    _seed(
        storage,
        table_id="pwd.vishwakarma.bad",
        table="bad",
        raw_types=[("amount", "money", "", "")],
        curated=[{
            "name": "amount", "data_type": "money", "length": "", "scale": "",
            "nullable": "False", "default": "", "business_description": "", "tag": "",
            "classification": "", "glossary_term": "", "active": "True",
        }],
    )

    outcomes = {o.table_id: o for o in backfill(storage)}

    assert outcomes["pwd.vishwakarma.good"].status == "backfilled"
    assert outcomes["pwd.vishwakarma.bad"].status == "failed"
    assert "No readable label" in outcomes["pwd.vishwakarma.bad"].detail


def test_soft_deleted_tables_are_skipped(storage):
    _seed(storage)
    lookups.soft_delete_table(storage, "pwd.vishwakarma.t1")

    outcomes = backfill(storage)

    assert [(o.table_id, o.status) for o in outcomes] == [("pwd.vishwakarma.t1", "skipped")]


def test_publish_is_called_and_recorded_on_the_run_row(storage, monkeypatch):
    _seed(storage)
    calls = []

    def _fake_publish(client, storage_arg, table_id, **kwargs):
        calls.append((client, storage_arg, table_id, kwargs))
        return {"fully_qualified_name": table_id}

    monkeypatch.setattr(
        "src.schema_registry.openmetadata.publish.publish_table", _fake_publish
    )
    client = object()

    outcomes = backfill(storage, client=client)

    assert [(o.status, o.publish) for o in outcomes] == [("backfilled", "published")]
    assert calls == [(client, storage, "pwd.vishwakarma.t1", {})]
    assert _run_rows(storage)[0]["publish_status"] == "published"


def test_publish_failure_is_reported_and_logged(storage, monkeypatch):
    _seed(storage)

    def _boom(*args, **kwargs):
        raise RuntimeError("OpenMetadata said no")

    monkeypatch.setattr("src.schema_registry.openmetadata.publish.publish_table", _boom)

    outcomes = backfill(storage, client=object())

    assert [(o.status, o.publish) for o in outcomes] == [("backfilled", "failed")]
    run_row = _run_rows(storage)[0]
    assert run_row["publish_status"] == "failed"
    assert "OpenMetadata said no" in run_row["error"]
    assert _snapshot_count(storage) == 2


def test_backfill_without_a_registry_raises(storage):
    with pytest.raises(ValueError, match="nothing registered"):
        backfill(storage)


def test_unit_is_renormalized_on_an_already_readable_snapshot(storage):
    _seed(storage)
    backfill(storage)
    curated_path = lookups.latest_curated_snapshot_path(storage, "pwd", "vishwakarma", "t1")
    rows = storage.read_csv(curated_path)
    rows[1]["unit"] = "Rs."
    storage.write_csv(curated_path, rows)

    outcomes = backfill(storage)

    assert [o.status for o in outcomes] == ["backfilled"]
    assert {r["name"]: r for r in _latest(storage)}["total_cost"]["unit"] == "INR"
