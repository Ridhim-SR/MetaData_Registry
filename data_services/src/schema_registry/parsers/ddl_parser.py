import re
from dataclasses import asdict, dataclass

from src.utils.logger import get_logger

logger = get_logger(__name__)

_LENGTH_RE = re.compile(r"\((\d+)(?:\s*,\s*(\d+))?\)")

# Words that end a column's data type and start one of its constraint
# clauses. None of them is ever part of a Postgres type name, so the type is
# everything before the first one.
_CLAUSE_KEYWORDS = {
    "DEFAULT", "NOT", "NULL", "COLLATE", "CONSTRAINT", "CHECK",
    "UNIQUE", "PRIMARY", "REFERENCES", "GENERATED",
}

# An entry starting with one of these is a table-level constraint, not a
# column -- e.g. "CONSTRAINT pk PRIMARY KEY (id)" in a pasted CREATE TABLE body.
_TABLE_CONSTRAINT_RE = re.compile(r"^(CONSTRAINT|PRIMARY\s+KEY|UNIQUE|FOREIGN\s+KEY|CHECK|EXCLUDE)\b", re.IGNORECASE)
_CREATE_TABLE_RE = re.compile(r"^\s*CREATE\s+(\w+\s+)*TABLE\b", re.IGNORECASE)


@dataclass
class ColumnDef:
    name: str
    data_type: str
    length: int | None
    scale: int | None
    nullable: bool
    default: str | None


def _scan(text: str, split_on):
    """Yield (char, at_top_level) for each char, where at_top_level means
    outside any parentheses and outside '...' / "..." quotes -- the only
    places a separator (comma between columns, space between tokens) counts.
    Doubled quotes ('it''s', "a""b") stay inside their quoted run."""

    depth = 0
    quote = None
    for char in text:
        if quote:
            if char == quote:
                quote = None  # a doubled quote just reopens on the next char
            yield char, False
            continue
        if char in ("'", '"'):
            quote = char
            yield char, False
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        yield char, depth == 0 and split_on(char)


def _split(text: str, split_on) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    for char, is_separator in _scan(text, split_on):
        if is_separator:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def _split_top_level(ddl_text: str) -> list[str]:
    """Split a comma-separated column list on top-level commas only,
    ignoring commas nested inside parentheses (e.g. numeric(10,2)) or
    quoted strings (e.g. DEFAULT 'a, b')."""

    return _split(ddl_text, lambda c: c == ",")


def _tokens(text: str) -> list[str]:
    return _split(text, str.isspace)


def _unquote_identifier(name: str) -> str:
    if len(name) >= 2 and name[0] == name[-1] == '"':
        return name[1:-1].replace('""', '"')
    return name


def parse_column(entry: str) -> ColumnDef:
    """Parse a single Postgres column definition, e.g.:
    'firm_pannumber character varying(10) COLLATE pg_catalog."default"'
    'id integer DEFAULT nextval('s'::regclass) NOT NULL'   (pg_dump order)
    '"Order Date" date'
    """

    text = entry.strip()
    if _TABLE_CONSTRAINT_RE.match(text):
        raise ValueError(
            f"'{text}' is a table-level constraint, not a column -- submit only the column list."
        )

    tokens = _tokens(text)
    name = _unquote_identifier(tokens[0])
    rest = tokens[1:]

    type_tokens: list[str] = []
    while rest and rest[0].upper() not in _CLAUSE_KEYWORDS:
        type_tokens.append(rest.pop(0))
    type_part = " ".join(type_tokens)

    if not type_part:
        logger.warning(f"Column '{name}' parsed with no data_type -- check the raw DDL entry: '{entry.strip()}'")

    nullable = True
    default = None
    while rest:
        keyword = rest.pop(0).upper()
        if keyword == "DEFAULT":
            # The default runs until the next clause keyword -- not to the
            # end of the line, which is what swallowed pg_dump's trailing
            # NOT NULL into the default. "DEFAULT NULL" is the one case
            # where the value itself is a clause keyword.
            value: list[str] = []
            if rest and rest[0].upper() == "NULL":
                value.append(rest.pop(0))
            while rest and rest[0].upper() not in _CLAUSE_KEYWORDS:
                value.append(rest.pop(0))
            default = " ".join(value) or None
        elif keyword == "NOT" and rest and rest[0].upper() == "NULL":
            rest.pop(0)
            nullable = False
        elif keyword == "PRIMARY":
            nullable = False  # PRIMARY KEY implies NOT NULL
        elif keyword in ("COLLATE", "CONSTRAINT") and rest:
            rest.pop(0)  # collation / constraint name
        # NULL, UNIQUE, CHECK (...), REFERENCES t(c), GENERATED ..., KEY:
        # nothing to record -- their operands are skipped below.
        while rest and rest[0].upper() not in _CLAUSE_KEYWORDS:
            rest.pop(0)

    length = scale = None
    length_match = _LENGTH_RE.search(type_part)
    if length_match:
        length = int(length_match.group(1))
        scale = int(length_match.group(2)) if length_match.group(2) else None
        type_part = re.sub(r"\s+", " ", _LENGTH_RE.sub("", type_part)).strip()

    return ColumnDef(
        name=name,
        data_type=type_part,
        length=length,
        scale=scale,
        nullable=nullable,
        default=default,
    )


def parse_postgres_columns(ddl_text: str) -> list[dict]:
    """Parse a raw Postgres column-list dump (as pasted from `\\d+ table`
    or a department Kobo submission) into structured column dicts.

    Refuses a full `CREATE TABLE ...` statement and table-level constraint
    lines rather than turning them into columns named "CREATE" or
    "CONSTRAINT" -- the submission should be the column list only."""

    if _CREATE_TABLE_RE.match(ddl_text):
        raise ValueError(
            "Source is a full CREATE TABLE statement -- submit only the column list "
            "(the part between the outer parentheses), without table-level constraints."
        )

    entries = _split_top_level(ddl_text.strip().rstrip(";"))
    columns = [asdict(parse_column(entry)) for entry in entries]
    logger.info(f"ddl_parser: parsed {len(columns)} column(s) from raw DDL text")
    return columns
