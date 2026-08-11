from __future__ import annotations

import pandas as pd

from metadata.generated.schema.entity.services.connections.metadata.openMetadataConnection import (
    OpenMetadataConnection,
)
from metadata.generated.schema.security.client.openMetadataJWTClientConfig import (
    OpenMetadataJWTClientConfig,
)
from metadata.generated.schema.api.data.createTable import CreateTableRequest
from metadata.generated.schema.entity.data.table import Column, DataType, Table, TableData
from metadata.ingestion.ometa.ometa_api import OpenMetadata


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

    def ensure_table(self, df: pd.DataFrame) -> Table:
        """Create the table if missing, or update it if it exists.
        Safe to call every run -- create_or_update upserts by FQN."""

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
            print("No new rows to append -- already up to date.")
            return

        sample = TableData(
            columns=list(new_rows.columns),
            rows=new_rows.astype(str).values.tolist()[-max_rows:],
        )

        self.client.ingest_table_sample_data(table=table, sample_data=sample)
        print(f"Appended {len(new_rows)} new row(s) to {self.fqn}")