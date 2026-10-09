from unittest.mock import MagicMock

import pytest

from src.schema_registry.catalog import parse_catalog
from src.schema_registry.openmetadata.publish import _unwrap
from src.schema_registry.registry import lookups
from src.schema_registry.sync import sync
from src.storage.local import LocalObjectStorage

_CATALOG = """
departments:
  pwd:
    name: Public Works Department
    datasets:
      vishwakarma:
        category: CAT-3
        owner: PWD IT Cell
        tables:
          works:
            source: storage:inputs/pwd/works.txt
          tenders:
            source: storage:inputs/pwd/tenders.txt
"""


def _fake_client():
    client = MagicMock()
    client.get_by_name.side_effect = Exception("Entity not found")

    def _create_or_update(request):
        entity = MagicMock()
        name = _unwrap(getattr(request, "name", None))
        parent = _unwrap(getattr(request, "service", None) or getattr(request, "database", None)
                         or getattr(request, "databaseSchema", None) or getattr(request, "classification", None))
        entity.fullyQualifiedName = f"{parent}.{name}" if parent else str(name)
        entity.name = name
        entity.columns = getattr(request, "columns", None)
        return entity

    client.create_or_update.side_effect = _create_or_update
    return client


def _published_tables(client):
    return sorted(
        _unwrap(c.args[0].name) for c in client.create_or_update.call_args_list
        if getattr(c.args[0], "columns", None) is not None
    )


@pytest.fixture
def storage(tmp_path):
    s = LocalObjectStorage(tmp_path / "storage")
    s.write_bytes("inputs/pwd/works.txt", b"work_id integer NOT NULL, total_cost numeric")
    s.write_bytes("inputs/pwd/tenders.txt", b"tender_id integer NOT NULL, firm_pannumber character varying(10)")
    return s


def _by_table(outcomes):
    return {o.table_id: o for o in outcomes}


def test_first_sync_fills_storage_and_openmetadata_from_nothing(storage):
    client, setup = _fake_client(), MagicMock()

    outcomes = _by_table(sync(storage, parse_catalog(_CATALOG), client=client, setup=setup))

    setup.assert_called_once()
    assert lookups.department_exists(storage, "pwd")
    assert {t: (o.ingest, o.publish) for t, o in outcomes.items()} == {
        "pwd.vishwakarma.works": ("ingested", "published"),
        "pwd.vishwakarma.tenders": ("ingested", "published"),
    }
    assert _published_tables(client) == ["tenders", "works"]
    row = lookups.get_dataset(storage, "pwd.vishwakarma")
    assert (row["category"], row["owner"]) == ("CAT-3", "PWD IT Cell")


def test_second_sync_changes_nothing_in_storage_but_still_publishes(storage):
    """Unchanged files aren't re-ingested -- but everything is published
    again, so a wiped OpenMetadata is refilled by the same command."""

    sync(storage, parse_catalog(_CATALOG), client=_fake_client())
    files_before = storage.list("department/")
    client = _fake_client()

    outcomes = _by_table(sync(storage, parse_catalog(_CATALOG), client=client))

    assert {o.ingest for o in outcomes.values()} == {"unchanged"}
    assert storage.list("department/") == files_before
    assert _published_tables(client) == ["tenders", "works"]


def test_only_the_changed_file_is_reingested(storage):
    sync(storage, parse_catalog(_CATALOG))
    storage.write_bytes("inputs/pwd/works.txt", b"work_id integer NOT NULL, total_cost numeric, district text")

    outcomes = _by_table(sync(storage, parse_catalog(_CATALOG)))

    assert outcomes["pwd.vishwakarma.works"].ingest == "ingested"
    assert "source file changed" in outcomes["pwd.vishwakarma.works"].detail
    assert outcomes["pwd.vishwakarma.tenders"].ingest == "unchanged"


def test_changed_metadata_file_triggers_reingest(storage):
    catalog = _CATALOG.replace(
        "source: storage:inputs/pwd/works.txt", "source: storage:inputs/pwd/works.txt\n            metadata: storage:inputs/pwd/works_meta.csv"
    )
    storage.write_bytes("inputs/pwd/works_meta.csv", b"name,business_description\ntotal_cost,Sanctioned cost\n")
    sync(storage, parse_catalog(catalog))
    storage.write_bytes("inputs/pwd/works_meta.csv", b"name,business_description\ntotal_cost,Sanctioned cost in INR\n")

    outcomes = _by_table(sync(storage, parse_catalog(catalog)))

    assert outcomes["pwd.vishwakarma.works"].detail.startswith("metadata file changed")
    curated = storage.read_csv(lookups.latest_curated_snapshot_path(storage, "pwd", "vishwakarma", "works"))
    assert next(r for r in curated if r["name"] == "total_cost")["business_description"] == "Sanctioned cost in INR"


def test_one_bad_table_does_not_stop_the_others(storage):
    storage.write_bytes("inputs/pwd/tenders.txt", b"tender_id integer, tender_id integer")  # duplicate column
    client = _fake_client()

    outcomes = _by_table(sync(storage, parse_catalog(_CATALOG), client=client))

    assert outcomes["pwd.vishwakarma.tenders"].ingest == "failed"
    assert "duplicate" in outcomes["pwd.vishwakarma.tenders"].detail
    assert outcomes["pwd.vishwakarma.tenders"].publish == "skipped"
    assert (outcomes["pwd.vishwakarma.works"].ingest, outcomes["pwd.vishwakarma.works"].publish) == ("ingested", "published")


def test_missing_input_file_is_reported_per_table(storage):
    catalog = _CATALOG.replace("inputs/pwd/tenders.txt", "inputs/pwd/not_uploaded.txt")
    outcomes = _by_table(sync(storage, parse_catalog(catalog)))
    assert outcomes["pwd.vishwakarma.tenders"].ingest == "failed"
    assert "upload it first" in outcomes["pwd.vishwakarma.tenders"].detail


def test_removing_a_field_from_the_catalog_clears_it(storage):
    sync(storage, parse_catalog(_CATALOG))
    sync(storage, parse_catalog(_CATALOG.replace("        owner: PWD IT Cell\n", "")))
    assert lookups.get_dataset(storage, "pwd.vishwakarma")["owner"] == ""


def test_dry_run_writes_nothing(storage):
    client, setup = _fake_client(), MagicMock()

    outcomes = _by_table(sync(storage, parse_catalog(_CATALOG), client=client, setup=setup, dry_run=True))

    assert {o.ingest for o in outcomes.values()} == {"would ingest"}
    assert storage.list("department/") == [] and not storage.exists(lookups.DEPARTMENTS_PATH)
    setup.assert_not_called()
    assert client.create_or_update.call_count == 0


def test_publish_only_restores_every_stored_table_without_ingesting(storage):
    sync(storage, parse_catalog(_CATALOG))
    files_before = storage.list("department/")
    client = _fake_client()

    outcomes = sync(storage, [], client=client, publish_only=True)  # works even without a catalog entry

    assert storage.list("department/") == files_before
    assert sorted(o.table_id for o in outcomes if o.publish == "published") == [
        "pwd.vishwakarma.tenders", "pwd.vishwakarma.works",
    ]


def test_table_dropped_from_catalog_is_not_published(storage):
    sync(storage, parse_catalog(_CATALOG))
    catalog = _CATALOG.replace("          tenders:\n            source: storage:inputs/pwd/tenders.txt\n", "")
    client = _fake_client()

    sync(storage, parse_catalog(catalog), client=client)

    assert _published_tables(client) == ["works"]


def test_category_below_columns_still_publishes(storage):
    catalog = _CATALOG.replace("CAT-3", "CAT-1")  # tenders has firm_pannumber (auto CAT-3)
    outcomes = _by_table(sync(storage, parse_catalog(catalog), client=_fake_client()))
    assert outcomes["pwd.vishwakarma.tenders"].publish == "published"


def test_field_dictionary_dataset(storage):
    storage.write_bytes(
        "inputs/welfare/dict.csv",
        b"Dataset Name,Dataset Field,Data Description,Format,Mandatory (Y/N)\n"
        b"cmsvy_bride,bride_name,Name,Text,Y\ncmsvy_bank,account_no,Account,Numeric (12 Digits),Y\n",
    )
    catalog = parse_catalog(
        "departments:\n  welfare:\n    name: Social Welfare\n    datasets:\n      cmsvy:\n"
        "        field_dictionary: storage:inputs/welfare/dict.csv\n"
    )
    client = _fake_client()

    first = sync(storage, catalog, client=client)
    second = sync(storage, catalog, client=_fake_client())

    assert first[0].ingest == "ingested" and "2 table(s)" in first[0].detail
    assert second[0].ingest == "unchanged"
    assert _published_tables(client) == ["cmsvy_bank", "cmsvy_bride"]


def test_sync_records_the_publish_outcome_on_the_run_row(storage):
    """sync() ingests through run() *without* a client -- so the run row is
    written as `unpublished` -- and publishes afterwards, itself. That publish
    has to land on the row, or runs.csv forever claims the snapshot never
    reached OpenMetadata and republish keeps offering a table that is live."""

    sync(storage, parse_catalog(_CATALOG), client=_fake_client())

    runs = {r["table_id"]: r for r in storage.read_csv(lookups.RUNS_PATH)}
    assert runs["pwd.vishwakarma.works"]["publish_status"] == "published"
    assert runs["pwd.vishwakarma.works"]["error"] == ""
    assert runs["pwd.vishwakarma.tenders"]["publish_status"] == "published"


def test_sync_records_a_failed_publish_on_the_run_row(storage):
    """A publish that blows up is recorded as `failed` (with the error), the
    vocabulary pipeline.run() uses -- so republish picks the snapshot up."""

    client = _fake_client()
    client.create_or_update.side_effect = RuntimeError("server said no")

    outcomes = _by_table(sync(storage, parse_catalog(_CATALOG), client=client))

    assert outcomes["pwd.vishwakarma.works"].publish == "failed"
    runs = {r["table_id"]: r for r in storage.read_csv(lookups.RUNS_PATH)}
    assert runs["pwd.vishwakarma.works"]["publish_status"] == "failed"
    assert "server said no" in runs["pwd.vishwakarma.works"]["error"]
    # the snapshot itself survived, so `republish` can still fix it
    assert lookups.latest_snapshot_run(storage, "pwd.vishwakarma.works")["publish_status"] == "failed"


def test_publish_outcome_is_recorded_for_unchanged_tables_too(storage):
    """An unchanged table is still republished (that is how a wiped server is
    refilled), so its row -- written by an earlier storage-only run -- must be
    corrected as well."""

    sync(storage, parse_catalog(_CATALOG))  # storage-only: every row unpublished
    assert {r["publish_status"] for r in storage.read_csv(lookups.RUNS_PATH)} == {"unpublished"}

    sync(storage, parse_catalog(_CATALOG), client=_fake_client())

    assert {r["publish_status"] for r in storage.read_csv(lookups.RUNS_PATH)} == {"published"}
