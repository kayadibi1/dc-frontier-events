import email
from email import policy

from aggregator.notify import build_message, deliver


def test_build_message_has_subject_and_html():
    msg = build_message("<html><body><h1>Digest</h1></body></html>", "Digest text",
                        "2026-05-29", upcoming=5, new_big=1)
    assert "2026-05-29" in msg["Subject"]
    assert "5 upcoming" in msg["Subject"] and "1 new big-name" in msg["Subject"]
    html = msg.get_body(preferencelist=("html",))
    assert html is not None and "<h1>Digest</h1>" in html.get_content()
    text = msg.get_body(preferencelist=("plain",))
    assert text is not None and "Digest text" in text.get_content()


def test_deliver_dryrun_writes_valid_eml(tmp_path, monkeypatch):
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "SMTP_TO"):
        monkeypatch.delenv(k, raising=False)
    msg = build_message("<html><body>Upcoming AI talk</body></html>", "Upcoming AI talk",
                        "2026-05-29", upcoming=3, new_big=0)
    mode, target = deliver(msg, str(tmp_path), "2026-05-29")
    assert mode == "dry-run"
    eml = tmp_path / "email" / "digest-2026-05-29.eml"
    assert eml.exists()
    parsed = email.message_from_bytes(eml.read_bytes(), policy=policy.default)
    assert "2026-05-29" in parsed["Subject"]
    assert "Upcoming AI talk" in parsed.get_body(preferencelist=("html",)).get_content()


def test_deliver_smtp_success_path(tmp_path, monkeypatch):
    # With SMTP_* set and a working server, deliver() does STARTTLS+login+send
    # and reports ("sent", recipient). Uses a fake SMTP so no real network.
    for k, v in {"SMTP_HOST": "h", "SMTP_USER": "u", "SMTP_PASS": "p",
                 "SMTP_TO": "to@example.com"}.items():
        monkeypatch.setenv(k, v)
    calls = []

    class FakeSMTP:
        def __init__(self, *a, **k):
            calls.append("init")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            calls.append("starttls")

        def login(self, u, p):
            calls.append(("login", u, p))

        def send_message(self, m):
            calls.append("send")

    import aggregator.notify as notify
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    msg = build_message("<html></html>", "x", "2026-05-29", 1, 0)
    mode, target = deliver(msg, str(tmp_path), "2026-05-29")
    assert mode == "sent" and target == "to@example.com"
    assert "starttls" in calls and "send" in calls
    assert ("login", "u", "p") in calls


def test_deliver_smtp_failure_falls_back_to_dryrun(tmp_path, monkeypatch):
    # All SMTP_* set but the server errors -> must fall back to dry-run, never raise
    # (the production-safety "never blocks the run" guarantee).
    for k, v in {"SMTP_HOST": "h", "SMTP_USER": "u", "SMTP_PASS": "p",
                 "SMTP_TO": "to@example.com"}.items():
        monkeypatch.setenv(k, v)

    def boom(*a, **k):
        raise OSError("connection refused")

    import aggregator.notify as notify
    monkeypatch.setattr(notify.smtplib, "SMTP", boom)
    msg = build_message("<html></html>", "x", "2026-05-29", 1, 0)
    mode, target = deliver(msg, str(tmp_path), "2026-05-29")
    assert mode == "dry-run"
    assert (tmp_path / "email" / "digest-2026-05-29.eml").exists()
