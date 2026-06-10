import threading
from datetime import datetime, timedelta, timezone

from aggregator.subscribers import SubscriberStore, valid_email


def test_valid_email_accepts_and_rejects():
    assert valid_email("a@b.co")
    assert valid_email("Sidar.Vig+dc@gmail.com")
    assert not valid_email("nope")
    assert not valid_email("a@b")                  # no TLD dot
    assert not valid_email("a b@c.com")            # space
    assert not valid_email("a@b.com,c@d.com")      # injection / list
    assert not valid_email("")


def test_subscribe_new_returns_send_verify_with_token(tmp_path):
    s = SubscriberStore(str(tmp_path / "subs.db"))
    r = s.subscribe("Person@Example.com")
    assert r.action == "send_verify"
    assert r.email == "person@example.com"         # normalized lower
    assert len(r.token) > 20
    assert s.status_of("person@example.com") == "pending"
    s.close()


def test_subscribe_invalid_email(tmp_path):
    s = SubscriberStore(str(tmp_path / "subs.db"))
    assert s.subscribe("garbage").action == "invalid"
    assert s.count() == 0
    s.close()


def test_verify_happy_path_then_idempotent(tmp_path):
    s = SubscriberStore(str(tmp_path / "subs.db"))
    token = s.subscribe("a@b.co").token
    v = s.verify(token)
    assert v.status == "verified" and v.email == "a@b.co"
    assert v.unsub_token                            # provided for welcome email
    assert s.status_of("a@b.co") == "verified"
    # second click: already verified -> 'already' (welcome not re-sent)
    assert s.verify(token).status == "already"
    s.close()


def test_verify_bad_token(tmp_path):
    s = SubscriberStore(str(tmp_path / "subs.db"))
    assert s.verify("nope").status == "invalid"
    assert s.verify("").status == "invalid"
    s.close()


def test_verify_expired_token_rejected(tmp_path):
    s = SubscriberStore(str(tmp_path / "subs.db"))
    token = s.subscribe("a@b.co").token
    # backdate creation beyond the 48h window
    old = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()
    s.conn.execute("UPDATE subscribers SET created_at=? WHERE email='a@b.co'", (old,))
    s.conn.commit()
    assert s.verify(token).status == "invalid"
    assert s.status_of("a@b.co") == "pending"      # not promoted
    s.close()


def test_already_verified_resubscribe_is_noop(tmp_path):
    s = SubscriberStore(str(tmp_path / "subs.db"))
    s.verify(s.subscribe("a@b.co").token)
    r = s.subscribe("a@b.co")                       # already on the list
    assert r.action == "already_verified"
    assert s.count(status="verified") == 1
    s.close()


def test_resubscribe_while_pending_refreshes_token(tmp_path):
    s = SubscriberStore(str(tmp_path / "subs.db"))
    t1 = s.subscribe("a@b.co").token
    t2 = s.subscribe("a@b.co").token               # didn't click yet -> resend
    assert t1 != t2
    assert s.verify(t1).status == "invalid"        # old token no longer valid
    assert s.verify(t2).status == "verified"
    s.close()


def test_unsubscribe_then_can_resubscribe(tmp_path):
    s = SubscriberStore(str(tmp_path / "subs.db"))
    v = s.verify(s.subscribe("a@b.co").token)
    assert s.unsubscribe(v.unsub_token) is True
    assert s.status_of("a@b.co") == "unsubscribed"
    assert s.verified() == []                       # off the send list
    # re-subscribe restarts double opt-in
    r = s.subscribe("a@b.co")
    assert r.action == "send_verify"
    assert s.verify(r.token).status == "verified"
    s.close()


def test_unsubscribe_bad_token(tmp_path):
    s = SubscriberStore(str(tmp_path / "subs.db"))
    assert s.unsubscribe("nope") is False
    assert s.unsubscribe("") is False
    s.close()


def test_store_is_usable_from_multiple_threads(tmp_path):
    # Reproduces the ThreadingHTTPServer failure: the store is opened in one
    # thread and used from many. Must not raise sqlite3.ProgrammingError, and
    # every distinct subscribe must persist.
    s = SubscriberStore(str(tmp_path / "subs.db"))
    errors: list[Exception] = []

    def worker(i: int):
        try:
            r = s.subscribe(f"user{i}@example.com")
            s.verify(r.token)
        except Exception as e:           # capture cross-thread errors
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []                  # no ProgrammingError / interleave
    assert s.count(status="verified") == 20
    s.close()


def test_verified_list_is_the_send_list(tmp_path):
    s = SubscriberStore(str(tmp_path / "subs.db"))
    s.verify(s.subscribe("a@b.co").token)
    s.subscribe("pending@b.co")                     # never verified
    verified = s.verified()
    assert [e for e, _ in verified] == ["a@b.co"]   # only verified included
    assert all(tok for _, tok in verified)          # each has an unsub token
    s.close()


def test_source_preferences_round_trip_and_update(tmp_path):
    s = SubscriberStore(str(tmp_path / "subs.db"))
    r = s.subscribe("a@b.co", ["csis", "nope", "DC2"])
    assert r.sources == ("DC2", "csis")
    v = s.verify(r.token)
    assert v.sources == ("DC2", "csis")
    assert s.verified_with_prefs() == [("a@b.co", v.unsub_token, ("DC2", "csis"))]
    assert s.preferences_for_token(v.unsub_token) == ("a@b.co", ("DC2", "csis"))
    assert s.update_preferences(v.unsub_token, ["cset"]) is True
    assert s.preferences_for_token(v.unsub_token) == ("a@b.co", ("cset",))
    s.close()
