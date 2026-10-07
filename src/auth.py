import os
import sqlite3
from datetime import datetime

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from src.db import get_connection


ADMIN_EMAIL = "aihemaharini@gmail.com"

SESSION_COOKIE = "edubridge_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7

# bcrypt silently ignores anything past 72 bytes, so a longer password
# would authenticate on its first 72 bytes alone. Reject instead.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8


def get_serializer():
    secret = os.getenv("SESSION_SECRET")

    if not secret:
        raise RuntimeError(
            "SESSION_SECRET is not set. Add it to your .env file "
            "(see .env.example)."
        )

    return URLSafeTimedSerializer(secret, salt="edubridge-session")


# ============================================================
# SCHEMA
# ============================================================

def init_auth_tables():
    """
    Created separately from database_setup.py so that rebuilding the
    reference data never drops real user accounts.
    """

    conn = get_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS search_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            query_text TEXT,
            detail TEXT,
            created_at TEXT NOT NULL,

            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """
    )

    # compare_key reuses the exact "us:<unitid>" / "intl:<name>" /
    # "india:<institute>" format recommender.py already normalises every
    # university into via get_comparable(), so a saved row resolves
    # through that same function instead of a second lookup path.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_universities (
            saved_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            compare_key TEXT NOT NULL,
            saved_at TEXT NOT NULL,

            FOREIGN KEY (user_id) REFERENCES users(user_id),
            UNIQUE (user_id, compare_key)
        )
        """
    )

    conn.commit()
    conn.close()


# ============================================================
# PASSWORDS
# ============================================================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8")
    )


def validate_password(password: str):
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )

    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes."
        )


# ============================================================
# ACCOUNTS
# ============================================================

def create_user(email: str, password: str, full_name: str = ""):
    email = email.strip().lower()

    validate_password(password)

    conn = get_connection()

    try:
        cursor = conn.execute(
            """
            INSERT INTO users (
                email, password_hash, full_name, is_admin, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                email,
                hash_password(password),
                full_name.strip(),
                1 if email == ADMIN_EMAIL else 0,
                datetime.now().isoformat(timespec="seconds")
            )
        )

        conn.commit()

        return get_user(cursor.lastrowid)

    except sqlite3.IntegrityError:
        raise ValueError("An account with that email already exists.")

    finally:
        conn.close()


def authenticate(email: str, password: str):
    conn = get_connection()

    row = conn.execute(
        "SELECT * FROM users WHERE email = ?",
        (email.strip().lower(),)
    ).fetchone()

    conn.close()

    if row is None or not verify_password(password, row["password_hash"]):
        return None

    return public_user(row)


def get_user(user_id: int):
    conn = get_connection()

    row = conn.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,)
    ).fetchone()

    conn.close()

    return public_user(row) if row else None


def public_user(row):
    """Never let password_hash leave this module."""

    return {
        "user_id": row["user_id"],
        "email": row["email"],
        "full_name": row["full_name"],
        "is_admin": bool(row["is_admin"]),
        "created_at": row["created_at"]
    }


# ============================================================
# SESSIONS
# ============================================================

def create_session_token(user_id: int) -> str:
    return get_serializer().dumps({"user_id": user_id})


def read_session_token(token: str):
    try:
        data = get_serializer().loads(token, max_age=SESSION_MAX_AGE)

    except (BadSignature, SignatureExpired):
        return None

    return get_user(data["user_id"])


# ============================================================
# HISTORY
# ============================================================

def record_history(user_id: int, kind: str, query_text: str, detail: str = ""):
    conn = get_connection()

    conn.execute(
        """
        INSERT INTO search_history (
            user_id, kind, query_text, detail, created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            kind,
            query_text,
            detail,
            datetime.now().isoformat(timespec="seconds")
        )
    )

    conn.commit()
    conn.close()


def get_history(user_id: int, limit: int = 50):
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT kind, query_text, detail, created_at
        FROM search_history
        WHERE user_id = ?
        ORDER BY history_id DESC
        LIMIT ?
        """,
        (user_id, limit)
    ).fetchall()

    conn.close()

    return [dict(row) for row in rows]


# ============================================================
# SAVED UNIVERSITIES
# ============================================================

def save_university(user_id: int, compare_key: str):
    conn = get_connection()

    # INSERT OR IGNORE makes saving an already-saved university a no-op
    # rather than a duplicate-row error, so the frontend never has to
    # check first.
    conn.execute(
        """
        INSERT OR IGNORE INTO saved_universities (
            user_id, compare_key, saved_at
        )
        VALUES (?, ?, ?)
        """,
        (user_id, compare_key, datetime.now().isoformat(timespec="seconds"))
    )

    conn.commit()
    conn.close()


def unsave_university(user_id: int, compare_key: str):
    conn = get_connection()

    conn.execute(
        "DELETE FROM saved_universities WHERE user_id = ? AND compare_key = ?",
        (user_id, compare_key)
    )

    conn.commit()
    conn.close()


def get_saved_keys(user_id: int):
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT compare_key FROM saved_universities
        WHERE user_id = ?
        ORDER BY saved_id DESC
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    return [row["compare_key"] for row in rows]
