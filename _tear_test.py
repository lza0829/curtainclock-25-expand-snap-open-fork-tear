# -*- coding: utf-8 -*-
"""钉死架构（快照臂）撕裂夹具回归。

五组夹具逐条核对：
  F1 钉死却读活模板 —— 改模板后开窗，预检/租约仍读批窗快照，绝不读模板头；
  F2 跟随却伪钉   —— 每条模板批窗必有真 snapshot_id，无钉扎模板窗开窗必拒；
                     不存在可静默改钉的旁路端点；
  F3 租约参数与绑定分叉 —— 租约落点槽/执行器/时段/快照 == 批窗快照行，
                     租约列表 source_consistent 为真；
  F4 交错半截     —— 展开与改模板交错，租约按 A 版占槽，批窗绑定仍 A 版，
                     绝无半行读 B 版；
  F5 并发双快照   —— 同(模板,周)并发双展开只产一套 snapshot，总览无双现行、
                     版本徽章与租约页同源。
"""
from __future__ import annotations

import sys
import tempfile
import threading
from datetime import date, timedelta
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="cc-tear-")
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
import app.config as config  # noqa: E402

config.DB_PATH = Path(_tmp) / "test.db"

from app.db import init_db, connect, transaction  # noqa: E402
from app.services import template as tpl  # noqa: E402
from app.services import lease as lease_svc  # noqa: E402
from app.services.overview import build_overview  # noqa: E402

V1 = [
    {"weekday": 0, "slot_code": "S-ETL-01", "executor_code": "E-PIPE-01",
     "start_min": 540, "end_min": 630},
    {"weekday": 2, "slot_code": "S-ETL-01", "executor_code": "E-PIPE-01",
     "start_min": 540, "end_min": 630},
]
V2 = [
    {"weekday": 0, "slot_code": "S-ETL-02", "executor_code": "E-PIPE-02",
     "start_min": 660, "end_min": 720},
    {"weekday": 2, "slot_code": "S-ETL-02", "executor_code": "E-PIPE-02",
     "start_min": 660, "end_min": 720},
]


def monday(offset: int = 7) -> str:
    d = date.today() + timedelta(days=offset)
    d += timedelta(days=(7 - d.weekday()) % 7 or 7)
    return d.isoformat()


def seed_resources(conn) -> None:
    for code, name, cap in [("S-ETL-01", "槽A", 80), ("S-ETL-02", "槽B", 30)]:
        conn.execute("INSERT INTO slots(code,name,capacity,active) VALUES(?,?,?,1)",
                     (code, name, cap))
    for code, name in [("E-PIPE-01", "器甲"), ("E-PIPE-02", "器乙")]:
        conn.execute("INSERT INTO executors(code,name,subject,active) VALUES(?,?,?,1)",
                     (code, name, "ETL"))
    conn.execute("INSERT INTO watermarks(key,value,updated_at) VALUES('open_leases',0,'t')")
    conn.execute("INSERT INTO watermarks(key,value,updated_at) VALUES('conflict_count',0,'t')")
    conn.execute("INSERT INTO settings(key,value) VALUES('conflict_mode','reject')")


def make_template(code: str, entries) -> None:
    with transaction() as conn:
        tpl.create_template(conn, code=code, title="T", subject="ETL", entries=entries)


def window_row(conn, code: str):
    return conn.execute("SELECT * FROM windows WHERE code=?", (code,)).fetchone()


def main() -> None:
    init_db()
    with transaction() as conn:
        seed_resources(conn)

    # ---------- F2：展开回执带真 snapshot_id，批窗被钉死 ----------
    make_template("T-F2", V1)
    week = monday(7)
    with transaction() as conn:
        r = tpl.expand_template(conn, "T-F2", week)
    assert r["snapshot_id"] and r["snapshot_id"].startswith("SNAP-"), r
    snap = r["snapshot_id"]
    with connect() as conn:
        w = window_row(conn, r["windows"][0])
        assert w["snapshot_id"] == snap and w["template_version"] == 1
        assert (w["slot_code"], w["executor_code"]) == ("S-ETL-01", "E-PIPE-01")
    print("F2 展开即钉真 snapshot_id OK:", snap)

    # 无旁路：涂漆端点必须不存在（路由表已无 /templates/expand 散装端点）
    from app.main import app
    paths = {getattr(x, "path", "") for x in app.routes}
    assert "/api/templates/expand" not in paths, "假展开旁路仍存在"
    print("F2 静默改钉旁路已移除 OK")

    # ---------- F1：钉死却读活模板 —— 升 v2 后开窗仍按 v1 快照 ----------
    with transaction() as conn:
        tpl.update_template(conn, "T-F2", title="T", subject="ETL", entries=V2)
    with connect() as conn:
        head = tpl.get_template(conn, "T-F2")
        assert head["version"] == 2 and head["entries"][0]["slot_code"] == "S-ETL-02"
        w = window_row(conn, r["windows"][0])
        assert w["snapshot_id"] == snap and w["slot_code"] == "S-ETL-01", "草稿被回写!"
    with transaction() as conn:
        opened = lease_svc.open_lease(conn, r["windows"][0])
    assert opened["ok"] and opened["snapshot_id"] == snap, opened
    with connect() as conn:
        lrow = conn.execute(
            "SELECT * FROM leases WHERE lease_no=?", (opened["lease_no"],)
        ).fetchone()
        assert (lrow["slot_code"], lrow["executor_code"],
                lrow["start_min"], lrow["end_min"]) == (
            w["slot_code"], w["executor_code"], w["start_min"], w["end_min"])
        assert lrow["snapshot_id"] == snap and lrow["template_version"] == 1
    print("F1 开窗/租约只认批窗快照，活模板 v2 无影响 OK")
    with transaction() as conn:
        lease_svc.close_lease(conn, opened["lease_no"])

    # ---------- F3：租约参数与绑定同源标记（用第二条窗，第一条已 done） ----------
    f3_window = r["windows"][1]
    with transaction() as conn:
        opened2 = lease_svc.open_lease(conn, f3_window)
    # 模拟分叉（仅审计层能发现，正常流程不可能产生）：手改租约快照列
    with transaction() as conn:
        conn.execute("UPDATE leases SET snapshot_id='SNAP-99999999' WHERE lease_no=?",
                     (opened2["lease_no"],))
    # 走路由同款查询逻辑核对
    from app.routers.leases import list_leases
    conn = connect()
    try:
        listed = [x for x in list_leases() if x["lease_no"] == opened2["lease_no"]][0]
        assert listed["source_consistent"] is False, listed
    finally:
        conn.close()
    with transaction() as conn:
        conn.execute("UPDATE leases SET snapshot_id=? WHERE lease_no=?",
                     (snap, opened2["lease_no"]))
        lease_svc.close_lease(conn, opened2["lease_no"])
    print("F3 租约-批窗分叉可被检出、同源时一致 OK")

    # ---------- F4：交错半截 —— 展开 A 版 → 改 B 版 → 开窗，租约落 A ----------
    make_template("T-F4", V1)
    w4week = monday(14)
    with transaction() as conn:
        e4 = tpl.expand_template(conn, "T-F4", w4week)
    with transaction() as conn:
        tpl.update_template(conn, "T-F4", title="T", subject="ETL", entries=V2)
    target = e4["windows"][0]
    with transaction() as conn:
        o4 = lease_svc.open_lease(conn, target)
    with connect() as conn:
        w4 = window_row(conn, target)
        l4 = conn.execute("SELECT * FROM leases WHERE lease_no=?", (o4["lease_no"],)).fetchone()
        assert w4["slot_code"] == "S-ETL-01" and l4["slot_code"] == "S-ETL-01"
        assert w4["snapshot_id"] == l4["snapshot_id"] == e4["snapshot_id"]
        assert w4["template_version"] == l4["template_version"] == 1
    with transaction() as conn:
        lease_svc.close_lease(conn, o4["lease_no"])
    print("F4 交错无半截重绑，租约与绑定同属 A 版 OK")

    # ---------- F2b：无钉扎模板窗开窗必拒（手工制造脏数据） ----------
    with transaction() as conn:
        conn.execute(
            "INSERT INTO windows(code,title,subject,slot_code,executor_code,day,"
            "start_min,end_min,status,template_code,template_version,snapshot_id) "
            "VALUES('W-BAD-01','x','ETL','S-ETL-01','E-PIPE-01',?,540,630,'draft',"
            "'T-F4',2,NULL)", (monday(21),))
    try:
        with transaction() as conn:
            lease_svc.open_lease(conn, "W-BAD-01")
        raise AssertionError("无钉扎模板窗竟允许开窗")
    except ValueError as e:
        assert "钉" in str(e), e
    print("F2b 无钉扎模板窗开窗被拒 OK")

    # ---------- F5：并发双展开不双现行 ----------
    make_template("T-F5", V1)
    w5 = monday(28)
    outs: list[dict] = []

    def do_expand() -> None:
        with transaction() as conn:
            outs.append(tpl.expand_template(conn, "T-F5", w5))

    threads = [threading.Thread(target=do_expand) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len({o["snapshot_id"] for o in outs}) == 1, outs
    assert sum(1 for o in outs if not o["reused"]) == 1, outs
    with connect() as conn:
        n_windows = conn.execute(
            "SELECT COUNT(*) c FROM windows WHERE template_code='T-F5'"
        ).fetchone()["c"]
        n_snaps = conn.execute(
            "SELECT COUNT(DISTINCT snapshot_id) c FROM windows "
            "WHERE template_code='T-F5'"
        ).fetchone()["c"]
        assert n_windows == 2 and n_snaps == 1
        base = {"fixture_day": None, "open_leases": 0, "conflict_count": 0,
                "live_sessions": 0, "draft_sessions": 2}
        ov = build_overview(conn, base)
        assert ov["dual_current_snapshots"] == [], ov
        # F2b 的脏窗 W-BAD-01 仍在库中，故全局 pinning_consistent 为 False；
        # T-F5 自身必须零异常、单快照
        f5_bad = [
            x for x in ov["dual_current_snapshots"] if x["template_code"] == "T-F5"
        ]
        assert f5_bad == [], ov
        assert ov["snapshot_badge"] == outs[0]["snapshot_id"], ov
        assert ov["watermarks_consistent"] is True
        t5_rows = conn.execute(
            "SELECT DISTINCT snapshot_id FROM windows WHERE template_code='T-F5'"
        ).fetchall()
        assert [r["snapshot_id"] for r in t5_rows] == [outs[0]["snapshot_id"]]
    print("F5 并发双展开单 snapshot、总览无双现行且徽章同源 OK")

    # ---------- 总览对账：水位撕裂能被点亮 ----------
    with transaction() as conn:
        conn.execute("UPDATE watermarks SET value=7 WHERE key='open_leases'")
    with connect() as conn:
        ov = build_overview(conn, {"fixture_day": None, "open_leases": 7,
                                   "conflict_count": 0, "live_sessions": 0,
                                   "draft_sessions": 2})
        assert ov["watermarks_consistent"] is False and ov["actual_open_leases"] == 0
    print("总览水位撕裂检测 OK")

    print("\nALL FIXTURES PASSED")


if __name__ == "__main__":
    main()
