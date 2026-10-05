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
        after: str | None = None,
    ) -> list[dict]:
        """Backward-compatible: single OM page + in-memory filter, returns list."""
        page = await self.list_tables_paged(
            search=search, service=service, database=database,
            schema=schema, limit=limit, after=after,
        )
        return page["data"]

    async def list_tables_paged(
        self,
        search: str | None = None,
        service: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        limit: int = 200,
        after: str | None = None,
        allowed_services: set[str] | None = None,
    ) -> dict:
        """One OM page with server-side paging cursor + in-memory FQN/text filter.

        Returns {"data": [...], "paging": {"total": int, "after": str|None}}.
        """
        params: dict[str, Any] = {"fields": "columns,tags,owners", "limit": limit}
        if after:
            params["after"] = after
        data = await self.get("tables", params=params)
        tables: list[dict] = data.get("data", [])
        paging: dict = data.get("paging", {})
        needle = search.lower() if search else None
        result: list[dict] = []
        for t in tables:
            fqn = (t.get("fullyQualifiedName") or "").split(".")
            svc = fqn[0] if fqn else ""
            if allowed_services is not None and svc not in allowed_services:
                continue
            if service and (len(fqn) < 1 or fqn[0] != service):
                continue
            if database and (len(fqn) < 2 or fqn[1] != database):
                continue
            if schema and (len(fqn) < 3 or fqn[2] != schema):
                continue
            if needle and not self._table_matches(t, needle):
                continue
            result.append(t)
        return {"data": result, "paging": {"total": paging.get("total"), "after": paging.get("after")}}

    async def get_table(self, table_id: str) -> dict:
        return await self.get(f"tables/{table_id}", params={"fields": "columns,tags,owners"})

    async def get_table_by_fqn(self, fqn: str) -> dict:
        return await self.get(f"tables/name/{fqn}", params={"fields": "columns,tags,owners"})

    async def get_table_lineage(self, fqn: str) -> dict:
        return await self.get(f"lineage/table/name/{fqn}")

    async def list_services(self, limit: int = 100, after: str | None = None) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if after:
            params["after"] = after
        return await self.get("services/databaseServices", params=params)

    async def list_databases(
        self, service: str | None = None, limit: int = 100, after: str | None = None
    ) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if after:
            params["after"] = after
        if service:
            params["service"] = service
        return await self.get("databases", params=params)

    async def list_schemas(
        self, database: str | None = None, limit: int = 100, after: str | None = None
    ) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if after:
            params["after"] = after
        if database:
            params["database"] = database
        return await self.get("databaseSchemas", params=params)

    async def get_facets(self) -> dict:
        """Lightweight filter values for Explore: service / database / schema names."""
        services = (await self.get("services/databaseServices", params={"limit": 100})).get("data", [])
        databases = (await self.get("databases", params={"limit": 1000})).get("data", [])
        schemas = (await self.get("databaseSchemas", params={"limit": 1000})).get("data", [])
        return {
            "services": sorted({s.get("name") for s in services if s.get("name")}),
            "databases": sorted({d.get("name") for d in databases if d.get("name")}),
            "schemas": sorted({s.get("name") for s in schemas if s.get("name")}),
        }

    async def _fetch_all(self, path: str, params: dict | None = None, max_pages: int = 20) -> list[dict]:
        """Follow OM paging cursors to get full counts. Bounded by max_pages."""
        out: list[dict] = []
        after: str | None = None
        for _ in range(max_pages):
            p = dict(params or {})
            if after:
                p["after"] = after
            data = await self.get(path, params=p)
            out.extend(data.get("data", []))
            after = (data.get("paging") or {}).get("after")
            if not after:
                break
        return out

    async def metadata_stats(self, allowed_services: set[str] | None = None) -> dict:
        services = await self._fetch_all("services/databaseServices", {"limit": 100})
        databases = await self._fetch_all("databases", {"limit": 1000})
        schemas = await self._fetch_all("databaseSchemas", {"limit": 1000})
        tables = await self._fetch_all("tables", {"fields": "columns", "limit": 1000})
        if allowed_services is not None:
            tables = [t for t in tables if (t.get("fullyQualifiedName") or "").split(".")[0] in allowed_services]
        by_service: dict[str, int] = {}
        for t in tables:
            svc = (t.get("fullyQualifiedName") or "").split(".")[0]
            by_service[svc] = by_service.get(svc, 0) + 1
        recent = [
            {"id": t.get("id"), "name": t.get("name"), "fullyQualifiedName": t.get("fullyQualifiedName")}
            for t in tables[:10]
        ]
        return {
            "services": len(services),
            "databases": len(databases),
            "schemas": len(schemas),
            "tables": len(tables),
            "columns": sum(len(t.get("columns") or []) for t in tables),
            "byService": [{"service": k, "tables": v} for k, v in sorted(by_service.items())],
            "recent": recent,
        }

    async def search_tables(
        self,
        query: str,
        service: str | None = None,
        limit: int = 20,
        page: int = 1,
        allowed_services: set[str] | None = None,
    ) -> dict:
        params: dict[str, Any] = {"q": query, "index": "table_search_index", "page": page, "size": limit}
        data = await self.get("search/query", params=params)
        hits = data.get("hits", {}).get("hits", []) if isinstance(data.get("hits"), dict) else data.get("hits", [])
        out: list[dict] = []
        for h in hits:
            src = h.get("_source", h) if isinstance(h, dict) else {}
            fqn = src.get("fullyQualifiedName", "")
            svc = fqn.split(".")[0] if fqn else ""
            if allowed_services is not None and svc not in allowed_services:
                continue
            if service and svc != service:
                continue
            out.append(src)
        total = data.get("hits", {}).get("total", {}).get("value", len(out)) if isinstance(data.get("hits"), dict) else len(out)
        return {"data": out, "total": total, "page": page}

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
