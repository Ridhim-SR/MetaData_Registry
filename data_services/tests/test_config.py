import os

import pytest

from src.utils import config

_KEYS = (
    "ENVIRONMENT", "OPENMETADATA_HOST_PORT", "OPENMETADATA_JWT_TOKEN",
    "LOCAL_OPENMETADATA_HOST_PORT", "LOCAL_OPENMETADATA_JWT_TOKEN",
    "DEV_OPENMETADATA_HOST_PORT", "DEV_OPENMETADATA_JWT_TOKEN",
    "PROD_OPENMETADATA_HOST_PORT", "PROD_OPENMETADATA_JWT_TOKEN",
    "WASABI_BUCKET", "WASABI_PREFIX", "DEPARTMENT", "WASABI_ACCESS_KEY_ID",
    "WASABI_ENDPOINT_URL", "WASABI_SECRET_ACCESS_KEY", "WASABI_REGION", "WASABI_BACKUP_BUCKET", "WASABI_BACKUP_REGION",
    "LOCAL_WASABI_BUCKET", "LOCAL_WASABI_ACCESS_KEY_ID", "LOCAL_WASABI_ENDPOINT_URL", "LOCAL_WASABI_SECRET_ACCESS_KEY",
)


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        "ENVIRONMENT=development\n"
        "LOCAL_OPENMETADATA_HOST_PORT=http://localhost:8585/api\nLOCAL_OPENMETADATA_JWT_TOKEN=local-token\n"
        "DEV_OPENMETADATA_HOST_PORT=http://10.0.96.105:8585/api\nDEV_OPENMETADATA_JWT_TOKEN=dev-token\n"
        "PROD_OPENMETADATA_HOST_PORT=http://prod:8585/api\nPROD_OPENMETADATA_JWT_TOKEN=prod-token\n"
        "WASABI_BUCKET=pwd-schema-registry\nDEPARTMENT=pwd\n"
        "LOCAL_WASABI_BUCKET=my-own-bucket\nLOCAL_WASABI_ENDPOINT_URL=https://s3.us-west-1.wasabisys.com\n"
        "LOCAL_WASABI_ACCESS_KEY_ID=my-own-key\nLOCAL_WASABI_SECRET_ACCESS_KEY=my-own-secret\n"
    )
    monkeypatch.setattr(config, "_ENV_FILE", path)
    monkeypatch.setattr(config, "_current_branch", lambda: "feature/some-work")  # tests pick their branch
    for key in _KEYS:
        monkeypatch.delenv(key, raising=False)
    yield path
    for key in _KEYS:  # load_env writes to os.environ directly; don't leak into other tests
        os.environ.pop(key, None)


def _on(monkeypatch, branch):
    monkeypatch.setattr(config, "_current_branch", lambda: branch)


def test_development_on_main_uses_dev_server_and_dev_folder(env_file, monkeypatch):
    _on(monkeypatch, "main")
    assert config.load_env() == "development"
    assert os.environ["OPENMETADATA_HOST_PORT"] == "http://10.0.96.105:8585/api"
    assert os.environ["OPENMETADATA_JWT_TOKEN"] == "dev-token"
    assert (os.environ["WASABI_BUCKET"], os.environ["WASABI_PREFIX"]) == ("pwd-schema-registry", "dev")
    assert os.environ["DEPARTMENT"] == "pwd"


def test_production_on_production_branch_uses_prod_server_and_prod_folder(env_file, monkeypatch):
    _on(monkeypatch, "production")
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert config.load_env() == "production"
    assert os.environ["OPENMETADATA_HOST_PORT"] == "http://prod:8585/api"
    assert os.environ["WASABI_PREFIX"] == "prod"


def test_local_uses_wasabi_local_folder_and_local_server(env_file, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    assert config.load_env() == "local"
    assert (os.environ["WASABI_BUCKET"], os.environ["WASABI_PREFIX"]) == ("my-own-bucket", "local")
    assert os.environ["OPENMETADATA_JWT_TOKEN"] == "local-token"


@pytest.mark.parametrize("branch, expected", [("feature/some-work", "local"), ("main", "development"),
                                              ("production", "production"), (None, "local")])
def test_blank_environment_follows_the_branch(env_file, monkeypatch, branch, expected):
    env_file.write_text(env_file.read_text().replace("ENVIRONMENT=development\n", ""))
    _on(monkeypatch, branch)
    assert config.load_env() == expected


def test_storage_is_wasabi_in_this_environments_folder(env_file, monkeypatch):
    from src.storage import storage_from_env
    from src.storage.s3 import S3ObjectStorage

    monkeypatch.setenv("ENVIRONMENT", "local")
    config.load_env()
    storage = storage_from_env()
    assert isinstance(storage, S3ObjectStorage)
    assert storage._key("_lookups/tables.csv") == "local/_lookups/tables.csv"


@pytest.mark.parametrize("env", ["local", "development"])
def test_without_bucket_refuses_to_run(env_file, monkeypatch, env):
    env_file.write_text("")
    _on(monkeypatch, "main" if env == "development" else "feature/x")
    monkeypatch.setenv("ENVIRONMENT", env)
    with pytest.raises(ValueError, match="WASABI_BUCKET (is|are) blank|LOCAL_WASABI_BUCKET"):
        config.load_env()


def test_exported_values_win_over_env_file(env_file, monkeypatch):
    _on(monkeypatch, "main")
    monkeypatch.setenv("OPENMETADATA_JWT_TOKEN", "from-shell")
    monkeypatch.setenv("WASABI_PREFIX", "sandbox-aditya")
    config.load_env()
    assert os.environ["OPENMETADATA_JWT_TOKEN"] == "from-shell"
    assert os.environ["WASABI_PREFIX"] == "sandbox-aditya"


def test_unknown_environment_is_rejected(env_file, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    with pytest.raises(ValueError, match="must be one of: local, development, production"):
        config.load_env()


@pytest.mark.parametrize(
    "branch, env, allowed",
    [
        ("production", "production", True),
        ("production", "development", False),
        ("production", "local", False),
        ("main", "development", True),
        ("main", "production", False),
        ("main", "local", False),
        ("fix/SDA-DS-001", "local", True),
        ("fix/SDA-DS-001", "development", False),
        ("fix/SDA-DS-001", "production", False),
        (None, "local", True),           # unknown branch = a feature branch
        (None, "production", False),
    ],
)
def test_branch_rule(branch, env, allowed):
    if allowed:
        config.check_branch_allows(env, branch)
    else:
        with pytest.raises(PermissionError, match=f"ENVIRONMENT={env} isn't allowed"):
            config.check_branch_allows(env, branch)


def test_production_blocked_off_production_branch_before_anything_else_happens(env_file, monkeypatch):
    _on(monkeypatch, "main")
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(PermissionError, match="production only runs on the 'production' branch"):
        config.load_env()
    assert "WASABI_PREFIX" not in os.environ  # refused before any setting was applied


def test_development_on_feature_branch_says_use_main(env_file):
    with pytest.raises(PermissionError, match="development only runs on 'main'"):
        config.load_env()


def test_real_git_branch_is_detected():
    branch = config._current_branch()
    assert branch is None or (branch and branch != "HEAD")


def test_local_uses_only_its_own_wasabi_account(env_file, monkeypatch):
    env_file.write_text(env_file.read_text() + "WASABI_ACCESS_KEY_ID=company-key\n")
    monkeypatch.setenv("ENVIRONMENT", "local")
    config.load_env()
    assert (os.environ["WASABI_BUCKET"], os.environ["WASABI_ACCESS_KEY_ID"]) == ("my-own-bucket", "my-own-key")
    for key in _KEYS:
        os.environ.pop(key, None)
    _on(monkeypatch, "main")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    config.load_env()  # main ignores the LOCAL_ ones
    assert (os.environ["WASABI_BUCKET"], os.environ["WASABI_ACCESS_KEY_ID"]) == ("pwd-schema-registry", "company-key")


def test_local_never_falls_back_to_the_company_wasabi(env_file, monkeypatch):
    env_file.write_text("WASABI_BUCKET=company\nWASABI_ACCESS_KEY_ID=company-key\nLOCAL_WASABI_BUCKET=mine\n")
    monkeypatch.setenv("ENVIRONMENT", "local")
    with pytest.raises(ValueError, match="LOCAL_WASABI_ENDPOINT_URL, LOCAL_WASABI_ACCESS_KEY_ID, "
                                         "LOCAL_WASABI_SECRET_ACCESS_KEY are blank"):
        config.load_env()
