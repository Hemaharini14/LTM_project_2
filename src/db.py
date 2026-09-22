import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "edubridge.db"

# Every page view writes history while other requests read, and a dev
# machine often has more than one server pointed at this file. Without
# these two settings SQLite fails a concurrent request outright with
# "database is locked" instead of waiting its turn.
BUSY_TIMEOUT_MS = 10000

_journal_mode_set = False


def get_connection():
    global _journal_mode_set

    conn = sqlite3.connect(DB_PATH, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row

    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")

    # WAL lets readers and the writer work at the same time. It is a
    # property of the file, so setting it once per process is enough.
    if not _journal_mode_set:
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            _journal_mode_set = True
        except sqlite3.OperationalError:
            # Another process may hold the lock while switching modes;
            # the busy timeout above still applies either way.
            pass

    return conn
