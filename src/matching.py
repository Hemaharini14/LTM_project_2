"""
Match scoring.

Every dimension here is computed from data we actually hold. Dimensions
we cannot measure — research strength, campus lifestyle — are simply not
scored, rather than filled with a plausible-looking number.
"""

from src.vector_store import MAX_DISTANCE


def percentile_rank(value, pool):
    """Where a value sits within a pool, 0-100. None if not comparable."""

    if value is None:
        return None

    comparable = [v for v in pool if v is not None]

    if len(comparable) < 3:
        return None

    below = sum(1 for v in comparable if v < value)

    return round(below / len(comparable) * 100)


def course_score(offered_fields, matched_distances):
    """
    How closely this university's own programmes match what the student
    asked for, from the semantic distance of the nearest one.
    """

    if not matched_distances or not offered_fields:
        return None

    offered = {f.strip() for f in offered_fields.split("|") if f.strip()}

    distances = [
        distance
        for field, distance in matched_distances.items()
        if field in offered
    ]

    if not distances:
        return None

    return round(max(0.0, 1 - min(distances) / MAX_DISTANCE) * 100)


def budget_score(tuition, fee_min, fee_max):
    """
    Whether the price fits the stated budget. Coming in under budget is
    not penalised; going over it decays with how far over.
    """

    if tuition is None or (fee_min is None and fee_max is None):
        return None

    if fee_max is not None and tuition > fee_max:
        overshoot = (tuition - fee_max) / fee_max
        return round(max(0.0, 1 - overshoot) * 100)

    if fee_min is not None and tuition < fee_min:
        return 100

    return 100


def score_rows(rows, preferences):
    """
    Adds a match breakdown to each result row.

    Outcome and affordability are scored as percentiles within this
    result set, so they answer "compared with your other options" rather
    than implying an absolute rating.
    """

    matched_distances = preferences.get("matched_distances") or {}
    fee_min = preferences.get("fee_min")
    fee_max = preferences.get("fee_max")
    wanted_country = preferences.get("country")

    earnings_pool = [row.get("median_earnings_10yr") for row in rows]

    # A lower net price is better, so the pool is negated before ranking.
    net_pool = [
        -row["net_price_avg"] if row.get("net_price_avg") is not None else None
        for row in rows
    ]

    for row in rows:
        dimensions = []

        course = course_score(row.get("matched_fields"), matched_distances)
        if course is not None:
            dimensions.append({"label": "Course match", "score": course})

        budget = budget_score(row.get("tuition_out_state"), fee_min, fee_max)
        if budget is not None:
            dimensions.append({"label": "Budget fit", "score": budget})

        if wanted_country:
            dimensions.append({"label": "Country match", "score": 100})

        outcomes = percentile_rank(row.get("median_earnings_10yr"), earnings_pool)
        if outcomes is not None:
            dimensions.append({"label": "Graduate earnings", "score": outcomes})

        net = row.get("net_price_avg")
        affordability = percentile_rank(
            -net if net is not None else None, net_pool
        )
        if affordability is not None:
            dimensions.append({"label": "Cost after aid", "score": affordability})

        row["match"] = {
            "dimensions": dimensions,
            "overall": (
                round(sum(d["score"] for d in dimensions) / len(dimensions))
                if dimensions else None
            )
        }

    return rows
