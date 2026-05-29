"""Orchestrate fetch -> normalize -> dedupe -> filter -> store -> emit, logging
concrete counts at each stage. Returns a summary dict (also used by tests).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .alerts import build_alerts
from .config import SOURCES
from .dedupe import dedupe
from .digest import build_digest
from .emit import filter_upcoming, write_ics, write_json, write_map, write_rss
from .fetchers import gather_all
from .filter import apply_filters
from .rank import score_event, top_upcoming
from .storage import open_store


def run(out_dir: str = "out", db_path: str = "data/events.db",
        today: str | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date().isoformat()
    results = asyncio.run(gather_all(SOURCES))

    per_source: dict[str, int] = {}
    layers_live: set[int] = set()
    raw_events = []
    quarantined = []
    for res in results:
        if not res.ok:
            per_source[res.source.slug] = 0
            quarantined.append((res.source.slug, res.reason))
            print(f"[fetch] QUARANTINE {res.source.slug}: {res.reason}")
            continue
        per_source[res.source.slug] = len(res.events)
        layers_live.add(res.source.layer)
        raw_events.extend(res.events)
        print(f"[fetch] {res.source.slug} (layer {res.source.layer}): {len(res.events)} events")

    total_raw = len(raw_events)
    deduped, removed = dedupe(raw_events)
    kept, fstats = apply_filters(deduped)

    # Persist for the durable archive; emit reflects THIS run's fresh fetch
    # (we full-refresh every source each run, so `kept` is the current truth;
    # the store accumulates history). all_events() round-trips through storage.
    store = open_store(db_path)
    prior_ids = store.existing_ids()          # ids known before this run -> new-event diff
    store.upsert_many(kept)
    roundtrip = store.all_events()
    store_total = store.count()
    store.close()
    assert len(roundtrip) >= len(kept), "storage round-trip lost rows"

    emitted = sorted(kept, key=lambda e: e.start or "")
    for e in emitted:
        e.raw["score"] = score_event(e, today)
    big = [e for e in emitted if e.is_big_name]
    upcoming = filter_upcoming(emitted, today)
    top = top_upcoming(emitted, today, 25)
    ics_n = write_ics(emitted, f"{out_dir}/events.ics")
    rss_n = write_rss(emitted, f"{out_dir}/feed.xml")
    write_ics(big, f"{out_dir}/events-big-names.ics")
    write_rss(big, f"{out_dir}/feed-big-names.xml", "DC AI & Semiconductor -- Big Names")
    up_n = write_ics(upcoming, f"{out_dir}/events-upcoming.ics")
    write_rss(upcoming, f"{out_dir}/feed-upcoming.xml", "DC AI & Semiconductor -- Upcoming")
    write_rss(top, f"{out_dir}/feed-top.xml", "DC AI & Semiconductor -- Top Picks")
    write_json(emitted, f"{out_dir}/events.json")
    mapped = write_map(emitted, f"{out_dir}/map.html")
    with open(f"{out_dir}/digest.md", "w", encoding="utf-8") as f:
        f.write(build_digest(emitted, today))  # out_dir already created by write_* above

    new_events = [e for e in emitted if e.id not in prior_ids]
    new_big = [e for e in new_events if e.is_big_name]
    with open(f"{out_dir}/alerts.md", "w", encoding="utf-8") as f:
        f.write(build_alerts(new_events, new_big, today, first_run=not prior_ids))

    summary = {
        "sources_total": len(SOURCES),
        "sources_live": sum(1 for v in per_source.values() if v > 0),
        "layers_live": sorted(layers_live),
        "per_source": per_source,
        "quarantined": quarantined,
        "raw_events": total_raw,
        "after_dedupe": len(deduped),
        "deduped_removed": removed,
        "kept_after_filter": len(kept),
        "dropped_location": fstats["dropped_location"],
        "dropped_topic": fstats["dropped_topic"],
        "big_name": len(big),
        "new_events": len(new_events),
        "new_big_name": len(new_big),
        "upcoming": up_n,
        "today": today,
        "mapped": mapped,
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
    print(f"layers live:       {s['layers_live']}")
    if s["quarantined"]:
        q = ", ".join(f"{slug} [{why}]" for slug, why in s["quarantined"])
        print(f"quarantined:       {q}")
    print(f"raw events:        {s['raw_events']}")
    print(f"after dedupe:      {s['after_dedupe']}  (removed {s['deduped_removed']})")
    print(f"kept after filter: {s['kept_after_filter']}  "
          f"(dropped {s['dropped_location']} loc, {s['dropped_topic']} topic)")
    print(f"big-name events:   {s['big_name']}")
    print(f"new since last run:{s['new_events']}  (new big-name: {s['new_big_name']})")
    print(f"upcoming (>= {s['today']}): {s['upcoming']}")
    print(f"stored total:      {s['stored_total']}")
    print(f"emitted:           events.ics={s['ics_events']}  feed.xml={s['rss_items']}  "
          f"map.html={s['mapped']} pins  events.json")
