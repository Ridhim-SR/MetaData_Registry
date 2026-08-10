import base64
import httpx
from typing import Any

from src.openmetadata.config import settings


class OpenMetadataClient:
    def __init__(self) -> None:
        self._base_url = settings.base_url
        self._token: str | None = None
        self._client = httpx.AsyncClient(timeout=settings.request_timeout)

    async def __aenter__(self) -> "OpenMetadataClient":
        if settings.jwt_token:
            self._token = settings.jwt_token
        else:
            await self._login()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.aclose()

    async def _login(self) -> None:
        encoded = base64.b64encode(settings.password.encode()).decode()
        resp = await self._client.post(
            settings.auth_endpoint,
            json={"email": settings.username, "password": encoded},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data.get("accessToken")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    async def get(self, path: str, params: dict | None = None) -> dict:
        resp = await self._client.get(
            f"{self._base_url}/{path.lstrip('/')}",
            headers=self._headers(),
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    async def post(self, path: str, json: dict | None = None) -> dict:
        resp = await self._client.post(
            f"{self._base_url}/{path.lstrip('/')}",
            headers=self._headers(),
            json=json,
        )
        resp.raise_for_status()
        return resp.json()

    async def put(self, path: str, json: dict | None = None) -> dict:
        resp = await self._client.put(
            f"{self._base_url}/{path.lstrip('/')}",
            headers=self._headers(),
            json=json,
        )
        resp.raise_for_status()
        return resp.json()

    async def delete(self, path: str) -> dict:
        resp = await self._client.delete(
            f"{self._base_url}/{path.lstrip('/')}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    # ---- convenience wrappers ----

    async def get_entity(self, entity_type: str, entity_id: str) -> dict:
        return await self.get(f"entities/{entity_type}/{entity_id}")

    async def list_entities(self, entity_type: str) -> list[dict]:
        data = await self.get(f"entities/{entity_type}")
        return data.get("data", [])

    async def upsert_database_service(self, data: dict) -> dict:
        return await self.put("services/databaseServices", json=data)

    async def upsert_database(self, data: dict) -> dict:
        return await self.put("databases", json=data)

    async def upsert_database_schema(self, data: dict) -> dict:
        return await self.put("databaseSchemas", json=data)

    async def upsert_table(self, data: dict) -> dict:
        return await self.put("tables", json=data)

    async def trigger_ingestion_pipeline(self, pipeline_id: str) -> dict:
        return await self.post(f"services/ingestionPipelines/{pipeline_id}/trigger")

    async def list_ingestion_pipelines(self) -> list[dict]:
        data = await self.get("services/ingestionPipelines")
        return data.get("data", [])

    async def create_ingestion_pipeline(self, pipeline_def: dict) -> dict:
        return await self.post("services/ingestionPipelines", json=pipeline_def)

    # ---- metadata discovery ----

    async def list_tables(
        self,
        search: str | None = None,
        service: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        data = await self.get("tables", params={"fields": "columns,tags", "limit": limit})
        tables: list[dict] = data.get("data", [])
        needle = search.lower() if search else None
        result: list[dict] = []
        for t in tables:
            fqn = (t.get("fullyQualifiedName") or "").split(".")
            if service and (len(fqn) < 1 or fqn[0] != service):
                continue
            if database and (len(fqn) < 2 or fqn[1] != database):
                continue
            if schema and (len(fqn) < 3 or fqn[2] != schema):
                continue
            if needle and not self._table_matches(t, needle):
                continue
            result.append(t)
        return result

    async def get_table(self, table_id: str) -> dict:
        return await self.get(f"tables/{table_id}", params={"fields": "columns,tags"})

    async def metadata_stats(self) -> dict:
        services = (await self.get("services/databaseServices", params={"limit": 100})).get("data", [])
        databases = (await self.get("databases", params={"limit": 100})).get("data", [])
        schemas = (await self.get("databaseSchemas", params={"limit": 100})).get("data", [])
        tables = (await self.get("tables", params={"fields": "columns", "limit": 100})).get("data", [])
        return {
            "services": len(services),
            "databases": len(databases),
            "schemas": len(schemas),
            "tables": len(tables),
            "columns": sum(len(t.get("columns") or []) for t in tables),
        }

    @staticmethod
    def _table_matches(table: dict, needle: str) -> bool:
        name = (table.get("name") or "").lower()
        fqn = (table.get("fullyQualifiedName") or "").lower()
        desc = (table.get("description") or "").lower()
        if needle in name or needle in fqn or needle in desc:
            return True
        for col in table.get("columns") or []:
            col_name = (col.get("name") or "").lower()
            col_desc = (col.get("description") or "").lower()
            if needle in col_name or needle in col_desc:
                return True
        return False

    # ---- tags & glossary ----

    async def get_tag_catalog(self) -> dict:
        classifications = (await self.get("classifications", params={"limit": 100})).get("data", [])
        tags = (await self.get("tags", params={"limit": 100})).get("data", [])
        glossaries = (await self.get("glossaries", params={"limit": 100})).get("data", [])
        terms = (await self.get("glossaryTerms", params={"limit": 100})).get("data", [])

        def slim(item: dict) -> dict:
            return {
                "name": item.get("name"),
                "fullyQualifiedName": item.get("fullyQualifiedName"),
                "description": item.get("description"),
            }

        return {
            "classifications": [
                {
                    **slim(c),
                    "tags": [
                        slim(t)
                        for t in tags
                        if (t.get("classification") or {}).get("fullyQualifiedName")
                        == c.get("fullyQualifiedName")
                    ],
                }
                for c in classifications
            ],
            "glossaries": [
                {
                    **slim(g),
                    "terms": [
                        slim(t)
                        for t in terms
                        if (t.get("glossary") or {}).get("fullyQualifiedName")
                        == g.get("fullyQualifiedName")
                    ],
                }
                for g in glossaries
            ],
        }

    async def create_classification(self, data: dict) -> dict:
        return await self.post("classifications", json=data)

    async def create_tag(self, data: dict) -> dict:
        return await self.post("tags", json=data)

    async def create_glossary(self, data: dict) -> dict:
        return await self.post("glossaries", json=data)

    async def create_glossary_term(self, data: dict) -> dict:
        return await self.post("glossaryTerms", json=data)

    async def update_table_tags(self, table_id: str, labels: list[dict]) -> dict:
        return await self.put(f"tables/{table_id}/tags", json=labels)

    async def health(self) -> dict:
        resp = await self._client.get(
            f"{self._base_url}/system/health",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return {"status": resp.text.strip() or "ok"}
