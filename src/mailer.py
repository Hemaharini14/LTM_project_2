"""
Outbound email.

Delivery is pluggable so the password-reset flow can be built and tested
without a mail server. With SMTP configured the message is sent; without
it, the message is written to the server console — visible to whoever is
running the server and to nobody else. It is never returned to the
browser, because anyone who could read it could take over the account.
"""

import os
import smtplib
from email.message import EmailMessage


def smtp_configured():
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER"))


def send(to_address, subject, body):
    """
    Deliver a message. Returns True when it actually left the machine.

    Never raises: a mail failure must not reveal whether an account
    exists, and must not break the request.
    """

    if not smtp_configured():
        print("\n" + "=" * 68)
        print("EMAIL NOT CONFIGURED — message printed here instead")
        print(f"To:      {to_address}")
        print(f"Subject: {subject}")
        print("-" * 68)
        print(body)
        print("=" * 68 + "\n", flush=True)
        return False

    message = EmailMessage()
    message["From"] = os.getenv("SMTP_FROM", os.environ["SMTP_USER"])
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            server.send_message(message)

        return True

    except Exception as error:
        # Logged for the operator, never surfaced to the caller.
        print(f"[mailer] delivery to {to_address} failed: {error}", flush=True)
        return False
