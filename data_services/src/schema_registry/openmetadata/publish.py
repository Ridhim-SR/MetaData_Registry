import json
import os
import re
from collections.abc import Iterable

import requests
from src.utils.config import load_env
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
from metadata.generated.schema.entity.data.table import Column, DataType, TableType
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
from metadata.generated.schema.security.client.openMetadataJWTClientConfig import (
    OpenMetadataJWTClientConfig,
)
from metadata.generated.schema.type.tagLabel import LabelType, State, TagLabel, TagSource
from metadata.ingestion.ometa.client import APIError
from metadata.ingestion.ometa.ometa_api import OpenMetadata
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

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
def _replace_entity_fields(client: OpenMetadata, rest_suffix: str, entity_id, fields: dict, op: str = "replace") -> None:
    """create_or_update()'s PUT merges array/object fields (tags, extension)
    instead of replacing them -- verified live: clearing a dataset's
    `category`/custom-property value in _lookups/datasets.csv and
    republishing left the old tag/extension values stuck in OpenMetadata.
    A JSON-Patch `replace` on the exact fields that carry this risk is the
    only way a cleared value actually clears here too.

    `op="add"` sets a path whether or not it exists yet (JSON-Patch `add` on
    an existing object member replaces it) -- used for per-column tags,
    where a column with no tags may not carry a `tags` member at all."""

    patch = [{"op": op, "path": f"/{field}", "value": value} for field, value in fields.items()]
    client.client.patch(path=f"{rest_suffix}/{entity_id}", data=json.dumps(patch))


# Where curate.py's per-column `tag`/`classification`/`glossary_term`
# values land in OpenMetadata -- one fixed Classification for each of the
# first two (their values are a small, code-defined vocabulary: AUTO_TAG_RULES
# and PII_CLASSIFICATION_RULES in curate.py), one fixed Glossary for the third
# (its values are free text from a department's Field Dictionary).
_TAG_CLASSIFICATION = "FieldTag"
_SENSITIVITY_CLASSIFICATION = "DataSensitivity"
_GLOSSARY = "BusinessGlossary"

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
}
# OM server rejects these types without an explicit dataLength.
_LENGTH_REQUIRED_TYPES = {DataType.CHAR, DataType.VARCHAR}
_DEFAULT_LENGTH = 256


def get_client(host_port: str, jwt_token: str) -> OpenMetadata:
    # Quick reachability check first: the SDK otherwise retries for ~35 s and
    # floods the screen with its own warnings before failing.
    try:
        requests.get(f"{host_port.rstrip('/')}/v1/system/version", timeout=8)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        raise requests.exceptions.ConnectionError(f"OpenMetadata at {host_port} isn't reachable") from exc
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
        tags.append(_tag_label(f"{_SENSITIVITY_CLASSIFICATION}.{row['classification']}", TagSource.Classification))
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
        # The PUT still merges these with whatever tags the column already
        # has -- _replace_column_tags() is what actually makes them exact.
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


def _ensure_database(
    client: OpenMetadata,
    service_fqn: str,
    database_name: str,
    description: str = "",
    category: str = "",
    custom_properties: dict | None = None,
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
    database = _create_or_update(
        client,
        CreateDatabaseRequest(
            name=database_name,
            service=service_fqn,
            description=description or None,
            tags=tags,
            extension=extension,
        ),
    )
    _replace_entity_fields(
        client,
        "/databases",
        _unwrap(database.id),
        {
            "tags": [t.model_dump(mode="json", exclude_none=True) for t in tags],
            "extension": extension,
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
_CAT_DESCRIPTIONS = {
    "CAT-1": "Open Access -- fully anonymised, aggregated or non-personal data. No risk of re-identification.",
    "CAT-2": "Registered Access -- de-identified data. Individual identity not exposed.",
    "CAT-3": "Restricted Access -- personal or sensitive data at individual/entity level. "
    "Shared only with DPDPA-compliant consent or a specific legal mandate.",
}


def _ensure_sensitivity_tag(client: OpenMetadata, category: str) -> None:
    """Shared by column-level `classification` (_ensure_tags_and_terms) and
    the dataset-level `category` (publish_table) -- both are the same MDSF
    CAT-1/2/3/4 vocabulary, just attached at different entity levels."""

    _ensure_classification(
        client,
        _SENSITIVITY_CLASSIFICATION,
        "Model Data Sharing Framework data classification (CAT-1 Open / CAT-2 Registered / "
        "CAT-3 Restricted), assigned per column by curate_schema() and per dataset in _lookups/datasets.csv.",
    )
    _ensure_tag(
        client,
        _SENSITIVITY_CLASSIFICATION,
        category,
        _CAT_DESCRIPTIONS.get(category, f"MDSF data classification category {category}."),
    )


_CATEGORY_RE = re.compile(r"^CAT-(\d+)$", re.IGNORECASE)


def _category_level(value: str) -> int | None:
    match = _CATEGORY_RE.match((value or "").strip())
    return int(match.group(1)) if match else None


def _check_category_covers_columns(table_id: str, category: str, curated_columns: list[dict]) -> None:
    """MDSF: when a dataset mixes categories, the highest one applies. So a
    dataset published as CAT-1 (Open) while one of its columns is CAT-3
    (Restricted) would advertise restricted data as open -- refuse that
    before anything is written to OpenMetadata.

    A blank dataset category (not confirmed yet) is only warned about, since
    most datasets are still waiting on their department's answer."""

    column_levels = {
        row["name"]: level
        for row in curated_columns
        if (level := _category_level(row.get("classification", ""))) is not None
    }
    if not column_levels:
        return
    highest = max(column_levels.values())
    highest_columns = sorted(name for name, level in column_levels.items() if level == highest)

    dataset_level = _category_level(category)
    if dataset_level is None:
        if category:
            raise ValueError(f"{table_id}: dataset category '{category}' isn't a CAT-<n> value.")
        logger.warning(
            f"{table_id}: dataset has no category yet, but column(s) {', '.join(highest_columns)} "
            f"are CAT-{highest}. Set the dataset's CATEGORY to at least CAT-{highest}."
        )
        return
    if dataset_level < highest:
        raise ValueError(
            f"{table_id}: dataset category is {category} but column(s) {', '.join(highest_columns)} "
            f"are CAT-{highest}. Under MDSF the highest category applies -- set the dataset's "
            f"CATEGORY to at least CAT-{highest}, or pass allow_category_below_columns=True if "
            f"those columns are removed/anonymised before sharing."
        )


def _replace_column_tags(client: OpenMetadata, table, columns: list[Column]) -> None:
    """create_or_update()'s PUT merges column tags with the ones already
    there, so a column moved from CAT-3 to CAT-1 would carry both labels.
    Set each column's tags to exactly this run's list, matching columns by
    name against the entity the server returned (its order, not ours)."""

    server_names = [str(_unwrap(c.name)) for c in (getattr(table, "columns", None) or [])]
    fields = {}
    for column in columns:
        name = str(_unwrap(column.name))
        if name not in server_names:
            raise ValueError(f"Column '{name}' missing from {_fqn(table)} after publish -- can't set its tags.")
        index = server_names.index(name)
        fields[f"columns/{index}/tags"] = [t.model_dump(mode="json", exclude_none=True) for t in column.tags or []]
    if fields:
        _replace_entity_fields(client, "/tables", _unwrap(table.id), fields, op="add")


def _ensure_tags_and_terms(client: OpenMetadata, curated_columns: list[dict]) -> None:
    """Create-or-reuse every Classification/Tag/Glossary/GlossaryTerm the
    curated columns reference, before the table request tries to attach
    them as TagLabels -- OpenMetadata won't accept a TagLabel pointing at a
    tag/term that doesn't exist yet."""

    tags = _unique_in_order(row.get("tag", "") for row in curated_columns)
    classifications = _unique_in_order(row.get("classification", "") for row in curated_columns)
    glossary_terms = _unique_in_order(row.get("glossary_term", "") for row in curated_columns)

    if tags:
        _ensure_classification(client, _TAG_CLASSIFICATION, "Rule-based field categories auto-assigned by curate_schema() (see AUTO_TAG_RULES).")
        for tag in tags:
            _ensure_tag(client, _TAG_CLASSIFICATION, tag, f"Columns matching curate.py's AUTO_TAG_RULES pattern for '{tag}'.")
    for classification in classifications:
        _ensure_sensitivity_tag(client, classification)
    if glossary_terms:
        _ensure_glossary(
            client, _GLOSSARY, "Business terms attached to columns via a department's Field Dictionary (business_metadata_file)."
        )
        for term in glossary_terms:
            _ensure_glossary_term(
                client, _GLOSSARY, term, "Business term supplied via a department's Field Dictionary (business_metadata_file)."
            )


def publish_table(
    client: OpenMetadata,
    storage: ObjectStorage,
    table_id: str,
    service_name: str | None = None,
    allow_category_below_columns: bool = False,
) -> dict:
    """Publish one table's latest curated schema snapshot into OpenMetadata
    as a Table entity (Service -> Database -> Schema -> Table -> Columns).

    This is the one function every publish path (CLI below, or a future
    batch loop over all registered tables) should call, so the create-or-
    update logic for the whole entity chain lives in exactly one place.
    `table_id` is the same hierarchical id used throughout this pipeline
    ("pwd.vishwakarma.<table>"); service defaults to the department so each
    department gets its own OpenMetadata database service.

    Refuses to publish a dataset whose `category` is lower than its most
    sensitive column's `classification` (see _check_category_covers_columns)
    unless `allow_category_below_columns=True`.
    """

    department_id, dataset_slug, table_slug = table_id.split(".")
    dataset_id = f"{department_id}.{dataset_slug}"

    table_row = lookups.get_table(storage, table_id)
    if table_row is None:
        raise ValueError(f"Unknown table_id '{table_id}' -- not found in {lookups.TABLES_PATH}")
    dataset_row = lookups.get_dataset(storage, dataset_id) or {}

    curated_path = lookups.latest_curated_snapshot_path(storage, department_id, dataset_slug, table_slug)
    curated_columns = storage.read_csv(curated_path)

    # Checked before any OpenMetadata call, so a refused publish leaves no
    # half-updated service/database behind.
    category = dataset_row.get("category", "")
    if allow_category_below_columns:
        logger.warning(f"{table_id}: dataset-vs-column category check skipped (allow_category_below_columns=True)")
    else:
        _check_category_covers_columns(table_id, category, curated_columns)

    service = _ensure_service(client, service_name or department_id)
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
    _replace_column_tags(client, table, columns)

    logger.info(f"Published {table_id} -> {_fqn(table)} ({len(curated_columns)} column(s)) from {curated_path}")

    return {
        "table_id": table_id,
        "fully_qualified_name": _fqn(table),
        "curated_path": curated_path,
        "column_count": len(curated_columns),
    }


def _main(argv: list[str]) -> int:
    """Command line entry point (settings come from .env / the shell)."""

    from src.utils.cli import confirm_changes

    load_env()
    confirm_changes(f"publish table {os.environ.get('TABLE_ID')} to OpenMetadata")
    _storage = storage_from_env()
    _client = get_client(
        host_port=os.environ.get("OPENMETADATA_HOST_PORT", "http://localhost:8585/api"),
        jwt_token=os.environ["OPENMETADATA_JWT_TOKEN"],
    )
    publish_table(
        _client,
        _storage,
        os.environ["TABLE_ID"],
        allow_category_below_columns=os.environ.get("ALLOW_CATEGORY_BELOW_COLUMNS", "").strip().lower()
        in {"y", "yes", "true", "1"},
    )
    return 0


if __name__ == "__main__":
    import sys

    from src.utils.cli import run_cli

    sys.exit(run_cli("publish", _main, sys.argv[1:]))
