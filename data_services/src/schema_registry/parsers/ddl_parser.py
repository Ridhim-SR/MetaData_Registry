import re
from dataclasses import asdict, dataclass

_DEFAULT_RE = re.compile(r"\bDEFAULT\s+(.+)$", re.IGNORECASE)
_NOT_NULL_RE = re.compile(r"\bNOT\s+NULL\b", re.IGNORECASE)
_COLLATE_RE = re.compile(r"\bCOLLATE\s+\S+", re.IGNORECASE)
_LENGTH_RE = re.compile(r"\((\d+)(?:\s*,\s*(\d+))?\)")


@dataclass
class ColumnDef:
    name: str
    data_type: str
    length: int | None
    scale: int | None
    nullable: bool
    default: str | None


def _split_top_level(ddl_text: str) -> list[str]:
    """Split a comma-separated column list on top-level commas only,
    ignoring commas nested inside parentheses (e.g. numeric(10,2))."""

    parts: list[str] = []
    depth = 0
    current: list[str] = []

    for char in ddl_text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1

        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)

    if current:
        parts.append("".join(current))

    return [p.strip() for p in parts if p.strip()]


def parse_column(entry: str) -> ColumnDef:
    """Parse a single Postgres column definition, e.g.:
    'firm_pannumber character varying(10) COLLATE pg_catalog."default"'
    """

    text = entry.strip()

    default = None
    match = _DEFAULT_RE.search(text)
    if match:
        default = match.group(1).strip()
        text = text[: match.start()].strip()

    nullable = not bool(_NOT_NULL_RE.search(text))
    text = _NOT_NULL_RE.sub("", text).strip()
    text = _COLLATE_RE.sub("", text).strip()

    name, _, type_part = text.partition(" ")
    type_part = type_part.strip()

    length = scale = None
    length_match = _LENGTH_RE.search(type_part)
    if length_match:
        length = int(length_match.group(1))
        scale = int(length_match.group(2)) if length_match.group(2) else None
        type_part = _LENGTH_RE.sub("", type_part).strip()

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
    or a department Kobo submission) into structured column dicts."""

    entries = _split_top_level(ddl_text)
    return [asdict(parse_column(entry)) for entry in entries]
