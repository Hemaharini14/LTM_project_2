import pandas as pd

from src.db import get_connection
from src.vector_store import find_matching_fields


def prepare_recommendations(university_df, cost_df):
    """
    Prepare university and cost-of-living data
    for the EduBridge recommendation engine.
    """

    universities = university_df.copy()
    costs = cost_df.copy()

    # --------------------------------------------------
    # CLEAN COLUMN NAMES
    # --------------------------------------------------

    universities.columns = (
        universities.columns
        .astype(str)
        .str.strip()
    )

    costs.columns = (
        costs.columns
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------
    # STANDARDIZE COUNTRY NAMES
    # --------------------------------------------------

    country_mapping = {
        "Hong Kong": "Hong Kong (China)",
        "Czechia": "Czech Republic",
        "Bosnia and Herzegovina":
            "Bosnia And Herzegovina",
        "Kosovo":
            "Kosovo (Disputed Territory)"
    }

    universities["Location"] = (
        universities["Location"]
        .astype(str)
        .str.strip()
        .replace(country_mapping)
    )

    costs["Country"] = (
        costs["Country"]
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------
    # CONVERT NUMERIC COLUMNS
    # --------------------------------------------------

    university_numeric_columns = [
        "Overall Teaching Score",
        "Research Score",
        "Research Quality",
        "Industry Income Score",
        "International Outlook Score",
        "Overall Score",
        "Rank"
    ]

    for column in university_numeric_columns:

        if column in universities.columns:

            universities[column] = pd.to_numeric(
                universities[column],
                errors="coerce"
            )

    cost_numeric_columns = [
        "Cost of Living Index",
        "Rent Index",
        "Cost of Living Plus Rent Index",
        "Groceries Index",
        "Restaurant Price Index",
        "Local Purchasing Power Index"
    ]

    for column in cost_numeric_columns:

        if column in costs.columns:

            costs[column] = pd.to_numeric(
                costs[column],
                errors="coerce"
            )

    # --------------------------------------------------
    # AVOID RANK COLUMN CONFLICT
    # --------------------------------------------------

    if "Rank" in costs.columns:
        costs = costs.drop(
            columns=["Rank"]
        )

    # --------------------------------------------------
    # MERGE
    # --------------------------------------------------

    merged = universities.merge(
        costs,
        left_on="Location",
        right_on="Country",
        how="left"
    )

    # --------------------------------------------------
    # RENAME UNIVERSITY RANK
    # --------------------------------------------------

    if "Rank" in merged.columns:

        merged = merged.rename(
            columns={
                "Rank": "University Rank"
            }
        )

    return merged


def calculate_score(
    df,
    academic_weight=70,
    affordability_weight=30
):
    """
    Calculate the EduBridge weighted recommendation score.
    """

    result = df.copy()

    # --------------------------------------------------
    # ACADEMIC SCORE
    # --------------------------------------------------

    result["Academic Score"] = pd.to_numeric(
        result["Overall Score"],
        errors="coerce"
    ).fillna(0)

    # --------------------------------------------------
    # AFFORDABILITY SCORE
    # --------------------------------------------------

    if "Cost of Living Index" in result.columns:

        cost = pd.to_numeric(
            result["Cost of Living Index"],
            errors="coerce"
        )

        max_cost = cost.max()

        if pd.notna(max_cost) and max_cost > 0:

            result["Affordability Score"] = (
                100
                -
                (
                    cost
                    / max_cost
                    * 100
                )
            )

        else:

            result["Affordability Score"] = 0

    else:

        result["Affordability Score"] = 0

    # --------------------------------------------------
    # FINAL EDUBRIDGE SCORE
    # --------------------------------------------------

    result["EduBridge Score"] = (
        result["Academic Score"]
        * academic_weight
        / 100
        +
        result["Affordability Score"]
        * affordability_weight
        / 100
    )

    # --------------------------------------------------
    # SORT
    # --------------------------------------------------

    result = result.sort_values(
        by="EduBridge Score",
        ascending=False
    )

    return result.reset_index(
        drop=True
    )


# ============================================================
# US INSTITUTIONS (College Scorecard — fee / field matching)
# ============================================================

def recommend_us_institutions(
    field_of_study=None,
    fee_min=None,
    fee_max=None,
    degree_granting_only=True,
    sort="outcomes"
):
    """
    Match US institutions by tuition range and field of study, using
    the real College Scorecard data in us_institutions /
    us_fields_of_study.

    The student's own wording is resolved to real CIP field names
    semantically, so "Artificial Intelligence" reaches Computer
    Science programmes even though no CIP field carries that name.

    Returns (results, matched_fields).
    """

    matched_fields = find_matching_fields(field_of_study)

    if field_of_study and not matched_fields:
        return pd.DataFrame(), []

    conditions = [
        "(? IS NULL OR i.tuition_out_state >= ?)",
        "(? IS NULL OR i.tuition_out_state <= ?)"
    ]

    params = [fee_min, fee_min, fee_max, fee_max]

    # Non-degree institutions rarely report fees, housing or admissions,
    # so including them by default fills results with half-empty pages.
    if degree_granting_only:
        conditions.append("i.grants_degree = 1")

    # Everything here already sits inside the student's budget, so ordering
    # by price alone just surfaces the cheapest option rather than the best
    # one they can afford. Graduate earnings is the outcome they asked about.
    order_clause = (
        "ORDER BY i.tuition_out_state ASC"
        if sort == "cheapest"
        else "ORDER BY i.median_earnings_10yr DESC, i.tuition_out_state ASC"
    )

    if matched_fields:

        placeholders = ", ".join("?" * len(matched_fields))

        conditions.append(
            f"""
            i.unitid IN (
                SELECT unitid
                FROM us_fields_of_study
                WHERE cip_description IN ({placeholders})
            )
            """
        )

        params.extend(matched_fields)

    query = f"""
        SELECT DISTINCT
            i.unitid,
            i.institution_name,
            i.city,
            i.state,
            i.control_label,
            i.tuition_in_state,
            i.tuition_out_state,
            i.roomboard_on_campus
        FROM us_institutions i
        WHERE {" AND ".join(conditions)}
        {order_clause}
    """

    conn = get_connection()

    result = pd.read_sql(query, conn, params=params)

    conn.close()

    return result, matched_fields


def search_institutions(term, limit=20):
    """Name search across all US institutions, for pickers and compare."""

    if not term or len(term.strip()) < 2:
        return []

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT unitid, institution_name, city, state
        FROM us_institutions
        WHERE institution_name LIKE ?
        ORDER BY
            CASE WHEN institution_name LIKE ? THEN 0 ELSE 1 END,
            institution_name
        LIMIT ?
        """,
        (f"%{term.strip()}%", f"{term.strip()}%", limit)
    ).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def get_institution_detail(unitid):
    """
    Everything the college detail page shows for one US institution:
    costs, admission difficulty, housing, outcomes, fields offered,
    and its world ranking when the name matches a ranked university.
    """

    conn = get_connection()

    institution = conn.execute(
        "SELECT * FROM us_institutions WHERE unitid = ?",
        (unitid,)
    ).fetchone()

    if institution is None:
        conn.close()
        return None

    detail = dict(institution)

    fields = conn.execute(
        """
        SELECT DISTINCT cip_description, credential_description
        FROM us_fields_of_study
        WHERE unitid = ?
        ORDER BY cip_description
        """,
        (unitid,)
    ).fetchall()

    detail["fields_of_study"] = [dict(row) for row in fields]

    # The rankings tables key on name, not UNITID, so this only
    # resolves where the spelling happens to line up.
    ranking = conn.execute(
        """
        SELECT university_rank, overall_score, teaching_score,
               research_score, international_outlook_score
        FROM universities
        WHERE LOWER(university_name) = LOWER(?)
        """,
        (institution["institution_name"],)
    ).fetchone()

    detail["ranking"] = dict(ranking) if ranking else None
    detail["aid"] = aid_summary(institution)
    detail["estimates"] = estimate_missing_costs(conn, institution)
    detail["housing_context"] = housing_context(conn, institution)

    conn.close()

    return detail


# Cost fields cluster tightly by state and sector, so a peer median is a
# defensible estimate. Selectivity and outcomes do not — an open-admission
# college and a highly selective one sit in the same state and sector — so
# admission rate, SAT/ACT and earnings are never estimated.
ESTIMATABLE_COST_FIELDS = (
    "tuition_in_state",
    "tuition_out_state",
    "roomboard_on_campus",
    "roomboard_off_campus",
    "books_supplies",
    "cost_of_attendance"
)


def median(values):
    ordered = sorted(v for v in values if v is not None)

    if not ordered:
        return None

    middle = len(ordered) // 2

    if len(ordered) % 2:
        return ordered[middle]

    return (ordered[middle - 1] + ordered[middle]) / 2


# Federal grants and loans are limited to US citizens and eligible
# non-citizens, so these figures describe domestic students. The UI must
# say so rather than implying an international applicant would pay this.
NET_PRICE_BANDS = [
    ("net_price_0_30k", "Under $30,000"),
    ("net_price_30_48k", "$30,001 - $48,000"),
    ("net_price_48_75k", "$48,001 - $75,000"),
    ("net_price_75_110k", "$75,001 - $110,000"),
    ("net_price_110k_plus", "$110,000+")
]


def aid_summary(institution):
    """Net price after aid, by family income, plus grant and debt context."""

    bands = [
        {"label": label, "net_price": institution[field]}
        for field, label in NET_PRICE_BANDS
        if institution[field] is not None
    ]

    sticker = institution["cost_of_attendance"]
    cheapest = min((b["net_price"] for b in bands), default=None)

    discount = None
    if sticker and cheapest is not None and sticker > 0:
        discount = round((sticker - cheapest) / sticker * 100)

    return {
        "average_net_price": institution["net_price_avg"],
        "bands": bands,
        "pell_grant_percent": institution["pell_grant_percent"],
        "median_debt": institution["median_debt"],
        "sticker_cost": sticker,
        "max_discount_percent": discount,
        "domestic_only": True
    }


def estimate_missing_costs(conn, institution):
    """
    Fill missing cost fields with the median of comparable institutions
    (same state and sector). Every estimate carries the basis it came
    from so the page can label it rather than pass it off as reported.
    """

    missing = [
        field
        for field in ESTIMATABLE_COST_FIELDS
        if institution[field] is None
    ]

    if not missing:
        return {}

    peers = conn.execute(
        f"""
        SELECT {", ".join(ESTIMATABLE_COST_FIELDS)}
        FROM us_institutions
        WHERE state = ?
          AND control_label = ?
          AND grants_degree = 1
          AND unitid != ?
        """,
        (
            institution["state"],
            institution["control_label"],
            institution["unitid"]
        )
    ).fetchall()

    if len(peers) < 3:
        return {}

    estimates = {}

    for field in missing:

        value = median([peer[field] for peer in peers])

        if value is None:
            continue

        estimates[field] = {
            "value": round(value),
            "basis": (
                f"median of {len(peers)} "
                f"{(institution['control_label'] or 'similar').lower()} "
                f"universities in {institution['state']}"
            )
        }

    return estimates


def housing_context(conn, institution):
    """
    Puts this university's off-campus housing cost in context against its
    state and the national picture, using real reported figures only.
    """

    reported = institution["roomboard_off_campus"]

    state_median = median([
        row["roomboard_off_campus"]
        for row in conn.execute(
            """
            SELECT roomboard_off_campus FROM us_institutions
            WHERE state = ? AND grants_degree = 1
            """,
            (institution["state"],)
        )
    ])

    national_median = median([
        row["roomboard_off_campus"]
        for row in conn.execute(
            """
            SELECT roomboard_off_campus FROM us_institutions
            WHERE grants_degree = 1
            """
        )
    ])

    def compare(reference):
        if reported is None or not reference:
            return None

        return round((reported - reference) / reference * 100)

    return {
        "annual": reported,
        "monthly": round(reported / 12) if reported else None,
        "academic_year_monthly": round(reported / 9) if reported else None,
        "state_median": round(state_median) if state_median else None,
        "national_median": round(national_median) if national_median else None,
        "vs_state_percent": compare(state_median),
        "vs_national_percent": compare(national_median)
    }


def get_us_filter_options():
    """
    Distinct fields of study and tuition bounds, for populating
    the fee-range slider and field-of-study input.
    """

    conn = get_connection()

    fields = pd.read_sql(
        """
        SELECT DISTINCT cip_description
        FROM us_fields_of_study
        WHERE cip_description IS NOT NULL
        ORDER BY cip_description ASC
        """,
        conn
    )["cip_description"].tolist()

    bounds = pd.read_sql(
        """
        SELECT
            MIN(tuition_out_state) AS min_fee,
            MAX(tuition_out_state) AS max_fee
        FROM us_institutions
        WHERE tuition_out_state IS NOT NULL
        """,
        conn
    ).iloc[0]

    conn.close()

    return {
        "fields_of_study": fields,
        "min_fee": bounds["min_fee"],
        "max_fee": bounds["max_fee"]
    }

# ============================================================
# INTERNATIONAL PROGRAMMES (non-US)
# ============================================================

# Admission statistics are a US convention. Elsewhere the published
# equivalent is an entry requirement, so we explain each country's own
# system rather than inventing a percentage that nobody reports.
ADMISSION_SYSTEMS = {
    "United Kingdom": (
        "UK universities publish entry requirements as A-level grades or "
        "UCAS tariff points rather than an acceptance rate. Applications "
        "go through UCAS, and providers make conditional offers."
    ),
    "Australia": (
        "Australian universities admit on ATAR cut-off scores (or an "
        "equivalent for international qualifications) published per "
        "course, rather than an overall acceptance rate."
    ),
    "India": (
        "Indian admissions are driven by national entrance exams — JEE "
        "Main and Advanced for engineering, NEET for medicine, CAT for "
        "management. Institutions publish closing ranks and cut-offs "
        "instead of acceptance rates."
    ),
    "Singapore": (
        "Singapore universities publish an Indicative Grade Profile "
        "(IGP) — the 10th to 90th percentile grades of admitted "
        "students — rather than an acceptance rate."
    ),
    "France": (
        "French public universities are largely non-selective at "
        "bachelor's level and tuition is set by national decree. "
        "Undergraduate applications go through Parcoursup; the grandes "
        "écoles select by competitive concours."
    ),
    "Germany": (
        "German public universities charge little or no tuition and "
        "admit on your qualification meeting the Hochschulzugangs"
        "berechtigung standard; competitive subjects use a numerus "
        "clausus grade cut-off."
    )
}


def search_international(term, limit=20):
    """Name search across non-US universities."""

    if not term or len(term.strip()) < 2:
        return []

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT university_name, country, city,
               MIN(tuition_usd) AS from_tuition,
               COUNT(*) AS programmes
        FROM international_programs
        WHERE university_name LIKE ? AND country != 'United States'
        GROUP BY university_name, country, city
        ORDER BY
            CASE WHEN university_name LIKE ? THEN 0 ELSE 1 END,
            university_name
        LIMIT ?
        """,
        (f"%{term.strip()}%", f"{term.strip()}%", limit)
    ).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def get_international_detail(university_name):
    """
    Everything held for one non-US university: its programmes with
    tuition, the recurring costs of studying there, and how admission
    works in that country.
    """

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT * FROM international_programs
        WHERE LOWER(university_name) = LOWER(?)
        ORDER BY level, program
        """,
        (university_name,)
    ).fetchall()

    if not rows:
        conn.close()
        return None

    first = dict(rows[0])
    country = first["country"]

    tuitions = [
        row["tuition_usd"]
        for row in rows
        if row["tuition_usd"] is not None
    ]

    ranking = conn.execute(
        """
        SELECT university_rank, overall_score, teaching_score,
               research_score, international_outlook_score
        FROM universities
        WHERE LOWER(university_name) = LOWER(?)
        """,
        (first["university_name"],)
    ).fetchone()

    country_costs = conn.execute(
        """
        SELECT cost_of_living_index, rent_index
        FROM countries WHERE country_name = ?
        """,
        (country,)
    ).fetchone()

    conn.close()

    rent_monthly = first["rent_usd_monthly"]

    return {
        "university_name": first["university_name"],
        "country": country,
        "city": first["city"],
        "tuition_min": min(tuitions) if tuitions else None,
        "tuition_max": max(tuitions) if tuitions else None,
        "living_cost_index": first["living_cost_index"],
        "rent_usd_monthly": rent_monthly,
        "rent_usd_annual": round(rent_monthly * 12) if rent_monthly else None,
        "visa_fee_usd": first["visa_fee_usd"],
        "insurance_usd": first["insurance_usd"],
        "programs": [
            {
                "program": row["program"],
                "level": row["level"],
                "duration_years": row["duration_years"],
                "tuition_usd": row["tuition_usd"]
            }
            for row in rows
        ],
        "ranking": dict(ranking) if ranking else None,
        "country_cost_of_living_index": (
            country_costs["cost_of_living_index"] if country_costs else None
        ),
        "admission_system": ADMISSION_SYSTEMS.get(country)
    }


def get_international_university_names():
    """Lowercased names we hold cost data for, so the UI only links
    through to pages that will actually have something on them."""

    conn = get_connection()

    names = {
        row[0].lower()
        for row in conn.execute(
            "SELECT DISTINCT university_name FROM international_programs"
        )
    }

    conn.close()

    return names


# ============================================================
# INDIA (JoSAA cutoffs + published fee bands)
# ============================================================

# Matches the rate the international cost dataset uses, so Indian
# figures stay comparable with every other country in the app.
INR_PER_USD = 83

# Indian tuition is set by policy, not per-institute price lists: IIT
# B.Tech tuition is centrally fixed, NITs sit in a published band, and
# IIIT/GFTI vary too widely to state a single figure honestly. These are
# bands with their basis attached, never invented per-institute numbers.
INDIA_FEE_BANDS = {
    "IIT": {
        "annual_inr_min": 200000,
        "annual_inr_max": 200000,
        "note": (
            "B.Tech tuition is centrally fixed at Rs 1,00,000 per semester "
            "(Rs 2,00,000 a year) across all 23 IITs. Families earning under "
            "Rs 1 lakh a year, and SC/ST/PwD students, pay no tuition; those "
            "between Rs 1-5 lakh pay about a third. Hostel and mess are extra, "
            "bringing a four-year B.Tech to roughly Rs 9-14 lakh."
        )
    },
    "NIT": {
        "annual_inr_min": 125000,
        "annual_inr_max": 150000,
        "note": (
            "NIT B.Tech tuition runs about Rs 1.25-1.5 lakh a year for the "
            "general category and is set per institute, so confirm the exact "
            "figure on that NIT's own site. Hostel and mess are extra."
        )
    },
    "IIIT": {
        "annual_inr_min": None,
        "annual_inr_max": None,
        "note": (
            "IIIT fees vary widely between the centrally funded institutes "
            "and the public-private ones — check the institute's own fee page."
        )
    },
    "GFTI": {
        "annual_inr_min": None,
        "annual_inr_max": None,
        "note": (
            "Government-funded technical institutes set their own fees; "
            "check the institute's own fee page."
        )
    }
}


# Fee concessions at the centrally funded institutes are set by policy,
# not awarded per applicant, so they can be stated exactly.
INDIA_WAIVERS = {
    "IIT": [
        {"who": "SC, ST and PwD students", "benefit": "Full tuition waiver"},
        {"who": "Family income under Rs 1 lakh a year", "benefit": "Full tuition waiver"},
        {"who": "Family income Rs 1-5 lakh a year", "benefit": "Two-thirds waiver (about Rs 66,666 a year payable)"},
        {"who": "All students", "benefit": "MCM and institute merit-cum-means scholarships, applied for separately"}
    ],
    "NIT": [
        {"who": "SC, ST and PwD students", "benefit": "Tuition waiver"},
        {"who": "Economically weaker students", "benefit": "Institute fee concessions; terms vary by NIT"},
        {"who": "All students", "benefit": "Central Sector and state merit scholarships"}
    ]
}


def india_scholarships(institute_type):
    """Published concessions for this class of institute, or none."""

    return INDIA_WAIVERS.get(institute_type, [])


def search_india(term, limit=20):
    """Name search across institutes in the JoSAA cutoff data."""

    if not term or len(term.strip()) < 2:
        return []

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT institute, institute_type,
               COUNT(DISTINCT program) AS programmes,
               MIN(closing_rank) AS best_closing_rank
        FROM india_cutoffs
        WHERE institute LIKE ?
        GROUP BY institute, institute_type
        ORDER BY
            CASE WHEN institute LIKE ? THEN 0 ELSE 1 END,
            institute
        LIMIT ?
        """,
        (f"%{term.strip()}%", f"{term.strip()}%", limit)
    ).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def get_india_detail(institute):
    """
    Cutoffs and published fee band for one Indian institute. Cutoffs are
    reported for the open, gender-neutral seats, which is the figure most
    students plan against.
    """

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT program, quota, seat_type, gender,
               opening_rank, closing_rank, year
        FROM india_cutoffs
        WHERE LOWER(institute) = LOWER(?)
        ORDER BY closing_rank
        """,
        (institute,)
    ).fetchall()

    if not rows:
        conn.close()
        return None

    header = conn.execute(
        """
        SELECT institute, institute_type, year
        FROM india_cutoffs WHERE LOWER(institute) = LOWER(?) LIMIT 1
        """,
        (institute,)
    ).fetchone()

    ranking = conn.execute(
        """
        SELECT university_rank, overall_score
        FROM universities WHERE LOWER(university_name) = LOWER(?)
        """,
        (header["institute"],)
    ).fetchone()

    conn.close()

    band = INDIA_FEE_BANDS.get(header["institute_type"], {})

    def to_usd(amount):
        return round(amount / INR_PER_USD) if amount else None

    open_seats = [
        dict(row) for row in rows
        if row["seat_type"] == "OPEN" and row["gender"] == "Gender-Neutral"
    ]

    return {
        "institute": header["institute"],
        "institute_type": header["institute_type"],
        "country": "India",
        "cutoff_year": header["year"],
        "fee_band_inr_min": band.get("annual_inr_min"),
        "fee_band_inr_max": band.get("annual_inr_max"),
        "fee_band_usd_min": to_usd(band.get("annual_inr_min")),
        "fee_band_usd_max": to_usd(band.get("annual_inr_max")),
        "fee_note": band.get("note"),
        "scholarships": india_scholarships(header["institute_type"]),
        "exam": (
            "JEE Advanced"
            if header["institute_type"] == "IIT"
            else "JEE Main"
        ),
        "programs": open_seats or [dict(row) for row in rows],
        "total_cutoff_rows": len(rows),
        "ranking": dict(ranking) if ranking else None
    }


def recommend_india_institutes(field_of_study=None, limit=30):
    """
    Indian institutes ranked by how competitive their best branch is
    (lowest closing rank first), optionally filtered to a branch.

    Branch names here are JoSAA's own wording, so a plain text match is
    the right tool — the CIP vector index covers US field names only.
    """

    conditions = []
    params = []

    if field_of_study:
        conditions.append("program LIKE ?")
        params.append(f"%{field_of_study.strip()}%")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    conn = get_connection()

    rows = conn.execute(
        f"""
        SELECT institute, institute_type,
               COUNT(DISTINCT program) AS programmes,
               MIN(closing_rank) AS best_closing_rank
        FROM india_cutoffs
        {where}
        GROUP BY institute, institute_type
        ORDER BY best_closing_rank ASC
        LIMIT ?
        """,
        params + [limit]
    ).fetchall()

    conn.close()

    results = []

    for row in rows:
        band = INDIA_FEE_BANDS.get(row["institute_type"], {})
        item = dict(row)
        item["fee_band_inr_min"] = band.get("annual_inr_min")
        item["fee_band_usd_min"] = (
            round(band["annual_inr_min"] / INR_PER_USD)
            if band.get("annual_inr_min") else None
        )
        results.append(item)

    return results


# ============================================================
# CROSS-BORDER COMPARISON
# ============================================================

# Universities reach us in three different shapes, so comparison keys are
# typed: "us:166683", "intl:University of Oxford", "india:IIT Bombay".
def parse_compare_key(key):
    kind, _, value = str(key).partition(":")

    if kind not in {"us", "intl", "india"} or not value:
        raise ValueError(f"Unrecognised comparison key: {key}")

    return kind, value


def comparable_us(unitid):
    detail = get_institution_detail(int(unitid))

    if detail is None:
        return None

    def figure(field):
        if detail[field] is not None:
            return detail[field], False

        estimate = detail["estimates"].get(field)

        return (estimate["value"], True) if estimate else (None, False)

    tuition, tuition_est = figure("tuition_out_state")
    housing, housing_est = figure("roomboard_on_campus")
    books, _ = figure("books_supplies")

    entry = []

    if detail["admission_rate"] is not None:
        entry.append(f"{detail['admission_rate']:.1%} admitted")
    if detail["sat_average"] is not None:
        entry.append(f"SAT {detail['sat_average']:.0f}")

    return {
        "key": f"us:{unitid}",
        "name": detail["institution_name"],
        "country": "United States",
        "location": f"{detail['city']}, {detail['state']}",
        "kind": detail["control_label"],
        "rank": detail["ranking"]["university_rank"] if detail["ranking"] else None,
        "tuition_usd": tuition,
        "tuition_estimated": tuition_est,
        "housing_usd": housing,
        "housing_estimated": housing_est,
        "other_costs_usd": books,
        "entry": ", ".join(entry) or None,
        "entry_basis": "Admission rate and SAT" if entry else None,
        "outcome_usd": detail["median_earnings_10yr"],
        "link": f"university.html?unitid={unitid}"
    }


def comparable_international(name):
    detail = get_international_detail(name)

    if detail is None:
        return None

    other = sum(
        value for value in
        [detail["visa_fee_usd"], detail["insurance_usd"]]
        if value is not None
    ) or None

    return {
        "key": f"intl:{detail['university_name']}",
        "name": detail["university_name"],
        "country": detail["country"],
        "location": f"{detail['city']}, {detail['country']}",
        "kind": "University",
        "rank": detail["ranking"]["university_rank"] if detail["ranking"] else None,
        "tuition_usd": detail["tuition_min"],
        "tuition_estimated": False,
        "housing_usd": detail["rent_usd_annual"],
        "housing_estimated": False,
        "other_costs_usd": other,
        "entry": None,
        "entry_basis": detail["admission_system"],
        "outcome_usd": None,
        "link": f"university.html?intl={detail['university_name']}"
    }


def comparable_india(institute):
    detail = get_india_detail(institute)

    if detail is None:
        return None

    best = detail["programs"][0] if detail["programs"] else None

    return {
        "key": f"india:{detail['institute']}",
        "name": detail["institute"],
        "country": "India",
        "location": "India",
        "kind": detail["institute_type"],
        "rank": detail["ranking"]["university_rank"] if detail["ranking"] else None,
        "tuition_usd": detail["fee_band_usd_min"],
        "tuition_estimated": False,
        "housing_usd": None,
        "housing_estimated": False,
        "other_costs_usd": None,
        "entry": (
            f"{detail['exam']} closing rank {int(best['closing_rank']):,}"
            f" ({detail['cutoff_year']}, best branch)"
            if best else None
        ),
        "entry_basis": f"{detail['exam']} rank, not an acceptance rate",
        "outcome_usd": None,
        "link": f"university.html?india={detail['institute']}"
    }


def get_comparable(key):
    """Normalise any university into the same comparison shape."""

    kind, value = parse_compare_key(key)

    entity = {
        "us": comparable_us,
        "intl": comparable_international,
        "india": comparable_india
    }[kind](value)

    if entity is None:
        return None

    annual = [
        entity["tuition_usd"],
        entity["housing_usd"],
        entity["other_costs_usd"]
    ]

    entity["annual_total_usd"] = (
        round(sum(v for v in annual if v is not None))
        if any(v is not None for v in annual) else None
    )

    return entity


def search_all(term, limit=8):
    """One search box across US, international and Indian institutions."""

    results = []

    for row in search_institutions(term, limit):
        results.append({
            "key": f"us:{row['unitid']}",
            "label": f"{row['institution_name']} ({row['city']}, {row['state']})",
            "country": "United States"
        })

    for row in search_international(term, limit):
        results.append({
            "key": f"intl:{row['university_name']}",
            "label": f"{row['university_name']} ({row['country']})",
            "country": row["country"]
        })

    for row in search_india(term, limit):
        results.append({
            "key": f"india:{row['institute']}",
            "label": f"{row['institute']} ({row['institute_type']}, India)",
            "country": "India"
        })

    return results


# ============================================================
# GLOBE DATA
# ============================================================

def get_globe_universities(limit_per_source=420):
    """
    Universities positioned by coordinates precomputed at build time.
    Joining city names at request time meant scanning 50,250 cities per
    row, which took minutes; these columns are filled once instead.
    """

    conn = get_connection()

    international = conn.execute(
        """
        SELECT NULL AS unitid, university_name AS name, country, city,
               latitude, longitude,
               MIN(tuition_usd) AS tuition_usd,
               COUNT(*) AS programmes,
               'intl' AS source
        FROM international_programs
        WHERE latitude IS NOT NULL AND country != 'United States'
        GROUP BY university_name, country, city, latitude, longitude
        ORDER BY tuition_usd DESC
        LIMIT ?
        """,
        (limit_per_source,)
    ).fetchall()

    american = conn.execute(
        """
        SELECT unitid, institution_name AS name, 'United States' AS country,
               city, latitude, longitude,
               tuition_out_state AS tuition_usd,
               0 AS programmes, 'us' AS source
        FROM us_institutions
        WHERE latitude IS NOT NULL
          AND grants_degree = 1
          AND median_earnings_10yr IS NOT NULL
        ORDER BY median_earnings_10yr DESC
        LIMIT ?
        """,
        (limit_per_source,)
    ).fetchall()

    conn.close()

    return [dict(r) for r in international] + [dict(r) for r in american]
