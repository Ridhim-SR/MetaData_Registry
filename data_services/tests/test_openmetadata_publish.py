import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from metadata.ingestion.ometa.client import APIError

from src.schema_registry.curate import CLASSIFICATION_LEVELS
from src.schema_registry.openmetadata.publish import (
    _create_or_update,
    _extra_metadata_json,
    _get_by_name,
    _to_column,
    _unwrap,
    publish_table,
)
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
        # curate_schema() no longer tags from the column name, so the two
        # tags every publish test below asserts on have to arrive the way a
        # department's do: through the metadata file.
        business_metadata_file=_write_tag_csv(tmp_path),
    )
    return storage


def _write_tag_csv(tmp_path) -> str:
    path = tmp_path / "tags.csv"
    path.write_text(
        "name,tag\n"
        "firm_name,Firm/Contractor-Identifier\n"
        "total_cost,Financial\n",
        encoding="utf-8",
    )
    return str(path)


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

    # FieldTag (with the tags the metadata file supplies for firm_name and
    # total_cost) and the MDSF classification (with all 7 level tags) are
    # ensured before the table request, so every tagFQN the columns
    # reference resolves against a real tag.
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
    # The PUT carries only the non-MDSF tags: OpenMetadata merges the
    # submitted list with the stored one, and two labels of the
    # mutuallyExclusive MDSF classification in that merge make the server
    # answer HTTP 400 -- which deadlocked --reclassify (the old MDSF.PII
    # could never be swapped for MDSF.Public). The MDSF labels travel in
    # the JSON-Patch that follows, which replaces the stored list exactly.
    assert [t.tagFQN.root for t in columns["sno"].tags] == []
    assert [t.tagFQN.root for t in columns["firm_name"].tags] == [
        "FieldTag.Firm/Contractor-Identifier",
    ]
    assert [t.tagFQN.root for t in columns["total_cost"].tags] == ["FieldTag.Financial"]
    patch_body = _last_patch_body(client, "/tables/")
    assert [[t["tagFQN"] for t in patch_body[f"/columns/{i}/tags"]] for i in range(3)] == [
        [],  # sno: no rule recognises it, so no classification
        ["FieldTag.Firm/Contractor-Identifier", "MDSF.PII"],
        ["FieldTag.Financial", "MDSF.Financial"],
    ]


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
    patch_body = _last_patch_body(client, "/tables/")

    # beneficiary_email got no business metadata -- auto-classified as
    # PII purely from its name (curate.py's AUTO_CLASSIFICATION_RULES).
    # The label rides in the post-PUT patch, not the PUT itself (see the
    # mutuallyExclusive note in test_publish_table_builds_full_entity_chain).
    assert [t.tagFQN.root for t in columns["beneficiary_email"].tags] == []
    index = {_unwrap(c.name): i for i, c in enumerate(table_request.columns)}
    assert [t["tagFQN"] for t in patch_body[f"/columns/{index['beneficiary_email']}/tags"]] == ["MDSF.PII"]

    # remarks' classification/glossary_term came from the business metadata
    # file, not auto-detection. The glossary term is not part of the MDSF
    # exclusivity problem, so the PUT carries it; the classification is
    # added by the patch.
    assert [t.tagFQN.root for t in columns["remarks"].tags] == ["BusinessGlossary.Field Note"]
    assert sorted(t["tagFQN"] for t in patch_body[f"/columns/{index['remarks']}/tags"]) == [
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
        business_metadata_file=_write_tag_csv(tmp_path),
        category="CAT-3",
        owner="Someone",
        steward="A Steward",
        dataset_description="PWD's master works dataset.",
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
        "datasetSteward": "A Steward",
        "frequency": "",
        "timeline": "",
        "datasetType": "",
        "schemaSource": "",
    }
    assert patch_body["/description"] == "PWD's master works dataset."

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
            row["steward"] = ""
            row["dataset_description"] = ""
    storage.write_csv(lookups.DATASETS_PATH, rows)
    publish_table(client, storage, "pwd.vishwakarma.t1")

    patch_body = _last_patch_body(client, "/databases/")
    assert patch_body["/tags"] == []
    assert patch_body["/extension"] == {
        "apiAvailable": "",
        "datasetOwner": "",
        "datasetSteward": "",
        "frequency": "",
        "timeline": "",
        "datasetType": "",
        "schemaSource": "",
    }
    assert patch_body["/description"] == ""

    # the PUT carries only the non-MDSF tags; the curated MDSF
    # classifications (plus the tags submitted in the metadata file) land in
    # the JSON-Patch that follows the PUT
    table_request = client.create_or_update.call_args_list[-1].args[0]
    assert [
        [str(_unwrap(t.tagFQN)) for t in (c.tags or [])]
        for c in table_request.columns
    ] == [
        [],
        ["FieldTag.Firm/Contractor-Identifier"],
        ["FieldTag.Financial"],
    ]
    assert [[t["tagFQN"] for t in _last_patch_body(client, "/tables/")[f"/columns/{i}/tags"]] for i in range(3)] == [
        [],  # sno: no rule recognises it, so no classification
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

    # publish_table() now sends a second /tables/ patch for the extraMetadata
    # extension property, so select on the column-tag ops this test is about.
    table_patches = [
        call for call in client.client.patch.call_args_list
        if call.kwargs["path"].startswith("/tables/") and "/columns/" in call.kwargs["data"]
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
        [],  # sno: no rule recognises it, so no classification
        ["FieldTag.Firm/Contractor-Identifier", "MDSF.PII"],
        ["FieldTag.Financial", "MDSF.Financial"],
    ]
    # the labels are the same TagLabel shape OpenMetadata stores, so the patch
    # overwrites rather than appends
    assert ops[1]["value"][-1] == {
        "tagFQN": "MDSF.PII",
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
    assert "Non-Shareable" in _CAT_DESCRIPTIONS["CAT-4"]
    # MeitY draft, 31 Aug 2026, section 5.1 -- definition, examples and the
    # access rule all travel with the tag, not just the level's name.
    for level, text in _CAT_DESCRIPTIONS.items():
        assert "Examples:" in text and "Access:" in text, level


def test_cat_definitions_file_matches_the_vocabulary_publish_writes():
    """samples/cat_definitions.txt is what ai_metadata feeds the model to
    pick a `category`; publish.py's tag descriptions are what the reader
    sees afterwards. The two must name the same four levels, or the draft
    and the published label drift apart."""

    from src.schema_registry.curate import CATEGORY_LEVELS
    from src.schema_registry.openmetadata.publish import _CAT_DESCRIPTIONS

    text = (Path(__file__).resolve().parents[1] / "samples" / "cat_definitions.txt").read_text(
        encoding="utf-8"
    )
    for level in CATEGORY_LEVELS:
        assert level in text
        assert _CAT_DESCRIPTIONS[level].split(" -- ")[0] in text


def test_ai_metadata_can_emit_every_tag_the_pipeline_accepts():
    """ai_metadata.apply_rules() writes PII / Sensitive straight into the
    metadata file, so anything it can emit has to be in curate's vocabulary
    -- otherwise the file passes review and then dies at ingest with
    "unknown tag 'Sensitive'". This is the same drift the
    test_all_cat_levels_have_a_published_description guards, on the tag axis.
    """

    from src.schema_registry import ai_metadata
    from src.schema_registry.curate import validate_tag

    for tag in ai_metadata.KNOWN_TAGS:
        assert validate_tag(tag), tag


def test_ai_metadata_category_never_drops_below_what_the_data_allows():
    """Any PII or Sensitive column floors the table at CAT-3, and a model
    suggestion can only raise it, never lower it."""

    from src.schema_registry import ai_metadata

    pii = [{"name": "farmer_name", "tag": "PII"}]
    plain = [{"name": "district_name", "tag": ""}]

    assert ai_metadata.category_floor(pii, "CAT-1") == "CAT-3"
    assert ai_metadata.category_floor(pii, "CAT-4") == "CAT-4"
    assert ai_metadata.category_floor(plain, "CAT-2") == "CAT-2"
    assert ai_metadata.category_floor(plain, None) == "CAT-1"
    assert ai_metadata.category_floor(plain, "CAT-9") == "CAT-1"


def test_apply_rules_overrides_the_model_and_covers_skipped_fields():
    from src.schema_registry import ai_metadata

    columns = [{"name": "farmer_name"}, {"name": "caste"}, {"name": "mobile_verified"},
               {"name": "status"}, {"name": "district_name"}]
    drafted = [{"name": "farmer_name", "business_description": "Name", "tag": "Financial"},
               {"name": "status", "business_description": "State", "tag": "Status/Workflow"}]

    out, changed = ai_metadata.apply_rules(columns, drafted)
    by_name = {d["name"]: d for d in out}

    assert by_name["farmer_name"]["tag"] == "PII"          # PII wins over Financial
    assert by_name["caste"]["tag"] == "Sensitive"          # skipped field still covered
    assert by_name["mobile_verified"]["tag"] == ""         # a flag, not the number
    assert by_name["district_name"]["tag"] == ""           # no rule, left to auto-tag
    assert by_name["status"]["tag"] == "Status/Workflow"   # untouched
    assert by_name["caste"]["business_description"] == ""  # no description invented
    assert any(line.startswith("farmer_name:") for line in changed)


def test_publish_rejects_an_unknown_category_written_before_validation(tmp_path):
    """publish_table() can run on its own (republish), against a datasets.csv
    row that predates the validation in run()."""

    storage = _ingested_storage(tmp_path)
    rows = storage.read_csv(lookups.DATASETS_PATH)
    for row in rows:
        row["category"] = "cat3"
    storage.write_csv(lookups.DATASETS_PATH, rows)

    # the dataset `category` is checked against the CAT vocabulary even when
    # publish runs on its own (republish, a datasets.csv row written by hand)
    with pytest.raises(ValueError, match="Unknown category 'cat3'"):
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
    # column 0 no longer shows the PII label from the first publish -- that's
    # the merge quirk this patch exists for
    assert [t["tagFQN"] for t in body["/columns/1/tags"]] == []  # remarks: no rule, so no level


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
    assert [t["tagFQN"] for t in body["/columns/0/tags"]] == []  # remarks, now first on the server
    assert body["/columns/1/tags"][0]["tagFQN"] == "MDSF.PII"


def _set_column_classification(storage, table_id: str, name: str, classification: str) -> None:
    """Write a CAT-<n> classification straight into a curated snapshot.

    curate_schema() normalises `classification` to CLASSIFICATION_LEVELS, so
    a CAT-<n> value can't survive run() -- but publish_table() also runs on
    its own (republish, a snapshot curated before that vocabulary), and that
    is the path the MDSF category floor has to hold for. Writing the value
    here is the only way to exercise it, and mirrors a pre-existing snapshot.
    """

    department_id, dataset_slug, table_slug = table_id.split(".")
    path = lookups.latest_curated_snapshot_path(storage, department_id, dataset_slug, table_slug)
    rows = storage.read_csv(path)
    next(row for row in rows if row["name"] == name)["classification"] = classification
    storage.write_csv(path, rows)


def test_publish_refuses_dataset_category_below_its_columns(tmp_path):
    """MDSF: when a dataset mixes categories the highest one applies, so a
    CAT-1 (Open) dataset carrying a CAT-3 (Restricted) column would advertise
    restricted data as open. Refused before anything is written."""

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    _run_with(tmp_path, storage, "beneficiary_email character varying(100), remarks text", category="CAT-1")
    _set_column_classification(storage, "pwd.vishwakarma.t1", "beneficiary_email", "CAT-3")
    client = _fake_client()

    with pytest.raises(ValueError, match=r"category is CAT-1 but column\(s\) beneficiary_email are CAT-3"):
        publish_table(client, storage, "pwd.vishwakarma.t1")

    # refused before touching OpenMetadata at all
    assert client.create_or_update.call_count == 0
    assert client.client.patch.call_count == 0


def test_publish_allows_category_below_columns_with_explicit_override(tmp_path):
    """`allow_category_below_columns: true` in catalog.yaml is the escape
    hatch for a dataset whose sensitive columns are removed or anonymised
    before sharing."""

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    _run_with(tmp_path, storage, "beneficiary_email character varying(100)", category="CAT-1")
    _set_column_classification(storage, "pwd.vishwakarma.t1", "beneficiary_email", "CAT-3")

    result = publish_table(_fake_client(), storage, "pwd.vishwakarma.t1", allow_category_below_columns=True)

    assert result["column_count"] == 1


def test_publish_allows_category_equal_or_above_columns(tmp_path):
    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    _run_with(tmp_path, storage, "beneficiary_email character varying(100)", category="CAT-3")
    _set_column_classification(storage, "pwd.vishwakarma.t1", "beneficiary_email", "CAT-3")

    assert publish_table(_fake_client(), storage, "pwd.vishwakarma.t1")["column_count"] == 1


def test_publish_with_blank_category_and_sensitive_columns_only_warns(tmp_path, monkeypatch):
    """A blank category means the department hasn't answered yet, so it is
    warned about rather than refused -- most datasets are still waiting."""

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    _run_with(tmp_path, storage, "beneficiary_email character varying(100)")
    _set_column_classification(storage, "pwd.vishwakarma.t1", "beneficiary_email", "CAT-3")
    warnings = []
    # src.utils.logger sets propagate=False, so caplog never sees these
    monkeypatch.setattr("src.schema_registry.openmetadata.publish.logger.warning", warnings.append)

    publish_table(_fake_client(), storage, "pwd.vishwakarma.t1")

    assert any("has no category yet" in w and "at least CAT-3" in w for w in warnings)


def test_publish_refuses_non_cat_dataset_category_when_columns_are_classified(tmp_path):
    """Columns that are CAT-tagged but a dataset category that isn't a CAT-<n>
    value: the dataset has to be pinned down before it can be compared."""

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    _run_with(tmp_path, storage, "beneficiary_email character varying(100)", category="CAT-3")
    _set_column_classification(storage, "pwd.vishwakarma.t1", "beneficiary_email", "CAT-3")
    lookups.set_dataset_fields(storage, "pwd.vishwakarma", "pwd", "vishwakarma", {"category": "Open"})

    with pytest.raises(ValueError, match="isn't a CAT-<n> value"):
        publish_table(_fake_client(), storage, "pwd.vishwakarma.t1")


def test_publish_refuses_a_category_outside_the_vocabulary(tmp_path):
    """`category` may be blank, but a value that is set must be one of the
    MDSF CAT levels: pipeline.run() rejects that at ingest, and
    publish_table() keeps the same check for the paths that write the
    lookup without going through run() (republish, a hand-edited CSV)."""

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")

    with pytest.raises(ValueError, match="unknown category 'Open'"):
        _run_with(tmp_path, storage, "beneficiary_email character varying(100)", category="Open")

    _run_with(tmp_path, storage, "beneficiary_email character varying(100)")
    lookups.set_dataset_fields(storage, "pwd.vishwakarma", "pwd", "vishwakarma", {"category": "Open"})
    with pytest.raises(ValueError, match="Unknown category 'Open'"):
        publish_table(_fake_client(), storage, "pwd.vishwakarma.t1")


def test_run_passes_category_override_through_to_publish(tmp_path, monkeypatch):
    """`allow_category_below_columns` is threaded from catalog.yaml through
    run() to publish_table(), so a dataset can opt out of the MDSF floor
    without a code change."""

    storage = LocalObjectStorage(tmp_path / "storage")
    lookups.register_department(storage, "pwd", "Public Works Department")
    seen: list[bool] = []
    monkeypatch.setattr(
        "src.schema_registry.pipeline.publish_table",
        lambda client, storage_, table_id, **kwargs: (seen.append(kwargs["allow_category_below_columns"]), {"column_count": 1})[1],
    )

    _run_with(tmp_path, storage, "beneficiary_email character varying(100)", openmetadata_client=_fake_client())
    _run_with(
        tmp_path, storage, "beneficiary_email character varying(100)",
        openmetadata_client=_fake_client(), allow_category_below_columns=True,
    )

    # run() doesn't publish a CAT-tagged snapshot here: curate normalises the
    # classification to the 7-level vocabulary, which is a different axis and
    # deliberately doesn't feed the floor check. What is asserted is that the
    # flag reaches publish_table() either way.
    assert seen == [False, True]


def test_new_service_gets_the_department_name_as_display_name(tmp_path):
    storage = _ingested_storage(tmp_path)
    client = _fake_client()

    publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    service_request = client.create_or_update.call_args_list[0].args[0]
    assert _unwrap(service_request.name) == "pwd"  # the id still identifies it
    assert _unwrap(service_request.displayName) == "Public Works Department"


def _existing_service(display_name):
    service = MagicMock(fullyQualifiedName="pwd")
    service.id = "service-id"
    service.displayName = display_name
    return service


def test_existing_service_without_a_display_name_gets_one_without_being_recreated(tmp_path):
    storage = _ingested_storage(tmp_path)
    client = _fake_client()
    client.get_by_name.side_effect = None
    client.get_by_name.return_value = _existing_service(None)

    publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    service_patches = [c for c in client.client.patch.call_args_list if "databaseServices" in c.kwargs["path"]]
    assert len(service_patches) == 1
    assert json.loads(service_patches[0].kwargs["data"]) == [
        {"op": "add", "path": "/displayName", "value": "Public Works Department"}
    ]
    assert all("databaseServices" not in str(c) for c in client.create_or_update.call_args_list)


def test_existing_service_with_the_right_display_name_is_left_alone(tmp_path):
    storage = _ingested_storage(tmp_path)
    client = _fake_client()
    client.get_by_name.side_effect = None
    client.get_by_name.return_value = _existing_service("Public Works Department")

    publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    assert not [c for c in client.client.patch.call_args_list if "databaseServices" in c.kwargs["path"]]


def test_publish_table_stores_unpublished_column_details_as_json_property(tmp_path):
    storage = _ingested_storage(tmp_path)
    client = _fake_client()

    publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    call = next(c for c in client.client.patch.call_args_list
                if c.kwargs["path"].startswith("/tables/") and "/extension" in c.kwargs["data"])
    ops = json.loads(call.kwargs["data"])
    assert [o["path"] for o in ops] == ["/extension"]
    extra = json.loads(ops[0]["value"]["extraMetadata"])
    assert extra["curated_file"].startswith("department/pwd/vishwakarma/")
    assert [c["name"] for c in extra["columns"]] == ["sno", "firm_name", "total_cost"]
    sno = extra["columns"][0]
    assert sno["data_type"] == "integer" and "business_description" not in sno and "tag" not in sno
    # the readable label is already the column's dataTypeDisplay; only the
    # machine-readable unit still needs the JSON blob
    assert "readable_type" not in sno


def test_unit_reaches_extra_metadata_even_though_it_is_also_in_the_display():
    extra = json.loads(_extra_metadata_json(
        [{"name": "total_cost", "data_type": "numeric", "readable_type": "Decimal Number",
          "unit": "INR", "ingestion_timestamp": "TS"}],
        "department/pwd/ds/t/curated/schemas/TS.csv",
    ))

    assert extra["columns"][0]["unit"] == "INR"
    assert "readable_type" not in extra["columns"][0]


_DENIED = Exception("Principal: CatalogPrincipal{name='ingestion-bot'} operation EditDisplayName denied by role "
                    "IngestionBotRole, policy DefaultBotPolicy, rule DisplayName-Deny")


def test_denied_display_name_edit_on_an_existing_service_only_warns(tmp_path):
    storage = _ingested_storage(tmp_path)
    client = _fake_client()
    client.get_by_name.side_effect = None
    client.get_by_name.return_value = _existing_service(None)

    def patch(path, data):
        if "databaseServices" in path:
            raise _DENIED

    client.client.patch.side_effect = patch

    result = publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    assert result["column_count"] == 3  # the table was still published


def test_denied_display_name_on_create_falls_back_to_creating_without_it(tmp_path):
    storage = _ingested_storage(tmp_path)
    client = _fake_client()
    real = client.create_or_update.side_effect

    def create_or_update(request):
        if _unwrap(getattr(request, "name", None)) == "pwd" and getattr(request, "displayName", None):
            raise _DENIED
        return real(request)

    client.create_or_update.side_effect = create_or_update

    result = publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")

    assert result["column_count"] == 3
    created = [c.args[0] for c in client.create_or_update.call_args_list
               if _unwrap(getattr(c.args[0], "name", None)) == "pwd"]
    assert getattr(created[-1], "displayName", None) is None


def test_other_errors_while_setting_the_display_name_are_not_hidden(tmp_path):
    storage = _ingested_storage(tmp_path)
    client = _fake_client()
    client.get_by_name.side_effect = None
    client.get_by_name.return_value = _existing_service(None)
    client.client.patch.side_effect = ValueError("something else broke")

    with pytest.raises(ValueError, match="something else broke"):
        publish_table(client, storage, "pwd.vishwakarma.tbd_confirm_with_pwd")


def test_a_columns_hindi_name_becomes_its_openmetadata_display_name():
    column = _to_column(
        {
            "name": "serial_number",
            "data_type": "integer",
            "business_description": "Row serial number in the portal export.",
            "name_hindi": "क्रमसं०",
        }
    )

    assert _unwrap(column.name) == "serial_number"
    assert _unwrap(column.displayName) == "क्रमसं०"
    assert _unwrap(column.description) == "Row serial number in the portal export."


def test_a_column_without_a_hindi_name_has_no_display_name():
    column = _to_column(
        {"name": "amount", "data_type": "numeric", "business_description": "Amount."}
    )

    assert column.displayName is None


def test_readable_type_becomes_the_openmetadata_data_type_display():
    column = _to_column(
        {"name": "sno", "data_type": "integer", "readable_type": "Whole Number"}
    )

    assert _unwrap(column.dataTypeDisplay) == "Whole Number"


def test_unit_is_appended_to_the_data_type_display():
    column = _to_column(
        {
            "name": "total_cost",
            "data_type": "numeric",
            "readable_type": "Decimal Number",
            "unit": "INR",
        }
    )

    assert _unwrap(column.dataTypeDisplay) == "Decimal Number (INR)"
