"""One-time setup: register the OpenMetadata Custom Properties that
`openmetadata/publish.py`'s `_ensure_database()` pushes values into for the
dataset-level fields (`api_available`/`owner`/`frequency`/`timeline`) that
have no built-in Database field. Entity *type* changes like this aren't
something the regular create-or-update entity APIs can make, so this is a
separate, run-once-per-OpenMetadata-instance step -- re-running it is safe
(skips properties that already exist).

    OPENMETADATA_JWT_TOKEN=<token> python3 -m src.schema_registry.openmetadata.setup_custom_properties
"""

import os

import requests
from dotenv import load_dotenv

from src.schema_registry.openmetadata.publish import _CUSTOM_PROPERTY_NAMES

_DESCRIPTIONS = {
    "apiAvailable": "Whether this dataset is exposed via an API (Y/N).",
    "datasetOwner": "Who owns/is accountable for this dataset (free text).",
    "frequency": "How often this dataset is refreshed/submitted.",
    "timeline": "The period/date range this dataset covers.",
}


def setup(host_port: str, jwt_token: str) -> None:
    auth = {"Authorization": f"Bearer {jwt_token}"}
    type_id = requests.get(f"{host_port}/v1/metadata/types/name/database", headers=auth).json()["id"]
    string_type_id = next(
        t["id"]
        for t in requests.get(f"{host_port}/v1/metadata/types?category=field&limit=50", headers=auth).json()["data"]
        if t["name"] == "string"
    )
    existing = {
        p["name"]
        for p in requests.get(f"{host_port}/v1/metadata/types/{type_id}?fields=customProperties", headers=auth)
        .json()
        .get("customProperties", [])
    }

    for property_name in _CUSTOM_PROPERTY_NAMES.values():
        if property_name in existing:
            print(f"'{property_name}' already exists -- skipping.")
            continue
        patch = [
            {
                "op": "add",
                "path": "/customProperties/-",
                "value": {
                    "name": property_name,
                    "description": _DESCRIPTIONS[property_name],
                    "propertyType": {"id": string_type_id, "type": "type", "name": "string"},
                },
            }
        ]
        resp = requests.patch(
            f"{host_port}/v1/metadata/types/{type_id}",
            headers={**auth, "Content-Type": "application/json-patch+json"},
            json=patch,
        )
        resp.raise_for_status()
        print(f"Added '{property_name}' to the Database entity type.")


if __name__ == "__main__":
    load_dotenv()
    setup(
        host_port=os.environ.get("OPENMETADATA_HOST_PORT", "http://localhost:8585/api"),
        jwt_token=os.environ["OPENMETADATA_JWT_TOKEN"],
    )
