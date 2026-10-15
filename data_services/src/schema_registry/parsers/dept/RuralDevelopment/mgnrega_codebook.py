"""Turn the MGNREGA codebook workbooks into Field Dictionary CSVs.

The Rural Development submission (Datasets/Manreaga/) is four codebook
workbooks describing one dataset, `mgnrega`. Each workbook holds three
sheets: `codebook` (Variable Name / Variable Description / Variable Type /
Unit Of Measurement / Unit Type), `metadata information` and `additional
information`. One workbook is one table, so the converter writes one Field
Dictionary CSV per workbook -- the exact shape parse_field_dictionary
already consumes -- and exposes the metadata sheets for the later `add`
step.

Variable Type values (text / integer / numeric) already match
field_dictionary_parser's FORMAT_TYPE_RULES, so the type is passed through
and validated there rather than remapped here. The unit of measurement,
which the dictionary format has no column for, is folded into the
description: "Applied Job Cards" + "In Lakh" -> "Applied Job Cards (In Lakh)".

The codebooks carry no Mandatory or Personal Data column, so both stay
blank: every column is nullable, and nothing is tagged PII (the variables
are gram-panchayat aggregates -- counts of job cards, workers, persondays
and expenditure -- never a person's record).

CLI, from data_services/:

    python -m src.schema_registry.parsers.dept.RuralDevelopment.mgnrega_codebook \
        --input ../Datasets/Manreaga --out-dir configs/field_dictionaries/mgnrega
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from src.schema_registry.parsers.field_dictionary_parser import parse_format_full
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEPARTMENT_ID = "rural_development_department"
DEPARTMENT_NAME = "Rural Development Department"
DATASET = "mgnrega"

# Exactly what parse_field_dictionary reads; the two codebook columns with
# no dictionary home (Unit Of Measurement / Unit Type) are folded in above.
OUTPUT_HEADERS = [
    "Dataset Name",
    "Dataset Field",
    "Data Description",
    "Format",
    "Mandatory (Y/N)",
    "Personal Data (Y/N)",
]

CODEBOOK_SHEET = "codebook"
METADATA_SHEET = "metadata information"
ADDITIONAL_SHEET = "additional information"

_CODEBOOK_HEADERS = ("Variable Name", "Variable Description", "Variable Type")

# Every workbook must describe the same scheme; a codebook claiming another
# dataset is a copy-paste the ingest must not silently absorb.
EXPECTED_DATASET_PREFIX = "MGNREGA"


@dataclass(frozen=True)
class CodebookConfig:
    file: str
    table: str
    resource: str


# The submission's own "Resource" label decides the table name (spaces and
# punctuation -> underscores); the file names are how the folder arrives.
TABLES: tuple[CodebookConfig, ...] = (
    CodebookConfig(
        file="category_wise_codebook.xlsx",
        table="category_wise_workers",
        resource="Category Wise Workers",
    ),
    CodebookConfig(
        file="codebook_employment_generated.xlsx",
        table="employment_generated",
        resource="Employment Generated",
    ),
    CodebookConfig(
        file="women_joint_acc_codebook.xlsx",
        table="women_joint_accounts",
        resource="Women Joint Accounts",
    ),
    CodebookConfig(
        file="work_structure_codebook.xlsx",
        table="work_structure",
        resource="Work Structure-wise Physical, Financial and Mandays Progress",
    ),
)


def _load_workbook(path: str | Path):
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("openpyxl is required to read the MGNREGA codebooks") from exc
    return openpyxl.load_workbook(str(path), read_only=True, data_only=True)


def _cell(row: tuple, index: int | None) -> str:
    if index is None or index >= len(row) or row[index] is None:
        return ""
    return str(row[index]).strip()


def _header_index(row: tuple) -> dict[str, int]:
    return {str(name).strip(): i for i, name in enumerate(row) if name is not None and str(name).strip()}


def _require_sheet(workbook, path: str | Path, name: str):
    if name not in workbook.sheetnames:
        raise ValueError(f"No '{name}' sheet in {path}. Sheets: {workbook.sheetnames}")
    return workbook[name]


def _sheet_pairs(sheet) -> dict[str, str]:
    """Read a key/value sheet (metadata / additional information) into a dict.

    Row 1 is the sheet's own title ("Metadata Information"), the rest are
    key/value pairs; blank keys and rows that repeat a header word are
    dropped, and the last value for a repeated key wins.
    """

    pairs: dict[str, str] = {}
    rows = list(sheet.iter_rows(values_only=True))
    for row in rows[1:]:
        key = _cell(row, 0)
        value = _cell(row, 1) if len(row) > 1 else ""
        if not key or key == _cell(rows[0], 0):
            continue
        pairs[key] = value
    return pairs


def read_metadata(workbook_path: str | Path) -> dict[str, str]:
    """The `metadata information` sheet: Dataset Name, Domains, About, ..."""

    workbook = _load_workbook(workbook_path)
    try:
        return _sheet_pairs(_require_sheet(workbook, workbook_path, METADATA_SHEET))
    finally:
        workbook.close()


def read_additional_info(workbook_path: str | Path) -> dict[str, str]:
    """The `additional information` sheet: Years Covered, coverage counts."""

    workbook = _load_workbook(workbook_path)
    try:
        return _sheet_pairs(_require_sheet(workbook, workbook_path, ADDITIONAL_SHEET))
    finally:
        workbook.close()


def _describe(description: str, unit: str) -> str:
    if not unit:
        return description
    return f"{description} ({unit})" if description else f"({unit})"


def read_codebook(workbook_path: str | Path, table: str) -> list[dict]:
    """One codebook's variables as OUTPUT_HEADERS-shaped dict rows.

    Raises when the sheet or a required header is missing, when a Variable
    Type has no rule in FORMAT_TYPE_RULES (a wrong type must not reach
    OpenMetadata), or when the sheet holds no variables at all.
    """

    workbook = _load_workbook(workbook_path)
    try:
        metadata = _sheet_pairs(_require_sheet(workbook, workbook_path, METADATA_SHEET))
        sheet = _require_sheet(workbook, workbook_path, CODEBOOK_SHEET)
        rows = list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()

    dataset_name = metadata.get("Dataset Name", "")
    if not dataset_name.upper().startswith(EXPECTED_DATASET_PREFIX):
        raise ValueError(
            f"{workbook_path}: metadata sheet says Dataset Name {dataset_name!r} -- "
            f"expected it to start with {EXPECTED_DATASET_PREFIX!r}"
        )

    header_at = next(
        (i for i, row in enumerate(rows) if any(str(c).strip() == "Variable Name" for c in row if c)),
        None,
    )
    if header_at is None:
        raise ValueError(f"{workbook_path}: no 'Variable Name' header row in the '{CODEBOOK_SHEET}' sheet")

    index = _header_index(rows[header_at])
    missing = [name for name in _CODEBOOK_HEADERS if name not in index]
    if missing:
        raise ValueError(
            f"{workbook_path}: codebook is missing column(s) {missing}. Headers found: {list(index)}"
        )

    records: list[dict] = []
    skipped = 0
    for row in rows[header_at + 1 :]:
        name = _cell(row, index["Variable Name"])
        description = _cell(row, index["Variable Description"])
        variable_type = _cell(row, index["Variable Type"])
        unit = _cell(row, index.get("Unit Of Measurement"))
        if not name:
            skipped += 1
            continue
        try:
            parse_format_full(variable_type)
        except ValueError:
            logger.error(f"mgnrega_codebook: {workbook_path} '{name}': unknown Variable Type '{variable_type}'")
            raise ValueError(
                f"{workbook_path}: variable '{name}' has unknown Variable Type {variable_type!r} -- "
                f"add a rule to FORMAT_TYPE_RULES in field_dictionary_parser.py or fix the codebook."
            ) from None
        records.append(
            {
                "Dataset Name": table,
                "Dataset Field": name,
                "Data Description": _describe(description, unit),
                "Format": variable_type,
                "Mandatory (Y/N)": "",
                "Personal Data (Y/N)": "",
            }
        )

    if not records:
        raise ValueError(f"{workbook_path}: codebook sheet holds no variables")
    if skipped:
        logger.warning(f"mgnrega_codebook: {workbook_path} skipped {skipped} row(s) with no variable name")
    return records


def _write_dictionary(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_HEADERS)
        writer.writeheader()
        writer.writerows(records)


def convert_codebook(workbook_path: str | Path, config: CodebookConfig, out_dir: str | Path) -> Path:
    """Convert one codebook workbook; returns the CSV path written."""

    records = read_codebook(workbook_path, config.table)
    path = Path(out_dir) / f"{config.table}.csv"
    _write_dictionary(path, records)
    logger.info(f"mgnrega_codebook: {config.file} -> {path.name} ({len(records)} field(s))")
    return path


def convert_all(input_dir: str | Path, out_dir: str | Path) -> dict[str, Path]:
    """Convert every codebook in TABLES found in `input_dir`; table -> CSV path.

    A missing workbook fails loudly -- the four are one dataset, and a
    silent three-table ingest would be worse than an error.
    """

    input_dir = Path(input_dir)
    written: dict[str, Path] = {}
    for config in TABLES:
        path = input_path_check(input_dir, config)
        written[config.table] = convert_codebook(path, config, out_dir)
    return written


def input_path_check(input_dir: Path, config: CodebookConfig) -> Path:
    path = input_dir / config.file
    if not path.exists():
        raise FileNotFoundError(f"Expected codebook {config.file} in {input_dir}, not found")
    return path


def write_combined_dictionary(input_dir: str | Path, out_path: str | Path) -> Path:
    """Write all four codebooks as ONE multi-table Field Dictionary CSV.

    This is the shape `add --field-dictionary` (README case D) and the
    catalog's `field_dictionary:` key consume: one file for the whole
    dataset, "Dataset Name" saying which of its tables a row belongs to.
    """

    input_dir = Path(input_dir)
    records: list[dict] = []
    for config in TABLES:
        records.extend(read_codebook(input_path_check(input_dir, config), config.table))
    out_path = Path(out_path)
    _write_dictionary(out_path, records)
    logger.info(f"mgnrega_codebook: combined -> {out_path.name} ({len(records)} field(s) / {len(TABLES)} table(s))")
    return out_path


def _config_for(path: Path) -> CodebookConfig:
    for config in TABLES:
        if config.file == path.name:
            return config
    raise ValueError(
        f"{path.name} is not a known MGNREGA codebook. Known files: {[c.file for c in TABLES]}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        required=True,
        help="the Manreaga folder (all four codebooks) or a single codebook workbook",
    )
    parser.add_argument("--out-dir", required=True, help="directory for one Field Dictionary CSV per table")
    parser.add_argument(
        "--combined",
        help="also write ONE multi-table Field Dictionary CSV here "
        "(the file `add --field-dictionary` takes; requires --input to be the folder)",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if input_path.is_dir():
        written = convert_all(input_path, args.out_dir)
        if args.combined:
            combined = write_combined_dictionary(input_path, args.combined)
            print(f"mgnrega (field dictionary) -> {combined}")
    else:
        if args.combined:
            parser.error("--combined needs --input to be the folder holding all four codebooks")
        config = _config_for(input_path)
        written = {config.table: convert_codebook(input_path, config, args.out_dir)}

    for table, path in written.items():
        print(f"{table} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
