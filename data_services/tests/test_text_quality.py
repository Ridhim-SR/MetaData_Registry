from src.schema_registry.text_quality import (
    ERROR,
    WARNING,
    lint_identifier,
    lint_text,
)


def _kinds(issues):
    return {issue.kind for issue in issues}


def test_known_misspelling_is_an_error():
    issues = lint_text("Count of abtract cases recorded.")
    assert [issue.kind for issue in issues] == ["misspelling"]
    assert issues[0].severity == ERROR
    assert issues[0].suggestion == "abstract"


def test_misspelling_inside_an_identifier_is_found():
    assert _kinds(lint_identifier("Abtract_Daily_Flood")) == {"misspelling"}
    assert _kinds(lint_identifier("abtractValue")) == {"misspelling"}
    assert lint_identifier("rajwahaTarget") == []


def test_repeated_content_word_is_an_error():
    issues = lint_text(
        "Proposed Potential Area proposed for irrigation during the Kharif crop season."
    )
    assert "repeated-word" in _kinds(issues)
    assert all(issue.severity == ERROR for issue in issues if issue.kind == "repeated-word")


def test_adjacent_duplicate_is_an_error():
    assert "duplicate-word" in _kinds(lint_text("The the record is hidden."))


def test_citation_marker_is_an_error():
    issues = lint_text("Report release date[cite: 139].")
    assert "citation-marker" in _kinds(issues)


def test_hindi_only_description_is_an_error():
    issues = lint_text("खंड")
    assert "hindi-only" in _kinds(issues)


def test_description_must_not_repeat_its_label():
    issues = lint_text("River Name", label="River Name")
    assert "description-is-label" in _kinds(issues)


def test_us_spelling_is_a_warning_not_an_error():
    issues = lint_text("Water depth measured in meters.")
    us = [issue for issue in issues if issue.kind == "us-spelling"]
    assert us and us[0].severity == WARNING
    assert us[0].suggestion == "metres"


def test_clean_indian_english_description_passes():
    text = (
        "Canal division (खंड) to which the entry belongs, selected from the "
        "departmental division list."
    )
    assert lint_text(text) == []


def test_romanised_hindi_and_ordinary_abbreviations_are_not_misspellings():
    text = "Desilting target for rajwaha and alpika works, inspected at the Sup level."
    assert [issue for issue in lint_text(text) if issue.kind == "misspelling"] == []
