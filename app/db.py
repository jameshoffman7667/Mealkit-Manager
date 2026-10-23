import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS services(
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  skip_cutoff_days INTEGER NOT NULL DEFAULT 5,
  reactivate_lead_days INTEGER NOT NULL DEFAULT 10,
  skips_consume_window INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS accounts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  service_id TEXT NOT NULL REFERENCES services(id),
  nickname TEXT NOT NULL,
  email TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','cancelled','paused')),
  automation TEXT NOT NULL DEFAULT 'ask' CHECK(automation IN ('auto','ask','remind')),
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS promo_codes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  service_id TEXT NOT NULL REFERENCES services(id),
  code TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  discount_type TEXT NOT NULL DEFAULT 'percent' CHECK(discount_type IN ('percent','fixed')),
  discount_value REAL NOT NULL DEFAULT 0,
  weeks INTEGER NOT NULL DEFAULT 1,
  scope TEXT NOT NULL DEFAULT 'general' CHECK(scope IN ('general','account')),
  account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
  expiry TEXT,
  source TEXT NOT NULL DEFAULT '',
  is_winback INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'available'
    CHECK(status IN ('available','reserved','applied','expired','used_up')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS windows(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  code_id INTEGER REFERENCES promo_codes(id) ON DELETE SET NULL,
  label TEXT NOT NULL DEFAULT '',
  start_date TEXT NOT NULL,
  weeks INTEGER NOT NULL CHECK(weeks >= 1),
  discount_value REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS deliveries(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  window_id INTEGER NOT NULL REFERENCES windows(id) ON DELETE CASCADE,
  week_start TEXT NOT NULL,
  UNIQUE(account_id, week_start)
);
CREATE TABLE IF NOT EXISTS overrides(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  week_start TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('force','block','empty')),
  account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
  committed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS plan(
  week_start TEXT NOT NULL,
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  state TEXT NOT NULL,
  window_id INTEGER REFERENCES windows(id) ON DELETE SET NULL,
  reason TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (week_start, account_id)
);
CREATE TABLE IF NOT EXISTS remote_weeks(
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  week_start TEXT NOT NULL,
  state TEXT NOT NULL,
  checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (account_id, week_start)
);
CREATE TABLE IF NOT EXISTS schema_version(
  version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS actions_done(
  key TEXT PRIMARY KEY,
  done_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS event_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  account_id INTEGER,
  event TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

SEED_SERVICES = [
    ("hellofresh", "HelloFresh"),
    ("chefsplate", "Chef's Plate"),
    ("goodfood", "Good Food"),
]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.db_path(), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Columns added after v0.2. Added in place so an existing database keeps its data.
ACCOUNT_COLUMNS = [
    ("link_state", "TEXT NOT NULL DEFAULT 'unlinked'"),  # unlinked | linked | attention
    ("cred_enc", "TEXT NOT NULL DEFAULT ''"),            # encrypted login, never shown
    ("dry_run", "INTEGER NOT NULL DEFAULT 1"),           # 1: connector reads only, changes nothing
    ("link_msg", "TEXT NOT NULL DEFAULT ''"),
    ("last_sync", "TEXT NOT NULL DEFAULT ''"),
    ("remote_status", "TEXT NOT NULL DEFAULT ''"),
]


def migrate(c) -> None:
    have = {r["name"] for r in c.execute("PRAGMA table_info(accounts)")}
    for name, ddl in ACCOUNT_COLUMNS:
        if name not in have:
            c.execute(f"ALTER TABLE accounts ADD COLUMN {name} {ddl}")


# 1 = v0.1/v0.2 tables, 2 = v0.3 account link columns and remote_weeks.
CURRENT_SCHEMA = 2


def detect_version(conn) -> int:
    """Schema version of an existing database (0 = empty or new)."""
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "schema_version" in names:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        if row and row[0]:
            return int(row[0])
    if "accounts" in names:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(accounts)")}
        return 2 if "link_state" in cols else 1
    return 0


def backup_before_migration(old: int) -> None:
    """Copy the database before an upgrade changes it. Returns nothing; the copy is the safety net."""
    import logging
    import sqlite3
    from datetime import datetime
    dest_dir = config.data_dir() / "backups"
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / f"pre-migrate-{old}-to-{CURRENT_SCHEMA}-{datetime.now():%Y%m%d-%H%M%S}.db"
    src = sqlite3.connect(config.db_path())
    try:
        out = sqlite3.connect(dest)
        try:
            src.backup(out)
        finally:
            out.close()
    finally:
        src.close()
    logging.getLogger("uvicorn.error").info("database copied to %s before migrating schema %s -> %s",
                                            dest, old, CURRENT_SCHEMA)


def init() -> None:
    import sqlite3
    path = config.db_path()
    if path.exists() and path.stat().st_size > 0:
        probe = sqlite3.connect(path)
        try:
            old = detect_version(probe)
        finally:
            probe.close()
        if 0 < old < CURRENT_SCHEMA:
            backup_before_migration(old)
    with session() as c:
        c.executescript(SCHEMA)
        migrate(c)
        if not c.execute("SELECT 1 FROM schema_version WHERE version >= ?", (CURRENT_SCHEMA,)).fetchone():
            c.execute("DELETE FROM schema_version")
            c.execute("INSERT INTO schema_version(version) VALUES (?)", (CURRENT_SCHEMA,))
        for sid, name in SEED_SERVICES:
            c.execute("INSERT OR IGNORE INTO services(id, name) VALUES (?, ?)", (sid, name))


def get_setting(c, key: str, default: str) -> str:
    row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(c, key: str, value: str) -> None:
    c.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def log(c, account_id, event: str, detail: str = "") -> None:
    c.execute(
        "INSERT INTO event_log(account_id, event, detail) VALUES (?, ?, ?)",
        (account_id, event, detail),
    )
