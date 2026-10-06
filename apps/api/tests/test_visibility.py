"""Unit tests for registry visibility policy (no DB / OM required)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.openmetadata.visibility import (  # noqa: E402
    can_view_full,
    dataset_fqn,
    group_datasets,
    normalize_dataset_fqn,
    normalize_visibility,
    split_fqn,
    summarize_cards,
    table_decision,
    viewer_key,
    visible_catalog,
    visible_tables,
)


def test_normalize_defaults_to_department():
    assert normalize_visibility(None) == "department"
    assert normalize_visibility("bogus") == "department"
    assert normalize_visibility(" PUBLIC ") == "public"
    assert normalize_visibility("restricted") == "restricted"
    assert normalize_visibility("confidential") == "confidential"


def test_split_and_dataset_fqn():
    assert split_fqn("svc.db.schema.tbl") == ("svc", "db", "schema", "tbl")
    # Dataset identity is the OM database (service.database).
    assert dataset_fqn("svc.db.schema.tbl") == "svc.db"
    assert normalize_dataset_fqn("svc.db") == "svc.db"
    # Legacy schema-level URLs resolve to the parent database.
    assert normalize_dataset_fqn("svc.db.schema") == "svc.db"


def _table(fqn, name="t"):
    return {"id": name, "name": name, "fullyQualifiedName": fqn, "columns": [{"name": "c"}]}


def test_anonymous_sees_only_public():
    tables = [_table("ag.db.s1.crop"), _table("ag.db.s2.sales"), _table("pwd.db.s3.bridges")]
    vmap = {
        "ag.db.s1.crop": {"visibility": "public", "department": "agriculture"},
        "ag.db.s2.sales": {"visibility": "department", "department": "agriculture"},
        "pwd.db.s3.bridges": {"visibility": "restricted", "department": "pwd"},
    }
    full, teasers = visible_tables(tables, vmap, None)
    assert [t["name"] for t in full] == ["t"][:1] or len(full) == 1
    assert full[0]["fullyQualifiedName"] == "ag.db.s1.crop"
    assert teasers == []


def test_department_user_sees_own_plus_public_plus_teasers():
    tables = [_table("ag.db.s1.crop"), _table("ag.db.s2.sales"), _table("pwd.db.s3.bridges")]
    vmap = {
        "ag.db.s1.crop": {"visibility": "public", "department": "agriculture"},
        "ag.db.s2.sales": {"visibility": "department", "department": "agriculture"},
        "pwd.db.s3.bridges": {"visibility": "restricted", "department": "pwd"},
    }
    user = {"role": "user", "department": "agriculture"}
    full, teasers = visible_tables(tables, vmap, user)
    assert {t["fullyQualifiedName"] for t in full} == {"ag.db.s1.crop", "ag.db.s2.sales"}
    assert len(teasers) == 1
    assert teasers[0]["restricted"] is True
    assert teasers[0]["columns"] == []


def test_cross_department_table_hidden():
    tables = [_table("ag.db.s2.sales")]
    vmap = {"ag.db.s2.sales": {"visibility": "department", "department": "agriculture"}}
    user = {"role": "user", "department": "pwd"}
    full, teasers = visible_tables(tables, vmap, user)
    assert full == [] and teasers == []


def test_admin_sees_everything_full():
    tables = [_table("ag.db.s2.sales"), _table("pwd.db.s3.bridges")]
    vmap = {
        "ag.db.s2.sales": {"visibility": "department", "department": "agriculture"},
        "pwd.db.s3.bridges": {"visibility": "restricted", "department": "pwd"},
    }
    full, teasers = visible_tables(tables, vmap, {"role": "admin", "department": None})
    assert len(full) == 2 and teasers == []


def test_missing_sidecar_row_defaults_to_department():
    tables = [_table("ag.db.s9.new_table")]
    full, _ = visible_tables(tables, {}, {"role": "user", "department": "agriculture"})
    # owner falls back to the FQN service; candidate matching is department-based
    assert full == []  # 'ag' service does not match 'agriculture' candidates
    assert can_view_full("department", "agriculture", {"role": "user", "department": "agriculture"})


def test_group_datasets_most_restrictive_wins():
    tables = [_table("ag.db.s1.a", "a"), _table("ag.db.s1.b", "b")]
    vmap = {
        "ag.db.s1.a": {"visibility": "public", "department": "agriculture"},
        "ag.db.s1.b": {"visibility": "restricted", "department": "agriculture"},
    }
    groups = group_datasets(tables, vmap)
    assert len(groups) == 1
    assert groups[0]["dataset"] == "ag.db"
    assert groups[0]["table_count"] == 2
    assert groups[0]["access_level"] == "restricted"


def test_guest_decisions_by_level():
    assert table_decision("public", "pwd", None) == "full"
    assert table_decision("department", "pwd", None) == "teaser"
    assert table_decision("restricted", "pwd", None) == "teaser"
    assert table_decision("confidential", "pwd", None) == "hidden"
    # Unclassified (no row) behaves as department.
    assert table_decision("", "pwd", None) == "teaser"
    assert table_decision(None, "pwd", None) == "teaser"


def test_confidential_logged_in_non_admin_hidden_admin_full():
    assert table_decision("confidential", "pwd", {"role": "user", "department": "pwd"}) == "hidden"
    assert table_decision("confidential", "pwd", {"role": "admin", "department": None}) == "full"
    full, teasers = visible_tables(
        [_table("pwd.db.s.t")],
        {"pwd.db.s.t": {"visibility": "confidential", "department": "pwd"}},
        {"role": "user", "department": "pwd"},
    )
    assert full == [] and teasers == []


def test_visible_catalog_guest_teaser_fields_only():
    tables = [_table("pwd.db.s.t", "t")]
    vmap = {"pwd.db.s.t": {"visibility": "department", "department": "pwd"}}
    cards = visible_catalog(tables, [], vmap, None)
    assert len(cards) == 1
    card = cards[0]
    assert card["locked"] is True
    assert card["dataset"] == "pwd.db"
    assert card["table_count"] == 1
    assert "tables" not in card
    assert "schema" not in card
    assert "owners" not in card
    assert "lineage" not in card
    assert set(card) == {
        "dataset", "service", "database", "name", "description",
        "department", "table_count", "access_level", "locked",
    }


def test_visible_catalog_guest_public_full_confidential_absent():
    tables = [_table("ag.db.s.a", "a"), _table("x.db.s.b", "b")]
    vmap = {
        "ag.db.s.a": {"visibility": "public", "department": "agriculture"},
        "x.db.s.b": {"visibility": "confidential", "department": "x"},
    }
    cards = visible_catalog(tables, [], vmap, None)
    assert [c["dataset"] for c in cards] == ["ag.db"]
    assert cards[0]["locked"] is False
    assert len(cards[0]["tables"]) == 1


def test_summarize_cards_counts_match_lists():
    cards = [
        {"dataset": "a.db", "table_count": 2},
        {"dataset": "b.db", "table_count": 0},
    ]
    assert summarize_cards(cards) == {"datasets": 2, "tables": 2}


def test_viewer_key_classes():
    assert viewer_key(None) == "guest"
    assert viewer_key({"role": "admin", "department": "x"}) == "admin"
    assert viewer_key({"role": "user", "department": "Pwd"}) == "user:pwd"
