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


def init() -> None:
    with session() as c:
        c.executescript(SCHEMA)
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
