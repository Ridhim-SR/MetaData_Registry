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
     "fullyQualifiedName": "pub.db",
     # OM Custom Properties + DataSensitivity tag, as OM returns them.
     "extension": {"apiAvailable": "Y", "datasetOwner": "Pub Owner", "frequency": "monthly",
                   "timeline": "2020-2024", "datasetSteward": "Pub Steward"},
     "tags": [{"tagFQN": "DataSensitivity.CAT-1", "name": "CAT-1",
               "description": "Open Access"}]},
    {"name": "vishwakarma", "displayName": "Vishwakarma", "description": None,
     "fullyQualifiedName": "pwd.vishwakarma",
     "extension": {"apiAvailable": "N", "datasetOwner": "", "frequency": "yearly",
                   "timeline": "2014-15 to 2025-26"}},
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

# Sidecar dataset defaults (users.dataset_info) and table rows (users.table_info).
DATASET_INFO = {
    "pwd.vishwakarma": {
        "owner": "PWD Data Cell", "steward": "Steward S", "frequency": "Monthly", "timeline": "2020-2025",
    },
}
TABLE_INFO = {
    "pwd.vishwakarma.public.dep_table": {
        "api_available": True, "dataset_owner": None, "frequency": None, "timeline": "2024 only",
    },
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
    """Stub AsyncSession serving canned sidecar visibility/info rows."""

    def __init__(self, vmap=None, info=None):
        self._vmap = vmap if vmap is not None else VMAP
        self._info = info if info is not None else TABLE_INFO

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
        if "dataset_info" in text:
            return _Result([types.SimpleNamespace(fqn=f, **v) for f, v in DATASET_INFO.items()])
        if "table_info" in text:
            return _Result([types.SimpleNamespace(fqn=f, **v) for f, v in self._info.items()])
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

    async def _fake_get_database_by_fqn(self, fqn):
        database = _DATABASES_BY_FQN.get(fqn)
        if database is None:
            raise Exception(f"404 Database {fqn} not found")
        return dict(database)

    monkeypatch.setattr(OpenMetadataClient, "_login", _fake_login)
    monkeypatch.setattr(OpenMetadataClient, "_fetch_all", _fake_fetch_all)
    monkeypatch.setattr(OpenMetadataClient, "search_tables", _fake_search_tables)
    monkeypatch.setattr(OpenMetadataClient, "get_table", _fake_get_table)
    monkeypatch.setattr(OpenMetadataClient, "get_database_by_fqn", _fake_get_database_by_fqn)
    registry_router._catalog_cache.clear()
    registry_router.clear_sidecar_caches()

    async def _fake_session():
        yield _FakeSession()

    app.dependency_overrides[db_get_session] = _fake_session
    try:
        yield TestClient(app, raise_server_exceptions=True)
    finally:
        app.dependency_overrides.pop(db_get_session, None)
        registry_router._catalog_cache.clear()
        registry_router.clear_sidecar_caches()
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
    # Dataset facts ride on full cards so the catalog can filter by them.
    assert pub[0]["info"]["table_count"] == 1
    assert {"owner", "steward", "frequency", "timeline", "api_available"} <= set(pub[0]["info"])

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
        "tags", "updated_at", "classification", "dataset_type",
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


def test_guest_stats_by_classification_matches_catalog(client):
    stats = _get(client, "/registry/stats")
    catalog = _get(client, "/registry/datasets")
    by_cat = stats["by_classification"]
    assert set(by_cat) == {"CAT-1", "CAT-2", "CAT-3", "CAT-4", "unclassified"}
    assert sum(by_cat.values()) == stats["datasets"]
    for key in ("CAT-1", "CAT-2", "CAT-3", "CAT-4"):
        assert by_cat[key] == sum(1 for c in catalog["items"] if c["classification"] == key)
    assert by_cat["CAT-1"] >= 1  # pub.db is tagged CAT-1


def test_guest_stats_by_dataset_type_matches_catalog(client, monkeypatch):
    db = next(d for d in DATABASES if d["fullyQualifiedName"] == "pub.db")
    monkeypatch.setitem(db, "extension", {**(db.get("extension") or {}), "datasetType": "Citizen Centric"})
    stats = _get(client, "/registry/stats")
    catalog = _get(client, "/registry/datasets")
    by_type = stats["by_dataset_type"]
    assert set(by_type) == {"Citizen Centric", "Administrative", "unspecified"}
    assert sum(by_type.values()) == stats["datasets"]
    assert by_type["Citizen Centric"] == 1
    assert [c["dataset_type"] for c in catalog["items"] if c["dataset"] == "pub.db"] == ["Citizen Centric"]


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

# OM database entities keyed by database FQN: the custom properties
# (extension) data_services publishes as dataset-level docs -- served as
# a table's `info` by registry_table -> _dataset_info.
_DATABASES_BY_FQN = {
    "pub.db": {
        "fullyQualifiedName": "pub.db",
        "extension": {
            "apiAvailable": "Y",
            "datasetOwner": "Pub Owner",
            "frequency": "monthly",
            "timeline": "2020-2024",
        },
    },
    "pwd.vishwakarma": {
        "fullyQualifiedName": "pwd.vishwakarma",
        "extension": {
            "apiAvailable": "N",
            "datasetOwner": "",
            "frequency": "yearly",
            "timeline": "2014-15 to 2025-26",
        },
    },
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


def test_table_info_served_from_om_database_custom_properties(client):
    """Dataset docs (frequency/timeline/API available/owner) come from the
    OM database entity's extension -- what data_services publishes -- so
    every catalog table has them without the manual sidecar POST."""

    resp = client.get("/registry/tables/t-pub")  # public table: guest gets full access
    assert resp.status_code == 200, resp.text[:300]
    body = resp.json()
    info = body["info"]
    assert info["api_available"] is True
    assert info["dataset_owner"] == "Pub Owner"
    assert info["frequency"] == "monthly"
    assert info["timeline"] == "2020-2024"
    assert body["facts"]["frequency"] == "monthly"


def test_sidecar_row_overrides_om_extension_field_by_field(client):
    """A manual POST /openmetadata/metadata/tables row wins where it has an
    answer; OM fills the fields it leaves blank."""

    async def _session_with_row():
        yield _FakeSession(info={
            "pwd.vishwakarma.public.dep_table": {
                "api_available": None,
                "dataset_owner": "Hand Set Owner",
                "frequency": "quarterly",
                "timeline": None,
            }
        })

    app.dependency_overrides[db_get_session] = _session_with_row
    _as_viewer(client, "admin", None)
    try:
        resp = client.get("/registry/tables/t-dep")
        assert resp.status_code == 200, resp.text[:300]
        info = resp.json()["info"]
        assert info["frequency"] == "quarterly"            # sidecar wins
        assert info["dataset_owner"] == "Hand Set Owner"   # sidecar wins
        assert info["timeline"] == "2014-15 to 2025-26"    # OM fills the gap
        assert info["api_available"] is False              # "N" mapped to bool
    finally:
        app.dependency_overrides.pop(db_get_session, None)
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


def test_admin_table_facts_inherit_dataset_defaults(client):
    _as_viewer(client, "admin", None)
    try:
        body = _get(client, "/registry/tables/t-dep")
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
    facts = body["facts"]
    # OM table owner wins over the dataset owner.
    assert facts["owner"] == "Data Owner" and facts["origin"]["owner"] == "table"
    # Steward (sidecar) and frequency (OM custom property, which wins over
    # the sidecar's "Monthly") are inherited from the dataset.
    assert facts["steward"] == "Steward S" and facts["origin"]["steward"] == "dataset"
    assert facts["frequency"] == "yearly" and facts["origin"]["frequency"] == "dataset"
    # The table's own timeline overrides the dataset timeline.
    assert facts["timeline"] == "2024 only" and facts["origin"]["timeline"] == "table"
    assert facts["api_available"] is True
    # Classification comes from the table's MDSF.* tag.
    assert body["data_classification"] == "Public"
    assert facts["data_classification"] == "Public"


def test_table_sidecar_row_overrides_dataset_values(client):
    async def _session_with_row():
        yield _FakeSession(info={
            "pub.db.s.pub_table": {
                "api_available": False, "dataset_owner": None, "frequency": "Daily", "timeline": None,
            }
        })

    app.dependency_overrides[db_get_session] = _session_with_row
    try:
        facts = _get(client, "/registry/tables/t-pub")["facts"]
    finally:
        app.dependency_overrides.pop(db_get_session, None)
    assert facts["frequency"] == "Daily" and facts["origin"]["frequency"] == "table"
    assert facts["api_available"] is False and facts["origin"]["api_available"] == "table"
    assert facts["timeline"] == "2020-2024" and facts["origin"]["timeline"] == "dataset"


def test_admin_dataset_info_summary(client):
    _as_viewer(client, "admin", None)
    try:
        card = _get(client, "/registry/datasets/by-fqn", fqn="pwd.vishwakarma")
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
    info = card["info"]
    assert info["owner"] == "PWD Data Cell"
    assert info["steward"] == "Steward S"
    assert info["frequency"] == "yearly"  # OM custom property beats the sidecar
    assert info["table_count"] == 2
    assert info["api_tables"] == 1 and info["api_known"] == 1


def test_guest_locked_dataset_has_no_info(client):
    card = _get(client, "/registry/datasets/by-fqn", fqn="pwd.vishwakarma")
    assert card["locked"] is True
    assert "info" not in card


def test_dataset_info_update_requires_admin(client):
    resp = client.put("/registry/datasets/info", json={"fqn": "pwd.vishwakarma", "owner": "X"})
    assert resp.status_code in (401, 403)


def test_om_custom_properties_flow_to_dataset_and_table(client):
    card = _get(client, "/registry/datasets/by-fqn", fqn="pub.db")
    info = card["info"]
    assert info["owner"] == "Pub Owner"
    assert info["frequency"] == "monthly"
    assert info["steward"] == "Pub Steward"
    assert info["timeline"] == "2020-2024"
    assert info["api_available"] is True  # "Y"
    assert info["data_classification"] == "CAT-1"
    assert info["data_classification_description"] == "Open Access"

    facts = _get(client, "/registry/tables/t-pub")["facts"]
    # No table-level values: everything is inherited from the OM database.
    assert facts["frequency"] == "monthly" and facts["origin"]["frequency"] == "dataset"
    assert facts["steward"] == "Pub Steward" and facts["origin"]["steward"] == "dataset"
    assert facts["timeline"] == "2020-2024" and facts["origin"]["timeline"] == "dataset"
    assert facts["api_available"] is True and facts["origin"]["api_available"] == "dataset"
    # The table's own MDSF tag wins over the dataset's CAT tag.
    assert facts["data_classification"] == "Public"


def _tag_database(monkeypatch, fqn, level):
    db = next(d for d in DATABASES if d["fullyQualifiedName"] == fqn)
    monkeypatch.setitem(db, "tags", [{"tagFQN": f"DataSensitivity.CAT-{level}", "name": f"CAT-{level}"}])


def test_guest_cat1_dataset_is_open_without_login(client, monkeypatch):
    # unc.db has no sidecar row (department by default); CAT-1 opens it.
    _tag_database(monkeypatch, "unc.db", 1)
    card = _get(client, "/registry/datasets/by-fqn", fqn="unc.db")
    assert card["locked"] is False
    assert card["access_level"] == "public"
    assert card["classification"] == "CAT-1"
    assert [t["name"] for t in card["tables"]] == ["unc_table"]
    public = _get(client, "/registry/datasets/public")
    assert "unc.db" in {c["dataset"] for c in public["items"]}


def test_cat4_dataset_hidden_from_guests(client, monkeypatch):
    _tag_database(monkeypatch, "pub.db", 4)
    assert client.get("/registry/datasets/by-fqn", params={"fqn": "pub.db"}).status_code == 404
    assert client.get("/registry/tables/t-pub").status_code == 404
    # Not counted either: guests never learn that a CAT-4 dataset exists.
    stats = _get(client, "/registry/stats")
    assert stats["by_classification"]["CAT-4"] == 0
    assert sum(stats["by_classification"].values()) == stats["datasets"]


def test_responses_carry_server_timing_breakdown(client):
    resp = client.get("/registry/stats")
    assert resp.status_code == 200
    header = resp.headers["Server-Timing"]
    for metric in ("db;dur=", "dbconn;dur=", "om;dur=", "app;dur=", "total;dur="):
        assert metric in header
    assert "Timing-Allow-Origin" in resp.headers


class _CountingSession(_FakeSession):
    """Fake session that counts dataset_visibility reads."""

    visibility_reads = 0

    async def execute(self, stmt):
        if "dataset_visibility" in str(stmt):
            _CountingSession.visibility_reads += 1
        return await super().execute(stmt)

    def add(self, obj):
        pass

    async def commit(self):
        pass


def _use_counting_session():
    _CountingSession.visibility_reads = 0

    async def _session():
        yield _CountingSession()

    app.dependency_overrides[db_get_session] = _session


def test_visibility_loaded_once_for_many_requests(client):
    _use_counting_session()
    for path in ("/registry/stats", "/registry/departments", "/registry/datasets/public", "/registry/stats"):
        assert client.get(path).status_code == 200
    assert client.get("/registry/tables/t-pub").status_code == 200
    assert _CountingSession.visibility_reads == 1


def test_visibility_reloaded_after_ttl(client, monkeypatch):
    _use_counting_session()
    monkeypatch.setattr(registry_router, "SIDECAR_TTL_SECONDS", 0)
    client.get("/registry/stats")
    client.get("/registry/stats")
    assert _CountingSession.visibility_reads == 2


def test_visibility_write_clears_cache(client):
    import asyncio

    _use_counting_session()
    client.get("/registry/stats")
    assert registry_router._visibility_cache.loaded
    asyncio.run(registry_router.upsert_table_visibility(
        _CountingSession(), fqn="pub.db.s.new_table", visibility="public", department=None,
    ))
    assert not registry_router._visibility_cache.loaded
    client.get("/registry/stats")
    assert _CountingSession.visibility_reads == 3  # first load, the write's own lookup, reload


def _bearer(role, department, user_id=7):
    from src.middleware.auth import create_access_token

    token = create_access_token({"sub": user_id, "role": role, "department": department})
    return {"Authorization": f"Bearer {token}"}


def test_signed_in_reads_use_token_claims_without_db_user_lookup(client):
    # _FakeSession raises on any unexpected query (e.g. users.users), so
    # this fails if a signed-in read still loads the user from the DB.
    resp = client.get("/registry/datasets/by-fqn", params={"fqn": "con.db"},
                      headers=_bearer("admin", None))
    assert resp.status_code == 200  # confidential: admin only -> role came from the token
    resp = client.get("/registry/datasets/by-fqn", params={"fqn": "pwd.vishwakarma"},
                      headers=_bearer("user", "pwd"))
    assert resp.status_code == 200 and resp.json()["locked"] is False  # own department
    assert client.get("/registry/datasets/by-fqn", params={"fqn": "con.db"},
                      headers=_bearer("user", "pwd")).status_code == 404


def test_invalid_token_is_anonymous_on_reads(client):
    resp = client.get("/registry/datasets/by-fqn", params={"fqn": "con.db"},
                      headers={"Authorization": "Bearer not-a-token"})
    assert resp.status_code == 404


def test_user_cache_keeps_every_field_auth_me_returns():
    from database.models import AuthProvider, User, UserRole
    from src.middleware import auth
    from src.schemas.auth import MeResponse

    user = User(id=99, username="ann", email="ann@x", first_name="Ann", last_name="Lee",
                role=UserRole.user, department="agri", auth_provider=AuthProvider.google)
    auth._store_user_cache(user)
    try:
        cached = auth._cached_user(99)
        me = MeResponse(id=cached.id, username=cached.username, email=cached.email,
                        first_name=cached.first_name, last_name=cached.last_name,
                        role=cached.role, department=cached.department,
                        auth_provider=cached.auth_provider)
        assert me.first_name == "Ann" and me.auth_provider == AuthProvider.google
    finally:
        auth.invalidate_user_cache(99)


class _InfoCountingSession(_CountingSession):
    info_reads = 0

    async def execute(self, stmt):
        text = str(stmt)
        if "table_info" in text or "dataset_info" in text:
            _InfoCountingSession.info_reads += 1
        return await super().execute(stmt)


def test_table_and_dataset_info_cached_across_pages(client):
    _InfoCountingSession.info_reads = 0

    async def _session():
        yield _InfoCountingSession()

    app.dependency_overrides[db_get_session] = _session
    _as_viewer(client, "admin", None)
    try:
        for _ in range(3):
            assert client.get("/registry/datasets/by-fqn", params={"fqn": "pwd.vishwakarma"}).status_code == 200
            assert client.get("/registry/tables/t-dep").status_code == 200
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
    assert _InfoCountingSession.info_reads == 2  # one load each of table_info and dataset_info


def test_table_info_write_clears_cache(client):
    import asyncio

    _use_counting_session()
    client.get("/registry/tables/t-pub")
    assert registry_router._table_info_cache.loaded
    asyncio.run(registry_router.upsert_table_info(
        _CountingSession(), fqn="pub.db.s.pub_table", api_available=True,
        dataset_owner=None, frequency=None, timeline=None,
    ))
    assert not registry_router._table_info_cache.loaded


def test_login_caches_user_for_auth_me():
    import asyncio

    from database.models import AuthProvider, User, UserRole
    from src.middleware import auth
    from src.schemas.auth import LoginRequest
    from src.services.auth import login_user

    user = User(id=123, username="bo", email="bo@x", first_name="Bo", last_name=None,
                password_hash=auth.hash_password("pw"), role=UserRole.user,
                department="agri", auth_provider=AuthProvider.local)

    class _LoginSession:
        async def execute(self, stmt):
            return _Result([user])

    auth.invalidate_user_cache(123)
    try:
        asyncio.run(login_user(LoginRequest(email="bo@x", password="pw"), _LoginSession()))
        cached = auth._cached_user(123)
        assert cached is not None and cached.first_name == "Bo"  # /auth/me needs no DB now
    finally:
        auth.invalidate_user_cache(123)


def test_dataset_list_filters_facets_and_paging_run_server_side(client):
    everything = _get(client, "/registry/datasets")
    assert everything["total"] == len(everything["items"]) >= 2
    api = {i["value"]: i["count"] for i in everything["facets"]["api"]}
    assert api == {"yes": 1, "no": 0}  # pwd's "N" is behind a locked teaser
    assert {"value": "CAT-1", "count": 1} in everything["facets"]["classification"]

    for params in ({"api": "yes"}, {"frequency": "monthly"}, {"year_from": 2023},
                   {"classification": "cat-1"}, {"tag": "theme.economy"}):
        body = _get(client, "/registry/datasets", **params)
        assert [c["dataset"] for c in body["items"]] == ["pub.db"], params
        assert body["total"] == 1 and body["department_count"] == 1

    # OR within one filter (repeated parameter), AND across filters.
    resp = client.get("/registry/datasets", params=[("department", "pub"), ("department", "pwd")])
    assert {c["service"] for c in resp.json()["items"]} == {"pub", "pwd"}
    assert _get(client, "/registry/datasets", department="pwd", api="yes")["total"] == 0

    page2 = _get(client, "/registry/datasets", sort="name", size=1, page=2)
    names = sorted(c["name"].lower() for c in everything["items"])
    assert page2["total"] == everything["total"]
    assert [c["name"].lower() for c in page2["items"]] == names[1:2]
    assert client.get("/registry/datasets", params={"sort": "bogus"}).status_code == 422


def test_search_applies_the_same_filters(client):
    body = _get(client, "/registry/search", q="table")
    assert "facets" in body and body["datasets"]["total"] >= 1
    filtered = _get(client, "/registry/search", q="table", api="no")
    assert filtered["datasets"]["total"] == 0 and filtered["tables"]["total"] == 0
