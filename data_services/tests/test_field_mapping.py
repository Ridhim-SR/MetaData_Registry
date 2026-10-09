import pytest

from src.schema_registry.mapping import report
from src.schema_registry.registry import lookups, paths

TS = "20260101T000000000000Z"


def _column(name, data_type="character varying", length=None, scale=None, nullable=True, description="", tag=""):
    return {
        "table_id": "placeholder",
        "name": name,
        "data_type": data_type,
        "length": "" if length is None else str(length),
        "scale": "" if scale is None else str(scale),
        "nullable": str(nullable),
        "business_description": description,
        "tag": tag,
        "classification": "Internal",
    }


def _seed_table(storage, department, dataset, table, columns):
    lookups.register_department(storage, department, department)
    lookups.upsert_dataset(storage, f"{department}.{dataset}", department, dataset)
    lookups.upsert_table(storage, f"{department}.{dataset}.{table}", f"{department}.{dataset}", table, "public")
    path = paths.curated_schema_path(department, dataset, table, TS)
    storage.write_csv(path, columns)
    return f"{department}.{dataset}.{table}"


@pytest.fixture
def catalog_storage(tmp_path):
    from src.storage.local import LocalObjectStorage

    storage = LocalObjectStorage(tmp_path / "storage")
    _seed_table(
        storage,
        "agri_dept",
        "farmers",
        "farmers",
        [
            _column("district_name", description="Revenue district", tag="Geospatial"),
            _column("start_date", data_type="date", nullable=False),
            _column("project_budget_amount", data_type="numeric", length=18, scale=2),
        ],
    )
    _seed_table(
        storage,
        "public_works_department",
        "vishwakarma",
        "vishwakarma_T",
        [
            _column("dist_code", length=100),
            _column("tender_cost", data_type="double precision", tag="Financial"),
        ],
    )
    return storage


def _ddl_text() -> str:
    return (
        "district_name character varying(100), work_start_date date, tender_cost double precision NOT NULL, "
        "budget_code character varying(50)"
    )


# --- helpers -----------------------------------------------------------


def test_normalize_strips_case_and_punctuation():
    assert report.normalize("District Name") == "district_name".replace("_", "")


def test_tokens_split_on_anything_non_alphanumeric():
    assert report.tokens("work_start_date") == {"work", "start", "date"}


def test_missing_attributes_flags_a_varchar_without_length():
    field = report.Field("d", "ds", "t", "name", "character varying", None, None, True)
    assert "length" in report.missing_attributes(field)


def test_missing_attributes_ignores_length_for_an_integer():
    field = report.Field("d", "ds", "t", "name", "integer", None, None, True)
    assert "length" not in report.missing_attributes(field)


def test_missing_attributes_flags_a_numeric_without_scale():
    field = report.Field("d", "ds", "t", "amount", "numeric", 18, None, False)
    assert report.missing_attributes(field) == ["scale", "business_description", "tag"]


def test_missing_attributes_is_empty_for_a_complete_field():
    field = report.Field(
        "d", "ds", "t", "amount", "numeric", 18, 2, False, business_description="Cost", tag="Financial"
    )
    assert report.missing_attributes(field) == []


def test_missing_attributes_flags_a_nullable_that_nobody_answered():
    field = report.Field("d", "ds", "t", "name", "integer", None, None, None)
    assert "nullable" in report.missing_attributes(field)


# --- matching ----------------------------------------------------------


def test_exact_name_maps_as_exact(catalog_storage):
    catalog = report.load_local_catalog(catalog_storage)
    submission = report.Field("pwd", "vishwakarma", "t", "tender_cost", "double precision", None, None, True)

    row = report.match_field(submission, catalog)

    assert row["status"] == "maps"
    assert row["match_type"] == "exact"
    assert row["matched_table_id"] == "public_works_department.vishwakarma.vishwakarma_T"
    assert row["existing_tag"] == "Financial"


def test_case_and_punctuation_only_differences_map_as_normalized(catalog_storage):
    catalog = report.load_local_catalog(catalog_storage)
    submission = report.Field("agri", "farmers", "t", "District Name", "character varying", 100, None, True)

    row = report.match_field(submission, catalog)

    assert (row["status"], row["match_type"]) == ("maps", "normalized")
    assert row["matched_field"] == "district_name"
    assert row["existing_business_description"] == "Revenue district"


def test_token_overlap_is_a_candidate_and_is_not_counted_as_mapped(catalog_storage):
    catalog = report.load_local_catalog(catalog_storage)
    submission = report.Field("pwd", "ds", "t", "work_start_date", "date", None, None, True)

    row = report.match_field(submission, catalog)

    assert row["status"] == "candidate"
    assert row["match_type"] == "token-overlap"
    assert row["matched_field"] in {"start_date", "project_budget_amount"}


def test_unrelated_field_is_new(catalog_storage):
    catalog = report.load_local_catalog(catalog_storage)
    submission = report.Field("pwd", "ds", "t", "zz_totally_unrelated", "integer", None, None, True)

    row = report.match_field(submission, catalog)

    assert row["status"] == "new"
    assert row["matched_table_id"] == ""


def test_empty_catalog_means_everything_is_new():
    row = report.match_field(report.Field("d", "ds", "t", "name", "integer", None, None, True), [])
    assert row["status"] == "new"


def test_type_difference_on_a_mapped_field_is_noted(catalog_storage):
    catalog = report.load_local_catalog(catalog_storage)
    submission = report.Field("pwd", "ds", "t", "dist_code", "integer", None, None, False)

    row = report.match_field(submission, catalog)

    assert "type integer != existing character varying" in row["notes"]
    assert "nullable False != existing True" in row["notes"]


def test_unrecognised_format_note_lands_in_notes():
    submission = report.Field(
        "d", "ds", "t", "col", "character varying", None, None, True, format_note="unrecognized Format 'Blob'"
    )

    row = report.match_field(submission, [])

    assert "unrecognized Format 'Blob'" in row["notes"]


def test_gaps_on_the_existing_field_are_reported_too(catalog_storage):
    lookups.register_department(catalog_storage, "thin", "Thin")
    lookups.upsert_dataset(catalog_storage, "thin.ds", "thin", "ds")
    lookups.upsert_table(catalog_storage, "thin.ds.t", "thin.ds", "t", "public")
    catalog_storage.write_csv(
        paths.curated_schema_path("thin", "ds", "t", TS),
        [_column("legacy_col", data_type="numeric", length=18)],
    )
    catalog = report.load_local_catalog(catalog_storage)

    row = report.match_field(report.Field("thin", "ds", "t", "legacy_col", "numeric", 18, 2, False), catalog)

    assert row["status"] == "maps"
    assert "scale" in row["missing_on_existing"]
    assert "business_description" in row["missing_on_existing"]


# --- rows / summary ----------------------------------------------------


def test_field_index_counts_per_table(catalog_storage):
    catalog = report.load_local_catalog(catalog_storage)
    submission = [
        report.Field("d", "ds", "t1", "a", "integer", None, None, True),
        report.Field("d", "ds", "t1", "b", "integer", None, None, True),
        report.Field("d", "ds", "t2", "c", "integer", None, None, True),
    ]

    rows = report.build_rows(submission, catalog)

    assert [row["field_index"] for row in rows] == [1, 2, 1]


def test_summarize_counts_status_and_gaps(catalog_storage):
    catalog = report.load_local_catalog(catalog_storage)
    submission = [
        report.Field("pwd", "ds", "t1", "tender_cost", "double precision", None, None, True),
        report.Field("pwd", "ds", "t1", "work_start_date", "date", None, None, True),
        report.Field("pwd", "ds", "t2", "brand_new_field", "integer", None, None, True),
    ]

    summary = report.summarize(report.build_rows(submission, catalog))

    assert summary["fields"] == 3
    assert summary["tables"] == 2
    assert summary["status"] == {"maps": 1, "candidate": 1, "new": 1}
    assert summary["missing_description"] == 3
    assert summary["missing_tag"] == 3
    assert summary["departments"]["pwd"] == {
        "fields": 3,
        "maps": 1,
        "candidate": 1,
        "new": 1,
        "missing_description": 3,
        "missing_tag": 3,
        "tables": 2,
    }


# --- outputs -----------------------------------------------------------


def test_write_csv_uses_the_declared_columns(tmp_path):
    rows = [
        report._result(report.Field("d", "ds", "t", "name", "integer", None, None, True), None, "new", "")
    ]

    path = report.write_csv(rows, tmp_path / "out.csv")

    with path.open(encoding="utf-8") as f:
        header = f.readline().strip().split(",")
    assert header == report.CSV_COLUMNS
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_write_markdown_states_the_headline_numbers(tmp_path):
    rows = [
        report._result(report.Field("d", "ds", "t", "name", "integer", None, None, True), None, "new", ""),
        report._result(report.Field("d", "ds", "t", "other", "integer", None, None, True), None, "candidate", "token-overlap"),
    ]

    path = report.write_markdown(
        rows,
        report.summarize(rows),
        tmp_path / "out.md",
        title="Field mapping report — x",
        source="sub.txt",
        catalog="local registry",
    )

    body = path.read_text(encoding="utf-8")
    assert "Fields: **2**" in body
    assert "New fields: **1**" in body
    assert "Candidates needing confirmation: **1**" in body
    assert "## Candidates to confirm" in body


# --- submissions -------------------------------------------------------


def test_ddl_submission_needs_department_dataset_and_table(tmp_path):
    source = tmp_path / "schema.txt"
    source.write_text(_ddl_text(), encoding="utf-8")

    with pytest.raises(ValueError, match="--department"):
        report.read_submission(source)


def test_ddl_submission_parses_columns_with_no_dictionary_metadata(tmp_path):
    source = tmp_path / "schema.txt"
    source.write_text(_ddl_text(), encoding="utf-8")

    fields = report.read_submission(source, department="pwd", dataset="vishwakarma", table="t")

    assert [f.name for f in fields] == ["district_name", "work_start_date", "tender_cost", "budget_code"]
    assert fields[0].length == 100
    assert fields[1].data_type == "date"
    assert fields[2].nullable is False
    assert fields[0].business_description == "" and fields[0].tag == ""


def test_dictionary_csv_submission_uses_the_file_stem_as_dataset(tmp_path):
    source = tmp_path / "my_dictionary.csv"
    source.write_text(
        "Dataset Name,Dataset Field,Data Description,Format,Mandatory (Y/N)\n"
        "t1,col_a,What it means,Text,Y\n"
        "t1,col_b,,Numeric (12 Digits),N\n",
        encoding="utf-8",
    )

    fields = report.read_submission(source, department="wcd")

    assert {(f.department, f.dataset, f.table) for f in fields} == {("wcd", "my_dictionary", "t1")}
    assert fields[0].business_description == "What it means"
    assert fields[1].nullable is True


def test_workbook_submission_takes_department_and_dataset_from_the_roster(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from src.schema_registry.parsers import kanya_xlsx

    header = kanya_xlsx.OUTPUT_HEADERS
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for config in kanya_xlsx.SHEETS:
        sheet = wb.create_sheet(config.sheet)
        sheet.append(header)
        sheet.append([config.dataset, "aadhaar_no", "The number", "Numeric (12 Digits)", "Y", "Y"])
    source = tmp_path / "workbook.xlsx"
    wb.save(str(source))

    fields = report.read_submission(source)

    assert len(fields) == len(kanya_xlsx.SHEETS)
    assert {f.department for f in fields} == {c.department_id for c in kanya_xlsx.SHEETS}
    assert all(f.tag == "PII" for f in fields)
    assert all(f.dataset != "" for f in fields)


# --- catalog -----------------------------------------------------------


def test_dictionary_csv_submission_uses_the_given_dataset_over_the_file_stem(tmp_path):
    source = tmp_path / "my_dictionary.csv"
    source.write_text(
        "Dataset Name,Dataset Field,Data Description,Format,Mandatory (Y/N)\n"
        "t1,col_a,What it means,Text,Y\n",
        encoding="utf-8",
    )

    fields = report.read_submission(source, department="agri_dept", dataset="farmers")

    assert {(f.department, f.dataset, f.table) for f in fields} == {("agri_dept", "farmers", "t1")}


def test_workbook_without_a_single_roster_sheet_is_rejected(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from src.schema_registry.parsers import kanya_xlsx

    wb = openpyxl.Workbook()
    wb.active.append(kanya_xlsx.OUTPUT_HEADERS)
    wb.active.append(["t1", "col", "desc", "Text", "Y", "N"])
    source = tmp_path / "workbook.xlsx"
    wb.save(str(source))

    with pytest.raises(ValueError, match="roster sheets"):
        report.read_submission(source)


def test_local_catalog_skips_soft_deleted_tables(tmp_path):
    from src.storage.local import LocalObjectStorage

    storage = LocalObjectStorage(tmp_path / "storage")
    _seed_table(storage, "dept", "ds", "keep", [_column("a")])
    _seed_table(storage, "dept", "ds", "gone", [_column("b")])
    rows = storage.read_csv(lookups.TABLES_PATH)
    for row in rows:
        if row["table_name"] == "gone":
            row["deleted"] = "20260101"
    storage.write_csv(lookups.TABLES_PATH, rows)

    catalog = report.load_local_catalog(storage)

    assert [f.table for f in catalog] == ["keep"]


def test_local_catalog_excludes_named_departments(catalog_storage):
    catalog = report.load_local_catalog(catalog_storage, exclude_departments=("public_works_department",))

    assert {f.department for f in catalog} == {"agri_dept"}


def test_local_catalog_raises_when_nothing_is_registered(tmp_path):
    from src.storage.local import LocalObjectStorage

    with pytest.raises(ValueError, match="nothing registered"):
        report.load_local_catalog(LocalObjectStorage(tmp_path / "empty"))


def test_local_catalog_carries_gaps_of_the_existing_field(catalog_storage):
    catalog = report.load_local_catalog(catalog_storage)

    by_name = {f.name: f for f in catalog}
    assert by_name["district_name"].business_description == "Revenue district"
    assert by_name["district_name"].tag == "Geospatial"
    assert by_name["dist_code"].business_description == ""
    assert by_name["project_budget_amount"].scale == 2


# --- CLI ---------------------------------------------------------------


def test_main_writes_csv_and_markdown(tmp_path, monkeypatch, capsys):
    from src.storage.local import LocalObjectStorage

    storage = LocalObjectStorage(tmp_path / "storage")
    _seed_table(storage, "agri_dept", "farmers", "farmers", [_column("district_name")])
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))

    source = tmp_path / "schema.txt"
    source.write_text("district_name character varying(100), new_col integer", encoding="utf-8")

    exit_code = report.main(
        [
            "--submission",
            str(source),
            "--department",
            "public_works_department",
            "--dataset",
            "vishwakarma",
            "--table",
            "vishwakarma_T",
            "--out-dir",
            str(tmp_path / "reports"),
            "--name",
            "pwd",
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "maps=1" in out and "new=1" in out
    assert (tmp_path / "reports" / "pwd_field_mapping.csv").exists()
    assert (tmp_path / "reports" / "pwd_field_mapping.md").exists()


def test_main_can_exclude_the_departments_the_submission_created(tmp_path, monkeypatch, capsys):
    from src.storage.local import LocalObjectStorage

    storage = LocalObjectStorage(tmp_path / "storage")
    _seed_table(storage, "public_works_department", "vishwakarma", "vishwakarma_T", [_column("dist_code")])
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))

    source = tmp_path / "schema.txt"
    source.write_text("dist_code character varying(100)", encoding="utf-8")

    report.main(
        [
            "--submission",
            str(source),
            "--department",
            "public_works_department",
            "--dataset",
            "vishwakarma",
            "--table",
            "vishwakarma_T",
            "--exclude-department",
            "public_works_department",
            "--out-dir",
            str(tmp_path / "reports"),
            "--name",
            "pwd_without_self",
            "--no-markdown",
        ]
    )

    assert "new=1" in capsys.readouterr().out


def test_main_splits_one_report_per_department(tmp_path, monkeypatch, capsys):
    openpyxl = pytest.importorskip("openpyxl")
    from src.schema_registry.parsers import kanya_xlsx

    from src.storage.local import LocalObjectStorage

    storage = LocalObjectStorage(tmp_path / "storage")
    _seed_table(storage, "agri_dept", "farmers", "farmers", [_column("district_name")])
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))

    for config in kanya_xlsx.SHEETS[:2]:
        lookups.register_department(storage, config.department_id, config.department_name)

    header = kanya_xlsx.OUTPUT_HEADERS
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for config in kanya_xlsx.SHEETS[:2]:
        sheet = wb.create_sheet(config.sheet)
        sheet.append(header)
        sheet.append([config.dataset, "district_name", "District", "Text", "Y", "N"])
        sheet.append([config.dataset, "brand_new_col", "Brand new", "Integer", "Y", "N"])
    source = tmp_path / "workbook.xlsx"
    wb.save(str(source))

    exit_code = report.main(
        [
            "--submission",
            str(source),
            "--catalog",
            "local",
            "--out-dir",
            str(tmp_path / "reports"),
            "--name",
            "kanya",
            "--split-by-department",
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "maps=1" in out and "new=1" in out
    written = sorted(p.name for p in (tmp_path / "reports").glob("*.csv"))
    assert len(written) == 2
    for config in kanya_xlsx.SHEETS[:2]:
        csv_name = f"kanya_{config.department_id}_field_mapping.csv"
        assert csv_name in written
        md_path = tmp_path / "reports" / f"kanya_{config.department_id}_field_mapping.md"
        body = md_path.read_text(encoding="utf-8")
        assert f"Field mapping report — {config.department_id} ({config.department_name})" in body
        assert "Map to an existing field: **1**" in body
        assert "New fields: **1**" in body


def test_note_flag_is_written_into_the_markdown(tmp_path, monkeypatch, capsys):
    from src.storage.local import LocalObjectStorage

    storage = LocalObjectStorage(tmp_path / "storage")
    _seed_table(storage, "agri_dept", "farmers", "farmers", [_column("district_name")])
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))

    source = tmp_path / "schema.txt"
    source.write_text("district_name character varying(100)", encoding="utf-8")

    report.main(
        [
            "--submission",
            str(source),
            "--department",
            "d",
            "--dataset",
            "ds",
            "--table",
            "t",
            "--out-dir",
            str(tmp_path / "reports"),
            "--name",
            "x",
            "--note",
            "Auto-tagged at ingest.",
        ]
    )

    capsys.readouterr()
    md = (tmp_path / "reports" / "x_field_mapping.md").read_text(encoding="utf-8")
    assert "## Notes" in md
    assert "- Auto-tagged at ingest." in md


def test_markdown_omits_the_notes_section_without_notes(tmp_path):
    rows = [report._result(report.Field("d", "ds", "t", "name", "integer", None, None, True), None, "new", "")]

    path = report.write_markdown(
        rows,
        report.summarize(rows),
        tmp_path / "x.md",
        title="t",
        source="s",
        catalog="local",
    )

    assert "## Notes" not in path.read_text(encoding="utf-8")
