from __future__ import annotations

import pandas as pd

from src.utils.logger import get_logger

from metadata.generated.schema.entity.services.connections.metadata.openMetadataConnection import (
    OpenMetadataConnection,
)
from metadata.generated.schema.security.client.openMetadataJWTClientConfig import (
    OpenMetadataJWTClientConfig,
)
from metadata.generated.schema.api.data.createDatabase import CreateDatabaseRequest
from metadata.generated.schema.api.data.createDatabaseSchema import CreateDatabaseSchemaRequest
from metadata.generated.schema.api.data.createTable import CreateTableRequest
from metadata.generated.schema.api.services.createDatabaseService import (
    CreateDatabaseServiceRequest,
)
from metadata.generated.schema.entity.data.database import Database
from metadata.generated.schema.entity.data.databaseSchema import DatabaseSchema
from metadata.generated.schema.entity.services.connections.database.mysqlConnection import (
    MysqlConnection,
)
from metadata.generated.schema.entity.services.databaseService import (
    DatabaseConnection,
    DatabaseService,
    DatabaseServiceType,
)
from metadata.generated.schema.entity.data.table import Column, DataType, Table, TableData
from metadata.ingestion.ometa.ometa_api import OpenMetadata

logger = get_logger(__name__)


class OpenMetadataLoader:
    """
    Registers a table in OpenMetadata (idempotent) and appends DataFrame
    rows as sample data, skipping rows already loaded (dedup by key).
    """

    DTYPE_MAP = {
        "int64": DataType.INT,
        "float64": DataType.DOUBLE,
        "object": DataType.STRING,
        "string": DataType.STRING,
        "bool": DataType.BOOLEAN,
    }

    def __init__(
        self,
        host_port: str,
        jwt_token: str,
        service_name: str,
        database_name: str,
        schema_name: str,
        table_name: str,
        dedupe_keys: list[str],
    ):
        self.service_name = service_name
        self.database_name = database_name
        self.schema_name = schema_name
        self.table_name = table_name
        self.dedupe_keys = dedupe_keys
        self.fqn = f"{service_name}.{database_name}.{schema_name}.{table_name}"

        server_config = OpenMetadataConnection(
            hostPort=host_port,
            authProvider="openmetadata",
            securityConfig=OpenMetadataJWTClientConfig(jwtToken=jwt_token),
        )
        self.client = OpenMetadata(server_config)

    def _columns_from_df(self, df: pd.DataFrame) -> list[Column]:
        return [
            Column(name=name, dataType=self.DTYPE_MAP.get(str(dtype), DataType.STRING))
            for name, dtype in df.dtypes.items()
        ]

    def ensure_service(self) -> DatabaseService:
        """Create the database service if it doesn't exist yet."""

        service = self.client.get_by_name(entity=DatabaseService, fqn=self.service_name)

        if service:
            return service

        logger.info(f"Creating database service {self.service_name}")
        return self.client.create_or_update(
            CreateDatabaseServiceRequest(
                name=self.service_name,
                serviceType=DatabaseServiceType.Mysql,
                connection=DatabaseConnection(
                    config=MysqlConnection(
                        username="dummy",
                        hostPort="localhost:3306",
                    )
                ),
            )
        )

    def ensure_database(self) -> Database:
        """Create the database if it doesn't exist yet."""

        fqn = f"{self.service_name}.{self.database_name}"
        database = self.client.get_by_name(entity=Database, fqn=fqn)

        if database:
            return database

        logger.info(f"Creating database {fqn}")
        return self.client.create_or_update(
            CreateDatabaseRequest(name=self.database_name, service=self.service_name)
        )

    def ensure_schema(self) -> DatabaseSchema:
        """Create the database schema if it doesn't exist yet."""

        fqn = f"{self.service_name}.{self.database_name}.{self.schema_name}"
        schema = self.client.get_by_name(entity=DatabaseSchema, fqn=fqn)

        if schema:
            return schema

        logger.info(f"Creating database schema {fqn}")
        return self.client.create_or_update(
            CreateDatabaseSchemaRequest(
                name=self.schema_name,
                database=f"{self.service_name}.{self.database_name}",
            )
        )

    def ensure_table(self, df: pd.DataFrame) -> Table:
        """Ensure the full hierarchy (service -> database -> schema -> table)
        exists, creating any missing piece. Safe to call every run."""

        self.ensure_service()
        self.ensure_database()
        self.ensure_schema()

        request = CreateTableRequest(
            name=self.table_name,
            databaseSchema=f"{self.service_name}.{self.database_name}.{self.schema_name}",
            columns=self._columns_from_df(df),
        )

        return self.client.create_or_update(request)

    def _existing_keys(self) -> set[tuple]:
        """Keys already present in the table's current sample data."""

        table = self.client.get_by_name(entity=Table, fqn=self.fqn)
        sample = self.client.get_sample_data(table)

        if not sample or not sample.sampleData:
            return set()

        cols = [c.lower() for c in sample.sampleData.columns]
        key_idx = [cols.index(k) for k in self.dedupe_keys]

        return {tuple(row[i] for i in key_idx) for row in sample.sampleData.rows}

    def append(self, df: pd.DataFrame, max_rows: int = 100) -> None:
        """Push only rows not already loaded, keeping the sample under max_rows."""

        table = self.ensure_table(df)
        existing = self._existing_keys()

        new_rows = df[~df[self.dedupe_keys].apply(tuple, axis=1).isin(existing)]

        if new_rows.empty:
            logger.info("No new rows to append -- already up to date.")
            return

        sample = TableData(
            columns=list(new_rows.columns),
            rows=new_rows.astype(str).values.tolist()[-max_rows:],
        )

        self.client.ingest_table_sample_data(table=table, sample_data=sample)
        logger.info(f"Appended {len(new_rows)} new row(s) to {self.fqn}")