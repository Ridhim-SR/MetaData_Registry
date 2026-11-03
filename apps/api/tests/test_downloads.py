"""Unit tests for the read-only download API (no S3/Wasabi required)."""

import csv
import io
import json
import os
import sys
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.curated_storage import CuratedStorage  # noqa: E402
from src.routers.downloads import router, storage_dep  # noqa: E402

HEADERS = {"X-API-Key": "test-key"}


class FakeStorage:
    def __init__(self, files):
        self.files = files

    def list(self, prefix):
        return sorted(key for key in self.files if key.startswith(prefix))

    def read(self, path):
        return self.files[path]

    def read_csv(self, path):
        return list(csv.DictReader(io.StringIO(self.read(path).decode("utf-8-sig"))))


FILES = {
    "_lookups/departments.csv": b"department_id,department_name\ndept,Department\n",
    "_lookups/datasets.csv": b"dataset_id,department_id,dataset_name\ndept.ds,dept,Display Dataset\n",
    "_lookups/tables.csv": b"table_id,dataset_id,table_name,deleted\ndept.ds.t,dept.ds,t,\ndept.ds.old,dept.ds,old,20260101T000000000000Z\n",
    "department/dept/ds/t/curated/schemas/20260101T000000000000Z.csv": b"name,data_type\nx,int\n",
    "department/dept/ds/t/curated/schemas/20260102T000000000000Z.csv": b"name,data_type\ny,text\n",
    "department/dept/ds/t/raw/schemas/20260101T000000000000Z.csv": b"name,data_type\nx,int\n",
    "department/dept/ds/t/raw/source/20260101T000000000000Z__source.csv": b"x\n1\n",
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_API_KEYS", "test-key")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[storage_dep] = lambda: FakeStorage(FILES)
    return TestClient(app)


def _zip(response):
    return zipfile.ZipFile(io.BytesIO(response.content))


def test_requires_api_key(client):
    assert client.get("/downloads/departments").status_code == 401


def test_lists_departments(client):
    response = client.get("/downloads/departments", headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "department_id": "dept",
                "department_name": "Department",
                "dataset_count": 1,
                "table_count": 1,
            }
        ],
        "total": 1,
    }


def test_explicit_department_list_endpoint(client):
    response = client.get("/downloads/departments", headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["department_id"] == "dept"


def test_legacy_download_route_is_removed(client):
    assert client.get("/downloads", headers=HEADERS).status_code == 404


def test_department_bundle_has_latest_curated_and_details(client):
    response = client.get("/downloads/departments/dept", headers=HEADERS)

    assert response.status_code == 200
    archive = _zip(response)
    names = archive.namelist()
    assert names == ["details.json", "ds/t/curated/20260102T000000000000Z.csv"]

    details = json.loads(archive.read("details.json"))
    assert details["department"]["department_id"] == "dept"
    assert details["total_datasets"] == 1
    assert details["total_tables"] == 1
    table = details["datasets"][0]["tables"][0]
    assert table["table_id"] == "dept.ds.t"
    assert table["curated"] == {
        "file": "ds/t/curated/20260102T000000000000Z.csv",
        "snapshot": "20260102T000000000000Z",
    }


def test_explicit_department_download_endpoint(client):
    response = client.get("/downloads/departments/dept", headers=HEADERS)

    assert response.status_code == 200
    assert _zip(response).namelist() == [
        "details.json",
        "ds/t/curated/20260102T000000000000Z.csv",
    ]


def test_department_bundle_excludes_raw_and_old_snapshots(client):
    response = client.get("/downloads/departments/dept", headers=HEADERS)

    archive = _zip(response)
    assert all("/raw/" not in name for name in archive.namelist())
    assert all("20260101" not in name for name in archive.namelist())


def test_unknown_department_is_404(client):
    assert client.get("/downloads?department_id=nope", headers=HEADERS).status_code == 404


def test_path_traversal_is_rejected():
    with pytest.raises(ValueError):
        CuratedStorage._check("../_lookups/departments.csv")
