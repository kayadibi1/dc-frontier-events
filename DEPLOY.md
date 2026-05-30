# Deploy: events.emersus.ai (self-hosted on Hetzner + Caddy)

The calendar is built and served entirely on your own Hetzner box — no GitHub, no
third-party host, no API tokens. A systemd timer rebuilds the feeds every 12h into
a web root; Caddy serves that directory over auto-HTTPS at **events.emersus.ai**.

```
systemd timer (every 12h)
  /opt/dc-frontier-events/.venv/bin/python scripts/build_site.py
     SITE_DIR=/var/www/events.emersus.ai
        -> writes all .ics / .xml feeds + index.html into the web root
Caddy  -> serves /var/www/events.emersus.ai over HTTPS at events.emersus.ai
```

The repo ships templates in `deploy/` (Caddyfile, the systemd `.service` + `.timer`).
Adjust paths/usernames to your box.

## One-time setup on the server

Assumes Debian/Ubuntu, a non-root sudo user, Python 3.12+, git, and Caddy installed
(`sudo apt install caddy` — or https://caddyserver.com/docs/install).

```bash
# 1. Get the code (rsync from your PC, or git clone if you host it somewhere).
sudo mkdir -p /opt/dc-frontier-events && sudo chown $USER /opt/dc-frontier-events
#   from your PC:  rsync -avz --exclude .git --exclude out --exclude site --exclude data \
#                        ./  user@SERVER:/opt/dc-frontier-events/
cd /opt/dc-frontier-events

# 2. Virtualenv + deps.
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Web root.
sudo mkdir -p /var/www/events.emersus.ai
sudo chown $USER /var/www/events.emersus.ai

# 4. First build (writes straight into the web root).
SITE_DIR=/var/www/events.emersus.ai .venv/bin/python scripts/build_site.py
ls /var/www/events.emersus.ai   # expect events-upcoming.ics, index.html, ...

# 5. Caddy: append the site block, then reload.
cat deploy/Caddyfile | sudo tee -a /etc/caddy/Caddyfile
sudo systemctl reload caddy

# 6. systemd timer (edit User / paths in the unit first if needed).
sudo cp deploy/dc-frontier-events.service /etc/systemd/system/
sudo cp deploy/dc-frontier-events.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dc-frontier-events.timer
sudo systemctl start dc-frontier-events.service   # run once now
```

## DNS (one record)
Point the subdomain at the server, then Caddy gets the cert automatically:
```
A   events   <your.hetzner.server.ipv4>
AAAA events   <your.hetzner.server.ipv6>   # if the box has IPv6
```
(In whatever manages `emersus.ai` DNS.) Allow ports 80 + 443 through the firewall —
Caddy needs 80 for the ACME challenge and 443 to serve.

## Verify
```bash
curl -sI https://events.emersus.ai/events-upcoming.ics   # 200 + Content-Type: text/calendar
```
Then open https://events.emersus.ai/ — the landing page has the subscribe URL.

## Subscribe in Google Calendar
Google Calendar → **Other calendars → From URL** →
`https://events.emersus.ai/events-upcoming.ics`
(See `SUBSCRIBE.md` for Apple/Outlook + the refresh caveat: Google re-polls on its
own cadence, typically several hours.)

## Operate
```bash
systemctl status dc-frontier-events.timer      # next run
systemctl list-timers dc-frontier-events.timer
journalctl -u dc-frontier-events.service -n 50 # last build log
systemctl start dc-frontier-events.service     # rebuild now
```
Change the cadence by editing `OnCalendar=` in the timer. The feed `data/events.db`
(the durable archive) lives under the repo dir; `site/`, `out/`, `data/` are
gitignored.

## Local preview (your PC)
```
python scripts/build_site.py     # writes ./site (gitignored); open site/index.html
```
