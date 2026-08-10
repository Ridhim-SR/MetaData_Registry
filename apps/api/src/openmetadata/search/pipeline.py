from typing import Any

from src.openmetadata.client import OpenMetadataClient


class SearchPipeline:
    def __init__(self, client: OpenMetadataClient) -> None:
        self._client = client

    async def reindex_all(self) -> dict[str, Any]:
        return await self._client.post("search/reindex", json={"entities": "*"})

    async def reindex_entity(self, entity_type: str) -> dict[str, Any]:
        return await self._client.post("search/reindex", json={"entities": entity_type})

    async def search(
        self,
        query: str,
        entity_type: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"q": query, "page": page, "size": size}
        if entity_type:
            params["entity"] = entity_type
        return await self._client.get("search/query", params=params)
