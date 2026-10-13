"""Pure visibility helpers for the metadata registry.

No database, OpenMetadata, or FastAPI imports here so the policy logic can be
unit-tested in isolation. FastAPI remains the policy enforcement point; these
helpers only compute decisions from already-fetched data.

Dataset identity is the OpenMetadata *database* FQN (service.database).
Department identity is the OM *service* name. Schema is a technical level
and is never exposed by these helpers.
"""

PUBLIC = "public"
DEPARTMENT = "department"
RESTRICTED = "restricted"
CONFIDENTIAL = "confidential"

VALID_VISIBILITIES = (PUBLIC, DEPARTMENT, RESTRICTED, CONFIDENTIAL)

# Most-restrictive-wins ranking for dataset cards.
_RANK = {PUBLIC: 0, DEPARTMENT: 1, RESTRICTED: 2, CONFIDENTIAL: 3}


def normalize_visibility(raw: str | None) -> str:
    """Normalize a visibility value; unknown/missing defaults to department."""
    value = (raw or "").strip().lower()
    return value if value in VALID_VISIBILITIES else DEPARTMENT


def split_fqn(fqn: str) -> tuple[str, str, str, str]:
    """Split an OM table FQN into (service, database, schema, table)."""
    parts = (fqn or "").split(".")
    parts += [""] * (4 - len(parts))
    return parts[0], parts[1], parts[2], parts[3]


def dataset_fqn(table_fqn: str) -> str:
    """Dataset identity: the OM database FQN (service.database)."""
    service, database, _, _ = split_fqn(table_fqn)
    return ".".join(p for p in (service, database) if p)


def normalize_dataset_fqn(fqn: str) -> str:
    """Resolve a dataset FQN to database level.

    Accepts the current 2-part form (service.database) and legacy 3-part
    schema-level URLs (service.database.schema), which resolve to their
    parent database so old bookmarks keep working.
    """
    parts = [p for p in (fqn or "").split(".") if p]
    return ".".join(parts[:2])


def department_candidates(department: str | None) -> set[str]:
    """Service-name candidates for a user department (mirrors auth scoping)."""
    if not department or not department.strip():
        return set()
    dept = department.strip()
    return {dept, f"gov_{dept}", dept.replace("gov_", "")}


def _is_admin(user: dict | None) -> bool:
    return bool(user) and user.get("role") == "admin"


def table_decision(visibility: str, owner_department: str | None, user: dict | None) -> str:
    """Per-table decision for a viewer: "full", "teaser", or "hidden".

    Guest (user is None):
      public -> full (columns included).
      department/restricted (or unclassified, which defaults to department)
        -> teaser (counted, never named).
      confidential -> hidden (never listed, searched, counted, or detailed).
    Logged-in non-admin without access: department and restricted both
      teaser (table names, no columns); only confidential is hidden.
    Admins: full everywhere.
    """
    visibility = normalize_visibility(visibility)
    if visibility == CONFIDENTIAL:
        return "full" if _is_admin(user) else "hidden"
    if visibility == PUBLIC:
        return "full"
    if user is None:
        return "teaser"
    if _is_admin(user):
        return "full"
    if visibility == DEPARTMENT:
        user_services = department_candidates(user.get("department"))
        owner_services = department_candidates(owner_department)
        if user_services & owner_services:
            return "full"
        return "teaser"  # no access: teaser (names, no columns), not hidden
    return "teaser"  # restricted: teaser only, never full for non-admins


def can_view_full(visibility: str, owner_department: str | None, user: dict | None) -> bool:
    """Whether the caller may see full table metadata (columns included)."""
    return table_decision(visibility, owner_department, user) == "full"


def viewer_key(user: dict | None) -> str:
    """Cache key class for a viewer: guest, admin, or role+department."""
    if user is None:
        return "guest"
    if user.get("role") == "admin":
        return "admin"
    return f"user:{(user.get('department') or '').strip().lower()}"


def visible_tables(
    tables: list[dict],
    visibility_by_fqn: dict[str, dict],
    user: dict | None,
) -> tuple[list[dict], list[dict]]:
    """Partition OM table dicts into (full, teasers) for the caller.

    visibility_by_fqn maps table FQN -> {"visibility": str, "department": str|None}.
    Missing entries default to department visibility owned by the FQN service.
    Tables the caller may not open are returned as teasers carrying table
    names but no columns (never for guests). Anonymous callers only receive
    public tables. Confidential tables are hidden from everyone except admins.
    """
    full: list[dict] = []
    teasers: list[dict] = []
    for table in tables:
        fqn = table.get("fullyQualifiedName") or ""
        meta = visibility_by_fqn.get(fqn, {})
        visibility = normalize_visibility(meta.get("visibility"))
        service, _, _, _ = split_fqn(fqn)
        owner = meta.get("department") or service
        decision = table_decision(visibility, owner, user)
        if decision == "full":
            full.append({**table, "access_level": visibility, "department": owner})
        elif decision == "teaser" and user is not None:
            teaser = {k: table.get(k) for k in ("id", "name", "fullyQualifiedName", "description")}
            teaser["columns"] = []
            teaser["access_level"] = visibility
            teaser["department"] = owner
            teaser["restricted"] = visibility == RESTRICTED
            teasers.append(teaser)
    return full, teasers


def _database_info(databases: list[dict], service: str, database: str) -> dict:
    """Display metadata for one OM database (name/displayName/description)."""
    for db in databases or []:
        db_fqn = db.get("fullyQualifiedName") or ""
        svc, name, _, _ = split_fqn(db_fqn + ".x")
        if svc == service and name == database:
            return {
                "name": db.get("displayName") or db.get("name") or database,
                "description": db.get("description"),
            }
    return {"name": database, "description": None}


def group_datasets(
    tables: list[dict],
    visibility_by_fqn: dict[str, dict],
    databases: list[dict] | None = None,
) -> list[dict]:
    """Group table dicts into dataset cards keyed by database FQN.

    Dataset visibility is the most restrictive among its tables
    (confidential > restricted > department > public). Confidential tables
    are SKIPPED (they must never leak into cards or counts for non-admins);
    callers pre-filter them via table_decision().
    """
    groups: dict[str, dict] = {}
    for table in tables:
        fqn = table.get("fullyQualifiedName") or ""
        key = dataset_fqn(fqn)
        if not key:
            continue
        meta = visibility_by_fqn.get(fqn, {})
        visibility = normalize_visibility(meta.get("visibility"))
        service, database, _, _ = split_fqn(fqn)
        info = _database_info(databases or [], service, database)
        group = groups.setdefault(
            key,
            {
                "dataset": key,
                "service": service,
                "database": database,
                "name": info["name"],
                "description": info["description"],
                "tables": [],
                "table_count": 0,
                "access_level": PUBLIC,
                "department": meta.get("department") or service,
            },
        )
        group["tables"].append(table)
        group["table_count"] += 1
        if _RANK[visibility] > _RANK[group["access_level"]]:
            group["access_level"] = visibility
    return sorted(groups.values(), key=lambda g: g["dataset"])


def visible_catalog(
    tables: list[dict],
    databases: list[dict],
    visibility_by_fqn: dict[str, dict],
    user: dict | None,
) -> list[dict]:
    """The single shared catalog computation for every registry endpoint.

    Departments and datasets (cards) are visible to everyone, including
    anonymous viewers, as FULL or locked TEASER cards ("locked": True, no
    table names, column names, owners, or lineage). Tables/columns require
    sign-in: anonymous viewers never receive table names or column details
    for non-public data (see visible_tables + table endpoints which return
    401 for anonymous table access). Missing or invalid visibility
    classifications normalize to department (non-public). Confidential
    content is excluded for non-admins. Counts are always len()/sum() over
    these exact cards, so every count equals its matching list.
    """
    per_dataset: dict[str, dict] = {}
    for table in tables:
        fqn = table.get("fullyQualifiedName") or ""
        key = dataset_fqn(fqn)
        if not key:
            continue
        meta = visibility_by_fqn.get(fqn, {})
        visibility = normalize_visibility(meta.get("visibility"))
        service, database, _, _ = split_fqn(fqn)
        owner = meta.get("department") or service
        decision = table_decision(visibility, owner, user)
        if decision == "hidden":
            continue
        entry = per_dataset.setdefault(
            key, {"service": service, "database": database, "owner": owner, "full": [], "teasers": 0, "level": PUBLIC}
        )
        if decision == "full":
            entry["full"].append({**table, "access_level": visibility, "department": owner})
        else:
            entry["teasers"] += 1
        if _RANK[visibility] > _RANK[entry["level"]]:
            entry["level"] = visibility

    cards: list[dict] = []
    for key in sorted(per_dataset):
        entry = per_dataset[key]
        info = _database_info(databases or [], entry["service"], entry["database"])
        table_count = len(entry["full"]) + entry["teasers"]
        if entry["full"]:
            slim = [
                {
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "fullyQualifiedName": t.get("fullyQualifiedName"),
                    "description": t.get("description"),
                    "columns": t.get("columns") or [],
                }
                for t in entry["full"]
            ]
            tag_set: list[str] = []
            for t in entry["full"]:
                for tag in t.get("tags") or []:
                    label = tag.get("tagFQN") or tag.get("name")
                    if label and label not in tag_set:
                        tag_set.append(label)
            updated = [t.get("updatedAt") for t in entry["full"] if t.get("updatedAt")]
            cards.append(
                {
                    "dataset": key,
                    "service": entry["service"],
                    "database": entry["database"],
                    "name": info["name"],
                    "description": info["description"],
                    "department": entry["owner"],
                    "table_count": table_count,
                    "access_level": entry["level"],
                    "locked": False,
                    "tables": slim,
                    "tags": tag_set,
                    "updated_at": max(updated) if updated else None,
                }
            )
        else:
            cards.append(
                {
                    "dataset": key,
                    "service": entry["service"],
                    "database": entry["database"],
                    "name": info["name"],
                    "description": info["description"],
                    "department": entry["owner"],
                    "table_count": table_count,
                    "access_level": entry["level"],
                    "locked": True,
                    "tags": [],
                    "updated_at": None,
                }
            )
    return cards


def summarize_cards(cards: list[dict]) -> dict:
    """Counts derived from the exact cards a viewer sees (never raw OM)."""
    return {
        "datasets": len(cards),
        "tables": sum(c.get("table_count", 0) for c in cards),
    }
