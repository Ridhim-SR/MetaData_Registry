import httpx
from fastapi import APIRouter, HTTPException, Query

from src.openmetadata.client import OpenMetadataClient

router = APIRouter(prefix="/openmetadata/metadata", tags=["openmetadata"])


@router.get("/tables")
async def list_tables(
    search: str | None = Query(default=None, description="Free text over table name, columns and description"),
    service: str | None = None,
    database: str | None = None,
    schema: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict]:
    async with OpenMetadataClient() as client:
        return await client.list_tables(
            search=search,
            service=service,
            database=database,
            schema=schema,
            limit=limit,
        )


@router.get("/tables/{table_id}")
async def get_table(table_id: str) -> dict:
    async with OpenMetadataClient() as client:
        try:
            return await client.get_table(table_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Table not found")
            raise


@router.get("/stats")
async def metadata_stats() -> dict:
    async with OpenMetadataClient() as client:
        return await client.metadata_stats()
