"""Pure visibility helpers for the metadata registry.

No database, OpenMetadata, or FastAPI imports here so the policy logic can be
unit-tested in isolation. FastAPI remains the policy enforcement point; these
helpers only compute decisions from already-fetched data.
"""

PUBLIC = "public"
DEPARTMENT = "department"
RESTRICTED = "restricted"

VALID_VISIBILITIES = (PUBLIC, DEPARTMENT, RESTRICTED)


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
    """Dataset identity: the OM schema FQN (service.database.schema)."""
    service, database, schema, _ = split_fqn(table_fqn)
    return ".".join(p for p in (service, database, schema) if p)


def department_candidates(department: str | None) -> set[str]:
    """Service-name candidates for a user department (mirrors auth scoping)."""
    if not department or not department.strip():
        return set()
    dept = department.strip()
    return {dept, f"gov_{dept}", dept.replace("gov_", "")}


def can_view_full(visibility: str, owner_department: str | None, user: dict | None) -> bool:
    """Whether the caller may see full table metadata (columns included)."""
    visibility = normalize_visibility(visibility)
    if visibility == PUBLIC:
        return True
    if user is None:
        return False
    if user.get("role") == "admin":
        return True
    if visibility == DEPARTMENT:
        user_services = department_candidates(user.get("department"))
        owner_services = department_candidates(owner_department)
        return bool(user_services & owner_services)
    return False  # restricted: teaser only, never full for non-admins


def visible_tables(
    tables: list[dict],
    visibility_by_fqn: dict[str, dict],
    user: dict | None,
) -> tuple[list[dict], list[dict]]:
    """Partition OM table dicts into (full, teasers) for the caller.

    visibility_by_fqn maps table FQN -> {"visibility": str, "department": str|None}.
    Missing entries default to department visibility owned by the FQN service.
    Restricted tables the caller may not open are returned as teasers with
    columns stripped. Anonymous callers only receive public tables.
    """
    full: list[dict] = []
    teasers: list[dict] = []
    for table in tables:
        fqn = table.get("fullyQualifiedName") or ""
        meta = visibility_by_fqn.get(fqn, {})
        visibility = normalize_visibility(meta.get("visibility"))
        service, _, _, _ = split_fqn(fqn)
        owner = meta.get("department") or service
        if can_view_full(visibility, owner, user):
            full.append({**table, "access_level": visibility, "department": owner})
        elif user is not None and visibility == RESTRICTED:
            teaser = {k: table.get(k) for k in ("id", "name", "fullyQualifiedName", "description")}
            teaser["columns"] = []
            teaser["access_level"] = RESTRICTED
            teaser["department"] = owner
            teaser["restricted"] = True
            teasers.append(teaser)
    return full, teasers


def group_datasets(tables: list[dict], visibility_by_fqn: dict[str, dict]) -> list[dict]:
    """Group table dicts into dataset cards keyed by schema FQN.

    Dataset visibility is the most restrictive among its tables
    (restricted > department > public).
    """
    rank = {PUBLIC: 0, DEPARTMENT: 1, RESTRICTED: 2}
    groups: dict[str, dict] = {}
    for table in tables:
        fqn = table.get("fullyQualifiedName") or ""
        key = dataset_fqn(fqn)
        if not key:
            continue
        meta = visibility_by_fqn.get(fqn, {})
        visibility = normalize_visibility(meta.get("visibility"))
        service, database, schema, _ = split_fqn(fqn)
        group = groups.setdefault(
            key,
            {
                "dataset": key,
                "service": service,
                "database": database,
                "schema": schema,
                "name": schema,
                "tables": [],
                "table_count": 0,
                "access_level": PUBLIC,
                "department": meta.get("department") or service,
            },
        )
        group["tables"].append(table)
        group["table_count"] += 1
        if rank[visibility] > rank[group["access_level"]]:
            group["access_level"] = visibility
    return sorted(groups.values(), key=lambda g: g["dataset"])
