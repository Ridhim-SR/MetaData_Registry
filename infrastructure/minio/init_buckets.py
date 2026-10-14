"""Create the local MinIO buckets once, so the S3 code path has somewhere to PUT.

    python infrastructure/minio/init_buckets.py

MinIO ships with no buckets and S3ObjectStorage never auto-creates one, so run
this once after `docker compose -f infrastructure/minio/docker-compose.yml up -d`.
Credentials/endpoints come from data_services/.env section 3b (LOCAL_WASABI_*),
or pass overrides as arguments for any other S3-compatible server.
"""
import argparse
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ConnectionError as BotoConnectionError, ClientError
from dotenv import load_dotenv

DEFAULTS = {"bucket": "sda-local", "endpoint": "http://localhost:9000",
            "access_key": "minioadmin", "secret_key": "minioadmin", "region": "us-east-1"}


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / "data_services" / ".env")
    p = argparse.ArgumentParser(description=__doc__)
    for name, default in DEFAULTS.items():
        p.add_argument(f"--{name.replace('_', '-')}", default=os.environ.get(f"LOCAL_WASABI_{name.upper()}", default))
    args = p.parse_args()

    client = boto3.client(
        "s3",
        endpoint_url=args.endpoint,
        aws_access_key_id=args.access_key,
        aws_secret_access_key=args.secret_key,
        region_name=args.region,
    )
    try:
        existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    except (BotoConnectionError, ClientError) as exc:
        print(f"Cannot reach {args.endpoint}: {exc}\n"
              f"Start it first: docker compose -f infrastructure/minio/docker-compose.yml up -d", file=sys.stderr)
        return 1
    for bucket in (args.bucket, f"{args.bucket}-backup"):
        if bucket in existing:
            print(f"{bucket}: already exists")
            continue
        client.create_bucket(Bucket=bucket)
        print(f"{bucket}: created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
