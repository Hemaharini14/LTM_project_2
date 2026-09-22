import sqlite3
import pandas as pd
from pathlib import Path


# ============================================================
# PATH CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "dataset"
DB_PATH = BASE_DIR / "edubridge.db"


# ============================================================
# CSV READER
# ============================================================

def read_csv_safely(file_path):
    encodings = ["utf-8", "utf-8-sig", "cp1252", "latin1"]

    for encoding in encodings:
        try:
            return pd.read_csv(
                file_path,
                encoding=encoding
            )
        except UnicodeDecodeError:
            continue

    raise ValueError(
        f"Could not determine encoding for {file_path}"
    )


# ============================================================
# BASIC CLEANING
# ============================================================

def clean_dataframe(df):
    df = df.copy()

    df = df.dropna(
        axis=1,
        how="all"
    )

    df = df.drop_duplicates()

    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
    )

    return df


# ============================================================
# MAIN DATABASE CREATION
# ============================================================

def create_database():

    print("Loading datasets...")

    # --------------------------------------------------------
    # LOAD DATA
    # --------------------------------------------------------

    university_df = read_csv_safely(
        DATA_DIR / "CleanData_universityRanking.csv"
    )

    cost_df = read_csv_safely(
        DATA_DIR / "Cost_of_Living_Index_by_Country_2024.csv"
    )

    city_df = read_csv_safely(
        DATA_DIR / "worldcities.csv"
    )

    qs_df = read_csv_safely(
        DATA_DIR /
        "QS World University Rankings 2025 (Top global universities).csv"
    )

    institution_df = pd.read_csv(
        DATA_DIR / "Most-Recent-Cohorts-Institution.csv",
        usecols=[
            "UNITID", "INSTNM", "CITY", "STABBR", "ZIP",
            "CONTROL", "TUITIONFEE_IN", "TUITIONFEE_OUT",
            "ADM_RATE", "SAT_AVG", "ACTCM25", "ACTCM75",
            "ROOMBOARD_ON", "ROOMBOARD_OFF", "BOOKSUPPLY",
            "COSTT4_A", "MD_EARN_WNE_P10", "INSTURL"
        ],
        dtype={"ZIP": str, "INSTURL": str},
        low_memory=False
    )

    field_of_study_df = pd.read_csv(
        DATA_DIR / "Most-Recent-Cohorts-Field-of-Study.csv",
        usecols=[
            "UNITID", "INSTNM", "CIPCODE", "CIPDESC", "CREDDESC"
        ],
        low_memory=False
    )

    international_df = read_csv_safely(
        DATA_DIR / "International_Education_Costs.csv"
    )

    josaa_df = read_csv_safely(
        DATA_DIR / "JoSAA_Cutoffs_2021.csv"
    )

    # --------------------------------------------------------
    # CLEAN DATA
    # --------------------------------------------------------

    university_df = clean_dataframe(university_df)
    cost_df = clean_dataframe(cost_df)
    city_df = clean_dataframe(city_df)
    qs_df = clean_dataframe(qs_df)
    institution_df = clean_dataframe(institution_df)
    field_of_study_df = clean_dataframe(field_of_study_df)
    international_df = clean_dataframe(international_df)

    print(
        f"Universities loaded: {len(university_df)}"
    )

    print(
        f"Countries loaded: {len(cost_df)}"
    )

    print(
        f"Cities loaded: {len(city_df)}"
    )

    print(
        f"QS records loaded: {len(qs_df)}"
    )

    print(
        f"US institutions loaded: {len(institution_df)}"
    )

    print(
        f"US fields of study loaded: {len(field_of_study_df)}"
    )

    print(
        f"International programmes loaded: {len(international_df)}"
    )

    print(
        f"JoSAA cutoffs loaded: {len(josaa_df)}"
    )

    # ========================================================
    # STANDARDIZE COUNTRY NAMES
    # ========================================================

    country_name_mapping = {
        "Hong Kong": "Hong Kong (China)",
        "Czechia": "Czech Republic",
        "Bosnia and Herzegovina":
            "Bosnia And Herzegovina",
        "Kosovo":
            "Kosovo (Disputed Territory)"
    }

    # ========================================================
    # PREPARE UNIVERSITIES
    # ========================================================

    universities = pd.DataFrame()

    universities["university_name"] = (
        university_df["University"]
        .astype(str)
        .str.strip()
    )

    universities["country"] = (
        university_df["Location"]
        .astype(str)
        .str.strip()
        .replace(country_name_mapping)
    )

    universities["university_rank"] = pd.to_numeric(
        university_df["Rank"],
        errors="coerce"
    )

    universities["overall_score"] = pd.to_numeric(
        university_df["Overall Score"],
        errors="coerce"
    )

    universities["teaching_score"] = pd.to_numeric(
        university_df["Overall Teaching Score"],
        errors="coerce"
    )

    universities["research_score"] = pd.to_numeric(
        university_df["Research Score"],
        errors="coerce"
    )

    universities["research_quality"] = pd.to_numeric(
        university_df["Research Quality"],
        errors="coerce"
    )

    universities["industry_income_score"] = pd.to_numeric(
        university_df["Industry Income Score"],
        errors="coerce"
    )

    universities["international_outlook_score"] = pd.to_numeric(
        university_df["International Outlook Score"],
        errors="coerce"
    )

    # ========================================================
    # PREPARE COUNTRIES
    # ========================================================

    countries = cost_df.copy()

    countries = countries.rename(
        columns={
            "Country": "country_name",
            "Cost of Living Index":
                "cost_of_living_index",
            "Rent Index":
                "rent_index",
            "Cost of Living Plus Rent Index":
                "cost_of_living_plus_rent",
            "Groceries Index":
                "groceries_index",
            "Restaurant Price Index":
                "restaurant_price_index",
            "Local Purchasing Power Index":
                "local_purchasing_power_index"
        }
    )

    country_columns = [
        "country_name",
        "cost_of_living_index",
        "rent_index",
        "cost_of_living_plus_rent",
        "groceries_index",
        "restaurant_price_index",
        "local_purchasing_power_index"
    ]

    countries = countries[
        [
            col
            for col in country_columns
            if col in countries.columns
        ]
    ]

    countries["country_name"] = (
        countries["country_name"]
        .astype(str)
        .str.strip()
    )

    for column in country_columns[1:]:

        if column in countries.columns:

            countries[column] = pd.to_numeric(
                countries[column],
                errors="coerce"
            )

    # ========================================================
    # PREPARE CITIES
    # ========================================================

    cities = city_df.copy()

    cities = cities.rename(
        columns={
            "city": "city_name",
            "country": "country_name",
            "lat": "latitude",
            "lng": "longitude"
        }
    )

    city_columns = [
        "city_name",
        "country_name",
        "latitude",
        "longitude",
        "admin_name",
        "capital",
        "population"
    ]

    cities = cities[
        [
            col
            for col in city_columns
            if col in cities.columns
        ]
    ]

    # ========================================================
    # PREPARE QS DATA
    # ========================================================

    qs = qs_df.copy()

    qs = qs.rename(
        columns={
            "RANK_2025": "qs_rank_2025",
            "RANK_2024": "qs_rank_2024",
            "Institution_Name": "institution_name",
            "Location": "location",
            "Region": "region",
            "SIZE": "size",
            "FOCUS": "focus",
            "RES.": "research",
            "STATUS": "status",
            "Academic_Reputation_Score":
                "academic_reputation_score"
        }
    )

    qs_columns = [
        "institution_name",
        "location",
        "region",
        "size",
        "focus",
        "research",
        "status",
        "academic_reputation_score",
        "qs_rank_2025",
        "qs_rank_2024"
    ]

    qs = qs[
        [
            col
            for col in qs_columns
            if col in qs.columns
        ]
    ]

    # ========================================================
    # PREPARE US INSTITUTIONS (College Scorecard)
    # ========================================================

    control_labels = {
        1: "Public",
        2: "Private nonprofit",
        3: "Private for-profit"
    }

    institutions = institution_df.rename(
        columns={
            "UNITID": "unitid",
            "INSTNM": "institution_name",
            "CITY": "city",
            "STABBR": "state",
            "ZIP": "zip_code",
            "CONTROL": "control",
            "TUITIONFEE_IN": "tuition_in_state",
            "TUITIONFEE_OUT": "tuition_out_state",
            "ADM_RATE": "admission_rate",
            "SAT_AVG": "sat_average",
            "ACTCM25": "act_25th",
            "ACTCM75": "act_75th",
            "ROOMBOARD_ON": "roomboard_on_campus",
            "ROOMBOARD_OFF": "roomboard_off_campus",
            "BOOKSUPPLY": "books_supplies",
            "COSTT4_A": "cost_of_attendance",
            "MD_EARN_WNE_P10": "median_earnings_10yr",
            "INSTURL": "institution_url"
        }
    )

    numeric_institution_columns = [
        "admission_rate",
        "sat_average",
        "act_25th",
        "act_75th",
        "roomboard_on_campus",
        "roomboard_off_campus",
        "books_supplies",
        "cost_of_attendance",
        "median_earnings_10yr"
    ]

    for column in numeric_institution_columns:

        institutions[column] = pd.to_numeric(
            institutions[column],
            errors="coerce"
        )

    institutions["control"] = pd.to_numeric(
        institutions["control"],
        errors="coerce"
    )

    institutions["control_label"] = (
        institutions["control"].map(control_labels)
    )

    institutions["tuition_in_state"] = pd.to_numeric(
        institutions["tuition_in_state"],
        errors="coerce"
    )

    institutions["tuition_out_state"] = pd.to_numeric(
        institutions["tuition_out_state"],
        errors="coerce"
    )

    # ========================================================
    # PREPARE US FIELDS OF STUDY (College Scorecard)
    # ========================================================

    fields_of_study = field_of_study_df.rename(
        columns={
            "UNITID": "unitid",
            "INSTNM": "institution_name",
            "CIPCODE": "cip_code",
            "CIPDESC": "cip_description",
            "CREDDESC": "credential_description"
        }
    )

    dropped_no_unitid = fields_of_study["unitid"].isna().sum()

    fields_of_study = fields_of_study.dropna(
        subset=["unitid"]
    )

    fields_of_study["unitid"] = (
        fields_of_study["unitid"].astype(int)
    )

    if dropped_no_unitid:

        print(
            f"Dropped {dropped_no_unitid} field-of-study rows "
            f"with no UNITID (closed/defunct institutions)"
        )

    # ========================================================
    # PREPARE INTERNATIONAL PROGRAMMES
    # ========================================================

    international = international_df.rename(
        columns={
            "Country": "country",
            "City": "city",
            "University": "university_name",
            "Program": "program",
            "Level": "level",
            "Duration_Years": "duration_years",
            "Tuition_USD": "tuition_usd",
            "Living_Cost_Index": "living_cost_index",
            "Rent_USD": "rent_usd_monthly",
            "Visa_Fee_USD": "visa_fee_usd",
            "Insurance_USD": "insurance_usd",
            "Exchange_Rate": "exchange_rate"
        }
    )

    international["country"] = (
        international["country"]
        .astype(str)
        .str.strip()
        .replace({"UK": "United Kingdom", "USA": "United States"})
    )

    for column in [
        "duration_years", "tuition_usd", "living_cost_index",
        "rent_usd_monthly", "visa_fee_usd", "insurance_usd",
        "exchange_rate"
    ]:
        international[column] = pd.to_numeric(
            international[column],
            errors="coerce"
        )

    # ========================================================
    # DATABASE CONNECTION
    # ========================================================

    print("Creating SQLite database...")

    conn = sqlite3.connect(DB_PATH)

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

    # ========================================================
    # DROP OLD TABLES
    # ========================================================

    conn.execute(
        "DROP TABLE IF EXISTS university_country"
    )

    conn.execute(
        "DROP TABLE IF EXISTS universities"
    )

    conn.execute(
        "DROP TABLE IF EXISTS countries"
    )

    conn.execute(
        "DROP TABLE IF EXISTS cities"
    )

    conn.execute(
        "DROP TABLE IF EXISTS qs_rankings"
    )

    conn.execute(
        "DROP TABLE IF EXISTS us_fields_of_study"
    )

    conn.execute(
        "DROP TABLE IF EXISTS us_institutions"
    )

    conn.execute(
        "DROP TABLE IF EXISTS international_programs"
    )

    conn.execute(
        "DROP TABLE IF EXISTS india_cutoffs"
    )

    # ========================================================
    # CREATE COUNTRIES TABLE
    # ========================================================

    conn.execute(
        """
        CREATE TABLE countries (
            country_id INTEGER PRIMARY KEY,
            country_name TEXT NOT NULL UNIQUE,
            cost_of_living_index REAL,
            rent_index REAL,
            cost_of_living_plus_rent REAL,
            groceries_index REAL,
            restaurant_price_index REAL,
            local_purchasing_power_index REAL
        )
        """
    )

    # ========================================================
    # CREATE UNIVERSITIES TABLE
    # ========================================================

    conn.execute(
        """
        CREATE TABLE universities (
            university_id INTEGER PRIMARY KEY,
            university_name TEXT NOT NULL,
            country TEXT,
            university_rank INTEGER,
            overall_score REAL,
            teaching_score REAL,
            research_score REAL,
            research_quality REAL,
            industry_income_score REAL,
            international_outlook_score REAL
        )
        """
    )

    # ========================================================
    # CREATE CITIES TABLE
    # ========================================================

    conn.execute(
        """
        CREATE TABLE cities (
            city_id INTEGER PRIMARY KEY,
            city_name TEXT,
            country_name TEXT,
            latitude REAL,
            longitude REAL,
            admin_name TEXT,
            capital TEXT,
            population REAL
        )
        """
    )

    # ========================================================
    # CREATE QS TABLE
    # ========================================================

    conn.execute(
        """
        CREATE TABLE qs_rankings (
            qs_id INTEGER PRIMARY KEY,
            institution_name TEXT,
            location TEXT,
            region TEXT,
            size TEXT,
            focus TEXT,
            research TEXT,
            status TEXT,
            academic_reputation_score REAL,
            qs_rank_2025 TEXT,
            qs_rank_2024 TEXT
        )
        """
    )

    # ========================================================
    # CREATE US INSTITUTIONS TABLE (College Scorecard)
    # ========================================================

    conn.execute(
        """
        CREATE TABLE us_institutions (
            unitid INTEGER PRIMARY KEY,
            institution_name TEXT NOT NULL,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            control INTEGER,
            control_label TEXT,
            tuition_in_state REAL,
            tuition_out_state REAL,
            admission_rate REAL,
            sat_average REAL,
            act_25th REAL,
            act_75th REAL,
            roomboard_on_campus REAL,
            roomboard_off_campus REAL,
            books_supplies REAL,
            cost_of_attendance REAL,
            median_earnings_10yr REAL,
            institution_url TEXT,
            grants_degree INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    # ========================================================
    # CREATE US FIELDS OF STUDY TABLE (College Scorecard)
    # ========================================================

    conn.execute(
        """
        CREATE TABLE us_fields_of_study (
            field_id INTEGER PRIMARY KEY,
            unitid INTEGER NOT NULL,
            institution_name TEXT,
            cip_code TEXT,
            cip_description TEXT,
            credential_description TEXT
        )
        """
    )

    # ========================================================
    # CREATE INTERNATIONAL PROGRAMMES TABLE
    # ========================================================

    conn.execute(
        """
        CREATE TABLE international_programs (
            program_id INTEGER PRIMARY KEY,
            country TEXT NOT NULL,
            city TEXT,
            university_name TEXT NOT NULL,
            program TEXT,
            level TEXT,
            duration_years REAL,
            tuition_usd REAL,
            living_cost_index REAL,
            rent_usd_monthly REAL,
            visa_fee_usd REAL,
            insurance_usd REAL,
            exchange_rate REAL
        )
        """
    )

    # ========================================================
    # CREATE INDIA CUTOFFS TABLE (JoSAA)
    # ========================================================

    # India publishes entrance-exam closing ranks rather than acceptance
    # rates, so this is the local equivalent of admission difficulty.
    conn.execute(
        """
        CREATE TABLE india_cutoffs (
            cutoff_id INTEGER PRIMARY KEY,
            institute TEXT NOT NULL,
            institute_type TEXT,
            program TEXT,
            quota TEXT,
            seat_type TEXT,
            gender TEXT,
            opening_rank INTEGER,
            closing_rank INTEGER,
            year INTEGER NOT NULL
        )
        """
    )

    # ========================================================
    # CREATE RELATIONSHIP TABLE
    # ========================================================

    conn.execute(
        """
        CREATE TABLE university_country (
            university_id INTEGER NOT NULL,
            country_id INTEGER NOT NULL,

            PRIMARY KEY (
                university_id,
                country_id
            ),

            FOREIGN KEY (
                university_id
            )
            REFERENCES universities(university_id),

            FOREIGN KEY (
                country_id
            )
            REFERENCES countries(country_id)
        )
        """
    )

    # ========================================================
    # INSERT COUNTRIES
    # ========================================================

    for index, row in countries.iterrows():

        conn.execute(
            """
            INSERT INTO countries (
                country_id,
                country_name,
                cost_of_living_index,
                rent_index,
                cost_of_living_plus_rent,
                groceries_index,
                restaurant_price_index,
                local_purchasing_power_index
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                index + 1,
                row.get("country_name"),
                row.get("cost_of_living_index"),
                row.get("rent_index"),
                row.get("cost_of_living_plus_rent"),
                row.get("groceries_index"),
                row.get("restaurant_price_index"),
                row.get("local_purchasing_power_index")
            )
        )

    # ========================================================
    # INSERT UNIVERSITIES
    # ========================================================

    for index, row in universities.iterrows():

        conn.execute(
            """
            INSERT INTO universities (
                university_id,
                university_name,
                country,
                university_rank,
                overall_score,
                teaching_score,
                research_score,
                research_quality,
                industry_income_score,
                international_outlook_score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                index + 1,
                row["university_name"],
                row["country"],
                row["university_rank"],
                row["overall_score"],
                row["teaching_score"],
                row["research_score"],
                row["research_quality"],
                row["industry_income_score"],
                row["international_outlook_score"]
            )
        )

    # ========================================================
    # INSERT CITIES
    # ========================================================

    for index, row in cities.iterrows():

        conn.execute(
            """
            INSERT INTO cities (
                city_id,
                city_name,
                country_name,
                latitude,
                longitude,
                admin_name,
                capital,
                population
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                index + 1,
                row.get("city_name"),
                row.get("country_name"),
                row.get("latitude"),
                row.get("longitude"),
                row.get("admin_name"),
                row.get("capital"),
                row.get("population")
            )
        )

    # ========================================================
    # INSERT QS RANKINGS
    # ========================================================

    for index, row in qs.iterrows():

        conn.execute(
            """
            INSERT INTO qs_rankings (
                qs_id,
                institution_name,
                location,
                region,
                size,
                focus,
                research,
                status,
                academic_reputation_score,
                qs_rank_2025,
                qs_rank_2024
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                index + 1,
                row.get("institution_name"),
                row.get("location"),
                row.get("region"),
                row.get("size"),
                row.get("focus"),
                row.get("research"),
                row.get("status"),
                row.get("academic_reputation_score"),
                row.get("qs_rank_2025"),
                row.get("qs_rank_2024")
            )
        )

    # ========================================================
    # INSERT US INSTITUTIONS
    # ========================================================

    institution_columns = [
        "unitid",
        "institution_name",
        "city",
        "state",
        "zip_code",
        "control",
        "control_label",
        "tuition_in_state",
        "tuition_out_state",
        "admission_rate",
        "sat_average",
        "act_25th",
        "act_75th",
        "roomboard_on_campus",
        "roomboard_off_campus",
        "books_supplies",
        "cost_of_attendance",
        "median_earnings_10yr",
        "institution_url"
    ]

    institution_records = list(
        institutions[institution_columns].itertuples(
            index=False,
            name=None
        )
    )

    conn.executemany(
        f"""
        INSERT INTO us_institutions (
            {", ".join(institution_columns)}
        )
        VALUES ({", ".join("?" * len(institution_columns))})
        """,
        institution_records
    )

    # ========================================================
    # INSERT US FIELDS OF STUDY
    # ========================================================

    field_of_study_records = [
        (index + 1,) + record
        for index, record in enumerate(
            fields_of_study[
                [
                    "unitid",
                    "institution_name",
                    "cip_code",
                    "cip_description",
                    "credential_description"
                ]
            ].itertuples(index=False, name=None)
        )
    ]

    conn.executemany(
        """
        INSERT INTO us_fields_of_study (
            field_id,
            unitid,
            institution_name,
            cip_code,
            cip_description,
            credential_description
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        field_of_study_records
    )

    # ========================================================
    # INSERT INTERNATIONAL PROGRAMMES
    # ========================================================

    international_columns = [
        "country", "city", "university_name", "program", "level",
        "duration_years", "tuition_usd", "living_cost_index",
        "rent_usd_monthly", "visa_fee_usd", "insurance_usd",
        "exchange_rate"
    ]

    conn.executemany(
        f"""
        INSERT INTO international_programs (
            program_id, {", ".join(international_columns)}
        )
        VALUES ({", ".join("?" * (len(international_columns) + 1))})
        """,
        [
            (index + 1,) + record
            for index, record in enumerate(
                international[international_columns].itertuples(
                    index=False, name=None
                )
            )
        ]
    )

    # ========================================================
    # INSERT INDIA CUTOFFS
    # ========================================================

    def institute_type(name):
        lowered = name.lower()

        if "indian institute of technology" in lowered:
            return "IIT"
        if "national institute of technology" in lowered:
            return "NIT"
        if "information technology" in lowered:
            return "IIIT"

        return "GFTI"

    josaa = josaa_df.copy()

    josaa["institute"] = (
        josaa["institute"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    )

    josaa["institute_type"] = josaa["institute"].map(institute_type)

    conn.executemany(
        """
        INSERT INTO india_cutoffs (
            cutoff_id, institute, institute_type, program, quota,
            seat_type, gender, opening_rank, closing_rank, year
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 2021)
        """,
        [
            (index + 1,) + record
            for index, record in enumerate(
                josaa[[
                    "institute", "institute_type", "program", "quota",
                    "seat_type", "gender", "opening_rank", "closing_rank"
                ]].itertuples(index=False, name=None)
            )
        ]
    )

    # ========================================================
    # FINANCIAL AID / SCHOLARSHIPS
    # ========================================================

    # Net price is what students actually pay after grants and
    # scholarships, reported per family income band. Each institution
    # files under one sector, so the four variants collapse into one.

    aid_bands = {
        "net_price_0_30k": "NPT41",
        "net_price_30_48k": "NPT42",
        "net_price_48_75k": "NPT43",
        "net_price_75_110k": "NPT44",
        "net_price_110k_plus": "NPT45",
        "net_price_avg": "NPT4"
    }

    aid_columns = ["UNITID", "PCTPELL", "GRAD_DEBT_MDN"]

    for prefix in aid_bands.values():
        aid_columns += [
            f"{prefix}_{sector}"
            for sector in ("PUB", "PRIV", "PROG", "OTHER")
        ]

    aid_df = pd.read_csv(
        DATA_DIR / "Most-Recent-Cohorts-Institution.csv",
        usecols=lambda column: column in aid_columns,
        low_memory=False
    )

    aid = pd.DataFrame({"unitid": aid_df["UNITID"]})

    for field, prefix in aid_bands.items():
        merged = None

        for sector in ("PUB", "PRIV", "PROG", "OTHER"):
            name = f"{prefix}_{sector}"

            if name not in aid_df.columns:
                continue

            values = pd.to_numeric(aid_df[name], errors="coerce")
            merged = values if merged is None else merged.fillna(values)

        aid[field] = merged

    aid["pell_grant_percent"] = pd.to_numeric(
        aid_df["PCTPELL"], errors="coerce"
    )
    aid["median_debt"] = pd.to_numeric(
        aid_df["GRAD_DEBT_MDN"], errors="coerce"
    )

    aid_fields = list(aid_bands.keys()) + ["pell_grant_percent", "median_debt"]

    for field in aid_fields:
        conn.execute(f"ALTER TABLE us_institutions ADD COLUMN {field} REAL")

    aid = aid.where(pd.notnull(aid), None)

    conn.executemany(
        f"""
        UPDATE us_institutions
        SET {", ".join(field + " = ?" for field in aid_fields)}
        WHERE unitid = ?
        """,
        [
            tuple(row[field] for field in aid_fields) + (int(row["unitid"]),)
            for _, row in aid.iterrows()
        ]
    )

    # ========================================================
    # GEOCODE UNIVERSITIES
    # ========================================================

    # Resolved once here. Doing this join per request meant scanning
    # 50,250 cities for every row, which took minutes to serve.

    conn.execute("ALTER TABLE us_institutions ADD COLUMN latitude REAL")
    conn.execute("ALTER TABLE us_institutions ADD COLUMN longitude REAL")
    conn.execute("ALTER TABLE international_programs ADD COLUMN latitude REAL")
    conn.execute("ALTER TABLE international_programs ADD COLUMN longitude REAL")

    conn.execute("DROP TABLE IF EXISTS city_lookup")
    conn.execute(
        """
        CREATE TABLE city_lookup AS
        SELECT LOWER(city_name) AS city_key,
               LOWER(country_name) AS country_key,
               latitude, longitude
        FROM (
            SELECT city_name, country_name, latitude, longitude,
                   ROW_NUMBER() OVER (
                       PARTITION BY LOWER(city_name), LOWER(country_name)
                       ORDER BY COALESCE(population, 0) DESC
                   ) AS rn
            FROM cities
            WHERE latitude IS NOT NULL
        )
        WHERE rn = 1
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX idx_city_lookup "
        "ON city_lookup(city_key, country_key)"
    )

    conn.execute(
        """
        UPDATE us_institutions SET
          latitude = (SELECT latitude FROM city_lookup
                      WHERE city_key = LOWER(us_institutions.city)
                        AND country_key = 'united states'),
          longitude = (SELECT longitude FROM city_lookup
                       WHERE city_key = LOWER(us_institutions.city)
                         AND country_key = 'united states')
        """
    )
    conn.execute(
        """
        UPDATE international_programs SET
          latitude = (SELECT latitude FROM city_lookup
                      WHERE city_key = LOWER(international_programs.city)
                        AND country_key = LOWER(international_programs.country)),
          longitude = (SELECT longitude FROM city_lookup
                       WHERE city_key = LOWER(international_programs.city)
                         AND country_key = LOWER(international_programs.country))
        """
    )

    # ========================================================
    # FLAG DEGREE-GRANTING INSTITUTIONS
    # ========================================================

    # Trade and cosmetology schools rarely report tuition, housing or
    # admissions, so they leave half-empty pages. Flagging the institutions
    # that actually award degrees lets search default to those.

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fos_unitid "
        "ON us_fields_of_study(unitid)"
    )

    conn.execute(
        """
        UPDATE us_institutions
        SET grants_degree = 1
        WHERE unitid IN (
            SELECT DISTINCT unitid
            FROM us_fields_of_study
            WHERE credential_description IN (
                'Bachelor''s Degree',
                'Master''s Degree',
                'Doctoral Degree'
            )
        )
        """
    )

    # ========================================================
    # CREATE UNIVERSITY → COUNTRY LINKS
    # ========================================================

    country_map = dict(
        zip(
            countries["country_name"],
            range(
                1,
                len(countries) + 1
            )
        )
    )

    links = []

    for index, row in universities.iterrows():

        country_name = row["country"]

        country_id = country_map.get(
            country_name
        )

        if country_id is not None:

            links.append(
                (
                    index + 1,
                    country_id
                )
            )

    conn.executemany(
        """
        INSERT INTO university_country (
            university_id,
            country_id
        )
        VALUES (?, ?)
        """,
        links
    )

    # ========================================================
    # COMMIT
    # ========================================================

    conn.commit()

    # ========================================================
    # VERIFY COUNTS
    # ========================================================

    university_count = conn.execute(
        "SELECT COUNT(*) FROM universities"
    ).fetchone()[0]

    country_count = conn.execute(
        "SELECT COUNT(*) FROM countries"
    ).fetchone()[0]

    city_count = conn.execute(
        "SELECT COUNT(*) FROM cities"
    ).fetchone()[0]

    qs_count = conn.execute(
        "SELECT COUNT(*) FROM qs_rankings"
    ).fetchone()[0]

    link_count = conn.execute(
        "SELECT COUNT(*) FROM university_country"
    ).fetchone()[0]

    us_institution_count = conn.execute(
        "SELECT COUNT(*) FROM us_institutions"
    ).fetchone()[0]

    us_field_of_study_count = conn.execute(
        "SELECT COUNT(*) FROM us_fields_of_study"
    ).fetchone()[0]

    international_count = conn.execute(
        "SELECT COUNT(*) FROM international_programs"
    ).fetchone()[0]

    india_cutoff_count = conn.execute(
        "SELECT COUNT(*) FROM india_cutoffs"
    ).fetchone()[0]

    conn.close()

    # ========================================================
    # FINAL OUTPUT
    # ========================================================

    print()
    print("===================================")
    print("EduBridge database created!")
    print("===================================")
    print(f"Universities : {university_count}")
    print(f"Countries    : {country_count}")
    print(f"Cities       : {city_count}")
    print(f"QS Rankings  : {qs_count}")
    print(
        f"University-Country links : {link_count}"
    )
    print(f"US Institutions   : {us_institution_count}")
    print(f"US Fields of Study : {us_field_of_study_count}")
    print(f"International programmes : {international_count}")
    print(f"India JoSAA cutoffs : {india_cutoff_count}")


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":
    create_database()