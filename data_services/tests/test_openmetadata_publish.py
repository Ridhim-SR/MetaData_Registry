import json
from unittest.mock import MagicMock

import pytest
import requests
from metadata.ingestion.ometa.client import APIError

from src.schema_registry.curate import CLASSIFICATION_LEVELS
from src.schema_registry.openmetadata.publish import _create_or_update, _get_by_name, _unwrap, publish_table
from src.schema_registry.registry import lookups
from src.schema_registry.pipeline import run
from src.storage.local import LocalObjectStorage


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """The retry tests below deliberately trigger tenacity's backoff --
    skip the actual wait so the suite doesn't slow down."""
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


def _ingested_storage(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    run(
        department="pwd",
        dataset="vishwakarma",
        table_name="TBD_confirm_with_pwd",
        source_file=_write_ddl(tmp_path),
        storage=storage,
        source_format="postgres_ddl",
    )
    return storage


def _write_ddl(tmp_path) -> str:
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text(
        "sno integer NOT NULL, firm_name character varying(100), total_cost double precision DEFAULT 0"
    )
    return str(ddl_file)


def _fake_client():
    """A minimal stand-in for OpenMetadata's SDK client: get_by_name always
    reports "not found" (nothing exists yet), create_or_update just echoes
    back something with a name/fullyQualifiedName so _fqn() can chain calls
    the same way the real SDK's response objects do."""

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
        fqn = f"{parent}.{name}" if parent else str(name)
        entity.fullyQualifiedName = fqn
        entity.name = name
        # a real id, so the follow-up JSON-Patch paths read like
        # /tables/pwd.vishwakarma.t1 instead of a MagicMock repr
        entity.id = fqn
        # the real server echoes a table's columns back -- _replace_column_tags()
        # maps names to indexes against this list
        entity.columns = getattr(request, "columns", None)
        return entity

    client.create_or_update.side_effect = _create_or_update
    return client


def _last_patch_body(client, path_prefix: str) -> dict:
    """{json-pointer path: value} of the most recent JSON-Patch sent to an
    entity under `path_prefix` (e.g. "/databases/", "/tables/")."""

    call = next(c for c in reversed(client.client.patch.call_args_list) if c.kwargs["path"].startswith(path_prefix))
    return {op["path"]: op["value"] for op in json.loads(call.kwargs["data"])}


def test_publish_table_builds_full_entity_chain(tmp_path):
    storage = _ingested_storage(tmp_path)
    client = _fake_client()

    result = publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    assert result["table_id"] == "pwd.vishwakarma.tbd_confirm_with_pwd"
    assert result["column_count"] == 3
    assert result["fully_qualified_name"] == "pwd.vishwakarma.public.TBD_confirm_with_pwd"

    created = [call.args[0] for call in client.create_or_update.call_args_list]

    # FieldTag (with firm_name/total_cost's auto-tags) and the MDSF
    # classification (with all 7 level tags) are ensured before the table
    # request, so every tagFQN the columns reference resolves against a
    # real tag.
    classification_requests = [r for r in created if type(r).__name__ == "CreateClassificationRequest"]
    assert [_unwrap(r.name) for r in classification_requests] == ["FieldTag", "MDSF"]
    tag_requests = [r for r in created if type(r).__name__ == "CreateTagRequest"]
    assert [_unwrap(r.name) for r in tag_requests] == ["Firm/Contractor-Identifier", "Financial", *CLASSIFICATION_LEVELS]

    service_request = next(r for r in created if type(r).__name__ == "CreateDatabaseServiceRequest")
    database_request = next(r for r in created if type(r).__name__ == "CreateDatabaseRequest")
    schema_request = next(r for r in created if type(r).__name__ == "CreateDatabaseSchemaRequest")
    table_request = next(r for r in created if type(r).__name__ == "CreateTableRequest")

    assert _unwrap(service_request.name) == "pwd"  # service defaults to department_id
    assert _unwrap(database_request.name) == "vishwakarma"  # database == dataset slug
    assert _unwrap(schema_request.name) == "public"  # schema_name from tables.csv
    assert _unwrap(table_request.name) == "TBD_confirm_with_pwd"
    columns = {_unwrap(c.name): c for c in table_request.columns}
    assert list(columns) == ["sno", "firm_name", "total_cost"]
    assert [t.tagFQN.root for t in columns["sno"].tags] == ["MDSF.Internal"]
    assert [t.tagFQN.root for t in columns["firm_name"].tags] == [
        "FieldTag.Firm/Contractor-Identifier",
        "MDSF.PII",
    ]
    assert [t.tagFQN.root for t in columns["total_cost"].tags] == ["FieldTag.Financial", "MDSF.Financial"]


def test_publish_table_pushes_classification_and_glossary_term(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text("beneficiary_email character varying(100), remarks text")
    metadata_file = tmp_path / "meta.csv"
    metadata_file.write_text(
        "name,business_description,tag,glossary_term,active,classification\n"
        "remarks,General notes,,Field Note,true,Confidential\n"
    )
    run(
        department="pwd",
        dataset="vishwakarma",
        table_name="t1",
        source_file=str(ddl_file),
        storage=storage,
        source_format="postgres_ddl",
        business_metadata_file=str(metadata_file),
    )

    client = _fake_client()
    publish_table(client, storage, "pwd.vishwakarma.t1")

    table_request = client.create_or_update.call_args_list[-1].args[0]
    columns = {_unwrap(c.name): c for c in table_request.columns}

    # beneficiary_email got no business metadata -- auto-classified as
    # PII purely from its name (curate.py's AUTO_CLASSIFICATION_RULES).
    assert [t.tagFQN.root for t in columns["beneficiary_email"].tags] == ["MDSF.PII"]

    # remarks' classification/glossary_term came from the business metadata
    # file, not auto-detection.
    assert sorted(t.tagFQN.root for t in columns["remarks"].tags) == [
        "BusinessGlossary.Field Note",
        "MDSF.Confidential",
    ]


def test_publish_table_pushes_dataset_category_and_description_to_database(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    run(
        department="pwd",
        dataset="vishwakarma",
        table_name="t1",
        source_file=_write_ddl(tmp_path),
        storage=storage,
        source_format="postgres_ddl",
        category="CAT-3",
        dataset_description="PWD's master works dataset.",
    )

    client = _fake_client()
    publish_table(client, storage, "pwd.vishwakarma.t1")

    database_request = next(
        call.args[0] for call in client.create_or_update.call_args_list if _unwrap(call.args[0].name) == "vishwakarma"
    )
    assert database_request.description.root == "PWD's master works dataset."
    assert [t.tagFQN.root for t in database_request.tags] == ["DataSensitivity.CAT-3"]


def test_publish_table_clears_stale_category_and_description_on_republish(tmp_path):
    """create_or_update()'s PUT merges tags/extension instead of replacing
    them (same quirk as column tags) -- without _replace_entity_fields(), a
    category/custom-property cleared in datasets.csv would stay stuck from
    a previous run. Verified live against a real server; this locks in the
    fix against the fake client's call history."""

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    run(
        department="pwd",
        dataset="vishwakarma",
        table_name="t1",
        source_file=_write_ddl(tmp_path),
        storage=storage,
        source_format="postgres_ddl",
        category="CAT-3",
        owner="Someone",
    )
    client = _fake_client()
    publish_table(client, storage, "pwd.vishwakarma.t1")

    patch_body = _last_patch_body(client, "/databases/")
    assert patch_body["/tags"] == [
        {
            "tagFQN": "DataSensitivity.CAT-3",
            "source": "Classification",
            "labelType": "Automated",
            "state": "Confirmed",
        }
    ]
    assert patch_body["/extension"] == {
        "apiAvailable": "",
        "datasetOwner": "Someone",
        "frequency": "",
        "timeline": "",
    }

    # now clear both -- upsert_dataset() itself carries forward unmentioned
    # fields (see test_lookups.py), so deliberately clearing one means
    # editing the lookup row directly, same as the real "known limitation"
    # documented on upsert_dataset(). The next publish's replace-patch must
    # carry the cleared (empty) values, not silently omit them (which would
    # mean "leave the stale ones alone").
    rows = storage.read_csv(lookups.DATASETS_PATH)
    for row in rows:
        if row["dataset_id"] == "pwd.vishwakarma":
            row["category"] = ""
            row["owner"] = ""
    storage.write_csv(lookups.DATASETS_PATH, rows)
    publish_table(client, storage, "pwd.vishwakarma.t1")

    patch_body = _last_patch_body(client, "/databases/")
    assert patch_body["/tags"] == []
    assert patch_body["/extension"] == {"apiAvailable": "", "datasetOwner": "", "frequency": "", "timeline": ""}

    # each column carries its curated classification as an MDSF tag (plus
    # its auto-tag where AUTO_TAG_RULES matched)
    table_request = client.create_or_update.call_args_list[-1].args[0]
    assert [
        [str(_unwrap(t.tagFQN)) for t in (c.tags or [])]
        for c in table_request.columns
    ] == [
        ["MDSF.Internal"],
        ["FieldTag.Firm/Contractor-Identifier", "MDSF.PII"],
        ["FieldTag.Financial", "MDSF.Financial"],
    ]


def test_publish_table_patches_column_tags_right_after_the_put(tmp_path):
    """Same merge quirk as the Database above, one level down: the table PUT
    carries every column's tags, but OpenMetadata merges each column's tag
    array with the one already stored -- verified live, 4 `farmers` columns
    kept a stale FieldTag.Internal after their dictionary `tag` was blanked.
    So publish_table() must patch the tags again, per column, right after the
    PUT."""

    storage = _ingested_storage(tmp_path)
    client = _fake_client()
    publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    table_patches = [
        call for call in client.client.patch.call_args_list if call.kwargs["path"].startswith("/tables/")
    ]
    assert len(table_patches) == 1
    assert table_patches[0].kwargs["path"] == "/tables/pwd.vishwakarma.public.TBD_confirm_with_pwd"

    ops = json.loads(table_patches[0].kwargs["data"])
    assert [(op["op"], op["path"]) for op in ops] == [
        ("add", "/columns/0/tags"),
        ("add", "/columns/1/tags"),
        ("add", "/columns/2/tags"),
    ]
    assert [[tag["tagFQN"] for tag in op["value"]] for op in ops] == [
        ["MDSF.Internal"],
        ["FieldTag.Firm/Contractor-Identifier", "MDSF.PII"],
        ["FieldTag.Financial", "MDSF.Financial"],
    ]
    # the labels are the same TagLabel shape OpenMetadata stores, so the patch
    # overwrites rather than appends
    assert ops[0]["value"][0] == {
        "tagFQN": "MDSF.Internal",
        "source": "Classification",
        "labelType": "Automated",
        "state": "Confirmed",
    }


def test_publish_table_patches_an_empty_tag_list_to_clear_a_stale_label(tmp_path):
    """The clearing case is the whole point of the patch: a column whose tags
    were all removed since the last publish must send `[]`, not be omitted
    (which would mean "leave the stale labels alone")."""

    storage = _ingested_storage(tmp_path)
    curated_path = storage.list("department/pwd/vishwakarma/tbd_confirm_with_pwd/curated/schemas/")[-1]
    rows = storage.read_csv(curated_path)
    rows[0]["classification"] = ""
    rows[0]["tag"] = ""
    storage.write_csv(curated_path, rows)

    client = _fake_client()
    publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    table_patches = [
        call for call in client.client.patch.call_args_list if call.kwargs["path"].startswith("/tables/")
    ]
    ops = json.loads(table_patches[-1].kwargs["data"])
    assert ops[0] == {"op": "add", "path": "/columns/0/tags", "value": []}
    # the other columns still carry their curated labels
    assert [[tag["tagFQN"] for tag in op["value"]] for op in ops[1:]] == [
        ["FieldTag.Firm/Contractor-Identifier", "MDSF.PII"],
        ["FieldTag.Financial", "MDSF.Financial"],
    ]


def test_publish_table_reuses_existing_entities_instead_of_recreating(tmp_path):
    storage = _ingested_storage(tmp_path)
    client = _fake_client()
    existing_service = MagicMock(fullyQualifiedName="pwd", name="pwd")
    client.get_by_name.side_effect = None
    client.get_by_name.return_value = existing_service

    publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    # service and schema found an existing entity and were reused; database
    # and table are always create-or-update (dataset_description/category
    # on the database, columns on the table, can change on a later run)
    assert client.create_or_update.call_count == 2


def test_ensure_classification_is_idempotent(tmp_path):
    """Re-publishing must not recreate the MDSF classification/tags --
    an existing classification and its tags are left alone."""

    storage = _ingested_storage(tmp_path)
    client = _fake_client()

    publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")
    first_count = client.create_or_update.call_count

    # second publish: classification + tags all resolve as existing
    client.reset_mock()
    client.get_by_name.side_effect = None
    client.get_by_name.return_value = MagicMock(fullyQualifiedName="MDSF", name="MDSF")

    publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    # only the database (always create-or-update for dataset-level fields)
    # and the table -- no classification/tag re-creation
    created_types = [type(call.args[0]).__name__ for call in client.create_or_update.call_args_list]
    assert "CreateClassificationRequest" not in created_types
    assert "CreateTagRequest" not in created_types
    assert created_types == ["CreateDatabaseRequest", "CreateTableRequest"]
    assert first_count > 1  # first run did create them


def test_all_cat_levels_have_a_published_description():
    """Item 14: every category the pipeline accepts must carry its MDSF
    meaning into OpenMetadata -- CAT-4 was the missing one, and an
    undocumented level is indistinguishable from a typo'd one in the UI."""

    from src.schema_registry.curate import CATEGORY_LEVELS
    from src.schema_registry.openmetadata.publish import _CAT_DESCRIPTIONS

    assert set(_CAT_DESCRIPTIONS) == set(CATEGORY_LEVELS)
    assert "No Sharing" in _CAT_DESCRIPTIONS["CAT-4"]


def test_publish_rejects_an_unknown_category_written_before_validation(tmp_path):
    """publish_table() can run on its own (republish), against a datasets.csv
    row that predates the validation in run()."""

    storage = _ingested_storage(tmp_path)
    rows = storage.read_csv(lookups.DATASETS_PATH)
    for row in rows:
        row["category"] = "cat3"
    storage.write_csv(lookups.DATASETS_PATH, rows)

    # refused before any OpenMetadata call: the dataset-vs-column check runs
    # first, and _ensure_sensitivity_tag() would refuse it again later
    with pytest.raises(ValueError, match="isn't a CAT-<n> value"):
        publish_table(_fake_client(), storage, "pwd.vishwakarma.tbd_confirm_with_pwd")


def test_publish_rejects_an_unknown_tag_in_a_tampered_snapshot(tmp_path):
    """curate_schema() already rejects unknown tags -- this is the same
    check on the publish side, for snapshots curated before it existed."""

    storage = _ingested_storage(tmp_path)
    curated_path = storage.list("department/pwd/vishwakarma/tbd_confirm_with_pwd/curated/schemas/")[-1]
    rows = storage.read_csv(curated_path)
    rows[0]["tag"] = "MadeUpTag"
    storage.write_csv(curated_path, rows)

    with pytest.raises(ValueError, match="Unknown tag 'MadeUpTag'"):
        publish_table(_fake_client(), storage, "pwd.vishwakarma.tbd_confirm_with_pwd")


def test_publish_rejects_a_glossary_term_containing_a_dot(tmp_path):
    """A '.' in a glossary term would silently produce an FQN OpenMetadata
    splits into a different term than the one we just created."""

    storage = _ingested_storage(tmp_path)
    curated_path = storage.list("department/pwd/vishwakarma/tbd_confirm_with_pwd/curated/schemas/")[-1]
    rows = storage.read_csv(curated_path)
    rows[0]["glossary_term"] = "Parent.Child"
    storage.write_csv(curated_path, rows)

    with pytest.raises(ValueError, match="contains '\\.'"):
        publish_table(_fake_client(), storage, "pwd.vishwakarma.tbd_confirm_with_pwd")


def test_publish_table_unknown_table_id_raises(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    client = _fake_client()

    with pytest.raises(ValueError, match="Unknown table_id"):
        publish_table(client, storage, "pwd.vishwakarma.does_not_exist")


def test_publish_table_no_curated_snapshot_raises(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    lookups.upsert_dataset(storage, "pwd.vishwakarma", "pwd", "vishwakarma")
    lookups.upsert_table(storage, "pwd.vishwakarma.t1", "pwd.vishwakarma", "t1", "public")
    client = _fake_client()

    with pytest.raises(FileNotFoundError, match="No curated schema"):
        publish_table(client, storage, "pwd.vishwakarma.t1")


def test_publish_table_unmapped_data_type_raises(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    run(
        department="pwd",
        dataset="vishwakarma",
        table_name="t1",
        source_file=_write_ddl(tmp_path),
        storage=storage,
        source_format="postgres_ddl",
    )
    # tamper with the curated snapshot to simulate a type this pipeline
    # never validated (should never happen via curate.py, but publish
    # should fail loudly rather than silently mis-typing a column in OM)
    curated_path = storage.list("department/pwd/vishwakarma/t1/curated/schemas/")[-1]
    rows = storage.read_csv(curated_path)
    rows[0]["data_type"] = "money"
    storage.write_csv(curated_path, rows)

    client = _fake_client()
    with pytest.raises(ValueError, match="No OpenMetadata mapping"):
        publish_table(client, storage, "pwd.vishwakarma.t1")


def test_publish_table_picks_latest_curated_snapshot(tmp_path):
    storage = _ingested_storage(tmp_path)
    # re-run with a different (shrunk) column set -- should produce a newer
    # snapshot; allow_column_removal=True since this deliberately drops
    # columns from the previous run (see test_pipeline.py for the guard
    # that rejects this without it).
    ddl_file = tmp_path / "raw2.txt"
    ddl_file.write_text("only_col integer NOT NULL")
    run(
        department="pwd",
        dataset="vishwakarma",
        table_name="TBD_confirm_with_pwd",
        source_file=str(ddl_file),
        storage=storage,
        source_format="postgres_ddl",
        allow_column_removal=True,
    )

    client = _fake_client()
    result = publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    assert result["column_count"] == 1
    table_request = client.create_or_update.call_args_list[-1].args[0]
    assert [_unwrap(c.name) for c in table_request.columns] == ["only_col"]


def _api_error(status_code: int) -> APIError:
    error = APIError({"code": status_code, "message": "boom"})
    error._http_error = MagicMock(response=MagicMock(status_code=status_code))
    return error


def test_create_or_update_retries_on_connection_error_then_succeeds():
    client = MagicMock()
    client.create_or_update.side_effect = [
        requests.exceptions.ConnectionError("server unreachable"),
        requests.exceptions.ConnectionError("still unreachable"),
        "created",
    ]

    result = _create_or_update(client, MagicMock())

    assert result == "created"
    assert client.create_or_update.call_count == 3


def test_create_or_update_retries_on_5xx_then_succeeds():
    client = MagicMock()
    client.create_or_update.side_effect = [_api_error(503), "created"]

    result = _create_or_update(client, MagicMock())

    assert result == "created"
    assert client.create_or_update.call_count == 2


def test_create_or_update_does_not_retry_on_4xx():
    """A 4xx means the request itself is wrong (e.g. bad payload) --
    retrying it just fails the same way every time, slower."""

    client = MagicMock()
    client.create_or_update.side_effect = _api_error(400)

    with pytest.raises(APIError):
        _create_or_update(client, MagicMock())

    assert client.create_or_update.call_count == 1


def test_create_or_update_gives_up_after_max_attempts():
    client = MagicMock()
    client.create_or_update.side_effect = requests.exceptions.ConnectionError("down")

    with pytest.raises(requests.exceptions.ConnectionError):
        _create_or_update(client, MagicMock())

    assert client.create_or_update.call_count == 4  # stop_after_attempt(4)


def test_get_by_name_retries_on_connection_error():
    client = MagicMock()
    client.get_by_name.side_effect = [requests.exceptions.ConnectionError("blip"), "found"]

    result = _get_by_name(client, MagicMock(), "some.fqn")

    assert result == "found"
    assert client.get_by_name.call_count == 2


def _run_with(tmp_path, storage, ddl: str, metadata_csv: str | None = None, **kwargs):
    ddl_file = tmp_path / "raw.txt"
    ddl_file.write_text(ddl)
    metadata_path = None
    if metadata_csv is not None:
        metadata_path = tmp_path / "meta.csv"
        metadata_path.write_text(metadata_csv)
    return run(
        department="pwd",
        dataset="vishwakarma",
        table_name="t1",
        source_file=str(ddl_file),
        storage=storage,
        source_format="postgres_ddl",
        business_metadata_file=str(metadata_path) if metadata_path else None,
        **kwargs,
    )


def test_publish_table_replaces_column_tags_instead_of_merging(tmp_path):
    """OpenMetadata's PUT merges column tags, so a column downgraded from
    PII to Internal would show both labels. publish_table() must follow the
    PUT with a patch setting each column's tags to exactly this run's list."""

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    _run_with(tmp_path, storage, "beneficiary_email character varying(100), remarks text", category="CAT-3")
    client = _fake_client()
    publish_table(client, storage, "pwd.vishwakarma.t1")
    assert _last_patch_body(client, "/tables/")["/columns/0/tags"][0]["tagFQN"] == "MDSF.PII"

    _run_with(
        tmp_path, storage, "beneficiary_email character varying(100), remarks text",
        metadata_csv="name,classification\nbeneficiary_email,Internal\n",
    )
    publish_table(client, storage, "pwd.vishwakarma.t1")

    call = next(c for c in reversed(client.client.patch.call_args_list) if c.kwargs["path"].startswith("/tables/"))
    ops = json.loads(call.kwargs["data"])
    assert {op["op"] for op in ops} == {"add"}
    body = {op["path"]: op["value"] for op in ops}
    assert [t["tagFQN"] for t in body["/columns/0/tags"]] == ["MDSF.Internal"]
    # every column carries at least its classification level, and column 0 no
    # longer shows the PII label from the first publish -- that's the merge
    # quirk this patch exists for
    assert [t["tagFQN"] for t in body["/columns/1/tags"]] == ["MDSF.Internal"]


def test_publish_table_matches_column_tags_by_name_not_request_order(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    _run_with(tmp_path, storage, "beneficiary_email character varying(100), remarks text", category="CAT-3")
    client = _fake_client()
    fake_create = client.create_or_update.side_effect

    def _server_reorders_columns(request):
        entity = fake_create(request)
        if entity.columns:
            entity.columns = list(reversed(entity.columns))
        return entity

    client.create_or_update.side_effect = _server_reorders_columns
    publish_table(client, storage, "pwd.vishwakarma.t1")

    body = _last_patch_body(client, "/tables/")
    assert [t["tagFQN"] for t in body["/columns/0/tags"]] == ["MDSF.Internal"]  # remarks, now first on the server
    assert body["/columns/1/tags"][0]["tagFQN"] == "MDSF.PII"


def test_publish_refuses_dataset_category_below_its_columns(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    _run_with(tmp_path, storage, "beneficiary_email character varying(100), remarks text", category="CAT-1")
    client = _fake_client()

    with pytest.raises(ValueError, match=r"category is CAT-1 but column\(s\) beneficiary_email are PII"):
        publish_table(client, storage, "pwd.vishwakarma.t1")

    # refused before touching OpenMetadata at all
    assert client.create_or_update.call_count == 0
    assert client.client.patch.call_count == 0


def test_publish_allows_category_below_columns_with_explicit_override(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    _run_with(tmp_path, storage, "beneficiary_email character varying(100)", category="CAT-1")

    result = publish_table(_fake_client(), storage, "pwd.vishwakarma.t1", allow_category_below_columns=True)

    assert result["column_count"] == 1


def test_publish_allows_category_equal_or_above_columns(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    _run_with(tmp_path, storage, "beneficiary_email character varying(100)", category="CAT-3")

    assert publish_table(_fake_client(), storage, "pwd.vishwakarma.t1")["column_count"] == 1


def test_publish_with_blank_category_and_sensitive_columns_only_warns(tmp_path, monkeypatch):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    _run_with(tmp_path, storage, "beneficiary_email character varying(100)")
    warnings = []
    # src.utils.logger sets propagate=False, so caplog never sees these
    monkeypatch.setattr("src.schema_registry.openmetadata.publish.logger.warning", warnings.append)

    publish_table(_fake_client(), storage, "pwd.vishwakarma.t1")

    assert any("has no category yet" in w and "at least CAT-3" in w for w in warnings)


def test_publish_refuses_non_cat_dataset_category_when_columns_are_classified(tmp_path):
    """pipeline.run() rejects a non-CAT `category` at ingest, so it never
    lands in _lookups/datasets.csv -- and publish_table() keeps the same
    check for the paths that write that lookup without going through run()
    (republish, a hand-edited CSV)."""

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")

    with pytest.raises(ValueError, match="unknown category 'Open'"):
        _run_with(tmp_path, storage, "beneficiary_email character varying(100)", category="Open")

    _run_with(tmp_path, storage, "beneficiary_email character varying(100)")
    lookups.set_dataset_fields(storage, "pwd.vishwakarma", "pwd", "vishwakarma", {"category": "Open"})
    with pytest.raises(ValueError, match="isn't a CAT-<n> value"):
        publish_table(_fake_client(), storage, "pwd.vishwakarma.t1")


def test_run_passes_category_override_through_to_publish(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    with pytest.raises(ValueError, match="Under MDSF the highest category applies"):
        _run_with(
            tmp_path, storage, "beneficiary_email character varying(100)",
            category="CAT-1", openmetadata_client=_fake_client(),
        )

    result = _run_with(
        tmp_path, storage, "beneficiary_email character varying(100)",
        openmetadata_client=_fake_client(), allow_category_below_columns=True,
    )
    assert result["openmetadata"]["column_count"] == 1
