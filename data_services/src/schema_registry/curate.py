import re

from src.utils.logger import get_logger

logger = get_logger(__name__)

KNOWN_POSTGRES_TYPES = {
    "integer", "bigint", "smallint", "serial", "bigserial",
    "character varying", "varchar", "character", "text",
    "double precision", "real", "numeric", "decimal",
    "boolean", "date", "timestamp without time zone",
    "timestamp with time zone", "time", "json", "jsonb", "uuid", "bytea",
}

# MDSF Classification Levels (per field, not per dataset)
# Ordered from least to most restrictive
CLASSIFICATION_LEVELS = [
    "Public",           # No risk of disclosure/re-identification
    "Internal",         # Internal use only, low sensitivity
    "Confidential",     # Sensitive, restricted access
    "Restricted",       # Highly sensitive, need-to-know basis
    "PII",              # Personally Identifiable Information
    "Financial",        # Financial data requiring protection
    "Health",           # Health/medical data
]

CLASSIFICATION_HIERARCHY = {level: idx for idx, level in enumerate(CLASSIFICATION_LEVELS)}

# Auto-classification rules (field_name pattern -> classification level)
# Based on MDSF: classify per field by risk of disclosure/re-identification/misuse
AUTO_CLASSIFICATION_RULES: list[tuple[str, re.Pattern]] = [
    # PII - Direct identifiers (MDSF PII-removal checklist: name, Aadhaar,
    # PAN, voter id, passport, driving licence, mobile, email, address, DOB)
    ("PII", re.compile(r"(aadha+r|pan|passport|voter_?id|ssn|national_id|driving_?licen[sc]e|vehicle_registration)", re.IGNORECASE)),
    ("PII", re.compile(r"(name|first_name|last_name|full_name|father_name|mother_name)", re.IGNORECASE)),
    ("PII", re.compile(r"(email|mobile|phone|contact)", re.IGNORECASE)),
    ("PII", re.compile(r"(address|pincode|zipcode)", re.IGNORECASE)),
    ("PII", re.compile(r"(date_of_birth|dob|birth_date)", re.IGNORECASE)),
    ("PII", re.compile(r"(gender|sex)", re.IGNORECASE)),
    ("PII", re.compile(r"(caste|religion|community)", re.IGNORECASE)),
    ("PII", re.compile(r"(image|photo|biometric|fingerprint|iris)", re.IGNORECASE)),
    ("PII", re.compile(r"(registration_no|application_no|beneficiary_id|farmer_id)", re.IGNORECASE)),

    # Financial - Direct financial identifiers
    ("Financial", re.compile(r"(bank_account|account_no|ifsc|branch_name|bank_name)", re.IGNORECASE)),
    ("Financial", re.compile(r"(amount|price|cost|budget|subsidy|payment|transaction)", re.IGNORECASE)),
    ("Financial", re.compile(r"(salary|income|wage|allowance|pension|benefit)", re.IGNORECASE)),
    ("Financial", re.compile(r"(loan|credit|debit|interest|emi|installment)", re.IGNORECASE)),
    ("Financial", re.compile(r"(grant|fund|allocation|sanction|disbursement)", re.IGNORECASE)),

    # Health - Health-related data
    ("Health", re.compile(r"(health|medical|diagnosis|treatment|prescription|hospital|clinic)", re.IGNORECASE)),

    # Restricted - High sensitivity identifiers
    ("Restricted", re.compile(r"(password|secret|token|key|credential|auth)", re.IGNORECASE)),
    ("Restricted", re.compile(r"(audit|log|audit_trail|change_log)", re.IGNORECASE)),

    # Confidential - Business sensitive
    ("Confidential", re.compile(r"(internal|confidential|proprietary|trade_secret)", re.IGNORECASE)),
    ("Confidential", re.compile(r"(strategy|plan|forecast|projection|estimate)", re.IGNORECASE)),

    # Internal - Operational identifiers
    ("Internal", re.compile(r"(id$|_id|code$|_code|reference|ref_no|sr_no|serial)", re.IGNORECASE)),
    ("Internal", re.compile(r"(created|modified|updated|deleted|version|status)", re.IGNORECASE)),
    ("Internal", re.compile(r"(department|division|unit|branch|office|zone|region|district|block)", re.IGNORECASE)),

    # Public - Non-sensitive reference data
    ("Public", re.compile(r"(country|state|district|city|village|pincode|latitude|longitude)", re.IGNORECASE)),
    ("Public", re.compile(r"(scheme|program|project|initiative|policy|guideline)", re.IGNORECASE)),
]

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


def auto_classify(field_name: str) -> str:
    """Auto-classify a field based on MDSF risk assessment.

    Classification is per-field based on potential risk of disclosure,
    re-identification, or misuse. First matching rule wins.
    """
    for classification, pattern in AUTO_CLASSIFICATION_RULES:
        if pattern.search(field_name):
            return classification
    return "Internal"  # Default: internal use only


def validate_classification(classification: str) -> bool:
    """Validate that classification is a known level."""
    return classification in CLASSIFICATION_LEVELS


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
    (business description / tag / glossary term / active / classification) 
    keyed by field name where it's available.

    MDSF Compliance: Classification is done PER FIELD based on potential
    risk of disclosure, re-identification, or misuse. Not per dataset.

    Fields without explicit classification get auto-classified via rules.
    Business metadata can override auto-classification.

    Returns one row per field, each carrying its own `validation_warning`
    (empty string if clean) so the whole thing writes straight to CSV.

    `classification` (Public / Internal / Confidential / Restricted / PII /
    Financial / Health, per the Model Data Sharing Framework) works the same
    way as `tag`: a business-metadata override wins, otherwise it falls back
    to `auto_classify()` (rules above, defaulting to "Internal"), and an
    override naming an unknown level is rejected and re-auto-classified.
    """

    business_metadata = business_metadata or {}
    curated_columns: list[dict] = []

    for column in raw_columns:
        name = column["name"]
        warnings = validate_column(column)
        if warnings:
            logger.warning(f"{name}: {'; '.join(warnings)}")

        meta = business_metadata.get(name, {})

        # Per-field classification (MDSF requirement)
        # Priority: explicit business metadata > auto-classification > default
        classification = meta.get("classification", "").strip()
        if not classification:
            classification = auto_classify(name)
        elif not validate_classification(classification):
            logger.warning(f"{name}: Invalid classification '{classification}', using auto-classification")
            classification = auto_classify(name)

        curated_columns.append(
            {
                **column,
                "business_description": meta.get("business_description", ""),
                "tag": meta.get("tag") or auto_tag(name) or "",
                "glossary_term": meta.get("glossary_term", ""),
                "active": meta.get("active", True),
                "classification": classification,
                "validation_warning": "; ".join(warnings),
            }
        )

    return curated_columns
