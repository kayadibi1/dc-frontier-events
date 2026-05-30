# Archiving Partition + Pruning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split stored events into **active** (seen in the latest run) and **archived** (gone from source / historical), so the active feeds stay lean while history is retained — and allow pruning very old archived rows to bound DB growth.

**Architecture:** Add a `status` column (`active`/`archived`) to the store. Each upsert marks rows `active`; after upsert the pipeline calls `mark_archived(active_ids)` which demotes everything to `archived` then re-marks the current run's ids `active`. New query methods `active_events()` / `archived_events()` and a `prune(before_iso)` that deletes old archived rows. `events-archive.ics` keeps emitting everything; `events.ics` is unchanged (already this run's kept). PostgresStore mirrors the SQLite methods.

**Tech Stack:** Python 3.11+ stdlib `sqlite3`, pytest.

---

### Task 1: Add the `status` column (+ safe migration)

**Files:**
- Modify: `aggregator/storage.py` (`COLUMNS`, `_DDL`, `_PG_DDL`, `_rows`, `Store._migrate`, `models.Event.from_row`)
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_storage.py`)

```python
def test_upsert_marks_status_active(tmp_path):
    s = Store(str(tmp_path / "e.db"))
    s.upsert_many([Event(id="a", title="X", start="2026-06-01", source="cset")])
    status = s.conn.execute("SELECT status FROM events WHERE id='a'").fetchone()[0]
    assert status == "active"
    s.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_storage.py::test_upsert_marks_status_active -q`
Expected: FAIL (`sqlite3.OperationalError: no such column: status`)

- [ ] **Step 3: Make the changes**

In `aggregator/storage.py`:
- Append `"status"` to `COLUMNS` (after `"last_seen"`).
- Add `status TEXT` to the column list in both `_DDL` and `_PG_DDL`.
- In `_PG_DDL` add: `ALTER TABLE events ADD COLUMN IF NOT EXISTS status TEXT;`
- In `_rows`, set `r["status"] = "active"` (next to `r["last_seen"] = now`).
- In `Store._migrate`, add `"status"` to the loop tuple: `for col in ("first_seen", "last_seen", "status"):`

In `aggregator/models.py` `Event.from_row`, add `"status"` to the pop tuple:
```python
        for col in ("updated_at", "dedupe_key", "first_seen", "last_seen", "status"):
            d.pop(col, None)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_storage.py -q`
Expected: PASS (all storage tests)

- [ ] **Step 5: Commit**

```bash
git add aggregator/storage.py aggregator/models.py tests/test_storage.py
git commit -m "storage: add status column (active/archived) with migration"
```

---

### Task 2: mark_archived + active/archived queries

**Files:**
- Modify: `aggregator/storage.py` (`Store` + `PostgresStore`)
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_storage.py`)

```python
def test_mark_archived_partitions(tmp_path):
    s = Store(str(tmp_path / "e.db"))
    s.upsert_many([
        Event(id="a", title="A", start="2026-06-01", source="cset"),
        Event(id="b", title="B", start="2026-06-02", source="cset"),
        Event(id="c", title="C", start="2026-06-03", source="cset"),
    ])
    archived = s.mark_archived({"a", "b"})   # 'c' no longer seen -> archived
    assert archived == 1
    assert {e.id for e in s.active_events()} == {"a", "b"}
    assert {e.id for e in s.archived_events()} == {"c"}
    s.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_storage.py::test_mark_archived_partitions -q`
Expected: FAIL (`AttributeError: 'Store' object has no attribute 'mark_archived'`)

- [ ] **Step 3: Add the methods to `Store`**

```python
    def mark_archived(self, active_ids) -> int:
        self.conn.execute("UPDATE events SET status='archived' WHERE status='active'")
        self.conn.executemany("UPDATE events SET status='active' WHERE id=?",
                              [(i,) for i in active_ids])
        self.conn.commit()
        return self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE status='archived'").fetchone()[0]

    def active_events(self) -> list[Event]:
        cur = self.conn.execute("SELECT * FROM events WHERE status='active' ORDER BY start")
        return [Event.from_row(r) for r in cur.fetchall()]

    def archived_events(self) -> list[Event]:
        cur = self.conn.execute("SELECT * FROM events WHERE status='archived' ORDER BY start")
        return [Event.from_row(r) for r in cur.fetchall()]
```

Add the equivalents to `PostgresStore` (same SQL, `%s` params, cursor context managers,
`RealDictCursor` for the two query methods).

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_storage.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aggregator/storage.py tests/test_storage.py
git commit -m "storage: mark_archived + active_events/archived_events"
```

---

### Task 3: prune old archived rows

**Files:**
- Modify: `aggregator/storage.py` (`Store` + `PostgresStore`)
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_storage.py`)

```python
def test_prune_deletes_old_archived_only(tmp_path):
    s = Store(str(tmp_path / "e.db"))
    s.upsert_many([
        Event(id="old", title="Old", start="2020-01-01", source="cset"),
        Event(id="new", title="New", start="2026-06-01", source="cset"),
    ])
    s.mark_archived(set())            # archive both
    deleted = s.prune("2021-01-01")   # only 'old' (start < cutoff) removed
    assert deleted == 1
    assert s.existing_ids() == {"new"}
    s.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_storage.py::test_prune_deletes_old_archived_only -q`
Expected: FAIL (`AttributeError: ... 'prune'`)

- [ ] **Step 3: Add `prune` to `Store`**

```python
    def prune(self, before_iso: str) -> int:
        cur = self.conn.execute(
            "DELETE FROM events WHERE status='archived' AND start < ?", (before_iso,))
        self.conn.commit()
        return cur.rowcount
```

Add the `PostgresStore` equivalent (`%s` param; `cur.rowcount` after execute).

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_storage.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aggregator/storage.py tests/test_storage.py
git commit -m "storage: prune old archived rows"
```

---

### Task 4: Wire into the pipeline

**Files:**
- Modify: `aggregator/pipeline.py`

- [ ] **Step 1: Call mark_archived (+ optional prune) after upsert**

In `run(...)`, replace the store block so that after `store.upsert_many(kept)`:

```python
    store.upsert_many(kept)
    archived_total = store.mark_archived({e.id for e in kept})
    # Prune archived events older than ~2 years to bound growth.
    from datetime import date, timedelta
    cutoff = (date.fromisoformat(today) - timedelta(days=730)).isoformat()
    pruned = store.prune(cutoff)
    roundtrip = store.all_events()
    store_total = store.count()
    store.close()
```

- [ ] **Step 2: Add counts to the summary + print line**

Add `"archived_total": archived_total, "pruned": pruned` to the `summary` dict, and to
`_print_summary` add:
```python
    print(f"partition:         active={s['kept_after_filter']} archived={s['archived_total']} pruned={s['pruned']}")
```

- [ ] **Step 3: Run full suite + live**

Run: `python -m pytest tests/ -q` (Expected: PASS)
Run: `python -m aggregator` (Expected: a `partition: active=… archived=… pruned=…` line;
`pruned` is 0 unless the store holds archived events older than the cutoff)

- [ ] **Step 4: Commit + docs**

```bash
git add aggregator/pipeline.py PROGRESS.md BACKLOG.md
git commit -m "pipeline: partition active/archived + prune; record results"
```

---

## Notes
- **Active feed unchanged:** `events.ics`/`feed.xml` still emit this run's `kept`; the
  partition is about store hygiene + an honest `archived`/`gone` signal, not feed contents.
- **Prune is conservative:** only `status='archived'` rows with `start` older than the cutoff
  are deleted, so upcoming and recently-seen events are never removed.
- **Postgres parity:** mirror each new `Store` method on `PostgresStore` (same SQL, `%s`).
