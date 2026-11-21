"""总览口径（快照臂）。

版本徽章与水位一律从实存表算，不读任何 settings 里的"涂漆"标记：
  * 每个模板批窗必须带 snapshot_id，且其值能回指 expansions 审计行；
  * 同一 (模板, 周) 只允许一个现行快照世代，双快照即 drift；
  * open_leases 水位必须等于 leases 表 status='open' 实存行数；
  * live 批窗数必须等于在途租约数。
"""
from __future__ import annotations

import sqlite3


def _watermark(conn: sqlite3.Connection, key: str) -> int:
    row = conn.execute(
        "SELECT value FROM watermarks WHERE key=?", (key,)
    ).fetchone()
    return int(row["value"]) if row else 0


def build_overview(conn: sqlite3.Connection, base: dict) -> dict:
    out = dict(base)

    wm_open = _watermark(conn, "open_leases")
    actual_open = conn.execute(
        "SELECT COUNT(*) c FROM leases WHERE status='open'"
    ).fetchone()["c"]
    live_windows = conn.execute(
        "SELECT COUNT(*) c FROM windows WHERE status='live'"
    ).fetchone()["c"]

    # 现行快照世代：template_code -> 该周仍存留批窗实际钉着的 snapshot 集合
    rows = conn.execute(
        "SELECT template_code, template_version, snapshot_id, status "
        "FROM windows WHERE template_code IS NOT NULL"
    ).fetchall()
    unpinned = [r for r in rows if not r["snapshot_id"]]

    # 双现行检测：同一模板同周（由 snapshot 反查 week_start）出现两套 snapshot
    week_snaps: dict[tuple[str, str], set[str]] = {}
    snap_weeks = {
        r["id"]: (r["template_code"], r["week_start"])
        for r in conn.execute("SELECT id, template_code, week_start FROM expansions")
    }
    for r in rows:
        sid = r["snapshot_id"]
        if not sid or not sid.startswith("SNAP-"):
            continue
        exp_id = int(sid.removeprefix("SNAP-"))
        hit = snap_weeks.get(exp_id)
        if hit is None:
            continue
        week_snaps.setdefault(hit, set()).add(sid)
    dual_current = [
        {"template_code": k[0], "week_start": k[1], "snapshots": sorted(v)}
        for k, v in week_snaps.items()
        if len(v) > 1
    ]

    # 孤钉：windows.snapshot_id 回指不到任何 expansions 行
    known_exp = {f"SNAP-{eid:08d}" for eid in snap_weeks}
    orphan_pins = sorted(
        {r["snapshot_id"] for r in rows if r["snapshot_id"] and r["snapshot_id"] not in known_exp}
    )

    out["pinned_windows"] = len(rows) - len(unpinned)
    out["unpinned_template_windows"] = len(unpinned)
    out["dual_current_snapshots"] = dual_current
    out["orphan_snapshot_pins"] = orphan_pins
    out["watermark_open_leases"] = wm_open
    out["actual_open_leases"] = actual_open
    out["watermarks_consistent"] = (
        wm_open == actual_open and live_windows == actual_open
    )
    out["pinning_consistent"] = (
        not unpinned and not dual_current and not orphan_pins
    )
    # 总览版本徽章：取最近一次展开的真快照，无展开则不亮灯（绝不伪造）
    latest = conn.execute(
        "SELECT id, template_code, template_version FROM expansions "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if latest is not None:
        out["snapshot_badge"] = f"SNAP-{latest['id']:08d}"
        out["snapshot_badge_template"] = latest["template_code"]
        out["snapshot_badge_version"] = latest["template_version"]
    return out
