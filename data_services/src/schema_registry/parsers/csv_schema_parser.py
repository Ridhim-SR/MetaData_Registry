import csv
import re

# canonical field -> normalized (lowercase, underscored) header aliases.
# "required"-style columns are deliberately not aliased to "nullable" here --
# they're the inverse (required=true means nullable=false), so guessing
# would silently flip the meaning instead of just being imprecise.
COLUMN_ALIASES: dict[str, list[str]] = {
    "name": ["name", "field_name", "column_name", "column", "field"],
    "data_type": ["data_type", "type", "datatype", "field_type"],
    "length": ["length", "max_length", "size"],
    "nullable": ["nullable", "is_nullable", "allow_null"],
    "default": ["default", "default_value"],
}

REQUIRED_FIELDS = ["name", "data_type"]

_FALSE_VALUES = {"n", "no", "false", "0"}


def _normalize_header(header: str) -> str:
    return re.sub(r"[^\w]+", "_", header.strip().lower()).strip("_")


def _to_bool(value: str | None, default: bool = True) -> bool:
    value = (value or "").strip().lower()
    return default if not value else value not in _FALSE_VALUES


def _build_header_map(headers: list[str]) -> dict[str, str]:
    """Map each canonical field to whichever actual CSV header matches one
    of its known aliases, regardless of the source department's naming."""

    normalized = {_normalize_header(h): h for h in headers}
    header_map = {}

    for canonical, aliases in COLUMN_ALIASES.items():
        match = next((normalized[a] for a in aliases if a in normalized), None)
        if match:
            header_map[canonical] = match

    missing = [f for f in REQUIRED_FIELDS if f not in header_map]
    if missing:
        raise ValueError(f"CSV is missing required field(s) {missing}. Headers found: {headers}")

    return header_map


def parse_csv_columns(path: str) -> list[dict]:
    """Parse a department-submitted CSV of column definitions into the same
    canonical shape as ddl_parser.parse_postgres_columns, regardless of
    that department's own header names or column order."""

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        header_map = _build_header_map(reader.fieldnames or [])


        columns = []
        for row in reader:
            length = (row.get(header_map.get("length", ""), "") or "").strip()

            columns.append(
                {
                    "name": row[header_map["name"]].strip(),
                    "data_type": row[header_map["data_type"]].strip(),
                    "length": int(length) if length.isdigit() else None,
                    "scale": None,
                    "nullable": _to_bool(row.get(header_map.get("nullable", ""))),
                    "default": (row.get(header_map.get("default", ""), "") or "").strip() or None,
                }
            )

        return columns
