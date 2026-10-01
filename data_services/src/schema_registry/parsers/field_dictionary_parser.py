import csv
import re

# (pattern over the start of the Format text, Postgres type) -- first match
# wins. This file's "Format" column describes application/data-entry field
# types in free text ("Numeric (12 Digits)", "Option: Bride, Guardian"),
# not real database types -- these are the literal mappings agreed with the
# user rather than a semantic guess (e.g. an Aadhaar number stays "numeric"
# because the source says "Numeric", even though VARCHAR would better
# preserve leading zeros -- that tradeoff was a deliberate choice, not an
# oversight).
FORMAT_TYPE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^numeric", re.IGNORECASE), "numeric"),
    (re.compile(r"^date", re.IGNORECASE), "date"),
    (re.compile(r"^(text|option|alphanumeric|image|file)", re.IGNORECASE), "character varying"),
]

# Captures a leading digit/character count in parentheses, e.g.
# "Numeric (12 Digits)" -> 12, "Alphanumeric (11 Characters)" -> 11.
_LENGTH_RE = re.compile(r"\((\d+)\s*(?:Digits?|Characters?)\)", re.IGNORECASE)


def parse_format(format_text: str) -> tuple[str, int | None]:
    """Map one Format-column value to (postgres_type, length). Raises if the
    text doesn't start with any known word -- silently guessing here is
    worse than failing loudly, since a wrong type reaches OpenMetadata."""

    text = format_text.strip()
    for pattern, data_type in FORMAT_TYPE_RULES:
        if pattern.match(text):
            length_match = _LENGTH_RE.search(text)
            length = int(length_match.group(1)) if length_match else None
            return data_type, length

    raise ValueError(
        f"Unrecognized Format value '{format_text}' -- add a rule to FORMAT_TYPE_RULES in "
        f"field_dictionary_parser.py."
    )


def parse_field_dictionary(path: str) -> dict[str, dict]:
    """Parse a multi-table Field Dictionary CSV (columns: Dataset Name,
    Dataset Field, Data Description, Format, Mandatory (Y/N), ...) into one
    entry per distinct "Dataset Name", each with the canonical raw-column
    shape (name/data_type/length/scale/nullable/default) plus a
    business_metadata dict -- both in the exact shapes pipeline.run() /
    curate_schema() already expect, so nothing downstream needs to change.

    One row = one field of one table; "Dataset Name" is the grouping key
    that tells us which of the several tables in this single file a row
    belongs to.
    """

    tables: dict[str, dict] = {}

    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            table_name = row["Dataset Name"].strip()
            field_name = row["Dataset Field"].strip()
            data_type, length = parse_format(row["Format"])
            nullable = row["Mandatory (Y/N)"].strip().upper() != "Y"

            table = tables.setdefault(table_name, {"columns": [], "business_metadata": {}})
            table["columns"].append(
                {
                    "name": field_name,
                    "data_type": data_type,
                    "length": length,
                    "scale": None,
                    "nullable": nullable,
                    "default": None,
                }
            )
            table["business_metadata"][field_name] = {
                "business_description": row.get("Data Description", "").strip(),
            }

    return tables
