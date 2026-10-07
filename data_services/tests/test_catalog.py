import pytest

from src.schema_registry.catalog import CatalogError, parse_catalog

_VALID = """
departments:
  pwd:
    name: Public Works Department
    datasets:
      vishwakarma:
        category: CAT-3
        owner: PWD IT Cell
        tables:
          vishwakarma_T:
            source: storage:inputs/pwd/v.txt
          works:
            source: storage:inputs/pwd/works.csv
            format: csv
            schema: ops
            metadata: storage:inputs/pwd/works_meta.csv
"""


def test_valid_catalog_parses():
    (dept,) = parse_catalog(_VALID)
    assert (dept.id, dept.name) == ("pwd", "Public Works Department")
    (ds,) = dept.datasets
    assert ds.fields["category"] == "CAT-3" and ds.fields["owner"] == "PWD IT Cell"
    assert ds.fields["frequency"] == ""
    v, works = ds.tables
    assert (v.format, v.schema, v.metadata) == ("postgres_ddl", "public", None)
    assert (works.format, works.schema, works.metadata) == ("csv", "ops", "storage:inputs/pwd/works_meta.csv")


@pytest.mark.parametrize(
    "bad, message",
    [
        (_VALID.replace("owner:", "ownr:"), r"unknown key\(s\) \['ownr'\]"),
        (_VALID.replace("CAT-3", "cat3"), "must be CAT-1, CAT-2, CAT-3 or CAT-4"),
        (_VALID.replace("format: csv", "format: excel"), "format: 'excel' must be one of"),
        (_VALID.replace("          works:", "          Vishwakarma-T:"), "same table id 'vishwakarma_t'"),
        (_VALID.replace("source: storage:inputs/pwd/v.txt", "schema: public"), r"missing required key\(s\) \['source'\]"),
        (_VALID.replace("  pwd:\n", "  PWD Dept:\n"), "lowercase letters, digits and _"),
        ("departments:\n  pwd:\n    name: P\n    datasets:\n      d: {}\n", "needs `tables` or `field_dictionary`"),
    ],
)
def test_mistakes_fail_with_the_place_to_fix(bad, message):
    with pytest.raises(CatalogError, match=message):
        parse_catalog(bad)


def test_shipped_catalog_is_valid():
    from src.schema_registry.catalog import load_catalog

    departments = load_catalog("catalog.yaml")
    assert any(d.id == "pwd" for d in departments)
