import { useEffect, useState } from "react";
import { api } from "../api";

export default function Home() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api
      .dashboard()
      .then(setD)
      .catch((e) => setErr(e.message));
  }, []);

  if (err) return <div className="msg err">{err}</div>;
  if (!d) return <div className="panel">加载中…</div>;

  return (
    <section className="panel">
      <h2>今日水位 · {d.fixture_day}</h2>

      {/* 版本徽章：只认真快照（由 expansions 实查），无展开不亮灯 */}
      <div className="row-actions" style={{ marginBottom: 12 }}>
        {d.snapshot_badge ? (
          <span className="tag live">
            现行快照 {d.snapshot_badge} · {d.snapshot_badge_template}·v
            {d.snapshot_badge_version}
          </span>
        ) : (
          <span className="tag">暂无展开快照</span>
        )}
        <span className={`tag ${d.watermarks_consistent ? "live" : "bad"}`}>
          水位对账{d.watermarks_consistent ? "一致" : "撕裂"}：水位 {d.watermark_open_leases}
          / 实存在途租约 {d.actual_open_leases}
        </span>
        <span className={`tag ${d.pinning_consistent ? "live" : "bad"}`}>
          快照钉扎{d.pinning_consistent ? "一致" : "异常"}
        </span>
      </div>

      {!d.pinning_consistent && (
        <div className="msg err" style={{ marginBottom: 10 }}>
          {d.unpinned_template_windows > 0 &&
            `无钉扎模板批窗 ${d.unpinned_template_windows} 个；`}
          {d.dual_current_snapshots?.length > 0 &&
            `同周双现行快照：${d.dual_current_snapshots
              .map((x) => `${x.template_code}@${x.week_start}[${x.snapshots.join(",")}]`)
              .join("；")}；`}
          {d.orphan_snapshot_pins?.length > 0 &&
            `孤钉快照：${d.orphan_snapshot_pins.join("、")}`}
        </div>
      )}

      <div className="stats">
        <div className="stat">
          在途租约
          <b>{d.open_leases}</b>
        </div>
        <div className="stat">
          冲突计数
          <b>{d.conflict_count}</b>
        </div>
        <div className="stat">
          占用中
          <b>{d.live_sessions}</b>
        </div>
        <div className="stat">
          待开窗
          <b>{d.draft_sessions}</b>
        </div>
      </div>
      <p style={{ marginTop: 12 }}>
        <small>
          已钉快照批窗 {d.pinned_windows} 个；口径：开窗预检与租约只认批窗快照行，
          改模板只升版不回写。
        </small>
      </p>
    </section>
  );
}
