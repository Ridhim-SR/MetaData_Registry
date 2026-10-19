import logging

from src.schema_registry.add import add
from src.schema_registry.catalog import load_catalog
from src.schema_registry.sync import sync
from src.storage.local import LocalObjectStorage


def test_no_false_not_in_catalog_warning(tmp_path, caplog):
    storage = LocalObjectStorage(tmp_path / "s")
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("departments:\n")
    f = tmp_path / "t.txt"
    f.write_text("id integer NOT NULL")
    add(storage, catalog, str(f), "d", "ds", table="t", department_name="D")
    with caplog.at_level(logging.WARNING):
        sync(storage, load_catalog(catalog))
    assert "not in catalog.yaml" not in caplog.text

    # a table that really left the catalog is still reported
    catalog.write_text("departments:\n")
    with caplog.at_level(logging.WARNING):
        sync(storage, load_catalog(catalog))
    assert "d.ds.t" in caplog.text
