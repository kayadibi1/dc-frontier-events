"""Weekly digest email: selection + rendering + delivery.

Decoupled from the 2x/day calendar build. The calendar feeds rebuild twice daily
for freshness, but subscribers get ONE email per week. This module reads the
already-built store (no re-fetch), highlights events first seen in the last week
(Store.new_since -> the "new listings" the user asked to capture), renders the
polished template (digest.render_email_html), and delivers through the same
SMTP-or-dry-run transport as notify.deliver (dry-run writes an .eml; nothing is
sent unless SMTP_* is configured).

Cadence is the weekly timer's job, not this module's: `python -m aggregator
--email` builds + delivers once, whenever called.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage

from .digest import build_digest, render_email_html
from .notify import deliver
from .storage import open_store

WEEKLY_WINDOW_DAYS = 7


def since_iso(today_iso: str, days: int = WEEKLY_WINDOW_DAYS) -> str:
    """The lower bound for 'new this week': `days` before today (ISO date)."""
    return (date.fromisoformat(today_iso) - timedelta(days=days)).isoformat()


def build_weekly_message(events: list, new_events: list, today_iso: str,
                         domain: str, sender: str | None = None,
                         to: str | None = None,
                         unsubscribe_url: str = "#") -> EmailMessage:
    """Assemble the weekly digest as a multipart email (polished HTML + a
    plain-text markdown alternative). Pure: no IO, fully unit-testable."""
    new_up = [e for e in new_events if (e.start or "")[:10] >= today_iso]
    html = render_email_html(events, today_iso, new_events=new_events,
                             domain=domain, unsubscribe_url=unsubscribe_url)
    text = build_digest(events, today_iso)
    msg = EmailMessage()
    msg["Subject"] = f"DC AI & Frontier Tech — week of {today_iso} ({len(new_up)} new)"
    msg["From"] = sender or os.environ.get("SMTP_FROM", "dc-frontier-events@localhost")
    msg["To"] = to or os.environ.get("SMTP_TO", "subscriber@localhost")
    msg.set_content(text)                       # plain-text alternative
    msg.add_alternative(html, subtype="html")   # preferred HTML body
    return msg


def send_transactional(to: str, subject: str, html: str, out_dir: str,
                       slug: str, text: str | None = None) -> tuple[str, str]:
    """Send a single transactional email (verify / welcome) to one recipient via
    the shared SMTP-or-dry-run transport. `slug` names the dry-run .eml so signup
    mails never overwrite the weekly digest. Returns (mode, target)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("SMTP_FROM", "dc-frontier-events@localhost")
    msg["To"] = to
    msg.set_content(text or "Open this email in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")
    # today_iso is unused here because slug overrides the dry-run filename.
    return deliver(msg, out_dir, today_iso="txn", slug=slug)


def send_weekly(out_dir: str = "out", db_path: str = "data/events.db",
                today: str | None = None, domain: str | None = None) -> tuple[str, str]:
    """Read the store, render the weekly digest, and deliver it. Returns
    (mode, target): ('sent', recipient) or ('dry-run', eml_path). Reads only the
    already-built store -- it never triggers a fetch, so it is cheap and safe to
    run on its own weekly schedule."""
    today_iso = today or datetime.now(timezone.utc).date().isoformat()
    domain = domain or os.environ.get("CAL_DOMAIN", "events.emersus.ai")
    store = open_store(db_path)
    try:
        events = store.active_events()
        new_events = store.new_since(since_iso(today_iso))
    finally:
        store.close()
    msg = build_weekly_message(events, new_events, today_iso, domain)
    mode, target = deliver(msg, out_dir, today_iso)
    print(f"[email] {mode}: {target} "
          f"({len(new_events)} new this week, {len(events)} active events)")
    return mode, target
