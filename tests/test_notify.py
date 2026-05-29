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
