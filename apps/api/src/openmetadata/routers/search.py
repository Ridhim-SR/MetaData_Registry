from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_session as db_get_session
from database.models import DatasetVisibility, User
from src.middleware.auth import allowed_services, get_current_user, scoped_service, user_context
from src.openmetadata import visibility as vis
from src.openmetadata.client import OpenMetadataClient
from src.openmetadata.search.pipeline import SearchPipeline

router = APIRouter(prefix="/openmetadata/search", tags=["openmetadata-search"])


@router.get("/q")
async def search(
    q: str = Query(min_length=1, description="Full-text query across datasets"),
    service: str | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_get_session),
) -> dict:
    async with OpenMetadataClient() as client:
        try:
            result = await client.search_tables(
                query=q,
                service=scoped_service(user, service),
                limit=size,
                page=page,
                allowed_services=allowed_services(user),
            )
            candidates, total, fallback = result.get("data", []), result.get("total"), False
        except Exception:
            # Fallback to metadata list filter when search index is unavailable
            page_data = await client.list_tables_paged(
                search=q,
                service=scoped_service(user, service),
                limit=size,
                allowed_services=allowed_services(user),
            )
            candidates, total, fallback = page_data["data"], page_data["paging"].get("total"), True
        rows = (
            await session.execute(
                select(DatasetVisibility).where(
                    DatasetVisibility.fqn.in_([t.get("fullyQualifiedName") or "" for t in candidates])
                )
            )
        ).scalars().all() if candidates else []
        vmap = {r.fqn: {"visibility": r.visibility.value, "department": r.department} for r in rows}
        full, teasers = vis.visible_tables(candidates, vmap, user_context(user))
        return {"data": full, "teasers": teasers, "total": total, "page": page, "fallback": fallback}


@router.post("/reindex")
async def reindex(
    entity_type: str | None = None,
    user: User = Depends(get_current_user),
) -> dict:
    from fastapi import HTTPException

    if user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    async with OpenMetadataClient() as client:
        pipeline = SearchPipeline(client)
        if entity_type:
            return await pipeline.reindex_entity(entity_type)
        return await pipeline.reindex_all()
