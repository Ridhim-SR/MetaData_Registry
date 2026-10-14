"""One-off, manual push of OUR two departments' files to the company Wasabi.

    python infrastructure/wasabi/push_agri_mgnrega.py            # dry-run: checks only
    python infrastructure/wasabi/push_agri_mgnrega.py --apply    # upload + verify

This is NOT part of the pipeline: nothing in `sync`/`add`/`batch`/`backup`
ever calls it, and it only runs when someone invokes it by hand. It exists
because feature branches (this one) are barred from the company bucket by
design (config.py), while the branch's work still has to reach `dev/`
eventually.

Safety model (why this can't break the other team's data):
  * Only keys under our four namespaces are ever built:
        dev/inputs/agri_dept/                        dev/department/agri_dept/
        dev/inputs/rural_development_department/     dev/department/rural_development_department/
  * It NEVER touches dev/_lookups/*.csv -- those are shared and hold every
    registered team's registry rows; overwriting them with local copies would
    wipe the other team's state. (The registry rows get added by the next
    server-side sync, which merges them the same way the code always has.)
  * It asserts every target key is (a) inside our namespaces, (b) free of any
    other department's marker, and (c) NOT already present in the bucket --
    so no pre-existing object can be modified, let alone deleted. The only
    S3 call that writes is put_object; there is no delete call anywhere.
  * After --apply it re-lists the bucket and proves every pre-existing object
    is unchanged (ETag + size + LastModified vs a snapshot taken seconds
    before the upload) and that every uploaded object is byte-identical to
    the local file (ETag == md5).

Credentials: reads WASABI_... from data_services/.env directly (load_dotenv,
not load_env) on purpose -- this is a deliberate main-branch-equivalent
action, performed from a feature branch by explicit human request.
"""
import hashlib
import os
import sys
from pathlib import Path

import boto3
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
ENV_FILE = REPO / "data_services" / ".env"
STORAGE = REPO / "data_services" / "storage"
PREFIX = "dev/"
APPLY = "--apply" in sys.argv

ALLOWED = (
    "dev/inputs/agri_dept/",
    "dev/department/agri_dept/",
    "dev/inputs/rural_development_department/",
    "dev/department/rural_development_department/",
)
# Any of these as a path segment means the key belongs to someone else.
DENIED = ("pwd", "vishwakarma", "health", "education", "public_works",
          "revenue", "social_welfare", "women_and_child", "basic_education")
# Shared files that must survive untouched (checked before AND after).
SHARED = ("dev/_lookups/departments.csv", "dev/_lookups/datasets.csv", "dev/_lookups/tables.csv")

load_dotenv(ENV_FILE)
client = boto3.client(
    "s3",
    endpoint_url=os.environ["WASABI_ENDPOINT_URL"],
    region_name=os.environ.get("WASABI_REGION") or "us-west-1",
    aws_access_key_id=os.environ["WASABI_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["WASABI_SECRET_ACCESS_KEY"],
)
bucket = os.environ["WASABI_BUCKET"]


def list_remote() -> dict:
    out = {}
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for o in page.get("Contents", []):
            out[o["Key"]] = (o["Size"], o["LastModified"].isoformat())
    return out


def snapshot(keys) -> dict:
    snap = {}
    for key in keys:
        h = client.head_object(Bucket=bucket, Key=key)
        snap[key] = {"etag": h["ETag"].strip('"'), "size": h["ContentLength"],
                     "last_modified": h["LastModified"].isoformat()}
    return snap


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


# ---- build the upload set: ONLY our two departments' local files ----
pairs = []  # (local path, remote key)
for dept in ("agri_dept", "rural_development_department"):
    for area in ("inputs", "department"):
        root = STORAGE / area / dept
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file():
                pairs.append((path, PREFIX + f"{area}/{dept}/" + path.relative_to(root).as_posix()))

print(f"upload set: {len(pairs)} file(s), "
      f"{sum(p.stat().st_size for p, _ in pairs):,} bytes")

# ---- every safety check must pass before anything is written ----
problems = []
for path, key in pairs:
    if not key.startswith(ALLOWED):
        problems.append(f"outside our namespaces: {key}")
    if any(marker in key.lower().split("/") for marker in DENIED):
        problems.append(f"belongs to another department: {key}")
    if key.startswith("dev/_lookups/"):
        problems.append(f"would touch a shared registry file: {key}")

remote = list_remote()
pre_existing = snapshot(list(remote))
overlap = [k for _, k in pairs if k in remote]
if overlap:
    problems.append(f"{len(overlap)} target(s) already exist in the bucket -- "
                    f"refusing to overwrite: {overlap[:5]}")

for key in SHARED:
    if key not in remote:
        problems.append(f"expected shared file missing from bucket: {key}")

if problems:
    print("\nSAFETY CHECKS FAILED -- nothing was written:")
    for p in problems:
        print(f"  x {p}")
    raise SystemExit(1)

print("\nsafety checks passed:")
print(f"  + all {len(pairs)} keys are inside our 4 namespaces")
print(f"  + zero overlap with the {len(remote)} pre-existing object(s) -- nothing can be overwritten")
print(f"  + the 3 shared _lookups files are NOT in the upload set (other teams' rows stay)")
print(f"  + no delete call exists in this script; the only write is put_object")
print(f"\npre-existing objects (must stay identical after --apply):")
for key in sorted(remote):
    print(f"  {remote[key][0]:>8}  {key}")

if not APPLY:
    print("\nDRY RUN -- nothing was written. Re-run with --apply to upload.")
    raise SystemExit(0)

# ---- upload (new keys only) ----
print("\nuploading...")
for i, (path, key) in enumerate(pairs, 1):
    client.put_object(Bucket=bucket, Key=key, Body=path.read_bytes())
    if i % 50 == 0 or i == len(pairs):
        print(f"  {i}/{len(pairs)}")

# ---- prove nothing else changed ----
print("\nverifying...")
after_remote = list_remote()
after_snapshot = snapshot(list(pre_existing))

drift = [k for k, v in pre_existing.items() if after_snapshot.get(k) != v]
new_keys = sorted(set(after_remote) - set(pre_existing))
bad_upload = []
for path, key in pairs:
    head = client.head_object(Bucket=bucket, Key=key)
    if head["ETag"].strip('"') != md5(path) or head["ContentLength"] != path.stat().st_size:
        bad_upload.append(key)

print(f"  uploaded:            {len(new_keys)} new object(s)")
print(f"  pre-existing drift:  {len(drift)} (0 = every other object untouched)")
print(f"  content mismatches:  {len(bad_upload)} (0 = every upload byte-identical to local)")
print(f"  bucket total now:    {len(after_remote)} object(s)")

ok = not drift and not bad_upload and len(new_keys) == len(pairs)
print("\nRESULT:", "verified -- our files are on Wasabi, nothing else was touched"
      if ok else "PROBLEM -- inspect above")
raise SystemExit(0 if ok else 1)
