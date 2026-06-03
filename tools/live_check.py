"""Live single-source check: fetch -> enrich -> filter, show raw + kept events.

Honors the BACKLOG rule: a new adapter must produce real on-topic DC events
against the LIVE page, not just pass fixture tests.

Usage: python tools/live_check.py <slug> [<slug> ...]
"""
from __future__ import annotations

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from aggregator.config import SOURCES  # noqa: E402
from aggregator.enrich import default_fetch, enrich_layer2, recompute_topics  # noqa: E402
from aggregator.fetchers import gather_all  # noqa: E402
from aggregator.filter import apply_filters  # noqa: E402
from aggregator.validate import validate_pre_filter  # noqa: E402


def check(slugs: list[str]) -> None:
    today = "2026-06-02"
    srcs = [s for s in SOURCES if s.slug in slugs]
    if not srcs:
        print(f"no such source(s): {slugs}; available: {[s.slug for s in SOURCES]}")
        return
    results = asyncio.run(gather_all(srcs))
    raw = []
    for res in results:
        print(f"\n=== {res.source.slug} === fetched={len(res.events)} "
              f"ok={res.ok} reason={res.reason}")
        raw.extend(res.events)
    layer_by_source = {s.slug: s.layer for s in SOURCES}
    n = asyncio.run(enrich_layer2(raw, layer_by_source, default_fetch))
    recompute_topics(raw, {s.slug for s in SOURCES if s.layer == 2 and s.dc_curated})
    print(f"\n[enrich] enriched {n} layer-2 events")
    raw, _ = validate_pre_filter(raw, today)
    kept, stats = apply_filters(raw)
    print(f"\n--- RAW ({len(raw)}) ---")
    for e in raw:
        tops = ",".join(t for t in e.topics if not t.startswith("big:")) or "—"
        print(f"  {e.start[:10]} | {e.title[:60]} | topics={tops}")
    print(f"\n--- KEPT ({len(kept)}) | dropped: {stats} ---")
    for e in kept:
        tops = ",".join(e.topics) or "—"
        up = "UPCOMING" if e.start[:10] >= today else "past"
        print(f"  [{up}] {e.start[:10]} | {e.title[:55]}")
        print(f"       topics={tops}")
        print(f"       venue={e.venue_name or '—'} | addr={(e.address or '—')[:70]}")
        if e.speakers:
            print(f"       speakers={e.speakers[:6]}")


if __name__ == "__main__":
    check(sys.argv[1:] or ["itif"])
