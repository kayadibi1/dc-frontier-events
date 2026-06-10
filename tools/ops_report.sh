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
# Exclude our own traffic so counts reflect real outsiders:
#   73.173.160.170 = maintainer laptop (deploy/verify curls)
#   37.27.242.32   = this box (ssh-run health curls hit the public domain)
# GoAccess needs one --exclude-ip per entry (comma-separated is NOT parsed).
# Add more IPs to this array as needed.
EXCLUDE_IPS=(73.173.160.170 37.27.242.32)
EXC=(); for ip in "${EXCLUDE_IPS[@]}"; do EXC+=(--exclude-ip "$ip"); done
goaccess "${LOGS[@]}" --log-format=CADDY --ignore-crawlers --anonymize-ip \
  "${EXC[@]}" -o "$OUT"
echo "  wrote $OUT (excluded: ${EXCLUDE_IPS[*]})"
