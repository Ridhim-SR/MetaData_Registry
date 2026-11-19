from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

from src.schema_registry.parsers.irrigation_parser import (
    parse_irrigation_field_dictionary,
)
from src.schema_registry.parsers.irrigation_xlsx import (
    FLOOD_WORKBOOK,
    MONITORING_WORKBOOK,
    NON_DATA_SHEETS,
    OPEN_ACCESS_WORKBOOK,
    SKIPPED_SHEETS,
    WORKBOOKS,
    DatasetConfig,
    _MONITORING_DATASETS,
    convert_workbook,
    load_descriptions,
)

DELIVERY = (
    Path(__file__).resolve().parents[2]
    / "Datasets"
    / "Irrigation Dept"
    / "Irrigation"
    / "Irrigation"
)
REAL = pytest.mark.skipif(
    not all((DELIVERY / name).exists() for name in WORKBOOKS),
    reason=f"{DELIVERY} is gitignored or incomplete",
)

# Field counts read off each workbook's own "No. of fields" column / sheet
# rows. They guard the converter against a shifted header silently dropping a
# field. Dataset -> table -> columns; a single-table dataset repeats its id.
EXPECTED = {
    "irrigation_target_and_achievement": {"irrigation_target_and_achievement": 22},
    "chief_minister_reference_cases_tracking": {"chief_minister_reference_cases_tracking": 13},
    "public_representatives_reference_cases_status": {
        "public_representatives_reference_cases_status": 12
    },
    "jal_shakti_minister_reference_cases_status": {
        "jal_shakti_minister_reference_cases_status": 14
    },
    "tail_end_canal_water_supply_progress": {"tail_end_canal_water_supply_progress": 18},
    "canal_desilting_progress": {"canal_desilting_progress": 22},
    "inspection_buildings": {"inspection_buildings": 23},
    "organization_wise_revenue_collection": {"organization_wise_revenue_collection": 40},
    "budget_allocation_major_heads_4700_4701": {
        "budget_allocation_major_heads_4700_4701": 21
    },
    "illegal_activities_fir": {"illegal_activities_fir": 14},
    "ponds_and_water_bodies_development_progress": {
        "ponds_and_water_bodies_development_progress": 28
    },
    "national_green_tribunal_case_tracking": {
        "national_green_tribunal_case_tracking": 13
    },
    "mgnrega_irrigation_works": {"mgnrega_irrigation_works": 16},
    "inspection_reports": {"inspection_reports": 17},
    "open_access_portals": {
        "Irrigation System Portal": 14,
        "Contractor Management": 9,
    },
    "flood_bulletin": {
        "Abtract_Daily_Flood": 25,
        "Daily River Level & Flood Info": 14,
        "Rainfall Information P-2": 15,
    },
}


@REAL
def test_roster_covers_every_sheet_once():
    assert set(WORKBOOKS) == {MONITORING_WORKBOOK, OPEN_ACCESS_WORKBOOK, FLOOD_WORKBOOK}

    for workbook_name, datasets in WORKBOOKS.items():
        workbook = openpyxl.load_workbook(DELIVERY / workbook_name, read_only=True)
        try:
            covered = {sheet for config in datasets for sheet in config.sheets}
            unaccounted = (
                set(workbook.sheetnames) - covered - NON_DATA_SHEETS - SKIPPED_SHEETS
            )
        finally:
            workbook.close()
        assert not unaccounted, f"{workbook_name}: sheet(s) not in the roster: {unaccounted}"

    assert SKIPPED_SHEETS == {"S17"}


@REAL
def test_monitoring_roster_matches_the_index_sheet():
    workbook = openpyxl.load_workbook(DELIVERY / MONITORING_WORKBOOK, read_only=True)
    try:
        rows = workbook["Index"].iter_rows(values_only=True)
        header = [str(cell).strip() if cell else "" for cell in next(rows)]
        name_at = header.index("Dataset Name")
        indexed = {
            str(row[name_at]).strip()
            for row in rows
            if row[name_at] and str(row[name_at]).strip()
        }
    finally:
        workbook.close()

    # S17 is catalogued already; every other dataset the Index names must be
    # exported by this delivery.
    assert indexed - {"Restoration and Renovation Works Dataset"} == {
        config.name for config in _MONITORING_DATASETS
    }


@REAL
def test_converts_every_dataset_and_parses_back(tmp_path):
    written = {}
    for workbook_name in WORKBOOKS:
        written.update(convert_workbook(DELIVERY / workbook_name, tmp_path))

    assert set(written) == set(EXPECTED)
    assert "restoration_and_renovation_works" not in written

    for dataset, expected_tables in EXPECTED.items():
        text = written[dataset].read_text(encoding="utf-8")
        tables = parse_irrigation_field_dictionary(
            text, label=str(written[dataset]), default_table_name=dataset
        )
        assert {name: len(t["columns"]) for name, t in tables.items()} == expected_tables
        for table in tables.values():
            assert all(column["name"] for column in table["columns"])
            assert all(column["data_type"] for column in table["columns"])


@REAL
def test_converted_rows_keep_descriptions_and_pii(tmp_path):
    written = convert_workbook(DELIVERY / OPEN_ACCESS_WORKBOOK, tmp_path)
    tables = parse_irrigation_field_dictionary(
        written["open_access_portals"].read_text(encoding="utf-8"),
        default_table_name="open_access_portals",
    )
    contractor = tables["Contractor Management"]

    assert all(
        meta["business_description"] for meta in contractor["business_metadata"].values()
    )
    assert contractor["business_metadata"]["contractor_firm_name_address"][
        "classification"
    ] == "PII"
    assert all(
        meta["classification"] == ""
        for name, meta in contractor["business_metadata"].items()
        if name != "contractor_firm_name_address"
    )


MONITORING_HEADERS = (
    "Dataset Name",
    "Name",
    "Name (Hindi)",
    "Data Format",
    "Maximum Size",
    "Mandatory",
    "Values",
    "Default Value",
    "Contains Personal Data",
    "Access Level Classification",
    "Validations",
    "Tags",
    "Remarks / Comments",
)


def _monitoring_workbook(tmp_path: Path, headers, rows):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "2nd"
    sheet.append(list(headers))
    for row in rows:
        sheet.append(list(row))
    path = tmp_path / MONITORING_WORKBOOK
    workbook.save(path)
    return path


def _description_file(tmp_path: Path, rows) -> Path:
    path = tmp_path / "descriptions.csv"
    path.write_text(
        "dataset,field,description,name_hindi\n"
        + "".join(",".join(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def test_blank_description_is_filled_from_the_review_file(tmp_path):
    # The 2026-11 monitoring sheets carry the Hindi label where a description
    # belongs and no English description at all.
    workbook = _monitoring_workbook(
        tmp_path,
        MONITORING_HEADERS,
        [("Dataset", "khand", "खंड", "select (dropdown)")],
    )
    descriptions = load_descriptions(
        _description_file(
            tmp_path,
            [("dataset_id", "khand", "Canal division of the entry.", "खंड")],
        )
    )

    written = convert_workbook(
        workbook,
        tmp_path,
        datasets=(DatasetConfig("dataset_id", "Dataset Name", ("2nd",)),),
        descriptions=descriptions,
        require_descriptions=True,
    )

    text = written["dataset_id"].read_text(encoding="utf-8")
    assert "Canal division of the entry." in text
    assert "खंड" in text


def test_department_description_is_never_overwritten(tmp_path):
    workbook = _monitoring_workbook(
        tmp_path,
        MONITORING_HEADERS[:2] + ("Description",) + MONITORING_HEADERS[3:],
        [("Dataset", "khand", "Canal division as supplied.", "text")],
    )
    written = convert_workbook(
        workbook,
        tmp_path,
        datasets=(DatasetConfig("dataset_id", "Dataset Name", ("2nd",)),),
        descriptions={("dataset_id", "khand"): "Replacement text."},
        require_descriptions=True,
    )

    text = written["dataset_id"].read_text(encoding="utf-8")
    assert "Canal division as supplied." in text
    assert "Replacement text." not in text


def test_require_descriptions_refuses_a_blank_field(tmp_path):
    workbook = _monitoring_workbook(
        tmp_path,
        MONITORING_HEADERS,
        [
            ("Dataset", "khand", "खंड", "text"),
            ("Dataset", "entryDate", "प्रविष्टि की दिनांक", "date"),
        ],
    )

    with pytest.raises(ValueError, match="entryDate"):
        convert_workbook(
            workbook,
            tmp_path,
            datasets=(DatasetConfig("dataset_id", "Dataset Name", ("2nd",)),),
            descriptions={("dataset_id", "khand"): "Canal division."},
            require_descriptions=True,
        )
    # The partial dataset must not be left behind for a later upload.
    assert not (tmp_path / "dataset_id.csv").exists()


def test_load_descriptions_skips_incomplete_rows(tmp_path):
    descriptions = load_descriptions(
        _description_file(
            tmp_path,
            [
                ("dataset_id", "khand", "Canal division.", "खंड"),
                ("dataset_id", "entryDate", "", "प्रविष्टि की दिनांक"),
                ("", "status", "Orphan row.", "Status"),
            ],
        )
    )

    assert descriptions == {("dataset_id", "khand"): "Canal division."}


PORTAL_HEADERS = (
    "Dataset Name",
    "Table Name",
    "Dataset Field/Variable/Column",
    "Field Label (Hindi/Regional Language)",
    "Field Label (English)",
    "Data/Field/Column Description",
    "Format/Data Type",
    "Mandatory (Y/N)",
)


def _portal_workbook(tmp_path: Path, rows):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(list(PORTAL_HEADERS))
    for row in rows:
        sheet.append(list(row))
    path = tmp_path / "Flood Bulletin (OA).xlsx"
    workbook.save(path)
    return path


def _portal_dataset():
    return (DatasetConfig("flood_bulletin", "Flood Bulletin", ("Sheet1",)),)


def test_strict_descriptions_refuses_a_misspelled_table_name(tmp_path):
    workbook = _portal_workbook(
        tmp_path,
        [
            (
                "Flood Bulletin",
                "Abtract_Daily_Flood",
                "river_name",
                "नदी का नाम",
                "River Name",
                "Name of the river.",
                "Varchar",
                "Y",
            )
        ],
    )

    with pytest.raises(ValueError, match="Abtract"):
        convert_workbook(
            workbook,
            tmp_path,
            datasets=_portal_dataset(),
            strict_descriptions=True,
        )
    assert not (tmp_path / "flood_bulletin.csv").exists()


def test_strict_descriptions_refuses_a_repeated_word(tmp_path):
    workbook = _portal_workbook(
        tmp_path,
        [
            (
                "Flood Bulletin",
                "Daily Flood",
                "ppa_kharif_ha",
                "पीपीए खरीफ",
                "PPA Kharif (ha)",
                "Proposed Potential Area proposed for irrigation during the Kharif crop season.",
                "Integer",
                "Y",
            )
        ],
    )

    with pytest.raises(ValueError, match="repeated-word"):
        convert_workbook(
            workbook,
            tmp_path,
            datasets=_portal_dataset(),
            strict_descriptions=True,
        )


def test_text_quality_problems_only_warn_without_strict(tmp_path):
    workbook = _portal_workbook(
        tmp_path,
        [
            (
                "Flood Bulletin",
                "Abtract_Daily_Flood",
                "river_name",
                "नदी का नाम",
                "River Name",
                "Name of the river.",
                "Varchar",
                "Y",
            )
        ],
    )

    written = convert_workbook(workbook, tmp_path, datasets=_portal_dataset())

    assert written["flood_bulletin"].read_text(encoding="utf-8").count("Abtract") == 1
