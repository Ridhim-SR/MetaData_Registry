"""Read-only access to the curated/raw snapshots kept in Wasabi.

The download API must never be able to change the bucket. This module only
exposes list/read operations, and the Wasabi key it uses is expected to have
just s3:GetObject + s3:ListBucket. Paths are relative to the configured
prefix (e.g. "dev") and are restricted to the two roots the pipeline writes:
department/... and _lookups/...
"""

from __future__ import annotations

import csv
import io
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

_SNAPSHOT_NAME = re.compile(r"^\d{8}T\d+Z\.csv$")


class CuratedStorage:
    def __init__(self) -> None:
        _load_shared_environment()
        self.environment = _download_environment()
        self.bucket = (
            os.environ.get("WASABI_DOWNLOAD_BUCKET")
            or os.environ.get("WASABI_BUCKET", "")
        ).strip()
        if not self.bucket:
            raise RuntimeError("WASABI_BUCKET or WASABI_DOWNLOAD_BUCKET is not set")
        self.prefix = (
            os.environ.get("WASABI_DOWNLOAD_PREFIX")
            or {"local": "local", "development": "dev", "production": "prod"}[self.environment]
        ).strip("/")
        self.client = boto3.client(
            "s3",
            endpoint_url=(
                os.environ.get("WASABI_DOWNLOAD_ENDPOINT_URL")
                or os.environ.get("WASABI_ENDPOINT_URL")
                or None
            ),
            aws_access_key_id=(
                os.environ.get("WASABI_DOWNLOAD_ACCESS_KEY_ID")
                or os.environ.get("WASABI_ACCESS_KEY_ID")
                or None
            ),
            aws_secret_access_key=(
                os.environ.get("WASABI_DOWNLOAD_SECRET_ACCESS_KEY")
                or os.environ.get("WASABI_SECRET_ACCESS_KEY")
                or None
            ),
            region_name=(
                os.environ.get("WASABI_DOWNLOAD_REGION")
                or os.environ.get("WASABI_REGION")
                or None
            ),
        )

    def _key(self, path: str) -> str:
        path = self._check(path)
        return f"{self.prefix}/{path}" if self.prefix else path

    @staticmethod
    def _check(path: str) -> str:
        path = path.replace("\\", "/").strip("/")
        if ".." in path.split("/") or not (
            path.startswith("department/") or path.startswith("_lookups/")
        ):
            raise ValueError(f"Refusing path outside the download roots: {path!r}")
        return path

    def list(self, prefix: str) -> list[str]:
        prefix = self._check(prefix)
        full_prefix = f"{self.prefix}/{prefix}" if self.prefix else prefix
        strip = len(self.prefix) + 1 if self.prefix else 0
        paginator = self.client.get_paginator("list_objects_v2")
        keys = [
            obj["Key"][strip:]
            for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix)
            for obj in page.get("Contents", [])
        ]
        return sorted(keys)

    def read(self, path: str) -> bytes:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self._key(path))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                raise FileNotFoundError(path) from exc
            raise
        return obj["Body"].read()

    def read_csv(self, path: str) -> list[dict]:
        return list(csv.DictReader(io.StringIO(self.read(path).decode("utf-8-sig"))))


@lru_cache(maxsize=1)
def get_storage() -> CuratedStorage:
    return CuratedStorage()


def _download_environment() -> str:
    """Resolve the same branch default used by data_services.

    Explicit ``ENVIRONMENT`` remains authoritative. Otherwise main reads the
    development prefix and production reads the production prefix.
    """
    configured = os.environ.get("ENVIRONMENT", "").strip().lower()
    if configured in {"local", "development", "production"}:
        return configured
    try:
        repo = Path(__file__).resolve().parents[3]
        branch = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        branch = ""
    return {"main": "development", "production": "production"}.get(branch, "local")


def _load_shared_environment() -> None:
    """Load the repository's shared environment file without overriding exports."""
    repo = Path(__file__).resolve().parents[3]
    load_dotenv(repo / "data_services" / ".env", override=False)


def latest_snapshot(keys: list[str], prefix: str) -> str | None:
    """Newest timestamped snapshot under `prefix` (None if there is none)."""
    prefix = prefix.rstrip("/") + "/"
    found = [
        key
        for key in keys
        if key.startswith(prefix) and _SNAPSHOT_NAME.match(key.rsplit("/", 1)[-1])
    ]
    return max(found, key=lambda key: key.rsplit("/", 1)[-1]) if found else None


def latest_source(keys: list[str], prefix: str) -> str | None:
    """Newest original submission under `raw/source/` (None if there is none)."""
    prefix = prefix.rstrip("/") + "/"
    found = [
        key
        for key in keys
        if key.startswith(prefix)
        and "T" in key.rsplit("/", 1)[-1]
        and "__" in key.rsplit("/", 1)[-1]
        and "__metadata__" not in key
        and not key.endswith(".sha256")
    ]
    return found[-1] if found else None
