"""Item 16: a dataset's free-text `owner` lands in OpenMetadata's built-in
Owners field on the Database, so ownership-driven access rules, "my assets"
filters and ownership reports actually apply -- not just the custom
property."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from metadata.generated.schema.entity.teams.team import Team
from metadata.generated.schema.entity.teams.user import User

from src.schema_registry.openmetadata.publish import _resolve_owner, _unwrap, publish_table
from src.schema_registry.pipeline import run
from src.schema_registry.registry import lookups
from src.storage.local import LocalObjectStorage


def _fake_client():
    client = MagicMock()
    client.get_by_name.side_effect = Exception("Entity not found")

    def _create_or_update(request):
        entity = MagicMock()
        name = _unwrap(getattr(request, "name", None))
        parent = _unwrap(
            getattr(request, "service", None)
            or getattr(request, "database", None)
            or getattr(request, "databaseSchema", None)
            or getattr(request, "classification", None)
            or getattr(request, "glossary", None)
        )
        entity.fullyQualifiedName = f"{parent}.{name}" if parent else str(name)
        entity.name = name
        entity.id = str(uuid.uuid4())
        return entity

    client.create_or_update.side_effect = _create_or_update
    return client


def _client_with_users(users: dict[str, str], teams: dict[str, str] | None = None):
    """get_by_name returns a real-ish User/Team for the given FQNs, "not
    found" for everything else.

    Note: plain SimpleNamespace, not MagicMock -- `MagicMock(name="x")` sets
    the mock's *repr name*, not a `.name` attribute."""

    teams = teams or {}
    client = _fake_client()

    def _get(entity, fqn):
        if entity is Team and fqn in teams:
            return SimpleNamespace(
                id=uuid.uuid4(), name=fqn, fullyQualifiedName=fqn, displayName=teams[fqn]
            )
        if entity is User and fqn in users:
            return SimpleNamespace(
                id=uuid.uuid4(), name=fqn, fullyQualifiedName=fqn, displayName=users[fqn]
            )
        raise Exception("Entity not found")

    client.get_by_name.side_effect = _get
    return client


def _storage_with_owner(tmp_path, owner: str) -> LocalObjectStorage:
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    source = tmp_path / "raw.txt"
    source.write_text("col_a integer NOT NULL")
    run(
        department="pwd", dataset="vishwakarma", table_name="t1",
        source_file=str(source), storage=storage, source_format="postgres_ddl",
        owner=owner,
    )
    return storage


def _database_patch_body(client) -> dict:
    """path -> value of the last JSON-Patch sent to a Database. publish_table
    patches the table's column tags too, so call_args alone no longer says
    which entity the patch was for."""

    calls = [c for c in client.client.patch.call_args_list if c.kwargs["path"].startswith("/databases/")]
    assert calls, "publish_table() sent no Database JSON-Patch"
    return {op["path"]: op["value"] for op in json.loads(calls[-1].kwargs["data"])}


def test_resolve_owner_finds_a_user_by_name(tmp_path):
    client = _client_with_users({"john.doe": "John Doe"})

    ref = _resolve_owner(client, "john.doe")

    assert ref is not None
    assert _unwrap(ref.name) == "john.doe"
    assert _unwrap(ref.type) == "user"


def test_resolve_owner_finds_a_user_by_email_local_part(tmp_path):
    """`owner` is typed as an email in datasets.csv for some datasets --
    OM's FQN for a user is their username, so try that half too."""

    client = _client_with_users({"john.doe": "John Doe"})

    ref = _resolve_owner(client, "john.doe@example.gov.in")

    assert ref is not None
    assert _unwrap(ref.name) == "john.doe"


def test_resolve_owner_falls_back_to_a_team():
    client = _client_with_users({}, teams={"pwd-team": "PWD Team"})

    ref = _resolve_owner(client, "pwd-team")

    assert ref is not None
    assert _unwrap(ref.type) == "team"


def test_resolve_owner_is_none_for_an_unknown_owner():
    """A warning, not a failure: the raw text still reaches the datasetOwner
    custom property and the next republish picks the owner up once created."""

    client = _fake_client()

    assert _resolve_owner(client, "not-in-openmetadata-yet") is None
    assert _resolve_owner(client, "") is None


def test_publish_sends_owners_on_the_database(tmp_path):
    storage = _storage_with_owner(tmp_path, "john.doe")
    client = _client_with_users({"john.doe": "John Doe"})

    publish_table(client, storage, "pwd.vishwakarma.t1")

    database_request = next(
        call.args[0]
        for call in client.create_or_update.call_args_list
        if type(call.args[0]).__name__ == "CreateDatabaseRequest"
    )
    owners = _unwrap(database_request.owners)
    assert [_unwrap(o.name) for o in owners] == ["john.doe"]

    # ...and the JSON-Patch replace carries it too, so clearing the owner in
    # datasets.csv actually clears it in OM (same quirk as tags/extension)
    patch_body = _database_patch_body(client)
    assert len(patch_body["/owners"]) == 1
    assert "john.doe" in json.dumps(patch_body["/owners"])


def test_publish_sends_an_empty_owners_list_when_nothing_resolves(tmp_path):
    """`replace` on /owners needs the path to exist in OM's response, so an
    unresolved owner must still be sent -- as []."""

    storage = _storage_with_owner(tmp_path, "not-in-openmetadata-yet")
    client = _fake_client()

    publish_table(client, storage, "pwd.vishwakarma.t1")

    database_request = next(
        call.args[0]
        for call in client.create_or_update.call_args_list
        if type(call.args[0]).__name__ == "CreateDatabaseRequest"
    )
    assert _unwrap(database_request.owners) == []

    patch_body = _database_patch_body(client)
    assert patch_body["/owners"] == []
