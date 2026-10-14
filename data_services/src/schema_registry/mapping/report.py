"""Field-mapping reports: a department submits a schema, and before we
ingest it someone has to answer "are these fields new, or do we already
have them?" -- per field, with enough evidence for the department to check.

Usage (see --help for the full set):

    python -m src.schema_registry.mapping.report \
        --submission ../Datasets/pwd_vishwakarma_full_raw_columns.txt \
        --department public_works_department --dataset vishwakarma --table vishwakarma_T \
        --catalog global --out-dir reports

Submission formats are auto-detected by extension:
  .txt  raw Postgres column list (ddl_parser, like PWD's file)
  .csv  multi-table Field Dictionary (field_dictionary_parser)
  .xlsx the Kanya Sumangla workbook (kanya_xlsx, one sheet per scheme --
        each sheet's department/dataset comes from the workbook's own Note
        sheet, so no --department/--dataset is needed for it)

Catalogs:
  local   storage/_lookups/*.csv + each table's latest curated snapshot
  global  GET-only reads of the catalog OpenMetadata instance (never a
          write -- see the module docstring in openmetadata/publish.py and
          the project's publishing rules)
  both    both, de-duplicated on (table_id, field name)

Match classes, in order:
  exact        identical field name
  normalized   same name once case/punctuation are stripped ("District Name"
               vs "district_name") -- counts as mapped
  candidate    token overlap strong enough to be worth a human look, but NOT
               counted as mapped (it would overstate reuse)
  new          nothing close

Column tags: `missing_on_submission` lists the required attributes the
department's own row is missing; `missing_on_existing` does the same for the
field we already have (that's the gap a mapping report exposes on our side).
"""

from __future__ import annotations

import argparse
import csv
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.schema_registry.parsers import field_dictionary_parser, kanya_xlsx
from src.schema_registry.parsers.ddl_parser import parse_postgres_columns
from src.schema_registry.registry import lookups
from src.storage.base import ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)

# A `character varying(n)`/`numeric(p,s)` that arrives without its width is
# not a usable definition; plain `integer`/`date`/`double precision` never
# carry one, so those are never reported as missing.
_LENGTH_TYPES = {"character varying", "character", "varchar", "text", "numeric", "decimal"}
_SCALE_TYPES = {"numeric", "decimal"}

_CANDIDATE_THRESHOLD = 0.5

CSV_COLUMNS = [
    "department",
    "dataset",
    "table",
    "field_index",
    "field_name",
    "submission_data_type",
    "submission_length",
    "submission_scale",
    "submission_nullable",
    "status",
    "match_type",
    "matched_table_id",
    "matched_field",
    "matched_data_type",
    "matched_length",
    "matched_nullable",
    "existing_business_description",
    "existing_tag",
    "missing_on_submission",
    "missing_on_existing",
    "notes",
]


@dataclass
class Field:
    """One field of one table, as either the submission or the catalog sees it."""

    department: str
    dataset: str
    table: str
    name: str
    data_type: str
    length: int | None
    scale: int | None
    nullable: bool | None
    business_description: str = ""
    tag: str = ""
    table_id: str = ""
    format_note: str = ""


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def tokens(name: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", (name or "").lower()) if token}


def _similarity(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def missing_attributes(item: Field) -> list[str]:
    """Required field-level attributes this row can't answer (see module doc)."""

    missing: list[str] = []
    if not item.data_type:
        missing.append("data_type")
    if item.data_type.lower() in _LENGTH_TYPES and item.length is None:
        missing.append("length")
    if item.data_type.lower() in _SCALE_TYPES and item.scale is None:
        missing.append("scale")
    if item.nullable is None:
        missing.append("nullable")
    if not item.business_description.strip():
        missing.append("business_description")
    if not item.tag.strip():
        missing.append("tag")
    return missing


# --- submissions -------------------------------------------------------


def _submission_from_dictionary(path: Path, department: str, dataset: str = "") -> list[Field]:
    fields: list[Field] = []
    for table_name, table in field_dictionary_parser.parse_field_dictionary(str(path)).items():
        for column in table["columns"]:
            meta = table["business_metadata"].get(column["name"], {})
            fields.append(
                Field(
                    department=department,
                    dataset=dataset or path.stem,
                    table=table_name,
                    name=column["name"],
                    data_type=column["data_type"],
                    length=column["length"],
                    scale=column["scale"],
                    nullable=column["nullable"],
                    business_description=meta.get("business_description", ""),
                    tag=meta.get("tag", ""),
                    format_note=meta.get("format_note", ""),
                )
            )
    return fields


def _submission_from_ddl(path: Path, department: str, dataset: str, table: str) -> list[Field]:
    return [
        Field(
            department=department,
            dataset=dataset,
            table=table,
            name=column["name"],
            data_type=column["data_type"],
            length=column["length"],
            scale=column["scale"],
            nullable=column["nullable"],
        )
        for column in parse_postgres_columns(path.read_text(encoding="utf-8"))
    ]


def _submission_from_workbook(path: Path) -> list[Field]:
    fields: list[Field] = []
    missing: list[str] = []
    for config in kanya_xlsx.SHEETS:
        try:
            records = kanya_xlsx.read_sheet(path, config.sheet)
        except ValueError:
            # a submission may legitimately carry only some of the roster's schemes
            missing.append(config.sheet)
            continue
        for record in records:
            try:
                spec = field_dictionary_parser.parse_format_full(record["Format"])
                format_note = ""
            except ValueError as exc:
                spec = field_dictionary_parser.FormatSpec("character varying", None, None)
                format_note = str(exc)
            mandatory = record["Mandatory (Y/N)"].strip().upper()
            personal = record["Personal Data (Y/N)"].strip().upper()
            fields.append(
                Field(
                    department=config.department_id,
                    dataset=config.dataset,
                    table=record["Dataset Name"],
                    name=record["Dataset Field"],
                    data_type=spec.data_type,
                    length=spec.length,
                    scale=spec.scale,
                    nullable=not mandatory.startswith("Y"),
                    business_description=record["Data Description"],
                    tag="PII" if personal.startswith("Y") else "",
                    format_note=format_note,
                )
            )
    if len(missing) == len(kanya_xlsx.SHEETS):
        raise ValueError(
            f"none of the roster sheets are in {path} "
            f"(present sheets: {', '.join(kanya_xlsx.sheet_names(path))})"
        )
    if missing:
        logger.warning(f"{path}: skipping {len(missing)} roster sheet(s) not in the workbook: {', '.join(missing)}")
    return fields


def read_submission(
    path: str | Path,
    department: str = "",
    dataset: str = "",
    table: str = "",
) -> list[Field]:
    """Parse a submission into Field rows; the format comes from the extension."""

    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return _submission_from_workbook(path)
    if suffix == ".csv":
        if not department:
            raise ValueError("--department is required for a Field Dictionary CSV submission")
        return _submission_from_dictionary(path, department, dataset)
    if not (department and dataset and table):
        raise ValueError("--department, --dataset and --table are required for a raw DDL submission")
    return _submission_from_ddl(path, department, dataset, table)


# --- catalogs ----------------------------------------------------------


def load_local_catalog(
    storage: ObjectStorage,
    exclude_departments: tuple[str, ...] = (),
) -> list[Field]:
    """Every registered table's latest curated snapshot (what we actually hold)."""

    if not storage.exists(lookups.TABLES_PATH):
        raise ValueError(f"{lookups.TABLES_PATH} not found -- nothing registered locally yet")

    catalog: list[Field] = []
    for table_row in storage.read_csv(lookups.TABLES_PATH):
        if table_row.get("deleted"):
            continue
        table_id = table_row["table_id"]
        department_id, dataset_slug, table_slug = table_id.split(".")
        if department_id in exclude_departments:
            continue
        try:
            snapshot = lookups.latest_curated_snapshot_path(storage, department_id, dataset_slug, table_slug)
        except FileNotFoundError:
            logger.warning(f"mapping: no curated snapshot for {table_id} -- skipped")
            continue
        for column in storage.read_csv(snapshot):
            catalog.append(
                Field(
                    department=department_id,
                    dataset=dataset_slug,
                    table=table_row["table_name"],
                    name=column["name"],
                    data_type=column["data_type"],
                    length=_int_or_none(column.get("length")),
                    scale=_int_or_none(column.get("scale")),
                    nullable=_bool_or_none(column.get("nullable")),
                    business_description=column.get("business_description", ""),
                    tag=column.get("tag", ""),
                    table_id=table_id,
                )
            )
    return catalog


def load_global_catalog(
    host_port: str,
    jwt_token: str,
    exclude_departments: tuple[str, ...] = (),
) -> list[Field]:
    """Read-only walk of the catalog OpenMetadata instance.

    GETs only -- this project publishes to no instance without explicit
    permission, and this function has no write path at all (no POST/PUT/
    PATCH is issued, and the response of a write-shaped call is never used).
    """

    base = host_port.rstrip("/")
    headers = {"Authorization": f"Bearer {jwt_token}"}

    def get(url: str, **params) -> dict:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    catalog: list[Field] = []
    services = get(f"{base}/services/databaseServices", limit=100).get("data", [])
    for service in services:
        service_name = service["name"]
        if service_name in exclude_departments:
            continue
        databases = get(f"{base}/services/databaseServices/{service_name}/databases", limit=1000).get("data", [])
        for database in databases:
            db_name = database["name"]
            schemas = get(f"{base}/databases/{service_name}.{db_name}/schemas", limit=1000).get("data", [])
            for schema in schemas:
                schema_fqn = f"{service_name}.{db_name}.{schema['name']}"
                tables = get(f"{base}/schemas/{schema_fqn}/tables", limit=1000, fields="columns").get("data", [])
                for table in tables:
                    table_id = f"{service_name}.{db_name}.{table['name']}"
                    for column in table.get("columns") or []:
                        catalog.append(
                            Field(
                                department=service_name,
                                dataset=db_name,
                                table=table["name"],
                                name=column.get("name", ""),
                                data_type=column.get("dataType", ""),
                                length=column.get("dataLength") or column.get("dataPrecision"),
                                scale=column.get("dataScale"),
                                nullable=column.get("nullable"),
                                business_description=column.get("description") or "",
                                tag=_field_tag(column),
                                table_id=table_id,
                            )
                        )
    return catalog


def _field_tag(column: dict) -> str:
    for label in column.get("tags") or []:
        if str(label.get("tagFQN", "")).startswith("FieldTag."):
            return label["tagFQN"].split(".", 1)[1]
    return ""


def _int_or_none(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "t", "yes", "y"}


# --- matching ----------------------------------------------------------


def match_field(item: Field, catalog: list[Field], candidate_threshold: float = _CANDIDATE_THRESHOLD) -> dict:
    """Classify one submission field against the catalog (see module docstring)."""

    exact = next((c for c in catalog if c.name == item.name), None)
    if exact is not None:
        return _result(item, exact, "maps", "exact")

    normalized = next((c for c in catalog if normalize(c.name) == normalize(item.name) and normalize(item.name)), None)
    if normalized is not None:
        return _result(item, normalized, "maps", "normalized")

    scored = sorted(
        ((c, _similarity(item.name, c.name)) for c in catalog),
        key=lambda pair: pair[1],
        reverse=True,
    )
    if scored and scored[0][1] >= candidate_threshold:
        return _result(item, scored[0][0], "candidate", "token-overlap")

    return _result(item, None, "new", "")


def _result(item: Field, matched: Field | None, status: str, match_type: str) -> dict:
    notes = []
    if item.format_note:
        notes.append(item.format_note)
    if matched is not None and status == "maps":
        differences = []
        if matched.data_type and item.data_type and matched.data_type.lower() != item.data_type.lower():
            differences.append(f"type {item.data_type} != existing {matched.data_type}")
        if matched.length != item.length:
            differences.append(f"length {item.length} != existing {matched.length}")
        if matched.nullable is not None and item.nullable is not None and matched.nullable != item.nullable:
            differences.append(f"nullable {item.nullable} != existing {matched.nullable}")
        if differences:
            notes.append("; ".join(differences))

    return {
        "department": item.department,
        "dataset": item.dataset,
        "table": item.table,
        "field_name": item.name,
        "submission_data_type": item.data_type,
        "submission_length": "" if item.length is None else str(item.length),
        "submission_scale": "" if item.scale is None else str(item.scale),
        "submission_nullable": "" if item.nullable is None else str(item.nullable),
        "status": status,
        "match_type": match_type,
        "matched_table_id": matched.table_id if matched else "",
        "matched_field": matched.name if matched else "",
        "matched_data_type": matched.data_type if matched else "",
        "matched_length": "" if not matched or matched.length is None else str(matched.length),
        "matched_nullable": "" if not matched or matched.nullable is None else str(matched.nullable),
        "existing_business_description": matched.business_description if matched else "",
        "existing_tag": matched.tag if matched else "",
        "missing_on_submission": "; ".join(missing_attributes(item)),
        "missing_on_existing": "; ".join(missing_attributes(matched)) if matched else "",
        "notes": "; ".join(notes),
    }


def build_rows(submission: list[Field], catalog: list[Field]) -> list[dict]:
    rows = []
    counters: Counter[tuple[str, str, str]] = Counter()
    for item in submission:
        counters[(item.department, item.dataset, item.table)] += 1
        row = match_field(item, catalog)
        row["field_index"] = counters[(item.department, item.dataset, item.table)]
        rows.append(row)
    return rows


# --- outputs -----------------------------------------------------------


def summarize(rows: list[dict]) -> dict:
    status_counts = Counter(row["status"] for row in rows)
    departments: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        bucket = departments[row["department"]]
        bucket["fields"] += 1
        bucket[row["status"]] += 1
        bucket["missing_description"] += int("business_description" in row["missing_on_submission"])
        bucket["missing_tag"] += int("tag" in row["missing_on_submission"])

    tables: dict[tuple[str, str], set] = defaultdict(set)
    for row in rows:
        tables[row["department"]].add((row["dataset"], row["table"]))
    for department, dataset_tables in tables.items():
        departments[department]["tables"] = len(dataset_tables)

    return {
        "fields": len(rows),
        "tables": len({(r["department"], r["dataset"], r["table"]) for r in rows}),
        "status": dict(status_counts),
        "missing_description": sum(int("business_description" in r["missing_on_submission"]) for r in rows),
        "missing_tag": sum(int("tag" in r["missing_on_submission"]) for r in rows),
        "departments": {name: dict(counts) for name, counts in departments.items()},
    }


def write_csv(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in CSV_COLUMNS})
    return path


def write_markdown(
    rows: list[dict],
    summary: dict,
    path: Path,
    *,
    title: str,
    source: str,
    catalog: str,
    notes: list[str] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    status = summary["status"]
    total = summary["fields"] or 1
    mapped = status.get("maps", 0)

    lines = [
        f"# {title}",
        "",
        f"- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Submission: {source}",
        f"- Catalog: {catalog}",
        "",
        "## Headline",
        "",
        f"- Fields: **{summary['fields']}** in {summary['tables']} table(s)",
        f"- Map to an existing field: **{mapped}** ({mapped * 100 // total}%)",
        f"- Candidates needing confirmation: **{status.get('candidate', 0)}**",
        f"- New fields: **{status.get('new', 0)}**",
        f"- Missing `business_description` on the submission: **{summary['missing_description']}**",
        f"- Missing `tag` on the submission: **{summary['missing_tag']}**",
    ]
    if notes:
        lines += ["", "## Notes"] + [f"- {note}" for note in notes]
    lines += [
        "",
        "## By department",
        "",
        "| department | tables | fields | mapped | candidate | new | desc gaps | tag gaps |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for department, counts in sorted(summary["departments"].items()):
        lines.append(
            f"| {department} | {counts.get('tables', 0)} | {counts.get('fields', 0)} | "
            f"{counts.get('maps', 0)} | {counts.get('candidate', 0)} | {counts.get('new', 0)} | "
            f"{counts.get('missing_description', 0)} | {counts.get('missing_tag', 0)} |"
        )

    candidates = [row for row in rows if row["status"] == "candidate"]
    if candidates:
        lines += ["", "## Candidates to confirm", ""]
        for row in candidates[:25]:
            lines.append(
                f"- `{row['table']}.{row['field_name']}` ~ `{row['matched_table_id']}.{row['matched_field']}` "
                f"({row['match_type']})"
            )

    noted = [row for row in rows if row["notes"]]
    if noted:
        lines += ["", "## Needs fixing before ingest", ""]
        for row in noted[:25]:
            lines.append(f"- `{row['table']}.{row['field_name']}`: {row['notes']}")

    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# --- CLI ---------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.schema_registry.mapping.report",
        description="Field-level mapping report for a department submission.",
    )
    parser.add_argument("--submission", required=True, help=".txt (raw DDL), .csv (Field Dictionary) or .xlsx workbook")
    parser.add_argument("--department", default="", help="department id (raw DDL / Field Dictionary submissions)")
    parser.add_argument("--dataset", default="", help="dataset id (raw DDL / Field Dictionary submissions)")
    parser.add_argument("--table", default="", help="table name (raw DDL submissions)")
    parser.add_argument("--catalog", choices=("local", "global", "both"), default="local")
    parser.add_argument(
        "--exclude-department",
        action="append",
        default=[],
        help="department id to leave out of the catalog (repeatable) -- use it to compare a submission "
        "against everything *except* the departments it just created",
    )
    parser.add_argument("--global-host", default=os.environ.get("GLOBAL_OPENMETADATA_HOST_PORT", ""))
    parser.add_argument("--global-token", default=os.environ.get("GLOBAL_OPENMETADATA_JWT_TOKEN", ""))
    parser.add_argument("--out-dir", default="reports", help="directory for <name>.csv / <name>.md")
    parser.add_argument("--name", default="", help="output file stem (default: submission file name)")
    parser.add_argument("--no-markdown", action="store_true", help="skip the Markdown summary")
    parser.add_argument(
        "--split-by-department",
        action="store_true",
        help="write one CSV/Markdown pair per department instead of one pair for the whole submission",
    )
    parser.add_argument(
        "--note",
        action="append",
        default=[],
        help="extra line for the Markdown 'Notes' section (repeatable)",
    )
    args = parser.parse_args(argv)

    submission = read_submission(
        args.submission, department=args.department, dataset=args.dataset, table=args.table
    )
    excluded = tuple(args.exclude_department)

    storage = None
    catalogs: list[list[Field]] = []
    sources: list[str] = []
    if args.catalog in ("local", "both"):
        from src.storage import storage_from_env

        storage = storage_from_env()
        catalogs.append(load_local_catalog(storage, excluded))
        sources.append("local registry")
    if args.catalog in ("global", "both"):
        if not (args.global_host and args.global_token):
            raise ValueError("--catalog global needs --global-host and --global-token (or the GLOBAL_* env vars)")
        catalogs.append(load_global_catalog(args.global_host, args.global_token, excluded))
        sources.append(f"catalog OpenMetadata at {args.global_host}")

    catalog: list[Field] = []
    seen: set[tuple[str, str]] = set()
    for source_catalog in catalogs:
        for item in source_catalog:
            key = (item.table_id, normalize(item.name))
            if key in seen:
                continue
            seen.add(key)
            catalog.append(item)

    rows = build_rows(submission, catalog)
    catalog_label = " + ".join(sources) + (f" (excluding {', '.join(excluded)})" if excluded else "")

    if args.split_by_department:
        departments = sorted({row["department"] for row in rows})
        groups = {name: [row for row in rows if row["department"] == name] for name in departments}
    else:
        groups = {"": rows}

    out_dir = Path(args.out_dir)
    stem = args.name or Path(args.submission).stem

    for department, group in groups.items():
        summary = summarize(group)
        suffix = f"_{department}" if department else ""
        csv_path = write_csv(group, out_dir / f"{stem}{suffix}_field_mapping.csv")
        print(
            f"{department or 'all'}: fields={summary['fields']} maps={summary['status'].get('maps', 0)} "
            f"candidate={summary['status'].get('candidate', 0)} new={summary['status'].get('new', 0)} "
            f"missing_description={summary['missing_description']} missing_tag={summary['missing_tag']}"
        )
        logger.info(f"mapping: {department or stem} -> {summary['fields']} field(s) in {csv_path}")
        print(f"csv={csv_path}")

        if not args.no_markdown:
            title = f"Field mapping report — {department or stem}"
            if department and storage is not None:
                display = _department_display_name(storage, department)
                if display:
                    title = f"{title} ({display})"
            md_path = write_markdown(
                group,
                summary,
                out_dir / f"{stem}{suffix}_field_mapping.md",
                title=title,
                source=args.submission,
                catalog=catalog_label,
                notes=args.note,
            )
            print(f"markdown={md_path}")
    return 0


def _department_display_name(storage: ObjectStorage, department_id: str) -> str:
    if not storage.exists(lookups.DEPARTMENTS_PATH):
        return ""
    for row in storage.read_csv(lookups.DEPARTMENTS_PATH):
        if row["department_id"] == department_id:
            return row["department_name"]
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
