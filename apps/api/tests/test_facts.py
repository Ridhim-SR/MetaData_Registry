"""Unit tests for table/dataset fact resolution (pure, no I/O)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.openmetadata import facts


def _table(fqn="s.d.p.t", owners=None, tags=None, **extra):
    return {"fullyQualifiedName": fqn, "owners": owners or [], "tags": tags or [], **extra}


def test_table_values_win_over_dataset():
    resolved = facts.resolve_table_facts(
        _table(owners=[{"name": "alice"}]),
        {"frequency": "Daily", "timeline": None, "api_available": True},
        {"owner": "Dept", "steward": "Bob", "frequency": "Monthly", "timeline": "2020-2025"},
        {"owners": [{"displayName": "DB Owner"}]},
    )
    assert resolved["owner"] == "alice" and resolved["origin"]["owner"] == "table"
    assert resolved["frequency"] == "Daily" and resolved["origin"]["frequency"] == "table"
    assert resolved["timeline"] == "2020-2025" and resolved["origin"]["timeline"] == "dataset"
    assert resolved["steward"] == "Bob" and resolved["origin"]["steward"] == "dataset"
    assert resolved["api_available"] is True


def test_owner_falls_back_through_levels():
    # Table sidecar override, then dataset sidecar, then OM database owner.
    assert facts.resolve_table_facts(_table(), {"dataset_owner": "T"}, {"owner": "D"}, None)["owner"] == "T"
    assert facts.resolve_table_facts(_table(), {"dataset_owner": "  "}, {"owner": "D"}, None)["owner"] == "D"
    om_db = {"owners": [{"name": "db-owner"}]}
    resolved = facts.resolve_table_facts(_table(), None, None, om_db)
    assert resolved["owner"] == "db-owner" and resolved["origin"]["owner"] == "dataset"
    empty = facts.resolve_table_facts(_table(), None, None, None)
    assert empty["owner"] is None and empty["origin"]["owner"] is None


def test_classification_reads_only_mdsf_tags():
    assert facts.classification_of(_table(tags=[{"tagFQN": "PII.Sensitive"}])) is None
    assert facts.classification_of(_table(tags=[{"tagFQN": "MDSF.Internal"}])) == "Internal"
    both = _table(tags=[{"tagFQN": "MDSF.Public"}, {"tagFQN": "MDSF.PII"}])
    assert facts.classification_of(both) == "PII"
    assert facts.classification_of(_table(data_classification="Restricted")) == "Restricted"


def test_dataset_summary():
    tables = [
        _table("s.d.p.a", tags=[{"tagFQN": "MDSF.Public"}]),
        _table("s.d.p.b", tags=[{"tagFQN": "MDSF.Restricted"}]),
        _table("s.d.p.c"),
    ]
    infos = {"s.d.p.a": {"api_available": True}, "s.d.p.b": {"api_available": False}}
    info = facts.resolve_dataset_info({"owner": "Dept"}, None, tables, infos)
    assert info["owner"] == "Dept"
    assert info["api_tables"] == 1 and info["api_known"] == 2 and info["table_count"] == 3
    assert info["data_classification"] == "Restricted"


# Shape of GET /databases/name/pwd.vishwakarma?fields=owners,tags,extension
OM_DATABASE = {
    "fullyQualifiedName": "pwd.vishwakarma",
    "owners": [],
    "tags": [{
        "tagFQN": "DataSensitivity.CAT-3", "name": "CAT-3",
        "description": "Restricted Access -- personal or sensitive data.",
        "source": "Classification",
    }],
    "extension": {"frequency": "lll"},
}


def test_om_database_extension_is_inherited():
    resolved = facts.resolve_table_facts(_table(), None, {"frequency": "Monthly"}, OM_DATABASE)
    # OM custom property wins over the sidecar dataset row.
    assert resolved["frequency"] == "lll" and resolved["origin"]["frequency"] == "dataset"
    assert resolved["data_classification"] == "CAT-3"
    assert resolved["origin"]["data_classification"] == "dataset"
    assert resolved["data_classification_description"].startswith("Restricted Access")
    assert resolved["api_available"] is None


def test_table_extension_overrides_dataset():
    table = _table(extension={"apiAvailable": "No", "datasetOwner": {"displayName": "Table Team"}},
                   tags=[{"tagFQN": "DataSensitivity.CAT-1"}])
    resolved = facts.resolve_table_facts(table, None, None, OM_DATABASE)
    assert resolved["api_available"] is False and resolved["origin"]["api_available"] == "table"
    assert resolved["owner"] == "Table Team"
    assert resolved["data_classification"] == "CAT-1"


def test_extension_value_shapes():
    assert facts.ext_text(["Monthly"]) == "Monthly"
    assert facts.ext_text([{"name": "a"}, {"displayName": "B"}]) == "a, B"
    assert facts.ext_text({"start": 0, "end": 86400000}) == "01 Jan 1970 – 02 Jan 1970"
    assert facts.ext_text("  ") is None
    assert facts.ext_bool(["Yes"]) is True
    assert facts.ext_bool("N") is False
    assert facts.ext_bool("maybe") is None


def test_dataset_classification_prefers_database_tag():
    tables = [_table("s.d.p.a", tags=[{"tagFQN": "DataSensitivity.CAT-4"}])]
    assert facts.resolve_dataset_info(None, OM_DATABASE, tables, {})["data_classification"] == "CAT-3"
    assert facts.resolve_dataset_info(None, None, tables, {})["data_classification"] == "CAT-4"
