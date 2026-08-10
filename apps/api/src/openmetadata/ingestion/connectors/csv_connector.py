import csv
import os
from typing import Any

from src.openmetadata.client import OpenMetadataClient
from src.openmetadata.ingestion.base import BaseConnector


class CsvConnector(BaseConnector):
    SERVICE_NAME = "csv_files"
    DATABASE_NAME = "csv_import_db"
    SCHEMA_NAME = "public"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.file_path = config.get("file_path", "")
        self.table_name = config.get("table_name", "csv_import")
        self.delimiter = config.get("delimiter", ",")
        self.has_header = config.get("has_header", True)

    def _read_csv(self) -> list[list[str]]:
        if not os.path.isfile(self.file_path):
            raise FileNotFoundError(f"CSV not found: {self.file_path}")

        with open(self.file_path, newline="", encoding=self.config.get("encoding", "utf-8-sig")) as f:
            return list(csv.reader(f, delimiter=self.delimiter))

    def _infer_columns(self, header: list[str], rows: list[list[str]]) -> list[dict[str, str]]:
        def looks_numeric(value: str) -> bool:
            try:
                float(value.replace(",", ""))
                return True
            except ValueError:
                return False

        sample = next((r for r in rows if r and any(c.strip() for c in r)), [])
        columns: list[dict[str, str]] = []
        for i, name in enumerate(header):
            if not name.strip():
                continue
            data_type = "NUMBER" if i < len(sample) and looks_numeric(sample[i]) else "STRING"
            columns.append({"name": name.strip(), "dataType": data_type})
        return columns

    async def extract_entities(self, client: OpenMetadataClient) -> list[dict]:
        rows = self._read_csv()
        if not rows:
            return []

        header = [h for h in rows[0]] if self.has_header else [f"col_{i}" for i in range(len(rows[0]))]
        data_rows = rows[1:] if self.has_header else rows
        columns = self._infer_columns(header, data_rows)

        return [
            {
                "name": self.table_name,
                "columns": columns,
                "row_count": len(data_rows),
                "sample_rows": data_rows[:5],
            }
        ]

    async def ingest(self, client: OpenMetadataClient) -> dict[str, Any]:
        entities = await self.extract_entities(client)
        results: list[dict] = []

        service = await client.upsert_database_service(
            {
                "name": self.SERVICE_NAME,
                "serviceType": "CustomDatabase",
                "connection": {
                    "config": {
                        "type": "CustomDatabase",
                        "sourcePythonClass": "custom.csv.CsvSource",
                        "connectionOptions": {},
                    }
                },
            }
        )
        results.append(("databaseService", service))

        db_fqn = f"{self.SERVICE_NAME}.{self.DATABASE_NAME}"
        schema_fqn = f"{db_fqn}.{self.SCHEMA_NAME}"

        database = await client.upsert_database(
            {"name": self.DATABASE_NAME, "service": self.SERVICE_NAME}
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
                    "description": (
                        f"Imported from {self.file_path} "
                        f"({entity['row_count']} rows)"
                    ),
                }
            )
            results.append(("table", table))

        return {
            "connector": "csv",
            "service": self.SERVICE_NAME,
            "entities_ingested": len(entities),
            "row_count": entities[0]["row_count"] if entities else 0,
            "results": results,
        }
