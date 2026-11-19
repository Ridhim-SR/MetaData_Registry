"""Parser for the Irrigation Department's form-definition CSV exports.

The department supplies two header layouts for the same field dictionary:

* the original form-definition export (``Name``, ``Description``,
  ``Data Format``, ``Mandatory``, ...), where ``Table Name`` is blank; and
* the 2026-11 portal/bulletin layout (``Dataset Field/Variable/Column``,
  ``Data/Field/Column Description``, ``Format/Data Type``,
  ``Mandatory (Y/N)``, ...), where ``Dataset Name`` is blank and every row
  carries its ``Table Name``.

Both are read here because treating either as a normal Field Dictionary
would silently drop every description and tag. ``_NAME_HEADERS`` and the
other alias tuples below are the single place those spellings live, so a
future delivery that renames a column fails loudly instead of publishing
blank descriptions.

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

``Table Name`` is blank in the original layout, so rows are grouped under
``default_table_name`` (the reviewed table id) instead; the newer layout
supplies ``Table Name`` and groupings come from it. ``Values``,
``Validations``, ``Example/ Illustration``, ``Sample Value`` and
``Remarks / Comments`` are form-implementation details, not business
descriptions, and are not copied into the description.
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

# One tuple per logical field, listing every header spelling the department
# has used. The first spelling is the canonical one; lookups try each in turn.
_NAME_HEADERS = ("Name", "Dataset Field/Variable/Column", "Dataset Field")
_HINDI_HEADERS = (
    "Name (Hindi)",
    "Hindi Name",
    "Field Label (Hindi/Regional Language)",
)
_DESCRIPTION_HEADERS = (
    "Description",
    "Data/Field/Column Description",
    "Data Description",
)
_FORMAT_HEADERS = ("Data Format", "Format/Data Type", "Format")
_MAX_SIZE_HEADERS = ("Maximum Size", "Length")
_MANDATORY_HEADERS = ("Mandatory", "Mandatory (Y/N)")
_PERSONAL_HEADERS = ("Contains Personal Data", "Personal Data (Y/N)")

# Without a name, a format and a mandatory answer there is nothing to build a
# column from. The check is per group so the newer layout's headers count.
_REQUIRED_HEADER_GROUPS = (
    ("field name", _NAME_HEADERS),
    ("format", _FORMAT_HEADERS),
    ("mandatory", _MANDATORY_HEADERS),
)


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
    ``gadhamuktiTarget`` as text, so it stays text). ``number``,
    ``number (step=0.01)`` and ``Numeric (8 to 9 digits)`` become numeric;
    a step's decimal places become the scale. Everything else -- ``date``,
    ``DD-MM-YYYY / Date``, ``HH.MM / Time``, ``Char(3)``, ... -- is the
    shared Field Dictionary vocabulary.
    """

    text = format_text.strip()
    lowered = text.lower()

    if lowered.startswith("select") or lowered.startswith("dropdown"):
        return FormatSpec("character varying", None, None)

    spec = parse_format_full(text)
    if spec.data_type == "numeric":
        step_match = _STEP_RE.search(text)
        if step_match and "." in step_match.group(1):
            spec = FormatSpec(spec.data_type, spec.length, len(step_match.group(1).partition(".")[2]))
    return spec


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
    personal_data = _cell(row, *_PERSONAL_HEADERS).lower()

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
    fieldnames = reader.fieldnames or []
    missing = [
        f"{group} (one of: {' / '.join(aliases)})"
        for group, aliases in _REQUIRED_HEADER_GROUPS
        if not any(alias in fieldnames for alias in aliases)
    ]
    if missing:
        raise ValueError(
            f"{label}: Irrigation field dictionary is missing required column(s) "
            f"{missing}; headers found: {reader.fieldnames}"
        )

    tables: dict[str, dict] = {}
    for row_number, row in enumerate(reader, start=2):
        field_name = _cell(row, *_NAME_HEADERS)
        if not field_name:
            raise ValueError(f"{label}:{row_number}: field name is blank")

        # The original layout names the dataset and leaves Table Name blank;
        # the newer one leaves Dataset Name blank and names every table. A row
        # that answers neither has no place to go.
        dataset_name = _cell(row, "Dataset Name")
        raw_table_name = _cell(row, "Table Name")
        if not dataset_name and not raw_table_name:
            raise ValueError(
                f"{label}:{row_number}: Dataset Name and Table Name are both blank"
            )

        table_name = raw_table_name or default_table_name.strip()
        if not table_name:
            raise ValueError(f"{label}:{row_number}: table name is blank")

        spec = _parse_format(_cell(row, *_FORMAT_HEADERS))
        maximum_size = _cell(row, *_MAX_SIZE_HEADERS)
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
            "business_description": _cell(row, *_DESCRIPTION_HEADERS),
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
            "nullable": _nullable(_cell(row, *_MANDATORY_HEADERS), field_name),
            "default": _cell(row, "Default Value") or None,
        }
        name_hindi = _cell(row, *_HINDI_HEADERS)
        if name_hindi:
            column["name_hindi"] = name_hindi
        table["columns"].append(column)
        table["business_metadata"][field_name] = metadata

    if not tables:
        raise ValueError(f"{label}: no field rows found")
    return tables
