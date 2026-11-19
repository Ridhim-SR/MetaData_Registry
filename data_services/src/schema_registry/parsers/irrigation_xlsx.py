"""Turn the Irrigation Department's workbook delivery into Field Dictionary CSVs.

Three workbooks make up the 2026-11 delivery:

* ``Monitoring_Management_System_Details.xlsx`` -- one data sheet per
  monitoring dataset (``Index`` is the roster, not data);
* ``Open_Access_Portals.xlsx`` -- two tables that belong to one portal
  dataset; and
* ``Flood Bulletin (OA).xlsx`` -- three tables that belong to one bulletin
  dataset.

Each dataset is written as one CSV in the shape ``irrigation_parser`` reads.
The output keeps both layouts' headers (the parser's alias tuples are the
single source of truth for those spellings) and adds nothing the department
did not state. ``Sample Value`` is dropped on purpose: one contractor row
contains a firm's name and street address, and a field dictionary is not the
place for an example record. ``Index`` and ``S17`` are not exported -- S17
(``restoration_and_renovation_works``) was onboarded earlier and must not be
re-ingested by this delivery.

Sheet -> dataset ownership is the workbook's own ``Index`` sheet: it names
every dataset and lists the sheet that describes it. ``DATASETS`` records
that roster next to the converter so it can be reviewed; the test suite reads
the Index sheet back to prove the roster still covers it.

Every description, table name and field name is run through
``text_quality`` before it is written, because the catalogue copies text
verbatim and a typo in the workbook becomes a published typo. Problems are
logged; ``strict_descriptions`` additionally refuses the dataset.
"""

import argparse
import csv
from pathlib import Path
from typing import NamedTuple

from src.schema_registry.text_quality import ERROR, Issue, lint_identifier, lint_text
from src.utils.logger import get_logger

logger = get_logger(__name__)

MONITORING_WORKBOOK = "Monitoring_Management_System_Details.xlsx"
OPEN_ACCESS_WORKBOOK = "Open_Access_Portals.xlsx"
FLOOD_WORKBOOK = "Flood Bulletin (OA).xlsx"

# Columns the converted CSV carries. It is the union of both department
# layouts: `Dataset Field/Variable/Column`, `Format/Data Type`, ... from the
# portal/bulletin workbooks, and `Default Value`/`Validations`/`Tags` from the
# monitoring workbooks. `Sample Value` is deliberately absent.
OUTPUT_HEADERS = (
    "Dataset Name",
    "Table Name",
    "Dataset Field/Variable/Column",
    "Field Label (Hindi/Regional Language)",
    "Field Label (English)",
    "Data/Field/Column Description",
    "Format/Data Type",
    "Length",
    "Allowed Code sets/values",
    "Reference/Relationship with other key (Foreign Key)",
    "Source Table",
    "Mandatory (Y/N)",
    "Personal Data (Y/N)",
    "Availability (Public/internal)",
    "Default Value",
    "Validations",
    "Tags",
    "Notes",
)

# Output header -> the source spellings it can come from, most specific first.
# A header not listed here is read by its own name.
_SOURCE_ALIASES = {
    "Dataset Field/Variable/Column": (
        "Dataset Field/Variable/Column",
        "Name",
        "Dataset Field",
    ),
    "Field Label (Hindi/Regional Language)": (
        "Field Label (Hindi/Regional Language)",
        "Name (Hindi)",
        "Hindi Name",
    ),
    "Data/Field/Column Description": (
        "Data/Field/Column Description",
        "Description",
        "Data Description",
    ),
    "Format/Data Type": ("Format/Data Type", "Data Format", "Format"),
    "Length": ("Length", "Maximum Size"),
    "Allowed Code sets/values": ("Allowed Code sets/values", "Values"),
    "Mandatory (Y/N)": ("Mandatory (Y/N)", "Mandatory"),
    "Personal Data (Y/N)": ("Personal Data (Y/N)", "Contains Personal Data"),
    "Notes": ("Notes", "Remarks / Comments"),
}


class DatasetConfig(NamedTuple):
    dataset: str
    name: str
    sheets: tuple[str, ...]


# The Index sheet's roster, minus Restoration and Renovation Works (S17):
# that dataset is already catalogued and this delivery only adds the missing
# tables. Dataset ids drop the trailing "Dataset" the department writes, the
# same convention as `restoration_and_renovation_works`.
_MONITORING_DATASETS: tuple[DatasetConfig, ...] = (
    DatasetConfig(
        "irrigation_target_and_achievement",
        "Irrigation Target and Achievement Dataset",
        ("2nd",),
    ),
    DatasetConfig(
        "chief_minister_reference_cases_tracking",
        "Chief Minister Reference Cases Tracking Dataset",
        ("S13_1",),
    ),
    DatasetConfig(
        "public_representatives_reference_cases_status",
        "Public Representatives Reference Cases Status Dataset",
        ("S13_3",),
    ),
    DatasetConfig(
        "jal_shakti_minister_reference_cases_status",
        "Jal Shakti Minister Reference Cases Status Dataset",
        ("S132",),
    ),
    DatasetConfig(
        "tail_end_canal_water_supply_progress",
        "Tail-End Canal Water Supply Progress Dataset",
        ("S14",),
    ),
    DatasetConfig(
        "canal_desilting_progress",
        "Canal Desilting Progress Dataset",
        ("S16",),
    ),
    DatasetConfig(
        "inspection_buildings",
        "Inspection Buildings Dataset",
        ("S18",),
    ),
    DatasetConfig(
        "organization_wise_revenue_collection",
        "Organization-wise Revenue Collection Dataset",
        ("S19",),
    ),
    DatasetConfig(
        "budget_allocation_major_heads_4700_4701",
        "Budget Allocation Dataset (Major Heads 4700/4701)",
        ("SNO5",),
    ),
    DatasetConfig(
        "illegal_activities_fir",
        "Illegal Activities FIR Dataset",
        ("SNO8",),
    ),
    DatasetConfig(
        "ponds_and_water_bodies_development_progress",
        "Ponds and Water Bodies Development Progress Dataset",
        ("SNo10",),
    ),
    DatasetConfig(
        "national_green_tribunal_case_tracking",
        "National Green Tribunal Case Tracking Dataset",
        ("SNo11",),
    ),
    DatasetConfig(
        "mgnrega_irrigation_works",
        "MGNREGA Irrigation Works Dataset",
        ("SNo12",),
    ),
    DatasetConfig(
        "inspection_reports",
        "Inspection Reports Dataset",
        ("parpatr9",),
    ),
)

_OPEN_ACCESS_DATASETS: tuple[DatasetConfig, ...] = (
    DatasetConfig(
        "open_access_portals",
        "Open Access Portals",
        ("Irrigation_System", "Contractor_Management"),
    ),
)

_FLOOD_DATASETS: tuple[DatasetConfig, ...] = (
    DatasetConfig(
        "flood_bulletin",
        "Flood Bulletin",
        (
            "Abtract_Daily_Flood",
            "Daily River Level & Flood Info",
            "Daily Rainfall Info",
        ),
    ),
)

# Workbook file name -> the datasets it contains. This is also the sheet
# roster the test suite checks against the real workbooks.
WORKBOOKS: dict[str, tuple[DatasetConfig, ...]] = {
    MONITORING_WORKBOOK: _MONITORING_DATASETS,
    OPEN_ACCESS_WORKBOOK: _OPEN_ACCESS_DATASETS,
    FLOOD_WORKBOOK: _FLOOD_DATASETS,
}

# Sheets that are roster/cover pages, never data.
NON_DATA_SHEETS = frozenset({"Index"})

# Already catalogued from the previous delivery -- see _MONITORING_DATASETS.
SKIPPED_SHEETS = frozenset({"S17"})


def _load_workbook(path: str | Path):
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("openpyxl is required to read Irrigation workbooks") from exc
    return openpyxl.load_workbook(str(path), read_only=True, data_only=True)


def _cell(row: tuple, index: int | None) -> str:
    if index is None or index >= len(row) or row[index] is None:
        return ""
    return str(row[index]).strip()


def _header_index(header: tuple) -> dict[str, int]:
    return {
        str(name).strip(): i
        for i, name in enumerate(header)
        if name is not None and str(name).strip()
    }


def _sheet_rows(sheet) -> tuple[list[dict[str, str]], int]:
    """One sheet's rows keyed by the output headers, plus skipped-row count."""

    rows = sheet.iter_rows(values_only=True)
    try:
        source_header = next(rows)
    except StopIteration:
        raise ValueError(f"Sheet '{sheet.title}' is empty -- no header row")

    index = _header_index(source_header)
    field_headers = _SOURCE_ALIASES["Dataset Field/Variable/Column"]
    if not any(name in index for name in field_headers):
        raise ValueError(
            f"Sheet '{sheet.title}' has no field-name column "
            f"({' / '.join(field_headers)}). Headers found: {list(index)}"
        )

    def source_index(output_header: str) -> int | None:
        for name in _SOURCE_ALIASES.get(output_header, (output_header,)):
            if name in index:
                return index[name]
        return None

    positions = {name: source_index(name) for name in OUTPUT_HEADERS}
    records: list[dict[str, str]] = []
    skipped = 0
    for row in rows:
        record = {name: _cell(row, positions[name]) for name in OUTPUT_HEADERS}
        if not any(record.values()):
            # Spreadsheet applications report a large used range; a row with
            # nothing in any mapped column is formatting, not data.
            continue
        if not record["Dataset Field/Variable/Column"]:
            skipped += 1
            continue
        records.append(record)
    return records, skipped


def load_descriptions(path: str | Path) -> dict[tuple[str, str], str]:
    """Read dataset/field -> English description from a review CSV.

    Expected columns: ``dataset``, ``field``, ``description``. Extra columns
    (e.g. the Hindi label for review) are ignored. A blank description is not
    stored, so it cannot erase a department-provided one.
    """

    descriptions: dict[tuple[str, str], str] = {}
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            dataset = (row.get("dataset") or "").strip()
            field = (row.get("field") or "").strip()
            description = (row.get("description") or "").strip()
            if dataset and field and description:
                descriptions[(dataset, field)] = description
    return descriptions


def _write_dataset(path: Path, name: str, records: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_HEADERS)
        writer.writeheader()
        for record in records:
            record["Dataset Name"] = name
            writer.writerow(record)


def convert_workbook(
    workbook_path: str | Path,
    out_dir: str | Path,
    datasets: tuple[DatasetConfig, ...] | None = None,
    descriptions: dict[tuple[str, str], str] | None = None,
    require_descriptions: bool = False,
    strict_descriptions: bool = False,
) -> dict[str, Path]:
    """Write one Field Dictionary CSV per dataset; returns dataset -> path.

    ``descriptions`` fills a blank ``Data/Field/Column Description`` (keyed by
    ``(dataset, field)``) and never overwrites a description the department
    supplied. With ``require_descriptions``, a dataset that still has a blank
    description is refused rather than published without one. Every written
    description and identifier is checked by ``text_quality``; issues are
    logged, and ``strict_descriptions`` turns the errors into a refusal.
    """

    workbook_path = Path(workbook_path)
    if datasets is None:
        datasets = WORKBOOKS.get(workbook_path.name)
        if datasets is None:
            raise ValueError(
                f"No dataset roster for '{workbook_path.name}'. Known workbooks: "
                f"{', '.join(WORKBOOKS)}"
            )

    out_dir = Path(out_dir)
    workbook = _load_workbook(workbook_path)
    written: dict[str, Path] = {}
    used: set[tuple[str, str]] = set()
    try:
        for config in datasets:
            records: list[dict[str, str]] = []
            skipped = 0
            for sheet_name in config.sheets:
                if sheet_name not in workbook.sheetnames:
                    raise ValueError(
                        f"No sheet '{sheet_name}' in workbook. "
                        f"Sheets: {workbook.sheetnames}"
                    )
                sheet_records, sheet_skipped = _sheet_rows(workbook[sheet_name])
                records.extend(sheet_records)
                skipped += sheet_skipped
            if not records:
                raise ValueError(
                    f"Dataset '{config.dataset}' produced no field rows from "
                    f"sheet(s) {list(config.sheets)}"
                )

            missing: list[str] = []
            for record in records:
                field = record["Dataset Field/Variable/Column"]
                if not record["Data/Field/Column Description"] and descriptions:
                    description = descriptions.get((config.dataset, field), "")
                    if description:
                        record["Data/Field/Column Description"] = description
                        used.add((config.dataset, field))
                if require_descriptions and not record["Data/Field/Column Description"]:
                    missing.append(field)
            if missing:
                raise ValueError(
                    f"Dataset '{config.dataset}' has {len(missing)} field(s) without "
                    f"a description: {', '.join(missing)}"
                )

            problems: dict[tuple[str, str], Issue] = {}
            for record in records:
                field = record["Dataset Field/Variable/Column"]
                table = record["Table Name"] or config.dataset
                description = record["Data/Field/Column Description"]
                checks = (
                    (f"table '{table}'", lint_identifier(table)),
                    (f"field '{field}'", lint_identifier(field)),
                    (
                        f"field '{field}' description",
                        lint_text(description, label=record["Field Label (English)"]),
                    ),
                )
                for location, issues in checks:
                    for issue in issues:
                        problems.setdefault((location, f"{issue.kind}:{issue.text}"), issue)
            if problems:
                for (location, _), issue in problems.items():
                    logger.warning(
                        f"irrigation_xlsx: {config.dataset}: {location}: {issue}"
                    )
                errors = [issue for issue in problems.values() if issue.severity == ERROR]
                if strict_descriptions and errors:
                    sample = "; ".join(str(issue) for issue in errors[:5])
                    raise ValueError(
                        f"Dataset '{config.dataset}' has {len(errors)} text-quality "
                        f"error(s): {sample}"
                    )

            path = out_dir / f"{config.dataset}.csv"
            _write_dataset(path, config.name, records)
            written[config.dataset] = path
            logger.info(
                f"irrigation_xlsx: '{workbook_path.name}' -> {path.name} "
                f"({len(records)} field(s), {skipped} skipped row(s))"
            )
    finally:
        workbook.close()

    if descriptions:
        unused = set(descriptions) - used
        if unused:
            logger.warning(
                f"irrigation_xlsx: {len(unused)} description(s) matched no field "
                f"in '{workbook_path.name}' (kept for another workbook): "
                f"{sorted(unused)[:5]}"
            )
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="one of the three delivery workbooks")
    parser.add_argument("--out-dir", required=True, help="directory for the dataset CSV(s)")
    parser.add_argument(
        "--descriptions",
        help="review CSV (dataset,field,description) for columns the source leaves blank",
    )
    parser.add_argument(
        "--require-descriptions",
        action="store_true",
        help="refuse to write a dataset if any field still has no description",
    )
    parser.add_argument(
        "--strict-descriptions",
        action="store_true",
        help="refuse to write a dataset whose descriptions or identifiers fail the text-quality checks",
    )
    args = parser.parse_args(argv)

    descriptions = load_descriptions(args.descriptions) if args.descriptions else None
    for dataset, path in convert_workbook(
        args.input,
        args.out_dir,
        descriptions=descriptions,
        require_descriptions=args.require_descriptions,
        strict_descriptions=args.strict_descriptions,
    ).items():
        print(f"{dataset} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
