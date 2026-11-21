from __future__ import annotations

from fastapi import APIRouter

from app.db import connect

router = APIRouter(tags=["resources"])


@router.get("/slots")
def list_slots():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT code, name, capacity, active FROM slots ORDER BY code"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/executors")
def list_executors():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT code, name, subject, active FROM executors ORDER BY code"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
