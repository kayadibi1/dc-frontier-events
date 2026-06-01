"""Tiny public HTTP service for double-opt-in digest signups.

Stdlib only (http.server) -- no new deps -- listening on localhost; the existing
Caddy reverse-proxies /api/* to it over HTTPS. The request logic lives in the
pure `route()` function (testable with fakes, no socket); `SubscribeHandler` is a
thin shell that parses the request and writes the Response.

Endpoints:
  POST /api/subscribe          form: email (+ honeypot 'website') -> verify email
  GET  /api/verify?token=...   confirm -> welcome email -> "you're in" page
  GET  /api/unsubscribe?token= remove from the list

Hardening: per-IP rate limit, bot honeypot, capped body size, email validation,
enumeration-safe subscribe response (always "check your inbox"), no reflected
user input, no open redirects (pages rendered inline).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit

from .subscribers import SubscriberStore

MAX_BODY = 8192            # bytes; signup posts are tiny
RATE_MAX = 10             # max requests
RATE_WINDOW_S = 3600      # per hour, per IP
HONEYPOT_FIELD = "website"  # hidden in the form; humans leave it empty


@dataclass
class Response:
    status: int
    body: str
    content_type: str = "text/html; charset=utf-8"
    location: str | None = None


class RateLimiter:
    """In-memory sliding-window limiter keyed by client IP. Process-local, which
    is fine for a single-instance signup endpoint (abuse protection, not auth)."""

    def __init__(self, max_hits: int = RATE_MAX, window_s: int = RATE_WINDOW_S):
        self.max_hits = max_hits
        self.window_s = window_s
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str, now: float) -> bool:
        hits = [t for t in self._hits.get(key, []) if now - t < self.window_s]
        if len(hits) >= self.max_hits:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True


@dataclass
class Deps:
    store: SubscriberStore
    send_verify: callable      # (email, token) -> None
    send_welcome: callable     # (email, unsub_token) -> None
    rate: RateLimiter
    # Owner alert when a subscriber is newly CONFIRMED. Default no-op so tests /
    # other callers that don't care can omit it.
    send_admin_notify: callable = lambda email: None   # (email) -> None


_PAGE_CSS = (
    "body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f4f6fb;"
    "color:#1f2533;margin:0;padding:0}.card{max-width:460px;margin:8vh auto;background:#fff;"
    "border-radius:14px;padding:32px 30px;box-shadow:0 1px 4px rgba(0,0,0,.06)}"
    "h1{font-size:20px;margin:0 0 8px}p{font-size:15px;line-height:1.55;color:#444}"
    "a{color:#1a4fd0}.muted{color:#6b7280;font-size:13px}"
)


def _page(title: str, heading: str, message_html: str, status: int = 200) -> Response:
    body = (
        f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{title}</title><style>{_PAGE_CSS}</style></head><body>'
        f'<div class="card"><h1>{heading}</h1>{message_html}</div></body></html>'
    )
    return Response(status, body)


def route(method: str, path: str, query: dict, form: dict, client_ip: str,
          deps: Deps, now: float) -> Response:
    """Pure request handler: inputs in, Response out, side effects only via deps."""
    if path == "/api/subscribe" and method == "POST":
        if not deps.rate.allow(client_ip, now):
            return _page("Slow down", "Too many requests",
                         '<p>Please try again in a little while.</p>', status=429)
        # Honeypot: a bot fills the hidden field -> pretend success, do nothing.
        if (form.get(HONEYPOT_FIELD) or "").strip():
            return _check_inbox_page()
        email = (form.get("email") or "").strip()
        result = deps.store.subscribe(email)
        if result.action == "invalid":
            return _page("Check the address", "Hmm, that address looks off",
                         '<p>That doesn&rsquo;t look like a valid email. '
                         '<a href="/">Try again</a>.</p>', status=400)
        if result.action == "send_verify":
            deps.send_verify(result.email, result.token)
        # send_verify and already_verified return the SAME page (enumeration-safe).
        return _check_inbox_page()

    if path == "/api/verify" and method == "GET":
        token = (query.get("token") or "").strip()
        result = deps.store.verify(token)
        if result.status == "verified":
            deps.send_welcome(result.email, result.unsub_token)
            deps.send_admin_notify(result.email)   # owner alert: a real new subscriber
            return _page("You're in", "You&rsquo;re subscribed ✅",
                         '<p>Welcome aboard! A confirmation email with a taste of '
                         'what&rsquo;s coming is on its way.</p>'
                         '<p class="muted">Your full digest lands every Monday.</p>')
        if result.status == "already":
            return _page("Already confirmed", "Already confirmed ✅",
                         '<p>You&rsquo;re already on the list — nothing more to do.</p>')
        return _page("Link problem", "This link didn&rsquo;t work",
                     '<p>The confirmation link is invalid or has expired (they last '
                     '48 hours). <a href="/">Sign up again</a> to get a fresh one.</p>',
                     status=400)

    if path == "/api/unsubscribe" and method in ("GET", "POST"):
        # GET = a human clicking the link; POST = RFC 8058 one-click from the mail
        # client (List-Unsubscribe-Post). Token is in the query either way.
        token = (query.get("token") or "").strip()
        deps.store.unsubscribe(token)   # idempotent; same page either way
        return _page("Unsubscribed", "You&rsquo;re unsubscribed",
                     '<p>You will no longer receive the weekly digest. '
                     'Changed your mind? <a href="/">Re-subscribe anytime</a>.</p>')

    return _page("Not found", "Not found", '<p><a href="/">Go home</a></p>', status=404)


def _check_inbox_page() -> Response:
    return _page("Check your inbox", "Almost there — check your inbox",
                 '<p>We sent you a confirmation link. Click it to start getting the '
                 'weekly DC AI &amp; frontier-tech radar.</p>'
                 '<p class="muted">No email after a few minutes? Check spam, or '
                 '<a href="/">try again</a>.</p>')


# --- production wiring -------------------------------------------------------
def _base_url() -> str:
    return f"https://{os.environ.get('CAL_DOMAIN', 'events.emersus.ai')}"


def make_production_deps(db_path: str, events_db: str, out_dir: str) -> Deps:
    """Wire the real subscriber store + email-sending callbacks."""
    from .digest import render_verify_email_html, render_welcome_email_html
    from .emailer import send_transactional
    from .storage import open_store

    store = SubscriberStore(db_path)
    base = _base_url()

    def send_verify(email: str, token: str) -> None:
        url = f"{base}/api/verify?token={quote(token)}"
        html = render_verify_email_html(url)
        text = ("Confirm your subscription to the DC AI & Frontier Tech weekly radar.\n\n"
                f"Open this link to confirm (expires in 48 hours):\n{url}\n\n"
                "If you didn't sign up, ignore this email — nothing happens until "
                "you confirm.")
        send_transactional(email, "Confirm your DC AI events subscription", html,
                            out_dir, slug=f"verify-{token[:10]}", text=text)

    def send_welcome(email: str, unsub_token: str) -> None:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).date().isoformat()
        es = open_store(events_db)
        try:
            events = es.active_events()
        finally:
            es.close()
        unsub = f"{base}/api/unsubscribe?token={quote(unsub_token)}"
        html = render_welcome_email_html(events, today, unsubscribe_url=unsub)
        text = ("You're in — the DC AI & Frontier Tech weekly radar.\n\n"
                f"Add the live calendar (always current): {base}/events-upcoming.ics\n"
                "Your full weekly digest lands every Monday morning.\n\n"
                f"Unsubscribe anytime: {unsub}")
        send_transactional(email, "You're in — DC AI & Frontier Tech radar", html,
                           out_dir, slug=f"welcome-{unsub_token[:10]}", text=text,
                           list_unsubscribe=unsub)

    def send_admin_notify(email: str) -> None:
        """Email the owner (SMTP_TO) when someone confirms their subscription."""
        owner = os.environ.get("SMTP_TO")
        if not owner:
            return
        n = store.count("verified")
        safe = escape(email)
        html = (f"<p>🎉 <b>{safe}</b> just confirmed their subscription to the "
                f"DC AI &amp; Frontier Tech weekly digest.</p>"
                f"<p>You now have <b>{n}</b> verified subscriber(s).</p>")
        slug_email = "".join(c if c.isalnum() else "-" for c in email)[:24]
        send_transactional(owner, f"New subscriber: {email} ({n} total)", html,
                           out_dir, slug=f"newsub-{slug_email}",
                           text=f"{email} confirmed. {n} verified subscriber(s).")

    return Deps(store=store, send_verify=send_verify, send_welcome=send_welcome,
                rate=RateLimiter(), send_admin_notify=send_admin_notify)


class SubscribeHandler(BaseHTTPRequestHandler):
    deps: Deps | None = None     # injected by serve()

    def _client_ip(self) -> str:
        xff = self.headers.get("X-Forwarded-For")
        return xff.split(",")[0].strip() if xff else self.client_address[0]

    def _dispatch(self, method: str, form: dict) -> None:
        u = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(u.query).items()}
        resp = route(method, u.path, query, form, self._client_ip(),
                     self.deps, time.time())
        body = resp.body.encode("utf-8")
        self.send_response(resp.status)
        if resp.location:
            self.send_header("Location", resp.location)
        self.send_header("Content-Type", resp.content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._dispatch("GET", {})

    def do_POST(self) -> None:
        length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY)
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        form = {k: v[0] for k, v in parse_qs(raw).items()}
        self._dispatch("POST", form)

    def log_message(self, *args) -> None:
        pass   # stay quiet in the journal


def serve(host: str | None = None, port: int | None = None,
          db_path: str = "data/subscribers.db",
          events_db: str = "data/events.db", out_dir: str = "out") -> None:
    # Host/port overridable via env (the box is busy; 8800 is glitchtip).
    host = host or os.environ.get("SUBSCRIBE_HOST", "127.0.0.1")
    port = port or int(os.environ.get("SUBSCRIBE_PORT", "8810"))
    SubscribeHandler.deps = make_production_deps(db_path, events_db, out_dir)
    httpd = ThreadingHTTPServer((host, port), SubscribeHandler)
    print(f"[subscribe] listening on http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    serve()
