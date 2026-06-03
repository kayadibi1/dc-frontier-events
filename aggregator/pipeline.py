"""Orchestrate fetch -> normalize -> dedupe -> filter -> store -> emit, logging
concrete counts at each stage. Returns a summary dict (also used by tests).
"""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta, timezone

import json as _json

from .alerts import build_alerts, big_names_in_dc
from .config import SOURCES
from .credentials import (
    CREDENTIALS,
    apply_fetched_info,
    credentials_dicts,
    open_applications,
    render_credentials_md,
    render_deadlines_md,
    upcoming_deadlines,
)
from .deadline_fetch import fetch_deadline_info
from .dedupe import dedupe
from .digest import build_digest, render_html
from .emit import filter_upcoming, write_ics, write_json, write_map, write_rss
from .enrich import default_fetch, enrich_layer2, recompute_topics
from .geocode import DEFAULT_CACHE, geocode_events, nominatim_query, scrub_far_geo
from .validate import validate_pre_filter, validate_post_geocode
from .fetchers import gather_all
from .filter import apply_filters
from .health import load_health, render_status_html, update_health, write_health
from .web import render_index
from .notify import build_message, deliver
from .rank import score_event, top_upcoming
from .storage import open_store


def run(out_dir: str = "out", db_path: str = "data/events.db",
        today: str | None = None, enrich: bool = True) -> dict:
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

    # Per-source health + regression detection (enterprise observability): persist
    # each run's per-source status and flag any source that was healthy last run
    # and is now broken, so a silently-failing scraper is caught, not just absorbed.
    health_path = os.path.join(os.path.dirname(db_path) or ".", "source_health.json")
    prior_health = load_health(health_path)
    observations = [(r.source.slug, len(r.events), r.error) for r in results]
    health, regressions = update_health(prior_health, observations, today)
    write_health(health, health_path)
    if regressions:
        print(f"[health] REGRESSIONS (healthy -> broken since last run): {', '.join(regressions)}")
    healthy = sum(1 for h in health.values() if h["status"] == "ok")

    total_raw = len(raw_events)
    if enrich:
        layer_by_source = {s.slug: s.layer for s in SOURCES}
        n_enriched = asyncio.run(enrich_layer2(raw_events, layer_by_source, default_fetch))
        print(f"[enrich] enriched {n_enriched} Layer-2 events (descriptions + speakers)")
        # Re-derive topics from enriched blurbs for curated Layer-2 policy sources,
        # so a vague-titled but on-topic event ("A Conversation With...") is kept.
        curated_l2 = {s.slug for s in SOURCES if s.layer == 2 and s.dc_curated}
        recompute_topics(raw_events, curated_l2)
    raw_events, pre_dropped = validate_pre_filter(raw_events, today)
    print(f"[validate] pre-filter: excluded "
          f"{sum(1 for d in pre_dropped if d[1] == 'date')}, cleaned {len(pre_dropped)} field(s)")
    deduped, removed = dedupe(raw_events)
    kept, fstats = apply_filters(deduped)

    store = open_store(db_path)
    prior_ids = store.existing_ids()          # ids known before this run -> new diff
    store.close()

    # Scrub junk feed GEO BEFORE geocode so a real DC address can re-pin (B2).
    scrub_far_geo(kept)
    if enrich:
        n_geo = geocode_events(kept)
        print(f"[geocode] added coordinates to {n_geo} event(s)")
    clean, post_dropped = validate_post_geocode(
        kept, today, query=nominatim_query if enrich else None,
        cache_path=DEFAULT_CACHE if enrich else None)
    print(f"[validate] post-geocode: dropped {len(post_dropped)} field(s); "
          f"kept {len(clean)}/{len(kept)}")

    # Persist the VALIDATED active set; the store is the durable archive.
    store = open_store(db_path)
    store.upsert_many(clean)
    archived_total = store.mark_archived({e.id for e in clean})
    # Prune archived events older than ~2 years to bound store growth.
    cutoff = (date.fromisoformat(today) - timedelta(days=730)).isoformat()
    pruned = store.prune(cutoff)
    roundtrip = store.all_events()
    store_total = store.count()
    store.close()
    assert len(roundtrip) >= len(clean), "storage round-trip lost rows"
    gone = sorted(set(prior_ids) - {e.id for e in clean})  # in store, not in this run

    emitted = sorted(clean, key=lambda e: e.start or "")
    for e in emitted:
        e.raw["score"] = score_event(e, today)   # ephemeral; AFTER store
    big = [e for e in emitted if e.is_big_name]
    upcoming = filter_upcoming(emitted, today)
    top = top_upcoming(emitted, today, 25)
    ics_n = write_ics(emitted, f"{out_dir}/events.ics", today,
                      cal_name="DC AI & Frontier Tech Events")
    rss_n = write_rss(emitted, f"{out_dir}/feed.xml")
    write_ics(big, f"{out_dir}/events-big-names.ics", today,
              cal_name="DC AI — Big Names")
    write_rss(big, f"{out_dir}/feed-big-names.xml", "DC AI & Frontier Tech -- Big Names")
    up_n = write_ics(upcoming, f"{out_dir}/events-upcoming.ics", today,
                     cal_name="DC AI & Frontier Tech — Upcoming")
    write_rss(upcoming, f"{out_dir}/feed-upcoming.xml", "DC AI & Frontier Tech -- Upcoming")
    write_rss(top, f"{out_dir}/feed-top.xml", "DC AI & Frontier Tech -- Top Picks")
    write_json(emitted, f"{out_dir}/events.json")
    mapped = write_map(emitted, f"{out_dir}/map.html", today)
    # Ops status page + machine-readable health (enterprise observability).
    src_names = {s.slug: s.name for s in SOURCES}
    src_layers = {s.slug: s.layer for s in SOURCES}
    with open(f"{out_dir}/status.html", "w", encoding="utf-8") as f:
        f.write(render_status_html(health, today, src_names, src_layers))
    write_health(health, f"{out_dir}/health.json")
    # Flagship landing page (the primary public surface; the map is secondary).
    with open(f"{out_dir}/index.html", "w", encoding="utf-8") as f:
        f.write(render_index(emitted, today,
                             {"sources_healthy": healthy, "sources_total": len(SOURCES)}))
    archive_n = write_ics(sorted(roundtrip, key=lambda e: e.start or ""),
                          f"{out_dir}/events-archive.ics", today,
                          cal_name="DC AI & Frontier Tech — Archive")
    # Credentials track (curated prestige courses/certs/programs) — separate
    # from the DC event pipeline; not date/location bound. Auto-fetch each
    # program's page for a real future application deadline (best-effort; expired
    # / missing dates are simply not applied), then merge into the curated list.
    if enrich:
        found = asyncio.run(
            fetch_deadline_info([c.scrape_url for c in CREDENTIALS], today))
        n_dates = sum(1 for i in found.values() if i.get("deadline"))
        n_open = sum(1 for i in found.values() if i.get("status") == "open")
        n_blind = sum(1 for i in found.values() if not i.get("ok"))
        if found:
            print(f"[deadlines] auto-detected {n_dates} date(s), {n_open} open "
                  f"application(s), {n_blind} unreadable page(s)")
    else:
        found = {}
    creds = apply_fetched_info(found)
    with open(f"{out_dir}/credentials.md", "w", encoding="utf-8") as f:
        f.write(render_credentials_md(creds))
    with open(f"{out_dir}/credentials.json", "w", encoding="utf-8") as f:
        _json.dump(credentials_dicts(creds), f, ensure_ascii=False, indent=2)
    with open(f"{out_dir}/deadlines.md", "w", encoding="utf-8") as f:
        f.write(render_deadlines_md(today, creds=creds))
    deadlines_soon = upcoming_deadlines(today, creds=creds)
    open_apps = open_applications(creds)

    digest_md = build_digest(emitted, today)
    digest_html = render_html(emitted, today)
    with open(f"{out_dir}/digest.md", "w", encoding="utf-8") as f:
        f.write(digest_md)  # out_dir already created by write_* above
    with open(f"{out_dir}/digest.html", "w", encoding="utf-8") as f:
        f.write(digest_html)

    new_events = [e for e in emitted if e.id not in prior_ids]
    new_big = [e for e in new_events if e.is_big_name]
    big_in_dc = big_names_in_dc(emitted, today)
    with open(f"{out_dir}/alerts.md", "w", encoding="utf-8") as f:
        f.write(build_alerts(new_events, new_big, today, first_run=not prior_ids,
                             deadlines_soon=deadlines_soon, open_apps=open_apps,
                             big_in_dc=big_in_dc))

    # Notify (digest + alerts). Dry-run unless SMTP_* env is set; never blocks.
    msg = build_message(digest_html, digest_md, today, up_n, len(new_big))
    notify_mode, notify_target = deliver(msg, out_dir, today)
    print(f"[notify] {notify_mode}: {notify_target}")

    summary = {
        "sources_total": len(SOURCES),
        "sources_live": sum(1 for v in per_source.values() if v > 0),
        "sources_healthy": healthy,
        "regressions": regressions,
        "layers_live": sorted(layers_live),
        "per_source": per_source,
        "quarantined": quarantined,
        "raw_events": total_raw,
        "after_dedupe": len(deduped),
        "deduped_removed": removed,
        "kept_after_filter": len(clean),
        "pre_excluded": sum(1 for d in pre_dropped if d[1] == "date"),
        "post_excluded": sum(1 for d in post_dropped if d[1] == "dc"),
        "dropped_location": fstats["dropped_location"],
        "dropped_topic": fstats["dropped_topic"],
        "dropped_admin": fstats["dropped_admin"],
        "big_name": len(big),
        "new_events": len(new_events),
        "new_big_name": len(new_big),
        "big_in_dc": len(big_in_dc),
        "notify": notify_mode,
        "upcoming": up_n,
        "today": today,
        "mapped": mapped,
        "archive_events": archive_n,
        "gone": len(gone),
        "archived_total": archived_total,
        "pruned": pruned,
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
          f"(dropped {s['dropped_location']} loc, {s['dropped_topic']} topic, "
          f"{s['dropped_admin']} admin)")
    print(f"validated:         pre-excluded={s['pre_excluded']} post-excluded={s['post_excluded']}")
    print(f"big-name events:   {s['big_name']}")
    print(f"new since last run:{s['new_events']}  (new big-name: {s['new_big_name']})")
    print(f"big names in DC:    {s['big_in_dc']}  (in person, upcoming)")
    print(f"upcoming (>= {s['today']}): {s['upcoming']}")
    print(f"stored total:      {s['stored_total']}  (archive.ics={s['archive_events']}, "
          f"gone-from-sources={s['gone']})")
    print(f"partition:         active={s['kept_after_filter']} archived={s['archived_total']} "
          f"pruned={s['pruned']}")
    print(f"emitted:           events.ics={s['ics_events']}  feed.xml={s['rss_items']}  "
          f"map.html={s['mapped']} pins  events.json")
