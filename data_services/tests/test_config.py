import os

import pytest

from src.utils import config

_KEYS = (
    "ENVIRONMENT", "OPENMETADATA_HOST_PORT", "OPENMETADATA_JWT_TOKEN",
    "LOCAL_OPENMETADATA_HOST_PORT", "LOCAL_OPENMETADATA_JWT_TOKEN",
    "DEV_OPENMETADATA_HOST_PORT", "DEV_OPENMETADATA_JWT_TOKEN",
    "PROD_OPENMETADATA_HOST_PORT", "PROD_OPENMETADATA_JWT_TOKEN",
    "WASABI_BUCKET", "WASABI_PREFIX", "DEPARTMENT",
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
    )
    monkeypatch.setattr(config, "_ENV_FILE", path)
    monkeypatch.setattr(config, "_current_branch", lambda: "feature/some-work")  # tests pick their branch
    for key in _KEYS:
        monkeypatch.delenv(key, raising=False)
    yield path
    for key in _KEYS:  # load_env writes to os.environ directly; don't leak into other tests
        os.environ.pop(key, None)


def test_development_uses_dev_server_and_dev_folder_in_wasabi(env_file):
    assert config.load_env() == "development"
    assert os.environ["OPENMETADATA_HOST_PORT"] == "http://10.0.96.105:8585/api"
    assert os.environ["OPENMETADATA_JWT_TOKEN"] == "dev-token"
    assert (os.environ["WASABI_BUCKET"], os.environ["WASABI_PREFIX"]) == ("pwd-schema-registry", "dev")
    assert os.environ["DEPARTMENT"] == "pwd"


def test_production_uses_prod_server_and_prod_folder(env_file, monkeypatch):
    monkeypatch.setattr(config, "_current_branch", lambda: "main")
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert config.load_env() == "production"
    assert os.environ["OPENMETADATA_HOST_PORT"] == "http://prod:8585/api"
    assert os.environ["WASABI_PREFIX"] == "prod"


def test_local_never_uses_wasabi_even_if_bucket_is_set(env_file, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    assert config.load_env() == "local"
    assert os.environ["WASABI_BUCKET"] == ""
    assert os.environ["OPENMETADATA_JWT_TOKEN"] == "local-token"


def test_storage_follows_environment(env_file, monkeypatch, tmp_path):
    from src.storage import storage_from_env
    from src.storage.local import LocalObjectStorage
    from src.storage.s3 import S3ObjectStorage

    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    config.load_env()
    assert isinstance(storage_from_env(), LocalObjectStorage)

    for key in _KEYS:
        os.environ.pop(key, None)
    monkeypatch.setenv("ENVIRONMENT", "development")
    config.load_env()
    storage = storage_from_env()
    assert isinstance(storage, S3ObjectStorage)
    assert storage._key("_lookups/tables.csv") == "dev/_lookups/tables.csv"


def test_development_without_bucket_refuses_to_run(env_file, monkeypatch):
    env_file.write_text("ENVIRONMENT=development\n")
    with pytest.raises(ValueError, match="WASABI_BUCKET is blank"):
        config.load_env()


def test_exported_values_win_over_env_file(env_file, monkeypatch):
    monkeypatch.setenv("OPENMETADATA_JWT_TOKEN", "from-shell")
    monkeypatch.setenv("WASABI_PREFIX", "sandbox-aditya")
    config.load_env()
    assert os.environ["OPENMETADATA_JWT_TOKEN"] == "from-shell"
    assert os.environ["WASABI_PREFIX"] == "sandbox-aditya"


def test_defaults_to_local(env_file):
    env_file.write_text("DEPARTMENT=pwd\n")
    assert config.load_env() == "local"


def test_unknown_environment_is_rejected(env_file, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    with pytest.raises(ValueError, match="must be one of: local, development, production"):
        config.load_env()


@pytest.mark.parametrize(
    "branch, env, allowed",
    [
        ("main", "production", True),
        ("main", "development", True),   # BIPP2 dev server runs main
        ("main", "local", False),
        ("fix/SDA-DS-001", "local", True),
        ("fix/SDA-DS-001", "development", True),
        ("fix/SDA-DS-001", "production", False),
        (None, "production", False),     # unknown branch = not main
        (None, "development", True),
    ],
)
def test_branch_rule(branch, env, allowed):
    if allowed:
        config.check_branch_allows(env, branch)
    else:
        with pytest.raises(PermissionError, match=f"ENVIRONMENT={env} isn't allowed"):
            config.check_branch_allows(env, branch)


def test_production_blocked_off_main_before_anything_else_happens(env_file, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(PermissionError, match="production can only be used on 'main'"):
        config.load_env()
    assert "WASABI_PREFIX" not in os.environ  # refused before any setting was applied


def test_local_blocked_on_main_with_a_hint(env_file, monkeypatch):
    monkeypatch.setattr(config, "_current_branch", lambda: "main")
    monkeypatch.setenv("ENVIRONMENT", "local")
    with pytest.raises(PermissionError, match="use development or production"):
        config.load_env()


def test_real_git_branch_is_detected():
    branch = config._current_branch()
    assert branch is None or (branch and branch != "HEAD")
