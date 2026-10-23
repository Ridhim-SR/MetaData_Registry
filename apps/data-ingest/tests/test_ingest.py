import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main  # noqa: E402
from src.storage.local import LocalObjectStorage  # noqa: E402

DDL = "sno integer NOT NULL, firm_name character varying(100), total_cost double precision"


@pytest.fixture
def client(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("departments:\n")
    state = {"env": "local", "branch": "main", "storage": LocalObjectStorage(str(tmp_path / "s")),
             "catalog": catalog, "client": None, "setup": None}
    monkeypatch.setattr(main, "runtime", lambda: state)
    monkeypatch.setattr(main, "backup_after_run", lambda storage: True)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return TestClient(main.app), catalog, state


def _post(client, headers=None, **extra):
    data = {"department": "pwd", "dataset": "vishwakarma", "table": "works",
            "department_name": "Public Works Department", **extra}
    return client.post("/v1/ingest", data=data, files={"file": ("works.txt", DDL)}, headers=headers or {})


def test_status_reports_the_environment(client):
    c, _, _ = client
    assert c.get("/v1/status").json()["environment"] == "local"


def test_a_change_without_the_environment_header_is_refused(client):
    c, catalog, _ = client
    r = _post(c)
    assert r.status_code == 409 and "local" in r.json()["fix"]
    assert catalog.read_text() == "departments:\n"


def test_a_wrong_environment_header_is_refused(client):
    c, _, _ = client
    assert _post(c, headers={"X-Confirm-Environment": "production"}).status_code == 409


def test_ingest_stores_file_writes_dataset_fields_and_ingests(client):
    c, catalog, state = client
    r = _post(c, headers={"X-Confirm-Environment": "local"}, category="CAT-2",
              description="Works and tenders", steward="PWD Data Cell")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tables"][0]["store"] == "ingested" and body["tables"][0]["publish"] == "skipped"
    assert body["backup_ok"] is True and body["descriptions"]["source"].startswith("none")
    text = catalog.read_text()
    assert "category: CAT-2" in text and "steward: PWD Data Cell" in text and "description: Works and tenders" in text
    assert state["storage"].exists("inputs/pwd/vishwakarma/works.txt")


def test_dry_run_changes_nothing_and_needs_no_header(client):
    c, catalog, state = client
    r = _post(c, dry_run="true", category="CAT-3")
    assert r.status_code == 200 and r.json()["dry_run"] is True
    assert any("set category" in ch for ch in r.json()["catalog_changes"])
    assert catalog.read_text() == "departments:\n"
    assert not state["storage"].exists("inputs/pwd/vishwakarma/works.txt")


def test_a_bad_category_is_a_clear_422_and_nothing_is_stored(client):
    c, catalog, state = client
    r = _post(c, headers={"X-Confirm-Environment": "local"}, category="CAT-9")
    assert r.status_code == 422 and r.json()["problem"]
    assert not state["storage"].exists("inputs/pwd/vishwakarma/works.txt")


def test_a_rejected_file_is_a_422_and_leaves_the_catalog_as_it_was(client):
    c, catalog, _ = client
    ok = {"X-Confirm-Environment": "local"}
    assert _post(c, headers=ok, table="tenders").status_code == 200
    before = catalog.read_text()

    r = c.post("/v1/ingest", headers=ok, files={"file": ("tenders.txt", "sno integer NOT NULL")},
               data={"department": "pwd", "dataset": "vishwakarma", "table": "tenders"})
    assert r.status_code == 422
    assert "missing" in r.json()["problem"] and r.json()["catalog"] == "unchanged"
    assert catalog.read_text() == before


def test_a_failed_publish_is_a_502_that_says_the_files_are_stored(client, monkeypatch):
    c, _, state = client
    real_sync = main.sync

    def failing(storage, departments, **kw):
        out = real_sync(storage, departments, **kw)
        for o in out:
            o.publish = "failed"
            o.detail = "OpenMetadata unreachable"
        return out

    monkeypatch.setattr(main, "sync", failing)
    r = _post(c, headers={"X-Confirm-Environment": "local"})
    assert r.status_code == 502 and r.json()["stored"] is True
    assert state["storage"].exists("inputs/pwd/vishwakarma/works.txt")


def test_a_drafting_failure_is_a_502_and_stores_nothing(client, monkeypatch):
    c, catalog, state = client

    def boom(raw, work):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(main, "draft_descriptions", boom)
    r = _post(c, headers={"X-Confirm-Environment": "local"})
    assert r.status_code == 502 and "nothing was stored" in r.json()["fix"]
    assert catalog.read_text() == "departments:\n"
    assert not state["storage"].exists("inputs/pwd/vishwakarma/works.txt")


def test_api_key_is_required_when_one_is_configured(client, monkeypatch):
    c, _, _ = client
    monkeypatch.setenv("INGEST_API_KEY", "s3cret")
    ok = {"X-Confirm-Environment": "local"}
    assert _post(c, headers=ok).status_code == 401
    assert _post(c, headers={**ok, "X-API-Key": "wrong"}).status_code == 401
    assert _post(c, headers={**ok, "X-API-Key": "s3cret"}).status_code == 200


def test_production_refuses_to_start_without_an_api_key(monkeypatch):
    monkeypatch.setattr(main, "_state", {})
    monkeypatch.setattr(main.config, "load_env", lambda: "production")  # what the production branch resolves to
    monkeypatch.delenv("INGEST_API_KEY", raising=False)
    with pytest.raises(main.HTTPException) as caught:
        main.runtime()
    assert caught.value.status_code == 503
    assert "INGEST_API_KEY" in caught.value.detail["problem"]


def test_add_only_uploads_and_registers_but_does_not_sync(client):
    c, catalog, state = client
    r = _post(c, headers={"X-Confirm-Environment": "local"}, run_sync="false", category="CAT-2")
    assert r.status_code == 200 and "tables" not in r.json() and "POST /v1/sync" in r.json()["next"]
    assert "category: CAT-2" in catalog.read_text()
    assert state["storage"].exists("inputs/pwd/vishwakarma/works.txt")
    assert not state["storage"].exists("_lookups/tables.csv")  # nothing ingested yet


def test_run_sync_defaults_to_true_when_the_field_is_omitted(client):
    """FastAPI 0.161 turns an omitted bool Form into False even when its
    default is True, which silently skipped sync. The default must not depend
    on the installed FastAPI version."""

    c, _, _ = client
    r = _post(c, headers={"X-Confirm-Environment": "local"})
    assert r.status_code == 200, r.text
    assert r.json()["tables"][0]["store"] == "ingested"

    explicit = _post(c, headers={"X-Confirm-Environment": "local"}, run_sync="true")
    assert explicit.status_code == 200, explicit.text
    assert explicit.json()["tables"][0]["store"] == "unchanged"


def test_sync_after_add_ingests_it(client):
    c, _, state = client
    ok = {"X-Confirm-Environment": "local"}
    _post(c, headers=ok, run_sync="false")
    r = c.post("/v1/sync", headers=ok, data={"department": "pwd"})
    assert r.status_code == 200
    assert [(t["store"], t["publish"]) for t in r.json()["tables"]] == [("ingested", "skipped")]
    again = c.post("/v1/sync", headers=ok, data={})
    assert [t["store"] for t in again.json()["tables"]] == ["unchanged"]


def test_sync_dry_run_needs_no_header_and_writes_nothing(client):
    c, _, state = client
    _post(c, headers={"X-Confirm-Environment": "local"}, run_sync="false")
    r = c.post("/v1/sync", data={"dry_run": "true"})
    assert r.status_code == 200 and r.json()["tables"][0]["store"] == "would ingest"
    assert not state["storage"].exists("_lookups/tables.csv")


def test_sync_without_header_is_refused(client):
    c, _, _ = client
    assert c.post("/v1/sync", data={}).status_code == 409
