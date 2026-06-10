from aggregator.subscribe_server import Deps, RateLimiter, route
from aggregator.models import Event
from aggregator.storage import Store
from aggregator.subscribers import SubscriberStore


def _deps(tmp_path):
    """Real subscriber store + recording fake send callbacks."""
    sent = {"verify": [], "welcome": [], "admin": []}
    store = SubscriberStore(str(tmp_path / "subs.db"))
    deps = Deps(
        store=store,
        send_verify=lambda email, token: sent["verify"].append((email, token)),
        send_welcome=lambda email, tok: sent["welcome"].append((email, tok)),
        rate=RateLimiter(max_hits=100, window_s=3600),
        send_admin_notify=lambda email: sent["admin"].append(email),
    )
    return deps, sent


def test_read_endpoints_are_rate_limited(tmp_path):
    # calendar.ics / verify / unsubscribe / preferences share a generous read
    # limiter (separate from the strict subscribe one) so a single IP cannot flood
    # the DB-reading calendar endpoint while normal polling stays well under it.
    deps, _ = _deps(tmp_path)
    deps.rate_read = RateLimiter(max_hits=2, window_s=3600)
    deps.events_db = str(tmp_path / "events.db")
    assert route("GET", "/api/calendar.ics", {}, {}, "9.9.9.9", deps, 1.0).status == 200
    assert route("GET", "/api/calendar.ics", {}, {}, "9.9.9.9", deps, 1.0).status == 200
    assert route("GET", "/api/calendar.ics", {}, {}, "9.9.9.9", deps, 1.0).status == 429
    # a different IP is unaffected
    assert route("GET", "/api/calendar.ics", {}, {}, "8.8.8.8", deps, 1.0).status == 200
    deps.store.close()


def test_subscribe_uses_its_own_strict_limiter_not_the_read_one(tmp_path):
    # POST /api/subscribe must keep using the strict `rate`, untouched by rate_read.
    deps, _ = _deps(tmp_path)
    deps.rate_read = RateLimiter(max_hits=1, window_s=3600)
    for _ in range(3):
        r = route("POST", "/api/subscribe", {}, {"email": "a@b.co"}, "1.1.1.1", deps, 1.0)
        assert r.status == 200          # not 429 from the read limiter
    deps.store.close()


def test_verify_notifies_admin_once(tmp_path):
    deps, sent = _deps(tmp_path)
    token = deps.store.subscribe("a@b.co").token
    route("POST", "/api/verify", {"token": token}, {}, "1.1.1.1", deps, 1000.0)
    assert sent["admin"] == ["a@b.co"]           # owner alerted on confirm
    # re-click -> 'already' -> must NOT alert again
    route("POST", "/api/verify", {"token": token}, {}, "1.1.1.1", deps, 1000.0)
    assert sent["admin"] == ["a@b.co"]
    deps.store.close()


def test_bare_subscribe_does_not_notify_admin(tmp_path):
    # only a CONFIRMED signup alerts the owner, not an unconfirmed form submit
    deps, sent = _deps(tmp_path)
    route("POST", "/api/subscribe", {}, {"email": "a@b.co"}, "1.1.1.1", deps, 1000.0)
    assert sent["admin"] == []
    deps.store.close()


def test_subscribe_sends_verify_and_shows_inbox_page(tmp_path):
    deps, sent = _deps(tmp_path)
    r = route("POST", "/api/subscribe", {}, {"email": "a@b.co"}, "1.1.1.1", deps, 1000.0)
    assert r.status == 200
    assert "check your inbox" in r.body.lower()
    assert len(sent["verify"]) == 1 and sent["verify"][0][0] == "a@b.co"
    deps.store.close()


def test_subscribe_records_source_preferences(tmp_path):
    deps, sent = _deps(tmp_path)
    form = {"email": "a@b.co", "sources": ["csis", "DC2", "bogus"]}
    route("POST", "/api/subscribe", {}, form, "1.1.1.1", deps, 1000.0)
    token = sent["verify"][0][1]
    result = deps.store.verify(token)
    assert result.sources == ("DC2", "csis")
    deps.store.close()


def test_subscribe_invalid_email_no_send(tmp_path):
    deps, sent = _deps(tmp_path)
    r = route("POST", "/api/subscribe", {}, {"email": "garbage"}, "1.1.1.1", deps, 1000.0)
    assert r.status == 400
    assert sent["verify"] == []
    deps.store.close()


def test_subscribe_honeypot_silently_succeeds_without_sending(tmp_path):
    deps, sent = _deps(tmp_path)
    form = {"email": "bot@b.co", "website": "http://spam"}   # honeypot filled
    r = route("POST", "/api/subscribe", {}, form, "1.1.1.1", deps, 1000.0)
    assert r.status == 200 and "check your inbox" in r.body.lower()
    assert sent["verify"] == []                              # nothing actually done
    assert deps.store.count() == 0
    deps.store.close()


def test_subscribe_already_verified_is_enumeration_safe(tmp_path):
    deps, sent = _deps(tmp_path)
    # verify a@b.co first
    tok = deps.store.subscribe("a@b.co").token
    deps.store.verify(tok)
    sent["verify"].clear()
    # subscribing again returns the SAME inbox page as a brand-new signup
    r_existing = route("POST", "/api/subscribe", {}, {"email": "a@b.co"}, "1.1.1.1", deps, 1000.0)
    r_new = route("POST", "/api/subscribe", {}, {"email": "new@b.co"}, "1.1.1.1", deps, 1000.0)
    assert r_existing.status == r_new.status == 200
    assert r_existing.body == r_new.body                     # indistinguishable
    assert sent["verify"] == [("new@b.co", sent["verify"][-1][1])]  # only the new one emailed
    deps.store.close()


def test_rate_limit_blocks_after_max(tmp_path):
    deps, sent = _deps(tmp_path)
    deps.rate.max_hits = 3
    for _ in range(3):
        assert route("POST", "/api/subscribe", {}, {"email": "a@b.co"}, "9.9.9.9", deps, 5.0).status != 429
    blocked = route("POST", "/api/subscribe", {}, {"email": "a@b.co"}, "9.9.9.9", deps, 5.0)
    assert blocked.status == 429
    # a different IP is unaffected
    assert route("POST", "/api/subscribe", {}, {"email": "a@b.co"}, "8.8.8.8", deps, 5.0).status != 429
    deps.store.close()


def test_verify_confirms_and_sends_welcome(tmp_path):
    deps, sent = _deps(tmp_path)
    token = deps.store.subscribe("a@b.co").token
    r = route("POST", "/api/verify", {"token": token}, {}, "1.1.1.1", deps, 1000.0)
    assert r.status == 200 and "subscribed" in r.body.lower()
    assert len(sent["welcome"]) == 1 and sent["welcome"][0][0] == "a@b.co"
    assert deps.store.status_of("a@b.co") == "verified"
    deps.store.close()


def test_verify_twice_sends_welcome_once(tmp_path):
    deps, sent = _deps(tmp_path)
    token = deps.store.subscribe("a@b.co").token
    route("POST", "/api/verify", {"token": token}, {}, "1.1.1.1", deps, 1000.0)
    r2 = route("POST", "/api/verify", {"token": token}, {}, "1.1.1.1", deps, 1000.0)
    assert "already confirmed" in r2.body.lower()
    assert len(sent["welcome"]) == 1            # not re-sent
    deps.store.close()


def test_verify_bad_token(tmp_path):
    deps, sent = _deps(tmp_path)
    r = route("POST", "/api/verify", {"token": "nope"}, {}, "1.1.1.1", deps, 1000.0)
    assert r.status == 400 and "didn" in r.body.lower()
    assert sent["welcome"] == []
    deps.store.close()


def test_unsubscribe_idempotent_page(tmp_path):
    deps, sent = _deps(tmp_path)
    tok = deps.store.subscribe("a@b.co").token
    v = deps.store.verify(tok)
    r = route("POST", "/api/unsubscribe", {"token": v.unsub_token}, {}, "1.1.1.1", deps, 1000.0)
    assert r.status == 200 and "unsubscribed" in r.body.lower()
    assert deps.store.status_of("a@b.co") == "unsubscribed"
    # unknown token still shows the same confirmation (no info leak)
    r2 = route("POST", "/api/unsubscribe", {"token": "nope"}, {}, "1.1.1.1", deps, 1000.0)
    assert r2.status == 200 and "unsubscribed" in r2.body.lower()
    deps.store.close()


def test_verify_get_is_a_form_with_no_side_effects(tmp_path):
    # A bare GET (mail scanner / prefetch) must NOT confirm; it only shows a form.
    deps, sent = _deps(tmp_path)
    token = deps.store.subscribe("a@b.co").token
    r = route("GET", "/api/verify", {"token": token}, {}, "1.1.1.1", deps, 1000.0)
    assert r.status == 200
    assert "<form" in r.body.lower() and 'method="post"' in r.body.lower()
    assert token in r.body                                    # token carried in form
    assert sent["welcome"] == [] and sent["admin"] == []      # nothing happened
    assert deps.store.status_of("a@b.co") == "pending"
    deps.store.close()


def test_unsubscribe_get_is_a_form_with_no_side_effects(tmp_path):
    deps, sent = _deps(tmp_path)
    tok = deps.store.subscribe("a@b.co").token
    v = deps.store.verify(tok)
    r = route("GET", "/api/unsubscribe", {"token": v.unsub_token}, {}, "1.1.1.1", deps, 1000.0)
    assert r.status == 200 and "<form" in r.body.lower()
    assert deps.store.status_of("a@b.co") == "verified"       # GET did NOT unsubscribe
    deps.store.close()


def test_calendar_endpoint_filters_by_sources_query(tmp_path):
    events_db = str(tmp_path / "events.db")
    store = Store(events_db)
    evs = [
        Event(id="c", title="CSET AI policy", start="2026-06-20", source="cset"),
        Event(id="d", title="Community build night", start="2026-06-20", source="DC2"),
    ]
    store.upsert_many(evs)
    store.mark_archived({e.id for e in evs})
    store.close()
    deps, sent = _deps(tmp_path)
    deps.events_db = events_db
    r = route("GET", "/api/calendar.ics", {"sources": "cset"}, {}, "1.1.1.1",
              deps, 1781058692.0)
    body = r.body.decode("utf-8")
    assert r.status == 200 and r.content_type.startswith("text/calendar")
    assert "CSET AI policy" in body
    assert "Community build night" not in body
    deps.store.close()


def test_calendar_endpoint_filters_by_subscriber_token(tmp_path):
    events_db = str(tmp_path / "events.db")
    store = Store(events_db)
    evs = [
        Event(id="c", title="CSET AI policy", start="2026-06-20", source="cset"),
        Event(id="d", title="Community build night", start="2026-06-20", source="DC2"),
    ]
    store.upsert_many(evs)
    store.mark_archived({e.id for e in evs})
    store.close()
    deps, sent = _deps(tmp_path)
    deps.events_db = events_db
    sub = deps.store.subscribe("a@b.co", ["DC2"])
    verified = deps.store.verify(sub.token)
    r = route("GET", "/api/calendar.ics", {"token": verified.unsub_token}, {},
              "1.1.1.1", deps, 1781058692.0)
    body = r.body.decode("utf-8")
    assert "Community build night" in body
    assert "CSET AI policy" not in body
    deps.store.close()


def test_unknown_path_404(tmp_path):
    deps, sent = _deps(tmp_path)
    assert route("GET", "/api/wat", {}, {}, "1.1.1.1", deps, 1000.0).status == 404
    # wrong method on a real path
    assert route("GET", "/api/subscribe", {}, {}, "1.1.1.1", deps, 1000.0).status == 404
    deps.store.close()
