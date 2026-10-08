import csv
import io
import json
import os
import socket
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

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

    Locking (lock()) works across machines: a lock is an object under
    `_locks/` created with a conditional PUT ("only if it doesn't exist"),
    so of several machines racing for it exactly one succeeds. Verified
    against Wasabi on 2026-10-07 (If-None-Match and If-Match both enforced).
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        region_name: str | None = None,
        lock_timeout_seconds: float = 120,
        lock_ttl_seconds: float = 900,
        lock_poll_seconds: float = 1.0,
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
        self.lock_timeout_seconds = lock_timeout_seconds
        self.lock_ttl_seconds = lock_ttl_seconds
        self.lock_poll_seconds = lock_poll_seconds
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
        self.write_bytes(path, rows_to_csv(rows).encode("utf-8"))

    def write_bytes(self, path: str, data: bytes) -> None:
        # A single PUT is already atomic on S3 -- readers see the old object
        # or the new one, never a partial write.
        try:
            self.client.put_object(Bucket=self.bucket, Key=self._key(path), Body=data)
        except ClientError as exc:
            self._log_client_error(exc, "write", path)
            raise

    def read_bytes(self, path: str) -> bytes:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self._key(path))
        except ClientError as exc:
            self._log_client_error(exc, "read", path)
            raise
        return obj["Body"].read()

    def read_csv(self, path: str) -> list[dict]:
        return list(csv.DictReader(io.StringIO(self.read_bytes(path).decode("utf-8"))))

    def write_bytes(self, path: str, data: bytes) -> None:
        try:
            self.client.put_object(Bucket=self.bucket, Key=self._key(path), Body=data)
        except ClientError as exc:
            self._log_client_error(exc, "write", path)
            raise

    def read_bytes(self, path: str) -> bytes:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self._key(path))
        except ClientError as exc:
            self._log_client_error(exc, "read", path)
            raise
        return obj["Body"].read()

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

    @contextmanager
    def lock(self, path: str) -> Iterator[None]:
        """Hold `_locks/<path>.lock` for the duration of the `with` block.

        Acquire = PUT the lock object with If-None-Match: * -- the store
        refuses it (412) while anyone else holds it, so of several machines
        racing, exactly one wins. A holder that died without releasing is
        recognised by its `expires_at` (lock_ttl_seconds after acquiring)
        and taken over with If-Match on the lock's current ETag, so two
        machines can't both take over the same stale lock. Gives up with
        TimeoutError after lock_timeout_seconds, naming who holds it."""

        key = self._key(f"_locks/{path}.lock")
        owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        deadline = time.monotonic() + self.lock_timeout_seconds

        while True:
            now = time.time()
            body = json.dumps({"owner": owner, "acquired_at": now, "expires_at": now + self.lock_ttl_seconds}).encode()
            if self._conditional_put(key, body, IfNoneMatch="*"):
                break
            held = self._read_lock(key)
            if held is None:
                continue  # released between our attempt and the read -- try again at once
            holder, etag = held
            if holder.get("expires_at", 0) < now and self._conditional_put(key, body, IfMatch=etag):
                logger.warning(f"Took over expired lock on '{path}' from {holder.get('owner')}")
                break
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Couldn't lock '{path}' within {self.lock_timeout_seconds:.0f}s -- held by "
                    f"{holder.get('owner')} since {time.ctime(holder.get('acquired_at', 0))}. If that run "
                    f"is dead, the lock frees itself at {time.ctime(holder.get('expires_at', 0))}."
                )
            time.sleep(self.lock_poll_seconds)

        try:
            yield
        finally:
            held = self._read_lock(key)
            if held is not None and held[0].get("owner") == owner:
                self.client.delete_object(Bucket=self.bucket, Key=key)
            else:
                logger.warning(f"Lock on '{path}' was no longer ours at release (expired and taken over?)")

    def _conditional_put(self, key: str, body: bytes, **condition) -> bool:
        """True if written, False if the condition failed (someone else got
        there first); any other error is raised."""

        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=body, **condition)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("PreconditionFailed", "ConditionalRequestConflict"):
                return False
            self._log_client_error(exc, "lock", key)
            raise

    def _read_lock(self, key: str) -> tuple[dict, str] | None:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise
        return json.loads(obj["Body"].read() or b"{}"), obj["ETag"]
