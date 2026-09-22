import numpy as np
from dotenv import load_dotenv
from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Response,
    UploadFile
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src import auth
from src.data_loader import load_cost_data, load_university_data
from src.llm_extractor import extract_preferences
from src.news import fetch_news
from src.rag import answer_question
from src.recommender import (
    calculate_score,
    get_institution_detail,
    get_comparable,
    get_india_detail,
    get_international_detail,
    get_international_university_names,
    get_us_filter_options,
    prepare_recommendations,
    recommend_india_institutes,
    recommend_us_institutions,
    search_all,
    search_india,
    search_institutions,
    search_international
)
from src.resume_parser import extract_text_from_pdf
from src.reviews import get_reviews

load_dotenv()

app = FastAPI(title="EduBridge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

auth.init_auth_tables()


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================

class TextPreferencesRequest(BaseModel):
    text: str


class RecommendationRequest(BaseModel):
    country: str | None = None
    field_of_study: str | None = None
    fee_min: float | None = None
    fee_max: float | None = None
    academic_weight: int = 70
    sort: str = "outcomes"


class SignupRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class ChatRequest(BaseModel):
    question: str


# ============================================================
# AUTHENTICATION
# ============================================================

def current_user(edubridge_session: str | None = Cookie(default=None)):
    """Resolves the signed session cookie, or None when signed out."""

    if not edubridge_session:
        return None

    return auth.read_session_token(edubridge_session)


def require_user(user=Depends(current_user)):
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in.")

    return user


def require_admin(user=Depends(require_user)):
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Admins only.")

    return user


def set_session_cookie(response: Response, user_id: int):
    response.set_cookie(
        auth.SESSION_COOKIE,
        auth.create_session_token(user_id),
        max_age=auth.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax"
    )


@app.post("/api/auth/signup")
def signup(request: SignupRequest, response: Response):
    try:
        user = auth.create_user(
            request.email,
            request.password,
            request.full_name
        )

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    set_session_cookie(response, user["user_id"])

    return user


@app.post("/api/auth/login")
def login(request: LoginRequest, response: Response):
    user = auth.authenticate(request.email, request.password)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password."
        )

    set_session_cookie(response, user["user_id"])

    return user


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(auth.SESSION_COOKIE)

    return {"ok": True}


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return user or {}


# ============================================================
# HELPERS
# ============================================================

def records(df):
    return df.replace({np.nan: None}).to_dict(orient="records")


# ============================================================
# FILTERS
# ============================================================

@app.get("/api/filters")
def get_filters():
    university_df = load_university_data()

    global_countries = sorted(
        university_df["Location"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    us_options = get_us_filter_options()

    return {
        "countries": global_countries,
        "fields_of_study": us_options["fields_of_study"],
        "min_fee": us_options["min_fee"],
        "max_fee": us_options["max_fee"]
    }


# ============================================================
# PREFERENCE EXTRACTION
# ============================================================

@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    file_bytes = await file.read()

    text = extract_text_from_pdf(file_bytes)

    if not text:
        raise HTTPException(
            status_code=422,
            detail="Could not extract any text from that PDF."
        )

    try:
        preferences = extract_preferences(text)
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error))

    return preferences.model_dump()


@app.post("/api/preferences/extract")
def extract_from_text(request: TextPreferencesRequest):
    try:
        preferences = extract_preferences(request.text)
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error))

    return preferences.model_dump()


# ============================================================
# RECOMMENDATIONS
# ============================================================

@app.post("/api/recommendations")
def get_recommendations(
    request: RecommendationRequest,
    user=Depends(current_user)
):

    if user:
        auth.record_history(
            user["user_id"],
            "search",
            request.field_of_study or "any field",
            f"{request.country or 'any country'}"
        )

    if request.country == "United States":

        results, matched_fields = recommend_us_institutions(
            field_of_study=request.field_of_study,
            fee_min=request.fee_min,
            fee_max=request.fee_max,
            sort=request.sort
        )

        return {
            "source": "us_institutions",
            "fee_field_applied": True,
            "matched_fields": matched_fields,
            "results": records(results.head(30))
        }

    if request.country == "India":
        return {
            "source": "india_institutes",
            "fee_field_applied": True,
            "matched_fields": [],
            "results": recommend_india_institutes(request.field_of_study)
        }

    university_df = load_university_data()
    cost_df = load_cost_data()

    merged_df = prepare_recommendations(university_df, cost_df)

    if request.country:
        merged_df = merged_df[
            merged_df["Location"] == request.country
        ]

    if len(merged_df) == 0:
        return {
            "source": "global",
            "fee_field_applied": False,
            "matched_fields": [],
            "results": []
        }

    academic_weight = request.academic_weight
    affordability_weight = 100 - academic_weight

    scored = calculate_score(
        merged_df,
        academic_weight=academic_weight,
        affordability_weight=affordability_weight
    )

    rows = records(scored.head(30))

    # Only some ranked universities have cost data behind them; flag the
    # ones that do, so the UI never links through to an empty page.
    known = get_international_university_names()

    for row in rows:
        row["has_detail"] = str(row.get("University", "")).lower() in known

    return {
        "source": "global",
        "fee_field_applied": False,
        "matched_fields": [],
        "results": rows
    }


# ============================================================
# UNIVERSITY DETAIL / COMPARE
# ============================================================

def institution_payload(unitid: int, include_reviews: bool = True):
    detail = get_institution_detail(unitid)

    if detail is None:
        raise HTTPException(status_code=404, detail="University not found.")

    if include_reviews:
        detail["reviews"] = get_reviews(detail["institution_name"])

    return detail


@app.get("/api/search")
def search(q: str):
    return {"results": search_institutions(q)}


@app.get("/api/search/india")
def search_india_endpoint(q: str):
    return {"results": search_india(q)}


@app.get("/api/india/{institute}")
def india_detail(institute: str, user=Depends(current_user)):
    detail = get_india_detail(institute)

    if detail is None:
        raise HTTPException(status_code=404, detail="Institute not found.")

    detail["reviews"] = get_reviews(detail["institute"])

    if user:
        auth.record_history(
            user["user_id"], "view", detail["institute"], "India"
        )

    return detail


@app.get("/api/search/international")
def search_intl(q: str):
    return {"results": search_international(q)}


@app.get("/api/international/{university_name}")
def international_detail(university_name: str, user=Depends(current_user)):
    detail = get_international_detail(university_name)

    if detail is None:
        raise HTTPException(status_code=404, detail="University not found.")

    detail["reviews"] = get_reviews(detail["university_name"])

    if user:
        auth.record_history(
            user["user_id"],
            "view",
            detail["university_name"],
            detail["country"]
        )

    return detail


@app.get("/api/university/{unitid}")
def university_detail(unitid: int, user=Depends(current_user)):
    detail = institution_payload(unitid)

    if user:
        auth.record_history(
            user["user_id"],
            "view",
            detail["institution_name"],
            f"unitid={unitid}"
        )

    return detail


@app.get("/api/compare")
def compare(a: str, b: str):
    """Compares any two universities, including across countries."""

    try:
        left, right = get_comparable(a), get_comparable(b)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    if left is None or right is None:
        raise HTTPException(status_code=404, detail="University not found.")

    return {"a": left, "b": right}


@app.get("/api/search/all")
def search_everywhere(q: str):
    return {"results": search_all(q)}


# ============================================================
# NEWS
# ============================================================

@app.get("/api/news")
def news():
    return {"articles": fetch_news()}


# ============================================================
# RAG CHAT
# ============================================================

@app.post("/api/chat")
def chat(request: ChatRequest, user=Depends(current_user)):
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="Ask a question first.")

    try:
        result = answer_question(request.question)

    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))

    if user:
        auth.record_history(user["user_id"], "chat", request.question)

    return result


# ============================================================
# HISTORY
# ============================================================

@app.get("/api/history")
def history(user=Depends(require_user)):
    return {"history": auth.get_history(user["user_id"])}


# ============================================================
# ADMIN
# ============================================================

@app.get("/api/admin/stats")
def admin_stats(user=Depends(require_admin)):
    from src.db import get_connection

    conn = get_connection()

    def scalar(query):
        return conn.execute(query).fetchone()[0]

    stats = {
        "total_users": scalar("SELECT COUNT(*) FROM users"),
        "total_queries": scalar("SELECT COUNT(*) FROM search_history"),
        "indexed_institutions": scalar("SELECT COUNT(*) FROM us_institutions"),
        "recent_users": [
            dict(row)
            for row in conn.execute(
                """
                SELECT email, full_name, is_admin, created_at
                FROM users ORDER BY user_id DESC LIMIT 10
                """
            )
        ],
        "popular_colleges": [
            dict(row)
            for row in conn.execute(
                """
                SELECT query_text AS name, COUNT(*) AS views
                FROM search_history WHERE kind = 'view'
                GROUP BY query_text ORDER BY views DESC LIMIT 10
                """
            )
        ]
    }

    conn.close()

    return stats


# ============================================================
# STATIC FRONTEND
# ============================================================

app.mount(
    "/",
    StaticFiles(directory="frontend", html=True),
    name="frontend"
)
