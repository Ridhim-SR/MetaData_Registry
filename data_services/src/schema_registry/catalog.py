"""catalog.yaml: the reviewed list of what should be in OpenMetadata --
departments, their datasets (with category/owner/steward/...), and which file in
storage each table comes from. `sync` reads it; see README "Adding or
updating a department's data".

Checked strictly when loaded: an unknown key (a typo like `ownr:`), a
category that isn't CAT-1..CAT-4, or an unknown format fails with the exact
place to fix, instead of being silently ignored. So does a `dataset_type`
that isn't one of DATASET_TYPES.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.schema_registry.registry import lookups

_FORMATS = {"postgres_ddl", "csv"}
_CATEGORY_RE = re.compile(r"^CAT-[1-4]$")
# Who the dataset is about: citizens/beneficiaries, or the department's own
# administration (schemes, budgets, works). Exact spelling, like `category`.
DATASET_TYPES = ("Citizen Centric", "Administrative")

# catalog key -> datasets.csv field
_DATASET_FIELD_KEYS = {
    "category": "category",
    "dataset_type": "dataset_type",
    "api_available": "api_available",
    "owner": "owner",
    "steward": "steward",
    "frequency": "frequency",
    "timeline": "timeline",
    "description": "dataset_description",
    "source_url": "source_url",
}


@dataclass
class TableEntry:
    name: str
    source: str
    format: str = "postgres_ddl"
    schema: str = "public"
    metadata: str | None = None
    allow_column_removal: bool = False


@dataclass
class DatasetEntry:
    name: str
    fields: dict = field(default_factory=dict)  # datasets.csv field -> value
    tables: list[TableEntry] = field(default_factory=list)
    field_dictionary: str | None = None  # one file describing several tables
    allow_category_below_columns: bool = False


@dataclass
class DepartmentEntry:
    id: str
    name: str
    description: str = ""
    datasets: list[DatasetEntry] = field(default_factory=list)


class CatalogError(ValueError):
    pass


def _check_keys(where: str, value, allowed: set[str], required: set[str] = frozenset()) -> dict:
    if not isinstance(value, dict):
        raise CatalogError(f"{where}: expected a section of keys, got {type(value).__name__}")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise CatalogError(
            f"{where}: unknown key(s) {unknown} in catalog.yaml -- fix the spelling there. "
            f"Allowed here: {', '.join(sorted(allowed))}"
        )
    missing = sorted(required - set(value))
    if missing:
        raise CatalogError(f"{where}: missing required key(s) {missing}")
    return value


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def parse_catalog(text: str) -> list[DepartmentEntry]:
    data = yaml.safe_load(text) or {}
    _check_keys("catalog", data, {"departments"})
    departments: list[DepartmentEntry] = []

    for dept_id, dept in (data.get("departments") or {}).items():
        where = f"departments.{dept_id}"
        if lookups.slugify(str(dept_id)) != str(dept_id):
            raise CatalogError(f"{where}: department id must be lowercase letters, digits and _ (try '{lookups.slugify(str(dept_id))}')")
        dept = _check_keys(where, dept, {"name", "description", "datasets"}, {"name"})
        entry = DepartmentEntry(
            id=str(dept_id),
            name=_text(dept["name"]),
            description=_text(dept.get("description")),
        )

        for ds_name, ds in (dept.get("datasets") or {}).items():
            ds_where = f"{where}.datasets.{ds_name}"
            ds = _check_keys(
                ds_where, ds or {},
                set(_DATASET_FIELD_KEYS) | {"tables", "field_dictionary", "allow_category_below_columns"},
            )
            category = _text(ds.get("category"))
            if category and not _CATEGORY_RE.match(category):
                raise CatalogError(f"{ds_where}.category: '{category}' must be CAT-1, CAT-2, CAT-3 or CAT-4 (or left blank)")
            dataset_type = _text(ds.get("dataset_type"))
            if dataset_type and dataset_type not in DATASET_TYPES:
                raise CatalogError(
                    f"{ds_where}.dataset_type: '{dataset_type}' must be "
                    f"{' or '.join(repr(t) for t in DATASET_TYPES)} (or left blank)"
                )
            dataset = DatasetEntry(
                name=str(ds_name),
                fields={csv_field: _text(ds.get(key)) for key, csv_field in _DATASET_FIELD_KEYS.items()},
                field_dictionary=_text(ds.get("field_dictionary")) or None,
                allow_category_below_columns=bool(ds.get("allow_category_below_columns", False)),
            )

            seen: dict[str, str] = {}
            for table_name, table in (ds.get("tables") or {}).items():
                t_where = f"{ds_where}.tables.{table_name}"
                table = _check_keys(
                    t_where, table, {"source", "format", "schema", "metadata", "allow_column_removal"}, {"source"}
                )
                fmt = _text(table.get("format")) or "postgres_ddl"
                if fmt not in _FORMATS:
                    raise CatalogError(f"{t_where}.format: '{fmt}' must be one of {sorted(_FORMATS)}")
                slug = lookups.slugify(str(table_name))
                if slug in seen:
                    raise CatalogError(f"{t_where}: same table id '{slug}' as '{seen[slug]}' -- rename one of them")
                seen[slug] = str(table_name)
                dataset.tables.append(TableEntry(
                    name=str(table_name),
                    source=_text(table["source"]),
                    format=fmt,
                    schema=_text(table.get("schema")) or "public",
                    metadata=_text(table.get("metadata")) or None,
                    allow_column_removal=bool(table.get("allow_column_removal", False)),
                ))

            if not dataset.tables and not dataset.field_dictionary:
                raise CatalogError(f"{ds_where}: needs `tables` or `field_dictionary`")
            entry.datasets.append(dataset)
        departments.append(entry)

    return departments


def load_catalog(path: str | Path) -> list[DepartmentEntry]:
    # explicit utf-8: catalog descriptions carry Hindi labels, and on Windows
    # Path.read_text() otherwise uses the locale codec (cp1252) and refuses them
    return parse_catalog(Path(path).read_text(encoding="utf-8"))
