"""Auto-fetch application deadlines + open/closed status for credential programs.

On each run, fetch each program's real cohort/application/jobs page and look for:
  - a date adjacent to an application keyword ("apply by", "applications close",
    "deadline", "due", "register by"), OR a structured "applicationDeadline"
    JSON field (Ashby/Greenhouse boards expose this);
  - the application OPEN/closed status, which is real actionable info even when
    no date is posted (e.g. Anthropic Fellows "apply now").

Fetch fidelity matters as much as extraction: a page we could NOT read (a WAF
403, an empty body) must not masquerade as "no deadline found". So each fetch
reports `ok` (did we actually read real content?), and non-200 responses are
retried with curl_cffi browser-TLS impersonation (same trick the event
fetchers use for Cloudflare-walled sites like CSET). Unreadable pages surface
downstream as "⚠️ couldn't verify", never as a silent "rolling".

Honesty rules: only accept a FUTURE date (rejects expired/archived cycle dates
like a past "apply by January 20, 2025"); ignore a bare date with no keyword;
never invent; never extract from a page we couldn't actually read. Pure
extractors (html -> result) are unit-tested offline; the fetch wrappers are
best-effort (failures skip, flagged not-ok).
"""

from __future__ import annotations

import asyncio
import re
from datetime import date

import httpx

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 25.0
# A 200 response with less readable text than this is treated as a non-page
# (empty shell / error stub) -> not readable.
MIN_READABLE_CHARS = 500

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_KEYWORD = (r"appl(?:y|ication[s]?)\s+(?:by|close[sd]?|due|deadline|open[s]? until)|"
            r"\bdeadline\b|\bdue\s+(?:by|date)\b|submissions?\s+(?:close|due)|"
            r"close[sd]?\s+on|register\s+by")
_MONTH = (r"(?:January|February|March|April|May|June|July|August|September|"
          r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)")
_DATE = rf"{_MONTH}\.?\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}/\d{{1,2}}/\d{{4}}"

_KW_THEN_DATE = re.compile(rf"(?:{_KEYWORD})[^.\n]{{0,60}}?({_DATE})", re.I)
_DATE_THEN_KW = re.compile(rf"({_DATE})[^.\n]{{0,40}}?(?:{_KEYWORD})", re.I)

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
_ABBR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
         "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}

# Application open / closed phrasing (status is real even with no date).
# `open\b` (word boundary) is load-bearing: without it, "application openings"
# (a noun, as on OpenAI Residency's rolling-hire page) falsely matched as
# "applications open". Only count an explicit, current "apply now / open" signal.
_OPEN = re.compile(
    r"\bapply now\b|\bapply today\b|"
    r"now accepting applications|accepting applications|"
    r"applications?\s+(?:are\s+)?(?:now\s+)?(?:currently\s+)?open\b|"
    r"\bopen\b\s+(?:now\s+)?for\s+applications?", re.I)
_CLOSED = re.compile(
    r"applications? (?:are |have )?clos|no longer accepting|"
    r"applications? closed|deadline has passed|round (?:is )?closed", re.I)
# Structured boards (OpenAI/Ashby, etc.) expose this JSON field.
_JSON_DEADLINE = re.compile(r'"applicationDeadline"\s*:\s*"([^"]+)"')


def _clean(html: str) -> str:
    """Strip tags + collapse whitespace -> readable text."""
    return _WS.sub(" ", _TAG.sub(" ", html or "")).strip()


def _to_iso(raw: str) -> str | None:
    raw = raw.strip().rstrip(".,")
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:  # US M/D/Y
        mo, da, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.match(rf"({_MONTH})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})", raw, re.I)
        if not m:
            return None
        name = m.group(1).lower().rstrip(".")
        mo = _MONTHS.get(name) or _ABBR.get(name)
        da, yr = int(m.group(2)), int(m.group(3))
    if not mo or not (1 <= da <= 31):
        return None
    try:
        return date(yr, mo, da).isoformat()
    except ValueError:
        return None


def extract_deadline(html: str, today_iso: str) -> str | None:
    """Soonest FUTURE deadline date (ISO) found near a deadline keyword, else None."""
    text = _clean(html)
    cands: set[str] = set()
    for rx in (_KW_THEN_DATE, _DATE_THEN_KW):
        for m in rx.finditer(text):
            iso = _to_iso(m.group(1))
            if iso:
                cands.add(iso)
    future = sorted(d for d in cands if d >= today_iso)
    return future[0] if future else None


def extract_app_status(html: str) -> str:
    """'open' | 'closed' | '' from application-status phrasing. 'closed' wins
    (an explicit close is more decisive than a stray 'apply')."""
    text = _clean(html)
    if _CLOSED.search(text):
        return "closed"
    if _OPEN.search(text):
        return "open"
    return ""


def _json_deadline(html: str, today_iso: str) -> str | None:
    """Soonest FUTURE date from a structured 'applicationDeadline' JSON field."""
    future = []
    for raw in _JSON_DEADLINE.findall(html or ""):
        iso = raw[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso) and iso >= today_iso:
            future.append(iso)
    return sorted(future)[0] if future else None


def extract_info(html: str, today_iso: str) -> dict:
    """Combined: {'deadline': iso|None, 'status': 'open'|'closed'|''}.
    Prefers a structured JSON deadline, else the keyword-adjacent text date."""
    deadline = _json_deadline(html, today_iso) or extract_deadline(html, today_iso)
    return {"deadline": deadline, "status": extract_app_status(html)}


def _curl_get(url: str) -> tuple[int, str]:
    """Sync fetch via curl_cffi with Chrome TLS impersonation (beats most WAFs).
    Run in a thread. Returns (status_code, html); (0, '') if curl_cffi absent."""
    try:
        from curl_cffi import requests as creq
    except Exception:
        return 0, ""
    r = creq.Session(impersonate="chrome").get(url, timeout=TIMEOUT)
    return r.status_code, r.text or ""


async def _fetch_raw(client: httpx.AsyncClient, url: str) -> tuple[int, str]:
    """(status_code, html). Tries httpx first; on any non-200 (e.g. a Cloudflare
    403) retries with curl_cffi browser-TLS impersonation before giving up."""
    code, html = 0, ""
    try:
        r = await client.get(url)
        code, html = r.status_code, r.text or ""
    except Exception:
        pass
    if code != 200:  # blocked / errored -> try to look like a real browser
        try:
            code, html = await asyncio.to_thread(_curl_get, url)
        except Exception:
            pass
    return code, html


def _interpret(code: int, html: str, today_iso: str) -> dict:
    """Pure: a fetch result -> {'deadline', 'status', 'ok', 'code'}. `ok` is True
    only for a real page (HTTP 200 + enough text); extraction runs ONLY on a
    readable page, so a block/empty page can never yield a false deadline/status."""
    ok = code == 200 and len(_clean(html)) >= MIN_READABLE_CHARS
    info = extract_info(html, today_iso) if ok else {"deadline": None, "status": ""}
    return {"deadline": info["deadline"], "status": info["status"],
            "ok": ok, "code": code}


def _reconcile(first: dict, second: dict) -> dict:
    """Confirmation guard: keep a positive signal only if a second fetch agrees.
    WAF/variant pages return slightly different bytes per fetch (observed: the
    OpenAI Residency page's length varied across repeated fetches), so a
    deadline/'open' present in one variant but not the next is not trustworthy.
    On disagreement, downgrade to no-signal and flag `unstable` for manual
    review rather than emit a false 'apply now'."""
    if (first["deadline"], first["status"]) == (second["deadline"], second["status"]):
        return {**first, "unstable": False}
    return {"deadline": None, "status": "", "ok": first["ok"],
            "code": first["code"], "unstable": True}


async def _fetch_one(client: httpx.AsyncClient, url: str, today_iso: str) -> dict:
    """Fetch `url` (httpx, then curl_cffi on a block), interpret, and CONFIRM:
    a positive signal is re-fetched once and kept only if it reproduces, so a
    transient false 'open'/date from a flaky page can't slip through."""
    code, html = await _fetch_raw(client, url)
    info = _interpret(code, html, today_iso)
    if info["ok"] and (info["deadline"] or info["status"]):
        code2, html2 = await _fetch_raw(client, url)
        info = _reconcile(info, _interpret(code2, html2, today_iso))
    else:
        info["unstable"] = False
    return info


async def fetch_deadline_info(urls: list[str], today_iso: str) -> dict[str, dict]:
    """url -> {'deadline', 'status', 'ok', 'code'} for EVERY url attempted (not
    just hits), so callers can tell a real "nothing found" from a failed read."""
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"}
    async with httpx.AsyncClient(headers=headers, timeout=TIMEOUT,
                                 follow_redirects=True) as client:
        results = await asyncio.gather(
            *[_fetch_one(client, u, today_iso) for u in urls])
    return dict(zip(urls, results))


async def fetch_deadlines(urls: list[str], today_iso: str) -> dict[str, str]:
    """Back-compat: url -> future deadline ISO date only (subset of info)."""
    info = await fetch_deadline_info(urls, today_iso)
    return {u: i["deadline"] for u, i in info.items() if i.get("deadline")}
