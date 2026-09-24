"""
Retrieval evaluation.

Measures whether the system puts the right university in front of the
model, comparing pure vector search against the hybrid router. Ground
truth comes from SQL, so the correct answer for every question is known
before it is asked and nothing here depends on judging prose.

Run:  python -m src.evaluation
"""

import random

from src.db import get_connection
from src.query_router import structured_context
from src.rag import retrieve

RETRIEVE_COUNT = 8

# Fixed so the same questions are produced on every run and results are
# comparable between changes.
SEED = 20260924


def build_questions(sample_size=40):
    """
    A question set with a known correct institution for each entry.

    Three shapes, because they stress different parts of the system: a
    named lookup is exact, a superlative is a ranking, and a descriptive
    question is genuine similarity.
    """

    random.seed(SEED)
    conn = get_connection()

    named_pool = conn.execute(
        """
        SELECT institution_name, city, state, tuition_out_state
        FROM us_institutions
        WHERE grants_degree = 1
          AND tuition_out_state IS NOT NULL
          AND median_earnings_10yr IS NOT NULL
        ORDER BY median_earnings_10yr DESC
        LIMIT 300
        """
    ).fetchall()

    questions = []

    # --- named lookups -------------------------------------------------
    for row in random.sample(list(named_pool), min(sample_size, len(named_pool))):
        questions.append({
            "question": f"What is the tuition at {row['institution_name']}?",
            "expected": row["institution_name"],
            "kind": "named lookup"
        })

    # --- superlatives, answered from the database ----------------------
    superlatives = [
        ("Which US university has the lowest tuition?",
         "SELECT institution_name FROM us_institutions "
         "WHERE grants_degree=1 AND tuition_out_state IS NOT NULL "
         "ORDER BY tuition_out_state ASC LIMIT 1"),
        ("Which university has the highest graduate earnings?",
         "SELECT institution_name FROM us_institutions "
         "WHERE grants_degree=1 AND median_earnings_10yr IS NOT NULL "
         "ORDER BY median_earnings_10yr DESC LIMIT 1"),
        ("Which universities have the best scholarships?",
         "SELECT institution_name FROM us_institutions "
         "WHERE grants_degree=1 AND net_price_avg IS NOT NULL "
         "ORDER BY net_price_avg ASC LIMIT 1"),
        ("Which university is the most selective?",
         "SELECT institution_name FROM us_institutions "
         "WHERE grants_degree=1 AND admission_rate IS NOT NULL "
         "ORDER BY admission_rate ASC LIMIT 1"),
        ("Which university has the cheapest on-campus housing?",
         "SELECT institution_name FROM us_institutions "
         "WHERE grants_degree=1 AND roomboard_on_campus IS NOT NULL "
         "ORDER BY roomboard_on_campus ASC LIMIT 1"),
        ("What is the most expensive university?",
         "SELECT institution_name FROM us_institutions "
         "WHERE grants_degree=1 AND tuition_out_state IS NOT NULL "
         "ORDER BY tuition_out_state DESC LIMIT 1"),
    ]

    for text, sql in superlatives:
        expected = conn.execute(sql).fetchone()

        if expected:
            questions.append({
                "question": text,
                "expected": expected["institution_name"],
                "kind": "superlative"
            })

    # --- acronyms, which is how students actually write ----------------
    # Full names embed close to their own document; short acronyms do not,
    # so these are tested separately.
    for acronym, full_name in [
        ("MIT", "Massachusetts Institute of Technology"),
        ("UCLA", "University of California-Los Angeles"),
        ("NYU", "New York University"),
        ("CMU", "Carnegie Mellon University"),
        ("Caltech", "California Institute of Technology"),
        ("Georgia Tech", "Georgia Institute of Technology"),
    ]:
        questions.append({
            "question": f"Tell me about {acronym}.",
            "expected": full_name,
            "kind": "acronym lookup"
        })

    # --- descriptive, where similarity is the right tool ---------------
    descriptive = conn.execute(
        """
        SELECT institution_name, city, state
        FROM us_institutions
        WHERE grants_degree = 1 AND sat_average IS NOT NULL
        ORDER BY sat_average DESC LIMIT 60
        """
    ).fetchall()

    for row in random.sample(list(descriptive), 10):
        questions.append({
            "question": (
                f"Tell me about a selective university in "
                f"{row['city']}, {row['state']}."
            ),
            "expected": row["institution_name"],
            "kind": "descriptive"
        })

    conn.close()

    return questions


def vector_only(question):
    """The system as it behaved before routing was added."""

    return retrieve(question, RETRIEVE_COUNT)


def hybrid(question):
    """The current system: SQL for rankings and lookups, vectors other."""

    routed = structured_context(question)

    if routed is None:
        return retrieve(question, RETRIEVE_COUNT)

    documents, _ = routed

    if len(documents) == 1:
        documents = documents + retrieve(question, 4)

    return documents


def rank_of_expected(documents, expected):
    """1-based position of the correct institution, or None if absent."""

    for position, document in enumerate(documents, start=1):
        if expected.lower() in document.lower():
            return position

    return None


def evaluate(strategy, questions):
    """Hit rate and mean reciprocal rank for one retrieval strategy."""

    by_kind = {}

    for item in questions:
        documents = strategy(item["question"])
        rank = rank_of_expected(documents, item["expected"])

        bucket = by_kind.setdefault(
            item["kind"], {"total": 0, "hits": 0, "reciprocal": 0.0}
        )
        bucket["total"] += 1

        if rank is not None:
            bucket["hits"] += 1
            bucket["reciprocal"] += 1 / rank

    return by_kind


def report(name, results):
    print(f"\n{name}")
    print(f"  {'question type':<16}{'n':>5}{'hit rate':>11}{'MRR':>9}")

    total = hits = 0
    reciprocal = 0.0

    for kind, stats in sorted(results.items()):
        rate = stats["hits"] / stats["total"]
        mrr = stats["reciprocal"] / stats["total"]
        print(f"  {kind:<16}{stats['total']:>5}{rate:>10.0%}{mrr:>9.2f}")

        total += stats["total"]
        hits += stats["hits"]
        reciprocal += stats["reciprocal"]

    print(f"  {'OVERALL':<16}{total:>5}{hits / total:>10.0%}"
          f"{reciprocal / total:>9.2f}")

    return hits / total, reciprocal / total


if __name__ == "__main__":
    questions = build_questions()

    print(f"Evaluating retrieval on {len(questions)} questions "
          f"with known answers.")
    print("Hit rate: correct university anywhere in the retrieved context.")
    print("MRR: 1.0 means it was always ranked first, 0.5 means second.")

    baseline_rate, baseline_mrr = report(
        "VECTOR ONLY (before routing)", evaluate(vector_only, questions)
    )
    hybrid_rate, hybrid_mrr = report(
        "HYBRID (current)", evaluate(hybrid, questions)
    )

    print(f"\nChange: hit rate {baseline_rate:.0%} -> {hybrid_rate:.0%}, "
          f"MRR {baseline_mrr:.2f} -> {hybrid_mrr:.2f}")
