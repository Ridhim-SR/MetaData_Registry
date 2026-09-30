"""Unit tests for registry visibility policy (no DB / OM required)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.openmetadata.visibility import (  # noqa: E402
    can_view_full,
    dataset_fqn,
    group_datasets,
    normalize_visibility,
    split_fqn,
    visible_tables,
)


def test_normalize_defaults_to_department():
    assert normalize_visibility(None) == "department"
    assert normalize_visibility("bogus") == "department"
    assert normalize_visibility(" PUBLIC ") == "public"
    assert normalize_visibility("restricted") == "restricted"


def test_split_and_dataset_fqn():
    assert split_fqn("svc.db.schema.tbl") == ("svc", "db", "schema", "tbl")
    assert dataset_fqn("svc.db.schema.tbl") == "svc.db.schema"


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
    assert groups[0]["dataset"] == "ag.db.s1"
    assert groups[0]["table_count"] == 2
    assert groups[0]["access_level"] == "restricted"
