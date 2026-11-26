"""Convert the Sericulture department's workbook templates to field dictionaries.

Each workbook describes one table. The output is a field-dictionary CSV that
``run_field_dictionary`` can consume. Example/sample-value columns are
deliberately excluded because these files describe schemas, not records.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)

OUTPUT_HEADERS = (
    "Dataset Name",
    "Dataset Field",
    "name_hindi",
    "Field Label (English)",
    "Data Description",
    "Format",
    "Length",
    "Mandatory (Y/N)",
    "Personal Data (Y/N)",
    "Unit",
    "Section",
    "Allowed Values",
    "Source Data Type",
    "Source Length / Format",
)


@dataclass(frozen=True)
class WorkbookConfig:
    filename: str
    dataset: str
    table: str
    merge_prefilled_fields: tuple[str, ...] = ()


_RESHAM_PREFILLED_FIELDS = (
    "beneficiary_name (Inferred)",
    "aadhar_number (Inferred)",
    "mobile_number (Inferred)",
)

WORKBOOKS = (
    WorkbookConfig("MPR.xlsx", "monthly_progress_report", "monthly_progress_report"),
    WorkbookConfig(
        "Mukhyamantri Resham Vikas Yojana.xlsx",
        "mukhyamantri_resham_vikas_yojana",
        "mukhyamantri_resham_vikas_yojana",
    ),
    WorkbookConfig(
        "Resham Mitra.xlsx", "resham_mitra", "resham_mitra",
        merge_prefilled_fields=_RESHAM_PREFILLED_FIELDS,
    ),
)

_HEADER_ALIASES = {
    "field": (
        "dataset_field_variable_column",
        "logical_field_name",
    ),
    "hindi": (
        "field_label_hindi",
        "field_label_hindi_regional_language",
        "field_label_hindi_regional_language",
    ),
    "english": ("field_label_english",),
    "description": (
        "data_field_column_description",
        "data_field_column_description",
        "description",
    ),
    "data_type": (
        "format_data_type",
        "data_type",
    ),
    "length": ("length", "max_length_format"),
    "mandatory": ("mandatory_y_n", "mandatory_yes_no"),
    "personal": ("personal_data_y_n", "personal_data_yes_no"),
    "unit": ("units", "unit", "unit_of_measure"),
    "section": ("section_group",),
    "allowed_values": ("allowed_values_master_dropdown_options",),
}

_HEADER_ROWS_TO_SKIP = {
    "exact_field_column_name",
    "field_name",
    "logical_field_name",
}


def _normalize_header(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _cell(row: tuple, index: int | None) -> str:
    if index is None or index >= len(row) or row[index] is None:
        return ""
    return str(row[index]).strip()


def _header_map(header: tuple, sheet_name: str) -> dict[str, int | None]:
    indexes = {
        _normalize_header(name): index
        for index, name in enumerate(header)
        if name is not None and str(name).strip()
    }
    mapped = {
        field: next((indexes[name] for name in aliases if name in indexes), None)
        for field, aliases in _HEADER_ALIASES.items()
    }
    missing = [field for field in ("field", "data_type") if mapped[field] is None]
    if missing:
        raise ValueError(
            f"Sheet '{sheet_name}' is missing required field(s) {missing}. "
            f"Headers found: {list(indexes)}"
        )
    return mapped


def _registry_format(data_type: str, length: str, *, row_number: int) -> str:
    """Map source type hints to a parser-supported format without guessing IDs as numbers."""

    text = re.sub(r"\s+", " ", data_type).strip()
    lowered = text.lower()
    if not text:
        raise ValueError(f"Row {row_number}: data type is blank")

    if "decimal" in lowered or "numeric" in lowered:
        normalized_type = "Decimal"
    elif re.search(r"\b(integer|int)\b", lowered):
        normalized_type = "Integer"
    elif re.search(r"\bboolean\b", lowered) and "multi-select" not in lowered:
        normalized_type = "Boolean"
    elif re.search(r"\bnumber\b", lowered) and "text" not in lowered:
        normalized_type = "Numeric"
    elif any(
        token in lowered
        for token in ("varchar", "character", "text", "string", "dropdown", "option", "file", "image", "checkbox")
    ):
        normalized_type = "Text"
    else:
        raise ValueError(
            f"Row {row_number}: unsupported source data type {data_type!r}; "
            "add an explicit mapping before converting"
        )

    size = re.sub(r"\s+", " ", length).strip()
    already_sized = re.search(r"\(\s*\d+\s*(?:,\s*\d+)?", text)
    if size and not already_sized:
        return f"{normalized_type} ({size})"
    return normalized_type if not already_sized else f"{normalized_type} {text[text.find('('):]}"


def _sheet_records(sheet, config: WorkbookConfig) -> list[dict[str, str]]:
    rows = sheet.iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration as exc:
        raise ValueError(f"Sheet '{sheet.title}' is empty") from exc

    indexes = _header_map(header, sheet.title)
    records: list[dict[str, str]] = []
    current_section = ""
    for row_number, row in enumerate(rows, start=2):
        section = _cell(row, indexes["section"])
        if section:
            current_section = section

        field_name = _cell(row, indexes["field"])
        if not field_name or _normalize_header(field_name) in _HEADER_ROWS_TO_SKIP:
            continue

        data_type = _cell(row, indexes["data_type"])
        length = _cell(row, indexes["length"])
        registry_format = _registry_format(data_type, length, row_number=row_number)
        records.append(
            {
                "Dataset Name": config.table,
                "Dataset Field": field_name,
                "name_hindi": _cell(row, indexes["hindi"]),
                "Field Label (English)": _cell(row, indexes["english"]),
                "Data Description": _cell(row, indexes["description"]),
                "Format": registry_format,
                "Length": length,
                "Mandatory (Y/N)": _cell(row, indexes["mandatory"]),
                "Personal Data (Y/N)": _cell(row, indexes["personal"]),
                "Unit": _cell(row, indexes["unit"]),
                "Section": current_section,
                "Allowed Values": _cell(row, indexes["allowed_values"]),
                "Source Data Type": data_type,
                "Source Length / Format": length,
            }
        )

    if not records:
        raise ValueError(f"Sheet '{sheet.title}' contains no field rows")

    if config.merge_prefilled_fields:
        records = _merge_prefilled_fields(records, config)

    duplicates = sorted(name for name, count in Counter(r["Dataset Field"] for r in records).items() if count > 1)
    if duplicates:
        logger.warning(
            f"{config.filename}: duplicate field name(s) retained for review: {', '.join(duplicates)}. "
            "Do not sync this table until each duplicate is assigned to the correct table or renamed."
        )
    return records


def _merge_prefilled_fields(
    records: list[dict[str, str]], config: WorkbookConfig
) -> list[dict[str, str]]:
    """Collapse documented repeats of registration fields pre-filled in applications."""

    grouped: dict[str, list[dict[str, str]]] = {}
    for record in records:
        grouped.setdefault(record["Dataset Field"], []).append(record)

    merged: list[dict[str, str]] = []
    invariant_fields = (
        "Format",
        "Length",
        "Mandatory (Y/N)",
        "Personal Data (Y/N)",
        "Unit",
        "Allowed Values",
        "Source Data Type",
        "Source Length / Format",
    )
    for field_name, group in grouped.items():
        if len(group) == 1 or field_name not in config.merge_prefilled_fields:
            merged.extend(group)
            continue
        for field in invariant_fields:
            if len({record[field] for record in group}) != 1:
                raise ValueError(
                    f"{config.filename}: repeated field {field_name!r} has conflicting {field} values"
                )
        combined = dict(group[0])
        for field in ("name_hindi", "Field Label (English)", "Data Description"):
            values = list(dict.fromkeys(record[field] for record in group if record[field]))
            combined[field] = " / ".join(values)
        merged.append(combined)
    return merged


def _load_workbook(path: str | Path):
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("openpyxl is required to read Sericulture workbooks") from exc
    return openpyxl.load_workbook(str(path), read_only=True, data_only=True)


def convert_workbook(
    workbook_path: str | Path,
    out_dir: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write one workbook as a normalized, sample-free field-dictionary CSV."""

    workbook_path = Path(workbook_path)
    config = next((item for item in WORKBOOKS if item.filename == workbook_path.name), None)
    if config is None:
        raise ValueError(
            f"No Sericulture workbook mapping for '{workbook_path.name}'. "
            f"Expected one of: {', '.join(item.filename for item in WORKBOOKS)}"
        )

    output = Path(out_dir) / f"{config.dataset}.csv"
    if output.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite {output}; pass overwrite=True to replace it")

    workbook = _load_workbook(workbook_path)
    try:
        if len(workbook.worksheets) != 1:
            raise ValueError(
                f"{workbook_path.name} has {len(workbook.worksheets)} sheets; "
                "add an explicit sheet-to-table mapping before converting"
            )
        records = _sheet_records(workbook.worksheets[0], config)
    finally:
        workbook.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)

    logger.info(
        f"sericulture_xlsx: '{workbook_path.name}' -> '{output.name}' "
        f"({len(records)} field(s); sample/example values excluded)"
    )
    return output


def convert_all(
    input_dir: str | Path,
    out_dir: str | Path,
    *,
    overwrite: bool = False,
) -> dict[str, Path]:
    """Convert all three expected workbooks, refusing a partial input set."""

    input_dir = Path(input_dir)
    sources: dict[str, Path] = {}
    for config in WORKBOOKS:
        matches = list(input_dir.rglob(config.filename))
        if len(matches) != 1:
            raise FileNotFoundError(
                f"Expected exactly one {config.filename} under {input_dir}; found {len(matches)}"
            )
        sources[config.dataset] = matches[0]

    if not overwrite:
        existing = [
            Path(out_dir) / f"{dataset}.csv"
            for dataset in sources
            if (Path(out_dir) / f"{dataset}.csv").exists()
        ]
        if existing:
            raise FileExistsError(
                "Refusing to overwrite existing output(s): " + ", ".join(map(str, existing))
            )

    return {
        dataset: convert_workbook(source, out_dir, overwrite=overwrite)
        for dataset, source in sources.items()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, help="directory containing the three Sericulture workbooks")
    parser.add_argument("--out-dir", required=True, help="directory for normalized field-dictionary CSVs")
    parser.add_argument("--overwrite", action="store_true", help="replace existing converted CSVs")
    args = parser.parse_args(argv)

    for dataset, path in convert_all(args.input_dir, args.out_dir, overwrite=args.overwrite).items():
        print(f"{dataset} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
