"""Unit tests for catalog filters, facets, sorting and paging (no DB / OM)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.openmetadata import catalog_filters as cf  # noqa: E402


def _card(name, service, cat, tags=(), updated=None, **info):
    card = {
        "dataset": f"{service}.{name}",
        "name": name,
        "service": service,
        "department_display": service.upper(),
        "classification": cat,
        "tags": list(tags),
        "updated_at": updated,
        "locked": not info,
    }
    if info:
        card["info"] = {"api_tables": 0, "api_known": 0, **info}
    return card


CARDS = [
    _card("awas", "rd", "CAT-1", ["FieldTag.Geospatial"], 3, frequency="yearly", api_available=False),
    _card("mgnrega", "rd", "CAT-1", ["FieldTag.Geospatial", "MDSF.PII"], 1,
          frequency="Annual", api_available=True, timeline="2014-15 to 2025-26"),
    _card("ntl", "npd", "CAT-1", ["FieldTag.Geospatial"], 2, frequency="Monthly", timeline="2023-27"),
    _card("farmers", "agri", "CAT-3"),  # locked teaser: no facts
]


def names(cards):
    return [c["name"] for c in cards]


def test_timeline_years():
    assert cf.timeline_years("2014-15 to 2025-26") == (2014, 2026)
    assert cf.timeline_years("2023-27") == (2023, 2027)
    assert cf.timeline_years("2019") == (2019, 2019)
    assert cf.timeline_years("1998-02") == (1998, 2002)
    assert cf.timeline_years("ongoing") is None


def test_frequency_aliases_and_api_value():
    assert cf.frequency_value(" annual ") == "Yearly"
    assert cf.frequency_value("monthly") == "Monthly"
    assert cf.api_value({"api_available": True}) == "yes"
    assert cf.api_value({"api_available": None, "api_known": 2, "api_tables": 0}) == "no"
    assert cf.api_value({"api_available": None, "api_known": 0, "api_tables": 0}) is None
    assert cf.api_value(None) is None


def test_or_within_filter_and_across_filters():
    f = cf.CatalogFilters(classification=frozenset({"CAT-1", "CAT-3"}))
    assert names(cf.filter_cards(CARDS, f)) == ["awas", "mgnrega", "ntl", "farmers"]
    f = cf.CatalogFilters(classification=frozenset({"CAT-1"}), frequency=frozenset({"Yearly"}))
    assert names(cf.filter_cards(CARDS, f)) == ["awas", "mgnrega"]
    f = cf.CatalogFilters(frequency=frozenset({"Yearly"}), api=frozenset({"yes"}))
    assert names(cf.filter_cards(CARDS, f)) == ["mgnrega"]
    f = cf.CatalogFilters(tags=frozenset({"MDSF.PII", "Nope"}))
    assert names(cf.filter_cards(CARDS, f)) == ["mgnrega"]


def test_timeline_overlap_excludes_unknown_timelines():
    assert names(cf.filter_cards(CARDS, cf.CatalogFilters(year_from=2024))) == ["mgnrega", "ntl"]
    assert names(cf.filter_cards(CARDS, cf.CatalogFilters(year_to=2020))) == ["mgnrega"]
    assert names(cf.filter_cards(CARDS, cf.CatalogFilters(year_from=2027, year_to=2030))) == ["ntl"]


def test_facets_are_disjunctive_and_list_fixed_options():
    f = cf.CatalogFilters(frequency=frozenset({"Yearly"}))
    out = cf.facets(CARDS, f)
    by = {name: {i["value"]: i["count"] for i in items} for name, items in out.items() if name != "years"}
    # Frequency ignores its own selection; others count only yearly datasets.
    assert by["frequency"] == {"Monthly": 1, "Yearly": 2}
    assert by["classification"] == {"CAT-1": 2, "CAT-2": 0, "CAT-3": 0, "CAT-4": 0}
    assert by["api"] == {"yes": 1, "no": 1}
    assert by["department"] == {"agri": 0, "npd": 0, "rd": 2}
    assert by["tags"]["FieldTag.Geospatial"] == 2 and by["tags"]["MDSF.PII"] == 1
    assert by["steward"] == {}
    assert out["years"] == {"min": 2014, "max": 2027}
    assert [i["label"] for i in out["department"]] == ["AGRI", "NPD", "RD"]


def test_sort_and_page():
    assert names(cf.sort_items(CARDS, "name")) == ["awas", "farmers", "mgnrega", "ntl"]
    assert names(cf.sort_items(CARDS, "updated")) == ["awas", "ntl", "mgnrega", "farmers"]
    assert names(cf.sort_items(CARDS, "relevance")) == names(CARDS)
    assert names(cf.page_of(CARDS, 2, 3)) == ["farmers"]


def test_schema_source_filter_and_facet():
    cards = [
        _card("awas", "rd", "CAT-1", schema_source="Department Provided"),
        _card("mgnrega", "rd", "CAT-1", schema_source=" Public Extraction "),
        _card("ntl", "npd", "CAT-1", schema_source=""),  # blank: not provided
        _card("farmers", "agri", "CAT-3"),  # locked teaser: no facts
    ]
    f = cf.CatalogFilters(schema_source=frozenset({"Public Extraction"}))
    assert f.active
    assert names(cf.filter_cards(cards, f)) == ["mgnrega"]
    out = cf.facets(cards, cf.CatalogFilters(schema_source=frozenset({"Department Provided"}), departments=frozenset({"rd"})))
    # Ignores its own selection, honours the others; blanks are not an option.
    assert {i["value"]: i["count"] for i in out["schema_source"]} == {"Department Provided": 1, "Public Extraction": 1}
