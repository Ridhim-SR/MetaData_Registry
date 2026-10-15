import pytest

from src.schema_registry.add import add
from src.schema_registry.catalog import load_catalog
from src.schema_registry.sync import sync
from src.storage.local import LocalObjectStorage

_CATALOG = """# What should be in OpenMetadata. (header comment must survive)

departments:

  pwd:
    name: Public Works Department
    datasets:
      vishwakarma:
        category: CAT-3
        tables:
          # Provisional name.
          vishwakarma_T:
            source: storage:inputs/pwd/old_place.txt
            format: postgres_ddl
"""


@pytest.fixture
def setup(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(_CATALOG)
    ddl = tmp_path / "works.txt"
    ddl.write_text("work_id integer NOT NULL, total_cost numeric")
    return storage, catalog, ddl, tmp_path


def test_new_table_is_uploaded_and_added_to_the_catalog(setup):
    storage, catalog, ddl, _ = setup

    changes = add(storage, catalog, str(ddl), "pwd", "vishwakarma", table="works")

    assert storage.read_bytes("inputs/pwd/vishwakarma/works.txt") == ddl.read_bytes()
    assert "added table pwd/vishwakarma/works" in changes
    (dept,) = load_catalog(catalog)
    works = next(t for t in dept.datasets[0].tables if t.name == "works")
    assert (works.source, works.format) == ("storage:inputs/pwd/vishwakarma/works.txt", "postgres_ddl")


def test_comments_and_existing_entries_are_kept(setup):
    storage, catalog, ddl, _ = setup
    add(storage, catalog, str(ddl), "pwd", "vishwakarma", table="works")
    text = catalog.read_text()
    assert "# What should be in OpenMetadata. (header comment must survive)" in text
    assert "# Provisional name." in text
    assert "category: CAT-3" in text
    assert "storage:inputs/pwd/old_place.txt" in text


def test_same_file_again_only_uploads(setup):
    storage, catalog, ddl, _ = setup
    add(storage, catalog, str(ddl), "pwd", "vishwakarma", table="works")
    before = catalog.read_text()

    changes = add(storage, catalog, str(ddl), "pwd", "vishwakarma", table="works")

    assert all(c.startswith("uploaded") for c in changes)
    assert catalog.read_text() == before


def test_existing_table_is_pointed_at_the_new_upload(setup):
    storage, catalog, ddl, tmp_path = setup
    newer = tmp_path / "pwd_vishwakarma_v2.txt"
    newer.write_text("sno integer NOT NULL")

    changes = add(storage, catalog, str(newer), "pwd", "vishwakarma", table="vishwakarma_T")

    assert "set source of pwd/vishwakarma/vishwakarma_T to storage:inputs/pwd/vishwakarma/pwd_vishwakarma_v2.txt" in changes


def test_new_department_needs_its_full_name_and_uploads_nothing_without_it(setup):
    storage, catalog, ddl, tmp_path = setup
    csv_file = tmp_path / "apps.csv"
    csv_file.write_text("name,data_type\napplication_no,text\n")

    with pytest.raises(ValueError, match="--department-name"):
        add(storage, catalog, str(csv_file), "samaj_kalyan", "cmsvy", table="applications")
    assert storage.list("inputs/") == []

    changes = add(storage, catalog, str(csv_file), "samaj_kalyan", "cmsvy", table="applications",
                  department_name="Department of Social Welfare")
    assert "added department samaj_kalyan (Department of Social Welfare)" in changes
    sk = next(d for d in load_catalog(catalog) if d.id == "samaj_kalyan")
    assert sk.datasets[0].tables[0].format == "csv"  # guessed from .csv


def test_field_dictionary_and_metadata_files(setup):
    storage, catalog, ddl, tmp_path = setup
    meta = tmp_path / "works_meta.csv"
    meta.write_text("name,business_description\ntotal_cost,Sanctioned cost\n")
    add(storage, catalog, str(ddl), "pwd", "vishwakarma", table="works", metadata_file=str(meta))
    dictionary = tmp_path / "dict.csv"
    dictionary.write_text("x")
    add(storage, catalog, str(dictionary), "pwd", "tenders", department_name=None)

    pwd = load_catalog(catalog)[0]
    works = next(t for t in pwd.datasets[0].tables if t.name == "works")
    assert works.metadata == "storage:inputs/pwd/vishwakarma/works_meta.csv"
    assert storage.exists("inputs/pwd/vishwakarma/works_meta.csv")
    assert next(d for d in pwd.datasets if d.name == "tenders").field_dictionary == "storage:inputs/pwd/tenders/dict.csv"


@pytest.mark.parametrize("bad_department", ["PWD", "pwd dept"])
def test_bad_department_id_is_refused(setup, bad_department):
    storage, catalog, ddl, _ = setup
    with pytest.raises(ValueError, match="lowercase"):
        add(storage, catalog, str(ddl), bad_department, "vishwakarma", table="works", department_name="X")


def test_added_table_goes_through_sync(setup):
    storage, catalog, ddl, _ = setup
    add(storage, catalog, str(ddl), "pwd", "vishwakarma", table="works")
    storage.write_bytes("inputs/pwd/old_place.txt", b"sno integer NOT NULL")

    outcomes = {o.table_id: o.ingest for o in sync(storage, load_catalog(catalog))}

    assert outcomes == {"pwd.vishwakarma.works": "ingested", "pwd.vishwakarma.vishwakarma_t": "ingested"}


def test_sync_department_filter(setup):
    storage, catalog, ddl, tmp_path = setup
    other = tmp_path / "apps.csv"
    other.write_text("name,data_type\napplication_no,text\n")
    add(storage, catalog, str(other), "samaj_kalyan", "cmsvy", table="applications", department_name="Social Welfare")
    storage.write_bytes("inputs/pwd/old_place.txt", b"sno integer NOT NULL")

    outcomes = sync(storage, load_catalog(catalog), only_department="samaj_kalyan")

    assert [o.table_id for o in outcomes] == ["samaj_kalyan.cmsvy.applications"]
    with pytest.raises(ValueError, match="isn't in catalog.yaml"):
        sync(storage, load_catalog(catalog), only_department="health")


def test_long_source_paths_stay_on_one_line(setup):
    storage, catalog, _, tmp_path = setup
    long_file = tmp_path / ("a_very_long_department_file_name_" * 3 + ".txt")
    long_file.write_text("sno integer NOT NULL")
    add(storage, catalog, str(long_file), "pwd", "vishwakarma", table="works")
    assert f"source: storage:inputs/pwd/vishwakarma/{long_file.name}\n" in catalog.read_text()


def test_header_comments_kept_when_catalog_has_no_departments_yet():
    from src.schema_registry.add import update_catalog_text
    from src.schema_registry.catalog import parse_catalog

    new, _ = update_catalog_text("# keep me\n", "pwd", "ds", "storage:inputs/x.txt", department_name="PWD", table="t")
    assert new.startswith("# keep me")
    assert parse_catalog(new)[0].id == "pwd"
