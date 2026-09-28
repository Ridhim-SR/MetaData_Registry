from fastapi import APIRouter, Depends, Query

from database.models import User
from src.middleware.auth import allowed_services, get_current_user, scoped_service
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
) -> dict:
    async with OpenMetadataClient() as client:
        try:
            return await client.search_tables(
                query=q,
                service=scoped_service(user, service),
                limit=size,
                page=page,
                allowed_services=allowed_services(user),
            )
        except Exception:
            # Fallback to metadata list filter when search index is unavailable
            page_data = await client.list_tables_paged(
                search=q,
                service=scoped_service(user, service),
                limit=size,
                allowed_services=allowed_services(user),
            )
            return {"data": page_data["data"], "total": page_data["paging"].get("total"), "page": page, "fallback": True}


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
