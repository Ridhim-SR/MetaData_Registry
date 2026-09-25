import csv
import hashlib
import io
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from src.storage.base import ObjectStorage


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

    def _key(self, path: str) -> str:
        return f"{self.prefix}/{path}" if self.prefix else path

    def write_csv(self, path: str, rows: list[dict]) -> None:
        buf = io.StringIO()
        if rows:
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        self.client.put_object(Bucket=self.bucket, Key=self._key(path), Body=buf.getvalue().encode("utf-8"))

    def read_csv(self, path: str) -> list[dict]:
        obj = self.client.get_object(Bucket=self.bucket, Key=self._key(path))
        text = obj["Body"].read().decode("utf-8")
        return list(csv.DictReader(io.StringIO(text)))

    def exists(self, path: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(path))
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
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
