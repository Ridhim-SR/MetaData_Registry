import os

from src.storage.base import ObjectStorage
from src.storage.local import LocalObjectStorage
from src.storage.s3 import S3ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)


def storage_from_env() -> ObjectStorage:
    """Pick the storage backend from environment variables, so every CLI
    entry point (pipeline.py, batch.py, lookups.py, openmetadata_publish.py)
    switches the same way instead of each hard-coding LocalObjectStorage.

    Set WASABI_BUCKET to use Wasabi (or any other S3-compatible provider,
    via WASABI_ENDPOINT_URL); leave it unset to keep using the local
    filesystem under STORAGE_ROOT (default "storage").
    """

    bucket = os.environ.get("WASABI_BUCKET")
    if bucket:
        logger.info(f"Storage backend: S3/Wasabi (bucket={bucket}, endpoint={os.environ.get('WASABI_ENDPOINT_URL')})")
        return S3ObjectStorage(
            bucket=bucket,
            prefix=os.environ.get("WASABI_PREFIX", ""),
            endpoint_url=os.environ.get("WASABI_ENDPOINT_URL"),
            aws_access_key_id=os.environ.get("WASABI_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("WASABI_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("WASABI_REGION"),
        )
    root = os.environ.get("STORAGE_ROOT", "storage")
    logger.info(f"Storage backend: local filesystem (root={root})")
    return LocalObjectStorage(root)
