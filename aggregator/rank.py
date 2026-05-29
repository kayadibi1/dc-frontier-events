"""Relevance scoring (GOAL: rank by relevance + proximity + big name).

Pure functions over normalized Events so they are trivially testable. Weights
are interpretable: a big-name event dominates; on-topic + upcoming + close-to-DC
add up underneath it.
"""

from __future__ import annotations

import math

from .models import Event

DC_CENTER = (38.9007, -77.0339)  # downtown DC
W_TOPIC = 8.0       # per distinct real topic
W_BIG = 50.0        # is_big_name (GOAL's first-class signal)
W_UPCOMING = 20.0   # event is today or later
W_PROX_MAX = 5.0    # at DC center; linearly to 0 by ~40 km out


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _real_topics(ev: Event) -> int:
    return sum(1 for t in ev.topics if not t.startswith("big:"))


def score_event(ev: Event, today_iso: str) -> float:
    s = W_TOPIC * _real_topics(ev)
    if ev.is_big_name:
        s += W_BIG
    if (ev.start or "")[:10] >= today_iso:
        s += W_UPCOMING
    if ev.lat is not None and ev.lng is not None:
        d = _haversine_km(ev.lat, ev.lng, *DC_CENTER)
        s += max(0.0, W_PROX_MAX * (1 - d / 40.0))
    return round(s, 2)


def top_upcoming(events: list[Event], today_iso: str, n: int = 25) -> list[Event]:
    upcoming = [e for e in events if (e.start or "")[:10] >= today_iso]
    upcoming.sort(key=lambda e: (-score_event(e, today_iso), e.start or ""))
    return upcoming[:n]
