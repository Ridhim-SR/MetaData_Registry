"""Add or update a department's file in one step: upload it to storage and
write its entry into catalog.yaml. No paths to choose or copy.

    # a table (format guessed from the extension: .csv -> csv, else postgres_ddl)
    python3 -m src.schema_registry.add samples/pwd_vishwakarma.txt \\
        --department pwd --dataset vishwakarma --table vishwakarma_T

    # first file of a new department: also give its full name
    python3 -m src.schema_registry.add samples/x.csv --department samaj_kalyan \\
        --department-name "Department of Social Welfare" --dataset cmsvy --table applications

    # one Field Dictionary file describing several tables of a dataset
    python3 -m src.schema_registry.add samples/dict.csv --department samaj_kalyan \\
        --dataset cmsvy --field-dictionary

Files always go to  inputs/<department>/<dataset>/<file name>  in the
storage ENVIRONMENT points at (Wasabi dev/ or prod/, or local storage/).
For production, run the same command with ENVIRONMENT=production -- the
catalog entry is already there, so only the upload happens.

Then commit catalog.yaml (open a PR) and run sync.
"""

import argparse
import io
import sys
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from src.schema_registry import inputs
from src.schema_registry.catalog import parse_catalog
from src.schema_registry.registry import lookups
from src.storage.base import ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_CATALOG = Path(__file__).resolve().parents[2] / "catalog.yaml"
_DATASET_FIELD_KEYS = ("category", "owner", "frequency", "timeline", "api_available", "description")


def input_key(department: str, dataset: str, file_name: str) -> str:
    return f"inputs/{department}/{lookups.slugify(dataset)}/{file_name}"


def guess_format(path: str) -> str:
    return "csv" if path.lower().endswith(".csv") else "postgres_ddl"


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 4096  # never wrap a long storage: path onto a second line
    return y


def update_catalog_text(
    text: str,
    department: str,
    dataset: str,
    source_ref: str,
    department_name: str | None = None,
    table: str | None = None,
    file_format: str | None = None,
    schema: str | None = None,
    metadata_ref: str | None = None,
) -> tuple[str, list[str]]:
    """Return catalog.yaml text with the entry added or updated, plus a
    list of what changed (empty = already up to date). Comments and the
    order of everything else are kept. table=None means `source_ref` is the
    dataset's field dictionary."""

    y = _yaml()
    data = y.load(text) or CommentedMap()
    changes: list[str] = []

    departments = data.setdefault("departments", CommentedMap())
    if departments is None:
        departments = data["departments"] = CommentedMap()
    dept = departments.get(department)
    if dept is None:
        if not department_name:
            raise ValueError(
                f"Department '{department}' isn't in catalog.yaml yet -- add --department-name \"<full name>\" "
                f"the first time."
            )
        dept = departments[department] = CommentedMap(name=department_name, datasets=CommentedMap())
        changes.append(f"added department {department} ({department_name})")
    elif department_name and dept.get("name") != department_name:
        dept["name"] = department_name
        changes.append(f"renamed department {department} to '{department_name}'")

    datasets = dept.get("datasets")
    if datasets is None:
        datasets = dept["datasets"] = CommentedMap()
    ds = datasets.get(dataset)
    if ds is None:
        ds = datasets[dataset] = CommentedMap((key, None) for key in _DATASET_FIELD_KEYS)
        changes.append(f"added dataset {department}/{dataset} (fill in category, owner, ... when known)")

    if table is None:
        if ds.get("field_dictionary") != source_ref:
            ds["field_dictionary"] = source_ref
            changes.append(f"set field dictionary of {department}/{dataset} to {source_ref}")
    else:
        tables = ds.get("tables")
        if tables is None:
            tables = ds["tables"] = CommentedMap()
        wanted = {"source": source_ref, "format": file_format or guess_format(source_ref)}
        if schema:
            wanted["schema"] = schema
        if metadata_ref:
            wanted["metadata"] = metadata_ref
        entry = tables.get(table)
        if entry is None:
            tables[table] = CommentedMap(wanted)
            changes.append(f"added table {department}/{dataset}/{table}")
        else:
            for key, value in wanted.items():
                if entry.get(key) != value:
                    entry[key] = value
                    changes.append(f"set {key} of {department}/{dataset}/{table} to {value}")

    out = io.StringIO()
    y.dump(data, out)
    new_text = out.getvalue()
    parse_catalog(new_text)  # never write a catalog that sync would reject
    return new_text, changes


def add(
    storage: ObjectStorage,
    catalog_path: str | Path,
    file: str,
    department: str,
    dataset: str,
    table: str | None = None,
    department_name: str | None = None,
    file_format: str | None = None,
    schema: str | None = None,
    metadata_file: str | None = None,
) -> list[str]:
    """Upload `file` (and `metadata_file`) and update catalog.yaml. The
    catalog change is worked out and checked first, so a mistake (unknown
    department without a name, bad id) uploads nothing."""

    if lookups.slugify(department) != department:
        raise ValueError(f"--department must be lowercase letters, digits and _ (try '{lookups.slugify(department)}')")
    if not Path(file).is_file():
        raise FileNotFoundError(f"No such file: {file}")

    source_key = input_key(department, dataset, Path(file).name)
    metadata_key = input_key(department, dataset, Path(metadata_file).name) if metadata_file else None
    catalog_path = Path(catalog_path)
    new_text, changes = update_catalog_text(
        catalog_path.read_text() if catalog_path.exists() else "",
        department, dataset, f"{inputs.STORAGE_SCHEME}{source_key}",
        department_name=department_name, table=table,
        file_format=file_format or (guess_format(file) if table else None), schema=schema,
        metadata_ref=f"{inputs.STORAGE_SCHEME}{metadata_key}" if metadata_key else None,
    )

    for local, key in [(file, source_key), (metadata_file, metadata_key)]:
        if local:
            data = Path(local).read_bytes()
            storage.write_bytes(key, data)
            changes.insert(0, f"uploaded {local} -> {key} (sha256 {inputs.sha256(data)[:12]}...)")

    if new_text != (catalog_path.read_text() if catalog_path.exists() else ""):
        catalog_path.write_text(new_text)
    return changes


def _main(argv: list[str]) -> int:
    from src.storage import storage_from_env
    from src.utils.config import load_env

    parser = argparse.ArgumentParser(prog="python3 -m src.schema_registry.add", description=__doc__.split("\n\n")[0])
    parser.add_argument("file", help="the department's file on this machine")
    parser.add_argument("--department", required=True, help="department id, e.g. pwd")
    parser.add_argument("--department-name", help="full name -- needed the first time a department is added")
    parser.add_argument("--dataset", required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--table", help="table this file describes")
    target.add_argument("--field-dictionary", action="store_true", help="the file describes several tables of the dataset")
    parser.add_argument("--format", choices=["postgres_ddl", "csv"], help="default: .csv -> csv, otherwise postgres_ddl")
    parser.add_argument("--schema", help="database schema name (default public)")
    parser.add_argument("--metadata", help="a business-metadata CSV for the table (descriptions, tags, ...)")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    args = parser.parse_args(argv)

    env = load_env()
    changes = add(
        storage_from_env(), args.catalog, args.file, args.department, args.dataset,
        table=args.table, department_name=args.department_name, file_format=args.format,
        schema=args.schema, metadata_file=args.metadata,
    )
    print("\n".join(f"  - {c}" for c in changes))
    if any(not c.startswith("uploaded") for c in changes):
        print(f"\ncatalog.yaml changed -- commit it and open a PR, then run: "
              f"ENVIRONMENT={env} python3 -m src.schema_registry.sync")
    else:
        print(f"\ncatalog.yaml already up to date -- just run: ENVIRONMENT={env} python3 -m src.schema_registry.sync")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
