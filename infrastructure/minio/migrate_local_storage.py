"""One-time copy of a local filesystem storage/ tree into MinIO/S3.

    python infrastructure/minio/migrate_local_storage.py

Main's config (2026-10-13) routes every feature-branch run to S3, so the
registry state that used to live under data_services/storage/ (inputs,
department snapshots, _lookups) has to exist in the bucket too. Copies each
file through the same S3ObjectStorage the pipeline uses, so keys land exactly
where sync will look for them. Local files are left in place (they stay
gitignored and serve as a restore point).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data_services"))

from src.storage import storage_from_env  # noqa: E402
from src.utils.config import load_env  # noqa: E402

LOCAL_ROOT = Path(__file__).resolve().parents[2] / "data_services" / "storage"


def main() -> int:
    load_env()
    storage = storage_from_env()
    files = [p for p in LOCAL_ROOT.rglob("*") if p.is_file()]
    if not files:
        print(f"nothing under {LOCAL_ROOT}")
        return 1
    copied = skipped = 0
    for path in files:
        key = path.relative_to(LOCAL_ROOT).as_posix()
        if storage.exists(key):
            skipped += 1
            continue
        storage.write_bytes(key, path.read_bytes())
        copied += 1
        print(f"  copied {key}")
    print(f"done: {copied} copied, {skipped} already present (of {len(files)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
