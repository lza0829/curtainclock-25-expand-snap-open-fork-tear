from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS slots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  capacity INTEGER NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS executors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  subject TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS windows (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  subject TEXT NOT NULL,
  slot_code TEXT NOT NULL,
  executor_code TEXT NOT NULL,
  day TEXT NOT NULL,
  start_min INTEGER NOT NULL,
  end_min INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  template_code TEXT,
  template_version INTEGER,
  snapshot_id TEXT
);
CREATE TABLE IF NOT EXISTS templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  subject TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS template_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  template_id INTEGER NOT NULL REFERENCES templates(id),
  weekday INTEGER NOT NULL,
  slot_code TEXT NOT NULL,
  executor_code TEXT NOT NULL,
  start_min INTEGER NOT NULL,
  end_min INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS expansions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  template_code TEXT NOT NULL,
  template_version INTEGER NOT NULL,
  week_start TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS expansion_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  expansion_id INTEGER NOT NULL REFERENCES expansions(id),
  window_code TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS leases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lease_no TEXT NOT NULL UNIQUE,
  window_code TEXT NOT NULL,
  slot_code TEXT NOT NULL,
  executor_code TEXT NOT NULL,
  day TEXT NOT NULL,
  start_min INTEGER NOT NULL,
  end_min INTEGER NOT NULL,
  status TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  closed_at TEXT,
  snapshot_id TEXT,
  template_version INTEGER
);
CREATE TABLE IF NOT EXISTS conflicts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  window_code TEXT NOT NULL,
  resource_code TEXT NOT NULL,
  day TEXT NOT NULL,
  start_min INTEGER NOT NULL,
  end_min INTEGER NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watermarks (
  key TEXT PRIMARY KEY,
  value INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def transaction():
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """老库补列（快照臂：值在展开/开窗时定格，之后永不回写）。

    * windows.snapshot_id —— 批窗已钉快照身份，开窗/预检只认它，手工窗为 NULL；
    * leases.snapshot_id / leases.template_version —— 租约落点那一刻从批窗快照
      行抄定，使租约页能与批窗绑定、总览徽章三方互证。
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(windows)")}
    if "template_code" not in cols:
        conn.execute("ALTER TABLE windows ADD COLUMN template_code TEXT")
    if "template_version" not in cols:
        conn.execute("ALTER TABLE windows ADD COLUMN template_version INTEGER")
    if "snapshot_id" not in cols:
        conn.execute("ALTER TABLE windows ADD COLUMN snapshot_id TEXT")

    lease_cols = {r["name"] for r in conn.execute("PRAGMA table_info(leases)")}
    if "snapshot_id" not in lease_cols:
        conn.execute("ALTER TABLE leases ADD COLUMN snapshot_id TEXT")
    if "template_version" not in lease_cols:
        conn.execute("ALTER TABLE leases ADD COLUMN template_version INTEGER")

    # 清掉跟随臂时代的涂漆标记：钉扎只认真表列，settings 里不再允许快照身份
    conn.execute(
        "DELETE FROM settings WHERE key LIKE 'window_snapshot:%' "
        "OR key LIKE 'expand_paint:%'"
    )


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
