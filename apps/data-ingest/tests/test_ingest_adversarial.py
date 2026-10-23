"""Adversarial checks for the ingest API, written during review of feature/ingest-api.

These complement test_ingest.py: they probe the edges that suite does not
exercise -- path traversal, validation consistency between dry-run and the real
call, transactional behaviour when a sibling table fails, concurrency, Excel
uploads, auth, upload limits, and the rules the CLI applies but the API once
skipped. Tests that used to pin a bug now pin the fix.
"""

import base64
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main  # noqa: E402
from src.schema_registry.add import write_catalog_text  # noqa: E402
from src.schema_registry.catalog import load_catalog  # noqa: E402
from src.storage.local import LocalObjectStorage  # noqa: E402

DDL = "sno integer NOT NULL, firm_name character varying(100), total_cost double precision"
OK = {"X-Confirm-Environment": "local"}
DEV = {"X-Confirm-Environment": "development"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("departments:\n")
    state = {"env": "local", "branch": "main", "storage": LocalObjectStorage(str(tmp_path / "s")),
             "catalog": catalog, "client": None, "setup": None}
    monkeypatch.setattr(main, "runtime", lambda: state)
    monkeypatch.setattr(main, "backup_after_run", lambda storage: True)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("INGEST_API_KEY", raising=False)
    monkeypatch.delenv("OPENMETADATA_JWT_TOKEN", raising=False)
    return TestClient(main.app), catalog, state


def post(c, filename="works.txt", content=DDL, headers=None, metadata_content=None,
         metadata_name="meta.csv", **extra):
    data = {"department": "pwd", "dataset": "vishwakarma", "table": "works",
            "department_name": "Public Works Department", **extra}
    files = {"file": (filename, content)}
    if metadata_content is not None:
        files["metadata"] = (metadata_name, metadata_content)
    return c.post("/v1/ingest", data=data, files=files, headers=headers or {})


def _tables(catalog):
    return load_catalog(str(catalog))[0].datasets[0].tables


# --- path traversal and naming -----------------------------------------------------------------

@pytest.mark.parametrize("filename", ["../../evil.txt", "..\\..\\evil.txt", "C:\\Windows\\evil.txt"])
def test_a_file_name_cannot_escape_the_inputs_folder(client, tmp_path, filename):
    c, _, state = client
    r = post(c, filename=filename, headers=OK)
    assert r.status_code == 200, r.text
    landed = sorted(p for p in tmp_path.rglob("evil.txt"))
    assert landed == [tmp_path / "s" / "inputs" / "pwd" / "vishwakarma" / "evil.txt"], landed


def test_department_path_traversal_is_refused_and_nothing_is_written(client):
    c, catalog, state = client
    r = post(c, headers=OK, department="../../evil", category="CAT-2")
    assert r.status_code == 422
    assert catalog.read_text() == "departments:\n"
    assert state["storage"].list("inputs/") == []
    assert state["storage"].list("_lookups/") == []


@pytest.mark.parametrize("field,bad", [("dataset", "../evil"), ("dataset", "a/b"), ("table", "..\\evil"),
                                       ("table", "a.b"), ("table", "-x")])
def test_dataset_and_table_names_cannot_contain_path_characters(client, field, bad):
    c, catalog, state = client
    r = post(c, headers=OK, **{field: bad})
    assert r.status_code == 422, r.text
    assert catalog.read_text() == "departments:\n"
    assert state["storage"].list("inputs/") == []


def test_dataset_and_table_names_have_a_100_character_limit(client):
    c, catalog, _ = client
    assert post(c, headers=OK, dataset="d" * 101).status_code == 422
    assert catalog.read_text() == "departments:\n"
    assert post(c, headers=OK, dataset="d" * 100).status_code == 200


def test_surrounding_or_repeated_spaces_are_refused(client):
    """'works ' and 'works' slugify to one id but were two catalog keys."""

    c, catalog, _ = client
    for bad in ["works ", " works", "two  spaces"]:
        r = post(c, headers=OK, table=bad)
        assert r.status_code == 422, (bad, r.text)
        assert "isn't allowed" in r.json()["problem"]
        assert "spaces" in r.json()["fix"]
    assert catalog.read_text() == "departments:\n"


def test_names_with_spaces_and_uppercase_work_end_to_end(client):
    c, catalog, state = client
    r = post(c, headers=OK, dataset="My Data", table="My Table")
    assert r.status_code == 200, r.text
    assert r.json()["tables"][0]["id"] == "pwd.my_data.my_table"
    assert load_catalog(str(catalog))[0].datasets[0].name == "My Data"
    assert state["storage"].exists("inputs/pwd/my_data/works.txt")


# --- confirmation / auth / status --------------------------------------------------------------

def test_the_environment_header_is_case_sensitive(client):
    c, _, _ = client
    assert post(c, headers={"X-Confirm-Environment": "Local"}).status_code == 409


def test_dry_run_still_needs_the_api_key_when_one_is_configured(client, monkeypatch):
    c, _, _ = client
    monkeypatch.setenv("INGEST_API_KEY", "s3cret")
    assert post(c, dry_run="true").status_code == 401
    assert post(c, dry_run="true", headers={"X-API-Key": "s3cret"}).status_code == 200


def test_status_requires_the_api_key_and_hides_configuration_without_it(client, monkeypatch):
    c, _, _ = client
    monkeypatch.setenv("INGEST_API_KEY", "s3cret")
    monkeypatch.setenv("WASABI_BUCKET", "up-sda-schema-registry")
    monkeypatch.setenv("WASABI_PREFIX", "dev/")

    anonymous = c.get("/v1/status")
    assert anonymous.status_code == 401
    assert "bucket" not in anonymous.json()

    r = c.get("/v1/status", headers={"X-API-Key": "s3cret"})
    assert r.status_code == 200
    assert r.json()["bucket"] == "up-sda-schema-registry"
    assert r.json()["folder"] == "dev/"


def test_status_reports_an_expired_openmetadata_token(client, monkeypatch):
    c, _, _ = client
    payload = base64.urlsafe_b64encode(json.dumps({"exp": 1}).encode()).decode().rstrip("=")
    monkeypatch.setenv("OPENMETADATA_JWT_TOKEN", f"x.{payload}.y")
    body = c.get("/v1/status").json()
    assert body["openmetadata_token_expired"] is True
    assert body["openmetadata_token_expires_at"].startswith("1970")


# --- dataset fields ----------------------------------------------------------------------------

def test_dataset_fields_round_trip_through_the_catalog(client):
    c, catalog, _ = client
    r = post(c, headers=OK, category="CAT-2", description="Works & tenders: roads",
             owner="Public Works Department", steward="PWD Data Cell",
             frequency="yearly", timeline="2023-27", api_available="N")
    assert r.status_code == 200, r.text
    fields = load_catalog(str(catalog))[0].datasets[0].fields
    assert fields == {
        "category": "CAT-2", "api_available": "N", "owner": "Public Works Department",
        "steward": "PWD Data Cell", "frequency": "yearly", "timeline": "2023-27",
        "dataset_description": "Works & tenders: roads",
    }


def test_values_a_yaml_reader_would_coerce_round_trip_through_the_api(client):
    c, catalog, _ = client
    r = post(c, headers=OK, owner="yes", steward="no", frequency="1:30",
             timeline="null", description="Works: roads")
    assert r.status_code == 200, r.text
    fields = load_catalog(str(catalog))[0].datasets[0].fields
    assert fields["owner"] == "yes" and fields["steward"] == "no"
    assert fields["frequency"] == "1:30" and fields["timeline"] == "null"
    assert fields["dataset_description"] == "Works: roads"


def test_a_unicode_description_is_stored_as_utf8(client):
    c, catalog, _ = client
    hindi = "सड़कें और निविदा"
    r = post(c, headers=OK, description=hindi)
    assert r.status_code == 200, r.text
    assert hindi in catalog.read_text(encoding="utf-8")
    assert load_catalog(str(catalog))[0].datasets[0].fields["dataset_description"] == hindi


def test_an_invalid_api_available_is_refused_before_anything_is_stored(client):
    c, catalog, state = client
    r = post(c, headers=OK, api_available="maybe")
    assert r.status_code == 422
    assert "api_available" in r.json()["problem"]
    assert catalog.read_text() == "departments:\n"
    assert state["storage"].list("inputs/") == []


# --- transactional behaviour -------------------------------------------------------------------

def test_a_second_table_cannot_take_over_another_tables_file(client):
    c, catalog, state = client
    assert post(c, filename="shared.txt", headers=OK).status_code == 200
    before = catalog.read_text()
    r = post(c, filename="shared.txt", table="tenders", content="sno integer", headers=OK)
    assert r.status_code == 422
    assert "already the file of table 'works'" in r.json()["problem"]
    assert catalog.read_text() == before
    stored = state["storage"].read_bytes("inputs/pwd/vishwakarma/shared.txt")
    assert stored == DDL.encode()


def test_a_rejected_update_never_replaces_the_good_stored_file(client):
    c, catalog, state = client
    assert post(c, headers=OK).status_code == 200
    before_catalog = catalog.read_text()
    before_file = state["storage"].read_bytes("inputs/pwd/vishwakarma/works.txt")

    assert post(c, content="", headers=OK).status_code == 422
    assert post(c, content="work_id weirdtype", headers=OK).status_code == 422
    assert state["storage"].read_bytes("inputs/pwd/vishwakarma/works.txt") == before_file
    assert catalog.read_text() == before_catalog


def test_a_rejected_department_leaves_no_lookup_rows(client):
    c, _, state = client
    assert post(c, headers=OK, department="NEW_DEPT", table="works").status_code == 422  # no department_name
    assert state["storage"].list("_lookups/") == []


def test_publish_failure_can_be_retried_without_duplicating_the_table(client, monkeypatch):
    c, catalog, _ = client
    real_sync = main.sync

    def failing(storage, departments, **kw):
        out = real_sync(storage, departments, **kw)
        for o in out:
            o.publish = "failed"
            o.detail = "OpenMetadata unreachable"
        return out

    monkeypatch.setattr(main, "sync", failing)
    assert post(c, headers=OK).status_code == 502
    assert [t.name for t in _tables(catalog)] == ["works"]

    monkeypatch.setattr(main, "sync", real_sync)
    r = post(c, headers=OK)
    assert r.status_code == 200, r.text
    assert r.json()["tables"][0]["store"] == "unchanged"
    assert [t.name for t in _tables(catalog)] == ["works"]


def test_a_broken_sibling_table_does_not_fail_this_request_but_is_reported(client):
    """sync is department-wide, so one ingest also touches every other table in
    the department. A sibling failure must not hide behind a 200 for this call;
    it is reported inside `tables`."""

    c, catalog, _ = client
    catalog.write_text(
        "departments:\n"
        "  pwd:\n"
        "    name: Public Works Department\n"
        "    datasets:\n"
        "      vishwakarma:\n"
        "        category: CAT-2\n"
        "        tables:\n"
        "          broken:\n"
        "            source: storage:inputs/pwd/vishwakarma/missing.txt\n"
        "            format: postgres_ddl\n",
        encoding="utf-8",
    )
    r = post(c, headers=OK)
    assert r.status_code == 200, r.text
    by_id = {t["id"]: t for t in r.json()["tables"]}
    assert by_id["pwd.vishwakarma.broken"]["store"] == "failed"
    assert by_id["pwd.vishwakarma.works"]["store"] == "ingested"


def test_local_without_openmetadata_says_it_did_not_publish(client):
    c, _, _ = client
    r = post(c, headers=OK)
    assert r.status_code == 200
    assert r.json()["tables"][0]["publish"] == "skipped"
    assert r.json()["published"] is False


def test_development_without_openmetadata_is_a_503_and_stores_nothing(client):
    c, catalog, state = client
    state["env"] = "development"
    r = post(c, headers=DEV)
    assert r.status_code == 503
    assert "nothing would be published" in r.json()["problem"]
    assert catalog.read_text() == "departments:\n"
    assert state["storage"].list("inputs/") == []


def test_ingesting_the_same_file_twice_is_idempotent(client):
    c, catalog, _ = client
    assert post(c, headers=OK).status_code == 200
    first = catalog.read_text()
    r = post(c, headers=OK)
    assert r.status_code == 200
    assert r.json()["tables"][0]["store"] == "unchanged"
    assert catalog.read_text() == first


# --- concurrency -------------------------------------------------------------------------------

def test_two_concurrent_ingests_do_not_lose_a_catalog_entry(client):
    c, catalog, _ = client

    def send(i):
        with TestClient(main.app) as other:
            return post(other, filename=f"f{i}.txt", table=f"t{i}", headers=OK).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(send, (1, 2))) == [200, 200]
    names = {t.name for t in _tables(catalog)}
    assert {"t1", "t2"} <= names


# --- dry-run consistency -----------------------------------------------------------------------

def test_dry_run_validates_catalog_names_like_the_real_call(client):
    c, catalog, _ = client
    assert post(c, dry_run="true", department="../evil", category="CAT-2").status_code == 422
    assert post(c, dry_run="true", category="CAT-9").status_code == 422
    assert catalog.read_text() == "departments:\n"


def test_dry_run_parses_the_file_and_rejects_garbage(client):
    c, catalog, state = client
    r = post(c, dry_run="true", content="this is not a schema")
    assert r.status_code == 422
    assert "problem" in r.json()
    assert catalog.read_text() == "departments:\n"
    assert state["storage"].list("inputs/") == []

    good = post(c, dry_run="true")
    assert good.status_code == 200
    assert good.json()["validated"] is True


# --- error contract ----------------------------------------------------------------------------

def test_every_error_uses_problem_and_fix_at_the_top_level(client):
    c, _, _ = client
    r = c.post("/v1/ingest", data={"dataset": "d", "table": "t"},
               files={"file": ("x.txt", DDL)}, headers=OK)
    assert r.status_code == 422
    body = r.json()
    assert "detail" not in body
    assert body["problem"] and body["fix"]


# --- input formats -----------------------------------------------------------------------------

def test_a_csv_schema_file_works(client):
    c, _, _ = client
    csv = "column,type\nsno,integer\nfirm_name,varchar\ntotal_cost,double precision\n"
    r = post(c, filename="works.csv", content=csv, headers=OK)
    assert r.status_code == 200, r.text
    assert r.json()["tables"][0]["store"] == "ingested"
    assert "3 columns" in r.json()["tables"][0]["detail"]


def _excel_bytes(path: Path) -> bytes:
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    sheet.append(["Financial Status"])                        # merged title row
    sheet.append(["Exported On 2026-01-01"])                  # one-cell preamble
    sheet.append(["Serial No", "Firm Name", "Total Cost"])    # header
    sheet.append([1, "Alpha", 12.5])
    sheet.append([2, "Beta", 7])
    workbook.save(path)
    return path.read_bytes()


def test_a_real_excel_workbook_is_converted_and_stored(client, tmp_path):
    c, catalog, state = client
    r = post(c, filename="financial_status.xlsx", content=_excel_bytes(tmp_path / "book.xlsx"), headers=OK)
    assert r.status_code == 200, r.text
    assert r.json()["conversion"]["from"] == "financial_status.xlsx"
    assert r.json()["conversion"]["sheet"] == "Data"
    assert r.json()["tables"][0]["store"] == "ingested"

    entry = _tables(catalog)[0]
    assert entry.source == "storage:inputs/pwd/vishwakarma/financial_status.csv"
    assert entry.format == "csv"
    assert state["storage"].exists("inputs/pwd/vishwakarma/_original/financial_status.xlsx")
    columns = state["storage"].read_csv("inputs/pwd/vishwakarma/financial_status.csv")
    assert [column["name"] for column in columns] == ["serial_no", "firm_name", "total_cost"]
    assert [column["data_type"] for column in columns] == [
        "integer", "character varying", "double precision",
    ]


def test_a_corrupt_excel_file_is_a_clear_422(client):
    c, catalog, state = client
    r = post(c, filename="financial_status.xlsx", content=b"PK\x03\x04\xf2\x00\x00\x00", headers=OK)
    assert r.status_code == 422, r.text
    assert "Excel" in r.json()["problem"]
    assert r.json()["fix"]
    assert catalog.read_text() == "departments:\n"
    assert state["storage"].list("inputs/") == []


def test_a_legacy_xls_file_is_refused_with_a_fix(client):
    c, catalog, _ = client
    r = post(c, filename="old.xls", content=b"\xd0\xcf\x11\xe0", headers=OK)
    assert r.status_code == 422
    assert ".xlsx" in r.json()["fix"]
    assert catalog.read_text() == "departments:\n"


# --- slug collisions ---------------------------------------------------------------------------

def test_two_dataset_names_that_slugify_alike_are_refused(client):
    c, catalog, _ = client
    assert post(c, filename="a.txt", dataset="My Data", table="t1", headers=OK).status_code == 200
    r = post(c, filename="b.txt", dataset="my_data", table="t2", headers=OK)
    assert r.status_code == 422
    assert "same dataset id" in r.json()["problem"]
    assert [ds.name for ds in load_catalog(str(catalog))[0].datasets] == ["My Data"]


# --- schema evolution / atomicity -------------------------------------------------------------

def test_an_additive_schema_change_is_accepted(client):
    c, _, _ = client
    assert post(c, content="sno integer, firm_name varchar", headers=OK).status_code == 200
    r = post(c, content="sno integer, firm_name varchar, total_cost double precision", headers=OK)
    assert r.status_code == 200, r.text
    assert r.json()["tables"][0]["store"] == "ingested"
    assert "3 columns" in r.json()["tables"][0]["detail"]


def test_column_removal_can_be_allowed_through_the_api(client):
    c, _, _ = client
    assert post(c, headers=OK, content="sno integer, firm_name varchar").status_code == 200

    refused = post(c, headers=OK, content="sno integer")
    assert refused.status_code == 422
    assert "allow_column_removal" in str(refused.json())

    spec = c.get("/openapi.json").json()
    form = spec["paths"]["/v1/ingest"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]
    props = spec["components"]["schemas"][form["$ref"].rsplit("/", 1)[-1]]["properties"]
    assert "allow_column_removal" in props

    allowed = post(c, headers=OK, content="sno integer", allow_column_removal="true")
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["tables"][0]["store"] == "ingested"


def test_a_sync_stage_rejection_restores_the_good_input_file(client):
    """add() uploads before sync validates. On a sync-stage rejection the
    catalog *and* the stored input must go back to the accepted version, or the
    published snapshot and its registered source disagree."""

    c, catalog, state = client
    good = "sno integer, firm_name varchar, total_cost double precision"
    key = "inputs/pwd/vishwakarma/works.txt"
    assert post(c, content=good, headers=OK).status_code == 200
    assert state["storage"].read_bytes(key).decode() == good

    r = post(c, content="sno integer", headers=OK)
    assert r.status_code == 422
    assert r.json()["catalog"] == "unchanged"
    assert r.json()["file_restored"] is True
    assert state["storage"].read_bytes(key).decode() == good
    assert [t.name for t in _tables(catalog)] == ["works"]

    # The earlier failure must not poison every later sync.
    again = post(c, content=good, headers=OK)
    assert again.status_code == 200, again.text


# --- AI drafting path -------------------------------------------------------------------------

def test_the_api_drafting_path_applies_the_cli_pii_rules(client, monkeypatch):
    c, catalog, state = client
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(main.ai_metadata, "DEFAULT_DEFINITIONS", Path("does-not-exist"))

    def fake_draft(columns, definitions):
        return {
            "columns": [
                {"name": "sno", "business_description": "Serial number", "tag": "Financial"},
                {"name": "farmer_name", "business_description": "The farmer", "tag": "Made Up"},
            ],
            "dataset": {"description": "A table", "category": "CAT-1", "reason": "looks harmless"},
        }

    monkeypatch.setattr(main.ai_metadata, "draft", fake_draft)
    r = post(c, content="sno integer, farmer_name varchar", headers=OK, category="CAT-1")
    assert r.status_code == 200, r.text
    assert r.json()["descriptions"]["source"] == "claude"

    rows = state["storage"].read_csv("inputs/pwd/vishwakarma/works_metadata.csv")
    by_name = {row["name"]: row for row in rows}
    assert by_name["sno"]["tag"] == "Financial"      # a known tag survives
    assert by_name["farmer_name"]["tag"] == "PII"    # MDSF s5.1 rule overrides the model
    assert r.json()["descriptions"]["dataset_suggestion"]["category"] == "CAT-3"  # PII floor
    assert any("farmer_name" in change for change in r.json()["descriptions"]["rules_changed"])
    assert load_catalog(str(catalog))[0].datasets[0].fields["category"] == "CAT-3"  # supplied CAT-1 raised

    entry = _tables(catalog)[0]
    assert entry.metadata == "storage:inputs/pwd/vishwakarma/works_metadata.csv"


def test_a_crashing_ai_service_is_a_502_and_writes_nothing(client, monkeypatch):
    c, catalog, state = client
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def boom(columns, definitions):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(main.ai_metadata, "draft", boom)
    r = post(c, headers=OK)
    assert r.status_code == 502
    assert "nothing was stored" in r.json()["fix"]
    assert catalog.read_text() == "departments:\n"
    assert state["storage"].list("inputs/") == []


def test_a_malformed_ai_reply_is_a_502_and_writes_nothing(client, monkeypatch):
    c, catalog, state = client
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def bad_reply(columns, definitions):
        return {"unexpected": "shape"}

    monkeypatch.setattr(main.ai_metadata, "draft", bad_reply)
    r = post(c, headers=OK)
    assert r.status_code == 502
    assert "no usable column descriptions" in r.json()["problem"]
    assert catalog.read_text() == "departments:\n"
    assert state["storage"].list("inputs/") == []


# --- the API's other parity features -----------------------------------------------------------

def test_a_department_metadata_file_is_used_instead_of_claude(client, monkeypatch):
    c, catalog, state = client
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")  # must be ignored
    monkeypatch.setattr(main.ai_metadata, "draft", lambda *a: pytest.fail("AI called"))

    metadata = "name,business_description,tag\nsno,Serial number,\nfirm_name,The firm,\n"
    r = post(c, headers=OK, metadata_content=metadata)
    assert r.status_code == 200, r.text
    assert r.json()["descriptions"]["source"] == "department"
    entry = _tables(catalog)[0]
    assert entry.metadata == "storage:inputs/pwd/vishwakarma/department_meta.csv"
    assert state["storage"].exists("inputs/pwd/vishwakarma/department_meta.csv")


def test_a_field_dictionary_can_be_ingested_through_the_api(client):
    c, catalog, state = client
    dictionary = (
        "Dataset Name,Dataset Field,Data Description,Format,Mandatory (Y/N)\n"
        "works,sno,Serial,Numeric (10 Digits),Y\n"
        "works,firm_name,Firm,Text,Y\n"
    )
    r = post(c, filename="dictionary.csv", content=dictionary, headers=OK,
             table="", field_dictionary="true")
    assert r.status_code == 200, r.text
    assert r.json()["tables"][0]["id"] == "pwd.vishwakarma.* (field dictionary)"
    assert r.json()["tables"][0]["store"] == "ingested"
    dataset = load_catalog(str(catalog))[0].datasets[0]
    assert dataset.field_dictionary == "storage:inputs/pwd/vishwakarma/dictionary.csv"
    assert state["storage"].exists("inputs/pwd/vishwakarma/dictionary.csv")


def test_an_oversized_upload_is_a_413_before_anything_is_stored(client, monkeypatch):
    c, catalog, state = client
    monkeypatch.setenv("INGEST_MAX_UPLOAD_BYTES", "10")
    r = post(c, headers=OK)
    assert r.status_code == 413
    assert "upload limit" in r.json()["problem"]
    assert catalog.read_text() == "departments:\n"
    assert state["storage"].list("inputs/") == []


def test_the_catalog_is_written_atomically(client, tmp_path):
    target = tmp_path / "catalog.yaml"
    write_catalog_text(target, "departments:\n")
    assert target.read_text() == "departments:\n"
    assert list(tmp_path.glob(".catalog.yaml.*.tmp")) == []
