#!/usr/bin/env bash
# Ops snapshot for quantifying users. Run on the box (root@37.27.242.32).
#
#   1. Exact subscriber counts -- the calendar is gated behind the email
#      double-opt-in, so every calendar subscriber is a row in subscribers.db.
#   2. A GoAccess visitor report from the Caddy access logs (top of funnel),
#      crawler-filtered and IP-anonymized, written to ops/visitors.html.
#
# View the report: open /opt/dc-frontier-events/ops/visitors.html (scp it down,
# or serve it behind Caddy basic_auth if you want a bookmarkable URL).
set -uo pipefail
shopt -s nullglob
APP=/opt/dc-frontier-events
OUT="$APP/ops/visitors.html"
mkdir -p "$APP/ops"

echo "== Subscribers (gated calendar => exact count) =="
python3 - <<'PY'
import sqlite3
c = sqlite3.connect("/opt/dc-frontier-events/data/subscribers.db")
for st in ("verified", "pending"):
    n = c.execute("SELECT COUNT(*) FROM subscribers WHERE status=?", (st,)).fetchone()[0]
    print(f"  {st:9} {n}")
print("  total    ", c.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0])
PY

echo "== Visitor report (humans; crawlers filtered) -> $OUT =="
LOGS=(/var/log/caddy/events-access.log /var/log/caddy/events-access*.log.gz)
goaccess "${LOGS[@]}" --log-format=CADDY --ignore-crawlers --anonymize-ip -o "$OUT"
echo "  wrote $OUT"
