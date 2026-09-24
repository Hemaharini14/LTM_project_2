import os

import chromadb
from openai import OpenAI

from src.db import get_connection
from src.llm_extractor import FREE_MODELS, OPENROUTER_BASE_URL
from src.vector_store import CHROMA_DIR, get_model


COLLECTION_NAME = "university_docs"

RETRIEVE_COUNT = 8

SYSTEM_PROMPT = (
    "You are EduBridge, an advisor helping students choose universities. "
    "Answer ONLY from the context below, which comes from official "
    "university and government datasets. Quote the real figures it "
    "gives and name the institutions you drew on. If the context does "
    "not contain the answer, say so plainly instead of guessing — "
    "never invent a fee, ranking, test score or salary."
)

_collection = None


def get_collection():
    global _collection

    if _collection is None:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))

        _collection = client.get_or_create_collection(
            COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )

    return _collection


# ============================================================
# DOCUMENT BUILDING
# ============================================================

def money(value):
    return f"${value:,.0f}" if value is not None else "not reported"


def build_us_documents(conn):
    """One plain-language document per US institution."""

    rows = conn.execute(
        """
        SELECT i.*, (
            SELECT GROUP_CONCAT(DISTINCT f.cip_description)
            FROM (
                SELECT cip_description
                FROM us_fields_of_study
                WHERE unitid = i.unitid
                LIMIT 25
            ) f
        ) AS fields
        FROM us_institutions i
        """
    ).fetchall()

    documents = []
    ids = []

    for row in rows:

        admission = (
            f"{row['admission_rate']:.0%}"
            if row["admission_rate"] is not None
            else "not reported"
        )

        act = (
            f"{row['act_25th']:.0f}-{row['act_75th']:.0f}"
            if row["act_25th"] is not None and row["act_75th"] is not None
            else "not reported"
        )

        fields = (row["fields"] or "").replace(",", ", ")

        documents.append(
            f"{row['institution_name']} is a {row['control_label'] or 'US'} "
            f"university in {row['city']}, {row['state']}, United States. "
            f"Out-of-state tuition is {money(row['tuition_out_state'])} per year "
            f"and in-state tuition is {money(row['tuition_in_state'])}. "
            f"Total cost of attendance is {money(row['cost_of_attendance'])}. "
            f"On-campus room and board (hostel) costs "
            f"{money(row['roomboard_on_campus'])} and off-campus housing costs "
            f"{money(row['roomboard_off_campus'])}. "
            f"Admission rate is {admission}. "
            f"Average SAT is "
            f"{row['sat_average'] or 'not reported'} and ACT range is {act}. "
            f"Median earnings 10 years after entry are "
            f"{money(row['median_earnings_10yr'])}. "
            f"{aid_sentence(row)}"
            f"Fields of study offered include: {fields}."
        )

        ids.append(f"us_{row['unitid']}")

    return ids, documents


def aid_sentence(row):
    """Scholarship and net-price wording for a US institution."""

    parts = []

    if row["net_price_avg"] is not None:
        parts.append(
            "after grants and scholarships the average student actually "
            f"pays {money(row['net_price_avg'])} per year"
        )

    if row["net_price_0_30k"] is not None:
        paid = (
            "nothing at all"
            if row["net_price_0_30k"] <= 0
            else money(row["net_price_0_30k"])
        )
        parts.append(
            f"families earning under $30,000 pay {paid} while families "
            f"earning over $110,000 pay "
            f"{money(row['net_price_110k_plus'])}"
        )

    if row["pell_grant_percent"] is not None:
        parts.append(
            f"{row['pell_grant_percent'] * 100:.0f} percent of students "
            "receive need-based Pell Grants"
        )

    if row["median_debt"] is not None:
        parts.append(
            f"median debt at graduation is {money(row['median_debt'])}"
        )

    # Saying "aid is not reported" put the words "financial aid" into
    # documents that have none. Those entries are mostly "not reported"
    # already, so the phrase dominated them and they won every
    # scholarship query. Silence keeps them out of that competition.
    if not parts:
        return ""

    return (
        "Scholarships and financial aid: " + "; ".join(parts) +
        ". Pell Grants and US federal loans are open only to US citizens "
        "and eligible non-citizens, not to international students. "
    )


def build_international_documents(conn):
    """Non-US universities with real tuition, rent, visa and insurance."""

    rows = conn.execute(
        """
        SELECT university_name, country, city,
               MIN(tuition_usd) AS tuition_min,
               MAX(tuition_usd) AS tuition_max,
               MAX(rent_usd_monthly) AS rent,
               MAX(visa_fee_usd) AS visa,
               MAX(insurance_usd) AS insurance,
               GROUP_CONCAT(DISTINCT program) AS programs
        FROM international_programs
        WHERE country != 'United States'
        GROUP BY university_name, country, city
        """
    ).fetchall()

    documents = []
    ids = []

    for index, row in enumerate(rows):
        rent_annual = row["rent"] * 12 if row["rent"] else None
        programs = (row["programs"] or "").replace(",", ", ")

        documents.append(
            f"{row['university_name']} is a university in {row['city']}, "
            f"{row['country']}. Annual tuition for international students "
            f"ranges from {money(row['tuition_min'])} to "
            f"{money(row['tuition_max'])}. Rent is about "
            f"{money(row['rent'])} a month, roughly {money(rent_annual)} a "
            f"year. The student visa fee is {money(row['visa'])} and health "
            f"insurance costs about {money(row['insurance'])} a year. "
            f"Programmes offered include: {programs}. "
            "Acceptance rates are a US statistic; universities here publish "
            f"entry requirements instead. Scholarship data for "
            f"{row['country']} is not held in this dataset."
        )
        ids.append(f"intl_{index}")

    return ids, documents


def build_india_documents(conn):
    """Indian institutes with JoSAA closing ranks and fee policy."""

    from src.recommender import INDIA_FEE_BANDS, INDIA_WAIVERS, INR_PER_USD

    rows = conn.execute(
        """
        SELECT institute, institute_type, year,
               COUNT(DISTINCT program) AS branches,
               MIN(closing_rank) AS best_rank
        FROM india_cutoffs
        WHERE seat_type = 'OPEN' AND gender = 'Gender-Neutral'
        GROUP BY institute, institute_type, year
        """
    ).fetchall()

    documents = []
    ids = []

    for index, row in enumerate(rows):
        kind = row["institute_type"]
        band = INDIA_FEE_BANDS.get(kind, {})
        exam = "JEE Advanced" if kind == "IIT" else "JEE Main"

        fee = band.get("annual_inr_min")

        if fee:
            fee_text = (
                f"Annual tuition is about Rs {fee:,}, roughly "
                f"{money(round(fee / INR_PER_USD))}. "
            )
        else:
            fee_text = "Tuition varies by institute. "

        waivers = INDIA_WAIVERS.get(kind, [])

        if waivers:
            listed = "; ".join(
                f"{w['who']} - {w['benefit']}" for w in waivers
            )
            waiver_text = f"Fee waivers and scholarships: {listed}. "
        else:
            waiver_text = ""

        branches = conn.execute(
            """
            SELECT program, closing_rank FROM india_cutoffs
            WHERE institute = ? AND seat_type = 'OPEN'
              AND gender = 'Gender-Neutral'
            ORDER BY closing_rank LIMIT 8
            """,
            (row["institute"],)
        ).fetchall()

        branch_text = "; ".join(
            f"{b['program']} closing rank {int(b['closing_rank']):,}"
            for b in branches
        )

        documents.append(
            f"{row['institute']} is an {kind} in India. It admits through "
            f"{exam} and publishes entrance-exam closing ranks rather than "
            f"an acceptance rate. In {row['year']} its most competitive "
            f"open-category branch closed at rank "
            f"{int(row['best_rank']):,}, across {row['branches']} branches. "
            f"{fee_text}{waiver_text}"
            f"Branch closing ranks: {branch_text}."
        )
        ids.append(f"india_{index}")

    return ids, documents


def build_global_documents(conn):
    """One document per globally ranked university."""

    rows = conn.execute(
        """
        SELECT u.university_name, u.country, u.university_rank,
               u.overall_score, u.teaching_score, u.research_score,
               u.international_outlook_score,
               c.cost_of_living_index, c.rent_index
        FROM universities u
        LEFT JOIN countries c ON c.country_name = u.country
        WHERE u.university_name IS NOT NULL
        """
    ).fetchall()

    documents = []
    ids = []

    for index, row in enumerate(rows):

        cost = (
            f"{row['cost_of_living_index']:.1f}"
            if row["cost_of_living_index"] is not None
            else "not reported"
        )

        rent = (
            f"{row['rent_index']:.1f}"
            if row["rent_index"] is not None
            else "not reported"
        )

        documents.append(
            f"{row['university_name']} is a university in {row['country']}. "
            f"World rank {row['university_rank']}, overall score "
            f"{row['overall_score']}, teaching score {row['teaching_score']}, "
            f"research score {row['research_score']}, international outlook "
            f"{row['international_outlook_score']}. "
            f"{row['country']} has a cost-of-living index of {cost} and a "
            f"rent index of {rent}. "
            f"Tuition figures are not available for institutions outside "
            f"the United States in this dataset."
        )

        ids.append(f"global_{index}")

    return ids, documents


def build_index(batch_size=1000):
    conn = get_connection()

    us_ids, us_documents = build_us_documents(conn)
    intl_ids, intl_documents = build_international_documents(conn)
    india_ids, india_documents = build_india_documents(conn)
    global_ids, global_documents = build_global_documents(conn)

    conn.close()

    ids = us_ids + intl_ids + india_ids + global_ids
    documents = (
        us_documents + intl_documents + india_documents + global_documents
    )

    print(
        f"  {len(us_documents)} US, {len(intl_documents)} international, "
        f"{len(india_documents)} Indian, {len(global_documents)} ranked"
    )

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    client.get_or_create_collection(COLLECTION_NAME)
    client.delete_collection(COLLECTION_NAME)

    collection = client.get_or_create_collection(
        COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    model = get_model()

    for start in range(0, len(documents), batch_size):

        chunk = documents[start:start + batch_size]

        collection.add(
            ids=ids[start:start + batch_size],
            documents=chunk,
            embeddings=model.encode(chunk).tolist()
        )

        print(f"  embedded {min(start + batch_size, len(documents))}/{len(documents)}")

    return len(documents)


# ============================================================
# RETRIEVAL + ANSWERING
# ============================================================

def retrieve(question, n_results=RETRIEVE_COUNT):
    embedding = get_model().encode([question]).tolist()

    response = get_collection().query(
        query_embeddings=embedding,
        n_results=n_results
    )

    return response["documents"][0]


def answer_question(question):
    """Retrieve real university records, then answer grounded in them."""

    context_documents = retrieve(question)

    if not context_documents:
        return {
            "answer": (
                "I don't have any university data indexed yet. "
                "Run: python -m src.rag"
            ),
            "sources": []
        }

    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file "
            "(see .env.example)."
        )

    context = "\n\n".join(
        f"[{index + 1}] {document}"
        for index, document in enumerate(context_documents)
    )

    client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)

    errors = []

    for model in FREE_MODELS:

        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Context:\n{context}\n\n"
                            f"Question: {question}"
                        )
                    }
                ]
            )

            content = completion.choices[0].message.content

            if content:
                return {
                    "answer": content.strip(),
                    "sources": context_documents
                }

            errors.append(f"{model}: empty response")

        except Exception as error:
            errors.append(f"{model}: {type(error).__name__}")

    raise RuntimeError(
        "All free OpenRouter models failed or are rate-limited. "
        + "; ".join(errors)
    )


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":
    print("Building university RAG corpus...")

    count = build_index()

    print(f"Indexed {count} university documents into {CHROMA_DIR}")
