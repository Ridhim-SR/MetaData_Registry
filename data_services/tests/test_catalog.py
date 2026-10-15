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


def test_load_catalog_reads_a_utf8_description(tmp_path):
    """Windows' locale codec is cp1252: a Hindi description must still load."""

    from src.schema_registry.catalog import load_catalog

    path = tmp_path / "catalog.yaml"
    path.write_text(
        _VALID.replace(
            "owner: PWD IT Cell",
            "owner: PWD IT Cell\n"
            "        description: >-\n"
            "          विधान मण्डल क्षेत्र विकास निधि योजना",
        ),
        encoding="utf-8",
    )

    (dept,) = load_catalog(path)
    assert "विधान मण्डल क्षेत्र विकास निधि योजना" in dept.datasets[0].fields["dataset_description"]


def test_shipped_catalog_is_valid():
    from src.schema_registry.catalog import load_catalog

    departments = load_catalog("catalog.yaml")
    # All three live departments, pwd first exactly as main has it. pwd is
    # another team's; commenting it out here would silently disable their
    # data the moment this branch merges into main, so the list is asserted
    # in full rather than by membership.
    assert [d.id for d in departments] == ["pwd", "agri_dept", "rural_development_department"]


@pytest.mark.parametrize("given,stored", [("Y", "Y"), ("N", "N"), ("yes", "Y"), ("no", "N"), ("true", "Y"), ("", "")])
def test_api_available_is_normalised_to_y_or_n(given, stored):
    text = _VALID.replace("owner: PWD IT Cell", f"owner: PWD IT Cell\n        api_available: \"{given}\"")
    assert parse_catalog(text)[0].datasets[0].fields["api_available"] == stored


def test_api_available_bare_yaml_boolean_is_read_as_y():
    text = _VALID.replace("owner: PWD IT Cell", "owner: PWD IT Cell\n        api_available: yes")
    assert parse_catalog(text)[0].datasets[0].fields["api_available"] == "Y"


def test_api_available_rejects_anything_else():
    text = _VALID.replace("owner: PWD IT Cell", "owner: PWD IT Cell\n        api_available: maybe")
    with pytest.raises(CatalogError, match="must be Y or N"):
        parse_catalog(text)
