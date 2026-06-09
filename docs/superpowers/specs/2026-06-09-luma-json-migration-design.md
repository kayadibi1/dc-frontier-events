# Luma layer: ICS → JSON migration + city-wide discover source

**Date:** 2026-06-09 · **Status:** approved (user picked Approach B, future-only)

## Context

The Luma layer consumed per-calendar ICS feeds (`api.lu.ma/ics/get?entity=calendar&id=cal-…`).
Two failures exposed its weaknesses on 2026-06-09:

- The `ai` source (Global AI) died permanently: Luma converted it to a *discover*
  calendar (`disccal-…`), which has no ICS export.
- DCtechevents went dormant (calendar verified empty upstream).

Probes established (all live-verified 2026-06-09):

- `api.lu.ma/calendar/get-items?calendar_api_id=<cal>&period=future` returns the
  calendar's complete upcoming set as JSON (DC2: 4 entries = exactly the 4
  upcoming VEVENTs in its ICS; the other 69 ICS events are past).
- `api.lu.ma/discover/get-paginated-events?discover_place_api_id=discplace-AANPgOymN6bqFn8`
  returns the **whole-of-Luma DC-area upcoming feed** (~16+ events, paginated),
  including events from calendars we don't subscribe to.
- Event JSON carries `coordinate` (lat/lng), IANA `timezone`, `location_type` /
  `virtual_info`, `geo_address_info`, and a direct event `url` — all richer than
  the ICS, whose DESCRIPTION is boilerplate ("Get up-to-date information at: …").

## Goals (user-selected)

1. **Coverage:** city-wide DC net — catch Luma AI events on calendars we never curated.
2. **Replace the lost global-AI feed** — subsumed by goal 1: the radar stays
   DC-physical-only (user decision), and any global calendar's DC event appears
   in the DC discover feed.
3. **Richer per-event data:** coordinates, real timezones, virtual flags from JSON.

Out of scope (user deselected): resilience automation (auto-resolving cal_ids,
dead-calendar alerting beyond existing health.py).

## Design

### Fetchers (`aggregator/fetchers/luma.py`, rewritten)

- `fetch_luma(source)` — calendar sources: GET `get-items` with
  `period=future&pagination_limit=100`, follow `next_cursor` while `has_more`.
- `fetch_luma_discover(source)` — new adapter kind `"luma-discover"`: GET
  `get-paginated-events` with `pagination_limit=50`, same pagination loop.
- Both share `_event_from_json(source, entry) -> Event | None` (pure, fixture-tested):

| Event field | JSON source | Note |
|---|---|---|
| `id` | `event.api_id` (`evt-XXX`) | identical to ICS-normalized ids → store continuity + cross-source dedupe |
| `title` | `event.name` | |
| `start` | `event.start_at` + `event.timezone` | UTC → venue-local tz-aware ISO (zoneinfo) |
| `end` | `event.end_at` | same conversion |
| `location` | `event.geo_address_info` | address / city_state, best available text |
| coords | `event.coordinate` | structured → geocoder skipped, no 📍approx |
| virtual | `event.location_type` / `virtual_info` | |
| `source_url` | `https://lu.ma/<event.url>` | replaces "information at:" regex |
| `organizer` | source title | as before |
| `topics` | `detect_topics(title)` | ICS desc was boilerplate → no regression |

- Provenance: location/time = `structured` where taken from JSON.
- HTTP: httpx async (api.lu.ma served every probe without WAF), existing Luma UA,
  TIMEOUT and retry semantics via the shared `_fetch_with_retry` wrapper.

### Config (`aggregator/config.py`)

- `LUMA_SOURCES` keep their `cal_id`s; `Source.ics_url` property deleted
  (with any remaining usages migrated).
- New source: `Source("luma-dc", "Luma DC (city-wide)", "luma-discover", 1, False,
  cal_id="discplace-AANPgOymN6bqFn8")` — NOT dc_curated: the strict topic/geo
  filter drops off-topic city events (mahjong, dinner clubs).
- DCtechevents stays (quarantines as `empty`, self-heals if it wakes).

### Pipeline

No changes. `ADAPTERS["luma"]` points at the new fetcher; `ADAPTERS["luma-discover"]`
added. Dedupe pass 1 (exact id) merges discover/calendar overlap; `_absorb_fields`
keeps the most-complete copy, so structured coords/tz upgrade calendar events too.

## Behavior changes (accepted)

- **Future-only:** past Luma events stop being re-seen → archived on the next run
  (store + `archive.ics` retain them). One-time `gone-from-sources` spike on first
  deploy run; raw counts drop sharply (DC2 73→4, aic-washington 302→upcoming-only).
  That is stale noise leaving, not coverage loss.
- Luma starts stored venue-local tz-aware instead of UTC.

## Failure modes

Identical quarantine semantics: non-200 → quarantined with HTTP reason; zero
entries → `empty`. Known cost of full migration: if Luma breaks these unofficial
endpoints, the whole Luma layer quarantines at once. Rollback = `git revert` to
the ICS fetcher (endpoint still live today).

## Testing

- Captured real JSON fixtures: one `get-items` page (DC2), one discover page.
- TDD: mapper field tests (id, tz-aware start, coords, virtual, url, topics),
  pagination across pages (fakes), 404/empty → quarantine, adapter routing.
- Live: `tools/live_check.py` per Luma source, full box build, before/after run
  summary comparison, `accuracy_check`.

## Risks

- Unofficial API drift (same class as the disccal break that killed `ai`).
  Mitigated by quarantine + health fail-streaks + trivial revert.
- Discover feed horizon is near-term; calendar sources keep the longer horizon.
