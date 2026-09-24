import os

from metadata.generated.schema.api.data.createDatabase import CreateDatabaseRequest
from metadata.generated.schema.api.data.createDatabaseSchema import (
    CreateDatabaseSchemaRequest,
)
from metadata.generated.schema.api.data.createTable import CreateTableRequest
from metadata.generated.schema.api.services.createDatabaseService import (
    CreateDatabaseServiceRequest,
)
from metadata.generated.schema.entity.data.database import Database
from metadata.generated.schema.entity.data.databaseSchema import DatabaseSchema
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
from metadata.ingestion.ometa.ometa_api import OpenMetadata

from src.schema_registry import lookups
from src.storage.base import ObjectStorage
from src.storage.local import LocalObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)

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
        return client.get_by_name(entity=entity, fqn=fqn)
    except Exception as exc:  # noqa: BLE001
        if "not found" in str(exc).lower() or "404" in str(exc):
            return None
        raise


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
    }
    if data_type in _LENGTH_REQUIRED_TYPES:
        length = row.get("length")
        kwargs["dataLength"] = int(length) if length else _DEFAULT_LENGTH
    return Column(**kwargs)


def _ensure_service(client: OpenMetadata, service_name: str) -> DatabaseService:
    existing = _get_or_none(client, DatabaseService, service_name)
    if existing:
        return existing
    return client.create_or_update(
        CreateDatabaseServiceRequest(
            name=service_name,
            serviceType=DatabaseServiceType.CustomDatabase,
            connection=DatabaseConnection(
                config=CustomDatabaseConnection(type="CustomDatabase", sourcePythonClass="custom")
            ),
        )
    )


def _ensure_database(client: OpenMetadata, service_fqn: str, database_name: str) -> Database:
    fqn = f"{service_fqn}.{database_name}"
    existing = _get_or_none(client, Database, fqn)
    if existing:
        return existing
    return client.create_or_update(CreateDatabaseRequest(name=database_name, service=service_fqn))


def _ensure_schema(client: OpenMetadata, database_fqn: str, schema_name: str) -> DatabaseSchema:
    fqn = f"{database_fqn}.{schema_name}"
    existing = _get_or_none(client, DatabaseSchema, fqn)
    if existing:
        return existing
    return client.create_or_update(CreateDatabaseSchemaRequest(name=schema_name, database=database_fqn))


def _latest_curated_path(storage: ObjectStorage, department_id: str, dataset_slug: str, table_slug: str) -> str:
    prefix = f"department/{department_id}/{dataset_slug}/{table_slug}/curated/schemas/"
    files = storage.list(prefix)
    if not files:
        raise FileNotFoundError(f"No curated schema under {prefix} -- run the pipeline for this table first.")
    return files[-1]  # filenames are fixed-width UTC timestamps -> lexical order == chronological order


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

    table_row = lookups.get_table(storage, table_id)
    if table_row is None:
        raise ValueError(f"Unknown table_id '{table_id}' -- not found in {lookups.TABLES_PATH}")

    curated_path = _latest_curated_path(storage, department_id, dataset_slug, table_slug)
    curated_columns = storage.read_csv(curated_path)

    service = _ensure_service(client, service_name or department_id)
    database = _ensure_database(client, _fqn(service), dataset_slug)
    schema = _ensure_schema(client, _fqn(database), table_row["schema_name"])

    table = client.create_or_update(
        CreateTableRequest(
            name=table_row["table_name"],
            tableType=TableType.Regular,
            databaseSchema=_fqn(schema),
            columns=[_to_column(row) for row in curated_columns],
        )
    )

    logger.info(f"Published {table_id} -> {_fqn(table)} ({len(curated_columns)} column(s)) from {curated_path}")

    return {
        "table_id": table_id,
        "fully_qualified_name": _fqn(table),
        "curated_path": curated_path,
        "column_count": len(curated_columns),
    }


if __name__ == "__main__":
    _storage = LocalObjectStorage(os.environ.get("STORAGE_ROOT", "storage"))
    _client = get_client(
        host_port=os.environ.get("OPENMETADATA_HOST_PORT", "http://localhost:8585/api"),
        jwt_token=os.environ["OPENMETADATA_JWT_TOKEN"],
    )
    publish_table(_client, _storage, os.environ["TABLE_ID"])
