"""Guest HTTP tests for the metadata registry (no Authorization header).

All requests are anonymous. OpenMetadata and the database are stubbed:
- OpenMetadataClient._fetch_all / .search_tables return canned payloads.
- The DB session dependency returns canned sidecar rows and profiles.
- The shared catalog cache is cleared before every test.
"""

import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from database.database import get_session as db_get_session
from src.main import app
from src.middleware.auth import get_optional_user
from src.openmetadata import routers
from src.openmetadata.client import OpenMetadataClient
from src.openmetadata.routers import registry as registry_router


def _col(name):
    return {"name": name, "dataType": "VARCHAR", "dataTypeDisplay": "varchar"}


def _table(service, db, schema, name, description=None, columns=None, tags=None):
    return {
        "id": f"{service}-{db}-{name}",
        "name": name,
        "fullyQualifiedName": f"{service}.{db}.{schema}.{name}",
        "description": description,
        "columns": columns or [],
        "tags": tags or [],
        "owners": [],
    }


def _crop_table(name, description, columns):
    return _table(
        "agriculture_department", "distribution_record_dataset", "public",
        name, description, [_col(c) for c in columns],
    )


TABLES = [
    _table("pub", "db", "s", "pub_table", "Public stats table",
           [_col("id"), _col("name")], [{"tagFQN": "theme.economy"}]),
    _table("pwd", "vishwakarma", "public", "dep_table", None, [_col("road_safety")]),
    _table("pwd", "vishwakarma", "public", "dep_table2", "Second table", [_col("division")]),
    _table("res", "db", "s", "res_table", "Restricted table", [_col("secret_col")]),
    _table("con", "db", "s", "con_table", "Confidential table", [_col("top_secret")]),
    _table("unc", "db", "s", "unc_table", None, [_col("misc")]),
    _crop_table("crop_sales", "Crop sale records", ["crop_id", "id"]),
    _crop_table("online_booking_details", "Booking records",
                ["crop_noncrop_name_id", "total_non_crop_distributed", "id"]),
    _crop_table("current_booking", "Booking records",
                ["crop_noncrop_name_id", "id"]),
]

DATABASES = [
    {"name": "db", "displayName": "Db", "description": "Public database",
     "fullyQualifiedName": "pub.db"},
    {"name": "vishwakarma", "displayName": "Vishwakarma", "description": None,
     "fullyQualifiedName": "pwd.vishwakarma"},
    {"name": "db", "displayName": "Db", "description": None, "fullyQualifiedName": "res.db"},
    {"name": "db", "displayName": "Db", "description": None, "fullyQualifiedName": "con.db"},
    {"name": "db", "displayName": "Db", "description": None, "fullyQualifiedName": "unc.db"},
    {"name": "distribution_record_dataset", "displayName": "Distribution Record Dataset",
     "description": None,
     "fullyQualifiedName": "agriculture_department.distribution_record_dataset"},
]

VMAP = {
    "pub.db.s.pub_table": {"visibility": "public", "department": None},
    "pwd.vishwakarma.public.dep_table": {"visibility": "department", "department": "pwd"},
    "pwd.vishwakarma.public.dep_table2": {"visibility": "department", "department": "pwd"},
    "res.db.s.res_table": {"visibility": "restricted", "department": "res"},
    "con.db.s.con_table": {"visibility": "confidential", "department": "con"},
    # unc.db.s.unc_table has no row -> unclassified -> department.
    # The agriculture_department tables deliberately have no rows either:
    # production users.dataset_visibility is empty, so every table is
    # unclassified (department-by-default, owned by its FQN service).
}

PROFILES = None  # OM-only: departments come from OM services, not a local table.

SERVICES = [
    {"name": "pwd", "displayName": "Public Works Department",
     "description": "Roads and buildings.",
     "fullyQualifiedName": "pwd"},
    {"name": "pub", "displayName": "Public Department",
     "description": "Open data publisher.",
     "fullyQualifiedName": "pub"},
]


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Stub AsyncSession serving canned sidecar visibility rows."""

    def __init__(self, vmap=None):
        self._vmap = vmap if vmap is not None else VMAP

    async def execute(self, stmt):
        text = str(stmt)
        if "dataset_visibility" in text:
            rows = [
                types.SimpleNamespace(
                    fqn=fqn,
                    visibility=types.SimpleNamespace(value=meta["visibility"]),
                    department=meta["department"],
                )
                for fqn, meta in self._vmap.items()
            ]
            return _Result(rows)
        if "table_info" in text:
            return _Result([])
        raise AssertionError(f"unexpected query in guest test: {text}")


async def _fake_fetch_all(self, path, params=None):
    if path == "tables":
        return [dict(t) for t in TABLES]
    if path == "databases":
        return [dict(d) for d in DATABASES]
    if path == "services/databaseServices":
        return [dict(s) for s in SERVICES]
    raise AssertionError(f"unexpected OM path in guest test: {path}")


async def _fake_search_tables(self, query="", limit=20, page=1):
    """Emulate OM index recall: substring plus token-prefix matches over
    FQN and column names (real OM also returns structural/context hits)."""
    import re

    def _toks(s):
        return [t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t]

    qtokens = _toks(query)
    hits = []
    for t in TABLES:
        ctokens = _toks(t["fullyQualifiedName"]) + [
            tok for c in t.get("columns") or [] for tok in _toks(c.get("name"))
        ]
        if any(
            (a.startswith(b) or b.startswith(a))
            for a in qtokens
            for b in ctokens
            if len(a) >= 3 and len(b) >= 3
        ):
            hits.append(t)
    return {"data": hits, "total": len(hits), "page": page, "fallback": False}


@pytest.fixture
def client(monkeypatch):
    async def _fake_login(self):
        self._token = "test-token"

    async def _fake_get_table(self, table_id):
        if table_id not in _TABLES_BY_ID:
            raise Exception("404 Table not found")
        return dict(_TABLES_BY_ID[table_id])

    monkeypatch.setattr(OpenMetadataClient, "_login", _fake_login)
    monkeypatch.setattr(OpenMetadataClient, "_fetch_all", _fake_fetch_all)
    monkeypatch.setattr(OpenMetadataClient, "search_tables", _fake_search_tables)
    monkeypatch.setattr(OpenMetadataClient, "get_table", _fake_get_table)
    registry_router._catalog_cache.clear()

    async def _fake_session():
        yield _FakeSession()

    app.dependency_overrides[db_get_session] = _fake_session
    try:
        yield TestClient(app, raise_server_exceptions=True)
    finally:
        app.dependency_overrides.pop(db_get_session, None)
        registry_router._catalog_cache.clear()
        assert routers is not None  # keep import used


def _get(client, path, **params):
    resp = client.get(path, params=params or None)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}: {resp.text[:300]}"
    return resp.json()


def test_guest_public_dataset_everywhere_full_detail(client):
    stats = _get(client, "/registry/stats")
    assert stats["datasets"] >= 1
    catalog = _get(client, "/registry/datasets")
    pub = [c for c in catalog["items"] if c["dataset"] == "pub.db"]
    assert len(pub) == 1 and pub[0]["locked"] is False
    assert pub[0]["tags"] == ["theme.economy"]
    assert "updated_at" in pub[0]
    assert [c["name"] for c in pub[0]["tables"]] == ["pub_table"]
    assert [c["name"] for c in pub[0]["tables"][0]["columns"]] == ["id", "name"]

    public = _get(client, "/registry/datasets/public")
    assert any(c["dataset"] == "pub.db" for c in public["items"])

    detail = _get(client, "/registry/datasets/by-fqn", fqn="pub.db")
    assert detail["locked"] is False
    assert [t["name"] for t in detail["tables"]] == ["pub_table"]
    assert "columns" in detail["tables"][0]


def test_guest_department_restricted_teaser_locked_no_columns(client):
    # Datasets stay visible to anonymous as locked teasers; tables/columns
    # require sign-in (no table/column names leak in lists).
    catalog = _get(client, "/registry/datasets")
    body = client.get("/registry/datasets").text
    assert "road_safety" not in body  # no column names of non-public data
    assert "dep_table" not in body  # no table names of non-public data
    assert "secret_col" not in body

    teaser = [c for c in catalog["items"] if c["dataset"] == "pwd.vishwakarma"]
    assert len(teaser) == 1
    card = teaser[0]
    assert card["locked"] is True
    assert card["table_count"] == 2
    assert "tables" not in card
    assert set(card) <= {
        "dataset", "service", "database", "name", "description",
        "department", "department_display", "table_count", "access_level", "locked",
        "tags", "updated_at",
    }
    assert card["tags"] == [] and card["updated_at"] is None

    res = [c for c in catalog["items"] if c["dataset"] == "res.db"]
    assert len(res) == 1 and res[0]["locked"] is True

    detail = _get(client, "/registry/datasets/by-fqn", fqn="pwd.vishwakarma")
    assert detail["locked"] is True
    assert "tables" not in detail and "columns" not in client.get(
        "/registry/datasets/by-fqn", params={"fqn": "pwd.vishwakarma"}).text


def test_guest_confidential_absent_and_404(client):
    for path, params in [
        ("/registry/stats", None),
        ("/registry/datasets", None),
        ("/registry/datasets/public", None),
        ("/registry/departments", None),
    ]:
        body = client.get(path, params=params).text
        assert "con_table" not in body
        assert "top_secret" not in body
        assert "con.db" not in body
    search = client.get("/registry/search", params={"q": "con_table"})
    assert search.status_code == 200
    assert "con_table" not in search.text and "con.db" not in search.text
    resp = client.get("/registry/datasets/by-fqn", params={"fqn": "con.db"})
    assert resp.status_code == 404


def test_guest_unclassified_behaves_as_department(client):
    # Missing/invalid visibility defaults to department (locked teaser for guests).
    catalog = _get(client, "/registry/datasets")
    unc = [c for c in catalog["items"] if c["dataset"] == "unc.db"]
    assert len(unc) == 1 and unc[0]["locked"] is True
    detail = _get(client, "/registry/datasets/by-fqn", fqn="unc.db")
    assert detail["locked"] is True and "tables" not in detail


def test_guest_search_roads_returns_pwd_teaser_no_columns(client):
    # Datasets visible as teasers; tables/columns stay gated behind sign-in.
    resp = _get(client, "/registry/search", q="roads")
    dept_slugs = [d["slug"] for d in resp["departments"]["items"]]
    assert "pwd" in dept_slugs  # matched via OM service description
    ds = [c["dataset"] for c in resp["datasets"]["items"]]
    assert "pwd.vishwakarma" in ds  # dataset teaser
    assert resp["datasets"]["total"] == len(resp["datasets"]["items"])
    assert resp["total"] == sum(resp[g]["total"] for g in ("departments", "datasets", "tables", "columns"))
    text = client.get("/registry/search", params={"q": "roads"}).text
    assert "road_safety" not in text  # no column names of non-public data
    assert "dep_table" not in text  # no table names of non-public data


def test_guest_search_column_name_of_non_public_returns_nothing(client):
    resp = _get(client, "/registry/search", q="road_safety")
    assert resp["total"] == 0
    for group in ("departments", "datasets", "tables", "columns"):
        assert resp[group] == {"items": [], "total": 0}


def test_guest_counts_identical_across_home_card_and_page(client):
    stats = _get(client, "/registry/stats")
    catalog = _get(client, "/registry/datasets")
    directory = _get(client, "/registry/departments")
    page = _get(client, "/registry/departments/pwd")

    assert stats["datasets"] == catalog["total"] == len(catalog["items"])
    assert stats["departments"] == directory["total"] == len(directory["items"])
    card = [d for d in directory["items"] if d["slug"] == "pwd"][0]
    assert card["dataset_count"] == page["total"] == len(page["datasets"])
    assert stats["tables"] == sum(c["table_count"] for c in catalog["items"])


def test_guest_legacy_schema_fqn_resolves_to_database(client):
    detail = _get(client, "/registry/datasets/by-fqn", fqn="pwd.vishwakarma.public")
    assert detail["dataset"] == "pwd.vishwakarma"


def test_guest_scope_filters_groups(client):
    resp = _get(client, "/registry/search", q="roads", scope="departments")
    assert resp["departments"]["total"] >= 1
    assert resp["datasets"] == {"items": [], "total": 0}
    assert resp["tables"] == {"items": [], "total": 0}
    assert resp["columns"] == {"items": [], "total": 0}


def _viewer(role, department):
    import types as _t

    return _t.SimpleNamespace(role=_t.SimpleNamespace(value=role), department=department)


def _detail_table(table_id, fqn, name, columns):
    return {
        "id": table_id,
        "name": name,
        "fullyQualifiedName": fqn,
        "description": f"{name} description",
        "columns": [
            {
                "name": c,
                "dataType": "VARCHAR",
                "dataTypeDisplay": "varchar",
                "description": f"{c} description",
                "tags": [{"tagFQN": "MDSF.Internal", "name": "Internal"}],
            }
            for c in columns
        ],
        "owners": [{"displayName": "Data Owner"}],
        "tags": [{"tagFQN": "MDSF.Public", "name": "Public"}],
        "updatedAt": 1791199916652,
    }


_TABLES_BY_ID = {
    "t-pub": _detail_table("t-pub", "pub.db.s.pub_table", "pub_table", ["id", "name"]),
    "t-dep": _detail_table("t-dep", "pwd.vishwakarma.public.dep_table", "dep_table", ["road_safety"]),
    "t-con": _detail_table("t-con", "con.db.s.con_table", "con_table", ["top_secret"]),
}


def test_admin_search_crop_full_tables_with_matched_in(client):
    async def _admin():
        return _viewer("admin", None)

    app.dependency_overrides[get_optional_user] = _admin
    try:
        resp = _get(client, "/registry/search", q="crop")
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
    assert resp["datasets"]["total"] == 1
    assert resp["datasets"]["items"][0]["dataset"] == "agriculture_department.distribution_record_dataset"
    assert resp["tables"]["total"] == 3
    assert {t["name"] for t in resp["tables"]["items"]} == {
        "crop_sales", "online_booking_details", "current_booking"}
    assert resp["columns"]["total"] == 4
    assert resp["total"] == 8
    by_name = {t["name"]: t for t in resp["tables"]["items"]}
    assert "name" in by_name["crop_sales"]["matched_in"]
    assert by_name["online_booking_details"]["matched_in"] == ["column"]
    assert "crop_noncrop_name_id" in by_name["online_booking_details"]["matched_columns"]
    assert "total_non_crop_distributed" in by_name["online_booking_details"]["matched_columns"]
    assert by_name["current_booking"]["matched_columns"] == ["crop_noncrop_name_id"]


def test_user_without_access_crop_strict_tables_no_columns(client):
    async def _user():
        return _viewer("user", "other")

    app.dependency_overrides[get_optional_user] = _user
    try:
        resp = _get(client, "/registry/search", q="crop")
        body = client.get("/registry/search", params={"q": "crop"}).text
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
    assert resp["datasets"]["total"] == 1
    assert resp["datasets"]["items"][0].get("locked") is True
    assert resp["tables"]["total"] == 1
    assert resp["tables"]["items"][0]["name"] == "crop_sales"
    assert resp["columns"] == {"items": [], "total": 0}
    assert "crop_noncrop_name_id" not in body
    assert "total_non_crop_distributed" not in body
    assert "crop_id" not in body


def test_guest_crop_dataset_query_teaser_only(client):
    # Datasets visible as teasers; tables/columns require sign-in.
    resp = _get(client, "/registry/search", q="distribution")
    assert resp["datasets"]["total"] == 1
    assert resp["datasets"]["items"][0].get("locked") is True
    assert resp["tables"] == {"items": [], "total": 0}
    assert resp["columns"] == {"items": [], "total": 0}
    body = client.get("/registry/search", params={"q": "distribution"}).text
    assert "crop_noncrop_name_id" not in body
    assert "crop_sales" not in body
    assert "total_non_crop_distributed" not in body


def test_user_other_department_gets_teaser_with_table_names_no_columns(client):
    async def _user():
        return _viewer("user", "other")

    app.dependency_overrides[get_optional_user] = _user
    try:
        catalog = _get(client, "/registry/datasets")
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
    agri = [c for c in catalog["items"]
            if c["dataset"] == "agriculture_department.distribution_record_dataset"]
    assert len(agri) == 1 and agri[0]["locked"] is True
    teasers = [t for t in catalog.get("teasers", [])
               if (t["fullyQualifiedName"] or "").startswith("agriculture_department.")]
    assert len(teasers) == 3
    assert {t["name"] for t in teasers} == {
        "crop_sales", "online_booking_details", "current_booking"}
    assert all(t["columns"] == [] for t in teasers)
    assert all(t["access_level"] == "department" for t in teasers)


def test_guest_never_receives_non_public_table_names(client):
    forbidden = [
        "dep_table", "res_table", "con_table", "unc_table",
        "crop_sales", "online_booking_details", "current_booking",
        "road_safety", "secret_col", "top_secret", "misc", "division",
        "crop_id", "crop_noncrop_name_id", "total_non_crop_distributed",
    ]
    bodies = [
        client.get("/registry/datasets").text,
        client.get("/registry/datasets/public").text,
        client.get("/registry/search", params={"q": "distribution"}).text,
        client.get("/registry/search", params={"q": "roads"}).text,
        client.get("/registry/datasets/by-fqn",
                   params={"fqn": "pwd.vishwakarma"}).text,
        client.get("/registry/datasets/by-fqn",
                   params={"fqn": "agriculture_department.distribution_record_dataset"}).text,
    ]
    for body in bodies:
        for name in forbidden:
            assert name not in body, f"{name!r} leaked to guest"


def _as_viewer(client, role, department):
    async def _user():
        return _viewer(role, department)

    app.dependency_overrides[get_optional_user] = _user
    return get_optional_user


def test_user_without_access_table_locked_no_column_detail(client):
    _as_viewer(client, "user", "other")
    try:
        resp = client.get("/registry/tables/t-dep")
        assert resp.status_code == 200, resp.text[:300]
        body = resp.json()
        assert body["locked"] is True
        assert body["columns"] == []
        assert body["column_count"] == 1
        assert "tags" not in body and "owners" not in body and "facts" not in body
        text = resp.text
        assert "road_safety" not in text
        assert "varchar" not in text
        assert "Internal" not in text
    finally:
        app.dependency_overrides.pop(get_optional_user, None)


def test_guest_table_non_public_401_no_metadata(client):
    # Anonymous direct table access to non-public data is 401, no metadata.
    resp = client.get("/registry/tables/t-dep")
    assert resp.status_code == 401, resp.text[:300]
    assert "road_safety" not in resp.text and "dep_table" not in resp.text
    # Public tables remain fully visible.
    pub = client.get("/registry/tables/t-pub")
    assert pub.status_code == 200, pub.text[:300]
    assert [c["name"] for c in pub.json()["columns"]] == ["id", "name"]


def test_table_confidential_and_missing_404(client):
    assert client.get("/registry/tables/t-con").status_code == 404
    assert client.get("/registry/tables/nope").status_code == 404


def test_admin_table_full_with_facts(client):
    _as_viewer(client, "admin", None)
    try:
        resp = client.get("/registry/tables/t-dep")
        assert resp.status_code == 200, resp.text[:300]
        body = resp.json()
        assert body.get("locked", False) is False
        assert [c["name"] for c in body["columns"]] == ["road_safety"]
        assert body["facts"]["owner"] == "Data Owner"
        assert body["facts"]["updated_at"] == 1791199916652
    finally:
        app.dependency_overrides.pop(get_optional_user, None)


def test_csv_refused_without_full_access(client):
    _as_viewer(client, "user", "other")
    try:
        assert client.get("/registry/tables/t-dep/dictionary").status_code == 403
        assert client.get("/registry/tables/t-con/dictionary").status_code == 404
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
    # Anonymous receives 401 (sign-in prompt), never the CSV.
    assert client.get("/registry/tables/t-dep/dictionary").status_code == 401


def test_csv_download_full_access(client):
    resp = client.get("/registry/tables/t-pub/dictionary")
    assert resp.status_code == 200, resp.text[:200]
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().split("\n")
    # Metadata header lines, then the column header with data_classification.
    assert lines[0].startswith("# table: pub_table")
    assert lines[1].startswith("# dataset: pub.db")
    assert lines[2].startswith("# data_classification: ")
    assert lines[3].startswith("# api_available: ")
    assert lines[4] == "column_name,data_type,description,tags,data_classification"
    assert any(l.startswith("id,varchar,") for l in lines[5:])
