"""Seed the Oct-5 demo scenario: 2 departments, 4 datasets, 7 tables.

Usage (backend + OpenMetadata running, bot JWT configured server-side):
    python scripts/seed_demo_registry.py --admin-email admin@example.com --admin-password secret

The script logs in, creates/updates each table with its access level, triggers
a search reindex, then verifies the public registry surface (no auth).
"""

import argparse
import sys

import httpx

TABLES = [
    {
        "name": "crop_statistics",
        "display_name": "Crop Statistics",
        "description": "Season-wise crop area, yield and production statistics by district.",
        "database_service": "agriculture",
        "database": "agri_db",
        "database_schema": "crop_statistics",
        "visibility": "public",
        "department": "agriculture",
        "columns": [
            {"name": "district", "data_type": "VARCHAR", "description": "District name"},
            {"name": "season", "data_type": "VARCHAR", "description": "Kharif, Rabi or Zaid"},
            {"name": "crop_name", "data_type": "VARCHAR", "description": "Crop name"},
            {"name": "year", "data_type": "INT", "description": "Agricultural year"},
            {"name": "area_hectares", "data_type": "DECIMAL", "description": "Sown area in hectares"},
            {"name": "production_tonnes", "data_type": "DECIMAL", "description": "Production in tonnes"},
        ],
    },
    {
        "name": "crop_production",
        "display_name": "Crop Production",
        "description": "Annual crop production estimates used in Crop Statistics releases.",
        "database_service": "agriculture",
        "database": "agri_db",
        "database_schema": "crop_statistics",
        "visibility": "public",
        "department": "agriculture",
        "columns": [
            {"name": "district", "data_type": "VARCHAR", "description": "District name"},
            {"name": "crop_name", "data_type": "VARCHAR", "description": "Crop name"},
            {"name": "year", "data_type": "INT", "description": "Agricultural year"},
            {"name": "production_tonnes", "data_type": "DECIMAL", "description": "Production in tonnes"},
            {"name": "yield_per_hectare", "data_type": "DECIMAL", "description": "Yield per hectare"},
        ],
    },
    {
        "name": "crop_sales",
        "display_name": "Crop Sales",
        "description": "Mandi-level crop sale transactions (Agriculture department only).",
        "database_service": "agriculture",
        "database": "agri_db",
        "database_schema": "crop_sales",
        "visibility": "department",
        "department": "agriculture",
        "columns": [
            {"name": "id", "data_type": "INT", "description": "Transaction id"},
            {"name": "mandi_code", "data_type": "VARCHAR", "description": "Mandi code"},
            {"name": "crop_name", "data_type": "VARCHAR", "description": "Crop name"},
            {"name": "year", "data_type": "INT", "description": "Sale year"},
            {"name": "quantity_quintals", "data_type": "DECIMAL", "description": "Quantity sold"},
            {"name": "price_per_quintal", "data_type": "DECIMAL", "description": "Modal price"},
        ],
    },
    {
        "name": "crop_prices",
        "display_name": "Crop Prices",
        "description": "Daily modal prices informing Crop Sales analysis (Agriculture only).",
        "database_service": "agriculture",
        "database": "agri_db",
        "database_schema": "crop_sales",
        "visibility": "department",
        "department": "agriculture",
        "columns": [
            {"name": "mandi_code", "data_type": "VARCHAR", "description": "Mandi code"},
            {"name": "crop_name", "data_type": "VARCHAR", "description": "Crop name"},
            {"name": "price_date", "data_type": "DATE", "description": "Price date"},
            {"name": "modal_price", "data_type": "DECIMAL", "description": "Modal price per quintal"},
        ],
    },
    {
        "name": "roads",
        "display_name": "Roads",
        "description": "Road network master: road identity, class and length by division.",
        "database_service": "public_works",
        "database": "pwd_db",
        "database_schema": "road_network",
        "visibility": "public",
        "department": "public_works",
        "columns": [
            {"name": "road_code", "data_type": "VARCHAR", "description": "Unique road code"},
            {"name": "road_name", "data_type": "VARCHAR", "description": "Road name"},
            {"name": "road_class", "data_type": "VARCHAR", "description": "NH, SH, MDR or rural"},
            {"name": "division", "data_type": "VARCHAR", "description": "PWD division"},
            {"name": "length_km", "data_type": "DECIMAL", "description": "Length in km"},
        ],
    },
    {
        "name": "road_segments",
        "display_name": "Road Segments",
        "description": "Segment-level breakup of the Road Network dataset.",
        "database_service": "public_works",
        "database": "pwd_db",
        "database_schema": "road_network",
        "visibility": "public",
        "department": "public_works",
        "columns": [
            {"name": "road_code", "data_type": "VARCHAR", "description": "Parent road code"},
            {"name": "segment_id", "data_type": "VARCHAR", "description": "Segment id"},
            {"name": "start_chainage", "data_type": "DECIMAL", "description": "Start chainage km"},
            {"name": "end_chainage", "data_type": "DECIMAL", "description": "End chainage km"},
            {"name": "surface_type", "data_type": "VARCHAR", "description": "Surface type"},
        ],
    },
    {
        "name": "bridges",
        "display_name": "Bridges",
        "description": "Bridge infrastructure inventory incl. safety inspection grading (restricted).",
        "database_service": "public_works",
        "database": "pwd_db",
        "database_schema": "bridge_infrastructure",
        "visibility": "restricted",
        "department": "public_works",
        "columns": [
            {"name": "bridge_id", "data_type": "VARCHAR", "description": "Bridge id"},
            {"name": "road_code", "data_type": "VARCHAR", "description": "Road code"},
            {"name": "span_meters", "data_type": "DECIMAL", "description": "Span in meters"},
            {"name": "inspection_grade", "data_type": "VARCHAR", "description": "Latest safety grade"},
            {"name": "last_inspected", "data_type": "DATE", "description": "Last inspection date"},
        ],
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    client = httpx.Client(base_url=args.base_url, timeout=120)
    login = client.post(
        "/auth/login", json={"email": args.admin_email, "password": args.admin_password}
    )
    if login.status_code != 200:
        print(f"Login failed: {login.status_code} {login.text}")
        return 1
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    failures = 0
    for table in TABLES:
        resp = client.post("/openmetadata/metadata/tables", json=table, headers=headers)
        status = "ok" if resp.status_code == 201 else f"FAILED {resp.status_code} {resp.text}"
        if resp.status_code != 201:
            failures += 1
        print(f"{table['database_service']}.{table['database_schema']}.{table['name']}: {status}")

    reindex = client.post("/openmetadata/search/reindex", headers=headers)
    print(f"reindex: {reindex.status_code}")

    stats = client.get("/registry/stats")
    print(f"registry stats: {stats.status_code} {stats.text[:300]}")
    public = client.get("/registry/datasets/public")
    try:
        body = public.json()
        names = [d["dataset"] for d in body.get("items", [])]
        print(f"public datasets ({body.get('total')}): {names}")
    except Exception:
        print(f"public datasets: {public.status_code} {public.text[:300]}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
