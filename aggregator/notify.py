"""Notification delivery for the digest + alerts.

Builds a multipart email (HTML digest body + plain-text alternative). Transport
is pluggable and **never blocks the run**:
  - if SMTP_HOST/SMTP_USER/SMTP_PASS/SMTP_TO are all set -> send via SMTP+STARTTLS;
  - otherwise (or on send failure) -> dry-run: write the full RFC822 message to
    out/email/digest-<today>.eml so it is inspectable and testable without creds.
Stdlib only (email, smtplib).
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def build_message(html_body: str, text_body: str, today_iso: str,
                  upcoming: int, new_big: int,
                  sender: str | None = None, to: str | None = None) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = (f"DC AI & Semiconductor — {today_iso} "
                      f"({upcoming} upcoming, {new_big} new big-name)")
    msg["From"] = sender or os.environ.get("SMTP_FROM", "dc-frontier-events@localhost")
    msg["To"] = to or os.environ.get("SMTP_TO", "subscriber@localhost")
    msg.set_content(text_body)                      # plain-text alternative
    msg.add_alternative(html_body, subtype="html")  # preferred HTML body
    return msg


def deliver(msg: EmailMessage, out_dir: str, today_iso: str) -> tuple[str, str]:
    """Return (mode, target): ("sent", recipient) or ("dry-run", eml_path)."""
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    pw = os.environ.get("SMTP_PASS")
    to = os.environ.get("SMTP_TO")
    if host and user and pw and to:
        try:
            port = int(os.environ.get("SMTP_PORT", "587"))
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls()
                s.login(user, pw)
                s.send_message(msg)
            return ("sent", to)
        except Exception as e:  # never block the run on a send failure
            print(f"[notify] SMTP send failed ({e!r}); falling back to dry-run.")

    email_dir = os.path.join(out_dir, "email")
    os.makedirs(email_dir, exist_ok=True)
    path = os.path.join(email_dir, f"digest-{today_iso}.eml")
    with open(path, "wb") as f:
        f.write(msg.as_bytes())
    return ("dry-run", path)
