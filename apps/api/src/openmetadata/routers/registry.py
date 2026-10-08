"""Public metadata-registry endpoints.

Frontend → FastAPI → OpenMetadata. These routes are safe for anonymous users:
guest visibility is computed by one shared function
(src.openmetadata.visibility.visible_catalog) and every count is derived
from the exact cards the same viewer sees. FastAPI is the policy
enforcement point — the frontend must never be trusted.

Dataset identity is the OpenMetadata *database* FQN (service.database);
department identity is the OM *service* name. Display names come from the
local department_profile table, never from formatted service IDs.
"""

import time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_session as db_get_session
from database.models import (
    AccessRequest,
    DatasetVisibility,
    TableInfo,
    User,
    Visibility,
)
from src.middleware.auth import get_optional_user, user_context
from src.openmetadata import visibility as vis
from src.openmetadata.client import OpenMetadataClient
from src.openmetadata.schemas.dataset import AccessRequestCreate

router = APIRouter(prefix="/registry", tags=["registry"])

CATALOG_TTL_SECONDS = 60

# Viewer-class -> (fetched_at, {"tables": [...], "databases": [...]})
# Raw OpenMetadata payloads only; the visibility map and profiles stay fresh
# per request so access changes apply immediately while OM polling is cached.
_catalog_cache: dict[str, tuple[float, dict]] = {}


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


def _profiles_from_services(services: list[dict]) -> list[dict]:
    """Department directory from OM services (data engineering owns names).

    display_name/description are the OM values verbatim; the raw service
    name is the fallback (never reformatted). OM has no aliases, contacts,
    or short names, so those stay empty.
    """
    profiles = []
    for s in services or []:
        name = s.get("name") or ""
        if not name:
            continue
        profiles.append(
            {
                "slug": name,
                "name": name,
                "display_name": s.get("displayName") or name,
                "short_name": None,
                "description": s.get("description"),
                "aliases": [],
                "contact_email": None,
                "contact_phone": None,
                "head_name": None,
                "category": None,
            }
        )
    profiles.sort(key=lambda p: (p["display_name"] or "").lower())
    return profiles


async def _catalog_raw(session: AsyncSession, ctx: dict | None) -> dict:
    """Raw OM payloads shared by every endpoint (60s cache per viewer class).

    One tables fetch (with columns, needed for full cards/detail) and one
    light databases fetch per window; visibility maps and profiles are read
    fresh on every request.
    """
    key = vis.viewer_key(ctx)
    now = time.monotonic()
    hit = _catalog_cache.get(key)
    if hit and now - hit[0] < CATALOG_TTL_SECONDS:
        return hit[1]
    async with OpenMetadataClient() as client:
        tables = await client._fetch_all("tables", {"fields": "columns,tags,owners", "limit": 1000})
        databases = await client._fetch_all("databases", {"limit": 1000})
        services = await client._fetch_all("services/databaseServices", {"limit": 100})
    payload = {"tables": tables, "databases": databases, "services": services}
    _catalog_cache[key] = (now, payload)
    return payload


async def _viewer_catalog(session: AsyncSession, ctx: dict | None) -> tuple[list[dict], dict, list[dict], list[dict]]:
    """Cards the viewer sees + fresh vmap + databases + services (single source of truth)."""
    raw = await _catalog_raw(session, ctx)
    vmap = await _visibility_map(session)
    cards = vis.visible_catalog(raw["tables"], raw["databases"], vmap, ctx)
    return cards, vmap, raw["databases"], raw["services"]


def _dept_counts(cards: list[dict]) -> dict[str, dict]:
    """service -> {"datasets": n, "tables": n} from the exact visible cards."""
    counts: dict[str, dict] = {}
    for c in cards:
        entry = counts.setdefault(c["service"], {"datasets": 0, "tables": 0})
        entry["datasets"] += 1
        entry["tables"] += c.get("table_count", 0)
    return counts


def _with_dept_display(items: list[dict], profiles: list[dict]) -> list[dict]:
    """Attach department_display (profile display_name) so the frontend
    never formats raw service names. Falls back to the raw value."""
    disp = {p["slug"]: p["display_name"] for p in profiles}
    for item in items:
        service = item.get("service") or (item.get("dataset") or "").split(".")[0]
        item["department_display"] = disp.get(service, item.get("department"))
    return items


# ---- stats ----

@router.get("/stats")
async def registry_stats(
    session: AsyncSession = Depends(db_get_session),
    user: User | None = Depends(get_optional_user),
) -> dict:
    """Homepage statistics. Every number matches its visible list exactly."""
    ctx = user_context(user)
    cards, _, _, services = await _viewer_catalog(session, ctx)
    profiles = _profiles_from_services(services)
    summary = vis.summarize_cards(cards)
    return {
        "departments": len(profiles),
        "datasets": summary["datasets"],
        "tables": summary["tables"],
    }


# ---- departments ----

@router.get("/departments")
async def list_departments(
    session: AsyncSession = Depends(db_get_session),
    user: User | None = Depends(get_optional_user),
) -> dict:
    """Department directory: all OM services with this viewer's visible counts.

    Services with zero visible datasets still appear (counts of 0).
    """
    ctx = user_context(user)
    cards, _, _, services = await _viewer_catalog(session, ctx)
    counts = _dept_counts(cards)
    profiles = _profiles_from_services(services)
    items = []
    for p in profiles:
        c = counts.get(p["slug"], {"datasets": 0, "tables": 0})
        items.append({**p, "name": p["slug"], "dataset_count": c["datasets"], "table_count": c["tables"]})
    items.sort(key=lambda i: (-i["dataset_count"], (i["display_name"] or "").lower()))
    return {"items": items, "total": len(items)}


@router.get("/departments/{slug}")
async def department_detail(
    slug: str,
    session: AsyncSession = Depends(db_get_session),
    user: User | None = Depends(get_optional_user),
) -> dict:
    """One department (OM service) with this viewer's visible dataset cards."""
    ctx = user_context(user)
    cards, _, _, services = await _viewer_catalog(session, ctx)
    profiles = _profiles_from_services(services)
    row = next((p for p in profiles if p["slug"] == slug), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Department not found")
    mine = _with_dept_display([c for c in cards if c["service"] == slug], profiles)
    profile = {
        **row,
        "dataset_count": len(mine),
        "table_count": sum(c.get("table_count", 0) for c in mine),
    }
    return {"profile": profile, "datasets": mine, "total": len(mine)}


# ---- datasets ----

@router.get("/datasets/public")
async def public_datasets(
    session: AsyncSession = Depends(db_get_session),
    user: User | None = Depends(get_optional_user),
) -> dict:
    """Only public datasets. {items: [], total: 0} (200) when none exist."""
    ctx = user_context(user)
    cards, _, _, services = await _viewer_catalog(session, ctx)
    profiles = _profiles_from_services(services)
    items = [c for c in cards if c["access_level"] == vis.PUBLIC and not c.get("locked")]
    return {"items": _with_dept_display(items, profiles), "total": len(items)}


@router.get("/datasets")
async def list_datasets(
    department: str | None = None,
    search: str | None = None,
    session: AsyncSession = Depends(db_get_session),
    user: User | None = Depends(get_optional_user),
) -> dict:
    """Catalog datasets visible to the caller (full cards + locked teasers).

    Logged-in callers additionally receive table-level restricted teasers
    (historical shape); guests never receive table names of non-public data.
    """
    ctx = user_context(user)
    cards, vmap, _databases, services = await _viewer_catalog(session, ctx)
    profiles = _profiles_from_services(services)
    if department:
        wanted = vis.department_candidates(department) | {department}
        cards = [c for c in cards if c["service"] in wanted]
    if search:
        needle = search.lower()
        cards = [
            c for c in cards
            if needle in (c["name"] or "").lower() or needle in (c["dataset"] or "").lower()
        ]
    teasers: list[dict] = []
    if user is not None:
        raw = await _catalog_raw(session, ctx)
        _full, table_teasers = vis.visible_tables(raw["tables"], vmap, ctx)
        if department:
            wanted = vis.department_candidates(department) | {department}
            table_teasers = [
                t for t in table_teasers
                if (t.get("fullyQualifiedName") or "").split(".")[0] in wanted
            ]
        teasers = table_teasers
    _with_dept_display(cards, profiles)
    return {"items": cards, "teasers": teasers, "total": len(cards)}


def _dataset_exists(raw_tables: list[dict], databases: list[dict], fqn: str) -> bool:
    if any((d.get("fullyQualifiedName") or "") == fqn for d in databases):
        return True
    prefix = fqn + "."
    return any((t.get("fullyQualifiedName") or "").startswith(prefix) for t in raw_tables)


def _dataset_confidential_only(
    raw_tables: list[dict], vmap: dict[str, dict], fqn: str
) -> bool:
    """True when every known member table of the dataset is confidential."""
    prefix = fqn + "."
    members = [t for t in raw_tables if (t.get("fullyQualifiedName") or "").startswith(prefix)]
    if not members:
        return False
    return all(
        vis.normalize_visibility(vmap.get(t.get("fullyQualifiedName") or "", {}).get("visibility"))
        == vis.CONFIDENTIAL
        for t in members
    )


@router.get("/datasets/by-fqn")
async def dataset_by_fqn(
    fqn: str = Query(min_length=1),
    session: AsyncSession = Depends(db_get_session),
    user: User | None = Depends(get_optional_user),
) -> dict:
    """Single dataset (OM database). Teaser-level returns 200 locked.

    Legacy 3-part schema-level FQNs resolve to their parent database.
    Confidential datasets are 404 for everyone except admins. Guests never
    receive 401 here: hidden datasets are either locked (200) or 404.
    """
    ctx = user_context(user)
    key = vis.normalize_dataset_fqn(fqn)
    cards, vmap, databases, services = await _viewer_catalog(session, ctx)
    profiles = _profiles_from_services(services)
    for card in cards:
        if card["dataset"] == key:
            _with_dept_display([card], profiles)
            return card
    # Not visible: confidential (non-admin) -> 404, never admit existence.
    raw = await _catalog_raw(session, ctx)
    if _dataset_confidential_only(raw["tables"], vmap, key) and not (
        ctx and ctx.get("role") == "admin"
    ):
        raise HTTPException(status_code=404, detail="Dataset not found")
    if user is None:
        # Guest: teaser-level datasets are already returned above as locked
        # cards; anything else is indistinguishable from missing.
        raise HTTPException(status_code=404, detail="Dataset not found")
    if _dataset_exists(raw["tables"], databases, key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this dataset.",
        )
    raise HTTPException(status_code=404, detail="Dataset not found")


@router.get("/tables/{table_id}")
async def registry_table(
    table_id: str,
    session: AsyncSession = Depends(db_get_session),
    user: User | None = Depends(get_optional_user),
) -> dict:
    """Single table. Public → anyone; confidential → 404 (non-admin).

    Viewers without full access receive 200 with a locked table summary
    (name, description, column count, columns: []); there is no 403.
    Used by the frontend only to resolve legacy table links to datasets.
    """
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
    visibility = vis.normalize_visibility(vmap.get(fqn, {}).get("visibility"))
    if visibility == vis.CONFIDENTIAL and not (ctx and ctx.get("role") == "admin"):
        raise HTTPException(status_code=404, detail="Table not found")
    service, _, _, _ = vis.split_fqn(fqn)
    owner = vmap.get(fqn, {}).get("department") or service
    annotated = {**table, "access_level": visibility, "department": owner}
    full, _ = vis.visible_tables([table], vmap, ctx)
    if full:
        info = (await table_info_map(session, [fqn])).get(fqn)
        info = info or {
            "api_available": None, "dataset_owner": None, "frequency": None, "timeline": None,
        }
        annotated["info"] = info
        owners = table.get("owners") or []
        first_owner = owners[0] if owners else {}
        annotated["facts"] = {
            "owner": first_owner.get("displayName") or first_owner.get("name"),
            "steward": None,
            "department_contact": None,
            "updated_at": table.get("updatedAt"),
            "frequency": info.get("frequency"),
            "source": None,
        }
        return annotated
    columns = table.get("columns") or []
    return {
        "id": table.get("id"),
        "name": table.get("name"),
        "fullyQualifiedName": fqn,
        "description": table.get("description"),
        "column_count": len(columns),
        "columns": [],
        "locked": True,
        "access_level": visibility,
        "department": owner,
    }


def _csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    if any(ch in text for ch in (',', '"', "\n", "\r")):
        return '"' + text.replace('"', '""') + '"'
    return text


@router.get("/tables/{table_id}/dictionary")
async def table_dictionary(
    table_id: str,
    session: AsyncSession = Depends(db_get_session),
    user: User | None = Depends(get_optional_user),
):
    """Downloadable data dictionary (CSV) for one table — full access only.

    Viewers without full access are refused (403 locked, 404 hidden or
    confidential); the frontend hides the button unless the table is open.
    """
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
    visibility = vis.normalize_visibility(vmap.get(fqn, {}).get("visibility"))
    if visibility == vis.CONFIDENTIAL and not (ctx and ctx.get("role") == "admin"):
        raise HTTPException(status_code=404, detail="Table not found")
    service, _, _, _ = vis.split_fqn(fqn)
    owner = vmap.get(fqn, {}).get("department") or service
    full, _ = vis.visible_tables([table], vmap, ctx)
    if not full:
        # The table exists (fetched above) but the viewer may not open it.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sign in with an authorized account to download this dictionary.",
        )
    lines = ["column_name,data_type,description,tags"]
    for col in table.get("columns") or []:
        tags = ";".join(
            t.get("tagFQN") or t.get("name") or ""
            for t in col.get("tags") or []
        )
        lines.append(",".join([
            _csv_cell(col.get("name")),
            _csv_cell(col.get("dataTypeDisplay") or col.get("dataType")),
            _csv_cell(col.get("description")),
            _csv_cell(tags),
        ]))
    filename = f"{(table.get('name') or 'table')}_data_dictionary.csv"
    return PlainTextResponse(
        "\n".join(lines) + "\n",
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---- search ----

_VALID_SCOPES = ("departments", "datasets", "tables", "columns")


def _profile_text(profile: dict) -> str:
    return " ".join(
        [
            profile.get("display_name") or "",
            profile.get("short_name") or "",
            profile.get("description") or "",
            " ".join(profile.get("aliases") or []),
        ]
    ).lower()


def _dataset_allowed_text(
    card: dict,
    tables_by_dataset: dict[str, list[dict]],
    dept_text: str,
) -> str:
    """Non-column text a dataset may match for viewers without full access.

    Database name/displayName/description, its tables' tags, and the owning
    department's profile text. Never table names, column names, or table
    descriptions.
    """
    parts = [
        card.get("name") or "",
        card.get("database") or "",
        card.get("description") or "",
        dept_text,
    ]
    for t in tables_by_dataset.get(card["dataset"], []):
        for tag in t.get("tags") or []:
            parts.append(tag.get("tagFQN") or tag.get("name") or "")
    return " ".join(parts).lower()


@router.get("/search")
async def registry_search(
    q: str = Query(min_length=1),
    department: str | None = None,
    scope: str | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(db_get_session),
    user: User | None = Depends(get_optional_user),
) -> dict:
    """Grouped registry search: departments, datasets, tables, columns.

    The OpenMetadata search runs first; the visibility filter applies after
    it and totals are re-computed post-filter. For viewers without full
    access, OM hits whose only match is structural/column text are
    discarded, and table/column names of non-public datasets are never
    returned. `scope` limits the groups returned.
    """
    ctx = user_context(user)
    needle = q.strip().lower()
    wanted_scopes = (
        {s.strip().lower() for s in scope.split(",") if s.strip().lower() in _VALID_SCOPES}
        if scope
        else set(_VALID_SCOPES)
    )
    if scope and not wanted_scopes:
        wanted_scopes = set(_VALID_SCOPES)

    cards, vmap, databases, services = await _viewer_catalog(session, ctx)
    profiles = _profiles_from_services(services)
    raw = await _catalog_raw(session, ctx)
    tables_by_dataset: dict[str, list[dict]] = {}
    for t in raw["tables"]:
        tables_by_dataset.setdefault(vis.dataset_fqn(t.get("fullyQualifiedName") or ""), []).append(t)
    dept_text_by_service = {p["slug"]: _profile_text(p) for p in profiles}

    async with OpenMetadataClient() as client:
        try:
            result = await client.search_tables(query=q, limit=size, page=page)
            candidates = result.get("data", [])
            fallback = False
        except Exception:
            page_data = await client.list_tables_paged(limit=1000)
            candidates = [t for t in page_data["data"] if _matches(t, needle)]
            fallback = True
    if department:
        wanted = vis.department_candidates(department) | {department}
        candidates = [t for t in candidates if (t.get("fullyQualifiedName") or "").split(".")[0] in wanted]

    cards_by_dataset = {c["dataset"]: c for c in cards}
    kept_datasets: dict[str, dict] = {}
    kept_tables: list[dict] = []
    for t in candidates:
        fqn = t.get("fullyQualifiedName") or ""
        key = vis.dataset_fqn(fqn)
        card = cards_by_dataset.get(key)
        if card is None:
            continue  # hidden (confidential or out of policy) for this viewer
        service = key.split(".")[0]
        if not card.get("locked"):
            kept_datasets[key] = card
            # Per-table gate: table/column names are only exposed for tables
            # the viewer may open in full (never for non-public data).
            meta = vmap.get(fqn, {})
            owner = meta.get("department") or service
            if vis.table_decision(vis.normalize_visibility(meta.get("visibility")), owner, ctx) == "full":
                kept_tables.append(t)
            continue
        if user is not None:
            # Logged-in historical behavior: non-public OM hits still surface
            # the dataset teaser (table teasers unchanged elsewhere). Tables
            # of locked datasets enter the strict name/description gate below.
            kept_datasets[key] = card
            kept_tables.append(t)
            continue
        # Guest + non-public: keep only on a non-column match.
        allowed = _dataset_allowed_text(card, tables_by_dataset, dept_text_by_service.get(service, ""))
        if needle and needle in allowed:
            kept_datasets[key] = card
        # else: only structural/column text matched -> discard

    dataset_items = [kept_datasets[k] for k in sorted(kept_datasets)]
    if department:
        wanted = vis.department_candidates(department) | {department}
        dataset_items = [c for c in dataset_items if c["service"] in wanted]

    table_items: list[dict] = []
    column_items: list[dict] = []
    for t in kept_tables:
        fqn = t.get("fullyQualifiedName") or ""
        key = vis.dataset_fqn(fqn)
        card = cards_by_dataset.get(key)
        if card is None:
            continue
        locked = bool(card.get("locked"))
        name_hit = bool(needle) and needle in " ".join(
            [t.get("name") or "", t.get("displayName") or ""]
        ).lower()
        desc_hit = bool(needle) and needle in (t.get("description") or "").lower()
        if locked:
            # Viewers without full access: only name/description matches are
            # shown; column-only matches stay hidden, as do column names.
            if not (name_hit or desc_hit):
                continue
            matched_in = (["name"] if name_hit else []) + (["description"] if desc_hit else [])
            table_items.append(
                {
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "fullyQualifiedName": fqn,
                    "description": t.get("description"),
                    "department": card.get("department"),
                    "dataset": key,
                    "matched_in": matched_in,
                    "matched_columns": [],
                    "tags": [],
                    "updated_at": None,
                }
            )
            continue
        col_hits = [
            col.get("name")
            for col in t.get("columns") or []
            if needle and needle in (col.get("name") or "").lower()
        ]
        matched_in = (
            (["name"] if name_hit else [])
            + (["description"] if desc_hit else [])
            + (["column"] if col_hits else [])
        )
        table_items.append(
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "fullyQualifiedName": fqn,
                "description": t.get("description"),
                "department": card.get("department"),
                "dataset": key,
                "matched_in": matched_in,
                "matched_columns": col_hits,
                "tags": [
                    tag.get("tagFQN") or tag.get("name")
                    for tag in t.get("tags") or []
                    if tag.get("tagFQN") or tag.get("name")
                ],
                "updated_at": t.get("updatedAt"),
            }
        )
        for col_name in col_hits:
            col = next(
                (c for c in t.get("columns") or [] if c.get("name") == col_name), {}
            )
            column_items.append(
                {
                    "name": col_name,
                    "dataType": col.get("dataTypeDisplay") or col.get("dataType"),
                    "table": t.get("name"),
                    "dataset": key,
                }
            )

    dept_items = [p for p in profiles if needle in _profile_text(p)] if needle else []
    if department:
        dept_items = [p for p in dept_items if p["slug"] == department]

    groups = {
        "departments": {"items": dept_items, "total": len(dept_items)},
        "datasets": {"items": dataset_items, "total": len(dataset_items)},
        "tables": {"items": table_items, "total": len(table_items)},
        "columns": {"items": column_items, "total": len(column_items)},
    }
    _with_dept_display(dataset_items, profiles)
    _with_dept_display(table_items, profiles)
    for name in _VALID_SCOPES:
        if name not in wanted_scopes:
            groups[name] = {"items": [], "total": 0}
    total = sum(groups[n]["total"] for n in _VALID_SCOPES)
    # Back-compat flat fields for existing clients.
    return {
        "departments": groups["departments"],
        "datasets": groups["datasets"],
        "tables": groups["tables"],
        "columns": groups["columns"],
        "data": dataset_items,
        "teasers": [],
        "total": total,
        "page": page,
        "fallback": fallback,
    }


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
