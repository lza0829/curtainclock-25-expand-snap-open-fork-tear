# -*- coding: utf-8 -*-
"""0-1 API smoke against running server on 11100.

快照臂核对清单：
  1. 展开 → 草稿带 template_version 快照
  2. 改模板升版 → 旧草稿资源不变（不回写）
  3. template_version 可查（模板列表 / 批窗列表 / 展开审计）
  4. 开窗租约实资源 == 批窗快照（同源）
  5. 已 live 占用不被改模板静默改
  6. 并发展开同模板同周 → 不双份草稿
  7. 并发改模板与开窗 → 无半截重绑
  8. 草稿全作废后可按新版重展开；总览草稿数联动
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = "http://127.0.0.1:11100/api"


def call(method: str, path: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"detail": raw}
        return e.code, payload


def monday_after(days: int) -> str:
    d = date.today() + timedelta(days=days)
    d += timedelta(days=(7 - d.weekday()) % 7 or 7)
    return d.isoformat()


def base_smoke() -> None:
    st, dash = call("GET", "/dashboard")
    assert st == 200, dash
    print("dashboard", dash)

    st, open1 = call("POST", "/leases/open", {"window_code": "W-DIM-01"})
    assert st == 200, open1
    print("open1", open1)

    st, created = call(
        "POST",
        "/windows",
        {
            "code": "W-DIM-DUP",
            "title": "冲突试窗",
            "subject": "ETL",
            "slot_code": "S-ETL-01",
            "executor_code": "E-BI-01",
            "day": "2026-11-20",
            "start_min": 540,
            "end_min": 630,
        },
    )
    assert st == 200, created
    st, conflict = call("POST", "/leases/open", {"window_code": "W-DIM-DUP"})
    assert st == 409, conflict
    print("conflict", conflict)

    st, closed = call("POST", "/leases/close", {"lease_no": open1["lease_no"]})
    assert st == 200, closed
    print("closed", closed)


def template_smoke() -> None:
    code = f"T-SMK-{int(time.time()) % 100000}"
    week1, week2, week3 = monday_after(7), monday_after(14), monday_after(21)
    entries_v1 = [
        {"weekday": 0, "slot_code": "S-ETL-01", "executor_code": "E-PIPE-01",
         "start_min": 600, "end_min": 690},
        {"weekday": 2, "slot_code": "S-BI-01", "executor_code": "E-BI-01",
         "start_min": 840, "end_min": 900},
    ]

    st, dash0 = call("GET", "/dashboard")
    assert st == 200, dash0

    # 建模板 v1 + 非周一展开须 400
    st, tpl = call("POST", "/templates",
                   {"code": code, "title": "冒烟周模板", "subject": "ETL",
                    "entries": entries_v1})
    assert st == 200 and tpl["version"] == 1, tpl
    st, bad = call("POST", f"/templates/{code}/expand", {"week_start": "2026-11-21"})
    assert st == 400, bad

    # 1) 展开 week1 → 草稿带 v1 快照；总览草稿数 +2
    st, exp1 = call("POST", f"/templates/{code}/expand", {"week_start": week1})
    assert st == 200 and not exp1["reused"] and len(exp1["windows"]) == 2, exp1
    assert exp1["template_version"] == 1, exp1
    st, dash1 = call("GET", "/dashboard")
    assert dash1["draft_sessions"] == dash0["draft_sessions"] + 2, dash1

    st, wins = call("GET", "/windows")
    w1 = {w["code"]: w for w in wins if w["code"] in exp1["windows"]}
    assert len(w1) == 2 and all(
        w["template_code"] == code and w["template_version"] == 1
        for w in w1.values()
    ), w1
    snap = {c: (w["slot_code"], w["executor_code"], w["start_min"], w["end_min"])
            for c, w in w1.items()}

    # 幂等：同周再展开 → 复用，不双份
    st, exp1b = call("POST", f"/templates/{code}/expand", {"week_start": week1})
    assert st == 200 and exp1b["reused"] and exp1b["windows"] == exp1["windows"], exp1b

    # 2) 改模板升 v2（换槽/执行器/时段）→ 旧草稿纹丝不动
    entries_v2 = [
        {"weekday": 0, "slot_code": "S-ETL-02", "executor_code": "E-PIPE-02",
         "start_min": 660, "end_min": 720},
        {"weekday": 2, "slot_code": "S-BI-02", "executor_code": "E-BI-02",
         "start_min": 900, "end_min": 960},
    ]
    st, tpl2 = call("PUT", f"/templates/{code}",
                    {"title": "冒烟周模板改", "subject": "ETL", "entries": entries_v2})
    assert st == 200 and tpl2["version"] == 2, tpl2
    st, wins = call("GET", "/windows")
    for c, expect in snap.items():
        w = next(w for w in wins if w["code"] == c)
        got = (w["slot_code"], w["executor_code"], w["start_min"], w["end_min"])
        assert got == expect and w["template_version"] == 1, (c, got, expect)
    print("snapshot-kept-after-template-edit OK")

    # 3) template_version 三处可查：模板列表 / 批窗列表 / 展开审计
    st, tpls = call("GET", "/templates")
    assert next(t for t in tpls if t["code"] == code)["version"] == 2
    st, xps = call("GET", "/expansions")
    x1 = next(x for x in xps if x["template_code"] == code and x["week_start"] == week1)
    assert x1["template_version"] == 1 and len(x1["items"]) == 2, x1

    # 4) 开窗：租约实资源 == 批窗快照（v1 旧绑定，不是现行模板 v2）
    open_code = exp1["windows"][0]
    st, opened = call("POST", "/leases/open", {"window_code": open_code})
    assert st == 200, opened
    st, leases = call("GET", "/leases")
    lease = next(l for l in leases if l["lease_no"] == opened["lease_no"])
    assert (lease["slot_code"], lease["executor_code"],
            lease["start_min"], lease["end_min"]) == snap[open_code], lease
    print("lease-resources==window-snapshot OK", lease["lease_no"])

    # 5) 占用中再改模板（v3）→ live 批窗与租约都不被静默改
    st, _ = call("PUT", f"/templates/{code}",
                 {"title": "冒烟周模板改3", "subject": "ETL", "entries": entries_v1})
    st, wins = call("GET", "/windows")
    w_live = next(w for w in wins if w["code"] == open_code)
    assert w_live["status"] == "live"
    assert (w_live["slot_code"], w_live["executor_code"]) == snap[open_code][:2]
    st, leases = call("GET", "/leases")
    lease2 = next(l for l in leases if l["lease_no"] == opened["lease_no"])
    assert lease2["status"] == "open" and lease2["slot_code"] == snap[open_code][0]
    st, _ = call("POST", "/leases/close", {"lease_no": opened["lease_no"]})
    assert st == 200
    print("live-occupancy-untouched OK")

    # 5b) live 批窗不可作废
    st, opened2 = call("POST", "/leases/open", {"window_code": exp1["windows"][1]})
    assert st == 200, opened2
    st, rej = call("DELETE", f"/windows/{exp1['windows'][1]}")
    assert st == 409, rej
    call("POST", "/leases/close", {"lease_no": opened2["lease_no"]})

    # 6) 并发展开同模板同周 → 不双份草稿
    st, dash2 = call("GET", "/dashboard")
    results: list[tuple[int, dict]] = []

    def do_expand():
        results.append(call("POST", f"/templates/{code}/expand",
                            {"week_start": week2}))

    threads = [threading.Thread(target=do_expand) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert all(st == 200 for st, _ in results), results
    assert sum(1 for _, r in results if not r.get("reused")) == 1, results
    assert all(len(r["windows"]) == 2 for _, r in results), results
    st, dash3 = call("GET", "/dashboard")
    assert dash3["draft_sessions"] == dash2["draft_sessions"] + 2, dash3
    print("concurrent-expand-no-duplicates OK")

    # 7) 并发改模板与开窗 → 租约必须等于批窗快照，无半截重绑
    st, exp2 = call("POST", f"/templates/{code}/expand", {"week_start": week2})
    target = exp2["windows"][0]
    st, wins = call("GET", "/windows")
    w_target = next(w for w in wins if w["code"] == target)
    expect_snap = (w_target["slot_code"], w_target["executor_code"],
                   w_target["day"], w_target["start_min"], w_target["end_min"])
    open_out: list[tuple[int, dict]] = []

    def do_edit():
        call("PUT", f"/templates/{code}",
             {"title": "并发改版", "subject": "BI", "entries": entries_v2})

    def do_open():
        open_out.append(call("POST", "/leases/open", {"window_code": target}))

    t_edit, t_open = threading.Thread(target=do_edit), threading.Thread(target=do_open)
    t_edit.start()
    t_open.start()
    t_edit.join()
    t_open.join()
    assert open_out[0][0] == 200, open_out
    lease_no = open_out[0][1]["lease_no"]
    st, leases = call("GET", "/leases")
    lease3 = next(l for l in leases if l["lease_no"] == lease_no)
    got_snap = (lease3["slot_code"], lease3["executor_code"],
                lease3["day"], lease3["start_min"], lease3["end_min"])
    assert got_snap == expect_snap, (got_snap, expect_snap)
    call("POST", "/leases/close", {"lease_no": lease_no})
    print("concurrent-edit-vs-open-atomic OK")

    # 8) week3：展开 → 草稿全作废 → 改模板升版 → 重展开须按现行版本取快照
    st, exp_w3 = call("POST", f"/templates/{code}/expand", {"week_start": week3})
    assert st == 200 and not exp_w3["reused"], exp_w3
    for c in exp_w3["windows"]:
        st, _ = call("DELETE", f"/windows/{c}")
        assert st == 200, c
    st, tpl5 = call("PUT", f"/templates/{code}",
                    {"title": "重展开版", "subject": "ETL", "entries": entries_v1})
    assert st == 200, tpl5
    st, exp3 = call("POST", f"/templates/{code}/expand", {"week_start": week3})
    assert st == 200 and not exp3["reused"], exp3
    assert exp3["template_version"] == tpl5["version"], (exp3, tpl5)
    st, wins = call("GET", "/windows")
    w_new = next(w for w in wins if w["code"] == exp3["windows"][0])
    assert w_new["template_version"] == tpl5["version"]
    assert (w_new["slot_code"], w_new["executor_code"],
            w_new["start_min"], w_new["end_min"]) == (
        entries_v1[0]["slot_code"], entries_v1[0]["executor_code"],
        entries_v1[0]["start_min"], entries_v1[0]["end_min"]), w_new
    print("re-expand-after-discard OK")

    # week1/week2 有已结束批窗 → 封存，重展开仍复用旧审计，不双份
    st, exp1c = call("POST", f"/templates/{code}/expand", {"week_start": week1})
    assert st == 200 and exp1c["reused"] and exp1c["template_version"] == 1, exp1c
    st, exp2c = call("POST", f"/templates/{code}/expand", {"week_start": week2})
    assert st == 200 and exp2c["reused"], exp2c
    print("sealed-week OK")


def main() -> None:
    base_smoke()
    template_smoke()
    print("SMOKE OK")


if __name__ == "__main__":
    main()
