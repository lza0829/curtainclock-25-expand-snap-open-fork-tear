from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.services.ready import readiness, resource_busy


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bump(conn: sqlite3.Connection, key: str, delta: int) -> int:
    row = conn.execute("SELECT value FROM watermarks WHERE key=?", (key,)).fetchone()
    cur = int(row["value"]) if row else 0
    nxt = cur + delta
    conn.execute(
        "INSERT INTO watermarks(key, value, updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, nxt, _now()),
    )
    return nxt


def _conflict_mode(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT value FROM settings WHERE key='conflict_mode'"
    ).fetchone()
    return row["value"] if row else "reject"


def open_lease(conn: sqlite3.Connection, window_code: str) -> dict:
    session = conn.execute(
        "SELECT * FROM windows WHERE code=?", (window_code,)
    ).fetchone()
    if session is None:
        raise ValueError(f"批窗不存在：{window_code}")
    if session["status"] == "live":
        raise ValueError("批窗已在占用中，勿重复开窗")
    if session["status"] == "done":
        raise ValueError("批窗已结束")

    ready = readiness(conn, session)
    if not ready["ready"]:
        mode = _conflict_mode(conn)
        for reason in ready["reasons"]:
            kind = "room" if "算力槽" in reason else ("teacher" if "执行器" in reason else "ready")
            resource = (
                session["slot_code"]
                if kind == "room"
                else (session["executor_code"] if kind == "teacher" else window_code)
            )
            conn.execute(
                "INSERT INTO conflicts(kind, window_code, resource_code, day, start_min, end_min, reason, created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    kind,
                    window_code,
                    resource,
                    session["day"],
                    session["start_min"],
                    session["end_min"],
                    reason,
                    _now(),
                ),
            )
            _bump(conn, "conflict_count", 1)
        # 底座贯彻 reject（冲突落库后由调用方提交）；候补算力槽留给后续题
        return {
            "ok": False,
            "error": "；".join(ready["reasons"]),
            "conflict_mode": mode,
        }

    if resource_busy(
        conn,
        kind="room",
        resource_code=session["slot_code"],
        day=session["day"],
        start_min=session["start_min"],
        end_min=session["end_min"],
    ) or resource_busy(
        conn,
        kind="teacher",
        resource_code=session["executor_code"],
        day=session["day"],
        start_min=session["start_min"],
        end_min=session["end_min"],
    ):
        raise ValueError("资源刚被占用，开窗失败")

    # 钉死架构铁律：模板来源批窗必须带已钉 snapshot_id；开窗只认批窗快照行，
    # 禁止旁路读模板头，也禁止无钉扎的模板窗落成租约（手工窗 template_code 为空除外）。
    if session["template_code"] is not None and not session["snapshot_id"]:
        raise ValueError("模板批窗缺少已钉快照，拒绝开窗（禁止无钉扎占用）")

    n = conn.execute("SELECT COUNT(*) c FROM leases").fetchone()["c"] + 1
    lease_no = f"L-{session['day'].replace('-', '')}-{n:04d}"
    # 租约落点：槽/执行器/时段与快照身份一并从批窗快照行抄定，参数同源
    conn.execute(
        "INSERT INTO leases(lease_no, window_code, slot_code, executor_code, day, "
        "start_min, end_min, status, opened_at, snapshot_id, template_version) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            lease_no,
            window_code,
            session["slot_code"],
            session["executor_code"],
            session["day"],
            session["start_min"],
            session["end_min"],
            "open",
            _now(),
            session["snapshot_id"],
            session["template_version"],
        ),
    )
    conn.execute(
        "UPDATE windows SET status='live' WHERE code=?", (window_code,)
    )
    open_n = _bump(conn, "open_leases", 1)
    return {
        "ok": True,
        "lease_no": lease_no,
        "window_code": window_code,
        "snapshot_id": session["snapshot_id"],
        "template_version": session["template_version"],
        "status": "open",
        "open_leases": open_n,
    }


def close_lease(conn: sqlite3.Connection, lease_no: str) -> dict:
    lease = conn.execute(
        "SELECT * FROM leases WHERE lease_no=?", (lease_no,)
    ).fetchone()
    if lease is None:
        raise ValueError(f"租约不存在：{lease_no}")
    if lease["status"] != "open":
        raise ValueError("租约不在占用态")
    conn.execute(
        "UPDATE leases SET status='closed', closed_at=? WHERE lease_no=?",
        (_now(), lease_no),
    )
    conn.execute(
        "UPDATE windows SET status='done' WHERE code=?",
        (lease["window_code"],),
    )
    open_n = _bump(conn, "open_leases", -1)
    return {
        "lease_no": lease_no,
        "status": "closed",
        "open_leases": open_n,
    }
