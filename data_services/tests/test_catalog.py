import pytest

from src.schema_registry.catalog import CatalogError, parse_catalog

_VALID = """
departments:
  pwd:
    name: Public Works Department
    description: Department overview.
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
    assert dept.description == "Department overview."
    (ds,) = dept.datasets
    assert ds.fields["category"] == "CAT-3" and ds.fields["owner"] == "PWD IT Cell"
    assert ds.fields["frequency"] == ""
    assert ds.fields["dataset_type"] == ""
    assert ds.fields["schema_source"] == ""
    v, works = ds.tables
    assert (v.format, v.schema, v.metadata) == ("postgres_ddl", "public", None)
    assert (works.format, works.schema, works.metadata) == ("csv", "ops", "storage:inputs/pwd/works_meta.csv")


def test_dataset_type_values_parse():
    for value in ("Citizen Centric", "Administrative"):
        (dept,) = parse_catalog(_VALID.replace("owner: PWD IT Cell", f"dataset_type: {value}"))
        assert dept.datasets[0].fields["dataset_type"] == value


def test_schema_source_values_parse():
    for value in ("Department Provided", "Public Extraction"):
        (dept,) = parse_catalog(_VALID.replace("owner: PWD IT Cell", f"schema_source: {value}"))
        assert dept.datasets[0].fields["schema_source"] == value


@pytest.mark.parametrize(
    "bad, message",
    [
        (_VALID.replace("owner:", "ownr:"), r"unknown key\(s\) \['ownr'\]"),
        (_VALID.replace("CAT-3", "cat3"), "must be CAT-1, CAT-2, CAT-3 or CAT-4"),
        (_VALID.replace("owner: PWD IT Cell", "dataset_type: citizen"), "dataset_type: 'citizen' must be 'Citizen Centric' or 'Administrative'"),
        (_VALID.replace("owner: PWD IT Cell", "schema_source: Extracted"), "schema_source: 'Extracted' must be 'Department Provided' or 'Public Extraction'"),
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
    # Every live department, pwd first exactly as main has it. pwd is
    # another team's; commenting it out here would silently disable their
    # data the moment this branch merges into main, so the list is asserted
    # in full rather than by membership.
    assert [d.id for d in departments] == [
        "pwd",
        "agri_dept",
        "rural_development_department",
        "horticulture_department",
        "women_and_child_development_department",
        "non_proprietary_data",
    ]

    # Kanya Sumangala is Women & Child Development, not Agriculture: two
    # citizen-facing datasets, both personal data (CAT-3), each described by
    # one multi-table Field Dictionary in storage.
    wcd = next(d for d in departments if d.id == "women_and_child_development_department")
    assert wcd.name == "Women and Child Development Department"
    assert [ds.name for ds in wcd.datasets] == ["kanya_sumangla_portal", "pm_matru_vandana_yojana"]
    assert all(ds.fields["category"] == "CAT-3" for ds in wcd.datasets)
    assert all(ds.fields["dataset_type"] == "Citizen Centric" for ds in wcd.datasets)
    assert all(ds.field_dictionary and ds.field_dictionary.startswith("storage:inputs/")
               for ds in wcd.datasets)
