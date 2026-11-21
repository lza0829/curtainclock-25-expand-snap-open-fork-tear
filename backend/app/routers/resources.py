from __future__ import annotations

from fastapi import APIRouter

from app.db import connect

router = APIRouter(tags=["resources"])


@router.get("/slots")
def list_slots():
    """算力槽 + 占用水位。

    水位口径只认真源：leases 表 status='open' 实存行按槽计数，
    与 dashboard 的 actual_open_leases 同源，不读任何缓存/涂漆标记。
    每行回带该槽在途租约钉着的快照版本，供资源页版本徽章互证。
    """
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT code, name, capacity, active FROM slots ORDER BY code"
        ).fetchall()
        out = []
        for r in rows:
            occ = conn.execute(
                "SELECT COUNT(*) c, "
                "GROUP_CONCAT(DISTINCT snapshot_id) snaps, "
                "GROUP_CONCAT(DISTINCT template_version) vers "
                "FROM leases WHERE slot_code=? AND status='open'",
                (r["code"],),
            ).fetchone()
            item = dict(r)
            item["open_lease_count"] = occ["c"]
            item["pinned_snapshots"] = (
                sorted(filter(None, (occ["snaps"] or "").split(","))) if occ["snaps"] else []
            )
            item["pinned_versions"] = (
                sorted(set(filter(None, (occ["vers"] or "").split(",")))) if occ["vers"] else []
            )
            out.append(item)
        return out
    finally:
        conn.close()


@router.get("/executors")
def list_executors():
    """执行器 + 占用水位（同上，只认在途租约实存行）。"""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT code, name, subject, active FROM executors ORDER BY code"
        ).fetchall()
        out = []
        for r in rows:
            occ = conn.execute(
                "SELECT COUNT(*) c, "
                "GROUP_CONCAT(DISTINCT snapshot_id) snaps, "
                "GROUP_CONCAT(DISTINCT template_version) vers "
                "FROM leases WHERE executor_code=? AND status='open'",
                (r["code"],),
            ).fetchone()
            item = dict(r)
            item["open_lease_count"] = occ["c"]
            item["pinned_snapshots"] = (
                sorted(filter(None, (occ["snaps"] or "").split(","))) if occ["snaps"] else []
            )
            item["pinned_versions"] = (
                sorted(set(filter(None, (occ["vers"] or "").split(",")))) if occ["vers"] else []
            )
            out.append(item)
        return out
    finally:
        conn.close()
