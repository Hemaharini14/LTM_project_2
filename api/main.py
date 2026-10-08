from typing import Any

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
from src.matching import score_rows
from src.news import fetch_news
from src.rag import answer_question, explain_match, summarize_recommendations
from src.accommodation import geocode, geocode_city, get_accommodation_listings
from src.flights import (
    FlightSearchError,
    get_booking_links,
    resolve_destination_airport_candidates,
    search_airports,
    search_round_trip,
)
from src.recommender import (
    calculate_score,
    cheaper_international,
    get_institution_detail,
    get_comparable,
    get_india_detail,
    get_globe_universities,
    get_international_detail,
    get_international_university_names,
    get_us_filter_options,
    parse_compare_key,
    prepare_recommendations,
    recommend_india_institutes,
    recommend_us_institutions,
    search_all,
    search_india,
    search_institutions,
    search_international
)
from src.resume_parser import ResumeParseError, extract_text_from_pdf
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


class ExplainRequest(BaseModel):
    unitid: int
    field_of_study: str | None = None
    fee_min: float | None = None
    fee_max: float | None = None
    country: str | None = None


class SummaryRequest(BaseModel):
    field_of_study: str | None = None
    fee_min: float | None = None
    fee_max: float | None = None
    country: str | None = None
    results: list[dict[str, Any]]


class SaveRequest(BaseModel):
    key: str


class FlightSearchRequest(BaseModel):
    origin_code: str
    key: str
    departure_date: str
    return_date: str
    adults: int = 1


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

    try:
        text = extract_text_from_pdf(file_bytes)
    except ResumeParseError as error:
        raise HTTPException(status_code=422, detail=str(error))

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

        results, scored_fields = recommend_us_institutions(
            field_of_study=request.field_of_study,
            fee_min=request.fee_min,
            fee_max=request.fee_max,
            sort=request.sort
        )

        # A broad field like "business" genuinely matches most four-year
        # colleges, so the SQL filter alone leaves thousands of rows sorted
        # by raw earnings. Truncating to 30 at that point buries schools
        # strongly matched to the field under elite schools that merely
        # also offer something adjacent. Each row carries the fields it
        # offers so the score can measure how close its own programmes
        # are to what was asked for, and — when a field was given — that
        # closeness decides what makes the top 30, not earnings alone.
        rows = records(results)

        for row in rows:
            row["matched_fields"] = (row.pop("all_fields", "") or "").replace(",", "|")

        rows = score_rows(rows, {
            "matched_distances": dict(scored_fields),
            "fee_min": request.fee_min,
            "fee_max": request.fee_max,
            "country": request.country
        })

        if scored_fields and request.sort != "cheapest":
            def course_match_score(row):
                for dimension in row["match"]["dimensions"]:
                    if dimension["label"] == "Course match":
                        return dimension["score"]
                return -1

            rows.sort(key=course_match_score, reverse=True)

        rows = rows[:30]

        return {
            "source": "us_institutions",
            "fee_field_applied": True,
            "matched_fields": [name for name, _ in scored_fields],
            "results": rows
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


@app.post("/api/recommendations/explain")
def explain_recommendation(request: ExplainRequest):
    try:
        explanation = explain_match(request.unitid, request.model_dump())

    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))

    if explanation is None:
        raise HTTPException(status_code=404, detail="University not found.")

    return {"explanation": explanation}


@app.post("/api/recommendations/summary")
def summarize(request: SummaryRequest):
    try:
        summary = summarize_recommendations(request.results, request.model_dump())

    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))

    if summary is None:
        raise HTTPException(status_code=400, detail="No results to summarize.")

    return {"summary": summary}


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


@app.get("/api/accommodation")
def accommodation(key: str):
    """
    Illustrative sample accommodation listings for one university, plus
    whatever real housing-cost figure exists to anchor them to. Takes
    the same "us:<unitid>" / "intl:<name>" / "india:<institute>" key
    used everywhere else a university is identified across sources.
    """

    try:
        kind, value = parse_compare_key(key)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    base_monthly_rent = None
    city = None
    lat = lon = None

    if kind == "us":
        detail = get_institution_detail(int(value))

        if detail is None:
            raise HTTPException(status_code=404, detail="University not found.")

        base_monthly_rent = detail["housing_context"].get("monthly")

        if base_monthly_rent is None:
            estimate = detail["estimates"].get("roomboard_off_campus")
            base_monthly_rent = round(estimate["value"] / 12) if estimate else None

        city = detail["city"]
        lat, lon = detail.get("latitude"), detail.get("longitude")

    elif kind == "intl":
        detail = get_international_detail(value)

        if detail is None:
            raise HTTPException(status_code=404, detail="University not found.")

        base_monthly_rent = detail["rent_usd_monthly"]
        city = detail["city"]
        lat, lon = detail.get("latitude"), detail.get("longitude")

    elif kind == "india":
        detail = get_india_detail(value)

        if detail is None:
            raise HTTPException(status_code=404, detail="Institute not found.")

        # No accommodation cost data, and no stored coordinates either,
        # exist for India in this dataset — geocode the institute name
        # itself to still get a real search point for real listings.
        resolved = geocode(f"{value}, India")

        if resolved is not None:
            lat, lon = resolved

    listings, has_real_baseline, is_real_data = get_accommodation_listings(
        key, lat=lat, lon=lon, base_monthly_rent=base_monthly_rent, city=city
    )

    return {
        "listings": listings,
        "is_real_data": is_real_data,
        "has_real_baseline": has_real_baseline,
        "real_monthly_baseline": base_monthly_rent
    }


@app.get("/api/accommodation/cheaper-international")
def cheaper_international_endpoint(country: str, budget: float, exclude: str | None = None):
    return {"alternatives": cheaper_international(country, budget, exclude_name=exclude)}


def _destination_context(kind: str, value: str):
    """The real city, country and coordinates to resolve a university's
    airport from. Coordinates feed the Geoapify-based fallback in
    resolve_destination_airport_candidates() for towns with no airport of their
    own; the country disambiguates a city name that collides across
    countries (Cambridge, MA vs Cambridge, UK — a real example this
    app hit)."""

    if kind == "us":
        detail = get_institution_detail(int(value))

        if not detail:
            return None

        return {
            "city": detail["city"], "country": "United States",
            "lat": detail.get("latitude"), "lon": detail.get("longitude"),
        }

    if kind == "intl":
        detail = get_international_detail(value)

        if not detail:
            return None

        return {
            "city": detail["city"], "country": detail["country"],
            "lat": detail.get("latitude"), "lon": detail.get("longitude"),
        }

    if kind == "india":
        # No stored city or coordinates for India — geocode the
        # institute name itself for both.
        resolved = geocode(f"{value}, India")
        city = geocode_city(f"{value}, India")

        return {
            "city": city, "country": "India",
            "lat": resolved[0] if resolved else None,
            "lon": resolved[1] if resolved else None,
        }

    return None


@app.get("/api/flights/airports")
def flight_airports(q: str):
    try:
        return {"airports": search_airports(q)}
    except FlightSearchError as error:
        raise HTTPException(status_code=502, detail=str(error))


@app.post("/api/flights/search")
def flight_search(request: FlightSearchRequest):
    try:
        kind, value = parse_compare_key(request.key)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    context = _destination_context(kind, value)

    if not context or not context["city"]:
        raise HTTPException(
            status_code=404,
            detail="Couldn't determine a destination city for this university."
        )

    candidates = resolve_destination_airport_candidates(
        context["city"], context["country"], context["lat"], context["lon"]
    )

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=f"No airport found near {context['city']}."
        )

    # The nearest airport to a smaller university town sometimes has
    # no real international fares at all (Oxford's own small airport
    # has none — students actually fly via London), so each candidate
    # is tried in order rather than trusting the first one blindly.
    last_error = None

    for airport in candidates:
        try:
            itineraries = search_round_trip(
                request.origin_code, airport["code"],
                request.departure_date, request.return_date,
                adults=request.adults
            )
        except FlightSearchError as error:
            last_error = error
            continue

        return {"destination_airport": airport, "itineraries": itineraries}

    raise HTTPException(status_code=502, detail=str(last_error))


@app.get("/api/flights/booking-links")
def flight_booking_links(ignav_id: str):
    try:
        return {"links": get_booking_links(ignav_id)}
    except FlightSearchError as error:
        raise HTTPException(status_code=502, detail=str(error))


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
# PUBLIC STATS
# ============================================================

@app.get("/api/stats")
def stats():
    """Real counts for the landing hero — no signin required."""

    from src.db import get_connection

    conn = get_connection()

    def scalar(query):
        return conn.execute(query).fetchone()[0]

    payload = {
        "universities": (
            scalar("SELECT COUNT(*) FROM us_institutions")
            + scalar("SELECT COUNT(DISTINCT university_name) FROM international_programs")
            + scalar("SELECT COUNT(DISTINCT institute) FROM india_cutoffs")
        ),
        "countries": scalar(
            "SELECT COUNT(DISTINCT country) FROM international_programs"
        ),
        "programmes": (
            scalar("SELECT COUNT(*) FROM us_fields_of_study")
            + scalar("SELECT COUNT(*) FROM international_programs")
            + scalar("SELECT COUNT(*) FROM india_cutoffs")
        )
    }

    conn.close()

    return payload


@app.get("/api/globe")
def globe():
    """Universities with real coordinates for the 3D explorer."""

    return {"universities": get_globe_universities()}


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
# SAVED UNIVERSITIES
# ============================================================

@app.post("/api/saved")
def save_university(request: SaveRequest, user=Depends(require_user)):
    auth.save_university(user["user_id"], request.key)
    return {"ok": True}


@app.post("/api/saved/remove")
def unsave_university(request: SaveRequest, user=Depends(require_user)):
    auth.unsave_university(user["user_id"], request.key)
    return {"ok": True}


@app.get("/api/saved")
def list_saved(user=Depends(require_user)):
    keys = auth.get_saved_keys(user["user_id"])

    # A saved key can go stale if the underlying record disappears (e.g.
    # a dataset rebuild), so resolution failures are dropped rather than
    # shown as broken cards.
    saved = []

    for key in keys:
        try:
            entity = get_comparable(key)
        except ValueError:
            continue

        if entity is not None:
            entity["key"] = key
            saved.append(entity)

    return {"saved": saved}


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
