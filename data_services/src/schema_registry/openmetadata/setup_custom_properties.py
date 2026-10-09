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
from src.utils.config import load_env

from src.schema_registry.openmetadata.publish import _CUSTOM_PROPERTY_NAMES
from src.utils.logger import get_logger

logger = get_logger(__name__)

_TIMEOUT = 15  # seconds -- an unreachable server fails fast instead of hanging

_DESCRIPTIONS = {
    "apiAvailable": "Whether this dataset is exposed via an API (Y/N).",
    "datasetOwner": "Who owns/is accountable for this dataset (free text).",
    "frequency": "How often this dataset is refreshed/submitted.",
    "timeline": "The period/date range this dataset covers.",
}


def setup(host_port: str, jwt_token: str) -> None:
    auth = {"Authorization": f"Bearer {jwt_token}"}

    def get(path: str) -> dict:
        response = requests.get(f"{host_port}{path}", headers=auth, timeout=_TIMEOUT)
        response.raise_for_status()  # e.g. 401 -> a clear "token not valid" message, not a KeyError
        return response.json()

    type_id = get("/v1/metadata/types/name/database")["id"]
    string_type_id = next(t["id"] for t in get("/v1/metadata/types?category=field&limit=50")["data"] if t["name"] == "string")
    existing = {p["name"] for p in get(f"/v1/metadata/types/{type_id}?fields=customProperties").get("customProperties", [])}

    for property_name in _CUSTOM_PROPERTY_NAMES.values():
        if property_name in existing:
            logger.info(f"'{property_name}' already exists -- skipping.")
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
            timeout=_TIMEOUT,
        )
        if not resp.ok:
            logger.error(f"Failed to add '{property_name}': {resp.status_code} {resp.text}")
        resp.raise_for_status()
        logger.info(f"Added '{property_name}' to the Database entity type.")


def _main(argv: list[str]) -> int:
    """Command line entry point (settings come from .env / the shell)."""

    from src.utils.cli import confirm_changes

    load_env()
    confirm_changes("create OpenMetadata custom properties and tags")
    setup(
        host_port=os.environ.get("OPENMETADATA_HOST_PORT", "http://localhost:8585/api"),
        jwt_token=os.environ["OPENMETADATA_JWT_TOKEN"],
    )
    return 0


if __name__ == "__main__":
    import sys

    from src.utils.cli import run_cli

    sys.exit(run_cli("setup_custom_properties", _main, sys.argv[1:]))
