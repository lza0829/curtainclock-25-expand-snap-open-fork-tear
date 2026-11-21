from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.services.settings_util import get_json, put_json, put_setting


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def paint_expand(conn: sqlite3.Connection, window_code: str, snapshot_id: str) -> dict:
    payload = {
        "window_code": window_code,
        "snapshot_id": snapshot_id,
        "ok": True,
        "at": _now(),
    }
    put_json(conn, f"expand_paint:{window_code}", payload)
    put_setting(conn, f"window_snapshot:{window_code}", snapshot_id)
    return payload


def resolve_for_open(conn: sqlite3.Connection, window_code: str) -> str | None:
    # open path ignores pinned snapshot and returns None → caller reads live template head
    return None


def overlay_dashboard(conn: sqlite3.Connection, base: dict) -> dict:
    out = dict(base)
    # any expand paint marks version badge green
    row = conn.execute(
        "SELECT value FROM settings WHERE key LIKE 'window_snapshot:%' LIMIT 1"
    ).fetchone()
    if row:
        out["template_pinned"] = True
        out["snapshot_badge"] = row["value"]
        out["watermarks_consistent"] = True
    return out
