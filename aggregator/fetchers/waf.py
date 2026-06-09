"""Shared curl_cffi GET with TLS-profile fallback.

Cloudflare scores TLS fingerprints per site+IP: the chrome profile started
getting challenged from the box (2026-06, first seen on cdt.org) while
safari/firefox passed 4/4 -> try profiles in order, first 200 wins. A profile
can also be rejected at the connection level (reset/handshake timeout), so each
attempt is exception-tolerant; only if every profile raises does the last error
propagate. Non-challenge statuses (404/500/...) are the origin answering -- a
new fingerprint can't change them, so they short-circuit.
"""
from __future__ import annotations

TIMEOUT = 30.0
TLS_PROFILES = ("safari", "firefox", "chrome")
_CHALLENGE_STATUSES = {403, 503}


def curl_get(url: str, timeout: float = TIMEOUT) -> tuple[int, str]:
    from curl_cffi import requests as creq
    code, text, last_exc = 0, "", None
    for prof in TLS_PROFILES:
        try:
            with creq.Session(impersonate=prof) as s:
                r = s.get(url, timeout=timeout)
        except Exception as e:  # noqa: BLE001 -- challenged profiles often reset
            last_exc = e
            continue
        code, text = r.status_code, (r.text or "")
        if code == 200 or code not in _CHALLENGE_STATUSES:
            break
    if code == 0 and last_exc is not None:
        raise last_exc
    return code, text
