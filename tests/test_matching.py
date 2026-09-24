"""Match scoring. Pure arithmetic, no database or network."""

import pytest

from src.matching import budget_score, course_score, percentile_rank, score_rows


# --- budget -----------------------------------------------------------

def test_inside_budget_scores_full():
    assert budget_score(30000, None, 40000) == 100


def test_under_the_minimum_is_not_penalised():
    """Cheaper than asked for is good news, not a mismatch."""

    assert budget_score(5000, 20000, 40000) == 100


def test_over_budget_decays_with_distance():
    near = budget_score(44000, None, 40000)
    far = budget_score(70000, None, 40000)

    assert 0 < near < 100
    assert far < near


def test_far_over_budget_floors_at_zero():
    assert budget_score(200000, None, 40000) == 0


def test_no_budget_means_no_score():
    """A dimension the student did not express should not be invented."""

    assert budget_score(30000, None, None) is None
    assert budget_score(None, None, 40000) is None


# --- course match -----------------------------------------------------

def test_closer_field_scores_higher():
    offered = "Computer Science.|Data Science."

    close = course_score(offered, {"Computer Science.": 0.1})
    distant = course_score(offered, {"Computer Science.": 0.5})

    assert close > distant


def test_best_matching_offered_field_wins():
    """Scored on the nearest programme the university actually offers."""

    offered = "Nursing.|Computer Science."
    distances = {"Computer Science.": 0.1, "Astrophysics.": 0.01}

    assert course_score(offered, distances) == course_score(
        offered, {"Computer Science.": 0.1}
    )


def test_no_overlap_gives_no_score():
    assert course_score("Nursing.", {"Computer Science.": 0.1}) is None


# --- percentiles ------------------------------------------------------

def test_percentile_of_the_best_value():
    assert percentile_rank(100, [10, 20, 30, 100]) == 75


def test_percentile_needs_a_real_pool():
    assert percentile_rank(10, [10, None]) is None


def test_percentile_ignores_missing_values():
    assert percentile_rank(30, [10, 20, 30, None, None]) is not None


# --- whole rows -------------------------------------------------------

def _row(name, tuition, earnings, net):
    return {
        "institution_name": name,
        "tuition_out_state": tuition,
        "median_earnings_10yr": earnings,
        "net_price_avg": net,
        "matched_fields": "Computer Science.",
    }


def test_scoring_adds_a_breakdown_and_overall():
    rows = score_rows(
        [
            _row("A", 20000, 90000, 12000),
            _row("B", 60000, 50000, 40000),
            _row("C", 35000, 70000, 25000),
        ],
        {
            "matched_distances": {"Computer Science.": 0.1},
            "fee_min": None,
            "fee_max": 40000,
            "country": "United States",
        },
    )

    for row in rows:
        assert row["match"]["dimensions"]
        assert 0 <= row["match"]["overall"] <= 100

    # A is inside budget with the best earnings and lowest net price.
    assert rows[0]["match"]["overall"] > rows[1]["match"]["overall"]


def test_unmeasurable_dimensions_are_absent():
    """Research and lifestyle have no data source and must not appear."""

    rows = score_rows([_row("A", 20000, 90000, 12000)], {})
    labels = {d["label"] for d in rows[0]["match"]["dimensions"]}

    assert "Research match" not in labels
    assert "Lifestyle match" not in labels
