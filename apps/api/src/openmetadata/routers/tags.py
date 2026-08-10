from fastapi import APIRouter

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
async def get_catalog() -> dict:
    async with OpenMetadataClient() as client:
        return await client.get_tag_catalog()


@router.post("/classifications")
async def create_classification(data: ClassificationCreate) -> dict:
    async with OpenMetadataClient() as client:
        return await client.create_classification(data.model_dump(exclude_none=True))


@router.post("/tags")
async def create_tag(data: TagCreate) -> dict:
    async with OpenMetadataClient() as client:
        return await client.create_tag(data.model_dump(exclude_none=True))


@router.post("/glossaries")
async def create_glossary(data: GlossaryCreate) -> dict:
    async with OpenMetadataClient() as client:
        return await client.create_glossary(data.model_dump(exclude_none=True))


@router.post("/glossary-terms")
async def create_glossary_term(data: GlossaryTermCreate) -> dict:
    async with OpenMetadataClient() as client:
        return await client.create_glossary_term(data.model_dump(exclude_none=True))


@router.put("/tables/{table_id}/tags")
async def update_table_tags(table_id: str, data: TableTagUpdate) -> dict:
    async with OpenMetadataClient() as client:
        labels = [label.model_dump(exclude_none=True) for label in data.labels]
        return await client.update_table_tags(table_id, labels)
