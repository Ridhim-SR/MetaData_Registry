import csv
import io

import pytest

from src.schema_registry.curate import auto_classify
from src.schema_registry.parsers.irrigation_parser import (
    parse_irrigation_field_dictionary,
)

_FIELDS = [
    ("gadhamuktiId", "ID", "text", "No", "", "", "Hidden field in form."),
    ("khand", "खंड", "select (dropdown)", "Yes", "", "Division A, Division B", ""),
    ("entryDate", "प्रविष्टि की दिनांक", "date", "Yes", "", "", ""),
    ("cropName", "फसली नाम", "text", "Yes", "", "", "Hidden field."),
    ("cropYear", "फसली वर्ष", "text", "Yes", "", "", ""),
    ("financialYear", "वित्तीय वर्ष", "text", "Yes", "", "", ""),
    ("month", "माह का नाम", "text", "Yes", "", "", ""),
    ("year", "वर्ष", "text", "Yes", "", "", ""),
    ("gadhamuktiTarget", "गड्ढामुक्त", "text (step=0.01)", "Yes", "step=0.01", "", ""),
    ("naviniTarget", "नवीनीकरण", "number (step=0.01)", "Yes", "step=0.01", "", ""),
    ("totalTarget", "कुल लक्ष्य", "number", "Yes", "", "", "Calculated field."),
    ("gadhamuktiProgress", "गड्ढामुक्त", "number (step=0.01)", "Yes", "step=0.01", "", ""),
    ("naviniProgress", "नवीनीकरण", "number (step=0.01)", "Yes", "step=0.01", "", ""),
    ("totalProgress", "कुल प्रगति", "number", "Yes", "", "", "Calculated field."),
    ("gadhaProgressPer", "प्रगाति प्रतिशत", "number", "Yes", "", "", ""),
    ("naviniProgressPer", "प्रगाति प्रतिशत", "number", "Yes", "", "", ""),
    ("remark", "अभ्युक्ति", "text", "No", "", "", ""),
    ("status", "Status", "select (dropdown)", "No", "", "Submitted", ""),
]


def _dictionary_text(personal_data: str = "", explicit_tag: str = "") -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "Dataset Name",
            "Table Name",
            "Name",
            "Description",
            "Data Format",
            "Maximum Size",
            "Mandatory",
            "Validations",
            "Values",
            "Default Value",
            "Contains Personal Data",
            "Access Level Classification",
            "Example/ Illustration",
            "Tags",
            "Remarks / Comments",
        ],
    )
    writer.writeheader()
    for name, description, data_format, mandatory, validations, values, remarks in _FIELDS:
        writer.writerow(
            {
                "Dataset Name": "Restoration and Renovation Works Dataset",
                "Table Name": "",
                "Name": name,
                "Description": description,
                "Data Format": data_format,
                "Maximum Size": "",
                "Mandatory": mandatory,
                "Validations": validations,
                "Values": values,
                "Default Value": "",
                "Contains Personal Data": personal_data if name == "gadhamuktiId" else "",
                "Access Level Classification": "",
                "Example/ Illustration": "Never copy this example into metadata.",
                "Tags": explicit_tag if name == "gadhamuktiId" else "",
                "Remarks / Comments": remarks,
            }
        )
    return output.getvalue()


def test_parses_all_fields_and_uses_the_reviewed_table_name():
    (table_name, table), = parse_irrigation_field_dictionary(
        _dictionary_text(),
        default_table_name="restoration_and_renovation_works",
    ).items()

    columns = table["columns"]
    metadata = table["business_metadata"]
    assert table_name == "restoration_and_renovation_works"
    assert [column["name"] for column in columns] == [field[0] for field in _FIELDS]
    assert len(columns) == 18
    assert set(metadata) == {field[0] for field in _FIELDS}


def test_keeps_camel_case_names_descriptions_and_format_mapping():
    table = parse_irrigation_field_dictionary(_dictionary_text())[
        "restoration_and_renovation_works"
    ]
    columns = {column["name"]: column for column in table["columns"]}
    metadata = table["business_metadata"]

    # Names stay exactly as the department wrote them.
    assert "gadhamuktiId" in columns
    assert "gadhamukti_id" not in columns

    # Mandatory -> nullable.
    assert columns["gadhamuktiId"]["nullable"] is True
    assert columns["khand"]["nullable"] is False

    # Formats: text/select stay character varying, number becomes numeric,
    # and a numeric step becomes the scale. gadhamuktiTarget is text in the
    # source, so it stays text.
    assert columns["gadhamuktiTarget"]["data_type"] == "character varying"
    assert columns["gadhamuktiTarget"]["scale"] is None
    assert columns["naviniTarget"]["data_type"] == "numeric"
    assert columns["naviniTarget"]["scale"] == 2
    assert columns["totalTarget"]["data_type"] == "numeric"
    assert columns["khand"]["data_type"] == "character varying"
    assert columns["entryDate"]["data_type"] == "date"

    # The source description is used verbatim -- remarks, validations and
    # allowed values are not folded into it.
    assert metadata["gadhamuktiId"]["business_description"] == "ID"
    assert metadata["khand"]["business_description"] == "खंड"
    assert metadata["entryDate"]["business_description"] == "प्रविष्टि की दिनांक"
    assert "Hidden field" not in metadata["gadhamuktiId"]["business_description"]
    assert "Allowed values" not in metadata["khand"]["business_description"]
    assert "Never copy this example" not in str(metadata)
    assert auto_classify("cropName") == "Public"


def test_generates_reviewable_tag_suggestions_without_touching_descriptions():
    table = parse_irrigation_field_dictionary(_dictionary_text())
    metadata = table["restoration_and_renovation_works"]["business_metadata"]

    assert {name: value["tag"] for name, value in metadata.items()} == {
        "gadhamuktiId": "Identifier",
        "khand": "Administrative-Unit",
        "entryDate": "Date/Timestamp",
        # No controlled tag fits a crop label yet.
        "cropName": "",
        "cropYear": "Date/Timestamp",
        "financialYear": "Date/Timestamp",
        "month": "Date/Timestamp",
        "year": "Date/Timestamp",
        "gadhamuktiTarget": "Quantity",
        "naviniTarget": "Quantity",
        "totalTarget": "Quantity",
        "gadhamuktiProgress": "Quantity",
        "naviniProgress": "Quantity",
        "totalProgress": "Quantity",
        "gadhaProgressPer": "Quantity",
        "naviniProgressPer": "Quantity",
        "remark": "Remarks",
        "status": "Status/Workflow",
    }
    # Descriptions remain exactly what the department supplied.
    assert metadata["gadhamuktiTarget"]["business_description"] == "गड्ढामुक्त"


def test_personal_data_answer_is_classified_as_pii():
    parsed = parse_irrigation_field_dictionary(_dictionary_text(personal_data="Yes"))
    assert parsed["restoration_and_renovation_works"]["business_metadata"]["gadhamuktiId"][
        "classification"
    ] == "PII"


def test_unknown_explicit_tag_is_rejected():
    with pytest.raises(ValueError, match="unsupported tag 'made-up'"):
        parse_irrigation_field_dictionary(_dictionary_text(explicit_tag="made-up"))


def test_add_and_local_sync_ingest_the_catalogued_table(tmp_path):
    from src.schema_registry.add import add
    from src.schema_registry.catalog import load_catalog
    from src.schema_registry.registry import lookups, paths
    from src.schema_registry.sync import sync
    from src.storage.local import LocalObjectStorage

    storage = LocalObjectStorage(tmp_path / "storage")
    source = tmp_path / "irrigation.csv"
    source.write_text(_dictionary_text(), encoding="utf-8")
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("departments:\n", encoding="utf-8")

    add(
        storage,
        catalog,
        str(source),
        "irrigation_dept",
        "restoration_and_renovation_works",
        department_name="Irrigation Department",
    )
    department = load_catalog(catalog)
    outcomes = sync(
        storage,
        department,
        only_department="irrigation_dept",
    )

    assert any(outcome.ingest == "ingested" for outcome in outcomes)
    table_id = (
        "irrigation_dept.restoration_and_renovation_works."
        "restoration_and_renovation_works"
    )
    assert lookups.get_table(storage, table_id) is not None
    snapshots = storage.list(
        paths.curated_schemas_prefix(
            "irrigation_dept",
            "restoration_and_renovation_works",
            "restoration_and_renovation_works",
        )
    )
    (snapshot,) = snapshots
    columns = storage.read_csv(snapshot)
    assert len(columns) == 18
    assert next(column for column in columns if column["name"] == "cropName")[
        "classification"
    ] == "Public"
    assert next(column for column in columns if column["name"] == "khand")["tag"] == (
        "Administrative-Unit"
    )
    assert next(column for column in columns if column["name"] == "gadhamuktiId")[
        "business_description"
    ] == "ID"
    assert next(column for column in columns if column["name"] == "entryDate")[
        "business_description"
    ] == "प्रविष्टि की दिनांक"
