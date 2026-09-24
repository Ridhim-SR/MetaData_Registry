"""Metadata ingestion via the OFFICIAL OpenMetadata Python SDK.

App flow: FastAPI -> Pydantic (schemas/dataset.py) -> this service -> OM server.
No hand-built /api/v1/... URLs and no custom httpx wrapper here.
"""

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
from metadata.generated.schema.security.client.openMetadataJWTClientConfig import (
    OpenMetadataJWTClientConfig,
)
from metadata.ingestion.ometa.ometa_api import OpenMetadata

from src.openmetadata.config import settings
from src.openmetadata.schemas.dataset import DatasetCreate


def get_client() -> OpenMetadata:
    if not settings.jwt_token:
        raise RuntimeError(
            "OPENMETADATA_JWT_TOKEN is not set. Create a bot JWT in the "
            "OpenMetadata UI (Settings -> Bots -> ingestion-bot) and export it."
        )
    server_config = OpenMetadataConnection(
        hostPort=settings.host_port,
        authProvider=AuthProvider.openmetadata,
        securityConfig=OpenMetadataJWTClientConfig(jwtToken=settings.jwt_token),
    )
    return OpenMetadata(server_config)


def _to_data_type(raw: str) -> DataType:
    try:
        return DataType(raw.upper())
    except ValueError:
        valid = sorted(d.value for d in DataType)
        raise ValueError(f"Unsupported data_type '{raw}'. Valid examples: VARCHAR, INT, DECIMAL. Full list: {valid}")


# OM server mandates dataLength for these types; our input has none, so default it.
LENGTH_REQUIRED_TYPES = {"CHAR", "VARCHAR", "BINARY", "VARBINARY"}
DEFAULT_DATA_LENGTH = 256


def _to_column(col) -> Column:
    data_type = _to_data_type(col.data_type)
    kwargs: dict = {
        "name": col.name,
        "dataType": data_type,
        "description": col.description,
    }
    if data_type.value in LENGTH_REQUIRED_TYPES:
        kwargs["dataLength"] = DEFAULT_DATA_LENGTH
    return Column(**kwargs)


def _get_or_none(client: OpenMetadata, entity, fqn: str):
    """get_by_name returns None when nullable, but some server versions raise on 404."""
    try:
        return client.get_by_name(entity=entity, fqn=fqn)
    except Exception as exc:  # noqa: BLE001
        message = str(exc).lower()
        if "not found" in message or "404" in message:
            return None
        raise


def _unwrap(value):
    """SDK v2 entities wrap scalars in RootModels (e.g. EntityName(root='x'))."""
    root = getattr(value, "root", None)
    return root if root is not None else value


def _entity_ref(entity) -> str:
    name = getattr(entity, "fullyQualifiedName", None) or getattr(entity, "name", None)
    return str(_unwrap(name))


def ensure_database_service(client: OpenMetadata, service_name: str) -> DatabaseService:
    existing = _get_or_none(client, DatabaseService, service_name)
    if existing:
        return existing
    return client.create_or_update(
        CreateDatabaseServiceRequest(
            name=service_name,
            serviceType=DatabaseServiceType.CustomDatabase,
            connection=DatabaseConnection(
                config=CustomDatabaseConnection(
                    type="CustomDatabase",
                    sourcePythonClass="custom",
                )
            ),
        )
    )


def ensure_database(client: OpenMetadata, service_fqn: str, database_name: str) -> Database:
    fqn = f"{service_fqn}.{database_name}"
    existing = _get_or_none(client, Database, fqn)
    if existing:
        return existing
    return client.create_or_update(
        CreateDatabaseRequest(name=database_name, service=service_fqn)
    )


def ensure_database_schema(
    client: OpenMetadata, database_fqn: str, schema_name: str
) -> DatabaseSchema:
    fqn = f"{database_fqn}.{schema_name}"
    existing = _get_or_none(client, DatabaseSchema, fqn)
    if existing:
        return existing
    return client.create_or_update(
        CreateDatabaseSchemaRequest(name=schema_name, database=database_fqn)
    )


def store_dataset(payload: DatasetCreate) -> dict:
    """Create-or-update Service -> Database -> Schema -> Table. Returns table info."""
    client = get_client()
    if not client.health_check():
        raise ConnectionError(
            f"OpenMetadata server at {settings.host_port} is unreachable."
        )

    service = ensure_database_service(client, payload.database_service)
    database = ensure_database(client, _entity_ref(service), payload.database)
    schema = ensure_database_schema(client, _entity_ref(database), payload.database_schema)

    table = client.create_or_update(
        CreateTableRequest(
            name=payload.name,
            displayName=payload.display_name,
            description=payload.description,
            tableType=TableType.Regular,
            databaseSchema=_entity_ref(schema),
            columns=[_to_column(col) for col in payload.columns],
        )
    )
    table_id = str(_unwrap(getattr(table, "id", "")))
    return {
        "name": str(_unwrap(getattr(table, "name", payload.name))),
        "fully_qualified_name": _entity_ref(table),
        "id": table_id,
    }


def table_exists_fqn(service: str, database: str, schema: str, table: str) -> str:
    return f"{service}.{database}.{schema}.{table}"
