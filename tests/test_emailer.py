import email
from email import policy

from aggregator.emailer import build_weekly_message, send_weekly, since_iso
from aggregator.models import Event
from aggregator.storage import Store


def test_since_iso_is_seven_days_back():
    assert since_iso("2026-05-31") == "2026-05-24"
    assert since_iso("2026-05-31", days=14) == "2026-05-17"


def test_build_weekly_message_subject_and_parts():
    up = Event(id="a", title="AI policy panel", start="2026-06-02",
               source="cset", topics=["ai"], source_url="https://cset.org/e/a")
    msg = build_weekly_message([up], [up], "2026-05-31", "events.emersus.ai",
                               sender="from@x", to="to@x")
    assert "week of 2026-05-31" in msg["Subject"]
    assert "(1 new)" in msg["Subject"]
    assert msg["To"] == "to@x"
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert "AI policy panel" in html and "New this week (1)" in html
    # plain-text alternative present (markdown digest)
    text = msg.get_body(preferencelist=("plain",)).get_content()
    assert "AI policy panel" in text


def test_build_weekly_message_counts_only_upcoming_as_new():
    past = Event(id="p", title="Past talk", start="2026-01-01", source="DC2")
    msg = build_weekly_message([past], [past], "2026-05-31", "events.emersus.ai")
    assert "(0 new)" in msg["Subject"]   # a past event is not "new this week"


def test_send_weekly_dryrun_reads_store_and_writes_eml(tmp_path, monkeypatch):
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SMTP_TO", "owner@example.com")   # owner-fallback path
    db = str(tmp_path / "e.db")
    s = Store(db)
    s.upsert_many([Event(id="a", title="New AI talk", start="2026-06-10",
                         source="cset", topics=["ai"])])
    s.close()
    sent, total = send_weekly(out_dir=str(tmp_path / "out"), db_path=db,
                              today="2026-05-31",
                              subscribers_db=str(tmp_path / "subs.db"))
    assert (sent, total) == (0, 1)       # dry-run (no SMTP creds) to the 1 owner
    eml_path = tmp_path / "out" / "email" / "digest-2026-05-31.eml"
    assert eml_path.exists()
    parsed = email.message_from_bytes(eml_path.read_bytes(), policy=policy.default)
    html = parsed.get_body(preferencelist=("html",)).get_content()
    assert "New AI talk" in html
    assert "New this week (1)" in html   # the just-upserted event is new + upcoming


def test_send_weekly_targets_verified_subscribers(tmp_path, monkeypatch):
    from aggregator.subscribers import SubscriberStore
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "SMTP_TO"):
        monkeypatch.delenv(k, raising=False)
    db = str(tmp_path / "e.db")
    Store(db).close()
    subs_db = str(tmp_path / "subs.db")
    subs = SubscriberStore(subs_db)
    subs.verify(subs.subscribe("alice@example.com").token)   # verified
    subs.subscribe("pending@example.com")                    # NOT verified
    subs.close()

    sent, total = send_weekly(out_dir=str(tmp_path / "out"), db_path=db,
                              today="2026-05-31", subscribers_db=subs_db)
    assert total == 1                    # only the verified subscriber
    # dry-run .eml is addressed to the verified subscriber, with an unsub link
    eml = (tmp_path / "out" / "email" / "digest-2026-05-31.eml")
    parsed = email.message_from_bytes(eml.read_bytes(), policy=policy.default)
    assert parsed["To"] == "alice@example.com"
    html = parsed.get_body(preferencelist=("html",)).get_content()
    assert "api/unsubscribe?token=" in html   # personal unsubscribe link
