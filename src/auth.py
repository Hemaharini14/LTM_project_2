import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from src import mailer
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

    # Reset tokens are stored hashed, so a leaked database cannot be used
    # to seize accounts. They expire and can only be spent once.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS password_resets (
            reset_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL,

            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """
    )

    # Added after the fact, so existing databases need the column.
    columns = [row[1] for row in conn.execute("PRAGMA table_info(users)")]

    if "password_changed_at" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN password_changed_at TEXT")

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
        data, issued_at = get_serializer().loads(
            token, max_age=SESSION_MAX_AGE, return_timestamp=True
        )

    except (BadSignature, SignatureExpired):
        return None

    user = get_user(data["user_id"])

    if user is None:
        return None

    # A password reset has to evict whoever was already signed in,
    # otherwise resetting does not actually lock an intruder out.
    changed_at = password_changed_at(user["user_id"])

    if changed_at is not None and as_utc(issued_at) < changed_at:
        return None

    return user


def password_changed_at(user_id):
    conn = get_connection()

    row = conn.execute(
        "SELECT password_changed_at FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()

    conn.close()

    if row is None or row["password_changed_at"] is None:
        return None

    return as_utc(datetime.fromisoformat(row["password_changed_at"]))


def as_utc(stamp):
    """
    Session timestamps come from itsdangerous in UTC, so anything
    compared against them has to be in UTC too. Storing this one in
    local time made every session issued after a reset look older than
    the reset, which signed the account out of its own new sessions.
    """

    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=timezone.utc)

    return stamp.astimezone(timezone.utc)


# ============================================================
# PASSWORD RESET
# ============================================================

RESET_TOKEN_TTL_MINUTES = 30


def hash_reset_token(token):
    """
    SHA-256 rather than bcrypt: the token is 32 random bytes, so it needs
    no stretching, and the hash has to be looked up directly.
    """

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def request_password_reset(email, build_link):
    """
    Issues a reset link for a real account and delivers it by email.

    Returns the same value whether or not the address is registered, so
    this cannot be used to discover who has an account. The token is
    never returned to the caller — only mailed.
    """

    email = email.strip().lower()

    conn = get_connection()

    row = conn.execute(
        "SELECT user_id FROM users WHERE email = ?", (email,)
    ).fetchone()

    if row is None:
        conn.close()
        return False

    token = secrets.token_urlsafe(32)
    expires = datetime.now() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)

    # Any earlier request is void once a new one is made.
    conn.execute(
        "UPDATE password_resets SET used_at = ? "
        "WHERE user_id = ? AND used_at IS NULL",
        (datetime.now().isoformat(timespec="seconds"), row["user_id"])
    )

    conn.execute(
        """
        INSERT INTO password_resets (
            user_id, token_hash, expires_at, created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            row["user_id"],
            hash_reset_token(token),
            expires.isoformat(timespec="seconds"),
            datetime.now().isoformat(timespec="seconds")
        )
    )

    conn.commit()
    conn.close()

    mailer.send(
        email,
        "Reset your EduBridge password",
        "Someone asked to reset the password for this EduBridge account.\n\n"
        f"Open this link within {RESET_TOKEN_TTL_MINUTES} minutes to choose "
        f"a new one:\n\n    {build_link(token)}\n\n"
        "The link works once. If this was not you, ignore this message — "
        "your password has not changed."
    )

    return True


def reset_password(token, new_password):
    """
    Spends a reset token and sets a new password.

    Raises ValueError when the token is unknown, expired or already used,
    or when the new password fails validation.
    """

    validate_password(new_password)

    conn = get_connection()

    row = conn.execute(
        """
        SELECT reset_id, user_id, expires_at, used_at
        FROM password_resets WHERE token_hash = ?
        """,
        (hash_reset_token(token),)
    ).fetchone()

    if row is None or row["used_at"] is not None:
        conn.close()
        raise ValueError("That reset link is no longer valid.")

    if datetime.fromisoformat(row["expires_at"]) < datetime.now():
        conn.close()
        raise ValueError("That reset link has expired. Request a new one.")

    now = datetime.now().isoformat(timespec="seconds")

    conn.execute(
        "UPDATE users SET password_hash = ?, password_changed_at = ? "
        "WHERE user_id = ?",
        (
            hash_password(new_password),
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            row["user_id"]
        )
    )

    conn.execute(
        "UPDATE password_resets SET used_at = ? WHERE reset_id = ?",
        (now, row["reset_id"])
    )

    conn.commit()
    conn.close()

    return True


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
