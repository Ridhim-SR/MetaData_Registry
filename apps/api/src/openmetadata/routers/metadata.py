import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_session as db_get_session
from database.models import DatasetVisibility, User
from src.middleware.auth import allowed_services, get_current_user, scoped_service, user_context
from src.openmetadata import visibility as vis
from src.openmetadata.client import OpenMetadataClient

router = APIRouter(prefix="/openmetadata/metadata", tags=["openmetadata"])


async def _visibility_map(session: AsyncSession, fqns: list[str]) -> dict[str, dict]:
    if not fqns:
        return {}
    rows = (
        await session.execute(select(DatasetVisibility).where(DatasetVisibility.fqn.in_(fqns)))
    ).scalars().all()
    return {r.fqn: {"visibility": r.visibility.value, "department": r.department} for r in rows}


async def _visible_full(session: AsyncSession, tables: list[dict], user: User) -> list[dict]:
    """Keep tables the caller may open; annotate with access_level/department.

    Public tables bypass department scoping; everything else follows the
    existing service policy plus the visibility sidecar.
    """
    vmap = await _visibility_map(session, [t.get("fullyQualifiedName") or "" for t in tables])
    full, _ = vis.visible_tables(tables, vmap, user_context(user))
    return full


def _filter_allowed(items: list[dict], allowed: set[str] | None) -> list[dict]:
    if allowed is None:
        return items
    return [i for i in items if (i.get("fullyQualifiedName") or "").split(".")[0] in allowed]


@router.get("/tables")
async def list_tables(
    search: str | None = Query(default=None, description="Free text over table name, columns and description"),
    service: str | None = None,
    database: str | None = None,
    schema: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    after: str | None = Query(default=None, description="Paging cursor from previous response"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_get_session),
) -> list[dict]:
    """Legacy list shape (array) for backward compat with current web UI."""
    effective_service = scoped_service(user, service)
    async with OpenMetadataClient() as client:
        raw = await client.list_tables(
            search=search,
            service=effective_service,
            database=database,
            schema=schema,
            limit=limit,
            after=after,
        )
    return await _visible_full(session, raw, user)


@router.get("/tables/paged")
async def list_tables_paged(
    search: str | None = None,
    service: str | None = None,
    database: str | None = None,
    schema: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    after: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_get_session),
) -> dict:
    """Paged envelope {data, paging{total, after}} for scalable Explore UI."""
    effective_service = scoped_service(user, service)
    async with OpenMetadataClient() as client:
        page = await client.list_tables_paged(
            search=search, service=effective_service, database=database,
            schema=schema, limit=limit, after=after,
            allowed_services=allowed_services(user),
        )
    page["data"] = await _visible_full(session, page["data"], user)
    return page


@router.get("/tables/by-fqn")
async def get_table_by_fqn(fqn: str, user: User = Depends(get_current_user)) -> dict:
    scoped_service(user, fqn.split(".")[0] if fqn else None)
    async with OpenMetadataClient() as client:
        try:
            return await client.get_table_by_fqn(fqn)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Table not found")
            raise


@router.get("/tables/{table_id}")
async def get_table(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_get_session),
) -> dict:
    async with OpenMetadataClient() as client:
        try:
            table = await client.get_table(table_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Table not found")
            raise
        fqn = table.get("fullyQualifiedName") or ""
        vmap = await _visibility_map(session, [fqn])
        full, _ = vis.visible_tables([table], vmap, user_context(user))
        if not full:
            raise HTTPException(status_code=403, detail="Access denied for this table")
        return full[0]


@router.get("/tables/{table_id}/lineage")
async def get_table_lineage(table_id: str, user: User = Depends(get_current_user)) -> dict:
    async with OpenMetadataClient() as client:
        try:
            table = await client.get_table(table_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Table not found")
            raise
        fqn = table.get("fullyQualifiedName", "")
        allowed = allowed_services(user)
        if allowed is not None and fqn.split(".")[0] not in allowed:
            raise HTTPException(status_code=403, detail="Access denied for this table")
        try:
            return await client.get_table_lineage(fqn)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {"detail": "No lineage available", "nodes": [], "edges": []}
            raise


@router.get("/stats")
async def metadata_stats(user: User = Depends(get_current_user)) -> dict:
    async with OpenMetadataClient() as client:
        return await client.metadata_stats(allowed_services=allowed_services(user))


@router.get("/services")
async def list_services(
    limit: int = Query(default=100, ge=1, le=1000),
    after: str | None = None,
    user: User = Depends(get_current_user),
) -> dict:
    async with OpenMetadataClient() as client:
        data = await client.list_services(limit=limit, after=after)
        allowed = allowed_services(user)
        if allowed is not None:
            data = {**data, "data": [s for s in data.get("data", []) if s.get("name") in allowed]}
        return data


@router.get("/databases")
async def list_databases(
    service: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    after: str | None = None,
    user: User = Depends(get_current_user),
) -> dict:
    async with OpenMetadataClient() as client:
        return await client.list_databases(
            service=scoped_service(user, service), limit=limit, after=after
        )


@router.get("/schemas")
async def list_schemas(
    database: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    after: str | None = None,
    user: User = Depends(get_current_user),
) -> dict:
    async with OpenMetadataClient() as client:
        return await client.list_schemas(database=database, limit=limit, after=after)


@router.get("/facets")
async def get_facets(user: User = Depends(get_current_user)) -> dict:
    async with OpenMetadataClient() as client:
        facets = await client.get_facets()
        allowed = allowed_services(user)
        if allowed is not None:
            facets = {**facets, "services": [s for s in facets["services"] if s in allowed]}
        return facets


@router.get("/departments/{department}/summary")
async def department_summary(department: str, user: User = Depends(get_current_user)) -> dict:
    """Dept dashboard: counts + top schemas + recent tables for one OM service."""
    allowed = allowed_services(user)
    if allowed is not None and department not in allowed:
        raise HTTPException(status_code=403, detail=f"Access denied for department '{department}'")
    async with OpenMetadataClient() as client:
        page = await client.list_tables_paged(service=department, limit=1000)
        tables = page["data"]
        schemas: dict[str, int] = {}
        for t in tables:
            parts = (t.get("fullyQualifiedName") or "").split(".")
            if len(parts) >= 3:
                key = f"{parts[1]}.{parts[2]}"
                schemas[key] = schemas.get(key, 0) + 1
        return {
            "department": department,
            "tables": len(tables),
            "columns": sum(len(t.get("columns") or []) for t in tables),
            "topSchemas": [
                {"schema": k, "tables": v}
                for k, v in sorted(schemas.items(), key=lambda kv: -kv[1])[:10]
            ],
            "recent": [
                {"id": t.get("id"), "name": t.get("name"), "fullyQualifiedName": t.get("fullyQualifiedName")}
                for t in tables[:10]
            ],
        }
