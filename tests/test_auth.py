"""
Accounts and sessions.

Account creation writes, so these run against a temporary database file
rather than the real one.
"""

import os
import sqlite3

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


# --- saved universities ------------------------------------------------

def test_save_and_list(temp_db):
    user = auth.create_user("student@example.com", "GoodPassword1")
    auth.save_university(user["user_id"], "us:166683")

    assert auth.get_saved_keys(user["user_id"]) == ["us:166683"]


def test_saving_twice_does_not_duplicate(temp_db):
    user = auth.create_user("student@example.com", "GoodPassword1")
    auth.save_university(user["user_id"], "us:166683")
    auth.save_university(user["user_id"], "us:166683")

    assert auth.get_saved_keys(user["user_id"]) == ["us:166683"]


def test_unsave_removes_it(temp_db):
    user = auth.create_user("student@example.com", "GoodPassword1")
    auth.save_university(user["user_id"], "us:166683")
    auth.unsave_university(user["user_id"], "us:166683")

    assert auth.get_saved_keys(user["user_id"]) == []


def test_saved_universities_are_per_user(temp_db):
    a = auth.create_user("a@example.com", "GoodPassword1")
    b = auth.create_user("b@example.com", "GoodPassword1")

    auth.save_university(a["user_id"], "us:166683")

    assert auth.get_saved_keys(a["user_id"]) == ["us:166683"]
    assert auth.get_saved_keys(b["user_id"]) == []


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
