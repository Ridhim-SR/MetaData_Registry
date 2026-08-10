from typing import Any

from src.openmetadata.client import OpenMetadataClient
from src.openmetadata.ingestion.base import BaseConnector


class PostgresConnector(BaseConnector):
    SCHEMA_NAME = "public"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.host = config.get("host", "localhost")
        self.port = config.get("port", 5432)
        self.database = config.get("database", "appdb")
        self.username = config.get("username", "postgres")
        self.password = config.get("password", "")
        self.service_name = config.get("service_name", f"postgres_{self.database}")

    async def extract_entities(self, client: OpenMetadataClient) -> list[dict]:
        return [
            {
                "name": "users",
                "columns": [
                    {"name": "id", "dataType": "INT"},
                    {"name": "username", "dataType": "VARCHAR", "dataLength": 50},
                    {"name": "email", "dataType": "VARCHAR", "dataLength": 255},
                    {"name": "password_hash", "dataType": "VARCHAR", "dataLength": 255},
                    {"name": "role", "dataType": "VARCHAR", "dataLength": 20},
                    {"name": "created_at", "dataType": "TIMESTAMP"},
                    {"name": "updated_at", "dataType": "TIMESTAMP"},
                ],
                "description": "Application users table",
            }
        ]

    async def ingest(self, client: OpenMetadataClient) -> dict[str, Any]:
        entities = await self.extract_entities(client)
        results: list[dict] = []

        service = await client.upsert_database_service(
            {
                "name": self.service_name,
                "serviceType": "Postgres",
                "connection": {
                    "config": {
                        "type": "Postgres",
                        "hostPort": f"{self.host}:{self.port}",
                        "username": self.username,
                        "password": self.password,
                        "database": self.database,
                        "scheme": "postgresql+psycopg2",
                    }
                },
            }
        )
        results.append(("databaseService", service))

        db_fqn = f"{self.service_name}.{self.database}"
        schema_fqn = f"{db_fqn}.{self.SCHEMA_NAME}"

        database = await client.upsert_database(
            {"name": self.database, "service": self.service_name}
        )
        results.append(("database", database))

        schema = await client.upsert_database_schema(
            {"name": self.SCHEMA_NAME, "database": db_fqn}
        )
        results.append(("databaseSchema", schema))

        for entity in entities:
            table = await client.upsert_table(
                {
                    "name": entity["name"],
                    "databaseSchema": schema_fqn,
                    "tableType": "Regular",
                    "columns": entity["columns"],
                    "description": entity.get("description"),
                }
            )
            results.append(("table", table))

        return {
            "connector": "postgres",
            "service": self.service_name,
            "entities_ingested": len(entities),
            "results": results,
        }
