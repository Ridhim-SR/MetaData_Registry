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

# The Hindi display labels the department supplies in `Name (Hindi)`. They are
# deliberately a separate attribute from `Description` (business text).
_HINDI = {
    "gadhamuktiId": "ID",
    "khand": "खंड",
    "entryDate": "प्रविष्टि की दिनांक",
    "cropName": "फसली नाम",
    "cropYear": "फसली वर्ष",
    "financialYear": "वित्तीय वर्ष",
    "month": "माह का नाम",
    "year": "वर्ष",
    "gadhamuktiTarget": "गड्ढामुक्त",
    "naviniTarget": "नवीनीकरण",
    "totalTarget": "कुल लक्ष्य",
    "gadhamuktiProgress": "गड्ढामुक्त",
    "naviniProgress": "नवीनीकरण",
    "totalProgress": "कुल प्रगति",
    "gadhaProgressPer": "प्रगाति गड्ढामुक्ति कार्यो का प्रतिशत",
    "naviniProgressPer": "प्रगाति नवीनीकरण एवं रेस्टोरेशन कार्यो का प्रतिशत",
    "remark": "अभ्युक्ति",
    "status": "Status",
}


def _dictionary_text(
    personal_data: str = "",
    explicit_tag: str = "",
    include_hindi: bool = True,
    descriptions: dict[str, str] | None = None,
) -> str:
    descriptions = descriptions or {}
    fieldnames = ["Dataset Name", "Table Name", "Name"]
    if include_hindi:
        fieldnames.append("Name (Hindi)")
    fieldnames.extend(
        [
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
        ]
    )
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for name, description, data_format, mandatory, validations, values, remarks in _FIELDS:
        row = {
            "Dataset Name": "Restoration and Renovation Works Dataset",
            "Table Name": "",
            "Name": name,
            "Description": descriptions.get(name, description),
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
        if include_hindi:
            row["Name (Hindi)"] = _HINDI[name]
        writer.writerow(row)
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

    # `Name (Hindi)` is the column's display label, kept separately from the
    # English/Hindi business description.
    assert columns["gadhamuktiId"]["name_hindi"] == "ID"
    assert columns["khand"]["name_hindi"] == "खंड"
    assert columns["gadhaProgressPer"]["name_hindi"] == "प्रगाति गड्ढामुक्ति कार्यो का प्रतिशत"
    assert columns["naviniProgressPer"]["name_hindi"] == (
        "प्रगाति नवीनीकरण एवं रेस्टोरेशन कार्यो का प्रतिशत"
    )

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


def test_english_descriptions_replace_the_hindi_label_descriptions():
    descriptions = {
        "gadhamuktiId": "Unique system-generated identifier of the record.",
        "khand": (
            "Canal division (खंड) under which the restoration and renovation "
            "work is reported."
        ),
    }
    table = parse_irrigation_field_dictionary(
        _dictionary_text(descriptions=descriptions)
    )["restoration_and_renovation_works"]
    metadata = table["business_metadata"]
    columns = {column["name"]: column for column in table["columns"]}

    # The English description replaces the old Hindi-label description...
    assert metadata["gadhamuktiId"]["business_description"] == descriptions["gadhamuktiId"]
    assert metadata["khand"]["business_description"] == descriptions["khand"]
    # ...while the Hindi label is still carried as the display name.
    assert columns["gadhamuktiId"]["name_hindi"] == "ID"
    assert columns["khand"]["name_hindi"] == "खंड"
    assert columns["entryDate"]["name_hindi"] == "प्रविष्टि की दिनांक"


def test_legacy_export_without_a_hindi_column_still_parses():
    table = parse_irrigation_field_dictionary(
        _dictionary_text(include_hindi=False)
    )["restoration_and_renovation_works"]
    columns = {column["name"]: column for column in table["columns"]}

    # No `Name (Hindi)` header: the columns simply have no display label, and
    # the legacy Hindi `Description` values are kept as business text.
    assert "name_hindi" not in columns["khand"]
    assert "name_hindi" not in columns["entryDate"]
    assert table["business_metadata"]["khand"]["business_description"] == "खंड"
    assert table["business_metadata"]["entryDate"]["business_description"] == "प्रविष्टि की दिनांक"


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
    # The Hindi display label survives curation into the snapshot, ready for
    # OpenMetadata's Column.displayName.
    assert next(column for column in columns if column["name"] == "khand")[
        "name_hindi"
    ] == "खंड"
    assert next(column for column in columns if column["name"] == "entryDate")[
        "name_hindi"
    ] == "प्रविष्टि की दिनांक"
    assert next(column for column in columns if column["name"] == "gadhamuktiId")[
        "business_description"
    ] == "ID"
    assert next(column for column in columns if column["name"] == "entryDate")[
        "business_description"
    ] == "प्रविष्टि की दिनांक"
