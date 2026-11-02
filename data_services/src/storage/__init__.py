import os

from src.storage.base import ObjectStorage
from src.storage.local import LocalObjectStorage
from src.storage.s3 import S3ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)


def storage_from_env(delete_credentials: bool = False) -> ObjectStorage:
    """Pick the storage backend from environment variables, so every CLI
    entry point (pipeline.py, batch.py, lookups.py, openmetadata_publish.py)
    switches the same way instead of each hard-coding LocalObjectStorage.

    Set WASABI_BUCKET to use Wasabi (or any other S3-compatible provider,
    via WASABI_ENDPOINT_URL); leave it unset to keep using the local
    filesystem under STORAGE_ROOT (default "storage").
    """

    bucket = os.environ.get("WASABI_BUCKET")
    if bucket:
        access_key = os.environ.get("WASABI_ACCESS_KEY_ID")
        secret_key = os.environ.get("WASABI_SECRET_ACCESS_KEY")
        if delete_credentials:
            access_key = os.environ.get("WASABI_DELETE_ACCESS_KEY_ID")
            secret_key = os.environ.get("WASABI_DELETE_SECRET_ACCESS_KEY")
            missing = [
                name for name, value in (
                    ("WASABI_DELETE_ACCESS_KEY_ID", access_key),
                    ("WASABI_DELETE_SECRET_ACCESS_KEY", secret_key),
                ) if not value
            ]
            if missing:
                raise ValueError(
                    f"Permanent deletion requires dedicated S3 credentials: {', '.join(missing)}"
                )
        logger.info(f"Storage backend: S3/Wasabi (bucket={bucket}, endpoint={os.environ.get('WASABI_ENDPOINT_URL')})")
        return S3ObjectStorage(
            bucket=bucket,
            prefix=os.environ.get("WASABI_PREFIX", ""),
            endpoint_url=os.environ.get("WASABI_ENDPOINT_URL"),
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=os.environ.get("WASABI_REGION"),
        )
    root = os.environ.get("STORAGE_ROOT", "storage")
    logger.info(f"Storage backend: local filesystem (root={root})")
    return LocalObjectStorage(root)
