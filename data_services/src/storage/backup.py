"""A second, locked copy of the Wasabi data in another region, kept up to
date automatically.

    python3 -m src.storage.backup setup [--dry-run] [--pipeline-user NAME [--create-key]]
    python3 -m src.storage.backup copy    [--all]
    python3 -m src.storage.backup verify  [--all]
    python3 -m src.storage.backup restore [--all] [--overwrite] [--dry-run]

- setup (once per bucket, with the admin key) makes the backup bucket with
  Object Lock (nothing in it can be deleted for LOCK_DAYS), keeps old
  versions in both buckets for a while, and -- with --pipeline-user --
  creates a Wasabi user for .env that can never permanently delete data.
  Safe to run again: it only does what is still missing.
- copy runs by itself after every `add` and `sync` when WASABI_BACKUP_BUCKET
  is set; by hand it catches up after a failed copy. It only adds: nothing
  in the backup is ever deleted.
- verify checks every file has an identical copy in the backup.
- restore copies files back from the backup (missing ones only, unless
  --overwrite).

copy/verify/restore cover this ENVIRONMENT's folder (local/, dev/ or prod/); --all
covers the whole bucket. Wasabi's own bucket replication isn't used because
trial accounts can't turn it on, and this works on every plan.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

import boto3
from botocore.exceptions import ClientError

from src.storage.s3 import S3ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_BACKUP_REGION = "eu-central-1"  # a different region from the main bucket
LOCK_DAYS = 90  # nothing in the backup can be deleted for this long
MAIN_KEEP_OLD_VERSIONS_DAYS = 90  # overwritten/deleted files stay restorable this long
BACKUP_KEEP_OLD_VERSIONS_DAYS = 365
_LIFECYCLE_RULE_ID = "sda-keep-old-versions"
_POLICY_NAME = "sda-pipeline-no-permanent-delete"
_SKIP = "_locks/"  # short-lived lock files, never worth copying

# What the pipeline user may never do, on either bucket: erase an old
# version, drop a bucket, or switch off the protections setup turned on.
_DENIED_ACTIONS = [
    "s3:DeleteObjectVersion",
    "s3:DeleteBucket",
    "s3:PutBucketVersioning",
    "s3:PutLifecycleConfiguration",
    "s3:PutBucketObjectLockConfiguration",
    "s3:BypassGovernanceRetention",
    "s3:PutBucketPolicy",
    "s3:DeleteBucketPolicy",
]


def endpoint_for(region: str) -> str:
    return f"https://s3.{region}.wasabisys.com"


def _code(exc: ClientError) -> str:
    return exc.response.get("Error", {}).get("Code", "?")


# --- copying ---------------------------------------------------------------


@dataclass
class Bucket:
    client: object
    name: str


@dataclass
class Diff:
    missing: list[str] = field(default_factory=list)  # in source, not in target
    different: list[str] = field(default_factory=list)  # in both, content differs
    same: int = 0


def _objects(bucket: Bucket, prefix: str) -> dict[str, tuple[int, str]]:
    """key -> (size, ETag) of the current version of every file under
    `prefix`, lock files left out. One listing call per 1000 files."""

    found = {}
    paginator = bucket.client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket.name, Prefix=prefix):
        for obj in page.get("Contents", []):
            if not obj["Key"][len(prefix):].startswith(_SKIP):
                found[obj["Key"]] = (obj["Size"], obj["ETag"])
    return found


def compare(source: Bucket, target: Bucket, prefix: str) -> Diff:
    """Which files under `prefix` the target lacks or holds differently.
    The ETag of a file written in one PUT is the MD5 of its content, so
    equal size + ETag means identical bytes -- no download needed."""

    src, dst = _objects(source, prefix), _objects(target, prefix)
    diff = Diff()
    for key, meta in sorted(src.items()):
        if key not in dst:
            diff.missing.append(key)
        elif dst[key] != meta:
            diff.different.append(key)
        else:
            diff.same += 1
    return diff


def copy(source: Bucket, target: Bucket, prefix: str, overwrite: bool = True, dry_run: bool = False) -> list[str]:
    """Copy what `target` lacks (and, with overwrite, what differs) from
    `source`. Never deletes anything. Returns the keys copied. Downloads
    and re-uploads rather than a server-side copy, so the two buckets can
    be in different regions."""

    diff = compare(source, target, prefix)
    keys = diff.missing + (diff.different if overwrite else [])
    if not dry_run:
        for key in keys:
            body = source.client.get_object(Bucket=source.name, Key=key)["Body"].read()
            target.client.put_object(Bucket=target.name, Key=key, Body=body)
    return keys


def _prefix(storage_prefix: str, everything: bool) -> str:
    return "" if everything or not storage_prefix else storage_prefix.strip("/") + "/"


def backup_bucket_from_env() -> Bucket | None:
    name = os.environ.get("WASABI_BACKUP_BUCKET", "").strip()
    if not name:
        return None
    region = os.environ.get("WASABI_BACKUP_REGION") or DEFAULT_BACKUP_REGION
    client = boto3.client(
        "s3",
        endpoint_url=os.environ.get("WASABI_BACKUP_ENDPOINT_URL") or endpoint_for(region),
        aws_access_key_id=os.environ.get("WASABI_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("WASABI_SECRET_ACCESS_KEY"),
        region_name=region,
    )
    return Bucket(client, name)


def backup_after_run(storage) -> bool:
    """Called at the end of `add` and `sync`: bring the backup up to date
    for this ENVIRONMENT's folder. Does nothing for local storage or when no
    backup bucket is set. Never raises -- the run's own work is already
    saved; a failed backup is reported and caught up by the next run (or
    `backup copy`). Returns False only if the backup failed."""

    if not isinstance(storage, S3ObjectStorage):
        return True
    target = backup_bucket_from_env()
    if target is None:
        logger.warning("No backup bucket set (WASABI_BACKUP_BUCKET in .env) -- this run's files have no second copy.")
        return True
    try:
        copied = copy(Bucket(storage.client, storage.bucket), target, _prefix(storage.prefix, False))
    except Exception as exc:  # noqa: BLE001 -- see docstring
        logger.error(
            f"Backup to '{target.name}' failed ({type(exc).__name__}: {exc}). Your data is saved in "
            f"'{storage.bucket}'; the next add/sync catches up, or run: python3 -m src.storage.backup copy"
        )
        return False
    logger.info(f"Backup: {len(copied)} file(s) copied to '{target.name}'" if copied else
                f"Backup: '{target.name}' already up to date")
    return True


# --- one-time setup ----------------------------------------------------------


def pipeline_policy(main_bucket: str, backup_bucket: str) -> dict:
    resources = [f"arn:aws:s3:::{b}{suffix}" for b in (main_bucket, backup_bucket) for suffix in ("", "/*")]
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "ListBuckets", "Effect": "Allow", "Action": "s3:ListAllMyBuckets", "Resource": "*"},
            {
                "Sid": "PipelineReadWrite",
                "Effect": "Allow",
                "Action": ["s3:ListBucket", "s3:GetBucketLocation", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                "Resource": resources,
            },
            {"Sid": "NeverPermanentlyDelete", "Effect": "Deny", "Action": _DENIED_ACTIONS, "Resource": resources},
        ],
    }


def _keep_old_versions(client, bucket: str, days: int, dry_run: bool) -> str:
    """Our lifecycle rule (old versions expire after `days`, leftover
    delete markers are cleaned up), merged with any rules set in the
    console so those aren't lost."""

    try:
        rules = client.get_bucket_lifecycle_configuration(Bucket=bucket)["Rules"]
    except ClientError as exc:
        if _code(exc) != "NoSuchLifecycleConfiguration":
            raise
        rules = []
    ours = [r for r in rules if r.get("ID") == _LIFECYCLE_RULE_ID]
    if ours and ours[0].get("NoncurrentVersionExpiration", {}).get("NoncurrentDays") == days:
        return f"{bucket}: old versions kept {days} days -- already set"
    if not dry_run:
        rules = [r for r in rules if r.get("ID") != _LIFECYCLE_RULE_ID] + [{
            "ID": _LIFECYCLE_RULE_ID,
            "Status": "Enabled",
            "Filter": {"Prefix": ""},
            "NoncurrentVersionExpiration": {"NoncurrentDays": days},
            "Expiration": {"ExpiredObjectDeleteMarker": True},
        }]
        client.put_bucket_lifecycle_configuration(Bucket=bucket, LifecycleConfiguration={"Rules": rules})
    return f"{bucket}: old versions kept {days} days -- set"


def _ensure_versioning(client, bucket: str, dry_run: bool) -> tuple[str, bool]:
    """(step, whether the bucket exists after this). A new account has no
    main bucket yet, so it's created here, in the client's region."""

    try:
        if client.get_bucket_versioning(Bucket=bucket).get("Status") == "Enabled":
            return f"{bucket}: versioning -- already on", True
    except ClientError as exc:
        if _code(exc) != "NoSuchBucket":
            raise
        if dry_run:
            return f"{bucket}: created in {client.meta.region_name}, with versioning", False
        region = client.meta.region_name
        client.create_bucket(Bucket=bucket, **({} if region == "us-east-1" else
                                                {"CreateBucketConfiguration": {"LocationConstraint": region}}))
        client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
        return f"{bucket}: created in {region}, with versioning", True
    if not dry_run:
        client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
    return f"{bucket}: versioning -- turned on", True


def _ensure_backup_bucket(client, bucket: str, region: str, dry_run: bool) -> tuple[list[str], bool]:
    """(steps, whether the bucket exists after this)."""
    try:
        client.head_bucket(Bucket=bucket)
        exists = True
    except ClientError as exc:
        if _code(exc) not in ("404", "NoSuchBucket", "NotFound"):
            raise
        exists = False

    if exists:
        try:
            lock = client.get_object_lock_configuration(Bucket=bucket)["ObjectLockConfiguration"]
        except ClientError as exc:
            if _code(exc) != "ObjectLockConfigurationNotFoundError":
                raise
            lock = {}
        if lock.get("ObjectLockEnabled") != "Enabled":
            raise ValueError(
                f"Backup bucket '{bucket}' already exists without Object Lock, which can only be turned on "
                f"when a bucket is created -- set WASABI_BACKUP_BUCKET to a new name and run setup again"
            )
        steps = [f"{bucket}: exists in its region, with Object Lock -- already set"]
    else:
        if not dry_run:
            create = {"Bucket": bucket, "ObjectLockEnabledForBucket": True}
            if region != "us-east-1":
                create["CreateBucketConfiguration"] = {"LocationConstraint": region}
            client.create_bucket(**create)
        steps = [f"{bucket}: created in {region}, with Object Lock"]

    retention = {"Mode": "GOVERNANCE", "Days": LOCK_DAYS}
    current = lock.get("Rule", {}).get("DefaultRetention", {}) if exists else {}
    if {k: current.get(k) for k in retention} == retention:  # servers may add e.g. Years: 0
        steps.append(f"{bucket}: every file locked {LOCK_DAYS} days -- already set")
    else:
        if not dry_run:
            client.put_object_lock_configuration(Bucket=bucket, ObjectLockConfiguration={
                "ObjectLockEnabled": "Enabled", "Rule": {"DefaultRetention": retention},
            })
        steps.append(f"{bucket}: every file locked {LOCK_DAYS} days -- set")
    return steps, exists or not dry_run


def _ensure_pipeline_user(iam, user: str, policy: dict, create_key: bool, dry_run: bool) -> list[str]:
    steps = []
    try:
        iam.get_user(UserName=user)
        user_exists = True
        steps.append(f"user {user}: already exists")
    except ClientError as exc:
        if _code(exc) != "NoSuchEntity":
            raise
        if not dry_run:
            iam.create_user(UserName=user)
        user_exists = not dry_run
        steps.append(f"user {user}: created")

    account = iam.get_user()["User"]["Arn"].split(":")[4]
    arn = f"arn:aws:iam::{account}:policy/{_POLICY_NAME}"
    document = json.dumps(policy)
    try:
        version = iam.get_policy(PolicyArn=arn)["Policy"]["DefaultVersionId"]
        current = iam.get_policy_version(PolicyArn=arn, VersionId=version)["PolicyVersion"]["Document"]
        if isinstance(current, str):
            from urllib.parse import unquote
            current = json.loads(unquote(current))
        if current == policy:
            steps.append(f"policy {_POLICY_NAME}: already up to date")
        else:
            if not dry_run:
                old = [v for v in iam.list_policy_versions(PolicyArn=arn)["Versions"] if not v["IsDefaultVersion"]]
                if len(old) >= 4:  # AWS-style limit of 5 versions
                    iam.delete_policy_version(PolicyArn=arn, VersionId=sorted(old, key=lambda v: v["CreateDate"])[0]["VersionId"])
                iam.create_policy_version(PolicyArn=arn, PolicyDocument=document, SetAsDefault=True)
            steps.append(f"policy {_POLICY_NAME}: updated")
    except ClientError as exc:
        if _code(exc) != "NoSuchEntity":
            raise
        if not dry_run:
            iam.create_policy(PolicyName=_POLICY_NAME, PolicyDocument=document)
        steps.append(f"policy {_POLICY_NAME}: created (read/write, never permanently delete)")

    attached = [p["PolicyArn"] for p in iam.list_attached_user_policies(UserName=user)["AttachedPolicies"]] \
        if user_exists else []
    if arn in attached:
        steps.append(f"user {user}: policy already attached")
    else:
        if not dry_run:
            iam.attach_user_policy(UserName=user, PolicyArn=arn)
        steps.append(f"user {user}: policy attached")

    if create_key:
        if dry_run:
            steps.append(f"user {user}: new access key would be created")
        else:
            key = iam.create_access_key(UserName=user)["AccessKey"]
            steps.append(
                f"user {user}: new access key created -- put these in .env now (the secret is shown only once):\n"
                f"      WASABI_ACCESS_KEY_ID={key['AccessKeyId']}\n"
                f"      WASABI_SECRET_ACCESS_KEY={key['SecretAccessKey']}"
            )
    return steps


def setup(main: Bucket, backup: Bucket, backup_region: str, iam=None, pipeline_user: str | None = None,
          create_key: bool = False, dry_run: bool = False) -> list[str]:
    """Turn on every protection that's still missing; return what was (or,
    with dry_run, would be) done, one line per step."""

    step, main_exists = _ensure_versioning(main.client, main.name, dry_run)
    steps = [step, _keep_old_versions(main.client, main.name, MAIN_KEEP_OLD_VERSIONS_DAYS, dry_run) if main_exists
             else f"{main.name}: old versions kept {MAIN_KEEP_OLD_VERSIONS_DAYS} days -- set"]
    bucket_steps, backup_exists = _ensure_backup_bucket(backup.client, backup.name, backup_region, dry_run)
    steps += bucket_steps
    if backup_exists:
        steps.append(_keep_old_versions(backup.client, backup.name, BACKUP_KEEP_OLD_VERSIONS_DAYS, dry_run))
    else:  # dry run, bucket not made yet: nothing to read
        steps.append(f"{backup.name}: old versions kept {BACKUP_KEEP_OLD_VERSIONS_DAYS} days -- set")
    if pipeline_user:
        steps += _ensure_pipeline_user(iam, pipeline_user, pipeline_policy(main.name, backup.name), create_key, dry_run)
    return steps


# --- command line ------------------------------------------------------------


def _main(argv: list[str]) -> int:
    from src.storage import storage_from_env
    from src.utils.config import load_env

    parser = argparse.ArgumentParser(prog="python3 -m src.storage.backup", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_setup = sub.add_parser("setup", help="one-time: backup bucket, Object Lock, version history, pipeline user")
    p_setup.add_argument("--dry-run", action="store_true", help="show what would be done, change nothing")
    p_setup.add_argument("--pipeline-user", help="also create/update this Wasabi user for .env (e.g. sda-pipeline)")
    p_setup.add_argument("--create-key", action="store_true", help="with --pipeline-user: make it a new access key")
    for name, text in (("copy", "copy new/changed files to the backup"),
                       ("verify", "check the backup has an identical copy of every file"),
                       ("restore", "copy files back from the backup")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--all", action="store_true", help="the whole bucket, not just this ENVIRONMENT's folder")
    p_restore = sub.choices["restore"]
    p_restore.add_argument("--overwrite", action="store_true", help="also replace files that differ from the backup")
    p_restore.add_argument("--dry-run", action="store_true", help="show what would be restored, change nothing")
    args = parser.parse_args(argv)

    load_env()
    main_storage = storage_from_env()
    main = Bucket(main_storage.client, main_storage.bucket)
    backup = backup_bucket_from_env()
    if backup is None:
        raise ValueError(
            "WASABI_BACKUP_BUCKET is blank in .env -- set it (e.g. pwd-schema-registry-backup) "
            "and WASABI_BACKUP_REGION (default eu-central-1)"
        )
    if backup.name == main.name:
        raise ValueError("WASABI_BACKUP_BUCKET is the same as WASABI_BUCKET -- the backup needs its own bucket")

    if args.command == "setup":
        if args.create_key and not args.pipeline_user:
            parser.error("--create-key needs --pipeline-user")
        # Setup changes account settings, so it may use a separate admin key
        # that never sits in .env (put it in front of the command).
        admin = dict(
            aws_access_key_id=os.environ.get("WASABI_ADMIN_ACCESS_KEY_ID") or os.environ.get("WASABI_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("WASABI_ADMIN_SECRET_ACCESS_KEY") or os.environ.get("WASABI_SECRET_ACCESS_KEY"),
        )
        region = os.environ.get("WASABI_BACKUP_REGION") or DEFAULT_BACKUP_REGION
        main = Bucket(boto3.client("s3", endpoint_url=os.environ.get("WASABI_ENDPOINT_URL"),
                                   region_name=os.environ.get("WASABI_REGION"), **admin), main.name)
        backup = Bucket(boto3.client("s3", endpoint_url=os.environ.get("WASABI_BACKUP_ENDPOINT_URL") or endpoint_for(region),
                                     region_name=region, **admin), backup.name)
        iam = boto3.client("iam", endpoint_url="https://iam.wasabisys.com", region_name="us-east-1", **admin) \
            if args.pipeline_user else None
        print("Checking Wasabi settings -- this takes 1-3 minutes (Wasabi answers slowly), please wait...", flush=True)
        steps = setup(main, backup, region, iam=iam, pipeline_user=args.pipeline_user,
                      create_key=args.create_key, dry_run=args.dry_run)
        print(("Would do (dry run, nothing changed):" if args.dry_run else "Done:") + "\n" +
              "\n".join(f"  - {s}" for s in steps))
        if not args.dry_run:
            print("\nNext: python3 -m src.storage.backup copy --all   (first full copy), then verify --all")
        return 0

    prefix = _prefix(main_storage.prefix, args.all)
    where = f"{main.name}/{prefix or ''}"
    if args.command == "copy":
        copied = copy(main, backup, prefix)
        print(f"Copied {len(copied)} file(s) from {where} to {backup.name}." if copied else
              f"Backup already up to date for {where}.")
        return 0

    if args.command == "verify":
        diff = compare(main, backup, prefix)
        for key in diff.missing:
            print(f"  MISSING in backup:  {key}")
        for key in diff.different:
            print(f"  DIFFERENT in backup: {key}")
        if diff.missing or diff.different:
            print(f"\n{diff.same} OK, {len(diff.missing)} missing, {len(diff.different)} different. "
                  f"Fix with: python3 -m src.storage.backup copy{' --all' if args.all else ''}")
            return 1
        print(f"All {diff.same} file(s) in {where} have an identical copy in {backup.name}.")
        return 0

    restored = copy(backup, main, prefix, overwrite=args.overwrite, dry_run=args.dry_run)
    for key in restored:
        print(f"  {'would restore' if args.dry_run else 'restored'}: {key}")
    print(f"{len(restored)} file(s) {'would be ' if args.dry_run else ''}restored to {where}."
          + ("" if args.dry_run or not restored else "\nNext: python3 -m src.schema_registry.sync"))
    return 0


if __name__ == "__main__":
    from src.utils.cli import run_cli

    sys.exit(run_cli("backup", _main, sys.argv[1:]))
