"""
Set a password on an existing account, from the machine running the app.

There is no password-reset page: this project has no way to send email,
so the only honest recovery path is one that requires access to the
server itself. Run:

    python -m src.set_password aihemaharini@gmail.com

The password is typed at the prompt, never passed as an argument, so it
does not end up in shell history.
"""

import getpass
import sys

from src import auth
from src.db import get_connection


def list_accounts(conn):
    rows = conn.execute(
        "SELECT email, is_admin FROM users ORDER BY user_id"
    ).fetchall()

    if not rows:
        print("  (no accounts exist yet — sign up at /login.html)")
        return

    for row in rows:
        print(f"  {row['email']}{'  [admin]' if row['is_admin'] else ''}")


def main():
    if len(sys.argv) != 2:
        print(__doc__.strip())
        return 1

    email = sys.argv[1].strip().lower()

    conn = get_connection()

    row = conn.execute(
        "SELECT user_id, email, is_admin FROM users WHERE email = ?", (email,)
    ).fetchone()

    if row is None:
        print(f"No account with the email {email}. Accounts on this server:")
        list_accounts(conn)
        conn.close()
        return 1

    print(f"Setting a new password for {row['email']}"
          f"{' (admin)' if row['is_admin'] else ''}.")

    password = getpass.getpass("New password: ")

    if password != getpass.getpass("Confirm new password: "):
        print("Those did not match. Nothing was changed.")
        conn.close()
        return 1

    try:
        auth.validate_password(password)
    except ValueError as error:
        print(f"{error} Nothing was changed.")
        conn.close()
        return 1

    conn.execute(
        "UPDATE users SET password_hash = ? WHERE user_id = ?",
        (auth.hash_password(password), row["user_id"])
    )

    conn.commit()
    conn.close()

    print(f"Done. Sign in as {row['email']} with the new password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
