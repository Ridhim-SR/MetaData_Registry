"""Soft-delete one table from OpenMetadata and from the registry.

Renaming a table used to leave the old entity sitting in OpenMetadata with
nobody publishing it anymore (an orphan): the new name got ingested under a
new id, the old one was simply forgotten. This is the cleanup:

    OPENMETADATA_JWT_TOKEN=<token> TABLE_ID=pwd.vishwakarma.old_name \
        python3 -m src.schema_registry.openmetadata.delete_table

OpenMetadata's entity is soft-deleted (hidden from search, restorable by an
admin), then the registry row is marked with a `deleted` timestamp so
publish_table() refuses to push it again. Re-ingesting the same id later
clears the mark and brings it back.
"""

import os
import sys

from dotenv import load_dotenv

from src.schema_registry.openmetadata.publish import delete_table, get_client
from src.storage import storage_from_env
from src.utils.logger import get_logger

logger = get_logger(__name__)


if __name__ == "__main__":
    load_dotenv()
    _table_id = os.environ.get("TABLE_ID", "")
    if not _table_id:
        sys.exit("TABLE_ID is required, e.g. TABLE_ID=pwd.vishwakarma.roads")

    _client = get_client(
        host_port=os.environ.get("OPENMETADATA_HOST_PORT", "http://localhost:8585/api"),
        jwt_token=os.environ["OPENMETADATA_JWT_TOKEN"],
    )
    _result = delete_table(_client, storage_from_env(), _table_id)
    print(
        f"{_result['table_id']}: OpenMetadata={_result['openmetadata']}, "
        f"registry={_result['registry']} (fqn {_result['fully_qualified_name']})"
    )
