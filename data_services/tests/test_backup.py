import boto3
import pytest
from moto import mock_aws

from src.storage import backup
from src.storage.backup import Bucket, backup_after_run, compare, copy, setup
from src.storage.local import LocalObjectStorage
from src.storage.s3 import S3ObjectStorage


@pytest.fixture
def buckets(monkeypatch):
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="main")
        client.create_bucket(Bucket="backup", ObjectLockEnabledForBucket=True)
        monkeypatch.setenv("WASABI_BACKUP_BUCKET", "backup")
        monkeypatch.setenv("WASABI_BACKUP_REGION", "us-east-1")
        monkeypatch.delenv("WASABI_BACKUP_ENDPOINT_URL", raising=False)
        monkeypatch.setattr(backup, "endpoint_for", lambda region: None)  # AWS default -> the moto fake
        yield Bucket(client, "main"), Bucket(client, "backup")


def _put(bucket, key, body):
    bucket.client.put_object(Bucket=bucket.name, Key=key, Body=body)


def _get(bucket, key):
    return bucket.client.get_object(Bucket=bucket.name, Key=key)["Body"].read()


def _keys(bucket):
    return sorted(o["Key"] for o in bucket.client.list_objects_v2(Bucket=bucket.name).get("Contents", []))


def test_copy_adds_missing_and_changed_files_and_skips_locks(buckets):
    main, bak = buckets
    _put(main, "dev/inputs/pwd/a.txt", b"a")
    _put(main, "dev/_locks/x.lock", b"{}")
    copy(main, bak, "dev/")
    assert _keys(bak) == ["dev/inputs/pwd/a.txt"]

    _put(main, "dev/inputs/pwd/a.txt", b"a changed")
    _put(main, "dev/inputs/pwd/b.txt", b"b")
    assert copy(main, bak, "dev/") == ["dev/inputs/pwd/b.txt", "dev/inputs/pwd/a.txt"]
    assert _get(bak, "dev/inputs/pwd/a.txt") == b"a changed"
    assert copy(main, bak, "dev/") == []  # second run: nothing to do


def test_copy_never_deletes_from_backup(buckets):
    main, bak = buckets
    _put(main, "dev/a.txt", b"a")
    copy(main, bak, "dev/")
    main.client.delete_object(Bucket="main", Key="dev/a.txt")
    copy(main, bak, "dev/")
    assert _get(bak, "dev/a.txt") == b"a"


def test_copy_covers_only_the_given_folder(buckets):
    main, bak = buckets
    _put(main, "dev/a.txt", b"a")
    _put(main, "prod/b.txt", b"b")
    copy(main, bak, "dev/")
    assert _keys(bak) == ["dev/a.txt"]
    copy(main, bak, "")
    assert _keys(bak) == ["dev/a.txt", "prod/b.txt"]


def test_compare_reports_missing_and_different(buckets):
    main, bak = buckets
    _put(main, "dev/same.txt", b"s")
    _put(bak, "dev/same.txt", b"s")
    _put(main, "dev/diff.txt", b"new")
    _put(bak, "dev/diff.txt", b"old")
    _put(main, "dev/gone.txt", b"g")
    diff = compare(main, bak, "dev/")
    assert (diff.missing, diff.different, diff.same) == (["dev/gone.txt"], ["dev/diff.txt"], 1)


def test_restore_copies_missing_only_unless_overwrite(buckets):
    main, bak = buckets
    _put(bak, "dev/lost.txt", b"lost")
    _put(bak, "dev/edited.txt", b"backup version")
    _put(main, "dev/edited.txt", b"newer version")

    assert copy(bak, main, "dev/", overwrite=False, dry_run=True) == ["dev/lost.txt"]
    assert "dev/lost.txt" not in _keys(main)  # dry run changed nothing
    copy(bak, main, "dev/", overwrite=False)
    assert _get(main, "dev/lost.txt") == b"lost"
    assert _get(main, "dev/edited.txt") == b"newer version"
    copy(bak, main, "dev/", overwrite=True)
    assert _get(main, "dev/edited.txt") == b"backup version"


def test_backup_after_run_copies_this_environments_folder(buckets):
    main, bak = buckets
    storage = S3ObjectStorage(bucket="main", prefix="dev", region_name="us-east-1")
    storage.write_bytes("inputs/pwd/a.txt", b"a")
    _put(main, "prod/other.txt", b"p")
    assert backup_after_run(storage) is True
    assert _keys(bak) == ["dev/inputs/pwd/a.txt"]


def test_backup_after_run_reports_failure_without_raising(buckets, monkeypatch):
    storage = S3ObjectStorage(bucket="main", prefix="dev", region_name="us-east-1")
    storage.write_bytes("a.txt", b"a")
    monkeypatch.setenv("WASABI_BACKUP_BUCKET", "no-such-bucket")
    assert backup_after_run(storage) is False


def test_backup_after_run_does_nothing_for_local_or_unset(buckets, monkeypatch, tmp_path):
    assert backup_after_run(LocalObjectStorage(str(tmp_path))) is True
    monkeypatch.setenv("WASABI_BACKUP_BUCKET", "")
    assert backup_after_run(S3ObjectStorage(bucket="main", prefix="dev", region_name="us-east-1")) is True


@pytest.fixture
def account():
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="main")
        yield Bucket(s3, "main"), Bucket(s3, "new-backup"), boto3.client("iam", region_name="us-east-1")


def test_setup_turns_everything_on_and_second_run_does_nothing(account):
    main, bak, iam = account
    steps = setup(main, bak, "us-east-1", iam=iam, pipeline_user="sda-pipeline")
    assert all(s.endswith(("set", "on", "created", "attached", "Object Lock",
                           "created (read/write, never permanently delete)")) for s in steps), steps

    s3 = main.client
    assert s3.get_bucket_versioning(Bucket="main")["Status"] == "Enabled"
    lock = s3.get_object_lock_configuration(Bucket="new-backup")["ObjectLockConfiguration"]
    assert lock["Rule"]["DefaultRetention"]["Mode"] == "GOVERNANCE"
    assert lock["Rule"]["DefaultRetention"]["Days"] == backup.LOCK_DAYS
    rule = s3.get_bucket_lifecycle_configuration(Bucket="main")["Rules"][0]
    assert rule["NoncurrentVersionExpiration"]["NoncurrentDays"] == backup.MAIN_KEEP_OLD_VERSIONS_DAYS
    attached = iam.list_attached_user_policies(UserName="sda-pipeline")["AttachedPolicies"]
    assert [p["PolicyName"] for p in attached] == [backup._POLICY_NAME]

    again = setup(main, bak, "us-east-1", iam=iam, pipeline_user="sda-pipeline")
    assert all("already" in s for s in again), again


def test_setup_dry_run_changes_nothing(account):
    main, bak, iam = account
    steps = setup(main, bak, "us-east-1", iam=iam, pipeline_user="sda-pipeline", create_key=True, dry_run=True)
    assert any("created in us-east-1" in s for s in steps)
    s3 = main.client
    assert [b["Name"] for b in s3.list_buckets()["Buckets"]] == ["main"]
    assert s3.get_bucket_versioning(Bucket="main").get("Status") is None
    assert iam.list_users()["Users"] == []


def test_setup_keeps_existing_lifecycle_rules(account):
    main, bak, _ = account
    main.client.put_bucket_lifecycle_configuration(Bucket="main", LifecycleConfiguration={"Rules": [
        {"ID": "someone-elses", "Status": "Enabled", "Filter": {"Prefix": "tmp/"}, "Expiration": {"Days": 7}},
    ]})
    setup(main, bak, "us-east-1")
    ids = sorted(r["ID"] for r in main.client.get_bucket_lifecycle_configuration(Bucket="main")["Rules"])
    assert ids == ["sda-keep-old-versions", "someone-elses"]


def test_setup_refuses_existing_backup_bucket_without_object_lock(account):
    main, _, _ = account
    main.client.create_bucket(Bucket="plain")
    with pytest.raises(ValueError, match="without Object Lock"):
        setup(main, Bucket(main.client, "plain"), "us-east-1")


def test_create_key_returns_new_key(account):
    main, bak, iam = account
    steps = setup(main, bak, "us-east-1", iam=iam, pipeline_user="sda-pipeline", create_key=True)
    assert any("WASABI_SECRET_ACCESS_KEY=" in s for s in steps)
    assert len(iam.list_access_keys(UserName="sda-pipeline")["AccessKeyMetadata"]) == 1


def test_pipeline_policy_denies_permanent_deletes_on_both_buckets():
    policy = backup.pipeline_policy("main", "bak")
    deny = next(s for s in policy["Statement"] if s["Effect"] == "Deny")
    assert "s3:DeleteObjectVersion" in deny["Action"] and "s3:DeleteBucket" in deny["Action"]
    assert set(deny["Resource"]) == {"arn:aws:s3:::main", "arn:aws:s3:::main/*", "arn:aws:s3:::bak", "arn:aws:s3:::bak/*"}
