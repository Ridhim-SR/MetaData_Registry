import csv
import hashlib
import io
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from src.storage.base import ObjectStorage, rows_to_csv
from src.utils.logger import get_logger

logger = get_logger(__name__)


class S3ObjectStorage(ObjectStorage):
    """S3-compatible ObjectStorage -- AWS S3, Wasabi, or any other provider
    speaking the S3 API. Point `endpoint_url` at your provider (e.g. Wasabi's
    `https://s3.us-east-1.wasabisys.com`); credentials resolve the normal
    boto3 way (env vars `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, or pass
    them explicitly) -- nothing custom to configure here.

    Locking is still local-filesystem-only (see lock_path()): fine for
    today's single-machine pipeline runs, not yet safe for multiple
    machines writing to the same bucket concurrently -- that would need
    conditional-PUT/ETag-based locking instead of filelock.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        region_name: str | None = None,
        lock_dir: str | Path = "/tmp/schema-registry-locks",
    ):
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
        )
        self.lock_dir = Path(lock_dir)
        logger.info(f"S3ObjectStorage ready: bucket={bucket}, endpoint={endpoint_url}, prefix={self.prefix or '(none)'}")

    def _key(self, path: str) -> str:
        return f"{self.prefix}/{path}" if self.prefix else path

    def _log_client_error(self, exc: ClientError, action: str, path: str) -> None:
        """Surface exactly what boto3 is reporting -- a bad access key,
        a wrong bucket/endpoint, and a missing permission all raise the same
        generic ClientError otherwise, which is what made diagnosing a real
        Wasabi credential issue this slow in the first place."""

        code = exc.response.get("Error", {}).get("Code", "?")
        if code in ("InvalidAccessKeyId", "SignatureDoesNotMatch", "AccessDenied", "403"):
            logger.error(
                f"S3 {action} failed on '{path}' (bucket={self.bucket}): {code} -- "
                f"this is a credentials/permissions problem, not a code bug. "
                f"Verify WASABI_ACCESS_KEY_ID/WASABI_SECRET_ACCESS_KEY independently "
                f"(e.g. `aws s3 ls --endpoint-url <url>`) before changing any code."
            )
        elif code == "NoSuchBucket":
            logger.error(f"S3 {action} failed on '{path}': bucket '{self.bucket}' doesn't exist at this endpoint.")
        else:
            logger.error(f"S3 {action} failed on '{path}' (bucket={self.bucket}): {code} -- {exc}")

    def write_csv(self, path: str, rows: list[dict]) -> None:
        # A single PUT is already atomic on S3 -- readers see the old object
        # or the new one, never a partial write.
        try:
            self.client.put_object(Bucket=self.bucket, Key=self._key(path), Body=rows_to_csv(rows).encode("utf-8"))
        except ClientError as exc:
            self._log_client_error(exc, "write", path)
            raise

    def read_csv(self, path: str) -> list[dict]:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self._key(path))
        except ClientError as exc:
            self._log_client_error(exc, "read", path)
            raise
        text = obj["Body"].read().decode("utf-8")
        return list(csv.DictReader(io.StringIO(text)))

    def exists(self, path: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(path))
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            self._log_client_error(exc, "exists-check", path)
            raise

    def list(self, prefix: str) -> list[str]:
        full_prefix = self._key(prefix)
        prefix_len = len(self.prefix) + 1 if self.prefix else 0
        paginator = self.client.get_paginator("list_objects_v2")
        keys = [
            obj["Key"][prefix_len:]
            for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix)
            for obj in page.get("Contents", [])
        ]
        return sorted(keys)

    def lock_path(self, path: str) -> str:
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        safe_name = hashlib.sha256(self._key(path).encode()).hexdigest()
        return str(self.lock_dir / f"{safe_name}.lock")
