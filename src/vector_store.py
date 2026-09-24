from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from src.db import get_connection


BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = BASE_DIR / "chroma_db"

COLLECTION_NAME = "cip_fields"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Cosine distance: 0.0 is identical, 2.0 is opposite. Real subject matches
# measure 0.14-0.55 against this index while unmatchable text sits at 0.80+,
# so this cuts nonsense without discarding loosely-worded fields.
MAX_DISTANCE = 0.6

_model = None
_collection = None


def get_model():
    """
    Cached embedding model. local_files_only keeps startup at ~0.3s —
    without it, blocked update checks stall the load for minutes.
    """

    global _model

    if _model is None:
        _model = SentenceTransformer(
            EMBEDDING_MODEL,
            local_files_only=True
        )

    return _model


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
# INDEX BUILD
# ============================================================

def build_field_index():
    """
    Embed every distinct CIP field name into ChromaDB so a student's
    own wording can be matched semantically instead of by substring.
    """

    conn = get_connection()

    fields = [
        row[0]
        for row in conn.execute(
            """
            SELECT DISTINCT cip_description
            FROM us_fields_of_study
            WHERE cip_description IS NOT NULL
            ORDER BY cip_description
            """
        )
    ]

    conn.close()

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    client.get_or_create_collection(COLLECTION_NAME)
    client.delete_collection(COLLECTION_NAME)

    collection = client.get_or_create_collection(
        COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    embeddings = get_model().encode(fields).tolist()

    collection.add(
        ids=[f"cip_{index}" for index in range(len(fields))],
        documents=fields,
        embeddings=embeddings
    )

    return len(fields)


# ============================================================
# SEMANTIC LOOKUP
# ============================================================

def find_matching_fields_scored(query, n_results=10):
    """
    Matching field names paired with their cosine distance, so callers
    can turn closeness into a score rather than a yes/no.
    """

    if not query:
        return []

    response = get_collection().query(
        query_embeddings=get_model().encode([query]).tolist(),
        n_results=n_results
    )

    return [
        (document, distance)
        for document, distance in zip(
            response["documents"][0], response["distances"][0]
        )
        if distance <= MAX_DISTANCE
    ]


def find_matching_fields(query, n_results=10):
    """
    Return the CIP field names closest in meaning to the student's
    wording, nearest first. Empty if nothing is close enough.
    """

    if not query:
        return []

    collection = get_collection()

    embedding = get_model().encode([query]).tolist()

    response = collection.query(
        query_embeddings=embedding,
        n_results=n_results
    )

    documents = response["documents"][0]
    distances = response["distances"][0]

    return [
        document
        for document, distance in zip(documents, distances)
        if distance <= MAX_DISTANCE
    ]


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":

    # The model is fetched once here, not at request time. truststore
    # makes the download work behind a TLS-inspecting corporate proxy.
    import truststore

    truststore.inject_into_ssl()

    print("Downloading embedding model (first run only)...")
    SentenceTransformer(EMBEDDING_MODEL)

    print("Building field index...")
    count = build_field_index()

    print(f"Indexed {count} fields of study into {CHROMA_DIR}")
