"""Quality checks for descriptions and identifiers bound for the catalogue.

The catalogue publishes descriptions verbatim, so every typo in a department
workbook or an agent draft becomes a published typo. This module is the gate
that was missing: `irrigation_xlsx` runs it over every description, table name
and field name before writing a dataset, and `ai_metadata` uses the same
spelling rules when drafting.

The checks are deliberately narrow. A general dictionary pass flags Romanised
Hindi (``rajwaha``, ``alpika``), river and district names, and abbreviations
the department never expands (``Sup``, ``Exe``, ``HFL``), which are legitimate
here. Only defects that are always wrong in English are errors:

* a known misspelling (``abtract``, ``achive``, ``recieve``, ...);
* a word repeated in the same sentence (``Proposed Potential Area proposed``);
* a copied citation marker (``[cite: 139]``);
* a description that is only Devanagari, or is just its label repeated.

US spellings are warnings, not errors: the house style is Indian English, but
a department's own wording is theirs to keep.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ERROR = "error"
WARNING = "warning"

# Only words actually seen in department submissions or agent drafts. Keeping
# this explicit is what lets the check run over Hindi transliterations without
# false positives.
MISSPELLINGS: dict[str, str] = {
    "abtract": "abstract",
    "acheive": "achieve",
    "achive": "achieve",
    "adress": "address",
    "adminstration": "administration",
    "availabe": "available",
    "avaliable": "available",
    "availible": "available",
    "begining": "beginning",
    "buisness": "business",
    "calender": "calendar",
    "cannal": "canal",
    "catagory": "category",
    "commitee": "committee",
    "compatable": "compatible",
    "definately": "definitely",
    "departmnet": "department",
    "enviroment": "environment",
    "expendeture": "expenditure",
    "existance": "existence",
    "finaly": "finally",
    "fourty": "forty",
    "freind": "friend",
    "goverment": "government",
    "immediatly": "immediately",
    "independant": "independent",
    "irigation": "irrigation",
    "irrigaton": "irrigation",
    "maintainance": "maintenance",
    "maintainence": "maintenance",
    "maintanance": "maintenance",
    "managment": "management",
    "mounth": "month",
    "neccessary": "necessary",
    "noticable": "noticeable",
    "occassion": "occasion",
    "occured": "occurred",
    "percentange": "percentage",
    "persentage": "percentage",
    "posession": "possession",
    "prefered": "preferred",
    "priviledge": "privilege",
    "probaly": "probably",
    "publically": "publicly",
    "recieve": "receive",
    "recieved": "received",
    "refered": "referred",
    "seperate": "separate",
    "similiar": "similar",
    "sucess": "success",
    "sucessful": "successful",
    "tommorow": "tomorrow",
    "todate": "to date",
    "transfered": "transferred",
    "untill": "until",
    "upto": "up to",
    "useage": "usage",
    "usefull": "useful",
    "usualy": "usually",
    "wether": "whether",
    "withold": "withhold",
    "yaer": "year",
}

# House style is Indian English. These are reported as warnings so a reviewer
# can decide whether a department's own wording should be normalised.
US_TO_INDIAN: dict[str, str] = {
    "analyze": "analyse",
    "analyzed": "analysed",
    "behavior": "behaviour",
    "categorize": "categorise",
    "categorized": "categorised",
    "categorizing": "categorising",
    "center": "centre",
    "centers": "centres",
    "color": "colour",
    "defense": "defence",
    "enrollment": "enrolment",
    "enrollments": "enrolments",
    "favor": "favour",
    "fulfill": "fulfil",
    "fulfillment": "fulfilment",
    "kilometer": "kilometre",
    "kilometers": "kilometres",
    "labor": "labour",
    "license": "licence",
    "meter": "metre",
    "meters": "metres",
    "millimeter": "millimetre",
    "millimeters": "millimetres",
    "neighbor": "neighbour",
    "offense": "offence",
    "organization": "organisation",
    "organizations": "organisations",
}

# Words that repeat legitimately in short catalogue sentences. A content word
# must be at least six letters to be considered, so this only covers the
# longer function/domain words that would otherwise trip the near-repeat test.
_REPEAT_ALLOWED = frozenset(
    {
        "number",
        "record",
        "records",
        "report",
        "reports",
        "source",
        "sources",
        "status",
        "target",
        "targets",
        "values",
        "within",
    }
)

# Date/time masks such as "YYYY-YYYY" or "(FORTNIGHT-1)" are placeholders, not
# words that can be accidentally repeated.
_MASK_WORDS = frozenset({"dd", "hh", "hhmm", "hhmmss", "mm", "yy", "yyyy"})

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’]*")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_CITE_RE = re.compile(r"\[\s*cite\s*:[^\]]*\]", re.IGNORECASE)
_DOUBLE_SPACE_RE = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+[,.;:!?]")
_NORMALISE_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Issue:
    """One defect in one piece of text."""

    kind: str
    severity: str
    text: str
    suggestion: str = ""

    def __str__(self) -> str:
        hint = f" -> {self.suggestion!r}" if self.suggestion else ""
        return f"{self.severity}: {self.kind} {self.text!r}{hint}"


def _words(text: str) -> list[str]:
    return [match.group(0).strip("'’").lower() for match in _WORD_RE.finditer(text)]


def _identifier_words(identifier: str) -> list[str]:
    spaced = identifier.replace("_", " ")
    return [word for part in spaced.split() for word in _CAMEL_RE.sub(" ", part).split()]


def lint_identifier(identifier: str) -> list[Issue]:
    """Check a table or field name for known misspellings.

    Identifiers are split on ``_`` and camelCase, so ``Abtract_Daily_Flood``
    and ``abtractValue`` are both caught while ``rajwahaTarget`` is not.
    """

    issues: list[Issue] = []
    for word in _identifier_words(identifier):
        lowered = word.lower()
        if lowered in MISSPELLINGS:
            suggestion = MISSPELLINGS[lowered].replace(" ", "_")
            issues.append(Issue("misspelling", ERROR, word, suggestion))
    return issues


def lint_text(
    text: str,
    *,
    label: str = "",
    indian_english: bool = True,
) -> list[Issue]:
    """Check one description. Returns every issue found, errors first."""

    if not text or not text.strip():
        return []

    issues: list[Issue] = []
    words = _words(text)

    for word in words:
        if word in MISSPELLINGS:
            issues.append(Issue("misspelling", ERROR, word, MISSPELLINGS[word]))

    # Adjacent repetition ("the the").
    for previous, current in zip(words, words[1:]):
        if previous == current and len(current) > 2 and current not in _MASK_WORDS:
            issues.append(Issue("duplicate-word", ERROR, f"{current} {current}", current))

    # Near repetition inside one sentence ("Proposed Potential Area proposed").
    # A repeat across a comma, bracket or "or"/"and" is an enumeration
    # ("major and medium canals, minor branch canals"), not a stutter.
    for sentence_match in re.finditer(r"[^.!?]+[.!?]?", text):
        sentence = sentence_match.group(0)
        matches = [
            match
            for match in _WORD_RE.finditer(sentence)
            if len(match.group(0)) >= 6
            and match.group(0).lower() not in _REPEAT_ALLOWED
            and match.group(0).lower() not in _MASK_WORDS
        ]
        for position, first in enumerate(matches):
            for later in matches[position + 1 :]:
                if later.start() - first.end() > 40:
                    break
                if first.group(0).lower() != later.group(0).lower():
                    continue
                between = sentence[first.end() : later.start()]
                if re.search(r"[,;:()/]|\b(?:or|and|to)\b", between, re.IGNORECASE):
                    continue
                issues.append(
                    Issue(
                        "repeated-word",
                        ERROR,
                        first.group(0),
                        "remove one occurrence",
                    )
                )

    for marker in _CITE_RE.findall(text):
        issues.append(Issue("citation-marker", ERROR, marker, "remove the marker"))

    if _DEVANAGARI_RE.search(text) and not re.search(r"[A-Za-z]{2,}", text):
        issues.append(
            Issue("hindi-only", ERROR, text.strip()[:60], "write an English description")
        )

    if label:
        normalise = lambda value: _NORMALISE_RE.sub(" ", value.lower()).strip()
        if normalise(text) == normalise(label):
            issues.append(
                Issue("description-is-label", ERROR, text.strip()[:60], "describe the field")
            )

    if indian_english:
        for word in words:
            if word in US_TO_INDIAN:
                issues.append(Issue("us-spelling", WARNING, word, US_TO_INDIAN[word]))

    for match in _DOUBLE_SPACE_RE.finditer(text):
        issues.append(Issue("double-space", WARNING, repr(match.group(0))))
    for match in _SPACE_BEFORE_PUNCT_RE.finditer(text):
        issues.append(Issue("space-before-punctuation", WARNING, repr(match.group(0))))

    unique: dict[tuple[str, str, str], Issue] = {}
    for issue in issues:
        unique.setdefault((issue.kind, issue.severity, issue.text), issue)
    return sorted(unique.values(), key=lambda issue: (issue.severity != ERROR, issue.kind))
