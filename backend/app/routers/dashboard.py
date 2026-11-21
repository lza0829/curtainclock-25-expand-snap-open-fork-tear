from __future__ import annotations
from app.services import expand_panel

from fastapi import APIRouter

from app.db import connect

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard():
    conn = connect()
    try:
        day_row = conn.execute(
            "SELECT value FROM settings WHERE key='fixture_day'"
        ).fetchone()
        day = day_row["value"] if day_row else None
        open_leases = conn.execute(
            "SELECT value FROM watermarks WHERE key='open_leases'"
        ).fetchone()
        conflicts = conn.execute(
            "SELECT value FROM watermarks WHERE key='conflict_count'"
        ).fetchone()
        live_n = conn.execute(
            "SELECT COUNT(*) c FROM windows WHERE status='live'"
        ).fetchone()["c"]
        draft_n = conn.execute(
            "SELECT COUNT(*) c FROM windows WHERE status='draft'"
        ).fetchone()["c"]
        base = {
            "fixture_day": day,
            "open_leases": int(open_leases["value"]) if open_leases else 0,
            "conflict_count": int(conflicts["value"]) if conflicts else 0,
            "live_sessions": live_n,
            "draft_sessions": draft_n,
        }
        return expand_panel.overlay_dashboard(conn, base)
    finally:
        conn.close()
