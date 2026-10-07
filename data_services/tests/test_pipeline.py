import csv
from unittest.mock import MagicMock

import pytest

from src.schema_registry.registry import lookups
from src.schema_registry.openmetadata.publish import _unwrap
from src.schema_registry.pipeline import run
from src.storage.local import LocalObjectStorage


def _write_business_metadata(tmp_path, filename: str, rows: list[dict]) -> str:
    path = tmp_path / filename
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "business_description", "tag", "glossary_term", "active"])
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def _storage_with_department(tmp_path, department_id="pwd", department_name="PWD"):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, department_id, department_name)
    return storage


def _fake_om_client():
    """Same minimal SDK stand-in as test_openmetadata_publish.py's
    _fake_client(): get_by_name always reports "not found", create_or_update
    echoes back a name/fullyQualifiedName so _fqn() can chain calls."""

    client = MagicMock()
    client.get_by_name.side_effect = Exception("Entity not found")

    def _create_or_update(request):
        entity = MagicMock()
        name = _unwrap(getattr(request, "name", None))
        parent = _unwrap(
            getattr(request, "service", None)
            or getattr(request, "database", None)
            or getattr(request, "databaseSchema", None)
        )
        entity.fullyQualifiedName = f"{parent}.{name}" if parent else str(name)
        entity.name = name
        # the real server echoes a table's columns back -- _replace_column_tags()
        # maps names to indexes against this list
        entity.columns = getattr(request, "columns", None)
        return entity

    client.create_or_update.side_effect = _create_or_update
    return client


def test_run_with_postgres_ddl_format(tmp_path):
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text('sno integer NOT NULL, total_cost double precision DEFAULT 0')
    storage = _storage_with_department(tmp_path)

    result = run(
        department="pwd",
        dataset="vishwakarma",
        table_name="TBD_confirm_with_pwd",
        source_file=str(ddl_file),
        storage=storage,
        source_format="postgres_ddl",
    )

    assert result["column_count"] == 2
    assert storage.exists(result["raw_path"])
    assert storage.exists(result["curated_path"])

    curated = storage.read_csv(result["curated_path"])
    assert curated[0]["table_id"] == "pwd.vishwakarma.tbd_confirm_with_pwd"
    assert curated[1]["tag"] == "Financial"


def test_run_with_openmetadata_client_publishes_in_the_same_call(tmp_path):
    """The whole point of wiring publish into run(): passing a client makes
    ingest -> curate -> publish one pipeline call instead of a separate
    manual openmetadata_publish.publish_table() step afterward."""

    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("sno integer NOT NULL, firm_name character varying(100)")
    storage = _storage_with_department(tmp_path)
    client = _fake_om_client()

    result = run(
        department="pwd",
        dataset="vishwakarma",
        table_name="t1",
        source_file=str(ddl_file),
        storage=storage,
        openmetadata_client=client,
    )

    assert result["openmetadata"]["fully_qualified_name"] == "pwd.vishwakarma.public.t1"
    assert result["openmetadata"]["column_count"] == 2
    # service, database, schema, table, + the "FieldTag" classification and
    # "Firm/Contractor-Identifier" tag that firm_name auto-tags into
    assert client.create_or_update.call_count == 6


def test_run_without_openmetadata_client_skips_publish(tmp_path):
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("sno integer NOT NULL")
    storage = _storage_with_department(tmp_path)

    result = run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)

    assert "openmetadata" not in result


def test_curated_rows_carry_ingestion_timestamp(tmp_path):
    """Audit requirement: ingestion timestamp must travel with the row data
    itself, not only live in the filename -- otherwise it's lost if the CSV
    is ever copied/extracted from its file path."""

    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("sno integer NOT NULL")
    storage = _storage_with_department(tmp_path)

    result = run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)

    curated = storage.read_csv(result["curated_path"])
    assert curated[0]["ingestion_timestamp"]
    raw = storage.read_csv(result["raw_path"])
    assert raw[0]["ingestion_timestamp"] == curated[0]["ingestion_timestamp"]


def test_run_with_csv_format(tmp_path):
    csv_file = tmp_path / "raw.csv"
    csv_file.write_text("Field Name,Data Type\nroad_id,integer\nroad_name,varchar\n")
    storage = _storage_with_department(tmp_path)

    result = run(
        department="pwd",
        dataset="srishti",
        table_name="roads",
        source_file=str(csv_file),
        storage=storage,
        source_format="csv",
    )

    assert result["column_count"] == 2
    curated = storage.read_csv(result["curated_path"])
    assert curated[0]["name"] == "road_id"


def test_run_registers_dataset_and_table_lookups(tmp_path):
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("sno integer NOT NULL")
    storage = _storage_with_department(tmp_path)

    run(
        department="pwd",
        dataset="vishwakarma",
        table_name="t1",
        source_file=str(ddl_file),
        storage=storage,
        source_format="postgres_ddl",
    )

    assert storage.read_csv("_lookups/departments.csv") == [{"department_id": "pwd", "department_name": "PWD"}]
    assert storage.read_csv("_lookups/datasets.csv")[0]["dataset_id"] == "pwd.vishwakarma"
    assert storage.read_csv("_lookups/tables.csv")[0]["table_id"] == "pwd.vishwakarma.t1"


def test_unregistered_department_raises(tmp_path):
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("sno integer NOT NULL")
    storage = LocalObjectStorage(tmp_path / "storage")  # no register_department call

    with pytest.raises(ValueError, match="Unknown department"):
        run(
            department="unknown_dept",
            dataset="vishwakarma",
            table_name="t1",
            source_file=str(ddl_file),
            storage=storage,
        )


def test_two_tables_same_dataset_get_separate_folders(tmp_path):
    storage = _storage_with_department(tmp_path)
    file_a = tmp_path / "a.txt"
    file_a.write_text("col_a integer")
    file_b = tmp_path / "b.txt"
    file_b.write_text("col_b integer")

    result_a = run(department="pwd", dataset="d1", table_name="table_a", source_file=str(file_a), storage=storage)
    result_b = run(department="pwd", dataset="d1", table_name="table_b", source_file=str(file_b), storage=storage)

    assert result_a["raw_path"] != result_b["raw_path"]
    assert "table_a" in result_a["raw_path"]
    assert "table_b" in result_b["raw_path"]


def test_rerun_does_not_duplicate_lookup_but_adds_new_snapshot(tmp_path):
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("sno integer NOT NULL")
    storage = _storage_with_department(tmp_path)

    run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)
    run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)

    assert len(storage.read_csv("_lookups/tables.csv")) == 1
    raw_files = storage.list("department/pwd/vishwakarma/t1/raw/schemas")
    assert len(raw_files) == 2


def test_differently_spelled_department_resolves_to_registered_entry(tmp_path):
    """slugify normalizes formatting of an already-registered department,
    it doesn't let you register a new one by typing it differently."""

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "amplify_data", "Amplify Data")

    file_a = tmp_path / "a.csv"
    file_a.write_text("Field Name,Data Type\ncol_a,integer\n")

    run(department="Amplify Data", dataset="usage", table_name="events", source_file=str(file_a), storage=storage, source_format="csv")

    departments = storage.read_csv("_lookups/departments.csv")
    assert len(departments) == 1
    assert departments[0]["department_id"] == "amplify_data"


def test_unknown_source_format_raises(tmp_path):
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("sno integer")
    storage = _storage_with_department(tmp_path)

    with pytest.raises(ValueError, match="Unknown source_format"):
        run(
            department="pwd",
            dataset="vishwakarma",
            table_name="t1",
            source_file=str(ddl_file),
            storage=storage,
            source_format="excel",
        )


def test_first_run_never_blocked_by_column_removal_guard(tmp_path):
    """A table's first-ever run has no previous snapshot to diff against,
    so it always succeeds regardless of allow_column_removal (this is
    "initial load")."""

    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("col_a integer NOT NULL")
    storage = _storage_with_department(tmp_path)

    result = run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)

    assert result["column_count"] == 1


def test_rerun_with_only_additions_succeeds_without_allow_column_removal(tmp_path):
    storage = _storage_with_department(tmp_path)
    ddl_v1 = tmp_path / "v1.txt"
    ddl_v1.write_text("col_a integer NOT NULL")
    run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v1), storage=storage)

    ddl_v2 = tmp_path / "v2.txt"
    ddl_v2.write_text("col_a integer NOT NULL, col_b character varying(50)")
    result = run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v2), storage=storage)

    assert result["column_count"] == 2


def test_rerun_dropping_a_column_raises_without_allow_column_removal(tmp_path):
    """The core guard: a source file missing a column that exists in the
    previous curated snapshot is treated as a likely partial/incremental
    submission, not an intentional removal -- it must fail loudly instead
    of silently publishing a table with fewer columns."""

    storage = _storage_with_department(tmp_path)
    ddl_v1 = tmp_path / "v1.txt"
    ddl_v1.write_text("col_a integer NOT NULL, col_b character varying(50)")
    run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v1), storage=storage)

    ddl_v2 = tmp_path / "v2.txt"
    ddl_v2.write_text("col_a integer NOT NULL")  # col_b missing

    with pytest.raises(ValueError, match="col_b"):
        run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v2), storage=storage)

    # the rejected run must not have written a new snapshot
    assert len(storage.list("department/pwd/vishwakarma/t1/curated/schemas")) == 1


def test_rerun_dropping_a_column_succeeds_with_allow_column_removal(tmp_path):
    storage = _storage_with_department(tmp_path)
    ddl_v1 = tmp_path / "v1.txt"
    ddl_v1.write_text("col_a integer NOT NULL, col_b character varying(50)")
    run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v1), storage=storage)

    ddl_v2 = tmp_path / "v2.txt"
    ddl_v2.write_text("col_a integer NOT NULL")

    result = run(
        department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v2), storage=storage,
        allow_column_removal=True,
    )

    assert result["column_count"] == 1
    assert [c["name"] for c in result["columns"]] == ["col_a"]


def test_rerun_carries_forward_business_metadata_not_resubmitted(tmp_path):
    """A department answering one column's Field Dictionary question
    shouldn't erase another column's previously-recorded answer just
    because this run's business_metadata_file doesn't mention it."""

    storage = _storage_with_department(tmp_path)
    ddl_v1 = tmp_path / "v1.txt"
    ddl_v1.write_text("col_a integer NOT NULL, col_b character varying(50)")
    meta_v1 = _write_business_metadata(tmp_path, "meta_v1.csv", [
        {"name": "col_a", "business_description": "First column", "tag": "", "glossary_term": "", "active": "true"},
        {"name": "col_b", "business_description": "Second column", "tag": "", "glossary_term": "", "active": "true"},
    ])
    run(
        department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v1), storage=storage,
        business_metadata_file=meta_v1,
    )

    # v2 only answers col_b, and adds col_c -- col_a's description should
    # still be there, not blanked out
    ddl_v2 = tmp_path / "v2.txt"
    ddl_v2.write_text("col_a integer NOT NULL, col_b character varying(50), col_c double precision")
    meta_v2 = _write_business_metadata(tmp_path, "meta_v2.csv", [
        {"name": "col_b", "business_description": "Updated second column", "tag": "", "glossary_term": "", "active": "true"},
    ])
    result = run(
        department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v2), storage=storage,
        business_metadata_file=meta_v2,
    )

    by_name = {c["name"]: c for c in result["columns"]}
    assert by_name["col_a"]["business_description"] == "First column"  # carried forward, not blanked
    assert by_name["col_b"]["business_description"] == "Updated second column"  # file overlay wins
    assert by_name["col_c"]["business_description"] == ""  # brand new column, nothing to carry forward


def test_rerun_with_no_metadata_file_still_carries_forward_previous_answers(tmp_path):
    storage = _storage_with_department(tmp_path)
    ddl_v1 = tmp_path / "v1.txt"
    ddl_v1.write_text("col_a integer NOT NULL")
    meta_v1 = _write_business_metadata(tmp_path, "meta_v1.csv", [
        {"name": "col_a", "business_description": "Only column", "tag": "PII", "glossary_term": "", "active": "true"},
    ])
    run(
        department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v1), storage=storage,
        business_metadata_file=meta_v1,
    )

    # v2: same column, no business_metadata_file at all
    ddl_v2 = tmp_path / "v2.txt"
    ddl_v2.write_text("col_a integer NOT NULL")
    result = run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_v2), storage=storage)

    assert result["columns"][0]["business_description"] == "Only column"
    assert result["columns"][0]["tag"] == "PII"


def _write_metadata_csv(tmp_path, filename: str, text: str) -> str:
    path = tmp_path / filename
    path.write_text(text)
    return str(path)


def test_description_only_rerun_keeps_manual_classification_glossary_and_active(tmp_path):
    """A later file that only answers business_description must not reset
    a hand-set classification back to the auto one, wipe the glossary term,
    or (by having no `active` column) mark the column inactive."""

    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("phone character varying(10), amount numeric")
    storage = _storage_with_department(tmp_path)
    common = dict(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)

    run(**common, business_metadata_file=_write_metadata_csv(
        tmp_path, "first.csv",
        "name,business_description,classification,glossary_term,active\nphone,Contact,CAT-2,Contact Number,false\n",
    ))
    result = run(**common, business_metadata_file=_write_metadata_csv(
        tmp_path, "second.csv", "name,business_description\nphone,Contact number of the firm\n",
    ))

    phone = next(c for c in result["columns"] if c["name"] == "phone")
    assert phone["business_description"] == "Contact number of the firm"  # new answer wins
    assert phone["classification"] == "CAT-2"  # not reset to auto CAT-3
    assert phone["glossary_term"] == "Contact Number"
    assert phone["active"] is False  # kept, not flipped by the missing column


def test_blank_cells_in_metadata_file_do_not_erase_previous_answers(tmp_path):
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("remarks text")
    storage = _storage_with_department(tmp_path)
    common = dict(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)

    run(**common, business_metadata_file=_write_metadata_csv(
        tmp_path, "first.csv", "name,business_description,tag,glossary_term\nremarks,Notes,Free Text,Field Note\n",
    ))
    result = run(**common, business_metadata_file=_write_metadata_csv(
        tmp_path, "second.csv", "name,business_description,tag,glossary_term\nremarks,,,\n",
    ))

    remarks = result["columns"][0]
    assert (remarks["business_description"], remarks["tag"], remarks["glossary_term"]) == (
        "Notes", "Free Text", "Field Note",
    )


def test_metadata_file_without_active_column_keeps_columns_active(tmp_path):
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("remarks text")
    storage = _storage_with_department(tmp_path)

    result = run(
        department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage,
        business_metadata_file=_write_metadata_csv(tmp_path, "m.csv", "name,business_description\nremarks,Notes\n"),
    )

    assert result["columns"][0]["active"] is True


def _snapshot_files(storage):
    return storage.list("department/")


def test_rejected_run_leaves_registry_unchanged(tmp_path):
    """The column-removal guard used to fire after upsert_dataset/
    upsert_table had already rewritten schema_name and owner."""

    storage = _storage_with_department(tmp_path)
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("a integer, b integer")
    common = dict(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)
    run(**common, owner="PWD IT Cell")
    tables_before = storage.read_csv(lookups.TABLES_PATH)
    datasets_before = storage.read_csv(lookups.DATASETS_PATH)
    files_before = _snapshot_files(storage)

    ddl_file.write_text("a integer")
    with pytest.raises(ValueError, match="missing 1 column"):
        run(**common, schema_name="other", owner="Someone Else")

    assert storage.read_csv(lookups.TABLES_PATH) == tables_before
    assert storage.read_csv(lookups.DATASETS_PATH) == datasets_before
    assert _snapshot_files(storage) == files_before


def test_first_run_with_bad_schema_registers_nothing(tmp_path):
    storage = _storage_with_department(tmp_path)
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("tags text[]")

    with pytest.raises(ValueError, match="schema rejected"):
        run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)

    assert lookups.get_table(storage, "pwd.vishwakarma.t1") is None
    assert lookups.get_dataset(storage, "pwd.vishwakarma") is None
    assert _snapshot_files(storage) == []


@pytest.mark.parametrize(
    "ddl, message",
    [
        ("phone character varying(10), tags text[]", r"unrecognized data type\(s\): tags \(text\[\]\)"),
        ("amount numeric, amount integer", r"duplicate column name\(s\): amount"),
    ],
)
def test_bad_schema_is_rejected_before_anything_is_stored(tmp_path, ddl, message):
    storage = _storage_with_department(tmp_path)
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("phone character varying(10)")
    common = dict(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)
    run(**common)
    files_before = _snapshot_files(storage)

    ddl_file.write_text(ddl)
    with pytest.raises(ValueError, match=message):
        run(**common)

    # the previous good snapshot is still the latest one
    assert _snapshot_files(storage) == files_before


def test_csv_column_with_empty_name_is_rejected(tmp_path):
    storage = _storage_with_department(tmp_path)
    csv_file = tmp_path / "cols.csv"
    csv_file.write_text("name,data_type\nphone,text\n,integer\n")

    with pytest.raises(ValueError, match=r"position 2 have no name"):
        run(
            department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(csv_file),
            storage=storage, source_format="csv",
        )


def test_schema_error_lists_every_problem_at_once(tmp_path):
    storage = _storage_with_department(tmp_path)
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("a integer, a integer, b money")

    with pytest.raises(ValueError) as excinfo:
        run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)

    assert "duplicate column name(s): a" in str(excinfo.value)
    assert "b (money)" in str(excinfo.value)


def test_unmatched_metadata_names_are_reported(tmp_path, monkeypatch):
    storage = _storage_with_department(tmp_path)
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("phone character varying(10)")
    warnings = []
    # src.utils.logger sets propagate=False, so caplog never sees these
    monkeypatch.setattr("src.schema_registry.pipeline.logger.warning", warnings.append)

    result = run(
        department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage,
        business_metadata_file=_write_metadata_csv(
            tmp_path, "m.csv", "name,business_description\nphone,Contact\nphnoe,Typo\nfax,Not a column\n"
        ),
    )

    assert result["unmatched_metadata_names"] == ["fax", "phnoe"]
    assert any("fax, phnoe" in w for w in warnings)
    assert result["columns"][0]["business_description"] == "Contact"


def test_missing_metadata_file_fails_before_anything_is_stored(tmp_path):
    storage = _storage_with_department(tmp_path)
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("phone character varying(10)")

    with pytest.raises(FileNotFoundError):
        run(
            department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage,
            business_metadata_file=str(tmp_path / "does_not_exist.csv"),
        )

    assert _snapshot_files(storage) == []
    assert lookups.get_table(storage, "pwd.vishwakarma.t1") is None


def test_run_archives_the_exact_source_and_metadata_files(tmp_path):
    import hashlib

    storage = _storage_with_department(tmp_path)
    ddl_file = tmp_path / "pwd_raw.txt"
    ddl_file.write_bytes(b"sno integer NOT NULL, phone character varying(10)")
    meta = _write_metadata_csv(tmp_path, "meta.csv", "name,business_description\nphone,Contact\n")

    result = run(
        department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file),
        storage=storage, business_metadata_file=meta,
    )

    assert result["source_archive_path"].endswith("__pwd_raw.txt")
    assert "/raw/source/" in result["source_archive_path"]
    assert storage.read_bytes(result["source_archive_path"]) == ddl_file.read_bytes()
    expected = hashlib.sha256(ddl_file.read_bytes()).hexdigest()
    assert result["source_sha256"] == expected
    assert storage.read_bytes(result["source_archive_path"] + ".sha256").decode().startswith(expected)
    assert storage.read_bytes(result["metadata_archive_path"]) == open(meta, "rb").read()


def test_run_reads_source_and_metadata_from_storage(tmp_path):
    """No local file at all: everything comes from the run's storage, the
    way BIPP2 (or anyone without the original files) runs it."""

    storage = _storage_with_department(tmp_path)
    storage.write_bytes("inputs/pwd/cols.csv", b"\xef\xbb\xbfname,data_type\r\nphone,text\r\n")  # BOM, CRLF
    storage.write_bytes("inputs/pwd/meta.csv", b"name,business_description\nphone,Contact\n")

    result = run(
        department="pwd", dataset="vishwakarma", table_name="t1", storage=storage, source_format="csv",
        source_file="storage:inputs/pwd/cols.csv", business_metadata_file="storage:inputs/pwd/meta.csv",
    )

    assert [c["name"] for c in result["columns"]] == ["phone"]
    assert result["columns"][0]["business_description"] == "Contact"
    assert result["source_archive_path"].endswith("__cols.csv")


def test_missing_storage_input_says_how_to_upload(tmp_path):
    storage = _storage_with_department(tmp_path)
    with pytest.raises(FileNotFoundError, match="upload it first"):
        run(department="pwd", dataset="vishwakarma", table_name="t1", storage=storage,
            source_file="storage:inputs/pwd/nope.txt")


def test_rejected_run_archives_nothing(tmp_path):
    storage = _storage_with_department(tmp_path)
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("a integer, a integer")

    with pytest.raises(ValueError, match="duplicate"):
        run(department="pwd", dataset="vishwakarma", table_name="t1", source_file=str(ddl_file), storage=storage)

    assert storage.list("department/") == []
