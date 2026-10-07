"""Item 17 (lock down credentials): the compose stack must not ship known
passwords, self-signup, or MySQL/Elasticsearch published on every interface.

These assertions are the automated half of the "done when" -- the other half
(changing the bootstrap admin password, generating an ingestion-bot JWT) is an
operator step on a running server, documented in
infrastructure/openmetadata/README.md."""

from pathlib import Path

import yaml

_INFRA = Path(__file__).resolve().parents[2] / "infrastructure" / "openmetadata"
_COMPOSE = yaml.safe_load((_INFRA / "docker-compose.yml").read_text(encoding="utf-8"))


def test_mysql_root_password_has_no_default():
    """The stack used to ship `MYSQL_ROOT_PASSWORD: password` -- one of the
    first credentials any scanner tries."""

    value = _COMPOSE["services"]["mysql"]["environment"]["MYSQL_ROOT_PASSWORD"]
    # ${VAR:?message} = required, no fallback value (the old `:-default`
    # form would happily start with a known password again)
    assert value.startswith("${MYSQL_ROOT_PASSWORD:?")
    assert ":-" not in value


def test_mysql_and_elasticsearch_are_only_reachable_from_localhost():
    """'listen on every network interface' -> the metadata DB and the search
    index carrying the same data stay on the loopback interface."""

    assert _COMPOSE["services"]["mysql"]["ports"] == ["127.0.0.1:3306:3306"]
    assert set(_COMPOSE["services"]["elasticsearch"]["ports"]) == {
        "127.0.0.1:9200:9200",
        "127.0.0.1:9300:9300",
    }


def test_self_signup_defaults_to_off_everywhere_it_is_configured():
    """Both the one-shot migration and the server configure it -- either one
    defaulting to true would let anyone who can reach 8585 create accounts."""

    configured = [
        svc["environment"]["AUTHENTICATION_ENABLE_SELF_SIGNUP"]
        for svc in _COMPOSE["services"].values()
        if isinstance(svc.get("environment"), dict)
        and "AUTHENTICATION_ENABLE_SELF_SIGNUP" in svc["environment"]
    ]
    assert configured, "compose no longer sets AUTHENTICATION_ENABLE_SELF_SIGNUP at all"
    assert configured == ["${AUTHENTICATION_ENABLE_SELF_SIGNUP:-false}"] * len(configured)


def test_env_example_exists_and_is_not_committed_with_the_secrets():
    env_example = (_INFRA / ".env.example").read_text(encoding="utf-8")
    assert "MYSQL_ROOT_PASSWORD=" in env_example
    assert "AUTHENTICATION_ENABLE_SELF_SIGNUP=false" in env_example
    assert ".env" in (_INFRA / ".gitignore").read_text(encoding="utf-8").split()


def test_readme_tells_the_operator_to_change_the_bootstrap_admin_password():
    readme = (_INFRA / "README.md").read_text(encoding="utf-8")
    assert "change this" in readme.lower() or "change the" in readme.lower()
    assert "ingestion-bot" in readme
    assert "127.0.0.1" in readme
