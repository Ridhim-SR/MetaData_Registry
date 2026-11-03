"""Read-only download APIs for the latest curated snapshots.

The endpoints require an X-API-Key. The storage adapter only exposes
list/read, so this API cannot change anything in Wasabi even if a request is
malformed.
"""

import json
import os
import tempfile
import zipfile
from collections import Counter
from secrets import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from src.curated_storage import CuratedStorage, get_storage, latest_snapshot


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
    keys = [k.strip() for k in os.getenv("DOWNLOAD_API_KEYS", "").split(",") if k.strip()]
    if not keys:
        raise HTTPException(status_code=503, detail="Download API is not configured")
    if not x_api_key or not any(compare_digest(x_api_key, key) for key in keys):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return x_api_key


def storage_dep() -> CuratedStorage:
    return get_storage()


router = APIRouter(
    prefix="/downloads",
    tags=["downloads"],
    dependencies=[Depends(require_api_key)],
)
Store = Depends(storage_dep)


def _rows(storage: CuratedStorage, name: str) -> list[dict]:
    return storage.read_csv(f"_lookups/{name}")


def _datasets(storage: CuratedStorage, department_id: str) -> list[dict]:
    return [r for r in _rows(storage, "datasets.csv") if r.get("department_id") == department_id]


def _tables(storage: CuratedStorage, dataset_ids: set[str]) -> list[dict]:
    return [
        r
        for r in _rows(storage, "tables.csv")
        if r.get("dataset_id") in dataset_ids and not r.get("deleted")
    ]


def _department(storage: CuratedStorage, department_id: str) -> dict:
    department = next(
        (r for r in _rows(storage, "departments.csv") if r.get("department_id") == department_id),
        None,
    )
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return department


def _dataset_slug(dataset: dict) -> str:
    """Return the storage directory name, which is the dataset ID component.

    ``dataset_name`` is metadata and may be a display name; the pipeline path
    is always based on the canonical ``department.dataset`` identifier.
    """
    return dataset["dataset_id"].split(".", 1)[-1]


def _entries(
    storage: CuratedStorage,
    department: dict,
    datasets: list[dict],
    tables: list[dict],
    keys: list[str],
) -> list[tuple[str, bytes]]:
    department_id = department["department_id"]
    by_dataset = {
        d["dataset_id"]: {**d, "tables": []} for d in datasets
    }
    entries: list[tuple[str, bytes]] = []
    for table in tables:
        dataset = by_dataset.get(table["dataset_id"])
        if dataset is None:
            continue
        slug = _dataset_slug(dataset)
        name = table.get("table_name") or table["table_id"].rsplit(".", 1)[-1]
        base = f"department/{department_id}/{slug}/{name}"
        path = latest_snapshot(keys, f"{base}/curated/schemas")
        curated = None
        if path:
            filename = path.rsplit("/", 1)[-1]
            arcname = f"{slug}/{name}/curated/{filename}"
            entries.append((arcname, storage.read(path)))
            curated = {"file": arcname, "snapshot": filename[:-4]}
        dataset["tables"].append({**table, "curated": curated})

    details = {
        "department": department,
        "total_datasets": len(datasets),
        "total_tables": len(tables),
        "datasets": list(by_dataset.values()),
    }
    return [("details.json", json.dumps(details, indent=2).encode())] + entries


def _zip_response(entries: list[tuple[str, bytes]], filename: str) -> StreamingResponse:
    buf = tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    buf.seek(0)

    def chunks():
        try:
            while chunk := buf.read(64 * 1024):
                yield chunk
        finally:
            buf.close()

    return StreamingResponse(
        chunks(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def list_departments(storage: CuratedStorage) -> dict:
    """Return lightweight department summaries for download discovery."""
    departments = _rows(storage, "departments.csv")
    datasets = _rows(storage, "datasets.csv")
    tables = [t for t in _rows(storage, "tables.csv") if not t.get("deleted")]
    department_by_dataset = {d["dataset_id"]: d["department_id"] for d in datasets}
    dataset_counts = Counter(d["department_id"] for d in datasets)
    table_counts = Counter(
        department_by_dataset[t["dataset_id"]]
        for t in tables
        if t["dataset_id"] in department_by_dataset
    )
    items = [
        {
            "department_id": d["department_id"],
            "department_name": d["department_name"],
            "dataset_count": dataset_counts.get(d["department_id"], 0),
            "table_count": table_counts.get(d["department_id"], 0),
        }
        for d in departments
    ]
    return {"items": items, "total": len(items)}


@router.get("/departments")
def departments(storage: CuratedStorage = Store):
    """List departments available for curated downloads."""
    return list_departments(storage)


@router.get("/departments/{department_id}")
def department_download(
    department_id: str,
    storage: CuratedStorage = Store,
):
    """Download latest curated CSVs and metadata for one department."""
    department = _department(storage, department_id)
    datasets = _datasets(storage, department_id)
    tables = _tables(storage, {d["dataset_id"] for d in datasets})
    keys = storage.list(f"department/{department_id}/")
    entries = _entries(storage, department, datasets, tables, keys)
    return _zip_response(entries, f"{department_id}_curated_latest.zip")
