"""Table/dataset fact resolution for the metadata registry.

Pure helpers (no database, OpenMetadata, or FastAPI imports) so the
inheritance rules can be unit-tested in isolation.

Facts come from two levels, each with two sources:
- table level: the OM table (owners, updatedAt, classification tags and
  custom properties in `extension`) plus its TableInfo sidecar row;
- dataset level: the OM database (owners, classification tags and custom
  properties in `extension`) plus its DatasetInfo sidecar row.

OpenMetadata wins over the sidecar at each level; table values win over
dataset values. Every inheritable fact reports where its value came from
("table" | "dataset" | None) so the UI can tell overrides from defaults.
"""

from datetime import datetime, timezone

# OM custom property names (Custom Properties panel on databases/tables).
EXT_API_AVAILABLE = "apiAvailable"
EXT_OWNER = "datasetOwner"
EXT_STEWARD = "datasetSteward"
EXT_FREQUENCY = "frequency"
EXT_TIMELINE = "timeline"
EXT_SCHEMA_SOURCE = "schemaSource"

# Classification tag namespaces, in priority order. DataSensitivity holds
# the CAT-1..CAT-4 levels; MDSF is the older Public/Internal/... scheme.
CLASSIFICATION_PREFIXES = ("DataSensitivity.", "MDSF.")

# Most-restrictive-wins ranking (aliases match the frontend normalizer).
_CLASSIFICATION_RANK = {
    "public": 0, "internal": 1, "restricted": 2, "sensitive": 3,
    "cat-1": 0, "cat-2": 1, "cat-3": 2, "cat-4": 3,
}
_CLASSIFICATION_ALIASES = {
    "open": "public",
    "pii": "sensitive",
    "confidential": "sensitive",
    "secret": "sensitive",
    "personal": "sensitive",
}


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _format_epoch(value: object) -> str | None:
    """OM timestamps are epoch milliseconds; render them as a date."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return _text(value)
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).strftime("%d %b %Y")
    except (OverflowError, OSError, ValueError):
        return str(value)


def ext_text(value: object) -> str | None:
    """Display text for any OM custom property value.

    Handles plain strings/numbers, enum values (lists of strings), entity
    references (dicts or lists of them) and time intervals ({start, end}).
    """
    if value is None or isinstance(value, bool):
        return None if value is None else ("Yes" if value else "No")
    if isinstance(value, list):
        parts = [ext_text(v) for v in value]
        return ", ".join(p for p in parts if p) or None
    if isinstance(value, dict):
        named = _text(value.get("displayName")) or _text(value.get("name"))
        if named:
            return named
        if "start" in value or "end" in value:
            start, end = _format_epoch(value.get("start")), _format_epoch(value.get("end"))
            return " – ".join(p for p in (start, end) if p) or None
        return _text(value.get("value"))
    return _text(value)


def ext_bool(value: object) -> bool | None:
    """Yes/no custom property (boolean, Y/N string, or single-value enum)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, list):
        return ext_bool(value[0]) if len(value) == 1 else None
    text = (_text(value) or "").lower()
    if text in ("yes", "y", "true", "1", "available"):
        return True
    if text in ("no", "n", "false", "0", "not available", "unavailable"):
        return False
    return None


def _ext(entity: dict | None, key: str) -> object:
    return ((entity or {}).get("extension") or {}).get(key)


def owner_name(owners: list[dict] | None) -> str | None:
    """Display name of the first OM owner reference, if any."""
    for owner in owners or []:
        name = _text(owner.get("displayName")) or _text(owner.get("name"))
        if name:
            return name
    return None


def _classification_rank(value: str | None) -> int:
    key = (value or "").strip().lower()
    key = _CLASSIFICATION_ALIASES.get(key, key)
    return _CLASSIFICATION_RANK.get(key, -1)


def classification_tag(entity: dict | None) -> dict | None:
    """{"value", "description"} of the entity's classification tag, if any.

    Only the dedicated classification namespaces are read (never other
    tags). An explicit `data_classification` value wins. With several
    classification tags the most restrictive recognized one is used.
    """
    entity = entity or {}
    explicit = _text(entity.get("data_classification"))
    if explicit:
        return {"value": explicit, "description": None}
    for prefix in CLASSIFICATION_PREFIXES:
        found = [
            {"value": (tag.get("tagFQN") or "")[len(prefix):], "description": _text(tag.get("description"))}
            for tag in entity.get("tags") or []
            if (tag.get("tagFQN") or "").startswith(prefix)
        ]
        found = [f for f in found if f["value"]]
        if found:
            return max(found, key=lambda f: _classification_rank(f["value"]))
    return None


def classification_of(entity: dict | None) -> str | None:
    tag = classification_tag(entity)
    return tag["value"] if tag else None


def _pick(*candidates: tuple[str, object]) -> tuple[object, str | None]:
    for origin, value in candidates:
        if value is not None and value != "":
            return value, origin
    return None, None


def resolve_table_facts(
    table: dict,
    table_info: dict | None,
    dataset_info: dict | None,
    database: dict | None,
) -> dict:
    """Facts for one table with dataset-level inheritance applied."""
    ti = table_info or {}
    di = dataset_info or {}
    owner, owner_from = _pick(
        ("table", owner_name(table.get("owners"))),
        ("table", ext_text(_ext(table, EXT_OWNER))),
        ("table", _text(ti.get("dataset_owner"))),
        ("dataset", ext_text(_ext(database, EXT_OWNER))),
        ("dataset", _text(di.get("owner"))),
        ("dataset", owner_name((database or {}).get("owners"))),
    )
    steward, steward_from = _pick(
        ("table", ext_text(_ext(table, EXT_STEWARD))),
        ("dataset", ext_text(_ext(database, EXT_STEWARD))),
        ("dataset", _text(di.get("steward"))),
    )
    frequency, frequency_from = _pick(
        ("table", ext_text(_ext(table, EXT_FREQUENCY))),
        ("table", _text(ti.get("frequency"))),
        ("dataset", ext_text(_ext(database, EXT_FREQUENCY))),
        ("dataset", _text(di.get("frequency"))),
    )
    timeline, timeline_from = _pick(
        ("table", ext_text(_ext(table, EXT_TIMELINE))),
        ("table", _text(ti.get("timeline"))),
        ("dataset", ext_text(_ext(database, EXT_TIMELINE))),
        ("dataset", _text(di.get("timeline"))),
    )
    api, api_from = _pick(
        ("table", ext_bool(_ext(table, EXT_API_AVAILABLE))),
        ("table", ti.get("api_available")),
        ("dataset", ext_bool(_ext(database, EXT_API_AVAILABLE))),
    )
    classification, classification_from = _pick(
        ("table", classification_tag(table)),
        ("dataset", classification_tag(database)),
    )
    return {
        "owner": owner,
        "steward": steward,
        "department_contact": None,
        "updated_at": table.get("updatedAt"),
        "frequency": frequency,
        "timeline": timeline,
        "api_available": api,
        "data_classification": classification["value"] if classification else None,
        "data_classification_description": classification["description"] if classification else None,
        "source": None,
        "origin": {
            "owner": owner_from,
            "steward": steward_from,
            "frequency": frequency_from,
            "timeline": timeline_from,
            "api_available": api_from,
            "data_classification": classification_from,
        },
    }


def table_api_available(table: dict, table_info: dict | None) -> bool | None:
    """The table's own API flag (OM custom property, else sidecar)."""
    value = ext_bool(_ext(table, EXT_API_AVAILABLE))
    return value if value is not None else (table_info or {}).get("api_available")


def resolve_dataset_info(
    dataset_info: dict | None,
    database: dict | None,
    tables: list[dict],
    table_infos: dict[str, dict],
) -> dict:
    """Dataset-level facts plus summaries over the given (visible) tables."""
    di = dataset_info or {}
    flags = [
        table_api_available(t, table_infos.get(t.get("fullyQualifiedName") or ""))
        for t in tables
    ]
    classification = classification_tag(database)
    if classification is None:
        ranked = [
            tag for tag in (classification_tag(t) for t in tables)
            if tag and _classification_rank(tag["value"]) >= 0
        ]
        classification = max(ranked, key=lambda f: _classification_rank(f["value"])) if ranked else None
    return {
        "owner": ext_text(_ext(database, EXT_OWNER))
        or _text(di.get("owner"))
        or owner_name((database or {}).get("owners")),
        "steward": ext_text(_ext(database, EXT_STEWARD)) or _text(di.get("steward")),
        "frequency": ext_text(_ext(database, EXT_FREQUENCY)) or _text(di.get("frequency")),
        "timeline": ext_text(_ext(database, EXT_TIMELINE)) or _text(di.get("timeline")),
        "api_available": ext_bool(_ext(database, EXT_API_AVAILABLE)),
        # Dataset-only (never per table): "Department Provided" or "Public Extraction".
        "schema_source": ext_text(_ext(database, EXT_SCHEMA_SOURCE)),
        "api_tables": sum(1 for f in flags if f is True),
        "api_known": sum(1 for f in flags if f is not None),
        "table_count": len(tables),
        "data_classification": classification["value"] if classification else None,
        "data_classification_description": classification["description"] if classification else None,
    }
