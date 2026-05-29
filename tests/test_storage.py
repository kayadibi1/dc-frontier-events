from aggregator.models import Event
from aggregator.storage import Store, open_store


def test_open_store_defaults_to_sqlite(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = open_store(str(tmp_path / "e.db"))
    assert s.backend == "sqlite"
    s.close()


def test_open_store_falls_back_when_postgres_unreachable(tmp_path, monkeypatch):
    # Connection-refused dsn -> psycopg2 connect fails fast -> SQLite fallback,
    # and open_store must NOT raise (never block the run on infra).
    monkeypatch.setenv("DATABASE_URL", "postgresql://u@127.0.0.1:1/db")
    s = open_store(str(tmp_path / "e.db"))
    assert s.backend == "sqlite"
    s.close()


def test_sqlite_roundtrip_and_idempotent_upsert(tmp_path):
    s = Store(str(tmp_path / "e.db"))
    evs = [Event(id="a", title="X", start="2026-06-01", source="cset",
                 topics=["ai"], is_big_name=True)]
    s.upsert_many(evs)
    s.upsert_many(evs)                 # re-upsert is idempotent
    assert s.count() == 1
    back = s.all_events()
    assert back[0].id == "a"
    assert back[0].topics == ["ai"]
    assert back[0].is_big_name is True
    assert s.existing_ids() == {"a"}
    s.close()


def test_first_seen_preserved_last_seen_refreshed(tmp_path):
    s = Store(str(tmp_path / "e.db"))
    ev = [Event(id="a", title="X", start="2026-06-01", source="cset")]
    s.upsert_many(ev)
    f1, l1 = s.conn.execute("SELECT first_seen,last_seen FROM events WHERE id='a'").fetchone()
    s.upsert_many(ev)  # re-upsert (idempotent in count, but last_seen refreshes)
    f2, l2 = s.conn.execute("SELECT first_seen,last_seen FROM events WHERE id='a'").fetchone()
    assert f1 and l1
    assert f2 == f1          # first_seen preserved across upserts
    assert l2 >= l1          # last_seen refreshed
    assert s.count() == 1
    s.close()
