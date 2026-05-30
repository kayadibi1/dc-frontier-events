# Subscribe to the calendar (Google Calendar, Apple, Outlook)

The pipeline emits standard iCalendar (`.ics`) files that work as **live calendar
subscriptions** — add one by URL and your calendar app re-polls it for new events.
Each feed carries `X-WR-CALNAME`, `X-WR-CALDESC`, `X-WR-TIMEZONE`, and an
auto-refresh hint (`REFRESH-INTERVAL` / `X-PUBLISHED-TTL` = 12h).

## Which feed?

| File | What's in it | Best for |
|---|---|---|
| `events-upcoming.ics` | only events today-or-later | **recommended** — a clean forward calendar |
| `events.ics` | everything kept this run (incl. recent past) | full view |
| `events-big-names.ics` | only marquee-org/person events | just the prestige events |
| `events-archive.ics` | the durable history from the store | reference |

Most people want **`events-upcoming.ics`**.

## Step 1 — host the file at a public URL (one-time, manual)

Google can only subscribe to a publicly reachable `https://` URL, so the local
`out/*.ics` must be hosted somewhere. Pick one:

- **GitHub Pages (simplest):** commit `out/events-upcoming.ics` to a public repo
  with Pages enabled (or push it to a `gh-pages` branch). Your URL becomes
  `https://<user>.github.io/<repo>/events-upcoming.ics`.
- **Any object store / static host:** S3, Cloudflare R2, Netlify, or the MinIO
  bucket if you run one — upload the file and use its public object URL.
- **Re-publish on a schedule:** run `python -m aggregator` on a cron / GitHub
  Action (e.g. every 12h) and re-upload, so the hosted file stays current.

> This hosting step is yours to do — it can't be done from inside the tool.

## Step 2 — add it to Google Calendar

1. Open Google Calendar (web).
2. Left sidebar → **Other calendars** → **+** → **From URL**.
3. Paste the public `https://…/events-upcoming.ics` URL → **Add calendar**.
4. It appears under "Other calendars"; rename/recolor via its options.

**Apple Calendar:** File → New Calendar Subscription → paste URL.
**Outlook:** Add calendar → Subscribe from web → paste URL.

## Step 3 — refresh cadence (honest caveat)

The files request a 12-hour refresh (`REFRESH-INTERVAL:PT12H`), but **Google
decides its own polling cadence and often only re-fetches a subscribed URL every
~8–24 hours** — there's no way to force it faster from the file. So a brand-new
event can take up to a day to appear. If you need it sooner, re-add the URL, or
use the per-run `out/alerts.md` / email digest for time-sensitive items.

## One-shot import vs. subscription

Subscribing (above) keeps updating. If you'd rather drop the current events in
once (no future updates), use Google Calendar **Settings → Import & export →
Import** and select a downloaded `.ics` instead.
