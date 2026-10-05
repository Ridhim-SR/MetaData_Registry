"""Public metadata-registry endpoints.

Frontend → FastAPI → OpenMetadata. These routes are safe for anonymous users:
they only ever expose public metadata in full; department data requires a
valid token and restricted data is returned as a teaser at most. FastAPI is
the policy enforcement point — the frontend must never be trusted.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_session as db_get_session
from database.models import AccessRequest, DatasetVisibility, TableInfo, User, Visibility
from src.middleware.auth import get_optional_user, user_context
from src.openmetadata import visibility as vis
from src.openmetadata.client import OpenMetadataClient
from src.openmetadata.schemas.dataset import AccessRequestCreate

router = APIRouter(prefix="/registry", tags=["registry"])


# ---- sidecar helpers ----

async def _visibility_map(session: AsyncSession, fqns: list[str] | None = None) -> dict[str, dict]:
    """FQN -> {"visibility": str, "department": str|None} from the sidecar table."""
    stmt = select(DatasetVisibility)
    if fqns is not None:
        if not fqns:
            return {}
        stmt = stmt.where(DatasetVisibility.fqn.in_(fqns))
    rows = (await session.execute(stmt)).scalars().all()
    return {
        r.fqn: {"visibility": r.visibility.value, "department": r.department} for r in rows
    }


async def _fetch_tables(client: OpenMetadataClient) -> list[dict]:
    """All OM tables (bounded paging) for registry aggregation."""
    return await client._fetch_all("tables", {"fields": "columns,tags,owners", "limit": 1000})


def _visibility_of(vmap: dict[str, dict], table: dict) -> str:
    return vis.normalize_visibility(vmap.get(table.get("fullyQualifiedName") or "", {}).get("visibility"))


def _annotate(table: dict, vmap: dict[str, dict]) -> dict:
    fqn = table.get("fullyQualifiedName") or ""
    meta = vmap.get(fqn, {})
    service = fqn.split(".")[0] if fqn else ""
    return {
        **table,
        "access_level": vis.normalize_visibility(meta.get("visibility")),
        "department": meta.get("department") or service,
    }


# ---- stats ----

@router.get("/stats")
async def registry_stats(session: AsyncSession = Depends(db_get_session)) -> dict:
    """Homepage statistics. Never hard-coded; zero values are valid."""
    async with OpenMetadataClient() as client:
        services = await client._fetch_all("services/databaseServices", {"limit": 100})
        schemas = await client._fetch_all("databaseSchemas", {"limit": 1000})
        tables = await _fetch_tables(client)
    vmap = await _visibility_map(session)
    public_tables = sum(
        1 for t in tables if _visibility_of(vmap, t) == vis.PUBLIC
    )
    return {
        "departments": len(services),
        "datasets": len(schemas),
        "tables": len(tables),
        "public_tables": public_tables,
    }


# ---- departments ----

@router.get("/departments")
async def list_departments(session: AsyncSession = Depends(db_get_session)) -> dict:
    """Department list with live counts. Empty list is a valid response."""
    async with OpenMetadataClient() as client:
        services = await client._fetch_all("services/databaseServices", {"limit": 100})
        tables = await _fetch_tables(client)
    counts: dict[str, dict] = {}
    for t in tables:
        svc = (t.get("fullyQualifiedName") or "").split(".")[0]
        if not svc:
            continue
        entry = counts.setdefault(svc, {"tables": 0, "schemas": set()})
        entry["tables"] += 1
        parts = (t.get("fullyQualifiedName") or "").split(".")
        if len(parts) >= 3:
            entry["schemas"].add(".".join(parts[:3]))
    items = []
    for s in services:
        if not s.get("name"):
            continue
        entry = counts.get(s.get("name"), {"tables": 0, "schemas": set()})
        items.append(
            {
                "name": s.get("name"),
                "description": s.get("description"),
                "dataset_count": len(entry["schemas"]),
                "table_count": entry["tables"],
            }
        )
    # Services seen only via tables (edge case) still appear.
    for svc in sorted(counts):
        if not any(i["name"] == svc for i in items):
            items.append({
                "name": svc, "description": None,
                "dataset_count": len(counts[svc]["schemas"]), "table_count": counts[svc]["tables"],
            })
    return {"items": sorted(items, key=lambda i: i["name"] or ""), "total": len(items)}


# ---- datasets ----

def _dataset_cards(tables: list[dict], vmap: dict[str, dict]) -> list[dict]:
    """Group annotated tables into dataset cards (one per OM schema)."""
    cards = vis.group_datasets(tables, vmap)
    out = []
    for card in cards:
        card_tables = [
            {
                "id": t.get("id"), "name": t.get("name"),
                "fullyQualifiedName": t.get("fullyQualifiedName"),
                "description": t.get("description"),
                "columns": t.get("columns") or [],
            }
            for t in card.pop("tables")
        ]
        out.append({**card, "tables": card_tables})
    return out


@router.get("/datasets/public")
async def public_datasets(session: AsyncSession = Depends(db_get_session)) -> dict:
    """Only public datasets. {items: [], total: 0} (200) when none exist."""
    async with OpenMetadataClient() as client:
        tables = await _fetch_tables(client)
    vmap = await _visibility_map(session)
    public = [_annotate(t, vmap) for t in tables if _visibility_of(vmap, t) == vis.PUBLIC]
    items = _dataset_cards(public, vmap)
    return {"items": items, "total": len(items)}


@router.get("/datasets")
async def list_datasets(
    department: str | None = None,
    search: str | None = None,
    session: AsyncSession = Depends(db_get_session),
    user: User | None = Depends(get_optional_user),
) -> dict:
    """Catalog datasets visible to the caller (full + restricted teasers)."""
    ctx = user_context(user)
    async with OpenMetadataClient() as client:
        tables = await _fetch_tables(client)
    vmap = await _visibility_map(session)
    full, teasers = vis.visible_tables(tables, vmap, ctx)
    cards = _dataset_cards(full, vmap)
    if department:
        wanted = vis.department_candidates(department) | {department}
        cards = [c for c in cards if c["service"] in wanted or c["department"] in wanted]
    if search:
        needle = search.lower()
        cards = [
            c for c in cards
            if needle in (c["name"] or "").lower() or needle in (c["dataset"] or "").lower()
        ]
        teasers = [
            t for t in teasers
            if needle in (t.get("name") or "").lower()
            or needle in (t.get("fullyQualifiedName") or "").lower()
        ]
    return {"items": cards, "teasers": teasers, "total": len(cards)}


@router.get("/datasets/by-fqn")
async def dataset_by_fqn(
    fqn: str = Query(min_length=1),
    session: AsyncSession = Depends(db_get_session),
    user: User | None = Depends(get_optional_user),
) -> dict:
    """Single dataset (OM schema) with its tables. 401 anon/non-public, 403 denied."""
    ctx = user_context(user)
    async with OpenMetadataClient() as client:
        tables = await _fetch_tables(client)
    vmap = await _visibility_map(session)
    wanted = [t for t in tables if vis.dataset_fqn(t.get("fullyQualifiedName") or "") == fqn]
    if not wanted:
        raise HTTPException(status_code=404, detail="Dataset not found")
    full, _ = vis.visible_tables(wanted, vmap, ctx)
    if not full:
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sign in to view this dataset.",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this dataset.",
        )
    cards = _dataset_cards([_annotate(t, vmap) for t in full], vmap)
    return cards[0] if cards else {"dataset": fqn, "tables": [], "table_count": 0}


@router.get("/tables/{table_id}")
async def registry_table(
    table_id: str,
    session: AsyncSession = Depends(db_get_session),
    user: User | None = Depends(get_optional_user),
) -> dict:
    """Single table. Public → anyone; otherwise 401 (anon) / 403 (denied)."""
    ctx = user_context(user)
    async with OpenMetadataClient() as client:
        try:
            table = await client.get_table(table_id)
        except Exception as exc:
            message = str(exc).lower()
            if "404" in message or "not found" in message:
                raise HTTPException(status_code=404, detail="Table not found")
            raise
    fqn = table.get("fullyQualifiedName") or ""
    rows = (await session.execute(
        select(DatasetVisibility).where(DatasetVisibility.fqn == fqn)
    )).scalars().all()
    vmap = {r.fqn: {"visibility": r.visibility.value, "department": r.department} for r in rows}
    full, _ = vis.visible_tables([table], vmap, ctx)
    if not full:
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This metadata requires sign-in.",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this metadata.",
        )
    annotated = _annotate(full[0], vmap)
    info = (await table_info_map(session, [fqn])).get(fqn)
    annotated["info"] = info or {
        "api_available": None, "dataset_owner": None, "frequency": None, "timeline": None,
    }
    return annotated


# ---- search ----

@router.get("/search")
async def registry_search(
    q: str = Query(min_length=1),
    department: str | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(db_get_session),
    user: User | None = Depends(get_optional_user),
) -> dict:
    """Registry search with access filtering. Anonymous callers see public only."""
    ctx = user_context(user)
    async with OpenMetadataClient() as client:
        try:
            result = await client.search_tables(query=q, limit=size, page=page)
            candidates = result.get("data", [])
            fallback = False
        except Exception:
            page_data = await client.list_tables_paged(limit=1000)
            candidates = [t for t in page_data["data"] if _matches(t, q.lower())]
            fallback = True
    if department:
        wanted = vis.department_candidates(department) | {department}
        candidates = [t for t in candidates if (t.get("fullyQualifiedName") or "").split(".")[0] in wanted]
    vmap = await _visibility_map(session, [t.get("fullyQualifiedName") or "" for t in candidates])
    full, teasers = vis.visible_tables(candidates, vmap, ctx)
    annotated = [_annotate(t, vmap) for t in full]
    # Recompute after department + visibility filtering: the OM search total
    # counts unfiltered hits, which contradicts data/teasers once policy drops
    # tables the caller may not see (e.g. department tables for outsiders).
    total = len(annotated) + len(teasers)
    return {"data": annotated, "teasers": teasers, "total": total, "page": page, "fallback": fallback}


def _matches(table: dict, needle: str) -> bool:
    haystacks = [
        (table.get("name") or "").lower(),
        (table.get("fullyQualifiedName") or "").lower(),
        (table.get("description") or "").lower(),
    ]
    if any(needle in h for h in haystacks):
        return True
    return any(
        needle in (c.get("name") or "").lower() or needle in (c.get("description") or "").lower()
        for c in table.get("columns") or []
    )


# ---- access requests (simple demo flow) ----

@router.post("/access-requests", status_code=201)
async def create_access_request(
    payload: AccessRequestCreate,
    session: AsyncSession = Depends(db_get_session),
    user: User | None = Depends(get_optional_user),
) -> dict:
    record = AccessRequest(
        fqn=payload.fqn,
        user_id=user.id if user else None,
        requester_email=user.email if user else None,
        note=payload.note,
        status="pending",
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return {"id": record.id, "fqn": record.fqn, "status": record.status}


async def upsert_table_visibility(
    session: AsyncSession,
    *,
    fqn: str,
    visibility: str,
    department: str | None,
) -> None:
    """Record access metadata after a successful OM table write."""
    service, database, schema, table = vis.split_fqn(fqn)
    existing = (
        await session.execute(select(DatasetVisibility).where(DatasetVisibility.fqn == fqn))
    ).scalar_one_or_none()
    if existing:
        existing.visibility = Visibility(vis.normalize_visibility(visibility))
        existing.department = department or service
        existing.service = service
        existing.database_name = database
        existing.schema_name = schema
        existing.table_name = table
    else:
        session.add(
            DatasetVisibility(
                fqn=fqn,
                service=service,
                database_name=database,
                schema_name=schema,
                table_name=table,
                visibility=Visibility(vis.normalize_visibility(visibility)),
                department=department or service,
            )
        )
    await session.commit()


async def upsert_table_info(
    session: AsyncSession,
    *,
    fqn: str,
    api_available: bool | None,
    dataset_owner: str | None,
    frequency: str | None,
    timeline: str | None,
) -> None:
    """Record dataset information tags after a successful OM table write."""
    existing = (
        await session.execute(select(TableInfo).where(TableInfo.fqn == fqn))
    ).scalar_one_or_none()
    if existing:
        existing.api_available = api_available
        existing.dataset_owner = dataset_owner
        existing.frequency = frequency
        existing.timeline = timeline
    else:
        session.add(
            TableInfo(
                fqn=fqn,
                api_available=api_available,
                dataset_owner=dataset_owner,
                frequency=frequency,
                timeline=timeline,
            )
        )
    await session.commit()


async def table_info_map(session: AsyncSession, fqns: list[str] | None = None) -> dict[str, dict]:
    """FQN -> {"api_available": bool|None, ...} from the sidecar table."""
    stmt = select(TableInfo)
    if fqns is not None:
        if not fqns:
            return {}
        stmt = stmt.where(TableInfo.fqn.in_(fqns))
    rows = (await session.execute(stmt)).scalars().all()
    return {
        r.fqn: {
            "api_available": r.api_available,
            "dataset_owner": r.dataset_owner,
            "frequency": r.frequency,
            "timeline": r.timeline,
        }
        for r in rows
    }


__all__ = ["router", "upsert_table_visibility", "upsert_table_info", "table_info_map"]
