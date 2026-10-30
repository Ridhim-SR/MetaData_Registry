"""Catalog filters, facet counts, sorting and paging for dataset cards.

Pure helpers (no database, OpenMetadata, or FastAPI imports) shared by the
dataset list and search endpoints, so the catalog page never filters or
counts in the browser. Cards are the viewer's own (visibility already
applied); facts come from `card["info"]`, which only unlocked cards carry.

Values selected within one filter are ORed; filters are ANDed together.
Each facet's counts ignore that facet's own selection ("disjunctive"
facets), so a count is the number of results after ticking that box.
"""

import re
from dataclasses import dataclass, field

CAT_LEVELS = ("CAT-1", "CAT-2", "CAT-3", "CAT-4")
API_VALUES = ("yes", "no")
SORTS = ("relevance", "updated", "name")

# Same schedule written different ways ("Annual", "yearly") filters as one.
_FREQUENCY_ALIASES = {"annual": "Yearly", "annually": "Yearly", "yearly": "Yearly"}

_YEAR_SPAN = re.compile(r"(\d{4})(?:\s*[-–/]\s*(\d{2,4}))?")


@dataclass(frozen=True)
class CatalogFilters:
    classification: frozenset[str] = field(default_factory=frozenset)
    tags: frozenset[str] = field(default_factory=frozenset)
    departments: frozenset[str] = field(default_factory=frozenset)
    frequency: frozenset[str] = field(default_factory=frozenset)
    api: frozenset[str] = field(default_factory=frozenset)
    steward: frozenset[str] = field(default_factory=frozenset)
    schema_source: frozenset[str] = field(default_factory=frozenset)
    year_from: int | None = None
    year_to: int | None = None

    @property
    def active(self) -> bool:
        return bool(
            self.classification or self.tags or self.departments or self.frequency
            or self.api or self.steward or self.schema_source or self.year_from is not None or self.year_to is not None
        )


def frequency_value(text: str | None) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None
    return _FREQUENCY_ALIASES.get(raw.lower()) or raw[0].upper() + raw[1:]


def api_value(info: dict | None) -> str | None:
    """"yes"/"no" as the dataset page shows it, else None (not provided)."""
    if not info:
        return None
    if info.get("api_available") is not None:
        return "yes" if info["api_available"] else "no"
    if not info.get("api_known"):
        return None
    return "yes" if info.get("api_tables") else "no"


def timeline_years(text: str | None) -> tuple[int, int] | None:
    """First and last year a free-text timeline covers, else None.

    "2023-27" -> (2023, 2027); "2014-15 to 2025-26" -> (2014, 2026).
    """
    spans = _YEAR_SPAN.findall(text or "")
    if not spans:
        return None
    start = int(spans[0][0])
    last_year, tail = spans[-1]
    end = int(last_year)
    if tail:
        end = int(tail) if len(tail) == 4 else end // 100 * 100 + int(tail)
        if end < int(last_year):
            end += 100
    return start, max(start, end)


def card_facts(card: dict) -> dict:
    """The filterable values of one card (None = not provided)."""
    info = card.get("info")
    steward = ((info or {}).get("steward") or "").strip() or None
    schema_source = ((info or {}).get("schema_source") or "").strip() or None
    return {
        "classification": card.get("classification"),
        "tags": card.get("tags") or [],
        "department": card.get("service"),
        "frequency": frequency_value((info or {}).get("frequency")),
        "api": api_value(info),
        "steward": steward,
        "schema_source": schema_source,
        "years": timeline_years((info or {}).get("timeline")),
    }


def _passes(facts: dict, f: CatalogFilters, skip: str | None = None, *, tags: list[str] | None = None) -> bool:
    def one(name: str, selected: frozenset[str]) -> bool:
        return name == skip or not selected or facts[name] in selected

    if not (
        one("classification", f.classification)
        and one("department", f.departments)
        and one("frequency", f.frequency)
        and one("api", f.api)
        and one("steward", f.steward)
        and one("schema_source", f.schema_source)
    ):
        return False
    if skip != "tags" and f.tags and not set(facts["tags"] if tags is None else tags) & f.tags:
        return False
    if f.year_from is None and f.year_to is None:
        return True
    years = facts["years"]
    if years is None:
        return False  # no timeline: nothing says it covers the range
    lo = f.year_from if f.year_from is not None else years[0]
    hi = f.year_to if f.year_to is not None else years[1]
    return years[0] <= hi and years[1] >= lo


def card_matches(card: dict, f: CatalogFilters, *, tags: list[str] | None = None) -> bool:
    """Whether a card passes every filter. `tags` overrides the card's own
    tags (a table hit is matched on its own tags, the rest on its dataset)."""
    return _passes(card_facts(card), f, tags=tags)


def filter_cards(cards: list[dict], f: CatalogFilters) -> list[dict]:
    return [c for c in cards if card_matches(c, f)] if f.active else list(cards)


def facets(cards: list[dict], f: CatalogFilters) -> dict:
    """Option counts per filter over `cards`, each ignoring its own selection.

    Classification always lists CAT-1..CAT-4 and API always lists yes/no
    (zero counts included); other facets list only values that occur.
    `years` is the overall timeline span for the year pickers.
    """
    counts: dict[str, dict[str, int]] = {
        "classification": dict.fromkeys(CAT_LEVELS, 0),
        "tags": {},
        "department": {},
        "frequency": {},
        "api": dict.fromkeys(API_VALUES, 0),
        "steward": {},
        "schema_source": {},
    }
    labels: dict[str, str] = {}
    for card in cards:
        facts = card_facts(card)
        if facts["department"]:
            labels[facts["department"]] = card.get("department_display") or facts["department"]
        for name, bucket in counts.items():
            values = facts[name] if name == "tags" else [facts[name]]
            match = _passes(facts, f, skip=name)
            for value in values:
                if value is None:
                    continue
                bucket[value] = bucket.get(value, 0) + (1 if match else 0)
    out: dict = {}
    for name, bucket in counts.items():
        if name in ("classification", "api"):
            items = [{"value": v, "count": n} for v, n in bucket.items()]
        else:
            items = [{"value": v, "count": n} for v, n in sorted(bucket.items(), key=lambda kv: kv[0].lower())]
        if name == "department":
            for item in items:
                item["label"] = labels.get(item["value"], item["value"])
            items.sort(key=lambda i: i["label"].lower())
        out[name] = items
    out["years"] = year_span(cards)
    return out


def year_span(cards: list[dict]) -> dict | None:
    """{"min", "max"} over every card's timeline, else None (no timelines)."""
    spans = [y for y in (card_facts(c)["years"] for c in cards) if y]
    if not spans:
        return None
    return {"min": min(y[0] for y in spans), "max": max(y[1] for y in spans)}


def sort_items(items: list[dict], sort: str) -> list[dict]:
    """"relevance" keeps the given order; "updated" is newest first (unknown
    last); "name" is A-Z."""
    if sort == "name":
        return sorted(items, key=lambda i: (i.get("name") or i.get("display_name") or "").lower())
    if sort == "updated":
        return sorted(items, key=lambda i: (i.get("updated_at") is None, -(i.get("updated_at") or 0)))
    return list(items)


def page_of(items: list[dict], page: int, size: int) -> list[dict]:
    start = (page - 1) * size
    return items[start:start + size]
