"""Unit tests for registry visibility policy (no DB / OM required)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.openmetadata.visibility import (  # noqa: E402
    can_view_full,
    count_by_classification,
    count_by_dataset_type,
    dataset_fqn,
    effective_visibility_map,
    group_datasets,
    normalize_dataset_fqn,
    normalize_visibility,
    split_fqn,
    summarize_cards,
    table_decision,
    table_tags,
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


def test_cross_department_table_teaser():
    tables = [_table("ag.db.s2.sales")]
    vmap = {"ag.db.s2.sales": {"visibility": "department", "department": "agriculture"}}
    user = {"role": "user", "department": "pwd"}
    full, teasers = visible_tables(tables, vmap, user)
    assert full == []
    assert len(teasers) == 1
    assert teasers[0]["name"] == "t"  # table names are shown...
    assert teasers[0]["columns"] == []  # ...but no columns
    assert teasers[0]["access_level"] == "department"


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
    full, teasers = visible_tables(tables, {}, {"role": "user", "department": "agriculture"})
    # owner falls back to the FQN service; candidate matching is department-based
    assert full == []  # 'ag' service does not match 'agriculture' candidates
    assert len(teasers) == 1  # unclassified behaves as department: teaser, not hidden
    assert teasers[0]["access_level"] == "department"
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


def test_logged_in_cross_department_decisions_by_level():
    user = {"role": "user", "department": "other"}
    assert table_decision("public", "pwd", user) == "full"
    assert table_decision("department", "pwd", user) == "teaser"
    assert table_decision("restricted", "pwd", user) == "teaser"
    assert table_decision("confidential", "pwd", user) == "hidden"
    assert table_decision("", "pwd", user) == "teaser"
    assert table_decision(None, "pwd", user) == "teaser"


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
    # Departments/datasets stay visible to anonymous as locked teasers;
    # tables/columns require sign-in (enforced at the table endpoints).
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
        "tags", "updated_at", "classification", "dataset_type",
    }
    assert card["tags"] == [] and card["updated_at"] is None


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


def test_count_by_classification_always_lists_every_category():
    cards = [
        {"dataset": "a.db", "classification": "CAT-1"},
        {"dataset": "b.db", "classification": "CAT-3"},
        {"dataset": "c.db", "classification": "CAT-3"},
        {"dataset": "d.db", "classification": None},
        {"dataset": "e.db", "classification": "CAT-9"},  # unknown -> unclassified
    ]
    counts = count_by_classification(cards)
    assert counts == {"CAT-1": 1, "CAT-2": 0, "CAT-3": 2, "CAT-4": 0, "unclassified": 2}
    assert sum(counts.values()) == len(cards)
    assert count_by_classification([]) == {"CAT-1": 0, "CAT-2": 0, "CAT-3": 0, "CAT-4": 0, "unclassified": 0}


def test_dataset_type_read_from_database_custom_property():
    tables = [{"fullyQualifiedName": f"a.{d}.s.t"} for d in ("cit", "adm", "odd", "none")]
    databases = [
        {"fullyQualifiedName": "a.cit", "extension": {"datasetType": "Citizen Centric"}},
        {"fullyQualifiedName": "a.adm", "extension": {"datasetType": " administrative "}},
        {"fullyQualifiedName": "a.odd", "extension": {"datasetType": "Other"}},
        {"fullyQualifiedName": "a.none", "extension": {"datasetType": ""}},
    ]
    vmap = {t["fullyQualifiedName"]: {"visibility": "public"} for t in tables}
    cards = {c["dataset"]: c for c in visible_catalog(tables, databases, vmap, None)}
    assert cards["a.cit"]["dataset_type"] == "Citizen Centric"
    assert cards["a.adm"]["dataset_type"] == "Administrative"  # case/space tolerant
    assert cards["a.odd"]["dataset_type"] is None and cards["a.none"]["dataset_type"] is None
    counts = count_by_dataset_type(list(cards.values()))
    assert counts == {"Citizen Centric": 1, "Administrative": 1, "unspecified": 2}
    assert count_by_dataset_type([]) == {"Citizen Centric": 0, "Administrative": 0, "unspecified": 0}


def test_count_by_classification_never_counts_cat4_for_non_admins():
    tables = [
        {"fullyQualifiedName": "a.open.s.t"},
        {"fullyQualifiedName": "a.secret.s.t"},
    ]
    databases = [
        {"fullyQualifiedName": "a.open", "tags": [{"tagFQN": "DataSensitivity.CAT-1"}]},
        {"fullyQualifiedName": "a.secret", "tags": [{"tagFQN": "DataSensitivity.CAT-4"}]},
    ]
    vmap = effective_visibility_map(tables, databases, {})
    for viewer in (None, {"role": "user", "department": "a"}):
        counts = count_by_classification(visible_catalog(tables, databases, vmap, viewer))
        assert counts["CAT-1"] == 1 and counts["CAT-4"] == 0
    admin = count_by_classification(visible_catalog(tables, databases, vmap, {"role": "admin"}))
    assert admin["CAT-1"] == 1 and admin["CAT-4"] == 1


def test_viewer_key_classes():
    assert viewer_key(None) == "guest"
    assert viewer_key({"role": "admin", "department": "x"}) == "admin"
    assert viewer_key({"role": "user", "department": "Pwd"}) == "user:pwd"





def test_cat_tags_drive_effective_visibility():
    from src.openmetadata.visibility import effective_visibility_map

    def tagged(level):
        return [{"tagFQN": f"DataSensitivity.CAT-{level}"}]

    tables = [
        {"fullyQualifiedName": "a.d1.s.open"},
        {"fullyQualifiedName": "a.d1.s.raised", "tags": tagged(3)},
        {"fullyQualifiedName": "a.d2.s.plain"},
    ]
    databases = [{"fullyQualifiedName": "a.d1", "tags": tagged(1)}]
    sidecar = {
        "a.d1.s.open": {"visibility": "department", "department": "agri"},
        "a.d2.s.plain": {"visibility": "restricted", "department": "agri"},
    }
    vmap = effective_visibility_map(tables, databases, sidecar)
    # Dataset CAT-1 opens the table; the owning department is kept.
    assert vmap["a.d1.s.open"] == {"visibility": "public", "department": "agri"}
    # A higher table-level CAT wins over the dataset's CAT-1.
    assert vmap["a.d1.s.raised"]["visibility"] == "restricted"
    # Untagged tables keep their sidecar visibility.
    assert vmap["a.d2.s.plain"]["visibility"] == "restricted"


def test_card_tags_include_column_tags_but_not_cat():
    cat = [{"tagFQN": "DataSensitivity.CAT-1"}]
    tables = [
        {
            "fullyQualifiedName": "a.d.s.t",
            "tags": cat,
            "columns": [
                {"name": "lat", "tags": [{"tagFQN": "FieldTag.Geospatial"}]},
                {"name": "name", "tags": [{"tagFQN": "MDSF.PII"}, {"tagFQN": "FieldTag.Geospatial"}]},
            ],
        }
    ]
    assert table_tags(tables[0]) == ["FieldTag.Geospatial", "MDSF.PII"]
    databases = [{"fullyQualifiedName": "a.d", "tags": cat}]
    vmap = effective_visibility_map(tables, databases, {})
    [card] = visible_catalog(tables, databases, vmap, None)
    assert card["classification"] == "CAT-1"
    assert card["tags"] == ["FieldTag.Geospatial", "MDSF.PII"]
