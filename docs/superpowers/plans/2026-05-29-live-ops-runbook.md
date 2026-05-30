# Live Ops Runbook — SMTP Emailer + Postgres

> **For agentic workers:** This is an **operations runbook**, not a code plan — the
> emailer (`notify.py`, F4) and Postgres backend (`storage.PostgresStore`, F5) are already
> built and fallback-tested. These steps flip the live paths on and verify them. Use
> superpowers:executing-plans if you want checkpointed execution; otherwise run the steps directly.

**Goal:** Enable real email delivery of the digest/alerts, and run against a real Postgres database, then verify both end to end.

---

## A. Enable the SMTP emailer

`deliver()` sends when `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, and `SMTP_TO` are all set
(STARTTLS on `SMTP_PORT`, default 587); otherwise it writes a dry-run `.eml`.

### A1. Verify the send path locally (no real provider)

- [ ] **Start a local debugging SMTP server** (prints messages instead of sending):

```bash
python -m smtpd -n -c DebuggingServer localhost:1025
```
(Leave it running in one terminal. On Python ≥3.12 where `smtpd` is removed, use
`pip install aiosmtpd` then `python -m aiosmtpd -n -l localhost:1025`.)

- [ ] **Point the aggregator at it and run** (another terminal):

```bash
SMTP_HOST=localhost SMTP_PORT=1025 SMTP_USER=x SMTP_PASS=x \
  SMTP_FROM=dcfe@localhost SMTP_TO=me@localhost python -m aggregator
```
Note: `DebuggingServer` does not do STARTTLS/AUTH; if `deliver()` errors on `starttls()`
it falls back to dry-run (by design). To exercise the full STARTTLS+AUTH path, use a real
provider in A2. The local server confirms the message is built and handed to SMTP.

Expected: console shows either `[notify] sent: me@localhost` (message printed by the
debug server) or, if STARTTLS is rejected, `[notify] SMTP send failed (...); falling back
to dry-run` followed by `[notify] dry-run: out/email/...`. Both confirm the wiring.

### A2. Production send (real provider)

- [ ] Set real credentials (example: a transactional-email provider):

```bash
export SMTP_HOST=smtp.youprovider.com SMTP_PORT=587
export SMTP_USER=apikey SMTP_PASS=*** SMTP_FROM=digest@yourdomain SMTP_TO=you@yourdomain
python -m aggregator
```
Expected: `[notify] sent: you@yourdomain`; the email arrives with subject
`DC AI & Semiconductor — <date> (N upcoming, M new big-name)` and the HTML digest body.

- [ ] **Schedule it** (weekly): add a cron entry / scheduled task that exports the env and
  runs `python -m aggregator`. Verify one scheduled run delivers.

---

## B. Run against real Postgres

`open_store()` uses `PostgresStore` when `DATABASE_URL` is set and connectable, else SQLite.

### B1. Spin up a local Postgres for verification

- [ ] **Start Postgres** (Docker):

```bash
docker run --rm -d --name dcfe-pg -e POSTGRES_PASSWORD=pw -p 5432:5432 postgres:16
```

- [ ] **Install the driver** (optional extra) if not present:

```bash
pip install "psycopg2-binary>=2.9"
```

### B2. Run the pipeline against it

- [ ] **Point `DATABASE_URL` at the DB and run:**

```bash
DATABASE_URL="postgresql://postgres:pw@127.0.0.1:5432/postgres" python -m aggregator
```
Expected: `[storage] backend=postgres` (NOT the sqlite fallback line).

- [ ] **Verify rows landed and upsert is idempotent:**

```bash
docker exec dcfe-pg psql -U postgres -c "SELECT count(*) FROM events;"
# run the pipeline a second time, then re-check count -- it must NOT grow
DATABASE_URL="postgresql://postgres:pw@127.0.0.1:5432/postgres" python -m aggregator
docker exec dcfe-pg psql -U postgres -c "SELECT count(*), count(*) FILTER (WHERE is_big_name=1) AS big FROM events;"
```
Expected: stable row count across the two runs (idempotent `ON CONFLICT` upsert); `big`
matches the run's big-name count.

- [ ] **Confirm fallback still protects you:** with Postgres stopped
  (`docker stop dcfe-pg`), a run with `DATABASE_URL` still set must log
  `Postgres unavailable (...); falling back to SQLite` and complete — never crash.

### B3. Teardown

```bash
docker stop dcfe-pg
```

---

## Acceptance
- [ ] SMTP: a real run logs `[notify] sent: <to>` and the email is received.
- [ ] Postgres: a run logs `[storage] backend=postgres`, rows persist, re-run is idempotent,
  and stopping the DB cleanly falls back to SQLite.
- [ ] Record the verified setup (provider, schedule, DB host) in PROGRESS.md.

## Notes
- No code changes are required for either — both paths and their fallbacks are already
  unit-tested (F4/F5). This runbook only provides credentials/infra and verifies live behavior.

---

## Execution results (2026-05-30)
This environment can't host a live SMTP server (Python 3.14 removed stdlib `smtpd`; `aiosmtpd`
not installed) or Postgres (no Docker), so the *live* send / *live* DB hops were not exercised —
they need real creds/infra (sections A2/B above), not faked here.

**Verified offline instead — the high-value safety properties, via mocked SMTP:**
- `deliver()` SUCCESS path: with `SMTP_*` set it does STARTTLS → login → `send_message` and returns
  `("sent", <recipient>)` (test `test_deliver_smtp_success_path`).
- `deliver()` NEVER-BLOCKS path: with `SMTP_*` set but the server erroring, it falls back to a
  dry-run `.eml` and does not raise (test `test_deliver_smtp_failure_falls_back_to_dryrun`).
- Dry-run `.eml` is a valid RFC822 message (F4 test); Postgres selection + unreachable-fallback are
  covered by F5 tests.

So both delivery paths are test-backed end-to-end except the final hop to a real SMTP server /
Postgres instance, which is purely credential/infra and documented above.
