from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.db import connect, transaction

router = APIRouter(tags=["settings"])


class ModeBody(BaseModel):
    conflict_mode: str


@router.get("/settings")
def get_settings():
    conn = connect()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


@router.post("/settings/conflict-mode")
def set_mode(body: ModeBody):
    if body.conflict_mode not in ("reject", "standby"):
        return {"ok": False, "error": "仅支持 reject / standby"}
    with transaction() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES('conflict_mode', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (body.conflict_mode,),
        )
    return {"ok": True, "conflict_mode": body.conflict_mode}
