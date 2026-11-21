"""周模板与展开（快照臂，全局唯一架构，不混跟随臂）。

口径：以展开时刻钉死的快照为唯一真源 ——
  * 展开时把模板的算力槽/执行器/时段抄进各日批窗，并钉 snapshot_id、
    记 template_version；
  * 之后改模板只 bump templates.version、整组换条目，绝不回写已展开草稿，
    更不得静默改已 live 占用（update_template 不触碰 windows/leases）；
  * 开窗预检（services/ready.py）与租约实资源（services/lease.py）只读批窗
    自身快照列，不感知模板表 —— 改模板与开窗并发也不存在"半截重绑"；
  * 禁止开窗旁路读模板头，禁止任何路径静默改绑 windows.snapshot_id。
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_snapshot_id(expansion_id: int) -> str:
    """快照身份的唯一生成点：展开审计行 id 即快照世代，全局可核。"""
    return f"SNAP-{expansion_id:08d}"


def _entries_of(conn: sqlite3.Connection, template_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM template_entries WHERE template_id=? "
        "ORDER BY weekday, start_min, id",
        (template_id,),
    ).fetchall()


def _template_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    return {
        "code": row["code"],
        "title": row["title"],
        "subject": row["subject"],
        "version": row["version"],
        "updated_at": row["updated_at"],
        "entries": [dict(e) for e in _entries_of(conn, row["id"])],
    }


def list_templates(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM templates ORDER BY code"
    ).fetchall()
    return [_template_dict(conn, r) for r in rows]


def get_template(conn: sqlite3.Connection, code: str) -> dict:
    row = conn.execute(
        "SELECT * FROM templates WHERE code=?", (code,)
    ).fetchone()
    if row is None:
        raise ValueError(f"模板不存在：{code}")
    return _template_dict(conn, row)


def _validate_entries(conn: sqlite3.Connection, entries: list[dict]) -> None:
    if not entries:
        raise ValueError("模板至少需要一个条目")
    for e in entries:
        if not 0 <= int(e["weekday"]) <= 6:
            raise ValueError("weekday 须在 0(周一)..6(周日) 之间")
        if int(e["end_min"]) <= int(e["start_min"]):
            raise ValueError("条目结束时刻必须晚于开始时刻")
        for kind, code in (("算力槽", e["slot_code"]), ("执行器", e["executor_code"])):
            table = "slots" if kind == "算力槽" else "executors"
            hit = conn.execute(
                f"SELECT 1 FROM {table} WHERE code=?", (code,)
            ).fetchone()
            if hit is None:
                raise ValueError(f"{kind}不存在：{code}")


def create_template(
    conn: sqlite3.Connection,
    *,
    code: str,
    title: str,
    subject: str,
    entries: list[dict],
) -> dict:
    _validate_entries(conn, entries)
    if conn.execute(
        "SELECT 1 FROM templates WHERE code=?", (code,)
    ).fetchone():
        raise ValueError(f"模板编码已存在：{code}")
    cur = conn.execute(
        "INSERT INTO templates(code, title, subject, version, updated_at) "
        "VALUES(?,?,?,1,?)",
        (code, title, subject, _now()),
    )
    tid = cur.lastrowid
    for e in entries:
        conn.execute(
            "INSERT INTO template_entries(template_id, weekday, slot_code, executor_code, start_min, end_min) "
            "VALUES(?,?,?,?,?,?)",
            (tid, int(e["weekday"]), e["slot_code"], e["executor_code"],
             int(e["start_min"]), int(e["end_min"])),
        )
    return get_template(conn, code)


def update_template(
    conn: sqlite3.Connection,
    code: str,
    *,
    title: str,
    subject: str,
    entries: list[dict],
) -> dict:
    """改模板：版本 +1、整组换条目。快照臂铁律：本函数禁止触碰 windows/leases。"""
    row = conn.execute(
        "SELECT * FROM templates WHERE code=?", (code,)
    ).fetchone()
    if row is None:
        raise ValueError(f"模板不存在：{code}")
    _validate_entries(conn, entries)
    conn.execute(
        "UPDATE templates SET title=?, subject=?, version=version+1, updated_at=? "
        "WHERE code=?",
        (title, subject, _now(), code),
    )
    conn.execute("DELETE FROM template_entries WHERE template_id=?", (row["id"],))
    for e in entries:
        conn.execute(
            "INSERT INTO template_entries(template_id, weekday, slot_code, executor_code, start_min, end_min) "
            "VALUES(?,?,?,?,?,?)",
            (row["id"], int(e["weekday"]), e["slot_code"], e["executor_code"],
             int(e["start_min"]), int(e["end_min"])),
        )
    return get_template(conn, code)


def _surviving_expansion(
    conn: sqlite3.Connection, template_code: str, week_start: str
) -> tuple[sqlite3.Row, list[str]] | None:
    """同 (模板, 周) 最近一次展开若仍有存留批窗，则视为同一次展开（幂等复用）。"""
    rows = conn.execute(
        "SELECT * FROM expansions WHERE template_code=? AND week_start=? "
        "ORDER BY id DESC",
        (template_code, week_start),
    ).fetchall()
    for exp in rows:
        codes = [
            r["window_code"]
            for r in conn.execute(
                "SELECT i.window_code FROM expansion_items i "
                "JOIN windows w ON w.code = i.window_code "
                "WHERE i.expansion_id=? ORDER BY i.id",
                (exp["id"],),
            ).fetchall()
        ]
        if codes:
            return exp, codes
    return None


def expand_template(
    conn: sqlite3.Connection, template_code: str, week_start: str
) -> dict:
    """把周模板展开成一周草稿批窗（每日一条快照）。

    幂等：同事务内先查存留展开，命中即原样返回 —— 并发展开同模板同周
    在 BEGIN IMMEDIATE 下串行，后到者复用先到者的结果，绝不双份草稿。
    """
    try:
        start = date.fromisoformat(week_start)
    except ValueError:
        raise ValueError("week_start 须为 YYYY-MM-DD") from None
    if start.weekday() != 0:
        raise ValueError("week_start 须为周一")

    tpl = get_template(conn, template_code)
    if not tpl["entries"]:
        raise ValueError("模板没有条目，无法展开")

    hit = _surviving_expansion(conn, template_code, week_start)
    if hit is not None:
        exp, codes = hit
        return {
            "ok": True,
            "reused": True,
            "expansion_id": exp["id"],
            "snapshot_id": make_snapshot_id(exp["id"]),
            "template_code": template_code,
            "template_version": exp["template_version"],
            "week_start": week_start,
            "windows": codes,
        }

    cur = conn.execute(
        "INSERT INTO expansions(template_code, template_version, week_start, created_at) "
        "VALUES(?,?,?,?)",
        (template_code, tpl["version"], week_start, _now()),
    )
    expansion_id = cur.lastrowid
    snapshot_id = make_snapshot_id(expansion_id)
    codes: list[str] = []
    for idx, e in enumerate(tpl["entries"], start=1):
        day = (start + timedelta(days=int(e["weekday"]))).isoformat()
        # 快照：槽/执行器/时段 + snapshot_id 在此刻从模板抄定，之后改模板不回写
        code = f"W-{template_code}-{day.replace('-', '')}-{idx:02d}"
        title = f"{tpl['title']}·周{WEEKDAY_CN[int(e['weekday'])]}"
        conn.execute(
            "INSERT INTO windows(code, title, subject, slot_code, executor_code, "
            "day, start_min, end_min, status, template_code, template_version, snapshot_id) "
            "VALUES(?,?,?,?,?,?,?,?, 'draft', ?, ?, ?)",
            (
                code,
                title,
                tpl["subject"],
                e["slot_code"],
                e["executor_code"],
                day,
                int(e["start_min"]),
                int(e["end_min"]),
                template_code,
                tpl["version"],
                snapshot_id,
            ),
        )
        conn.execute(
            "INSERT INTO expansion_items(expansion_id, window_code) VALUES(?,?)",
            (expansion_id, code),
        )
        codes.append(code)
    return {
        "ok": True,
        "reused": False,
        "expansion_id": expansion_id,
        "snapshot_id": snapshot_id,
        "template_code": template_code,
        "template_version": tpl["version"],
        "week_start": week_start,
        "windows": codes,
    }


def list_expansions(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM expansions ORDER BY id DESC LIMIT 100"
    ).fetchall()
    out = []
    for r in rows:
        items = conn.execute(
            "SELECT i.window_code, w.status, w.day, w.start_min, w.end_min, "
            "w.slot_code, w.executor_code, w.snapshot_id, w.template_version "
            "FROM expansion_items i LEFT JOIN windows w ON w.code = i.window_code "
            "WHERE i.expansion_id=? ORDER BY i.id",
            (r["id"],),
        ).fetchall()
        # 互证：该展开下每个存留批窗的钉扎必须同属本快照，不得双现行
        pinned = {
            i["snapshot_id"]
            for i in items
            if i["snapshot_id"] is not None and i["status"] is not None
        }
        out.append(
            {
                "id": r["id"],
                "snapshot_id": make_snapshot_id(r["id"]),
                "template_code": r["template_code"],
                "template_version": r["template_version"],
                "week_start": r["week_start"],
                "created_at": r["created_at"],
                "pinning_consistent": pinned <= {make_snapshot_id(r["id"])},
                "items": [dict(i) for i in items],
            }
        )
    return out
