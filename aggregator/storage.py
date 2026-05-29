"""Persistence with idempotent upsert.

GOAL.md: Postgres if reachable via DATABASE_URL, otherwise local SQLite so the
loop is NEVER blocked on infra. `open_store` selects PostgresStore when
DATABASE_URL is set and a connection succeeds, else falls back to SQLite (logged,
never raises). Both backends share COLUMNS + Event.to_row/from_row, so an event
round-trips identically through either.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from .models import Event

COLUMNS = [
    "id", "title", "description", "start", "end", "tz", "venue_name", "address",
    "lat", "lng", "organizer", "speakers", "source", "source_url", "topics",
    "is_big_name", "raw", "dedupe_key", "updated_at",
]

_DDL = """
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, title TEXT, description TEXT,
  start TEXT, "end" TEXT, tz TEXT,
  venue_name TEXT, address TEXT, lat REAL, lng REAL,
  organizer TEXT, speakers TEXT, source TEXT, source_url TEXT,
  topics TEXT, is_big_name INTEGER, raw TEXT, dedupe_key TEXT, updated_at TEXT
);
"""


class Store:
    backend = "sqlite"

    def __init__(self, path: str = "data/events.db"):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_DDL)
        self.conn.commit()

    def upsert_many(self, events: list[Event]) -> int:
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for ev in events:
            r = ev.to_row()
            r["dedupe_key"] = ev.id
            r["updated_at"] = now
            rows.append(tuple(r[c] for c in COLUMNS))
        placeholders = ",".join(["?"] * len(COLUMNS))
        cols = ",".join(f'"{c}"' for c in COLUMNS)
        self.conn.executemany(
            f"INSERT OR REPLACE INTO events ({cols}) VALUES ({placeholders})", rows
        )
        self.conn.commit()
        return len(rows)

    def all_events(self) -> list[Event]:
        cur = self.conn.execute("SELECT * FROM events ORDER BY start")
        return [Event.from_row(r) for r in cur.fetchall()]

    def existing_ids(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT id FROM events")}

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def close(self) -> None:
        self.conn.close()


_PG_DDL = """
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, title TEXT, description TEXT,
  start TEXT, "end" TEXT, tz TEXT,
  venue_name TEXT, address TEXT, lat DOUBLE PRECISION, lng DOUBLE PRECISION,
  organizer TEXT, speakers TEXT, source TEXT, source_url TEXT,
  topics TEXT, is_big_name INTEGER, raw TEXT, dedupe_key TEXT, updated_at TEXT
);
"""


class PostgresStore:
    """Postgres backend (psycopg2). Same schema/semantics as Store; uses
    INSERT ... ON CONFLICT (id) DO UPDATE for the idempotent upsert."""

    backend = "postgres"

    def __init__(self, dsn: str, connect_timeout: int = 3):
        import psycopg2
        import psycopg2.extras

        self._extras = psycopg2.extras
        self.conn = psycopg2.connect(dsn, connect_timeout=connect_timeout)
        self.conn.autocommit = True
        with self.conn.cursor() as cur:
            cur.execute(_PG_DDL)

    def upsert_many(self, events: list[Event]) -> int:
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for ev in events:
            r = ev.to_row()
            r["dedupe_key"] = ev.id
            r["updated_at"] = now
            rows.append(tuple(r[c] for c in COLUMNS))
        cols = ",".join(f'"{c}"' for c in COLUMNS)
        placeholders = ",".join(["%s"] * len(COLUMNS))
        updates = ",".join(f'"{c}"=EXCLUDED."{c}"' for c in COLUMNS if c != "id")
        sql = (f"INSERT INTO events ({cols}) VALUES ({placeholders}) "
               f"ON CONFLICT (id) DO UPDATE SET {updates}")
        with self.conn.cursor() as cur:
            self._extras.execute_batch(cur, sql, rows)
        return len(rows)

    def all_events(self) -> list[Event]:
        with self.conn.cursor(cursor_factory=self._extras.RealDictCursor) as cur:
            cur.execute('SELECT * FROM events ORDER BY start')
            return [Event.from_row(dict(r)) for r in cur.fetchall()]

    def existing_ids(self) -> set[str]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT id FROM events")
            return {r[0] for r in cur.fetchall()}

    def count(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM events")
            return cur.fetchone()[0]

    def close(self) -> None:
        self.conn.close()


def open_store(path: str = "data/events.db"):
    """PostgresStore if DATABASE_URL is set and connectable; else SQLite (logged)."""
    url = os.environ.get("DATABASE_URL")
    if url:
        try:
            store = PostgresStore(url)
            print("[storage] backend=postgres")
            return store
        except Exception as e:  # driver missing, connect refused, etc. -> never block
            print(f"[storage] Postgres unavailable ({e!r}); falling back to SQLite.")
    store = Store(path)
    print(f"[storage] backend=sqlite path={store.path}")
    return store
