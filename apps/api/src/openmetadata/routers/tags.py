from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_session as db_get_session
from database.models import DatasetVisibility, User
from src.middleware.auth import get_current_user, require_admin, user_context
from src.openmetadata import visibility as vis
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
async def get_table_tags(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_get_session),
) -> dict:
    async with OpenMetadataClient() as client:
        try:
            table = await client.get_table(table_id)
        except Exception as exc:
            from httpx import HTTPStatusError

            if isinstance(exc, HTTPStatusError) and exc.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Table not found")
            raise
        fqn = table.get("fullyQualifiedName") or ""
        rows = (
            await session.execute(select(DatasetVisibility).where(DatasetVisibility.fqn == fqn))
        ).scalars().all()
        vmap = {r.fqn: {"visibility": r.visibility.value, "department": r.department} for r in rows}
        ctx = user_context(user)
        visibility = vis.normalize_visibility(vmap.get(fqn, {}).get("visibility"))
        if visibility == vis.CONFIDENTIAL and not (ctx and ctx.get("role") == "admin"):
            raise HTTPException(status_code=404, detail="Table not found")
        full, _ = vis.visible_tables([table], vmap, ctx)
        if not full:
            raise HTTPException(status_code=403, detail="Access denied for this table")
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
