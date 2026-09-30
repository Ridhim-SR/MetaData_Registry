import re

from src.utils.logger import get_logger

logger = get_logger(__name__)

KNOWN_POSTGRES_TYPES = {
    "integer", "bigint", "smallint", "serial", "bigserial",
    "character varying", "varchar", "character", "text",
    "double precision", "real", "numeric", "decimal",
    "boolean", "date", "timestamp without time zone",
    "timestamp with time zone", "time", "json", "jsonb", "uuid",
}

# (tag, pattern over field name) -- first match wins, order matters
AUTO_TAG_RULES: list[tuple[str, re.Pattern]] = [
    ("Financial", re.compile(r"(cost|amount|budget|expense|deposit|surrender|saving|fund|price)", re.IGNORECASE)),
    ("Firm/Contractor-Identifier", re.compile(r"(firm_pannumber|firm_name|bidder_name|contractor)", re.IGNORECASE)),
    ("Geospatial", re.compile(r"^(lat|longs?|chainage_|geofanc_)", re.IGNORECASE)),
    ("Status/Workflow", re.compile(r"_status$", re.IGNORECASE)),
    ("Date/Timestamp", re.compile(r"(_date|_at)$", re.IGNORECASE)),
]


def auto_tag(field_name: str) -> str | None:
    for tag, pattern in AUTO_TAG_RULES:
        if pattern.search(field_name):
            return tag
    return None


# (classification, pattern over field name) -- first match wins. These are
# the direct identifiers the Model Data Sharing Framework's PII removal
# checklist names (name, Aadhaar, PAN, mobile, email, address, DOB, ...) --
# a column matching one of these always carries at least CAT-3 (Restricted
# Access) risk, so it's auto-classified rather than left for a department to
# forget. Anything not matched here is left blank, never guessed as
# non-sensitive -- when in doubt, MDSF says the higher category applies, so
# we only auto-assign when confident.
PII_CLASSIFICATION_RULES: list[tuple[str, re.Pattern]] = [
    (
        "CAT-3",
        re.compile(
            r"(aadhaar|pan_?number|voter_?id|passport|driving_?licen[sc]e|vehicle_registration|"
            r"mobile|phone|email|bank_?account|^name$|residential_address|date_of_birth|\bdob\b)",
            re.IGNORECASE,
        ),
    ),
]


def auto_classification(field_name: str) -> str | None:
    for classification, pattern in PII_CLASSIFICATION_RULES:
        if pattern.search(field_name):
            return classification
    return None


def validate_column(column: dict) -> list[str]:
    """Return validation warnings for one column (empty list = clean)."""

    warnings: list[str] = []

    if not column["name"]:
        warnings.append("Missing column name")

    if column["data_type"].lower() not in KNOWN_POSTGRES_TYPES:
        warnings.append(f"Unrecognized Postgres type '{column['data_type']}'")

    return warnings


def curate_schema(
    raw_columns: list[dict],
    business_metadata: dict[str, dict] | None = None,
) -> list[dict]:
    """Validate & standardize raw columns, merging in business metadata
    (business description / tag / glossary term / active) keyed by field
    name where it's available. Fields without an answer yet are left
    blank rather than guessed, except `tag`, which falls back to a
    rule-based auto-tag so sensitive fields are never left unclassified.

    Returns one row per field, each carrying its own `validation_warning`
    (empty string if clean) so the whole thing writes straight to CSV.

    `classification` (CAT-1/CAT-2/CAT-3, per the Model Data Sharing
    Framework) works the same way as `tag`: a business-metadata override
    wins, otherwise it falls back to `auto_classification()`, otherwise
    blank for a human to assign later.
    """

    business_metadata = business_metadata or {}
    curated_columns: list[dict] = []

    for column in raw_columns:
        name = column["name"]
        warnings = validate_column(column)
        if warnings:
            logger.warning(f"{name}: {'; '.join(warnings)}")

        meta = business_metadata.get(name, {})

        curated_columns.append(
            {
                **column,
                "business_description": meta.get("business_description", ""),
                "tag": meta.get("tag") or auto_tag(name) or "",
                "classification": meta.get("classification") or auto_classification(name) or "",
                "glossary_term": meta.get("glossary_term", ""),
                "active": meta.get("active", True),
                "validation_warning": "; ".join(warnings),
            }
        )

    return curated_columns
