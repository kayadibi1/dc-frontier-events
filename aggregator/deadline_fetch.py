"""Auto-fetch application deadlines + open/closed status for credential programs.

On each run, fetch each program's real cohort/application/jobs page and look for:
  - a date adjacent to an application keyword ("apply by", "applications close",
    "deadline", "due", "register by"), OR a structured "applicationDeadline"
    JSON field (Ashby/Greenhouse boards expose this);
  - the application OPEN/closed status, which is real actionable info even when
    no date is posted (e.g. Anthropic Fellows "apply now").

Honesty rules: only accept a FUTURE date (rejects expired/archived cycle dates
like a past "apply by January 20, 2025"); ignore a bare date with no keyword;
never invent. Pure extractors (html -> result) are unit-tested offline; the
fetch wrappers are best-effort (failures skip).
"""

from __future__ import annotations

import asyncio
import re
from datetime import date

import httpx

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 25.0

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
_OPEN = re.compile(
    r"appl(?:y now|ications? (?:are |now )?open|ications? open now)|"
    r"now accepting applications|accepting applications|apply today|"
    r"applications? (?:are )?(?:currently )?open", re.I)
_CLOSED = re.compile(
    r"applications? (?:are |have )?clos|no longer accepting|"
    r"applications? closed|deadline has passed|round (?:is )?closed", re.I)
# Structured boards (OpenAI/Ashby, etc.) expose this JSON field.
_JSON_DEADLINE = re.compile(r'"applicationDeadline"\s*:\s*"([^"]+)"')


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
    text = _WS.sub(" ", _TAG.sub(" ", html or ""))
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
    text = _WS.sub(" ", _TAG.sub(" ", html or ""))
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


async def _fetch_one(client: httpx.AsyncClient, url: str, today_iso: str) -> dict:
    try:
        r = await client.get(url)
        if r.status_code != 200:
            return {"deadline": None, "status": ""}
        return extract_info(r.text, today_iso)
    except Exception:
        return {"deadline": None, "status": ""}


async def fetch_deadline_info(urls: list[str], today_iso: str) -> dict[str, dict]:
    """url -> {'deadline': iso|None, 'status': ...} for urls where a deadline OR
    status was found. Best-effort (unreachable / empty pages absent)."""
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"}
    async with httpx.AsyncClient(headers=headers, timeout=TIMEOUT,
                                 follow_redirects=True) as client:
        results = await asyncio.gather(
            *[_fetch_one(client, u, today_iso) for u in urls])
    return {u: info for u, info in zip(urls, results)
            if info.get("deadline") or info.get("status")}


async def fetch_deadlines(urls: list[str], today_iso: str) -> dict[str, str]:
    """Back-compat: url -> future deadline ISO date only (subset of info)."""
    info = await fetch_deadline_info(urls, today_iso)
    return {u: i["deadline"] for u, i in info.items() if i.get("deadline")}
