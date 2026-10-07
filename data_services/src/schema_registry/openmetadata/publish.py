import json
import os
from collections.abc import Iterable

import requests
from dotenv import load_dotenv
from metadata.generated.schema.api.classification.createClassification import (
    CreateClassificationRequest,
)
from metadata.generated.schema.api.classification.createTag import CreateTagRequest
from metadata.generated.schema.api.data.createDatabase import CreateDatabaseRequest
from metadata.generated.schema.api.data.createDatabaseSchema import (
    CreateDatabaseSchemaRequest,
)
from metadata.generated.schema.api.data.createGlossary import CreateGlossaryRequest
from metadata.generated.schema.api.data.createGlossaryTerm import (
    CreateGlossaryTermRequest,
)
from metadata.generated.schema.api.data.createTable import CreateTableRequest
from metadata.generated.schema.api.services.createDatabaseService import (
    CreateDatabaseServiceRequest,
)
from metadata.generated.schema.entity.classification.classification import (
    Classification,
)
from metadata.generated.schema.entity.classification.tag import Tag
from metadata.generated.schema.entity.data.database import Database
from metadata.generated.schema.entity.data.databaseSchema import DatabaseSchema
from metadata.generated.schema.entity.data.glossary import Glossary
from metadata.generated.schema.entity.data.glossaryTerm import GlossaryTerm
from metadata.generated.schema.entity.data.table import Column, DataType, Table, TableType
from metadata.generated.schema.entity.services.connections.database.customDatabaseConnection import (
    CustomDatabaseConnection,
)
from metadata.generated.schema.entity.services.connections.metadata.openMetadataConnection import (
    AuthProvider,
    OpenMetadataConnection,
)
from metadata.generated.schema.entity.services.databaseService import (
    DatabaseConnection,
    DatabaseService,
    DatabaseServiceType,
)
from metadata.generated.schema.entity.teams.team import Team
from metadata.generated.schema.entity.teams.user import User
from metadata.generated.schema.security.client.openMetadataJWTClientConfig import (
    OpenMetadataJWTClientConfig,
)
from metadata.generated.schema.type.entityReference import EntityReference
from metadata.generated.schema.type.tagLabel import LabelType, State, TagLabel, TagSource
from metadata.ingestion.ometa.client import APIError
from metadata.ingestion.ometa.ometa_api import OpenMetadata
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.schema_registry.curate import (
    CATEGORY_LEVELS,
    CLASSIFICATION_LEVELS,
    KNOWN_TAGS,
    validate_category,
    validate_glossary_term,
    validate_tag,
)
from src.schema_registry.registry import lookups
from src.storage import storage_from_env
from src.storage.base import ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _is_transient_error(exc: BaseException) -> bool:
    """Worth retrying: the server didn't answer at all (connection refused,
    DNS blip, timeout) or answered with a 5xx (its own transient failure).
    Never retry a 4xx (e.g. a genuinely unmapped type, bad request) --
    retrying the same broken request just wastes time before failing the
    same way."""

    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, APIError):
        return exc.status_code is not None and exc.status_code >= 500
    return False


_retry_transient = retry(
    retry=retry_if_exception(_is_transient_error),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


@_retry_transient
def _get_by_name(client: OpenMetadata, entity, fqn: str):
    return client.get_by_name(entity=entity, fqn=fqn)


@_retry_transient
def _create_or_update(client: OpenMetadata, request):
    return client.create_or_update(request)


@_retry_transient
def _replace_entity_fields(client: OpenMetadata, rest_suffix: str, entity_id, fields: dict) -> None:
    """create_or_update()'s PUT merges array/object fields (tags, extension)
    instead of replacing them -- verified live: clearing a dataset's
    `category`/custom-property value in _lookups/datasets.csv and
    republishing left the old tag/extension values stuck in OpenMetadata.
    A JSON-Patch `replace` on the exact fields that carry this risk is the
    only way a cleared value actually clears here too.

    Every field here must therefore always be sent on the PUT as well
    (non-null, empty list included) -- `replace` needs the path to exist in
    the entity's JSON, and OpenMetadata omits null fields from its responses."""

    patch = [{"op": "replace", "path": f"/{field}", "value": value} for field, value in fields.items()]
    client.client.patch(path=f"{rest_suffix}/{entity_id}", data=json.dumps(patch))


# Where curate.py's per-column `tag`/`classification`/`glossary_term`
# values land in OpenMetadata -- one fixed Classification for each of the
# first two (their values are a small, code-defined vocabulary: AUTO_TAG_RULES
# and CLASSIFICATION_LEVELS in curate.py), one fixed Glossary for the third
# (its values are free text from a department's Field Dictionary).
_TAG_CLASSIFICATION = "FieldTag"
_MDSF_CLASSIFICATION = "MDSF"
_SENSITIVITY_CLASSIFICATION = "DataSensitivity"
_GLOSSARY = "BusinessGlossary"

# The MDSF per-field levels, reused verbatim as the OpenMetadata tag
# descriptions so anyone browsing the catalog sees what a level means
# without leaving OpenMetadata.
_MDSF_LEVEL_DESCRIPTIONS = {
    "Public": "No risk of disclosure or re-identification.",
    "Internal": "Internal use only; low sensitivity.",
    "Confidential": "Sensitive; restricted access.",
    "Restricted": "Highly sensitive; need-to-know basis.",
    "PII": "Personally identifiable information.",
    "Financial": "Financial data requiring protection.",
    "Health": "Health or medical data.",
}

# Only the Postgres types curate.py's KNOWN_POSTGRES_TYPES actually allows
# through -- everything else already fails validation before it gets here.
_TYPE_MAP: dict[str, DataType] = {
    "integer": DataType.INT,
    "bigint": DataType.BIGINT,
    "smallint": DataType.SMALLINT,
    "serial": DataType.INT,
    "bigserial": DataType.BIGINT,
    "character varying": DataType.VARCHAR,
    "varchar": DataType.VARCHAR,
    "character": DataType.CHAR,
    "text": DataType.TEXT,
    "double precision": DataType.DOUBLE,
    "real": DataType.FLOAT,
    "numeric": DataType.NUMERIC,
    "decimal": DataType.DECIMAL,
    "boolean": DataType.BOOLEAN,
    "date": DataType.DATE,
    "timestamp without time zone": DataType.TIMESTAMP,
    "timestamp with time zone": DataType.TIMESTAMPZ,
    "time": DataType.TIME,
    "json": DataType.JSON,
    "jsonb": DataType.JSON,
    "uuid": DataType.UUID,
    "bytea": DataType.BYTEA,
}
# OM server rejects these types without an explicit dataLength.
_LENGTH_REQUIRED_TYPES = {DataType.CHAR, DataType.VARCHAR}
_DEFAULT_LENGTH = 256


def get_client(host_port: str, jwt_token: str) -> OpenMetadata:
    server_config = OpenMetadataConnection(
        hostPort=host_port,
        authProvider=AuthProvider.openmetadata,
        securityConfig=OpenMetadataJWTClientConfig(jwtToken=jwt_token),
    )
    return OpenMetadata(server_config)


def _unwrap(value):
    """SDK v2 entities wrap scalars in RootModels (e.g. EntityName(root='x'))."""
    root = getattr(value, "root", None)
    return root if root is not None else value


def _fqn(entity) -> str:
    name = getattr(entity, "fullyQualifiedName", None) or getattr(entity, "name", None)
    return str(_unwrap(name))


def _get_or_none(client: OpenMetadata, entity, fqn: str):
    try:
        return _get_by_name(client, entity, fqn)
    except Exception as exc:  # noqa: BLE001
        if "not found" in str(exc).lower() or "404" in str(exc):
            return None
        raise


def _tag_label(tag_fqn: str, source: TagSource) -> TagLabel:
    # Automated/Confirmed: curate.py assigned this, not a human clicking a
    # tag on in the OpenMetadata UI, and we're not hedging it as a mere
    # suggestion -- it's the pipeline's actual answer for this column.
    return TagLabel(tagFQN=tag_fqn, source=source, labelType=LabelType.Automated, state=State.Confirmed)


def _column_tags(row: dict) -> list[TagLabel]:
    """curate.py's `tag`/`classification`/`glossary_term` columns, mapped to
    where publish_table() ensures them to live in OpenMetadata (see
    _ensure_tags_and_terms)."""

    tags = []
    if row.get("tag"):
        tags.append(_tag_label(f"{_TAG_CLASSIFICATION}.{row['tag']}", TagSource.Classification))
    if row.get("classification"):
        tags.append(_tag_label(f"{_MDSF_CLASSIFICATION}.{row['classification']}", TagSource.Classification))
    if row.get("glossary_term"):
        tags.append(_tag_label(f"{_GLOSSARY}.{row['glossary_term']}", TagSource.Glossary))
    return tags


def _to_column(row: dict) -> Column:
    raw_type = row["data_type"].strip().lower()
    data_type = _TYPE_MAP.get(raw_type)
    if data_type is None:
        raise ValueError(
            f"No OpenMetadata mapping for Postgres type '{row['data_type']}' "
            f"(column '{row['name']}') -- add one to _TYPE_MAP."
        )

    kwargs = {
        "name": row["name"],
        "dataType": data_type,
        "description": row.get("business_description") or None,
        # Explicit [] on purpose, not None: OpenMetadata treats a missing
        # `tags` field as "leave existing tags alone", so a column that had
        # a tag/classification/glossary_term removed on this run would keep
        # its old, now-stale tags forever unless we say so explicitly.
        "tags": _column_tags(row),
    }
    if data_type in _LENGTH_REQUIRED_TYPES:
        length = row.get("length")
        kwargs["dataLength"] = int(length) if length else _DEFAULT_LENGTH
    return Column(**kwargs)


def _ensure_service(client: OpenMetadata, service_name: str) -> DatabaseService:
    existing = _get_or_none(client, DatabaseService, service_name)
    if existing:
        return existing
    return _create_or_update(
        client,
        CreateDatabaseServiceRequest(
            name=service_name,
            serviceType=DatabaseServiceType.CustomDatabase,
            connection=DatabaseConnection(
                config=CustomDatabaseConnection(type="CustomDatabase", sourcePythonClass="custom")
            ),
        ),
    )


# Dataset-level fields (_lookups/datasets.csv) that don't map to a built-in
# Database field -- pushed instead as OpenMetadata Custom Properties on the
# Database entity type (one-time setup: see setup_custom_properties.py).
_CUSTOM_PROPERTY_NAMES = {
    "api_available": "apiAvailable",
    "owner": "datasetOwner",
    "frequency": "frequency",
    "timeline": "timeline",
}


def _resolve_owner(client: OpenMetadata, owner: str) -> EntityReference | None:
    """Resolve a dataset's free-text `owner` (`_lookups/datasets.csv`) to an
    existing OpenMetadata User or Team, so the Database's built-in Owners
    field gets populated and everything driven by it -- ownership-based
    access rules, "my assets" filters, ownership reports -- actually applies.

    Tries User first, then Team, by fully-qualified name (for a user that
    can be either the username or the email address). Returns None when
    nothing matches: that's a warning, not a failure -- the raw text still
    lands in the `datasetOwner` custom property, and the owner can be
    created in OpenMetadata later and picked up by the next republish."""

    if not owner:
        return None

    candidates = list(dict.fromkeys([owner, owner.split("@", 1)[0]] if "@" in owner else [owner]))
    for candidate in candidates:
        for entity, entity_type in ((User, "user"), (Team, "team")):
            found = _get_or_none(client, entity, candidate)
            if found is None:
                continue
            name = str(_unwrap(found.name))
            return EntityReference(
                id=str(_unwrap(found.id)),
                type=entity_type,
                name=name,
                fullyQualifiedName=str(_unwrap(getattr(found, "fullyQualifiedName", None) or name)),
                displayName=str(_unwrap(getattr(found, "displayName", None) or name)),
            )

    logger.warning(
        f"Dataset owner '{owner}' matches no OpenMetadata user or team -- the built-in Owners "
        f"field stays unset (the datasetOwner custom property still records the text). "
        f"Create the user/team in OpenMetadata, or fix the owner in _lookups/datasets.csv."
    )
    return None


def _ensure_database(
    client: OpenMetadata,
    service_fqn: str,
    database_name: str,
    description: str = "",
    category: str = "",
    custom_properties: dict | None = None,
    owner_ref: EntityReference | None = None,
) -> Database:
    """Unlike _ensure_service/_ensure_schema, always create-or-update (never
    short-circuits on an existing entity) -- `description`/`category`/
    `custom_properties` are dataset-level fields from _lookups/datasets.csv
    that can be confirmed or changed on a later run, same reasoning as why
    the table itself is always create-or-update rather than get-or-create."""

    tags = [_tag_label(f"{_SENSITIVITY_CLASSIFICATION}.{category}", TagSource.Classification)] if category else []
    # Every custom property name is always included, blank ("") if unset --
    # so the field is visibly present (not yet answered) rather than the
    # whole `extension` silently disappearing when nothing's been set yet.
    custom_properties = custom_properties or {}
    extension = {name: custom_properties.get(field, "") for field, name in _CUSTOM_PROPERTY_NAMES.items()}
    # `owners` is always a list, empty when nothing resolved: _replace_entity_fields()
    # does a JSON-Patch `replace` on it, and `replace` needs the path to exist
    # in the entity OpenMetadata just returned. Sending [] is accepted the same
    # way column `tags: []` is (see _to_column).
    owners = [owner_ref] if owner_ref else []
    database = _create_or_update(
        client,
        CreateDatabaseRequest(
            name=database_name,
            service=service_fqn,
            description=description or None,
            tags=tags,
            extension=extension,
            owners=owners,
        ),
    )
    _replace_entity_fields(
        client,
        "/databases",
        _unwrap(database.id),
        {
            "tags": [t.model_dump(mode="json", exclude_none=True) for t in tags],
            "extension": extension,
            "owners": [o.model_dump(mode="json", exclude_none=True) for o in owners],
        },
    )
    return database


def _ensure_schema(client: OpenMetadata, database_fqn: str, schema_name: str) -> DatabaseSchema:
    fqn = f"{database_fqn}.{schema_name}"
    existing = _get_or_none(client, DatabaseSchema, fqn)
    if existing:
        return existing
    return _create_or_update(client, CreateDatabaseSchemaRequest(name=schema_name, database=database_fqn))


def _ensure_classification(client: OpenMetadata, name: str, description: str) -> Classification:
    existing = _get_or_none(client, Classification, name)
    if existing:
        return existing
    return _create_or_update(client, CreateClassificationRequest(name=name, description=description))


def _ensure_tag(client: OpenMetadata, classification_name: str, tag_name: str, description: str) -> Tag:
    fqn = f"{classification_name}.{tag_name}"
    existing = _get_or_none(client, Tag, fqn)
    if existing:
        return existing
    return _create_or_update(
        client, CreateTagRequest(classification=classification_name, name=tag_name, description=description)
    )


def _ensure_glossary(client: OpenMetadata, name: str, description: str) -> Glossary:
    existing = _get_or_none(client, Glossary, name)
    if existing:
        return existing
    return _create_or_update(client, CreateGlossaryRequest(name=name, description=description))


def _ensure_glossary_term(client: OpenMetadata, glossary_name: str, term_name: str, description: str) -> GlossaryTerm:
    fqn = f"{glossary_name}.{term_name}"
    existing = _get_or_none(client, GlossaryTerm, fqn)
    if existing:
        return existing
    return _create_or_update(
        client, CreateGlossaryTermRequest(glossary=glossary_name, name=term_name, description=description)
    )


def _unique_in_order(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))


# MDSF (Model Data Sharing Framework) Section 5.1's own category definitions,
# reused verbatim as the OpenMetadata Tag description so anyone browsing the
# catalog sees what a CAT-x label actually means without leaving OpenMetadata.
# Keys are the entire allowed vocabulary for a dataset's `category`
# (curate.CATEGORY_LEVELS) -- anything else is rejected instead of being
# published as a new tag next to the real ones.
_CAT_DESCRIPTIONS = {
    "CAT-1": "Open Access -- fully anonymised, aggregated or non-personal data. No risk of re-identification.",
    "CAT-2": "Registered Access -- de-identified data. Individual identity not exposed.",
    "CAT-3": "Restricted Access -- personal or sensitive data at individual/entity level. "
    "Shared only with DPDPA-compliant consent or a specific legal mandate.",
    "CAT-4": "No Sharing -- confidential data that must not leave the owning organisation. "
    "Not published through any API or external feed.",
}


def _ensure_sensitivity_tag(client: OpenMetadata, category: str) -> None:
    """Dataset-level `category` (publish_table) -- the MDSF CAT-1..CAT-4
    vocabulary attached to the Database entity. Column levels live in
    _ensure_mdsf_levels instead: they are a different axis (per-field
    sensitivity), published under the MDSF classification.

    Validated here as well as in pipeline.run(): publish_table() is also
    called on its own (republish, standalone republish), and `category` may
    still hold a value written before the validation existed."""

    if not validate_category(category):
        raise ValueError(
            f"Unknown category '{category}' -- allowed: {', '.join(CATEGORY_LEVELS)} "
            f"(MDSF CAT levels, exactly as written). Not publishing it as a tag."
        )
    _ensure_classification(
        client,
        _SENSITIVITY_CLASSIFICATION,
        "Model Data Sharing Framework data classification (CAT-1 Open / CAT-2 Registered / "
        "CAT-3 Restricted / CAT-4 No Sharing), assigned per column by curate_schema() and "
        "per dataset in _lookups/datasets.csv.",
    )
    _ensure_tag(
        client,
        _SENSITIVITY_CLASSIFICATION,
        category,
        _CAT_DESCRIPTIONS.get(category, f"MDSF data classification category {category}."),
    )


def _ensure_mdsf_levels(client: OpenMetadata) -> None:
    """Create the MDSF tag classification and all of its level tags.

    All of CLASSIFICATION_LEVELS, not just the levels this snapshot uses, so
    a column tagged later (or by another department) always resolves; also
    `mutuallyExclusive` so a column carries at most one level, matching
    curate_schema()'s single-`classification` model.
    """

    existing = _get_or_none(client, Classification, _MDSF_CLASSIFICATION)
    if existing is None:
        _create_or_update(
            client,
            CreateClassificationRequest(
                name=_MDSF_CLASSIFICATION,
                description=(
                    "MDSF per-field data classification levels, ordered from least to "
                    "most restrictive. Applied per column by the schema-registry pipeline."
                ),
                mutuallyExclusive=True,
            ),
        )
    for level in CLASSIFICATION_LEVELS:
        if _get_or_none(client, Tag, f"{_MDSF_CLASSIFICATION}.{level}") is None:
            _ensure_tag(
                client,
                _MDSF_CLASSIFICATION,
                level,
                _MDSF_LEVEL_DESCRIPTIONS.get(level, ""),
            )


def _ensure_tags_and_terms(client: OpenMetadata, curated_columns: list[dict]) -> None:
    """Create-or-reuse every Classification/Tag/Glossary/GlossaryTerm the
    curated columns reference, before the table request tries to attach
    them as TagLabels -- OpenMetadata won't accept a TagLabel pointing at a
    tag/term that doesn't exist yet.

    Also the last line of defence for item 14: curate_schema() already
    rejects unknown tags and "."-containing glossary terms, but publish can
    run against a snapshot curated before that validation existed."""

    tags = _unique_in_order(row.get("tag", "") for row in curated_columns)
    classifications = _unique_in_order(row.get("classification", "") for row in curated_columns)
    glossary_terms = _unique_in_order(row.get("glossary_term", "") for row in curated_columns)

    for tag in tags:
        if not validate_tag(tag):
            raise ValueError(
                f"Unknown tag '{tag}' -- allowed: {', '.join(KNOWN_TAGS)}. "
                f"Add it to KNOWN_TAGS in curate.py if it is a real new tag."
            )
    for term in glossary_terms:
        if not validate_glossary_term(term):
            raise ValueError(f"Glossary term '{term}' contains '.', which breaks OpenMetadata's FQN.")

    if tags:
        _ensure_classification(client, _TAG_CLASSIFICATION, "Rule-based field categories auto-assigned by curate_schema() (see AUTO_TAG_RULES).")
        for tag in tags:
            _ensure_tag(client, _TAG_CLASSIFICATION, tag, f"Columns matching curate.py's AUTO_TAG_RULES pattern for '{tag}'.")
    if classifications:
        _ensure_mdsf_levels(client)
    if glossary_terms:
        _ensure_glossary(
            client, _GLOSSARY, "Business terms attached to columns via a department's Field Dictionary (business_metadata_file)."
        )
        for term in glossary_terms:
            _ensure_glossary_term(
                client, _GLOSSARY, term, "Business term supplied via a department's Field Dictionary (business_metadata_file)."
            )


def publish_table(client: OpenMetadata, storage: ObjectStorage, table_id: str, service_name: str | None = None) -> dict:
    """Publish one table's latest curated schema snapshot into OpenMetadata
    as a Table entity (Service -> Database -> Schema -> Table -> Columns).

    This is the one function every publish path (CLI below, or a future
    batch loop over all registered tables) should call, so the create-or-
    update logic for the whole entity chain lives in exactly one place.
    `table_id` is the same hierarchical id used throughout this pipeline
    ("pwd.vishwakarma.<table>"); service defaults to the department so each
    department gets its own OpenMetadata database service.
    """

    department_id, dataset_slug, table_slug = table_id.split(".")
    dataset_id = f"{department_id}.{dataset_slug}"

    table_row = lookups.get_table(storage, table_id)
    if table_row is None:
        raise ValueError(f"Unknown table_id '{table_id}' -- not found in {lookups.TABLES_PATH}")
    if table_row.get("deleted"):
        raise ValueError(
            f"{table_id} was soft-deleted on {table_row['deleted']} -- it stays out of "
            f"OpenMetadata until it is re-ingested (run() re-registers it and clears the mark)."
        )
    dataset_row = lookups.get_dataset(storage, dataset_id) or {}

    curated_path = lookups.latest_curated_snapshot_path(storage, department_id, dataset_slug, table_slug)
    curated_columns = storage.read_csv(curated_path)

    service = _ensure_service(client, service_name or department_id)
    category = dataset_row.get("category", "")
    if category:
        _ensure_sensitivity_tag(client, category)
    database = _ensure_database(
        client,
        _fqn(service),
        dataset_slug,
        description=dataset_row.get("dataset_description", ""),
        category=category,
        custom_properties={
            "api_available": dataset_row.get("api_available", ""),
            "owner": dataset_row.get("owner", ""),
            "frequency": dataset_row.get("frequency", ""),
            "timeline": dataset_row.get("timeline", ""),
        },
        owner_ref=_resolve_owner(client, dataset_row.get("owner", "")),
    )
    schema = _ensure_schema(client, _fqn(database), table_row["schema_name"])

    # Built (and, if invalid, raised) before touching tags/glossary terms in
    # OpenMetadata, so a bad data type fails fast without side effects.
    columns = [_to_column(row) for row in curated_columns]
    _ensure_tags_and_terms(client, curated_columns)

    table = _create_or_update(
        client,
        CreateTableRequest(
            name=table_row["table_name"],
            tableType=TableType.Regular,
            databaseSchema=_fqn(schema),
            columns=columns,
        ),
    )

    logger.info(f"Published {table_id} -> {_fqn(table)} ({len(curated_columns)} column(s)) from {curated_path}")

    return {
        "table_id": table_id,
        "fully_qualified_name": _fqn(table),
        "curated_path": curated_path,
        "column_count": len(curated_columns),
    }


def delete_table(client: OpenMetadata, storage: ObjectStorage, table_id: str) -> dict:
    """Soft-delete a table in OpenMetadata and mark it deleted in the
    registry -- the command that fixes "renaming a table leaves the old one
    orphaned in OpenMetadata".

    OpenMetadata goes first: if that call fails, nothing in the registry
    changed and the whole thing can simply be retried. The registry mark is
    the *consequence* of the entity being gone, never the other way round."""

    department_id, dataset_slug, table_slug = table_id.split(".")
    table_row = lookups.get_table(storage, table_id)
    if table_row is None:
        raise ValueError(f"Unknown table_id '{table_id}' -- not found in {lookups.TABLES_PATH}")

    fqn = f"{department_id}.{dataset_slug}.{table_row['schema_name']}.{table_row['table_name']}"
    existing = _get_or_none(client, Table, fqn)
    deleted_in_om = False
    if existing is not None:
        client.delete(entity=Table, entity_id=str(_unwrap(existing.id)), recursive=False)
        deleted_in_om = True
        logger.info(f"Soft-deleted {fqn} in OpenMetadata")
    else:
        logger.info(f"{fqn} is not in OpenMetadata (already gone?) -- marking the registry only")

    registry_row = lookups.soft_delete_table(storage, table_id)
    return {
        "table_id": table_id,
        "fully_qualified_name": fqn,
        "openmetadata": "deleted" if deleted_in_om else "not-found",
        "registry": f"soft-deleted {registry_row['deleted']}",
    }


if __name__ == "__main__":
    load_dotenv()
    _storage = storage_from_env()
    _client = get_client(
        host_port=os.environ.get("OPENMETADATA_HOST_PORT", "http://localhost:8585/api"),
        jwt_token=os.environ["OPENMETADATA_JWT_TOKEN"],
    )
    publish_table(_client, _storage, os.environ["TABLE_ID"])
