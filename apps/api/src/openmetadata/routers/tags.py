from fastapi import APIRouter, Depends, HTTPException

from database.models import User
from src.middleware.auth import get_current_user, require_admin
from src.openmetadata.client import OpenMetadataClient
from src.openmetadata.schemas.tags import (
    ClassificationCreate,
    TagCreate,
    GlossaryCreate,
    GlossaryTermCreate,
    TableTagUpdate,
)

router = APIRouter(prefix="/openmetadata/metadata", tags=["openmetadata"])


@router.get("/catalog")
async def get_catalog(user: User = Depends(get_current_user)) -> dict:
    async with OpenMetadataClient() as client:
        return await client.get_tag_catalog()


@router.get("/tables/{table_id}/tags")
async def get_table_tags(table_id: str, user: User = Depends(get_current_user)) -> dict:
    async with OpenMetadataClient() as client:
        try:
            table = await client.get_table(table_id)
        except Exception as exc:
            from httpx import HTTPStatusError

            if isinstance(exc, HTTPStatusError) and exc.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Table not found")
            raise
        return {"tags": table.get("tags", [])}


@router.post("/classifications")
async def create_classification(
    data: ClassificationCreate, _admin: User = Depends(require_admin)
) -> dict:
    async with OpenMetadataClient() as client:
        return await client.create_classification(data.model_dump(exclude_none=True))


@router.post("/tags")
async def create_tag(data: TagCreate, _admin: User = Depends(require_admin)) -> dict:
    async with OpenMetadataClient() as client:
        return await client.create_tag(data.model_dump(exclude_none=True))


@router.post("/glossaries")
async def create_glossary(data: GlossaryCreate, _admin: User = Depends(require_admin)) -> dict:
    async with OpenMetadataClient() as client:
        return await client.create_glossary(data.model_dump(exclude_none=True))


@router.post("/glossary-terms")
async def create_glossary_term(
    data: GlossaryTermCreate, _admin: User = Depends(require_admin)
) -> dict:
    async with OpenMetadataClient() as client:
        return await client.create_glossary_term(data.model_dump(exclude_none=True))


@router.put("/tables/{table_id}/tags")
async def update_table_tags(
    table_id: str, data: TableTagUpdate, _admin: User = Depends(require_admin)
) -> dict:
    async with OpenMetadataClient() as client:
        labels = [label.model_dump(exclude_none=True) for label in data.labels]
        return await client.update_table_tags(table_id, labels)
