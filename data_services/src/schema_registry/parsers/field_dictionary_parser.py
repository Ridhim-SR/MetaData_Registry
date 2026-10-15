import csv
import io
import re
from typing import NamedTuple

from src.utils.logger import get_logger

logger = get_logger(__name__)


class FormatSpec(NamedTuple):
    """Everything a Format-cell can tell us about the column: the Postgres
    type, its character/precision count, and its decimal scale."""

    data_type: str
    length: int | None
    scale: int | None


# Date-assembly masks a department writes instead of a type, e.g.
# "WRYYDDnnnnnnn" (weekday/century/year/month/day + serial). The whole cell
# has to look like one -- uppercase pattern letters plus an `n` placeholder
# run -- so ordinary words like "Monetary" can't fall in here. A mask's
# "length" is the mask width itself (see parse_format_full).
_PATTERN_CODE_RULE = re.compile(r"^[A-Z]{2,6}[A-Z0-9]{0,4}n{2,14}[A-Z0-9]{0,4}$")

# (pattern over the start of the Format text, Postgres type) -- first match
# wins, so keep broader families (numeric/date/text) above the narrower
# department-invented spellings (VARCHAR, Enum, WRYYDDnnnnnnn). These are
# the literal mappings agreed with the user rather than a semantic guess
# (e.g. an Aadhaar number stays "numeric" because the source says "Numeric",
# even though VARCHAR would better preserve leading zeros -- that tradeoff
# was a deliberate choice, not an oversight).
FORMAT_TYPE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^numeric", re.IGNORECASE), "numeric"),
    (re.compile(r"^decimal", re.IGNORECASE), "numeric"),
    (re.compile(r"^date", re.IGNORECASE), "date"),
    (re.compile(r"^(text|option|alphanumeric|image|file)", re.IGNORECASE), "character varying"),
    (re.compile(r"^(varchar|character varying)", re.IGNORECASE), "character varying"),
    (re.compile(r"^char", re.IGNORECASE), "character"),
    (re.compile(r"^string", re.IGNORECASE), "character varying"),
    (re.compile(r"^boolean", re.IGNORECASE), "boolean"),
    (re.compile(r"^bigint", re.IGNORECASE), "bigint"),
    (re.compile(r"^integer", re.IGNORECASE), "integer"),
    (re.compile(r"^enum", re.IGNORECASE), "character varying"),
    (re.compile(r"^dropdown", re.IGNORECASE), "character varying"),
    (re.compile(r"^year", re.IGNORECASE), "integer"),
    (_PATTERN_CODE_RULE, "character varying"),
]

# Captures a leading digit/character count in parentheses, e.g.
# "Numeric (12 Digits)" -> 12, "Alphanumeric (11 Characters)" -> 11,
# "VARCHAR(30)" -> 30, "String (20-character)" -> 20, "Numeric (10)" -> 10.
_LENGTH_RE = re.compile(r"\(\s*(\d+)\s*(?:[-\s]?(?:digits?|characters?|chars?))?\s*\)", re.IGNORECASE)

# "Decimal (18,2)" -> precision 18 / scale 2. Checked before _LENGTH_RE,
# which deliberately cannot match this shape (it has no closing paren
# straight after the first number).
_SCALE_RE = re.compile(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)")

# ENUM('Rural','Urban') -> the longest value is the natural width.
_ENUM_LITERAL_RE = re.compile(r"'([^']*)'")


def parse_format_full(format_text: str) -> FormatSpec:
    """Map one Format-column value to its (postgres_type, length, scale).
    Raises if the text doesn't start with any known word -- silently guessing
    here is worse than failing loudly, since a wrong type reaches
    OpenMetadata."""

    text = format_text.strip()
    for pattern, data_type in FORMAT_TYPE_RULES:
        if not pattern.match(text):
            continue

        scale_match = _SCALE_RE.search(text)
        if scale_match:
            return FormatSpec(data_type, int(scale_match.group(1)), int(scale_match.group(2)))

        length_match = _LENGTH_RE.search(text)
        length = int(length_match.group(1)) if length_match else None
        if length is None:
            literals = _ENUM_LITERAL_RE.findall(text)
            if literals:
                length = max(len(value) for value in literals)
            elif pattern is _PATTERN_CODE_RULE:
                length = len(text)
        return FormatSpec(data_type, length, None)

    logger.error(f"field_dictionary_parser: unrecognized Format value '{format_text}'")
    raise ValueError(
        f"Unrecognized Format value '{format_text}' -- add a rule to FORMAT_TYPE_RULES in "
        f"field_dictionary_parser.py."
    )


def parse_format(format_text: str) -> tuple[str, int | None]:
    """Back-compatible two-tuple view of parse_format_full(); see that
    function for the matching rules and the raise-on-unknown contract."""

    spec = parse_format_full(format_text)
    return spec.data_type, spec.length


# Columns the file must carry to be a field dictionary at all -- without
# them there is no grouping key and no field name, i.e. nothing to parse.
_REQUIRED_HEADERS = ("Dataset Name", "Dataset Field")


def parse_field_dictionary_text(text: str, label: str = "<text>") -> dict[str, dict]:
    """Parse a multi-table Field Dictionary CSV (columns: Dataset Name,
    Dataset Field, Data Description, Format, Mandatory (Y/N),
    Personal Data (Y/N), ...) into one entry per distinct "Dataset Name",
    each with the canonical raw-column shape
    (name/data_type/length/scale/nullable/default) plus a business_metadata
    dict -- both in the exact shapes pipeline.run() / curate_schema() already
    expect, so nothing downstream needs to change.

    One row = one field of one table; "Dataset Name" is the grouping key
    that tells us which of the several tables in this single file a row
    belongs to.

    Bulk-file tolerance, deliberately narrower than parse_format's contract:
    a row this parser can't make sense of is logged and either skipped (no
    table/field name) or downgraded to a plain character varying with a
    `format_note` (unrecognised Format), so one bad cell of a 387-row
    workbook doesn't cost the department the other 386. Every downgrade is
    recorded in business_metadata, which is where the field-mapping report
    reads its "needs fixing" list from.
    """

    tables: dict[str, dict] = {}

    reader = csv.DictReader(io.StringIO(text))
    missing = [header for header in _REQUIRED_HEADERS if header not in (reader.fieldnames or [])]
    if missing:
        logger.error(f"field_dictionary_parser: missing required column(s) {missing}")
        raise ValueError(
            f"Field dictionary is missing required column(s) {missing}. "
            f"Headers found: {reader.fieldnames}"
        )

    for row in reader:
        table_name = (row.get("Dataset Name") or "").strip()
        field_name = (row.get("Dataset Field") or "").strip()
        if not table_name or not field_name:
            logger.warning(f"field_dictionary_parser: skipping row without a dataset/field name: {row}")
            continue

        format_text = (row.get("Format") or "").strip()
        try:
            spec = parse_format_full(format_text)
        except ValueError:
            spec = FormatSpec("character varying", None, None)
            format_note = f"unrecognized Format '{format_text}' -- treated as character varying"
            logger.warning(f"field_dictionary_parser: '{table_name}.{field_name}': {format_note}")
        else:
            format_note = ""

        mandatory = (row.get("Mandatory (Y/N)") or "").strip().upper()
        # "Y (Rural)" / "Y (Urban)" are still mandatory: any Y means
        # NOT NULL, not just a bare one.
        nullable = not mandatory.startswith("Y")

        personal = (row.get("Personal Data (Y/N)") or "").strip().upper()
        metadata: dict = {
            "business_description": (row.get("Data Description") or "").strip(),
            # Recorded here as what the department said, but NOT written into
            # the per-table business-metadata file by field_dictionary_ingest
            # (that writes name + business_description only) -- tags are set
            # by curate's auto-tag, per the decision to leave ingest blank.
            "tag": "PII" if personal.startswith("Y") else "",
        }
        if format_note:
            metadata["format_note"] = format_note

        table = tables.setdefault(table_name, {"columns": [], "business_metadata": {}})
        table["columns"].append(
            {
                "name": field_name,
                "data_type": spec.data_type,
                "length": spec.length,
                "scale": spec.scale,
                "nullable": nullable,
                "default": None,
            }
        )
        table["business_metadata"][field_name] = metadata

    for table_name, table in tables.items():
        logger.info(f"field_dictionary_parser: '{table_name}' -> {len(table['columns'])} column(s)")
    logger.info(f"field_dictionary_parser: parsed {len(tables)} table(s) from {label}")
    return tables


def parse_field_dictionary(path: str) -> dict[str, dict]:
    """The file-path view of parse_field_dictionary_text() -- utf-8-sig
    because spreadsheet exports start with a BOM that would otherwise land
    in the first header name."""

    with open(path, newline="", encoding="utf-8-sig") as f:
        return parse_field_dictionary_text(f.read(), label=str(path))

