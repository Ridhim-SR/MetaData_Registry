import re
from collections import Counter

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

def _tok(*words: str) -> str:
    """Regex alternatives that match only as whole snake_case tokens: a word
    counts when it is delimited by "_" or the ends of the name, so "log"
    matches audit_log but not cancel_by_logic or catalog_no."""

    return r"(?<![a-z0-9])(?:" + "|".join(words) + r")(?![a-z0-9])"


# Auto-classification rules (field_name pattern -> classification level)
# Based on MDSF: classify per field by risk of disclosure/re-identification/misuse
AUTO_CLASSIFICATION_RULES: list[tuple[str, re.Pattern]] = [
    # Geographic / administrative place names: reference data, not people.
    # This MUST stay first: the PII "name" rule below matches any column
    # ending in "_name", so state_name/district_name/block_name/gp_name used
    # to be tagged PII -- a state or a Gram Panchayat is not a person, and
    # per MDSF carries no re-identification risk (Public). Compound names
    # (curr_district_name, bank_district_name, project_block_name) match on
    # the place token anywhere in the name; bare non-`_name` columns keep
    # their existing rules further down.
    ("Public", re.compile(
        r"(^|_)(state|district|block|gp|gram_panchayat|village|tehsil|taluka|taluk|"
        r"mandal|town|city|ward|sector|ulb|cluster|hobli|country)(_[a-z]+)*_name$",
        re.IGNORECASE,
    )),
    # Non-person "name of ..." columns. MUST stay above the PII name rules:
    # "name of the work" is a title, not a person.
    ("Internal", re.compile(_tok(r"name_of_(?:work|scheme|project|department|office|division|road|bridge)"), re.IGNORECASE)),
    # PII - Direct identifiers (MDSF PII-removal checklist: name, Aadhaar,
    # PAN, voter id, passport, driving licence, mobile, email, address, DOB).
    # Short words (pan, name, ssn, dob, sex, iris) match as whole snake_case
    # tokens: "pan" in "company" or "expansion" is not a PAN. Concatenated
    # forms people really write (pannumber, aadhaarno) are listed explicitly.
    ("PII", re.compile(_tok(r"aadha+r(?:_?(?:no|number|num))?", r"pan(?:_?(?:no|number|num|card))?", "passport",
                            r"voter_?id", "ssn", "national_id", r"driving_?licen[sc]e", "vehicle_registration"), re.IGNORECASE)),
    # A column that ENDS in "name" (firm_name, farmername, sansthaname, name)
    # or reads "name_of_<something>" -- not one where "name" sits in the
    # middle (name_of_work, crop_noncrop_name_id). Conservative on purpose:
    # whether a firm's name is personal is a policy call (MDSF s5.1), and
    # when in doubt the higher level applies.
    ("PII", re.compile(r"name$|(^|_)name_of_", re.IGNORECASE)),
    ("PII", re.compile(r"(email|mobile|phone|contact)", re.IGNORECASE)),
    ("PII", re.compile(r"(address|pincode|zipcode)", re.IGNORECASE)),
    ("PII", re.compile(_tok("date_of_birth", "dob", "birth_date"), re.IGNORECASE)),
    ("PII", re.compile(_tok("gender", "sex"), re.IGNORECASE)),
    ("PII", re.compile(r"(caste|religion|community)", re.IGNORECASE)),
    ("PII", re.compile(_tok("images?", "photos?", "biometrics?", "fingerprints?", "iris"), re.IGNORECASE)),
    ("PII", re.compile(r"(registration_no|application_no|beneficiary_id|farmer_id)", re.IGNORECASE)),

    # Financial - Direct financial identifiers. Money words are long and
    # rarely sit inside another word, and PWD-style names glue them on
    # (extraamount, surrenderamount), so these stay substring matches;
    # the short or ambiguous ones (emi, grant) are whole tokens.
    ("Financial", re.compile(r"(bank_account|account_no|ifsc|branch_name|bank_name)", re.IGNORECASE)),
    ("Financial", re.compile(r"(amount|price|cost|budget|subsidy|payment|transaction)", re.IGNORECASE)),
    ("Financial", re.compile(r"(salary|income|wage|allowance|pension|benefit)", re.IGNORECASE)),
    ("Financial", re.compile(r"(loan|credit|debit|interest|installment)|" + _tok("emi"), re.IGNORECASE)),
    ("Financial", re.compile(r"(fund|allocation|sanction|disbursement)|(^|_)grants?", re.IGNORECASE)),

    # Health - Health-related data
    ("Health", re.compile(r"(health|medical|diagnosis|treatment|prescription|hospital|clinic)", re.IGNORECASE)),

    # Restricted - High sensitivity identifiers. "key", "auth" and "log" are
    # whole tokens: "monkey", "author", "catalog" and "cancel_by_logic" are
    # not credentials or audit trails.
    ("Restricted", re.compile(r"(password|secret|credential|authentication|authori[sz]ation)|(^|_)token|" + _tok("key", "auth"), re.IGNORECASE)),
    ("Restricted", re.compile(_tok("audit", "audit_trail", "change_log", "logs?", "logging"), re.IGNORECASE)),

    # Confidential - Business sensitive. "plan" is a whole token: not "plant".
    ("Confidential", re.compile(r"(internal|confidential|proprietary|trade_secret)", re.IGNORECASE)),
    ("Confidential", re.compile(_tok("plans?", "planning", "strategy", "forecast", "projection", "estimate"), re.IGNORECASE)),

    # Internal - Operational identifiers
    ("Internal", re.compile(r"(id$|_id|code$|_code|reference|ref_no|sr_no|serial)", re.IGNORECASE)),
    ("Internal", re.compile(r"(created|modified|updated|deleted|version|status)", re.IGNORECASE)),
    ("Internal", re.compile(r"(department|division|branch|office|zone|region|district|block)|" + _tok("units?"), re.IGNORECASE)),

    # Public - Non-sensitive reference data. Whole tokens: "capacity" is not
    # a city and "statement" is not a state -- a wrongly Public field is the
    # dangerous mistake.
    ("Public", re.compile(_tok(r"countr(?:y|ies)", "states?", "districts?", r"cit(?:y|ies)", "villages?", "latitude", "longitude"), re.IGNORECASE)),
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

# The controlled vocabulary for a column's `tag`. Two kinds of value live
# here, and only the first kind may ever be auto-assigned:
#
#   * everything AUTO_TAG_RULES can detect from a field name. Adding a rule
#     rewrites tagging for every department, so a new entry there is a
#     behaviour change, not a vocabulary change.
#
#   * values that are real but not name-inferable -- a human supplied them
#     and the vocabulary merely permits them. PII (already used by real
#     Field Dictionaries), Sensitive (the MDSF s5.1 sensitive attributes
#     ai_metadata's apply_rules() writes), and PWD's own field dictionary:
#     Remarks, Identifier, Administrative-Unit and Quantity. That file was
#     curated on 2026-10-13, before validate_tag() existed, so all four are
#     already published under OpenMetadata's FieldTag Classification. They
#     are allowed here so a republish passes, and deliberately kept out of
#     AUTO_TAG_RULES so the auto-tagger never starts inventing them.
#
# Anything outside this set is a typo or an invented value, and publishing
# it would silently create a brand-new tag under the FieldTag Classification
# in OpenMetadata -- which is how "cat3" ended up as a tag next to CAT-3.
# ai_metadata.KNOWN_TAGS must stay a subset of this set or a drafted file
# fails at ingest rather than at review.
KNOWN_TAGS = sorted({tag for tag, _ in AUTO_TAG_RULES} | {
    "PII", "Sensitive",
    "Remarks", "Identifier", "Administrative-Unit", "Quantity",
})

# MDSF dataset-level categories (the axis curate_schema()'s per-column
# `classification` is NOT part of -- this one is per dataset, see
# pipeline.run's `category` argument and openmetadata.publish's
# _ensure_sensitivity_tag).
CATEGORY_LEVELS = ["CAT-1", "CAT-2", "CAT-3", "CAT-4"]


def auto_tag(field_name: str) -> str | None:
    for tag, pattern in AUTO_TAG_RULES:
        if pattern.search(field_name):
            return tag
    return None


def auto_classify(field_name: str) -> str:
    """Auto-classify a field based on MDSF risk assessment.

    Classification is per-field based on potential risk of disclosure,
    re-identification, or misuse. First matching rule wins. A name no rule
    recognises gets "" (not classified yet): a default level would claim
    someone judged the field low-risk, and nobody did.
    """
    for classification, pattern in AUTO_CLASSIFICATION_RULES:
        if pattern.search(field_name):
            return classification
    return ""


def validate_classification(classification: str) -> bool:
    """Validate that classification is a known level."""
    return classification in CLASSIFICATION_LEVELS


def validate_category(category: str) -> bool:
    """Validate a dataset-level `category` (MDSF CAT-1..CAT-4).

    Exact match only: "cat3"/"Cat 3"/"CAT-5" used to be accepted and then
    published as a brand-new DataSensitivity tag in OpenMetadata, sitting
    next to the real CAT-3."""

    return category in CATEGORY_LEVELS


def validate_tag(tag: str) -> bool:
    """A column's `tag` must be one of the known vocabulary values, or it
    would silently become a new tag under OpenMetadata's FieldTag
    Classification on publish (a typo'd tag is a taxonomy leak, not a tag)."""

    return tag in KNOWN_TAGS


def validate_glossary_term(term: str) -> bool:
    """OpenMetadata glossary-term FQNs are dot-separated (`BusinessGlossary.
    Some_Term`), so a "." inside the term itself makes the FQN unresolvable
    -- the term appears to exist but every lookup after it fails."""

    return "." not in term


def validate_schema(table_id: str, columns: list[dict]) -> None:
    """Refuse a parsed schema that can't be stored or published correctly:
    empty column names, duplicate names (OpenMetadata rejects them, and the
    by-name diff/metadata merge would silently collapse them), and data
    types with no known mapping. These used to be warnings only -- the bad
    snapshot still became the table's "latest" and every later publish
    failed on it. Raises one error listing every problem, so the department
    can fix the whole file in one go."""

    problems: list[str] = []

    if not columns:
        problems.append("the file has no columns")

    empty_positions = [str(i) for i, col in enumerate(columns, start=1) if not col["name"]]
    if empty_positions:
        problems.append(f"column(s) at position {', '.join(empty_positions)} have no name")

    name_counts = Counter(col["name"] for col in columns if col["name"])
    duplicates = sorted(name for name, count in name_counts.items() if count > 1)
    if duplicates:
        problems.append(f"duplicate column name(s): {', '.join(duplicates)}")

    unknown_types = [
        f"{col['name'] or '?'} ({col['data_type'] or 'no type'})"
        for col in columns
        if col["data_type"].lower() not in KNOWN_POSTGRES_TYPES
    ]
    if unknown_types:
        problems.append(
            f"unrecognized data type(s): {', '.join(unknown_types)} -- if a type is valid, add it to "
            f"KNOWN_POSTGRES_TYPES (curate.py) and _TYPE_MAP (openmetadata/publish.py)"
        )

    if problems:
        raise ValueError(f"{table_id}: schema rejected, nothing was stored -- " + "; ".join(problems))


def curate_schema(
    raw_columns: list[dict],
    business_metadata: dict[str, dict] | None = None,
) -> list[dict]:
    """Standardize raw columns (already checked by validate_schema), merging
    in business metadata (business description / tag / glossary term / active
    / classification) keyed by field name where it's available. Fields without
    an answer yet are left blank rather than guessed -- including `tag`, which
    used to fall back to a rule-based auto-tag; that fallback is switched off
    (see the tag line below), so a tag now only ever comes from a submitted
    Field Dictionary / ai_metadata draft.

    `classification` is unaffected: every column is still classified by
    AUTO_CLASSIFICATION_RULES (defaulting to "Internal"), so the MDSF
    per-field compliance story does not depend on anyone having answered.

    MDSF Compliance: Classification is done PER FIELD based on potential risk
    of disclosure, re-identification, or misuse -- not per dataset.

    Returns one row per field, ready to write straight to CSV.

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
        meta = business_metadata.get(name, {})

        # Per-field classification (MDSF requirement)
        # Priority: explicit business metadata > auto-classification > default
        classification = meta.get("classification", "").strip()
        if not classification:
            classification = auto_classify(name)
        elif not validate_classification(classification):
            logger.warning(f"{name}: Invalid classification '{classification}', using auto-classification")
            classification = auto_classify(name)

        # tag/glossary_term come from a department's Field Dictionary (or a
        # carried-forward snapshot) and are rejected outright if they're not
        # in the controlled vocabulary -- unlike `classification` above,
        # which falls back to auto-classification, these would otherwise be
        # created as-is in OpenMetadata (a made-up tag, or a glossary term
        # whose "." breaks its own FQN).
        #
        # AUTO-TAGGING IS SWITCHED OFF. A tag used to be guessed from the
        # column name when the submitted metadata did not carry one; that
        # made the same column's tag depend on who ran the ingest last, and
        # put labels a reviewer never saw onto published tables. `tag` is
        # now whatever the submitted metadata says and nothing else:
        #   * a blank cell still means "not answered", so _merge's
        #     carry-forward keeps the table's existing tag -- nothing is
        #     silently stripped from OpenMetadata by re-ingesting;
        #   * AUTO_TAG_RULES itself stays, because KNOWN_TAGS is built from
        #     it (tags already published still have to validate) and because
        #     ai_metadata drafts against it. Turning off the *fallback*
        #     needs no change to the vocabulary;
        #   * `classification` keeps auto_classify: a column whose name a rule
        #     recognises is classified even with no submitted metadata, and
        #     one it does not recognise stays blank (not classified yet).
        # tag = meta.get("tag") or auto_tag(name) or ""
        tag = meta.get("tag") or ""
        if tag and not validate_tag(tag):
            raise ValueError(
                f"{name}: unknown tag {tag!r} -- allowed tags are "
                f"{', '.join(KNOWN_TAGS)}. If this is a real new tag, add it to "
                f"KNOWN_TAGS/AUTO_TAG_RULES in curate.py first."
            )

        glossary_term = meta.get("glossary_term", "")
        if glossary_term and not validate_glossary_term(glossary_term):
            raise ValueError(
                f"{name}: glossary term {glossary_term!r} contains '.', which breaks "
                f"OpenMetadata's dot-separated FQN -- rename the term (e.g. use '_')."
            )

        curated_columns.append(
            {
                **column,
                "business_description": meta.get("business_description", ""),
                "tag": tag,
                "glossary_term": glossary_term,
                "active": meta.get("active", True),
                "classification": classification,
            }
        )

    return curated_columns
