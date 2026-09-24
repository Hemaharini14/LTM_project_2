"""
Query routing for hybrid retrieval.

Vector search compares meaning, which answers "tell me about universities
like this" well and "which one is cheapest" badly — a superlative is a
ranking over numbers, not a similarity. Those questions are answered from
SQL instead, and the rows are handed back as context in the same shape as
retrieved documents so the answering step does not change.
"""

import re

from src.db import get_connection


# Each intent maps to a column and a direction to sort it.
SUPERLATIVES = [
    (r"\b(cheap(est)?|least expensive|lowest (tuition|fee|cost)|most affordable|"
     r"lowest priced)\b", "tuition_out_state", "ASC", "lowest tuition"),
    (r"\b(most expensive|highest (tuition|fee|cost)|priciest)\b",
     "tuition_out_state", "DESC", "highest tuition"),
    (r"\b(highest (paying|salary|earnings)|best (paid|salary|earnings|outcomes)|"
     r"top earning|best return)\b",
     "median_earnings_10yr", "DESC", "highest graduate earnings"),
    (r"\b((most|best|good|top) (generous )?(scholarships?|aid|financial aid)|"
     r"most generous|lowest net price|cheapest after aid|"
     r"(scholarships?|financial aid) for)\b",
     "net_price_avg", "ASC", "lowest net price after aid"),
    (r"\b(easiest to get in|highest accept|least selective)\b",
     "admission_rate", "DESC", "highest admission rate"),
    (r"\b(hardest to get in|most selective|lowest accept)\b",
     "admission_rate", "ASC", "lowest admission rate"),
    (r"\b(cheapest (housing|accommodation|hostel)|lowest (rent|room))\b",
     "roomboard_on_campus", "ASC", "lowest on-campus housing cost"),
]

BUDGET_PATTERN = re.compile(
    r"(?:under|below|less than|cheaper than|within|max(?:imum)?(?: of)?)\s*"
    r"\$?\s*([\d,]+)\s*(k|thousand)?",
    re.IGNORECASE
)

COUNT_PATTERN = re.compile(
    r"\bhow many\b", re.IGNORECASE
)


# Students use acronyms, which embed nowhere near the spelled-out name:
# "MIT" retrieved Karlsruhe and KAIST before this existed.
ACRONYMS = {
    "mit": "Massachusetts Institute of Technology",
    "ucla": "University of California-Los Angeles",
    "usc": "University of Southern California",
    "nyu": "New York University",
    "ucb": "University of California-Berkeley",
    "cmu": "Carnegie Mellon University",
    "gatech": "Georgia Institute of Technology",
    "georgia tech": "Georgia Institute of Technology",
    "caltech": "California Institute of Technology",
    "uiuc": "University of Illinois Urbana-Champaign",
    "umich": "University of Michigan-Ann Arbor",
    "utaustin": "The University of Texas at Austin",
    "penn state": "Pennsylvania State University-Main Campus",
    "virginia tech": "Virginia Polytechnic Institute and State University"
}


def named_institution(question):
    """
    The institution this question is about, if it names one.

    Checks acronyms first, then asks SQL which institution name appears
    inside the question — the reverse of a normal LIKE, which lets the
    database do the matching across all 6,273 names.
    """

    lowered = question.lower()

    for acronym, full_name in ACRONYMS.items():
        if re.search(rf"\b{re.escape(acronym)}\b", lowered):
            return full_name

    conn = get_connection()

    row = conn.execute(
        """
        SELECT institution_name
        FROM us_institutions
        WHERE LENGTH(institution_name) > 10
          AND LOWER(?) LIKE '%' || LOWER(institution_name) || '%'
        ORDER BY LENGTH(institution_name) DESC
        LIMIT 1
        """,
        (question,)
    ).fetchone()

    if row is None:
        row = conn.execute(
            """
            SELECT university_name AS institution_name
            FROM international_programs
            WHERE LENGTH(university_name) > 8
              AND LOWER(?) LIKE '%' || LOWER(university_name) || '%'
            ORDER BY LENGTH(university_name) DESC
            LIMIT 1
            """,
            (question,)
        ).fetchone()

    conn.close()

    return row["institution_name"] if row else None


def parse_budget(question):
    """Dollar ceiling stated in the question, if any."""

    match = BUDGET_PATTERN.search(question)

    if not match:
        return None

    amount = float(match.group(1).replace(",", ""))

    if match.group(2):
        amount *= 1000

    # "under 40" almost certainly means $40,000, not $40.
    if amount < 1000:
        amount *= 1000

    return amount


def detect_superlative(question):
    """The ranking the question is asking for, if it is asking for one."""

    lowered = question.lower()

    for pattern, column, direction, label in SUPERLATIVES:
        if re.search(pattern, lowered):
            return column, direction, label

    return None


def wants_structured_answer(question):
    """Whether SQL will serve this question better than similarity."""

    return bool(
        detect_superlative(question)
        or COUNT_PATTERN.search(question)
    )


def describe(row, column, label):
    """One retrieved row, worded so the model can quote it directly."""

    def money(value):
        return f"${value:,.0f}" if value is not None else "not reported"

    parts = [
        f"{row['institution_name']} in {row['city']}, {row['state']}, "
        f"United States."
    ]

    parts.append(f"Out-of-state tuition {money(row['tuition_out_state'])}.")

    if row["net_price_avg"] is not None:
        # Aid can exceed the full cost, which the data reports as a
        # negative price. Saying so beats printing "$-778".
        after_aid = (
            "nothing — aid covers the full cost"
            if row["net_price_avg"] <= 0
            else money(row["net_price_avg"])
        )
        parts.append(
            f"Average price after grants and scholarships: {after_aid}."
        )

    if row["roomboard_on_campus"] is not None:
        parts.append(
            f"On-campus housing {money(row['roomboard_on_campus'])}."
        )

    if row["median_earnings_10yr"] is not None:
        parts.append(
            f"Median earnings 10 years after entry "
            f"{money(row['median_earnings_10yr'])}."
        )

    if row["admission_rate"] is not None:
        parts.append(f"Admission rate {row['admission_rate']:.1%}.")

    parts.append(f"Ranked here by {label}.")

    return " ".join(parts)


def structured_context(question, limit=8):
    """
    Answers a ranking or counting question from SQL.

    Returns (documents, explanation) or None when the question is not of
    that shape, so the caller can fall back to vector retrieval.
    """

    superlative = detect_superlative(question)
    budget = parse_budget(question)
    counting = bool(COUNT_PATTERN.search(question))

    # A question about one named university is a lookup, so fetch that
    # institution directly rather than hoping similarity surfaces it.
    if not superlative and not counting:
        name = named_institution(question)

        if name is None:
            return None

        conn = get_connection()

        row = conn.execute(
            """
            SELECT institution_name, city, state, tuition_out_state,
                   net_price_avg, roomboard_on_campus,
                   median_earnings_10yr, admission_rate
            FROM us_institutions
            WHERE institution_name = ?
            """,
            (name,)
        ).fetchone()

        conn.close()

        if row is None:
            return None

        return (
            [describe(row, "institution_name", "name match")],
            f"looked up {name} by name"
        )

    column, direction, label = superlative or (
        "median_earnings_10yr", "DESC", "graduate earnings"
    )

    conditions = [
        "grants_degree = 1",
        f"{column} IS NOT NULL"
    ]
    params = []

    if budget is not None:
        conditions.append("tuition_out_state <= ?")
        params.append(budget)

    conn = get_connection()

    if counting and not superlative:
        total = conn.execute(
            f"SELECT COUNT(*) FROM us_institutions WHERE {' AND '.join(conditions)}",
            params
        ).fetchone()[0]

        conn.close()

        budget_text = (
            f" with tuition at or below ${budget:,.0f}" if budget else ""
        )

        return (
            [
                f"There are {total:,} degree-granting US universities"
                f"{budget_text} in this dataset."
            ],
            f"counted from the database{budget_text}"
        )

    rows = conn.execute(
        f"""
        SELECT institution_name, city, state, tuition_out_state,
               net_price_avg, roomboard_on_campus, median_earnings_10yr,
               admission_rate
        FROM us_institutions
        WHERE {" AND ".join(conditions)}
        ORDER BY {column} {direction}
        LIMIT ?
        """,
        params + [limit]
    ).fetchall()

    conn.close()

    if not rows:
        return None

    documents = [describe(row, column, label) for row in rows]

    explanation = f"ranked by {label}"
    if budget is not None:
        explanation += f", tuition at or below ${budget:,.0f}"

    return documents, explanation
