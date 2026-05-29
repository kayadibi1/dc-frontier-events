"""Orchestrate fetch -> normalize -> dedupe -> filter -> store -> emit, logging
concrete counts at each stage. Returns a summary dict (also used by tests).
"""

from __future__ import annotations

import asyncio

from .config import SOURCES
from .dedupe import dedupe
from .emit import write_ics, write_rss
from .fetchers import fetch_all
from .filter import apply_filters
from .normalize import parse_ics
from .storage import open_store


def run(out_dir: str = "out", db_path: str = "data/events.db") -> dict:
    results = asyncio.run(fetch_all(SOURCES))

    per_source: dict[str, int] = {}
    raw_events = []
    quarantined = []
    for res in results:
        if not res.ok:
            per_source[res.source.slug] = 0
            reason = res.error or ("empty (HTTP 200, 0 events)" if res.status == 200 else "no data")
            quarantined.append((res.source.slug, reason))
            print(f"[fetch] QUARANTINE {res.source.slug}: {reason}")
            continue
        evs = parse_ics(res.source, res.ics_text)
        per_source[res.source.slug] = len(evs)
        raw_events.extend(evs)
        print(f"[fetch] {res.source.slug} (layer {res.source.layer}): {len(evs)} events")

    total_raw = len(raw_events)
    deduped, removed = dedupe(raw_events)
    kept, fstats = apply_filters(deduped)

    # Persist for the durable archive; emit reflects THIS run's fresh fetch
    # (we full-refresh every source each run, so `kept` is the current truth;
    # the store accumulates history). all_events() round-trips through storage.
    store = open_store(db_path)
    store.upsert_many(kept)
    roundtrip = store.all_events()
    store_total = store.count()
    store.close()
    assert len(roundtrip) >= len(kept), "storage round-trip lost rows"

    emitted = sorted(kept, key=lambda e: e.start or "")
    big = [e for e in emitted if e.is_big_name]
    ics_n = write_ics(emitted, f"{out_dir}/events.ics")
    rss_n = write_rss(emitted, f"{out_dir}/feed.xml")
    write_ics(big, f"{out_dir}/events-big-names.ics")
    write_rss(big, f"{out_dir}/feed-big-names.xml", "DC AI & Semiconductor -- Big Names")

    summary = {
        "sources_total": len(SOURCES),
        "sources_live": sum(1 for v in per_source.values() if v > 0),
        "per_source": per_source,
        "quarantined": quarantined,
        "raw_events": total_raw,
        "after_dedupe": len(deduped),
        "deduped_removed": removed,
        "kept_after_filter": len(kept),
        "dropped_location": fstats["dropped_location"],
        "dropped_topic": fstats["dropped_topic"],
        "big_name": len(big),
        "stored_total": store_total,
        "ics_events": ics_n,
        "rss_items": rss_n,
    }
    _print_summary(summary)
    return summary


def _print_summary(s: dict) -> None:
    live = ", ".join(f"{k}={v}" for k, v in s["per_source"].items())
    print("\n=== RUN SUMMARY ===")
    print(f"sources:           {s['sources_live']}/{s['sources_total']} live  ({live})")
    if s["quarantined"]:
        q = ", ".join(f"{slug} [{why}]" for slug, why in s["quarantined"])
        print(f"quarantined:       {q}")
    print(f"raw events:        {s['raw_events']}")
    print(f"after dedupe:      {s['after_dedupe']}  (removed {s['deduped_removed']})")
    print(f"kept after filter: {s['kept_after_filter']}  "
          f"(dropped {s['dropped_location']} loc, {s['dropped_topic']} topic)")
    print(f"big-name events:   {s['big_name']}")
    print(f"stored total:      {s['stored_total']}")
    print(f"emitted:           events.ics={s['ics_events']}  feed.xml={s['rss_items']}")
