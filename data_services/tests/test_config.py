import os

import pytest

from src.utils import config

_KEYS = (
    "OPENMETADATA_ENV", "OPENMETADATA_HOST_PORT", "OPENMETADATA_JWT_TOKEN",
    "LOCAL_OPENMETADATA_HOST_PORT", "LOCAL_OPENMETADATA_JWT_TOKEN",
    "DEV_OPENMETADATA_HOST_PORT", "DEV_OPENMETADATA_JWT_TOKEN", "DEPARTMENT",
)


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        "OPENMETADATA_ENV=development\n"
        "LOCAL_OPENMETADATA_HOST_PORT=http://localhost:8585/api\nLOCAL_OPENMETADATA_JWT_TOKEN=local-token\n"
        "DEV_OPENMETADATA_HOST_PORT=http://10.0.96.105:8585/api\nDEV_OPENMETADATA_JWT_TOKEN=dev-token\n"
        "DEPARTMENT=pwd\n"
    )
    monkeypatch.setattr(config, "_ENV_FILE", path)
    for key in _KEYS:
        monkeypatch.delenv(key, raising=False)
    yield path
    for key in _KEYS:  # load_env writes to os.environ directly; don't leak into other tests
        os.environ.pop(key, None)


def test_openmetadata_env_picks_that_servers_address_and_token(env_file):
    assert config.load_env() == "development"
    assert os.environ["OPENMETADATA_HOST_PORT"] == "http://10.0.96.105:8585/api"
    assert os.environ["OPENMETADATA_JWT_TOKEN"] == "dev-token"
    assert os.environ["DEPARTMENT"] == "pwd"


def test_shell_can_switch_server_for_one_run(env_file, monkeypatch):
    monkeypatch.setenv("OPENMETADATA_ENV", "local")
    assert config.load_env() == "local"
    assert os.environ["OPENMETADATA_HOST_PORT"] == "http://localhost:8585/api"
    assert os.environ["OPENMETADATA_JWT_TOKEN"] == "local-token"


def test_exported_token_wins_over_env_file(env_file, monkeypatch):
    monkeypatch.setenv("OPENMETADATA_JWT_TOKEN", "from-shell")
    config.load_env()
    assert os.environ["OPENMETADATA_JWT_TOKEN"] == "from-shell"


def test_defaults_to_local(env_file):
    env_file.write_text("LOCAL_OPENMETADATA_HOST_PORT=http://localhost:8585/api\n")
    assert config.load_env() == "local"
    assert os.environ["OPENMETADATA_HOST_PORT"] == "http://localhost:8585/api"


def test_unknown_environment_is_rejected(env_file, monkeypatch):
    monkeypatch.setenv("OPENMETADATA_ENV", "staging")
    with pytest.raises(ValueError, match="must be one of: local, development"):
        config.load_env()
