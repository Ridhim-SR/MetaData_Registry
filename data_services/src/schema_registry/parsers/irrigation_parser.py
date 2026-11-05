"""Parser for the Irrigation Department's form-definition CSV export.

The department submits one file per dataset. Its shape differs from the
Field Dictionary format in ``field_dictionary_parser.py``: the column name
is in ``Name`` (not ``Dataset Field``), the description in ``Description``
(not ``Data Description``), the format in ``Data Format`` (not ``Format``)
and the mandatory answer in ``Mandatory`` (not ``Mandatory (Y/N)``). Treating
it as a normal Field Dictionary would therefore silently drop every
description and tag, so it gets its own small parser.

What is kept as-is:
  * ``Name`` -> the column name, exactly as written (this export is
    camelCase and is deliberately not snake_cased);
  * ``Name (Hindi)`` -> ``name_hindi``, the column's display label. It is an
    attribute of the column, not a business description; when the header is
    absent the column keeps whatever label it already had;
  * ``Description`` -> ``business_description`` verbatim. A description
    supplied by the department is never rewritten; a blank one stays blank
    so it can be filled by ``ai_metadata.py`` later;
  * ``Mandatory`` -> nullable (Yes means NOT NULL, No/blank means nullable);
  * ``Default Value`` -> the column default;
  * ``Tags`` -> the FieldTag answer when one is supplied, otherwise a
    reviewable ``auto_tag()`` suggestion.

``Table Name`` is blank in this format, so rows are grouped under
``default_table_name`` (the reviewed table id) instead. ``Values``,
``Validations``, ``Example/ Illustration`` and ``Remarks / Comments`` are
form-implementation details, not business descriptions, and are not copied
into the description.
"""

import csv
import io
import re

from src.schema_registry.curate import auto_tag, validate_classification, validate_tag
from src.schema_registry.parsers.field_dictionary_parser import (
    FormatSpec,
    parse_format_full,
)

_YES = {"yes", "y"}
_NO = {"no", "n"}
_STEP_RE = re.compile(r"\bstep\s*=\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)

_REQUIRED_HEADERS = ("Dataset Name", "Name", "Data Format", "Mandatory")


def _cell(row: dict[str, str | None], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value and value.strip():
            return value.strip()
    return ""


def _parse_format(format_text: str) -> FormatSpec:
    """Map this export's format vocabulary to a Postgres type.

    ``text``/``select (dropdown)`` become character varying (even when the
    form attaches a ``step`` to a text field: the department marked
    ``gadhamuktiTarget`` as text, so it stays text). ``number`` and
    ``number (step=0.01)`` become numeric; the step's decimal places become
    the scale.
    """

    text = format_text.strip()
    lowered = text.lower()

    if lowered.startswith("select") or lowered.startswith("dropdown"):
        return FormatSpec("character varying", None, None)

    if lowered.startswith(("number", "numeric")):
        step_match = _STEP_RE.search(text)
        scale = (
            len(step_match.group(1).partition(".")[2])
            if step_match and "." in step_match.group(1)
            else None
        )
        return FormatSpec("numeric", None, scale)

    return parse_format_full(text)


def _nullable(value: str, field_name: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return True
    if normalized in _YES:
        return False
    if normalized in _NO:
        return True
    raise ValueError(
        f"{field_name}: unsupported Mandatory value {value!r}; expected Yes or No"
    )


def _classification(row: dict[str, str | None], field_name: str) -> str:
    classification = _cell(row, "Access Level Classification", "Classification")
    personal_data = _cell(row, "Contains Personal Data").lower()

    if classification and not validate_classification(classification):
        raise ValueError(
            f"{field_name}: unsupported Access Level Classification {classification!r}"
        )
    if personal_data in _YES:
        return "PII"
    if personal_data and personal_data not in _NO:
        raise ValueError(
            f"{field_name}: unsupported Contains Personal Data value {personal_data!r}; "
            "expected Yes or No"
        )
    return classification


def parse_irrigation_field_dictionary(
    text: str,
    label: str = "<text>",
    default_table_name: str = "restoration_and_renovation_works",
) -> dict[str, dict]:
    """Convert the department's form fields into standard registry columns."""

    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    missing = [name for name in _REQUIRED_HEADERS if name not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(
            f"{label}: Irrigation field dictionary is missing required column(s) "
            f"{missing}; headers found: {reader.fieldnames}"
        )

    tables: dict[str, dict] = {}
    for row_number, row in enumerate(reader, start=2):
        field_name = _cell(row, "Name")
        if not field_name:
            raise ValueError(f"{label}:{row_number}: field Name is blank")

        dataset_name = _cell(row, "Dataset Name")
        if not dataset_name:
            raise ValueError(f"{label}:{row_number}: Dataset Name is blank")

        table_name = _cell(row, "Table Name") or default_table_name.strip()
        if not table_name:
            raise ValueError(f"{label}:{row_number}: table name is blank")

        spec = _parse_format(_cell(row, "Data Format"))
        maximum_size = _cell(row, "Maximum Size")
        if maximum_size and spec.length is None and spec.data_type in {
            "character",
            "character varying",
        }:
            if not maximum_size.isdigit():
                raise ValueError(
                    f"{label}:{row_number}: unsupported Maximum Size {maximum_size!r}"
                )
            spec = FormatSpec(spec.data_type, int(maximum_size), spec.scale)

        tag = _cell(row, "Tags", "Tag")
        if tag and not validate_tag(tag):
            raise ValueError(f"{field_name}: unsupported tag {tag!r}")
        if not tag:
            tag = auto_tag(field_name) or ""

        metadata = {
            "business_description": _cell(row, "Description"),
            "tag": tag,
            "classification": _classification(row, field_name),
        }

        table = tables.setdefault(
            table_name,
            {"columns": [], "business_metadata": {}},
        )
        column = {
            "name": field_name,
            "data_type": spec.data_type,
            "length": spec.length,
            "scale": spec.scale,
            "nullable": _nullable(_cell(row, "Mandatory"), field_name),
            "default": _cell(row, "Default Value") or None,
        }
        name_hindi = _cell(row, "Name (Hindi)", "Hindi Name")
        if name_hindi:
            column["name_hindi"] = name_hindi
        table["columns"].append(column)
        table["business_metadata"][field_name] = metadata

    if not tables:
        raise ValueError(f"{label}: no field rows found")
    return tables
