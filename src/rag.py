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
            f"Fields of study offered include: {fields}."
        )

        ids.append(f"us_{row['unitid']}")

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
    global_ids, global_documents = build_global_documents(conn)

    conn.close()

    ids = us_ids + global_ids
    documents = us_documents + global_documents

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
