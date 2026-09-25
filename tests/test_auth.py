"""
Accounts and sessions.

Account creation writes, so these run against a temporary database file
rather than the real one.
"""

import os
import sqlite3
import time
from datetime import datetime, timedelta

import pytest

from src import auth
from src.llm_extractor import normalize_country


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point the connection helper at a throwaway database."""

    path = tmp_path / "test.db"
    monkeypatch.setattr("src.db.DB_PATH", path)

    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr("src.auth.get_connection", connect)

    auth.init_auth_tables()
    return path


@pytest.fixture(autouse=True)
def session_secret(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-not-used-in-production")


# --- passwords --------------------------------------------------------

def test_password_is_hashed_not_stored():
    hashed = auth.hash_password("correct horse battery")

    assert hashed != "correct horse battery"
    assert hashed.startswith("$2b$")


def test_verify_accepts_right_and_rejects_wrong():
    hashed = auth.hash_password("correct horse battery")

    assert auth.verify_password("correct horse battery", hashed)
    assert not auth.verify_password("wrong horse battery", hashed)


def test_same_password_hashes_differently_each_time():
    """Distinct salts, so identical passwords do not look identical."""

    assert auth.hash_password("repeated") != auth.hash_password("repeated")


def test_short_passwords_rejected():
    with pytest.raises(ValueError):
        auth.validate_password("short")


def test_overlong_passwords_rejected():
    """
    bcrypt silently ignores anything past 72 bytes, so a longer password
    would authenticate on its first 72 bytes alone.
    """

    with pytest.raises(ValueError):
        auth.validate_password("x" * 100)


# --- accounts ---------------------------------------------------------

def test_signup_and_authenticate(temp_db):
    auth.create_user("student@example.com", "GoodPassword1")

    assert auth.authenticate("student@example.com", "GoodPassword1")
    assert auth.authenticate("student@example.com", "WrongPassword") is None


def test_duplicate_email_rejected(temp_db):
    auth.create_user("student@example.com", "GoodPassword1")

    with pytest.raises(ValueError):
        auth.create_user("student@example.com", "AnotherPassword1")


def test_admin_email_is_elevated(temp_db):
    admin = auth.create_user(auth.ADMIN_EMAIL, "GoodPassword1")
    student = auth.create_user("someone@example.com", "GoodPassword1")

    assert admin["is_admin"] is True
    assert student["is_admin"] is False


def test_public_user_never_exposes_the_hash(temp_db):
    user = auth.create_user("student@example.com", "GoodPassword1")

    assert "password_hash" not in user


def test_email_is_case_insensitive(temp_db):
    auth.create_user("Student@Example.com", "GoodPassword1")

    assert auth.authenticate("student@example.com", "GoodPassword1")


# --- sessions ---------------------------------------------------------

def test_session_round_trip(temp_db):
    user = auth.create_user("student@example.com", "GoodPassword1")
    token = auth.create_session_token(user["user_id"])

    assert auth.read_session_token(token)["email"] == "student@example.com"


def test_tampered_session_is_rejected(temp_db):
    user = auth.create_user("student@example.com", "GoodPassword1")
    token = auth.create_session_token(user["user_id"])

    assert auth.read_session_token(token[:-4] + "aaaa") is None


def test_garbage_session_is_rejected(temp_db):
    assert auth.read_session_token("not-a-token") is None


# --- password reset ---------------------------------------------------

@pytest.fixture
def captured_link(monkeypatch):
    """
    Intercept the mail so tests can read the token. In production this
    link only ever reaches the mailbox or the server console.
    """

    sent = {}

    def fake_send(to_address, subject, body):
        sent["to"] = to_address
        sent["body"] = body
        return True

    monkeypatch.setattr("src.mailer.send", fake_send)
    return sent


def issue_token(email, captured_link):
    auth.request_password_reset(email, lambda token: f"TOKEN:{token}")
    return captured_link["body"].split("TOKEN:")[1].split()[0]


def test_reset_changes_the_password(temp_db, captured_link):
    auth.create_user("student@example.com", "original-password")

    token = issue_token("student@example.com", captured_link)
    auth.reset_password(token, "brand-new-password")

    assert auth.authenticate("student@example.com", "brand-new-password")
    assert auth.authenticate("student@example.com", "original-password") is None


def test_token_is_stored_hashed_never_in_the_clear(temp_db, captured_link):
    """A stolen database must not hand over working reset links."""

    auth.create_user("student@example.com", "original-password")
    token = issue_token("student@example.com", captured_link)

    conn = sqlite3.connect(temp_db)
    stored = [row[0] for row in conn.execute("SELECT token_hash FROM password_resets")]
    conn.close()

    assert token not in stored
    assert stored == [auth.hash_reset_token(token)]


def test_token_works_only_once(temp_db, captured_link):
    auth.create_user("student@example.com", "original-password")
    token = issue_token("student@example.com", captured_link)

    auth.reset_password(token, "first-new-password")

    with pytest.raises(ValueError, match="no longer valid"):
        auth.reset_password(token, "second-new-password")

    assert auth.authenticate("student@example.com", "first-new-password")


def test_requesting_again_voids_the_earlier_token(temp_db, captured_link):
    auth.create_user("student@example.com", "original-password")

    first = issue_token("student@example.com", captured_link)
    second = issue_token("student@example.com", captured_link)

    with pytest.raises(ValueError, match="no longer valid"):
        auth.reset_password(first, "attacker-chosen-password")

    auth.reset_password(second, "rightful-new-password")
    assert auth.authenticate("student@example.com", "rightful-new-password")


def test_expired_token_is_refused(temp_db, captured_link):
    auth.create_user("student@example.com", "original-password")
    token = issue_token("student@example.com", captured_link)

    expired = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
    conn = sqlite3.connect(temp_db)
    conn.execute("UPDATE password_resets SET expires_at = ?", (expired,))
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="expired"):
        auth.reset_password(token, "too-late-password")

    assert auth.authenticate("student@example.com", "original-password")


def test_unknown_token_is_refused(temp_db):
    with pytest.raises(ValueError, match="no longer valid"):
        auth.reset_password("not-a-real-token", "some-new-password")


def test_reset_enforces_password_rules(temp_db, captured_link):
    auth.create_user("student@example.com", "original-password")
    token = issue_token("student@example.com", captured_link)

    with pytest.raises(ValueError, match="at least"):
        auth.reset_password(token, "short")

    # The rejected attempt must not have spent the token.
    auth.reset_password(token, "long-enough-password")
    assert auth.authenticate("student@example.com", "long-enough-password")


def test_unknown_email_does_not_reveal_itself(temp_db, captured_link):
    """
    No account, no mail, no error — otherwise the form becomes a way to
    test whether an address is registered.
    """

    auth.request_password_reset("stranger@example.com", lambda token: token)

    assert captured_link == {}

    conn = sqlite3.connect(temp_db)
    count = conn.execute("SELECT COUNT(*) FROM password_resets").fetchone()[0]
    conn.close()

    assert count == 0


def test_reset_signs_out_existing_sessions(temp_db, captured_link):
    """
    Resetting is how you lock out someone who got in, so a session that
    predates the reset has to stop working.
    """

    user = auth.create_user("student@example.com", "original-password")
    token_cookie = auth.create_session_token(user["user_id"])

    assert auth.read_session_token(token_cookie)["email"] == "student@example.com"

    # Sessions carry a whole-second timestamp; without this the new
    # session and the reset can land inside the same second.
    time.sleep(1.1)
    auth.reset_password(issue_token("student@example.com", captured_link),
                        "brand-new-password")

    assert auth.read_session_token(token_cookie) is None


def test_session_issued_after_the_reset_still_works(temp_db, captured_link):
    user = auth.create_user("student@example.com", "original-password")

    auth.reset_password(issue_token("student@example.com", captured_link),
                        "brand-new-password")
    time.sleep(1.1)

    fresh = auth.create_session_token(user["user_id"])
    assert auth.read_session_token(fresh)["email"] == "student@example.com"


# --- country normalisation --------------------------------------------

@pytest.mark.parametrize("given,expected", [
    ("US", "United States"),
    ("usa", "United States"),
    ("U.S.A.", "United States"),
    ("  united states of america ", "United States"),
    ("uk", "United Kingdom"),
    ("England", "United Kingdom"),
    ("Germany", "Germany"),
    (None, None),
])
def test_country_aliases(given, expected):
    """
    The API routes on an exact country string, so "US" silently fell
    through to global results before this existed.
    """

    assert normalize_country(given) == expected
