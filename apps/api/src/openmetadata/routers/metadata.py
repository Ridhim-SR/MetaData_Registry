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

    The visibility sidecar is authoritative: public → anyone with access,
    department → owning department (or admin), restricted → teaser only
    (never full for non-admins), confidential → admin only. Missing or
    invalid classifications normalize to department (non-public). The
    ``service``/``department`` query parameters are Owner filters only and
    never grant access.
    """
    vmap = await _visibility_map(session, [t.get("fullyQualifiedName") or "" for t in tables])
    full, _ = vis.visible_tables(tables, vmap, user_context(user))
    return full


def _is_confidential(session_vmap: dict[str, dict], fqn: str, ctx: dict | None) -> bool:
    visibility = vis.normalize_visibility(session_vmap.get(fqn, {}).get("visibility"))
    return visibility == vis.CONFIDENTIAL and not (ctx and ctx.get("role") == "admin")


async def _visible_dataset_keys(session: AsyncSession, tables: list[dict], user: User) -> set[str]:
    """Dataset FQNs (service.database) with at least one full table for the caller."""
    vmap = await _visibility_map(session, [t.get("fullyQualifiedName") or "" for t in tables])
    ctx = user_context(user)
    keys: set[str] = set()
    full, _ = vis.visible_tables(tables, vmap, ctx)
    for t in full:
        keys.add(vis.dataset_fqn(t.get("fullyQualifiedName") or ""))
    return keys


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
    """Paged envelope {data, paging{total, after}} for scalable Explore UI.

    ``service`` is an Owner filter only. Authorization is applied before
    counts/pagination: only tables the caller may open in full are returned
    and ``paging.total`` reflects the visible subset, never the raw index.
    """
    effective_service = scoped_service(user, service)
    async with OpenMetadataClient() as client:
        page = await client.list_tables_paged(
            search=search, service=effective_service, database=database,
            schema=schema, limit=limit, after=after,
            allowed_services=allowed_services(user),
        )
    filtered = await _visible_full(session, page["data"], user)
    page["data"] = filtered
    # Post-filter total so hidden tables are never counted.
    paging = page.get("paging") or {}
    paging["total"] = len(filtered)
    page["paging"] = paging
    return page


@router.get("/tables/by-fqn")
async def get_table_by_fqn(
    fqn: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_get_session),
) -> dict:
    """Single table by FQN. Enforces the visibility sidecar (no dept pinning).

    ``service`` prefix is not a permission: cross-department discovery is
    allowed, but only tables the caller may open in full are returned.
    Authenticated users without full access receive 403; confidential tables
    are 404 for non-admins so existence is never revealed.
    """
    async with OpenMetadataClient() as client:
        try:
            table = await client.get_table_by_fqn(fqn)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Table not found")
            raise
        real_fqn = table.get("fullyQualifiedName") or fqn
        vmap = await _visibility_map(session, [real_fqn])
        ctx = user_context(user)
        if _is_confidential(vmap, real_fqn, ctx):
            raise HTTPException(status_code=404, detail="Table not found")
        full, _ = vis.visible_tables([table], vmap, ctx)
        if not full:
            raise HTTPException(status_code=403, detail="Access denied for this table")
        return full[0]


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
        ctx = user_context(user)
        if _is_confidential(vmap, fqn, ctx):
            raise HTTPException(status_code=404, detail="Table not found")
        full, _ = vis.visible_tables([table], vmap, ctx)
        if not full:
            raise HTTPException(status_code=403, detail="Access denied for this table")
        return full[0]


@router.get("/tables/{table_id}/lineage")
async def get_table_lineage(
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
        fqn = table.get("fullyQualifiedName", "")
        vmap = await _visibility_map(session, [fqn])
        ctx = user_context(user)
        if _is_confidential(vmap, fqn, ctx):
            raise HTTPException(status_code=404, detail="Table not found")
        full, _ = vis.visible_tables([table], vmap, ctx)
        if not full:
            raise HTTPException(status_code=403, detail="Access denied for this table")
        try:
            return await client.get_table_lineage(fqn)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {"detail": "No lineage available", "nodes": [], "edges": []}
            raise


@router.get("/stats")
async def metadata_stats(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_get_session),
) -> dict:
    """Visibility-aware stats: counts derived only from tables the caller may open."""
    async with OpenMetadataClient() as client:
        raw = await client.metadata_stats(allowed_services=allowed_services(user))
        # Re-compute table-level numbers from the visible subset so hidden
        # tables never leak via counts, byService, or recent lists.
        tables = await client._fetch_all("tables", {"fields": "columns", "limit": 1000})
    visible = await _visible_full(session, tables, user)
    by_service: dict[str, int] = {}
    for t in visible:
        svc = (t.get("fullyQualifiedName") or "").split(".")[0]
        by_service[svc] = by_service.get(svc, 0) + 1
    return {
        "services": raw.get("services"),
        "databases": raw.get("databases"),
        "schemas": raw.get("schemas"),
        "tables": len(visible),
        "columns": sum(len(t.get("columns") or []) for t in visible),
        "byService": [{"service": k, "tables": v} for k, v in sorted(by_service.items())],
        "recent": [
            {"id": t.get("id"), "name": t.get("name"), "fullyQualifiedName": t.get("fullyQualifiedName")}
            for t in visible[:10]
        ],
    }


@router.get("/services")
async def list_services(
    limit: int = Query(default=100, ge=1, le=1000),
    after: str | None = None,
    user: User = Depends(get_current_user),
) -> dict:
    """Department directory (services are public). No department pinning."""
    async with OpenMetadataClient() as client:
        return await client.list_services(limit=limit, after=after)


@router.get("/databases")
async def list_databases(
    service: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    after: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_get_session),
) -> dict:
    """Databases filtered to datasets with at least one table the caller may open.

    ``service`` is an Owner filter only.
    """
    async with OpenMetadataClient() as client:
        data = await client.list_databases(
            service=scoped_service(user, service), limit=limit, after=after
        )
        tables = await client._fetch_all("tables", {"fields": "columns", "limit": 1000})
    visible_keys = await _visible_dataset_keys(session, tables, user)
    items = []
    for d in data.get("data", []):
        fqn = d.get("fullyQualifiedName") or ""
        if fqn in visible_keys:
            items.append(d)
    return {**data, "data": items}


@router.get("/schemas")
async def list_schemas(
    database: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    after: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_get_session),
) -> dict:
    """Schemas filtered to visible datasets (schema is a technical level)."""
    async with OpenMetadataClient() as client:
        data = await client.list_schemas(database=database, limit=limit, after=after)
        tables = await client._fetch_all("tables", {"fields": "columns", "limit": 1000})
    visible_keys = await _visible_dataset_keys(session, tables, user)
    # Schema FQNs look like service.database.schema; keep only those whose
    # parent dataset is visible.
    items = []
    for s in data.get("data", []):
        fqn = s.get("fullyQualifiedName") or ""
        parts = fqn.split(".")
        parent = ".".join(parts[:2]) if len(parts) >= 2 else ""
        if parent in visible_keys:
            items.append(s)
    return {**data, "data": items}


@router.get("/facets")
async def get_facets(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_get_session),
) -> dict:
    """Filter values derived from visible datasets only (never raw OM)."""
    async with OpenMetadataClient() as client:
        facets = await client.get_facets()
        tables = await client._fetch_all("tables", {"fields": "columns", "limit": 1000})
    visible = await _visible_full(session, tables, user)
    visible_services = sorted({(t.get("fullyQualifiedName") or "").split(".")[0] for t in visible if t.get("fullyQualifiedName")})
    visible_dbs = sorted({vis.dataset_fqn(t.get("fullyQualifiedName") or "") for t in visible})
    # Database facet values are bare names; restrict to visible datasets.
    visible_db_names = sorted({k.split(".")[1] for k in visible_dbs if "." in k})
    return {
        "services": [s for s in facets.get("services", []) if s in visible_services] or visible_services,
        "databases": [d for d in facets.get("databases", []) if d in visible_db_names],
        "schemas": facets.get("schemas", []),
    }


@router.get("/departments/{department}/summary")
async def department_summary(
    department: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_get_session),
) -> dict:
    """Dept dashboard: counts + top schemas + recent tables the caller may open.

    Cross-department discovery is allowed; only tables the caller may open in
    full contribute to counts, topSchemas, and recent (no name leaks).
    """
    async with OpenMetadataClient() as client:
        page = await client.list_tables_paged(service=department, limit=1000)
        tables = await _visible_full(session, page["data"], user)
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
