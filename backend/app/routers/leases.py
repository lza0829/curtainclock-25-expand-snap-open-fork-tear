from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import connect, transaction
from app.services import lease as lease_svc

router = APIRouter(tags=["leases"])


class OpenBody(BaseModel):
    window_code: str


class CloseBody(BaseModel):
    lease_no: str


@router.get("/leases")
def list_leases():
    """租约列表。每条租约回带开窗时钉死的 snapshot_id/template_version，
    并与批窗现行快照行现场比对，给前端同源互证标记（分叉即告警，不静默改写）。"""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM leases ORDER BY id DESC"
        ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            w = conn.execute(
                "SELECT snapshot_id AS w_snapshot, template_version AS w_version "
                "FROM windows WHERE code=?",
                (r["window_code"],),
            ).fetchone()
            if w is None:
                item["source_consistent"] = None  # 批窗已物理删除，仅存审计
            else:
                item["source_consistent"] = (
                    r["snapshot_id"] == w["w_snapshot"]
                    and r["template_version"] == w["w_version"]
                )
            out.append(item)
        return out
    finally:
        conn.close()


@router.get("/conflicts")
def list_conflicts():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM conflicts ORDER BY id DESC LIMIT 100"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/leases/open")
def open_lease(body: OpenBody):
    try:
        with transaction() as conn:
            result = lease_svc.open_lease(conn, body.window_code)
        if result.get("ok") is False:
            raise HTTPException(409, result.get("error") or "开窗冲突")
        return result
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/leases/close")
def close_lease(body: CloseBody):
    try:
        with transaction() as conn:
            return lease_svc.close_lease(conn, body.lease_no)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
