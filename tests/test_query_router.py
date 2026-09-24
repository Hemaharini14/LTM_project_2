"""
Query routing.

The two regression tests at the bottom cover bugs that reached the
committed code and were only caught by the retrieval evaluation. They
are here so a future pattern change cannot quietly reintroduce them.
"""

import pytest

from src.query_router import (
    detect_superlative,
    named_institution,
    parse_budget,
    wants_structured_answer,
)


# --- which questions belong in SQL ------------------------------------

@pytest.mark.parametrize("question", [
    "which universities have the best scholarships",
    "what are the cheapest universities",
    "most generous financial aid",
    "highest paying universities",
    "how many universities cost less than 20000",
    "which university is the most selective",
])
def test_ranking_questions_route_to_sql(question):
    assert wants_structured_answer(question)


@pytest.mark.parametrize("question", [
    "what is campus life like in a big city",
    "which universities suit someone interested in robotics",
    "how do I write a statement of purpose",
])
def test_descriptive_questions_stay_on_vector_search(question):
    assert not wants_structured_answer(question)


# --- budgets ----------------------------------------------------------

@pytest.mark.parametrize("question,expected", [
    ("universities under $30,000", 30000),
    ("cheaper than 25000", 25000),
    ("under 40k", 40000),
    ("less than 15 thousand", 15000),
    ("under 40", 40000),          # bare numbers mean thousands here
    ("tell me about MIT", None),
])
def test_budget_parsing(question, expected):
    assert parse_budget(question) == expected


# --- named lookups ----------------------------------------------------

def test_acronym_resolves_to_full_name():
    assert named_institution("tell me about MIT") == \
        "Massachusetts Institute of Technology"


def test_full_name_in_question_is_found():
    assert named_institution("what is tuition at Stanford University?") == \
        "Stanford University"


def test_question_naming_nobody_returns_none():
    assert named_institution("which universities are cheapest") is None


def test_acronym_needs_word_boundary():
    """'admit' contains 'mit' but is not a reference to MIT."""

    assert named_institution("what admit rate should I expect") != \
        "Massachusetts Institute of Technology"


# --- regressions ------------------------------------------------------

def test_housing_superlative_beats_generic_cheapest():
    """
    Regression: "cheapest on-campus housing" ranked by tuition, because
    the generic "cheapest" pattern was tested first and matched.
    """

    column, _, _ = detect_superlative("cheapest on-campus housing")

    assert column == "roomboard_on_campus"


def test_superlative_tolerates_a_word_before_the_noun():
    """
    Regression: "highest graduate earnings" fell through to similarity
    search, because the pattern allowed no word between the superlative
    and the noun and so never matched.
    """

    column, direction, _ = detect_superlative(
        "which university has the highest graduate earnings"
    )

    assert column == "median_earnings_10yr"
    assert direction == "DESC"
